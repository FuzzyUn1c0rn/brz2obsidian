"""Exact-source reference tracing over Markdown parser-recognized links."""

import base64
import re
from hashlib import sha256
from html.parser import HTMLParser
from itertools import pairwise
from urllib.parse import unquote, urlsplit
from uuid import UUID

from markdown_it import MarkdownIt
from markdown_it.rules_block.state_block import StateBlock
from markdown_it.rules_inline import autolink, image, link

from brz2obsidian.contracts import Issue, MigrationRefused, ReferenceSpan


def _refuse(code, message):
    raise MigrationRefused(
        (
            Issue(
                code=code,
                phase="source",
                message=message,
                guidance="Use supported same-Brain inline Markdown references to live thoughts and archived images, then re-export.",
            ),
        )
    )


def _local(target):
    parts = urlsplit(target)
    return parts.scheme.casefold() == "brain" or (
        not parts.scheme and not parts.netloc and not target.startswith("#")
    )


class _HtmlReferences(HTMLParser):
    def handle_starttag(self, tag, attrs):
        if any(
            name in {"href", "src"} and value and _local(value) for name, value in attrs
        ):
            _refuse(
                "unsupported_feature", "HTML source-local references are not supported"
            )


def bind_note_references(document, assets, thoughts):
    """Bind parsed source destinations to canonical IDs after asset inventory."""
    bound = []
    for reference in document.references:
        destination = reference.target
        if reference.kind == "item":
            parts = urlsplit(destination)
            if parts.netloc.casefold() in {"api.thebrain.com", "api.bra.in"}:
                _refuse(
                    "unsupported_feature",
                    "Cross-Brain/server-qualified thought references are unsupported",
                )
            compact = parts.netloc
            if (
                parts.scheme != "brain"
                or not re.fullmatch(r"[A-Za-z0-9_-]{22}", compact)
                or not parts.path.startswith("/")
                or parts.query
                or parts.fragment
            ):
                _refuse(
                    "invalid_reference",
                    "Invalid or unsupported compact thought reference: " + destination,
                )
            raw = base64.urlsafe_b64decode(compact + "==")
            if base64.urlsafe_b64encode(raw).decode().rstrip("=") != compact:
                _refuse("invalid_reference", "Noncanonical compact thought identity")
            canonical = str(UUID(bytes_le=raw))
            if canonical not in thoughts or thoughts[canonical]["Kind"] == 5:
                _refuse(
                    "invalid_reference",
                    "Local thought reference does not identify a live navigable thought: "
                    + canonical,
                )
        else:
            parts = urlsplit(destination)
            location = unquote(parts.path.removeprefix(".data/md-images/"))
            if (
                not parts.path.startswith(".data/md-images/")
                or parts.query
                or parts.fragment
                or not location
                or "\\" in location
                or any(p in {"", ".", ".."} for p in location.split("/"))
            ):
                _refuse(
                    "invalid_reference",
                    "Invalid or unsupported local image destination: " + destination,
                )
            matches = [
                a.asset_id
                for a in assets
                if a.owner == document.owner
                and a.role == "image"
                and a.original_name == location
                and a.availability == "present"
            ]
            if len(matches) != 1:
                _refuse(
                    "invalid_reference",
                    "Local image does not identify one preserved owner image: "
                    + destination,
                )
            canonical = matches[0]
        bound.append(
            reference.model_copy(
                update={"target": canonical, "source_target": destination}
            )
        )
    return document.model_copy(update={"references": tuple(bound)})


class _MappedText(str):
    """Parser input whose slices retain exact original character provenance."""

    def __new__(cls, value, offsets):
        result = super().__new__(cls, value)
        result.offsets = tuple(offsets)
        return result

    def __getitem__(self, index):
        value = super().__getitem__(index)
        return (
            _MappedText(value, self.offsets[index])
            if isinstance(index, slice)
            else value
        )

    def strip(self, chars=None):
        left = len(self) - len(super().lstrip(chars))
        right = len(super().rstrip(chars))
        return self[left : max(left, right)]


class _MappedBlock(StateBlock):
    def getLines(self, begin, end, indent, keepLastLF):
        # Mirror the base parser's indentation removal, retaining the origin
        # of partially expanded tabs. Check the result against its own method.
        parts, offsets = [], []
        for line in range(begin, end):
            first = line_start = self.bMarks[line]
            last = self.eMarks[line] + (1 if line + 1 < end or keepLastLF else 0)
            width = 0
            while first < last and width < indent:
                char = self.src[first]
                if char in " \t":
                    width += 4 - (width + self.bsCount[line]) % 4 if char == "\t" else 1
                elif first - line_start < self.tShift[line]:
                    width += 1
                else:
                    break
                first += 1
            padding = max(0, width - indent)
            parts.append(" " * padding + self.src[first:last])
            offsets.extend([self.src.offsets[first - 1]] * padding)
            offsets.extend(self.src.offsets[first:last])
        value = "".join(parts)
        if value != super().getLines(begin, end, indent, keepLastLF):
            _refuse(
                "unsupported_feature", "Markdown block provenance cannot be established"
            )
        return _MappedText(value, offsets)


def trace_note_references(text: str) -> tuple[ReferenceSpan, ...]:
    """Trace parser-recognized active links into exact original text spans.

    Carry character provenance through normalization and block indentation;
    never reconstruct a document from parsed tokens.
    """
    parser = MarkdownIt("commonmark", {"store_labels": True})
    display_parser = MarkdownIt("commonmark")
    hits = []

    def display_text(value):
        children = []
        display_parser.inline.parse(value, display_parser, {}, children)
        return "".join(
            t.content
            if t.type in {"text", "code_inline"}
            else "\n"
            if t.type in {"softbreak", "hardbreak"}
            else ""
            for t in children
        )

    def instrument(rule, kind):
        def run(state, silent):
            begin, count = state.pos, len(state.tokens)
            destination = None
            label_end = -1
            if kind in {"item", "image"} and not silent:
                label_end = state.md.helpers.parseLinkLabel(
                    state, begin + (1 if kind == "image" else 0), kind == "item"
                )
            if (
                kind == "image"
                and not silent
                and label_end >= 0
                and state.src[label_end + 1 : label_end + 2] == "("
            ):
                pos = label_end + 2
                while pos < state.posMax and state.src[pos] in " \t\n":
                    pos += 1
                parsed = state.md.helpers.parseLinkDestination(
                    state.src, pos, state.posMax
                )
                if parsed.ok:
                    destination = (pos, parsed.pos)
            success = rule(state, silent)
            if success and not silent:
                new = state.tokens[count:]
                token = next(
                    (
                        t
                        for t in new
                        if t.type == ("image" if kind == "image" else "link_open")
                    ),
                    None,
                )
                if token:
                    target = token.attrGet("src" if kind == "image" else "href")
                    if target and _local(target):
                        if "label" in token.meta:
                            _refuse(
                                "unsupported_feature",
                                "Reference-style source-local references are unsupported",
                            )
                        if kind == "autolink":
                            _refuse(
                                "unsupported_feature",
                                "Source-local autolinks are unsupported",
                            )
                        if not (
                            (
                                kind == "item"
                                and urlsplit(target).scheme.casefold() == "brain"
                            )
                            or (
                                kind == "image"
                                and target.startswith(".data/md-images/")
                            )
                        ):
                            _refuse(
                                "unsupported_feature",
                                "Local reference form is outside reviewed inline thought/image coverage",
                            )
                        if kind == "item" and any(t.type == "image" for t in new):
                            _refuse(
                                "unsupported_feature",
                                "An image-wrapped thought link is an unsupported rich-content form",
                            )
                        display = display_text(
                            state.src[begin + (2 if kind == "image" else 1) : label_end]
                        )
                        hits.append(
                            (
                                state.src,
                                begin,
                                state.pos,
                                kind,
                                target,
                                display,
                                destination,
                            )
                        )
            return success

        return run

    parser.inline.ruler.at("link", instrument(link, "item"))
    parser.inline.ruler.at("image", instrument(image, "image"))
    parser.inline.ruler.at("autolink", instrument(autolink, "autolink"))
    chars, offsets = [], []
    index = 0
    while index < len(text):
        char = text[index]
        chars.append("\n" if char == "\r" else "\ufffd" if char == "\0" else char)
        offsets.append(index)
        index += 2 if text[index : index + 2] == "\r\n" else 1
    normalized = _MappedText("".join(chars), offsets)
    env, tokens = {}, []
    if normalized:
        state = _MappedBlock(normalized, parser, env, tokens)
        parser.block.tokenize(state, state.line, state.lineMax)
    result = []
    digest = sha256(text.encode("utf-8")).hexdigest()

    def check_html(token):
        if token.type in {"html_inline", "html_block"}:
            _HtmlReferences().feed(token.content)

    for block in tokens:
        check_html(block)
        if block.type != "inline":
            continue
        hits.clear()
        children = []
        parser.inline.parse(block.content, parser, env, children)
        for child in children:
            check_html(child)
        for source, begin, end, kind, target, display, destination in hits:
            if not isinstance(source, _MappedText) or not 0 <= begin < end <= len(
                source
            ):
                _refuse(
                    "unsupported_feature",
                    "Markdown reference provenance cannot be established",
                )
            start, stop = source.offsets[begin], source.offsets[end - 1] + 1
            original = text[start:stop]
            if original.replace("\r\n", "\n").replace("\r", "\n") != source[begin:end]:
                _refuse(
                    "unsupported_feature",
                    "Markdown reference crosses transformed block syntax; exact adaptation is unsupported",
                )
            result.append(
                ReferenceSpan(
                    start=start,
                    end=stop,
                    expected_original=original,
                    kind=kind,
                    target=target,
                    display_text=str(display),
                    document_digest=digest,
                    destination_start=source.offsets[destination[0]]
                    if destination
                    else None,
                    destination_end=source.offsets[destination[1] - 1] + 1
                    if destination
                    else None,
                )
            )
    result.sort(key=lambda span: span.start)
    if any(a.end > b.start for a, b in pairwise(result)):
        _refuse(
            "unsupported_feature",
            "Nested local image/link references overlap; this rich-content form is unsupported",
        )
    return tuple(result)
