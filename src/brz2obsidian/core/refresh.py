"""Dependency-scoped immutable refresh; no observation, parsing or new consent."""

from brz2obsidian.contracts import (
    ReconciliationInput,
    ReviewAction,
    ReviewAttachmentApplicability,
    ReviewPreflight,
    ReviewProducerApplicability,
    ReviewRefreshEvent,
    ReviewRetention,
)

from .resolution import _plan, _transition, validate_review
from .review_attachments import retained_attachment_view
from .review_dependencies import review_dependencies
from .review_links import selected_current_links_safe
from .review_preflight import consent_requirements
from .text_candidates import validate_text_candidate


def _closure(changed, nodes):
    result = set(changed)
    while True:
        added = {
            key for key, node in nodes.items() if set(node.depends_on) & result
        } - result
        if not added:
            return result
        result.update(added)


def _approval_safe(facts, change, approval, origin, attachment_applicability=()):
    if approval.attachment_candidate is not None:
        return any(
            a.decision_id == approval.decision_id for a in attachment_applicability
        )
    if approval.choice == "decline_restoration":
        subject = next(
            s
            for s in facts.subjects
            if (s.item_id, s.facet) == (change.item_id, change.facet)
        )
        # Fresh producer/graph validation establishes safety; retain the original
        # reviewed absence policy without emitting another memory or decision.
        return (
            approval.domain == "restoration"
            and change.disposition == "restoration"
            and facts.inventory == "complete"
            and subject.current.existence == "absent"
            and change.current is None
            and change.result is None
            and approval.result is None
            and change.target_path == approval.target_path
            and approval.source_memory is not None
            and approval.source_memory.source_version == change.source_version
            and approval.source_memory.review_domain
            == (
                "configuration" if subject.output_role == "configuration" else "content"
            )
        )
    if origin.candidate is not None:
        return validate_text_candidate(
            facts,
            change,
            origin.candidate,
            approval.choice,
            mapping_choice=approval.domain == "mapping",
        )
    if approval.choice == "current":
        return selected_current_links_safe(facts, change)
    return (
        approval.choice == "approve"
        and change.result == approval.result
        and change.target_path == approval.target_path
    )


def _attachment_views(plan, facts, approvals):
    result = []
    for approval in approvals:
        if approval.attachment_candidate is None:
            continue
        original_facts = plan.history.initial_facts
        for event in plan.history.events:
            if isinstance(event, ReviewRefreshEvent):
                original_facts = event.facts
            elif (
                isinstance(event, ReviewAction)
                and event.decision_id == approval.decision_id
            ):
                break
        view = retained_attachment_view(
            facts,
            approval.attachment_selection,
            approval.attachment_candidate,
            original_facts,
        )
        if view is not None:
            result.append(
                ReviewAttachmentApplicability(
                    schema_id="brz2obsidian.review-attachment-applicability",
                    schema_version=1,
                    decision_id=approval.decision_id,
                    generation=facts.generation,
                    candidate=view,
                )
            )
    return tuple(result)


def _producer_choices(plan, facts, fresh):
    retained, associations, renames = [], [], []
    changes = {(c.item_id, c.facet): c for c in fresh.proposal.changes}
    originals = (
        plan.producer_facts.association_decisions + plan.producer_facts.rename_decisions
    )
    for supplied in (
        facts.association_decisions
        + facts.rename_decisions
        + facts.preservation_decisions
    ):
        if supplied not in originals + plan.producer_facts.preservation_decisions:
            raise ValueError("Refresh cannot accept a new explicit producer decision")
    prior_changes = {(c.item_id, c.facet): c for c in plan.proposal.changes}
    for decision in originals:
        prior = prior_changes.get((decision.item_id, decision.facet))
        if prior is None:
            continue
        admitted = (
            prior.identity_review
            if hasattr(decision, "selected_entry_id")
            else prior.rename_review
        )
        statuses = (
            ("matched", "association_proposed")
            if hasattr(decision, "selected_entry_id")
            else ("accepted", "declined")
        )
        if (
            admitted is None
            or admitted.status not in statuses
            or admitted.decision_id != decision.decision_id
            or admitted.provenance != "explicit_user"
        ):
            continue
        change = changes.get((decision.item_id, decision.facet))
        if change is None:
            continue
        if hasattr(decision, "selected_entry_id"):
            review = change.identity_review
            requested = {decision.selected_entry_id, *decision.disassociate_entry_ids}
            assumptions = review.assumptions + tuple(
                a
                for c in review.candidates
                if c.entry_id in requested
                for a in c.assumptions
            )
        else:
            if change.rename_review is None:
                continue
            assumptions = change.rename_review.assumptions
        if sorted(assumptions, key=lambda a: a.key) != sorted(
            decision.reviewed_assumptions, key=lambda a: a.key
        ):
            continue
        retained.append(
            ReviewProducerApplicability(
                schema_id="brz2obsidian.review-producer-applicability",
                schema_version=1,
                original=decision,
                proposal_id=facts.proposal_id,
                generation=facts.generation,
                reviewed_assumptions=assumptions,
            )
        )
        (associations if hasattr(decision, "selected_entry_id") else renames).append(
            decision
        )
    return facts.model_copy(
        update={
            "association_decisions": tuple(associations),
            "rename_decisions": tuple(renames),
            "preservation_decisions": (),
        }
    ), tuple(retained)


def _refresh(plan, facts, preflight):
    if facts.proposal_id != plan.proposal.proposal_id:
        return _transition(plan, "refused", "wrong_proposal")
    if facts.generation != plan.proposal.generation + 1:
        return _transition(plan, "stale", "generation_changed")
    attachment_applicability = ()
    fresh = _plan(facts, preflight, actions=plan.actions)
    try:
        producer_facts, applicability = _producer_choices(plan, facts, fresh)
    except ValueError:
        return _transition(plan, "refused", "choice_not_admitted")
    fresh = _plan(
        facts,
        preflight,
        actions=plan.actions,
        producer_facts=producer_facts,
        producer_applicability=applicability,
        attachment_applicability=attachment_applicability,
    )
    new_by_id = {c.change_id: c for c in fresh.proposal.changes}
    retained = tuple(a for a in plan.approvals if a.change_id in new_by_id)
    old_changes = {c.change_id: c for c in plan.proposal.changes}
    try:
        old = review_dependencies(plan)
        while True:
            attachment_applicability = _attachment_views(plan, producer_facts, retained)
            tentative = _plan(
                facts,
                preflight,
                actions=plan.actions,
                approvals=retained,
                consents=plan.consents,
                producer_facts=producer_facts,
                producer_applicability=applicability,
                attachment_applicability=attachment_applicability,
            )
            new = review_dependencies(tentative)
            changed = {
                key for key in old.keys() | new.keys() if old.get(key) != new.get(key)
            }
            invalidated = _closure(changed, old)
            while True:
                enlarged = _closure(_closure(invalidated, old), new)
                if enlarged == invalidated:
                    break
                invalidated = enlarged
            next_applicability = tuple(
                b
                for b in applicability
                if not (
                    {a.key for a in b.reviewed_assumptions}
                    | {"producer-choice:" + b.original.decision_id}
                )
                & invalidated
            )
            current = {c.subject_id: c for c in tentative.proposal.changes}
            surviving = []
            for approval in retained:
                before = old_changes[approval.change_id]
                after = current.get(before.subject_id)
                keys = {a.key for a in approval.assumptions} | {
                    "effect:" + before.subject_id
                }
                origin = next(
                    a for a in plan.actions if a.decision_id == approval.decision_id
                )
                if (
                    after is not None
                    and not keys & invalidated
                    and after.change_id == approval.change_id
                    and _approval_safe(
                        producer_facts,
                        after,
                        approval,
                        origin,
                        attachment_applicability,
                    )
                ):
                    surviving.append(approval)
            if tuple(surviving) == retained and next_applicability == applicability:
                break
            retained = tuple(surviving)
            applicability = next_applicability
            originals = tuple(b.original for b in applicability)
            producer_facts = producer_facts.model_copy(
                update={
                    "association_decisions": tuple(
                        d
                        for d in producer_facts.association_decisions
                        if d in originals
                    ),
                    "rename_decisions": tuple(
                        d for d in producer_facts.rename_decisions if d in originals
                    ),
                }
            )
    except ValueError:
        return _transition(plan, "refused", "dependency_graph_invalid")
    bindings = []
    for approval in retained:
        before = old_changes[approval.change_id]
        origin = next(a for a in plan.actions if a.decision_id == approval.decision_id)
        keys = {a.key for a in approval.assumptions} | {"effect:" + before.subject_id}
        bindings.append(
            ReviewRetention(
                schema_id="brz2obsidian.review-retention",
                schema_version=1,
                decision_id=approval.decision_id,
                subject_id=before.subject_id,
                domain=approval.domain,
                origin_generation=origin.expected_generation,
                origin_change_id=approval.change_id,
                current_change_id=approval.change_id,
                dependency_keys=tuple(sorted(keys)),
            )
        )
    selected = _plan(
        facts,
        preflight,
        actions=plan.actions,
        approvals=retained,
        producer_facts=producer_facts,
        producer_applicability=applicability,
        attachment_applicability=attachment_applicability,
    )
    consent_nodes = {
        r.change_id: r.assumptions
        for r in consent_requirements(preflight, selected.proposal, selected.approvals)
    }
    consents = tuple(
        c
        for c in plan.consents
        if "consent:" + c.consent_id not in invalidated
        and consent_nodes.get("consent:" + c.consent_id) == c.assumptions
    )
    event = ReviewRefreshEvent(
        schema_id="brz2obsidian.review-refresh-event",
        schema_version=1,
        expected_generation=plan.proposal.generation,
        facts=facts,
        preflight=preflight,
        previous_dependencies=tuple(old[k] for k in sorted(old)),
        dependencies=tuple(new[k] for k in sorted(new)),
        changed_keys=tuple(sorted(changed)),
        invalidated_keys=tuple(sorted(invalidated)),
        retained=tuple(bindings),
        producer_applicability=applicability,
        attachment_applicability=attachment_applicability,
    )
    updated = _plan(
        facts,
        preflight,
        actions=plan.actions,
        approvals=tuple(retained),
        consents=consents,
        producer_facts=producer_facts,
        producer_applicability=applicability,
        attachment_applicability=attachment_applicability,
    )
    updated = updated.model_copy(
        update={
            "history": plan.history.model_copy(
                update={"events": plan.history.events + (event,)}
            )
        }
    )
    return _transition(updated, "accepted", "accepted")


def refresh_review(plan, facts, *, preflight):
    validated = validate_review(plan)
    if validated.status != "accepted":
        return validated
    return _refresh(
        validated.plan,
        ReconciliationInput.model_validate(facts),
        ReviewPreflight.model_validate(preflight),
    )
