"""Public history descriptions reject contradictory routing and results.

These supplied wire values describe observations; they do not establish native authority.
"""

import copy
import json

import pytest

from brz2obsidian.application.history_workflow_contracts import (
    HistoryAdmission,
    HistoryWorkflowResult,
)


def operation(status="unknown"):
    return {
        "schema_id": "brz2obsidian.vault-apply-result",
        "schema_version": 1,
        "status": status,
        "code": "observed",
        "operation_id": "1" * 32 if status == "incomplete" else None,
        "kind": "apply",
        "direction": "finish" if status == "incomplete" else None,
        "generation": 7 if status == "incomplete" else None,
        "phase": "publication" if status == "incomplete" else "admission",
        "publication": "partial" if status == "incomplete" else "unknown",
        "history": "intent" if status == "incomplete" else "unknown",
        "planned_files": 0,
        "published_files": 0,
        "authored_files_changed": None,
        "checkpoint_commit": None,
        "intent_commit": "2" * 40 if status == "incomplete" else None,
        "result_commit": None,
        "receipt_commit": None,
        "recovery_required": True,
        "elapsed_ms": 0,
        "message": "Observed state",
    }


def checkpoint():
    return {
        "schema_id": "brz2obsidian.checkpoint-locator",
        "schema_version": 1,
        "generation": 2,
        "commit": "1" * 40,
        "association": {
            "schema_id": "brz2obsidian.vault-association",
            "schema_version": 1,
            "association_id": "a" * 64,
            "vault_id": "vault",
            "import_id": "import",
            "collection_id": "collection",
            "module_id": "module",
            "vault_anchor": "vault-anchor",
            "git_anchor": "git-anchor",
            "ref": "refs/example",
        },
    }


def admission(status):
    values = {
        "recovery_required": ("recovery_first", ["review_recovery"], None, False),
        "available": ("history_available", ["review_update"], checkpoint(), True),
        "onboarding_required": (
            "onboarding_required",
            ["review_onboarding"],
            None,
            False,
        ),
        "initialization_required": (
            "repository_initialization_required",
            ["initialize_vault"],
            None,
            False,
        ),
    }
    code, actions, locator, retained = values[status]
    return {
        "schema_id": "brz2obsidian.history-admission",
        "schema_version": 1,
        "status": status,
        "code": code,
        "next_actions": actions,
        "operation": operation()
        if status == "recovery_required"
        else operation("refused")
        | {
            "code": "operation_absent",
            "publication": "not_started",
            "history": "none",
            "recovery_required": False,
        },
        "checkpoint": locator,
        "history_retained": retained,
        "recovery_gaps": [],
        "findings": [],
        "summary": "Observed history",
        "guidance": [],
    }


def repair_preparation():
    return {
        "schema_id": "brz2obsidian.history-workflow-preparation",
        "schema_version": 1,
        "kind": "repair",
        "vault": "target",
        "copy_path": "copy",
        "native": {
            "schema_id": "brz2obsidian.history-repair-preparation",
            "schema_version": 1,
            "status": "prepared",
            "code": "exact_missing_dependency",
            "validation": {
                "schema_id": "brz2obsidian.history-copy-validation",
                "schema_version": 1,
                "status": "matching",
                "code": "exact_missing_dependency",
                "message": "Matched",
            },
            "target_anchor": "target",
            "target_git_anchor": "target-git",
            "copy_anchor": "copy",
            "copy_git_anchor": "copy-git",
            "target_snapshot": "b" * 64,
            "copy_snapshot": "c" * 64,
            "message": "Prepared",
        },
    }


def workflow(status="ready"):
    return {
        "schema_id": "brz2obsidian.history-workflow-result",
        "schema_version": 1,
        "kind": "repair",
        "status": status,
        "code": "observed",
        "summary": "Observed",
        "next_actions": [],
        "preparation": repair_preparation() if status == "ready" else None,
        "operation": None,
        "repair": None,
        "copy_validation": None,
        "publication": None,
        "history_retained": None,
        "recovery_gaps": None,
        "guidance": [],
    }


def read(model, value):
    return model.model_validate_json(json.dumps(value))


@pytest.mark.parametrize(
    "base,change,message",
    [
        (
            "recovery_required",
            {"next_actions": ["review_recovery", "review_recovery"]},
            "History actions must be distinct",
        ),
        (
            "recovery_required",
            {"next_actions": ["review_update"]},
            "only recovery/setup routing",
        ),
        (
            "recovery_required",
            {"next_actions": ["review_recovery", "review_update"]},
            "only recovery/setup routing",
        ),
        (
            "recovery_required",
            {
                "operation": operation("incomplete"),
                "next_actions": ["review_recovery", "review_history_repair"],
            },
            "Known incomplete operations",
        ),
        ("available", {"checkpoint": None}, "validated current checkpoint"),
        ("available", {"history_retained": False}, "validated current checkpoint"),
        ("onboarding_required", {"history_retained": True}, "Absent history"),
        ("onboarding_required", {"checkpoint": checkpoint()}, "Absent history"),
        (
            "initialization_required",
            {"next_actions": ["review_update"]},
            "explicit repository absence",
        ),
        (
            "initialization_required",
            {"history_retained": True},
            "explicit repository absence",
        ),
        (
            "initialization_required",
            {"checkpoint": checkpoint()},
            "explicit repository absence",
        ),
        (
            "initialization_required",
            {"operation": operation("incomplete")},
            "explicit repository absence",
        ),
    ],
)
def test_history_admission_wire_refuses_contradictory_routes(base, change, message):
    valid = admission(base)
    accepted = read(HistoryAdmission, valid)
    assert accepted.status == base and accepted.next_actions == tuple(
        valid["next_actions"]
    )
    bad = copy.deepcopy(valid)
    bad.update(change)
    with pytest.raises(ValueError, match=message):
        read(HistoryAdmission, bad)


@pytest.mark.parametrize(
    "change,message",
    [
        ({"preparation": None}, "Review readiness"),
        ({"status": "review_required"}, "Review readiness"),
        ({"kind": "undo"}, "preserve its preparation role"),
        ({"status": "direction_required"}, "Review readiness"),
        ({"status": "refused"}, "cannot carry live preparation"),
        ({"publication": "complete"}, "Publication describes"),
    ],
)
def test_history_workflow_wire_refuses_untruthful_preparation(change, message):
    valid = workflow()
    accepted = read(HistoryWorkflowResult, valid)
    assert (
        accepted.kind == "repair"
        and accepted.status == "ready"
        and accepted.preparation.ready
    )
    bad = copy.deepcopy(valid)
    bad.update(change)
    with pytest.raises(ValueError, match=message):
        read(HistoryWorkflowResult, bad)


def repair_result():
    return {
        "schema_id": "brz2obsidian.history-repair-result",
        "schema_version": 1,
        "status": "repaired",
        "code": "repaired",
        "history_retained": True,
        "object_storage": "verified",
        "objects_written": 1,
        "authored_files_changed": False,
        "message": "Verified",
    }


def terminal_operation():
    return operation() | {
        "status": "undone",
        "kind": "undo",
        "direction": "finish",
        "operation_id": "1" * 32,
        "generation": 8,
        "phase": "terminal",
        "publication": "complete",
        "history": "terminal",
        "intent_commit": "2" * 40,
        "checkpoint_commit": "3" * 40,
        "result_commit": "3" * 40,
        "receipt_commit": "4" * 40,
        "recovery_required": False,
    }


@pytest.mark.parametrize(
    "kind,change,message",
    [
        ("operation", {"repair": repair_result()}, "one native execution result"),
        ("operation", {"publication": "partial"}, "Publication describes"),
        ("operation", {"status": "applied"}, "exact native result"),
        ("operation", {"operation": None, "publication": None}, "exact native result"),
        ("repair", {"repair": None}, "verified native repair result"),
        ("repair", {"kind": "undo"}, "repair workflow role"),
    ],
)
def test_history_workflow_wire_preserves_terminal_native_outcome(kind, change, message):
    valid = workflow("undone" if kind == "operation" else "repaired")
    if kind == "operation":
        valid.update(
            kind="undo", operation=terminal_operation(), publication="complete"
        )
    else:
        valid["repair"] = repair_result()
    accepted = read(HistoryWorkflowResult, valid)
    assert accepted.status == valid["status"] and accepted.kind == valid["kind"]
    if kind == "operation":
        assert accepted.operation.receipt_commit == "4" * 40
    else:
        assert (
            accepted.repair.object_storage == "verified"
            and accepted.repair.objects_written == 1
        )
    bad = copy.deepcopy(valid)
    bad.update(change)
    with pytest.raises(ValueError, match=message):
        read(HistoryWorkflowResult, bad)


def test_history_direction_choice_requires_unselected_recovery():
    from brz2obsidian.application.history_workflow_contracts import (
        HistoryWorkflowPreparation,
    )
    from brz2obsidian.application.vault_undo_contracts import VaultUndoPreparation
    from tests.application.test_update_lifecycle_contracts import preparation

    review = preparation().review
    assert not review.ready
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
    prepared = HistoryWorkflowPreparation(kind="undo", vault="target", native=native)
    valid = workflow("review_required")
    valid.update(
        kind="undo", preparation=prepared.model_dump(mode="json", by_alias=True)
    )
    accepted = read(HistoryWorkflowResult, valid)
    assert accepted.kind == "undo" and not accepted.preparation.ready
    valid["status"] = "direction_required"
    with pytest.raises(ValueError, match="Only an unselected recovery direction"):
        read(HistoryWorkflowResult, valid)
