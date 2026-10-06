"""Independent retention interpretation of original record streams.

Original ordinals are recorded separately. Public evidence pointers address the
retained safe tables, not physical original JSON-line positions.
"""

import base64
import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import PurePosixPath
from urllib.parse import unquote
from uuid import UUID

from .facts import identities, member


class ScopedRecords(dict):
    """Raw-derived tables plus private audit facts, never emitted output facts."""


def dump_json(value):
    """Exact JSON numbers, without a float conversion in audit tooling."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(json.dumps(k) + ":" + dump_json(v) for k, v in value.items())
            + "}"
        )
    if isinstance(value, list):
        return "[" + ",".join(map(dump_json, value)) + "]"
    return json.dumps(value, ensure_ascii=False)


def expanded(value):
    if type(value) is str:
        try:
            # Preserve all duplicate declarations inside opaque serialized JSON.
            value = json.loads(
                value, parse_float=Decimal, object_pairs_hook=lambda p: p
            )
        except ValueError:
            return
        if type(value) is str:
            yield None, value
            yield from expanded(value)
            return
    if isinstance(value, dict):
        yield from value.items()
        for child in value.values():
            yield from expanded(child)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, tuple) and len(child) == 2:
                yield child
                yield from expanded(child[1])
            else:
                yield from expanded(child)


def scope(raw, archive):
    thoughts = identities(raw["thoughts.json"], "item")
    attachments = identities(raw["attachments.json"], "attachment")
    links = identities(raw["links.json"], "relationship")
    live = list(thoughts) + list(attachments) + list(links)
    assert len(set(live)) == len(live), "raw cross-table live identities"
    brain = raw["meta.json"][0]["BrainId"]
    assert str(UUID(brain)) == brain, "raw collection identity"
    for collection in (thoughts, attachments, links):
        for key, row in collection.items():
            assert str(UUID(key)) == key and row["BrainId"] == brain, "raw ownership"
    settings = {r["Id"]: r for r in raw["settings.json"]}
    assert len(settings) == len(raw["settings.json"]), "raw setting duplicate identity"
    assert all(
        str(UUID(key)) == key and row.get("BrainId", brain) == brain
        for key, row in settings.items()
    ), "raw setting identity/ownership"
    assert not any(r.get("Id") in live for r in raw["tombstones.json"]), (
        "raw live/deleted identity conflict"
    )
    excluded = set()
    states = raw["meta.json"][0]["AttachmentFileStates"]
    assert type(states) is dict and states.keys() <= attachments.keys(), (
        "raw state-map ownership"
    )
    assert all(type(v) is int and v in {1, 2, 3} for v in states.values()), (
        "raw file-state scalars"
    )
    for key, row in thoughts.items():
        if row.get("TypeId"):
            assert row["TypeId"] in thoughts, "raw live provider"
        marker = row.get("ForgottenDateTime")
        if marker in (None, ""):
            continue
        assert type(marker) is str and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?",
            marker,
        ), "raw forgotten timestamp"
        datetime.fromisoformat(marker)
        excluded.add(key)
    omitted = set(excluded)
    members = set()
    declarations = {}
    dropped = set()
    for key, row in attachments.items():
        assert row["SourceId"] in thoughts, "raw attachment owner"
        if row["Type"] not in {3, 8}:
            path = row["Location"]
            assert (
                str(PurePosixPath(path)) == path
                and not PurePosixPath(path).is_absolute()
                and not set(path.split("/")) & {".", "..", ""}
                and "\\" not in path
                and ":" not in path
            ), "raw safe unique path"
            name = member(row)
            declarations.setdefault(name, []).append(row)
            members.add(name)
            if row["SourceId"] in excluded:
                dropped.add(name)
        if row["SourceId"] in excluded:
            omitted.add(key)
    for name, rows in declarations.items():
        if len(rows) == 1:
            continue
        assert name not in archive.namelist() and all(
            all(
                type(row[field]) is int and row[field] == value
                for field, value in (("SourceType", 2), ("Type", 15), ("NoteType", 0))
            )
            and type(row["DataLength"]) is int
            and row["DataLength"] > 0
            and type(row.get("Name", "")) is str
            and states.get(row["Id"]) == 2
            and PurePosixPath(row["Location"]).suffix.casefold() == ".txt"
            and all(
                value is False for field, value in row.items() if field.startswith("Is")
            )
            and all(
                row.get(field) is None or type(row[field]) is str and row[field] == ""
                for field in ("ThoughtTypeId", "LinkTypeId", "TypeId")
            )
            for row in rows
        ), "raw unique payload declaration"
    for key, row in links.items():
        endpoints = {row["ThoughtIdA"], row["ThoughtIdB"]}
        assert endpoints <= thoughts.keys(), "raw live endpoints"
        if endpoints & excluded:
            omitted.add(key)
    associations = {
        "SourceId",
        "ThoughtId",
        "AttachmentId",
        "ObjectId",
        "ItemId",
        "LinkId",
        "TargetId",
    }

    def associated_identity(value):
        if type(value) is str:
            if value in omitted or (
                re.fullmatch(
                    r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value
                )
                and value.lower() in omitted
            ):
                return True
            try:
                return associated_identity(json.loads(value))
            except ValueError:
                return False
        return isinstance(value, list) and any(map(associated_identity, value))

    def owned(row):
        return any(
            field in associations and associated_identity(value)
            for field, value in expanded(row)
        )

    if excluded:
        while True:
            more = {
                row["Id"]
                for rows in raw.values()
                for row in rows
                if type(row.get("Id")) is str and owned(row)
            } - omitted
            if not more:
                break
            omitted |= more
    tokens = set(omitted)
    canonical_tokens = set()
    for key in omitted:
        try:
            canonical_tokens.add(str(UUID(key)))
            tokens.add(
                base64.urlsafe_b64encode(UUID(key).bytes_le).decode().rstrip("=")
            )
        except ValueError:
            pass

    def unsafe(value):
        if type(value) is str:
            # Interpret only common percent and ASCII JSON-Unicode spellings.
            # Canonical UUID hex is case insensitive; compact base64 is not.
            decoded = unquote(value)
            decoded = re.sub(
                r"\\u([0-9a-fA-F]{4})",
                lambda match: chr(int(match[1], 16)),
                decoded,
            )
            return (
                any(t in decoded for t in tokens)
                or any(t in decoded.casefold() for t in canonical_tokens)
                or any(unsafe(k) or unsafe(v) for k, v in expanded(value))
            )
        if isinstance(value, dict):
            return any(unsafe(k) or unsafe(v) for k, v in value.items())
        if isinstance(value, (list, tuple)):
            return any(unsafe(v) for v in value)
        return False

    result = ScopedRecords()
    result.original_ordinals = {}
    for name, rows in raw.items():
        result[name] = []
        for ordinal, row in enumerate(rows):
            if excluded and (
                name in {"modificationlogs.json", "syncpoints.json", "tombstones.json"}
                or row.get("Id") in omitted
                or owned(row)
            ):
                continue
            clean = {}
            for field, value in row.items():
                if field == "AttachmentFileStates":
                    clean[field] = {k: v for k, v in value.items() if k not in omitted}
                elif not unsafe(field) and not unsafe(value):
                    clean[field] = value
            result.original_ordinals[name, len(result[name])] = ordinal
            result[name].append(clean)
    result.excluded = excluded
    result.tokens = tokens
    result.unsafe = unsafe
    result.dropped_members = dropped
    result.documents = {}
    result.unsafe_originals = set()
    assert {
        n for n in archive.namelist() if n not in raw and not n.endswith("/")
    } <= members, "raw undeclared payload"
    return result
