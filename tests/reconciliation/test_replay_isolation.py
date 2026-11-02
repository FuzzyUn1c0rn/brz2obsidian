"""Repeated public review calls retain exact authority and independent values."""

import pytest

from brz2obsidian.contracts import ExactContent, ReviewPlan
from brz2obsidian.core import (
    load_review,
    prepare_review,
    refresh_review,
    resolve_review,
    save_review,
    select_review_effects,
    validate_review,
)
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links


def reviewed(*, incoming=b"incoming\n", state="validated:state:1"):
    initial = prepare_review(
        with_review_links(request(incoming=incoming)),
        preflight=preflight().model_copy(update={"state_fingerprint": state}),
    )
    result = resolve_review(initial, action(initial))
    assert result.status == "accepted" and result.plan.ready
    return result.plan


def assert_selected(plan, expected):
    selected = select_review_effects(plan)
    assert selected.status == "selected" and selected.remove_paths == ()
    assert [(row.path, row.content.data) for row in selected.files] == [
        ("Notes/Opening.md", expected)
    ]


@pytest.mark.parametrize("forgery", ("ready", "approval", "producer"))
def test_warm_review_refuses_derived_forgery_without_poisoning(forgery):
    original = reviewed()
    assert validate_review(original).status == "accepted"
    assert_selected(original, b"incoming\n")
    saved = save_review(original).record.model_dump_json()
    if forgery == "ready":
        forged = original.model_copy(update={"ready": False})
    elif forgery == "approval":
        forged = original.model_copy(
            update={
                "approvals": (
                    original.approvals[0].model_copy(
                        update={"result": ExactContent(data=b"Unreviewed output")}
                    ),
                )
            }
        )
    else:
        forged = original.model_copy(
            update={
                "producer_facts": original.producer_facts.model_copy(
                    update={"proposal_id": "foreign:producer"}
                )
            }
        )
    assert validate_review(forged).code == "invalid_plan"
    assert select_review_effects(forged).status == "refused"
    assert save_review(forged).code == "invalid_review"
    loaded = load_review(saved)
    assert loaded.status == "loaded" and not loaded.ready
    assert loaded.loaded.historical_effects.files[0].content.data == b"incoming\n"
    assert_selected(loaded.loaded.saved.plan, b"incoming\n")


def test_returned_review_and_nested_content_cannot_poison_later_calls():
    original = reviewed()
    record = save_review(original).record.model_dump_json()
    returned = validate_review(original).plan
    # Frozen assignment alone would not exercise a caller bypassing that guard.
    object.__setattr__(returned, "ready", False)
    returned.proposal.changes[0].incoming.__dict__["data"] = b"Poisoned nested value"
    fresh = load_review(record)
    assert fresh.status == "loaded" and not fresh.loaded.ready
    checked = validate_review(fresh.loaded.saved.plan)
    assert checked.status == "accepted" and checked.plan.ready
    assert checked.plan.proposal.changes[0].incoming.data == b"incoming\n"
    assert_selected(checked.plan, b"incoming\n")


def test_equal_identifiers_keep_distinct_initial_facts_preflight_and_suffix():
    first = reviewed(incoming=b"First source\n", state="state:first")
    second = reviewed(incoming=b"Second source\n", state="state:second")
    assert first.proposal.proposal_id == second.proposal.proposal_id == "review:one"
    assert first.proposal.generation == second.proposal.generation == 1
    assert first.actions[0].decision_id == second.actions[0].decision_id
    for plan, literal, state in (
        (first, b"First source\n", "state:first"),
        (second, b"Second source\n", "state:second"),
        (first, b"First source\n", "state:first"),
    ):
        checked = validate_review(plan)
        assert checked.status == "accepted"
        assert checked.plan.preflight.state_fingerprint == state
        assert_selected(checked.plan, literal)
    initial = prepare_review(
        with_review_links(request(incoming=b"First source\n")),
        preflight=first.preflight,
    )
    kept = resolve_review(initial, action(initial, choice="current"))
    assert kept.status == "accepted" and kept.plan.ready
    assert kept.plan.history.events != first.history.events
    assert_selected(kept.plan, b"original\r\n")
    assert_selected(first, b"First source\n")


def test_forged_refresh_metadata_and_changed_suffix_remain_untrusted():
    original = reviewed()
    later = with_review_links(request(current=b"Later local\n", generation=2))
    refreshed = refresh_review(original, later, preflight=preflight())
    assert refreshed.status == "accepted" and not refreshed.plan.ready
    event = refreshed.plan.history.events[-1]
    assert event.changed_keys
    forged = refreshed.plan.model_copy(
        update={
            "history": refreshed.plan.history.model_copy(
                update={
                    "events": original.history.events
                    + (event.model_copy(update={"changed_keys": ()}),)
                }
            )
        }
    )
    assert validate_review(forged).code == "invalid_plan"
    assert select_review_effects(forged).status == "refused"
    assert validate_review(refreshed.plan).status == "accepted"
    chosen = resolve_review(
        refreshed.plan,
        action(refreshed.plan, choice="current", decision_id="after:refresh"),
    )
    assert chosen.status == "accepted" and chosen.plan.ready
    assert_selected(chosen.plan, b"Later local\n")
    other = refresh_review(
        original,
        with_review_links(request(current=b"Other later local\n", generation=2)),
        preflight=preflight(),
    )
    chosen_other = resolve_review(
        other.plan, action(other.plan, choice="current", decision_id="after:refresh")
    )
    assert chosen_other.status == "accepted"
    assert_selected(chosen_other.plan, b"Other later local\n")
    assert_selected(chosen.plan, b"Later local\n")


def test_malformed_nested_history_cannot_use_a_warm_result():
    original = reviewed()
    assert validate_review(original).status == "accepted"
    independent = ReviewPlan.model_validate_json(original.model_dump_json())
    facts = original.history.initial_facts
    current = facts.subjects[0].current.model_copy(
        update={
            "content": ExactContent.model_construct(data="not bytes", reference=None)
        }
    )
    bad_facts = facts.model_copy(
        update={"subjects": (facts.subjects[0].model_copy(update={"current": current}),)}
    )
    forged = original.model_copy(
        update={"history": original.history.model_copy(update={"initial_facts": bad_facts})}
    )
    assert select_review_effects(forged).status == "refused"
    assert save_review(forged).code == "invalid_review"
    assert_selected(independent, b"incoming\n")
