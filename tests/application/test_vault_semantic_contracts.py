"""Public wire meanings; parsing these claims never establishes physical authority."""

import json

import pytest

from brz2obsidian.application.checkpoint_contracts import CheckpointManifest
from brz2obsidian.application.vault_repair_contracts import (
    HistoryCopyValidation,
    HistoryRepairResult,
)
from brz2obsidian.application.vault_update_contracts import (
    VaultApplyResult,
    VaultOperationIntent,
    VaultOperationReceipt,
)


def wire(model, value):
    return model.model_validate_json(json.dumps(value))


@pytest.mark.parametrize(
    "kind,direction,status,paths,bad_receipt,bad_result",
    [
        (
            "apply",
            "finish",
            "applied",
            ["Note.md"],
            {"status": "undone"},
            {"receipt_commit": None},
        ),
        (
            "apply",
            "finish",
            "no_content_change",
            [],
            {"published_paths": ["Note.md"]},
            {"planned_files": 1},
        ),
        (
            "apply",
            "finish",
            "applied",
            [],
            {"kind": "undo"},
            {"phase": "result"},
        ),
        (
            "undo",
            "finish",
            "undone",
            ["Note.md"],
            {"direction": "restore"},
            {"kind": "apply"},
        ),
        (
            "apply",
            "restore",
            "restored",
            ["Note.md"],
            {"direction": "finish"},
            {"direction": "finish"},
        ),
        (
            "undo",
            "restore",
            "restored",
            [],
            {"status": "undone"},
            {"recovery_required": True},
        ),
    ],
    ids=[
        "applied",
        "ordinary-no-op",
        "already-published-no-new-moves",
        "undone",
        "restored-apply",
        "restored-undo-no-new-moves",
    ],
)
def test_terminal_wire_values_preserve_direction_and_publication_truth(
    kind, direction, status, paths, bad_receipt, bad_result
):
    receipt = {
        "schema_id": "brz2obsidian.vault-operation-receipt",
        "schema_version": 1,
        "operation_id": "a" * 32,
        "kind": kind,
        "generation": 2,
        "status": status,
        "direction": direction,
        "intent_commit": "1" * 40,
        "prepared_commit": "2" * 40,
        "result_commit": "3" * 40,
        "published_paths": paths,
    }
    accepted = wire(VaultOperationReceipt, receipt)
    restored = VaultOperationReceipt.model_validate_json(accepted.model_dump_json())
    assert (restored.kind, restored.direction, restored.status) == (
        kind,
        direction,
        status,
    )
    assert restored.published_paths == tuple(paths)
    with pytest.raises(ValueError):
        wire(VaultOperationReceipt, receipt | bad_receipt)

    result = {
        "schema_id": "brz2obsidian.vault-apply-result",
        "schema_version": 1,
        "status": status,
        "code": "literal-terminal-result",
        "operation_id": "a" * 32,
        "kind": kind,
        "direction": direction,
        "generation": 2,
        "phase": "terminal",
        "publication": "complete",
        "history": "terminal",
        "planned_files": len(paths),
        "published_files": len(paths),
        "authored_files_changed": bool(paths),
        "checkpoint_commit": "2" * 40,
        "intent_commit": "1" * 40,
        "result_commit": "3" * 40,
        "receipt_commit": "4" * 40,
        "recovery_required": False,
        "elapsed_ms": 0,
        "message": "Literal result",
    }
    accepted_result = wire(VaultApplyResult, result)
    assert accepted_result.status == status
    assert accepted_result.published_files == len(paths)
    assert accepted_result.authored_files_changed == bool(paths)
    with pytest.raises(ValueError):
        wire(VaultApplyResult, result | bad_result)


def file_claim(path, identifier):
    return {
        "path": path,
        "mode": "100644",
        "size": 1,
        "sha256": identifier * 64,
        "object_id": identifier * 40,
    }


def metadata(path):
    return {"path": path, "mode": 0, "attributes": 0, "security": "literal-security"}


@pytest.mark.parametrize(
    "contradiction",
    [
        {"created_directories": [metadata("Unrelated")]},
        {"created_directories": [metadata("New/Restored.md")]},
        {"result_metadata": []},
        {"affected_paths": ["New/Restored.md", "Notes/Kept.md"]},
    ],
    ids=[
        "unrelated-parent",
        "file-is-not-directory",
        "missing-result-metadata",
        "kept-is-not-affected",
    ],
)
def test_transition_wire_roles_name_only_changed_files_and_their_new_parents(
    contradiction,
):
    kept = file_claim("Notes/Kept.md", "1")
    created = file_claim("New/Restored.md", "2")
    value = {
        "schema_id": "brz2obsidian.vault-operation-intent",
        "schema_version": 1,
        "operation_id": "a" * 32,
        "kind": "apply",
        "generation": 1,
        "direction": "finish",
        "association_id": "b" * 64,
        "prepared_commit": "3" * 40,
        "before": [kept],
        "proposed": [created, kept],
        "affected_paths": ["New/Restored.md"],
        "protected_paths": ["Notes/Kept.md"],
        "before_metadata": [],
        "result_metadata": [metadata("New/Restored.md")],
        "created_directories": [metadata("New")],
    }
    accepted = wire(VaultOperationIntent, value)
    assert accepted.affected_paths == ("New/Restored.md",)
    assert accepted.protected_paths == ("Notes/Kept.md",)
    assert tuple(row.path for row in accepted.created_directories) == ("New",)
    assert tuple(row.path for row in accepted.proposed) == (
        "New/Restored.md",
        "Notes/Kept.md",
    )
    with pytest.raises(ValueError):
        wire(VaultOperationIntent, value | contradiction)


MISSING = {"object_id": "1" * 40, "size": 3, "sha256": "a" * 64}
DAMAGED = {"object_id": "2" * 40, "size": 5, "sha256": "b" * 64}


@pytest.mark.parametrize(
    "status,code,missing,damaged,bad_validation,result_status,storage,count,diagnostic,bad_result",
    [
        (
            "matching",
            "exact_missing_dependency",
            [MISSING],
            [],
            {"missing_objects": [MISSING, MISSING]},
            "repaired",
            "verified",
            1,
            None,
            {"history_retained": False},
        ),
        (
            "matching",
            "exact_damaged_dependency",
            [],
            [DAMAGED],
            {"code": "exact_missing_dependency"},
            "unknown",
            "possible",
            0,
            "retained-diagnostic",
            {"object_storage": "not_started", "objects_written": 1},
        ),
        (
            "matching",
            "exact_unavailable_dependency",
            [MISSING],
            [DAMAGED],
            {"damaged_objects": [MISSING]},
            "repaired",
            "verified",
            2,
            None,
            {"diagnostic_path": "unresolved-bytes"},
        ),
        (
            "refused",
            "history_copy_mismatch",
            [],
            [],
            {"missing_objects": [MISSING]},
            "failed",
            "not_started",
            0,
            None,
            {"status": "repaired"},
        ),
    ],
    ids=[
        "missing-once",
        "damaged-distinct-from-missing",
        "no-overlapping-object",
        "refusal-grants-no-repair",
    ],
)
def test_repair_wire_values_separate_dependency_knowledge_from_storage_truth(
    status,
    code,
    missing,
    damaged,
    bad_validation,
    result_status,
    storage,
    count,
    diagnostic,
    bad_result,
):
    validation = {
        "schema_id": "brz2obsidian.history-copy-validation",
        "schema_version": 1,
        "status": status,
        "code": code,
        "missing_objects": missing,
        "damaged_objects": damaged,
        "message": "Literal matching judgment",
        "target_generation": 1,
        "copy_generation": 1,
        "target_commit": "3" * 40,
        "copy_commit": ("3" if status == "matching" else "4") * 40,
        "association_id": "c" * 64,
    }
    accepted = wire(HistoryCopyValidation, validation)
    assert [row.object_id for row in accepted.missing_objects] == [
        row["object_id"] for row in missing
    ]
    assert [row.object_id for row in accepted.damaged_objects] == [
        row["object_id"] for row in damaged
    ]
    with pytest.raises(ValueError):
        wire(HistoryCopyValidation, validation | bad_validation)

    result = {
        "schema_id": "brz2obsidian.history-repair-result",
        "schema_version": 1,
        "status": result_status,
        "code": "literal-storage-result",
        "history_retained": result_status == "repaired",
        "object_storage": storage,
        "objects_written": count,
        "authored_files_changed": False,
        "diagnostic_path": diagnostic,
        "message": "Literal storage result",
    }
    accepted_result = wire(HistoryRepairResult, result)
    assert (
        accepted_result.status,
        accepted_result.object_storage,
        accepted_result.objects_written,
    ) == (result_status, storage, count)
    assert accepted_result.authored_files_changed is False
    with pytest.raises(ValueError):
        wire(HistoryRepairResult, result | bad_result)


RECOVERY_MARKERS = {
    "recovery_origin_intent_commit": "1" * 40,
    "recovery_previous_operation_commit": "2" * 40,
    "recovery_direction": "restore",
}


@pytest.mark.parametrize(
    "boundary,markers,contradiction",
    [
        ("local", {}, {"recovery_origin_intent_commit": "1" * 40}),
        ("prepared", {"undo_of_receipt_commit": "4" * 40}, RECOVERY_MARKERS),
        ("prepared", RECOVERY_MARKERS, {"boundary": "local"}),
        (
            "result",
            {"operation_intent_commit": "5" * 40},
            {"boundary": "prepared"},
        ),
    ],
    ids=["local", "initial-undo", "selected-recovery", "actual-result"],
)
def test_checkpoint_wire_roles_do_not_exchange_durable_provenance(
    boundary, markers, contradiction
):
    value = {
        "schema_id": "brz2obsidian.checkpoint-manifest",
        "schema_version": 1,
        "association_id": "a" * 64,
        "generation": 1,
        "boundary": boundary,
        "identity": {
            "collection_id": "literal-collection",
            "module_id": "literal-module",
            "module_version": "1",
            "profile_id": "literal-profile",
            "profile_version": "1",
            "output_format": 1,
            "settings_digest": "literal-settings",
        },
        "source": [],
        "vault": [],
        "preimage": [],
        "proposed": [],
        "review_content": [],
        "recovery_gaps": [],
        "semantic_fingerprint": "b" * 64,
        "policy_fingerprint": "c" * 64,
        "policy_continuity_fingerprint": "d" * 64,
        "previous": None,
        "review_object": None,
        "review_size": None,
        "review_sha256": None,
    } | markers
    accepted = wire(CheckpointManifest, value)
    restored = CheckpointManifest.model_validate_json(accepted.model_dump_json())
    assert restored.boundary == boundary
    for name, expected in markers.items():
        assert restored.model_dump()[name] == expected
    with pytest.raises(ValueError):
        wire(CheckpointManifest, value | contradiction)
