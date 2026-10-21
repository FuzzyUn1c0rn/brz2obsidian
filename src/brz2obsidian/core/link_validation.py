"""Independent validation of normalized exact link documents; no markup parsing."""

from typing import Literal

from pydantic import ValidationError

from brz2obsidian.contracts import (
    ExactContent,
    LinkDocument,
    LinkDocumentValidation,
    LinkTargetFacts,
    LinkValidationFinding,
    ReferenceTarget,
)

from .link_meanings import SAFE_LINK_STATUSES, resolve_occurrence
from .memberships import appearance_issues, validate_memberships
from .reference_targets import validate_targets


def validate_link_target_state(state, targets):
    """Check exact normalized membership safety with compatible file roles.

    One registry entry represents each stable file. A category/relationship
    producer may refer to the same imported file using its own compatible role.
    Per-list duplicate memberships remain rejected by their own validator.
    """
    if state.structure is None:
        return
    selected = next((t for t in targets if t.target_id == state.target_id), None)
    if selected is not None and selected.kind != "resource":
        for field in state.structure.fields:
            if field.identity_component is not None and (
                selected.identity is None
                or field.value
                != {
                    "collection": selected.identity.collection_id,
                    "module": selected.identity.module_id,
                    "item": selected.identity.item_id,
                }[field.identity_component]
            ):
                raise ValueError("link_membership_invalid")
    validate_memberships(state.structure)
    for membership in state.structure.memberships:
        for entry in membership.entries:
            matching = tuple(t for t in targets if t.target_id == entry.target_id)
            if len(matching) != 1:
                raise ValueError("link_membership_invalid")
            (target,) = matching
            compatible = target.kind == entry.target.kind or {
                target.kind,
                entry.target.kind,
            } <= {"note", "category", "relationship"}
            if (
                not compatible
                or target.identity != entry.target.identity
                or target.canonical_path != entry.target.canonical_path
                or target.target != entry.target.target
            ):
                raise ValueError("link_membership_invalid")


def validate_link_document(
    document: LinkDocument,
    *,
    expected_content: ExactContent,
    expected_path: str,
    targets: tuple[ReferenceTarget, ...],
    target_facts: tuple[LinkTargetFacts, ...],
    inventory: Literal["complete", "partial", "unreadable"],
    baseline: LinkDocument | None = None,
    affected_target_ids: tuple[str, ...] = (),
) -> LinkDocumentValidation:
    """Validate selected semantics; baseline only exempts unchanged existing warnings.

    Facts must come from a complete bounded outer interpretation. This proves
    their exact binding and semantic consistency, never parsing or write consent.
    """
    findings = []
    document_id = getattr(document, "document_id", "unknown")

    def add(code, occurrence_id=None, blocking=True):
        findings.append(
            LinkValidationFinding(
                code=code,
                document_id=document_id,
                occurrence_id=occurrence_id,
                blocking=blocking,
            )
        )

    def result():
        return LinkDocumentValidation(
            valid=not any(f.blocking for f in findings), findings=tuple(findings)
        )

    try:
        document = LinkDocument.model_validate(document)
        expected_content = ExactContent.model_validate(expected_content)
        targets = tuple(ReferenceTarget.model_validate(t) for t in targets)
        target_facts = tuple(LinkTargetFacts.model_validate(t) for t in target_facts)
        if baseline is not None:
            baseline = LinkDocument.model_validate(baseline)
    except ValidationError, TypeError, ValueError:
        add("link_facts_invalid")
        return result()
    if (
        document.content.data != expected_content.data
        or document.source_path != expected_path
    ):
        add("link_unbound")
    if inventory != "complete" or document.inventory != "complete":
        add("link_inventory_uncertain")
    if document.status != "supported":
        add("link_unsupported")
    if len({t.target_id for t in targets}) != len(targets) or len(
        {s.target_id for s in target_facts}
    ) != len(target_facts):
        add("link_facts_invalid")
        return result()
    if baseline is not None and (
        baseline.document_id != document.document_id
        or baseline.source_path != expected_path
        or baseline.path_mode != document.path_mode
        or baseline.inventory != "complete"
        or baseline.status != "supported"
    ):
        add("link_unbound")
        baseline = None
    own_targets = tuple(t for t in targets if t.canonical_path == expected_path)
    try:
        validate_targets(own_targets)
    except ValueError:
        add("link_facts_invalid")
    old = () if baseline is None else baseline.occurrences
    for occurrence in document.occurrences:
        declared = occurrence.meaning
        actual = resolve_occurrence(occurrence, targets, target_facts, inventory)
        if actual != declared:
            add("link_meaning_mismatch", occurrence.occurrence_id)
            continue
        previous = sum(o.raw == occurrence.raw and o.meaning == actual for o in old)
        current = sum(
            o.raw == occurrence.raw and o.meaning == actual
            for o in document.occurrences[: document.occurrences.index(occurrence) + 1]
        )
        affected = actual.target_id in affected_target_ids or bool(
            set(actual.candidates).intersection(affected_target_ids)
        )
        existing_warning = (
            actual.status not in SAFE_LINK_STATUSES
            and previous >= current
            and not affected
        )
        if existing_warning:
            add("existing_link_warning", occurrence.occurrence_id, False)
            continue
        relevant = tuple(
            t
            for t in targets
            if t.target_id == actual.target_id or t.target_id in actual.candidates
        )
        try:
            validate_targets(relevant)
        except ValueError:
            add("link_facts_invalid", occurrence.occurrence_id)
        state = next((s for s in target_facts if s.target_id == actual.target_id), None)
        if state is not None and actual.status == "resolved":
            try:
                validate_link_target_state(state, targets)
            except ValueError:
                add("link_membership_invalid", occurrence.occurrence_id)
            if state.structure is not None and appearance_issues(state.structure):
                # Available selected bytes plus the same resolved historical version
                # prove retention. A changed version or missing proof cannot do so.
                retained = actual.target_version is not None and any(
                    previous.meaning.status == "resolved"
                    and previous.meaning.target_id == actual.target_id
                    and previous.meaning.target_identity == actual.target_identity
                    and previous.meaning.path == actual.path
                    and previous.meaning.target_version == actual.target_version
                    for previous in old
                )
                add(
                    "link_appearance_warning"
                    if retained
                    else "link_membership_invalid",
                    occurrence.occurrence_id,
                    not retained,
                )
        if actual.status not in SAFE_LINK_STATUSES:
            add("link_harmed", occurrence.occurrence_id)
    return result()
