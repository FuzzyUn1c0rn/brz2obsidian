"""Canonical reference validation, independent of any source syntax."""

from hashlib import sha256

from brz2obsidian.contracts import Issue, MigrationRefused


def validate_references(snapshot, phase="analysis"):
    items = {i.key: i for i in snapshot.items}
    assets = {a.asset_id: a for a in snapshot.assets}
    known_evidence = {e.key for e in snapshot.original_evidence} | {
        e.identity for e in snapshot.accounting.entries
    }
    for document in snapshot.documents:
        digest = sha256(document.text.encode("utf-8")).hexdigest()
        previous_end = 0
        for span in sorted(document.references, key=lambda s: s.start):
            valid = (
                document.text_digest == digest == span.document_digest
                and 0 <= span.start < span.end <= len(document.text)
                and span.start >= previous_end
                and document.text[span.start : span.end] == span.expected_original
            )
            if span.kind == "item":
                target = items.get(span.target)
                valid = (
                    valid
                    and target is not None
                    and target.live
                    and target.role != "system"
                )
            else:
                target = assets.get(span.target)
                valid = (
                    valid
                    and target is not None
                    and target.owner == document.owner
                    and target.role == "image"
                    and target.availability == "present"
                    and span.destination_start is not None
                    and span.destination_end is not None
                    and span.start
                    <= span.destination_start
                    < span.destination_end
                    <= span.end
                )
            normalization = span.presentation_normalization
            if normalization:
                valid = valid and (
                    span.kind == "image"
                    and normalization.presentation == "responsive"
                    and normalization.basis == "document.text/unicode_codepoints"
                    and normalization.document_digest == digest
                    and span.destination_start
                    <= normalization.start
                    < normalization.end
                    <= span.destination_end
                    and document.text[normalization.start : normalization.end]
                    == normalization.declaration
                    and bool(document.evidence)
                    and set(document.evidence) <= known_evidence
                )
            if not valid:
                raise MigrationRefused(
                    (
                        Issue(
                            code="invalid_reference",
                            phase=phase,
                            message="Reference bounds, overlap, exact text, digest or canonical binding is invalid",
                            affected=(document.key, span.target),
                            evidence=document.evidence,
                            guidance="Parse and bind references against the adapted document text and its digest before planning or rendering.",
                        ),
                    )
                )
            previous_end = span.end


def image_presentation_issues(snapshot):
    return tuple(
        Issue(
            code="image_presentation_normalized",
            severity="warning",
            phase="analysis",
            message=f"Original image declaration {span.presentation_normalization.declaration} uses ordinary responsive inline Markdown presentation; exact percentage sizing is not reproduced.",
            affected=(
                document.owner,
                document.key,
                span.target,
                f"reference:{document.key}:{index}",
            ),
            evidence=document.evidence,
            guidance="Review image placement and readability in the affected note. Adjust the note manually if desired; intact source image bytes and exact declarations remain preserved.",
        )
        for document in sorted(snapshot.documents, key=lambda d: d.key)
        for index, span in enumerate(document.references)
        if span.presentation_normalization
    )
