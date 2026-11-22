"""Bounded static target inspection for native Bases expressions."""

import re
from dataclasses import dataclass
from urllib.parse import unquote

import yaml

from brz2obsidian.contracts import ExactContent, LinkMeaning, LinkQuery

from .links import interpret_links

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
    if not tokens or any(token != "+" for token in tokens[1::2]):
        return None
    values = []
    for token in tokens[::2]:
        matched = _STRING.fullmatch(token)
        if matched is None:
            return None
        values.append(matched[1] if matched[1] is not None else matched[2])
    return "".join(values) if len(tokens) % 2 else None


def _note_properties(tokens):
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
            token in ("file", "link")
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


def _fixed_reference(target, display, path, ordinal, catalog):
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
    return BaseOccurrence(f"{path}:base:{ordinal}", row.query, meaning)


def inspect_base_document(path, raw, catalog):
    """Observe literal path arguments and retain evidence for unsupported calls."""
    content = ExactContent(data=raw)
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
                    target, _literal(display), path, len(occurrences), catalog
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
