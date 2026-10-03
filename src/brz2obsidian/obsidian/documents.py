"""Apply approved exact-source edits without rebuilding authored Markdown."""

import posixpath
from urllib.parse import quote

from brz2obsidian.contracts import Issue, MigrationRefused

from .relationships import note_link


def render_document(document, note_path, plan):
    items = {t.item_key: t for t in plan.item_targets}
    assets = {t.asset_id: t for t in plan.asset_targets}
    text = document.text
    for span in sorted(document.references, key=lambda s: s.start, reverse=True):
        assigned = (items if span.kind == "item" else assets).get(span.target)
        if assigned is None or assigned.relative_path is None:
            raise MigrationRefused(
                (
                    Issue(
                        code="invalid_reference",
                        phase="rendering",
                        message="Canonical reference has no assigned vault target",
                        affected=(document.key, span.target),
                        guidance="Plan every referenced item and preserved image before rendering.",
                    ),
                )
            )
        if span.kind == "item":
            replacement = note_link(assigned, span.display_text)
        else:
            relative = posixpath.relpath(
                assigned.relative_path, posixpath.dirname(note_path) or "."
            )
            # Keep the original authored image alt/title and replace only its destination.
            replacement = (
                span.expected_original[: span.destination_start - span.start]
                + quote(relative, safe="/")
                + span.expected_original[span.destination_end - span.start :]
            )
        text = text[: span.start] + replacement + text[span.end :]
    return text
