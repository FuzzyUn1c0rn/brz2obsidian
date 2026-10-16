"""Independent API-only expected display from retained authored Markdown.

No converter/parser imports; source activity comes from the independent scanner.
This helper preserves the original source separately and never reads record text.
"""

import html
import posixpath
import re
from urllib.parse import quote

from .checker import inline_display, source_references, wiki
from .text import active_mask, inline_candidates, literal_edits

KINDS = frozenset(
    [
        "note",
        "abstract",
        "info",
        "todo",
        "tip",
        "success",
        "question",
        "warning",
        "failure",
        "danger",
        "bug",
        "example",
        "quote",
    ]
)


def markdown_lines(text):
    """CommonMark lines split at CR/LF only; caller normalized those bytes."""
    return [line for line in re.findall(r"[^\n]*(?:\n|$)", text) if line]


def cross_container_code(text):
    """Supplement scanner regions for admitted lazy multiline quote code spans.

    Prefix depth alone cannot terminate inline code. A blank paragraph does;
    balanced equal backtick runs preserve every raw character between them.
    Existing scanner-owned fences/comments/ordinary code remain authoritative.
    """
    scan, ranges, cursor = active_mask(text), [], 0
    for opening in re.finditer(r"(?<![\\`])`+(?!`)", text):
        if opening.start() < cursor or scan[opening.start() : opening.end()].isspace():
            continue
        for closing in re.finditer(
            r"(?<!`)" + re.escape(opening[0]) + r"(?!`)", text[opening.end() :]
        ):
            end = opening.end() + closing.end()
            between = text[opening.end() : end - len(opening[0])]
            if re.search(r"\n[ \t]*(?:> ?)*\n", between):
                break
            if "\n" in between:
                ranges.append((opening.start(), end))
            cursor = end
            break
    return ranges


def protect_cross_container_code(text):
    masked = list(text)
    for start, end in cross_container_code(text):
        masked[start:end] = ["\n" if char == "\n" else " " for char in text[start:end]]
    return "".join(masked)


def insert_activity(text):
    mask = list(active_mask(text))
    for start, end in cross_container_code(text):
        mask[start:end] = " " * (end - start)
    return "".join(mask)


def callouts(text):
    mask = insert_activity(text)
    output, opened, offset = [], set(), 0
    for line in markdown_lines(text):
        scan = mask[offset : offset + len(line)]
        offset += len(line)
        prefix = re.match(r"^( {0,3}(?:> ?)+)", line)
        depth = prefix[0].count(">") if prefix else 0
        marker = re.match(
            r"^( {0,3}(?:> ?)+)\[!([A-Za-z]+)([^\]]*)\]([+-]?)([^\r\n]*)(\r?\n|\r|$)",
            line,
        )
        active = (
            marker
            and scan[len(marker[1]) : len(marker[1]) + 2] == "[!"
            and marker[2].lower() in KINDS
        )
        blank = not line.strip(" >\r\n\t")
        previous_blank = not output or not output[-1].strip(" >\r\n\t")
        if active:
            if any(d >= depth for d in opened) and not previous_blank:
                output.append("> " * (depth - 1) + "\n")
            opened = {d for d in opened if d < depth} | {depth}
            if marker[3]:
                declaration = marker[3]
                icon = declaration.removeprefix("|icon:")
                title = marker[5].strip() or marker[2].capitalize()
                emoji = (
                    declaration.startswith("|icon:")
                    and bool(icon)
                    and all(
                        not c.isspace() and not c.isascii() and c not in "|:[]\\`<>"
                        for c in icon
                    )
                )
                safe = re.sub(
                    r"([\\`*_{}\[\]<>])", lambda match: "\\" + match[1], declaration
                )
                title = icon + " " + title if emoji else title + " — " + safe
                line = (
                    marker[1]
                    + "[!"
                    + marker[2].lower()
                    + "]"
                    + marker[4]
                    + " "
                    + title
                    + marker[6]
                )
        elif depth and scan.strip() and opened and depth < max(opened):
            if not previous_blank:
                output.append("> " * depth + "\n")
            opened = {d for d in opened if d <= depth}
        elif not depth and (blank or line.startswith(("```", "~~~"))):
            opened.clear()
        output.append(line)
    return "".join(output)


def row_cells(line):
    """Cell separators are active pipes outside backslash escapes/code spans."""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    cells, start, cursor = [], 1, 1
    while cursor < len(stripped) - 1:
        if stripped[cursor] == "\\":
            cursor += 2
            continue
        if stripped[cursor] == "`":
            opener = re.match(r"`+", stripped[cursor:])[0]
            close = re.search(
                r"(?<!`)" + re.escape(opener) + r"(?!`)",
                stripped[cursor + len(opener) :],
            )
            if close:
                cursor += len(opener) + close.end()
                continue
        if stripped[cursor] == "|":
            cells.append(stripped[start:cursor])
            start = cursor + 1
        cursor += 1
    return cells + [stripped[start:-1]]


def tables(text):
    lines = markdown_lines(text)
    scan = insert_activity(text)
    offsets, cursor = [], 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)
    edits = {}
    for index, line in enumerate(lines):
        suffix = re.search(
            r':\(table="column-widths:([-0-9,]+);justification:default"\):(?:\n|$)',
            line,
        )
        if (
            not suffix
            or index + 1 >= len(lines)
            or scan[offsets[index] + suffix.start()] != ":"
        ):
            continue
        header = line[: suffix.start()]
        cells = row_cells(header)
        values = suffix[1].split(",")
        if (
            cells is None
            or len(values) != len(cells) + 1
            or any(not re.fullmatch(r"-1|0|[1-9][0-9]*", v) for v in values)
            or sum(
                scan[offsets[index] + match.start()] == ":"
                for match in re.finditer(re.escape(":(table="), line)
            )
            != 1
            or scan[offsets[index] + len(header) - len(header.lstrip())] != "|"
            or scan[offsets[index] + len(header.rstrip()) - 1] != "|"
        ):
            continue
        rows = []
        for following in range(index + 1, len(lines)):
            parts = row_cells(lines[following])
            # A literal comment pipe cannot be converted into a native delimiter.
            if parts is None:
                if lines[following].lstrip().startswith("|"):
                    rows = []
                break
            first = len(lines[following]) - len(lines[following].lstrip())
            last = len(lines[following].rstrip()) - 1
            if (
                scan[offsets[following] + first] != "|"
                or scan[offsets[following] + last] != "|"
            ):
                rows = []
                break
            if len(parts) != len(cells):
                rows = []
                break
            if "<!--" in lines[following] and re.search(
                r"<!--.*(?<!\\)\|.*-->", lines[following]
            ):
                rows = []
                break
            rows.append(following)
        if not rows:
            continue
        separator = all(
            re.fullmatch(r"\s*:?-{3,}:?\s*", cell) for cell in row_cells(lines[rows[0]])
        )
        edits[index] = (
            header
            + "\n"
            + ("" if separator else "|" + "|".join("---" for _ in cells) + "|\n")
        )
        for following in [index, *rows]:
            original = edits.get(following, lines[following])

            def code(match, following=following):
                position = offsets[following] + match.start()
                # Comments own backticks too; code spans are not inferred there.
                if (
                    "<!--" in lines[following][: match.start()]
                    and "-->"
                    not in lines[following][
                        lines[following].rfind("<!--", 0, match.start()) : match.start()
                    ]
                ):
                    return match[0]
                if (
                    scan[position : position + len(match[0])].strip()
                    or "|" not in match[2]
                ):
                    return match[0]
                value = match[2].replace("\n", " ")
                if value.startswith(" ") and value.endswith(" ") and value.strip():
                    value = value[1:-1]
                return (
                    "<code>"
                    + html.escape(value, quote=False).replace("|", "&#124;")
                    + "</code>"
                )

            edits[following] = re.sub(r"(?<!`)(`+)(?!`)(.*?)\1(?!`)", code, original)
    return "".join(edits.get(i, line) for i, line in enumerate(lines))


def label_text(value):
    """Derive visible inline text, distinguishing code, escapes and active math."""
    placeholder = "\ue000"
    while placeholder in value:
        placeholder += "\ue000"
    mathematics, literals = [], []

    def escaped_at(text, position):
        return (len(text[:position]) - len(text[:position].rstrip("\\"))) % 2 == 1

    def owned_codes(text):
        ranges, cursor = [], 0
        while cursor < len(text):
            if text.startswith("<!--", cursor) and not escaped_at(text, cursor):
                close = text.find("-->", cursor + 4)
                if close >= 0:
                    cursor = close + 3
                    continue
            if text[cursor] != "`":
                cursor += 1
                continue
            if escaped_at(text, cursor):
                cursor += 1
                continue
            opening = re.match(r"`+", text[cursor:])
            start = cursor
            cursor += len(opening[0])
            closing = next(
                (
                    run
                    for run in re.finditer(r"`+", text[cursor:])
                    if len(run[0]) == len(opening[0])
                ),
                None,
            )
            if closing is not None:
                content_end = cursor + closing.start()
                finish = cursor + closing.end()
                ranges.append((start, finish, cursor, content_end))
                cursor = finish
        return ranges

    phrases = [
        (start, end) for start, end, *_ in inline_candidates(value, inline_only=True)[0]
    ]
    codes = [(start, end) for start, end, _, _ in owned_codes(value)]
    dollars = [
        (i - 1, i + 1)
        for i, char in enumerate(value)
        if char == "$" and escaped_at(value, i)
    ]

    def math(match):
        if any(
            start < match.end() and match.start() < end
            for start, end in [*phrases, *codes, *dollars]
        ):
            return match[0]
        mathematics.append(match[0])
        return placeholder + "M" + str(len(mathematics) - 1) + placeholder

    value = re.sub(r"(?<!\\)\$[^$\n\[\]<>]+(?<!\\)\$", math, value)

    def keep(text):
        literals.append(text)
        return placeholder + "L" + str(len(literals) - 1) + placeholder

    for begin, end, content_start, content_end in reversed(owned_codes(value)):
        text = re.sub(r"\r\n?|\n", " ", value[content_start:content_end])
        if text.startswith(" ") and text.endswith(" ") and text.strip():
            text = text[1:-1]
        value = value[:begin] + keep(text) + value[end:]
    # Shield visible escaped punctuation before the independent display flattener.
    # This keeps a code literal backslash distinct from a normal escape of '<'.
    value = re.sub(
        r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~])",
        lambda match: keep(match[1]),
        value,
    )

    value = re.sub(r"<!--[\s\S]*?-->", "", value)

    def visible_literals(text):
        return re.sub(
            re.escape(placeholder) + r"L(\d+)" + re.escape(placeholder),
            lambda match: literals[int(match[1])],
            text,
        )

    for begin, end, image, label, _, _ in reversed(
        inline_candidates(value, inline_only=True)[0]
    ):
        display = inline_display(label)
        if not visible_literals(display).strip():
            display = "Image" if image else ""
        value = value[:begin] + display + value[end:]
    value = inline_display(value)
    value = re.sub(r"(?: {2,}|\\)?(?:\r\n?|\n)", " ", value)
    value = visible_literals(value).strip() or "Heading"
    value = re.sub(r"([\\`*_{}\[\]<>$])", lambda match: "\\" + match[1], value)
    value = re.sub(
        r"(^| )(\^[A-Za-z0-9-]+)$", lambda match: match[1] + "\\" + match[2], value
    )
    return re.sub(
        re.escape(placeholder) + r"M(\d+)" + re.escape(placeholder),
        lambda match: mathematics[int(match[1])],
        value,
    )


def contents(text):
    lines = markdown_lines(text)
    mask = insert_activity(text)
    offsets, cursor = [], 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)
    markers, headings = {}, []
    for index, line in enumerate(lines):
        prefix = re.match(r"^(?: {0,3}> ?)*", line)[0]
        content = line[len(prefix) :].rstrip("\r\n")
        scan = mask[offsets[index] + len(prefix) : offsets[index] + len(line)].rstrip(
            "\r\n"
        )
        if content.strip() == "[/toc/]" and "[/toc/]" in scan:
            markers[index] = prefix
        atx = re.fullmatch(r" {0,3}(#{1,6})(?:[ \t]+(.*)|$)", content)
        if atx and scan.lstrip().startswith("#"):
            name = atx[2] or ""
            closed = bool(re.search(r"[ \t]+#+[ \t]*$", name))
            name = re.sub(r"[ \t]+#+[ \t]*$", "", name)
            headings.append(
                {
                    "start": index,
                    "end": index,
                    "level": len(atx[1]),
                    "name": name,
                    "prefix": prefix,
                    "setext": False,
                    "closed": closed,
                }
            )
        elif (
            re.fullmatch(r" {0,3}(=+|-+)[ \t]*", content)
            and index
            and mask[offsets[index - 1] : offsets[index]].strip()
        ):
            start = index - 1
            chunks = []
            while start >= 0:
                previous = lines[start]
                if (
                    not previous.startswith(prefix)
                    or not previous[len(prefix) :].strip()
                    or re.match(r" {0,3}#", previous[len(prefix) :])
                    or not mask[offsets[start] : offsets[start] + len(previous)].strip()
                ):
                    break
                chunks.insert(0, previous[len(prefix) :].strip())
                start -= 1
            if chunks:
                headings.append(
                    {
                        "start": start + 1,
                        "end": index,
                        "level": 1 if content.strip()[0] == "=" else 2,
                        "name": " ".join(chunks),
                        "prefix": prefix,
                        "setext": True,
                        "closed": False,
                    }
                )
    if not markers:
        return text
    headings = [
        h
        for h in headings
        if not any(
            h["end"] < marker
            and not any(line.strip() for line in lines[h["end"] + 1 : marker])
            for marker in markers
        )
    ]
    used = set(re.findall(r"(?<!\S)\^([A-Za-z0-9-]+)(?=\s*$)", mask, re.MULTILINE))
    claimed, replacements = set(), {}
    for number, heading in enumerate(headings, 1):
        name = heading["name"]
        ident = (
            None
            if heading["closed"]
            else re.search(r"(?:^|\s)\^([A-Za-z0-9-]+)$", name)
        )
        if ident:
            # An ID sheltered inside an inline code span is visible text.
            original = lines[heading["end"]].rstrip("\r\n")
            caret = original.rfind("^")
            if caret < 0 or mask[offsets[heading["end"]] + caret] != "^":
                ident = None
        old = ident[1] if ident else None
        if ident:
            name = name[: ident.start()].rstrip()
        collision_in_body = bool(
            old
            and any(
                re.search(
                    r"(?<!\S)\^" + re.escape(old) + r"\s*$",
                    mask[offsets[i] : offsets[i] + len(line)],
                )
                for i, line in enumerate(lines)
                if not any(h["start"] <= i <= h["end"] for h in headings)
            )
        )
        if old and old not in claimed and not collision_in_body:
            destination = old
        else:
            destination = f"brz-toc-heading-{number}"
            while destination in used or re.search(
                r"\^" + re.escape(destination) + r"\b", text
            ):
                destination += "-generated"
            used.add(destination)
        claimed.add(destination)
        heading.update(label=label_text(name), destination=destination)
        if heading["setext"] or old != destination or heading["closed"]:
            replacements[heading["start"]] = (
                heading["prefix"]
                + "#" * heading["level"]
                + (" " + name if name else "")
                + " ^"
                + destination
                + "\n"
            )
            for i in range(heading["start"] + 1, heading["end"] + 1):
                replacements[i] = ""
    hierarchy, entries = [], []
    for heading in headings:
        while hierarchy and hierarchy[-1] >= heading["level"]:
            hierarchy.pop()
        entries.append(
            "  " * len(hierarchy)
            + "- ["
            + heading["label"]
            + "](#^"
            + heading["destination"]
            + ")\n"
        )
        hierarchy.append(heading["level"])
    for index, prefix in markers.items():
        replacements[index] = (
            "".join(prefix + entry for entry in entries)
            or prefix + "No authored headings.\n"
        )
    return "".join(replacements.get(i, line) for i, line in enumerate(lines))


def render_references(text, owner, path, names, assets):
    result = text
    lines = markdown_lines(text)
    table_rows, offset = set(), 0
    for index, line in enumerate(lines[:-1]):
        cells, separator = row_cells(line), row_cells(lines[index + 1])
        if (
            cells
            and separator
            and len(cells) == len(separator)
            and all(re.fullmatch(r"\s*:?-{3,}:?\s*", value) for value in separator)
        ):
            table_rows.add(index)
            for following in range(index + 1, len(lines)):
                row = row_cells(lines[following])
                if row is None or len(row) != len(cells):
                    break
                table_rows.add(following)
    contexts = []
    for index, line in enumerate(lines):
        if index in table_rows:
            contexts.append((offset, offset + len(line)))
        offset += len(line)
    masked = re.sub(
        r"<code>[^<]*</code>",
        lambda match: " " * len(match[0]),
        protect_cross_container_code(text),
    )
    for reference in reversed(source_references(masked, owner, assets)):
        if reference["kind"] == "item":
            begin, end = reference["start"], reference["end"]
            replacement = wiki(names[reference["target"]], reference["label"])
            if any(start <= begin < end <= stop for start, stop in contexts):
                replacement = replacement.replace("|", "\\|")
        else:
            begin, end = reference["destination_start"], reference["destination_end"]
            replacement = quote(
                posixpath.relpath(
                    assets[reference["target"]]["relative_path"],
                    posixpath.dirname(path) or ".",
                ),
                safe="/",
            )
        result = result[:begin] + replacement + result[end:]
    return result


def expected_note_text(raw, owner, path, names, assets):
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    _, edits = literal_edits(protect_cross_container_code(normalized))
    text = normalized
    for edit in reversed(edits):
        text = text[: edit["start"]] + edit["after"] + text[edit["end"] :]
    text = contents(callouts(tables(text)))
    return render_references(text, owner, path, names, assets)
