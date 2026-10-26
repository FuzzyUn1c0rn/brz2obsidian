"""Pure policy-query subjects from current facts and canonical review choices."""

from brz2obsidian.contracts import reconciliation_subject_id
from brz2obsidian.core import select_review_effects

from .vault_contracts import VaultSubject


def approved_attachment_subjects(plan):
    """Project approved outputs and reference edits from a canonical saved plan."""
    context = plan.producer_facts.link_context
    documents = (
        {}
        if context is None
        else {row.document_id: row for row in context.current_documents}
    )
    changes = {row.change_id: row for row in plan.proposal.changes}
    candidates = {
        row.decision_id: row.candidate for row in plan.attachment_applicability
    }
    paths = set()
    for approval in plan.approvals:
        candidate = candidates.get(approval.decision_id, approval.attachment_candidate)
        if candidate is None or approval.attachment_selection is None:
            continue
        owner = changes[approval.change_id].subject_id
        paths.update((output.path, owner) for output in candidate.outputs)
        explicit = {
            row.document_id for row in approval.attachment_selection.link_choices
        }
        for document in candidate.documents:
            prior = documents.get(document.document_id)
            if (
                document.document_id in explicit
                and prior is not None
                and prior.source_path == document.source_path
                and prior.content != document.content
            ):
                paths.add((document.source_path, owner))
    return tuple(
        VaultSubject(path=path, subject_id=owner) for path, owner in sorted(paths)
    )


def review_subjects(facts, review=None, *, effects=None):
    paths = {}

    def add(path, subject_id):
        paths[path, subject_id] = VaultSubject(path=path, subject_id=subject_id)

    observed = (facts,) if review is None else (facts, review.facts)
    for current in observed:
        for subject in current.subjects:
            subject_id = reconciliation_subject_id(
                current.incoming_identity.module_id,
                current.incoming_identity.collection_id,
                subject.item_id,
                subject.facet,
            )
            for path in (subject.path, subject.current.path):
                add(path, subject_id)
    if review is not None:
        declared = tuple(paths)
        changed_documents = set()
        approvals = {a.change_id: a for a in review.approvals}
        views = {a.decision_id: a.candidate for a in review.attachment_applicability}
        context = review.producer_facts.link_context
        documents = (
            {}
            if context is None
            else {d.document_id: d for d in context.current_documents}
        )
        for change in review.proposal.changes:
            approval = approvals.get(change.change_id)
            candidate = (
                None
                if approval is None
                else views.get(approval.decision_id, approval.attachment_candidate)
            )
            if candidate is not None:
                for output in candidate.outputs:
                    add(output.path, change.subject_id)
                for document in candidate.documents:
                    prior = documents.get(document.document_id)
                    if prior is None or (prior.source_path, prior.content) != (
                        document.source_path,
                        document.content,
                    ):
                        if (
                            prior is not None
                            and prior.source_path == document.source_path
                        ):
                            changed_documents.add(document.source_path)
                        add(document.source_path, change.subject_id)
            elif (change.result if approval is None else approval.result) is not None:
                add(
                    change.target_path if approval is None else approval.target_path,
                    change.subject_id,
                )
        if facts.format_operation.kind == "attachment_cleanup":
            selected = select_review_effects(review) if effects is None else effects
            if selected.status == "selected":
                for row in selected.files:
                    if (
                        row.path not in changed_documents
                        or sum(path == row.path for path, _ in declared) > 1
                    ):
                        continue
                    # One physical write has the selected effect's actual owner.
                    # Its scoped tracking/storage consent must use that same owner.
                    paths = {
                        key: value for key, value in paths.items() if key[0] != row.path
                    }
                    add(row.path, row.subject_id)
    return tuple(paths[key] for key in sorted(paths))
