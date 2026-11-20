"""Interpret one leading UTF-8 signature without changing retained source text."""

from hashlib import sha256

from brz2obsidian.contracts import TextAdaptation
from brz2obsidian.sources.thebrain.inserts import adapt_note as _adapt_note
from brz2obsidian.sources.thebrain.literals import adapt_literals as _adapt_literals


def _signature_edits(original, edits):
    digest = sha256(original.encode("utf-8")).hexdigest()
    return (
        TextAdaptation(
            start=0,
            end=1,
            before="\ufeff",
            after="",
            adapted_start=0,
            adapted_end=0,
            source_digest=digest,
        ),
        *(
            edit.model_copy(
                update={
                    "start": edit.start + 1,
                    "end": edit.end + 1,
                    "source_digest": digest,
                }
            )
            for edit in edits
        ),
    )


def adapt_literals(text, *, allow_literal_tokens=False):
    if not text.startswith("\ufeff"):
        return _adapt_literals(text, allow_literal_tokens=allow_literal_tokens)
    adapted, edits = _adapt_literals(
        text[1:], allow_literal_tokens=allow_literal_tokens
    )
    return adapted, _signature_edits(text, edits)


def adapt_note(
    text,
    *,
    allow_literal_tokens=False,
    preserve_bom=False,
    preserve_table_colors=False,
    legacy_tables=False,
    previous_tables=False,
    compact_tables=False,
    legacy_table_boundaries=False,
    preserve_table_warnings=False,
    _provenance=None,
):
    if preserve_bom or not text.startswith("\ufeff"):
        return _adapt_note(
            text,
            allow_literal_tokens=allow_literal_tokens,
            preserve_table_colors=preserve_table_colors,
            legacy_tables=legacy_tables,
            previous_tables=previous_tables,
            compact_tables=compact_tables,
            legacy_table_boundaries=legacy_table_boundaries,
            preserve_table_warnings=preserve_table_warnings,
            _provenance=_provenance,
        )
    adapted, edits, losses = _adapt_note(
        text[1:],
        allow_literal_tokens=allow_literal_tokens,
        preserve_table_colors=preserve_table_colors,
        legacy_tables=legacy_tables,
        previous_tables=previous_tables,
        compact_tables=compact_tables,
        legacy_table_boundaries=legacy_table_boundaries,
        preserve_table_warnings=preserve_table_warnings,
        _provenance=_provenance,
    )
    return adapted, _signature_edits(text, edits), losses
