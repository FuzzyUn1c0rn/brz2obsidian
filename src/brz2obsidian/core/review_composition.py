"""Compose explicit reference authority for a shared reviewed document."""

from dataclasses import dataclass, replace
from hashlib import sha256

from brz2obsidian.content_fingerprints import (
    CompletedWork,
    CreatedRequest,
    PendingCreated,
    canonical_equal,
    consume_created,
    drive_inline,
    request_token,
    source_span,
)
from brz2obsidian.content_values import content_sha
from brz2obsidian.contracts import (
    LinkDocument,
    LinkTargetFacts,
    StructureSpan,
)
from brz2obsidian.output_formats import QUALIFIED_OUTPUT_FORMATS


def _shift(span, edits):
    if any(start < span.end and span.start < end for start, end, _ in edits):
        raise ValueError("Reference rewrite intersects other bound evidence")
    offset = sum(
        raw.end - raw.start - (end - start)
        for start, end, raw in edits
        if end <= span.start
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
    roles = state.file_roles
    if roles is not None:
        prefix = structure.content.data[: structure.body.start]
        if content.data[: structure.body.start] != prefix or (
            structure.body.start == 0 and content.data.startswith(b"---")
        ):
            raise ValueError("Reference rewrite changes native property evidence")
        roles = roles.model_copy(
            update={"content_sha256": sha256(content.data).hexdigest()}
        )
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
                "file_roles": roles,
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
    if state.file_roles is not None and state.file_roles.path != document.source_path:
        raise ValueError("Reference rewrite changes the qualified file path")
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
        if previous is not None and previous[0] != template:
            raise ValueError("Reference choices select conflicting final effects")
        replacements[selected.occurrence_id] = template, proof
    edits, occurrences, offset = [], [], 0
    for occurrence in document.occurrences:
        replacement = replacements.get(occurrence.occurrence_id)
        if replacement is None:
            occurrences.append(
                occurrence.model_copy(
                    update={
                        "span": _shift(occurrence.span, edits),
                        "destination_span": _shift(occurrence.destination_span, edits),
                    }
                )
            )
            continue
        template, proof = replacement
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
            edits.append(
                (
                    occurrence.span.start,
                    occurrence.span.end,
                    source_span(
                        proof.content,
                        template.span.start,
                        template.span.end,
                    ),
                )
            )
            offset += len(template.raw) - len(occurrence.raw)
    spans, cursor = [], 0
    for start, end, replacement in edits:
        if cursor < start:
            spans.append(source_span(document.content, cursor, start))
        spans.append(replacement)
        cursor = end
    if cursor < document.content.identity.size:
        spans.append(
            source_span(document.content, cursor, document.content.identity.size)
        )
    return CompositionGeometry(
        document, state, tuple(edits), tuple(occurrences), tuple(spans)
    )


def _complete(geometry, content):
    document, state = geometry.document, geometry.state
    return (
        LinkDocument.model_validate(
            document.model_copy(
                update={"content": content, "occurrences": geometry.occurrences}
            )
        ),
        _rewritten_state(state, content, geometry.edits),
    )


def _composition_inputs(facts, actions, approvals):
    """Renew only uniquely unchanged occurrences; retain historical decisions intact."""
    context = facts.link_context
    if context is None:
        return (), False
    originals = {d.document_id: d for d in context.current_documents}
    action_by_id = {a.decision_id: a for a in actions}
    action_order = {a.decision_id: index for index, a in enumerate(actions)}
    documents, conflict = [], False
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
        documents.append((document, states[0], prior, choices))
    edited_documents = {document.document_id for document, _, _, _ in documents}
    for document_id, prior in originals.items():
        if (
            document_id in edited_documents
            or facts.format_operation.kind != "source_update"
        ):
            continue
        selected = tuple(
            (binary, choice, proof)
            for binary in approvals
            if binary.attachment_selection is not None
            and binary.attachment_candidate is not None
            for choice in binary.attachment_selection.link_choices
            if choice.document_id == document_id
            for proof in binary.attachment_candidate.documents
            if proof.document_id == document_id
        )
        if len({binary.decision_id for binary, _, _ in selected}) < 2:
            continue
        states = tuple(
            state
            for state in context.current_target_facts
            if state.content == prior.content
            and any(
                target.target_id == state.target_id
                and target.canonical_path == prior.source_path
                for target in context.current_targets
            )
        )
        if prior.status != "supported" or len(states) != 1:
            conflict = True
            continue
        choices = tuple((choice, proof, True) for _, choice, proof in selected)
        documents.append((prior, states[0], prior, choices))
    return tuple(documents), conflict


@dataclass(frozen=True)
class CompositionGeometry:
    document: object
    state: object
    edits: tuple
    occurrences: tuple
    spans: tuple


@dataclass(frozen=True)
class CompositionOutcome:
    documents: tuple = ()
    contents: tuple = ()
    conflict: bool = False


@dataclass(frozen=True)
class CompositionWork:
    facts: object
    actions: tuple
    approvals: tuple
    phase: str = "prepare"
    jobs: tuple = ()
    index: int = 0
    documents: tuple = ()
    contents: tuple = ()
    conflict: bool = False
    geometry: object = None
    pending: object = None


def advance_composition(work, returned, context):
    if work.phase == "prepare":
        jobs, conflict = _composition_inputs(work.facts, work.actions, work.approvals)
        return replace(work, phase="compose", jobs=jobs, conflict=conflict)
    if work.phase == "compose":
        if work.index == len(work.jobs):
            return CompletedWork(
                CompositionOutcome(work.documents, work.contents, work.conflict)
            )
        try:
            geometry = _compose(*work.jobs[work.index])
            if not geometry.edits:
                document, state = _complete(geometry, geometry.document.content)
                return replace(
                    work,
                    index=work.index + 1,
                    documents=work.documents
                    + ((document.document_id, (document, state)),),
                    contents=work.contents
                    + ((document.document_id, document.content),),
                )
            role = (
                "composed-document",
                geometry.document.document_id,
                geometry.document.source_path,
            )
            request = CreatedRequest(
                request_token(context, "created", role),
                role,
                sum(span.end - span.start for span in geometry.spans),
                geometry.spans,
            )
            return PendingCreated(
                request,
                replace(work, phase="finish", geometry=geometry, pending=request),
            )
        except ValueError:
            return replace(work, index=work.index + 1, conflict=True)
    if work.phase == "finish":
        result = consume_created(work.pending, returned)
        try:
            document, state = _complete(work.geometry, result.semantic)
        except ValueError:
            if result.content.occurrence is not None:
                # Owned generation was already admitted. Its later semantic
                # failure must invalidate the owner operation, not look ready.
                raise
            return replace(
                work,
                phase="compose",
                index=work.index + 1,
                conflict=True,
                geometry=None,
                pending=None,
            )
        return replace(
            work,
            phase="compose",
            index=work.index + 1,
            documents=work.documents + ((document.document_id, (document, state)),),
            contents=work.contents + ((document.document_id, result.content),),
            geometry=None,
            pending=None,
        )
    raise ValueError("Invalid composition phase")


def composed_text_documents(facts, actions, approvals):
    result = drive_inline(CompositionWork(facts, actions, approvals))
    return dict(result.documents), result.conflict


def automatic_composed_document(facts, change, approval, composed):
    """Bind a shared explicit reference result to its unchanged automatic owner."""
    if (
        approval is not None
        or change.requires_decision
        or change.disposition not in ("preserve_vault", "no_change")
        or facts.link_context is None
        or facts.format_operation.kind != "source_update"
    ):
        return None
    subject = next(
        row
        for row in facts.subjects
        if (row.item_id, row.facet) == (change.item_id, change.facet)
    )
    if (
        subject.attachment is not None
        or subject.operation_reversal is not None
        or change.target_path != subject.current.path
        or not canonical_equal(change.result, subject.current.content)
    ):
        return None
    matches = tuple(
        composed[prior.document_id]
        for prior in facts.link_context.current_documents
        if prior.document_id in composed
        and prior.source_path == subject.current.path
        and canonical_equal(prior.content, subject.current.content)
    )
    return matches[0] if len(matches) == 1 else None


def automatic_reference_document(facts, change, approval, approvals):
    """A current8 explicit reference choice outranks only an automatic keep."""
    if (
        facts.incoming_identity.output_format not in QUALIFIED_OUTPUT_FORMATS
        or facts.format_operation.kind != "source_update"
        or approval is not None
        or change.requires_decision
        or change.disposition not in ("preserve_vault", "no_change")
        or facts.link_context is None
    ):
        return None
    subject = next(
        row
        for row in facts.subjects
        if (row.item_id, row.facet) == (change.item_id, change.facet)
    )
    if (
        subject.attachment is not None
        or change.target_path != subject.current.path
        or not canonical_equal(change.result, subject.current.content)
    ):
        return None
    owners = {
        row.target_id
        for row in facts.link_context.current_targets
        if row.canonical_path == subject.current.path
    }
    states = tuple(
        row
        for row in facts.link_context.current_target_facts
        if row.target_id in owners
    )
    if len(states) != 1:
        return None
    state = states[0]
    if (
        state.file_roles is None
        or state.file_roles.path != subject.current.path
        or not canonical_equal(state.content, subject.current.content)
        or state.content is None
        or state.file_roles.content_sha256 != content_sha(state.content)
    ):
        return None
    selected = []
    for binary in approvals:
        if binary.attachment_candidate is None or binary.attachment_selection is None:
            continue
        explicit = {
            choice.document_id for choice in binary.attachment_selection.link_choices
        }
        for document in binary.attachment_candidate.documents:
            if (
                document.document_id not in explicit
                or document.source_path != subject.current.path
            ):
                continue
            prior = next(
                (
                    row
                    for row in facts.link_context.current_documents
                    if row.document_id == document.document_id
                ),
                None,
            )
            if (
                prior is not None
                and prior.source_path == subject.current.path
                and canonical_equal(prior.content, subject.current.content)
            ):
                selected.append(document)
    return (
        selected[0]
        if selected and all(canonical_equal(row, selected[0]) for row in selected)
        else None
    )
