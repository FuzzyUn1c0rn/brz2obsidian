"""Qualified scoped Markdown, reusing pure text/reference grammars."""

import base64
import hashlib
from uuid import UUID

from brz2obsidian.contracts import MigrationRefused, SourceFinding
from brz2obsidian.sources.thebrain.inserts import adapt_note, trace_adapted_references
from brz2obsidian.sources.thebrain.literals import adapt_literals, source_position
from brz2obsidian.sources.thebrain.notes import (
    bind_note_references,
    compact_thought_identity,
    trace_note_references,
)
from brz2obsidian.sources.thebrain.scope import contains_omitted_identity

from .errors import refuse, with_subject


def scope_text(text, excluded):
    try:
        adapted, edits = adapt_literals(text)
        references = trace_note_references(adapted, excluded)
        removals = [
            r
            for r in references
            if r.kind == "item" and compact_thought_identity(r.target) in excluded
        ]
        removed = {compact_thought_identity(r.target) for r in removals}
        for reference in reversed(removals):
            begin, end = (
                source_position(reference.start, edits),
                source_position(reference.end, edits),
            )
            text = text[:begin] + text[end:]
        tokens = {
            token
            for key in excluded
            for token in (
                key,
                key.replace("-", ""),
                base64.urlsafe_b64encode(UUID(key).bytes_le).decode().rstrip("="),
            )
        }
        if contains_omitted_identity(text, tokens):
            refuse("Excluded note associations cannot be removed safely")
        return text, removed
    except MigrationRefused:
        raise


def bind_documents(documents, assets, included, *, with_findings=False, subjects=None):
    from .capture import canonical

    result, findings = [], []
    for document in documents:
        try:
            adapted, edits, losses = adapt_note(document.text)
            for loss in losses:
                findings.append(
                    SourceFinding(
                        kind="formatting_loss",
                        rule_id="local-api.note-formatting.v1",
                        affected=tuple(sorted((document.owner, document.key))),
                        observed_json=canonical(loss).decode("utf-8"),
                        evidence=document.evidence,
                    )
                )
            document = document.model_copy(
                update={
                    "text": adapted,
                    "text_digest": hashlib.sha256(adapted.encode("utf-8")).hexdigest(),
                    "text_adaptations": edits,
                    "references": trace_adapted_references(adapted, edits),
                }
            )
            bound = []
            for reference in document.references:
                if reference.kind == "item":
                    target = compact_thought_identity(reference.target)
                    if target not in included:
                        refuse("A note reference has no included source target")
                    bound.append(
                        reference.model_copy(
                            update={"target": target, "source_target": reference.target}
                        )
                    )
                else:
                    # Only the pure image-path/span binder runs here. No archive
                    # thought declarations or flags are manufactured.
                    image_document = document.model_copy(
                        update={"references": (reference,)}
                    )
                    bound.extend(
                        bind_note_references(image_document, assets, {}).references
                    )
            result.append(document.model_copy(update={"references": tuple(bound)}))
        except MigrationRefused as error:
            raise with_subject(
                error, "document", (subjects or {}).get(document.owner)
            ) from None
    return (result, findings) if with_findings else result
