"""Public values describe scoped authority; they never prove native publication."""

import json

import pytest

from brz2obsidian.contracts import (
    AttachmentCandidateValidation,
    ExactContent,
    LinkDocumentValidation,
    ReviewChoiceAvailability,
    ReviewLoadResult,
    ReviewResumeResult,
    ReviewSaveResult,
    SelectedReviewEffects,
)


def test_selected_effects_cannot_conflict_or_survive_a_refused_selection():
    value = {
        "schema_id": "brz2obsidian.selected-review-effects",
        "schema_version": 1,
        "status": "selected",
        "code": "selected",
        "proposal_id": "literal-review",
        "generation": 3,
        "files": (
            {
                "path": "Note.md",
                "subject_id": "note",
                "content": ExactContent(data=b"A\r\n"),
            },
        ),
        "remove_paths": ("Old.md",),
    }
    selected = SelectedReviewEffects.model_validate(value)
    reopened = SelectedReviewEffects.model_validate_json(selected.model_dump_json())
    assert [(row.path, row.content.data) for row in reopened.files] == [
        ("Note.md", b"A\r\n")
    ]
    assert reopened.remove_paths == ("Old.md",)
    with pytest.raises(ValueError, match="also be removed"):
        SelectedReviewEffects.model_validate(value | {"remove_paths": ("Note.md",)})
    with pytest.raises(ValueError, match="unique and sorted"):
        SelectedReviewEffects.model_validate(value | {"files": value["files"] * 2})
    with pytest.raises(ValueError, match="status and identity"):
        SelectedReviewEffects.model_validate(value | {"generation": None})
    refused = value | {
        "status": "refused",
        "code": "review_not_ready",
        "proposal_id": None,
        "generation": None,
    }
    with pytest.raises(ValueError, match="cannot authorize files"):
        SelectedReviewEffects.model_validate(refused)
    empty = SelectedReviewEffects.model_validate(
        refused | {"files": (), "remove_paths": ()}
    )
    assert empty.status == "refused" and not empty.files and not empty.remove_paths


def test_saved_loaded_and_resumed_values_cannot_exchange_current_authority():
    from brz2obsidian.core import load_review, prepare_review, save_review
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import preflight, with_review_links

    plan = prepare_review(with_review_links(request()), preflight=preflight())
    saved = save_review(plan)
    loaded = load_review(saved.record.model_dump_json())
    assert saved.status == "saved" and loaded.status == "loaded"
    assert loaded.ready is False and loaded.loaded.ready is False
    save_value = saved.model_dump(mode="python")
    with pytest.raises(ValueError, match="saved record"):
        ReviewSaveResult.model_validate(save_value | {"record": None})
    with pytest.raises(ValueError, match="saved record"):
        ReviewSaveResult.model_validate(save_value | {"code": "invalid_review"})
    load_value = loaded.model_dump(mode="python")
    with pytest.raises(ValueError, match="unready loaded value"):
        ReviewLoadResult.model_validate(load_value | {"loaded": None})
    with pytest.raises(ValueError, match="explicit Boolean"):
        ReviewLoadResult.model_validate(load_value | {"ready": 0})
    resume_value = {
        "schema_id": "brz2obsidian.review-resume-result",
        "schema_version": 1,
        "status": "resumed",
        "code": "unchanged",
        "loaded": loaded.loaded,
        "plan": plan,
        "ready": False,
    }
    resumed = ReviewResumeResult.model_validate(resume_value)
    assert resumed.plan == plan and not resumed.ready
    with pytest.raises(ValueError, match="loaded provenance"):
        ReviewResumeResult.model_validate(resume_value | {"loaded": None})
    with pytest.raises(ValueError, match="current plan"):
        ReviewResumeResult.model_validate(resume_value | {"status": "refused"})
    assert loaded.loaded.saved.plan == plan and not loaded.ready


def test_blocking_link_and_attachment_findings_cannot_be_labelled_valid():
    warning = {
        "code": "existing_link_warning",
        "document_id": "manual-note",
        "occurrence_id": "literal-link",
        "blocking": False,
    }
    blocker = warning | {"code": "link_meaning_mismatch", "blocking": True}
    good = LinkDocumentValidation.model_validate_json(
        json.dumps({"valid": True, "findings": [warning]})
    )
    assert good.valid and good.findings[0].code == "existing_link_warning"
    with pytest.raises(ValueError, match="blocking findings"):
        LinkDocumentValidation.model_validate({"valid": True, "findings": (blocker,)})
    blocked = LinkDocumentValidation.model_validate(
        {"valid": False, "findings": (blocker,)}
    )
    assert not blocked.valid and blocked.findings[0].occurrence_id == "literal-link"
    with pytest.raises(ValueError, match="blocking findings"):
        AttachmentCandidateValidation.model_validate(
            {"valid": True, "findings": (), "link_findings": (blocker,)}
        )
    attachment = AttachmentCandidateValidation.model_validate(
        {"valid": False, "findings": (), "link_findings": (blocker,)}
    )
    assert not attachment.valid and not attachment.findings
    available = ReviewChoiceAvailability(choice="incoming", enabled=True, reasons=())
    assert available.enabled
    with pytest.raises(ValueError, match="shared reason"):
        ReviewChoiceAvailability(choice="incoming", enabled=False, reasons=())
    unavailable = ReviewChoiceAvailability(
        choice="incoming", enabled=False, reasons=("source_unavailable",)
    )
    assert unavailable.reasons == ("source_unavailable",)


def test_worker_sequence_and_terminal_identity_do_not_cross_operation_boundaries(
    tmp_path,
):
    from brz2obsidian.application.contracts import (
        CheckResult,
        InspectArguments,
        ProtocolError,
        WorkerRequest,
        WorkerResponse,
    )
    from brz2obsidian.application.protocol import decode_request, encode_request
    from brz2obsidian.application.update_context_contracts import UpdateContextResult

    request = WorkerRequest(
        request_id="11111111-1111-4111-8111-111111111111",
        operation="inspect",
        arguments=InspectArguments(source=str(tmp_path / "source.brz")),
    )
    assert decode_request(encode_request(request)) == request
    with pytest.raises(ValueError, match="One-shot"):
        WorkerRequest.model_validate(
            request.model_dump(mode="python", by_alias=True) | {"sequence": 1}
        )
    update = {
        "request_id": request.request_id,
        "operation": "update",
        "sequence": 1,
        "arguments": {
            "command": "load",
            "vault": str(tmp_path),
            "selection_id": request.request_id,
        },
    }
    current = WorkerRequest.model_validate(update)
    assert decode_request(encode_request(current)) == current
    with pytest.raises(ValueError, match="persistent request sequence"):
        WorkerRequest.model_validate(update | {"sequence": None})
    error = ProtocolError(
        code="internal_error", message="The operation could not complete."
    )
    terminal = WorkerResponse(
        request_id=request.request_id, operation="inspect", protocol_error=error
    )
    assert terminal.result is None and terminal.protocol_error == error
    with pytest.raises(ValueError, match="Exactly one"):
        WorkerResponse(request_id=request.request_id, operation="inspect")
    with pytest.raises(ValueError, match="operation disagrees"):
        WorkerResponse(
            request_id=request.request_id,
            operation="inspect",
            result=CheckResult(outcome="failed", status="check_failed"),
        )
    update_result = UpdateContextResult(
        kind="source_update", status="refused", code="context_changed"
    )
    update_terminal = WorkerResponse(
        request_id=request.request_id,
        operation="update",
        sequence=1,
        result=update_result,
    )
    assert update_terminal.result.code == "context_changed"
    with pytest.raises(ValueError, match="operation disagrees"):
        WorkerResponse(
            request_id=request.request_id,
            operation="inspect",
            result=update_result,
        )
    with pytest.raises(ValueError, match="sequence differs"):
        WorkerResponse(
            request_id=request.request_id, operation="update", protocol_error=error
        )


def test_publication_and_listing_descriptions_require_their_own_evidence(tmp_path):
    from brz2obsidian.application.contracts import (
        BrainListResult,
        CheckResult,
        ConversionResult,
        DiagnosticOmission,
        Publication,
    )

    publication = Publication(
        state="published_verified",
        destination=str(tmp_path / "vault"),
        receipt_verified=True,
    )
    assert publication.destination == str(tmp_path / "vault")
    assert publication.receipt_verified
    with pytest.raises(ValueError, match="requires a destination"):
        Publication(state="published_verified", receipt_verified=True)
    with pytest.raises(ValueError, match="Created requires"):
        ConversionResult(
            outcome="clean",
            status="conversion_created",
            publication=Publication(state="not_published"),
        )
    with pytest.raises(ValueError, match="check result"):
        CheckResult(outcome="clean", status="check_clean", publication=publication)
    omission = DiagnosticOmission(findings_count=2)
    with pytest.raises(ValueError, match="omission must be disclosed"):
        CheckResult(
            outcome="failed", status="check_failed", diagnostic_omission=omission
        )
    disclosed = CheckResult(
        outcome="failed",
        status="check_failed",
        diagnostic_omission=omission,
        diagnostic_text="Two findings omitted.",
    )
    assert disclosed.diagnostic_omission.findings_count == 2
    brain = {
        "brain_id": "11111111-1111-4111-8111-111111111111",
        "name": "Literal Brain",
    }
    listed = BrainListResult(outcome="clean", status="brains_listed", brains=(brain,))
    assert [row.name for row in listed.brains] == ["Literal Brain"]
    with pytest.raises(ValueError, match="distinct"):
        BrainListResult(outcome="clean", status="brains_listed", brains=(brain, brain))
    with pytest.raises(ValueError, match="Failed listing"):
        BrainListResult(outcome="failed", status="brains_failed", brains=(brain,))
