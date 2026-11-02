"""Pure canonical owned outputs compose without acquiring current authority."""

from brz2obsidian.core import prepare_review
from tests.reconciliation.test_resolution import preflight
from tests.reconciliation.test_reversal_note_versions import (
    HOME_LATER,
    MANUAL_BEFORE,
    choose,
    operation_document_facts,
)


def document_origin():
    plan = prepare_review(operation_document_facts(), preflight=preflight())
    plan = choose(plan, "Notes/Opening.md", "current")
    plan = choose(plan, "Manual.md", "reverse")
    assert plan.ready and not plan.requirements and not plan.blockers
    return plan


def query_for(plan, path):
    change = next(c for c in plan.proposal.changes if c.path == path)
    approval = next(a for a in plan.approvals if a.change_id == change.change_id)
    return approval.change_id, approval.decision_id


def test_composed_owned_outputs_preserve_later_note_and_exact_document_reversal():
    plan = document_origin()
    home = query_for(plan, "Notes/Opening.md")
    manual = query_for(plan, "Manual.md")

    from brz2obsidian.core import review_owned_outputs

    outputs = review_owned_outputs(plan, (home,))
    assert tuple(
        tuple((t.target_id, t.canonical_path) for t in group)
        for group in outputs.target_groups
    ) == ((("review:opening-entry", "Notes/Opening.md"),),)
    assert tuple(
        (change, decision, target.target_id, target.canonical_path)
        for change, decision, target in outputs.documents
    ) == ((manual[0], manual[1], "file:Manual.md", "Manual.md"),)
    assert outputs.effects.status == "selected"
    assert {f.path: f.content.data for f in outputs.effects.files} == {
        "Notes/Opening.md": HOME_LATER,
        "Manual.md": MANUAL_BEFORE,
    }
    assert outputs.effects.remove_paths == ()
