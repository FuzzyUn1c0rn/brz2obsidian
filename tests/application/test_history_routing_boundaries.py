"""Public history routing over controlled descriptions, not native authority."""

from pathlib import Path

import pytest

from brz2obsidian.application.history_workflow_contracts import (
    HistoryWorkflowPreparation,
)
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.vault_undo_contracts import VaultUndoPreparation
from brz2obsidian.application.vault_update_contracts import VaultApplyResult
from tests.application.test_history_value_boundaries import (
    repair_preparation,
    terminal_operation,
)
from tests.application.test_history_workflow import (
    operation_state,
    ready_native_recovery,
)
from tests.application.test_update_lifecycle_contracts import preparation


def undo_preparation(*, ready):
    review = ready_native_recovery().native.review if ready else preparation().review
    native = VaultUndoPreparation(
        schema_id="brz2obsidian.vault-undo-preparation",
        schema_version=1,
        status="offered",
        code="offered",
        checkpoint_commit="1" * 40,
        generation=2,
        target_receipt_commit="2" * 40,
        review=review,
    )
    return HistoryWorkflowPreparation(kind="undo", vault="target", native=native)


@pytest.mark.parametrize("method", ["refresh", "resolve", "execute"])
def test_recovery_workflow_rechecks_authority_before_native_contact(method):
    saved = ready_native_recovery()

    class Changed(Operations):
        def inspect_update_status(self, vault):
            assert vault == "controlled-vault"
            return operation_state("incomplete").model_copy(update={"generation": 8})

        def refresh_recovery(self, *args, **kwargs):
            pytest.fail("Changed authority reached refresh")

        def resolve_recovery(self, *args, **kwargs):
            pytest.fail("Changed authority reached resolve")

        def execute_recovery(self, *args, **kwargs):
            pytest.fail("Changed authority reached execution")

    operations = Changed()
    if method == "refresh":
        result = operations.refresh_history_workflow(saved)
    elif method == "resolve":
        result = operations.resolve_history_workflow(saved, object())
    else:
        result = operations.execute_history_workflow(saved)
    assert (result.status, result.code) == ("refused", "history_authority_changed")
    assert result.operation.generation == 8
    assert result.preparation is None


def test_undo_workflow_forwards_reviewed_values_and_native_terminal_result():
    saved = undo_preparation(ready=True)
    marker = object()
    terminal = VaultApplyResult.model_validate(terminal_operation())
    calls = []

    class UndoPort(Operations):
        def prepare_undo(self, vault, *, previous=None):
            calls.append(("refresh", vault, previous))
            return previous

        def resolve_undo(self, vault, previous, action):
            calls.append(("resolve", vault, previous, action))
            return previous

        def execute_undo(self, vault, previous, *, cancel=None, progress=None):
            calls.append(("execute", vault, previous, cancel, progress))
            return terminal

    operations = UndoPort()
    refreshed = operations.refresh_history_workflow(saved)
    resolved = operations.resolve_history_workflow(saved, marker)
    executed = operations.execute_history_workflow(saved)
    assert refreshed.status == resolved.status == "ready"
    assert refreshed.preparation.native == resolved.preparation.native == saved.native
    assert (executed.status, executed.kind, executed.operation.receipt_commit) == (
        "undone",
        "undo",
        "4" * 40,
    )
    assert calls == [
        ("refresh", "target", saved.native),
        ("resolve", "target", saved.native, marker),
        ("execute", "target", saved.native, None, None),
    ]


def test_unready_undo_and_repair_cancellation_do_not_reach_native_execution():
    class NoExecution(Operations):
        def execute_undo(self, *args, **kwargs):
            pytest.fail("Unready Undo reached execution")

        def execute_history_repair(self, *args, **kwargs):
            pytest.fail("Invalid repair cancellation reached execution")

    operations = NoExecution()
    refused = operations.execute_history_workflow(undo_preparation(ready=False))
    repair = HistoryWorkflowPreparation.model_validate(repair_preparation())
    invalid = operations.execute_history_workflow(repair, cancel="not callable")
    assert (refused.status, refused.code) == ("refused", "history_review_required")
    assert (invalid.status, invalid.code) == ("refused", "invalid_history_cancellation")


def test_repair_refresh_preserves_copy_and_validation_and_is_not_reviewable():
    saved = HistoryWorkflowPreparation.model_validate(repair_preparation())
    calls = []

    class RepairPort(Operations):
        def prepare_history_repair(self, vault, copy, validation):
            calls.append((vault, copy, validation))
            return saved.native

        def resolve_recovery(self, *args, **kwargs):
            pytest.fail("Repair action reached recovery")

        def resolve_undo(self, *args, **kwargs):
            pytest.fail("Repair action reached Undo")

    operations = RepairPort()
    refreshed = operations.refresh_history_workflow(saved)
    refused = operations.resolve_history_workflow(saved, object())
    assert refreshed.status == "ready"
    assert refreshed.preparation.native == saved.native
    assert refreshed.preparation.vault == str(Path("target").absolute())
    assert refreshed.preparation.copy_path == str(Path("copy").absolute())
    assert calls == [("target", "copy", saved.native.validation)]
    assert (refused.status, refused.code) == (
        "refused",
        "history_action_not_reviewable",
    )
