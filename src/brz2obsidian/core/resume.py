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
from .resolution import _reconstruct_review, validate_review
from .selected_effects import _project_review_effects


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


def _load_result(code, saved=None, effects=None):
    result = ReviewLoadResult(
        schema_id="brz2obsidian.review-load-result",
        schema_version=1,
        status="loaded" if saved is not None else "refused",
        code=code,
        loaded={
            "schema_id": "brz2obsidian.loaded-review",
            "schema_version": 1,
            "saved": saved,
            "readiness": "revalidation_required",
            "ready": False,
        }
        if saved is not None
        else None,
        ready=False,
    )
    if result.loaded is not None:
        result.loaded._historical_effects = effects
    return result


def load_review(raw: str | bytes | SavedReview) -> ReviewLoadResult:
    try:
        if isinstance(raw, SavedReview):
            saved = SavedReview.model_validate(raw.model_dump(mode="python"))
        elif type(raw) is bytes:
            raw = raw.decode("utf-8")
            raw.encode("utf-8")
            saved = SavedReview.model_validate_json(raw)
        elif type(raw) is str:
            raw.encode("utf-8")
            saved = SavedReview.model_validate_json(raw)
        else:
            return _load_result("invalid_record")
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
        _load_result("loaded", saved, _project_review_effects(validated.plan))
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


def _load_local_review(saved: SavedReview) -> ReviewLoadResult:
    """Verified local memo ingress only: reinterpret one historical derived cache.

    The storage caller owns graph/boundary/integrity admission. This is not a
    raw-load option, and no authority-bearing field may differ after full replay.
    The returned SavedReview is canonical in memory; recorded bytes stay intact.
    """
    old = saved.plan
    replayed = _reconstruct_review(old)
    if replayed.status != "accepted":
        return _load_result("invalid_review")
    canonical = replayed.plan
    effects = _project_review_effects(canonical)
    if canonical == old:
        return _load_result("loaded", saved, effects)
    if (
        old.facts.format_operation.kind != "source_update"
        or old.requirements
        or old.blockers != ("selected_link_context_conflict",)
        or old.readiness != "refused"
        or old.ready is not False
    ):
        return _load_result("invalid_review")
    if (
        canonical.requirements
        or canonical.blockers
        or canonical.readiness != "ready"
        or canonical.ready is not True
        or effects.status != "selected"
        or old.model_copy(
            update={
                "blockers": canonical.blockers,
                "readiness": canonical.readiness,
                "ready": canonical.ready,
            }
        )
        != canonical
    ):
        return _load_result("invalid_review")
    return _load_result(
        "loaded",
        SavedReview(
            schema_id="brz2obsidian.saved-review", schema_version=1, plan=canonical
        ),
        effects,
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
