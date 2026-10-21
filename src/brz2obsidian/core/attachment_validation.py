"""Validate an offered binary selection and exact per-occurrence document edits."""

from pydantic import ValidationError

from brz2obsidian.contracts import (
    AttachmentCandidate,
    AttachmentCandidateValidation,
    AttachmentSelection,
    AttachmentValidationFinding,
    LinkValidationBaseline,
    ReconciliationInput,
)

from .identity import _paths_collide
from .link_validation import validate_link_document
from .reference_targets import validate_targets
from .structures import validate_structure_facts


def validate_attachment_candidate(
    facts: ReconciliationInput,
    selection: AttachmentSelection,
    candidate: AttachmentCandidate,
) -> AttachmentCandidateValidation:
    """Validate candidate facts, never grant whole-plan consent or write files."""
    from .reconciliation import reconcile

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

    try:
        facts = ReconciliationInput.model_validate(facts)
        selection = AttachmentSelection.model_validate(selection)
        candidate = AttachmentCandidate.model_validate(candidate)
    except ValueError, TypeError, ValidationError:
        add("attachment_facts_invalid")
        return result()
    proposal = reconcile(facts)
    changes = tuple(
        c
        for c in proposal.changes
        if (c.item_id, c.facet) == (selection.item_id, selection.facet)
        and c.attachment_review is not None
    )
    if len(changes) != 1:
        add("attachment_stale_selection")
        return result()
    (change,) = changes
    if (
        selection.proposal_id != proposal.proposal_id
        or selection.generation != proposal.generation
        or selection.reviewed_change_id != change.change_id
        or selection.reviewed_assumptions != change.assumptions
    ):
        add("attachment_stale_selection")
        return result()
    if (
        any(
            f.blocking and f.subject_id in (None, change.subject_id)
            for f in proposal.findings
        )
        or change.identity_review.status != "matched"
        or change.format_review is not None
        or change.target_path != change.path
        or change.disposition in ("stale", "refused", "identity_resolution")
    ):
        add("attachment_unsafe_input")
        return result()
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
        return result()
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
        return result()

    def payloads(outputs):
        return tuple(
            (o.target_id, o.path, o.content.data, o.content_version) for o in outputs
        )

    if payloads(candidate.outputs) != payloads(alternative.outputs):
        add("attachment_payload_mismatch")
        return result()
    context = facts.link_context
    association = alternative.outputs[0].target_id
    expected_ids = {t.target_id for t in context.current_targets} | {
        o.target_id for o in alternative.outputs
    }
    targets = {t.target_id: t for t in candidate.targets}
    states = {s.target_id: s for s in candidate.target_facts}
    if (
        len(targets) != len(candidate.targets)
        or set(targets) != expected_ids
        or len(states) != len(candidate.target_facts)
        or set(states) != {t.target_id for t in candidate.targets if t.kind != "tag"}
    ):
        add("attachment_context_incomplete")
        return result()
    try:
        validate_targets(
            tuple(
                t
                for t in candidate.targets
                if t.target_id in {o.target_id for o in alternative.outputs}
            )
        )
    except ValueError:
        add("attachment_target_invalid")
    outputs = {o.target_id: o for o in alternative.outputs}
    for target_id, target in targets.items():
        state = states.get(target_id)
        if target_id in outputs:
            output = outputs[target_id]
            if (
                target.kind != "resource"
                or target.identity is not None
                or target.canonical_path != output.path
                or state.content is None
                or state.content.data != output.content.data
                or state.existence != "present"
            ):
                add("attachment_target_invalid")
            if any(
                other.target_id != target_id
                and other.canonical_path is not None
                and _paths_collide(output.path, other.canonical_path)
                for other in candidate.targets
            ):
                add("attachment_target_invalid")
            for entry in facts.identity_inventory:
                if _paths_collide(output.path, entry.current.path) and not (
                    target_id == association and entry.current.path == change.path
                ):
                    add("attachment_target_invalid")
        else:
            old = next(t for t in context.current_targets if t.target_id == target_id)
            if target != old:
                add("attachment_target_invalid")
    old_docs = {d.document_id: d for d in context.current_documents}
    docs = {d.document_id: d for d in candidate.documents}
    if len(docs) != len(candidate.documents) or set(docs) != set(old_docs):
        add("attachment_context_incomplete")
        return result()
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
                or state.content.data != bound_docs[0].content.data
                or state.existence != "present"
            ):
                add("attachment_target_invalid", bound_docs[0].document_id)
        else:
            prior = next(
                (s for s in context.current_target_facts if s.target_id == target_id),
                None,
            )
            if prior != state:
                add("attachment_target_invalid")
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
        validation = validate_link_document(
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
            affected_target_ids=tuple(outputs),
        )
        link_findings.extend(validation.findings)
        if not validation.valid:
            add("attachment_link_invalid", document_id)
    if used != set(choices):
        add("attachment_link_choice_invalid")
    return result()
