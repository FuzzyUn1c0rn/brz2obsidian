"""Bounded format-7 interpretation, outside the source-neutral core.

The exact grammar and merge bounds are documented in docs/structure-grammar.md.
No bytes are normalized or rendered here; offsets always address supplied bytes.
"""

import json
import re
from datetime import date
from difflib import SequenceMatcher

from brz2obsidian.contracts import (
    StructureByteEdit,
    StructureComparison,
    StructuredDocument,
    StructureField,
    StructureSpan,
)


class _Unsupported(ValueError):
    pass


def _scalar(value):
    if value == "":
        return None, "null"
    if (
        value.startswith('"')
        or value in ("true", "false", "null")
        or re.fullmatch(r"-?(0|[1-9][0-9]*)", value)
    ):
        try:
            scalar = json.loads(value)
        except ValueError as error:
            raise _Unsupported("yaml_unsupported") from error
        types = {str: "string", int: "integer", bool: "boolean", type(None): "null"}
        if type(scalar) not in types:
            raise _Unsupported("yaml_unsupported")
        return scalar, types[type(scalar)]
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise _Unsupported("yaml_unsupported") from error
        return value, "date"
    if re.fullmatch(r"[A-Za-z_][\w ./-]*", value) and value.casefold() not in (
        "yes",
        "no",
        "on",
        "off",
        "null",
        "true",
        "false",
    ):
        return value, "string"
    raise _Unsupported("yaml_unsupported")


def _fields(lines):
    fields, seen, index, offset = [], set(), 1, len(lines[0])
    while index < len(lines):
        raw = lines[index]
        text = raw.decode("utf-8").rstrip("\r\n")
        if text == "---":
            return tuple(fields), offset + len(raw)
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*):(?: (.*))?", text)
        if match is None:
            raise _Unsupported("yaml_unsupported")
        key, value = match[1], match[2] or ""
        if key in seen:
            raise _Unsupported("duplicate_property")
        seen.add(key)
        kind = (
            "identity"
            if key in ("source_item_id", "source_collection_id")
            else "scalar"
        )
        semantic, scalar_type = (None, "opaque") if value == "[]" else _scalar(value)
        end = offset + len(raw)
        if value == "[]":
            kind = "opaque"
        index += 1
        if value == "" and index < len(lines) and lines[index].startswith(b"  - "):
            kind, scalar_type = "opaque", "opaque"
            while index < len(lines) and lines[index].startswith(b"  - "):
                _scalar(lines[index][4:].decode("utf-8").rstrip("\r\n"))
                end += len(lines[index])
                index += 1
        if key in ("source_item_id", "source_collection_id") and (
            kind != "identity" or not isinstance(semantic, str) or not semantic
        ):
            raise _Unsupported("identity_invalid")
        fields.append(
            StructureField(
                key=key,
                kind=kind,
                identity_component={
                    "source_item_id": "item",
                    "source_collection_id": "collection",
                }.get(key),
                value=semantic,
                scalar_type=scalar_type,
                span=StructureSpan(start=offset, end=end),
                value_span=StructureSpan(
                    start=offset + len(key) + 1 + (1 if match[2] is not None else 0),
                    end=offset + len(raw.rstrip(b"\r\n")),
                ),
            )
        )
        offset = end
    raise _Unsupported("frontmatter_malformed")


def interpret_structure(content, *, output_format):
    """Read immutable in-memory bytes into bounded source-neutral structure facts."""
    raw = content.data
    fields, body_start, status, issues = (), 0, "supported", ()
    try:
        if output_format != 7:
            raise _Unsupported("format_unsupported")
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise _Unsupported("encoding_uncertain") from error
        if (
            raw.startswith(b"\xef\xbb\xbf")
            or any(c < 32 and c not in (9, 10, 13) for c in raw)
            or b"\r" in raw.replace(b"\r\n", b"")
        ):
            raise _Unsupported("encoding_uncertain")
        lines = raw.splitlines(keepends=True)
        if lines and lines[0].rstrip(b"\r\n") == b"---":
            fields, body_start = _fields(lines)
        elif raw.startswith(b"---"):
            raise _Unsupported("frontmatter_malformed")
    except _Unsupported as error:
        issues = (str(error),)
        status = "opaque" if issues == ("encoding_uncertain",) else "unsupported"
    return StructuredDocument(
        schema_id="brz2obsidian.structured-document",
        schema_version=1,
        output_format=output_format,
        content=content,
        status=status,
        issues=issues,
        fields=fields,
        body=StructureSpan(start=body_start, end=len(raw)),
    )


def _prose_lines(body):
    lines = body.splitlines(keepends=True)
    text = [line.rstrip(b"\r\n") for line in lines]
    if len(set(text)) != len(text):
        raise _Unsupported("prose_ambiguous")
    if any(
        line.startswith((b"    ", b"\t"))
        or re.match(rb"^\s*(#|[-*+] |[0-9]+[.)] |>|`|~|<|\||\t|---$)", line)
        or any(c in line for c in (b"[[", b"](", b"`", b"<"))
        for line in text
    ):
        raise _Unsupported("prose_unsupported")
    return lines


def _edits(original, changed):
    before, after = _prose_lines(original), _prose_lines(changed)
    positions = {line: index for index, line in enumerate(after)}
    anchors = [positions[line] for line in before if line in positions]
    if anchors != sorted(anchors):
        raise _Unsupported("prose_ambiguous")
    offsets = [0]
    for line in before:
        offsets.append(offsets[-1] + len(line))
    return tuple(
        StructureByteEdit(
            span=StructureSpan(start=offsets[a], end=offsets[b]),
            expected=b"".join(before[a:b]),
            replacement=b"".join(after[c:d]),
        )
        for kind, a, b, c, d in SequenceMatcher(
            None, before, after, autojunk=False
        ).get_opcodes()
        if kind != "equal"
    )


def align_structure(original, current, incoming):
    """Supply explicit body alignment facts without deciding a merged result."""
    bodies = tuple(
        doc.content.data[doc.body.start : doc.body.end]
        for doc in (original, current, incoming)
    )
    old_body, local_body, source_body = bodies
    local_edits, source_edits, alignment, issues = (), (), "supported", ()
    try:
        if source_body == old_body:
            local_edits = (
                ()
                if local_body == old_body
                else (
                    StructureByteEdit(
                        span=StructureSpan(start=0, end=len(old_body)),
                        expected=old_body,
                        replacement=local_body,
                    ),
                )
            )
        else:
            local_edits = _edits(old_body, local_body)
            source_edits = _edits(old_body, source_body)
    except _Unsupported as error:
        issues = (str(error),)
        alignment = "ambiguous" if issues == ("prose_ambiguous",) else "unsupported"
    return StructureComparison(
        schema_id="brz2obsidian.structure-comparison",
        schema_version=1,
        original=original,
        current=current,
        incoming=incoming,
        alignment=alignment,
        issues=issues,
        local_edits=local_edits,
        source_edits=source_edits,
    )
