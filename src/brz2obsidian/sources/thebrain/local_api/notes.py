"""Qualified scoped Markdown, reusing pure text/reference grammars."""

import base64
import hashlib
from functools import partial
from uuid import UUID

from brz2obsidian.contracts import MigrationRefused, SourceFinding
from brz2obsidian.diagnostics import with_subject
from brz2obsidian.sources.thebrain.inserts import trace_adapted_references
from brz2obsidian.sources.thebrain.literals import source_position
from brz2obsidian.sources.thebrain.notes import (
    bind_note_references,
    compact_thought_identity,
    trace_note_references,
)
from brz2obsidian.sources.thebrain.scope import contains_omitted_identity

from .errors import refuse
from .markdown import adapt_literals, adapt_note


def _omitted_tokens(excluded):
    return {
        token
        for key in excluded
        for token in (
            key,
            key.replace("-", ""),
            base64.urlsafe_b64encode(UUID(key).bytes_le).decode().rstrip("="),
        )
    }


def scope_text(
    text, excluded, *, brain_id=None, allow_qualified=False, allow_literal_tokens=False
):
    adapted, edits = adapt_literals(text, allow_literal_tokens=allow_literal_tokens)
    references = trace_note_references(
        adapted, excluded, allow_qualified=allow_qualified
    )
    removals, removed = [], set()
    for reference in references:
        if reference.kind == "item":
            target = compact_thought_identity(
                reference.target, brain_id=brain_id, allow_qualified=allow_qualified
            )
            if target in excluded:
                removals.append(reference)
                removed.add(target)
    for reference in reversed(removals):
        begin, end = (
            source_position(reference.start, edits),
            source_position(reference.end, edits),
        )
        text = text[:begin] + text[end:]
    tokens = _omitted_tokens(excluded)
    removed_spans = {(r.start, r.end) for r in removals}
    if (
        contains_omitted_identity(text, tokens)
        or allow_qualified
        and any(
            contains_omitted_identity(value, tokens)
            for reference in references
            if (reference.start, reference.end) not in removed_spans
            for value in (reference.target, reference.display_text)
        )
    ):
        refuse("Excluded note associations cannot be removed safely")
    return text, removed


def _bind_references(document, assets, included, brain_id, allow_qualified):
    bound = []
    for reference in document.references:
        if reference.kind == "item":
            target = compact_thought_identity(
                reference.target,
                brain_id=brain_id,
                allow_qualified=allow_qualified,
            )
            if target is None:
                continue
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
            image_document = document.model_copy(update={"references": (reference,)})
            bound.extend(bind_note_references(image_document, assets, {}).references)
    return tuple(bound)


def bind_documents(
    documents,
    assets,
    included,
    *,
    with_findings=False,
    allow_literal_tokens=False,
    preserve_bom=False,
    preserve_table_colors=False,
    legacy_tables=False,
    previous_tables=False,
    compact_tables=False,
    legacy_table_boundaries=False,
    preserve_table_warnings=False,
    subjects=None,
    brain_id=None,
    allow_qualified=False,
    excluded=None,
    profile_version="1",
    image_absences=None,
):
    from .capture import canonical

    if allow_qualified and excluded is None:
        refuse("Current note binding needs authoritative exclusion context")
    tokens = _omitted_tokens(excluded) if allow_qualified else set()
    result, findings = [], []
    for document in documents:
        try:
            adapted, edits, losses = adapt_note(
                document.text,
                allow_literal_tokens=allow_literal_tokens,
                preserve_bom=preserve_bom,
                preserve_table_colors=preserve_table_colors,
                legacy_tables=legacy_tables,
                previous_tables=previous_tables,
                compact_tables=compact_tables,
                legacy_table_boundaries=legacy_table_boundaries,
                preserve_table_warnings=preserve_table_warnings,
            )
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
                    "references": trace_adapted_references(
                        adapted, edits, allow_qualified=allow_qualified
                    ),
                }
            )
            if allow_qualified and (
                contains_omitted_identity(document.text, tokens)
                or any(
                    contains_omitted_identity(value, tokens)
                    for reference in document.references
                    for value in (reference.target, reference.display_text)
                )
            ):
                refuse("Excluded note associations cannot be removed safely")
            if profile_version in {"4", "5"}:
                from ..unavailable_images import adapt_unavailable_images

                document, image_findings = adapt_unavailable_images(
                    document,
                    assets,
                    basis="api_undeclared_inventory",
                    declared_absence=image_absences,
                    preparation=partial(
                        adapt_note,
                        allow_literal_tokens=allow_literal_tokens,
                        preserve_bom=preserve_bom,
                        preserve_table_colors=preserve_table_colors,
                        legacy_tables=legacy_tables,
                        previous_tables=previous_tables,
                        compact_tables=compact_tables,
                        legacy_table_boundaries=legacy_table_boundaries,
                        preserve_table_warnings=preserve_table_warnings,
                    ),
                )
                findings.extend(image_findings)
            bound = _bind_references(
                document, assets, included, brain_id, allow_qualified
            )
            result.append(document.model_copy(update={"references": bound}))
        except MigrationRefused as error:
            raise with_subject(
                error, "document", (subjects or {}).get(document.owner)
            ) from None
    return (result, findings) if with_findings else result
