"""Public optional path choices retain their own domain and safe availability."""

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_offers import choice_offers
from brz2obsidian.core import prepare_review, resolve_review
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_attachments import attachment_request, binary_context
from tests.reconciliation.test_identity import inventory_item, with_subjects
from tests.reconciliation.test_optional_rename_offers import moved_facts
from tests.reconciliation.test_resolution import action, preflight


def moved_attachment_facts():
    facts = attachment_request()
    current = facts.subjects[0].current.model_copy(update={"path": "Authored/data.bin"})
    slot = (
        facts.subjects[0]
        .attachment.allocation_candidates[0]
        .model_copy(
            update={
                "path": "Authored/data (incoming-ba7816bf).bin",
                "target": facts.subjects[0]
                .attachment.allocation_candidates[0]
                .target.model_copy(
                    update={"normalized_path": "authored/data (incoming-ba7816bf).bin"}
                ),
            }
        )
    )
    subject = facts.subjects[0].model_copy(
        update={
            "current": current,
            "attachment": facts.subjects[0].attachment.model_copy(
                update={"allocation_candidates": (slot,)}
            ),
        }
    )
    entry = facts.identity_inventory[0].model_copy(
        update={
            "current": current,
            "target": facts.identity_inventory[0].target.model_copy(
                update={"normalized_path": "authored/data.bin"}
            ),
        }
    )
    facts = with_subjects(facts, (subject,), (entry,))
    return facts.model_copy(update={"link_context": binary_context(facts)})


def test_public_binary_optional_rename_is_not_an_attachment_selection():
    prepared = preparation(moved_attachment_facts())
    offers = choice_offers(prepared)
    binary = next(row for row in offers if row.domain == "attachment")
    rename = next(row for row in offers if row.domain == "rename")
    assert binary.requirement_id != rename.requirement_id
    assert binary.choices == ("current", "incoming", "both")
    assert rename.choices == ("keep_path", "source_path")
    kept = Operations().resolve_update_choice(
        prepared,
        requirement_id=rename.requirement_id,
        choice="keep_path",
        assumptions_digest=rename.assumptions_digest,
    )
    assert kept.code == "accepted", kept.code
    assert not kept.ready and kept.unresolved == 1
    assert kept.preparation.review.approvals == ()
    assert kept.preparation.review.actions[-1].attachment_candidate is None
    assert (
        kept.preparation.review.proposal.changes[0].target_path == "Authored/data.bin"
    )
    offers = choice_offers(kept.preparation)
    assert next(row for row in offers if row.domain == "rename").selected == "keep_path"
    assert next(row for row in offers if row.domain == "attachment").selected is None
    assert (
        next(row for row in offers if row.domain == "rename").unavailable_choices == ()
    )
    assert not next(row for row in offers if row.domain == "rename").reference_review
    assert next(row for row in offers if row.domain == "attachment").reference_review


def test_colliding_optional_source_path_stays_disabled_after_keep_replacement():
    facts = moved_facts()
    collision = inventory_item(
        "other", "entry:other", "Notes/Opening.md", b"Unrelated existing bytes.\n"
    )
    # Interpret the complete actual collision inventory through the public fixture.
    facts = facts.model_copy(
        update={
            "identity_inventory": facts.identity_inventory + (collision,),
            "link_context": None,
        }
    )
    from tests.reconciliation.test_resolution import with_review_links

    facts = with_review_links(facts)
    plan = prepare_review(facts, preflight=preflight())
    (change,) = plan.proposal.changes
    assert change.rename_review.status == "blocked"
    assert not change.rename_review.requires_decision
    refused = resolve_review(plan, action(plan, domain="rename", choice="source_path"))
    assert refused.code == "unsafe_producer_choice" and refused.plan == plan
    prepared = preparation(facts)
    for step in ("initial", "declined"):
        offer = next(row for row in choice_offers(prepared) if row.domain == "rename")
        assert offer.choices == ("keep_path",), step
        assert [(row.choice, row.reasons) for row in offer.unavailable_choices] == [
            ("source_path", ("unsafe_producer_choice",))
        ]
        before = prepared.review.model_dump_json()
        with pytest.raises(ValueError, match="Review offer changed"):
            Operations().resolve_update_choice(
                prepared,
                requirement_id=offer.requirement_id,
                choice="source_path",
                assumptions_digest=offer.assumptions_digest,
            )
        assert prepared.review.model_dump_json() == before
        if step == "initial":
            kept = Operations().resolve_update_choice(
                prepared,
                requirement_id=offer.requirement_id,
                choice="keep_path",
                assumptions_digest=offer.assumptions_digest,
            )
            assert kept.code == "accepted", kept.code
            prepared = kept.preparation
            assert (
                prepared.review.proposal.changes[0].rename_review.status == "declined"
            )
    assert prepared.review.proposal.changes[0].target_path == "Authored/Opening.md"
    assert len(prepared.review.requirements) == 1 and not prepared.review.ready
