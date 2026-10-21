"""Conservative combination of normalized field and byte-span facts, without parsing."""

from hashlib import sha256

from brz2obsidian.contracts import ExactContent, StructuredDocument, StructureSpan


def _value(document, field):
    if field.kind == "opaque":
        return field.kind, document.content.data[field.span.start : field.span.end]
    return field.kind, field.scalar_type, field.value


def validate_structure_facts(subject, baseline_identity, incoming_identity):
    """Check exact binding and declared identity, independently of merge support.

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
    return None


def structure_proposal(subject, baseline_identity, incoming_identity):
    comparison = subject.structure
    documents = comparison.original, comparison.current, comparison.incoming

    def unresolved(rule):
        return ("unresolved", None, rule, True), None

    problem = validate_structure_facts(subject, baseline_identity, incoming_identity)
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
    for key, source in source_fields.items():
        old, local = old_fields[key], current_fields[key]
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
        candidate_body = _combine_body(
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
    )
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
    return current


def structure_assumption(comparison):
    if comparison is None:
        return None
    values = comparison.model_dump(
        mode="json", exclude={"original", "current", "incoming"}
    )
    for name in ("original", "current", "incoming"):
        doc = getattr(comparison, name)
        values[name] = doc.model_dump(mode="json", exclude={"content"}) | {
            "content_sha256": sha256(doc.content.data).hexdigest(),
        }
    return values
