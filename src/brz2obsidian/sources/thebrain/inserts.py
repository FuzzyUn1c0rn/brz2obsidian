"""Scoped TheBrain inserts become editable native Markdown with exact evidence."""

import re
from hashlib import sha256
from html import escape

from markdown_it import MarkdownIt
from markdown_it.rules_inline import escape as inline_escape
from markdown_it.rules_inline import image, link
from markdown_it.rules_inline.backticks import backtick

from brz2obsidian.contracts import TextAdaptation

from ._origins import CopiedText, copied_join
from .literals import adapt_literals, source_position
from .notes import _mapped_blocks, trace_inline_literal_ranges, trace_note_references

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


def _cell_code_end(row, index, source_offset, code_ranges):
    end = index + 1
    while end < len(row) and row[end] == "`":
        end += 1
    owned = next(
        (finish for begin, finish in code_ranges if begin == source_offset + index),
        None,
    )
    if owned is not None:
        # A span crossing rows cannot become a faithful native cell.
        if owned - source_offset > len(row) - 1:
            return None
        end = owned - source_offset
    return end


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
            end = _cell_code_end(row, index, source_offset, code_ranges)
            if end is None:
                return None
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


def _split_insert_lines(text, _provenance):
    lines = re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", text)
    if lines and not lines[-1]:
        lines.pop()
    offsets, position = [], 0
    for line in lines:
        offsets.append(position)
        position += len(line)
    if _provenance is not None:
        lines = [
            CopiedText(line, range(offset, offset + len(line)))
            for line, offset in zip(lines, offsets, strict=True)
        ]
    return lines, offsets


def _insert_tokens(text, _provenance):
    if _provenance is None:
        tokens = MarkdownIt("commonmark").parse(text)
    else:
        parser, env = MarkdownIt("commonmark"), {}
        tokens = _mapped_blocks(text, parser, env)
        for token in tokens:
            if token.type == "inline":
                token.children = []
                parser.inline.parse(token.content, parser, env, token.children)
    return tokens


def _insert_blocks(tokens):
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
    return active, quoted, headings, paragraph_lines


def _finish_insert_edits(original, literal_edits, edits):
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
    return text, result


def _bind_insert_provenance(text, _provenance, literal_text, edits):
    if _provenance is not None:
        mapped = CopiedText(literal_text, range(len(literal_text)))
        for begin, end, after in sorted(edits, key=lambda e: e[0], reverse=True):
            mapped = mapped[:begin] + after + mapped[end:]
        if str(mapped) != text:
            from .notes import _refuse

            _refuse(
                "invalid_reference",
                "Insert origin mapping differs from exact adaptation",
            )
        _provenance.update(origins=mapped.origins, literal_text=literal_text)


class _NoteInserts:
    def __init__(
        self,
        text,
        provenance,
        preserve_table_colors,
        legacy_tables,
        previous_tables,
        compact_tables,
        legacy_table_boundaries,
        preserve_table_warnings,
    ):
        self.text = text
        self._provenance = provenance
        self.preserve_table_colors = preserve_table_colors
        self.legacy_tables = legacy_tables
        self.previous_tables = previous_tables
        self.compact_tables = compact_tables
        self.blank_cell = (
            "" if compact_tables or previous_tables or legacy_tables else " "
        )
        self.separate_tables = not (
            legacy_table_boundaries
            or legacy_tables
            or previous_tables
            or compact_tables
        )
        self.warn_tables = preserve_table_warnings or not self.separate_tables
        self.lines, self.offsets = _split_insert_lines(text, provenance)
        tokens = _insert_tokens(text, provenance)
        self.active, self.quoted, self.headings, self.paragraph_lines = _insert_blocks(
            tokens
        )
        self.inline_code, inline_comments = trace_inline_literal_ranges(text)
        self.inline_literals = self.inline_code + inline_comments
        self.edits, self.losses = [], []
        self.declared_tables = set()

    def literal_owned(self, line, start, end):
        begin, finish = self.offsets[line] + start, self.offsets[line] + end
        return any(
            left < finish and begin < right for left, right in self.inline_literals
        )

    def replace(self, line, before, after):
        begin = self.offsets[line] + max(0, self.lines[line].find(before))
        self.edits.append((begin, begin + len(before), after))

    def loss(self, feature, declaration, change):
        self.losses.append(
            {"feature": feature, "declaration": declaration, "change": change}
        )

    def adapt_callouts(self):
        # Callouts are containers: a sibling start needs an empty line at its
        # parent's quote depth. A deeper start remains inside its parent.
        seen = {}
        for line in range(len(self.lines)):
            self._adapt_callout_line(line, seen)

    def _adapt_callout_line(self, line, seen):
        raw = self.lines[line].rstrip("\r\n")
        if line not in self.quoted:
            seen.clear()
        prefix = re.match(r" {0,3}(?:> ?)*", raw)[0]
        content_start = (
            len(prefix) + len(raw[len(prefix) :]) - len(raw[len(prefix) :].lstrip())
        )
        if content_start < len(raw) and self.literal_owned(
            line, content_start, content_start + 1
        ):
            return
        if re.fullmatch(r" {0,3}(?:> ?)+\s*", raw):
            for prior in list(seen):
                if prior > raw.count(">"):
                    del seen[prior]
        if line not in self.active:
            if not raw.strip():
                seen.clear()
            return
        match = _CALLOUT.fullmatch(raw)
        declaration = re.match(r" {0,3}(?:> ?)+(\[!)", raw)
        if declaration and self.literal_owned(
            line, declaration.start(1), declaration.end(1)
        ):
            return
        if not match:
            self._plain_callout_line(line, raw, seen)
            return
        self._apply_callout(line, raw, match, seen)

    def _plain_callout_line(self, line, raw, seen):
        quote = re.match(r" {0,3}(?:> ?)+", raw)
        if quote and any(prior > quote[0].count(">") for prior in seen):
            self.replace(line, raw, quote[0] + "\n" + raw)
            for prior in list(seen):
                if prior > quote[0].count(">"):
                    del seen[prior]
        if re.match(r" {0,3}(?:> ?)+\[![A-Za-z]", raw):
            self.loss(
                "callout",
                raw,
                "Malformed callout declaration retained as source text; use [!type] with an optional folding flag and title.",
            )
        if not raw.strip():
            seen.clear()

    def _apply_callout(self, line, raw, match, seen):
        prefix, kind, metadata, fold, title = match.groups()
        if self._provenance is not None:
            prefix = raw[slice(*match.span(1))]
            title = raw[slice(*match.span(5))]
        kind = kind.lower()
        if kind not in CALLOUTS:
            self.loss(
                "callout",
                raw,
                "Unsupported callout type retained as source text; change it to a supported native type.",
            )
            return
        depth = prefix.count(">")
        if depth in seen:
            separator = "\n" if depth == 1 else "> " * (depth - 1) + "\n"
        else:
            separator = ""
        for prior in list(seen):
            if prior > depth:
                del seen[prior]
        seen[depth] = line
        after = raw
        if metadata:
            after = self._callout_title(prefix, kind, metadata, fold, title)
        if separator or after != raw:
            self.replace(line, raw, separator + after)

    def _callout_title(self, prefix, kind, metadata, fold, title):
        emoji = metadata.removeprefix("|icon:")
        supported = (
            metadata.startswith("|icon:")
            and emoji
            and not any(c.isspace() or c in "|:[]\\`<>" or c.isascii() for c in emoji)
        )
        if supported:
            label = title.strip() or kind.title()
            after = prefix + f"[!{kind}]{fold} {emoji} " + label
            change = "Emoji is visible in the title; Obsidian's native icon remains. Edit the title to adjust this fallback."
        else:
            # Preserve ambiguous metadata visibly without activating it.
            safe = re.sub(r"([\\`*_{}\[\]<>])", r"\\\1", metadata)
            after = (
                prefix
                + f"[!{kind}]{fold} "
                + (title.strip() or kind.title())
                + f" — {safe}"
            )
            change = "Unsupported or ambiguous icon metadata is retained visibly in the title; replace it with a title emoji or remove it manually."
        self.loss("callout_icon", metadata, change)
        return after

    def adapt_declared_tables(self):
        for line in sorted(self.active):
            self._adapt_declared_table(line)

    def _adapt_declared_table(self, line):
        raw = self.lines[line].rstrip("\r\n")
        if ":(table=" not in raw:
            return
        declarations = [
            candidate.start()
            for candidate in re.finditer(re.escape(":(table="), raw)
            if not self.literal_owned(line, candidate.start(), candidate.end())
            and (
                len(raw[: candidate.start()])
                - len(raw[: candidate.start()].rstrip("\\"))
            )
            % 2
            == 0
        ]
        if not declarations:
            return
        style_match = (
            _STYLE_TABLE.search(raw)
            if not (self.legacy_tables or self.previous_tables)
            else None
        )
        if style_match:
            declarations = [
                start
                for start in declarations
                if not style_match.start() < start < style_match.end()
            ]
        widths_match = _TABLE.search(raw)
        colors_match = None if self.preserve_table_colors else _COLOR_TABLE.search(raw)
        match = style_match or widths_match or colors_match
        if match and match.start() not in declarations:
            match = None
        cells = (
            _cells(
                raw[: match.start()],
                self.offsets[line],
                self.inline_code,
                self.inline_literals,
                legacy=self.legacy_tables,
            )
            if match
            else None
        )
        declaration = raw[declarations[0] :]
        rows, cursor = self._declared_rows(line)
        self.declared_tables.update(range(line, cursor))
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
            self.loss(
                "table",
                declaration,
                "Malformed or ambiguous table retained as source text; supply an ordinary Markdown table with a matching header separator.",
            )
            return
        self._render_declared_table(
            line, cursor, raw, match, cells, imported, separator_present
        )
        self._warn_declared_table(
            style_match, colors_match, separator_present, cells, declaration
        )

    def _declared_rows(self, line):
        rows = []
        cursor = line + 1
        while (
            cursor < len(self.lines)
            and cursor in self.active
            and self.lines[cursor].lstrip().startswith("|")
        ):
            row = self.lines[cursor].rstrip("\r\n")
            rows.append(
                _cells(
                    row,
                    self.offsets[cursor],
                    self.inline_code,
                    self.inline_literals,
                    legacy=self.legacy_tables,
                )
            )
            cursor += 1
        return rows, cursor

    def _render_declared_table(
        self, line, cursor, raw, match, cells, imported, separator_present
    ):
        header = (
            _native_code_pipes(
                raw[: match.start()], self.offsets[line], self.inline_code, legacy=True
            )
            if self.legacy_tables
            else _native_table_row(
                raw[: match.start()],
                self.offsets[line],
                self.inline_code,
                self.inline_literals,
                previous_tables=self.previous_tables,
            )
        )
        if (
            imported
            or not (self.legacy_tables or self.previous_tables or self.compact_tables)
            and all(not cell.strip() for cell in cells)
        ):
            header = "|" + "|".join(self.blank_cell for _ in cells) + "|"
        separator_row = "|" + "|".join("---" for _ in cells) + "|"
        if separator_present:
            replacement = header
        elif (
            self.legacy_tables
            or self.previous_tables
            or all(not cell.strip() for cell in cells)
        ):
            replacement = header + "\n" + separator_row
        else:
            replacement = (
                "|"
                + "|".join(self.blank_cell for _ in cells)
                + "|\n"
                + separator_row
                + "\n"
                + header
            )
        if self.separate_tables and line and self.lines[line - 1].strip():
            replacement = "\n" + replacement
        self.replace(line, raw, replacement)
        self._render_declared_rows(line, cursor)

    def _render_declared_rows(self, line, cursor):
        for row_line in range(line + 1, cursor):
            row = self.lines[row_line].rstrip("\r\n")
            native_row = (
                _native_code_pipes(
                    row, self.offsets[row_line], self.inline_code, legacy=True
                )
                if self.legacy_tables
                else _native_table_row(
                    row,
                    self.offsets[row_line],
                    self.inline_code,
                    self.inline_literals,
                    previous_tables=self.previous_tables,
                )
            )
            if (
                self.separate_tables
                and row_line == cursor - 1
                and cursor < len(self.lines)
                and self.lines[cursor].strip()
            ):
                native_row += "\n"
            if row != native_row:
                self.replace(row_line, row, native_row)

    def _warn_declared_table(
        self, style_match, colors_match, separator_present, cells, declaration
    ):
        if self.warn_tables:
            change = (
                "Custom table colors are not reproduced; the editable table uses Obsidian's native styling."
                if colors_match
                else "Column widths and justification become native responsive table layout; edit the table in Obsidian to adjust its presentation."
            )
            if style_match:
                change = "Source table styling is omitted; the editable table uses native Markdown layout."
            if not (
                self.legacy_tables or self.previous_tables or separator_present
            ) and any(cell.strip() for cell in cells):
                change += " Blank native headings preserve every source row as data."
            self.loss("table", declaration, change)

    def adapt_plain_tables(self):
        line = 0
        while not self.legacy_tables and line < len(self.lines):
            start = line
            rows, line = self._plain_rows(line)
            if len(rows) < 2 or rows[0] is None:
                line = max(line, start + 1)
                continue
            self._adapt_plain_table(start, line, rows)

    def _plain_rows(self, line):
        rows = []
        while (
            line < len(self.lines)
            and line in self.active
            and line in self.paragraph_lines
            and line not in self.declared_tables
            and self.lines[line].lstrip().startswith("|")
        ):
            rows.append(
                _cells(
                    self.lines[line].rstrip("\r\n"),
                    self.offsets[line],
                    self.inline_code,
                    self.inline_literals,
                )
            )
            line += 1
        return rows, line

    def _adapt_plain_table(self, start, line, rows):
        imported = (
            len(rows) == 2
            and self.lines[start].strip() == "||"
            and rows[1] is not None
            and len(rows[1]) == 2
        )
        empty_header = not self.previous_tables and all(
            not cell.strip() for cell in rows[0]
        )
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
            self.loss(
                "table",
                self.lines[start].rstrip("\r\n"),
                "Malformed or ambiguous table retained as source text; supply an ordinary Markdown table with matching columns and a header separator.",
            )
            return
        self._render_plain_table(start, line, imported, empty_header, width, separator)
        if self.warn_tables and not separator:
            self.loss(
                "table",
                self.lines[start].rstrip("\r\n"),
                "The empty source header is expanded to the two-column data width; both data cells are preserved."
                if imported
                else "No column headings were declared; blank native headings preserve every source row as data.",
            )

    def _render_plain_table(
        self, start, line, imported, empty_header, width, separator
    ):
        empty_row = "|" + "|".join(self.blank_cell for _ in range(width)) + "|"
        header = empty_row + "\n|" + "|".join("---" for _ in range(width)) + "|"
        for row_line in range(start, line):
            raw = self.lines[row_line].rstrip("\r\n")
            native = _native_table_row(
                raw,
                self.offsets[row_line],
                self.inline_code,
                self.inline_literals,
                previous_tables=self.previous_tables,
            )
            if row_line == start:
                native = self._plain_header(
                    start, native, empty_header, separator, imported, empty_row, header
                )
            if (
                row_line == line - 1
                and line < len(self.lines)
                and self.lines[line].strip()
            ):
                native += "\n"
            if native != raw:
                self.replace(row_line, raw, native)

    def _plain_header(
        self, start, native, empty_header, separator, imported, empty_row, header
    ):
        if empty_header and separator and not self.compact_tables:
            native = empty_row
        elif imported or empty_header and not separator:
            native = header
        elif not separator:
            native = header + "\n" + native
        if start and self.lines[start - 1].strip():
            native = "\n" + native
        return native

    def _toc_markers(self):
        marker_prefixes = {
            line: match[1]
            for line in sorted(self.active)
            if (
                match := re.fullmatch(
                    r"( {0,3}(?:> ?)*)\[/toc/\]\s*", self.lines[line].rstrip("\r\n")
                )
            )
            and not self.literal_owned(line, match.start() + len(match[1]), match.end())
        }
        markers = list(marker_prefixes)
        excluded = set()
        for marker in markers:
            preceding = [h for h in self.headings if h[0] < marker]
            if preceding:
                last = preceding[-1]
                if not any(self.lines[i].strip() for i in range(last[1], marker)):
                    excluded.add(last[0])
        return marker_prefixes, markers, excluded

    def _block_id_occurrences(self):
        occurrences = {}
        for line in sorted(self.active):
            match = re.search(
                r"(?:^| )\^([A-Za-z0-9-]+)\s*$", self.lines[line].rstrip("\r\n")
            )
            if match and not self.literal_owned(line, match.start(1) - 1, match.end(1)):
                occurrences.setdefault(match[1], []).append(line)
        return occurrences

    def _toc_heading_ids(self, selected):
        identifiers, authored_identifiers = {}, {}
        selected_lines = {h[0] if h[4] else h[1] - 2 for h in selected}
        occurrences = self._block_id_occurrences()
        retained = set()
        for number, (line, end, level, _title, atx, authored, _math) in enumerate(
            selected, 1
        ):
            anchor_line = line if atx else end - 2
            raw = self.lines[anchor_line].rstrip("\r\n")
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
                while re.search(rf"\^{re.escape(identifier)}\b", self.text):
                    identifier += "-generated"
                identifiers[line] = identifier
                if existing:
                    self.loss(
                        "table_of_contents",
                        "^" + existing[1],
                        "A duplicate authored block ID was replaced with a distinct ToC destination; update authored links to this heading if needed.",
                    )
            self._set_heading_id(
                line,
                end,
                level,
                atx,
                authored,
                existing,
                keep_existing,
                raw,
                anchor_line,
                identifiers[line],
            )
        return identifiers, authored_identifiers

    def _set_heading_id(
        self,
        line,
        end,
        level,
        atx,
        authored,
        existing,
        keep_existing,
        raw,
        anchor_line,
        identifier,
    ):
        if not atx and end - line > 2:
            before = "".join(self.lines[line:end]).rstrip("\r\n")
            prefix = re.match(r" {0,3}(?:> ?)*", self.lines[line])[0]
            content = authored
            if self._provenance is not None:
                content = CopiedText(authored, authored.offsets)
            if existing:
                suffix = re.search(rf"(?:^| )\^{re.escape(existing[1])}\s*$", content)
                content = content[: suffix.start()] if suffix else content
            self.replace(
                line,
                before,
                prefix
                + "#" * level
                + " "
                + (
                    copied_join(" ", content.splitlines())
                    if self._provenance is not None
                    else " ".join(content.splitlines())
                )
                + " ^"
                + identifier,
            )
        elif not keep_existing:
            closing = re.search(r"[ \t]+#+[ \t]*$", raw) if atx else None
            base = raw[: closing.start()] if closing else raw
            if existing:
                base = base[: existing.start()]
            self.replace(anchor_line, raw, base + " ^" + identifier)

    def _toc_entries(self, selected, identifiers, authored_identifiers):
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
        return entries

    def adapt_toc(self):
        marker_prefixes, markers, excluded = self._toc_markers()
        if markers:
            selected = [h for h in self.headings if h[0] not in excluded]
            identifiers, authored_identifiers = self._toc_heading_ids(selected)
            entries = self._toc_entries(selected, identifiers, authored_identifiers)
            for marker in markers:
                self.replace(
                    marker,
                    "[/toc/]",
                    ("\n" + marker_prefixes[marker]).join(entries)
                    or "No authored headings.",
                )
        self._warn_malformed_toc()

    def _warn_malformed_toc(self):
        for line in sorted(self.active):
            raw = self.lines[line].strip()
            if (
                re.fullmatch(r"\[/toc[^\]]*\]", raw)
                and raw != "[/toc/]"
                and not self.literal_owned(
                    line,
                    self.lines[line].find(raw),
                    self.lines[line].find(raw) + len("[/toc"),
                )
            ):
                self.loss(
                    "table_of_contents",
                    raw,
                    "Unsupported ToC declaration retained; use a standalone [/toc/] marker and reconvert, or author links manually.",
                )


def adapt_note(
    text,
    *,
    allow_literal_tokens=False,
    preserve_table_colors=False,
    legacy_tables=False,
    previous_tables=False,
    compact_tables=False,
    legacy_table_boundaries=False,
    preserve_table_warnings=False,
    _provenance=None,
):
    """Return scoped adapted text, source-neutral exact edits and loss facts.

    Parser block ownership protects code, comments and literal examples. All
    references are traced after adaptation, so their offsets bind final text.
    """
    original = text
    text, literal_edits = adapt_literals(
        text, allow_literal_tokens=allow_literal_tokens
    )
    inserts = _NoteInserts(
        text,
        _provenance,
        preserve_table_colors,
        legacy_tables,
        previous_tables,
        compact_tables,
        legacy_table_boundaries,
        preserve_table_warnings,
    )
    inserts.adapt_callouts()
    inserts.adapt_declared_tables()
    inserts.adapt_plain_tables()
    inserts.adapt_toc()
    text, result = _finish_insert_edits(original, literal_edits, inserts.edits)
    _bind_insert_provenance(text, _provenance, inserts.text, inserts.edits)
    return text, tuple(result), tuple(inserts.losses)


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


def trace_adapted_references(
    text, edits, *, allow_qualified=False, generated_code_ranges=()
):
    """Mask only adapter-generated code elements during source reference tracing.

    Their escaped literal payload cannot contain active references. Coordinate
    lengths remain fixed; all declared spans rebind to the actual document's
    digest. Imported HTML has already passed the unchanged refusal boundary.
    """
    masked = text
    for start, end in sorted(generated_code_ranges, reverse=True):
        masked = masked[:start] + " " * (end - start) + masked[end:]
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
        for reference in trace_note_references(masked, allow_qualified=allow_qualified)
    )
    return bind_table_context(text, references)
