"""Fresh shared history consumers over tiny owned real S2 operations."""

import json
import subprocess
import sys
from pathlib import Path

from brz2obsidian.application.history_workflow_contracts import HistoryAdmission
from brz2obsidian.application.operations import Operations
from brz2obsidian.contracts import ReviewPlan
from brz2obsidian.publication.vault_replace import move_file
from tests.application.test_vault_checkpoints import user_state
from tests.application.test_vault_recovery_process import (
    _incoming_candidate,
    _two_note_case,
)
from tests.reconciliation.test_resolution import action


def remember_owner(vault):
    record = json.loads((vault.parent / ".fixture-owner.json").read_bytes())
    assert Path(record["root"]).resolve() == vault.parent.resolve()
    evidence = (
        Path(__file__).resolve().parents[2] / "tmp/issue-284/fixtures" / record["owner"]
    )
    evidence.mkdir(parents=True)
    (evidence / "owner.json").write_text(json.dumps(record), encoding="utf-8")
    return evidence


def authored(vault):
    return {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*")
        if path.is_file()
        and path.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    }


def fresh_admission(vault):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from brz2obsidian.application.operations import Operations; "
                "print(Operations().inspect_history_workflow(sys.argv[1]).model_dump_json())"
            ),
            str(vault),
        ],
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return HistoryAdmission.model_validate_json(result.stdout)


def test_restart_recovery_action_preserves_later_writing_and_native_binding():
    vault, source, review_path, user_before, checkpoint_ref = _two_note_case()
    evidence = remember_owner(vault)
    plan = ReviewPlan.model_validate_json(review_path.read_bytes())
    source_before = authored(source)
    assert source_before == {
        "Notes/Closing.md": b"closing incoming\n",
        "Notes/Opening.md": b"opening incoming\n",
    }

    class StopAfterActualMove:
        def move(self, stage, target, *, replace):
            move_file(stage, target, replace=replace)
            raise OSError("Owned test stopped after actual first file publication")

        def directory(self, stage, target):
            raise AssertionError("Ordinary existing parents are sufficient")

        def remove(self, target, destination):
            raise AssertionError("This fixture selects no removal")

    stopped = Operations(vault_executor=StopAfterActualMove()).apply_reviewed_update(
        vault,
        source,
        review=plan,
        source_binding=Operations().observe_reviewed_source(source, plan),
        vault_id="vault-one",
        import_id="import-one",
    )
    assert (stopped.status, stopped.publication) == ("incomplete", "partial"), stopped
    assert authored(vault) == {
        "Notes/Closing.md": b"closing incoming\n",
        "Notes/Opening.md": b"opening authored\r\n",
        "Unrelated.bin": b"protected\x00\xff",
    }
    later = b"opening authored\r\nlater writing\n"
    (vault / "Notes/Opening.md").write_bytes(later)
    before_prepare = authored(vault)
    user_stopped = user_state(vault)
    admission = fresh_admission(vault)
    assert admission.status == "recovery_required"
    assert admission.next_actions == ("review_recovery",)
    assert admission.operation.operation_id == stopped.operation_id
    assert admission.operation.generation == stopped.generation
    assert authored(vault) == before_prepare
    assert user_state(vault) == user_stopped
    operations = Operations()
    offered = operations.prepare_history_workflow(
        vault, kind="recovery", direction="finish"
    )
    assert offered.status == "review_required", offered
    prepared = offered.preparation
    assert prepared.native.operation_id == stopped.operation_id
    assert prepared.native.intent_commit == stopped.intent_commit
    assert prepared.native.kind == "apply" and prepared.native.direction == "finish"
    first_generation = prepared.native.review.proposal.generation
    later += b"second stopped edit\n"
    (vault / "Notes/Opening.md").write_bytes(later)
    before_refresh = authored(vault)
    user_refresh = user_state(vault)
    refreshed = operations.refresh_history_workflow(prepared)
    assert refreshed.status == "review_required", refreshed
    prepared = refreshed.preparation
    assert prepared.native.generation == stopped.generation
    assert prepared.native.review.proposal.generation == first_generation + 1
    assert authored(vault) == before_refresh
    assert user_state(vault) == user_refresh
    while prepared.native.review.requirements:
        review = prepared.native.review
        requirement = review.requirements[0]
        change = next(
            c for c in review.proposal.changes if c.change_id == requirement.change_id
        )
        subject = next(
            s
            for s in review.facts.subjects
            if (s.item_id, s.facet) == (change.item_id, change.facet)
        )
        keep = subject.path == "Notes/Opening.md"
        result = operations.resolve_history_workflow(
            prepared,
            action(
                review,
                change,
                choice="current" if keep else "incoming",
                decision_id="shared:finish:" + subject.item_id,
                candidate=None
                if keep
                else _incoming_candidate(review.facts, subject, b"closing incoming\n"),
            ),
        )
        assert result.status in ("review_required", "ready"), result
        prepared = result.preparation
    assert result.status == "ready"
    completed = operations.execute_history_workflow(prepared)
    assert (completed.status, completed.publication) == ("applied", "complete"), (
        completed
    )
    assert completed.operation.operation_id == stopped.operation_id
    assert (
        completed.operation.kind == "apply"
        and completed.operation.direction == "finish"
    )
    assert (
        completed.operation.review_generation
        == prepared.native.review.proposal.generation
    )
    assert authored(vault) == {
        "Notes/Closing.md": b"closing incoming\n",
        "Notes/Opening.md": b"opening authored\r\nlater writing\nsecond stopped edit\n",
        "Unrelated.bin": b"protected\x00\xff",
    }
    after = user_state(vault)
    for key in ("index", "head", "config", "stages"):
        assert after[key] == user_before[key]
    assert {
        r for r in after["refs"] if not r.startswith(b"refs/brz2obsidian/imports/")
    } == {
        r
        for r in user_before["refs"]
        if not r.startswith(b"refs/brz2obsidian/imports/")
    }
    assert checkpoint_ref.encode() in b"\n".join(after["refs"])
    assert authored(source) == source_before
    (evidence / "completed.json").write_text(
        completed.model_dump_json(), encoding="utf-8"
    )


def test_latest_undo_interruption_keeps_current_content_and_finishes_as_undone():
    vault, source, review_path, user_before, checkpoint_ref = _two_note_case()
    evidence = remember_owner(vault)
    plan = ReviewPlan.model_validate_json(review_path.read_bytes())
    source_before = authored(source)
    operations = Operations()
    applied = operations.apply_reviewed_update(
        vault,
        source,
        review=plan,
        source_binding=operations.observe_reviewed_source(source, plan),
        vault_id="vault-one",
        import_id="import-one",
    )
    assert applied.status == "applied", applied.code
    assert authored(vault) == {
        "Notes/Closing.md": b"closing incoming\n",
        "Notes/Opening.md": b"opening incoming\n",
        "Unrelated.bin": b"protected\x00\xff",
    }
    later = b"opening incoming\nlater after apply\n"
    (vault / "Notes/Opening.md").write_bytes(later)
    before_review = user_state(vault)
    offered = operations.prepare_history_workflow(vault, kind="undo")
    assert offered.status == "review_required", offered
    prepared = offered.preparation
    assert prepared.native.target_receipt_commit == applied.receipt_commit
    assert "retain imported" in offered.summary
    assert user_state(vault) == before_review
    while prepared.native.review.requirements:
        review = prepared.native.review
        requirement = review.requirements[0]
        change = next(
            c for c in review.proposal.changes if c.change_id == requirement.change_id
        )
        keep = change.path == "Notes/Opening.md"
        reverse = "reverse" in requirement.choices
        subject = next(
            s
            for s in review.facts.subjects
            if (s.item_id, s.facet) == (change.item_id, change.facet)
        )
        chosen = operations.resolve_history_workflow(
            prepared,
            action(
                review,
                change,
                domain=requirement.domain,
                choice="current" if keep else "reverse" if reverse else "incoming",
                decision_id="shared:undo:" + change.item_id,
                candidate=None
                if keep or reverse
                else _incoming_candidate(
                    review.facts, subject, b"closing authored\r\n"
                ),
            ),
        )
        (evidence / f"undo-resolution-{len(review.approvals)}.json").write_text(
            chosen.model_dump_json(), encoding="utf-8"
        )
        assert chosen.status in ("review_required", "ready"), (
            chosen.code,
            requirement.domain,
            requirement.choices,
        )
        prepared = chosen.preparation
    assert prepared.ready
    serialized = evidence / "undo-preparation.json"
    serialized.write_text(prepared.model_dump_json(), encoding="utf-8")
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import os
import sys
from pathlib import Path
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.history_workflow_contracts import HistoryWorkflowPreparation
from brz2obsidian.publication.vault_replace import move_file

class StopAfterMove:
    def move(self, stage, target, *, replace):
        move_file(stage, target, replace=replace)
        os._exit(84)
    def directory(self, stage, target):
        raise AssertionError("Existing parents only")
    def remove(self, target, destination):
        raise AssertionError("No removals selected")

prepared = HistoryWorkflowPreparation.model_validate_json(Path(sys.argv[1]).read_bytes())
result = Operations(vault_executor=StopAfterMove()).execute_history_workflow(prepared)
print(result.model_dump_json(), flush=True)
os._exit(85)
""",
            str(serialized),
        ],
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert child.returncode == 84, (child.stdout, child.stderr)
    assert authored(vault) == {
        "Notes/Closing.md": b"closing authored\r\n",
        "Notes/Opening.md": later,
        "Unrelated.bin": b"protected\x00\xff",
    }
    restarted = fresh_admission(vault)
    (evidence / "undo-restart-status.json").write_text(
        restarted.model_dump_json(), encoding="utf-8"
    )
    assert restarted.status == "recovery_required"
    assert restarted.operation.kind == "undo"
    assert restarted.operation.publication == "complete"
    assert restarted.operation.recovery_required
    later += b"later after stopped Undo\n"
    (vault / "Notes/Opening.md").write_bytes(later)
    before_finish = user_state(vault)
    finish = operations.prepare_history_workflow(
        vault, kind="recovery", direction="finish"
    )
    (evidence / "undo-finish-before-refresh.json").write_text(
        finish.model_dump_json(), encoding="utf-8"
    )
    assert finish.status in ("review_required", "ready"), finish.code
    initial_native = finish.preparation.native
    refreshed = operations.refresh_history_workflow(finish.preparation)
    (evidence / "undo-finish-after-refresh.json").write_text(
        refreshed.model_dump_json(), encoding="utf-8"
    )
    assert refreshed.status in ("review_required", "ready"), refreshed.code
    prepared = refreshed.preparation
    assert prepared.native.generation == initial_native.generation
    assert (
        prepared.native.review.proposal.generation
        == initial_native.review.proposal.generation + 1
    )
    assert user_state(vault) == before_finish
    assert prepared.native.kind == "undo" and prepared.native.direction == "finish"
    while prepared.native.review.requirements:
        review = prepared.native.review
        requirement = review.requirements[0]
        change = next(
            c for c in review.proposal.changes if c.change_id == requirement.change_id
        )
        chosen = operations.resolve_history_workflow(
            prepared,
            action(
                review,
                change,
                domain=requirement.domain,
                choice="current",
                decision_id="shared:undo-finish:" + change.item_id,
            ),
        )
        (evidence / f"undo-finish-resolution-{len(review.approvals)}.json").write_text(
            chosen.model_dump_json(), encoding="utf-8"
        )
        assert chosen.status in ("review_required", "ready"), (
            chosen.code,
            requirement.domain,
            requirement.choices,
        )
        prepared = chosen.preparation
    assert user_state(vault) == before_finish
    (evidence / "undo-finish-preparation.json").write_text(
        prepared.model_dump_json(), encoding="utf-8"
    )
    completed = operations.execute_history_workflow(prepared)
    (evidence / "undo-finish-result.json").write_text(
        completed.model_dump_json(), encoding="utf-8"
    )
    assert completed.status == "undone" and completed.publication == "complete", (
        completed.code,
        completed.operation,
    )
    assert (
        completed.operation.kind == "undo" and completed.operation.direction == "finish"
    )
    assert authored(vault) == {
        "Notes/Closing.md": b"closing authored\r\n",
        "Notes/Opening.md": b"opening incoming\nlater after apply\nlater after stopped Undo\n",
        "Unrelated.bin": b"protected\x00\xff",
    }
    terminal = user_state(vault)
    replay = operations.execute_history_workflow(prepared)
    assert replay.status == "refused" and replay.code == "history_authority_changed"
    latest = operations.prepare_history_workflow(vault, kind="undo")
    assert latest.status == "refused" and latest.code == "latest_update_already_undone"
    assert user_state(vault) == terminal
    for key in ("index", "head", "config", "stages"):
        assert terminal[key] == user_before[key]
    assert {
        r for r in terminal["refs"] if not r.startswith(b"refs/brz2obsidian/imports/")
    } == {
        r
        for r in user_before["refs"]
        if not r.startswith(b"refs/brz2obsidian/imports/")
    }
    assert checkpoint_ref.encode() in b"\n".join(terminal["refs"])
    assert authored(source) == source_before
    (evidence / "undo-completed.json").write_text(
        completed.model_dump_json(), encoding="utf-8"
    )
