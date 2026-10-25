"""Build review actions from canonical offers without exporting proof bodies."""

from hashlib import sha256
from uuid import uuid4

from brz2obsidian.contracts import (
    AttachmentCandidate,
    AttachmentSelection,
    ExactContent,
    LinkOccurrenceChoice,
    ReviewAction,
    ReviewRequirement,
)
from brz2obsidian.core import inspect_review_choices
from brz2obsidian.obsidian import interpret_link_target, interpret_links

from .update_contracts import UpdatePreparation


def requirement_digest(requirement):
    canonical = ReviewRequirement.model_validate(
        requirement.model_dump(include=set(ReviewRequirement.model_fields))
    )
    return sha256(canonical.model_dump_json().encode("utf-8")).hexdigest()


def attachment_references(preparation, requirement_id):
    plan = UpdatePreparation.model_validate(preparation).review
    requirement = next(
        row
        for row in inspect_review_choices(plan)
        if row.requirement_id == requirement_id and row.domain == "attachment"
    )
    change = next(
        row for row in plan.proposal.changes if row.change_id == requirement.change_id
    )
    offered = {
        (link.document_id, link.occurrence_id)
        for link in change.attachment_review.links
        if link.old is not None
    }
    return tuple(
        (
            sha256(
                (
                    requirement_digest(requirement)
                    + document.document_id
                    + "\0"
                    + occurrence.model_dump_json()
                ).encode("utf-8")
            ).hexdigest(),
            document,
            occurrence,
        )
        for document in plan.facts.link_context.current_documents
        for occurrence in document.occurrences
        if (document.document_id, occurrence.occurrence_id) in offered
    )


def review_choice_action(
    preparation,
    *,
    requirement_id,
    choice,
    assumptions_digest,
    references=(),
):
    preparation = UpdatePreparation.model_validate(preparation)
    plan = preparation.review
    requirement = next(
        (
            row
            for row in inspect_review_choices(plan)
            if row.requirement_id == requirement_id
        ),
        None,
    )
    if (
        requirement is None
        or requirement_digest(requirement) != assumptions_digest
        or choice not in requirement.enabled_choices
    ):
        raise ValueError("Review offer changed")
    change = next(
        row for row in plan.proposal.changes if row.change_id == requirement.change_id
    )
    selection = candidate = None
    if change.attachment_review is not None:
        if choice not in ("current", "remove"):
            raise ValueError("Reference choices are required")
        alternative = next(
            row
            for row in change.attachment_review.alternatives
            if row.choice == choice and row.eligible
        )
        context = plan.facts.link_context
        documents, states, links = (
            context.current_documents,
            context.current_target_facts,
            (),
        )
        if choice == "remove":
            from .update_context_contracts import UpdateReferenceChoice

            supplied = tuple(
                UpdateReferenceChoice.model_validate(row) for row in references
            )
            offered_refs = attachment_references(preparation, requirement_id)
            if len({row.reference_id for row in supplied}) != len(supplied) or {
                row.reference_id for row in supplied
            } != {row[0] for row in offered_refs}:
                raise ValueError("Reference offer changed")
            subject = next(
                row
                for row in plan.facts.subjects
                if (row.item_id, row.facet) == (change.item_id, change.facet)
            )
            target_id = subject.attachment.current_target_id
            if any(
                occurrence.meaning.target_id != target_id
                for _, _, occurrence in offered_refs
            ):
                raise ValueError("Reference choice is unavailable")
            states = tuple(
                interpret_link_target(
                    None, target_id=row.target_id, existence="missing", memberships=()
                )
                if row.target_id == target_id
                else row
                for row in states
            )
            links = tuple(
                LinkOccurrenceChoice(
                    document_id=document.document_id,
                    occurrence_id=occurrence.occurrence_id,
                    old=occurrence.meaning,
                    replacement=b"",
                    selected=None,
                    expected_memberships=(),
                    provenance="explicit_user",
                )
                for _, document, occurrence in offered_refs
            )
            rewritten = []
            for document in documents:
                raw = document.content.data
                for _, _, occurrence in reversed(
                    tuple(
                        row
                        for row in offered_refs
                        if row[1].document_id == document.document_id
                    )
                ):
                    raw = raw[: occurrence.span.start] + raw[occurrence.span.end :]
                rewritten.append(
                    interpret_links(
                        ExactContent(data=raw),
                        document_id=document.document_id,
                        source_path=document.source_path,
                        path_mode=document.path_mode,
                        targets=context.current_targets,
                        target_facts=states,
                        inventory=document.inventory,
                    )
                )
            documents = tuple(rewritten)
            states = tuple(
                interpret_link_target(
                    document.content,
                    target_id=row.target_id,
                    existence="present",
                    memberships=row.memberships,
                )
                if (
                    document := next(
                        (doc for doc in documents if doc.document_id == row.target_id),
                        None,
                    )
                )
                is not None
                else row
                for row in states
            )
        elif references:
            raise ValueError("Reference choice is unavailable")
        selection = AttachmentSelection(
            schema_id="brz2obsidian.attachment-selection",
            schema_version=1,
            proposal_id=plan.proposal.proposal_id,
            generation=plan.proposal.generation,
            item_id=change.item_id,
            facet=change.facet,
            reviewed_change_id=change.change_id,
            reviewed_assumptions=requirement.assumptions,
            choice=choice,
            link_choices=links,
            provenance="explicit_user",
        )
        candidate = AttachmentCandidate(
            schema_id="brz2obsidian.attachment-candidate",
            schema_version=1,
            outputs=alternative.outputs,
            documents=documents,
            targets=context.current_targets,
            target_facts=states,
        )
    action = ReviewAction(
        schema_id="brz2obsidian.review-action",
        schema_version=1,
        decision_id=str(uuid4()),
        proposal_id=plan.proposal.proposal_id,
        expected_generation=plan.proposal.generation,
        change_id=change.change_id,
        reviewed_assumptions=requirement.assumptions,
        domain=requirement.domain,
        choice=choice,
        candidate=None,
        attachment_selection=selection,
        attachment_candidate=candidate,
        selected_entry_id=None,
        disassociate_entry_ids=(),
    )
    return action


def resolve_update_choice(
    operations,
    preparation,
    *,
    requirement_id,
    choice,
    assumptions_digest,
    references=(),
    edited=None,
):
    preparation = UpdatePreparation.model_validate(preparation)
    action = review_choice_action(
        preparation,
        requirement_id=requirement_id,
        choice=choice,
        assumptions_digest=assumptions_digest,
        references=references,
    )
    if preparation.kind == "format_transition" and action.domain == "configuration":
        return operations.resolve_configuration(preparation, ())
    return operations.resolve_update(preparation, action, edited=edited)
