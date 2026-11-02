"""Pure canonical owned outputs compose without acquiring current authority."""

import pytest

from brz2obsidian.core import prepare_review, resolve_review
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


def test_empty_and_reordered_queries_keep_required_documents_and_effects():
    from brz2obsidian.core import review_owned_outputs

    plan = document_origin()
    home = query_for(plan, "Notes/Opening.md")
    manual = query_for(plan, "Manual.md")
    reordered = review_owned_outputs(plan, (manual, home, manual))
    assert tuple(group[0].canonical_path for group in reordered.target_groups) == (
        "Manual.md",
        "Notes/Opening.md",
        "Manual.md",
    )
    empty = review_owned_outputs(plan, ())
    assert empty.target_groups == ()
    assert tuple(t.canonical_path for _, _, t in empty.documents) == ("Manual.md",)
    assert empty.effects.status == "selected"
    assert {f.path: f.content.data for f in empty.effects.files} == {
        "Notes/Opening.md": HOME_LATER,
        "Manual.md": MANUAL_BEFORE,
    }


@pytest.mark.parametrize("invalid", ("foreign_query", "forged_origin", "unready"))
def test_composition_requires_ready_canonical_origin_and_exact_query(invalid):
    from brz2obsidian.core import review_owned_outputs

    plan = document_origin()
    requests = ()
    if invalid == "foreign_query":
        change, _ = query_for(plan, "Notes/Opening.md")
        requests = ((change, "foreign:decision"),)
    elif invalid == "forged_origin":
        plan = plan.model_copy(update={"approvals": ()})
    else:
        plan = prepare_review(operation_document_facts(), preflight=preflight())
    with pytest.raises(ValueError, match="Origin decision|canonical ready origin"):
        review_owned_outputs(plan, requests)


def test_retaining_current_document_does_not_claim_changed_document_ownership():
    from brz2obsidian.core import review_owned_outputs

    plan = prepare_review(operation_document_facts(), preflight=preflight())
    plan = choose(plan, "Notes/Opening.md", "current")
    plan = choose(plan, "Manual.md", "current")
    assert plan.ready
    outputs = review_owned_outputs(plan, ())
    assert outputs.documents == ()
    assert outputs.effects.status == "selected"
    manual = next(f for f in outputs.effects.files if f.path == "Manual.md")
    assert manual.content.data == (
        b"[[Notes/Opening.md|Recorded home]]\n"
        b"[[Notes/Opening.md#Shared|Heading]]\n"
        b"[[Notes/Opening.md#^kept|Block]]\n"
        b"[Relative](Notes/Opening.md)\n"
    )
    assert outputs.effects.remove_paths == ()


def test_direct_attachment_and_reversal_targets_keep_protected_primary_bytes():
    from brz2obsidian.core import review_owned_outputs
    from tests.reconciliation.test_resolution import action
    from tests.reconciliation.test_reversal_outputs import both_reversal_facts

    facts, attachment = both_reversal_facts(with_origin=True)
    initial = prepare_review(facts, preflight=preflight())
    reversal = resolve_review(
        initial, action(initial, domain="reversal", choice="reverse")
    ).plan
    assert reversal.ready
    for plan, removals in (
        (attachment, ()),
        (reversal, ("Assets/data (incoming-ba7816bf).bin",)),
    ):
        approval = plan.approvals[0]
        outputs = review_owned_outputs(
            plan, ((approval.change_id, approval.decision_id),)
        )
        assert tuple(t.canonical_path for t in outputs.target_groups[0]) == (
            "Assets/data.bin",
            "Assets/data (incoming-ba7816bf).bin",
        )
        assert outputs.documents == ()
        assert outputs.effects.status == "selected"
        primary = next(f for f in outputs.effects.files if f.path == "Assets/data.bin")
        assert primary.content.data == b"\x00authored"
        assert outputs.effects.remove_paths == removals


def test_returned_owned_values_are_detached_from_origin_and_later_calls():
    from brz2obsidian.core import review_owned_outputs

    plan = document_origin()
    before = plan.model_dump_json()
    requests = (query_for(plan, "Notes/Opening.md"),)
    first = review_owned_outputs(plan, requests)
    first.target_groups[0][0].__dict__["canonical_path"] = "Foreign.md"
    first.documents[0][2].__dict__["canonical_path"] = "Other.md"
    manual = next(f for f in first.effects.files if f.path == "Manual.md")
    manual.content.__dict__["data"] = b"forged returned bytes"
    assert plan.model_dump_json() == before
    again = review_owned_outputs(plan, requests)
    assert again.target_groups[0][0].canonical_path == "Notes/Opening.md"
    assert again.documents[0][2].canonical_path == "Manual.md"
    assert {f.path: f.content.data for f in again.effects.files} == {
        "Notes/Opening.md": HOME_LATER,
        "Manual.md": MANUAL_BEFORE,
    }
