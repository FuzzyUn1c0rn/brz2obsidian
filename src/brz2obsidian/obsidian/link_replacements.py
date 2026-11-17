"""Render one offered destination, then prove its meaning with the link reader."""

import posixpath
from urllib.parse import quote

from brz2obsidian.contracts import ExactContent

from .links import interpret_links


def render_link_replacement(
    document, occurrence_id, selected, *, targets, target_facts
):
    occurrence = next(
        (item for item in document.occurrences if item.occurrence_id == occurrence_id),
        None,
    )
    if (
        occurrence is None
        or selected.status != "resolved"
        or selected.path is None
        or document.content.data[occurrence.span.start : occurrence.span.end]
        != occurrence.raw
    ):
        raise ValueError("A bound resolved link occurrence is required")

    def agrees(raw, expected, *, output_format=7, expected_query=None):
        parsed = interpret_links(
            ExactContent(data=raw),
            document_id=document.document_id,
            source_path=document.source_path,
            path_mode=document.path_mode,
            targets=targets,
            target_facts=target_facts,
            inventory=document.inventory,
            output_format=output_format,
        )
        return (
            parsed.status == "supported"
            and len(parsed.occurrences) == 1
            and parsed.occurrences[0].raw == raw
            and parsed.occurrences[0].syntax == occurrence.syntax
            and parsed.occurrences[0].embedded == occurrence.embedded
            and parsed.occurrences[0].meaning == expected
            and (
                expected_query is None or parsed.occurrences[0].query == expected_query
            )
        )

    relative_markdown = (
        document.path_mode == "vault"
        and document.status == "supported"
        and occurrence.syntax == "markdown"
        and occurrence.query is not None
        and occurrence.meaning.status == "resolved"
        and agrees(
            occurrence.raw,
            occurrence.meaning,
            output_format=8,
            expected_query=occurrence.query,
        )
        and not agrees(occurrence.raw, occurrence.meaning)
    )
    output_format = 8 if relative_markdown else 7
    if agrees(occurrence.raw, selected, output_format=output_format):
        return occurrence.raw
    path = selected.path
    if document.path_mode == "relative" or relative_markdown:
        path = posixpath.relpath(path, posixpath.dirname(document.source_path) or ".")
        if relative_markdown and not path.startswith(("../", "./")):
            path = "./" + path
    fragment = ""
    if selected.fragment is not None:
        fragment = (
            "^" if selected.fragment.kind == "block" else ""
        ) + selected.fragment.value
    prefix = "!" if occurrence.embedded else ""
    if occurrence.syntax == "wiki":
        destination = path + ("#" + fragment if fragment else "")
        display = selected.display_text
        # An implicit wiki label changes when its destination changes.
        alias = "|" + display if display != destination else ""
        replacement = f"{prefix}[[{destination}{alias}]]".encode()
    else:
        destination = quote(path, safe="/-._~")
        if fragment:
            destination += "#" + quote(fragment, safe="#^-._~")
        start = occurrence.destination_span.start - occurrence.span.start
        end = occurrence.destination_span.end - occurrence.span.start
        original = occurrence.raw[start:end]
        if original.startswith(b"<") and original.endswith(b">"):
            destination = "<" + destination + ">"
        # Retain the original Markdown label and embed marker byte for byte.
        replacement = (
            occurrence.raw[:start] + destination.encode() + occurrence.raw[end:]
        )
    if not agrees(replacement, selected, output_format=output_format):
        raise ValueError(
            "The selected destination cannot preserve the offered link meaning"
        )
    return replacement
