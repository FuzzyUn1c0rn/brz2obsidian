"""Application offers retain the shared non-row approval and consent semantics."""

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_choices import requirement_digest
from brz2obsidian.contracts import ReviewConsentRequirement
from brz2obsidian.core import inspect_review_choices, prepare_review
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import (
    mixed_review_facts,
    preflight,
    with_review_links,
)


@pytest.mark.parametrize("domain", ("compatible_group", "tracking", "storage"))
def test_nonrow_choices_preserve_shared_bulk_and_explicit_consent_semantics(domain):
    facts = with_review_links(
        mixed_review_facts() if domain == "compatible_group" else request()
    )
    prepared = preparation(facts)
    gate = preflight()
    if domain != "compatible_group":
        requirement = ReviewConsentRequirement(
            schema_id="brz2obsidian.review-consent-requirement",
            schema_version=1,
            consent_id="actual-policy",
            kind=domain,
            requirement="required",
            policy="ordinary" if domain == "tracking" else "builtin_transform",
            fingerprint="actual-policy-fingerprint",
            disclosure="Literal owned history is retained",
            subjects=tuple(row.subject_id for row in prepared.review.proposal.changes),
        )
        gate = gate.model_copy(update={"consents": (requirement,)})
    prepared = prepared.model_copy(
        update={"review": prepare_review(facts, preflight=gate)}
    )
    offered = next(
        row for row in inspect_review_choices(prepared.review) if row.domain == domain
    )
    result = Operations().resolve_update_choice(
        prepared,
        requirement_id=offered.requirement_id,
        choice="approve" if domain == "compatible_group" else "accept",
        assumptions_digest=requirement_digest(offered),
    )
    assert result.code == "accepted"
    if domain == "compatible_group":
        assert [row.result.data for row in result.preparation.review.approvals] == [
            b"new one",
            b"new two",
        ]
        assert {row.domain for row in result.preparation.review.requirements} == {
            "text",
            "configuration",
        }
    else:
        (decision,) = result.preparation.review.consents
        assert decision.kind == domain and decision.choice == "accept"
        assert not result.preparation.review.approvals and not result.ready
        assert decision.assumptions == offered.assumptions
    with pytest.raises(ValueError):
        Operations().resolve_update_choice(
            prepared,
            requirement_id=offered.requirement_id,
            choice="approve" if domain == "compatible_group" else "accept",
            assumptions_digest="0" * 64,
        )


def test_identity_choice_binds_actual_selected_and_disassociated_entries():
    from tests.reconciliation.test_identity import inventory_item

    facts = request().model_copy(
        update={
            "identity_inventory": (
                inventory_item("copy-a", "entry:opening", "A.md", b"Exact copy A.\r\n"),
                inventory_item("copy-b", "entry:opening", "B.md", b"Exact copy B.\r\n"),
            )
        }
    )
    prepared = preparation(with_review_links(facts))
    offer = next(
        row
        for row in inspect_review_choices(prepared.review)
        if row.domain == "identity"
    )
    options = {
        "requirement_id": offer.requirement_id,
        "choice": "associate",
        "assumptions_digest": requirement_digest(offer),
    }
    with pytest.raises(ValueError):
        Operations().resolve_update_choice(
            prepared,
            **options,
            selected_entry_id="foreign",
            disassociate_entry_ids=("copy-a",),
        )
    result = Operations().resolve_update_choice(
        prepared,
        **options,
        selected_entry_id="copy-b",
        disassociate_entry_ids=("copy-a",),
    )
    assert result.code == "accepted" and not result.ready
    review = result.preparation.review.proposal.changes[0].identity_review
    assert review.selected_entry_id == "copy-b" and review.disassociate_entry_ids == (
        "copy-a",
    )
    assert review.repair_required and review.provenance == "explicit_user"
    assert (
        result.preparation.review.producer_facts.identity_inventory
        == prepared.review.producer_facts.identity_inventory
    )
    assert {row.current.content.data for row in review.candidates} == {
        b"Exact copy A.\r\n",
        b"Exact copy B.\r\n",
    }
