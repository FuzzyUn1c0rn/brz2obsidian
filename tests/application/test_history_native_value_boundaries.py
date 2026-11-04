"""Public history descriptions retain meaning without proving native authority."""

import json

import pytest

from brz2obsidian.application.update_history_contracts import UpdateHistoryActionState
from brz2obsidian.application.vault_progress_contracts import VaultProgress
from brz2obsidian.application.vault_undo_contracts import VaultUndoPreparation


def recovery_direction_value():
    return {
        "kind": "recovery",
        "status": "direction_required",
        "ready": False,
        "available_directions": ["finish", "restore"],
        "operation": None,
        "summary": "Choose the direction of the retained interrupted operation.",
    }


def repaired_action_value():
    return {
        "kind": "repair",
        "status": "repaired",
        "ready": False,
        "available_directions": [],
        "operation": None,
        "summary": "One retained history object was restored by the repair.",
        "repair": {
            "schema_id": "brz2obsidian.history-repair-result",
            "schema_version": 1,
            "status": "repaired",
            "code": "matching_history_repaired",
            "history_retained": True,
            "object_storage": "verified",
            "objects_written": 1,
            "authored_files_changed": False,
            "message": "Literal supplied repair result; no native execution here.",
        },
    }


@pytest.fixture
def offered_undo_value():
    from brz2obsidian.core import prepare_review
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import preflight, with_review_links

    review = prepare_review(
        with_review_links(
            request(
                original=b"Published update.\n",
                current=b"Published update.\n",
                incoming=b"Prior authored bytes.\r\n",
            )
        ),
        preflight=preflight(),
    )
    assert review.facts.subjects[0].current.content.data == b"Published update.\n"
    assert review.facts.subjects[0].incoming.data == b"Prior authored bytes.\r\n"
    assert not review.ready
    return {
        "schema_id": "brz2obsidian.vault-undo-preparation",
        "schema_version": 1,
        "status": "offered",
        "code": "latest_undo_review_required",
        "checkpoint_commit": "a" * 40,
        "generation": 3,
        "target_receipt_commit": "b" * 40,
        "review": json.loads(review.model_dump_json()),
    }


def test_recovery_direction_selection_does_not_claim_action_readiness():
    value = recovery_direction_value()
    offered = UpdateHistoryActionState.model_validate_json(json.dumps(value))
    assert offered.kind == "recovery" and not offered.ready
    assert offered.status == "direction_required"
    assert offered.available_directions == ("finish", "restore")
    with pytest.raises(
        ValueError, match="History action readiness must match its status"
    ):
        UpdateHistoryActionState.model_validate_json(
            json.dumps(value | {"ready": True})
        )


def test_direction_selection_belongs_to_an_offered_recovery_action():
    value = recovery_direction_value()
    offered = UpdateHistoryActionState.model_validate_json(json.dumps(value))
    assert offered.kind == "recovery" and offered.operation is None
    assert offered.available_directions == ("finish", "restore")
    with pytest.raises(
        ValueError, match="Only an offered recovery direction requires selection"
    ):
        UpdateHistoryActionState.model_validate_json(
            json.dumps(value | {"kind": "undo"})
        )


def test_a_repair_result_cannot_be_relabelled_as_an_undo_action():
    value = repaired_action_value()
    repaired = UpdateHistoryActionState.model_validate_json(json.dumps(value))
    assert repaired.kind == "repair" and repaired.status == "repaired"
    assert not repaired.ready and repaired.operation is None
    assert repaired.repair.object_storage == "verified"
    assert repaired.repair.history_retained and repaired.repair.objects_written == 1
    assert not repaired.repair.authored_files_changed
    with pytest.raises(
        ValueError, match="Repair outcomes must keep their actual native role/result"
    ):
        UpdateHistoryActionState.model_validate_json(
            json.dumps(value | {"kind": "undo"})
        )


def test_a_repaired_action_requires_its_retained_storage_result():
    value = repaired_action_value()
    repaired = UpdateHistoryActionState.model_validate_json(json.dumps(value))
    assert repaired.repair.status == "repaired" and repaired.repair.history_retained
    assert repaired.repair.objects_written == 1
    with pytest.raises(
        ValueError, match="Repaired requires verified native object storage"
    ):
        UpdateHistoryActionState.model_validate_json(
            json.dumps(value | {"repair": None})
        )


def test_known_file_progress_counts_require_a_declared_unit():
    unknown = VaultProgress.model_validate_json(
        json.dumps({"phase": "current_inspection"})
    )
    assert unknown.completed_units is unknown.total_units is unknown.unit is None
    value = {
        "phase": "publication",
        "completed_units": 1,
        "total_units": 2,
        "unit": "files",
    }
    known = VaultProgress.model_validate_json(json.dumps(value))
    assert (known.completed_units, known.total_units, known.unit) == (1, 2, "files")
    with pytest.raises(ValueError, match="Known progress counts require their unit"):
        VaultProgress.model_validate_json(json.dumps(value | {"unit": None}))


def test_completed_progress_cannot_exceed_its_known_total():
    value = {
        "phase": "publication",
        "completed_units": 1,
        "total_units": 2,
        "unit": "files",
    }
    known = VaultProgress.model_validate_json(json.dumps(value))
    assert known.phase == "publication" and known.completed_units == 1
    assert known.total_units == 2 and known.unit == "files"
    with pytest.raises(
        ValueError, match="Observed completed count exceeds the known total"
    ):
        VaultProgress.model_validate_json(json.dumps(value | {"completed_units": 3}))


def test_an_undo_offer_requires_its_exact_target_receipt_binding(offered_undo_value):
    offered = VaultUndoPreparation.model_validate_json(json.dumps(offered_undo_value))
    assert offered.status == "offered" and offered.generation == 3
    assert offered.checkpoint_commit == "a" * 40
    assert offered.target_receipt_commit == "b" * 40
    assert offered.review.facts.subjects[0].incoming.data == (
        b"Prior authored bytes.\r\n"
    )
    incomplete = dict(offered_undo_value)
    del incomplete["target_receipt_commit"]
    with pytest.raises(
        ValueError, match="Undo offer requires current history and reviewed target"
    ):
        VaultUndoPreparation.model_validate_json(json.dumps(incomplete))


def test_unavailable_undo_cannot_expose_a_retained_review(offered_undo_value):
    value = {
        "schema_id": "brz2obsidian.vault-undo-preparation",
        "schema_version": 1,
        "status": "unavailable",
        "code": "undo_history_or_review_unavailable",
        "review": None,
    }
    unavailable = VaultUndoPreparation.model_validate_json(json.dumps(value))
    assert unavailable.status == "unavailable" and unavailable.review is None
    assert unavailable.checkpoint_commit is unavailable.target_receipt_commit is None
    with pytest.raises(ValueError, match="Unavailable Undo cannot carry a review"):
        VaultUndoPreparation.model_validate_json(
            json.dumps(value | {"review": offered_undo_value["review"]})
        )
