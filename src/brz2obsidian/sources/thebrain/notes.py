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
from markdown_it.rules_inline import autolink, html_inline, image, link
from markdown_it.rules_inline.backticks import backtick

from brz2obsidian.contracts import (
    ImagePresentationNormalization,
    Issue,
    MigrationRefused,
    ReferenceSpan,
)
from brz2obsidian.diagnostics import diagnosed_issue


def _refuse(code, message):
    raise MigrationRefused(
        (
            diagnosed_issue(
                Issue(
                    code=code,
                    phase="source",
                    message=message,
                    guidance="Use supported same-Brain inline Markdown references to live thoughts and archived images, then re-export.",
                )
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
        # The accepted format-5 Markdown includes attribute-free line breaks.
        # Preserve them verbatim; this does not interpret legacy HTML notes.
        if tag == "br" and not attrs:
            return
        _refuse(
            "unsupported_feature",
            "HTML note content is outside reviewed Markdown coverage",
        )

    def handle_endtag(self, tag):
        _refuse(
            "unsupported_feature",
            "HTML note content is outside reviewed Markdown coverage",
        )

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_decl(self, decl):
        _refuse(
            "unsupported_feature",
            "HTML declarations are outside reviewed Markdown coverage",
        )

    def handle_pi(self, data):
        _refuse(
            "unsupported_feature",
            "HTML processing instructions are outside reviewed Markdown coverage",
        )


def _qualified_identities(destination):
    prefix = "brain://api.thebrain.com/"
    components = destination.removeprefix(prefix).split("/")
    if (
        not destination.startswith(prefix)
        or len(components) not in {2, 3}
        or any(c in destination for c in "?#\\")
        or any(ord(c) < 32 or ord(c) == 127 for c in destination)
        or re.search(
            r"%(?![0-9a-fA-F]{2})|%(?:0[0-9a-f]|1[0-9a-f]|7f|5c)",
            destination,
            re.IGNORECASE,
        )
        or any(not re.fullmatch(r"[A-Za-z0-9_-]{22}", c) for c in components[:2])
    ):
        _refuse(
            "invalid_reference", "Invalid or unsupported qualified thought reference"
        )
    identities = []
    for token in components[:2]:
        raw = base64.urlsafe_b64decode(token + "==")
        if base64.urlsafe_b64encode(raw).decode().rstrip("=") != token:
            _refuse("invalid_reference", "Noncanonical qualified thought identity")
        identities.append(str(UUID(bytes_le=raw)))
    return identities


def compact_thought_identity(destination, *, brain_id=None, allow_qualified=False):
    """Decode local identity; qualified foreign namespaces return no local ID.

    Qualified handling requires both an explicit capability and authoritative
    Brain context. Defaults retain historical compact-only interpretation.
    """
    parts = urlsplit(destination)
    if parts.netloc.casefold() in {"api.thebrain.com", "api.bra.in"}:
        if not allow_qualified:
            _refuse(
                "unsupported_feature",
                "Cross-Brain/server-qualified thought references are unsupported",
            )
        if not brain_id:
            _refuse(
                "invalid_reference",
                "Qualified thought reference needs authoritative Brain context",
            )
        identities = _qualified_identities(destination)
        return identities[1] if identities[0] == brain_id else None
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
            "Invalid or unsupported compact thought reference",
        )
    raw = base64.urlsafe_b64decode(compact + "==")
    if base64.urlsafe_b64encode(raw).decode().rstrip("=") != compact:
        _refuse("invalid_reference", "Noncanonical compact thought identity")
    return str(UUID(bytes_le=raw))


def image_destination(document, reference):
    """Validate the exact owned-image path and optional presentation declaration."""
    destination = reference.target
    normalization = None
    parts = urlsplit(destination)
    raw = document.text[reference.destination_start : reference.destination_end]
    raw = raw[1:-1] if raw.startswith("<") and raw.endswith(">") else raw
    raw_path = raw.split("#", 1)[0]
    if (
        "?" in destination
        or "?" in raw
        or ("#" in destination and not parts.fragment)
        or re.search(r"%(?![0-9a-fA-F]{2})|%(?:2f|5c)", raw_path, re.IGNORECASE)
        or re.search(r"%(?![0-9a-fA-F]{2})|%(?:2f|5c)", parts.path, re.IGNORECASE)
    ):
        _refuse(
            "invalid_reference",
            "Invalid or ambiguous local image destination encoding or query",
        )
    if parts.fragment:
        if (
            not re.fullmatch(r"\$width=([1-9]|[1-9][0-9]|100)p\$", parts.fragment)
            or raw.rsplit("#", 1)[-1] != parts.fragment
        ):
            _refuse(
                "invalid_reference",
                "Invalid or unsupported local image sizing declaration",
            )
        begin = reference.destination_start + document.text[
            reference.destination_start : reference.destination_end
        ].rindex("#")
        declaration = "#" + parts.fragment
        normalization = ImagePresentationNormalization(
            declaration=declaration,
            start=begin,
            end=begin + len(declaration),
            document_digest=document.text_digest,
        )
    try:
        location = unquote(parts.path.removeprefix(".data/md-images/"), errors="strict")
    except UnicodeDecodeError:
        _refuse("invalid_reference", "Invalid local image UTF-8 encoding")
    if (
        not parts.path.startswith(".data/md-images/")
        or parts.query
        or not location
        or re.search(r"%[0-9a-fA-F]{2}", location)
        or "\\" in location
        or any(p in {"", ".", ".."} for p in location.split("/"))
    ):
        _refuse(
            "invalid_reference",
            "Invalid or unsupported local image destination",
        )
    return location, normalization


def bind_note_references(
    document, assets, thoughts, *, brain_id=None, allow_qualified=False
):
    """Bind parsed source destinations to canonical IDs after asset inventory."""
    bound = []
    for reference in document.references:
        destination = reference.target
        normalization = None
        if reference.kind == "item":
            canonical = compact_thought_identity(
                destination, brain_id=brain_id, allow_qualified=allow_qualified
            )
            if canonical is None:
                # A qualified foreign link remains the exact authored Markdown;
                # it is not a local relation and grants no foreign acquisition.
                continue
            if canonical not in thoughts or thoughts[canonical]["Kind"] == 5:
                _refuse(
                    "invalid_reference",
                    "Local thought reference does not identify a live navigable thought",
                )
        else:
            location, normalization = image_destination(document, reference)
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
                    "Local image does not identify one preserved owner image",
                )
            canonical = matches[0]
        bound.append(
            reference.model_copy(
                update={
                    "target": canonical,
                    "source_target": destination,
                    "presentation_normalization": normalization,
                }
            )
        )
    return document.model_copy(update={"references": tuple(bound)})


class _BlockSlice(str):
    """A source slice with any leading tab padding emitted by getLines."""

    def __new__(cls, value, span):
        result = super().__new__(cls, value)
        result.span = span
        result.padding = ""
        return result

    def __radd__(self, padding):
        if (
            not isinstance(padding, str)
            or self.padding
            or len(padding) > 3
            or padding.strip(" ")
        ):
            _refuse_unmapped_block()
        self.padding = padding
        return padding + str(self)


class _MappedText(str):
    """Parser input whose slices retain exact original character provenance."""

    _block_slices = None

    def __new__(cls, value, offsets):
        result = super().__new__(cls, value)
        result.offsets = tuple(offsets)
        return result

    def __getitem__(self, index):
        value = super().__getitem__(index)
        if not isinstance(index, slice):
            return value
        if self._block_slices is None:
            return _MappedText(value, self.offsets[index])
        fragment = _BlockSlice(value, index)
        self._block_slices.append(fragment)
        return fragment

    def strip(self, chars=None):
        left = len(self) - len(super().lstrip(chars))
        right = len(super().rstrip(chars))
        return self[left : max(left, right)]


def _refuse_unmapped_block():
    _refuse("unsupported_feature", "Markdown block provenance cannot be established")


class _MappedBlock(StateBlock):
    """Map getLines slices and tab padding within the parser's active line bounds."""

    def getLines(self, begin, end, indent, keepLastLF):
        source = self.src
        if not isinstance(source, _MappedText) or source._block_slices is not None:
            _refuse_unmapped_block()
        fragments = []
        source._block_slices = fragments
        try:
            value = super().getLines(begin, end, indent, keepLastLF)
        finally:
            source._block_slices = None

        if not isinstance(value, str) or len(fragments) != max(0, end - begin):
            _refuse_unmapped_block()
        offsets = []
        cursor = previous_stop = 0
        for line, fragment in enumerate(fragments, begin):
            start, stop, step = fragment.span.indices(len(source))
            padding = fragment.padding
            line_start = self.bMarks[line]
            line_stop = self.eMarks[line] + (line + 1 < end or keepLastLF)
            if (
                step != 1
                or not max(line_start, previous_stop) <= start <= stop
                or stop != min(line_stop, len(source))
            ):
                _refuse_unmapped_block()
            content_start = line_start + max(0, self.tShift[line])
            skipped = str.__getitem__(source, slice(content_start, start))
            if skipped.strip(" \t"):
                _refuse_unmapped_block()
            if padding:
                if (
                    start == line_start
                    or source[start - 1] != "\t"
                    or not value.startswith(padding, cursor)
                ):
                    _refuse_unmapped_block()
                offsets.extend([source.offsets[start - 1]] * len(padding))
                cursor += len(padding)
            if not value.startswith(fragment, cursor):
                _refuse_unmapped_block()
            offsets.extend(source.offsets[start:stop])
            cursor += len(fragment)
            previous_stop = stop
        if cursor != len(value):
            _refuse_unmapped_block()
        return _MappedText(value, offsets)


def _mapped_blocks(text, parser, env):
    chars, offsets = [], []
    index = 0
    while index < len(text):
        char = text[index]
        chars.append("\n" if char == "\r" else "\ufffd" if char == "\0" else char)
        offsets.append(index)
        index += 2 if text[index : index + 2] == "\r\n" else 1
    normalized = _MappedText("".join(chars), offsets)
    tokens = []
    if normalized:
        state = _MappedBlock(normalized, parser, env, tokens)
        parser.block.tokenize(state, state.line, state.lineMax)
    if any(
        token.type == "inline"
        and token.content
        and not isinstance(token.content, _MappedText)
        for token in tokens
    ):
        _refuse_unmapped_block()
    return tokens


def trace_inline_literal_ranges(text):
    """Trace code and admitted comments across complete mapped inline containers."""
    parser, env, code, comments = MarkdownIt("commonmark"), {}, [], []

    def instrument(rule, ranges, token_type):
        def run(state, silent):
            begin, count = state.pos, len(state.tokens)
            success = rule(state, silent)
            if (
                success
                and not silent
                and any(
                    token.type == token_type
                    and (
                        token_type != "html_inline" or token.content.startswith("<!--")
                    )
                    for token in state.tokens[count:]
                )
            ):
                ranges.append(
                    (state.src.offsets[begin], state.src.offsets[state.pos - 1] + 1)
                )
            return success

        return run

    parser.inline.ruler.at("backticks", instrument(backtick, code, "code_inline"))
    parser.inline.ruler.at(
        "html_inline", instrument(html_inline, comments, "html_inline")
    )
    for token in _mapped_blocks(text, parser, env):
        if token.type == "inline":
            parser.inline.parse(token.content, parser, env, [])
    return tuple(code), tuple(comments)


def _reference_display_text(value, display_parser):
    children = []
    display_parser.inline.parse(value, display_parser, {}, children)
    return "".join(
        "\\<"
        if t.type == "text_special" and t.markup == "\\<"
        else t.content
        if t.type in {"text", "text_special", "code_inline"}
        else "\n"
        if t.type in {"softbreak", "hardbreak"}
        else ""
        for t in children
    )


def _reference_destination(state, kind, begin, silent):
    destination = parsed = None
    label_end = -1
    if kind in {"item", "image"} and not silent:
        label_end = state.md.helpers.parseLinkLabel(
            state, begin + (1 if kind == "image" else 0), kind == "item"
        )
    if (
        kind in {"item", "image"}
        and not silent
        and label_end >= 0
        and state.src[label_end + 1 : label_end + 2] == "("
    ):
        pos = label_end + 2
        while pos < state.posMax and state.src[pos] in " \t\n":
            pos += 1
        parsed = state.md.helpers.parseLinkDestination(state.src, pos, state.posMax)
        if parsed.ok:
            destination = (pos, parsed.pos)
    return label_end, destination, parsed


def _check_qualified_destination(
    text, state, parts, destination, parsed, allow_qualified
):
    if (
        allow_qualified
        and destination
        and parts.netloc.casefold() in {"api.thebrain.com", "api.bra.in"}
    ):
        # Check the parsed Markdown destination before URL
        # normalization can repair malformed percent data.
        _qualified_identities(parsed.str)
        raw_destination = text[
            state.src.offsets[destination[0]] : state.src.offsets[destination[1] - 1]
            + 1
        ]
        if any(ord(c) < 32 or ord(c) == 127 for c in raw_destination):
            _refuse(
                "invalid_reference",
                "Control character in qualified thought destination",
            )


def _references_omitted_subject(parts, excluded):
    removed_subject = False
    if parts.scheme == "brain" and re.fullmatch(r"[A-Za-z0-9_-]{22}", parts.netloc):
        raw = base64.urlsafe_b64decode(parts.netloc + "==")
        removed_subject = str(UUID(bytes_le=raw)) in excluded
        if removed_subject and (
            base64.urlsafe_b64encode(raw).decode().rstrip("=") != parts.netloc
            or not parts.path.startswith("/")
            or parts.query
            or parts.fragment
        ):
            _refuse(
                "invalid_reference",
                "Invalid compact thought reference",
            )
    return removed_subject


def _check_reference_form(token, kind, target, new, removed_subject):
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
    if not removed_subject and not (
        (kind == "item" and urlsplit(target).scheme.casefold() == "brain")
        or (kind == "image" and target.startswith(".data/md-images/"))
    ):
        _refuse(
            "unsupported_feature",
            "Local reference form is outside reviewed inline thought/image coverage",
        )
    if not removed_subject and kind == "item" and any(t.type == "image" for t in new):
        _refuse(
            "unsupported_feature",
            "An image-wrapped thought link is an unsupported rich-content form",
        )


def _record_reference_hit(
    state,
    begin,
    kind,
    target,
    label_end,
    destination,
    removed_subject,
    display_parser,
    hits,
):
    if removed_subject:
        hits[:] = [
            hit
            for hit in hits
            if not (hit[0] is state.src and begin <= hit[1] and hit[2] <= state.pos)
        ]
    display = _reference_display_text(
        state.src[begin + (2 if kind == "image" else 1) : label_end],
        display_parser,
    )
    hits.append(
        (
            state.src,
            begin,
            state.pos,
            "item" if removed_subject else kind,
            target,
            display,
            destination if kind == "image" else None,
        )
    )


def _reference_rule(rule, kind, text, excluded, allow_qualified, display_parser, hits):
    def run(state, silent):
        begin, count = state.pos, len(state.tokens)
        label_end, destination, parsed = _reference_destination(
            state, kind, begin, silent
        )
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
                    parts = urlsplit(target)
                    _check_qualified_destination(
                        text, state, parts, destination, parsed, allow_qualified
                    )
                    removed_subject = _references_omitted_subject(parts, excluded)
                    _check_reference_form(token, kind, target, new, removed_subject)
                    _record_reference_hit(
                        state,
                        begin,
                        kind,
                        target,
                        label_end,
                        destination,
                        removed_subject,
                        display_parser,
                        hits,
                    )
        return success

    return run


def _reference_span(
    text, digest, source, begin, end, kind, target, display, destination
):
    if not isinstance(source, _MappedText) or not 0 <= begin < end <= len(source):
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
    return ReferenceSpan(
        start=start,
        end=stop,
        expected_original=original,
        kind=kind,
        target=target,
        display_text=str(display),
        document_digest=digest,
        destination_start=source.offsets[destination[0]] if destination else None,
        destination_end=source.offsets[destination[1] - 1] + 1 if destination else None,
    )


def _trace_reference_blocks(text, parser, tokens, env, hits, digest):
    result = []

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
            result.append(
                _reference_span(
                    text, digest, source, begin, end, kind, target, display, destination
                )
            )
    return result


def trace_note_references(
    text: str, excluded=(), *, allow_qualified=False
) -> tuple[ReferenceSpan, ...]:
    """Trace parser-recognized active links into exact original text spans.

    Carry character provenance through normalization and block indentation;
    never reconstruct a document from parsed tokens.
    """
    parser = MarkdownIt("commonmark", {"store_labels": True})
    display_parser = MarkdownIt("commonmark")
    hits = []

    parser.inline.ruler.at(
        "link",
        _reference_rule(
            link, "item", text, excluded, allow_qualified, display_parser, hits
        ),
    )
    parser.inline.ruler.at(
        "image",
        _reference_rule(
            image, "image", text, excluded, allow_qualified, display_parser, hits
        ),
    )
    parser.inline.ruler.at(
        "autolink",
        _reference_rule(
            autolink, "autolink", text, excluded, allow_qualified, display_parser, hits
        ),
    )
    env = {}
    tokens = _mapped_blocks(text, parser, env)
    digest = sha256(text.encode("utf-8")).hexdigest()

    result = _trace_reference_blocks(text, parser, tokens, env, hits, digest)
    result.sort(key=lambda span: span.start)
    if any(a.end > b.start for a, b in pairwise(result)):
        _refuse(
            "unsupported_feature",
            "Nested local image/link references overlap; this rich-content form is unsupported",
        )
    return tuple(result)
