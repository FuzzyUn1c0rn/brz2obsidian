"""Derive effective selected files and check cross-choice link coherence."""

from brz2obsidian.content_fingerprints import canonical_equal
from brz2obsidian.content_values import same_content
from brz2obsidian.contracts import QUALIFIED_OUTPUT_FORMATS, LinkTargetFacts
from brz2obsidian.core.link_meanings import matches_exact_note_path, resolve_occurrence
from brz2obsidian.core.link_validation import _validate_link_document
from brz2obsidian.core.review_appearance import provider_chain_blockers
from brz2obsidian.core.review_composition import (
    automatic_composed_document,
    automatic_reference_document,
)
from brz2obsidian.core.review_links import (
    bound_resource_record,
    collection_asset_effect,
    current_baseline,
    current_keep_needs_proof,
    current_lookup_coverage,
    known_result_document,
    onboarding_current_context,
)

from .reversals import (
    content_bytes,
    reversal_document_target,
    reversal_subject,
    reversal_target,
    selected_reversal_outputs,
)
from .text_candidates import validate_text_candidate


def _promoted_reservation(occurrence, actual, adopted_ids):
    before = occurrence.meaning
    query = occurrence.query
    if (
        query is None
        or before.path is None
        or not matches_exact_note_path(query, before.path)
        or actual.status != "resolved"
        or actual.target_identity is None
    ):
        return False
    identity = before.target_identity
    if (
        before.status == "resolved"
        and identity is None
        and before.target_id in adopted_ids
    ):
        identity = actual.target_identity
    elif before.status != "intentionally_uncreated":
        return False
    return (
        before.model_copy(
            update={
                "status": "resolved",
                "target_identity": identity,
                "target_version": actual.target_version,
            }
        )
        == actual
    )


def _onboarding_attachment_is_current(approval, subject, context):
    candidate = approval.attachment_candidate
    if candidate is None:
        return True
    candidate_states = {s.target_id: s for s in candidate.target_facts}
    current_states = {s.target_id: s for s in context.current_target_facts}
    return not (
        approval.attachment_selection.link_choices
        or len(candidate.outputs) != 1
        or len(candidate.targets) != len(context.current_targets)
        or {t.target_id: t for t in candidate.targets}
        != {t.target_id: t for t in context.current_targets}
        or len(candidate.target_facts) != len(context.current_target_facts)
        or candidate_states.keys() != current_states.keys()
        or any(
            not canonical_equal(state, current_states[target_id])
            for target_id, state in candidate_states.items()
        )
        or len(candidate.documents) != len(context.current_documents)
        or {d.document_id: d for d in candidate.documents}
        != {d.document_id: d for d in context.current_documents}
        or any(
            o.path != subject.current.path
            or not canonical_equal(o.content, subject.current.content)
            for o in candidate.outputs
        )
    )


def _onboarding_current_effects(facts, proposal, actions, approvals):
    context = facts.link_context
    if not onboarding_current_context(facts):
        return False
    if any(
        a.domain == "identity" or a.domain == "rename" and a.choice != "keep_path"
        for a in actions
    ):
        return False
    approved = {a.change_id: a for a in approvals}
    action_by_id = {a.decision_id: a for a in actions}
    for change in proposal.changes:
        subject = next(
            s
            for s in facts.subjects
            if (s.item_id, s.facet) == (change.item_id, change.facet)
        )
        approval = approved.get(change.change_id)
        if approval is None and change.requires_decision:
            continue
        if change.target_path != subject.current.path:
            return False
        if approval is not None:
            action = action_by_id.get(approval.decision_id)
            if (
                action is None
                or action.candidate is not None
                or approval.choice != "current"
                or approval.source_accepted
            ):
                return False
            if not _onboarding_attachment_is_current(approval, subject, context):
                return False
        content = change.result if approval is None else approval.result
        path = change.target_path if approval is None else approval.target_path
        if (
            not canonical_equal(content, subject.current.content)
            or path != subject.current.path
        ):
            return False
    return True


def _renew_selected_current_resources(
    facts, authority, document, resolved, targets, states, current_resources
):
    """Recertify unchanged incoming bytes after a later exact Current selection."""
    if authority is None:
        return document
    change, candidate, ordinal = authority
    if not canonical_equal(document, candidate.links):
        return document
    prior_targets = {target.target_id: target for target in candidate.link_targets}
    selected_targets = {target.target_id: target for target in targets}
    occurrences = []
    changed = False
    for occurrence, actual in zip(document.occurrences, resolved, strict=True):
        target_id = occurrence.meaning.target_id
        before, after = prior_targets.get(target_id), selected_targets.get(target_id)
        if (
            current_resources.get(target_id, -1) > ordinal
            and before is not None
            and after is not None
            and before.kind == after.kind == "resource"
            and before.status == after.status == "safe"
            and canonical_equal(
                (
                    before.target_id,
                    before.identity,
                    before.canonical_path,
                    before.target,
                ),
                (after.target_id, after.identity, after.canonical_path, after.target),
            )
            and occurrence.meaning.status == actual.status == "resolved"
            and occurrence.meaning != actual
            and occurrence.meaning.model_copy(
                update={"target_version": actual.target_version}
            )
            == actual
        ):
            occurrence = occurrence.model_copy(update={"meaning": actual})
            changed = True
        occurrences.append(occurrence)
    if not changed:
        return document
    renewed = document.model_copy(update={"occurrences": tuple(occurrences)})
    proof = candidate.model_copy(
        update={
            "links": renewed,
            "link_targets": targets,
            "link_target_facts": states,
        }
    )
    return (
        renewed
        if validate_text_candidate(facts, change, proof, "incoming")
        else document
    )


class _SelectedTargetEffects:
    def __init__(self, context):
        self.targets = {t.target_id: t for t in context.current_targets}
        self.states = {s.target_id: s for s in context.current_target_facts}
        self.writes = {}
        self.changed_ids = set()
        self.adopted_ids = set()
        self.edited_navigation_ids = set()
        self.current_resources = {}

    def write(self, target, content, path, state, add):
        previous = self.writes.get(target.target_id)
        if previous is not None and (content_bytes(previous[0]), previous[1]) != (
            content_bytes(content),
            path,
        ):
            add("selected_output_conflict")
            return
        self.writes[target.target_id] = (content, path)
        current = self.targets.get(target.target_id)
        old_state = self.states.get(target.target_id)
        if current != target or old_state != state:
            self.changed_ids.add(target.target_id)
        self.targets[target.target_id] = target
        if state is None or not canonical_equal(state.content, content):
            self.states.pop(target.target_id, None)
        else:
            self.states[target.target_id] = state


class _SelectedDocumentEffects:
    def __init__(self, context, composition):
        self.documents = {d.document_id: d for d in context.current_documents}
        self.original_documents = dict(self.documents)
        self.proof_documents = {}
        self.explicit_documents = set()
        self.operation_documents = set()
        self.incoming_authorities = {}
        self.composed_documents = dict(composition.documents)


def _retain_reversal_document(
    subject, context, approval, row, content, target_id, document_effects, add
):
    if reversal_document_target(subject) is not None:
        source_documents = (
            context.incoming_documents
            if approval is not None and approval.choice == "reverse"
            else context.current_documents
        )
        retained_documents = tuple(
            d
            for d in source_documents
            if d.source_path == row.path
            and d.document_id == target_id
            and canonical_equal(d.content, content)
        )
        if len(retained_documents) != 1:
            add("selected_link_context_conflict")
            return False
        document_effects.documents = {
            key: doc
            for key, doc in document_effects.documents.items()
            if doc.source_path != row.path
        }
        document_effects.documents[target_id] = retained_documents[0]
        document_effects.explicit_documents.add(target_id)
        document_effects.operation_documents.add(target_id)
    return True


def _apply_reversal_group(
    facts,
    change,
    approval,
    candidate,
    target_id,
    members,
    registry,
    document_effects,
    add,
):
    context = facts.link_context
    present = [(row, content) for row, content in members if content is not None]
    if len(present) > 1:
        add("selected_link_context_conflict")
        return
    subject = reversal_subject(facts, change)
    if present:
        row, content = present[0]
        target = reversal_target(subject.operation_reversal, row)
        state = next(
            (
                s
                for s in (() if candidate is None else candidate.link_target_facts)
                + context.current_target_facts
                + context.incoming_target_facts
                if s.target_id == target_id
                and s.content is not None
                and same_content(s.content, content)
            ),
            None,
        )
    else:
        row = members[0][0]
        content = None
        target = registry.targets.get(
            target_id, reversal_target(subject.operation_reversal, row)
        )
        state = LinkTargetFacts(
            schema_id="brz2obsidian.link-target-facts",
            schema_version=1,
            target_id=target_id,
            existence="missing",
            content=None,
            fragments=(),
            anchors=(),
            structure=None,
            memberships=(),
            interpretation="supported",
        )
    registry.write(target, content, target.canonical_path, state, add)
    if not _retain_reversal_document(
        subject, context, approval, row, content, target_id, document_effects, add
    ):
        return
    absent = {r.path for r, data in members if data is None}
    document_effects.documents = {
        key: doc
        for key, doc in document_effects.documents.items()
        if doc.source_path not in absent
    }
    if (
        candidate is not None
        and present
        and candidate.links.source_path == row.path
        and same_content(candidate.content, content)
    ):
        document_effects.documents = {
            key: doc
            for key, doc in document_effects.documents.items()
            if doc.source_path != row.path
        }
        document_effects.documents[candidate.links.document_id] = candidate.links
        document_effects.explicit_documents.add(candidate.links.document_id)


def _apply_reversal_outputs(
    facts, change, approval, candidate, selected, registry, document_effects, add
):
    groups = {}
    for row, content in selected:
        groups.setdefault(row.target_id, []).append((row, content))
    for target_id, members in groups.items():
        _apply_reversal_group(
            facts,
            change,
            approval,
            candidate,
            target_id,
            members,
            registry,
            document_effects,
            add,
        )


def _apply_retired_classification_views(proposal, registry, document_effects, add):
    targets = {row.canonical_path: row for row in registry.targets.values()}
    for change in proposal.changes:
        if change.provenance.rule != "classification_view_retired":
            continue
        target = targets.get(change.path)
        if target is None:
            add("selected_link_context_conflict")
            continue
        registry.write(target, None, change.path, None, add)
        document_effects.documents.pop(target.target_id, None)


def _apply_selected_reversals(
    facts, proposal, approved, action_by_id, registry, document_effects, add
):
    for change in proposal.changes:
        approval = approved.get(change.change_id)
        if approval is None and change.requires_decision:
            continue
        selected = selected_reversal_outputs(facts, change, approval)
        action = None if approval is None else action_by_id.get(approval.decision_id)
        candidate = None if action is None else action.candidate
        _apply_reversal_outputs(
            facts,
            change,
            approval,
            candidate,
            selected,
            registry,
            document_effects,
            add,
        )


def _write_attachment_outputs(
    facts, change, approval, candidate, action_by_id, action_order, registry, add
):
    if (
        facts.format_operation.kind == "attachment_cleanup"
        and approval.choice == "remove"
    ):
        subject = reversal_subject(facts, change)
        target_id = subject.attachment.current_target_id
        target = next(t for t in candidate.targets if t.target_id == target_id)
        state = next(s for s in candidate.target_facts if s.target_id == target_id)
        registry.write(target, None, change.path, state, add)
    selection_action = action_by_id.get(approval.decision_id)
    for output in candidate.outputs:
        target = next(t for t in candidate.targets if t.target_id == output.target_id)
        state = next(
            (s for s in candidate.target_facts if s.target_id == output.target_id),
            None,
        )
        registry.write(target, output.content, output.path, state, add)
        if (
            facts.format_operation.automatic_merge
            and approval.provenance == "explicit_user"
            and selection_action is not None
            and selection_action.domain == approval.domain == "attachment"
            and selection_action.choice
            == approval.choice
            == approval.attachment_selection.choice
            == "current"
            and len(candidate.outputs) == 1
            and output.path == change.path
            and canonical_equal(output.content, change.current)
        ):
            registry.current_resources[output.target_id] = action_order[
                approval.decision_id
            ]


def _apply_attachment_documents(candidate, relevant, registry, document_effects, add):
    for document in candidate.documents:
        composed = document_effects.composed_documents.get(document.document_id)
        if composed is not None:
            document = composed[0]
        prior = document_effects.original_documents.get(document.document_id)
        changed = prior is None or (prior.content, prior.source_path) != (
            document.content,
            document.source_path,
        )
        if changed:
            matching = tuple(
                t for t in candidate.targets if t.canonical_path == document.source_path
            )
            if len(matching) != 1:
                add("selected_output_conflict")
                continue
            target = matching[0]
            state = next(
                (s for s in candidate.target_facts if s.target_id == target.target_id),
                None,
            )
            if composed is not None:
                state = composed[1]
            registry.write(target, document.content, document.source_path, state, add)
            document_effects.explicit_documents.add(document.document_id)
        if changed or (
            document.document_id in relevant
            and document.document_id not in document_effects.operation_documents
        ):
            document_effects.proof_documents[document.document_id] = document


def _apply_selected_attachments(
    facts,
    proposal,
    approvals,
    action_by_id,
    action_order,
    registry,
    document_effects,
    add,
):
    for approval in approvals:
        candidate = approval.attachment_candidate
        if candidate is None:
            continue
        change = next(c for c in proposal.changes if c.change_id == approval.change_id)
        relevant = {link.document_id for link in change.attachment_review.links}
        relevant.update(
            choice.document_id for choice in approval.attachment_selection.link_choices
        )
        _write_attachment_outputs(
            facts,
            change,
            approval,
            candidate,
            action_by_id,
            action_order,
            registry,
            add,
        )
        _apply_attachment_documents(
            candidate, relevant, registry, document_effects, add
        )
    document_effects.documents.update(document_effects.proof_documents)


def _apply_automatic_text(
    facts,
    change,
    subject,
    approval,
    approvals,
    content,
    selected_path,
    registry,
    document_effects,
    add,
):
    context = facts.link_context
    composed = automatic_composed_document(
        facts, change, approval, document_effects.composed_documents
    )
    if composed is not None:
        document, state = composed
        document_effects.documents[document.document_id] = document
        document_effects.proof_documents[document.document_id] = document
        if not canonical_equal(document.content, subject.current.content):
            targets_for_path = tuple(
                t for t in context.current_targets if t.canonical_path == selected_path
            )
            if len(targets_for_path) != 1:
                add("selected_link_context_conflict")
            else:
                registry.write(
                    targets_for_path[0], document.content, selected_path, state, add
                )
        return True
    reference = automatic_reference_document(facts, change, approval, approvals)
    if reference is not None:
        document_effects.documents[reference.document_id] = reference
        document_effects.proof_documents[reference.document_id] = reference
        return True
    return (
        facts.format_operation.kind == "attachment_cleanup"
        and approval is None
        and not change.requires_decision
        and change.disposition == "preserve_vault"
        and selected_path == subject.current.path
        and canonical_equal(content, subject.current.content)
        and any(
            document.document_id in document_effects.explicit_documents
            and document.source_path == selected_path
            and not canonical_equal(document.content, content)
            and (prior := document_effects.original_documents.get(document.document_id))
            is not None
            and canonical_equal(
                (prior.content, prior.source_path), (content, selected_path)
            )
            for document in document_effects.proof_documents.values()
        )
    )


def _selected_text_evidence(
    facts, change, approval, candidate, content, selected_path, composed_documents
):
    context = facts.link_context
    known = (
        known_result_document(facts, change)
        if approval is None or approval.choice == "approve"
        else None
    )
    if candidate is not None:
        composed = composed_documents.get(candidate.links.document_id)
        document = candidate.links if composed is None else composed[0]
        if composed is not None:
            content = document.content
        source_targets = candidate.link_targets
        source_states = (
            candidate.link_target_facts
            if composed is None
            else tuple(
                state
                for state in candidate.link_target_facts
                if state.target_id != composed[1].target_id
            )
            + (composed[1],)
        )
    elif known is not None:
        document, source_targets, source_states = known
    else:
        matching = tuple(
            d
            for d in context.current_documents
            if canonical_equal(d.content, content) and d.source_path == selected_path
        )
        document = matching[0] if len(matching) == 1 else None
        source_targets = context.current_targets
        source_states = context.current_target_facts
    return document, content, source_targets, source_states


def _write_selected_text_target(
    context,
    change,
    subject,
    approval,
    candidate,
    selected_path,
    source_targets,
    source_states,
    content,
    registry,
    add,
):
    observed_path = (
        change.rename_review.current_path
        if candidate is not None
        and approval is not None
        and approval.choice == "current"
        and change.rename_review is not None
        and change.rename_review.status == "accepted"
        else subject.current.path
    )
    own = tuple(t for t in context.current_targets if t.canonical_path == observed_path)
    if len(own) == 1:
        target = own[0]
        if change.identity_review.reason == "reserved_path_adoption":
            promoted = tuple(
                t
                for t in source_targets
                if t.target_id == target.target_id
                and t.canonical_path == selected_path
                and candidate is not None
                and t.identity == candidate.identity
            )
            if len(promoted) != 1:
                add("selected_link_context_conflict")
                return False
            target = promoted[0]
            registry.adopted_ids.add(target.target_id)
        if selected_path != target.canonical_path:
            supplied = tuple(
                t
                for t in source_targets
                if t.target_id == target.target_id and t.canonical_path == selected_path
            )
            if len(supplied) != 1:
                add("selected_link_context_conflict")
                return False
            target = supplied[0]
        state = next(
            (
                s
                for s in source_states
                if s.target_id == target.target_id
                and canonical_equal(s.content, content)
            ),
            None,
        )
        if state is None:
            state = next(
                (
                    s
                    for s in context.current_target_facts
                    + context.incoming_target_facts
                    if s.target_id == target.target_id
                    and canonical_equal(s.content, content)
                ),
                None,
            )
        registry.write(target, content, selected_path, state, add)
        if subject.moved_navigation and approval is not None:
            registry.edited_navigation_ids.add(target.target_id)
    return True


def _record_selected_text_document(
    context, change, subject, document, content, selected_path, document_effects, add
):
    if document is None:
        if (
            any(
                d.source_path == subject.current.path for d in context.current_documents
            )
            or change.requires_decision
        ):
            add("selected_link_context_conflict")
        return False
    if document.source_path != selected_path or not canonical_equal(
        document.content, content
    ):
        add("selected_link_context_conflict")
        return False
    existing = document_effects.documents.get(document.document_id)
    if (
        document.document_id in document_effects.explicit_documents
        and existing is not None
        and not canonical_equal(
            (existing.content, existing.source_path), (content, selected_path)
        )
    ):
        add("selected_output_conflict")
    document_effects.documents[document.document_id] = document
    return True


def _record_incoming_authority(
    facts,
    change,
    subject,
    approval,
    action,
    candidate,
    content,
    document,
    action_order,
    document_effects,
):
    if (
        facts.format_operation.automatic_merge
        and approval is not None
        and approval.provenance == "explicit_user"
        and action is not None
        and action.domain == "text"
        and action.choice == approval.choice == "incoming"
        and candidate is not None
        and canonical_equal(content, change.incoming)
    ):
        document_effects.incoming_authorities[document.document_id] = (
            change,
            candidate,
            action_order[action.decision_id],
        )
    elif (
        facts.format_operation.automatic_merge
        and approval is None
        and change.disposition == "compatible"
        and not change.requires_decision
        and subject.baseline.status == "known"
        and subject.current.existence == "present"
        and same_content(subject.current.content, subject.baseline.content)
        and same_content(content, change.incoming)
        and subject.automatic_result is not None
        and same_content(subject.automatic_result.content, change.incoming)
        and validate_text_candidate(facts, change, subject.automatic_result, "incoming")
        and canonical_equal(document, subject.automatic_result.links)
    ):
        document_effects.incoming_authorities[document.document_id] = (
            change,
            subject.automatic_result,
            -1,
        )


def _apply_text_change(
    facts,
    change,
    approval,
    approvals,
    action_by_id,
    action_order,
    registry,
    document_effects,
    add,
):
    if approval is not None and approval.attachment_candidate is not None:
        return
    content = change.result if approval is None else approval.result
    if content is None:
        return
    subject = next(
        s
        for s in facts.subjects
        if (s.item_id, s.facet) == (change.item_id, change.facet)
    )
    if subject.operation_reversal is not None:
        return
    if subject.attachment is not None:
        return
    selected_path = change.target_path if approval is None else approval.target_path
    asset = collection_asset_effect(facts, change)
    if asset is not None and approval is None:
        target, state = asset
        registry.write(target, content, selected_path, state, add)
        return

    if _apply_automatic_text(
        facts,
        change,
        subject,
        approval,
        approvals,
        content,
        selected_path,
        registry,
        document_effects,
        add,
    ):
        return
    action = None if approval is None else action_by_id.get(approval.decision_id)
    candidate = None if action is None else action.candidate
    document, content, source_targets, source_states = _selected_text_evidence(
        facts,
        change,
        approval,
        candidate,
        content,
        selected_path,
        document_effects.composed_documents,
    )
    if not _write_selected_text_target(
        facts.link_context,
        change,
        subject,
        approval,
        candidate,
        selected_path,
        source_targets,
        source_states,
        content,
        registry,
        add,
    ):
        return
    if _record_selected_text_document(
        facts.link_context,
        change,
        subject,
        document,
        content,
        selected_path,
        document_effects,
        add,
    ):
        _record_incoming_authority(
            facts,
            change,
            subject,
            approval,
            action,
            candidate,
            content,
            document,
            action_order,
            document_effects,
        )
        if approval is not None or change.provenance.rule == "remembered_keep":
            document_effects.explicit_documents.add(document.document_id)


def _apply_selected_text(
    facts,
    proposal,
    approved,
    approvals,
    action_by_id,
    action_order,
    registry,
    document_effects,
    add,
):
    for change in proposal.changes:
        approval = approved.get(change.change_id)
        _apply_text_change(
            facts,
            change,
            approval,
            approvals,
            action_by_id,
            action_order,
            registry,
            document_effects,
            add,
        )


def _renew_document_navigation(
    document,
    prior,
    resolved,
    renew_unselected,
    attachment_links,
    output_format,
    registry,
):
    # A proven reversal document can also retain a destination's later prose.
    # A retained note's unrelated prose version is not a link redirect. Resource choices
    # and path/identity/fragment changes still require their explicit selected proof.
    occurrences = []
    for occurrence, actual in zip(document.occurrences, resolved, strict=True):
        target = registry.targets.get(actual.target_id)
        if (
            target is not None
            and target.kind != "resource"
            and (
                renew_unselected
                or actual.target_id in registry.edited_navigation_ids
                or prior is not None
                and (document.document_id, occurrence.occurrence_id)
                not in attachment_links
                and any(
                    (old.raw, old.syntax, old.embedded, old.query, old.meaning)
                    == (
                        occurrence.raw,
                        occurrence.syntax,
                        occurrence.embedded,
                        occurrence.query,
                        occurrence.meaning,
                    )
                    for old in prior.occurrences
                )
            )
            and (
                occurrence.meaning.model_copy(
                    update={"target_version": actual.target_version}
                )
                == actual
                or output_format == 9
                and _promoted_reservation(occurrence, actual, registry.adopted_ids)
            )
        ):
            occurrence = occurrence.model_copy(update={"meaning": actual})
        occurrences.append(occurrence)
    document = document.model_copy(update={"occurrences": tuple(occurrences)})
    return document


def _unrelated_import_document(facts, document):
    return (
        facts.format_operation.kind == "collection_import"
        and (
            document.source_path,
            document.content.identity.sha256,
        )
        in facts.link_context.import_unrelated_documents
    )


def _retained_import_links(context, document):
    selection = (document.source_path, document.content.identity.sha256)
    if selection not in context.import_finished_outputs:
        return {}
    matches = tuple(
        row
        for row in context.incoming_documents
        if row.source_path == document.source_path
        and row.document_id == document.document_id
        and same_content(row.content, document.content)
    )
    return (
        {row.occurrence_id: row for row in matches[0].occurrences}
        if len(matches) == 1
        else {}
    )


def _renew_import_connections(facts, document, prior, resolved):
    if (
        facts.format_operation.kind != "collection_import"
        or prior is None
        or prior.content != document.content
        or prior.source_path != document.source_path
    ):
        return document
    choices = {
        (row.occurrence_id, row.target_path, row.target_sha256)
        for row in facts.link_context.import_link_connections
        if row.document_path == document.source_path
        and row.document_sha256 == document.content.identity.sha256
    }
    old_occurrences = {row.occurrence_id: row for row in prior.occurrences}
    retained_links = _retained_import_links(facts.link_context, document)
    occurrences = []
    for row, actual in zip(document.occurrences, resolved, strict=True):
        ordinal = row.occurrence_id.rsplit(":link:", 1)[-1]
        key = (
            f"{document.source_path}:link:{ordinal}",
            actual.path,
            actual.target_version,
        )
        if (
            old_occurrences.get(row.occurrence_id) == row
            and row.meaning.status == "missing"
            and actual.status == "resolved"
            and (
                key in choices
                or retained_links.get(row.occurrence_id)
                == row.model_copy(update={"meaning": actual})
            )
        ):
            row = row.model_copy(update={"meaning": actual})
        occurrences.append(row)
    return document.model_copy(update={"occurrences": tuple(occurrences)})


def _validate_effect_document(
    facts,
    final_targets,
    final_states,
    attachment_links,
    attachment_documents,
    document,
    registry,
    document_effects,
    add,
):
    context = facts.link_context
    prior = document_effects.original_documents.get(document.document_id)
    unchanged_current = document == prior
    relevant = (
        document.document_id in document_effects.explicit_documents
        or document.document_id in document_effects.proof_documents
    )
    resolved = tuple(
        resolve_occurrence(o, final_targets, final_states, context.inventory)
        for o in document.occurrences
    )
    relevant |= any(
        m.target_id in registry.changed_ids
        or bool(set(m.candidates) & registry.changed_ids)
        for m in resolved
    )
    relevant |= any(
        o.meaning.target_id in registry.changed_ids
        or bool(set(o.meaning.candidates) & registry.changed_ids)
        for o in document.occurrences
    )
    if not relevant:
        return
    ordinary_renewal = (
        document.document_id not in document_effects.explicit_documents
        and document.document_id not in document_effects.proof_documents
    ) or (
        facts.format_operation.kind == "format_transition"
        and unchanged_current
        and document.document_id not in document_effects.proof_documents
    )
    operation_renewal = document.document_id in document_effects.operation_documents
    if (
        ordinary_renewal
        or operation_renewal
        or document.document_id in attachment_documents
        or any(m.target_id in registry.edited_navigation_ids for m in resolved)
    ):
        document = _renew_document_navigation(
            document,
            prior,
            resolved,
            ordinary_renewal or operation_renewal,
            attachment_links,
            facts.incoming_identity.output_format,
            registry,
        )
    document = _renew_selected_current_resources(
        facts,
        document_effects.incoming_authorities.get(document.document_id),
        document,
        resolved,
        final_targets,
        final_states,
        registry.current_resources,
    )
    document = _renew_import_connections(facts, document, prior, resolved)
    validation = _validate_link_document(
        document,
        expected_content=document.content,
        expected_path=document.source_path,
        targets=final_targets,
        target_facts=final_states,
        inventory=context.inventory,
        allow_existing_unsupported=(
            prior is not None
            and prior.content == document.content
            and prior.source_path == document.source_path
            and _unrelated_import_document(facts, document)
        ),
        baseline=None
        if prior is None or prior.source_path != document.source_path
        else current_baseline(context, document),
        affected_target_ids=tuple(
            registry.changed_ids
            | (
                {m.target_id for m in resolved if m.target_id is not None}
                if document.document_id in document_effects.explicit_documents
                and not (
                    facts.format_operation.kind in ("onboarding", "format_transition")
                    and unchanged_current
                )
                else set()
            )
        ),
    )
    if not validation.valid:
        add("selected_link_context_conflict")


def _validate_selected_documents(
    facts, approvals, final_targets, final_states, registry, document_effects, add
):
    attachment_links = {
        (choice.document_id, choice.occurrence_id)
        for approval in approvals
        if approval.attachment_selection is not None
        for choice in approval.attachment_selection.link_choices
    }
    attachment_documents = (
        {key[0] for key in attachment_links}
        if facts.format_operation.kind == "source_update"
        else set()
    )
    for document in document_effects.documents.values():
        _validate_effect_document(
            facts,
            final_targets,
            final_states,
            attachment_links,
            attachment_documents,
            document,
            registry,
            document_effects,
            add,
        )


def selected_effect_blockers(facts, proposal, actions, approvals, *, composition):
    context = facts.link_context
    if context is None:
        return (
            ("current_link_coverage_unavailable",)
            if (
                selected_effect_active(facts, proposal, approvals)
                or any(
                    c.provenance.rule == "remembered_keep"
                    and current_keep_needs_proof(facts, c)
                    for c in proposal.changes
                )
            )
            else ()
        )
    if facts.format_operation.kind in ("onboarding", "format_transition") and any(
        d.status != "supported" for d in context.current_documents
    ):
        return (
            ()
            if _onboarding_current_effects(facts, proposal, actions, approvals)
            else ("onboarding_opaque_effects_unsafe",)
        )
    registry = _SelectedTargetEffects(context)
    document_effects = _SelectedDocumentEffects(context, composition)
    approved = {a.change_id: a for a in approvals}
    action_by_id = {a.decision_id: a for a in actions}
    action_order = {a.decision_id: index for index, a in enumerate(actions)}
    blockers = []

    def add(code):
        if code not in blockers:
            blockers.append(code)

    if composition.conflict:
        add("selected_link_context_conflict")

    if any(
        c.provenance.rule == "remembered_keep" and current_keep_needs_proof(facts, c)
        for c in proposal.changes
    ) and not current_lookup_coverage(facts):
        add("current_link_coverage_unavailable")

    _apply_retired_classification_views(proposal, registry, document_effects, add)
    _apply_selected_reversals(
        facts, proposal, approved, action_by_id, registry, document_effects, add
    )
    _apply_selected_attachments(
        facts,
        proposal,
        approvals,
        action_by_id,
        action_order,
        registry,
        document_effects,
        add,
    )
    _apply_selected_text(
        facts,
        proposal,
        approved,
        approvals,
        action_by_id,
        action_order,
        registry,
        document_effects,
        add,
    )
    if (
        registry.changed_ids or selected_effect_active(facts, proposal, approvals)
    ) and not current_note_coverage(facts):
        add("current_link_coverage_unavailable")

    final_targets = tuple(registry.targets.values())
    final_states = tuple(registry.states.values())
    if facts.incoming_identity.output_format in QUALIFIED_OUTPUT_FORMATS:
        for code in provider_chain_blockers(
            context.current_target_facts,
            final_states,
            current_targets=context.current_targets,
            selected_targets=final_targets,
        ):
            add(code)
    _validate_selected_documents(
        facts, approvals, final_targets, final_states, registry, document_effects, add
    )
    return tuple(blockers)


def current_note_coverage(facts):
    """An omitted registry entry cannot hide an independently observed potential note."""
    context = facts.link_context
    if not current_lookup_coverage(facts):
        return False
    for entry in facts.identity_inventory:
        if entry.current.existence == "unknown":
            return False
        if entry.current.existence == "absent":
            continue
        resources = tuple(
            t
            for t in context.current_targets
            if t.kind == "resource" and t.canonical_path == entry.current.path
        )
        resource = False
        if len(resources) == 1:
            (target,) = resources
            states = tuple(
                s
                for s in context.current_target_facts
                if s.target_id == target.target_id
            )
            resource = len(states) == 1 and bound_resource_record(
                facts, entry, target, states[0]
            )
        if resource:
            continue
        documents = tuple(
            d
            for d in context.current_documents
            if d.source_path == entry.current.path
            and canonical_equal(d.content, entry.current.content)
        )
        if (
            len(documents) != 1
            or (
                documents[0].status != "supported"
                and not _unrelated_import_document(facts, documents[0])
            )
            or documents[0].inventory != "complete"
        ):
            return False
    return True


def selected_effect_active(facts, proposal, approvals):
    approved = {a.change_id: a for a in approvals}
    for change in proposal.changes:
        approval = approved.get(change.change_id)
        if approval is not None and approval.choice == "reverse":
            return True
        if (
            approval is not None
            and approval.choice == "remove"
            and facts.format_operation.kind == "attachment_cleanup"
        ):
            return True
        if approval is not None and approval.attachment_candidate is not None:
            if any(
                not any(
                    e.current.path == o.path
                    and canonical_equal(e.current.content, o.content)
                    for e in facts.identity_inventory
                )
                for o in approval.attachment_candidate.outputs
            ):
                return True
            continue
        content = change.result if approval is None else approval.result
        if content is None:
            continue
        subject = next(
            s
            for s in facts.subjects
            if (s.item_id, s.facet) == (change.item_id, change.facet)
        )
        path = change.target_path if approval is None else approval.target_path
        if path != subject.current.path or not canonical_equal(
            content, subject.current.content
        ):
            return True
        if (
            approval is not None
            and approval.domain in ("mapping", "format")
            and approval.choice in ("incoming", "edited", "approve")
        ):
            return True
    return False
