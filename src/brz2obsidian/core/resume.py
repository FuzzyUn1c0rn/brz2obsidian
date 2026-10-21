"""Save/load exact review values; historical validation never observes current state."""

from pydantic import ValidationError

from brz2obsidian.contracts import (
    LoadedReview,
    ReconciliationInput,
    ReviewLoadResult,
    ReviewPlan,
    ReviewPreflight,
    ReviewResumeResult,
    ReviewSaveResult,
    SavedReview,
)

from .refresh import refresh_review
from .resolution import validate_review


def save_review(plan: ReviewPlan) -> ReviewSaveResult:
    try:
        validated = validate_review(plan)
    except ValueError:
        validated = None
    return ReviewSaveResult(
        schema_id="brz2obsidian.review-save-result",
        schema_version=1,
        status="saved"
        if validated is not None and validated.status == "accepted"
        else "refused",
        code="saved"
        if validated is not None and validated.status == "accepted"
        else "invalid_review",
        record=SavedReview(
            schema_id="brz2obsidian.saved-review", schema_version=1, plan=validated.plan
        )
        if validated is not None and validated.status == "accepted"
        else None,
    )


def _load_result(code, saved=None):
    return ReviewLoadResult(
        schema_id="brz2obsidian.review-load-result",
        schema_version=1,
        status="loaded" if saved is not None else "refused",
        code=code,
        loaded=LoadedReview(
            schema_id="brz2obsidian.loaded-review",
            schema_version=1,
            saved=saved,
            readiness="revalidation_required",
            ready=False,
        )
        if saved is not None
        else None,
        ready=False,
    )


def load_review(raw: str | bytes) -> ReviewLoadResult:
    try:
        if type(raw) is bytes:
            raw = raw.decode("utf-8")
        elif type(raw) is not str:
            return _load_result("invalid_record")
        raw.encode("utf-8")
        saved = SavedReview.model_validate_json(raw)
    except ValidationError as error:
        for problem in error.errors():
            if problem["type"] == "literal_error":
                if problem["loc"][-1:] == ("schema_id",):
                    return _load_result("unsupported_schema")
                if problem["loc"][-1:] == ("schema_version",):
                    return _load_result("unsupported_version")
        return _load_result("invalid_record")
    except ValueError, RecursionError:
        return _load_result("invalid_record")
    try:
        validated = validate_review(saved.plan)
    except ValueError:
        return _load_result("invalid_review")
    return (
        _load_result("loaded", saved)
        if validated.status == "accepted"
        else _load_result("invalid_review")
    )


def _resume_result(status, code, loaded=None, plan=None):
    return ReviewResumeResult(
        schema_id="brz2obsidian.review-resume-result",
        schema_version=1,
        status=status,
        code=code,
        loaded=loaded,
        plan=plan,
        ready=plan is not None and plan.ready,
    )


def resume_review(
    loaded: LoadedReview, facts: ReconciliationInput, *, preflight: ReviewPreflight
) -> ReviewResumeResult:
    try:
        loaded = LoadedReview.model_validate(loaded)
    except ValueError:
        return _resume_result("refused", "invalid_loaded")
    try:
        historical = validate_review(loaded.saved.plan)
    except ValueError:
        return _resume_result("refused", "invalid_review", loaded)
    if historical.status != "accepted":
        return _resume_result("refused", "invalid_review", loaded)
    try:
        facts = ReconciliationInput.model_validate(facts)
        preflight = ReviewPreflight.model_validate(preflight)
    except ValueError:
        return _resume_result("refused", "invalid_current_facts", loaded)
    if facts == historical.plan.facts and preflight == historical.plan.preflight:
        return _resume_result("resumed", "unchanged", loaded, historical.plan)
    refreshed = refresh_review(historical.plan, facts, preflight=preflight)
    return (
        _resume_result("resumed", "refreshed", loaded, refreshed.plan)
        if refreshed.status == "accepted"
        else _resume_result(refreshed.status, refreshed.code, loaded)
    )
