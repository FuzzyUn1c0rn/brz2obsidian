"""Conservative combination of normalized field and byte-span facts, without parsing."""

from hashlib import sha256

from brz2obsidian.contracts import ExactContent, StructuredDocument, StructureSpan
from brz2obsidian.core.memberships import (
    appearance_issues,
    combine_memberships,
    validate_memberships,
)
from brz2obsidian.core.sections import (
    result_sections,
    validate_section_combination,
    validate_section_document,
    validate_section_facts,
)


def _value(document, field):
    if field.kind == "opaque":
        return field.kind, document.content.data[field.span.start : field.span.end]
    return field.kind, field.scalar_type, field.value


def validate_structure_facts(
    subject, baseline_identity, incoming_identity, *, source_version
):
    """Check exact normalized binding and target/identity safety before any policy.

    Opaque documents need whole-file review; absent parsed fields in those facts
    do not establish missing imported identity. Supported documents must agree.
    """
    baseline_format, incoming_format = (
        baseline_identity.output_format,
        incoming_identity.output_format,
    )
    comparison = subject.structure
    documents = comparison.original, comparison.current, comparison.incoming
    versions = subject.baseline.content, subject.current.content, subject.incoming

    if any(
        content is None
        or doc.content.data != content.data
        or doc.output_format != version
        for doc, content, version in zip(
            documents,
            versions,
            (baseline_format, baseline_format, incoming_format),
            strict=True,
        )
    ):
        return "structure_unbound"
    expected_identity = {
        "collection": incoming_identity.collection_id,
        "item": subject.item_id,
        "module": incoming_identity.module_id,
    }
    if any(
        field.identity_component is not None
        and field.value != expected_identity[field.identity_component]
        for document in documents
        for field in document.fields
    ):
        return "structure_identity_conflict"
    identities = tuple(
        tuple(sorted((f.key, f.value) for f in doc.fields if f.kind == "identity"))
        for doc in documents
    )
    if all(doc.status == "supported" for doc in documents) and (
        identities[0] != identities[1] or identities[0] != identities[2]
    ):
        return "structure_identity_conflict"
    # Preservation selects exact current bytes. Combination validates its targets
    # separately; an unsafe unchosen incoming alternative cannot veto safe keep.
    try:
        if comparison.alignment == "supported":
            bodies = tuple(d.content.data[d.body.start : d.body.end] for d in documents)
            if (
                _apply(bodies[0], comparison.local_edits) != bodies[1]
                or _apply(bodies[0], comparison.source_edits) != bodies[2]
            ):
                return "structure_unbound"
        for index, document in enumerate(documents):
            validate_memberships(document, target_safety=index == 1)
        validate_section_facts(subject, baseline_identity, source_version)
    except ValueError as error:
        return str(error)
    return None


def structure_proposal(
    subject, baseline_identity, incoming_identity, *, source_version
):
    comparison = subject.structure
    documents = comparison.original, comparison.current, comparison.incoming

    def unresolved(rule):
        return ("unresolved", None, rule, True), None

    problem = validate_structure_facts(
        subject, baseline_identity, incoming_identity, source_version=source_version
    )
    if problem is not None:
        return unresolved(problem)
    if (
        any(doc.status != "supported" for doc in documents)
        or comparison.alignment == "unsupported"
    ):
        return unresolved("structure_unsupported")
    if comparison.alignment != "supported":
        return unresolved("structure_ambiguous")
    original, current, incoming = documents
    old_fields, current_fields, source_fields = (
        {f.key: f for f in doc.fields} for doc in documents
    )
    if set(old_fields) != set(source_fields) or not set(old_fields) <= set(
        current_fields
    ):
        return unresolved("structure_conflict")
    replacements = {}
    try:
        membership_replacements, memberships = combine_memberships(
            documents, comparison
        )
        validate_section_combination(comparison)
    except ValueError as error:
        return unresolved(str(error))
    if len({d.appearance_field for d in documents}) != 1:
        return unresolved("structure_conflict")
    for key, source in source_fields.items():
        old, local = old_fields[key], current_fields[key]
        if key in memberships or key == current.appearance_field:
            continue
        if old.kind != local.kind or old.kind != source.kind:
            return unresolved("structure_conflict")
        old_value, local_value, source_value = (
            _value(doc, f)
            for doc, f in zip(documents, (old, local, source), strict=True)
        )
        if source_value == old_value or local_value == source_value:
            continue
        if source.kind != "scalar" or local_value != old_value:
            return unresolved("structure_conflict")
        replacements[key] = source
    source_body = incoming.content.data[incoming.body.start : incoming.body.end]
    old_body = original.content.data[original.body.start : original.body.end]
    local_body = current.content.data[current.body.start : current.body.end]
    try:
        candidate_body, patches = _combine_body(
            old_body,
            local_body,
            source_body,
            comparison.local_edits,
            comparison.source_edits,
        )
    except ValueError as error:
        return unresolved(str(error))
    # Copy untouched current spans exactly; only validated source scalar entries move.
    data, cursor, fields = b"", 0, []
    for field in current.fields:
        data += current.content.data[cursor : field.span.start]
        source = replacements.get(field.key)
        raw = current.content.data[field.span.start : field.span.end]
        value_start = field.value_span.start - field.span.start
        value_end = field.value_span.end - field.span.start
        if source:
            replacement = incoming.content.data[
                source.value_span.start : source.value_span.end
            ]
            raw = raw[:value_start] + replacement + raw[value_end:]
            value_end = value_start + len(replacement)
        if field.key in membership_replacements:
            raw = membership_replacements[field.key]
        start = len(data)
        data += raw
        fields.append(
            field.model_copy(
                update={
                    "value": source.value if source else field.value,
                    "scalar_type": source.scalar_type if source else field.scalar_type,
                    "span": StructureSpan(start=start, end=len(data)),
                    "value_span": StructureSpan(
                        start=start + value_start, end=start + value_end
                    ),
                }
            )
        )
        cursor = field.span.end
    body_start = current.body.start + len(data) - cursor
    data += current.content.data[cursor : current.body.start] + candidate_body
    result = StructuredDocument(
        schema_id="brz2obsidian.structured-document",
        schema_version=1,
        output_format=incoming_identity.output_format,
        content=ExactContent(data=data),
        status="supported",
        issues=(),
        fields=tuple(fields),
        body=StructureSpan(start=body_start, end=len(data)),
        memberships=tuple(memberships.values()),
        appearance_field=current.appearance_field,
        owned_sections=result_sections(comparison, patches, body_start),
    )
    try:
        validate_memberships(result)
        validate_section_document(
            result, {b.section_id: b for b in comparison.section_bases}
        )
    except ValueError as error:
        return unresolved(str(error))
    result = result.model_copy(update={"issues": appearance_issues(result)})
    if result.content.data == current.content.data:
        return ("no_change", current.content, "structure_combined", False), result
    return ("compatible", result.content, "structure_combined", True), result


def _apply(original, edits):
    cursor, result, previous = 0, b"", None
    for edit in edits:
        start, end = edit.span.start, edit.span.end
        if (
            previous is not None
            and start == cursor
            and (start == end or previous.span.start == previous.span.end)
        ):
            raise ValueError("structure_unbound")
        if (
            start < cursor
            or end > len(original)
            or original[start:end] != edit.expected
        ):
            raise ValueError("structure_unbound")
        result += original[cursor:start] + edit.replacement
        cursor, previous = end, edit
    return result + original[cursor:]


def _combine_body(original, current, incoming, local_edits, source_edits):
    if (
        _apply(original, local_edits) != current
        or _apply(original, source_edits) != incoming
    ):
        raise ValueError("structure_unbound")
    patches = []
    for source in source_edits:
        start, end = source.span.start, source.span.end
        identical = False
        for local in local_edits:
            a, b = local.span.start, local.span.end
            if source == local:
                identical = True
                break
            overlap = max(start, a) < min(end, b)
            insertion_overlap = (start == end and a <= start <= b) or (
                a == b and start <= a <= end
            )
            if overlap or insertion_overlap:
                raise ValueError("structure_conflict")
        if identical:
            continue
        offset = sum(
            len(local.replacement) - len(local.expected)
            for local in local_edits
            if local.span.end <= start
        )
        start, end = start + offset, end + offset
        if current[start:end] != source.expected:
            raise ValueError("structure_unbound")
        patches.append((start, end, source.replacement))
    for start, end, replacement in reversed(patches):
        current = current[:start] + replacement + current[end:]
    return current, patches


def structure_assumption(comparison):
    if comparison is None:
        return None
    values = comparison.model_dump(
        mode="json", exclude={"original", "current", "incoming"}
    )
    for name in ("prior_mappings", "incoming_mappings"):
        values[name] = [
            record.model_dump(mode="json", exclude={"source_label"})
            for record in getattr(comparison, name)
        ]
    values["section_bases"] = [
        basis.model_dump(mode="json", exclude={"original"})
        | {
            "original_sha256": sha256(basis.original.data).hexdigest(),
        }
        for basis in comparison.section_bases
    ]
    for name in ("original", "current", "incoming"):
        doc = getattr(comparison, name)
        values[name] = doc.model_dump(mode="json", exclude={"content"}) | {
            "content_sha256": sha256(doc.content.data).hexdigest(),
        }
    return values
