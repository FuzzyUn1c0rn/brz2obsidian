"""Scoped immutable evidence for an admitted exact binary/link choice."""

import json
from hashlib import sha256

from brz2obsidian.contracts import ProposalAssumption
from brz2obsidian.core.attachment_validation import validate_attachment_candidate


def attachment_candidate_assumption(facts, change, selection, candidate, decision_id):
    current = {d.document_id: d for d in facts.link_context.current_documents}
    relevant = {r.document_id for r in change.attachment_review.links} | {
        c.document_id for c in selection.link_choices
    }
    documents = tuple(
        d
        for d in candidate.documents
        if d.document_id in relevant
        or d.document_id not in current
        or d.content.data != current[d.document_id].content.data
    )
    target_ids = {o.target_id for o in candidate.outputs}
    target_ids.update(
        t
        for d in documents
        for o in d.occurrences
        for t in (o.meaning.target_id, *o.meaning.candidates)
        if t is not None
    )
    payload = {
        "selection": selection.model_dump(mode="json"),
        "outputs": [o.model_dump(mode="json") for o in candidate.outputs],
        "documents": [d.model_dump(mode="json") for d in documents],
        "targets": [
            t.model_dump(mode="json")
            for t in candidate.targets
            if t.target_id in target_ids
        ],
        "target_facts": [
            t.model_dump(mode="json")
            for t in candidate.target_facts
            if t.target_id in target_ids
        ],
    }
    return ProposalAssumption(
        key="review-attachment:" + decision_id,
        kind="candidate",
        fingerprint=sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        depends_on=tuple(a.key for a in change.assumptions),
    )


def attachment_selection_valid(facts, change, action, choice):
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
        and validate_attachment_candidate(facts, selection, candidate).valid
    )
