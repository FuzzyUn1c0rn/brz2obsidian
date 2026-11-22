"""Validate an offered binary selection and exact per-occurrence document edits."""

from dataclasses import dataclass, replace

from pydantic import ValidationError

from brz2obsidian.content_fingerprints import (
    ChildWork,
    CompletedWork,
    canonical_equal,
    drive_inline,
)
from brz2obsidian.content_values import content_key, require_inline, same_content
from brz2obsidian.contracts import (
    AttachmentCandidate,
    AttachmentCandidateValidation,
    AttachmentSelection,
    AttachmentValidationFinding,
    LinkValidationBaseline,
    ReconciliationInput,
)

from .identity import _paths_collide
from .link_validation import _validate_link_document
from .reference_targets import validate_targets
from .review_links import consumed_context, onboarding_current_context
from .structures import validate_structure_facts


def _payloads(outputs):
    return tuple(
        (o.target_id, o.path, content_key(o.content), o.content_version)
        for o in outputs
    )


def _bound_attachment_selection(facts, selection, candidate, proposal, add):
    changes = tuple(
        c
        for c in proposal.changes
        if (c.item_id, c.facet) == (selection.item_id, selection.facet)
        and c.attachment_review is not None
    )
    if len(changes) != 1:
        add("attachment_stale_selection")
        return None
    (change,) = changes
    if (
        selection.proposal_id != proposal.proposal_id
        or selection.generation != proposal.generation
        or selection.reviewed_change_id != change.change_id
        or selection.reviewed_assumptions != change.assumptions
    ):
        add("attachment_stale_selection")
        return None
    if (
        any(
            f.blocking and f.subject_id in (None, change.subject_id)
            for f in proposal.findings
        )
        or change.identity_review.status != "matched"
        or change.format_review is not None
        and not (
            facts.format_operation.kind in ("onboarding", "format_transition")
            and selection.choice == "current"
        )
        or change.target_path != change.path
        or change.disposition in ("stale", "refused", "identity_resolution")
    ):
        add("attachment_unsafe_input")
        return None
    subject = next(
        s
        for s in facts.subjects
        if (s.item_id, s.facet) == (selection.item_id, selection.facet)
    )
    if (
        subject.structure is not None
        and validate_structure_facts(
            subject,
            facts.baseline_identity,
            facts.incoming_identity,
            source_version=facts.format_operation.baseline_source_version,
        )
        is not None
    ):
        add("attachment_unsafe_input")
        return None
    alternative = next(
        (
            a
            for a in change.attachment_review.alternatives
            if a.choice == selection.choice
        ),
        None,
    )
    if alternative is None or not alternative.eligible:
        add("attachment_unavailable")
        return None

    if _payloads(candidate.outputs) != _payloads(alternative.outputs):
        add("attachment_payload_mismatch")
        return None
    return change, subject, alternative


def _attachment_registry_complete(context, candidate, targets, states, output_ids):
    expected_ids = {t.target_id for t in context.current_targets} | output_ids
    required_states = {s.target_id for s in context.current_target_facts} | output_ids
    return not (
        len(targets) != len(candidate.targets)
        or set(targets) != expected_ids
        or len(states) != len(candidate.target_facts)
        or set(states) != required_states
        or not required_states <= set(targets)
        or any(
            targets[state_id].kind == "tag"
            for state_id in states
            if state_id in targets
        )
    )


def _unused_targets_safe(facts, selection, candidate, output_ids, required_states):
    context = facts.link_context
    unobserved = tuple(
        target
        for target in candidate.targets
        if target.kind != "tag" and target.target_id not in required_states
    )
    if not unobserved:
        return True
    consumed_ids = set(output_ids)
    for choice in selection.link_choices:
        for meaning in (choice.old, choice.selected):
            if meaning is not None:
                consumed_ids.update(meaning.candidates)
                if meaning.target_id is not None:
                    consumed_ids.add(meaning.target_id)
    for documents, registry, observed in (
        (
            context.current_documents,
            context.current_targets,
            context.current_target_facts,
        ),
        (
            context.incoming_documents,
            context.incoming_targets,
            context.incoming_target_facts,
        ),
        (candidate.documents, candidate.targets, candidate.target_facts),
    ):
        _, _, used_targets, _ = consumed_context(
            documents,
            registry,
            observed,
            context.inventory,
            target_ids=tuple(consumed_ids),
        )
        consumed_ids.update(target.target_id for target in used_targets)
    current_targets = {target.target_id: target for target in context.current_targets}
    for target in unobserved:
        if (
            target.kind != "resource"
            or target.identity is not None
            or current_targets.get(target.target_id) != target
            or target.target_id in consumed_ids
            or any(
                entry.current.path == target.canonical_path
                for entry in facts.identity_inventory
            )
        ):
            return False
    return True


def _validate_candidate_targets(
    facts, targets, states, outputs, association, current_path, reversal, add
):
    context = facts.link_context
    original_targets = tuple(targets.values())
    try:
        validate_targets(tuple(t for t in original_targets if t.target_id in outputs))
    except ValueError:
        add("attachment_target_invalid")
    for target_id, target in targets.items():
        state = states.get(target_id)
        if target_id in outputs:
            output = outputs[target_id]
            if (
                target.kind != "resource"
                or target.identity is not None
                or target.canonical_path != output.path
                or state.content is None
                or not same_content(state.content, output.content)
                or state.existence != "present"
            ):
                add("attachment_target_invalid")
            if any(
                other.target_id != target_id
                and other.canonical_path is not None
                and _paths_collide(output.path, other.canonical_path)
                for other in original_targets
            ):
                add("attachment_target_invalid")
            for entry in facts.identity_inventory:
                if _paths_collide(output.path, entry.current.path) and not (
                    target_id == association
                    and entry.current.path == current_path
                    or reversal is not None
                    and any(
                        r.path == output.path == entry.current.path
                        and r.target_id == target_id
                        for r in reversal.outputs
                    )
                ):
                    add("attachment_target_invalid")
        else:
            old = next(t for t in context.current_targets if t.target_id == target_id)
            if target != old:
                add("attachment_target_invalid")


def _validate_retained_states(
    context, targets, states, outputs, docs, association, removing, reversal, add
):
    for target_id, state in states.items():
        if target_id in outputs:
            continue
        bound_docs = tuple(
            d
            for d in docs.values()
            if d.source_path == targets[target_id].canonical_path
        )
        if bound_docs:
            if (
                len(bound_docs) != 1
                or state.content is None
                or not same_content(state.content, bound_docs[0].content)
                or state.existence != "present"
            ):
                add("attachment_target_invalid", bound_docs[0].document_id)
        else:
            prior = next(
                (s for s in context.current_target_facts if s.target_id == target_id),
                None,
            )
            absent = (
                removing
                and target_id == association
                or reversal is not None
                and any(
                    r.target_id == target_id and r.target is None
                    for r in reversal.outputs
                )
            )
            if (
                absent
                and (
                    state.existence != "missing"
                    or state.content is not None
                    or state.structure is not None
                    or state.fragments
                    or state.anchors
                    or state.memberships
                )
                or not absent
                and prior != state
            ):
                add("attachment_target_invalid")


def _expected_document_edits(old, choices, offered_links, outputs, used, add):
    document_id = old.document_id
    replacements, expected_meanings = [], []
    for occurrence in old.occurrences:
        key = document_id, occurrence.occurrence_id
        choice = choices.get(key)
        if choice is not None:
            used.add(key)
            if (
                key not in offered_links
                or choice.old != occurrence.meaning
                or (
                    choice.selected is not None
                    and choice.selected.target_id not in outputs
                )
            ):
                add("attachment_link_choice_invalid", *key)
            replacements.append(
                (occurrence.span.start, occurrence.span.end, choice.replacement)
            )
            if choice.selected is not None:
                expected_meanings.append(
                    (
                        choice.replacement,
                        choice.selected,
                        choice.expected_memberships,
                    )
                )
            elif choice.replacement:
                add("attachment_link_choice_invalid", *key)
        else:
            expected_meanings.append((occurrence.raw, occurrence.meaning, None))
    raw = old.content.data
    for start, end, replacement in reversed(replacements):
        raw = raw[:start] + replacement + raw[end:]
    return raw, expected_meanings


def _validate_document_edits(
    old, doc, choices, offered_links, outputs, used, states, add
):
    raw, expected_meanings = _expected_document_edits(
        old, choices, offered_links, outputs, used, add
    )
    document_id = old.document_id
    if (
        doc.content.data != raw
        or doc.source_path != old.source_path
        or doc.path_mode != old.path_mode
    ):
        add("attachment_document_changed", document_id)
    if len(doc.occurrences) != len(expected_meanings):
        add("attachment_link_choice_missing", document_id)
    for occurrence, (raw_token, expected_meaning, memberships) in zip(
        doc.occurrences, expected_meanings
    ):
        if occurrence.raw != raw_token or occurrence.meaning != expected_meaning:
            add(
                "attachment_link_choice_missing",
                document_id,
                occurrence.occurrence_id,
            )
        if memberships is not None:
            state = states.get(expected_meaning.target_id)
            if state is None or state.memberships != memberships:
                add(
                    "attachment_link_choice_invalid",
                    document_id,
                    occurrence.occurrence_id,
                )


def _retains_opaque_attachment_context(facts, selection, candidate, doc, old):
    context = facts.link_context
    return (
        doc.status != "supported"
        and selection.choice == "current"
        and not selection.link_choices
        and onboarding_current_context(facts)
        and doc == old
        and len(candidate.outputs) == 1
        and len(candidate.documents) == len(context.current_documents)
        and {d.document_id: d for d in candidate.documents}
        == {d.document_id: d for d in context.current_documents}
        and len(candidate.targets) == len(context.current_targets)
        and {t.target_id: t for t in candidate.targets}
        == {t.target_id: t for t in context.current_targets}
        and len(candidate.target_facts) == len(context.current_target_facts)
        and {s.target_id: s for s in candidate.target_facts}
        == {s.target_id: s for s in context.current_target_facts}
    )


def _validate_candidate_documents(
    facts,
    selection,
    candidate,
    change,
    old_docs,
    docs,
    outputs,
    states,
    affected_target_ids,
    add,
    link_findings,
):
    context = facts.link_context
    choices = {(c.document_id, c.occurrence_id): c for c in selection.link_choices}
    if len(choices) != len(selection.link_choices):
        add("attachment_link_choice_invalid")
    offered_links = {
        (link.document_id, link.occurrence_id)
        for link in change.attachment_review.links
        if link.old is not None
    }
    used = set()
    for document_id, old in old_docs.items():
        doc = docs[document_id]
        _validate_document_edits(
            old, doc, choices, offered_links, outputs, used, states, add
        )
        if _retains_opaque_attachment_context(facts, selection, candidate, doc, old):
            continue
        validation = _validate_link_document(
            doc,
            expected_content=doc.content,
            expected_path=old.source_path,
            targets=candidate.targets,
            target_facts=candidate.target_facts,
            inventory=context.inventory,
            baseline=LinkValidationBaseline(
                schema_id="brz2obsidian.link-validation-baseline",
                schema_version=1,
                document=old,
                targets=context.current_targets,
                target_facts=context.current_target_facts,
                inventory=context.inventory,
            ),
            affected_target_ids=affected_target_ids,
        )
        link_findings.extend(validation.findings)
        if not validation.valid:
            add("attachment_link_invalid", document_id)
    if used != set(choices):
        add("attachment_link_choice_invalid")


def _validate_proposed_attachment(facts, selection, candidate, proposal):
    findings, link_findings = [], []

    def add(code, document_id=None, occurrence_id=None):
        findings.append(
            AttachmentValidationFinding(
                code=code,
                document_id=document_id,
                occurrence_id=occurrence_id,
                blocking=True,
            )
        )

    def result():
        return AttachmentCandidateValidation(
            valid=not any(f.blocking for f in findings + link_findings),
            findings=tuple(findings),
            link_findings=tuple(link_findings),
        )

    selected = _bound_attachment_selection(facts, selection, candidate, proposal, add)
    if selected is None:
        return result()
    change, subject, alternative = selected
    context = facts.link_context
    removing = (
        facts.format_operation.kind == "attachment_cleanup"
        and selection.choice == "remove"
    )
    association = (
        subject.attachment.current_target_id
        if subject.operation_reversal is not None or removing
        else alternative.outputs[0].target_id
    )
    outputs = {o.target_id: o for o in alternative.outputs}
    targets = {t.target_id: t for t in candidate.targets}
    states = {s.target_id: s for s in candidate.target_facts}
    if not _attachment_registry_complete(
        context, candidate, targets, states, set(outputs)
    ):
        add("attachment_context_incomplete")
        return result()
    if not _unused_targets_safe(facts, selection, candidate, set(outputs), set(states)):
        add("attachment_context_incomplete")
        return result()
    _validate_candidate_targets(
        facts,
        targets,
        states,
        outputs,
        association,
        change.path,
        subject.operation_reversal,
        add,
    )
    old_docs = {d.document_id: d for d in context.current_documents}
    docs = {d.document_id: d for d in candidate.documents}
    if len(docs) != len(candidate.documents) or set(docs) != set(old_docs):
        add("attachment_context_incomplete")
        return result()
    _validate_retained_states(
        context,
        targets,
        states,
        outputs,
        docs,
        association,
        removing,
        subject.operation_reversal,
        add,
    )
    _validate_candidate_documents(
        facts,
        selection,
        candidate,
        change,
        old_docs,
        docs,
        outputs,
        states,
        tuple(outputs) + ((association,) if removing else ()),
        add,
        link_findings,
    )
    return result()


@dataclass(frozen=True)
class CandidateWork:
    facts: ReconciliationInput
    selection: AttachmentSelection
    candidate: AttachmentCandidate
    phase: str = "validate"
    canonical_proposal: object = None


@dataclass(frozen=True)
class CandidateValidationProof:
    facts: ReconciliationInput
    selection: AttachmentSelection
    candidate: AttachmentCandidate
    validation: AttachmentCandidateValidation


def advance_candidate(work, returned=None):
    from .reconciliation import ReconcileWork

    if work.phase == "validate":
        try:
            facts = ReconciliationInput.model_validate(work.facts)
            selection = AttachmentSelection.model_validate(work.selection)
            candidate = AttachmentCandidate.model_validate(work.candidate)
        except ValueError, TypeError, ValidationError:
            invalid = AttachmentCandidateValidation(
                valid=False,
                findings=(
                    AttachmentValidationFinding(
                        code="attachment_facts_invalid",
                        document_id=None,
                        occurrence_id=None,
                        blocking=True,
                    ),
                ),
                link_findings=(),
            )
            return CompletedWork(
                CandidateValidationProof(
                    work.facts, work.selection, work.candidate, invalid
                )
            )
        if work.canonical_proposal is not None:
            return replace(
                work,
                facts=facts,
                selection=selection,
                candidate=candidate,
                phase="finish_bound",
            )
        return ChildWork(
            ReconcileWork(facts),
            replace(
                work,
                facts=facts,
                selection=selection,
                candidate=candidate,
                phase="finish",
            ),
        )
    if work.phase not in ("finish", "finish_bound"):
        raise ValueError("Unknown candidate phase")
    validation = _validate_proposed_attachment(
        work.facts,
        work.selection,
        work.candidate,
        work.canonical_proposal if work.phase == "finish_bound" else returned,
    )
    return CompletedWork(
        CandidateValidationProof(work.facts, work.selection, work.candidate, validation)
    )


def _candidate_validation(facts, selection, candidate, proof=None):
    if proof is None:
        proof = drive_inline(CandidateWork(facts, selection, candidate))
    if (
        type(proof) is not CandidateValidationProof
        or not canonical_equal(facts, proof.facts)
        or not canonical_equal(selection, proof.selection)
        or not canonical_equal(candidate, proof.candidate)
    ):
        raise ValueError("Candidate validation belongs to different inputs")
    return proof.validation


def _validate_attachment_candidate(facts, selection, candidate):
    return _candidate_validation(facts, selection, candidate)


def validate_attachment_candidate(
    facts: ReconciliationInput,
    selection: AttachmentSelection,
    candidate: AttachmentCandidate,
) -> AttachmentCandidateValidation:
    """Validate public inline inputs before entering the shared pure engine."""
    try:
        facts = ReconciliationInput.model_validate(facts)
        selection = AttachmentSelection.model_validate(selection)
        candidate = AttachmentCandidate.model_validate(candidate)
        require_inline((facts, selection, candidate))
    except ValueError, TypeError, ValidationError:
        return AttachmentCandidateValidation(
            valid=False,
            findings=(
                AttachmentValidationFinding(
                    code="attachment_facts_invalid",
                    document_id=None,
                    occurrence_id=None,
                    blocking=True,
                ),
            ),
            link_findings=(),
        )
    return _validate_attachment_candidate(facts, selection, candidate)
