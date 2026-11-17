"""Canonical format attachment offers agree with existing safe resolution."""

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_choices import requirement_digest
from brz2obsidian.application.review_offers import choice_offers
from brz2obsidian.contracts import ExactContent
from brz2obsidian.core import (
    inspect_review_choices,
    load_review,
    prepare_review,
    save_review,
    select_review_effects,
)
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_attachments import attachment_request, binary_context
from tests.reconciliation.test_identity import inventory_item, with_subjects
from tests.reconciliation.test_resolution import preflight


def format_attachment_preparation(
    kind="format_transition", *, absent=False, inventory="complete", existence="absent"
):
    facts = attachment_request()
    first = facts.subjects[0]
    retained = ExactContent(data=b"\x00independent retained asset\r\n")
    second = first.model_copy(
        update={
            "facet": "attachment:keep",
            "path": "Assets/keep.bin",
            "baseline": first.baseline.model_copy(update={"content": retained}),
            "current": first.current.model_copy(
                update={"path": "Assets/keep.bin", "content": retained}
            ),
            "incoming": retained,
            "source_target": first.source_target.model_copy(
                update={"normalized_path": "assets/keep.bin"}
            ),
            "attachment": first.attachment.model_copy(
                update={
                    "current_target_id": "resource:keep",
                    "allocation_candidates": (),
                }
            ),
        }
    )
    facts = with_subjects(
        facts,
        (first, second),
        facts.identity_inventory
        + (
            inventory_item(
                "keep",
                first.item_id,
                "Assets/keep.bin",
                retained.data,
                facet="attachment:keep",
            ),
        ),
    )
    facts = facts.model_copy(
        update={
            "incoming_identity": facts.incoming_identity.model_copy(
                update={"output_format": 8}
            ),
            "format_operation": facts.format_operation.model_copy(
                update={"kind": kind, "target_source_version": "source:a"}
            ),
        }
    )
    facts = facts.model_copy(update={"link_context": binary_context(facts)})
    if absent:
        first = facts.subjects[0].model_copy(
            update={
                "current": first.current.model_copy(
                    update={"existence": existence, "content": None}
                )
            }
        )
        context = facts.link_context.model_copy(
            update={
                "current_target_facts": tuple(
                    row.model_copy(
                        update={
                            "existence": "missing"
                            if existence == "absent"
                            else "unknown",
                            "content": None,
                            "fragments": (),
                            "anchors": (),
                            "structure": None,
                            "interpretation": "unknown",
                        }
                    )
                    if row.target_id == "resource:payload"
                    else row
                    for row in facts.link_context.current_target_facts
                )
            }
        )
        facts = facts.model_copy(
            update={
                "subjects": (first, *facts.subjects[1:]),
                "identity_inventory": (
                    facts.identity_inventory[0].model_copy(
                        update={"current": first.current}
                    ),
                    *facts.identity_inventory[1:],
                ),
                "link_context": context,
            }
        )
    if kind == "source_update":
        facts = facts.model_copy(
            update={
                "incoming_identity": facts.baseline_identity,
                "format_operation": facts.format_operation.model_copy(
                    update={
                        "recorded_generation": "unknown",
                        "baseline_source_version": None,
                        "established_baseline": None,
                    }
                ),
            }
        )
    facts = facts.model_copy(update={"inventory": inventory})
    plan = prepare_review(facts, preflight=preflight())
    base = preparation()
    return base.model_copy(
        update={
            "kind": kind,
            "review": plan,
            "source_binding": base.source_binding.model_copy(
                update={
                    "incoming_identity": facts.incoming_identity,
                    "target_source_version": "source:a",
                }
            ),
        }
    )


def choose(prepared, offer, choice):
    return Operations().resolve_update_choice(
        prepared,
        requirement_id=offer.requirement_id,
        choice=choice,
        assumptions_digest=requirement_digest(offer),
    )


def offer_for(prepared, path):
    paths = {row.change_id: row.path for row in prepared.review.proposal.changes}
    return next(
        row
        for row in inspect_review_choices(prepared.review)
        if paths.get(row.change_id) == path
    )


@pytest.mark.parametrize("kind", ("format_transition", "onboarding"))
def test_format_attachment_choices_preserve_prior_decisions_and_allow_only_current(
    kind,
):
    prepared = format_attachment_preparation(kind)
    keep = offer_for(prepared, "Assets/keep.bin")
    prior = choose(prepared, keep, "current")
    assert prior.code == "accepted", prior
    prepared = prior.preparation
    plan = prepared.review
    change = next(row for row in plan.proposal.changes if row.path == "Assets/data.bin")
    assert change.format_review.target_eligible and change.attachment_review is not None
    assert [
        (row.choice, row.eligible) for row in change.attachment_review.alternatives
    ] == [("current", True), ("incoming", True), ("both", True)]
    offer = offer_for(prepared, "Assets/data.bin")
    assert offer.domain == "format" and offer.enabled_choices == ("current",)
    public = next(
        row for row in choice_offers(prepared) if row.change_id == change.change_id
    )
    assert public.choices == ("current",)
    assert {row.choice for row in public.unavailable_choices} == {"incoming", "both"}
    assert all(
        "keep_vault_version_is_required_for_attachment_format_review" in row.reasons
        for row in public.unavailable_choices
    )
    before = plan.model_dump_json()
    for unsupported in ("incoming", "both"):
        with pytest.raises(ValueError, match="Review offer changed"):
            choose(prepared, offer, unsupported)
        assert prepared.review.model_dump_json() == before
    selected = choose(prepared, offer, "current")
    assert selected.code == "accepted", selected
    assert selected.preparation.review.approvals[:-1] == plan.approvals
    assert selected.preparation.review.actions[:-1] == plan.actions
    assert selected.preparation.review.approvals[-1].result.data == b"\x00authored"
    saved = save_review(selected.preparation.review)
    assert saved.status == "saved"
    loaded = load_review(saved.record.model_dump_json())
    assert loaded.status == "loaded" and loaded.loaded.ready is False
    assert loaded.loaded.saved.plan.actions == selected.preparation.review.actions
    assert loaded.loaded.saved.plan.approvals == selected.preparation.review.approvals
    replayed = next(
        row
        for row in inspect_review_choices(loaded.loaded.saved.plan)
        if row.change_id == change.change_id
    )
    assert replayed.enabled_choices == ("current",)


def test_source_update_format_attachment_has_no_admissible_binary_choice():
    prepared = format_attachment_preparation("source_update")
    change = next(
        row for row in prepared.review.proposal.changes if row.path == "Assets/data.bin"
    )
    assert change.format_review is not None and change.attachment_review is not None
    offer = offer_for(prepared, "Assets/data.bin")
    assert offer.enabled_choices == ()
    assert all(
        "review_onboarding_or_output_format_transition_before_choosing_this_attachment"
        in row.reasons
        for row in offer.availability
    )
    before = prepared.review.model_dump_json()
    for choice in ("current", "incoming", "both"):
        with pytest.raises(ValueError, match="Review offer changed"):
            choose(prepared, offer, choice)
        assert prepared.review.model_dump_json() == before


def test_format_attachment_current_absence_preserves_explicit_absence():
    prepared = format_attachment_preparation(absent=True)
    keep = offer_for(prepared, "Assets/keep.bin")
    prior = choose(prepared, keep, "current")
    assert prior.code == "accepted"
    prepared = prior.preparation
    change = next(
        row for row in prepared.review.proposal.changes if row.path == "Assets/data.bin"
    )
    assert change.current is None and change.format_review is not None
    offer = offer_for(prepared, "Assets/data.bin")
    assert offer.enabled_choices == ("current",)
    selected = choose(prepared, offer, "current")
    assert selected.code == "accepted", selected
    approval = next(
        row
        for row in selected.preparation.review.approvals
        if row.change_id == change.change_id
    )
    assert approval.result is None
    assert selected.preparation.review.actions[:-1] == prepared.review.actions
    assert selected.preparation.review.approvals[:-1] == prepared.review.approvals
    assert selected.ready
    assert {
        row.path: row.content.data
        for row in select_review_effects(selected.preparation.review).files
    } == {"Assets/keep.bin": b"\x00independent retained asset\r\n"}


@pytest.mark.parametrize("condition", ("source_update", "partial", "unreadable"))
def test_uncertain_or_source_update_absence_does_not_gain_current_authority(condition):
    prepared = format_attachment_preparation(
        "source_update" if condition == "source_update" else "format_transition",
        absent=True,
        inventory="partial" if condition == "partial" else "complete",
        existence="unknown" if condition == "unreadable" else "absent",
    )
    offer = offer_for(prepared, "Assets/data.bin")
    assert "current" not in offer.enabled_choices
    before = prepared.review.model_dump_json()
    with pytest.raises(ValueError, match="Review offer changed"):
        choose(prepared, offer, "current")
    assert prepared.review.model_dump_json() == before
