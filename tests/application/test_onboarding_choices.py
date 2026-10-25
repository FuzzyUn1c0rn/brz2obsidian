"""Unknown-source preservation choices do not grant generated-target authority."""

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_contracts import UpdatePreparation
from brz2obsidian.contracts import ContentVersion
from brz2obsidian.core import prepare_review
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links


@pytest.mark.parametrize("choice", ("current", "incoming"))
@pytest.mark.parametrize("binary", (False, True))
def test_unknown_source_onboarding_preserves_current_without_authorizing_target(
    choice, binary
):
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        attachment_request,
        binary_context,
    )

    facts = (
        attachment_request()
        if binary
        else request(current=b"Exact authored bytes.\r\n")
    )
    facts = facts.model_copy(
        update={
            "subjects": (
                facts.subjects[0].model_copy(
                    update={
                        "baseline": ContentVersion(
                            status="unknown", content=None, unavailable_digest=None
                        ),
                    }
                ),
            ),
            "format_operation": facts.format_operation.model_copy(
                update={
                    "kind": "onboarding",
                    "recorded_generation": "unknown",
                    "baseline_source_version": None,
                    "established_baseline": None,
                }
            ),
        }
    )
    facts = (
        facts.model_copy(update={"link_context": binary_context(facts)})
        if binary
        else with_review_links(facts)
    )
    plan = prepare_review(facts, preflight=preflight())
    from brz2obsidian.core import inspect_review_choices

    displayed = next(
        row for row in inspect_review_choices(plan) if row.domain == "format"
    )
    assert (
        "current" in displayed.enabled_choices
        and "incoming" not in displayed.enabled_choices
    )
    unavailable = next(
        row for row in displayed.availability if row.choice == "incoming"
    )
    assert not unavailable.enabled and "unsafe_producer_choice" in unavailable.reasons
    original = preparation()
    prepared = UpdatePreparation(
        **(
            original.model_dump()
            | {
                "kind": "onboarding",
                "locator": None,
                "review": plan,
                "source_binding": original.source_binding.model_copy(
                    update={
                        "incoming_identity": plan.facts.incoming_identity,
                    }
                ),
            }
        )
    )
    assert not plan.proposal.changes[0].format_review.target_eligible
    options = {}
    if binary:
        selection, candidate = attachment_candidate(facts, choice)
        options = {"attachment_selection": selection, "attachment_candidate": candidate}
    if choice == "current":
        from brz2obsidian.application.review_choices import requirement_digest

        requirement = next(row for row in plan.requirements if row.domain == "format")
        result = Operations().resolve_update_choice(
            prepared,
            requirement_id=requirement.requirement_id,
            choice=choice,
            assumptions_digest=requirement_digest(requirement),
        )
    else:
        result = Operations().resolve_update(
            prepared, action(plan, domain="format", choice=choice, **options)
        )
    assert result.kind == "onboarding"
    if choice == "current":
        assert result.code == "accepted" and result.ready, result
        assert result.next_actions == ("save_update",)
        assert result.preparation.review.approvals[0].result.data == (
            b"\x00authored" if binary else b"Exact authored bytes.\r\n"
        )
        assert result.preparation.review.approvals[0].source_memory is None
        assert not result.preparation.review.approvals[0].source_accepted
    else:
        assert result.status == "refused" and not result.ready
        assert not result.preparation.review.approvals
