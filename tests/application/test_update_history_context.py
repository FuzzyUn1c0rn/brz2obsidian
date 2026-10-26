"""Worker history actions consume shared native admission, never caller authority."""

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from brz2obsidian.application.update_context import UpdateContext
from tests.application.test_update_context import worker_context_call


@pytest.mark.parametrize(
    "changed", ("operation_id", "generation", "intent_commit", "kind")
)
def test_history_prepare_cannot_retarget_an_old_offer_to_a_different_native_operation(
    tmp_path, changed
):
    from brz2obsidian.application.operations import Operations
    from tests.application.test_history_workflow import (
        absent_history,
        operation_state,
        ready_native_recovery,
    )

    observed = operation_state("incomplete")
    native = ready_native_recovery().native.model_copy(
        update={
            changed: {
                "operation_id": "f" * 32,
                "generation": 8,
                "intent_commit": "e" * 40,
                "kind": "undo",
            }[changed]
        }
    )
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Personal.md").write_bytes(b"Later personal bytes\r\n")

    class NativePorts(Operations):
        def inspect_history(self, path, **kwargs):
            return absent_history()

        def inspect_update_status(self, path):
            return observed

        def prepare_recovery(self, path, *, direction=None):
            return native

        def execute_recovery(self, *args, **kwargs):
            raise AssertionError("A changed target must not reach execution")

    context = UpdateContext(operations=NativePorts())
    offered = worker_context_call(
        context,
        {
            "command": "history",
            "vault": str(vault),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    result = worker_context_call(
        context,
        {
            "command": "prepare_history",
            "binding": offered.binding,
            "kind": "recovery",
            "direction": "finish",
        },
    )
    assert result.status == "refused" and result.code == "history_target_changed"
    assert (
        result.binding is None
        and not result.ready
        and result.next_actions == ("inspect_history",)
    )
    assert (vault / "Personal.md").read_bytes() == b"Later personal bytes\r\n"


@pytest.mark.parametrize(
    "outcome", ("restored", "undone", "content_complete", "unknown")
)
def test_worker_history_recovery_keeps_native_direction_and_distinct_terminal(
    tmp_path, outcome
):
    from brz2obsidian.application.contracts import WorkerResponse
    from brz2obsidian.application.operations import ApplicationSession, Operations
    from brz2obsidian.application.transport import Terminal
    from brz2obsidian.application.vault_update_contracts import VaultApplyResult
    from tests.application.test_history_workflow import (
        absent_history,
        operation_state,
        ready_native_recovery,
    )

    vault = tmp_path / "vault"
    vault.mkdir()
    literal = b"Later authored bytes\r\n"
    (vault / "Personal.md").write_bytes(literal)
    direction = "restore" if outcome == "restored" else "finish"
    native_kind = "undo" if outcome == "undone" else "apply"
    origin_role = "source_update" if native_kind == "undo" else "attachment_cleanup"
    observed = operation_state("incomplete").model_copy(
        update={"kind": native_kind, "direction": direction, "origin_role": origin_role}
    )
    prepared = ready_native_recovery(kind=native_kind, direction=direction).native
    terminal = outcome in ("restored", "undone")
    result = VaultApplyResult.model_validate(
        observed.model_dump()
        | {
            "status": outcome,
            "code": "native_" + outcome,
            "generation": 8,
            "phase": "terminal"
            if terminal
            else "result"
            if outcome == "content_complete"
            else "publication",
            "publication": "unknown" if outcome == "unknown" else "complete",
            "history": "terminal"
            if terminal
            else "result"
            if outcome == "content_complete"
            else "unknown",
            "checkpoint_commit": "3" * 40,
            "result_commit": None if outcome == "unknown" else "4" * 40,
            "receipt_commit": "5" * 40 if terminal else None,
            "published_files": 1 if outcome == "unknown" else 2,
            "authored_files_changed": None if outcome == "unknown" else True,
            "recovery_required": not terminal,
        }
    )
    writes = []

    class NativePorts(Operations):
        def inspect_history(self, path, **kwargs):
            assert Path(path) == vault
            return absent_history()

        def inspect_update_status(self, path):
            assert Path(path) == vault
            return observed

        def prepare_recovery(self, path, *, direction=None):
            assert Path(path) == vault
            if direction is None:
                return prepared.model_copy(
                    update={
                        "direction": None,
                        "review": None,
                        "available_directions": ("finish", "restore"),
                    }
                )
            assert direction == prepared.direction
            return prepared

        def refresh_recovery(self, path, previous):
            assert Path(path) == vault and previous == prepared
            return prepared

        def execute_recovery(self, path, previous, *, cancel=None):
            assert Path(path) == vault and previous == prepared
            writes.append(previous)
            return result

    context = UpdateContext(operations=NativePorts())
    session = ApplicationSession()
    selection = "11111111-1111-4111-8111-111111111111"
    session.select_update(str(vault), selection_id=selection)

    def wire(arguments):
        request = session.start_update(arguments)
        assert request is not None
        result = worker_context_call(context, arguments)
        session.complete_update(
            request.request_id,
            Terminal(
                phase="completed",
                response=WorkerResponse(
                    operation="update",
                    request_id=request.request_id,
                    sequence=request.sequence,
                    result=result,
                ),
            ),
        )
        return result

    offered = wire(
        {"command": "history", "vault": str(vault), "selection_id": selection}
    )
    assert offered.publication == "partial" and offered.history.operation == observed
    assert (
        offered.binding.operation_generation == 7
        and offered.binding.intent_commit == "2" * 40
    )
    directions = wire(
        {"command": "prepare_history", "binding": offered.binding, "kind": "recovery"}
    )
    assert directions.status == "direction_required" and not directions.ready
    assert directions.history_action.available_directions == ("finish", "restore")
    selected = wire(
        {
            "command": "prepare_history",
            "binding": directions.binding,
            "kind": "recovery",
            "direction": direction,
        }
    )
    assert selected.ready and selected.binding.operation_generation == 7
    assert (
        selected.binding.review_generation == 3
        and selected.binding.direction == direction
    )
    assert selected.history_action.kind == "recovery" and selected.history_action.ready
    stale = worker_context_call(
        context, {"command": "execute_history", "binding": directions.binding}
    )
    assert stale.status == "refused" and not writes
    refreshed = wire({"command": "refresh_history", "binding": selected.binding})
    assert refreshed.ready and refreshed.binding != selected.binding
    completed = wire({"command": "execute_history", "binding": refreshed.binding})
    assert completed.status == outcome and completed.history_action.status == outcome
    assert completed.history_action.operation == result and len(writes) == 1
    assert completed.history_action.operation.generation == 8
    assert completed.history_action.operation.review_generation == 3
    assert completed.history_action.operation.origin_role == origin_role
    assert completed.publication == result.publication and completed.binding is None
    assert completed.history_retained is (None if outcome == "unknown" else True)
    assert not completed.ready and (vault / "Personal.md").read_bytes() == literal
    state = session.update_snapshot
    assert state.publication == result.publication and state.reply.status == outcome
    assert state.needs_inspection is (not terminal)
    assert state.history_retained is (None if outcome == "unknown" else True)
    closed = wire({"command": "close", "binding": None, "choice": "discard"})
    assert closed.status == outcome and closed.publication == result.publication
    assert (
        closed.history_action.operation == result and not session.update_snapshot.ready
    )


@pytest.mark.parametrize("conditional_policy", (False, True))
def test_worker_history_initialization_requires_explicit_current_native_offer(
    monkeypatch, conditional_policy
):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-285-history-"))
    owner = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(owner), encoding="utf-8")
    evidence = Path(__file__).resolve().parents[2] / "tmp/issue-285/history-fixtures"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (owner["owner"] + ".json")).write_text(
        json.dumps(owner), encoding="utf-8"
    )
    vault = root / "vault"
    vault.mkdir()
    raw = b"Exact opaque personal bytes.\x00\xff\r\n"
    (vault / "Personal.bin").write_bytes(raw)
    note = b"Authored note stays exact.\r\n"
    (vault / "Note.md").write_bytes(note)
    if conditional_policy:
        rules = root / "attributes"
        rules.write_bytes(b"*.md filter=unavailable\n")
        included = root / "included-config"
        included.write_text(
            '[core]\n attributesFile = "' + rules.as_posix() + '"\n', encoding="utf-8"
        )
        global_config = root / "global-config"
        global_config.write_text(
            '[includeIf "gitdir/i:'
            + (vault / ".git").as_posix()
            + '"]\n path = "'
            + included.as_posix()
            + '"\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    context = UpdateContext()
    selection = "11111111-1111-4111-8111-111111111111"
    offered = worker_context_call(
        context, {"command": "history", "vault": str(vault), "selection_id": selection}
    )
    assert offered.kind == "history" and offered.status == "initialization_required"
    assert offered.history.status == "initialization_required"
    assert offered.next_actions == ("initialize_vault",) and offered.binding is not None
    assert (
        not offered.history_retained
        and not offered.ready
        and not (vault / ".git").exists()
    )
    assert (
        offered.binding.operation_id is None
        and offered.binding.review_generation is None
    )
    forged = offered.binding.model_copy(update={"fingerprint": "0" * 64})
    refused = worker_context_call(
        context,
        {"command": "initialize_vault", "binding": forged, "choice": "initialize"},
    )
    assert refused.status == "refused" and not (vault / ".git").exists()
    declined = worker_context_call(
        context,
        {
            "command": "initialize_vault",
            "binding": offered.binding,
            "choice": "decline",
        },
    )
    assert declined.status == "declined" and declined.binding == offered.binding
    assert (
        not (vault / ".git").exists() and (vault / "Personal.bin").read_bytes() == raw
    )
    initialized = worker_context_call(
        context,
        {
            "command": "initialize_vault",
            "binding": declined.binding,
            "choice": "initialize",
        },
    )
    assert initialized.status == "initialized_review_required" and not initialized.ready
    assert initialized.binding is None and not initialized.history_retained
    if conditional_policy:
        assert "review_onboarding" not in initialized.next_actions
        assert "custom_filter" in initialized.history.findings
    else:
        assert initialized.next_actions == ("review_onboarding",)
    assert (vault / ".git").is_dir() and (vault / "Personal.bin").read_bytes() == raw
    assert (vault / "Note.md").read_bytes() == note
    assert not (vault / ".brz2obsidian").exists()
