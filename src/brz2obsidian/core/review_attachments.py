"""Scoped immutable evidence for an admitted exact binary/link choice."""

from brz2obsidian.content_fingerprints import (
    consume_fingerprint,
    fingerprint_request,
    inline_fingerprint,
)
from brz2obsidian.content_values import same_content
from brz2obsidian.contracts import ProposalAssumption
from brz2obsidian.core.attachment_validation import _validate_attachment_candidate


def _selected_target_ids(facts, selection, candidate):
    target_ids = {o.target_id for o in candidate.outputs}
    if (
        facts.format_operation.kind == "attachment_cleanup"
        and selection.choice == "remove"
    ):
        subject = next(
            s
            for s in facts.subjects
            if (s.item_id, s.facet) == (selection.item_id, selection.facet)
        )
        target_ids.add(subject.attachment.current_target_id)
    return target_ids


def attachment_candidate_request(
    facts,
    change,
    selection,
    candidate,
    decision_id,
    *,
    prefix=(),
    epoch=0,
    context=None,
):
    current = {d.document_id: d for d in facts.link_context.current_documents}
    relevant = {r.document_id for r in change.attachment_review.links} | {
        c.document_id for c in selection.link_choices
    }
    documents = tuple(
        d
        for d in candidate.documents
        if d.document_id in relevant
        or d.document_id not in current
        or not same_content(d.content, current[d.document_id].content)
    )
    target_ids = _selected_target_ids(facts, selection, candidate)
    target_ids.update(
        t
        for d in documents
        for o in d.occurrences
        for t in (o.meaning.target_id, *o.meaning.candidates)
        if t is not None
    )
    payload = {
        "selection": selection,
        "outputs": candidate.outputs,
        "documents": documents,
        "targets": [t for t in candidate.targets if t.target_id in target_ids],
        "target_facts": [
            t for t in candidate.target_facts if t.target_id in target_ids
        ],
    }
    return fingerprint_request(
        payload,
        dialect="Js",
        scope=(
            "attachment-candidate",
            facts.proposal_id,
            facts.generation,
            change.subject_id,
            decision_id,
            prefix,
        ),
        epoch=epoch,
        context=context,
    )


def attachment_candidate_assumption(
    facts,
    change,
    selection,
    candidate,
    decision_id,
    *,
    prefix=(),
    epoch=0,
    result=None,
    request=None,
):
    if request is None:
        if result is not None:
            raise ValueError(
                "A supplied fingerprint result requires its exact issued request"
            )
        request = attachment_candidate_request(
            facts,
            change,
            selection,
            candidate,
            decision_id,
            prefix=prefix,
            epoch=epoch,
        )
    result = inline_fingerprint(request) if result is None else result
    return ProposalAssumption(
        key="review-attachment:" + decision_id,
        kind="candidate",
        fingerprint=consume_fingerprint(request, result),
        depends_on=tuple(a.key for a in change.assumptions),
    )


def _attachment_selection_matches(facts, change, action, choice):
    selection, candidate = action.attachment_selection, action.attachment_candidate
    return (
        selection is not None
        and candidate is not None
        and action.candidate is None
        and selection.choice == choice
        and (
            selection.proposal_id,
            selection.generation,
            selection.item_id,
            selection.facet,
            selection.reviewed_change_id,
            selection.reviewed_assumptions,
        )
        == (
            action.proposal_id,
            action.expected_generation,
            change.item_id,
            change.facet,
            change.change_id,
            action.reviewed_assumptions,
        )
    )


def attachment_selection_valid(facts, change, action, choice):
    return (
        _attachment_selection_matches(facts, change, action, choice)
        and _validate_attachment_candidate(
            facts,
            action.attachment_selection,
            action.attachment_candidate,
        ).valid
    )


def applicable_approvals(approvals, applicability):
    views = {a.decision_id: a.candidate for a in applicability}
    return tuple(
        a.model_copy(update={"attachment_candidate": views[a.decision_id]})
        if a.decision_id in views
        else a
        for a in approvals
    )


def retained_attachment_inputs(facts, selection, candidate, original_facts):
    """Rebind unrelated proof observations without changing originally selected writes."""
    from .review_effects import current_note_coverage
    from .review_links import current_observation_problem

    context = facts.link_context
    original = original_facts.link_context
    if (
        context is None
        or original is None
        or not current_note_coverage(facts)
        or current_observation_problem(facts) is not None
    ):
        return None
    old_documents = {d.document_id: d for d in original.current_documents}
    writes = {
        d.document_id: d
        for d in candidate.documents
        if d.document_id not in old_documents
        or d.content != old_documents[d.document_id].content
        or d.source_path != old_documents[d.document_id].source_path
    }
    if not set(writes) <= {d.document_id for d in context.current_documents}:
        return None
    outputs = _selected_target_ids(facts, selection, candidate)
    document_paths = {d.source_path for d in writes.values()}
    selected_ids = outputs | {
        t.target_id for t in candidate.targets if t.canonical_path in document_paths
    }
    targets = tuple(
        t for t in context.current_targets if t.target_id not in outputs
    ) + tuple(t for t in candidate.targets if t.target_id in outputs)
    states = tuple(
        s for s in context.current_target_facts if s.target_id not in selected_ids
    ) + tuple(s for s in candidate.target_facts if s.target_id in selected_ids)
    documents = tuple(writes.get(d.document_id, d) for d in context.current_documents)
    view = candidate.model_copy(
        update={"targets": targets, "target_facts": states, "documents": documents}
    )
    observed_epoch = facts.model_copy(update={"generation": selection.generation})
    return observed_epoch, view


def retained_attachment_view(facts, selection, candidate, original_facts):
    inputs = retained_attachment_inputs(facts, selection, candidate, original_facts)
    if inputs is None:
        return None
    observed_epoch, view = inputs
    return (
        view
        if _validate_attachment_candidate(observed_epoch, selection, view).valid
        else None
    )
