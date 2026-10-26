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
    return review_plan_attachment_references(plan, requirement_id)


def review_plan_attachment_references(plan, requirement_id):
    requirement = next(
        row
        for row in inspect_review_choices(plan)
        if row.requirement_id == requirement_id
    )
    change = next(
        row for row in plan.proposal.changes if row.change_id == requirement.change_id
    )
    if change.attachment_review is None:
        raise ValueError("An attachment reference offer is required")
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


def attachment_reference_destinations(preparation, requirement_id):
    """Return canonical offered meanings, without deriving new destinations."""
    plan = UpdatePreparation.model_validate(preparation).review
    return review_plan_attachment_reference_destinations(plan, requirement_id)


def review_plan_attachment_reference_destinations(plan, requirement_id):
    from .update_context_contracts import UpdateReferenceDestination

    requirement = next(
        row
        for row in inspect_review_choices(plan)
        if row.requirement_id == requirement_id
    )
    change = next(
        row for row in plan.proposal.changes if row.change_id == requirement.change_id
    )
    if change.attachment_review is None:
        raise ValueError("An attachment reference offer is required")
    links = {
        (row.document_id, row.occurrence_id): row
        for row in change.attachment_review.links
    }
    return {
        token: tuple(
            UpdateReferenceDestination(choice=choice, meaning=meaning)
            for choice, meaning in (
                ("keep_current", link.old),
                ("use_incoming", link.incoming),
                ("use_secondary", link.secondary),
            )
            if choice in link.choices and meaning is not None
        )
        for token, document, occurrence in review_plan_attachment_references(
            plan, requirement_id
        )
        for link in (links[(document.document_id, occurrence.occurrence_id)],)
    }


def attachment_reference_page(preparation, requirement_id, *, offset=0, limit=100):
    """Page canonical reference offers; no producer context or candidate is accepted."""
    preparation = UpdatePreparation.model_validate(preparation)
    return review_plan_attachment_reference_page(
        preparation.review,
        requirement_id,
        offset=offset,
        limit=limit,
        drop_only=preparation.kind == "attachment_cleanup",
    )


def review_plan_attachment_reference_page(
    plan, requirement_id, *, offset=0, limit=100, drop_only=False
):
    from .update_context_contracts import UpdateReferenceOffer

    if (
        type(offset) is not int
        or offset < 0
        or type(limit) is not int
        or not 1 <= limit <= 100
    ):
        raise ValueError("Invalid reference page")
    refs = review_plan_attachment_references(plan, requirement_id)
    destinations = review_plan_attachment_reference_destinations(plan, requirement_id)
    end = min(len(refs), offset + limit)
    return (
        tuple(
            UpdateReferenceOffer(
                reference_id=token,
                document_id=document.document_id,
                occurrence_id=occurrence.occurrence_id,
                document_path=document.source_path,
                snippet=document.content.data[
                    max(0, occurrence.span.start - 120) : max(
                        0, occurrence.span.start - 120
                    )
                    + 512
                ],
                old=occurrence.meaning,
                choices=("drop",)
                if drop_only
                else tuple(row.choice for row in destinations[token]),
                destinations=() if drop_only else destinations[token],
            )
            for token, document, occurrence in refs[offset:end]
        ),
        len(refs),
        end if end < len(refs) else None,
    )


def review_choice_action(
    preparation,
    *,
    requirement_id,
    choice,
    assumptions_digest,
    references=(),
    selected_entry_id=None,
    disassociate_entry_ids=(),
):
    preparation = UpdatePreparation.model_validate(preparation)
    return review_plan_choice_action(
        preparation.review,
        requirement_id=requirement_id,
        choice=choice,
        assumptions_digest=assumptions_digest,
        references=references,
        selected_entry_id=selected_entry_id,
        disassociate_entry_ids=disassociate_entry_ids,
    )


def review_plan_choice_action(
    plan,
    *,
    requirement_id,
    choice,
    assumptions_digest,
    references=(),
    selected_entry_id=None,
    disassociate_entry_ids=(),
):
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
        (
            row
            for row in plan.proposal.changes
            if row.change_id == requirement.change_id
        ),
        None,
    )
    if change is None and requirement.domain not in (
        "compatible_group",
        "tracking",
        "storage",
    ):
        raise ValueError("Review offer changed")
    selection = candidate = None
    if requirement.domain == "identity":
        candidates = {row.entry_id for row in change.identity_review.candidates}
        requested = (selected_entry_id, *disassociate_entry_ids)
        if (
            selected_entry_id is None
            or len(set(requested)) != len(requested)
            or not set(requested) <= candidates
        ):
            raise ValueError("Identity offer changed")
    elif selected_entry_id is not None or disassociate_entry_ids:
        raise ValueError("Identity choice is unavailable")
    if (
        change is not None
        and change.attachment_review is not None
        and not (requirement.domain == "reversal" and choice == "current")
    ):
        attachment_choice = (
            "incoming"
            if requirement.domain == "reversal" and choice == "reverse"
            else choice
        )
        alternative = next(
            row
            for row in change.attachment_review.alternatives
            if row.choice == attachment_choice and row.eligible
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
            offered_refs = review_plan_attachment_references(plan, requirement_id)
            if (
                any(row.choice != "drop" for row in supplied)
                or len({row.reference_id for row in supplied}) != len(supplied)
                or {row.reference_id for row in supplied}
                != {row[0] for row in offered_refs}
            ):
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
        elif attachment_choice in ("incoming", "both"):
            from .attachment_choices import selected_attachment_candidate

            links, candidate = selected_attachment_candidate(
                plan,
                change,
                alternative,
                references,
                review_plan_attachment_references(plan, requirement_id),
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
            choice=attachment_choice,
            link_choices=links,
            provenance="explicit_user",
        )
        candidate = candidate or AttachmentCandidate(
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
        change_id=requirement.change_id,
        reviewed_assumptions=requirement.assumptions,
        domain=requirement.domain,
        choice=choice,
        candidate=None,
        attachment_selection=selection,
        attachment_candidate=candidate,
        selected_entry_id=selected_entry_id,
        disassociate_entry_ids=disassociate_entry_ids,
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
    selected_entry_id=None,
    disassociate_entry_ids=(),
):
    preparation = UpdatePreparation.model_validate(preparation)
    action = review_choice_action(
        preparation,
        requirement_id=requirement_id,
        choice=choice,
        assumptions_digest=assumptions_digest,
        references=references,
        selected_entry_id=selected_entry_id,
        disassociate_entry_ids=disassociate_entry_ids,
    )
    if preparation.kind == "format_transition" and action.domain == "configuration":
        return operations.resolve_configuration(preparation, ())
    return operations.resolve_update(preparation, action, edited=edited)
