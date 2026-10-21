"""Independent binding and atomicity of supplied section facts; no text parsing."""

from brz2obsidian.contracts import StructureSpan
from brz2obsidian.core.formats import output_semantics
from brz2obsidian.core.reference_targets import validate_targets


def validate_section_document(document, bases, *, target_safety=True):
    ids = [s.section_id for s in document.owned_sections]
    if len(set(ids)) != len(ids) or not set(ids) <= set(bases):
        raise ValueError("structure_unbound")
    end = document.body.start
    for section in document.owned_sections:
        if (
            section.kind != bases[section.section_id].kind
            or section.span.start < end
            or section.span.end > document.body.end
            or document.content.data[section.span.start : section.span.end]
            != section.raw
            or len(section.targets) != len(section.entries)
        ):
            raise ValueError("structure_unbound")
        if target_safety:
            validate_targets(section.targets)
        if any(
            t.kind != section.kind or entry not in t.representations
            for entry, t in zip(section.entries, section.targets, strict=True)
        ):
            raise ValueError("structure_conflict")
        end = section.span.end


def validate_section_facts(
    subject, baseline_identity, source_version, *, current_target_safety=True
):
    comparison = subject.structure
    documents = (comparison.original, comparison.current, comparison.incoming)
    bases = {b.section_id: b for b in comparison.section_bases}
    if len(bases) != len(comparison.section_bases):
        raise ValueError("structure_unbound")
    for basis in bases.values():
        if (
            basis.original.data != subject.baseline.content.data
            or output_semantics(basis.output_identity)
            != output_semantics(baseline_identity)
            or basis.source_version != source_version
            or basis.item_id != subject.item_id
            or basis.facet != subject.facet
            or basis.span.end > len(basis.original.data)
            or not basis.heading
            or basis.span.start + len(basis.heading) > basis.span.end
            or basis.original.data[
                basis.span.start : basis.span.start + len(basis.heading)
            ]
            != basis.heading
        ):
            raise ValueError("structure_unbound")
    for index, document in enumerate(documents):
        validate_section_document(
            document, bases, target_safety=current_target_safety and index == 1
        )
    for section in documents[0].owned_sections:
        if section.span != bases[section.section_id].span:
            raise ValueError("structure_unbound")


def validate_section_combination(comparison):
    documents = (comparison.original, comparison.current, comparison.incoming)
    bases = {b.section_id: b for b in comparison.section_bases}
    for document in documents:
        validate_section_document(document, bases)
    expected = tuple(s.section_id for s in documents[0].owned_sections)
    if set(expected) != {b.section_id for b in comparison.section_bases} or any(
        tuple(s.section_id for s in document.owned_sections) != expected
        for document in documents
    ):
        raise ValueError("structure_conflict")
    for changed, edits in (
        (documents[1], comparison.local_edits),
        (documents[2], comparison.source_edits),
    ):
        for old, new in zip(
            documents[0].owned_sections, changed.owned_sections, strict=True
        ):
            start, end = (
                old.span.start - documents[0].body.start,
                old.span.end - documents[0].body.start,
            )
            touching = [
                e
                for e in edits
                if max(start, e.span.start) < min(end, e.span.end)
                or (e.span.start == e.span.end and start < e.span.start < end)
            ]
            if old.raw == new.raw:
                if touching:
                    raise ValueError("structure_unbound")
            elif (
                len(touching) != 1
                or touching[0].span != StructureSpan(start=start, end=end)
                or touching[0].expected != old.raw
                or touching[0].replacement != new.raw
            ):
                raise ValueError("structure_unbound")


def result_sections(comparison, patches, body_start):
    current, incoming = comparison.current, comparison.incoming
    results = []
    for local, source in zip(
        current.owned_sections, incoming.owned_sections, strict=True
    ):
        start, end = (
            local.span.start - current.body.start,
            local.span.end - current.body.start,
        )
        shift = sum(
            len(replacement) - (b - a) for a, b, replacement in patches if b <= start
        )
        replaced = any(a == start and b == end for a, b, _ in patches)
        selected = source if replaced else local
        results.append(
            selected.model_copy(
                update={
                    "span": StructureSpan(
                        start=body_start + start + shift,
                        end=body_start + start + shift + len(selected.raw),
                    )
                }
            )
        )
    return tuple(results)
