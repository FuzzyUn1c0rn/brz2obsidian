"""Establish trusted ownership, then expose only included source records."""

import base64
import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import PurePosixPath
from uuid import UUID

from .relationships import relationship_problem

_UUID_TEXT = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


def contains_omitted_identity(text, tokens, *, diagnostic=False):
    """Recognize proven identity spellings without changing retained source text."""
    if not tokens:
        return False
    if any(token in text for token in tokens):
        return True
    # Retained-source screening keeps its reviewed single pass. Diagnostics can
    # reveal an arbitrary invalid scalar, so inspect mixed nested escapes for at
    # most eight shrinking rounds, then suppress unresolved escaped context.
    # Neither path rewrites source text or authorizes inclusion/validity.
    decoded = text
    for _ in range(8 if diagnostic else 1):
        previous = decoded
        decoded = re.sub(
            r"%([0-9a-fA-F]{2})", lambda match: chr(int(match[1], 16)), decoded
        )
        decoded = re.sub(
            r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match[1], 16)), decoded
        )
        if any(token in decoded for token in tokens) or any(
            match[0].lower() in tokens for match in _UUID_TEXT.finditer(decoded)
        ):
            return True
        if decoded == previous:
            return False
    return diagnostic and bool(re.search(r"%[0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4}", decoded))


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
    private_ids = {
        r.get("Id")
        for r in records["thoughts.json"]
        if r.get("ForgottenDateTime") and type(r.get("Id")) is str
    }

    omitted = set(private_ids)
    for record in records["links.json"]:
        if (
            record.get("ThoughtIdA") in private_ids
            or record.get("ThoughtIdB") in private_ids
        ) and type(record.get("Id")) is str:
            omitted.add(record["Id"])

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

    def identifies_omitted(value, subjects=None):
        subjects = omitted if subjects is None else subjects
        if isinstance(value, str):
            return (
                value in subjects
                or (
                    _UUID_TEXT.fullmatch(value) is not None
                    and value.lower() in subjects
                )
                or identifies_omitted(decoded(value), subjects)
            )
        if isinstance(value, (list, tuple)):
            return any(identifies_omitted(entry, subjects) for entry in value)
        return False

    def associated(value, subjects=None):
        subjects = omitted if subjects is None else subjects
        if isinstance(value, dict):
            return any(
                (field in associations and identifies_omitted(entry, subjects))
                or associated(entry, subjects)
                for field, entry in value.items()
            )
        if isinstance(value, (list, tuple)):
            return any(associated(entry, subjects) for entry in value)
        if isinstance(value, str):
            return associated(decoded(value), subjects)
        return False

    # Provisional omission is used only to suppress diagnostics before global
    # validation. The validated inclusion/omission algorithm below is unchanged.
    diagnostic_omitted = set(omitted)
    while True:
        previous = set(diagnostic_omitted)
        for collection in records.values():
            for record in collection:
                if (
                    associated(record, diagnostic_omitted)
                    and type(record.get("Id")) is str
                ):
                    diagnostic_omitted.add(record["Id"])
        if diagnostic_omitted == previous:
            break

    diagnostic_tokens = set(diagnostic_omitted)
    for key in diagnostic_omitted:
        try:
            canonical = UUID(key)
        except ValueError:
            continue
        diagnostic_tokens.add(
            base64.urlsafe_b64encode(canonical.bytes_le).decode().rstrip("=")
        )

    def diagnostic_unsafe(value):
        if isinstance(value, str):
            return contains_omitted_identity(
                value, diagnostic_tokens, diagnostic=True
            ) or diagnostic_unsafe(decoded(value))
        if isinstance(value, dict):
            return any(
                diagnostic_unsafe(k) or diagnostic_unsafe(v) for k, v in value.items()
            )
        if isinstance(value, (list, tuple)):
            return any(diagnostic_unsafe(v) for v in value)
        return False

    def relation_problem(record, index, code, message):
        relationship_problem(
            record,
            index,
            refuse,
            uuid,
            code,
            message,
            private=diagnostic_unsafe(record) or associated(record, diagnostic_omitted),
        )

    def extend_omitted():
        if not omitted:
            return
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

    # This conservative closure controls disclosure only; all identities,
    # ownership and forgotten markers must still pass validation below.
    extend_omitted()
    private_ids = omitted

    def attachment_problem(record, index, message):
        # Ownership is not yet fully trusted. Never expose a record that names
        # a forgotten subject; only canonical identifiers enter diagnostics.
        if contains_omitted_identity(json.dumps(record), private_ids):
            refuse("invalid_source", message)
        subjects = []
        for field in ("SourceId", "Id"):
            try:
                subjects.append(uuid(record.get(field)))
            except ValueError, TypeError, AttributeError:
                pass
        refuse(
            "invalid_source",
            message,
            tuple(dict.fromkeys(subjects)),
            evidence=(f"attachments.json:{index}",),
            guidance=(
                "Review the external-file attachment identity and ownership in the source records; external targets are not accessed."
                if record.get("Type") == 2
                else "Review the attachment identity and ownership in the source records."
            ),
        )

    for name in ("thoughts.json", "links.json", "attachments.json"):
        for index, record in enumerate(records[name]):
            try:
                key = uuid(record.get("Id"))
            except ValueError, TypeError, AttributeError:
                if name == "attachments.json":
                    attachment_problem(record, index, "Invalid attachment identity")
                if name == "links.json":
                    relation_problem(
                        record, index, "invalid_source", "Invalid relationship identity"
                    )
                raise
            if key in identities or record.get("BrainId") != brain:
                if name == "attachments.json":
                    attachment_problem(
                        record,
                        index,
                        "Invalid attachment identity or collection ownership",
                    )
                if name == "links.json":
                    relation_problem(
                        record,
                        index,
                        "invalid_source",
                        "Invalid relationship identity or collection ownership",
                    )
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
    for index, record in enumerate(records["attachments.json"]):
        try:
            owner = uuid(record.get("SourceId"))
        except ValueError, TypeError, AttributeError:
            attachment_problem(record, index, "Invalid attachment ownership")
        if owner not in thoughts:
            attachment_problem(record, index, "Invalid attachment ownership")
        location = record.get("Location")
        if type(location) is not str or not location:
            attachment_problem(record, index, "Invalid attachment location")
        if record.get("Type") not in {2, 3, 8}:
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
    for index, record in enumerate(records["links.json"]):
        try:
            a, b = uuid(record.get("ThoughtIdA")), uuid(record.get("ThoughtIdB"))
        except ValueError, TypeError, AttributeError:
            relation_problem(
                record,
                index,
                "invalid_source",
                "Invalid relationship endpoint identity",
            )
        if a not in thoughts or b not in thoughts:
            relation_problem(
                record,
                index,
                "invalid_reference",
                "Relationship has a nonlive endpoint",
            )
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
            if any(
                contains_omitted_identity(json.dumps(r), private_ids)
                for r in declarations
            ):
                refuse("invalid_source", "Multiple declarations assign one payload")
            owner = declarations[0]["SourceId"]
            related = [
                r
                for r in records["attachments.json"]
                if r["SourceId"] == owner
                and (
                    r in declarations
                    or (
                        type(r.get("SourceType")) is int
                        and r["SourceType"] == 2
                        and type(r.get("Type")) is int
                        and r["Type"] == 1
                        and type(r.get("NoteType")) is int
                        and (
                            r["NoteType"] == 4
                            or (r["NoteType"] == 0 and r.get("Location") == "Notes.md")
                        )
                    )
                )
                and not contains_omitted_identity(json.dumps(r), private_ids)
            ]
            refuse(
                "invalid_source",
                "Multiple declarations assign one payload",
                (owner, *(r["Id"] for r in related)),
                evidence=tuple(
                    f"attachments.json:{i}"
                    for i, r in enumerate(records["attachments.json"])
                    if r in related
                ),
                guidance="Review the affected note references and attachment declarations; each archived image payload must have one unambiguous identity.",
            )
    if not excluded:
        return records, excluded, dropped_members, ()
    extend_omitted()
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
