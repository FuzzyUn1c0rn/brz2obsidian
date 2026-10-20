"""Scoped TheBrain inserts become editable native Markdown with exact evidence."""

import re
from hashlib import sha256
from html import escape

from markdown_it import MarkdownIt
from markdown_it.rules_inline import escape as inline_escape
from markdown_it.rules_inline import image, link
from markdown_it.rules_inline.backticks import backtick

from brz2obsidian.contracts import TextAdaptation

from .literals import adapt_literals, source_position
from .notes import trace_inline_literal_ranges, trace_note_references

INSERT_RULE = "thebrain.markdown-inserts.v1"
CALLOUTS = frozenset(
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
_CALLOUT = re.compile(r"^( {0,3}(?:> ?)+)\[!([A-Za-z]+)([^\]]*)\]([+-]?)(.*)$")
_TABLE = re.compile(r':\(table="column-widths:([-0-9,]+);justification:([a-z]+)"\):$')
_TABLE_COLORS = ";".join(
    key + r":#[0-9a-fA-F]{8}"
    for key in (
        "foreground-color",
        "background-color",
        "alt-background-color",
        "line-color",
        "first-row-background-color",
        "first-row-foreground-color",
        "first-row-line-color",
        "first-column-background-color",
        "first-column-foreground-color",
        "first-column-line-color",
    )
)
_COLOR_TABLE = re.compile(r':\(table="' + _TABLE_COLORS + r'"\):$')
_STYLE_TABLE = re.compile(r':\(table="(?:[^"\\\r\n]|\\.)*"\):$')
_TABLE_CODE_LINK = re.compile(
    r"(?P<space>\s*)`(?P<prefix>curl -[Ii] )\[(?P<url>https?://[^\s`|<>\[\]()\\]+)`\]\((?P=url)\)(?P<tail>\s*)"
)


def _cells(row, source_offset, code_ranges, literal_ranges, *, legacy=False):
    """Only parser-owned code or escapes shelter an authored cell's pipes."""
    source_offset += len(row) - len(row.lstrip())
    row = row.strip()
    if not row.startswith("|") or not row.endswith("|"):
        return None
    if not legacy and (len(row[:-1]) - len(row[:-1].rstrip("\\"))) % 2:
        return None
    if any(
        begin <= boundary < end
        for begin, end in literal_ranges
        for boundary in (source_offset, source_offset + len(row) - 1)
    ):
        return None
    cells, start, index = [], 1, 1
    while index < len(row) - 1:
        if row[index] == "\\":
            index += 2
            continue
        if row[index] == "`":
            end = index + 1
            while end < len(row) and row[end] == "`":
                end += 1
            owned = next(
                (
                    finish
                    for begin, finish in code_ranges
                    if begin == source_offset + index
                ),
                None,
            )
            if owned is not None:
                # A span crossing rows cannot become a faithful native cell.
                if owned - source_offset > len(row) - 1:
                    return None
                end = owned - source_offset
            index = end
            continue
        if row[index] == "|":
            cells.append(row[start:index])
            start = index + 1
        index += 1
    cells.append(row[start:-1])
    return cells


def _inline_label(token):
    return "".join(
        t.content
        if t.type in {"text", "text_special", "code_inline"}
        else (_inline_label(t) or "Image")
        if t.type == "image"
        else " "
        if t.type in {"softbreak", "hardbreak"}
        else ""
        for t in token.children or ()
    ).strip()


def _heading_label(token):
    """Protect compatible complete math before flattening Markdown display."""
    parser, protected = MarkdownIt("commonmark"), []

    def instrument(rule):
        def wrapped(state, silent):
            begin = state.pos
            result = rule(state, silent)
            if (
                result
                and not silent
                and state.src == token.content
                and (rule is not inline_escape or state.src[begin : state.pos] == "\\$")
            ):
                protected.append((begin, state.pos))
            return result

        return wrapped

    for name, rule in (
        ("backticks", backtick),
        ("escape", inline_escape),
        ("image", image),
        ("link", link),
    ):
        parser.inline.ruler.at(name, instrument(rule))
    parser.parseInline(token.content)
    content, mathematics = token.content, []
    displayed = _inline_label(token)
    for match in reversed(list(re.finditer(r"(?<!\\)\$[^$\r\n]+(?<!\\)\$", content))):
        if any(c in match[0] for c in "[]<>") or any(
            begin < match.end() and match.start() < end for begin, end in protected
        ):
            continue
        marker = f"BRZTocMath{len(mathematics)}"
        while marker in content or marker in displayed:
            marker += "Token"
        mathematics.append((marker, match[0]))
        content = content[: match.start()] + marker + content[match.end() :]
    return _inline_label(MarkdownIt("commonmark").parseInline(content)[0]), mathematics


def _toc_label(title, mathematics):
    # Protect only complete parser-owned math while escaping ordinary label
    # text. Dollars in code/alt text and escaped source dollars stay literal.
    label = re.sub(r"([\\`*_{}\[\]<>$])", r"\\\1", title)
    # Obsidian hides an unescaped trailing ID-like label suffix. Limit this
    # protection to that suffix so inline mathematics keeps its exponent.
    label = re.sub(r"(^| )(\^[A-Za-z0-9-]+)$", r"\1\\\2", label)
    for marker, value in mathematics:
        label = label.replace(marker, value)
    return label


def _native_code_pipes(row, source_offset, code_ranges, *, legacy=False):
    """A narrowly generated code element preserves native code-cell pipes.

    Obsidian displays a backslash for pipe escapes inside inline code. Source
    HTML remains refused before this generated normalization is reached.
    """

    def replace(match):
        if (
            source_offset + match.start(),
            source_offset + match.end(),
        ) not in code_ranges:
            return match[0]
        content = match[2]
        if "|" not in content:
            return match[0]
        content = content.replace("\r", " ").replace("\n", " ")
        if content.startswith(" ") and content.endswith(" ") and content.strip():
            content = content[1:-1]
        content = escape(content, quote=False)
        if not legacy:
            content = content.replace("\\", "&#92;")
        return "<code>" + content.replace("|", "&#124;") + "</code>"

    return re.sub(r"(?<![\\`])(`+)(?!`)(.*?)(?<!`)\1(?!`)", replace, row)


def _native_table_row(
    row, source_offset, code_ranges, literal_ranges, *, previous_tables=False
):
    changes = []
    if not previous_tables:
        cells = _cells(row, source_offset, code_ranges, literal_ranges)
        position = len(row) - len(row.lstrip()) + 1
        for cell in cells or ():
            match = _TABLE_CODE_LINK.fullmatch(cell)
            if (
                match
                and (
                    source_offset + position + len(match["space"]),
                    source_offset + position + match.end("url") + 1,
                )
                in code_ranges
            ):
                linked = (
                    match["space"]
                    + "[`"
                    + match["prefix"]
                    + match["url"]
                    + "`]("
                    + match["url"]
                    + ")"
                    + match["tail"]
                )
                changes.append((position, position + len(cell), linked))
            position += len(cell) + 1
    for begin, end in code_ranges:
        if source_offset <= begin < end <= source_offset + len(row):
            before = row[begin - source_offset : end - source_offset]
            after = _native_code_pipes(before, begin, code_ranges)
            if before != after:
                changes.append((begin - source_offset, end - source_offset, after))
    for marker in re.finditer(re.escape("{nl}"), row):
        begin, end = source_offset + marker.start(), source_offset + marker.end()
        slashes = len(row[: marker.start()]) - len(row[: marker.start()].rstrip("\\"))
        if slashes % 2 == 0 and not any(
            left < end and begin < right for left, right in literal_ranges
        ):
            changes.append((marker.start(), marker.end(), "<br>"))
    for begin, end, after in sorted(changes, reverse=True):
        row = row[:begin] + after + row[end:]
    return row


def adapt_note(
    text,
    *,
    preserve_table_colors=False,
    legacy_tables=False,
    previous_tables=False,
    compact_tables=False,
    legacy_table_boundaries=False,
    preserve_table_warnings=False,
):
    """Return scoped adapted text, source-neutral exact edits and loss facts.

    Parser block ownership protects code, comments and literal examples. All
    references are traced after adaptation, so their offsets bind final text.
    """
    blank_cell = "" if compact_tables or previous_tables or legacy_tables else " "
    separate_tables = not (
        legacy_table_boundaries or legacy_tables or previous_tables or compact_tables
    )
    warn_tables = preserve_table_warnings or not separate_tables
    original = text
    text, literal_edits = adapt_literals(text)
    lines = re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", text)
    if lines and not lines[-1]:
        lines.pop()
    offsets, position = [], 0
    for line in lines:
        offsets.append(position)
        position += len(line)
    tokens = MarkdownIt("commonmark").parse(text)
    active, protected, quoted, headings = set(), set(), set(), []
    paragraph_lines = set()
    for index, token in enumerate(tokens):
        if not token.map:
            continue
        extent = range(*token.map)
        if token.type == "paragraph_open" and token.level == 0:
            paragraph_lines.update(extent)
        if token.type == "blockquote_open":
            quoted.update(extent)
        if token.type in {"fence", "code_block", "html_block"}:
            protected.update(extent)
        elif token.type == "inline":
            active.update(extent)
        elif token.type == "heading_open":
            title, mathematics = _heading_label(tokens[index + 1])
            headings.append(
                (
                    token.map[0],
                    token.map[1],
                    int(token.tag[1:]),
                    title,
                    token.markup.startswith("#"),
                    tokens[index + 1].content,
                    mathematics,
                )
            )
    active -= protected
    inline_code, inline_comments = trace_inline_literal_ranges(text)
    inline_literals = inline_code + inline_comments
    edits, losses = [], []

    def literal_owned(line, start, end):
        begin, finish = offsets[line] + start, offsets[line] + end
        return any(left < finish and begin < right for left, right in inline_literals)

    def replace(line, before, after):
        begin = offsets[line] + max(0, lines[line].find(before))
        edits.append((begin, begin + len(before), after))

    def loss(feature, declaration, change):
        losses.append(
            {"feature": feature, "declaration": declaration, "change": change}
        )

    # Callouts are containers: a sibling start needs an empty line at its
    # parent's quote depth. A deeper start remains inside its parent.
    seen = {}
    for line in range(len(lines)):
        raw = lines[line].rstrip("\r\n")
        if line not in quoted:
            seen.clear()
        prefix = re.match(r" {0,3}(?:> ?)*", raw)[0]
        content_start = (
            len(prefix) + len(raw[len(prefix) :]) - len(raw[len(prefix) :].lstrip())
        )
        if content_start < len(raw) and literal_owned(
            line, content_start, content_start + 1
        ):
            continue
        if re.fullmatch(r" {0,3}(?:> ?)+\s*", raw):
            for prior in list(seen):
                if prior > raw.count(">"):
                    del seen[prior]
        if line not in active:
            if not raw.strip():
                seen.clear()
            continue
        match = _CALLOUT.fullmatch(raw)
        declaration = re.match(r" {0,3}(?:> ?)+(\[!)", raw)
        if declaration and literal_owned(
            line, declaration.start(1), declaration.end(1)
        ):
            continue
        if not match:
            quote = re.match(r" {0,3}(?:> ?)+", raw)
            if quote and any(prior > quote[0].count(">") for prior in seen):
                replace(line, raw, quote[0] + "\n" + raw)
                for prior in list(seen):
                    if prior > quote[0].count(">"):
                        del seen[prior]
            if re.match(r" {0,3}(?:> ?)+\[![A-Za-z]", raw):
                loss(
                    "callout",
                    raw,
                    "Malformed callout declaration retained as source text; use [!type] with an optional folding flag and title.",
                )
            if not raw.strip():
                seen.clear()
            continue
        prefix, kind, metadata, fold, title = match.groups()
        kind = kind.lower()
        if kind not in CALLOUTS:
            loss(
                "callout",
                raw,
                "Unsupported callout type retained as source text; change it to a supported native type.",
            )
            continue
        depth = prefix.count(">")
        if depth in seen:
            # Consume the marker line in the edit, avoiding empty-source edits.
            separator = "\n" if depth == 1 else "> " * (depth - 1) + "\n"
        else:
            separator = ""
        for prior in list(seen):
            if prior > depth:
                del seen[prior]
        seen[depth] = line
        after = raw
        if metadata:
            emoji = metadata.removeprefix("|icon:")
            supported = (
                metadata.startswith("|icon:")
                and emoji
                and not any(
                    c.isspace() or c in "|:[]\\`<>" or c.isascii() for c in emoji
                )
            )
            if supported:
                label = title.strip() or kind.title()
                after = f"{prefix}[!{kind}]{fold} {emoji} {label}"
                change = "Emoji is visible in the title; Obsidian's native icon remains. Edit the title to adjust this fallback."
            else:
                # Preserve ambiguous metadata visibly without activating it.
                safe = re.sub(r"([\\`*_{}\[\]<>])", r"\\\1", metadata)
                after = (
                    f"{prefix}[!{kind}]{fold} {title.strip() or kind.title()} — {safe}"
                )
                change = "Unsupported or ambiguous icon metadata is retained visibly in the title; replace it with a title emoji or remove it manually."
            loss("callout_icon", metadata, change)
        if separator or after != raw:
            replace(line, raw, separator + after)

    declared_tables = set()
    for line in sorted(active):
        raw = lines[line].rstrip("\r\n")
        if ":(table=" not in raw:
            continue
        declarations = [
            candidate.start()
            for candidate in re.finditer(re.escape(":(table="), raw)
            if not literal_owned(line, candidate.start(), candidate.end())
            and (
                len(raw[: candidate.start()])
                - len(raw[: candidate.start()].rstrip("\\"))
            )
            % 2
            == 0
        ]
        if not declarations:
            continue
        style_match = (
            _STYLE_TABLE.search(raw) if not (legacy_tables or previous_tables) else None
        )
        if style_match:
            declarations = [
                start
                for start in declarations
                if not style_match.start() < start < style_match.end()
            ]
        widths_match = _TABLE.search(raw)
        colors_match = None if preserve_table_colors else _COLOR_TABLE.search(raw)
        match = style_match or widths_match or colors_match
        if match and match.start() not in declarations:
            match = None
        cells = (
            _cells(
                raw[: match.start()],
                offsets[line],
                inline_code,
                inline_literals,
                legacy=legacy_tables,
            )
            if match
            else None
        )
        declaration = raw[declarations[0] :]
        rows = []
        cursor = line + 1
        while (
            cursor < len(lines)
            and cursor in active
            and lines[cursor].lstrip().startswith("|")
        ):
            row = lines[cursor].rstrip("\r\n")
            rows.append(
                _cells(
                    row,
                    offsets[cursor],
                    inline_code,
                    inline_literals,
                    legacy=legacy_tables,
                )
            )
            cursor += 1
        declared_tables.update(range(line, cursor))
        imported = bool(
            style_match
            and raw[: style_match.start()].strip() == "||"
            and len(rows) == 1
            and rows[0] is not None
            and len(rows[0]) == 2
        )
        if imported:
            cells = ["", ""]
        separator_present = bool(
            cells
            and rows
            and rows[0] is not None
            and len(rows[0]) == len(cells)
            and all(re.fullmatch(r"\s*:?-{3,}:?\s*", cell) for cell in rows[0])
        )
        widths = widths_match[1].split(",") if widths_match else []
        valid = bool(
            cells
            and len(cells) >= 1
            and (
                style_match
                or colors_match
                or widths_match
                and len(widths) == len(cells) + 1
                and all(re.fullmatch(r"-1|0|[1-9][0-9]*", w) for w in widths)
                and widths_match[2] == "default"
            )
            and len(declarations) == 1
            and rows
            and (
                style_match
                and separator_present
                or all(r is not None and len(r) == len(cells) for r in rows)
            )
        )
        if not valid:
            loss(
                "table",
                declaration,
                "Malformed or ambiguous table retained as source text; supply an ordinary Markdown table with a matching header separator.",
            )
            continue
        header = (
            _native_code_pipes(
                raw[: match.start()], offsets[line], inline_code, legacy=True
            )
            if legacy_tables
            else _native_table_row(
                raw[: match.start()],
                offsets[line],
                inline_code,
                inline_literals,
                previous_tables=previous_tables,
            )
        )
        if (
            imported
            or not (legacy_tables or previous_tables or compact_tables)
            and all(not cell.strip() for cell in cells)
        ):
            header = "|" + "|".join(blank_cell for _ in cells) + "|"
        separator_row = "|" + "|".join("---" for _ in cells) + "|"
        if separator_present:
            replacement = header
        elif (
            legacy_tables or previous_tables or all(not cell.strip() for cell in cells)
        ):
            replacement = header + "\n" + separator_row
        else:
            replacement = (
                "|"
                + "|".join(blank_cell for _ in cells)
                + "|\n"
                + separator_row
                + "\n"
                + header
            )
        if separate_tables and line and lines[line - 1].strip():
            replacement = "\n" + replacement
        replace(line, raw, replacement)
        for row_line in range(line + 1, cursor):
            row = lines[row_line].rstrip("\r\n")
            native_row = (
                _native_code_pipes(row, offsets[row_line], inline_code, legacy=True)
                if legacy_tables
                else _native_table_row(
                    row,
                    offsets[row_line],
                    inline_code,
                    inline_literals,
                    previous_tables=previous_tables,
                )
            )
            if (
                separate_tables
                and row_line == cursor - 1
                and cursor < len(lines)
                and lines[cursor].strip()
            ):
                native_row += "\n"
            if row != native_row:
                replace(row_line, row, native_row)
        if warn_tables:
            change = (
                "Custom table colors are not reproduced; the editable table uses Obsidian's native styling."
                if colors_match
                else "Column widths and justification become native responsive table layout; edit the table in Obsidian to adjust its presentation."
            )
            if style_match:
                change = "Source table styling is omitted; the editable table uses native Markdown layout."
            if not (legacy_tables or previous_tables or separator_present) and any(
                cell.strip() for cell in cells
            ):
                change += " Blank native headings preserve every source row as data."
            loss("table", declaration, change)

    line = 0
    while not legacy_tables and line < len(lines):
        start = line
        rows = []
        while (
            line < len(lines)
            and line in active
            and line in paragraph_lines
            and line not in declared_tables
            and lines[line].lstrip().startswith("|")
        ):
            rows.append(
                _cells(
                    lines[line].rstrip("\r\n"),
                    offsets[line],
                    inline_code,
                    inline_literals,
                )
            )
            line += 1
        if len(rows) < 2 or rows[0] is None:
            line = max(line, start + 1)
            continue
        imported = (
            len(rows) == 2
            and lines[start].strip() == "||"
            and rows[1] is not None
            and len(rows[1]) == 2
        )
        empty_header = not previous_tables and all(not cell.strip() for cell in rows[0])
        width = len(rows[1] if imported else rows[0])
        separator = (
            not imported
            and rows[1] is not None
            and len(rows[1]) == width
            and all(re.fullmatch(r"\s*:?-{3,}:?\s*", cell) for cell in rows[1])
        )
        if not separator and (
            width < 2
            or any(row is None or len(row) != width for row in rows[int(imported) :])
        ):
            loss(
                "table",
                lines[start].rstrip("\r\n"),
                "Malformed or ambiguous table retained as source text; supply an ordinary Markdown table with matching columns and a header separator.",
            )
            continue
        empty_row = "|" + "|".join(blank_cell for _ in range(width)) + "|"
        header = empty_row + "\n|" + "|".join("---" for _ in range(width)) + "|"
        for row_line in range(start, line):
            raw = lines[row_line].rstrip("\r\n")
            native = _native_table_row(
                raw,
                offsets[row_line],
                inline_code,
                inline_literals,
                previous_tables=previous_tables,
            )
            if row_line == start:
                if empty_header and separator and not compact_tables:
                    native = empty_row
                elif imported or empty_header and not separator:
                    native = header
                elif not separator:
                    native = header + "\n" + native
                if start and lines[start - 1].strip():
                    native = "\n" + native
            if row_line == line - 1 and line < len(lines) and lines[line].strip():
                native += "\n"
            if native != raw:
                replace(row_line, raw, native)
        if warn_tables and not separator:
            loss(
                "table",
                lines[start].rstrip("\r\n"),
                "The empty source header is expanded to the two-column data width; both data cells are preserved."
                if imported
                else "No column headings were declared; blank native headings preserve every source row as data.",
            )

    marker_prefixes = {
        line: match[1]
        for line in sorted(active)
        if (
            match := re.fullmatch(
                r"( {0,3}(?:> ?)*)\[/toc/\]\s*", lines[line].rstrip("\r\n")
            )
        )
        and not literal_owned(line, match.start() + len(match[1]), match.end())
    }
    markers = list(marker_prefixes)
    excluded = set()
    for marker in markers:
        preceding = [h for h in headings if h[0] < marker]
        if preceding:
            last = preceding[-1]
            if not any(lines[i].strip() for i in range(last[1], marker)):
                excluded.add(last[0])
    if markers:
        selected = [h for h in headings if h[0] not in excluded]
        identifiers, authored_identifiers = {}, {}
        selected_lines = {h[0] if h[4] else h[1] - 2 for h in selected}
        occurrences = {}
        for line in sorted(active):
            match = re.search(
                r"(?:^| )\^([A-Za-z0-9-]+)\s*$", lines[line].rstrip("\r\n")
            )
            if match and not literal_owned(line, match.start(1) - 1, match.end(1)):
                occurrences.setdefault(match[1], []).append(line)
        retained = set()
        for number, (line, end, level, _title, atx, authored, _math) in enumerate(
            selected, 1
        ):
            anchor_line = line if atx else end - 2
            raw = lines[anchor_line].rstrip("\r\n")
            existing = re.search(r" \^([A-Za-z0-9-]+)\s*$", raw)
            if existing:
                authored_identifiers[line] = existing[1]
            keep_existing = bool(
                existing
                and existing[1] not in retained
                and all(p in selected_lines for p in occurrences[existing[1]])
            )
            if keep_existing:
                identifiers[line] = existing[1]
                retained.add(existing[1])
            else:
                identifier = f"brz-toc-heading-{number}"
                while re.search(rf"\^{re.escape(identifier)}\b", text):
                    identifier += "-generated"
                identifiers[line] = identifier
                if existing:
                    loss(
                        "table_of_contents",
                        "^" + existing[1],
                        "A duplicate authored block ID was replaced with a distinct ToC destination; update authored links to this heading if needed.",
                    )
            if not atx and end - line > 2:
                before = "".join(lines[line:end]).rstrip("\r\n")
                prefix = re.match(r" {0,3}(?:> ?)*", lines[line])[0]
                content = authored
                if existing:
                    content = re.sub(
                        rf"(?:^| )\^{re.escape(existing[1])}\s*$", "", content
                    )
                replace(
                    line,
                    before,
                    prefix
                    + "#" * level
                    + " "
                    + " ".join(content.splitlines())
                    + " ^"
                    + identifiers[line],
                )
            elif not keep_existing:
                base = re.sub(r"[ \t]+#+[ \t]*$", "", raw) if atx else raw
                if existing:
                    base = base[: existing.start()]
                replace(anchor_line, raw, base + " ^" + identifiers[line])
        entries, hierarchy = [], []
        for line, _end, level, title, _atx, _authored, mathematics in selected:
            while hierarchy and hierarchy[-1] >= level:
                hierarchy.pop()
            if line in authored_identifiers:
                title = re.sub(
                    rf"(?:^| )\^{re.escape(authored_identifiers[line])}\s*$", "", title
                )
            title = title.strip() or "Heading"
            label = _toc_label(title, mathematics)
            entries.append(
                "  " * len(hierarchy) + f"- [{label}](#^{identifiers[line]})"
            )
            hierarchy.append(level)
        for marker in markers:
            replace(
                marker,
                "[/toc/]",
                ("\n" + marker_prefixes[marker]).join(entries)
                or "No authored headings.",
            )
    for line in sorted(active):
        raw = lines[line].strip()
        if (
            re.fullmatch(r"\[/toc[^\]]*\]", raw)
            and raw != "[/toc/]"
            and not literal_owned(
                line, lines[line].find(raw), lines[line].find(raw) + len("[/toc")
            )
        ):
            loss(
                "table_of_contents",
                raw,
                "Unsupported ToC declaration retained; use a standalone [/toc/] marker and reconvert, or author links manually.",
            )

    source_edits = [
        (
            source_position(begin, literal_edits),
            source_position(end, literal_edits),
            after,
            "markdown_insert",
        )
        for begin, end, after in edits
    ]
    source_edits.extend(
        (edit.start, edit.end, edit.after, "literal_text")
        for edit in literal_edits
        if not any(
            begin <= edit.start and edit.end <= end
            for begin, end, _after, _kind in source_edits
        )
    )
    digest = sha256(original.encode()).hexdigest()
    result, delta = [], 0
    for start, end, after, kind in sorted(source_edits):
        before = original[start:end]
        adapted_start, adapted_end = start + delta, start + delta + len(after)
        result.append(
            TextAdaptation(
                kind=kind,
                start=start,
                end=end,
                before=before,
                after=after,
                adapted_start=adapted_start,
                adapted_end=adapted_end,
                source_digest=digest,
            )
        )
        delta += len(after) - len(before)
    text = original
    for edit in reversed(result):
        text = text[: edit.start] + edit.after + text[edit.end :]
    return text, tuple(result), tuple(losses)


def bind_table_context(text, references):
    """Declare native table-cell reference context after all source text edits."""
    lines = re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", text)
    offsets, position = [0], 0
    for line in lines:
        position += len(line)
        offsets.append(position)
    tables = [
        (offsets[token.map[0]], offsets[token.map[1]])
        for token in MarkdownIt("commonmark").enable("table").parse(text)
        if token.type == "table_open" and token.map
    ]
    return tuple(
        reference.model_copy(
            update={
                "table_cell": any(
                    begin <= reference.start < reference.end <= end
                    for begin, end in tables
                )
            }
        )
        for reference in references
    )


def trace_adapted_references(text, edits):
    """Mask only adapter-generated code elements during source reference tracing.

    Their escaped literal payload cannot contain active references. Coordinate
    lengths remain fixed; all declared spans rebind to the actual document's
    digest. Imported HTML has already passed the unchanged refusal boundary.
    """
    masked = text
    for edit in reversed(edits):
        if edit.kind != "markdown_insert":
            continue
        for match in reversed(list(re.finditer(r"<code>[^<]*</code>", edit.after))):
            start, end = (
                edit.adapted_start + match.start(),
                edit.adapted_start + match.end(),
            )
            masked = masked[:start] + " " * (end - start) + masked[end:]
    digest = sha256(text.encode()).hexdigest()
    references = tuple(
        reference.model_copy(update={"document_digest": digest})
        for reference in trace_note_references(masked)
    )
    return bind_table_context(text, references)
