"""Adapt only active, standalone non-element opening words in Markdown."""

import re
from hashlib import sha256

from markdown_it import MarkdownIt
from markdown_it.rules_inline import html_inline

from brz2obsidian.contracts import TextAdaptation

from .notes import _HtmlReferences, _MappedBlock, _MappedText, _refuse

# WHATWG element index and obsolete-element list, reviewed 2026-10-09:
# https://html.spec.whatwg.org/multipage/indices.html#elements-3
# https://html.spec.whatwg.org/multipage/obsolete.html#non-conforming-features
# Include recognized obsolete elements and foreign-content roots, not just
# CommonMark's shorter block-element list. Matching is ASCII case-insensitive.
HTML_ELEMENTS = frozenset(
    [
        "a",
        "abbr",
        "address",
        "area",
        "article",
        "aside",
        "audio",
        "b",
        "base",
        "bdi",
        "bdo",
        "blockquote",
        "body",
        "br",
        "button",
        "canvas",
        "caption",
        "cite",
        "code",
        "col",
        "colgroup",
        "data",
        "datalist",
        "dd",
        "del",
        "details",
        "dfn",
        "dialog",
        "div",
        "dl",
        "dt",
        "em",
        "embed",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "head",
        "header",
        "hgroup",
        "hr",
        "html",
        "i",
        "iframe",
        "img",
        "input",
        "ins",
        "kbd",
        "label",
        "legend",
        "li",
        "link",
        "main",
        "map",
        "mark",
        "menu",
        "meta",
        "meter",
        "nav",
        "noscript",
        "object",
        "ol",
        "optgroup",
        "option",
        "output",
        "p",
        "picture",
        "pre",
        "progress",
        "q",
        "rp",
        "rt",
        "ruby",
        "s",
        "samp",
        "script",
        "search",
        "section",
        "select",
        "selectedcontent",
        "slot",
        "small",
        "source",
        "span",
        "strong",
        "style",
        "sub",
        "summary",
        "sup",
        "table",
        "tbody",
        "td",
        "template",
        "textarea",
        "tfoot",
        "th",
        "thead",
        "time",
        "title",
        "tr",
        "track",
        "u",
        "ul",
        "var",
        "video",
        "wbr",
        "math",
        "svg",
        "applet",
        "acronym",
        "bgsound",
        "dir",
        "frame",
        "frameset",
        "noframes",
        "isindex",
        "keygen",
        "listing",
        "menuitem",
        "nextid",
        "noembed",
        "param",
        "plaintext",
        "rb",
        "rtc",
        "strike",
        "xmp",
        "basefont",
        "big",
        "blink",
        "center",
        "font",
        "marquee",
        "multicol",
        "nobr",
        "spacer",
        "tt",
        "image",
    ]
)


def _literal(value):
    match = re.fullmatch(r"<([A-Za-z][A-Za-z0-9-]*)>", value)
    if match and match[1].lower() not in HTML_ELEMENTS:
        return True
    if value.startswith("<!") and not value.startswith("<!--"):
        _refuse(
            "unsupported_feature",
            "HTML declarations are outside reviewed Markdown coverage",
        )
    _HtmlReferences().feed(value)
    return False


def adapt_literals(text):
    """Expose codepoint edits from scoped source into explicitly adapted text.

    Escape a leading unknown HTML-block opener, then reparse newly exposed
    Markdown, so code behind that opener remains protected by the parser.
    """
    original = text
    origins = list(range(len(text)))
    edits = {}
    while True:
        parser = MarkdownIt("commonmark")
        hits = []

        def collect(state, silent, hits=hits):
            begin = state.pos
            success = html_inline(state, silent)
            if success and not silent and _literal(state.tokens[-1].content):
                hits.append(
                    (state.src.offsets[begin], state.src.offsets[state.pos - 1] + 1)
                )
            return success

        parser.inline.ruler.at("html_inline", collect)
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
        for block in tokens:
            if block.type == "html_block":
                match = re.match(r"[ \t]*(<[A-Za-z][A-Za-z0-9-]*>)", block.content)
                if match and _literal(match[1]):
                    if not isinstance(block.content, _MappedText):
                        _refuse(
                            "unsupported_feature",
                            "Markdown HTML provenance cannot be established",
                        )
                    hits.append(
                        (
                            block.content.offsets[match.start(1)],
                            block.content.offsets[match.end(1) - 1] + 1,
                        )
                    )
                else:
                    _literal(block.content)
            elif block.type == "inline":
                parser.inline.parse(block.content, parser, env, [])
        if not hits:
            break
        for begin, end in sorted(set(hits), reverse=True):
            start, stop = origins[begin], origins[end - 1] + 1
            before = original[start:stop]
            edits[start] = (stop, before)
            text = text[:begin] + "\\" + text[begin:]
            origins.insert(begin, start)
    digest = sha256(original.encode()).hexdigest()
    result = []
    for delta, (start, (end, before)) in enumerate(sorted(edits.items())):
        after = "\\" + before
        result.append(
            TextAdaptation(
                start=start,
                end=end,
                before=before,
                after=after,
                adapted_start=start + delta,
                adapted_end=end + delta + 1,
                source_digest=digest,
            )
        )
    return text, tuple(result)


def source_position(position, edits):
    """Map a reference boundary outside edits back into scoped source text."""
    return position - sum(
        len(edit.after) - len(edit.before)
        for edit in edits
        if edit.adapted_end <= position
    )
