"""Validate declared text edits without interpreting source-specific syntax."""

from hashlib import sha256

from brz2obsidian.contracts import Issue, MigrationRefused


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
