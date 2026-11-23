"""Bounded static target inspection for native Bases expressions."""

import re
from dataclasses import dataclass
from urllib.parse import unquote

import yaml

from brz2obsidian.contracts import ExactContent, LinkMeaning, LinkQuery

from .links import _code_ranges, interpret_links

_TOKEN = re.compile(r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[A-Za-z_][\w]*|[^\s]""")
_STRING = re.compile(r""""([^"\\]*)"|'([^'\\]*)' """.rstrip())


@dataclass(frozen=True)
class BaseOccurrence:
    occurrence_id: str
    query: LinkQuery | None
    meaning: LinkMeaning


@dataclass(frozen=True)
class BaseDocument:
    source_path: str
    content: ExactContent
    occurrences: tuple[BaseOccurrence, ...]
    uncertain: tuple[str, ...]
    unreadable: bool
    uncertain_properties: tuple[str, ...] = ()

    @property
    def status(self):
        return "unsupported" if self.unreadable or self.uncertain else "supported"


def _literal(tokens):
    values = []
    depth = 0
    needs_value = True
    for token in tokens:
        if token == "(" and needs_value:
            depth += 1
        elif token == ")" and not needs_value and depth:
            depth -= 1
        elif token == "+" and not needs_value:
            needs_value = True
        elif needs_value and (matched := _STRING.fullmatch(token)) is not None:
            values.append(matched[1] if matched[1] is not None else matched[2])
            needs_value = False
        else:
            return None
    return "".join(values) if not needs_value and not depth else None


def _ungroup_property(tokens):
    start, stop = 0, len(tokens)
    while start + 1 < stop and tokens[start] == "(" and tokens[stop - 1] == ")":
        start += 1
        stop -= 1
    if stop - start == 1 and tokens[start].isidentifier():
        return tokens[start]
    return None


def _note_properties(tokens):
    bare = _ungroup_property(tokens)
    if bare is not None:
        yield bare
    for i in range(len(tokens) - 2):
        owner, access, name = tokens[i : i + 3]
        if owner == "note" and access == "." and name.isidentifier():
            yield name
        elif owner == "note" and access == "[" and tokens[i + 3 : i + 4] == ("]",):
            literal = _literal((name,))
            if literal:
                yield literal


def _first_argument(tokens, start):
    depth = 0
    for i in range(start, len(tokens)):
        token = tokens[i]
        if depth == 0 and token in (",", ")"):
            return tokens[start:i], i
        depth += (token in ("(", "[", "{")) - (token in (")", "]", "}"))
    return tokens[start:], len(tokens)


def _calls(expression):
    tokens = tuple(_TOKEN.findall(expression))
    for i, token in enumerate(tokens[:-1]):
        if (
            token in ("file", "image", "link")
            and tokens[i + 1] == "("
            and (not i or tokens[i - 1] != ".")
        ):
            args, end = _first_argument(tokens, i + 2)
            display = ()
            if tokens[end : end + 1] == (",",):
                display, _ = _first_argument(tokens, end + 1)
            yield args, display


def _expression_roots(value):
    if not isinstance(value, dict):
        return ()
    views = value.get("views", ())
    filters = (
        (row.get("filters") for row in views if isinstance(row, dict))
        if isinstance(views, list)
        else ()
    )
    return value.get("formulas"), value.get("filters"), *filters


def _expressions(value):
    pending = list(_expression_roots(value))
    seen = set()
    while pending:
        row = pending.pop()
        if isinstance(row, str):
            yield row
        elif isinstance(row, (dict, list)) and id(row) not in seen:
            seen.add(id(row))
            pending.extend(
                reversed(tuple(row.values()) if isinstance(row, dict) else row)
            )


def _wiki_destination(target):
    if target.startswith("[[") and target.endswith("]]"):
        return target
    return f"[[{target}]]"


def _fixed_reference(target, display, path, occurrence_id, catalog):
    if re.match(r"(?i)^[a-z][a-z+.-]*://", target):
        return None
    interpreted = interpret_links(
        ExactContent(data=_wiki_destination(target).encode()),
        document_id=path,
        source_path=path,
        path_mode="vault",
        targets=catalog[0],
        target_facts=catalog[1],
        inventory="complete",
        output_format=9,
        authored_links=True,
    )
    if len(interpreted.occurrences) != 1:
        return None
    (row,) = interpreted.occurrences
    if row.query is None:
        return None
    meaning = (
        row.meaning
        if display is None
        else row.meaning.model_copy(update={"display_text": display})
    )
    return BaseOccurrence(occurrence_id, row.query, meaning)


def inspect_base_document(path, raw, catalog, *, document=None, prefix=None):
    """Observe literal path arguments and retain evidence for unsupported calls."""
    content = document if document is not None else ExactContent(data=raw)
    prefix = f"{path}:base" if prefix is None else prefix
    try:
        value = yaml.safe_load(raw.decode("utf-8"))
    except UnicodeDecodeError, yaml.YAMLError, RecursionError:
        return BaseDocument(path, content, (), (), True)
    occurrences, uncertain, properties = [], [], set()
    for expression in _expressions(value):
        for args, display in _calls(expression):
            target = _literal(args)
            if target is not None and re.match(r"(?i)^[a-z][a-z+.-]*://", target):
                continue
            row = (
                None
                if target is None
                else _fixed_reference(
                    target,
                    _literal(display),
                    path,
                    f"{prefix}:{len(occurrences)}",
                    catalog,
                )
            )
            if row is None:
                uncertain.extend(
                    unquote(token.strip("'\""))
                    for token in args
                    if token.startswith(("'", '"'))
                )
                uncertain.append("")
                properties.update(_note_properties(args))
            else:
                occurrences.append(row)
    return BaseDocument(
        path,
        content,
        tuple(occurrences),
        tuple(uncertain),
        False,
        tuple(sorted(properties)),
    )


def _base_fence_content(chunk):
    lines = chunk.splitlines(keepends=True)
    opening = re.fullmatch(r" {0,3}(`{3,}|~{3,})[ \t]*base\s*", lines[0])
    if opening is None:
        return None
    marker = opening[1]
    end = len(lines)
    if end > 1 and re.fullmatch(
        r" {0,3}" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}\s*",
        lines[-1],
    ):
        end -= 1
    return "".join(lines[1:end]).encode("utf-8")


def inspect_embedded_bases(path, content, catalog):
    """Observe only Markdown code ranges explicitly declared as native Bases."""
    try:
        text = content.data.decode("utf-8")
    except UnicodeDecodeError:
        return
    ranges, _ = _code_ranges(text)
    for index, (start, end) in enumerate(ranges):
        raw = _base_fence_content(text[start:end])
        if raw is not None:
            yield inspect_base_document(
                path,
                raw,
                catalog,
                document=content,
                prefix=f"{path}:base:{index}",
            )


def base_note_property_values(files, names):
    """Collect observed string values for directly named note properties only."""
    if not names:
        return {}
    values = {name: set() for name in names}
    for path, raw in files.items():
        if not path.casefold().endswith(".md") or not isinstance(raw, bytes):
            continue
        lines = raw.splitlines()
        if not lines or lines[0] != b"---":
            continue
        try:
            end = lines.index(b"---", 1)
            frontmatter = yaml.safe_load(b"\n".join(lines[1:end]).decode("utf-8"))
        except UnicodeDecodeError, ValueError, yaml.YAMLError, RecursionError:
            continue
        if isinstance(frontmatter, dict):
            for name in names:
                value = frontmatter.get(name)
                if isinstance(value, str):
                    values[name].add(value)
    return values
