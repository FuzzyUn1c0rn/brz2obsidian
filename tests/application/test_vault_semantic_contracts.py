"""Public wire meanings; parsing these claims never establishes physical authority."""

import json

import pytest

from brz2obsidian.application.checkpoint_contracts import CheckpointManifest
from brz2obsidian.application.vault_recovery_contracts import VaultRecoveryPreparation
from brz2obsidian.application.vault_repair_contracts import (
    HistoryCopyValidation,
    HistoryRepairResult,
)
from brz2obsidian.application.vault_update_contracts import (
    VaultApplyResult,
    VaultOperationIntent,
    VaultOperationReceipt,
    VaultUpdateDetailPage,
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


@pytest.mark.parametrize(
    "contradiction",
    [
        {"before": [file_claim("Notes/Kept.md", "1")] * 2},
        {
            "proposed": [file_claim("New/Restored.md", "2")] * 2
            + [file_claim("Notes/Kept.md", "1")]
        },
        {"affected_paths": ["New/Restored.md"] * 2},
        {"protected_paths": ["Notes/Kept.md"] * 2},
        {"created_directories": [metadata("New")] * 2},
        {"kind": "apply"},
    ],
    ids=[
        "repeated-before-file",
        "repeated-proposed-file",
        "repeated-affected-path",
        "repeated-protected-path",
        "repeated-created-parent",
        "apply-cannot-claim-undo-target",
    ],
)
def test_operation_wire_has_one_fact_per_role_and_a_bound_undo_target(contradiction):
    value = {
        "schema_id": "brz2obsidian.vault-operation-intent",
        "schema_version": 1,
        "operation_id": "a" * 32,
        "kind": "undo",
        "generation": 2,
        "direction": "finish",
        "association_id": "b" * 64,
        "prepared_commit": "3" * 40,
        "undo_of_receipt_commit": "4" * 40,
        "before": [file_claim("Notes/Kept.md", "1")],
        "proposed": [
            file_claim("New/Restored.md", "2"),
            file_claim("Notes/Kept.md", "1"),
        ],
        "affected_paths": ["New/Restored.md"],
        "protected_paths": ["Notes/Kept.md"],
        "before_metadata": [],
        "result_metadata": [metadata("New/Restored.md")],
        "created_directories": [metadata("New")],
    }
    accepted = wire(VaultOperationIntent, value)
    reopened = VaultOperationIntent.model_validate_json(accepted.model_dump_json())
    assert reopened.kind == "undo" and reopened.undo_of_receipt_commit == "4" * 40
    assert tuple(row.path for row in reopened.before) == ("Notes/Kept.md",)
    assert reopened.affected_paths == ("New/Restored.md",)
    assert reopened.protected_paths == ("Notes/Kept.md",)
    assert tuple(row.path for row in reopened.created_directories) == ("New",)
    with pytest.raises(ValueError):
        wire(VaultOperationIntent, value | contradiction)


@pytest.mark.parametrize(
    "case",
    [
        "repeated-published-path",
        "applied-cannot-claim-undo",
        "published-exceeds-planned",
        "terminal-needs-terminal-history",
        "page-exceeds-limit",
        "page-exceeds-total",
        "page-skips-continuation",
        "available-page-needs-operation",
    ],
)
def test_result_and_detail_wire_claims_are_truthful_and_bounded(case):
    if case == "repeated-published-path":
        model = VaultOperationReceipt
        value = {
            "schema_id": "brz2obsidian.vault-operation-receipt",
            "schema_version": 1,
            "operation_id": "a" * 32,
            "kind": "apply",
            "generation": 2,
            "status": "applied",
            "direction": "finish",
            "intent_commit": "1" * 40,
            "prepared_commit": "2" * 40,
            "result_commit": "3" * 40,
            "published_paths": ["Note.md"],
        }
        accepted = wire(model, value)
        assert accepted.status == "applied"
        assert accepted.published_paths == ("Note.md",)
        contradiction = {"published_paths": ["Note.md", "Note.md"]}
    elif case.startswith("page-") or case == "available-page-needs-operation":
        model = VaultUpdateDetailPage
        detail = {
            "path": "Note.md",
            "before_size": 1,
            "before_sha256": "a" * 64,
            "after_size": 2,
            "after_sha256": "b" * 64,
        }
        value = {
            "schema_id": "brz2obsidian.vault-update-detail-page",
            "schema_version": 1,
            "status": "available",
            "code": "literal-comparison",
            "operation_id": "a" * 32,
            "offset": 0,
            "limit": 1,
            "total": 2,
            "items": [detail],
            "next_offset": 1,
        }
        accepted = wire(model, value)
        assert accepted.operation_id == "a" * 32
        assert tuple(item.path for item in accepted.items) == ("Note.md",)
        assert (accepted.offset, accepted.limit, accepted.total) == (0, 1, 2)
        assert accepted.next_offset == 1
        contradiction = {
            "page-exceeds-limit": {"items": [detail, detail | {"path": "Other.md"}]},
            "page-exceeds-total": {"offset": 2},
            "page-skips-continuation": {"next_offset": 2},
            "available-page-needs-operation": {"operation_id": None},
        }[case]
    else:
        model = VaultApplyResult
        value = {
            "schema_id": "brz2obsidian.vault-apply-result",
            "schema_version": 1,
            "status": "applied",
            "code": "literal-terminal-result",
            "operation_id": "a" * 32,
            "kind": "apply",
            "direction": "finish",
            "generation": 2,
            "phase": "terminal",
            "publication": "complete",
            "history": "terminal",
            "planned_files": 1,
            "published_files": 1,
            "authored_files_changed": True,
            "checkpoint_commit": "2" * 40,
            "intent_commit": "1" * 40,
            "result_commit": "3" * 40,
            "receipt_commit": "4" * 40,
            "recovery_required": False,
            "elapsed_ms": 0,
            "message": "Literal complete result",
        }
        accepted = wire(model, value)
        assert (accepted.status, accepted.kind, accepted.history) == (
            "applied",
            "apply",
            "terminal",
        )
        assert accepted.planned_files == accepted.published_files == 1
        contradiction = {
            "applied-cannot-claim-undo": {"kind": "undo"},
            "published-exceeds-planned": {"published_files": 2},
            "terminal-needs-terminal-history": {"history": "intent"},
        }[case]
    reopened = model.model_validate_json(accepted.model_dump_json())
    assert reopened == accepted
    with pytest.raises(ValueError):
        wire(model, value | contradiction)


@pytest.mark.parametrize(
    "case",
    [
        "partial-review-metadata",
        "repeated-source-file",
        "review-content-without-review",
        "content-path-must-name-digest",
        "content-is-not-executable",
    ],
)
def test_checkpoint_review_wire_metadata_has_one_complete_meaning(case):
    content = file_claim("e" * 64, "e")
    value = {
        "schema_id": "brz2obsidian.checkpoint-manifest",
        "schema_version": 1,
        "association_id": "a" * 64,
        "generation": 1,
        "boundary": "local",
        "identity": {
            "collection_id": "literal-collection",
            "module_id": "literal-module",
            "module_version": "1",
            "profile_id": "literal-profile",
            "profile_version": "1",
            "output_format": 1,
            "settings_digest": "literal-settings",
        },
        "source": [file_claim("Note.md", "1")],
        "vault": [],
        "preimage": [],
        "proposed": [],
        "review_content": [content],
        "recovery_gaps": [],
        "semantic_fingerprint": "b" * 64,
        "policy_fingerprint": "c" * 64,
        "policy_continuity_fingerprint": "d" * 64,
        "previous": None,
        "review_object": "5" * 40,
        "review_size": 3,
        "review_sha256": "f" * 64,
    }
    accepted = wire(CheckpointManifest, value)
    reopened = CheckpointManifest.model_validate_json(accepted.model_dump_json())
    assert (reopened.review_object, reopened.review_size, reopened.review_sha256) == (
        "5" * 40,
        3,
        "f" * 64,
    )
    assert tuple(row.path for row in reopened.source) == ("Note.md",)
    assert (
        reopened.review_content[0].path == reopened.review_content[0].sha256 == "e" * 64
    )
    assert reopened.review_content[0].mode == "100644"
    contradiction = {
        "partial-review-metadata": {"review_size": None},
        "repeated-source-file": {"source": [file_claim("Note.md", "1")] * 2},
        "review-content-without-review": {
            "review_object": None,
            "review_size": None,
            "review_sha256": None,
        },
        "content-path-must-name-digest": {
            "review_content": [content | {"path": "f" * 64}]
        },
        "content-is-not-executable": {"review_content": [content | {"mode": "100755"}]},
    }[case]
    with pytest.raises(ValueError):
        wire(CheckpointManifest, value | contradiction)


@pytest.mark.parametrize(
    "case",
    [
        "repeated-damaged-dependency",
        "offered-operation-is-identified",
        "offered-directions-are-unique",
        "unavailable-cannot-carry-review",
        "review-needs-selected-direction",
        "selected-direction-needs-review",
        "selected-direction-is-offered",
    ],
)
def test_repair_and_recovery_wire_claims_keep_exact_dependencies_and_authority(case):
    if case == "repeated-damaged-dependency":
        model = HistoryCopyValidation
        value = {
            "schema_id": "brz2obsidian.history-copy-validation",
            "schema_version": 1,
            "status": "matching",
            "code": "exact_damaged_dependency",
            "target_generation": 1,
            "copy_generation": 1,
            "target_commit": "3" * 40,
            "copy_commit": "3" * 40,
            "association_id": "a" * 64,
            "missing_objects": [],
            "damaged_objects": [DAMAGED],
            "message": "One literal damaged dependency",
        }
        accepted = wire(model, value)
        assert accepted.status == "matching"
        assert accepted.missing_objects == ()
        assert tuple(row.object_id for row in accepted.damaged_objects) == ("2" * 40,)
        contradiction = {"damaged_objects": [DAMAGED, DAMAGED]}
    else:
        from brz2obsidian.core import prepare_review
        from tests.reconciliation.test_proposals import request
        from tests.reconciliation.test_resolution import preflight

        # A real public S1 value supplies the review's shape, not Git authority.
        review = prepare_review(request(), preflight=preflight()).model_dump(
            mode="json"
        )
        model = VaultRecoveryPreparation
        value = {
            "schema_id": "brz2obsidian.vault-recovery-preparation",
            "schema_version": 1,
            "status": "offered",
            "code": "literal-retained-operation",
            "operation_id": "a" * 32,
            "kind": "apply",
            "generation": 2,
            "intent_commit": "1" * 40,
            "available_directions": ["finish", "restore"],
            "direction": None,
            "review": None,
        }
        if case == "unavailable-cannot-carry-review":
            value |= {
                "status": "unavailable",
                "operation_id": None,
                "kind": None,
                "generation": None,
                "intent_commit": None,
                "available_directions": [],
            }
            contradiction = {"review": review}
        elif case == "selected-direction-is-offered":
            value |= {
                "available_directions": ["finish"],
                "direction": "finish",
                "review": review,
            }
            contradiction = {"direction": "restore"}
        else:
            contradiction = {
                "offered-operation-is-identified": {"operation_id": None},
                "offered-directions-are-unique": {
                    "available_directions": ["finish", "finish"]
                },
                "review-needs-selected-direction": {"review": review},
                "selected-direction-needs-review": {"direction": "finish"},
            }[case]
        accepted = wire(model, value)
        if case == "unavailable-cannot-carry-review":
            assert accepted.status == "unavailable" and accepted.operation_id is None
            assert accepted.available_directions == () and accepted.review is None
        else:
            assert accepted.status == "offered"
            assert (accepted.operation_id, accepted.kind, accepted.generation) == (
                "a" * 32,
                "apply",
                2,
            )
            if case == "selected-direction-is-offered":
                assert accepted.available_directions == ("finish",)
                assert accepted.direction == "finish"
                assert accepted.review.proposal.generation == 1
            else:
                assert accepted.available_directions == ("finish", "restore")
                assert accepted.direction is None and accepted.review is None
    reopened = model.model_validate_json(accepted.model_dump_json())
    assert reopened == accepted
    with pytest.raises(ValueError):
        wire(model, value | contradiction)
