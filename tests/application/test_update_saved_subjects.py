"""Canonical approved attachment writes remain owned while other choices wait."""

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_choices import requirement_digest
from brz2obsidian.application.update_subjects import (
    approved_attachment_subjects,
    review_subjects,
)
from brz2obsidian.core import inspect_review_choices, select_review_effects
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_attachments import attachment_request, binary_context
from tests.reconciliation.test_identity import inventory_item, with_subjects
from tests.reconciliation.test_proposals import request


def test_unready_both_keeps_approved_secondary_in_local_capture_scope():
    facts = attachment_request()
    note = request(original=b"Old note", current=b"My note", incoming=b"New note")
    facts = with_subjects(
        facts,
        (*facts.subjects, note.subjects[0]),
        (
            *facts.identity_inventory,
            inventory_item(
                "unresolved-note", "entry:opening", "Notes/Opening.md", b"My note"
            ),
        ),
    )
    facts = facts.model_copy(update={"link_context": binary_context(facts)})
    prepared = preparation(facts)
    offer = next(
        row
        for row in inspect_review_choices(prepared.review)
        if row.domain == "attachment"
    )
    chosen = Operations().resolve_update_choice(
        prepared,
        requirement_id=offer.requirement_id,
        choice="both",
        assumptions_digest=requirement_digest(offer),
    )
    assert chosen.code == "accepted" and not chosen.ready
    plan = chosen.preparation.review
    note_change = next(row for row in plan.proposal.changes if row.facet == "content")
    assert any(row.change_id == note_change.change_id for row in plan.requirements)
    assert select_review_effects(plan).code == "review_not_ready"
    (approval,) = plan.approvals
    change = next(
        row for row in plan.proposal.changes if row.change_id == approval.change_id
    )
    secondary = "Assets/data (incoming-ba7816bf).bin"
    assert [
        (row.path, row.content.data) for row in approval.attachment_candidate.outputs
    ] == [("Assets/data.bin", b"\x00authored"), (secondary, b"abc")]
    assert secondary not in {row.path for row in plan.facts.subjects}
    assert secondary not in {row.current.path for row in plan.facts.identity_inventory}
    assert (secondary, change.subject_id) in {
        (row.path, row.subject_id) for row in review_subjects(plan.producer_facts, plan)
    }
    # Native LOCAL capture consumes this canonical per-owner extension even
    # when another choice prevents whole-plan selected-effects projection.
    assert {
        (row.path, row.subject_id) for row in approved_attachment_subjects(plan)
    } == {
        ("Assets/data.bin", change.subject_id),
        (secondary, change.subject_id),
    }
