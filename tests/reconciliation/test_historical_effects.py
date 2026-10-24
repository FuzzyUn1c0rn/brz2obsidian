"""Historical selected values remain separate from current review authority."""

import json

import pytest
from pydantic import ValidationError

from brz2obsidian.core import (
    load_review,
    prepare_review,
    resolve_review,
    resume_review,
    save_review,
    select_review_effects,
)
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links


def ready_saved_review():
    offered = prepare_review(with_review_links(request()), preflight=preflight())
    chosen = resolve_review(offered, action(offered))
    assert chosen.plan.ready
    saved = save_review(chosen.plan)
    assert saved.status == "saved"
    return saved.record


def test_load_reports_exact_historical_files_without_current_readiness_or_disk_changes():
    saved = ready_saved_review()
    original = saved.model_dump_json()
    result = load_review(saved)
    assert result.status == "loaded" and result.ready is False
    loaded = result.loaded
    assert loaded.ready is False and loaded.readiness == "revalidation_required"
    effects = loaded.historical_effects
    assert effects.status == "selected"
    assert [(row.path, row.content.data) for row in effects.files] == [
        ("Notes/Opening.md", b"incoming\n")
    ]
    assert effects.remove_paths == ()
    assert saved.model_dump_json() == original
    assert "historical_effects" not in loaded.model_dump()
    assert "historical_effects" not in type(loaded).model_fields
    assert "historical_effects" not in type(loaded).model_json_schema()["properties"]
    forged = json.loads(original)
    forged["historical_effects"] = effects.model_dump(mode="json")
    assert load_review(json.dumps(forged)).code == "invalid_record"
    forged_loaded = json.loads(loaded.model_dump_json())
    forged_loaded["historical_effects"] = effects.model_dump(mode="json")
    with pytest.raises(ValidationError):
        type(loaded).model_validate_json(json.dumps(forged_loaded))


def test_historical_selection_cannot_make_changed_current_facts_ready():
    saved = ready_saved_review()
    loaded = load_review(saved).loaded
    assert loaded.historical_effects.status == "selected"
    actual = with_review_links(
        request(current=b"Later independent writing.\r\n", generation=2)
    )
    result = resume_review(loaded, actual, preflight=saved.plan.preflight)
    assert result.status == "resumed" and not result.ready
    assert (
        result.plan.proposal.changes[0].current.data
        == b"Later independent writing.\r\n"
    )
    selected = select_review_effects(result.plan)
    assert selected.status == "refused" and selected.files == ()


def test_forged_saved_readiness_and_public_selection_remain_refused():
    offered = prepare_review(with_review_links(request()), preflight=preflight())
    forged = offered.model_copy(update={"ready": True, "requirements": ()})
    assert select_review_effects(forged).status == "refused"
    saved = ready_saved_review().model_copy(update={"plan": forged})
    loaded = load_review(saved)
    assert loaded.status == "refused" and loaded.loaded is None
    assert loaded.ready is False
