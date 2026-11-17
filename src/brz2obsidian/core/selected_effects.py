"""Pure exact-file projection from a canonical whole S1 review."""

from dataclasses import dataclass, replace

from brz2obsidian.content_fingerprints import ChildWork, CompletedWork, drive_inline
from brz2obsidian.content_values import same_content
from brz2obsidian.contracts import ReviewPlan, SelectedReviewEffects, SelectedReviewFile
from brz2obsidian.core.resolution import validate_review
from brz2obsidian.core.reversals import reversal_subject, selected_reversal_outputs
from brz2obsidian.core.review_attachments import applicable_approvals
from brz2obsidian.core.review_composition import (
    CompositionWork,
    automatic_composed_document,
    automatic_reference_document,
)


def _refused(code):
    return SelectedReviewEffects(
        schema_id="brz2obsidian.selected-review-effects",
        schema_version=1,
        status="refused",
        code=code,
        proposal_id=None,
        generation=None,
        files=(),
        remove_paths=(),
    )


def select_review_effects(plan: ReviewPlan) -> SelectedReviewEffects:
    """Expose selected exact bytes; outer admission owns complete inventory and disk."""

    try:
        transition = validate_review(plan)
    except ValueError, TypeError, RecursionError:
        return _refused("invalid_plan")
    if transition.status != "accepted":
        return _refused("invalid_plan")
    return _project_review_effects(transition.plan)


def _project_review_effects(plan: ReviewPlan) -> SelectedReviewEffects:
    """Project a canonical plan already validated in this synchronous call."""
    return drive_inline(SelectedEffectsWork(plan))


@dataclass(frozen=True)
class SelectedEffectsWork:
    plan: ReviewPlan
    phase: str = "compose"
    approvals: tuple = ()


def advance_selected_effects(work, returned=None):
    plan = work.plan
    if work.phase == "compose":
        if not plan.ready or plan.requirements or plan.blockers:
            return CompletedWork(_refused("review_not_ready"))
        approvals = applicable_approvals(plan.approvals, plan.attachment_applicability)
        return ChildWork(
            CompositionWork(plan.producer_facts, plan.actions, approvals),
            replace(work, phase="finish", approvals=approvals),
        )
    if work.phase == "finish":
        return CompletedWork(
            _project_review_effects_body(work.plan, work.approvals, returned)
        )
    raise ValueError("Invalid selected effects phase")


def _project_review_effects_body(plan, effective_approvals, composition):
    if not plan.ready or plan.requirements or plan.blockers:
        return _refused("review_not_ready")

    approvals = {approval.change_id: approval for approval in effective_approvals}
    composed_documents = dict(composition.documents)
    composed_contents = dict(composition.contents)
    if composition.conflict:
        return _refused("effect_conflict")
    actions = {action.decision_id: action for action in plan.actions}
    current_documents = (
        {}
        if plan.producer_facts.link_context is None
        else {
            document.document_id: document
            for document in plan.producer_facts.link_context.current_documents
        }
    )
    cleanup_reference_originals = {}
    if plan.producer_facts.format_operation.kind == "attachment_cleanup":
        for approval in approvals.values():
            if approval.attachment_candidate is None:
                continue
            explicit = {
                choice.document_id
                for choice in approval.attachment_selection.link_choices
            }
            for document in approval.attachment_candidate.documents:
                prior = current_documents.get(document.document_id)
                if (
                    document.document_id in explicit
                    and prior is not None
                    and prior.source_path == document.source_path
                    and prior.content != document.content
                ):
                    cleanup_reference_originals[document.source_path] = prior.content
    files = {}
    removals = set()

    def add(path, content, subject_id):
        previous = files.get(path)
        if previous is not None and not same_content(previous[0], content):
            raise ValueError("Conflicting selected file bytes")
        files[path] = content, min(previous[1], subject_id) if previous else subject_id

    try:
        for change in plan.proposal.changes:
            approval = approvals.get(change.change_id)
            rows = selected_reversal_outputs(plan.producer_facts, change, approval)
            for row, content in rows:
                if content is None:
                    if (
                        row.current.existence == "present"
                        and approval is not None
                        and approval.choice == "reverse"
                    ):
                        removals.add(row.path)
                else:
                    add(row.path, content, change.subject_id)
            if approval is not None and approval.attachment_candidate is not None:
                candidate = approval.attachment_candidate
                if (
                    plan.producer_facts.format_operation.kind == "attachment_cleanup"
                    and approval.choice == "remove"
                ):
                    removals.add(change.path)
                for output in candidate.outputs:
                    add(output.path, output.content, change.subject_id)
                for document in candidate.documents:
                    if document.document_id in composed_documents:
                        document = composed_documents[document.document_id][0]
                    prior = current_documents.get(document.document_id)
                    if prior is None or (prior.content, prior.source_path) != (
                        document.content,
                        document.source_path,
                    ):
                        if prior is None:
                            raise ValueError(
                                "Changed document has no observed review context"
                            )
                        add(
                            document.source_path,
                            composed_contents.get(
                                document.document_id, document.content
                            ),
                            change.subject_id,
                        )
                continue
            content = change.result if approval is None else approval.result
            composed = automatic_composed_document(
                plan.producer_facts, change, approval, composed_documents
            )
            if composed is not None:
                content = composed_contents[composed[0].document_id]
            reference = automatic_reference_document(
                plan.producer_facts, change, approval, tuple(approvals.values())
            )
            if reference is not None and composed is None:
                content = reference.content
            subject = reversal_subject(plan.producer_facts, change)
            if subject.operation_reversal is not None:
                content = next(
                    (data for row, data in rows if row.path == subject.current.path),
                    subject.current.content,
                )
            if content is None:
                continue
            path = change.target_path if approval is None else approval.target_path
            action = None if approval is None else actions.get(approval.decision_id)
            if action is not None and action.candidate is not None:
                composed = composed_documents.get(action.candidate.links.document_id)
                if composed is not None:
                    content = composed_contents[action.candidate.links.document_id]
            if (
                approval is None
                and not change.requires_decision
                and change.disposition == "preserve_vault"
                and subject.attachment is None
                and path == subject.current.path
                and content == subject.current.content
                and cleanup_reference_originals.get(path) == content
            ):
                continue
            add(path, content, change.subject_id)
            if (
                change.rename_review is not None
                and change.rename_review.status == "accepted"
                and change.path != path
            ):
                removals.add(change.path)
        if removals & files.keys():
            raise ValueError("Selected removal conflicts with a file")
    except ValueError:
        return _refused("effect_conflict")

    return SelectedReviewEffects(
        schema_id="brz2obsidian.selected-review-effects",
        schema_version=1,
        status="selected",
        code="selected",
        proposal_id=plan.proposal.proposal_id,
        generation=plan.proposal.generation,
        files=tuple(
            SelectedReviewFile(
                path=path, content=files[path][0], subject_id=files[path][1]
            )
            for path in sorted(files)
        ),
        remove_paths=tuple(sorted(removals)),
    )
