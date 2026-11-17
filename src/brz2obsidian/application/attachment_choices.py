"""Compile small offered reference decisions into a local attachment candidate."""

from brz2obsidian.contracts import (
    AttachmentCandidate,
    ExactContent,
    LinkOccurrenceChoice,
)
from brz2obsidian.obsidian import (
    interpret_link_target,
    interpret_links,
    render_link_replacement,
)

REFERENCE_CHOICES_GUIDANCE = "Review references and stage a choice for every occurrence before choosing this version."


class ReferenceChoicesRequired(ValueError):
    """The current offer has valid but incomplete explicit reference decisions."""


def validated_reference_choices(references, offered):
    from .update_context_contracts import UpdateReferenceChoice

    supplied = tuple(UpdateReferenceChoice.model_validate(row) for row in references)
    choices = {row.reference_id: row.choice for row in supplied}
    if (
        len(choices) != len(supplied)
        or not choices.keys() <= offered.keys()
        or any(choice not in offered[token] for token, choice in choices.items())
    ):
        raise ValueError("Reference offer changed")
    if choices.keys() != offered.keys():
        raise ReferenceChoicesRequired
    return choices


def selected_attachment_candidate(
    plan, change, alternative, references, offered_refs, *, _owner=None, _session=None
):
    context = plan.facts.link_context
    subject = next(
        row
        for row in plan.facts.subjects
        if (row.item_id, row.facet) == (change.item_id, change.facet)
    )
    targets = {row.target_id: row for row in context.current_targets}
    states = {row.target_id: row for row in context.current_target_facts}
    session = _session if _session is not None else getattr(_owner, "_session", None)
    observe_target = (
        interpret_link_target if session is None else session._assembly_link_state
    )
    for output in alternative.outputs:
        templates = tuple(
            row
            for row in context.current_targets
            if row.target_id == output.target_id and row.canonical_path == output.path
        )
        if not templates:
            templates = tuple(
                row
                for row in context.incoming_targets
                if row.target_id == output.target_id
                and row.canonical_path == output.path
            )
        if len(templates) == 1:
            target = templates[0]
        else:
            bases = tuple(
                row
                for row in context.current_targets
                if row.target_id == subject.attachment.current_target_id
            )
            slots = tuple(
                row
                for row in subject.attachment.allocation_candidates
                if row.path == output.path
            )
            if templates or len(bases) != 1 or len(slots) != 1:
                raise ValueError("Selected destination is not qualified")
            target = bases[0].model_copy(
                update={
                    "target_id": output.target_id,
                    "canonical_path": output.path,
                    "target": slots[0].target,
                    "representations": (output.path,),
                }
            )
        targets[output.target_id] = target
        states[output.target_id] = observe_target(
            output.content,
            target_id=output.target_id,
            existence="present",
            memberships=(),
            source_path=output.path,
            output_format=plan.facts.incoming_identity.output_format,
        )
    offered = {
        (row.document_id, row.occurrence_id): row
        for row in change.attachment_review.links
    }
    output_ids = {row.target_id for row in alternative.outputs}
    available = {}
    for token, document, occurrence in offered_refs:
        review = offered[(document.document_id, occurrence.occurrence_id)]
        available[token] = tuple(
            choice
            for choice, meaning in (
                ("keep_current", review.old),
                ("use_incoming", review.incoming),
                ("use_secondary", review.secondary),
            )
            if choice in review.choices
            and meaning is not None
            and meaning.target_id in output_ids
        )
    choices = validated_reference_choices(references, available)
    links, replacements = [], {}
    for token, document, occurrence in offered_refs:
        review = offered[(document.document_id, occurrence.occurrence_id)]
        choice = choices[token]
        if choice not in review.choices:
            raise ValueError("Reference choice is unavailable")
        selected = {
            "keep_current": review.old,
            "use_incoming": review.incoming,
            "use_secondary": review.secondary,
        }.get(choice)
        if selected is None or selected.target_id not in {
            row.target_id for row in alternative.outputs
        }:
            raise ValueError("Reference choice is unavailable")
        replacement = render_link_replacement(
            document,
            occurrence.occurrence_id,
            selected,
            targets=tuple(targets.values()),
            target_facts=tuple(states.values()),
        )
        replacements.setdefault(document.document_id, []).append(
            (occurrence.span.start, occurrence.span.end, replacement)
        )
        links.append(
            LinkOccurrenceChoice(
                document_id=document.document_id,
                occurrence_id=occurrence.occurrence_id,
                old=occurrence.meaning,
                replacement=replacement,
                selected=selected,
                expected_memberships=states[selected.target_id].memberships,
                provenance="explicit_user",
            )
        )
    documents = []
    for document in context.current_documents:
        raw = document.content.data
        for start, end, replacement in sorted(
            replacements.get(document.document_id, ()), reverse=True
        ):
            raw = raw[:start] + replacement + raw[end:]
        documents.append(
            interpret_links(
                ExactContent(data=raw),
                document_id=document.document_id,
                source_path=document.source_path,
                path_mode=document.path_mode,
                targets=tuple(targets.values()),
                target_facts=tuple(states.values()),
                inventory=document.inventory,
                output_format=plan.facts.incoming_identity.output_format,
                record_format=plan.facts.baseline_identity.output_format,
            )
        )
    for target_id, state in tuple(states.items()):
        bound = tuple(
            doc
            for doc in documents
            if doc.source_path == targets[target_id].canonical_path
        )
        if bound:
            if len(bound) != 1:
                raise ValueError("Document target is ambiguous")
            states[target_id] = observe_target(
                bound[0].content,
                target_id=target_id,
                existence="present",
                memberships=state.memberships,
                membership_targets=tuple(targets.values()),
                source_path=bound[0].source_path,
                output_format=plan.facts.incoming_identity.output_format,
            )
    return tuple(links), AttachmentCandidate(
        schema_id="brz2obsidian.attachment-candidate",
        schema_version=1,
        outputs=alternative.outputs,
        documents=tuple(documents),
        targets=tuple(targets.values()),
        target_facts=tuple(states.values()),
    )
