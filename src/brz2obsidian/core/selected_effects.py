"""Pure exact-file projection from a canonical whole S1 review."""

from brz2obsidian.contracts import (
    ReviewPlan,
    SelectedReviewEffects,
    SelectedReviewFile,
)
from brz2obsidian.core.resolution import validate_review
from brz2obsidian.core.review_attachments import applicable_approvals


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
    plan = transition.plan
    if not plan.ready or plan.requirements or plan.blockers:
        return _refused("review_not_ready")

    approvals = {
        approval.change_id: approval
        for approval in applicable_approvals(
            plan.approvals, plan.attachment_applicability
        )
    }
    current_documents = (
        {}
        if plan.producer_facts.link_context is None
        else {
            document.document_id: document
            for document in plan.producer_facts.link_context.current_documents
        }
    )
    files = {}
    removals = set()

    def add(path, content, subject_id):
        previous = files.get(path)
        if previous is not None and previous[0] != content:
            raise ValueError("Conflicting selected file bytes")
        files[path] = content, min(previous[1], subject_id) if previous else subject_id

    try:
        for change in plan.proposal.changes:
            approval = approvals.get(change.change_id)
            if approval is not None and approval.attachment_candidate is not None:
                candidate = approval.attachment_candidate
                for output in candidate.outputs:
                    add(output.path, output.content, change.subject_id)
                for document in candidate.documents:
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
                            document.content,
                            change.subject_id,
                        )
                continue
            content = change.result if approval is None else approval.result
            if content is None:
                continue
            path = change.target_path if approval is None else approval.target_path
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
