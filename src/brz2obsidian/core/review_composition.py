"""Compose explicit reference authority with an independently approved edited body."""

from brz2obsidian.contracts import (
    ExactContent,
    LinkDocument,
    LinkTargetFacts,
    StructureSpan,
)


def _shift(span, edits):
    if any(start < span.end and span.start < end for start, end, _ in edits):
        raise ValueError("Reference rewrite intersects other bound evidence")
    offset = sum(
        len(raw) - (end - start) for start, end, raw in edits if end <= span.start
    )
    return StructureSpan(start=span.start + offset, end=span.end + offset)


def _rewritten_state(state, content, edits):
    if content == state.content:
        return state
    structure = state.structure
    if (
        structure is None
        or structure.status != "supported"
        or state.interpretation != "supported"
        or any(start < structure.body.start for start, _, _ in edits)
    ):
        raise ValueError("Reference rewrite lacks bounded body evidence")
    structure = structure.model_copy(
        update={
            "content": content,
            "body": StructureSpan(start=structure.body.start, end=len(content.data)),
            "owned_sections": tuple(
                section.model_copy(update={"span": _shift(section.span, edits)})
                for section in structure.owned_sections
            ),
        }
    )
    return LinkTargetFacts.model_validate(
        state.model_copy(
            update={
                "content": content,
                "structure": structure,
                "anchors": tuple(
                    anchor.model_copy(
                        update={
                            "spans": tuple(_shift(span, edits) for span in anchor.spans)
                        }
                    )
                    for anchor in state.anchors
                ),
            }
        )
    )


def _compose(document, state, prior, choices):
    replacements = {}
    for choice, proof, later_reference in choices:
        old = next(
            (o for o in prior.occurrences if o.occurrence_id == choice.occurrence_id),
            None,
        )
        templates = tuple(
            o
            for o in proof.occurrences
            if o.raw == choice.replacement and o.meaning == choice.selected
        )
        if old is None or choice.selected is None or len(templates) != 1:
            raise ValueError("Reference rewrite lacks one selected occurrence")
        template = templates[0]
        matching = tuple(
            o
            for o in document.occurrences
            if (
                later_reference
                and (o.raw, o.syntax, o.embedded, o.query)
                == (old.raw, old.syntax, old.embedded, old.query)
                and o.meaning.model_copy(
                    update={"target_version": old.meaning.target_version}
                )
                == old.meaning
            )
            or (
                (o.raw, o.syntax, o.embedded, o.query, o.meaning)
                == (
                    template.raw,
                    template.syntax,
                    template.embedded,
                    template.query,
                    template.meaning,
                )
            )
        )
        if sum(o.raw == old.raw for o in prior.occurrences) != 1 or len(matching) != 1:
            raise ValueError(
                "Edited reference changed, disappeared or became ambiguous"
            )
        selected = matching[0]
        previous = replacements.get(selected.occurrence_id)
        if previous is not None and previous != template:
            raise ValueError("Reference choices select conflicting final effects")
        replacements[selected.occurrence_id] = template
    edits, occurrences, offset = [], [], 0
    for occurrence in document.occurrences:
        template = replacements.get(occurrence.occurrence_id)
        if template is None:
            occurrences.append(
                occurrence.model_copy(
                    update={
                        "span": _shift(occurrence.span, edits),
                        "destination_span": _shift(occurrence.destination_span, edits),
                    }
                )
            )
            continue
        start = occurrence.span.start + offset
        occurrences.append(
            template.model_copy(
                update={
                    "occurrence_id": occurrence.occurrence_id,
                    "span": StructureSpan(start=start, end=start + len(template.raw)),
                    "destination_span": StructureSpan(
                        start=start
                        + template.destination_span.start
                        - template.span.start,
                        end=start + template.destination_span.end - template.span.start,
                    ),
                }
            )
        )
        if occurrence.raw != template.raw:
            edits.append((occurrence.span.start, occurrence.span.end, template.raw))
            offset += len(template.raw) - len(occurrence.raw)
    raw = document.content.data
    for start, end, replacement in reversed(edits):
        raw = raw[:start] + replacement + raw[end:]
    content = document.content if not edits else ExactContent(data=raw)
    return (
        LinkDocument.model_validate(
            document.model_copy(
                update={"content": content, "occurrences": tuple(occurrences)}
            )
        ),
        _rewritten_state(state, content, edits),
    )


def composed_text_documents(facts, actions, approvals):
    """Renew only uniquely unchanged occurrences; retain historical decisions intact."""
    context = facts.link_context
    if context is None:
        return {}, False
    originals = {d.document_id: d for d in context.current_documents}
    action_by_id = {a.decision_id: a for a in actions}
    action_order = {a.decision_id: index for index, a in enumerate(actions)}
    documents, conflict = {}, False
    for approval in approvals:
        action = action_by_id.get(approval.decision_id)
        if (
            action is None
            or action.domain != "text"
            or action.choice != "edited"
            or action.candidate is None
        ):
            continue
        candidate = action.candidate
        document = candidate.links
        choices = tuple(
            (
                choice,
                proof,
                action_order[binary.decision_id] > action_order[action.decision_id],
            )
            for binary in approvals
            if binary.attachment_selection is not None
            for choice in binary.attachment_selection.link_choices
            if choice.document_id == document.document_id
            for proof in binary.attachment_candidate.documents
            if proof.document_id == document.document_id
        )
        if not choices:
            continue
        prior = originals.get(document.document_id)
        if (
            prior is None
            or document.status != "supported"
            or (document.source_path, document.path_mode)
            != (prior.source_path, prior.path_mode)
        ):
            conflict = True
            continue
        states = tuple(
            state
            for state in candidate.link_target_facts
            if state.content == document.content
            and any(
                t.target_id == state.target_id
                and t.canonical_path == document.source_path
                for t in candidate.link_targets
            )
        )
        if len(states) != 1:
            conflict = True
            continue
        try:
            documents[document.document_id] = _compose(
                document, states[0], prior, choices
            )
        except ValueError:
            conflict = True
    return documents, conflict
