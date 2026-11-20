"""Dependency-scoped immutable refresh; no observation, parsing or new consent."""

from dataclasses import dataclass, replace

from brz2obsidian.content_fingerprints import ChildWork, CompletedWork, drive_inline
from brz2obsidian.content_values import require_inline
from brz2obsidian.contracts import (
    ReconciliationInput,
    ReviewAction,
    ReviewAttachmentApplicability,
    ReviewKeepCurrentGroup,
    ReviewPreflight,
    ReviewProducerApplicability,
    ReviewRefreshEvent,
    ReviewRetention,
)

from .attachment_validation import CandidateWork
from .resolution import PlanWork, _transition, validate_review
from .reversals import (
    content_bytes,
    primary_reversal_content,
    reversal_subject,
    reversal_text_comparison,
)
from .review_attachments import retained_attachment_inputs
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
    if (
        approval.choice == "reverse"
        and approval.attachment_candidate is None
        and origin.candidate is None
    ):
        subject = reversal_subject(facts, change)
        return (
            approval.domain == "reversal"
            and change.disposition == "operation_reversal"
            and subject.operation_reversal is not None
            and content_bytes(approval.result)
            == content_bytes(primary_reversal_content(subject, reverse=True))
            and not any(
                r.target is not None
                and content_bytes(r.target) != content_bytes(r.current.content)
                for r in subject.operation_reversal.outputs
            )
            and change.target_path == approval.target_path
        )
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
            reversal_text_comparison(facts, change)
            if approval.domain == "reversal"
            else change,
            origin.candidate,
            "incoming"
            if approval.domain == "reversal" and approval.choice == "reverse"
            else approval.choice,
            mapping_choice=approval.domain == "mapping",
        )
    if approval.choice == "current":
        return selected_current_links_safe(facts, change)
    return (
        approval.choice == "approve"
        and change.result == approval.result
        and change.target_path == approval.target_path
    )


@dataclass(frozen=True)
class AttachmentViewsWork:
    plan: object
    facts: object
    approvals: tuple
    index: int = 0
    history_index: int = 0
    original: object = None
    phase: str = "approval"
    view: object = None
    results: tuple = ()


def advance_attachment_views(work, returned=None):
    if work.index == len(work.approvals):
        return CompletedWork(work.results)
    approval = work.approvals[work.index]
    if work.phase == "approval":
        if approval.attachment_candidate is None:
            return replace(work, index=work.index + 1)
        return replace(
            work,
            phase="origin",
            original=work.plan.history.initial_facts,
            history_index=0,
        )
    if work.phase == "origin":
        if work.history_index == len(work.plan.history.events):
            return replace(work, phase="view")
        event = work.plan.history.events[work.history_index]
        if (
            isinstance(event, ReviewAction)
            and event.decision_id == approval.decision_id
            or isinstance(event, ReviewKeepCurrentGroup)
            and any(a.decision_id == approval.decision_id for a in event.actions)
        ):
            return replace(work, phase="view")
        return replace(
            work,
            history_index=work.history_index + 1,
            original=event.facts
            if isinstance(event, ReviewRefreshEvent)
            else work.original,
        )
    if work.phase == "view":
        inputs = retained_attachment_inputs(
            work.facts,
            approval.attachment_selection,
            approval.attachment_candidate,
            work.original,
        )
        if inputs is None:
            return replace(work, phase="approval", index=work.index + 1, original=None)
        observed_epoch, view = inputs
        return ChildWork(
            CandidateWork(observed_epoch, approval.attachment_selection, view),
            replace(work, phase="validated", view=view),
        )
    if work.phase == "validated":
        results = work.results
        if returned.validation.valid:
            results += (
                ReviewAttachmentApplicability(
                    schema_id="brz2obsidian.review-attachment-applicability",
                    schema_version=1,
                    decision_id=approval.decision_id,
                    generation=work.facts.generation,
                    candidate=work.view,
                ),
            )
        return replace(
            work,
            phase="approval",
            index=work.index + 1,
            original=None,
            view=None,
            results=results,
        )
    raise ValueError("Unknown attachment retention phase")


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


@dataclass(frozen=True)
class ClosureWork:
    nodes: tuple
    invalidated: frozenset
    index: int = 0
    added: frozenset = frozenset()


def advance_closure(work, returned=None):
    if returned is not None:
        raise ValueError("Unexpected closure return")
    if work.index == len(work.nodes):
        if not work.added:
            return CompletedWork(work.invalidated)
        return replace(
            work, index=0, invalidated=work.invalidated | work.added, added=frozenset()
        )
    node = work.nodes[work.index]
    added = work.added
    if node.key not in work.invalidated and any(
        key in work.invalidated for key in node.depends_on
    ):
        added = added | {node.key}
    return replace(work, index=work.index + 1, added=added)


@dataclass(frozen=True)
class RefreshWork:
    plan: object
    facts: ReconciliationInput
    preflight: ReviewPreflight
    phase: str = "initial"
    producer_facts: object = None
    applicability: tuple = ()
    attachment_applicability: tuple = ()
    retained: tuple = ()
    old: tuple = ()
    new: tuple = ()
    tentative: object = None
    changed: frozenset = frozenset()
    invalidated: frozenset = frozenset()
    closure_start: frozenset = frozenset()
    bindings: tuple = ()
    event: object = None
    consents: tuple = ()


def _refresh(plan, facts, preflight):
    return drive_inline(RefreshWork(plan, facts, preflight))


def advance_refresh(work, returned=None):
    plan, facts, preflight = work.plan, work.facts, work.preflight
    if work.phase == "initial":
        if facts.proposal_id != plan.proposal.proposal_id:
            return CompletedWork(_transition(plan, "refused", "wrong_proposal"))
        if facts.generation != plan.proposal.generation + 1:
            return CompletedWork(_transition(plan, "stale", "generation_changed"))
        return ChildWork(
            PlanWork(facts, preflight, actions=plan.actions),
            replace(work, phase="producer"),
        )
    if work.phase == "producer":
        try:
            producer, applicability = _producer_choices(plan, facts, returned)
        except ValueError:
            return CompletedWork(_transition(plan, "refused", "choice_not_admitted"))
        return ChildWork(
            PlanWork(
                facts,
                preflight,
                actions=plan.actions,
                producer_facts=producer,
                producer_applicability=applicability,
            ),
            replace(
                work,
                phase="fresh",
                producer_facts=producer,
                applicability=applicability,
            ),
        )
    if work.phase == "fresh":
        current_ids = {change.change_id for change in returned.proposal.changes}
        retained = tuple(a for a in plan.approvals if a.change_id in current_ids)
        try:
            old = review_dependencies(plan)
        except ValueError:
            return CompletedWork(
                _transition(plan, "refused", "dependency_graph_invalid")
            )
        return replace(
            work, phase="iteration", retained=retained, old=tuple(old.values())
        )
    if work.phase == "iteration":
        return ChildWork(
            AttachmentViewsWork(plan, work.producer_facts, work.retained),
            replace(work, phase="views"),
        )
    if work.phase == "views":
        views = returned
        return ChildWork(
            PlanWork(
                facts,
                preflight,
                actions=plan.actions,
                approvals=work.retained,
                consents=plan.consents,
                producer_facts=work.producer_facts,
                producer_applicability=work.applicability,
                attachment_applicability=views,
            ),
            replace(work, phase="dependencies", attachment_applicability=views),
        )
    if work.phase == "dependencies":
        try:
            new = review_dependencies(returned)
        except ValueError:
            return CompletedWork(
                _transition(plan, "refused", "dependency_graph_invalid")
            )
        old = {node.key: node for node in work.old}
        changed = frozenset(
            key for key in old.keys() | new.keys() if old.get(key) != new.get(key)
        )
        return ChildWork(
            ClosureWork(work.old, changed),
            replace(
                work,
                phase="close_old",
                tentative=returned,
                new=tuple(new.values()),
                changed=changed,
            ),
        )
    if work.phase == "close_old":
        return ChildWork(
            ClosureWork(work.old, returned),
            replace(work, phase="close_new", closure_start=returned),
        )
    if work.phase == "close_new":
        return ChildWork(
            ClosureWork(work.new, returned), replace(work, phase="closure_result")
        )
    if work.phase == "closure_result":
        if returned != work.closure_start:
            return ChildWork(
                ClosureWork(work.old, returned),
                replace(work, phase="close_new", closure_start=returned),
            )
        return replace(work, phase="retention", invalidated=returned)
    if work.phase == "retention":
        invalidated = work.invalidated
        applicability = tuple(
            b
            for b in work.applicability
            if not (
                {a.key for a in b.reviewed_assumptions}
                | {"producer-choice:" + b.original.decision_id}
            )
            & invalidated
        )
        current = {
            change.subject_id: change for change in work.tentative.proposal.changes
        }
        old_changes = {change.change_id: change for change in plan.proposal.changes}
        surviving = []
        try:
            for approval in work.retained:
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
                        work.producer_facts,
                        after,
                        approval,
                        origin,
                        work.attachment_applicability,
                    )
                ):
                    surviving.append(approval)
        except ValueError:
            return CompletedWork(
                _transition(plan, "refused", "dependency_graph_invalid")
            )
        if tuple(surviving) != work.retained or applicability != work.applicability:
            originals = tuple(binding.original for binding in applicability)
            producer = work.producer_facts.model_copy(
                update={
                    "association_decisions": tuple(
                        d
                        for d in work.producer_facts.association_decisions
                        if d in originals
                    ),
                    "rename_decisions": tuple(
                        d
                        for d in work.producer_facts.rename_decisions
                        if d in originals
                    ),
                }
            )
            return replace(
                work,
                phase="iteration",
                retained=tuple(surviving),
                applicability=applicability,
                producer_facts=producer,
            )
        bindings = []
        for approval in work.retained:
            before = old_changes[approval.change_id]
            origin = next(
                a for a in plan.actions if a.decision_id == approval.decision_id
            )
            keys = {a.key for a in approval.assumptions} | {
                "effect:" + before.subject_id
            }
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
        return ChildWork(
            PlanWork(
                facts,
                preflight,
                actions=plan.actions,
                approvals=work.retained,
                producer_facts=work.producer_facts,
                producer_applicability=work.applicability,
                attachment_applicability=work.attachment_applicability,
            ),
            replace(work, phase="consents", bindings=tuple(bindings)),
        )
    if work.phase == "consents":
        consent_nodes = {
            r.change_id: r.assumptions
            for r in consent_requirements(
                preflight, returned.proposal, returned.approvals
            )
        }
        consents = tuple(
            c
            for c in plan.consents
            if "consent:" + c.consent_id not in work.invalidated
            and consent_nodes.get("consent:" + c.consent_id) == c.assumptions
        )
        old, new = (
            {node.key: node for node in work.old},
            {node.key: node for node in work.new},
        )
        event = ReviewRefreshEvent(
            schema_id="brz2obsidian.review-refresh-event",
            schema_version=1,
            expected_generation=plan.proposal.generation,
            facts=facts,
            preflight=preflight,
            previous_dependencies=tuple(old[key] for key in sorted(old)),
            dependencies=tuple(new[key] for key in sorted(new)),
            changed_keys=tuple(sorted(work.changed)),
            invalidated_keys=tuple(sorted(work.invalidated)),
            retained=work.bindings,
            producer_applicability=work.applicability,
            attachment_applicability=work.attachment_applicability,
        )
        return ChildWork(
            PlanWork(
                facts,
                preflight,
                actions=plan.actions,
                approvals=work.retained,
                consents=consents,
                producer_facts=work.producer_facts,
                producer_applicability=work.applicability,
                attachment_applicability=work.attachment_applicability,
            ),
            replace(work, phase="finish", event=event),
        )
    if work.phase == "finish":
        updated = returned.model_copy(
            update={
                "history": plan.history.model_copy(
                    update={"events": plan.history.events + (work.event,)}
                )
            }
        )
        return CompletedWork(_transition(updated, "accepted", "accepted"))
    raise ValueError("Unknown refresh phase")


def refresh_review(plan, facts, *, preflight):
    validated = validate_review(plan)
    if validated.status != "accepted":
        return validated
    facts = ReconciliationInput.model_validate(facts)
    preflight = ReviewPreflight.model_validate(preflight)
    require_inline((facts, preflight))
    return _refresh(validated.plan, facts, preflight)
