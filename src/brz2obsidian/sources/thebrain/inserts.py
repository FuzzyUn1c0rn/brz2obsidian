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
from .notes import trace_note_references

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


def _cells(row):
    """Pipes in escapes and balanced code spans belong to their authored cell."""
    row = row.strip()
    if not row.startswith("|") or not row.endswith("|"):
        return None
    cells, start, index, code = [], 1, 1, 0
    while index < len(row) - 1:
        if row[index] == "\\":
            index += 2
            continue
        if row[index] == "`":
            end = index + 1
            while end < len(row) and row[end] == "`":
                end += 1
            width = end - index
            if not code:
                # An unmatched tick is prose, not a cell-boundary shelter.
                if re.search(rf"(?<!`)`{{{width}}}(?!`)", row[end:]):
                    code = width
            elif width == code:
                code = 0
            index = end
            continue
        if row[index] == "|" and not code:
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


def _native_code_pipes(row):
    """A narrowly generated code element preserves native code-cell pipes.

    Obsidian displays a backslash for pipe escapes inside inline code. Source
    HTML remains refused before this generated normalization is reached.
    """

    def replace(match):
        content = match[2]
        if "|" not in content:
            return match[0]
        content = content.replace("\r", " ").replace("\n", " ")
        if content.startswith(" ") and content.endswith(" ") and content.strip():
            content = content[1:-1]
        return (
            "<code>" + escape(content, quote=False).replace("|", "&#124;") + "</code>"
        )

    return re.sub(r"(?<![\\`])(`+)(?!`)(.*?)(?<!`)\1(?!`)", replace, row)


def adapt_note(text):
    """Return scoped adapted text, source-neutral exact edits and loss facts.

    Parser block ownership protects code, comments and literal examples. All
    references are traced after adaptation, so their offsets bind final text.
    """
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
    active, protected, headings = set(), set(), []
    for index, token in enumerate(tokens):
        if not token.map:
            continue
        extent = range(*token.map)
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
    edits, losses = [], []

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
        if re.fullmatch(r" {0,3}(?:> ?)+\s*", raw):
            for prior in list(seen):
                if prior > raw.count(">"):
                    del seen[prior]
        if line not in active:
            if not raw.strip():
                seen.clear()
            continue
        match = _CALLOUT.fullmatch(raw)
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
            if not raw.strip() or (raw.strip() and not raw.lstrip().startswith(">")):
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

    for line in sorted(active):
        raw = lines[line].rstrip("\r\n")
        if ":(table=" not in raw:
            continue
        declaration_start = raw.find(":(table=")
        backslashes = len(raw[:declaration_start]) - len(
            raw[:declaration_start].rstrip("\\")
        )
        if backslashes % 2:
            continue
        # Only a suffix outside an inline code span is an insert declaration.
        inline = MarkdownIt("commonmark").parseInline(raw)[0]
        if not any(
            ":(table=" in t.content for t in inline.children or () if t.type == "text"
        ):
            continue
        match = _TABLE.search(raw)
        cells = _cells(raw[: match.start()]) if match else None
        declaration = raw[raw.find(":(table=") :]
        rows = []
        cursor = line + 1
        while (
            cursor < len(lines)
            and cursor in active
            and lines[cursor].lstrip().startswith("|")
        ):
            rows.append(_cells(lines[cursor].rstrip("\r\n")))
            cursor += 1
        widths = match[1].split(",") if match else []
        valid = bool(
            cells
            and len(cells) >= 1
            and len(widths) == len(cells) + 1
            and all(re.fullmatch(r"-1|0|[1-9][0-9]*", w) for w in widths)
            and raw.count(":(table=") == 1
            and match[2] == "default"
            and rows
            and all(r is not None and len(r) == len(cells) for r in rows)
        )
        if not valid:
            loss(
                "table",
                declaration,
                "Malformed or ambiguous table retained as source text; supply an ordinary Markdown table with a matching header separator.",
            )
            continue
        header = _native_code_pipes(raw[: match.start()])
        separator_present = all(re.fullmatch(r"\s*:?-{3,}:?\s*", c) for c in rows[0])
        replacement = (
            header
            if separator_present
            else header + "\n|" + "|".join("---" for _ in cells) + "|"
        )
        replace(line, raw, replacement)
        for row_line in range(line + 1, cursor):
            row = lines[row_line].rstrip("\r\n")
            native_row = _native_code_pipes(row)
            if row != native_row:
                replace(row_line, row, native_row)
        loss(
            "table",
            declaration,
            "Column widths and justification become native responsive table layout; edit the table in Obsidian to adjust its presentation.",
        )

    marker_prefixes = {
        line: match[1]
        for line in sorted(active)
        if (
            match := re.fullmatch(
                r"( {0,3}(?:> ?)*)\[/toc/\]\s*", lines[line].rstrip("\r\n")
            )
        )
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
            if match:
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
        if re.fullmatch(r"\[/toc[^\]]*\]", raw) and raw != "[/toc/]":
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
