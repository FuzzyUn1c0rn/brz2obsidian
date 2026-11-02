"""Explicit canonical ownership queries share one public batch admission."""

from brz2obsidian.core import prepare_review, resolve_review
from tests.reconciliation.test_identity import inventory_item, with_subjects
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links


def origin():
    facts = request(original=b"base\n", current=b"base\n", incoming=b"opening\n")
    entry = inventory_item("ending-entry", "entry:ending", "Notes/Ending.md", b"base\n")
    second = facts.subjects[0].model_copy(
        update={
            "item_id": "entry:ending",
            "path": "Notes/Ending.md",
            "current": entry.current,
            "source_target": entry.target,
        }
    )
    facts = with_subjects(
        facts, facts.subjects + (second,), facts.identity_inventory + (entry,)
    )
    plan = prepare_review(with_review_links(facts), preflight=preflight())
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
    assert tuple(tuple((t.target_id, t.canonical_path) for t in group) for group in groups) == (
        (("review:opening-entry", "Notes/Opening.md"),),
        (("review:ending-entry", "Notes/Ending.md"),),
    )