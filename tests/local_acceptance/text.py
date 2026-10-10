"""Independent bounded Markdown activity and literal edits in Unicode coordinates.

This scanner never imports the source adapter or its Markdown parser. It refuses
unestablished active HTML shapes instead of silently omitting expected edits.
HTML names follow the separately reviewed primary inventory (2026-10-10).
"""

import hashlib
import re

ELEMENTS = {
    "h5",
    "applet",
    "data",
    "body",
    "marquee",
    "iframe",
    "area",
    "figcaption",
    "i",
    "output",
    "rt",
    "frame",
    "nextid",
    "ul",
    "sub",
    "dir",
    "kbd",
    "button",
    "html",
    "plaintext",
    "search",
    "var",
    "hgroup",
    "caption",
    "option",
    "rp",
    "dl",
    "s",
    "slot",
    "video",
    "pre",
    "base",
    "style",
    "section",
    "form",
    "code",
    "ruby",
    "acronym",
    "bgsound",
    "datalist",
    "isindex",
    "content",
    "rb",
    "big",
    "rtc",
    "tr",
    "em",
    "input",
    "thead",
    "p",
    "title",
    "basefont",
    "blink",
    "u",
    "noembed",
    "image",
    "object",
    "figure",
    "portal",
    "aside",
    "listing",
    "meter",
    "nav",
    "div",
    "font",
    "ol",
    "meta",
    "frameset",
    "h1",
    "embed",
    "dfn",
    "source",
    "shadow",
    "math",
    "progress",
    "selectedcontent",
    "img",
    "samp",
    "article",
    "summary",
    "sup",
    "svg",
    "canvas",
    "dialog",
    "cite",
    "fieldset",
    "noscript",
    "textarea",
    "mark",
    "strong",
    "noframes",
    "abbr",
    "tfoot",
    "q",
    "span",
    "legend",
    "table",
    "dd",
    "nobr",
    "h3",
    "a",
    "li",
    "picture",
    "label",
    "bdi",
    "xmp",
    "h4",
    "keygen",
    "tt",
    "tbody",
    "bdo",
    "optgroup",
    "ins",
    "time",
    "colgroup",
    "h2",
    "th",
    "main",
    "wbr",
    "header",
    "dt",
    "map",
    "track",
    "col",
    "param",
    "link",
    "br",
    "h6",
    "b",
    "blockquote",
    "footer",
    "hr",
    "menu",
    "td",
    "del",
    "menuitem",
    "multicol",
    "select",
    "script",
    "small",
    "details",
    "center",
    "template",
    "head",
    "audio",
    "strike",
    "spacer",
    "address",
}

# CommonMark 0.31.2 section 6.6. Match original characters, never a protection
# mask: replacing escaped punctuation with spaces can invent an attribute.
# Quoted values own their angle/backtick/punctuation characters as one token.
_HTML_SPACE = r"[ \t\r\n]"
_HTML_NAME = r"[A-Za-z][A-Za-z0-9-]*"
_HTML_ATTRIBUTE = (
    _HTML_SPACE
    + r"+[A-Za-z_:][A-Za-z0-9_.:-]*"
    + r"(?:"
    + _HTML_SPACE
    + r"*="
    + _HTML_SPACE
    + r"*(?:[^ \t\r\n\"'=<>`]+|'[^']*'|\"[^\"]*\"))?"
)
_HTML_TOKEN = re.compile(
    r"<(?:"
    + _HTML_NAME
    + r"(?:"
    + _HTML_ATTRIBUTE
    + r")*"
    + _HTML_SPACE
    + r"*/?|/"
    + _HTML_NAME
    + _HTML_SPACE
    + r"*)>"
    # A declaration needs one ASCII letter after <! and no required whitespace
    # (CommonMark 0.31.2 section 6.6); case and empty trailing content are valid.
    + r"|<\?[\s\S]*?\?>|<![A-Za-z][^>]*>"
    + r"|<!\[CDATA\[[\s\S]*?\]\]>"
)


def _line_view(line, *, interrupt=False):
    """A bounded container view; slicing never alters raw source coordinates."""
    # Columns govern block indentation only. Inline syntax, authored bytes and
    # offsets still come exclusively from the untouched original body below.
    content, owner = line.expandtabs(4), []
    while content:
        quote = re.match(r"^ {0,3}> ?", content)
        listing = re.match(r"^( {0,3}(?:[-+*]|[0-9]{1,9}[.)]))( +)", content)
        if quote:
            content = content[quote.end() :]
            owner.append(("quote", 0))
        elif listing:
            number = re.match(r"[0-9]+", listing[1].lstrip())
            if interrupt and not owner and number and int(number[0]) != 1:
                # A non-1 ordered marker cannot interrupt a raw paragraph.
                break
            # CommonMark 5.2: a wide marker gap consumes one space, leaving
            # at least four as code indentation. Never fabricate an opener.
            indent = len(listing[1]) + (len(listing[2]) if len(listing[2]) <= 4 else 1)
            content = content[indent:]
            owner.append(("indent", indent))
        else:
            break
    return (
        content,
        sum(kind == "quote" for kind, _ in owner),
        sum(width for kind, width in owner if kind == "indent"),
        tuple(owner),
    )


def _owned_block_view(line, owner):
    """Consume existing container prefixes, never markers inside leaf content."""
    content = line.expandtabs(4)
    for kind, width in owner:
        if kind == "quote":
            prefix = re.match(r"^ {0,3}> ?", content)
            if prefix is None:
                return None
            content = content[prefix.end() :]
        else:
            spaces = len(content) - len(content.lstrip(" "))
            if content.strip() and spaces < width:
                return None
            content = content[min(spaces, width) :]
    return content


def _inline_regions(body):
    """Resolve leaf block ownership before scanning any inline delimiters.

    CommonMark HTML-comment blocks own the complete closing line (or the rest
    of their container). A fence inside a comment never opens a code block.
    Blank lines and real block transitions delimit backtick matching regions.
    Only CR/LF separate Markdown lines; splitlines would invent Unicode breaks.
    """
    mask = list(body)
    fence = None
    comment = None
    paragraph = False
    paragraph_owner = ()
    region = None
    regions = []
    previous_quotes = 0
    list_indent = 0
    for match in re.finditer(r"[^\r\n]*(?:\r\n|\r|\n|$)", body):
        line = match[0]
        if not line:
            continue
        owner = fence[1] if fence else comment
        if owner is not None:
            owned = _owned_block_view(line, owner)
            if owned is not None:
                # A protected leaf owns its text before new quote/list markers
                # are considered (CommonMark 4.5/4.6). Only its containing
                # prefixes and real closer affect ownership.
                if region is not None:
                    regions.append((region, match.start()))
                    region = None
                mask[match.start() : match.end()] = " " * len(line)
                if comment is not None:
                    if "-->" in owned:
                        comment = None
                else:
                    closer = re.match(r" {0,3}(`{3,}|~{3,})(.*)", owned)
                    if (
                        closer
                        and closer[1][0] == fence[0][0]
                        and len(closer[1]) >= len(fence[0])
                        and not closer[2].strip()
                    ):
                        fence = None
                previous_quotes = sum(kind == "quote" for kind, _ in owner)
                list_indent = sum(width for kind, width in owner if kind == "indent")
                paragraph = False
                continue
            fence = comment = None
        continuing = _owned_block_view(line, paragraph_owner) if paragraph else None
        # The reviewed conservative owner boundary does not extend a missing
        # quote/list prefix into an ordered declaration route. This is a bounded
        # source-policy limit, not a claim about all CommonMark lazy paragraphs.
        container_content, quotes, listing, container_owner = _line_view(
            continuing if continuing is not None else line,
            interrupt=continuing is not None,
        )
        if continuing is not None:
            # Existing prefixes precede a new marker. A non-1 ordered marker
            # cannot interrupt that paragraph within its actual quote/list.
            container_owner = paragraph_owner + container_owner
            quotes = sum(kind == "quote" for kind, _ in container_owner)
        if quotes != previous_quotes:
            list_indent = 0
        if continuing is not None:
            list_indent = sum(
                width for kind, width in container_owner if kind == "indent"
            )
        elif listing:
            list_indent = listing
        elif (
            list_indent
            and container_content.strip()
            and len(container_content) - len(container_content.lstrip(" "))
            < list_indent
        ):
            list_indent = 0
        content = container_content
        if continuing is None and list_indent and not listing:
            content = content[
                min(list_indent, len(content) - len(content.lstrip(" "))) :
            ]
            container_owner += (("indent", list_indent),)
        marker = re.match(r" {0,3}(`{3,}|~{3,})(.*)", content)
        protected = False
        if re.match(r" {0,3}<!--", content):
            protected = True
            if "-->" not in content:
                comment = container_owner
        elif marker and not (marker[1][0] == "`" and "`" in marker[2]):
            protected = True
            fence = (marker[1], container_owner)
        elif re.match(r" {0,3}<![A-Za-z]", content):
            # CommonMark 4.6 type 4 starts with <! and an ASCII letter.
            # Its HTML ownership extends to >, the container boundary or EOF;
            # unlike inline declarations, refusal needs no complete closer.
            # Existing code/comment leaves were handled before container parsing.
            raise AssertionError("raw-derived active HTML outside literal policy")
        elif (
            content.startswith(("    ", "\t"))
            and (not paragraph or listing)
            or re.fullmatch(
                r" {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})",
                content.rstrip("\r\n"),
            )
            or paragraph
            and re.fullmatch(r" {0,3}(?:=+|-+)[ \t]*", content.rstrip("\r\n"))
        ):
            protected = True
        boundary = (
            protected
            or not content.strip()
            or quotes != previous_quotes
            or listing
            or re.match(r" {0,3}#{1,6}(?:[ \t]|$)", content)
        )
        if boundary and region is not None:
            regions.append((region, match.start()))
            region = None
        if protected:
            mask[match.start() : match.end()] = " " * len(line)
        elif content.strip():
            if region is None:
                region = match.start()
            if re.match(r" {0,3}#{1,6}(?:[ \t]|$)", content):
                regions.append((region, match.end()))
                region = None
        paragraph = not (protected or not content.strip())
        paragraph_owner = container_owner if paragraph else ()
        previous_quotes = quotes
    if region is not None:
        regions.append((region, len(body)))
    return regions, mask, (fence, comment)


def generated_boundary(prefix):
    """Derive generated guard bytes from the accumulated expected raw prefix.

    Appended material starts at top level after a blank-line separation. An
    open top-level code/comment block still owns that material; quote/list
    containers naturally end. Guards frame following material only and never
    belong to authored document coordinates, digests or adaptation counts.
    """
    _, _, (fence, comment) = _inline_regions(prefix)
    if fence and not fence[1]:
        return "\n\n" + fence[0] + "\n"
    if comment == ():
        return "\n\n-->\n"
    return ""


def active_mask(body, *, autolinks=True, inline_only=False):
    """Lexically protect constructs in source order with exact raw coordinates."""
    if inline_only:
        # A reference display label is an inline fragment, not a new block.
        regions, mask = [(0, len(body))], list(body)
    else:
        regions, mask, _ = _inline_regions(body)
    for start, finish in regions:
        cursor = start
        while cursor < finish:
            stop = None
            if (
                body[cursor] == "\\"
                and cursor + 1 < finish
                and body[cursor + 1] in r"!\"#$%&'()*+,-./:;<=>?@[\]^_`{|}~\\"
            ):
                stop = cursor + 2
            elif body[cursor] == "`":
                end = cursor + 1
                while end < finish and body[end] == "`":
                    end += 1
                close = re.search(
                    r"(?<!`)" + re.escape(body[cursor:end]) + r"(?!`)", body[end:finish]
                )
                if close:
                    stop = end + close.end()
                else:
                    cursor = end
                    continue
            elif body.startswith("<!--", cursor):
                close = body.find("-->", cursor + 4, finish)
                if close >= 0:
                    stop = close + 3
            elif autolinks and body[cursor] == "<":
                link = re.match(
                    r"<(?:[A-Za-z][A-Za-z0-9+.-]{1,31}:[^<>\s]*|[^<>\s@]+@[^<>\s@]+)>",
                    body[cursor:finish],
                )
                if link:
                    stop = cursor + link.end()
            if stop is None and body[cursor] == "<":
                html = _HTML_TOKEN.match(body, cursor, finish)
                if html:
                    # HTML consumes its own quoted attributes before Markdown
                    # punctuation/code handling. Retain raw token coordinates.
                    cursor = html.end()
                    continue
            if stop is not None:
                mask[cursor:stop] = " " * (stop - cursor)
                cursor = stop
            else:
                cursor += 1
    return "".join(mask)


def inline_candidates(body, *, inline_only=False):
    """Find balanced active phrases, distinguishing bracket text from links."""
    scan = active_mask(body, autolinks=False, inline_only=inline_only)
    mask = list(scan)
    # Balanced brackets recognize whole outer phrases, including an image inside
    # a forgotten thought link. Escaped brackets never change nesting depth.
    candidates = []
    cursor = 0
    while cursor < len(scan):
        if scan[cursor : cursor + 9] == "<brain://":
            raise AssertionError(
                "unestablished source-local autolink in independent oracle"
            )
        if scan[cursor] == "\\":
            cursor += 2
            continue
        image = scan[cursor : cursor + 2] == "!["
        opening = cursor + int(image)
        if scan[opening : opening + 1] != "[":
            cursor += 1
            continue
        index, depth = opening + 1, 1
        while index < len(scan) and depth:
            if scan[index] == "\\":
                index += 2
                continue
            depth += (scan[index] == "[") - (scan[index] == "]")
            index += 1
        closing = index - 1
        if depth or scan[index : index + 1] != "(":
            cursor += 1
            continue
        start = index + 1
        if scan[start : start + 1] == "<":
            stop = scan.find(">", start + 1)
            destination_start, destination_end = start + 1, stop
            after = stop + 1
        else:
            after, nesting = start, 0
            while after < len(scan):
                if scan[after] == "\\":
                    after += 2
                    continue
                if scan[after] == ")" and nesting == 0 or scan[after].isspace():
                    break
                nesting += (scan[after] == "(") - (scan[after] == ")")
                after += 1
            destination_start, destination_end = start, after
        end = re.match(r'(?:\s+["\'][^"\']*["\'])?\)', scan[after:])
        if end is None or destination_end < destination_start:
            cursor += 1
            continue
        finish = after + end.end()
        candidates.append(
            (
                cursor,
                finish,
                image,
                body[opening + 1 : closing],
                destination_start,
                destination_end,
            )
        )
        cursor = finish
    return candidates, mask, scan


def literal_edits(body):
    scan = active_mask(body)
    # Labels are active; balanced whole phrases establish destinations/titles.
    mask = list(scan)
    for _, finish, _, _, start, _ in inline_candidates(body)[0]:
        # The opening angle delimiter belongs to a destination too. Checking
        # raw tokens means masking only its interior no longer hides it.
        if body[start - 1 : start] == "<":
            start -= 1
        mask[start : finish - 1] = " " * (finish - 1 - start)
    scan = "".join(mask)
    edits = []
    digest = hashlib.sha256(body.encode()).hexdigest()
    shift = 0
    regions, _, _ = _inline_regions(body)
    matches = []
    for start, finish in regions:
        cursor = start
        while cursor < finish:
            match = (
                _HTML_TOKEN.match(body, cursor, finish) if scan[cursor] == "<" else None
            )
            if match:
                matches.append(match)
                cursor = match.end()
            else:
                cursor += 1
    for match in matches:
        token = match[0]
        if re.fullmatch(r"<br\s*/?>", token, re.IGNORECASE):
            continue
        simple = re.fullmatch(r"<([A-Za-z][A-Za-z0-9-]*)>", token)
        assert simple and simple[1].casefold() not in ELEMENTS, (
            "unestablished active HTML in independent literal oracle"
        )
        edits.append(
            {
                "start": match.start(),
                "end": match.end(),
                "before": token,
                "after": "\\" + token,
                "adapted_start": match.start() + shift,
                "adapted_end": match.end() + shift + 1,
                "source_digest": digest,
                "source_basis": "scoped_source_text/unicode_codepoints",
                "adapted_basis": "document.text/unicode_codepoints",
            }
        )
        shift += 1
    adapted = body
    for edit in reversed(edits):
        adapted = adapted[: edit["start"]] + edit["after"] + adapted[edit["end"] :]
    return adapted, edits
