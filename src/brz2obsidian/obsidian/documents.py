"""Apply approved exact-source edits without rebuilding authored Markdown."""

import posixpath
from urllib.parse import quote

from .relationships import note_link


def render_document(document, note_path, plan):
    items = {t.item_key: t for t in plan.item_targets}
    assets = {t.asset_id: t for t in plan.asset_targets}
    text = document.text
    for span in sorted(document.references, key=lambda s: s.start, reverse=True):
        if span.kind == "item":
            replacement = note_link(items[span.target], span.display_text)
        else:
            relative = posixpath.relpath(
                assets[span.target].relative_path, posixpath.dirname(note_path) or "."
            )
            # Keep the original authored image alt/title and replace only its destination.
            replacement = (
                span.expected_original[: span.destination_start - span.start]
                + quote(relative, safe="/")
                + span.expected_original[span.destination_end - span.start :]
            )
        text = text[: span.start] + replacement + text[span.end :]
    return text
