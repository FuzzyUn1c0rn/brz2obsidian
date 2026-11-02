"""Canonical operation-owned output facts; no storage, parsing or independent merger."""

from .identity import _paths_collide, _target_safe


def cleanup_removal_continuation(facts, subject):
    """Recognize a known-absent retained target, never authorize a new deletion."""
    attachment = subject.attachment
    if attachment is None:
        return None
    fact = attachment.removal_continuation
    owner = attachment.retained_ownership
    if (
        fact is None
        or owner is None
        or subject.operation_reversal is not None
        or facts.format_operation.kind != "attachment_cleanup"
        or facts.inventory != "complete"
        or subject.current.existence != "absent"
        or subject.current.content is not None
        or subject.path != subject.current.path
        or fact.path != subject.current.path
        or fact.target_id != attachment.current_target_id
        or owner.source_path != fact.path
        or (
            owner.identity.module_id,
            owner.identity.collection_id,
            owner.identity.item_id,
            owner.facet,
        )
        != (
            facts.incoming_identity.module_id,
            facts.incoming_identity.collection_id,
            subject.item_id,
            subject.facet,
        )
    ):
        return None
    return fact


def content_bytes(content):
    return None if content is None else content.data


def reversal_subject(facts, change):
    return next(
        s
        for s in facts.subjects
        if (s.item_id, s.facet) == (change.item_id, change.facet)
    )


def primary_reversal_content(subject, *, reverse=False):
    row = next(
        (
            r
            for r in subject.operation_reversal.outputs
            if r.path == subject.current.path
        ),
        None,
    )
    return (
        subject.current.content
        if row is None
        else row.target
        if reverse
        else row.current.content
    )


def selected_reversal_outputs(facts, change, approval):
    subject = reversal_subject(facts, change)
    if subject.operation_reversal is None:
        return ()
    choice = "current" if approval is None else approval.choice
    edited_path = next(
        (r.path for r in subject.operation_reversal.outputs if r.target is not None),
        subject.current.path,
    )
    return tuple(
        (
            row,
            approval.result
            if choice == "edited" and row.path == edited_path
            else row.target
            if choice == "reverse"
            else row.current.content,
        )
        for row in subject.operation_reversal.outputs
    )


def reversal_target(proof, row):
    return next(
        t
        for t in proof.owned_targets
        if (t.target_id, t.canonical_path) == (row.target_id, row.path)
    )


def reversal_text_comparison(facts, change):
    subject = reversal_subject(facts, change)
    rows = tuple(r for r in subject.operation_reversal.outputs if r.target is not None)
    if len(rows) != 1:
        return change
    row = rows[0]
    return change.model_copy(
        update={
            "path": row.path,
            "target_path": row.path,
            "original": row.produced,
            "current": row.current.content,
            "incoming": row.target,
        }
    )


def reversal_resource_record(facts, entry, target, state):
    return any(
        subject.attachment is not None
        and subject.operation_reversal is not None
        and any(
            row.path == entry.current.path == target.canonical_path
            and row.target_id == target.target_id
            and row.current.existence == entry.current.existence == state.existence
            and content_bytes(row.current.content)
            == content_bytes(entry.current.content)
            == content_bytes(state.content)
            and target.kind == "resource"
            and target.identity is None
            and reversal_target(subject.operation_reversal, row).target == target.target
            for row in subject.operation_reversal.outputs
        )
        for subject in facts.subjects
    )


def reversal_physical_entry(facts, entry):
    """Qualify a transient note location without creating a second logical ID."""
    return any(
        subject.attachment is None
        and subject.operation_reversal is not None
        and entry.facet == subject.facet
        and any(
            row.path == entry.current.path
            and row.current.existence == entry.current.existence
            and content_bytes(row.current.content)
            == content_bytes(entry.current.content)
            and (retained := reversal_target(subject.operation_reversal, row)).kind
            == "note"
            and retained.identity == entry.identity
            and entry.identity is not None
            and (
                entry.identity.module_id,
                entry.identity.collection_id,
                entry.identity.item_id,
            )
            == (
                facts.incoming_identity.module_id,
                facts.incoming_identity.collection_id,
                subject.item_id,
            )
            and retained.target == entry.target
            and retained.status == "safe"
            and retained.target is not None
            and _target_safe(
                row.path,
                retained.target,
                tuple(
                    other
                    for other in facts.identity_inventory
                    if other.entry_id != entry.entry_id
                    and other.current.existence != "absent"
                    and _paths_collide(other.current.path, row.path)
                ),
            )
            for row in subject.operation_reversal.outputs
        )
        for subject in facts.subjects
    )


def reversal_document_target(subject):
    """Recognize an operation-local document key, never an imported identity."""
    proof = subject.operation_reversal
    if (
        proof is None
        or subject.attachment is not None
        or subject.facet != "content"
        or subject.output_role != "note"
        or subject.baseline.status != "unknown"
        or subject.baseline.content is not None
        or len(proof.outputs) != 1
        or len(proof.owned_targets) != 1
    ):
        return None
    row, target = proof.outputs[0], proof.owned_targets[0]
    if (
        row.path != subject.path
        or row.current != subject.current
        or row.target_id != subject.item_id
        or row.produced is None
        or row.target is None
        or row.produced.data == row.target.data
        or subject.incoming != row.target
        or (target.target_id, target.canonical_path) != (row.target_id, row.path)
        or target.kind != "note"
        or target.identity is not None
        or target.target != subject.source_target
    ):
        return None
    return target


def reversal_document_entry(facts, subject):
    """Bind the exact observed identityless document under retained proof."""
    target = reversal_document_target(subject)
    context = facts.link_context
    if target is None or facts.inventory != "complete" or context is None:
        return None
    entries = tuple(
        e for e in facts.identity_inventory if e.current.path == subject.path
    )
    documents = tuple(
        d for d in context.current_documents if d.source_path == subject.path
    )
    targets = tuple(
        t for t in context.current_targets if t.canonical_path == subject.path
    )
    states = tuple(
        s for s in context.current_target_facts if s.target_id == target.target_id
    )
    if len(entries) != 1 or len(documents) != 1 or targets != (target,):
        return None
    entry, document = entries[0], documents[0]
    if (
        entry.identity_state != "missing"
        or entry.identity is not None
        or entry.raw_identity is not None
        or entry.facet != "content"
        or entry.current != subject.current
        or entry.current.existence != "present"
        or entry.target != target.target
        or target.status != "safe"
        or document.document_id != target.target_id
        or document.content != entry.current.content
        or document.status != "supported"
        or document.inventory != "complete"
        or context.inventory != "complete"
        or len(states) != 1
        or states[0].existence != "present"
        or states[0].content != entry.current.content
        or not _target_safe(
            subject.path,
            entry.target,
            tuple(
                e
                for e in facts.identity_inventory
                if e.entry_id != entry.entry_id
                and e.current.existence != "absent"
                and _paths_collide(e.current.path, subject.path)
            ),
        )
    ):
        return None
    return entry


def reversal_safe(facts, subject, target_path):
    proof = subject.operation_reversal
    context = facts.link_context
    if proof is None:
        return True
    if (
        context is None
        or context.inventory != "complete"
        or target_path != subject.current.path
    ):
        return False
    if subject.attachment is None and not any(
        r.path == subject.current.path for r in proof.outputs
    ):
        return False
    owner = (
        facts.incoming_identity.module_id,
        facts.incoming_identity.collection_id,
        subject.item_id,
    )
    for row in proof.outputs:
        retained = reversal_target(proof, row)
        if subject.attachment is not None:
            if retained.kind != "resource" or retained.identity is not None:
                return False
        elif reversal_document_target(subject) is not None:
            if reversal_document_entry(facts, subject) is None:
                return False
        elif (
            retained.identity is None
            or (
                retained.identity.module_id,
                retained.identity.collection_id,
                retained.identity.item_id,
            )
            != owner
        ):
            return False
        entries = tuple(
            e for e in facts.identity_inventory if e.current.path == row.path
        )
        if len(entries) > 1 or (
            row.current.existence == "present" and len(entries) != 1
        ):
            return False
        for entry in entries:
            if (
                entry.current.existence != row.current.existence
                or content_bytes(entry.current.content)
                != content_bytes(row.current.content)
                or (
                    row.path != subject.current.path
                    and entry.identity is not None
                    and not reversal_physical_entry(facts, entry)
                )
            ):
                return False
        if row.path == subject.current.path and (
            row.current.existence != subject.current.existence
            or content_bytes(row.current.content)
            != content_bytes(subject.current.content)
        ):
            return False
        targets = tuple(
            t
            for t in context.current_targets
            if (t.target_id, t.canonical_path) == (row.target_id, row.path)
        )
        # A moved logical target can have one current registry path; retained
        # original facts still establish its other proven absent physical path.
        physical = bool(entries) and reversal_physical_entry(facts, entries[0])
        if not targets and (row.current.existence == "absent" or physical):
            targets = (retained,)
        if (
            len(targets) != 1
            or targets[0].target != retained.target
            or targets[0].identity != retained.identity
        ):
            return False
        target = targets[0]
        if (
            target.status != "safe"
            or retained.target is None
            or not _target_safe(
                row.path,
                retained.target,
                tuple(
                    e
                    for e in facts.identity_inventory
                    if e.current.path != row.path
                    and _paths_collide(e.current.path, row.path)
                ),
            )
        ):
            return False
        states = tuple(
            s for s in context.current_target_facts if s.target_id == row.target_id
        )
        registered = any(t.canonical_path == row.path for t in context.current_targets)
        if (
            row.current.existence == "present"
            and (registered or not physical)
            and (
                len(states) != 1
                or states[0].existence != "present"
                or content_bytes(states[0].content)
                != content_bytes(row.current.content)
            )
        ):
            return False
    return True


def review_owned_targets(plan, change_id, decision_id):
    """Return retained canonical output targets, never invent a version identity."""
    return review_owned_target_groups(plan, ((change_id, decision_id),))[0]


def review_owned_target_groups(plan, requests):
    """Return canonical owned targets in explicit (change, decision) query order."""
    from .resolution import validate_review
    from .selected_effects import _project_review_effects

    checked = validate_review(plan)
    if checked.status != "accepted" or not checked.plan.ready:
        raise ValueError("A canonical ready origin review is required")
    plan = checked.plan
    effects = None

    def selected_effects():
        nonlocal effects
        if effects is None:
            effects = _project_review_effects(plan)
        return effects

    return tuple(
        _owned_targets(plan, change_id, decision_id, selected_effects)
        for change_id, decision_id in requests
    )


def _owned_targets(plan, change_id, decision_id, selected_effects):
    approval = next(
        (
            a
            for a in plan.approvals
            if (a.change_id, a.decision_id) == (change_id, decision_id)
        ),
        None,
    )
    if approval is None:
        raise ValueError("Origin decision does not own this change")
    change = next(c for c in plan.proposal.changes if c.change_id == change_id)
    subject = reversal_subject(plan.producer_facts, change)
    if subject.operation_reversal is not None:
        return subject.operation_reversal.owned_targets
    if approval.attachment_candidate is not None:
        candidate = approval.attachment_candidate
        ids = {o.target_id for o in candidate.outputs}
        return tuple(t for t in candidate.targets if t.target_id in ids)
    action = next(a for a in plan.actions if a.decision_id == decision_id)
    context = plan.producer_facts.link_context
    targets = (
        () if context is None else context.current_targets + context.incoming_targets
    )
    if action.candidate is not None:
        targets = action.candidate.link_targets + targets
    effects = selected_effects()
    paths = {f.path for f in effects.files if f.subject_id == change.subject_id}
    if (
        change.rename_review is not None
        and change.rename_review.status == "accepted"
        and change.path in effects.remove_paths
    ):
        paths.add(change.path)
    owner = (
        plan.producer_facts.incoming_identity.module_id,
        plan.producer_facts.incoming_identity.collection_id,
        change.item_id,
    )
    selected = {}
    for path in sorted(paths):
        matching = tuple(
            t
            for t in targets
            if t.canonical_path == path
            and t.identity is not None
            and (t.identity.module_id, t.identity.collection_id, t.identity.item_id)
            == owner
        )
        if not matching or len({t.target_id for t in matching}) != 1:
            raise ValueError("Origin output has no unambiguous retained target")
        selected[path] = matching[0]
    return tuple(selected.values())


def review_owned_documents(plan):
    """Project exact identityless document ownership in one canonical pass.

    Unchanged document context conveys no ownership. The exact candidate,
    observed document, selected output and unique approval must all agree.
    Each returned target is bound to its originating change and decision.
    Resource ownership remains the separate review_owned_targets projection.
    """
    from .resolution import validate_review
    from .selected_effects import select_review_effects

    checked = validate_review(plan)
    if checked.status != "accepted" or not checked.plan.ready:
        raise ValueError("A canonical ready origin review is required")
    plan = checked.plan
    context = plan.producer_facts.link_context
    if context is None:
        return ()
    effects = select_review_effects(plan)
    selected = []
    for approval in plan.approvals:
        change = next(
            c for c in plan.proposal.changes if c.change_id == approval.change_id
        )
        subject = reversal_subject(plan.producer_facts, change)
        retained = reversal_document_target(subject)
        if retained is not None:
            files = tuple(f for f in effects.files if f.path == subject.path)
            if len(files) != 1 or files[0].subject_id != change.subject_id:
                raise ValueError("Reversed document lacks its selected owner")
            if content_bytes(files[0].content) == content_bytes(
                subject.current.content
            ):
                continue
            documents = tuple(
                d
                for d in context.incoming_documents
                if (d.document_id, d.source_path)
                == (retained.target_id, retained.canonical_path)
                and d.content == files[0].content
                and d.status == "supported"
                and d.inventory == "complete"
            )
            if (
                reversal_document_entry(plan.producer_facts, subject) is None
                or approval.domain != "reversal"
                or approval.choice != "reverse"
                or files[0].content != subject.operation_reversal.outputs[0].target
                or len(documents) != 1
            ):
                raise ValueError(
                    "Reversed document lacks exact retained byte authority"
                )
            selected.append((approval.change_id, approval.decision_id, retained))
            continue
        candidate = approval.attachment_candidate
        if candidate is None:
            continue
        for document in candidate.documents:
            prior = tuple(
                d
                for d in context.current_documents
                if d.document_id == document.document_id
            )
            if len(prior) != 1 or document.content.data == prior[0].content.data:
                continue
            targets = tuple(
                t for t in candidate.targets if t.canonical_path == document.source_path
            )
            if len(targets) != 1 or targets[0].identity is not None:
                continue
            target = targets[0]
            entries = tuple(
                e
                for e in plan.producer_facts.identity_inventory
                if e.current.path == document.source_path
            )
            owners = tuple(
                a
                for a in plan.approvals
                if a.attachment_candidate is not None
                and any(
                    d.document_id == document.document_id
                    and d.source_path == document.source_path
                    and d.content.data != prior[0].content.data
                    for d in a.attachment_candidate.documents
                )
            )
            files = tuple(f for f in effects.files if f.path == document.source_path)
            if (
                target.kind != "note"
                or target.target_id != document.document_id
                or document.source_path != prior[0].source_path
                or document.status != prior[0].status
                or document.status != "supported"
                or document.inventory != prior[0].inventory
                or document.inventory != "complete"
                or tuple(
                    t
                    for t in context.current_targets
                    if t.target_id == target.target_id
                )
                != (target,)
                or len(entries) != 1
                or entries[0].identity_state != "missing"
                or entries[0].identity is not None
                or entries[0].raw_identity is not None
                or entries[0].facet != "content"
                or entries[0].current.content != prior[0].content
                or entries[0].target != target.target
                or owners != (approval,)
                or len(files) != 1
                or files[0].subject_id != change.subject_id
                or files[0].content != document.content
            ):
                raise ValueError(
                    "Changed document lacks unique retained selected authority"
                )
            selected.append((approval.change_id, approval.decision_id, target))
    return tuple(selected)
