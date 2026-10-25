"""Actual historical format transition precedes one distinct ordinary source update."""

import hashlib
import subprocess
import sys

from brz2obsidian.application.update_contracts import UpdateResult
from brz2obsidian.application.vault_update_contracts import VaultApplyResult
from brz2obsidian.contracts import AttachmentCandidate, AttachmentSelection
from brz2obsidian.publication.vault_replace import move_file
from tests.application.test_format_transition_native import (
    native_format_case,
    user_git_state,
)
from tests.application.test_module_seams import METADATA
from tests.reconciliation.test_resolution import action
from tests.support.recorded_format6 import CURRENT, NOTE, ORIGINAL, changed_source


def finish_transition(operations, prepared, root):
    """Make literal preservation choices against the finite actual offered review."""
    configurations = [
        c
        for c in prepared.review.proposal.changes
        if c.format_review is not None and c.format_review.configuration_choice
    ]
    assert configurations
    chosen = operations.resolve_configuration(
        prepared,
        tuple(
            action(
                prepared.review,
                change,
                domain="configuration",
                choice="current",
                decision_id=f"decline-config-{index}",
            )
            for index, change in enumerate(configurations)
        ),
    )
    assert chosen.code == "accepted", chosen
    prepared = chosen.preparation
    for index in range(3 * len(prepared.review.proposal.changes) + 1):
        (root / "transition-stage.json").write_text(
            prepared.model_dump_json(), encoding="utf-8"
        )
        if prepared.review.ready:
            return prepared
        plan = prepared.review
        required = plan.requirements[0]
        change = next(
            c for c in plan.proposal.changes if c.change_id == required.change_id
        )
        assert required.domain == "format", required
        choice = (
            "current"
            if change.item_id == "5f71e626-527e-47b4-abaa-e53d124619f8"
            or change.current == change.incoming
            else "incoming"
        )
        options = {}
        if change.attachment_review is not None:
            assert choice == "current"
            options = current_attachment_options(plan, change)
        result = operations.resolve_update(
            prepared,
            action(
                plan,
                change,
                domain=required.domain,
                choice=choice,
                decision_id=f"explicit-transition-{index}",
                **options,
            ),
        )
        assert result.code == "accepted", (change.item_id, choice, result)
        prepared = result.preparation
    raise AssertionError("Finite format review did not finish")


def current_attachment_options(plan, change):
    alternative = next(
        row for row in change.attachment_review.alternatives if row.choice == "current"
    )
    assert alternative.eligible and len(alternative.outputs) == 1
    context = plan.producer_facts.link_context
    return {
        "attachment_selection": AttachmentSelection(
            schema_id="brz2obsidian.attachment-selection",
            schema_version=1,
            proposal_id=plan.proposal.proposal_id,
            generation=plan.proposal.generation,
            item_id=change.item_id,
            facet=change.facet,
            reviewed_change_id=change.change_id,
            reviewed_assumptions=change.assumptions,
            choice="current",
            link_choices=(),
            provenance="explicit_user",
        ),
        "attachment_candidate": AttachmentCandidate(
            schema_id="brz2obsidian.attachment-candidate",
            schema_version=1,
            outputs=alternative.outputs,
            documents=context.current_documents,
            targets=context.current_targets,
            target_facts=context.current_target_facts,
        ),
    }


def complete_inventory(root):
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


class StopAfterPublication:
    """Use the public executor fault seam after one actual native move."""

    moved = None

    def move(self, stage, target, *, replace):
        move_file(stage, target, replace=replace)
        self.moved = target
        raise OSError("Owned maintenance fixture stopped after actual publication")

    def directory(self, stage, target):
        move_file(stage, target, replace=False)

    def remove(self, target, destination):
        raise AssertionError("Format maintenance selects no removal")


def finish_interrupted_transition(operations, vault, prepared, root):
    executor = StopAfterPublication()
    operations.vault_executor = executor
    try:
        stopped = operations.apply_update(prepared)
    finally:
        operations.vault_executor = None
    (root / "transition-stopped.json").write_text(
        stopped.model_dump_json(), encoding="utf-8"
    )
    assert (
        stopped.kind == "format_transition" and stopped.status == "recovery_required"
    ), stopped
    assert executor.moved is not None and stopped.application.published_files >= 1
    assert (
        stopped.application.recovery_required
        and stopped.application.intent_commit is not None
    )
    frozen = complete_inventory(vault)
    script = (
        "import sys\nfrom pathlib import Path\n"
        "from brz2obsidian.application.operations import Operations\n"
        "result=Operations().inspect_update_status(sys.argv[1])\n"
        "Path(sys.argv[2]).write_text(result.model_dump_json(),encoding='utf-8')\n"
    )
    discovered_path = root / "transition-fresh-discovery.json"
    cold = subprocess.run(
        [sys.executable, "-c", script, str(vault), str(discovered_path)],
        check=False,
        capture_output=True,
        timeout=180,
    )
    assert cold.returncode == 0, cold.stderr.decode(errors="replace")
    discovered = VaultApplyResult.model_validate_json(discovered_path.read_bytes())
    assert (
        discovered.recovery_required
        and discovered.operation_id == stopped.application.operation_id
    )
    assert discovered.intent_commit == stopped.application.intent_commit
    assert complete_inventory(vault) == frozen
    recovering = operations.prepare_recovery(vault, direction="finish")
    assert recovering.status == "offered" and recovering.review is not None, recovering
    assert recovering.review.facts.format_operation.kind == "format_transition"
    assert recovering.review.facts.baseline_identity.output_format == 6
    assert recovering.review.facts.incoming_identity.output_format == 7
    refreshed = operations.refresh_recovery(vault, recovering)
    (root / "transition-recovery-refreshed.json").write_text(
        refreshed.model_dump_json(), encoding="utf-8"
    )
    assert (
        refreshed.status == "offered"
        and refreshed.operation_id == recovering.operation_id
    ), refreshed
    assert refreshed.intent_commit == stopped.application.intent_commit
    assert complete_inventory(vault) == frozen
    for index in range(3 * len(refreshed.review.proposal.changes) + 1):
        (root / "transition-recovery-stage.json").write_text(
            refreshed.model_dump_json(), encoding="utf-8"
        )
        if refreshed.review.ready:
            break
        plan = refreshed.review
        required = plan.requirements[0]
        change = next(
            c for c in plan.proposal.changes if c.change_id == required.change_id
        )
        choice = (
            "current"
            if required.domain == "configuration"
            or change.item_id == "5f71e626-527e-47b4-abaa-e53d124619f8"
            or change.current == change.incoming
            else "incoming"
        )
        options = {}
        if change.attachment_review is not None:
            choice = "current"
            options = current_attachment_options(plan, change)
        resolved = operations.resolve_recovery(
            vault,
            refreshed,
            action(
                plan,
                change,
                domain=required.domain,
                choice=choice,
                decision_id=f"finish-transition-{index}",
                **options,
            ),
        )
        assert resolved.status == "offered", (change.item_id, resolved)
        refreshed = resolved
    assert refreshed.review.ready, refreshed
    assert complete_inventory(vault) == frozen
    completed = operations.execute_recovery(vault, refreshed)
    (root / "transition-completed.json").write_text(
        completed.model_dump_json(), encoding="utf-8"
    )
    assert completed.status == "applied" and completed.history == "terminal", completed
    assert completed.operation_id == stopped.application.operation_id
    assert completed.receipt_commit is not None and not completed.recovery_required
    return completed


def test_actual_format6_transition_resumes_declines_config_then_applies_distinct_source_b():
    root, operations, vault, archive, user_before = native_format_case(True)
    configuration = b'{"user":"keep exact legacy configuration"}\r\n'
    (vault / ".obsidian/app.json").write_bytes(configuration)
    configs_before = {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in (vault / ".obsidian").rglob("*")
        if path.is_file()
    }
    offered = operations.prepare_format_transition(vault, archive)
    (root / "transition-offered.json").write_text(
        offered.model_dump_json(), encoding="utf-8"
    )
    assert offered.preparation is not None and offered.kind == "format_transition", (
        offered
    )
    facts = offered.preparation.review.facts
    assert (
        facts.baseline_identity.output_format == 6
        and facts.incoming_identity.output_format == 7
    )
    assert (
        facts.format_operation.baseline_source_version
        == facts.format_operation.target_source_version
    )
    assert {"note", "dashboard", "template", "guide", "configuration"} <= {
        s.output_role for s in facts.subjects
    }
    assert (vault / NOTE).read_bytes() == CURRENT
    prepared = finish_transition(operations, offered.preparation, root)
    decisions = [approval.decision_id for approval in prepared.review.approvals]
    source_note = next(
        s.incoming.data
        for s in prepared.review.facts.subjects
        if s.item_id == "5f71e626-527e-47b4-abaa-e53d124619f8"
    )
    assert source_note != ORIGINAL and source_note != CURRENT
    saved = operations.save_update(prepared)
    (root / "transition-saved.json").write_text(
        saved.model_dump_json(), encoding="utf-8"
    )
    assert saved.code == "saved" and saved.kind == "format_transition", saved
    loaded = operations.load_update(vault)
    assert (
        loaded.kind == "format_transition"
        and loaded.loaded is not None
        and not loaded.ready
    )
    script = (
        "import sys\nfrom pathlib import Path\n"
        "from brz2obsidian.application.operations import Operations\n"
        "result=Operations().resume_update(sys.argv[1])\n"
        "Path(sys.argv[2]).write_text(result.model_dump_json(),encoding='utf-8')\n"
    )
    resumed_path = root / "transition-fresh-resume.json"
    cold = subprocess.run(
        [sys.executable, "-c", script, str(vault), str(resumed_path)],
        check=False,
        capture_output=True,
        timeout=180,
    )
    assert cold.returncode == 0, cold.stderr.decode(errors="replace")
    resumed = UpdateResult.model_validate_json(resumed_path.read_bytes())
    assert (
        resumed.kind == "format_transition"
        and resumed.ready
        and resumed.generation == 1
    ), resumed
    assert [
        approval.decision_id for approval in resumed.preparation.review.approvals
    ] == decisions
    note = next(
        s
        for s in resumed.preparation.review.facts.subjects
        if s.item_id == "5f71e626-527e-47b4-abaa-e53d124619f8"
    )
    assert (
        note.baseline.content.data == ORIGINAL and note.current.content.data == CURRENT
    )
    assert user_git_state(vault) == user_before
    completed = finish_interrupted_transition(
        operations, vault, resumed.preparation, root
    )
    assert (vault / NOTE).read_bytes() == CURRENT
    assert {
        name: (vault / name).read_bytes() for name in configs_before
    } == configs_before
    assert user_git_state(vault) == user_before
    retained = operations.read_checkpoint(vault)
    assert retained.status == "valid" and retained.manifest.boundary == "result"
    assert retained.manifest.identity.output_format == 7
    assert retained.review.saved.plan.facts.format_operation.kind == "format_transition"
    assert (
        next(row.sha256 for row in retained.manifest.source if row.path == NOTE)
        == hashlib.sha256(source_note).hexdigest()
    )
    assert (
        next(row.sha256 for row in retained.manifest.vault if row.path == NOTE)
        == hashlib.sha256(CURRENT).hexdigest()
    )
    undo = operations.prepare_undo(vault)
    assert undo.status == "none" and undo.code == "latest_operation_is_maintenance", (
        undo
    )
    assert undo.target_receipt_commit is None

    archive_b = changed_source(root / "source-b.brz")
    operations.workflow.metadata_factory = lambda: METADATA.model_copy(
        update={"run_id": "source-b-run", "run_time": "2026-10-03T01:00:00+00:00"}
    )
    updated = operations.prepare_update(vault, archive_b)
    (root / "source-b-offered.json").write_text(
        updated.model_dump_json(), encoding="utf-8"
    )
    assert updated.preparation is not None and updated.kind == "source_update", updated
    plan = updated.preparation.review
    assert plan.proposal.proposal_id != prepared.review.proposal.proposal_id
    assert (
        plan.facts.baseline_identity.output_format
        == plan.facts.incoming_identity.output_format
        == 7
    )
    assert (
        plan.facts.format_operation.baseline_source_version
        != plan.facts.format_operation.target_source_version
    )
    note = next(
        c
        for c in plan.proposal.changes
        if c.item_id == "5f71e626-527e-47b4-abaa-e53d124619f8"
    )
    subject = next(s for s in plan.facts.subjects if s.item_id == note.item_id)
    assert (
        subject.baseline.content.data == source_note
        and subject.current.content.data == CURRENT
    )
    expected = CURRENT.replace(
        b"Independent legacy source body.", b"Separate source B body."
    )
    assert expected != CURRENT and b"Local legacy writing remains.\r\n" in expected
    chosen = operations.resolve_update(
        updated.preparation,
        action(plan, note, choice="edited", decision_id="source-b-with-local-writing"),
        edited=expected,
    )
    assert chosen.code == "accepted", chosen
    from tests.application.test_update_lifecycle import _finish_incoming

    ready = _finish_incoming(chosen.preparation)
    (root / "source-b-ready.json").write_text(ready.model_dump_json(), encoding="utf-8")
    applied = operations.apply_update(ready)
    (root / "source-b-applied.json").write_text(
        applied.model_dump_json(), encoding="utf-8"
    )
    assert applied.kind == "source_update" and applied.status == "applied", applied
    assert applied.application.history == "terminal"
    assert (vault / NOTE).read_bytes() == expected
    assert {
        name: (vault / name).read_bytes() for name in configs_before
    } == configs_before
    assert user_git_state(vault) == user_before
    assert (vault / "Manual.md").read_bytes() == b"Independent unstaged writing.\r\n"
    latest = operations.prepare_undo(vault)
    assert (
        latest.status == "offered"
        and latest.target_receipt_commit == applied.application.receipt_commit
    ), latest
    assert latest.target_receipt_commit != completed.receipt_commit
