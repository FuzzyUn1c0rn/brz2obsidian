"""Canonical reference validation, independent of any source syntax."""

from hashlib import sha256

from brz2obsidian.contracts import Issue, MigrationRefused


def validate_references(snapshot, phase="analysis"):
    items = {i.key: i for i in snapshot.items}
    assets = {a.asset_id: a for a in snapshot.assets}
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
            if not valid:
                raise MigrationRefused(
                    (
                        Issue(
                            code="invalid_reference",
                            phase=phase,
                            message="Reference bounds, overlap, exact text, digest or canonical binding is invalid",
                            affected=(document.key, span.target),
                            evidence=document.evidence,
                            guidance="Parse and bind references from the unchanged source document before planning or rendering.",
                        ),
                    )
                )
            previous_end = span.end
