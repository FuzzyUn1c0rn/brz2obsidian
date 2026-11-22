"""Independent validation of normalized exact link documents; no markup parsing."""

from typing import Literal

from pydantic import ValidationError

from brz2obsidian.content_values import require_inline
from brz2obsidian.contracts import (
    ExactContent,
    LinkDocument,
    LinkDocumentValidation,
    LinkTargetFacts,
    LinkValidationBaseline,
    LinkValidationFinding,
    OpaqueContent,
    ReferenceTarget,
    same_content,
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
                or target.status != entry.target.status
                or set(target.representations) != set(entry.target.representations)
            ):
                raise ValueError("link_membership_invalid")


def _validated_baseline(
    baseline, document, expected_path, *, allow_existing_unsupported=False
):
    if baseline is None:
        return None
    prior = baseline.document
    if (
        prior.document_id != document.document_id
        or prior.source_path != expected_path
        or prior.path_mode != document.path_mode
        or baseline.inventory != "complete"
        or prior.inventory != "complete"
        or (
            prior.status != "supported"
            and not (
                allow_existing_unsupported
                and same_content(prior.content, document.content)
            )
        )
    ):
        raise ValueError("link_unbound")
    if (
        len({t.target_id for t in baseline.targets}) != len(baseline.targets)
        or len({s.target_id for s in baseline.target_facts})
        != len(baseline.target_facts)
        or any(
            s.target_id not in {t.target_id for t in baseline.targets}
            for s in baseline.target_facts
        )
    ):
        raise ValueError("link_facts_invalid")
    own = tuple(t for t in baseline.targets if t.canonical_path == prior.source_path)
    validate_targets(own)
    for target in own:
        states = tuple(
            s for s in baseline.target_facts if s.target_id == target.target_id
        )
        if (
            len(states) != 1
            # Public calls require_inline the complete graph; the private owned
            # route has coadmitted exact bytes before this bytes-only binding.
            or not same_content(states[0].content, prior.content)
        ):
            raise ValueError("link_unbound")
    for occurrence in prior.occurrences:
        actual = resolve_occurrence(
            occurrence, baseline.targets, baseline.target_facts, baseline.inventory
        )
        if actual != occurrence.meaning:
            raise ValueError("link_meaning_mismatch")
        if actual.status == "resolved":
            selected = tuple(
                t for t in baseline.targets if t.target_id == actual.target_id
            )
            validate_targets(selected)
            state = next(
                s for s in baseline.target_facts if s.target_id == actual.target_id
            )
            validate_link_target_state(state, baseline.targets)
    return baseline


def _appearance_value(state):
    if state.structure is None or state.structure.appearance_field is None:
        return None
    key = state.structure.appearance_field
    field = next(f for f in state.structure.fields if f.key == key)
    return key, field.kind, field.scalar_type, field.value


def _retained_appearance(baseline, actual, state):
    if baseline is None:
        return False
    for previous in baseline.document.occurrences:
        meaning = previous.meaning
        if (
            meaning.status != "resolved"
            or meaning.target_id != actual.target_id
            or meaning.target_identity != actual.target_identity
            or meaning.path != actual.path
        ):
            continue
        prior_state = next(
            (s for s in baseline.target_facts if s.target_id == meaning.target_id), None
        )
        if (
            prior_state is not None
            and prior_state.content is not None
            and prior_state.structure is not None
            and appearance_issues(prior_state.structure)
            and _appearance_value(prior_state) == _appearance_value(state)
        ):
            return True
    return False


def validate_link_document(
    document: LinkDocument,
    *,
    expected_content: ExactContent,
    expected_path: str,
    targets: tuple[ReferenceTarget, ...],
    target_facts: tuple[LinkTargetFacts, ...],
    inventory: Literal["complete", "partial", "unreadable"],
    baseline: LinkValidationBaseline | None = None,
    affected_target_ids: tuple[str, ...] = (),
) -> LinkDocumentValidation:
    """Validate selected semantics; baseline only exempts unchanged existing warnings.

    Facts must come from a complete bounded outer interpretation. This proves
    their exact binding and semantic consistency, never parsing or write consent.
    """
    return _validate_link_document(
        document,
        expected_content=expected_content,
        expected_path=expected_path,
        targets=targets,
        target_facts=target_facts,
        inventory=inventory,
        baseline=baseline,
        affected_target_ids=affected_target_ids,
        _inline_only=True,
    )


def _validate_occurrence_target(
    actual, occurrence, targets, target_facts, baseline, add
):
    state = next((s for s in target_facts if s.target_id == actual.target_id), None)
    if state is not None and actual.status == "resolved":
        try:
            validate_link_target_state(state, targets)
        except ValueError:
            add("link_membership_invalid", occurrence.occurrence_id)
            return False
        if state.structure is not None and appearance_issues(state.structure):
            # Prior bytes and normalized lookup context independently establish
            # the old diagnostic; neither cached version nor bytes alone suffice.
            retained = _retained_appearance(baseline, actual, state)
            add(
                "link_appearance_warning" if retained else "link_membership_invalid",
                occurrence.occurrence_id,
                not retained,
            )
    return True


def _validate_occurrences(
    document, targets, target_facts, inventory, baseline, affected_target_ids, add
):
    old = () if baseline is None else baseline.document.occurrences
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
        if not _validate_occurrence_target(
            actual, occurrence, targets, target_facts, baseline, add
        ):
            continue
        if actual.status not in SAFE_LINK_STATUSES:
            add("link_harmed", occurrence.occurrence_id)


def _validated_link_inputs(
    document, expected_content, targets, target_facts, baseline, _inline_only
):
    document = LinkDocument.model_validate(document)
    expected_content = (
        OpaqueContent.model_validate(expected_content)
        if not _inline_only and type(expected_content) is OpaqueContent
        else ExactContent.model_validate(expected_content)
    )
    targets = tuple(ReferenceTarget.model_validate(t) for t in targets)
    target_facts = tuple(LinkTargetFacts.model_validate(t) for t in target_facts)
    if baseline is not None:
        baseline = LinkValidationBaseline.model_validate(baseline)
    if _inline_only:
        require_inline((document, expected_content, targets, target_facts, baseline))
    return document, expected_content, targets, target_facts, baseline


def _validate_link_document(
    document: LinkDocument,
    *,
    expected_content,
    expected_path: str,
    targets: tuple[ReferenceTarget, ...],
    target_facts: tuple[LinkTargetFacts, ...],
    inventory: Literal["complete", "partial", "unreadable"],
    baseline: LinkValidationBaseline | None = None,
    affected_target_ids: tuple[str, ...] = (),
    _inline_only: bool = False,
    allow_existing_unsupported: bool = False,
) -> LinkDocumentValidation:
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
        document, expected_content, targets, target_facts, baseline = (
            _validated_link_inputs(
                document,
                expected_content,
                targets,
                target_facts,
                baseline,
                _inline_only,
            )
        )
    except ValidationError, TypeError, ValueError:
        add("link_facts_invalid")
        return result()
    if (
        not same_content(document.content, expected_content)
        or document.source_path != expected_path
    ):
        add("link_unbound")
    if inventory != "complete" or document.inventory != "complete":
        add("link_inventory_uncertain")
    if document.status != "supported" and not allow_existing_unsupported:
        add("link_unsupported")
    if len({t.target_id for t in targets}) != len(targets) or len(
        {s.target_id for s in target_facts}
    ) != len(target_facts):
        add("link_facts_invalid")
        return result()
    try:
        baseline = _validated_baseline(
            baseline,
            document,
            expected_path,
            allow_existing_unsupported=allow_existing_unsupported,
        )
    except ValueError as error:
        add(
            str(error)
            if str(error)
            in ("link_unbound", "link_facts_invalid", "link_meaning_mismatch")
            else "link_facts_invalid"
        )
        baseline = None
    own_targets = tuple(t for t in targets if t.canonical_path == expected_path)
    try:
        validate_targets(own_targets)
    except ValueError:
        add("link_facts_invalid")
    _validate_occurrences(
        document, targets, target_facts, inventory, baseline, affected_target_ids, add
    )
    return result()
