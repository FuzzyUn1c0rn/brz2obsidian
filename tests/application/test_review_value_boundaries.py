"""Public review values reject contradictory scope without asserting native facts."""

import json

import pytest

from brz2obsidian.application.contracts import (
    ApiAcquisitionConfig,
    BrainChoice,
    ConversionResult,
    InspectionResult,
    LocalApiSourceSelection,
    SelectSource,
    SourceArguments,
)
from brz2obsidian.application.history_workflow_contracts import HistoryWorkflowPreparation
from brz2obsidian.application.update_contracts import UpdatePreparation
from brz2obsidian.contracts import StructureField, StructureSpan


def json_contract(model, value):
    parsed = model.model_validate_json(json.dumps(value))
    return model.model_validate_json(parsed.model_dump_json(by_alias=True))


def api_selection_value():
    return {
        "kind": "local-api",
        "brain_id": "11111111-1111-4111-8111-111111111111",
        "config": ApiAcquisitionConfig().model_dump(mode="json"),
    }


@pytest.fixture
def inspection_value(tmp_path):
    return {
        "outcome": "clean",
        "status": "inspection_clean",
        "reviewed": {
            "schema": "brz2obsidian.review",
            "schema_version": 3,
            "source_selection": {"kind": "brz", "path": str(tmp_path / "source.brz")},
            "source_identity": {
                "source_id": "literal-collection",
                "module_id": "literal-module",
                "module_version": "1",
                "format_version": "5",
                "source_sha256": "a" * 64,
                "snapshot_digest": "b" * 64,
            },
            "converter_version": "literal-converter",
            "profile_id": "literal-profile",
            "profile_version": "1",
            "outcome": "clean",
        },
    }


@pytest.fixture
def current_preparation_value():
    from tests.application.test_update_lifecycle_contracts import preparation

    prepared = preparation()
    assert prepared.kind == "source_update" and not prepared.review.ready
    assert prepared.review.facts.subjects[0].incoming.data == b"incoming\n"
    return json.loads(prepared.model_dump_json())


def test_local_api_json_selection_requires_explicit_effective_configuration():
    value = api_selection_value()
    selected = json_contract(LocalApiSourceSelection, value)
    assert selected.brain_id == "11111111-1111-4111-8111-111111111111"
    assert selected.config.api_url == "http://127.0.0.1:11522/api"
    incomplete = dict(value)
    del incomplete["config"]
    with pytest.raises(ValueError, match="Explicit acquisition configuration is required"):
        json_contract(LocalApiSourceSelection, incomplete)


def test_local_api_selection_cannot_name_the_zero_brain_identity():
    value = api_selection_value()
    selected = json_contract(LocalApiSourceSelection, value)
    assert selected.kind == "local-api" and selected.brain_id.startswith("11111111-")
    with pytest.raises(ValueError, match="A nonzero Brain UUID is required"):
        json_contract(
            LocalApiSourceSelection,
            value | {"brain_id": "00000000-0000-0000-0000-000000000000"},
        )


def test_python_source_arguments_choose_one_legacy_or_typed_archive(tmp_path):
    path = str(tmp_path / "source.brz")
    legacy = SourceArguments.model_validate({"source": path})
    typed = json_contract(SourceArguments, {"source_selection": {"kind": "brz", "path": path}})
    assert legacy.source == typed.source == path
    assert json_contract(SourceArguments, json.loads(legacy.model_dump_json())).source == path
    with pytest.raises(ValueError, match="Choose one source selection"):
        SourceArguments.model_validate({"source": path, "source_selection": typed.source_selection})


def test_clean_inspection_requires_its_review(inspection_value):
    inspected = json_contract(InspectionResult, inspection_value)
    assert inspected.outcome == inspected.reviewed.outcome == "clean"
    assert inspected.reviewed.profile_id == "literal-profile"
    with pytest.raises(ValueError, match="Only usable inspections carry a review"):
        json_contract(InspectionResult, inspection_value | {"reviewed": None})


def test_inspection_and_review_keep_the_same_warning_outcome(inspection_value):
    value = inspection_value | {
        "outcome": "warnings",
        "status": "inspection_warnings",
        "reviewed": inspection_value["reviewed"] | {"outcome": "warnings"},
    }
    inspected = json_contract(InspectionResult, value)
    assert inspected.outcome == inspected.reviewed.outcome == "warnings"
    with pytest.raises(ValueError, match="Review outcome disagrees with inspection"):
        json_contract(InspectionResult, value | {"outcome": "clean", "status": "inspection_clean"})


def test_inspection_does_not_describe_a_publication(inspection_value):
    inspected = json_contract(InspectionResult, inspection_value)
    assert inspected.publication is None and inspected.reviewed is not None
    with pytest.raises(ValueError, match="Inspection cannot publish"):
        json_contract(InspectionResult, inspection_value | {
            "publication": {"state": "not_published", "receipt_verified": False}
        })


def test_conversion_status_agrees_with_its_outcome_and_receipt(tmp_path):
    value = {
        "outcome": "clean",
        "status": "conversion_created",
        "publication": {
            "state": "published_verified",
            "destination": str(tmp_path / "vault"),
            "receipt_verified": True,
        },
    }
    result = json_contract(ConversionResult, value)
    assert result.outcome == "clean" and result.status == "conversion_created"
    assert result.publication.destination == str(tmp_path / "vault")
    with pytest.raises(ValueError, match="Conversion status disagrees with outcome/receipt"):
        json_contract(ConversionResult, value | {"status": "conversion_created_with_warnings"})


def test_brain_choices_require_a_named_canonical_identity():
    value = {"brain_id": "11111111-1111-4111-8111-111111111111", "name": "Literal Brain"}
    choice = json_contract(BrainChoice, value)
    assert choice.brain_id == value["brain_id"] and choice.name == "Literal Brain"
    with pytest.raises(ValueError, match="A named canonical Brain is required"):
        json_contract(BrainChoice, value | {"name": "   "})


def test_json_picker_requires_typed_source_selection(tmp_path):
    path = str(tmp_path / "source.brz")
    typed = json_contract(SelectSource, {"source_selection": {"kind": "brz", "path": path}})
    assert typed.path_or_null == path and typed.source_selection.kind == "brz"
    with pytest.raises(ValueError, match="Typed source selection is required in JSON"):
        json_contract(SelectSource, {"path_or_null": path})


def test_python_picker_cannot_mix_legacy_and_typed_selections(tmp_path):
    path = str(tmp_path / "source.brz")
    legacy = SelectSource.model_validate({"path_or_null": path})
    typed = json_contract(SelectSource, {"source_selection": {"kind": "brz", "path": path}})
    assert legacy.path_or_null == typed.path_or_null == path
    with pytest.raises(ValueError, match="Choose one source selection"):
        SelectSource.model_validate({"path_or_null": path, "source_selection": typed.source_selection})


def test_update_preparation_keeps_the_kind_of_its_review(current_preparation_value):
    prepared = json_contract(UpdatePreparation, current_preparation_value)
    assert prepared.kind == prepared.review.facts.format_operation.kind == "source_update"
    with pytest.raises(ValueError, match="Preparation kind differs from its review"):
        json_contract(UpdatePreparation, current_preparation_value | {"kind": "format_transition"})


def test_ordinary_update_preparation_requires_retained_history(current_preparation_value):
    prepared = json_contract(UpdatePreparation, current_preparation_value)
    assert prepared.locator.association.collection_id == "folio:collection"
    assert prepared.review.facts.subjects[0].incoming.data == b"incoming\n"
    with pytest.raises(ValueError, match="Ordinary updates require retained history"):
        json_contract(UpdatePreparation, current_preparation_value | {"locator": None})


def test_historical_reference_qualification_is_reserved_for_onboarding(
    current_preparation_value, tmp_path
):
    prepared = json_contract(UpdatePreparation, current_preparation_value)
    assert prepared.kind == "source_update" and prepared.original_source_ref is None
    with pytest.raises(ValueError, match="Historical reference qualification belongs to onboarding"):
        json_contract(UpdatePreparation, current_preparation_value | {
            "original_source_ref": str(tmp_path / "historical-reference.brz")
        })


def test_undo_workflow_cannot_borrow_a_history_copy_path(
    current_preparation_value, tmp_path
):
    value = {
        "kind": "undo",
        "vault": str(tmp_path / "vault"),
        "native": {
            "schema_id": "brz2obsidian.vault-undo-preparation",
            "schema_version": 1,
            "status": "offered",
            "code": "latest_undo_review_required",
            "checkpoint_commit": "a" * 40,
            "generation": 1,
            "target_receipt_commit": "b" * 40,
            "review": current_preparation_value["review"],
        },
    }
    offered = json_contract(HistoryWorkflowPreparation, value)
    assert offered.kind == "undo" and not offered.ready and offered.copy_path is None
    assert offered.native.target_receipt_commit == "b" * 40
    with pytest.raises(ValueError, match="History workflow must retain the exact admitted native role"):
        json_contract(HistoryWorkflowPreparation, value | {"copy_path": str(tmp_path / "copy")})


def test_retained_cleanup_can_be_ready_without_a_file_review(tmp_path):
    value = {
        "kind": "recovery",
        "vault": str(tmp_path / "vault"),
        "native": {
            "schema_id": "brz2obsidian.vault-recovery-preparation",
            "schema_version": 1,
            "status": "cleanup",
            "code": "terminal_cleanup_required",
            "operation_id": "a" * 32,
            "kind": "apply",
            "generation": 7,
            "intent_commit": "b" * 40,
            "available_directions": [],
            "direction": None,
            "review": None,
        },
    }
    cleanup = json_contract(HistoryWorkflowPreparation, value)
    assert cleanup.ready and cleanup.kind == "recovery"
    assert cleanup.native.status == "cleanup" and cleanup.native.review is None
    assert cleanup.native.direction is None and cleanup.native.available_directions == ()
    assert cleanup.native.operation_id == "a" * 32 and cleanup.native.generation == 7
    assert cleanup.native.intent_commit == "b" * 40


def test_structure_spans_preserve_the_order_of_exact_byte_boundaries():
    span = json_contract(StructureSpan, {"start": 1, "end": 3})
    assert b"abcd"[span.start:span.end] == b"bc"
    with pytest.raises(ValueError, match="Structure span ends before its start"):
        json_contract(StructureSpan, {"start": 3, "end": 1})


def test_identity_components_cannot_be_relabelled_as_ordinary_scalars():
    raw = b"source_item_id: entry:opening\n"
    value = {
        "key": "source_item_id",
        "kind": "identity",
        "identity_component": "item",
        "value": "entry:opening",
        "scalar_type": "string",
        "span": {"start": 0, "end": len(raw)},
        "value_span": {"start": 16, "end": 29},
    }
    identity = json_contract(StructureField, value)
    assert identity.identity_component == "item" and identity.kind == "identity"
    assert raw[identity.value_span.start:identity.value_span.end] == b"entry:opening"
    with pytest.raises(ValueError, match="Identity components require an identity field"):
        json_contract(StructureField, value | {"kind": "scalar"})
