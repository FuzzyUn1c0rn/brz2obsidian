"""Explicit unavailable-image edits, distinct from canonical asset references."""

import json
import re
import string
from hashlib import sha256
from uuid import UUID

from brz2obsidian.contracts import SourceFinding, TextAdaptation

from .inserts import trace_adapted_references
from .literals import source_position
from .notes import _refuse, image_destination, trace_note_references

RULE = "thebrain.unavailable-image.v1"


def _digest(text):
    return sha256(text.encode()).hexdigest()


def _notice(reference, location):
    label = (
        reference.display_text.replace("\\<", "<").strip()
        or location.rsplit("/", 1)[-1]
    )
    label = " ".join(label.split())
    # Entity output is never reparsed as Markdown. It cannot introduce raw
    # backticks, links, HTML, table pipes or a new block/container prefix.
    label = label.translate(
        {ord(char): f"&#{ord(char)};" for char in string.punctuation}
    )
    return "Image unavailable: " + label


def _observation(value, basis):
    if basis.startswith("api_"):
        from .local_api.capture import canonical

        return canonical(value).decode("utf-8")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def adapt_unavailable_images(
    document,
    assets,
    *,
    basis,
    members=(),
    provenance=None,
    preparation=None,
    declared_absence=None,
):
    """Adapt strictly valid references; keep each occurrence's staged proof."""
    missing = []
    absence_facts = {}
    declared_absence = declared_absence or {}
    for reference in document.references:
        if reference.kind != "image":
            continue
        location, _normalization = image_destination(document, reference)
        owned = [
            asset
            for asset in assets
            if asset.owner == document.owner and asset.original_name == location
        ]
        if (
            len(owned) == 1
            and owned[0].role == "image"
            and owned[0].availability == "present"
        ):
            continue
        declared = (
            owned[0]
            if len(owned) == 1
            and owned[0].role == "image"
            and owned[0].availability == "absent"
            and owned[0].asset_id in declared_absence
            else None
        )
        if (
            owned
            and declared is None
            or document.owner + "/.data/md-images/" + location in members
        ):
            _refuse(
                "invalid_reference",
                "Unavailable image conflicts with a source declaration or payload",
            )
        foreign_ids = {
            asset.asset_id for asset in assets if asset.owner != document.owner
        }
        try:
            filename_identity = str(UUID(location.rsplit("/", 1)[-1].rsplit(".", 1)[0]))
        except ValueError:
            filename_identity = None
        if filename_identity in foreign_ids:
            _refuse("invalid_reference", "Local image identifies another owner's asset")
        suffix = location.rsplit(".", 1)[-1].casefold() if "." in location else ""
        supported = (
            {"webp", "png", "jpg", "svg"}
            if basis.startswith("api_")
            else {"png", "jpg", "jpeg", "webp", "gif", "bmp", "avif", "svg"}
        )
        if suffix not in supported:
            _refuse(
                "unsupported_feature",
                "Unavailable local image has an unsupported declared filename kind",
            )
        absence_facts[reference.start] = (
            {
                **declared_absence[declared.asset_id],
                "asset_id": declared.asset_id,
            }
            if declared
            else {"basis": basis}
        )
        missing.append((reference, location, _notice(reference, location)))
    if not missing:
        return document, ()

    original = document.text
    for edit in reversed(document.text_adaptations):
        original = (
            original[: edit.adapted_start] + edit.before + original[edit.adapted_end :]
        )
    from .inserts import adapt_note
    from .local_api.markdown import adapt_literals

    literal, literal_edits = adapt_literals(original, allow_literal_tokens=True)
    if provenance is None:
        provenance = {}
        rebuilt, _edits, _losses = (
            preparation(original, _provenance=provenance)
            if preparation is not None
            else adapt_note(original, allow_literal_tokens=True, _provenance=provenance)
        )
        if rebuilt != document.text:
            _refuse(
                "invalid_reference",
                "Image provenance has a different insert interpretation",
            )
    if provenance["literal_text"] != literal:
        _refuse(
            "invalid_reference",
            "Image provenance has a different literal interpretation",
        )
    source_refs = {
        (reference.start, reference.end): reference
        for reference in trace_note_references(literal, allow_qualified=True)
        if reference.kind == "image"
    }
    occurrences = []
    origins = provenance["origins"]
    for reference, location, notice in missing:
        first, last = origins[reference.start], origins[reference.end - 1]
        raw_ref = source_refs.get((first, last + 1 if last is not None else None))
        copied = [
            position
            for position in origins[reference.start : reference.end]
            if position is not None
        ]
        if (
            raw_ref is None
            or reference.target != raw_ref.target
            or copied != sorted(copied)
            or any(not raw_ref.start <= position < raw_ref.end for position in copied)
        ):
            _refuse(
                "unsupported_feature",
                "Unavailable image has no exact copied source occurrence",
            )
        start = source_position(raw_ref.start, literal_edits)
        end = source_position(raw_ref.end, literal_edits)
        occurrences.append((reference, start, end, location, notice, raw_ref))

    base = document.text_adaptations
    groups = []
    for occurrence in occurrences:
        left, right = occurrence[1:3]
        changed = True
        while changed:
            changed = False
            for edit in base:
                if edit.start < right and left < edit.end:
                    bounds = min(left, edit.start), max(right, edit.end)
                    if bounds != (left, right):
                        left, right = bounds
                        changed = True
            for group in list(groups):
                if group[0] < right and left < group[1]:
                    left, right = min(left, group[0]), max(right, group[1])
                    groups.remove(group)
                    changed = True
        groups.append((left, right))
    result = [
        edit
        for edit in base
        if not any(left < edit.end and edit.start < right for left, right in groups)
    ]
    group_proofs = {}
    for left, right in groups:
        tleft = left + sum(
            len(edit.after) - len(edit.before) for edit in base if edit.end <= left
        )
        tright = right + sum(
            len(edit.after) - len(edit.before) for edit in base if edit.end <= right
        )
        after = document.text[tleft:tright]
        group_occurrences = [
            occurrence
            for occurrence in occurrences
            if left <= occurrence[1] and occurrence[2] <= right
        ]
        for reference, _start, _end, _location, notice, _raw_ref in reversed(
            group_occurrences
        ):
            after = (
                after[: reference.start - tleft]
                + notice
                + after[reference.end - tleft :]
            )
        proof = [
            edit.model_dump(mode="json")
            for edit in base
            if left < edit.end and edit.start < right
        ]
        kind = (
            "markdown_insert_image_unavailable"
            if any(edit["kind"] == "markdown_insert" for edit in proof)
            else "image_unavailable"
        )
        result.append(
            TextAdaptation(
                kind=kind,
                start=left,
                end=right,
                before=original[left:right],
                after=after,
                adapted_start=0,
                adapted_end=0,
                source_digest=_digest(original),
            )
        )
        group_proofs[left] = proof
    final, delta, edits = original, 0, []
    for edit in sorted(result, key=lambda value: value.start):
        edits.append(
            edit.model_copy(
                update={
                    "adapted_start": edit.start + delta,
                    "adapted_end": edit.start + delta + len(edit.after),
                }
            )
        )
        delta += len(edit.after) - len(edit.before)
    for edit in reversed(edits):
        final = final[: edit.start] + edit.after + final[edit.end :]

    def final_position(position):
        return position + sum(
            len(occurrence[4]) - (occurrence[0].end - occurrence[0].start)
            for occurrence in occurrences
            if occurrence[0].end <= position
        )

    code_ranges = []
    for edit in base:
        if edit.kind == "markdown_insert":
            for match in re.finditer(r"<code>[^<]*</code>", edit.after):
                begin, finish = (
                    edit.adapted_start + match.start(),
                    edit.adapted_start + match.end(),
                )
                if any(
                    occurrence[0].start < finish and begin < occurrence[0].end
                    for occurrence in occurrences
                ):
                    _refuse(
                        "invalid_reference",
                        "Active missing image overlaps generated literal code",
                    )
                code_ranges.append((final_position(begin), final_position(finish)))
    findings = []
    for reference, start, end, location, notice, raw_ref in occurrences:
        index = next(
            index
            for index, edit in enumerate(edits)
            if edit.start <= start and end <= edit.end
        )
        edit = edits[index]
        notice_start = final_position(reference.start)
        absence = absence_facts[reference.start]
        observation = {
            "owner": document.owner,
            "document": document.key,
            "source_reference": {
                "start": start,
                "end": end,
                "before": original[start:end],
                "source_digest": _digest(original),
                "uri": raw_ref.target,
                "label": raw_ref.display_text,
                "destination_start": source_position(
                    raw_ref.destination_start, literal_edits
                ),
                "destination_end": source_position(
                    raw_ref.destination_end, literal_edits
                ),
            },
            "intermediate_reference": {
                "start": reference.start,
                "end": reference.end,
                "before": reference.expected_original,
                "document_digest": document.text_digest,
            },
            "notice": {
                "start": notice_start,
                "end": notice_start + len(notice),
                "text": notice,
                "document_digest": _digest(final),
            },
            "absence": {**absence, "location": location},
            "composition": {
                "flat_edit": index,
                "base_edits": group_proofs.get(edit.start, []),
            },
        }
        findings.append(
            SourceFinding(
                kind="unavailable_image_reference",
                rule_id=(
                    "thebrain.unavailable-declared-image.v1"
                    if "asset_id" in absence
                    else RULE
                ),
                affected=(
                    (absence["asset_id"],)
                    if "asset_id" in absence
                    else tuple(sorted((document.owner, document.key)))
                ),
                evidence=document.evidence,
                observed_json=_observation(observation, basis),
            )
        )
    return document.model_copy(
        update={
            "text": final,
            "text_digest": _digest(final),
            "text_adaptations": tuple(edits),
            "references": trace_adapted_references(
                final,
                edits,
                allow_qualified=True,
                generated_code_ranges=code_ranges,
            ),
        }
    ), tuple(findings)
