"""Independent bounded Markdown activity and literal edits in Unicode coordinates.

This scanner never imports the source adapter or its Markdown parser. It refuses
unestablished active HTML shapes instead of silently omitting expected edits.
HTML names follow WHATWG current/obsolete element indices (reviewed 2026-10-09).
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


def _line_view(line):
    """A bounded container view; slicing never alters raw source coordinates."""
    quote = re.match(r"^ {0,3}(?:> ?)+", line)
    content = line[quote.end() :] if quote else line
    listing = re.match(r"^ {0,3}(?:[-+*]|[0-9]{1,9}[.)]) +", content)
    return (
        content[listing.end() :] if listing else content,
        quote[0].count(">") if quote else 0,
        listing.end() if listing else 0,
    )


def _inside_container(content, quotes, listing, owner):
    quoted, indentation = owner
    return quotes == quoted and not (
        indentation
        and content.strip()
        and (listing or len(content) - len(content.lstrip(" ")) < indentation)
    )


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
    region = None
    regions = []
    previous_quotes = 0
    for match in re.finditer(r"[^\r\n]*(?:\r\n|\r|\n|$)", body):
        line = match[0]
        if not line:
            continue
        content, quotes, listing = _line_view(line)
        marker = re.match(r" {0,3}(`{3,}|~{3,})(.*)", content)
        protected = False
        if fence and not _inside_container(content, quotes, listing, fence[1:]):
            fence = None
        if comment is not None:
            if not _inside_container(content, quotes, listing, comment):
                comment = None
            else:
                protected = True
                if "-->" in content:
                    comment = None
        if protected:
            pass
        elif fence:
            protected = True
            if (
                marker
                and marker[1][0] == fence[0][0]
                and len(marker[1]) >= len(fence[0])
                and not marker[2].strip()
            ):
                fence = None
        elif re.match(r" {0,3}<!--", content):
            protected = True
            if "-->" not in content:
                comment = (quotes, listing)
        elif marker and not (marker[1][0] == "`" and "`" in marker[2]):
            protected = True
            fence = (marker[1], quotes, listing)
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
        previous_quotes = quotes
    if region is not None:
        regions.append((region, len(body)))
    return regions, mask


def active_mask(body, *, autolinks=True):
    """Lexically protect constructs in source order with exact raw coordinates."""
    regions, mask = _inline_regions(body)
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
            if stop is not None:
                mask[cursor:stop] = " " * (stop - cursor)
                cursor = stop
            else:
                cursor += 1
    return "".join(mask)


def inline_candidates(body):
    """Find balanced active phrases, distinguishing bracket text from links."""
    scan = active_mask(body, autolinks=False)
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
        mask[start : finish - 1] = " " * (finish - 1 - start)
    scan = "".join(mask)
    edits = []
    digest = hashlib.sha256(body.encode()).hexdigest()
    shift = 0
    for match in re.finditer(r"<(?:/?[A-Za-z][^<>]*|![^<>]*|\?[^<>]*)>", scan):
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
