"""Immutable current-generation review; no storage, parsing or publication."""

import json
from dataclasses import dataclass, replace
from hashlib import sha256

from brz2obsidian.content_fingerprints import (
    ChildWork,
    CompletedWork,
    PendingFingerprint,
    canonical_equal,
    consume_fingerprint,
    drive_inline,
)
from brz2obsidian.content_values import (
    content_sha,
    content_size,
    require_inline,
    same_content,
)
from brz2obsidian.contracts import (
    AttachmentSelection,
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
    ReviewKeepCurrentGroup,
    ReviewPlan,
    ReviewPreflight,
    ReviewRefreshEvent,
    ReviewRequirement,
    ReviewTransition,
)
from brz2obsidian.core._replay_memo import _ReplayMemo
from brz2obsidian.core.attachment_validation import CandidateWork, _candidate_validation
from brz2obsidian.core.identity import rename_source_path_safe
from brz2obsidian.core.link_meanings import _semantic
from brz2obsidian.core.memberships import used_mappings
from brz2obsidian.core.reconciliation import ReconcileWork
from brz2obsidian.core.reversals import (
    primary_reversal_content,
    reversal_document_target,
    reversal_subject,
    reversal_text_comparison,
)
from brz2obsidian.core.review_attachments import (
    _attachment_selection_matches,
    applicable_approvals,
    attachment_candidate_assumption,
    attachment_candidate_request,
)
from brz2obsidian.core.review_composition import CompositionOutcome, CompositionWork
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

# Pure computed values belong to this replay implementation's loaded lifetime.
# Current storage observations, validation verdicts and caller plans are not cached.
_replay_memo = _ReplayMemo()


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
            ("edited",)
            if subject.attachment is None and reversal_document_target(subject) is None
            else ()
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


def _choice_requirements(facts, proposal):
    return tuple(
        ReviewRequirement(
            requirement_id=c.change_id,
            domain=_domain(facts, c),
            change_id=c.change_id,
            choices=_choices(facts, c, _domain(facts, c)),
            assumptions=c.assumptions,
        )
        for c in proposal.changes
    )


def _format_choice_unavailable(change, domain, choice):
    return (domain == "format" and change.format_review is None) or (
        domain in ("configuration", "format")
        and change.format_review is not None
        and choice != "current"
        and not change.format_review.target_eligible
    )


def _choice_offer(
    change,
    requirement,
    *,
    operation_kind,
    source_path_safe=True,
    current_absence_safe=False,
):
    from brz2obsidian.contracts import ReviewChoiceAvailability, ReviewChoiceOffer

    alternatives = (
        {a.choice: a for a in change.attachment_review.alternatives}
        if change is not None
        and change.attachment_review is not None
        and requirement.domain not in ("reversal", "rename")
        else {}
    )
    choices = tuple(dict.fromkeys((*requirement.choices, *alternatives)))
    availability = []
    for choice in choices:
        reasons = []
        if (
            requirement.domain == "rename"
            and choice == "source_path"
            and not source_path_safe
        ):
            reasons.append("unsafe_producer_choice")
        if change is not None and _format_choice_unavailable(
            change, requirement.domain, choice
        ):
            reasons.append("unsafe_producer_choice")
        if (
            change is not None
            and change.format_review is not None
            and change.attachment_review is not None
            and requirement.domain in ("configuration", "format")
            and not (choice == "current" and current_absence_safe)
        ):
            if operation_kind not in ("onboarding", "format_transition"):
                reasons.append(
                    "review_onboarding_or_output_format_transition_before_choosing_this_attachment"
                )
            elif choice != "current":
                reasons.append(
                    "keep_vault_version_is_required_for_attachment_format_review"
                )
        if (
            choice in alternatives
            and not alternatives[choice].eligible
            and not (choice == "current" and current_absence_safe)
        ):
            reasons.extend(alternatives[choice].unavailable_reasons)
        if choice not in requirement.choices and not reasons:
            reasons.append("choice_not_admitted")
        availability.append(
            ReviewChoiceAvailability(
                choice=choice,
                enabled=not reasons,
                reasons=tuple(dict.fromkeys(reasons)),
            )
        )
    return ReviewChoiceOffer(
        **requirement.model_dump(), availability=tuple(availability)
    )


def inspect_review_choices(plan):
    """Canonical offered decisions, including replacements of existing choices."""
    checked = validate_review(plan)
    if checked.status != "accepted":
        raise ValueError("Invalid review")
    return _inspect_canonical_choices(checked.plan)


def _inspect_canonical_choices(plan):
    """Project an already reconstructed plan; no input admission occurs here."""
    approved = {(a.change_id, a.domain) for a in plan.approvals}
    rows = tuple(
        _choice_offer(
            change,
            row,
            operation_kind=plan.producer_facts.format_operation.kind,
            current_absence_safe=_observed_absence(
                plan.producer_facts, change, row.domain
            ),
            source_path_safe=rename_source_path_safe(plan.producer_facts, change)
            if row.domain == "rename"
            else True,
        )
        for change, row in zip(
            plan.proposal.changes,
            _choice_requirements(plan.producer_facts, plan.proposal),
            strict=True,
        )
        if change.requires_decision
        or change.identity_review.repair_required
        or change.rename_review is not None
        and change.rename_review.requires_decision
        or (row.change_id, row.domain) in approved
    )
    return (
        rows
        + tuple(
            _choice_offer(
                change,
                ReviewRequirement(
                    requirement_id="rename:" + change.change_id,
                    domain="rename",
                    change_id=change.change_id,
                    choices=("keep_path", "source_path"),
                    assumptions=change.assumptions,
                ),
                operation_kind=plan.producer_facts.format_operation.kind,
                source_path_safe=rename_source_path_safe(plan.producer_facts, change),
            )
            for change in plan.proposal.changes
            if change.rename_review is not None
            and _domain(plan.producer_facts, change) != "rename"
        )
        + tuple(
            _choice_offer(
                None, row, operation_kind=plan.producer_facts.format_operation.kind
            )
            for row in plan.requirements
            if row.domain in ("tracking", "storage")
        )
        + tuple(
            _choice_offer(
                None,
                ReviewRequirement(
                    requirement_id=group.group_id,
                    domain="compatible_group",
                    change_id=group.group_id,
                    choices=("approve",),
                    assumptions=group.assumptions,
                ),
                operation_kind=plan.producer_facts.format_operation.kind,
            )
            for group in plan.groups
        )
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
    _canonical_prior=None,
):
    """Rebuild action safety; reuse a pure proposal only for identical bound facts.

    Only replay/resolution of an internally reconstructed canonical state supplies
    the prior. Initial preparation and refresh derive their proposal independently;
    no caller-provided derived plan or live admission verdict enters this reuse.
    """
    return drive_inline(
        PlanWork(
            facts,
            preflight,
            actions,
            approvals,
            consents,
            producer_facts,
            producer_applicability,
            attachment_applicability,
            _canonical_prior,
        )
    )


@dataclass(frozen=True)
class PlanWork:
    facts: ReconciliationInput
    preflight: ReviewPreflight
    actions: tuple = ()
    approvals: tuple = ()
    consents: tuple = ()
    producer_facts: object = None
    producer_applicability: tuple = ()
    attachment_applicability: tuple = ()
    canonical_prior: object = None
    phase: str = "proposal"
    proposal: object = None
    effective_approvals: tuple = ()
    filtered_applicability: tuple = ()
    automatic_plan: object = None
    automatic_index: int = 0
    automatic_jobs: tuple = ()
    automatic_action: object = None


def advance_plan(work, returned=None):
    facts = work.producer_facts or work.facts
    if work.phase == "proposal":
        prior = work.canonical_prior
        if (
            prior is not None
            and (
                prior.producer_facts is facts
                or canonical_equal(prior.producer_facts, facts)
            )
            and prior.producer_applicability == work.producer_applicability
        ):
            proposal = prior.proposal
        else:
            return ChildWork(
                ReconcileWork(facts, work.producer_applicability),
                replace(work, phase="finish"),
            )
    elif work.phase == "finish":
        proposal = returned
    elif work.phase == "automatic_member":
        if type(returned) is ReviewApproval:
            approval = returned.model_copy(update={"provenance": "automatic_merge"})
            work = replace(
                work,
                actions=work.actions + (work.automatic_action,),
                approvals=work.approvals + (approval,),
            )
        return replace(
            work, phase="automatic", automatic_index=work.automatic_index + 1
        )
    elif work.phase == "automatic":
        if work.automatic_index < len(work.automatic_jobs):
            change, subject = work.automatic_jobs[work.automatic_index]
            selection = AttachmentSelection(
                schema_id="brz2obsidian.attachment-selection",
                schema_version=1,
                proposal_id=facts.proposal_id,
                generation=facts.generation,
                item_id=change.item_id,
                facet=change.facet,
                reviewed_change_id=change.change_id,
                reviewed_assumptions=change.assumptions,
                choice="incoming",
                link_choices=subject.automatic_attachment_links,
                provenance="explicit_user",
            )
            action = ReviewAction(
                schema_id="brz2obsidian.review-action",
                schema_version=1,
                decision_id="automatic:" + change.change_id,
                proposal_id=facts.proposal_id,
                expected_generation=facts.generation,
                change_id=change.change_id,
                reviewed_assumptions=change.assumptions,
                domain="attachment",
                choice="incoming",
                candidate=None,
                attachment_selection=selection,
                attachment_candidate=subject.automatic_attachment,
                selected_entry_id=None,
                disassociate_entry_ids=(),
            )
            plan = work.automatic_plan.model_copy(
                update={"actions": work.actions, "approvals": work.approvals}
            )
            return ChildWork(
                AttachmentActionWork(
                    plan,
                    action,
                    change,
                    selection,
                    subject.automatic_attachment,
                    group_defer=True,
                ),
                replace(work, phase="automatic_member", automatic_action=action),
            )
        proposal = work.proposal
    elif work.phase == "composed":
        return CompletedWork(
            _finish_plan(
                work.facts,
                facts,
                work.preflight,
                work.actions,
                work.approvals,
                work.consents,
                work.proposal,
                work.producer_applicability,
                work.filtered_applicability,
                returned,
                work.effective_approvals,
            )
        )
    else:
        raise ValueError("Invalid plan phase")
    if work.phase in ("proposal", "finish") and facts.format_operation.automatic_merge:
        approved = {a.change_id for a in work.approvals}
        subjects = {(s.item_id, s.facet): s for s in facts.subjects}
        jobs = tuple(
            (c, subjects[(c.item_id, c.facet)])
            for c in proposal.changes
            if c.disposition == "compatible"
            and c.attachment_review is not None
            and c.format_review is None
            and c.change_id not in approved
            and subjects[(c.item_id, c.facet)].automatic_attachment is not None
        )
        if jobs:
            seed = _finish_plan(
                work.facts,
                facts,
                work.preflight,
                work.actions,
                work.approvals,
                work.consents,
                proposal,
                work.producer_applicability,
                work.attachment_applicability,
                CompositionOutcome(),
                work.approvals,
            )
            return replace(
                work,
                phase="automatic",
                proposal=proposal,
                automatic_plan=seed,
                automatic_jobs=jobs,
            )
    applicability = tuple(
        a
        for a in work.attachment_applicability
        if any(b.decision_id == a.decision_id for b in work.approvals)
    )
    effective = applicable_approvals(work.approvals, applicability)
    return ChildWork(
        CompositionWork(facts, work.actions, effective),
        replace(
            work,
            phase="composed",
            proposal=proposal,
            effective_approvals=effective,
            filtered_applicability=applicability,
        ),
    )


def _finish_plan(
    initial,
    facts,
    preflight,
    actions,
    approvals,
    consents,
    proposal,
    producer_applicability,
    attachment_applicability,
    composition,
    effective_approvals,
):
    approved = {(a.change_id, a.domain) for a in approvals}
    requirements = tuple(
        row
        for c, row in zip(
            proposal.changes, _choice_requirements(facts, proposal), strict=True
        )
        if (
            c.requires_decision
            or c.identity_review.repair_required
            or (c.rename_review is not None and c.rename_review.requires_decision)
        )
        and (row.change_id, row.domain) not in approved
    )
    members = tuple(
        c
        for c in proposal.changes
        if c.disposition == "compatible"
        and c.requires_decision
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
                proposed_bytes=sum(content_size(c.result) for c in members),
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
        + selected_effect_blockers(
            facts, proposal, actions, effective_approvals, composition=composition
        )
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
    facts = ReconciliationInput.model_validate(facts)
    preflight = ReviewPreflight.model_validate(preflight)
    require_inline((facts, preflight))
    return _plan(facts, preflight)


def _transition(plan, status, code):
    if type(plan) is PlanWork:
        return PlanTransition(plan, status, code)
    return ReviewTransition(
        schema_id="brz2obsidian.review-transition",
        schema_version=1,
        status=status,
        code=code,
        plan=plan,
    )


def _preserved_memory_facts(plan, change, action, choice):
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
    return plan.producer_facts.model_copy(update={"preservation_decisions": decisions})


def _candidate_assumption(candidate, change, decision_id):
    values = candidate.model_dump(
        mode="json",
        exclude={"content", "document", "links", "link_targets", "link_target_facts"},
    )
    values["content_sha256"] = content_sha(candidate.content)
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


def _producer_transition(plan, action, facts, change):
    return ProducerActionWork(plan, action, facts, change.subject_id)


def _resolve_action(plan, action, *, _epoch=0, _group_admitted=False):
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
    if (
        not _group_admitted
        and current_observation_problem(plan.producer_facts) is not None
    ):
        return _transition(plan, "refused", "unsafe_producer_choice")
    if not _group_admitted and preflight_blockers(
        plan.facts, plan.preflight, plan.proposal
    ):
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
            PlanWork(
                plan.facts,
                plan.preflight,
                plan.actions + (action,),
                plan.approvals,
                consents,
                producer_facts=plan.producer_facts,
                producer_applicability=plan.producer_applicability,
                attachment_applicability=plan.attachment_applicability,
                canonical_prior=plan,
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
            PlanWork(
                plan.facts,
                plan.preflight,
                plan.actions + (action,),
                plan.approvals + approvals,
                plan.consents,
                producer_facts=plan.producer_facts,
                producer_applicability=plan.producer_applicability,
                attachment_applicability=plan.attachment_applicability,
                canonical_prior=plan,
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
        return _producer_transition(plan, action, facts, change)
    if action.domain == "restoration":
        if (
            _domain(plan.producer_facts, change) != "restoration"
            or action.choice not in ("decline_restoration", "restore_incoming")
            or action.selected_entry_id is not None
            or action.disassociate_entry_ids
        ):
            return _transition(plan, "refused", "choice_not_admitted")
        result = None
        dependencies = change.assumptions
        if action.choice == "decline_restoration":
            if (
                action.candidate is not None
                or action.attachment_selection is not None
                or action.attachment_candidate is not None
            ):
                return _transition(plan, "refused", "choice_not_admitted")
            return ApprovalWork(
                plan,
                action,
                change,
                None,
                dependencies,
                False,
                memory_choice="decline_restoration",
            )
        elif change.attachment_review is not None:
            if not _attachment_selection_matches(
                plan.producer_facts, change, action, "incoming"
            ):
                return _transition(plan, "refused", "attachment_invalid")
            return AttachmentActionWork(
                plan,
                action,
                change,
                action.attachment_selection,
                action.attachment_candidate,
                _epoch,
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
        return ApprovalWork(plan, action, change, result, dependencies, True)
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
        return _producer_transition(plan, action, facts, change)
    if change.attachment_review is not None and not (
        action.choice == "current"
        and (
            action.domain == "reversal"
            or _observed_absence(plan.producer_facts, change, action.domain)
        )
    ):
        if (
            action.domain != _domain(plan.producer_facts, change)
            or action.choice not in _choices(plan.producer_facts, change, action.domain)
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
        if _format_choice_unavailable(change, action.domain, action.choice):
            return _transition(plan, "refused", "unsafe_producer_choice")
        return AttachmentActionWork(plan, action, change, selection, candidate, _epoch)
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
    if _format_choice_unavailable(change, action.domain, action.choice):
        return _transition(plan, "refused", "unsafe_producer_choice")
    reversal_present = (
        action.domain == "reversal"
        and action.choice == "reverse"
        and reversal_subject(plan.producer_facts, change).attachment is None
        and reversal_document_target(reversal_subject(plan.producer_facts, change))
        is None
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
    memory_choice = None
    if action.choice == "current":
        if not selected_current_links_safe(
            plan.producer_facts, change, candidate=action.candidate
        ):
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
        if (
            action.domain in ("text", "mapping")
            or action.domain == "configuration"
            and plan.producer_facts.format_operation.kind == "source_update"
        ) and not (
            change.current is not None
            and change.incoming is not None
            and same_content(change.current, change.incoming)
        ):
            memory_choice = "keep_vault"
    return ApprovalWork(
        plan,
        action,
        change,
        None,
        (),
        action.choice in ("approve", "incoming"),
        memory_choice=memory_choice,
        derive_plain=True,
    )


def _append_action(plan, action, result):
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


def _resolve(plan, action):
    return drive_inline(
        ActionWork(
            plan,
            ReviewKeepCurrentGroup.model_validate(action)
            if isinstance(action, ReviewKeepCurrentGroup)
            else ReviewAction.model_validate(action),
        )
    )


def _reconstruct_review(plan: ReviewPlan) -> ReviewTransition:
    """Reconstruct typed history using only successfully computed exact prefixes."""
    from .refresh import _refresh

    history = ReviewHistory.model_validate(plan.history)
    retained = _replay_memo.longest_prefix(history)
    if retained is not None and retained[0] == len(history.events):
        canonical = ReviewPlan.model_validate_json(retained[1])
        return _transition(canonical, "accepted", "accepted")
    prefixes = _replay_memo.prefixes(history)
    initial_prefix = next(prefixes, None)
    if retained is None:
        canonical = prepare_review(
            history.initial_facts, preflight=history.initial_preflight
        )
        _replay_memo.retain(initial_prefix, canonical)
        consumed = 0
    else:
        consumed, encoded = retained
        canonical = ReviewPlan.model_validate_json(encoded)
    for count, event in enumerate(history.events, 1):
        prefix = next(prefixes, None)
        if count <= consumed:
            continue
        if isinstance(event, ReviewRefreshEvent):
            replayed = _refresh(canonical, event.facts, event.preflight)
        else:
            replayed = _resolve(canonical, event)
        if replayed.status != "accepted":
            return _transition(canonical, "refused", "invalid_plan")
        canonical = replayed.plan
        _replay_memo.retain(prefix, canonical)
    return _transition(canonical, "accepted", "accepted")


def validate_review(plan: ReviewPlan) -> ReviewTransition:
    """Reconstruct original actions and require the entire canonical plan exactly."""
    plan = ReviewPlan.model_validate(plan)
    require_inline(plan)
    reconstructed = _reconstruct_review(plan)
    if reconstructed.status != "accepted":
        return reconstructed
    canonical = reconstructed.plan
    if canonical != plan:
        return _transition(canonical, "refused", "invalid_plan")
    return reconstructed


def resolve_review(
    plan: ReviewPlan, action: ReviewAction | ReviewKeepCurrentGroup
) -> ReviewTransition:
    """Reconstruct prior authority, then admit exactly one current-generation action."""
    validated = validate_review(plan)
    if validated.status != "accepted":
        return validated
    action = (
        ReviewKeepCurrentGroup.model_validate(action)
        if isinstance(action, ReviewKeepCurrentGroup)
        else ReviewAction.model_validate(action)
    )
    require_inline(action)
    return _resolve(validated.plan, action)


@dataclass(frozen=True)
class PlanTransition:
    work: PlanWork
    status: str
    code: str


@dataclass(frozen=True)
class ProducerActionWork:
    plan: ReviewPlan
    action: ReviewAction
    facts: ReconciliationInput
    subject_id: str
    phase: str = "reconcile"


def advance_producer_action(work, returned=None):
    plan, action = work.plan, work.action
    if work.phase == "reconcile":
        return ChildWork(
            ReconcileWork(work.facts, plan.producer_applicability),
            replace(work, phase="plan"),
        )
    if work.phase == "plan":
        current = {change.change_id: change for change in returned.changes}
        retained = tuple(
            approval
            for approval in plan.approvals
            if approval.change_id in current
            and all(
                assumption in approval.assumptions
                for assumption in current[approval.change_id].assumptions
            )
        )
        return ChildWork(
            PlanWork(
                plan.facts,
                plan.preflight,
                plan.actions + (action,),
                retained,
                plan.consents,
                producer_facts=work.facts,
                producer_applicability=plan.producer_applicability,
                attachment_applicability=plan.attachment_applicability,
                canonical_prior=plan,
            ),
            replace(work, phase="finish"),
        )
    if work.phase == "finish":
        changed = next(
            change
            for change in returned.proposal.changes
            if change.subject_id == work.subject_id
        )
        if action.domain == "identity":
            valid = changed.identity_review.status in (
                "matched",
                "association_proposed",
            )
        elif action.domain == "rename":
            valid = changed.rename_review.status in ("accepted", "declined")
        else:
            raise ValueError("Unknown producer action domain")
        return CompletedWork(
            _transition(returned, "accepted", "accepted")
            if valid
            else _transition(plan, "refused", "unsafe_producer_choice")
        )
    raise ValueError("Invalid producer action phase")


@dataclass(frozen=True)
class PreservedMemoryWork:
    plan: ReviewPlan
    change: object
    action: ReviewAction
    choice: str
    phase: str = "reconcile"


@dataclass(frozen=True)
class PreservedMemoryResult:
    work: PreservedMemoryWork
    memory: object


def advance_preserved_memory(work, returned=None):
    if work.phase == "reconcile":
        facts = _preserved_memory_facts(
            work.plan, work.change, work.action, work.choice
        )
        return ChildWork(
            ReconcileWork(facts, work.plan.producer_applicability),
            replace(work, phase="finish"),
        )
    if work.phase != "finish":
        raise ValueError("Invalid preserved memory phase")
    selected = next(
        change
        for change in returned.changes
        if change.subject_id == work.change.subject_id
    )
    valid = not selected.requires_decision and selected.disposition == (
        "preserve_vault" if work.choice == "keep_vault" else "local_deleted"
    )
    if (
        valid
        and work.choice == "keep_vault"
        and (
            selected.result is None
            or not same_content(selected.result, work.change.current)
        )
    ):
        valid = False
    memory = (
        next(
            (
                row
                for row in returned.source_version_memory
                if row.provenance.decision_id == work.action.decision_id
            ),
            None,
        )
        if valid
        else None
    )
    return CompletedWork(PreservedMemoryResult(work, memory))


def _consume_memory(result, plan, change, action, choice):
    if (
        type(result) is not PreservedMemoryResult
        or result.work.plan is not plan
        or result.work.change is not change
        or result.work.action is not action
        or result.work.choice != choice
        or result.work.phase != "finish"
    ):
        raise ValueError("Preservation memory belongs to different action inputs")
    return result.memory


@dataclass(frozen=True)
class ApprovalWork:
    plan: ReviewPlan
    action: ReviewAction
    change: object
    content: object
    dependencies: tuple
    source_accepted: bool
    memory_choice: str | None = None
    derive_plain: bool = False
    phase: str = "memory"
    group_defer: bool = False
    group_memory: object = None


def _plain_approval_values(plan, action, change):
    dependencies = change.assumptions + (
        ()
        if action.candidate is None
        else (_candidate_assumption(action.candidate, change, action.decision_id),)
    )
    content = (
        primary_reversal_content(
            reversal_subject(plan.producer_facts, change),
            reverse=True,
        )
        if action.choice == "reverse"
        else change.result
        if action.choice == "approve"
        else change.current
        if action.choice == "current"
        else action.candidate.content
    )
    return content, dependencies


def _approval_plan(
    plan, action, change, content, dependencies, source_accepted, memory, *, defer=False
):
    approval = ReviewApproval(
        schema_id="brz2obsidian.review-approval",
        schema_version=1,
        decision_id=action.decision_id,
        change_id=change.change_id,
        domain=action.domain,
        choice=action.choice,
        result=content,
        target_path=change.target_path,
        assumptions=dependencies,
        provenance="explicit_user",
        source_accepted=source_accepted,
        source_memory=memory,
        attachment_selection=action.attachment_selection,
        attachment_candidate=action.attachment_candidate,
    )
    if defer:
        return approval
    return PlanWork(
        plan.facts,
        plan.preflight,
        plan.actions + (action,),
        tuple(
            row
            for row in plan.approvals
            if (row.change_id, row.domain) != (change.change_id, action.domain)
        )
        + (approval,),
        plan.consents,
        producer_facts=plan.producer_facts,
        producer_applicability=plan.producer_applicability,
        attachment_applicability=plan.attachment_applicability,
        canonical_prior=plan,
    )


def advance_approval(work, returned=None):
    if (
        work.phase == "memory"
        and work.memory_choice is not None
        and not work.group_defer
    ):
        return ChildWork(
            PreservedMemoryWork(
                work.plan, work.change, work.action, work.memory_choice
            ),
            replace(work, phase="approved"),
        )
    if work.phase in ("memory", "approved"):
        memory = (
            None
            if work.phase == "memory"
            else _consume_memory(
                returned,
                work.plan,
                work.change,
                work.action,
                work.memory_choice,
            )
        )
        if work.phase == "approved" and memory is None:
            return CompletedWork(
                _transition(work.plan, "refused", "unsafe_producer_choice")
            )
        if work.group_defer:
            memory = work.group_memory
        content, dependencies = (
            _plain_approval_values(work.plan, work.action, work.change)
            if work.derive_plain
            else (work.content, work.dependencies)
        )
        updated = _approval_plan(
            work.plan,
            work.action,
            work.change,
            content,
            dependencies,
            work.source_accepted,
            memory,
            defer=work.group_defer,
        )
        if work.group_defer:
            return CompletedWork(updated)
        return ChildWork(updated, replace(work, phase="finish"))
    if work.phase == "finish":
        return CompletedWork(_transition(returned, "accepted", "accepted"))
    raise ValueError("Invalid approval phase")


@dataclass(frozen=True)
class ActionWork:
    plan: ReviewPlan
    action: ReviewAction
    epoch: int = 0
    phase: str = "resolve"
    status: str = "accepted"
    code: str = "accepted"


def advance_action(work, returned=None, context=None):
    if work.phase == "resolve" and isinstance(work.action, ReviewKeepCurrentGroup):
        return ChildWork(
            KeepCurrentWork(work.plan, work.action), replace(work, phase="append")
        )
    if work.phase == "resolve":
        result = _resolve_action(work.plan, work.action, _epoch=context.epoch)
        if type(result) is PlanTransition:
            return ChildWork(
                result.work,
                replace(work, phase="planned", status=result.status, code=result.code),
            )
        if type(result) in (AttachmentActionWork, ProducerActionWork, ApprovalWork):
            return ChildWork(result, replace(work, phase="append"))
        return CompletedWork(_append_action(work.plan, work.action, result))
    if work.phase == "planned":
        return CompletedWork(
            _append_action(
                work.plan, work.action, _transition(returned, work.status, work.code)
            )
        )
    if work.phase == "append":
        return CompletedWork(_append_action(work.plan, work.action, returned))
    raise ValueError("Invalid action phase")


@dataclass(frozen=True)
class AttachmentActionWork:
    plan: ReviewPlan
    action: ReviewAction
    change: object
    selection: object
    candidate: object
    epoch: int = 0
    phase: str = "validate"
    group_defer: bool = False
    memory: object = None
    pending: object = None


def advance_attachment_action(work, returned=None, context=None):
    plan, action, change = work.plan, work.action, work.change
    selection, candidate = work.selection, work.candidate
    if work.phase == "validate":
        return ChildWork(
            CandidateWork(
                plan.producer_facts,
                selection,
                candidate,
                canonical_proposal=plan.proposal if work.group_defer else None,
            ),
            replace(work, phase="validated"),
        )
    if work.phase == "validated":
        if not _candidate_validation(
            plan.producer_facts, selection, candidate, returned
        ).valid:
            return CompletedWork(_transition(plan, "refused", "attachment_invalid"))
        if (
            not work.group_defer
            and action.choice == "current"
            and plan.producer_facts.format_operation.kind == "source_update"
            and not (
                change.current is not None
                and change.incoming is not None
                and same_content(change.current, change.incoming)
            )
        ):
            return ChildWork(
                PreservedMemoryWork(plan, change, action, "keep_vault"),
                replace(work, phase="memory"),
            )
        return replace(
            work, phase="request", memory=work.memory if work.group_defer else None
        )
    if work.phase == "memory":
        memory = _consume_memory(returned, plan, change, action, "keep_vault")
        if memory is None:
            return CompletedWork(_transition(plan, "refused", "unsafe_producer_choice"))
        return replace(work, phase="request", memory=memory)
    if work.phase == "request":
        request = attachment_candidate_request(
            plan.producer_facts,
            change,
            selection,
            candidate,
            action.decision_id,
            prefix=plan.history,
            epoch=context.epoch,
            context=context,
        )
        return PendingFingerprint(
            request, replace(work, phase="approve", pending=request)
        )
    if work.phase == "approve":
        consume_fingerprint(work.pending, returned)
        memory = work.memory
        dependencies = change.assumptions + (
            attachment_candidate_assumption(
                plan.producer_facts,
                change,
                selection,
                candidate,
                action.decision_id,
                prefix=plan.history,
                epoch=work.pending.epoch,
                result=returned,
                request=work.pending,
            ),
        )
        content = (
            candidate.outputs[0].content
            if action.domain == "restoration" or len(candidate.outputs) == 1
            else None
        )
        updated = _approval_plan(
            plan,
            action,
            change,
            content,
            dependencies,
            action.choice not in ("current", "remove") and action.domain != "reversal",
            memory,
            defer=work.group_defer,
        )
        if work.group_defer:
            return CompletedWork(updated)
        return ChildWork(
            updated, replace(work, phase="finish", memory=None, pending=None)
        )
    if work.phase == "finish":
        return CompletedWork(_transition(returned, "accepted", "accepted"))
    raise ValueError("Invalid attachment action phase")


CONTENT_CONFLICT_DOMAINS = frozenset(
    {"text", "attachment", "mapping", "format", "configuration"}
)


def _current_conflict_safe(plan, change, domain):
    subject = next(
        s
        for s in plan.producer_facts.subjects
        if (s.item_id, s.facet) == (change.item_id, change.facet)
    )
    if (
        subject.structure is not None
        and domain in ("text", "mapping", "format", "configuration")
        and validate_structure_facts(
            subject,
            plan.producer_facts.baseline_identity,
            plan.producer_facts.incoming_identity,
            source_version=plan.producer_facts.format_operation.baseline_source_version,
            current_target_safety=True,
        )
        is not None
    ):
        return False
    return change.attachment_review is not None or selected_current_links_safe(
        plan.producer_facts, change
    )


def unresolved_current_scope(plan):
    """Describe current-capable unresolved content slots of an admitted plan."""
    requirements = {(r.change_id, r.domain) for r in plan.requirements}
    changes = {c.change_id: c for c in plan.proposal.changes}
    members = tuple(
        row
        for row in _inspect_canonical_choices(plan)
        if (row.change_id, row.domain) in requirements
        and row.domain in CONTENT_CONFLICT_DOMAINS
        and changes[row.change_id].disposition != "compatible"
        and "current" in row.enabled_choices
        and _current_conflict_safe(plan, changes[row.change_id], row.domain)
        and not any(
            f.blocking and f.subject_id in (None, changes[row.change_id].subject_id)
            for f in plan.proposal.findings
        )
    )
    digest = (
        sha256(
            json.dumps(
                [
                    (
                        r.change_id,
                        r.domain,
                        [(a.key, a.fingerprint) for a in r.assumptions],
                    )
                    for r in members
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        if members
        else None
    )
    return digest, members


@dataclass(frozen=True)
class KeepCurrentWork:
    plan: ReviewPlan
    event: ReviewKeepCurrentGroup
    phase: str = "validate"
    jobs: tuple = ()
    memory_facts: object = None
    memories: tuple = ()
    index: int = 0
    approvals: tuple = ()
    members: tuple = ()
    decision_ids: frozenset = frozenset()
    selected: object = None
    source_memories: object = None


def advance_keep_current(work, returned=None, context=None):
    plan, event = work.plan, work.event
    if work.phase == "validate":
        digest, members = unresolved_current_scope(plan)
        if digest != event.group_id or len(members) != len(event.actions):
            return CompletedWork(_transition(plan, "stale", "assumptions_changed"))
        if current_observation_problem(
            plan.producer_facts
        ) is not None or preflight_blockers(plan.facts, plan.preflight, plan.proposal):
            return CompletedWork(_transition(plan, "refused", "preflight_refused"))
        return replace(
            work,
            phase="validate_member",
            members=members,
            memory_facts=plan.producer_facts,
        )
    if work.phase == "validate_member":
        if work.index == len(work.members):
            if work.memory_facts is not plan.producer_facts:
                return ChildWork(
                    ReconcileWork(work.memory_facts, plan.producer_applicability),
                    replace(work, phase="memory", index=0),
                )
            return replace(work, phase="member", index=0)
        row, action = work.members[work.index], event.actions[work.index]
        if (
            action.change_id != row.change_id
            or action.domain != row.domain
            or action.choice != "current"
            or action.decision_id in work.decision_ids
        ):
            return CompletedWork(_transition(plan, "refused", "choice_not_admitted"))
        job = _resolve_action(plan, action, _epoch=context.epoch, _group_admitted=True)
        if type(job) not in (ApprovalWork, AttachmentActionWork):
            return CompletedWork(
                job
                if hasattr(job, "status")
                else _transition(plan, "refused", "choice_not_admitted")
            )
        memory_choice = (
            job.memory_choice
            if type(job) is ApprovalWork
            else (
                "keep_vault"
                if plan.producer_facts.format_operation.kind == "source_update"
                and not same_content(job.change.current, job.change.incoming)
                else None
            )
        )
        memory_facts = work.memory_facts
        if memory_choice is not None:
            memory_plan = plan.model_copy(update={"producer_facts": memory_facts})
            memory_facts = _preserved_memory_facts(
                memory_plan, job.change, action, memory_choice
            )
        return replace(
            work,
            jobs=work.jobs + ((job, memory_choice),),
            memory_facts=memory_facts,
            decision_ids=work.decision_ids | {action.decision_id},
            index=work.index + 1,
        )
    if work.phase == "memory":
        return replace(
            work,
            phase="memory_member",
            selected={c.subject_id: c for c in returned.changes},
            source_memories={
                m.provenance.decision_id: m for m in returned.source_version_memory
            },
        )
    if work.phase == "memory_member":
        if work.index == len(work.jobs):
            return replace(work, phase="member", index=0)
        job, choice = work.jobs[work.index]
        memory = None
        if choice is not None:
            change = work.selected[job.change.subject_id]
            memory = work.source_memories.get(job.action.decision_id)
            if (
                memory is None
                or change.requires_decision
                or change.disposition != "preserve_vault"
                or not same_content(change.result, job.change.current)
            ):
                return CompletedWork(
                    _transition(plan, "refused", "unsafe_producer_choice")
                )
        return replace(work, memories=work.memories + (memory,), index=work.index + 1)
    if work.phase == "member":
        if work.index == len(work.jobs):
            return ChildWork(
                PlanWork(
                    plan.facts,
                    plan.preflight,
                    plan.actions + event.actions,
                    plan.approvals + work.approvals,
                    plan.consents,
                    producer_facts=plan.producer_facts,
                    producer_applicability=plan.producer_applicability,
                    attachment_applicability=plan.attachment_applicability,
                    canonical_prior=plan,
                ),
                replace(work, phase="finish"),
            )
        job, _ = work.jobs[work.index]
        memory = work.memories[work.index] if work.memories else None
        job = replace(
            job,
            group_defer=True,
            **(
                {"group_memory": memory}
                if type(job) is ApprovalWork
                else {"memory": memory}
            ),
        )
        return ChildWork(job, replace(work, phase="collected"))
    if work.phase == "collected":
        if type(returned) is not ReviewApproval:
            return CompletedWork(returned)
        return replace(
            work,
            phase="member",
            index=work.index + 1,
            approvals=work.approvals + (returned,),
        )
    if work.phase == "finish":
        return CompletedWork(_transition(returned, "accepted", "accepted"))
    raise ValueError("Invalid keep-current group phase")
