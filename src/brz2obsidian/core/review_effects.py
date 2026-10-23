"""Derive effective selected files and check cross-choice link coherence."""

from brz2obsidian.contracts import LinkTargetFacts
from brz2obsidian.core.link_meanings import resolve_occurrence
from brz2obsidian.core.link_validation import validate_link_document
from brz2obsidian.core.review_links import (
    bound_resource_record,
    current_baseline,
    current_keep_needs_proof,
    current_lookup_coverage,
    known_result_document,
)


def selected_effect_blockers(facts, proposal, actions, approvals):
    context = facts.link_context
    if context is None:
        return (
            ("current_link_coverage_unavailable",)
            if (
                selected_effect_active(facts, proposal, approvals)
                or any(
                    c.provenance.rule == "remembered_keep"
                    and current_keep_needs_proof(facts, c)
                    for c in proposal.changes
                )
            )
            else ()
        )
    targets = {t.target_id: t for t in context.current_targets}
    states = {s.target_id: s for s in context.current_target_facts}
    documents = {d.document_id: d for d in context.current_documents}
    original_documents = dict(documents)
    approved = {a.change_id: a for a in approvals}
    action_by_id = {a.decision_id: a for a in actions}
    writes = {}
    proof_documents = {}
    explicit_documents = set()
    changed_ids = set()
    blockers = []

    def add(code):
        if code not in blockers:
            blockers.append(code)

    if any(
        c.provenance.rule == "remembered_keep" and current_keep_needs_proof(facts, c)
        for c in proposal.changes
    ) and not current_lookup_coverage(facts):
        add("current_link_coverage_unavailable")

    def write(target, content, path, state):
        previous = writes.get(target.target_id)
        if previous is not None and previous != (content, path):
            add("selected_output_conflict")
            return
        writes[target.target_id] = (content, path)
        current = targets.get(target.target_id)
        old_state = states.get(target.target_id)
        if current != target or old_state != state:
            changed_ids.add(target.target_id)
        targets[target.target_id] = target
        if state is None or state.content != content:
            states.pop(target.target_id, None)
        else:
            states[target.target_id] = state

    # An approved reversal changes existence in the same selected graph as bytes.
    # Retain the target's lookup identity so inbound references resolve missing.
    for change in proposal.changes:
        approval = approved.get(change.change_id)
        if (
            approval is None
            or approval.choice != "reverse"
            or approval.result is not None
        ):
            continue
        own = tuple(
            t for t in context.current_targets if t.canonical_path == change.path
        )
        if len(own) != 1:
            add("selected_link_context_conflict")
            continue
        (target,) = own
        state = LinkTargetFacts(
            schema_id="brz2obsidian.link-target-facts",
            schema_version=1,
            target_id=target.target_id,
            existence="missing",
            content=None,
            fragments=(),
            anchors=(),
            structure=None,
            memberships=(),
            interpretation="supported",
        )
        write(target, None, change.path, state)
        documents = {
            key: document
            for key, document in documents.items()
            if document.source_path != change.path
        }

    # Binary selections establish exact offered output versions first.
    for approval in approvals:
        candidate = approval.attachment_candidate
        if candidate is None:
            continue
        for output in candidate.outputs:
            target = next(
                t for t in candidate.targets if t.target_id == output.target_id
            )
            state = next(
                (s for s in candidate.target_facts if s.target_id == output.target_id),
                None,
            )
            write(target, output.content, output.path, state)
        for document in candidate.documents:
            prior = original_documents.get(document.document_id)
            if prior is None or (prior.content, prior.source_path) != (
                document.content,
                document.source_path,
            ):
                matching = tuple(
                    t
                    for t in candidate.targets
                    if t.canonical_path == document.source_path
                )
                if len(matching) != 1:
                    add("selected_output_conflict")
                    continue
                target = matching[0]
                state = next(
                    (
                        s
                        for s in candidate.target_facts
                        if s.target_id == target.target_id
                    ),
                    None,
                )
                write(target, document.content, document.source_path, state)
                explicit_documents.add(document.document_id)
            proof_documents[document.document_id] = document
    documents.update(proof_documents)

    for change in proposal.changes:
        approval = approved.get(change.change_id)
        if approval is not None and approval.attachment_candidate is not None:
            continue
        content = change.result if approval is None else approval.result
        if content is None:
            continue
        subject = next(
            s
            for s in facts.subjects
            if (s.item_id, s.facet) == (change.item_id, change.facet)
        )
        if subject.attachment is not None:
            continue
        selected_path = change.target_path if approval is None else approval.target_path
        action = None if approval is None else action_by_id.get(approval.decision_id)
        candidate = None if action is None else action.candidate
        known = (
            known_result_document(facts, change)
            if approval is None or approval.choice == "approve"
            else None
        )
        if candidate is not None:
            document = candidate.links
            source_targets = candidate.link_targets
            source_states = candidate.link_target_facts
        elif known is not None:
            document, source_targets, source_states = known
        else:
            matching = tuple(
                d
                for d in context.current_documents
                if d.content == content and d.source_path == selected_path
            )
            document = matching[0] if len(matching) == 1 else None
            source_targets = context.current_targets
            source_states = context.current_target_facts
        own = tuple(
            t
            for t in context.current_targets
            if t.canonical_path == subject.current.path
        )
        if len(own) == 1:
            target = own[0]
            if selected_path != target.canonical_path:
                supplied = tuple(
                    t
                    for t in source_targets
                    if t.target_id == target.target_id
                    and t.canonical_path == selected_path
                )
                if len(supplied) != 1:
                    add("selected_link_context_conflict")
                    continue
                target = supplied[0]
            state = next(
                (
                    s
                    for s in source_states
                    if s.target_id == target.target_id and s.content == content
                ),
                None,
            )
            # Exact target-state evidence can come from either interpreted comparison version.
            if state is None:
                state = next(
                    (
                        s
                        for s in context.current_target_facts
                        + context.incoming_target_facts
                        if s.target_id == target.target_id and s.content == content
                    ),
                    None,
                )
            write(target, content, selected_path, state)
        if document is None:
            if (
                any(
                    d.source_path == subject.current.path
                    for d in context.current_documents
                )
                or change.requires_decision
            ):
                add("selected_link_context_conflict")
            continue
        if document.source_path != selected_path or document.content != content:
            add("selected_link_context_conflict")
            continue
        existing = documents.get(document.document_id)
        if (
            document.document_id in explicit_documents
            and existing is not None
            and (existing.content, existing.source_path) != (content, selected_path)
        ):
            add("selected_output_conflict")
        documents[document.document_id] = document
        if approval is not None or change.provenance.rule == "remembered_keep":
            explicit_documents.add(document.document_id)

    if (
        changed_ids or selected_effect_active(facts, proposal, approvals)
    ) and not current_note_coverage(facts):
        add("current_link_coverage_unavailable")

    final_targets = tuple(targets.values())
    final_states = tuple(states.values())
    for document in documents.values():
        prior = original_documents.get(document.document_id)
        relevant = (
            document.document_id in explicit_documents
            or document.document_id in proof_documents
        )
        resolved = tuple(
            resolve_occurrence(o, final_targets, final_states, context.inventory)
            for o in document.occurrences
        )
        relevant |= any(
            m.target_id in changed_ids or bool(set(m.candidates) & changed_ids)
            for m in resolved
        )
        relevant |= any(
            o.meaning.target_id in changed_ids
            or bool(set(o.meaning.candidates) & changed_ids)
            for o in document.occurrences
        )
        if not relevant:
            continue
        if (
            document.document_id not in explicit_documents
            and document.document_id not in proof_documents
        ):
            # A retained note's unrelated prose version is not a link redirect. Resource choices
            # and path/identity/fragment changes still require their explicit selected proof.
            occurrences = []
            for occurrence, actual in zip(document.occurrences, resolved, strict=True):
                target = targets.get(actual.target_id)
                if (
                    target is not None
                    and target.kind != "resource"
                    and occurrence.meaning.model_copy(
                        update={"target_version": actual.target_version}
                    )
                    == actual
                ):
                    occurrence = occurrence.model_copy(update={"meaning": actual})
                occurrences.append(occurrence)
            document = document.model_copy(update={"occurrences": tuple(occurrences)})
        validation = validate_link_document(
            document,
            expected_content=document.content,
            expected_path=document.source_path,
            targets=final_targets,
            target_facts=final_states,
            inventory=context.inventory,
            baseline=None
            if prior is None or prior.source_path != document.source_path
            else current_baseline(context, document),
            affected_target_ids=tuple(
                changed_ids
                | (
                    {m.target_id for m in resolved if m.target_id is not None}
                    if document.document_id in explicit_documents
                    else set()
                )
            ),
        )
        if not validation.valid:
            add("selected_link_context_conflict")
    return tuple(blockers)


def current_note_coverage(facts):
    """An omitted registry entry cannot hide an independently observed potential note."""
    context = facts.link_context
    if not current_lookup_coverage(facts):
        return False
    for entry in facts.identity_inventory:
        if entry.current.existence == "unknown":
            return False
        if entry.current.existence == "absent":
            continue
        resources = tuple(
            t
            for t in context.current_targets
            if t.kind == "resource" and t.canonical_path == entry.current.path
        )
        resource = False
        if len(resources) == 1:
            (target,) = resources
            states = tuple(
                s
                for s in context.current_target_facts
                if s.target_id == target.target_id
            )
            resource = len(states) == 1 and bound_resource_record(
                facts, entry, target, states[0]
            )
        if resource:
            continue
        documents = tuple(
            d
            for d in context.current_documents
            if d.source_path == entry.current.path
            and d.content == entry.current.content
        )
        if (
            len(documents) != 1
            or documents[0].status != "supported"
            or documents[0].inventory != "complete"
        ):
            return False
    return True


def selected_effect_active(facts, proposal, approvals):
    approved = {a.change_id: a for a in approvals}
    for change in proposal.changes:
        approval = approved.get(change.change_id)
        if approval is not None and approval.choice == "reverse":
            return True
        if approval is not None and approval.attachment_candidate is not None:
            if any(
                not any(
                    e.current.path == o.path and e.current.content == o.content
                    for e in facts.identity_inventory
                )
                for o in approval.attachment_candidate.outputs
            ):
                return True
            continue
        content = change.result if approval is None else approval.result
        if content is None:
            continue
        subject = next(
            s
            for s in facts.subjects
            if (s.item_id, s.facet) == (change.item_id, change.facet)
        )
        path = change.target_path if approval is None else approval.target_path
        if path != subject.current.path or content != subject.current.content:
            return True
        if (
            approval is not None
            and approval.domain in ("mapping", "format")
            and approval.choice in ("incoming", "edited", "approve")
        ):
            return True
    return False
