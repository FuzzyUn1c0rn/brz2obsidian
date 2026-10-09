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


def active_mask(body, *, autolinks=True):
    """Keep exact coordinates while masking fenced/indented/code/comment regions."""
    mask = list(body)
    fence = None
    paragraph = False
    offset = 0
    for line in body.splitlines(keepends=True):
        # Quotes and list containers admit fences without making their content HTML.
        content = re.sub(r"^ {0,3}(?:> ?)+", "", line)
        content = re.sub(r"^ {0,3}(?:[-+*]|[0-9]{1,9}[.)]) +", "", content)
        marker = re.match(r" {0,3}(`{3,}|~{3,})(.*)", content)
        protected = False
        if fence:
            protected = True
            if (
                marker
                and marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not marker[2].strip()
            ):
                fence = None
        elif marker and not (marker[1][0] == "`" and "`" in marker[2]):
            protected = True
            fence = marker[1]
        elif content.startswith(("    ", "\t")) and not paragraph:
            protected = True
        if protected:
            mask[offset : offset + len(line)] = " " * len(line)
        paragraph = not (protected or not content.strip())
        offset += len(line)
    scan = "".join(mask)
    for match in re.finditer(r"<!--(?:.*?)-->", scan, re.DOTALL):
        mask[match.start() : match.end()] = " " * len(match[0])
    scan = "".join(mask)
    cursor = 0
    while cursor < len(scan):
        if scan[cursor] == "\\":
            mask[cursor : cursor + 2] = " " * len(mask[cursor : cursor + 2])
            cursor += 2
        elif scan[cursor] == "`":
            end = cursor
            while end < len(scan) and scan[end] == "`":
                end += 1
            close = re.search(
                r"(?<!`)" + re.escape(scan[cursor:end]) + r"(?!`)", scan[end:]
            )
            if close:
                stop = end + close.end()
                mask[cursor:stop] = " " * (stop - cursor)
                cursor = stop
            else:
                cursor = end
        else:
            cursor += 1
    scan = "".join(mask)
    if not autolinks:
        return scan
    for match in re.finditer(
        r"<(?:[A-Za-z][A-Za-z0-9+.-]{1,31}:[^<>\s]*|[^<>\s@]+@[^<>\s@]+)>", scan
    ):
        mask[match.start() : match.end()] = " " * len(match[0])
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
