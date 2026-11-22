"""Compare authored Obsidian link meanings around a proposed collection import."""

import re
import unicodedata
from collections import defaultdict
from hashlib import sha256
from urllib.parse import unquote

from brz2obsidian.contracts import (
    ContentIdentity,
    ExactContent,
    IdentityTargetFacts,
    ImportLinkConnection,
    ImportLinkImpact,
    ImportLinkObservation,
    OpaqueContent,
    ReferenceTarget,
)
from brz2obsidian.core.import_placement import import_name_key
from brz2obsidian.core.link_meanings import resolve_occurrence

from .base_import_links import (
    BaseDocument,
    base_note_property_values,
    inspect_base_document,
)
from .links import interpret_link_target, interpret_links


def _key(value):
    return unicodedata.normalize("NFC", value).casefold()


def _catalog(files, reserved_paths, gap_paths):
    roles = dict.fromkeys(reserved_paths, "intentionally_uncreated")
    roles.update(dict.fromkeys(gap_paths, "known_source_gap"))
    roles.update(dict.fromkeys(files, "present"))
    targets = tuple(
        ReferenceTarget(
            schema_id="brz2obsidian.reference-target",
            schema_version=1,
            target_id=path,
            kind="note" if path.lower().endswith(".md") else "resource",
            canonical_path=path,
            identity=None,
            target=IdentityTargetFacts(
                normalized_path=_key(path), containment="contained", status="safe"
            ),
            representations=(),
            validation_fingerprint=sha256(path.encode()).hexdigest(),
            status="safe",
        )
        for path in sorted(roles)
    )
    states = tuple(
        _link_state(path, roles[path], files.get(path)) for path in sorted(roles)
    )
    return targets, states


def _link_state(path, existence, value):
    textual = path.casefold().endswith((".md", ".base"))
    content = ExactContent(data=value) if textual and isinstance(value, bytes) else None
    state = interpret_link_target(
        content,
        target_id=path,
        existence=existence,
        memberships=(),
        source_path=path,
        output_format=9,
    )
    if isinstance(value, ContentIdentity):
        return state.model_copy(
            update={"content": OpaqueContent(identity=value), "file_roles": None}
        )
    if content is None and isinstance(value, bytes):
        digest = sha256(value).hexdigest()
        identity = ContentIdentity(
            content_id=f"sha256:{digest}:{len(value)}", sha256=digest, size=len(value)
        )
        return state.model_copy(
            update={"content": OpaqueContent(identity=identity), "file_roles": None}
        )
    return state


def _authored_documents(files, catalog):
    targets, states = catalog
    return tuple(
        inspect_base_document(path, raw, catalog)
        if path.lower().endswith(".base")
        else interpret_links(
            ExactContent(data=raw),
            document_id=path,
            source_path=path,
            path_mode="vault",
            targets=targets,
            target_facts=states,
            inventory="complete",
            output_format=9,
            authored_links=True,
        )
        for path, raw in sorted(files.items())
        if isinstance(raw, bytes) and path.lower().endswith((".md", ".base"))
    )


def _existing_kind(status):
    if status in ("resolved", "external"):
        return "preserved"
    if status == "intentionally_uncreated":
        return "intentional_absence"
    if status == "known_source_gap":
        return "known_source_gap"
    return "preexisting_warning"


def _connection(document, occurrence, after, incoming):
    if (
        occurrence.meaning.status != "missing"
        or after.status != "resolved"
        or after.path not in incoming
        or not after.path.lower().endswith(".md")
        or after.target_version is None
    ):
        return None
    return ImportLinkConnection(
        document_path=document.source_path,
        occurrence_id=occurrence.occurrence_id,
        document_sha256=sha256(document.content.data).hexdigest(),
        target_path=after.path,
        target_sha256=after.target_version,
    )


def _observation(document, occurrence, after_catalog, incoming, approved, continuation):
    before = occurrence.meaning
    after = resolve_occurrence(occurrence, *after_catalog, "complete")
    choice = None
    if before == after or (
        continuation
        and before.status == "resolved"
        and before.model_copy(update={"target_version": after.target_version}) == after
    ):
        kind = _existing_kind(before.status)
    else:
        choice = _connection(document, occurrence, after, incoming)
        kind = (
            "approved_connection"
            if choice in approved
            else "connection_required"
            if choice is not None
            else "changed_meaning"
        )
    return ImportLinkObservation(
        document_path=document.source_path,
        occurrence_id=occurrence.occurrence_id,
        query=occurrence.query,
        before=before,
        after=after,
        kind=kind,
        connection=choice,
    )


def _base_may_reach_import(document, incoming, property_values):
    if document.unreadable:
        return True
    property_targets = (
        value
        for name in document.uncertain_properties
        for value in property_values[name]
    )
    for token in (*document.uncertain, *property_targets):
        if not token:
            continue
        value = _key(token.removeprefix("[[").removesuffix("]]").lstrip("/"))
        for path in incoming:
            normalized = _key(path)
            if "/" in value and any(
                suffix.startswith(value)
                for suffix in (
                    normalized,
                    *(
                        normalized[i + 1 :]
                        for i, char in enumerate(normalized)
                        if char == "/"
                    ),
                )
            ):
                return True
            if "/" not in value and import_name_key(value) == import_name_key(path):
                return True
    return False


def _may_reach_import(document, incoming, property_values):
    if isinstance(document, BaseDocument):
        return _base_may_reach_import(document, incoming, property_values)
    incoming_names = {import_name_key(path) for path in incoming}
    raw = bytearray(document.content.data)
    for row in document.occurrences:
        if row.query is not None or row.meaning.status == "external":
            raw[row.span.start : row.span.end] = b" " * (row.span.end - row.span.start)
    try:
        decoded = _key(unquote(raw.decode("utf-8")).replace("\\", ""))
    except UnicodeDecodeError:
        return True
    if "[[##" in decoded or "[[^^" in decoded:
        return True
    destinations = re.findall(
        r"(?m)\[\[([^\]\r\n]*)|\]\(([^)\r\n]*)"
        r"|^ {0,3}\[[^\]\r\n]+\]:([^\r\n]*)"
        r"|\b(?:href|src|data)\s*=\s*([^>\r\n]+)",
        decoded,
    )
    return any(
        re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", value)
        for alternatives in destinations
        for value in alternatives
        if value
        for name in incoming_names
    )


def _path_conflicts(existing, incoming):
    before = {_key(path) for path in existing}
    after = {_key(path) for path in incoming}

    before_dirs = _directory_spellings(existing)
    after_dirs = _directory_spellings(incoming)
    return (
        len(after) != len(incoming)
        or bool(after & before)
        or bool(after.intersection(before_dirs))
        or bool((before | after).intersection(after_dirs))
        or any(
            len(spellings | before_dirs.get(key, set())) != 1
            for key, spellings in after_dirs.items()
        )
    )


def _directory_spellings(paths):
    result = defaultdict(set)
    for path in paths:
        parts = path.split("/")
        for i in range(1, len(parts)):
            directory = "/".join(parts[:i])
            result[_key(directory)].add(directory)
    return result


def inspect_import_links(
    existing,
    incoming,
    *,
    reserved_paths=(),
    gap_paths=(),
    connections=(),
    continuation=False,
    unchanged_generated=(),
):
    """Produce before/after evidence for unmodified authored links."""
    addition = {path: value for path, value in incoming.items() if path not in existing}
    if _path_conflicts(existing, addition if continuation else incoming):
        return ImportLinkImpact(blockers=("import_target_occupied",))
    before = _catalog(existing, reserved_paths, gap_paths)
    after = _catalog(existing | incoming, reserved_paths, gap_paths)
    documents = _authored_documents(
        {
            path: data
            for path, data in existing.items()
            if path not in unchanged_generated
        },
        before,
    )
    approved = frozenset(connections)
    observations = tuple(
        _observation(document, occurrence, after, incoming, approved, continuation)
        for document in documents
        for occurrence in document.occurrences
    )
    warnings, blockers, consumed = set(), set(), set()
    for row in observations:
        if row.kind == "approved_connection":
            consumed.add(row.connection)
        elif row.kind in ("connection_required", "changed_meaning"):
            blockers.add(row.kind)
        elif row.kind == "preexisting_warning":
            warnings.add(row.document_path)
    property_values = base_note_property_values(
        existing,
        {
            name
            for document in documents
            if isinstance(document, BaseDocument)
            for name in document.uncertain_properties
        },
    )
    for document in documents:
        if document.status == "unsupported":
            if _may_reach_import(document, incoming, property_values):
                blockers.add("affected_link_uncertain")
            else:
                warnings.add(document.source_path)
    if consumed != approved or len(approved) != len(connections):
        blockers.add("import_connection_stale")
    return ImportLinkImpact(
        observations=observations,
        warnings=tuple(sorted(warnings)),
        blockers=tuple(sorted(blockers)),
    )


def reserved_import_names(
    existing, location, *, reserved_paths=(), connections=(), preview_connections=False
):
    """Reserve physical names and inbound unresolved queries before rendering."""
    catalog = _catalog(existing, reserved_paths, ())
    names = {import_name_key(path) for path in (*existing, *reserved_paths)}
    approved = {(choice.document_path, choice.occurrence_id) for choice in connections}
    if preview_connections:
        return tuple(sorted(names))
    scope = _key(location)
    for document in _authored_documents(existing, catalog):
        for occurrence in document.occurrences:
            query = occurrence.query
            if (
                query is not None
                and occurrence.meaning.status
                in ("missing", "intentionally_uncreated", "ambiguous", "unknown")
                and _query_can_reach_scope(query, scope)
                and (document.source_path, occurrence.occurrence_id) not in approved
            ):
                names.add(import_name_key(query.value))
    return tuple(sorted(names))


def _query_can_reach_scope(query, scope):
    directory = _key(query.value).rpartition("/")[0]
    if directory == scope or directory.startswith(scope + "/"):
        return True
    if query.mode != "shortened":
        return False
    if not directory:
        return True
    scope_parts = scope.split("/")
    directories = ("attachments", "categories", "notes", "templates")
    return any(
        directory == suffix or directory.startswith(suffix + "/")
        for suffix in (
            *directories,
            *("/".join(scope_parts[i:]) for i in range(len(scope_parts))),
        )
    )
