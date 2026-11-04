"""Preservation-first onboarding at the shared public Operations seam."""

import json
from types import SimpleNamespace

import pytest

from brz2obsidian.application.operations import Operations


def owned_case():
    import tempfile
    from pathlib import Path
    from uuid import uuid4

    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-281-"))
    owner = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(owner))
    evidence = Path(__file__).resolve().parents[2] / "tmp/issue-281/fixtures"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (owner["owner"] + ".json")).write_text(json.dumps(owner))
    return root


def legacy_inputs(tmp_path, monkeypatch=None, *, opaque=False):
    from brz2obsidian.application import SourceModuleBinding, Workflow
    from brz2obsidian.application.vault_contracts import VaultFile
    from brz2obsidian.obsidian import ObsidianRenderer
    from brz2obsidian.publication import FilesystemPublisher
    from brz2obsidian.publication.vault_native import observe_file
    from tests.application.test_module_seams import METADATA
    from tests.reconciliation.test_resolution import preflight
    from tests.support.folio_source import FOLIO_POLICY, FolioSourceModule

    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "collection": "legacy-collection",
                "start": "entry:opening",
                "entries": [
                    {
                        "key": "entry:opening",
                        "seed": "00000001000040008000000000000000",
                        "title": "Opening",
                    }
                ],
                "connections": [],
                "assets": [],
                "documents": [],
            }
        )
    )
    vault = tmp_path / "vault"
    vault.mkdir()
    authored = b'---\r\nsource_collection_id: legacy-collection\r\nsource_item_id: "entry:opening"\r\n---\r\nAuthored older text.\r\n'
    (vault / "Home \u2014 Opening.md").write_bytes(authored)
    (vault / "Personal.bin").write_bytes(b"\x00\xffprivate\r\n")
    if opaque:
        (vault / "MIGRATION REPORT.md").write_bytes(
            b"\xffUnsupported authored report.\r\n"
        )

    def inventory():
        rows = []
        for path in sorted(p for p in vault.rglob("*") if p.is_file()):
            info, sha, _, physical = observe_file(vault, path, prefix_limit=0)
            rows.append(
                VaultFile(
                    path=path.relative_to(vault).as_posix(),
                    mode="100644",
                    size=info.st_size,
                    sha256=sha,
                    identity=physical,
                    tracked=True,
                    excluded=False,
                    exclusion=None,
                )
            )
        return tuple(rows)

    history = SimpleNamespace(
        status="absent",
        checkpoint=None,
        admission=SimpleNamespace(
            vault=str(vault),
            status="supported",
            repository=SimpleNamespace(kind="root"),
            inventory=inventory(),
            inventory_complete=True,
            preflight=preflight(),
            findings=(),
            recovery_gaps=(),
        ),
    )
    workflow = Workflow(
        SourceModuleBinding(FolioSourceModule(), FOLIO_POLICY),
        ObsidianRenderer(),
        FilesystemPublisher(),
        metadata_factory=lambda: METADATA,
    )
    operations = Operations(workflow=workflow)
    if monkeypatch is not None:

        def inspection(*args, **kwargs):
            history.admission.inventory = inventory()
            return history

        monkeypatch.setattr(operations, "inspect_history", inspection)
    return operations, vault, source, authored


def test_incomplete_history_gates_onboarding_before_any_source_access(monkeypatch):
    operations = Operations()
    history = SimpleNamespace(
        status="unavailable",
        checkpoint=None,
        admission=SimpleNamespace(
            status="recovery_first",
            vault="legacy-vault",
            recovery_gaps=("Attachments/private.bin",),
            findings=(),
        ),
    )
    monkeypatch.setattr(operations, "inspect_history", lambda vault: history)
    result = operations.prepare_onboarding("legacy-vault", "unopened-source.brz")
    assert result.status == "recovery_required"
    assert result.code == "recovery_first"
    assert result.kind == "onboarding"
    assert result.next_actions == ("review_recovery",)
    assert result.recovery_gaps == ("Attachments/private.bin",)
    assert result.vault == "legacy-vault"
    assert result.preparation is None
    assert result.publication == "not_started"


def test_notes_only_onboarding_keeps_exact_current_bytes_unknown(tmp_path, monkeypatch):
    operations, vault, source, authored = legacy_inputs(tmp_path, monkeypatch)
    before = {p.name: p.read_bytes() for p in vault.iterdir()}
    result = operations.prepare_onboarding(vault, source)
    assert result.status == "prepared_review", result
    assert result.kind == "onboarding" and not result.ready
    prepared = result.preparation
    assert prepared.kind == "onboarding" and prepared.locator is None
    facts = prepared.review.facts
    assert facts.format_operation.kind == "onboarding"
    assert facts.format_operation.recorded_generation == "unknown"
    assert facts.format_operation.established_baseline is None
    assert all(
        s.baseline.status == "unknown" and s.baseline.content is None
        for s in facts.subjects
    )
    note = next(s for s in facts.subjects if s.item_id == "entry:opening")
    assert note.current.content.data == authored
    assert note.current.path == "Home \u2014 Opening.md"
    assert prepared.review.requirements
    assert not result.history_retained and result.checkpoint is None
    assert "older_checkpoints_unavailable" in result.findings
    assert {p.name: p.read_bytes() for p in vault.iterdir()} == before
    assert (vault / "Personal.bin").read_bytes() == b"\x00\xffprivate\r\n"


def test_legacy_without_repository_offers_explicit_initialization():
    from brz2obsidian.application.checkpoint_contracts import (
        VaultInitializationDecision,
    )

    root = owned_case()
    operations, vault, source, _ = legacy_inputs(root)
    before = {p.name: p.read_bytes() for p in vault.iterdir()}
    initial = operations.inspect_history(vault)
    (root / "no-repository-inspection.json").write_text(initial.model_dump_json())
    result = operations.prepare_onboarding(vault, source)
    assert result.kind == "onboarding"
    assert not result.ready and result.preparation is None
    assert result.next_actions == ("initialize_vault",), result
    assert result.status != "recovery_required", result
    assert not (vault / ".git").exists()
    assert {p.name: p.read_bytes() for p in vault.iterdir()} == before
    initialized = operations.initialize_vault(
        vault,
        decision=VaultInitializationDecision(
            schema_id="brz2obsidian.vault-initialization-decision",
            schema_version=1,
            observation_fingerprint=initial.admission.observation_fingerprint,
            choice="initialize",
        ),
    )
    assert initialized.status == "initialized_review_required", initialized
    offered = operations.prepare_onboarding(vault, source)
    assert offered.preparation is not None and not offered.ready, offered
    assert not offered.history_retained
    assert {p.name: p.read_bytes() for p in vault.iterdir() if p.is_file()} == before


@pytest.mark.parametrize(
    "mode", ("preserve", "changed_target", "missing_document", "missing_state")
)
@pytest.mark.parametrize("operation_kind", ("onboarding", "format_transition"))
def test_opaque_legacy_output_offers_exact_current_preservation(
    tmp_path, monkeypatch, mode, operation_kind
):
    from brz2obsidian.core import prepare_review, select_review_effects
    from tests.reconciliation.test_resolution import action

    operations, vault, source, _ = legacy_inputs(tmp_path, monkeypatch, opaque=True)
    offered = operations.prepare_onboarding(vault, source)
    assert offered.preparation is not None, offered
    plan = offered.preparation.review
    facts = plan.producer_facts
    if operation_kind == "format_transition":
        facts = facts.model_copy(
            update={
                "format_operation": facts.format_operation.model_copy(
                    update={
                        "kind": operation_kind,
                        "baseline_source_version": facts.format_operation.target_source_version,
                    }
                )
            }
        )
    if mode == "changed_target":
        facts = facts.model_copy(
            update={
                "format_operation": facts.format_operation.model_copy(
                    update={
                        "baseline_source_version": facts.format_operation.target_source_version,
                    }
                )
            }
        )
    if mode in ("missing_document", "missing_state"):
        context = facts.link_context
        target_id = next(
            t.target_id
            for t in context.current_targets
            if t.canonical_path == "MIGRATION REPORT.md"
        )
        context = context.model_copy(
            update={
                "current_documents": tuple(
                    d
                    for d in context.current_documents
                    if d.source_path != "MIGRATION REPORT.md"
                )
            }
            if mode == "missing_document"
            else {
                "current_target_facts": tuple(
                    s for s in context.current_target_facts if s.target_id != target_id
                )
            }
        )
        facts = facts.model_copy(update={"link_context": context})
    plan = prepare_review(facts, preflight=plan.preflight)
    updates = {"kind": operation_kind, "review": plan}
    if operation_kind == "format_transition":
        from tests.application.test_update_lifecycle_contracts import preparation

        locator = preparation().locator
        identity = plan.facts.incoming_identity
        updates["locator"] = locator.model_copy(
            update={
                "association": locator.association.model_copy(
                    update={
                        "collection_id": identity.collection_id,
                        "module_id": identity.module_id,
                    }
                )
            }
        )
    prepared = offered.preparation.model_copy(update=updates)
    report = next(
        c for c in plan.proposal.changes if c.item_id == "support:MIGRATION REPORT.md"
    )
    assert report.original is None
    assert report.current.data == b"\xffUnsupported authored report.\r\n"
    chosen = operations.resolve_update(
        prepared,
        action(
            plan,
            report,
            domain="format",
            choice="current",
            decision_id="keep-opaque-report",
        ),
    )
    if mode in ("missing_document", "missing_state"):
        assert chosen.status == "refused" and not chosen.ready
        assert not chosen.preparation.review.approvals
        return
    assert chosen.code == "accepted", chosen
    approval = next(
        a
        for a in chosen.preparation.review.approvals
        if a.decision_id == "keep-opaque-report"
    )
    assert approval.result.data == b"\xffUnsupported authored report.\r\n"
    assert not approval.source_accepted
    prepared = chosen.preparation
    if mode == "changed_target":
        home = next(
            c for c in prepared.review.proposal.changes if c.item_id == "entry:opening"
        )
        assert home.format_review.target_eligible
        changed = operations.resolve_update(
            prepared,
            action(
                prepared.review,
                home,
                domain="format",
                choice="incoming",
                decision_id="different-target-bytes",
            ),
        )
        assert changed.code == "accepted", changed
        assert next(
            a
            for a in changed.preparation.review.approvals
            if a.decision_id == "different-target-bytes"
        ).source_accepted
        prepared = changed.preparation
    while prepared.review.requirements:
        requirement = prepared.review.requirements[0]
        change = next(
            c
            for c in prepared.review.proposal.changes
            if c.change_id == requirement.change_id
        )
        kept = operations.resolve_update(
            prepared,
            action(
                prepared.review,
                change,
                domain=requirement.domain,
                choice="current",
                decision_id="keep-" + change.item_id,
            ),
        )
        assert kept.code == "accepted", kept
        prepared = kept.preparation
    effects = select_review_effects(prepared.review)
    if mode == "changed_target":
        assert not prepared.review.ready and effects.status == "refused"
    else:
        assert prepared.review.ready and effects.status == "selected", (
            prepared.review.blockers
        )
        assert [(r.path, r.content.data) for r in effects.files] == [
            ("Home \u2014 Opening.md", (vault / "Home \u2014 Opening.md").read_bytes()),
            ("MIGRATION REPORT.md", b"\xffUnsupported authored report.\r\n"),
        ]
        assert effects.remove_paths == ()
        assert not (vault / "migration-record.json").exists()
    assert (
        vault / "MIGRATION REPORT.md"
    ).read_bytes() == b"\xffUnsupported authored report.\r\n"


def test_first_saved_onboarding_resumes_unknown_original_and_current_choice():
    import subprocess
    import sys

    from tests.application.test_vault_checkpoints import git
    from tests.reconciliation.test_resolution import action

    root = owned_case()
    operations, vault, source, authored = legacy_inputs(root)
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "User.md").write_bytes(b"Staged user history.\r\n")
    git(vault, "add", "User.md")
    git(vault, "commit", "-qm", "User baseline")
    (vault / "User.md").write_bytes(b"Staged writing.\r\n")
    git(vault, "add", "User.md")
    (vault / "User.md").write_bytes(b"Unstaged writing.\r\n")
    user_before = (
        git(vault, "rev-parse", "HEAD"),
        (vault / ".git/index").read_bytes(),
        git(vault, "show-ref"),
    )
    authored_before = {p.name: p.read_bytes() for p in vault.iterdir() if p.is_file()}
    offered = operations.prepare_onboarding(vault, source)
    assert offered.preparation is not None, offered
    note = next(
        c
        for c in offered.preparation.review.proposal.changes
        if c.item_id == "entry:opening"
    )
    assert note.identity_review.status == "matched"
    chosen = operations.resolve_update(
        offered.preparation,
        action(
            offered.preparation.review,
            note,
            domain="format",
            choice="current",
            decision_id="preserve-legacy-writing",
        ),
    )
    assert chosen.code == "accepted", chosen
    saved = operations.save_update(chosen.preparation)
    assert saved.code == "saved", saved
    assert saved.kind == "onboarding" and saved.checkpoint is not None
    loaded = operations.load_update(vault)
    assert loaded.loaded is not None and not loaded.ready and not loaded.loaded.ready
    from brz2obsidian.application.update_contracts import UpdateResult

    code = """
import sys
from pathlib import Path
from brz2obsidian.application import SourceModuleBinding, Workflow
from brz2obsidian.application.operations import Operations
from brz2obsidian.obsidian import ObsidianRenderer
from brz2obsidian.publication import FilesystemPublisher
from tests.application.test_module_seams import METADATA
from tests.support.folio_source import FOLIO_POLICY, FolioSourceModule
workflow = Workflow(SourceModuleBinding(FolioSourceModule(), FOLIO_POLICY), ObsidianRenderer(), FilesystemPublisher(), metadata_factory=lambda: METADATA)
result = Operations(workflow=workflow).resume_update(sys.argv[1])
Path(sys.argv[2]).write_text(result.model_dump_json())
"""
    resumed_file = root / "fresh-resume.json"
    process = subprocess.run(
        [sys.executable, "-c", code, str(vault), str(resumed_file)],
        capture_output=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr.decode(errors="replace")
    reopened = UpdateResult.model_validate_json(resumed_file.read_text())
    assert reopened.preparation is not None, reopened
    assert reopened.kind == "onboarding"
    assert reopened.generation == 1
    assert [a.decision_id for a in reopened.preparation.review.approvals] == [
        "preserve-legacy-writing"
    ]
    current = next(
        s
        for s in reopened.preparation.review.facts.subjects
        if s.item_id == "entry:opening"
    )
    assert current.baseline.status == "unknown" and current.baseline.content is None
    assert current.current.content.data == authored
    assert {
        p.name: p.read_bytes() for p in vault.iterdir() if p.is_file()
    } == authored_before
    assert (
        git(vault, "rev-parse", "HEAD"),
        (vault / ".git/index").read_bytes(),
        git(vault, "show-ref", "--heads"),
    ) == (user_before[0], user_before[1], user_before[2])
