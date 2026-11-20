"""Interpret generated sections and their retained layout."""

import re
from itertools import pairwise

from brz2obsidian.contracts import OwnedSection, StructureByteEdit, StructureSpan


class SectionUnsupported(ValueError):
    pass


def _locate(raw, basis, targets):
    allowed = {
        "relationship": (b"## Parents", b"## Children", b"## Related"),
        "resource": (b"## Resources",),
    }
    if basis.heading not in allowed[basis.kind]:
        raise SectionUnsupported("section_ownership_unknown")
    lines = raw.splitlines(keepends=True)
    starts = [
        i
        for i, line in enumerate(lines)
        if line.rstrip(b"\r\n").strip().lower() == basis.heading.lower()
    ]
    if len(starts) != 1:
        raise SectionUnsupported("section_boundary_ambiguous")
    index = starts[0]
    if lines[index].rstrip(b"\r\n") != basis.heading:
        raise SectionUnsupported("section_boundary_ambiguous")
    start = sum(map(len, lines[:index]))
    selected, entries = [lines[index]], []
    for line in lines[index + 1 :]:
        text = line.rstrip(b"\r\n")
        if not text:
            selected.append(line)
            continue
        if not text.startswith(b"- "):
            break
        match = re.fullmatch(rb"- (\[\[[^\[\]\r\n|#^]+(?:\|[^\[\]\r\n]+)?\]\])", text)
        if match is None:
            raise SectionUnsupported("section_entry_unsupported")
        entries.append(match[1].decode("utf-8"))
        selected.append(line)
    if not entries:
        raise SectionUnsupported("section_entry_unsupported")
    selected_targets = []
    for entry in entries:
        matches = [
            t for t in targets if t.kind == basis.kind and entry in t.representations
        ]
        if len(matches) != 1 or matches[0].status != "safe":
            raise SectionUnsupported("section_target_unknown")
        selected_targets.append(matches[0])
    ids = [t.target_id for t in selected_targets]
    if len(set(ids)) != len(ids):
        raise SectionUnsupported("section_duplicate_entry")
    section = b"".join(selected)
    return OwnedSection(
        section_id=basis.section_id,
        kind=basis.kind,
        span=StructureSpan(start=start, end=start + len(section)),
        raw=section,
        entries=tuple(entries),
        targets=tuple(selected_targets),
    )


def interpret_sections(content, bases, body_start, targets):
    if len({b.section_id for b in bases}) != len(bases):
        raise SectionUnsupported("section_ownership_ambiguous")
    sections = []
    for basis in bases:
        original = _locate(basis.original.data, basis, targets)
        if original.span != basis.span:
            raise SectionUnsupported("section_basis_unbound")
        section = _locate(content.data, basis, targets)
        if section.span.start < body_start:
            raise SectionUnsupported("section_basis_unbound")
        sections.append(section)
    sections.sort(key=lambda s: s.span.start)
    if any(a.span.end > b.span.start for a, b in pairwise(sections)):
        raise SectionUnsupported("section_boundary_ambiguous")
    return tuple(sections)


def _relationship_end(lines, heading_index):
    return next(
        (
            index
            for index in range(heading_index + 1, len(lines))
            if lines[index].strip() and not lines[index].startswith(b"- ")
        ),
        len(lines),
    )


def retained_relationship_survives(original, current, heading):
    """Prove the generated section survives an insertion-only local edit."""
    if original == current or (
        original.endswith(b"\n") and current.startswith(original)
    ):
        return True
    heading = b"## " + heading.encode()
    original_lines = original.splitlines(keepends=True)
    starts = [
        index
        for index, line in enumerate(original_lines)
        if line.rstrip(b"\r\n") == heading
    ]
    if len(starts) != 1:
        return False
    (start,) = starts
    end = _relationship_end(original_lines, start)
    prefix = b"".join(original_lines[:start])
    suffix = b"".join(original_lines[end:])
    if (
        not prefix.strip()
        or not suffix.strip()
        or not current.startswith(prefix)
        or not current.endswith(suffix)
        or current.count(prefix) != 1
        or current.count(suffix) != 1
    ):
        return False
    middle = current[len(prefix) : -len(suffix)].splitlines(keepends=True)
    if any(
        line.lstrip().startswith(b"#") and line.rstrip(b"\r\n") != heading
        for line in middle
    ):
        return False
    anchor = next((index for index, line in enumerate(middle) if line.strip()), None)
    if anchor is None or middle[anchor].rstrip(b"\r\n") != heading:
        return False
    retained = tuple(line for line in original_lines[start + 1 : end] if line.strip())
    rows = iter(middle[anchor + 1 : _relationship_end(middle, anchor)])
    return bool(retained) and all(
        any(actual == expected for actual in rows) for expected in retained
    )


def align_sections(documents, gap_edits):
    original = documents[0]
    if any(
        tuple(s.section_id for s in d.owned_sections)
        != tuple(s.section_id for s in original.owned_sections)
        for d in documents
    ):
        raise SectionUnsupported("section_boundary_ambiguous")
    local_edits, source_edits = [], []
    cursors = [d.body.start for d in documents]
    for sections in zip(*(d.owned_sections for d in documents), strict=True):
        gaps = tuple(
            d.content.data[cursor : s.span.start]
            for d, cursor, s in zip(documents, cursors, sections, strict=True)
        )
        edits = gap_edits(*gaps)
        offset = cursors[0] - original.body.start
        for destination, group in zip((local_edits, source_edits), edits, strict=True):
            destination.extend(
                e.model_copy(
                    update={
                        "span": StructureSpan(
                            start=e.span.start + offset, end=e.span.end + offset
                        )
                    }
                )
                for e in group
            )
        old, local, source = sections
        span = StructureSpan(
            start=old.span.start - original.body.start,
            end=old.span.end - original.body.start,
        )
        for destination, changed in ((local_edits, local), (source_edits, source)):
            if changed.raw != old.raw:
                destination.append(
                    StructureByteEdit(
                        span=span, expected=old.raw, replacement=changed.raw
                    )
                )
        cursors = [s.span.end for s in sections]
    tails = tuple(
        d.content.data[cursor : d.body.end]
        for d, cursor in zip(documents, cursors, strict=True)
    )
    offset = cursors[0] - original.body.start
    for destination, group in zip(
        (local_edits, source_edits), gap_edits(*tails), strict=True
    ):
        destination.extend(
            e.model_copy(
                update={
                    "span": StructureSpan(
                        start=e.span.start + offset, end=e.span.end + offset
                    )
                }
            )
            for e in group
        )
    return tuple(local_edits), tuple(source_edits)
