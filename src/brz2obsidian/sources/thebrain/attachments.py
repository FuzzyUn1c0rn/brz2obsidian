"""Verified attachment roles, physical accounting and streamed byte inventory."""

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

from brz2obsidian.contracts import (
    AccountingEntry,
    Asset,
    GeneratedPresentation,
    OriginalEvidence,
    SourceFinding,
    SourceGap,
)

from .external_files import external_file_uri
from .findings import (
    ABSENT_NOTE_IMAGES_RULE,
    ABSENT_TXT_DECLARATION_RULE,
    ABSENT_TXT_RULE,
    ABSENT_TYPE_ICON_RULE,
    ABSENT_TYPE_NOTE_RULE,
    ICON_LENGTH_RULE,
    ZERO_LENGTH_ABSENT_TXT_RULE,
)
from .images import validate_note_image
from .note_preparation import bind_prepared_notes, prepare_note
from .semantics import validate_semantic_fields
from .videos import reviewed_video

SPECIAL_FLAGS = (
    "IsBrainAttachment",
    "IsBrainIcon",
    "IsWallpaper",
    "IsAiScriptsFile",
    "IsKeyboardShortcutsFile",
    "IsToolbarConfigFile",
)


def _attachment_refusal(source_refuse, owner, asset_id, pointer, external):
    def refuse(code, message, affected=()):
        source_refuse(
            code,
            message,
            tuple(dict.fromkeys((owner, asset_id, *affected))),
            evidence=(pointer, "meta.json"),
            guidance=(
                "Review this attachment's external-file role, original location and local payload declarations; external targets are not accessed."
                if external
                else "Review this attachment's declared role and owned archive payload."
            ),
        )

    return refuse


def _validate_attachment_role(record, asset_id, refuse):
    kind, note_type = record["Type"], record["NoteType"]
    if record["SourceType"] != 2 or (kind, note_type) not in {
        (2, 0),
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


def _local_member(location, kind, owner, asset_id, refuse):
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
    return local, member


class _AttachmentInventory:
    def __init__(self, archive, meta, thoughts, refuse, uuid, excluded, scope_tokens):
        self.archive = archive
        self.meta = meta
        self.thoughts = thoughts
        self.source_refuse = refuse
        self.uuid = uuid
        self.excluded = excluded
        self.scope_tokens = scope_tokens
        (
            self.assets,
            self.documents,
            self.members,
            self.evidence,
            self.accounting,
            self.findings,
        ) = [], [], {}, [], [], []
        self.absent_records = []
        self.absent_notes, self.gaps, self.presentations = [], [], []
        self.note_owners = set()
        self.asset_records = {}
        self.states = meta["AttachmentFileStates"]
        self.names = set(archive.namelist())

    def validate_file_states(self, records):
        state_owners = {
            record["Id"]: (index, record) for index, record in enumerate(records)
        }
        for key, state in self.states.items():
            self.uuid(key)
            if type(state) is not int or state not in {1, 2, 3}:
                if key in state_owners:
                    index, record = state_owners[key]
                    contextual_refuse = _attachment_refusal(
                        self.source_refuse,
                        record["SourceId"],
                        key,
                        f"attachments.json:{index}",
                        record.get("Type") == 2,
                    )
                    contextual_refuse("invalid_source", "Invalid attachment file state")
                self.source_refuse(
                    "invalid_source", "Invalid attachment file state", (key,)
                )

    def _validate_declaration(self, record, asset_id, owner, refuse):
        validate_semantic_fields(record, refuse, ("IsIcon",) + SPECIAL_FLAGS)
        if (
            any(a.asset_id == asset_id for a in self.assets)
            or owner not in self.thoughts
            or record.get("BrainId") != self.meta["BrainId"]
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
        _validate_attachment_role(record, asset_id, refuse)
        location = record["Location"]
        if (
            type(location) is not str
            or not location
            or ("Name" in record and type(record["Name"]) is not str)
        ):
            refuse("invalid_source", "Attachment location/name is invalid", (asset_id,))
        return location

    def _add_external(self, record, common, kind, location, asset_id, video, refuse):
        if asset_id in self.states:
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
        elif kind == 2:
            uri = external_file_uri(location, refuse)
            common["display_name"] = (
                record.get("Name") or PureWindowsPath(location).name
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
        self.assets.append(
            Asset(
                **common,
                role={2: "file", 3: "url", 8: "directory"}[kind],
                availability="external",
                external_uri=uri,
                video_presentation=video,
            )
        )

    def _add_absent_txt(
        self, record, common, location, local, member, pointer, asset_id, owner, refuse
    ):
        if (
            local.suffix.casefold() != ".txt"
            or self.states.get(asset_id) != 2
            or member in self.names
        ):
            refuse(
                "unsupported_feature",
                "Type 15 attachment does not match the reviewed absent TXT rule",
                (asset_id,),
            )
        self.assets.append(Asset(**common, role="file", availability="absent"))
        self.absent_records.append(
            (asset_id, owner, location, record["DataLength"], pointer)
        )

    def _add_absent_note(
        self,
        record,
        common,
        kind,
        note_type,
        location,
        member,
        pointer,
        asset_id,
        owner,
        refuse,
    ):
        if (
            note_type != 4
            or location != "Notes.md"
            or self.thoughts[owner]["Kind"] not in {1, 2}
        ):
            refuse(
                "unsupported_feature",
                "Absent note does not match a reviewed note rule",
                (asset_id,),
            )
        self.assets.append(Asset(**common, role="note_original", availability="absent"))
        if self.thoughts[owner]["Kind"] == 2:
            pointers = (pointer, "meta.json")
            self.findings.append(
                SourceFinding(
                    kind="known_absent_payload",
                    rule_id=ABSENT_TYPE_NOTE_RULE,
                    affected=(asset_id,),
                    evidence=pointers,
                    observed_json=json.dumps(
                        {
                            "owner": owner,
                            "filename": location,
                            "member": member,
                            "source_type": 2,
                            "type": kind,
                            "note_type": note_type,
                            "state": 3,
                            "declared_length": record["DataLength"],
                            "present": False,
                        }
                    ),
                )
            )
            self.gaps.append(
                SourceGap(
                    owner=owner,
                    asset_id=asset_id,
                    role="definition_note",
                    rule_id=ABSENT_TYPE_NOTE_RULE,
                    evidence=pointers,
                )
            )
            return
        self.absent_notes.append(
            (asset_id, owner, member, record["DataLength"], pointer)
        )

    def _add_absent_icon(
        self,
        record,
        common,
        kind,
        note_type,
        location,
        member,
        pointer,
        asset_id,
        owner,
        refuse,
    ):
        if self.thoughts[owner]["Kind"] != 2:
            refuse(
                "unsupported_feature",
                "Absent icon requires a type owner",
                (asset_id,),
            )
        pointers = (pointer, "meta.json")
        self.assets.append(Asset(**common, role="icon", availability="absent"))
        self.findings.append(
            SourceFinding(
                kind="known_absent_payload",
                rule_id=ABSENT_TYPE_ICON_RULE,
                affected=(asset_id,),
                evidence=pointers,
                observed_json=json.dumps(
                    {
                        "owner": owner,
                        "filename": location,
                        "member": member,
                        "source_type": 2,
                        "type": kind,
                        "note_type": note_type,
                        "is_icon": True,
                        "state": 3,
                        "declared_length": record["DataLength"],
                        "present": False,
                    }
                ),
            )
        )
        self.gaps.append(
            SourceGap(
                owner=owner,
                asset_id=asset_id,
                role="definition_icon",
                rule_id=ABSENT_TYPE_ICON_RULE,
                evidence=pointers,
            )
        )

    def _payload_facts(self, record, pointer, asset_id, kind, member, refuse):
        if self.states.get(asset_id) != 1 or member not in self.names:
            refuse(
                "missing_required_payload",
                "Required attachment bytes are absent or not present-state",
                (asset_id,),
            )
        if member in self.members.values():
            refuse(
                "invalid_source",
                "Multiple attachments assign the same physical payload",
                (asset_id,),
            )
        length, digest = 0, hashlib.sha256()
        with self.archive.open(member) as stream:
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
            self.findings.append(
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
        return length, digest

    def _add_present(
        self,
        record,
        common,
        kind,
        note_type,
        location,
        member,
        pointer,
        asset_id,
        owner,
        refuse,
    ):
        length, digest = self._payload_facts(
            record, pointer, asset_id, kind, member, refuse
        )
        role = "icon" if kind == 5 else ("image" if kind == 12 else "file")
        if kind == 1 and (note_type == 4 or location == "Notes.md"):
            text = self.archive.read(member).decode("utf-8-sig")
            if note_type == 0 and text and self.thoughts[owner]["Kind"] != 1:
                refuse(
                    "unsupported_feature",
                    "Nonempty NoteType-0 Notes.md requires an ordinary thought owner",
                    (asset_id,),
                )
            if any(d.owner == owner for d in self.documents):
                refuse(
                    "invalid_source",
                    "Multiple thought notes have ambiguous ownership",
                    (asset_id,),
                )

            document, note_findings = prepare_note(
                text,
                owner=owner,
                asset_id=asset_id,
                pointer=pointer,
                member=member,
                excluded=self.excluded,
                scope_tokens=self.scope_tokens,
                source_refuse=self.source_refuse,
                brain_id=self.meta["BrainId"],
                allow_qualified=True,
                allow_literal_tokens=True,
            )
            self.documents.append(document)
            self.findings.extend(note_findings)
            role = "note_original"
            if document.original_copy_omitted:
                self.members[asset_id] = member
                return
        self.assets.append(
            Asset(
                **common,
                role=role,
                availability="present",
                actual_length=length,
                actual_sha256=digest.hexdigest(),
            )
        )
        self.members[asset_id] = member
        payload_pointer = "payload:" + member
        self.evidence.append(
            OriginalEvidence(
                key=payload_pointer,
                kind="payload",
                original_json=json.dumps(
                    {"member": member, "length": length, "sha256": digest.hexdigest()}
                ),
            )
        )
        self.accounting.append(
            AccountingEntry(
                identity=payload_pointer,
                disposition="normalized",
                references=(asset_id,),
            )
        )

    def add_record(self, index, record):
        asset_id, owner = self.uuid(record["Id"]), self.uuid(record["SourceId"])
        pointer = f"attachments.json:{index}"

        refuse = _attachment_refusal(
            self.source_refuse, owner, asset_id, pointer, record.get("Type") == 2
        )
        location = self._validate_declaration(record, asset_id, owner, refuse)
        kind, note_type = record["Type"], record["NoteType"]
        self.asset_records[asset_id] = record
        common = {
            "asset_id": asset_id,
            "owner": owner,
            "naming_seed": asset_id.replace("-", ""),
            "original_name": location,
            "display_name": record.get("Name"),
            "evidence": (pointer,),
        }
        video = reviewed_video(record, refuse)
        if kind in {2, 3, 8}:
            self._add_external(record, common, kind, location, asset_id, video, refuse)
            return
        local, member = _local_member(location, kind, owner, asset_id, refuse)
        if kind == 15:
            self._add_absent_txt(
                record,
                common,
                location,
                local,
                member,
                pointer,
                asset_id,
                owner,
                refuse,
            )
            return
        recognized_note = kind == 1 and (note_type == 4 or location == "Notes.md")
        if recognized_note:
            if owner in self.note_owners:
                refuse(
                    "invalid_source",
                    "Multiple thought notes have ambiguous ownership",
                    (asset_id,),
                )
            self.note_owners.add(owner)
        if self.states.get(asset_id) == 3 and member not in self.names:
            if recognized_note:
                self._add_absent_note(
                    record,
                    common,
                    kind,
                    note_type,
                    location,
                    member,
                    pointer,
                    asset_id,
                    owner,
                    refuse,
                )
                return
            if kind == 5:
                self._add_absent_icon(
                    record,
                    common,
                    kind,
                    note_type,
                    location,
                    member,
                    pointer,
                    asset_id,
                    owner,
                    refuse,
                )
                return
            if kind == 12:
                self.assets.append(Asset(**common, role="image", availability="absent"))
                return
        self._add_present(
            record,
            common,
            kind,
            note_type,
            location,
            member,
            pointer,
            asset_id,
            owner,
            refuse,
        )

    def validate_assignments(self):
        for asset in self.assets:
            if asset.role == "file" and asset.availability == "external":
                local_member = (
                    asset.owner + "/" + PureWindowsPath(asset.original_name).name
                )
                if (
                    local_member in self.names
                    and local_member not in self.members.values()
                ):
                    self.source_refuse(
                        "invalid_source",
                        "External file has an unassigned local payload claim",
                        (asset.owner, asset.asset_id),
                        evidence=asset.evidence + ("payload:" + local_member,),
                        guidance="Review the external-file role and conflicting archive payload declaration; declare an internal attachment separately when it owns these bytes.",
                    )
        if set(self.states) - (
            {a.asset_id for a in self.assets} | {d.key for d in self.documents}
        ):
            self.source_refuse(
                "invalid_source", "File states refer to an absent attachment"
            )

    def _record_zero_length_txt(self, asset_id, owner, location, declared, pointer):
        stem = PurePosixPath(location).stem
        associated = tuple(
            a
            for a in self.assets
            if a.asset_id == stem
            and a.owner == owner
            and a.availability == "present"
            and a.role == "file"
            and PurePosixPath(a.original_name).suffix.casefold() == ".pdf"
            and self.asset_records[a.asset_id]["Type"] == 1
            and self.asset_records[a.asset_id]["NoteType"] == 0
        )
        if len(associated) != 1:
            self.source_refuse(
                "missing_required_payload",
                "Zero-length absent TXT does not identify one intact same-owner PDF attachment",
                (asset_id,),
            )
        pdf = associated[0]
        member = self.members[pdf.asset_id]
        self.findings.append(
            SourceFinding(
                kind="known_absent_payload",
                rule_id=ZERO_LENGTH_ABSENT_TXT_RULE,
                affected=(asset_id,),
                evidence=(pointer, "meta.json") + pdf.evidence + ("payload:" + member,),
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
                            "state": self.states[pdf.asset_id],
                            "member": member,
                            "declared_length": self.asset_records[pdf.asset_id][
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

    def _record_absent_txt(self, asset_id, owner, location, declared, pointer):
        pdfs = tuple(
            sorted(
                a.asset_id
                for a in self.assets
                if a.owner == owner
                and a.availability == "present"
                and a.role == "file"
                and PurePosixPath(a.original_name).suffix.casefold() == ".pdf"
            )
        )
        if not pdfs:
            self.findings.append(
                SourceFinding(
                    kind="known_absent_payload",
                    rule_id=ABSENT_TXT_DECLARATION_RULE,
                    affected=(asset_id,),
                    evidence=(pointer, "meta.json"),
                    observed_json=json.dumps(
                        {
                            "owner": owner,
                            "filename": location,
                            "member": owner + "/" + location,
                            "source_type": 2,
                            "type": 15,
                            "note_type": 0,
                            "declared_length": declared,
                            "state": 2,
                            "present": False,
                        }
                    ),
                )
            )
            return
        self.findings.append(
            SourceFinding(
                kind="known_absent_payload",
                rule_id=ABSENT_TXT_RULE,
                affected=(asset_id,),
                evidence=(pointer, "meta.json")
                + tuple(
                    p for a in self.assets if a.asset_id in pdfs for p in a.evidence
                ),
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

    def _record_absent_ordinary_note(self, asset_id, owner, member, declared, pointer):
        images = tuple(
            sorted(
                (a for a in self.assets if a.owner == owner and a.role == "image"),
                key=lambda a: a.asset_id,
            )
        )
        if not images:
            self.source_refuse(
                "missing_required_payload",
                "Absent ordinary note lacks usable owned note images",
                (asset_id,),
            )
        unavailable = tuple(
            image.asset_id for image in images if image.availability != "present"
        )
        if unavailable:
            self.source_refuse(
                "missing_required_payload",
                "Absent ordinary note has an unavailable unreferenced owned image",
                (asset_id, *unavailable),
            )
        image_facts = []
        for image in images:
            with self.archive.open(self.members[image.asset_id]) as stream:
                dimensions = validate_note_image(
                    stream, image.original_name, self.source_refuse, image.asset_id
                )
            image_facts.append(
                {
                    "asset_id": image.asset_id,
                    "owner": owner,
                    "member": self.members[image.asset_id],
                    "state": 1,
                    "declared_length": self.asset_records[image.asset_id]["DataLength"],
                    "actual_length": image.actual_length,
                    "actual_sha256": image.actual_sha256,
                    "crc_valid": True,
                    **dimensions,
                }
            )
        pointers = (pointer, "meta.json") + tuple(
            p
            for image in images
            for p in (*image.evidence, "payload:" + self.members[image.asset_id])
        )
        self.findings.append(
            SourceFinding(
                kind="known_absent_payload",
                rule_id=ABSENT_NOTE_IMAGES_RULE,
                affected=(asset_id,),
                evidence=pointers,
                observed_json=json.dumps(
                    {
                        "owner": owner,
                        "filename": "Notes.md",
                        "member": member,
                        "source_type": 2,
                        "type": 1,
                        "note_type": 4,
                        "state": 3,
                        "declared_length": declared,
                        "present": False,
                        "images": image_facts,
                    }
                ),
            )
        )
        self.gaps.append(
            SourceGap(
                owner=owner,
                asset_id=asset_id,
                role="ordinary_note",
                rule_id=ABSENT_NOTE_IMAGES_RULE,
                evidence=pointers,
            )
        )
        self.presentations.append(
            GeneratedPresentation(
                owner=owner,
                source_gap_asset_id=asset_id,
                image_asset_ids=tuple(a.asset_id for a in images),
            )
        )

    def record_missing_payloads(self):
        for facts in self.absent_records:
            if facts[3] == 0:
                self._record_zero_length_txt(*facts)
            else:
                self._record_absent_txt(*facts)
        for facts in sorted(self.absent_notes):
            self._record_absent_ordinary_note(*facts)

    def finish(self):
        self.documents = bind_prepared_notes(
            self.documents,
            self.assets,
            self.thoughts,
            self.source_refuse,
            brain_id=self.meta["BrainId"],
            allow_qualified=True,
            image_context={
                "basis": "archive_undeclared_no_payload",
                "members": self.names,
                "declared_absence": {
                    asset.asset_id: {
                        "basis": "archive_declared_state3_no_payload",
                        "state": 3,
                    }
                    for asset in self.assets
                    if asset.role == "image" and asset.availability == "absent"
                },
            },
            findings=self.findings,
        )
        admitted_images = {
            key
            for finding in self.findings
            if finding.rule_id == "thebrain.unavailable-declared-image.v1"
            for key in finding.affected
        }
        if any(
            asset.role == "image"
            and asset.availability == "absent"
            and asset.asset_id not in admitted_images
            for asset in self.assets
        ):
            self.source_refuse(
                "missing_required_payload",
                "An unavailable declared image has no admitted active reference",
            )
        self.accounting.extend(
            AccountingEntry(
                identity=f"reference:{document.key}:{index}",
                disposition="normalized",
                references=(document.key, reference.target),
            )
            for document in self.documents
            for index, reference in enumerate(document.references)
        )
        return (
            self.assets,
            self.documents,
            self.members,
            self.evidence,
            self.accounting,
            self.findings,
            sorted(self.gaps, key=lambda g: g.asset_id),
            self.presentations,
        )


def normalize_attachments(
    archive, records, meta, thoughts, refuse, uuid, excluded=(), scope_tokens=()
):
    inventory = _AttachmentInventory(
        archive, meta, thoughts, refuse, uuid, excluded, scope_tokens
    )
    inventory.validate_file_states(records)
    for index, record in enumerate(records):
        inventory.add_record(index, record)
    inventory.validate_assignments()
    inventory.record_missing_payloads()
    return inventory.finish()
