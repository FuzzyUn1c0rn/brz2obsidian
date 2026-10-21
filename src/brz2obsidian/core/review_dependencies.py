"""Actual producer, candidate and selected-effect dependency facts; no observation."""

import json
from hashlib import sha256

from brz2obsidian.contracts import ProposalAssumption, ReviewDependencyNode

from .dependency_graph import validate_dependencies
from .link_meanings import _semantic, resolve_occurrence
from .review_attachments import applicable_approvals
from .review_effects import current_note_coverage
from .review_links import consumed_context
from .review_preflight import consent_requirements


def digest(value):
    return sha256(json.dumps(_semantic(value), sort_keys=True).encode()).hexdigest()


def review_dependencies(plan):
    nodes = {}

    def add(node, producer):
        value = ReviewDependencyNode(
            **node.model_dump(),
            producer=producer,
            schema_id="brz2obsidian.review-dependency-node",
            schema_version=1,
        )
        if node.key in nodes and nodes[node.key] != value:
            raise ValueError("Conflicting dependency definitions")
        nodes[node.key] = value

    def derived(key, kind, value, dependencies, producer):
        add(
            ProposalAssumption(
                key=key,
                kind=kind,
                fingerprint=digest(value),
                depends_on=tuple(sorted(set(dependencies))),
            ),
            producer,
        )

    approved = {
        a.change_id: a
        for a in applicable_approvals(plan.approvals, plan.attachment_applicability)
    }
    actions = {a.decision_id: a for a in plan.actions}
    context = plan.producer_facts.link_context
    state_key = "review:state"
    derived(
        state_key,
        "history",
        (
            plan.preflight.operation_status,
            plan.preflight.state_status,
            plan.preflight.state_schema,
            plan.preflight.state_version,
            plan.preflight.state_fingerprint,
        ),
        (),
        "coverage",
    )
    selected = {}
    for change in plan.proposal.changes:
        for node in change.assumptions:
            add(node, "producer")
        approval = approved.get(change.change_id)
        extra = (
            ()
            if approval is None
            else tuple(a for a in approval.assumptions if a not in change.assumptions)
        )
        for node in extra:
            add(node, "candidate")
        content = change.result if approval is None else approval.result
        path = change.target_path if approval is None else approval.target_path
        producer_keys = []
        for decision in (
            plan.producer_facts.association_decisions
            + plan.producer_facts.rename_decisions
        ):
            if (decision.item_id, decision.facet) == (change.item_id, change.facet):
                decision_key = "producer-choice:" + decision.decision_id
                derived(
                    decision_key,
                    "identity" if hasattr(decision, "selected_entry_id") else "target",
                    decision,
                    tuple(a.key for a in decision.reviewed_assumptions) + (state_key,),
                    "selected",
                )
                producer_keys.append(decision_key)
        key = "selected:" + change.subject_id
        selected[change.subject_id] = key
        derived(
            key,
            "content",
            (path, content),
            tuple(a.key for a in change.assumptions) + tuple(producer_keys),
            "selected",
        )
    coverage = "review:lookup-coverage"
    derived(
        coverage,
        "inventory",
        (
            plan.producer_facts.inventory,
            None
            if context is None
            else (context.inventory, current_note_coverage(plan.producer_facts)),
        ),
        (),
        "coverage",
    )
    for change in plan.proposal.changes:
        approval = approved.get(change.change_id)
        action = None if approval is None else actions.get(approval.decision_id)
        documents = ()
        inbound = []
        target_ids = set()
        if context is not None:
            own = {
                t.target_id
                for t in context.current_targets + context.incoming_targets
                if t.canonical_path in (change.path, change.target_path)
            }
            for doc in context.current_documents:
                occurrences = tuple(
                    o
                    for o in doc.occurrences
                    if any(
                        resolve_occurrence(
                            o, (t,), context.current_target_facts, context.inventory
                        ).target_id
                        in own
                        for t in context.current_targets
                    )
                )
                if occurrences:
                    inbound.append(
                        (
                            doc.document_id,
                            doc.source_path,
                            tuple(
                                (
                                    o.query,
                                    o.meaning,
                                    resolve_occurrence(
                                        o,
                                        context.current_targets,
                                        context.current_target_facts,
                                        context.inventory,
                                    ),
                                )
                                for o in occurrences
                            ),
                        )
                    )
            if action is not None and action.candidate is not None:
                documents = (action.candidate.links,)
            elif approval is not None and approval.attachment_candidate is not None:
                documents = tuple(
                    d
                    for d in approval.attachment_candidate.documents
                    if d.document_id
                    in {r.document_id for r in change.attachment_review.links}
                    | {
                        c.document_id
                        for c in approval.attachment_selection.link_choices
                    }
                )
            else:
                documents = tuple(
                    d
                    for d in context.current_documents + context.incoming_documents
                    if d.source_path in (change.path, change.target_path)
                )
            portions = tuple(
                consumed_context(documents, targets, states, context.inventory)
                for targets, states in (
                    (context.current_targets, context.current_target_facts),
                    (context.incoming_targets, context.incoming_target_facts),
                )
            )
            target_ids = {t.target_id for portion in portions for t in portion[2]}
        else:
            portions = ()
        dependencies = {a.key for a in change.assumptions}
        if approval is not None:
            dependencies.update(a.key for a in approval.assumptions)
        if context is not None:
            for other in plan.proposal.changes:
                if any(
                    t.target_id in target_ids
                    and t.canonical_path in (other.path, other.target_path)
                    for t in context.current_targets + context.incoming_targets
                ):
                    dependencies.add(selected[other.subject_id])
        dependencies.update((coverage, state_key))
        derived(
            "effect:" + change.subject_id,
            "candidate",
            (portions, inbound),
            dependencies,
            "effect",
        )
    for requirement in consent_requirements(
        plan.preflight, plan.proposal, plan.approvals
    ):
        for node in requirement.assumptions:
            scope = next(
                c
                for c in plan.preflight.consents
                if "consent:" + c.consent_id == node.key
            )
            extra = tuple(
                "effect:" + c.subject_id
                for c in plan.proposal.changes
                if requirement.domain == "storage"
                and (not scope.subjects or c.subject_id in scope.subjects)
            )
            add(
                node.model_copy(
                    update={
                        "depends_on": tuple(
                            sorted(set(node.depends_on + extra + (state_key,)))
                        )
                    }
                ),
                "consent",
            )
    for group in plan.groups:
        for node in group.assumptions:
            add(node, "group")
    validate_dependencies(nodes)
    return nodes
