"""Verified attachment roles, physical accounting and streamed byte inventory."""

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

from brz2obsidian.contracts import AccountingEntry, Asset, Document, OriginalEvidence

from .notes import bind_note_references, trace_note_references

SPECIAL_FLAGS = (
    "IsBrainAttachment",
    "IsBrainIcon",
    "IsWallpaper",
    "IsAiScriptsFile",
    "IsKeyboardShortcutsFile",
    "IsToolbarConfigFile",
)


def normalize_attachments(archive, records, meta, thoughts, refuse, uuid):
    assets, documents, members, evidence, accounting = [], [], {}, [], []
    states = meta["AttachmentFileStates"]
    names = set(archive.namelist())
    for key, state in states.items():
        uuid(key)
        if type(state) is not int or state not in {1, 2}:
            refuse("invalid_source", "Invalid attachment file state", (key,))
    for index, record in enumerate(records):
        asset_id, owner = uuid(record["Id"]), uuid(record["SourceId"])
        if (
            any(a.asset_id == asset_id for a in assets)
            or owner not in thoughts
            or record.get("BrainId") != meta["BrainId"]
        ):
            refuse(
                "invalid_source",
                "Attachment identity or ownership is invalid",
                (asset_id,),
            )
        for field in ("SourceType", "Type", "NoteType", "DataLength"):
            if type(record.get(field)) is not int:
                refuse(
                    "invalid_source",
                    "Attachment scalar fields must be integers",
                    (asset_id,),
                )
        if record["DataLength"] < 0:
            refuse(
                "invalid_source", "Attachment length must be nonnegative", (asset_id,)
            )
        for flag in ("IsIcon",) + SPECIAL_FLAGS:
            if flag in record and type(record[flag]) is not bool:
                refuse(
                    "invalid_source",
                    "Attachment role flags must be booleans",
                    (asset_id,),
                )
        if any(record.get(flag, False) for flag in SPECIAL_FLAGS):
            refuse(
                "unsupported_feature",
                "Special attachment role is not supported",
                (asset_id,),
            )
        kind, note_type = record["Type"], record["NoteType"]
        if record["SourceType"] != 2 or (kind, note_type) not in {
            (1, 4),
            (1, 0),
            (3, 0),
            (5, 0),
            (8, 0),
            (12, 0),
        }:
            refuse(
                "unsupported_feature",
                "Attachment role is outside reviewed coverage",
                (asset_id,),
            )
        if record.get("IsIcon", False) != (kind == 5):
            refuse(
                "unsupported_feature",
                "Attachment icon flag disagrees with its role",
                (asset_id,),
            )
        location = record["Location"]
        if (
            type(location) is not str
            or not location
            or ("Name" in record and type(record["Name"]) is not str)
        ):
            refuse("invalid_source", "Attachment location/name is invalid", (asset_id,))
        pointer = f"attachments.json:{index}"
        common = {
            "asset_id": asset_id,
            "owner": owner,
            "naming_seed": asset_id.replace("-", ""),
            "original_name": location,
            "display_name": record.get("Name"),
            "evidence": (pointer,),
        }
        if kind in {3, 8}:
            if asset_id in states:
                refuse(
                    "invalid_source",
                    "External reference must not have a local file state",
                    (asset_id,),
                )
            uri = location
            if kind == 3:
                if (
                    urlsplit(uri).scheme.casefold() not in {"http", "https"}
                    or not urlsplit(uri).netloc
                ):
                    refuse(
                        "unsupported_feature",
                        "External URL scheme is unsupported",
                        (asset_id,),
                    )
            else:
                directory = PureWindowsPath(location)
                if not directory.is_absolute():
                    refuse(
                        "unsupported_feature",
                        "External directory must be an absolute Windows path",
                        (asset_id,),
                    )
                uri = Path(location).as_uri()
            if any(ord(c) < 32 or c in "<>" for c in uri):
                refuse(
                    "invalid_source",
                    "External reference contains unsafe link characters",
                    (asset_id,),
                )
            assets.append(
                Asset(
                    **common,
                    role="url" if kind == 3 else "directory",
                    availability="external",
                    external_uri=uri,
                )
            )
            continue
        local = PurePosixPath(location)
        if (
            local.is_absolute()
            or any(p in {".", ".."} for p in location.split("/"))
            or "\\" in location
            or ":" in location
            or str(local) != location
        ):
            refuse(
                "invalid_source",
                "Unsafe or ambiguous local attachment location",
                (asset_id,),
            )
        prefix = ".data/" if kind == 5 else (".data/md-images/" if kind == 12 else "")
        member = owner + "/" + prefix + location
        if states.get(asset_id) != 1 or member not in names:
            refuse(
                "missing_required_payload",
                "Required attachment bytes are absent or not present-state",
                (asset_id,),
            )
        if member in members.values():
            refuse(
                "invalid_source",
                "Multiple attachments assign the same physical payload",
                (asset_id,),
            )
        length, digest = 0, hashlib.sha256()
        with archive.open(member) as stream:
            while chunk := stream.read(1024 * 1024):
                length += len(chunk)
                digest.update(chunk)
        if length != record["DataLength"]:
            refuse(
                "invalid_source",
                "Attachment metadata length differs from actual bytes",
                (asset_id,),
            )
        role = "icon" if kind == 5 else ("image" if kind == 12 else "file")
        if kind == 1 and (note_type == 4 or location == "Notes.md"):
            text = archive.read(member).decode("utf-8-sig")
            if note_type == 0 and text:
                refuse(
                    "unsupported_feature",
                    "Nonempty Notes.md placeholder has ambiguous meaning",
                    (asset_id,),
                )
            if any(d.owner == owner for d in documents):
                refuse(
                    "invalid_source",
                    "Multiple thought notes have ambiguous ownership",
                    (asset_id,),
                )
            references = trace_note_references(text)
            documents.append(
                Document(
                    key=asset_id,
                    owner=owner,
                    text=text,
                    text_digest=hashlib.sha256(text.encode()).hexdigest(),
                    original_asset_id=asset_id,
                    references=references,
                    evidence=(pointer,),
                )
            )
            role = "note_original"
        assets.append(
            Asset(
                **common,
                role=role,
                availability="present",
                actual_length=length,
                actual_sha256=digest.hexdigest(),
            )
        )
        members[asset_id] = member
        payload_pointer = "payload:" + member
        evidence.append(
            OriginalEvidence(
                key=payload_pointer,
                kind="payload",
                original_json=json.dumps(
                    {"member": member, "length": length, "sha256": digest.hexdigest()}
                ),
            )
        )
        accounting.append(
            AccountingEntry(
                identity=payload_pointer,
                disposition="normalized",
                references=(asset_id,),
            )
        )
    if set(states) - {a.asset_id for a in assets}:
        refuse("invalid_source", "File states refer to an absent attachment")
    documents = [bind_note_references(d, assets, thoughts) for d in documents]
    accounting.extend(
        AccountingEntry(
            identity=f"reference:{document.key}:{index}",
            disposition="normalized",
            references=(document.key, reference.target),
        )
        for document in documents
        for index, reference in enumerate(document.references)
    )
    return assets, documents, members, evidence, accounting
