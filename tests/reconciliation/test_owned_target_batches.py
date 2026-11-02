"""Explicit canonical ownership queries share one public batch admission."""

import pytest

from brz2obsidian.core import prepare_review, resolve_review
from tests.reconciliation.test_identity import inventory_item, with_subjects
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links


def origin(*, ending_path="Notes/Ending.md"):
    facts = request(original=b"base\n", current=b"base\n", incoming=b"opening\n")
    entry = inventory_item("ending-entry", "entry:ending", ending_path, b"base\n")
    second = facts.subjects[0].model_copy(
        update={
            "item_id": "entry:ending",
            "path": ending_path,
            "current": entry.current,
            "source_target": entry.target,
        }
    )
    facts = with_subjects(
        facts, facts.subjects + (second,), facts.identity_inventory + (entry,)
    )
    facts = with_review_links(facts)
    plan = prepare_review(facts, preflight=preflight())
    for item in ("entry:opening", "entry:ending"):
        change = next(c for c in plan.proposal.changes if c.item_id == item)
        chosen = resolve_review(
            plan, action(plan, change, decision_id="approve:" + item)
        )
        assert chosen.status == "accepted"
        plan = chosen.plan
    assert plan.ready
    return plan


def queries(plan):
    return tuple((a.change_id, a.decision_id) for a in plan.approvals)


def test_explicit_multiple_queries_return_literal_owned_targets_in_query_order():
    from brz2obsidian.core import review_owned_target_groups

    plan = origin()
    groups = review_owned_target_groups(plan, queries(plan))
    assert isinstance(groups, tuple)
    actual = tuple(
        tuple((t.target_id, t.canonical_path) for t in group) for group in groups
    )
    assert actual == (
        (("review:opening-entry", "Notes/Opening.md"),),
        (("review:ending-entry", "Notes/Ending.md"),),
    )


def test_query_order_repetition_and_returned_value_isolation():
    from brz2obsidian.core import review_owned_target_groups

    plan = origin()
    first, second = queries(plan)
    groups = review_owned_target_groups(plan, (second, first, second))
    assert tuple(group[0].canonical_path for group in groups) == (
        "Notes/Ending.md",
        "Notes/Opening.md",
        "Notes/Ending.md",
    )
    groups[0][0].__dict__["canonical_path"] = "Foreign.md"
    again = review_owned_target_groups(plan, (second,))
    assert again[0][0].canonical_path == "Notes/Ending.md"
    assert review_owned_target_groups(plan, ()) == ()


def test_empty_queries_still_require_canonical_ready_origin():
    from brz2obsidian.core import review_owned_target_groups

    plan = origin()
    assert review_owned_target_groups(plan, ()) == ()
    initial = prepare_review(with_review_links(request()), preflight=preflight())
    assert not initial.ready
    for invalid in (initial, plan.model_copy(update={"approvals": ()})):
        with pytest.raises(ValueError, match="canonical ready origin"):
            review_owned_target_groups(invalid, ())


def test_same_query_identifiers_do_not_reuse_changed_origin_targets():
    from brz2obsidian.core import review_owned_target_groups, review_owned_targets

    first = origin()
    assert review_owned_target_groups(first, queries(first))[1][0].canonical_path == (
        "Notes/Ending.md"
    )
    changed = origin(ending_path="Notes/Other.md")
    groups = review_owned_target_groups(changed, queries(changed)[1:])
    assert tuple(t.canonical_path for t in groups[0]) == ("Notes/Other.md",)
    single = review_owned_targets(changed, *queries(changed)[1])
    assert tuple(t.canonical_path for t in single) == ("Notes/Other.md",)


@pytest.mark.parametrize("foreign", ("change", "decision"))
def test_queries_must_match_the_exact_origin_approval(foreign):
    from brz2obsidian.core import review_owned_target_groups, review_owned_targets

    plan = origin()
    change, decision = queries(plan)[0]
    query = ("foreign", decision) if foreign == "change" else (change, "foreign")
    with pytest.raises(ValueError, match="Origin decision"):
        review_owned_target_groups(plan, (queries(plan)[0], query))
    with pytest.raises(ValueError, match="Origin decision"):
        review_owned_targets(plan, *query)


@pytest.mark.parametrize("forgery", ("ready", "approval", "history"))
def test_warm_batch_does_not_admit_forged_origin_or_poison_later_calls(forgery):
    from brz2obsidian.core import review_owned_target_groups

    plan = origin()
    requests = queries(plan)
    assert len(review_owned_target_groups(plan, requests)) == 2
    if forgery == "ready":
        forged = plan.model_copy(update={"ready": False})
    elif forgery == "approval":
        forged = plan.model_copy(update={"approvals": plan.approvals[:1]})
    else:
        forged = plan.model_copy(
            update={"history": plan.history.model_copy(update={"events": ()})}
        )
    with pytest.raises(ValueError, match="canonical ready origin"):
        review_owned_target_groups(forged, requests)
    groups = review_owned_target_groups(plan, requests)
    assert tuple(group[0].canonical_path for group in groups) == (
        "Notes/Opening.md",
        "Notes/Ending.md",
    )


def test_attachment_and_operation_reversal_keep_their_direct_owned_outputs():
    from brz2obsidian.core import review_owned_target_groups
    from tests.reconciliation.test_reversal_outputs import both_reversal_facts

    facts, attachment = both_reversal_facts(with_origin=True)
    prepared = prepare_review(facts, preflight=preflight())
    reversal = resolve_review(
        prepared, action(prepared, domain="reversal", choice="reverse")
    ).plan
    assert reversal.ready
    for plan in (attachment, reversal):
        groups = review_owned_target_groups(plan, queries(plan))
        assert tuple(t.canonical_path for t in groups[0]) == (
            "Assets/data.bin",
            "Assets/data (incoming-ba7816bf).bin",
        )
