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
import yaml

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_choices import (
    attachment_reference_page,
    requirement_digest,
)
from brz2obsidian.application.update_contracts import UpdatePreparation
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.contracts import OutputIdentity
from brz2obsidian.core import inspect_review_choices
from brz2obsidian.vault_check import check_vault
from tests.application.test_format_transition_native import user_git_state
from tests.application.test_graph_workflow import graph_archive
from tests.application.test_onboarding_completion import authored_files
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


def use_incoming(operations, prepared, *, resolved_only=False):
    for _ in range(3 * len(prepared.review.proposal.changes) + 1):
        plan = prepared.review
        if plan.ready:
            return prepared
        if resolved_only and not plan.requirements:
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


def fresh_resume(vault, output, *, expected_code="unchanged"):
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
        "code": expected_code,
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


def test_type_tag_update_inputs_preserve_qualified_reference_and_video_versions(
    tmp_path,
):
    for version, uri, title in (
        (
            1,
            "https://www.youtube.com/watch?index=00&list=original%2Fcontext&v=SYNTHVID001",
            "Original video",
        ),
        (
            2,
            "https://www.youtube.com/watch?list=updated%2Bcontext&v=SYNTHVID002&index=next",
            "Updated video",
        ),
    ):
        source = update_source(tmp_path / f"source{version}.brz", version=version)
        vault = tmp_path / f"vault{version}"
        result = default_workflow().convert(source, vault)
        assert result.outcome == "clean", result.issues
        assert f"Source G v{version}.".encode() in (vault / "Notes/G.md").read_bytes()
        independent = (vault / "Notes/Independent.md").read_bytes()
        assert f"- [{title}](<{uri}>)".encode() in independent
        video_id = "SYNTHVID001" if version == 1 else "SYNTHVID002"
        assert (
            f'<iframe src="https://www.youtube.com/embed/{video_id}?start=0"'.encode()
            in independent
        )
        label = "Original reference" if version == 1 else "Updated reference"
        assert (
            f"[[Notes/Independent.md|{label}]]".encode()
            in (vault / "Notes/D.md").read_bytes()
        )
        record = json.loads((vault / "migration-record.json").read_bytes())
        assert {r["item_key"] for r in record["item_targets"] if r["created"]} == {
            "00000000-0000-0000-0000-000000000001",
            *(IDS[name] for name in "ABCDEFGT"),
            INDEPENDENT,
        }
        external = next(a for a in record["asset_targets"] if a.get("external_uri"))
        assert external["external_uri"] == external["resource_link"] == uri
        assert external["video_presentation"]["embed_uri"] == (
            f"https://www.youtube.com/embed/{video_id}?start=0"
        )
        raw = next(
            r
            for group in record["original_evidence"]
            for r in group["records"]
            if r.get("Type") == 3
        )
        assert raw["Name"] == title and raw["Location"] == uri
        assert raw["VideoHtml"] == (
            "<iframe width='100%' height='100%' "
            f"src='https://www.youtube.com/embed/{video_id}?start=0' "
            "frameborder='0'></iframe>"
        )
        source_reference = next(
            reference
            for item in record["item_targets"]
            for document in item["documents"]
            for reference in document["references"]
            if reference["target"] == INDEPENDENT
        )
        assert source_reference["source_target"] == (
            "brain://api.thebrain.com/EREREREREUGBEREREREREQ/"
            f"AAAAAAAAAAAAAAAAAAAAEw/version-{version}"
        )


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
    d = vault / "Notes/D.md"
    d.write_bytes(d.read_bytes().replace(b"Source D v1.", b"Local D writing."))
    g = vault / "Notes/G.md"
    g.write_bytes(g.read_bytes().replace(b"Source G v1.", b"Local G writing."))
    independent = vault / "Notes/Independent.md"
    independent.write_bytes(
        independent.read_bytes().replace(
            b"Source Independent v1.", b"Local independent writing."
        )
    )
    original_c, original_i = c.read_bytes(), independent.read_bytes()
    original_d, original_g = d.read_bytes(), g.read_bytes()
    template_path = "Templates/New note.md"
    template = (vault / template_path).read_bytes() + b"\nLocal template prose.\n"
    (vault / template_path).write_bytes(template)
    configuration = b'{"user":"preserve N1 configuration"}\r\n'
    (vault / ".obsidian/app.json").write_bytes(configuration)
    user_before = user_git_state(vault)
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
    renamed.write_bytes(
        renamed.read_bytes().replace(
            b'appearance_category: "[[Categories/A.md]]"',
            b'appearance_category: "[[Categories/E.md]]"',
        )
    )
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
    before_unready = authored_files(vault)
    checkpoint_before = operations.read_checkpoint(vault).locator
    refused = measured(
        update_root, "unresolved-apply", operations.apply_update, refreshed.preparation
    )
    assert refused.code == "review_not_ready" and refused.application is None
    assert authored_files(vault) == before_unready
    assert operations.read_checkpoint(vault).locator == checkpoint_before
    assert user_git_state(vault) == user_before
    prepared = refreshed.preparation
    rename = next(
        r for r in inspect_review_choices(prepared.review) if r.domain == "rename"
    )
    kept_path = operations.resolve_update_choice(
        prepared,
        requirement_id=rename.requirement_id,
        choice="keep_path",
        assumptions_digest=requirement_digest(rename),
    )
    assert kept_path.code == "accepted", kept_path.code
    prepared = choose_current(
        operations, kept_path.preparation, IDS["B"], "keep-local-B"
    )
    prepared = choose_current(operations, prepared, IDS["G"], "keep-memory-G")
    asset = next(
        row
        for row in inspect_review_choices(prepared.review)
        if row.domain == "attachment"
        and next(
            change.item_id
            for change in prepared.review.proposal.changes
            if change.change_id == row.change_id
        )
        == ICON
    )
    references, total, following = attachment_reference_page(
        prepared, asset.requirement_id
    )
    assert total == len(references) and following is None
    kept_icon = operations.resolve_update_choice(
        prepared,
        requirement_id=asset.requirement_id,
        choice="current",
        assumptions_digest=requirement_digest(asset),
        references=tuple(
            {"reference_id": row.reference_id, "choice": "keep_current"}
            for row in references
        ),
    )
    assert kept_icon.code == "accepted", kept_icon.code
    prepared = kept_icon.preparation
    expected = {IDS["B"]: renamed.read_bytes(), IDS["G"]: original_g}
    # These are deliberately submitted user-choice bytes, independently checked
    # against source facts and the original/local/incoming/result boundaries.
    old_uri = (
        b"https://www.youtube.com/watch?index=00&list=original%2Fcontext&v=SYNTHVID001"
    )
    new_uri = (
        b"https://www.youtube.com/watch?list=updated%2Bcontext&v=SYNTHVID002&index=next"
    )
    expected[INDEPENDENT] = (
        original_i.replace(old_uri, new_uri)
        .replace(b"Original video", b"Updated video")
        .replace(b"/embed/SYNTHVID001?", b"/embed/SYNTHVID002?")
    )
    for item, old_paragraph, local in (
        (IDS["C"], b"Source C v2.", b"Local C writing."),
        (IDS["D"], b"Source D v2.", b"Local D writing."),
    ):
        change = next(c for c in prepared.review.proposal.changes if c.item_id == item)
        expected[item] = change.incoming.data.replace(old_paragraph, local).replace(
            b"[[Categories/B.md", b"[[Categories/B local.md"
        )
    for item in (INDEPENDENT, IDS["C"], IDS["D"]):
        prepared = choose_edited(
            operations, prepared, item, expected[item], "merge-v2:" + item
        )
    prepared = measured(
        update_root,
        "v2-resolve",
        use_incoming,
        operations,
        prepared,
        resolved_only=True,
    )
    # Related B/D/F links name selected file versions. Explicitly resubmitting
    # these chosen texts binds their references after the other text choices.
    prepared = choose_edited(
        operations, prepared, IDS["B"], expected[IDS["B"]], "requalify-B"
    )
    f_change = next(
        c for c in prepared.review.proposal.changes if c.item_id == IDS["F"]
    )
    prepared = choose_edited(
        operations, prepared, IDS["F"], f_change.incoming.data, "requalify-F"
    )
    assert prepared.review.ready, prepared.review.blockers
    memory = next(
        a for a in prepared.review.approvals if a.decision_id == "keep-memory-G"
    ).source_memory
    assert memory is not None and memory.choice == "keep_vault"
    saved_ready = measured(
        update_root, "v2-ready-save", operations.save_update, prepared
    )
    assert saved_ready.code == "saved", saved_ready.code
    (update_root / "v2-ready.json").write_text(
        saved_ready.preparation.model_dump_json()
    )
    applied = measured(
        update_root, "v2-apply", operations.apply_update, saved_ready.preparation
    )
    assert applied.status == "applied", applied.code
    assert applied.application.history == "terminal"
    assert (
        c.read_bytes(),
        d.read_bytes(),
        independent.read_bytes(),
        g.read_bytes(),
    ) == (expected[IDS["C"]], expected[IDS["D"]], expected[INDEPENDENT], original_g)
    assert renamed.read_bytes() == expected[IDS["B"]]
    assert not b.exists()
    assert (vault / icon_path).read_bytes() == YELLOW
    assert (vault / template_path).read_bytes() == template
    assert (vault / ".obsidian/app.json").read_bytes() == configuration
    assert user_git_state(vault) == user_before
    b_properties = yaml.safe_load(
        renamed.read_text(encoding="utf-8").split("---", 2)[1]
    )
    c_properties = yaml.safe_load(c.read_text(encoding="utf-8").split("---", 2)[1])
    assert b_properties["categories"] == ["[[Categories/A.md]]", "[[Categories/E.md]]"]
    assert b_properties["appearance_category"] == "[[Categories/E.md]]"
    assert b_properties["aliases"] == ["My B"] and b_properties["priority"] == 4
    assert b_properties["tags"] == c_properties["tags"] == ["categories", "T"]
    assert c_properties["categories"] == ["[[Categories/B local.md]]"]
    assert c_properties["appearance_category"] == "[[Categories/B local.md]]"
    record = json.loads((vault / "migration-record.json").read_bytes())
    targets = {r["item_key"]: r for r in record["item_targets"]}
    assert sum(r["created"] for r in targets.values()) == 10
    assert len({r["relative_path"] for r in targets.values() if r["created"]}) == 10
    assert targets[IDS["B"]]["relative_path"] == "Categories/B local.md"
    assert not targets[IDS["U"]]["created"]
    assert {
        (r["definition_key"], r["item_key"])
        for r in record["classification_assignments"]
    } == {
        (IDS[a], IDS[b])
        for a, b in (
            ("E", "B"),
            ("B", "C"),
            ("A", "E"),
            ("C", "D"),
            ("E", "F"),
            ("A", "G"),
        )
    }
    assert (
        len(
            [
                r
                for r in record["relationships"]
                if r["kind"] in ("hierarchy", "related")
            ]
        )
        == 6
    )
    assert {(r["tag_key"], r["item_key"]) for r in record["tag_memberships"]} == {
        (IDS["T"], IDS["B"]),
        (IDS["T"], IDS["C"]),
        (IDS["T"], IDS["U"]),
    }
    assert "Nested source tag: [[Notes/U.md|U]] (#U)" in (
        vault / "Tag memberships.md"
    ).read_text(encoding="utf-8")
    assert check_vault(vault).outcome == "clean"
    # The retained preimages also specify later Undo precisely: C's new source
    # tagT is converter-owned, while its local prose must survive the reversal.
    (update_root / "v2-undo-preimages.json").write_text(
        json.dumps(
            {"C": original_c.hex(), "D": original_d.hex(), "I": original_i.hex()}
        )
    )


def choose_edited(operations, prepared, item, raw, decision):
    plan = prepared.review
    comparison = next(
        c for c in plan.proposal.changes if c.item_id == item and c.facet == "content"
    )
    result = operations.resolve_update(
        prepared,
        action(plan, comparison, choice="edited", decision_id=decision),
        edited=raw,
    )
    assert result.code == "accepted", (item, result.code)
    return result.preparation
