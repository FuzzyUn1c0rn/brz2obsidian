"""Establish trusted ownership, then expose only included source records."""

import base64
import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import PurePosixPath
from uuid import UUID

_UUID_TEXT = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


def contains_omitted_identity(text, tokens):
    """Recognize proven identity spellings without changing retained source text."""
    if not tokens:
        return False
    if any(token in text for token in tokens):
        return True
    # One URL-encoding layer and one serialized Unicode-escape layer are enough
    # for these reviewed representations. This is inspection, never rewriting
    # or repeated arbitrary decoding. Compact base64 identities stay case exact.
    decoded = re.sub(r"%([0-9a-fA-F]{2})", lambda match: chr(int(match[1], 16)), text)
    decoded = re.sub(
        r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match[1], 16)), decoded
    )
    return any(token in decoded for token in tokens) or any(
        match[0].lower() in tokens for match in _UUID_TEXT.finditer(decoded)
    )


def _positive_absent_txt_declaration(record, states):
    """Recognize only the reviewed positive TXT role before inclusion filtering."""
    return (
        all(
            type(record.get(field)) is int and record[field] == expected
            for field, expected in (("SourceType", 2), ("Type", 15), ("NoteType", 0))
        )
        and type(record.get("DataLength")) is int
        and record["DataLength"] > 0
        and PurePosixPath(record["Location"]).suffix.casefold() == ".txt"
        and type(states.get(record["Id"])) is int
        and states[record["Id"]] == 2
        and ("Name" not in record or type(record["Name"]) is str)
        and all(
            type(value) is bool and not value
            for field, value in record.items()
            if field.startswith("Is")
        )
        and all(
            record.get(field) is None or record.get(field) == ""
            for field in ("ThoughtTypeId", "LinkTypeId", "TypeId")
        )
    )


def scope_records(records, physical_members, refuse, uuid):
    """Scope records only after globally validating identities and declarations.

    The caller supplies the ZIP namespace after its path, uniqueness and CRC
    checks. Repeated absent TXT declarations claim no physical bytes; each
    included row still passes the normalizer's complete reviewed TXT/PDF rule.
    """
    brain = uuid(records["meta.json"][0]["BrainId"])
    identities = set()
    thoughts = {}
    for name in ("thoughts.json", "links.json", "attachments.json"):
        for record in records[name]:
            key = uuid(record.get("Id"))
            if key in identities or record.get("BrainId") != brain:
                refuse(
                    "invalid_source", "Invalid live identity or collection ownership"
                )
            identities.add(key)
            if name == "thoughts.json":
                thoughts[key] = record
    setting_ids = set()
    for record in records["settings.json"]:
        key = uuid(record.get("Id"))
        if key in setting_ids or ("BrainId" in record and record["BrainId"] != brain):
            refuse("invalid_source", "Invalid setting identity or collection ownership")
        setting_ids.add(key)
    excluded = set()
    for key, record in thoughts.items():
        marker = record.get("ForgottenDateTime")
        if marker is None or marker == "":
            continue
        try:
            if type(marker) is not str or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?",
                marker,
            ):
                raise ValueError
            datetime.fromisoformat(marker)
        except ValueError:
            refuse("invalid_source", "Invalid forgotten scope timestamp")
        excluded.add(key)
    omitted = set(excluded)
    if any(record.get("Id") in identities for record in records["tombstones.json"]):
        refuse("invalid_source", "A live identity also occurs in deleted history")
    dropped_members = set()
    claimed_members = {}
    for record in records["attachments.json"]:
        owner = uuid(record.get("SourceId"))
        if owner not in thoughts:
            refuse("invalid_source", "Invalid attachment ownership")
        location = record.get("Location")
        if type(location) is not str or not location:
            refuse("invalid_source", "Invalid attachment location")
        if record.get("Type") not in {3, 8}:
            path = PurePosixPath(location)
            if (
                path.is_absolute()
                or str(path) != location
                or any(p in {".", ".."} for p in location.split("/"))
                or "\\" in location
                or ":" in location
            ):
                refuse(
                    "invalid_source", "Unsafe or ambiguous local attachment location"
                )
            prefix = (
                ".data/"
                if record.get("Type") == 5
                else (".data/md-images/" if record.get("Type") == 12 else "")
            )
            member = owner + "/" + prefix + location
            claimed_members.setdefault(member, []).append(record)
            if owner in excluded:
                dropped_members.add(member)
        if owner in excluded:
            omitted.add(record["Id"])
    for record in records["links.json"]:
        a, b = uuid(record.get("ThoughtIdA")), uuid(record.get("ThoughtIdB"))
        if a not in thoughts or b not in thoughts:
            refuse("invalid_reference", "Relationship has a nonlive endpoint")
        if a in excluded or b in excluded:
            omitted.add(record["Id"])
    for record in thoughts.values():
        if record.get("TypeId"):
            provider = uuid(record["TypeId"])
            if provider not in thoughts:
                refuse("invalid_reference", "Classification provider is not live")
    states = records["meta.json"][0].get("AttachmentFileStates")
    if type(states) is not dict:
        refuse("invalid_source", "AttachmentFileStates must be an object")
    asset_ids = {r["Id"] for r in records["attachments.json"]}
    if any(uuid(key) not in asset_ids for key in states):
        refuse("invalid_source", "File states refer to an absent attachment")
    for member, declarations in claimed_members.items():
        # Check the whole group, including omitted owners, so row order or
        # inclusion cannot hide a competing role or a real payload claim.
        if len(declarations) > 1 and (
            member in physical_members
            or not all(
                _positive_absent_txt_declaration(record, states)
                for record in declarations
            )
        ):
            refuse("invalid_source", "Multiple declarations assign one payload")
    if not excluded:
        return records, excluded, dropped_members, ()
    associations = {
        "SourceId",
        "ThoughtId",
        "AttachmentId",
        "ObjectId",
        "ItemId",
        "LinkId",
        "TargetId",
    }

    def decoded(value):
        if not isinstance(value, str) or value.lstrip()[:1] not in {"{", "[", '"'}:
            return None

        def pairs(entries):
            # Inspection must see every ownership declaration, including duplicate
            # keys in an otherwise opaque serialized string. Never rewrite it.
            result = {}
            for key, entry in entries:
                result[key] = [result[key], entry] if key in result else entry
            return result

        try:
            return json.loads(value, parse_float=Decimal, object_pairs_hook=pairs)
        except ValueError:
            return None

    def identifies_omitted(value):
        if isinstance(value, str):
            return (
                value in omitted
                or (
                    _UUID_TEXT.fullmatch(value) is not None and value.lower() in omitted
                )
                or identifies_omitted(decoded(value))
            )
        if isinstance(value, (list, tuple)):
            return any(identifies_omitted(entry) for entry in value)
        return False

    def associated(value):
        if isinstance(value, dict):
            return any(
                (field in associations and identifies_omitted(entry))
                or associated(entry)
                for field, entry in value.items()
            )
        if isinstance(value, (list, tuple)):
            return any(associated(entry) for entry in value)
        if isinstance(value, str):
            return associated(decoded(value))
        return False

    changed = True
    while changed:
        changed = False
        for collection in records.values():
            for record in collection:
                if record.get("Id") in omitted:
                    continue
                if associated(record) and type(record.get("Id")) is str:
                    omitted.add(record["Id"])
                    changed = True
    tokens = set(omitted)
    for key in omitted:
        try:
            canonical = UUID(key)
        except ValueError:
            continue
        tokens.add(base64.urlsafe_b64encode(canonical.bytes_le).decode().rstrip("="))

    def unsafe(value):
        if isinstance(value, str):
            return contains_omitted_identity(value, tokens) or unsafe(decoded(value))
        if isinstance(value, dict):
            return any(unsafe(k) or unsafe(v) for k, v in value.items())
        if isinstance(value, (list, tuple)):
            return any(unsafe(v) for v in value)
        return False

    scoped = {}
    for name, collection in records.items():
        if name in {"modificationlogs.json", "syncpoints.json", "tombstones.json"}:
            # History has no reviewed exhaustive live-subject ownership rule.
            scoped[name] = ()
            continue
        kept = []
        for record in collection:
            if record.get("Id") in omitted:
                continue
            if associated(record):
                continue
            clean = {}
            for field, value in record.items():
                if unsafe(field):
                    continue
                if field == "AttachmentFileStates":
                    clean[field] = {k: v for k, v in value.items() if k not in omitted}
                elif field == "TypeId" and value in excluded:
                    continue
                elif not unsafe(value):
                    clean[field] = value
            kept.append(clean)
        scoped[name] = tuple(kept)
    return scoped, excluded, dropped_members, tuple(tokens)


def records_json(collection, original_json):
    """Retain exact safe source numbers while omitting scoped fields/records."""
    originals = json.loads(original_json, parse_float=Decimal)
    remaining = iter(originals)
    retained = []
    for clean in collection:
        original = next(r for r in remaining if r.get("Id") == clean.get("Id"))
        record = {field: original[field] for field in clean}
        if "AttachmentFileStates" in record:
            record["AttachmentFileStates"] = {
                key: value
                for key, value in record["AttachmentFileStates"].items()
                if key in clean["AttachmentFileStates"]
            }
        retained.append(record)

    def encode(value):
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return (
                "{"
                + ",".join(json.dumps(k) + ":" + encode(v) for k, v in value.items())
                + "}"
            )
        if isinstance(value, list):
            return "[" + ",".join(encode(v) for v in value) + "]"
        return json.dumps(value, ensure_ascii=False)

    return encode(retained)
