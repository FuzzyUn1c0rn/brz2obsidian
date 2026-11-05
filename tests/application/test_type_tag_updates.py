"""Public BRZ update journeys for direct type members and provider chains."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_choices import requirement_digest
from brz2obsidian.application.update_contracts import UpdatePreparation
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.contracts import OutputIdentity
from brz2obsidian.core import inspect_review_choices
from tests.application.test_graph_workflow import graph_archive
from tests.application.test_update_lifecycle import git
from tests.reconciliation.test_resolution import action
from tests.support.type_tag_sources import BRAIN, ICON, IDS, PNG, brz_source
from tests.support.type_tag_updates import GREEN, INDEPENDENT, YELLOW, update_source


@pytest.fixture
def update_root():
    # The supported history route requires a vault outside the parent repository.
    # Retain every run, including failed admission/publication evidence.
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-r292-m4-"))
    evidence = Path(__file__).resolve().parents[2] / "tmp/r292-m4/fixtures"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (root.name + ".json")).write_text(
        json.dumps({"root": str(root), "purpose": "synthetic public update journey"}),
        encoding="utf-8",
    )
    return root


def measured(root, label, call, *args, **kwargs):
    started = time.perf_counter()
    result = call(*args, **kwargs)
    with (root / "operation-timings.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {
                    "stage": label,
                    "seconds": time.perf_counter() - started,
                    "status": getattr(result, "status", None),
                    "code": getattr(result, "code", None),
                }
            )
            + "\n"
        )
    return result


def use_incoming(operations, prepared):
    for _ in range(3 * len(prepared.review.proposal.changes) + 1):
        plan = prepared.review
        if plan.ready:
            return prepared
        assert plan.requirements, plan.blockers
        requirement = plan.requirements[0]
        offered = next(
            r
            for r in inspect_review_choices(plan)
            if r.requirement_id == requirement.requirement_id
        )
        choice = (
            "current"
            if requirement.domain == "configuration"
            else "restore_incoming"
            if requirement.domain == "restoration"
            else "keep_path"
            if requirement.domain == "rename"
            else "approve"
            if "approve" in offered.enabled_choices
            else "incoming"
        )
        assert choice in offered.enabled_choices, (
            requirement.domain,
            offered.enabled_choices,
        )
        result = operations.resolve_update_choice(
            prepared,
            requirement_id=offered.requirement_id,
            choice=choice,
            assumptions_digest=requirement_digest(offered),
        )
        assert result.code == "accepted", (requirement.domain, result.code)
        prepared = result.preparation
    raise AssertionError("The finite explicit incoming review did not complete")


def seed_current(root, *, source=None, onboarding=False):
    source = source or brz_source(root / "v1.brz")
    bootstrap = (
        graph_archive(root / "bootstrap.brz", {1: "Entry"}) if onboarding else source
    )
    vault = root / "vault"
    converted = default_workflow().convert(bootstrap, vault)
    assert converted.outcome == "clean", converted.issues
    original = root / "original-v1"
    if not onboarding:
        shutil.copytree(vault, original)
    identity = OutputIdentity(
        collection_id=BRAIN,
        module_id="thebrain-brz",
        module_version="11",
        profile_id="thebrain-format5-reviewed",
        profile_version="11",
        output_format=8,
        settings_digest=hashlib.sha256(b"{}").hexdigest(),
    )
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    operations = Operations()
    if onboarding:
        from tests.application.test_onboarding_completion import keep_current

        (vault / "Manual.md").write_bytes(b"Independent user baseline.\r\n")
        (vault / "Attachments").mkdir(exist_ok=True)
        (vault / "Attachments/manual.bin").write_bytes(
            b"\x00\xffIndependent binary.\r\n"
        )
        git(vault, "add", "Manual.md", "Attachments/manual.bin")
        git(vault, "commit", "-qm", "Independent user history")
        git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
        (vault / "Manual.md").write_bytes(b"Staged independent writing.\r\n")
        git(vault, "add", "Manual.md")
        (vault / "Manual.md").write_bytes(b"Unstaged independent writing.\r\n")
        offered = measured(
            root,
            "onboarding-prepare",
            operations.prepare_onboarding,
            vault,
            bootstrap,
            original_source=bootstrap,
        )
        assert offered.preparation is not None, (offered.status, offered.code)
        established = measured(
            root, "onboarding-resolve", keep_current, operations, offered.preparation
        )
        assert established.review.ready, established.review.blockers
        saved = measured(root, "onboarding-save", operations.save_update, established)
        assert saved.code == "saved", (saved.status, saved.code)
        applied = measured(
            root, "onboarding-apply", operations.apply_update, saved.preparation
        )
        assert applied.status in ("applied", "no_content_change"), (
            applied.status,
            applied.code,
        )
        assert applied.publication == "complete"
        establish_family(root, operations, vault, source, original)
        return operations, vault, source, original
    captured = operations.capture_checkpoint(
        vault,
        original,
        vault_id="r292-vault",
        import_id="r292-import",
        identity=identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert captured.status == "captured", captured
    return operations, vault, source, original


def establish_family(root, operations, vault, source, original):
    family = measured(
        root, "family-v1-prepare", operations.prepare_update, vault, source
    )
    assert family.preparation is not None, (family.status, family.code)
    established = measured(
        root, "family-v1-resolve", use_incoming, operations, family.preparation
    )
    shutil.copytree(established.payload_directory, original)
    saved = measured(root, "family-v1-save", operations.save_update, established)
    assert saved.code == "saved", (saved.status, saved.code)
    applied = measured(
        root, "family-v1-apply", operations.apply_update, saved.preparation
    )
    assert applied.status == "applied", (applied.status, applied.code)
    assert (
        applied.application.history == "terminal" and applied.application.result_commit
    )
    assert established.kind == "source_update"


def test_current_type_tag_vault_prepares_same_source_without_format_transition(
    update_root,
):
    operations, vault, source, original = seed_current(update_root)
    icon_path = "Attachments/0000000000000000000000000000000a/Icon.png"
    with operations.inspect_update_inputs(vault) as observed:
        proofs = observed.read_attachment_ownership(
            locator=observed.history.checkpoint.locator, paths=(icon_path,)
        )
    assert len(proofs) == 1
    assert proofs[0].identity.item_id == ICON and proofs[0].facet == "asset"
    assert proofs[0].payload_sha256 == hashlib.sha256(PNG).hexdigest()
    assert proofs[0].source_path == icon_path
    result = operations.prepare_update(vault, source)
    assert result.status == "prepared_review", result
    assert result.ready, (
        result.preparation.review.blockers,
        result.preparation.review.requirements,
    )
    assert result.preparation.review.facts.baseline_identity.output_format == 8
    assert result.preparation.review.facts.incoming_identity.output_format == 8
    assert result.preparation.retained_source_provenance
    assert all(
        c.disposition == "no_change" for c in result.preparation.review.proposal.changes
    )
    applied = operations.apply_update(result.preparation)
    assert (applied.status, applied.publication) == (
        "no_content_change",
        "not_published",
    )
    assert (vault / "Categories/B.md").read_bytes() == (
        original / "Categories/B.md"
    ).read_bytes()


def fresh_resume(vault, output):
    checkout = Path(__file__).resolve().parents[2]
    script = (
        "import json,pathlib,sys\n"
        "import brz2obsidian.application.operations as module\n"
        "assert pathlib.Path(module.__file__).resolve() == pathlib.Path(sys.argv[3]).resolve(), module.__file__\n"
        "from brz2obsidian.application.operations import Operations\n"
        "ops=Operations()\n"
        "loaded=ops.load_update(sys.argv[1])\n"
        "resumed=ops.resume_update(sys.argv[1])\n"
        "if resumed.preparation is not None:\n"
        " pathlib.Path(sys.argv[2]).write_text(resumed.preparation.model_dump_json(),encoding='utf-8')\n"
        "print(json.dumps({'loaded_code':loaded.code,'loaded_ready':loaded.ready,'status':resumed.status,'code':resumed.code}))\n"
    )
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(vault),
            str(output),
            str(checkout / "src/brz2obsidian/application/operations.py"),
        ],
        env=os.environ
        | {"PYTHONPATH": os.pathsep.join((str(checkout / "src"), str(checkout)))},
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    summary = json.loads(process.stdout)
    assert summary == {
        "loaded_code": "revalidation_required",
        "loaded_ready": False,
        "status": "prepared_review",
        "code": "unchanged",
    }, summary
    return UpdatePreparation.model_validate_json(output.read_bytes())


def choose_current(operations, prepared, item, decision):
    plan = prepared.review
    change = next(
        c for c in plan.proposal.changes if c.item_id == item and c.facet == "content"
    )
    selected = operations.resolve_update(
        prepared, action(plan, change, choice="current", decision_id=decision)
    )
    assert selected.code == "accepted", selected.code
    return selected.preparation


def test_type_tag_changes_survive_partial_save_fresh_resume_selective_refresh_and_apply(
    update_root,
):
    source = update_source(update_root / "v1.brz")
    operations, vault, _, original = seed_current(
        update_root, source=source, onboarding=True
    )
    exercise_partial_update(update_root, operations, vault, original)


def exercise_partial_update(update_root, operations, vault, original):
    icon_path = "Attachments/0000000000000000000000000000000a/Icon.png"
    assert (original / icon_path).read_bytes() == GREEN
    b = vault / "Categories/B.md"
    renamed = vault / "Categories/B local.md"
    b.rename(renamed)
    for file in vault.rglob("*.md"):
        raw = file.read_bytes()
        changed = raw.replace(b"[[Categories/B.md", b"[[Categories/B local.md")
        if changed != raw:
            file.write_bytes(changed)
    raw = renamed.read_bytes().replace(
        b"aliases: []", b'aliases:\n  - "My B"\npriority: 4'
    )
    raw = raw.replace(
        b'  - "[[Categories/A.md]]"',
        b'  - "[[Categories/A.md]]"\n  - "[[Categories/E.md]]"',
    )
    renamed.write_bytes(raw.replace(b"Source B v1.", b"Local B writing."))
    c = vault / "Categories/C.md"
    c.write_bytes(c.read_bytes().replace(b"Source C v1.", b"Local C writing."))
    independent = vault / "Notes/Independent.md"
    independent.write_bytes(
        independent.read_bytes().replace(
            b"Source Independent v1.", b"Local independent writing."
        )
    )
    original_c, original_i = c.read_bytes(), independent.read_bytes()
    incoming = update_source(update_root / "v2.brz", version=2)
    offered = measured(
        update_root, "v2-prepare", operations.prepare_update, vault, incoming
    )
    assert offered.status == "prepared_review", (offered.status, offered.code)
    prepared = offered.preparation
    current_b = next(
        s
        for s in prepared.review.facts.subjects
        if s.item_id == IDS["B"] and s.facet == "content"
    )
    assert current_b.current.path == "Categories/B local.md"
    assert current_b.current.content.data == renamed.read_bytes()
    assert (
        current_b.baseline.content.data == (original / "Categories/B.md").read_bytes()
    )
    assert b'appearance_category: "[[Categories/E.md]]"' in current_b.incoming.data
    for item, decision in (
        (IDS["C"], "keep-dependent-C"),
        (INDEPENDENT, "keep-independent-I"),
    ):
        prepared = choose_current(operations, prepared, item, decision)
    prior = tuple(prepared.review.approvals)
    assert [a.decision_id for a in prior] == ["keep-dependent-C", "keep-independent-I"]
    assert [a.result.data for a in prior] == [original_c, original_i]
    saved = measured(update_root, "partial-save", operations.save_update, prepared)
    assert saved.code == "saved", (saved.status, saved.code)
    resumed = measured(
        update_root,
        "partial-fresh-resume",
        fresh_resume,
        vault,
        update_root / "resumed-partial.json",
    )
    assert resumed.review.approvals == prior
    assert not resumed.review.ready
    (vault / icon_path).write_bytes(YELLOW)
    refreshed = measured(
        update_root, "asset-refresh", operations.refresh_update, resumed
    )
    assert refreshed.preparation is not None, (refreshed.status, refreshed.code)
    assert [a.decision_id for a in refreshed.preparation.review.approvals] == [
        "keep-independent-I"
    ]
    assert refreshed.preparation.review.approvals[0] == prior[1]
    assert (c.read_bytes(), independent.read_bytes()) == (original_c, original_i)
    assert not refreshed.ready
