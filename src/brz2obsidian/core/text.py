"""Validate declared text edits without interpreting source-specific syntax."""

import json
from hashlib import sha256

from brz2obsidian.contracts import Issue, MigrationRefused, TextAdaptation


def validate_text_adaptations(snapshot):
    known_evidence = {e.key for e in snapshot.original_evidence} | {
        e.identity for e in snapshot.accounting.entries
    }
    for document in snapshot.documents:
        restored = document.text
        previous_end = delta = 0
        valid = document.text_digest == sha256(document.text.encode()).hexdigest()
        if document.text_adaptations:
            valid = (
                valid
                and bool(document.evidence)
                and set(document.evidence) <= known_evidence
            )
        for edit in document.text_adaptations:
            valid = valid and (
                edit.source_basis == "scoped_source_text/unicode_codepoints"
                and edit.adapted_basis == "document.text/unicode_codepoints"
                and 0 <= previous_end <= edit.start < edit.end
                and edit.end - edit.start == len(edit.before)
                and edit.before != edit.after
                and edit.adapted_start == edit.start + delta
                and edit.adapted_end == edit.adapted_start + len(edit.after)
                and 0 <= edit.adapted_start <= edit.adapted_end <= len(document.text)
                and document.text[edit.adapted_start : edit.adapted_end] == edit.after
            )
            previous_end = edit.end
            delta += len(edit.after) - len(edit.before)
        for edit in reversed(document.text_adaptations):
            restored = (
                restored[: edit.adapted_start]
                + edit.before
                + restored[edit.adapted_end :]
            )
        digest = sha256(restored.encode()).hexdigest()
        valid = valid and all(
            edit.source_digest == digest
            and restored[edit.start : edit.end] == edit.before
            for edit in document.text_adaptations
        )
        if not valid:
            raise MigrationRefused(
                (
                    Issue(
                        code="invalid_reference",
                        phase="analysis",
                        message="Declared text adaptations have invalid bounds, exact text, coordinate basis or digest",
                        affected=(document.owner, document.key),
                        evidence=document.evidence,
                        guidance="Declare nonoverlapping edits against the scoped source text and bind references against the adapted document text.",
                    ),
                )
            )


def _require(condition):
    if not condition:
        raise ValueError("Invalid staged notice evidence")


def validate_image_notice_evidence(snapshot):
    """Check staged exact edits without interpreting any source image syntax."""
    kinds = {"image_unavailable", "markdown_insert_image_unavailable"}
    by_document = {}
    valid = True
    try:
        documents = {document.key: document for document in snapshot.documents}
        for finding in snapshot.findings:
            if finding.kind != "unavailable_image_reference":
                continue
            observed = json.loads(finding.observed_json)
            document = documents[observed["document"]]
            _require(observed["owner"] == document.owner)
            by_document.setdefault(document.key, []).append(observed)
        for document in snapshot.documents:
            expected_indices = {
                index
                for index, edit in enumerate(document.text_adaptations)
                if edit.kind in kinds
            }
            observations = by_document.get(document.key, [])
            if not expected_indices:
                _require(not observations)
                continue
            _require(observations)
            source = document.text
            for edit in reversed(document.text_adaptations):
                source = (
                    source[: edit.adapted_start]
                    + edit.before
                    + source[edit.adapted_end :]
                )
            source_digest = sha256(source.encode()).hexdigest()
            base = {
                edit.start: edit
                for edit in document.text_adaptations
                if edit.kind not in kinds
            }
            actual_indices, replacements, source_spans = set(), [], []
            for observed in observations:
                occurrence = observed["source_reference"]
                intermediate = observed["intermediate_reference"]
                notice = observed["notice"]
                composition = observed["composition"]
                index = composition["flat_edit"]
                _require(type(index) is int and index in expected_indices)
                edit = document.text_adaptations[index]
                actual_indices.add(index)
                for row in (occurrence, intermediate, notice):
                    _require(type(row["start"]) is int and type(row["end"]) is int)
                    _require(0 <= row["start"] < row["end"])
                _require(
                    edit.start <= occurrence["start"] < occurrence["end"] <= edit.end
                )
                _require(
                    source[occurrence["start"] : occurrence["end"]]
                    == occurrence["before"]
                )
                _require(occurrence["source_digest"] == source_digest)
                _require(
                    edit.adapted_start
                    <= notice["start"]
                    < notice["end"]
                    <= edit.adapted_end
                )
                _require(
                    document.text[notice["start"] : notice["end"]] == notice["text"]
                )
                _require(notice["document_digest"] == document.text_digest)
                _require(type(composition["base_edits"]) is list)
                inserted = False
                for value in composition["base_edits"]:
                    prior = TextAdaptation.model_validate(value)
                    _require(prior.kind in {"literal_text", "markdown_insert"})
                    _require(edit.start <= prior.start < prior.end <= edit.end)
                    _require(prior.start not in base or base[prior.start] == prior)
                    base[prior.start] = prior
                    inserted |= prior.kind == "markdown_insert"
                _require(inserted == (edit.kind == "markdown_insert_image_unavailable"))
                source_spans.append((occurrence["start"], occurrence["end"]))
                replacements.append((intermediate, notice))
            _require(actual_indices == expected_indices)
            _require(
                all(
                    left[1] <= right[0]
                    for left, right in zip(
                        sorted(source_spans), sorted(source_spans)[1:]
                    )
                )
            )
            intermediate_text = source
            base_edits = tuple(base[key] for key in sorted(base))
            for edit in reversed(base_edits):
                intermediate_text = (
                    intermediate_text[: edit.start]
                    + edit.after
                    + intermediate_text[edit.end :]
                )
            staged = document.model_copy(
                update={
                    "text": intermediate_text,
                    "text_digest": sha256(intermediate_text.encode()).hexdigest(),
                    "text_adaptations": base_edits,
                }
            )
            validate_text_adaptations(
                snapshot.model_copy(update={"documents": (staged,)})
            )
            previous_end = delta = 0
            for occurrence, notice in sorted(
                replacements, key=lambda pair: pair[0]["start"]
            ):
                _require(
                    previous_end
                    <= occurrence["start"]
                    < occurrence["end"]
                    <= len(intermediate_text)
                )
                _require(
                    intermediate_text[occurrence["start"] : occurrence["end"]]
                    == occurrence["before"]
                )
                _require(occurrence["document_digest"] == staged.text_digest)
                _require(notice["start"] == occurrence["start"] + delta)
                _require(notice["end"] == notice["start"] + len(notice["text"]))
                delta += len(notice["text"]) - len(occurrence["before"])
                previous_end = occurrence["end"]
            final = intermediate_text
            for occurrence, notice in sorted(
                replacements, key=lambda pair: pair[0]["start"], reverse=True
            ):
                final = (
                    final[: occurrence["start"]]
                    + notice["text"]
                    + final[occurrence["end"] :]
                )
            _require(final == document.text)
    except KeyError, IndexError, TypeError, ValueError, MigrationRefused:
        valid = False
    if not valid:
        raise MigrationRefused(
            (
                Issue(
                    code="invalid_reference",
                    phase="analysis",
                    message="Image notice transformation evidence is missing or inconsistent",
                    guidance="Rebind each original occurrence, insert stage and final notice against exact source evidence.",
                ),
            )
        )
