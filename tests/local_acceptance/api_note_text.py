"""Independent API-only expected display from retained authored Markdown.

No converter/parser imports; source activity comes from the independent scanner.
This helper preserves the original source separately and never reads record text.
"""

import hashlib
import html
import posixpath
import re
from urllib.parse import quote

from .checker import inline_display, source_references, wiki
from .text import (
    active_mask,
    inline_candidates,
    inline_code_spans,
    literal_edits,
    native_table_intervals,
    paragraph_intervals,
)

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
    return [line for line in re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", text) if line]


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
            if re.search(
                r"(?:\r\n|\r(?!\n)|(?<!\r)\n)[ \t]*(?:> ?)*(?:\r\n|\r(?!\n)|(?<!\r)\n)",
                between,
            ):
                break
            if "\n" in between or "\r" in between:
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


def callouts(text, operations=None, ownership=None, origins=None):
    mask = insert_activity(text)
    output, opened, offset = [], set(), 0
    containers = []
    mapped = []

    def close_container(stop):
        start, _, changed = containers.pop()
        if ownership is not None and changed:
            ownership.append((start, stop))

    for line in markdown_lines(text):
        original, first, begin = line, len(output), offset
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
        while containers and (
            depth < containers[-1][1] or active and depth <= containers[-1][1]
        ):
            close_container(begin)
        if active:
            containers.append([begin, depth, False])
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
        replacement = "".join(output[first:])
        if origins is not None:
            if line == original:
                line_origins = origins[begin:offset]
            else:
                title_start = marker.start(5) + len(marker[5]) - len(marker[5].lstrip())
                title_end = marker.end(5) - len(marker[5]) + len(marker[5].rstrip())
                lead = len(line) - len(marker[6]) - len(title)
                title_origins = [None] * len(title)
                authored = marker[5].strip()
                if authored:
                    shift = len(icon) + 1 if emoji else 0
                    title_origins[shift : shift + len(authored)] = origins[
                        begin + title_start : begin + title_end
                    ]
                line_origins = (
                    [None] * lead
                    + title_origins
                    + origins[begin + marker.start(6) : offset]
                )
            mapped.extend([None] * (len(replacement) - len(line)) + line_origins)
        if active and replacement != original:
            containers[-1][2] = True
        if operations is not None and replacement != original:
            operations.append((begin, begin + len(original), replacement))
    while containers:
        close_container(len(text))
    if origins is not None:
        origins[:] = mapped
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


def tables(
    text,
    operations=None,
    ownership=None,
    origins=None,
    *,
    current_tables=False,
    malformed=None,
):
    if current_tables:
        return current_table_text(text, operations, ownership, origins, malformed)
    lines = markdown_lines(text)
    scan = insert_activity(text)
    offsets, cursor = [], 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)
    edits, mapped = {}, {}
    for index, line in enumerate(lines):
        suffix = re.search(
            r':\(table="column-widths:([-0-9,]+);justification:default"\):(?:\r\n|\r|\n|$)',
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
        if ownership is not None:
            ownership.append((offsets[index], offsets[rows[-1]] + len(lines[rows[-1]])))
        separator = all(
            re.fullmatch(r"\s*:?-{3,}:?\s*", cell) for cell in row_cells(lines[rows[0]])
        )
        ending = re.search(r"(?:\r\n|\r|\n)$", line)
        blank_header = (
            current_tables and not separator and any(cell.strip() for cell in cells)
        )
        generated_header = (
            "|"
            + "|".join(" " for _ in cells)
            + "|\n|"
            + "|".join("---" for _ in cells)
            + "|\n"
        )
        edits[index] = (
            (generated_header + header if blank_header else header)
            + (
                ""
                if separator or blank_header
                else "\n|" + "|".join("---" for _ in cells) + "|"
            )
            + (ending[0] if ending else "")
        )
        if origins is not None:
            copied = origins[offsets[index] : offsets[index] + len(header)]
            eol = (
                origins[offsets[index] + ending.start() : offsets[index] + ending.end()]
                if ending
                else []
            )
            mapped[index] = (
                [None] * len(generated_header) + copied + eol
                if blank_header
                else copied
                + [None] * (len(edits[index]) - len(header) - len(eol))
                + eol
            )
        for following in [index, *rows]:
            original = edits.get(following, lines[following])
            code_edits = []

            def code(
                match,
                following=following,
                generated_header=generated_header,
                blank_header=blank_header,
                index=index,
                code_edits=code_edits,
            ):

                local_start = match.start() - (
                    len(generated_header) if blank_header and following == index else 0
                )
                position = offsets[following] + local_start
                if (
                    "<!--" in lines[following][:local_start]
                    and "-->"
                    not in lines[following][
                        lines[following].rfind("<!--", 0, local_start) : local_start
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
                replacement = (
                    "<code>"
                    + html.escape(value, quote=False).replace("|", "&#124;")
                    + "</code>"
                )
                code_edits.append((match.start(), match.end(), replacement))
                return replacement

            edits[following] = re.sub(r"(?<!`)(`+)(?!`)(.*?)\1(?!`)", code, original)
            if origins is not None:
                span = mapped.get(
                    following,
                    origins[
                        offsets[following] : offsets[following] + len(lines[following])
                    ],
                )[:]
                for begin, end, replacement in reversed(code_edits):
                    span[begin:end] = [None] * len(replacement)
                mapped[following] = span
    if operations is not None:
        operations.extend(
            (offsets[i], offsets[i] + len(lines[i]), replacement)
            for i, replacement in sorted(edits.items())
            if replacement != lines[i]
        )
    if origins is not None:
        origins[:] = [
            value
            for i, line in enumerate(lines)
            for value in mapped.get(i, origins[offsets[i] : offsets[i] + len(line)])
        ]
    return "".join(edits.get(i, line) for i, line in enumerate(lines))


def current_table_text(text, operations, ownership, origins, malformed):
    """Current native table facts, independently from source adapter parsers.

    Styling is an opaque source declaration. Ordinary row groups belong only
    to top-level paragraphs; declarations instead use active inline ownership.
    A real separator admits ragged data without inventing or discarding cells.
    """
    lines = markdown_lines(text)
    offsets, cursor = [], 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)
    scan = insert_activity(text)
    paragraphs = paragraph_intervals(text)
    codes = {(a, b): (c, d) for a, b, c, d in inline_code_spans(text)}
    protected_codes = cross_container_code(text)
    changes, mapped, declared = {}, {}, set()

    def active(index):
        return bool(scan[offsets[index] : offsets[index] + len(lines[index])].strip())

    def cells(index, row=None):
        raw = lines[index].rstrip("\r\n") if row is None else row
        first, last = len(raw) - len(raw.lstrip()), len(raw.rstrip()) - 1
        if (
            last < first
            or scan[offsets[index] + first] != "|"
            or scan[offsets[index] + last] != "|"
        ):
            return None
        if any(
            a < offsets[index] + len(raw) and offsets[index] < b
            for a, b in protected_codes
        ):
            return None
        return row_cells(raw)

    def separator(parts, width):
        return (
            parts is not None
            and len(parts) == width
            and all(re.fullmatch(r"\s*:?-{3,}:?\s*", part) for part in parts)
        )

    def native(index, row):
        local = []
        values = (
            origins[offsets[index] : offsets[index] + len(row)]
            if origins is not None
            else [None] * len(row)
        )
        position = len(row) - len(row.lstrip()) + 1
        for part in row_cells(row) or ():
            linked = re.fullmatch(
                r"(?P<space>\s*)(?P<source>`curl -[Ii] \["
                r"(?P<url>https?://[^\s`|<>\[\]()\\]+)`)"
                r"\]\((?P=url)\)(?P<tail>\s*)",
                part,
            )
            if (
                linked
                and (
                    offsets[index] + position + linked.start("source"),
                    offsets[index] + position + linked.end("source"),
                )
                in codes
            ):
                opening = linked.start("source")
                removed = linked.start("url") - 1
                replacement = (
                    part[:opening] + "[" + part[opening:removed] + part[removed + 1 :]
                )
                copied = values[position : position + len(part)]
                mapped_part = (
                    copied[:opening]
                    + [None]
                    + copied[opening:removed]
                    + copied[removed + 1 :]
                )
                local.append((position, position + len(part), replacement, mapped_part))
            position += len(part) + 1
        for (begin, end), (inside, stop) in codes.items():
            left, right = begin - offsets[index], end - offsets[index]
            if 0 <= left < right <= len(row) and "|" in text[inside:stop]:
                value = text[inside:stop].replace("\r", " ").replace("\n", " ")
                if value.startswith(" ") and value.endswith(" ") and value.strip():
                    value = value[1:-1]
                replacement = (
                    "<code>"
                    + html.escape(value, quote=False)
                    .replace("\\", "&#92;")
                    .replace("|", "&#124;")
                    + "</code>"
                )
                local.append((left, right, replacement, [None] * len(replacement)))
        for match in re.finditer(re.escape("{nl}"), row):
            if (
                scan[offsets[index] + match.start() : offsets[index] + match.end()]
                == "{nl}"
            ):
                local.append((match.start(), match.end(), "<br>", [None] * 4))
        for begin, end, replacement, mapped_part in sorted(local, reverse=True):
            row = row[:begin] + replacement + row[end:]
            values[begin:end] = mapped_part
        return row, values

    def emit(start, stop, parts, explicit, styled):
        empty = all(not part.strip() for part in parts)
        blank = "|" + "|".join(" " for _ in parts) + "|"
        header = blank + "\n|" + "|".join("---" for _ in parts) + "|"
        for index in range(start, stop):
            raw = lines[index].rstrip("\r\n")
            row = styled if index == start and styled is not None else raw
            row, values = native(index, row)
            if index == start:
                if empty:
                    row = blank if explicit else header
                    values = [None] * len(row)
                elif not explicit:
                    row = header + "\n" + row
                    values = [None] * (len(header) + 1) + values
                if start and lines[start - 1].strip():
                    row, values = "\n" + row, [None] + values
            if index == stop - 1 and stop < len(lines) and lines[stop].strip():
                row, values = row + "\n", values + [None]
            ending = lines[index][len(raw) :]
            changes[index] = row + ending
            mapped[index] = values + (
                origins[offsets[index] + len(raw) : offsets[index] + len(lines[index])]
                if origins is not None
                else [None] * len(ending)
            )
        if ownership is not None:
            ownership.append((offsets[start], offsets[stop - 1] + len(lines[stop - 1])))

    def warn(declaration, styled):
        if malformed is not None:
            malformed.append(
                {
                    "feature": "table",
                    "declaration": declaration,
                    "change": "Malformed or ambiguous table retained as source text; supply an ordinary Markdown table with "
                    + (
                        "a matching header separator."
                        if styled
                        else "matching columns and a header separator."
                    ),
                }
            )

    for index, line in enumerate(lines):
        raw = line.rstrip("\r\n")
        starts = [
            m.start()
            for m in re.finditer(re.escape(":(table="), raw)
            if scan[offsets[index] + m.start() : offsets[index] + m.start() + 2] == ":("
        ]
        if not starts:
            continue
        suffix = re.search(r':\(table="(?:[^"\\\r\n]|\\.)*"\):$', raw)
        if suffix and suffix.start() not in starts:
            suffix = None
        if suffix:
            starts = [
                position
                for position in starts
                if not suffix.start() < position < suffix.end()
            ]
        stop = index + 1
        while (
            stop < len(lines) and active(stop) and lines[stop].lstrip().startswith("|")
        ):
            stop += 1
        declared.update(range(index, stop))
        first = cells(index, raw[: suffix.start()]) if suffix else None
        rows = [cells(i) for i in range(index + 1, stop)]
        if (
            suffix
            and raw[: suffix.start()].strip() == "||"
            and len(rows) == 1
            and rows[0] is not None
            and len(rows[0]) == 2
        ):
            first = ["", ""]
        explicit = bool(first and rows and separator(rows[0], len(first)))
        if (
            first
            and len(starts) == 1
            and rows
            and (
                explicit
                or all(row is not None and len(row) == len(first) for row in rows)
            )
        ):
            emit(index, stop, first, explicit, raw[: suffix.start()])
        else:
            warn(raw[starts[0] :], True)

    index = 0
    while index < len(lines):
        start = index
        while (
            index < len(lines)
            and index not in declared
            and active(index)
            and lines[index].lstrip().startswith("|")
            and any(a <= offsets[index] < b for a, b in paragraphs)
        ):
            index += 1
        if index - start < 2:
            index = max(index, start + 1)
            continue
        rows = [cells(i) for i in range(start, index)]
        first = rows[0]
        if first is None:
            continue
        if (
            lines[start].strip() == "||"
            and len(rows) == 2
            and rows[1] is not None
            and len(rows[1]) == 2
        ):
            first = ["", ""]
        explicit = separator(rows[1], len(first))
        if not explicit and (
            len(first) < 2
            or any(row is None or len(row) != len(first) for row in rows[1:])
        ):
            warn(lines[start].rstrip("\r\n"), False)
            continue
        emit(start, index, first, explicit, None)
    if operations is not None:
        operations.extend(
            (offsets[i], offsets[i] + len(lines[i]), after)
            for i, after in sorted(changes.items())
            if after != lines[i]
        )
    if origins is not None:
        origins[:] = [
            value
            for i, line in enumerate(lines)
            for value in mapped.get(i, origins[offsets[i] : offsets[i] + len(line)])
        ]
    return "".join(changes.get(i, line) for i, line in enumerate(lines))


def label_text(value):
    """Derive visible inline text, distinguishing code, escapes and active math."""
    placeholder = "\ue000"
    while placeholder in value:
        placeholder += "\ue000"
    mathematics, literals = [], []

    def escaped_at(text, position):
        return (len(text[:position]) - len(text[:position].rstrip("\\"))) % 2 == 1

    phrases = [
        (start, end) for start, end, *_ in inline_candidates(value, inline_only=True)[0]
    ]
    codes = [(start, end) for start, end, _, _ in inline_code_spans(value)]
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

    for begin, end, content_start, content_end in reversed(inline_code_spans(value)):
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
        value = value[:begin] + keep(visible_literals(display)) + value[end:]
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


def contents(text, operations=None, ownership=None, origins=None):
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
    if ownership is not None:
        ownership.extend(
            (offsets[h["start"]], offsets[h["end"]] + len(lines[h["end"]]))
            for h in headings
        )
    used = set(re.findall(r"(?<!\S)\^([A-Za-z0-9-]+)(?=\s*$)", mask, re.MULTILINE))
    claimed, replacements, mapped = set(), {}, {}
    for number, heading in enumerate(headings, 1):
        name = heading["name"]
        ident = (
            None
            if heading["closed"]
            else re.search(r"(?:^|\s)\^([A-Za-z0-9-]+)$", name)
        )
        if ident:
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
                + (
                    re.search(r"(?:\r\n|\r|\n)$", lines[heading["end"]])[0]
                    if re.search(r"(?:\r\n|\r|\n)$", lines[heading["end"]])
                    else ""
                )
            )
            for i in range(heading["start"] + 1, heading["end"] + 1):
                replacements[i] = ""
            if origins is not None:
                copied = []
                if heading["setext"]:
                    for i in range(heading["start"], heading["end"]):
                        part = lines[i][len(heading["prefix"]) :].strip()
                        rest = lines[i][len(heading["prefix"]) :]
                        left = len(heading["prefix"]) + len(rest) - len(rest.lstrip())
                        if copied:
                            copied.append(None)
                        copied.extend(
                            origins[offsets[i] + left : offsets[i] + left + len(part)]
                        )
                elif name:
                    match = re.match(
                        r"^(?: {0,3}> ?)* {0,3}#{1,6}[ \t]+", lines[heading["start"]]
                    )
                    copied = origins[
                        offsets[heading["start"]] + match.end() : offsets[
                            heading["start"]
                        ]
                        + match.end()
                        + len(name)
                    ]
                start_generated = len(heading["prefix"]) + heading["level"] + bool(name)
                replacement = replacements[heading["start"]]
                mapped[heading["start"]] = (
                    [None] * start_generated
                    + copied
                    + [None] * (len(replacement) - start_generated - len(copied))
                )
                for i in range(heading["start"] + 1, heading["end"] + 1):
                    mapped[i] = []
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
            + ")"
        )
        hierarchy.append(heading["level"])
    for index, prefix in markers.items():
        ending = re.search(r"(?:\r\n|\r|\n)$", lines[index])
        replacements[index] = (
            "\n".join(prefix + entry for entry in entries)
            or prefix + "No authored headings."
        ) + (ending[0] if ending else "")
        mapped[index] = [None] * len(replacements[index])
    if operations is not None:
        operations.extend(
            (offsets[i], offsets[i] + len(lines[i]), replacement)
            for i, replacement in sorted(replacements.items())
            if replacement != lines[i]
        )
    if origins is not None:
        origins[:] = [
            value
            for i, line in enumerate(lines)
            for value in mapped.get(i, origins[offsets[i] : offsets[i] + len(line)])
        ]
    return "".join(replacements.get(i, line) for i, line in enumerate(lines))


def table_contexts(text):
    """Native table rows retain optional edge pipes within their own block.

    Native cell splitting differs from source-table admission: edge pipes are
    optional and body widths may differ. Blank/code/comment/heading blocks and
    new list items or quote/list ownership terminate continuation.
    """
    return native_table_intervals(text)


def document_references(text, owner, assets, *, qualified_brain=None):
    """Reference coordinates from active adapted text, with its exact digest."""
    masked = re.sub(
        r"<code>[^<]*</code>",
        lambda match: "".join(char if char in "\r\n" else " " for char in match[0]),
        protect_cross_container_code(text),
    )
    references = source_references(
        masked, owner, assets, qualified_brain=qualified_brain
    )
    digest = hashlib.sha256(text.encode()).hexdigest()
    contexts = table_contexts(masked)
    for reference in references:
        reference["table_cell"] = any(
            start <= reference["start"] < reference["end"] <= end
            for start, end in contexts
        )
        if reference["presentation_normalization"] is not None:
            reference["presentation_normalization"]["document_digest"] = digest
    return references


def render_references(text, owner, path, names, assets, *, qualified_brain=None):
    result = text
    contexts = table_contexts(text)
    masked = re.sub(
        r"<code>[^<]*</code>",
        lambda match: " " * len(match[0]),
        protect_cross_container_code(text),
    )
    for reference in reversed(
        source_references(masked, owner, assets, qualified_brain=qualified_brain)
    ):
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


def literal_note_edits(raw, *, profile_version="1"):
    """API4 signature ownership and literal spans in original source coordinates."""
    assert profile_version in {"1", "2", "3", "4", "5"}, "supported source profile"
    current = profile_version in {"4", "5"}
    signature = current and raw.startswith("\ufeff")
    source = raw[1:] if signature else raw
    _, edits = literal_edits(
        protect_cross_container_code(source), allow_literal_tokens=current
    )
    if not signature:
        return (
            [
                edit | {"source_digest": hashlib.sha256(raw.encode()).hexdigest()}
                for edit in edits
            ]
            if current
            else edits
        )
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return [
        {
            "kind": "literal_text",
            "start": 0,
            "end": 1,
            "before": "\ufeff",
            "after": "",
            "adapted_start": 0,
            "adapted_end": 0,
            "source_digest": digest,
            "source_basis": "scoped_source_text/unicode_codepoints",
            "adapted_basis": "document.text/unicode_codepoints",
        },
        *(
            edit
            | {
                "start": edit["start"] + 1,
                "end": edit["end"] + 1,
                "source_digest": digest,
            }
            for edit in edits
        ),
    ]


def expected_document_text(raw, *, profile_version="1"):
    """Independent adapted document facts; untouched source EOLs stay exact."""
    edits = literal_note_edits(raw, profile_version=profile_version)
    text = raw
    for edit in reversed(edits):
        text = text[: edit["start"]] + edit["after"] + text[edit["end"] :]
    return contents(
        callouts(tables(text, current_tables=profile_version in {"4", "5"}))
    )


def expected_note_text(
    raw,
    owner,
    path,
    names,
    assets,
    *,
    qualified_brain=None,
    profile_version="1",
    prepared=None,
):
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = (
        expected_document_text(normalized, profile_version=profile_version)
        if prepared is None
        else prepared.replace("\r\n", "\n").replace("\r", "\n")
    )
    return render_references(
        text, owner, path, names, assets, qualified_brain=qualified_brain
    )


def adaptation_activity(raw, *, profile_version="1"):
    """Raw ownership of independently recognized literal and insert operations.

    Origins propagate through composition. Recognized tables own their rows,
    adapted callouts own their quoted container, and ToC operations own their
    consumed headings even when those rows/headings need no string replacement.
    Unrelated source gaps cannot be relabeled by a large emitted edit.
    """
    literal = literal_note_edits(raw, profile_version=profile_version)
    activity = {
        "literal_text": [(e["start"], e["end"]) for e in literal],
        "markdown_insert": [],
    }
    text = raw
    origins = [(i, i + 1) for i in range(len(raw))]
    for edit in reversed(literal):
        start, end = edit["start"], edit["end"]
        text = text[:start] + edit["after"] + text[end:]
        origins[start:end] = [(start, end)] * len(edit["after"])
    for transform in (tables, callouts, contents):
        operations, ownership = [], []
        after = transform(
            text,
            operations,
            ownership,
            **(
                {"current_tables": profile_version in {"4", "5"}}
                if transform is tables
                else {}
            ),
        )
        for start, end in ownership:
            owned = origins[start:end]
            activity["markdown_insert"].append(
                (min(v[0] for v in owned), max(v[1] for v in owned))
            )
        mapped, cursor = [], 0
        for start, end, replacement in operations:
            mapped.extend(origins[cursor:start])
            owned = origins[start:end]
            span = (min(v[0] for v in owned), max(v[1] for v in owned))
            activity["markdown_insert"].append(span)
            mapped.extend([span] * len(replacement))
            cursor = end
        mapped.extend(origins[cursor:])
        text, origins = after, mapped
    for kind, intervals in activity.items():
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        activity[kind] = merged
    return activity


def owned_replacement(raw, start, end, replacement, intervals):
    """Existence of kind-owned changes, with all outside source gaps exact.

    A greedy search for each interior unchanged gap leaves the most room for
    later gaps. Prefix/suffix anchors keep boundaries exact. No preferred
    character-diff alignment or emitted atomic segmentation is imposed.
    """
    owned = [
        (max(start, left), min(end, right))
        for left, right in intervals
        if left <= end and start <= right
    ]
    if not owned:
        return replacement == raw[start:end]
    gaps, cursor = [], start
    for left, right in owned:
        gaps.append(raw[cursor:left])
        cursor = right
    gaps.append(raw[cursor:end])
    if not replacement.startswith(gaps[0]) or not replacement.endswith(gaps[-1]):
        return False
    cursor = len(gaps[0])
    for gap in gaps[1:-1]:
        found = replacement.find(gap, cursor)
        if found < 0:
            return False
        cursor = found + len(gap)
    return cursor <= len(replacement) - len(gaps[-1])


def validate_document_adaptations(raw, adapted, edits, *, profile_version="1"):
    """Validate serialized provenance without prescribing one edit segmentation."""
    assert type(edits) is list, "document adaptation collection"
    fields = {
        "kind",
        "start",
        "end",
        "before",
        "after",
        "adapted_start",
        "adapted_end",
        "source_digest",
        "source_basis",
        "adapted_basis",
    }
    activity = adaptation_activity(raw, profile_version=profile_version)
    current_literals = (
        literal_note_edits(raw, profile_version=profile_version)
        if profile_version in {"4", "5"}
        else None
    )
    digest = hashlib.sha256(raw.encode()).hexdigest()
    source_cursor = adapted_cursor = 0
    replay = []
    for edit in edits:
        assert type(edit) is dict and set(edit) == fields, "document adaptation fields"
        assert all(
            type(edit[k]) is int
            for k in ("start", "end", "adapted_start", "adapted_end")
        ), "document adaptation scalar coordinates"
        assert all(
            type(edit[k]) is str
            for k in fields - {"start", "end", "adapted_start", "adapted_end"}
        ), "document adaptation scalar text"
        kind = edit["kind"]
        assert kind in activity, "document adaptation kind"
        start, end = edit["start"], edit["end"]
        assert source_cursor <= start < end <= len(raw), (
            "document adaptation source spans"
        )
        assert edit["before"] == raw[start:end] and edit["before"] != edit["after"], (
            "document adaptation source before"
        )
        assert (
            edit["source_digest"] == digest
            and edit["source_basis"] == "scoped_source_text/unicode_codepoints"
            and edit["adapted_basis"] == "document.text/unicode_codepoints"
        ), "document adaptation digest/bases"
        gap = raw[source_cursor:start]
        adapted_start = adapted_cursor + len(gap)
        adapted_end = adapted_start + len(edit["after"])
        assert (edit["adapted_start"], edit["adapted_end"]) == (
            adapted_start,
            adapted_end,
        ), "document adaptation delta spans"
        assert (
            adapted[adapted_cursor:adapted_start] == gap
            and adapted[adapted_start:adapted_end] == edit["after"]
        ), "document adaptation unchanged gaps/replacement"
        if current_literals is not None and kind == "literal_text":
            # A literal token has one independently known logical extent.
            # Insert operations retain their existing composition freedom.
            assert any(
                (start, end, edit["after"])
                == (literal["start"], literal["end"], literal["after"])
                for literal in current_literals
            ), "document adaptation exact literal token extent"
        assert owned_replacement(raw, start, end, edit["after"], activity[kind]), (
            "document adaptation source activity kind"
        )
        replay.extend((gap, edit["after"]))
        source_cursor, adapted_cursor = end, adapted_end
    replay.append(raw[source_cursor:])
    assert "".join(replay) == adapted, "document adaptation complete replay"
