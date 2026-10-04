"""Verified attachment roles, physical accounting and streamed byte inventory."""

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

from brz2obsidian.contracts import (
    AccountingEntry,
    Asset,
    Document,
    OriginalEvidence,
    SourceFinding,
)

from .findings import ABSENT_TXT_RULE, ICON_LENGTH_RULE, ZERO_LENGTH_ABSENT_TXT_RULE
from .notes import bind_note_references, trace_note_references
from .semantics import validate_semantic_fields

SPECIAL_FLAGS = (
    "IsBrainAttachment",
    "IsBrainIcon",
    "IsWallpaper",
    "IsAiScriptsFile",
    "IsKeyboardShortcutsFile",
    "IsToolbarConfigFile",
)


def normalize_attachments(archive, records, meta, thoughts, refuse, uuid):
    assets, documents, members, evidence, accounting, findings = [], [], {}, [], [], []
    absent_records = []
    asset_records = {}
    states = meta["AttachmentFileStates"]
    names = set(archive.namelist())
    for key, state in states.items():
        uuid(key)
        if type(state) is not int or state not in {1, 2}:
            refuse("invalid_source", "Invalid attachment file state", (key,))
    for index, record in enumerate(records):
        asset_id, owner = uuid(record["Id"]), uuid(record["SourceId"])
        validate_semantic_fields(record, refuse, ("IsIcon",) + SPECIAL_FLAGS)
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
            (15, 0),
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
        asset_records[asset_id] = record
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
        if kind == 15:
            if (
                local.suffix.casefold() != ".txt"
                or states.get(asset_id) != 2
                or member in names
            ):
                refuse(
                    "unsupported_feature",
                    "Type 15 attachment does not match the reviewed absent TXT rule",
                    (asset_id,),
                )
            assets.append(Asset(**common, role="file", availability="absent"))
            absent_records.append(
                (asset_id, owner, location, record["DataLength"], pointer)
            )
            continue
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
            if kind != 5:
                refuse(
                    "invalid_source",
                    "Attachment metadata length differs from actual bytes",
                    (asset_id,),
                )
            findings.append(
                SourceFinding(
                    kind="approved_metadata_discrepancy",
                    rule_id=ICON_LENGTH_RULE,
                    affected=(asset_id,),
                    evidence=(pointer, "payload:" + member),
                    observed_json=json.dumps(
                        {
                            "member": member,
                            "declared_length": record["DataLength"],
                            "actual_length": length,
                            "actual_sha256": digest.hexdigest(),
                            "crc_valid": True,
                        }
                    ),
                )
            )
        role = "icon" if kind == 5 else ("image" if kind == 12 else "file")
        if kind == 1 and (note_type == 4 or location == "Notes.md"):
            text = archive.read(member).decode("utf-8-sig")
            if note_type == 0 and text and thoughts[owner]["Kind"] != 1:
                refuse(
                    "unsupported_feature",
                    "Nonempty NoteType-0 Notes.md requires an ordinary thought owner",
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
    for asset_id, owner, location, declared, pointer in absent_records:
        if declared == 0:
            stem = PurePosixPath(location).stem
            associated = tuple(
                a
                for a in assets
                if a.asset_id == stem
                and a.owner == owner
                and a.availability == "present"
                and a.role == "file"
                and PurePosixPath(a.original_name).suffix.casefold() == ".pdf"
                and asset_records[a.asset_id]["Type"] == 1
                and asset_records[a.asset_id]["NoteType"] == 0
            )
            if len(associated) != 1:
                refuse(
                    "missing_required_payload",
                    "Zero-length absent TXT does not identify one intact same-owner PDF attachment",
                    (asset_id,),
                )
            pdf = associated[0]
            member = members[pdf.asset_id]
            findings.append(
                SourceFinding(
                    kind="known_absent_payload",
                    rule_id=ZERO_LENGTH_ABSENT_TXT_RULE,
                    affected=(asset_id,),
                    evidence=(pointer, "meta.json")
                    + pdf.evidence
                    + ("payload:" + member,),
                    observed_json=json.dumps(
                        {
                            "owner": owner,
                            "filename": location,
                            "declared_length": declared,
                            "state": 2,
                            "present": False,
                            "filename_stem": stem,
                            "pdf_attachment_id": pdf.asset_id,
                            "pdf": {
                                "owner": pdf.owner,
                                "filename": pdf.original_name,
                                "source_type": 2,
                                "type": 1,
                                "note_type": 0,
                                "state": states[pdf.asset_id],
                                "member": member,
                                "declared_length": asset_records[pdf.asset_id][
                                    "DataLength"
                                ],
                                "actual_length": pdf.actual_length,
                                "actual_sha256": pdf.actual_sha256,
                                "crc_valid": True,
                            },
                        }
                    ),
                )
            )
            continue
        pdfs = tuple(
            sorted(
                a.asset_id
                for a in assets
                if a.owner == owner
                and a.availability == "present"
                and a.role == "file"
                and PurePosixPath(a.original_name).suffix.casefold() == ".pdf"
            )
        )
        if not pdfs:
            refuse(
                "missing_required_payload",
                "Absent TXT lacks an intact archived PDF under the same owner",
                (asset_id,),
            )
        findings.append(
            SourceFinding(
                kind="known_absent_payload",
                rule_id=ABSENT_TXT_RULE,
                affected=(asset_id,),
                evidence=(pointer, "meta.json")
                + tuple(p for a in assets if a.asset_id in pdfs for p in a.evidence),
                observed_json=json.dumps(
                    {
                        "owner": owner,
                        "filename": location,
                        "declared_length": declared,
                        "state": 2,
                        "present": False,
                        "intact_same_owner_pdfs": pdfs,
                    }
                ),
            )
        )
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
    return assets, documents, members, evidence, accounting, findings
