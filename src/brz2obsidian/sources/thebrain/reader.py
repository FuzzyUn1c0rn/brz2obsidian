"""Read-only BRZ interpretation and scoped payload access."""

import hashlib
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid5
from zipfile import BadZipFile, ZipFile

from pydantic import ValidationError

from brz2obsidian.contracts import (
    AccountingEntry,
    Issue,
    Item,
    MigrationFailed,
    MigrationRefused,
    OriginalEvidence,
    SourceAccounting,
    SourceIdentity,
    SourceSnapshot,
)

from .attachments import normalize_attachments
from .decoding import ROOT_FILES, decode_records


def _refuse(code, message, affected=()):
    raise MigrationRefused(
        (
            Issue(
                code=code,
                phase="source",
                message=message,
                affected=affected,
                guidance="Investigate the source, set a valid Home in TheBrain, and re-export.",
            ),
        )
    )


def _fingerprint(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError("Expected canonical UUID text")
    return value


class BrzSourceModule:
    @contextmanager
    def open(self, source_ref):
        session = None
        try:
            session = BrzSession(Path(source_ref))
        except MigrationRefused:
            raise
        except (
            BadZipFile,
            UnicodeError,
            ValueError,
            KeyError,
            TypeError,
            ValidationError,
        ) as error:
            _refuse("invalid_source", f"Invalid BRZ data: {error}")
        except OSError as error:
            raise MigrationFailed(
                (
                    Issue(
                        code="write_failure",
                        phase="source",
                        message=str(error),
                        guidance="Check source access and retry.",
                    ),
                )
            ) from error
        try:
            yield session
        finally:
            session.close()


class BrzSession:
    def __init__(self, path):
        self.path = path
        self.closed = False
        self.archive = ZipFile(path, "r")
        self.members = {}
        try:
            self.snapshot = self._read()
            self.source_identity = self.snapshot.identity
        except BaseException:
            self.archive.close()
            raise

    def _read(self):
        source_hash = _fingerprint(self.path)
        names = self.archive.namelist()
        folded = [name.casefold() for name in names]
        if len(set(folded)) != len(folded):
            _refuse("invalid_source", "Duplicate or case-ambiguous archive members")
        for info in self.archive.infolist():
            path = PurePosixPath(info.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in info.filename
                or ":" in info.filename
                or info.flag_bits & 1
                or (info.external_attr >> 16) & 0o170000 == 0o120000
            ):
                _refuse("invalid_source", "Unsafe, encrypted or symlink archive member")
        if self.archive.testzip() is not None:
            _refuse("invalid_source", "Archive CRC failure")
        if not set(ROOT_FILES).issubset(names):
            _refuse("invalid_source", "Missing required root record collections")
        records, evidence, accounting = {}, [], []
        for name in ROOT_FILES:
            collection, original_json = decode_records(name, self.archive.read(name))
            records[name] = collection
            evidence.append(
                OriginalEvidence(key=name, kind="records", original_json=original_json)
            )
            for index, record in enumerate(collection):
                pointer = f"{name}:{index}"
                accounting.append(
                    AccountingEntry(
                        identity=pointer,
                        disposition="normalized"
                        if name
                        in {
                            "meta.json",
                            "thoughts.json",
                            "attachments.json",
                            "settings.json",
                        }
                        else "retained_only",
                        references=(pointer,),
                    )
                )
        meta = records["meta.json"][0]
        if (
            type(meta.get("ExchangeFormatVersion")) is not int
            or meta["ExchangeFormatVersion"] != 5
        ):
            _refuse(
                "unsupported_format", "Only reviewed exchange format 5 is supported"
            )
        brain_id = _uuid(meta["BrainId"])
        if type(meta.get("AttachmentFileStates")) is not dict:
            _refuse("invalid_source", "AttachmentFileStates must be an object")
        for name in (
            "links.json",
            "calendarevents.json",
            "access.json",
            "fielddefinitions.json",
            "fieldinstances.json",
        ):
            if records[name]:
                _refuse(
                    "unsupported_feature",
                    f"This minimal profile does not yet implement {name}",
                )
        thought_records = records["thoughts.json"]
        thoughts = {}
        for record in thought_records:
            key = _uuid(record["Id"])
            if key in thoughts or record.get("BrainId") != brain_id:
                _refuse(
                    "invalid_source",
                    "Duplicate thought or foreign collection ownership",
                )
            if (
                type(record.get("Kind")) is not int
                or record["Kind"] != 1
                or type(record.get("ACType", 0)) is not int
                or record.get("ACType", 0) != 0
                or record.get("TagIds")
                or record.get("ThoughtTypeId")
            ):
                _refuse(
                    "unsupported_feature",
                    "Only ordinary untyped thoughts are implemented in the minimal profile",
                )
            if type(record.get("Name")) is not str or (
                record.get("Label") is not None and type(record["Label"]) is not str
            ):
                _refuse("invalid_source", "Thought title/label is invalid")
            thoughts[key] = record
        setting_id = str(uuid5(UUID(brain_id), "20"))
        home = [
            record
            for record in records["settings.json"]
            if record.get("Id") == setting_id
        ]
        if len(home) != 1:
            _refuse(
                "invalid_entry",
                "Home setting is absent or duplicated; set Home in TheBrain and re-export",
            )
        try:
            entry = _uuid(home[0].get("Value"))
        except ValueError, TypeError, AttributeError:
            _refuse("invalid_entry", "Home setting is not a valid thought identity")
        if entry not in thoughts:
            _refuse("invalid_entry", "Home does not identify a live ordinary thought")
        assets, documents, self.members, payload_evidence, payload_accounting = (
            normalize_attachments(
                self.archive,
                records["attachments.json"],
                meta,
                thoughts,
                _refuse,
                _uuid,
            )
        )
        evidence.extend(payload_evidence)
        accounting.extend(payload_accounting)
        resources = {
            name for name in names if name not in ROOT_FILES and not name.endswith("/")
        }
        if resources != set(self.members.values()):
            _refuse(
                "unsupported_feature",
                "Archive contains unaccounted payloads or root files",
            )
        items = tuple(
            Item(
                key=key,
                original_identity=key,
                naming_seed=key.replace("-", ""),
                title=record["Name"],
                label=record.get("Label"),
                document_ids=tuple(d.key for d in documents if d.owner == key),
                resource_ids=tuple(
                    a.asset_id
                    for a in assets
                    if a.owner == key and a.role != "note_original"
                ),
                evidence=(f"thoughts.json:{i}",),
            )
            for i, (key, record) in enumerate(thoughts.items())
        )
        snapshot_digest = hashlib.sha256(
            "".join(e.original_json for e in evidence).encode()
        ).hexdigest()
        identity = SourceIdentity(
            source_id=brain_id,
            module_id="thebrain-brz",
            module_version="1",
            format_version="5",
            source_sha256=source_hash,
            snapshot_digest=snapshot_digest,
        )
        return SourceSnapshot(
            identity=identity,
            collection_title=meta.get("Name", "TheBrain collection"),
            entry_key=entry,
            items=items,
            documents=tuple(documents),
            assets=tuple(assets),
            original_evidence=tuple(evidence),
            accounting=SourceAccounting(entries=tuple(accounting)),
        )

    @contextmanager
    def open_payload(self, asset_id):
        if self.closed:
            raise MigrationFailed(
                (
                    Issue(
                        code="invalid_source",
                        phase="source",
                        message="Source session is closed",
                        guidance="Open a new source session.",
                    ),
                )
            )
        if asset_id not in self.members:
            _refuse("invalid_reference", "Unknown payload identity", (asset_id,))
        with self.archive.open(self.members[asset_id]) as stream:
            yield stream

    def verify_consistency(self):
        if self.closed or _fingerprint(self.path) != self.source_identity.source_sha256:
            _refuse("source_changed", "Source changed or the source session is closed")

    def close(self):
        self.archive.close()
        self.closed = True
