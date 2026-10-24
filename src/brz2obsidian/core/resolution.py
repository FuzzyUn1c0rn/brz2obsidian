"""Immutable current-generation review; no storage, parsing or publication."""

import json
from hashlib import sha256

from brz2obsidian.contracts import (
    CompatibleReviewGroup,
    IdentityAssociationDecision,
    PreservationDecision,
    ProposalAssumption,
    ReconciliationInput,
    RenamePathDecision,
    ReviewAction,
    ReviewApproval,
    ReviewConsentDecision,
    ReviewHistory,
    ReviewPlan,
    ReviewPreflight,
    ReviewRefreshEvent,
    ReviewRequirement,
    ReviewTransition,
)
from brz2obsidian.core.attachment_validation import validate_attachment_candidate
from brz2obsidian.core.link_meanings import _semantic
from brz2obsidian.core.memberships import used_mappings
from brz2obsidian.core.reconciliation import _reconcile
from brz2obsidian.core.reversals import (
    primary_reversal_content,
    reversal_subject,
    reversal_text_comparison,
)
from brz2obsidian.core.review_attachments import (
    applicable_approvals,
    attachment_candidate_assumption,
    attachment_selection_valid,
)
from brz2obsidian.core.review_effects import selected_effect_blockers
from brz2obsidian.core.review_links import (
    compatible_result_eligible,
    consumed_context,
    current_observation_problem,
    selected_current_links_safe,
)
from brz2obsidian.core.review_preflight import consent_requirements, preflight_blockers
from brz2obsidian.core.structures import validate_structure_facts
from brz2obsidian.core.text_candidates import validate_text_candidate


def _domain(facts, change):
    subject = next(
        s
        for s in facts.subjects
        if (s.item_id, s.facet) == (change.item_id, change.facet)
    )
    if (
        change.identity_review.status != "matched"
        or change.identity_review.repair_required
    ):
        return "identity"
    if change.rename_review is not None and change.rename_review.requires_decision:
        return "rename"
    if subject.operation_reversal is not None:
        return "reversal"
    if change.disposition == "restoration":
        return "restoration"
    if subject.output_role == "configuration":
        return "configuration"
    if change.format_review is not None:
        return "format"
    if change.attachment_review is not None:
        return "attachment"
    comparison = subject.structure
    if comparison is not None:
        meaning = lambda records: {
            m.classification_id: (m.kind, m.target_id) for m in records
        }
        prior, incoming = used_mappings(comparison)
        if meaning(prior) != meaning(incoming):
            return "mapping"
    return "text"


def _observed_absence(facts, change, domain):
    subject = next(
        s
        for s in facts.subjects
        if (s.item_id, s.facet) == (change.item_id, change.facet)
    )
    return (
        (
            domain == "reversal"
            and subject.operation_reversal is not None
            or domain in ("configuration", "format")
            and facts.format_operation.kind != "source_update"
        )
        and facts.inventory == "complete"
        and change.current is None
        and subject.current.existence == "absent"
    )


def _choices(facts, change, domain):
    if domain == "reversal":
        if change.disposition != "operation_reversal":
            return ()
        subject = next(
            s
            for s in facts.subjects
            if (s.item_id, s.facet) == (change.item_id, change.facet)
        )
        return ("current", "reverse") + (
            ("edited",) if subject.attachment is None else ()
        )
    if domain == "identity":
        return ("associate",)
    if domain == "rename":
        return ("keep_path", "source_path")
    if domain == "restoration":
        return ("decline_restoration", "restore_incoming")
    if change.attachment_review is not None:
        choices = tuple(
            a.choice for a in change.attachment_review.alternatives if a.eligible
        )
        return (
            ("current",)
            if _observed_absence(facts, change, domain) and "current" not in choices
            else ()
        ) + choices
    return (
        (
            ("approve",)
            if change.disposition == "compatible"
            and compatible_result_eligible(facts, change)
            else ()
        )
        + (
            ("current",)
            if change.current is not None or _observed_absence(facts, change, domain)
            else ()
        )
        + (("incoming",) if change.incoming is not None else ())
        + ("edited",)
    )


def _plan(
    facts,
    preflight,
    actions=(),
    approvals=(),
    consents=(),
    *,
    producer_facts=None,
    producer_applicability=(),
    attachment_applicability=(),
):
    initial = facts
    facts = producer_facts or facts
    proposal = _reconcile(facts, _applicability=producer_applicability)
    attachment_applicability = tuple(
        a
        for a in attachment_applicability
        if any(b.decision_id == a.decision_id for b in approvals)
    )
    effective_approvals = applicable_approvals(approvals, attachment_applicability)
    approved = {(a.change_id, a.domain) for a in approvals}
    requirements = tuple(
        ReviewRequirement(
            requirement_id=c.change_id,
            domain=_domain(facts, c),
            change_id=c.change_id,
            choices=_choices(facts, c, _domain(facts, c)),
            assumptions=c.assumptions,
        )
        for c in proposal.changes
        if (
            c.requires_decision
            or c.identity_review.repair_required
            or (c.rename_review is not None and c.rename_review.requires_decision)
        )
        and (c.change_id, _domain(facts, c)) not in approved
    )
    members = tuple(
        c
        for c in proposal.changes
        if c.disposition == "compatible"
        and _domain(facts, c) == "text"
        and compatible_result_eligible(facts, c)
        and (c.change_id, "text") not in approved
        and not any(
            f.blocking and f.subject_id in (None, c.subject_id)
            for f in proposal.findings
        )
    )
    groups = ()
    if members:
        fingerprint = sha256(
            json.dumps(
                [
                    (c.change_id, [(a.key, a.fingerprint) for a in c.assumptions])
                    for c in members
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        group_id = "compatible:" + fingerprint
        dependency = ProposalAssumption(
            key=group_id,
            kind="candidate",
            fingerprint=fingerprint,
            depends_on=tuple(sorted({a.key for c in members for a in c.assumptions})),
        )
        groups = (
            CompatibleReviewGroup(
                group_id=group_id,
                member_change_ids=tuple(c.change_id for c in members),
                comparisons=members,
                count=len(members),
                proposed_bytes=sum(len(c.result.data) for c in members),
                assumptions=(dependency,),
            ),
        )
    consent_rows = consent_requirements(preflight, proposal, effective_approvals)
    satisfied = {c.consent_id: c for c in consents}
    requirements += tuple(
        r
        for r in consent_rows
        if r.change_id.removeprefix("consent:") not in satisfied
        or satisfied[r.change_id.removeprefix("consent:")].choice != "accept"
        or satisfied[r.change_id.removeprefix("consent:")].assumptions != r.assumptions
    )
    blockers = (
        tuple(f.code for f in proposal.findings if f.blocking)
        + preflight_blockers(facts, preflight, proposal)
        + (
            ()
            if current_observation_problem(facts) is None
            else (current_observation_problem(facts),)
        )
        + selected_effect_blockers(facts, proposal, actions, effective_approvals)
        + tuple(
            "consent_declined:" + c.consent_id
            for c in consents
            if c.choice == "decline"
        )
    )
    readiness = (
        "refused" if blockers else "review_required" if requirements else "ready"
    )
    return ReviewPlan(
        schema_id="brz2obsidian.review-plan",
        schema_version=1,
        history=ReviewHistory(
            schema_id="brz2obsidian.review-history",
            schema_version=1,
            initial_facts=initial,
            initial_preflight=preflight,
            events=(),
        ),
        producer_applicability=producer_applicability,
        attachment_applicability=attachment_applicability,
        facts=initial,
        producer_facts=facts,
        preflight=preflight,
        proposal=proposal,
        actions=actions,
        approvals=approvals,
        consents=consents,
        requirements=requirements,
        groups=groups,
        blockers=blockers,
        readiness=readiness,
        ready=readiness == "ready",
    )


def prepare_review(
    facts: ReconciliationInput, *, preflight: ReviewPreflight
) -> ReviewPlan:
    return _plan(facts, ReviewPreflight.model_validate(preflight))


def _transition(plan, status, code):
    return ReviewTransition(
        schema_id="brz2obsidian.review-transition",
        schema_version=1,
        status=status,
        code=code,
        plan=plan,
    )


def _preserved_memory(plan, change, action, choice="keep_vault"):
    subject = next(
        s
        for s in plan.producer_facts.subjects
        if (s.item_id, s.facet) == (change.item_id, change.facet)
    )
    decision = PreservationDecision(
        schema_id="brz2obsidian.preservation-decision",
        schema_version=1,
        decision_id=action.decision_id,
        proposal_id=action.proposal_id,
        generation=action.expected_generation,
        collection_id=plan.producer_facts.incoming_identity.collection_id,
        module_id=plan.producer_facts.incoming_identity.module_id,
        item_id=change.item_id,
        facet=change.facet,
        reviewed_change_id=change.change_id,
        reviewed_source_version=change.source_version,
        reviewed_assumptions=change.assumptions,
        choice=choice,
        review_domain="configuration"
        if subject.output_role == "configuration"
        else "content",
        provenance="explicit_user",
    )
    decisions = tuple(
        d
        for d in plan.producer_facts.preservation_decisions
        if (d.item_id, d.facet) != (change.item_id, change.facet)
    ) + (decision,)
    result = _reconcile(
        plan.producer_facts.model_copy(update={"preservation_decisions": decisions}),
        _applicability=plan.producer_applicability,
    )
    selected = next(c for c in result.changes if c.subject_id == change.subject_id)
    if selected.requires_decision or selected.disposition != (
        "preserve_vault" if choice == "keep_vault" else "local_deleted"
    ):
        return None
    if choice == "keep_vault" and (
        selected.result is None or selected.result.data != change.current.data
    ):
        return None
    return next(
        (
            m
            for m in result.source_version_memory
            if m.provenance.decision_id == action.decision_id
        ),
        None,
    )


def _candidate_assumption(candidate, change, decision_id):
    values = candidate.model_dump(
        mode="json",
        exclude={"content", "document", "links", "link_targets", "link_target_facts"},
    )
    values["content_sha256"] = sha256(candidate.content.data).hexdigest()
    values["links"] = _semantic(
        consumed_context(
            (candidate.links,),
            candidate.link_targets,
            candidate.link_target_facts,
            candidate.links.inventory,
        )
    )
    values["document"] = candidate.document.model_dump(mode="json", exclude={"content"})
    fingerprint = sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    return ProposalAssumption(
        key="review-candidate:" + decision_id,
        kind="candidate",
        fingerprint=fingerprint,
        depends_on=tuple(a.key for a in change.assumptions),
    )


def _producer_transition(plan, action, facts):
    proposal = _reconcile(facts, _applicability=plan.producer_applicability)
    current = {c.change_id: c for c in proposal.changes}
    retained = tuple(
        a
        for a in plan.approvals
        if a.change_id in current
        and all(
            assumption in a.assumptions
            for assumption in current[a.change_id].assumptions
        )
    )
    return _plan(
        plan.facts,
        plan.preflight,
        plan.actions + (action,),
        retained,
        plan.consents,
        producer_facts=facts,
        producer_applicability=plan.producer_applicability,
        attachment_applicability=plan.attachment_applicability,
    )


def _resolve_action(plan, action):
    action = ReviewAction.model_validate(action)
    reserved = {
        d.decision_id
        for d in plan.producer_facts.association_decisions
        + plan.producer_facts.rename_decisions
        + plan.producer_facts.preservation_decisions
    }
    reserved.update(
        m.provenance.decision_id for m in plan.producer_facts.source_version_memory
    )
    if action.decision_id in {a.decision_id for a in plan.actions} | reserved:
        return _transition(plan, "refused", "decision_id_reused")
    if action.proposal_id != plan.proposal.proposal_id:
        return _transition(plan, "refused", "wrong_proposal")
    if action.expected_generation != plan.proposal.generation:
        return _transition(plan, "stale", "generation_changed")
    if current_observation_problem(plan.producer_facts) is not None:
        return _transition(plan, "refused", "unsafe_producer_choice")
    if preflight_blockers(plan.facts, plan.preflight, plan.proposal):
        return _transition(plan, "refused", "preflight_refused")
    if action.domain not in (
        "attachment",
        "configuration",
        "format",
        "restoration",
        "reversal",
    ) and (
        action.attachment_selection is not None
        or action.attachment_candidate is not None
    ):
        return _transition(plan, "refused", "choice_not_admitted")
    if action.domain in ("storage", "tracking"):
        requirement = next(
            (
                r
                for r in plan.requirements
                if r.change_id == action.change_id and r.domain == action.domain
            ),
            None,
        )
        if requirement is None:
            return _transition(plan, "refused", "unknown_change")
        if action.reviewed_assumptions != requirement.assumptions:
            return _transition(plan, "stale", "assumptions_changed")
        if (
            action.choice not in requirement.choices
            or action.candidate is not None
            or action.selected_entry_id is not None
            or action.disassociate_entry_ids
        ):
            return _transition(plan, "refused", "choice_not_admitted")
        consent_id = action.change_id.removeprefix("consent:")
        decision = ReviewConsentDecision(
            schema_id="brz2obsidian.review-consent-decision",
            schema_version=1,
            decision_id=action.decision_id,
            consent_id=consent_id,
            kind=action.domain,
            choice=action.choice,
            assumptions=requirement.assumptions,
            provenance="explicit_user",
        )
        consents = tuple(c for c in plan.consents if c.consent_id != consent_id) + (
            decision,
        )
        return _transition(
            _plan(
                plan.facts,
                plan.preflight,
                plan.actions + (action,),
                plan.approvals,
                consents,
                producer_facts=plan.producer_facts,
                producer_applicability=plan.producer_applicability,
                attachment_applicability=plan.attachment_applicability,
            ),
            "accepted",
            "accepted",
        )
    if action.domain == "compatible_group":
        group = next((g for g in plan.groups if g.group_id == action.change_id), None)
        if group is None:
            return _transition(plan, "refused", "unknown_change")
        if action.reviewed_assumptions != group.assumptions:
            return _transition(plan, "stale", "assumptions_changed")
        if (
            action.choice != "approve"
            or action.candidate is not None
            or action.selected_entry_id is not None
            or action.disassociate_entry_ids
        ):
            return _transition(plan, "refused", "choice_not_admitted")
        approvals = tuple(
            ReviewApproval(
                schema_id="brz2obsidian.review-approval",
                schema_version=1,
                decision_id=action.decision_id,
                change_id=c.change_id,
                domain="text",
                choice="approve",
                result=c.result,
                target_path=c.target_path,
                assumptions=c.assumptions,
                provenance="compatible_bulk",
                source_accepted=True,
                source_memory=None,
                attachment_selection=None,
                attachment_candidate=None,
            )
            for c in group.comparisons
        )
        return _transition(
            _plan(
                plan.facts,
                plan.preflight,
                plan.actions + (action,),
                plan.approvals + approvals,
                plan.consents,
                producer_facts=plan.producer_facts,
                producer_applicability=plan.producer_applicability,
                attachment_applicability=plan.attachment_applicability,
            ),
            "accepted",
            "accepted",
        )
    change = next(
        (c for c in plan.proposal.changes if c.change_id == action.change_id), None
    )
    if change is None:
        return _transition(plan, "refused", "unknown_change")
    if sorted(action.reviewed_assumptions, key=lambda a: a.key) != sorted(
        change.assumptions, key=lambda a: a.key
    ):
        return _transition(plan, "stale", "assumptions_changed")
    if any(
        f.blocking and f.subject_id in (None, change.subject_id)
        for f in plan.proposal.findings
    ):
        return _transition(plan, "refused", "preflight_refused")
    if action.domain in ("text", "configuration", "mapping", "format", "restoration"):
        subject = next(
            s
            for s in plan.producer_facts.subjects
            if (s.item_id, s.facet) == (change.item_id, change.facet)
        )
        if (
            subject.structure is not None
            and validate_structure_facts(
                subject,
                plan.producer_facts.baseline_identity,
                plan.producer_facts.incoming_identity,
                source_version=plan.producer_facts.format_operation.baseline_source_version,
                current_target_safety=action.choice
                in ("current", "decline_restoration"),
            )
            is not None
        ):
            return _transition(plan, "refused", "unsafe_producer_choice")
    if action.domain == "identity":
        review = change.identity_review
        if (
            _domain(plan.producer_facts, change) != "identity"
            or action.choice != "associate"
            or action.candidate is not None
            or action.selected_entry_id is None
            or action.selected_entry_id in action.disassociate_entry_ids
            or len(set(action.disassociate_entry_ids))
            != len(action.disassociate_entry_ids)
        ):
            return _transition(plan, "refused", "choice_not_admitted")
        requested = (action.selected_entry_id, *action.disassociate_entry_ids)
        assumptions = review.assumptions + tuple(
            a
            for c in review.candidates
            if c.entry_id in requested
            for a in c.assumptions
        )
        decision = IdentityAssociationDecision(
            schema_id="brz2obsidian.identity-association-decision",
            schema_version=1,
            decision_id=action.decision_id,
            proposal_id=action.proposal_id,
            generation=action.expected_generation,
            collection_id=plan.producer_facts.incoming_identity.collection_id,
            module_id=plan.producer_facts.incoming_identity.module_id,
            item_id=change.item_id,
            facet=change.facet,
            selected_entry_id=action.selected_entry_id,
            disassociate_entry_ids=action.disassociate_entry_ids,
            reviewed_assumptions=assumptions,
            provenance="explicit_user",
        )
        facts = plan.producer_facts.model_copy(
            update={
                "association_decisions": tuple(
                    d
                    for d in plan.producer_facts.association_decisions
                    if (d.item_id, d.facet) != (change.item_id, change.facet)
                )
                + (decision,)
            }
        )
        updated = _producer_transition(plan, action, facts)
        changed = next(
            c for c in updated.proposal.changes if c.subject_id == change.subject_id
        )
        if changed.identity_review.status not in ("matched", "association_proposed"):
            return _transition(plan, "refused", "unsafe_producer_choice")
        return _transition(updated, "accepted", "accepted")
    if action.domain == "restoration":
        if (
            _domain(plan.producer_facts, change) != "restoration"
            or action.choice not in ("decline_restoration", "restore_incoming")
            or action.selected_entry_id is not None
            or action.disassociate_entry_ids
        ):
            return _transition(plan, "refused", "choice_not_admitted")
        memory = None
        result = None
        dependencies = change.assumptions
        if action.choice == "decline_restoration":
            if (
                action.candidate is not None
                or action.attachment_selection is not None
                or action.attachment_candidate is not None
            ):
                return _transition(plan, "refused", "choice_not_admitted")
            memory = _preserved_memory(plan, change, action, "decline_restoration")
            if memory is None:
                return _transition(plan, "refused", "unsafe_producer_choice")
        elif change.attachment_review is not None:
            if not attachment_selection_valid(
                plan.producer_facts, change, action, "incoming"
            ):
                return _transition(plan, "refused", "attachment_invalid")
            result = action.attachment_candidate.outputs[0].content
            dependencies += (
                attachment_candidate_assumption(
                    plan.producer_facts,
                    change,
                    action.attachment_selection,
                    action.attachment_candidate,
                    action.decision_id,
                ),
            )
        elif (
            action.attachment_selection is not None
            or action.attachment_candidate is not None
        ):
            return _transition(plan, "refused", "choice_not_admitted")
        elif action.candidate is None or not validate_text_candidate(
            plan.producer_facts, change, action.candidate, "incoming"
        ):
            return _transition(plan, "refused", "invalid_candidate")
        else:
            result = action.candidate.content
            dependencies += (
                _candidate_assumption(action.candidate, change, action.decision_id),
            )
        approval = ReviewApproval(
            schema_id="brz2obsidian.review-approval",
            schema_version=1,
            decision_id=action.decision_id,
            change_id=change.change_id,
            domain="restoration",
            choice=action.choice,
            result=result,
            target_path=change.target_path,
            assumptions=dependencies,
            provenance="explicit_user",
            source_accepted=memory is None,
            source_memory=memory,
            attachment_selection=action.attachment_selection,
            attachment_candidate=action.attachment_candidate,
        )
        return _transition(
            _plan(
                plan.facts,
                plan.preflight,
                plan.actions + (action,),
                tuple(
                    a
                    for a in plan.approvals
                    if (a.change_id, a.domain) != (change.change_id, "restoration")
                )
                + (approval,),
                plan.consents,
                producer_facts=plan.producer_facts,
                producer_applicability=plan.producer_applicability,
                attachment_applicability=plan.attachment_applicability,
            ),
            "accepted",
            "accepted",
        )
    if action.domain == "rename":
        review = change.rename_review
        if (
            review is None
            or action.choice not in ("keep_path", "source_path")
            or action.candidate is not None
            or action.selected_entry_id is not None
            or action.disassociate_entry_ids
        ):
            return _transition(plan, "refused", "choice_not_admitted")
        if review.status == "blocked" and action.choice == "source_path":
            return _transition(plan, "refused", "unsafe_producer_choice")
        decision = RenamePathDecision(
            schema_id="brz2obsidian.rename-decision",
            schema_version=1,
            decision_id=action.decision_id,
            proposal_id=action.proposal_id,
            generation=action.expected_generation,
            collection_id=plan.producer_facts.incoming_identity.collection_id,
            module_id=plan.producer_facts.incoming_identity.module_id,
            item_id=change.item_id,
            facet=change.facet,
            choice=action.choice,
            reviewed_assumptions=review.assumptions,
            provenance="explicit_user",
        )
        facts = plan.producer_facts.model_copy(
            update={
                "rename_decisions": tuple(
                    d
                    for d in plan.producer_facts.rename_decisions
                    if (d.item_id, d.facet) != (change.item_id, change.facet)
                )
                + (decision,)
            }
        )
        updated = _producer_transition(plan, action, facts)
        changed = next(
            c for c in updated.proposal.changes if c.subject_id == change.subject_id
        )
        if changed.rename_review.status not in ("accepted", "declined"):
            return _transition(plan, "refused", "unsafe_producer_choice")
        return _transition(updated, "accepted", "accepted")
    if change.attachment_review is not None and not (
        action.choice == "current"
        and (
            action.domain == "reversal"
            or _observed_absence(plan.producer_facts, change, action.domain)
        )
    ):
        if (
            action.domain != _domain(plan.producer_facts, change)
            or action.choice
            not in (
                _choices(plan.producer_facts, change, action.domain)
                if action.domain == "reversal"
                else ("current", "incoming", "both")
            )
            or action.candidate is not None
            or action.selected_entry_id is not None
            or action.disassociate_entry_ids
        ):
            return _transition(plan, "refused", "choice_not_admitted")
        selection, candidate = action.attachment_selection, action.attachment_candidate
        if (
            selection is None
            or candidate is None
            or selection.choice
            != ("incoming" if action.domain == "reversal" else action.choice)
            or (
                selection.proposal_id,
                selection.generation,
                selection.item_id,
                selection.facet,
                selection.reviewed_change_id,
                selection.reviewed_assumptions,
            )
            != (
                action.proposal_id,
                action.expected_generation,
                change.item_id,
                change.facet,
                change.change_id,
                action.reviewed_assumptions,
            )
        ):
            return _transition(plan, "refused", "attachment_invalid")
        if action.domain in ("configuration", "format") and (
            change.format_review is None or not change.format_review.target_eligible
        ):
            return _transition(plan, "refused", "unsafe_producer_choice")
        if not validate_attachment_candidate(
            plan.producer_facts, selection, candidate
        ).valid:
            return _transition(plan, "refused", "attachment_invalid")
        memory = None
        if (
            action.choice == "current"
            and plan.producer_facts.format_operation.kind == "source_update"
        ):
            memory = _preserved_memory(plan, change, action)
            if memory is None:
                return _transition(plan, "refused", "unsafe_producer_choice")
        approval = ReviewApproval(
            schema_id="brz2obsidian.review-approval",
            schema_version=1,
            decision_id=action.decision_id,
            change_id=change.change_id,
            domain=action.domain,
            choice=action.choice,
            result=candidate.outputs[0].content
            if len(candidate.outputs) == 1
            else None,
            target_path=change.target_path,
            assumptions=change.assumptions
            + (
                attachment_candidate_assumption(
                    plan.producer_facts,
                    change,
                    selection,
                    candidate,
                    action.decision_id,
                ),
            ),
            provenance="explicit_user",
            source_accepted=action.choice != "current" and action.domain != "reversal",
            source_memory=memory,
            attachment_selection=selection,
            attachment_candidate=candidate,
        )
        return _transition(
            _plan(
                plan.facts,
                plan.preflight,
                plan.actions + (action,),
                tuple(
                    a
                    for a in plan.approvals
                    if (a.change_id, a.domain) != (change.change_id, action.domain)
                )
                + (approval,),
                plan.consents,
                producer_facts=plan.producer_facts,
                producer_applicability=plan.producer_applicability,
                attachment_applicability=plan.attachment_applicability,
            ),
            "accepted",
            "accepted",
        )
    if (
        action.attachment_selection is not None
        or action.attachment_candidate is not None
    ):
        return _transition(plan, "refused", "choice_not_admitted")
    if action.domain != _domain(plan.producer_facts, change):
        return _transition(plan, "refused", "choice_not_admitted")
    if (
        action.domain not in ("text", "configuration", "mapping", "format", "reversal")
        or (
            action.choice == "approve"
            and (
                change.disposition != "compatible"
                or not compatible_result_eligible(plan.producer_facts, change)
            )
        )
        or action.choice not in _choices(plan.producer_facts, change, action.domain)
    ):
        return _transition(plan, "refused", "choice_not_admitted")
    if action.selected_entry_id is not None or action.disassociate_entry_ids:
        return _transition(plan, "refused", "choice_not_admitted")
    if action.domain in ("configuration", "format") and (
        change.format_review is None or not change.format_review.target_eligible
    ):
        return _transition(plan, "refused", "unsafe_producer_choice")
    reversal_present = (
        action.domain == "reversal"
        and action.choice == "reverse"
        and reversal_subject(plan.producer_facts, change).attachment is None
        and any(
            r.target is not None
            for r in reversal_subject(
                plan.producer_facts, change
            ).operation_reversal.outputs
        )
    )
    if (
        action.choice in ("incoming", "edited") or reversal_present
    ) and action.candidate is None:
        return _transition(plan, "refused", "invalid_candidate")
    if action.candidate is not None and not validate_text_candidate(
        plan.producer_facts,
        reversal_text_comparison(plan.producer_facts, change)
        if action.domain == "reversal" and action.choice in ("reverse", "edited")
        else change,
        action.candidate,
        "incoming" if reversal_present else action.choice,
        mapping_choice=action.domain == "mapping",
    ):
        return _transition(plan, "refused", "invalid_candidate")
    if action.choice == "approve" and action.candidate is not None:
        return _transition(plan, "refused", "choice_not_admitted")
    if (
        action.choice == "reverse"
        and not reversal_present
        and action.candidate is not None
    ):
        return _transition(plan, "refused", "choice_not_admitted")
    memory = None
    if action.choice == "current":
        if not selected_current_links_safe(plan.producer_facts, change):
            return _transition(plan, "refused", "invalid_candidate")
        if change.current is None and not _observed_absence(
            plan.producer_facts, change, action.domain
        ):
            return _transition(plan, "refused", "choice_not_admitted")
        subject = next(
            s
            for s in plan.producer_facts.subjects
            if (s.item_id, s.facet) == (change.item_id, change.facet)
        )
        if action.domain in ("text", "mapping") or (
            action.domain == "configuration"
            and plan.producer_facts.format_operation.kind == "source_update"
        ):
            memory = _preserved_memory(plan, change, action)
            if memory is None:
                return _transition(plan, "refused", "unsafe_producer_choice")
    dependencies = change.assumptions + (
        ()
        if action.candidate is None
        else (_candidate_assumption(action.candidate, change, action.decision_id),)
    )
    approval = ReviewApproval(
        schema_id="brz2obsidian.review-approval",
        schema_version=1,
        decision_id=action.decision_id,
        change_id=change.change_id,
        domain=action.domain,
        choice=action.choice,
        result=primary_reversal_content(
            reversal_subject(plan.producer_facts, change), reverse=True
        )
        if action.choice == "reverse"
        else change.result
        if action.choice == "approve"
        else change.current
        if action.choice == "current"
        else action.candidate.content,
        target_path=change.target_path,
        assumptions=dependencies,
        provenance="explicit_user",
        source_accepted=action.choice in ("approve", "incoming"),
        source_memory=memory,
        attachment_selection=None,
        attachment_candidate=None,
    )
    updated = _plan(
        plan.facts,
        plan.preflight,
        plan.actions + (action,),
        tuple(
            a
            for a in plan.approvals
            if (a.change_id, a.domain) != (approval.change_id, approval.domain)
        )
        + (approval,),
        plan.consents,
        producer_facts=plan.producer_facts,
        producer_applicability=plan.producer_applicability,
        attachment_applicability=plan.attachment_applicability,
    )
    return _transition(updated, "accepted", "accepted")


def _resolve(plan, action):
    action = ReviewAction.model_validate(action)
    result = _resolve_action(plan, action)
    if result.status == "accepted":
        result = result.model_copy(
            update={
                "plan": result.plan.model_copy(
                    update={
                        "history": plan.history.model_copy(
                            update={"events": plan.history.events + (action,)}
                        )
                    }
                )
            }
        )
    return result


def validate_review(plan: ReviewPlan) -> ReviewTransition:
    """Reconstruct original actions and publication-free refreshes in their epochs."""
    from .refresh import _refresh

    plan = ReviewPlan.model_validate(plan)
    canonical = prepare_review(
        plan.history.initial_facts, preflight=plan.history.initial_preflight
    )
    for event in plan.history.events:
        if isinstance(event, ReviewRefreshEvent):
            replayed = _refresh(canonical, event.facts, event.preflight)
        else:
            replayed = _resolve(canonical, event)
        if replayed.status != "accepted":
            return _transition(canonical, "refused", "invalid_plan")
        canonical = replayed.plan
    if canonical != plan:
        return _transition(canonical, "refused", "invalid_plan")
    return _transition(canonical, "accepted", "accepted")


def resolve_review(plan: ReviewPlan, action: ReviewAction) -> ReviewTransition:
    """Reconstruct prior authority, then admit exactly one current-generation action."""
    validated = validate_review(plan)
    return (
        validated
        if validated.status != "accepted"
        else _resolve(validated.plan, action)
    )
