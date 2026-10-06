"""Read-only BRZ interpretation and scoped payload access."""

import hashlib
import unicodedata
from compression.zstd import ZstdError
from contextlib import contextmanager
from lzma import LZMAError
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid5
from zipfile import ZIP_BZIP2, BadZipFile, ZipFile
from zlib import error as DeflateError

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
from .classifications import decode_classifications
from .decoding import ROOT_FILES, decode_records
from .metadata import calendar_dates, declared_appearance
from .relationships import decode_relationships
from .scope import records_json, scope_records
from .semantics import validate_semantic_fields


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


def _stream_fingerprint(stream):
    position = stream.tell()
    try:
        stream.seek(0)
        return hashlib.file_digest(stream, "sha256").hexdigest()
    finally:
        stream.seek(position)


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError("Expected canonical UUID text")
    return value


class _PayloadStream:
    """Translate archive read errors without translating a consumer's writes."""

    def __init__(self, stream, asset_id):
        self.stream, self.asset_id = stream, asset_id

    def __getattr__(self, name):
        value = getattr(self.stream, name)
        if name not in {
            "read",
            "read1",
            "readinto",
            "readinto1",
            "readline",
            "readlines",
            "seek",
        }:
            return value

        def read(*args, **kwargs):
            try:
                return value(*args, **kwargs)
            except (
                BadZipFile,
                OSError,
                EOFError,
                DeflateError,
                LZMAError,
                ZstdError,
            ) as error:
                raise MigrationFailed(
                    (
                        Issue(
                            code="payload_read_failure",
                            phase="source",
                            message=str(error),
                            affected=(self.asset_id,),
                            guidance="Check the source archive and re-export before retrying.",
                        ),
                    )
                ) from error

        return read

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stream.close()

    def __iter__(self):
        return self

    def __next__(self):
        line = self.readline()
        if not line:
            raise StopIteration
        return line


class BrzSourceModule:
    @contextmanager
    def open(self, source_ref):
        session = None
        try:
            session = BrzSession(Path(source_ref))
        except MigrationRefused:
            raise
        except NotImplementedError:
            _refuse("unsupported_feature", "Unsupported BRZ ZIP compression")
        except (
            BadZipFile,
            DeflateError,
            LZMAError,
            ZstdError,
            EOFError,
            UnicodeError,
            ValueError,
            KeyError,
            TypeError,
            ValidationError,
        ):
            _refuse("invalid_source", "Invalid BRZ data")
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
        except BaseException as error:
            try:
                session.close()
            except MigrationFailed as teardown:
                if isinstance(error, (MigrationRefused, MigrationFailed)):
                    raise MigrationFailed(
                        error.issues + teardown.issues, receipt=error.receipt
                    ) from error
                for issue in teardown.issues:
                    error.add_note(f"{issue.code}: {issue.message}")
            raise
        else:
            session.close()


class BrzSession:
    def __init__(self, path):
        self.path = path
        self.closed = False
        self.streams = set()
        self.source_stream = path.open("rb")
        self.members = {}
        try:
            self.initial_hash = _stream_fingerprint(self.source_stream)
            self.archive = ZipFile(self.source_stream, "r")
            self.snapshot = self._read()
            self.source_identity = self.snapshot.identity
            self.verify_consistency()
        except BaseException:
            try:
                if hasattr(self, "archive"):
                    self.archive.close()
            finally:
                self.source_stream.close()
            raise

    def _read(self):
        source_hash = self.initial_hash
        names = self.archive.namelist()
        folded = [unicodedata.normalize("NFC", name).casefold() for name in names]
        if len(set(folded)) != len(folded):
            _refuse("invalid_source", "Duplicate or case-ambiguous archive members")
        for info in self.archive.infolist():
            path = PurePosixPath(info.filename)
            if (
                path.is_absolute()
                or str(path) != info.filename.removesuffix("/")
                or info.filename in {"", ".", "./"}
                or ".." in path.parts
                or "\\" in info.filename
                or ":" in info.filename
                or info.flag_bits & 1
                or (info.external_attr >> 16) & 0o170000 == 0o120000
            ):
                _refuse("invalid_source", "Unsafe, encrypted or symlink archive member")
        for info in self.archive.infolist():
            try:
                with self.archive.open(info) as stream:
                    while stream.read(1024 * 1024):
                        pass
            except OSError as error:
                # bz2 reports corrupt compressed bytes with a plain OSError.
                # Translate only that known decoder error on a BZIP2 member;
                # filesystem/access errors keep their operational failure path.
                if (
                    info.compress_type == ZIP_BZIP2
                    and type(error) is OSError
                    and error.args == ("Invalid data stream",)
                ):
                    _refuse(
                        "invalid_source",
                        "Invalid BRZ compressed data",
                    )
                raise
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
                            "links.json",
                            "attachments.json",
                            "settings.json",
                        }
                        else "retained_only",
                        references=(pointer,),
                    )
                )
        records, self.excluded, dropped_members, self.scope_tokens = scope_records(
            records, _refuse, _uuid
        )
        if self.excluded:
            originals = {e.key: e.original_json for e in evidence}
            evidence = [
                OriginalEvidence(
                    key=name,
                    kind="records",
                    original_json=records_json(records[name], originals[name]),
                )
                for name in ROOT_FILES
            ]
            accounting = [
                AccountingEntry(
                    identity=f"{name}:{index}",
                    disposition="normalized"
                    if name
                    in {
                        "meta.json",
                        "thoughts.json",
                        "links.json",
                        "attachments.json",
                        "settings.json",
                    }
                    else "retained_only",
                    references=(f"{name}:{index}",),
                )
                for name in ROOT_FILES
                for index, _ in enumerate(records[name])
            ]
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
            "calendarevents.json",
            "access.json",
            "fielddefinitions.json",
            "fieldinstances.json",
        ):
            if records[name]:
                _refuse(
                    "unsupported_feature",
                    f"The reviewed profile does not implement nonempty {name}",
                )
        thought_records = records["thoughts.json"]
        live_id_list = [
            record.get("Id")
            for name in ("thoughts.json", "links.json", "attachments.json")
            for record in records[name]
        ]
        live_ids = set(live_id_list)
        if len(live_ids) != len(live_id_list):
            _refuse("invalid_source", "Duplicate live identities across source records")
        if any(record.get("Id") in live_ids for record in records["tombstones.json"]):
            _refuse("invalid_source", "A live identity also occurs in deleted history")
        thoughts = {}
        for record in thought_records:
            key = _uuid(record["Id"])
            validate_semantic_fields(record, _refuse, known_type_fields=("TypeId",))
            if "TagIds" in record and type(record["TagIds"]) is not list:
                _refuse("invalid_source", "TagIds must be an array", (key,))
            if record.get("Aliases"):
                _refuse(
                    "unsupported_feature",
                    "Thought aliases are outside reviewed content coverage",
                    (key,),
                )
            if key in thoughts or record.get("BrainId") != brain_id:
                _refuse(
                    "invalid_source",
                    "Duplicate thought or foreign collection ownership",
                )
            if (
                type(record.get("Kind")) is not int
                or record["Kind"] not in {1, 2, 4, 5}
                or type(record.get("ACType", 0)) is not int
                or record.get("ACType", 0) != 0
                or record.get("TagIds")
                or record.get("ThoughtTypeId")
            ):
                _refuse(
                    "unsupported_feature",
                    "Only reviewed ordinary, type, tag and system roles are supported",
                )
            if type(record.get("Name")) is not str or (
                record.get("Label") is not None and type(record["Label"]) is not str
            ):
                _refuse("invalid_source", "Thought title/label is invalid")
            thoughts[key] = record
        setting_id = str(uuid5(UUID(brain_id), "20"))
        setting_keys = set()
        for record in records["settings.json"]:
            key = _uuid(record.get("Id"))
            if key in setting_keys or (
                "BrainId" in record and record["BrainId"] != brain_id
            ):
                _refuse(
                    "invalid_source",
                    "Setting identity or collection ownership is invalid",
                    (key,),
                )
            setting_keys.add(key)
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
        if entry not in thoughts or thoughts[entry]["Kind"] != 1:
            _refuse("invalid_entry", "Home does not identify a live ordinary thought")
        (
            assets,
            documents,
            self.members,
            payload_evidence,
            payload_accounting,
            findings,
        ) = normalize_attachments(
            self.archive,
            records["attachments.json"],
            meta,
            thoughts,
            _refuse,
            _uuid,
            self.excluded,
            self.scope_tokens,
        )
        evidence.extend(payload_evidence)
        accounting.extend(payload_accounting)
        resources = {
            name for name in names if name not in ROOT_FILES and not name.endswith("/")
        }
        if resources - dropped_members != set(self.members.values()):
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
                calendar_dates=calendar_dates(record, _refuse),
                declared_appearance=declared_appearance(record, assets, _refuse),
                role={1: "ordinary", 2: "definition", 4: "tag", 5: "system"}[
                    record["Kind"]
                ],
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
            module_version="3",
            format_version="5",
            source_sha256=source_hash,
            snapshot_digest=snapshot_digest,
        )
        relationships = decode_relationships(
            records["links.json"], thoughts, brain_id, _refuse, _uuid
        )
        assignments = decode_classifications(thoughts, relationships, _refuse, _uuid)
        return SourceSnapshot(
            identity=identity,
            collection_title=meta.get("Name", "TheBrain collection"),
            entry_key=entry,
            items=items,
            relationships=relationships,
            classification_assignments=assignments,
            documents=tuple(documents),
            assets=tuple(assets),
            original_evidence=tuple(evidence),
            findings=tuple(findings),
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
        try:
            stream = self.archive.open(self.members[asset_id])
        except (
            BadZipFile,
            OSError,
            EOFError,
            DeflateError,
            LZMAError,
            ZstdError,
        ) as error:
            raise MigrationFailed(
                (
                    Issue(
                        code="payload_read_failure",
                        phase="source",
                        message=str(error),
                        affected=(asset_id,),
                        guidance="Check the source archive and re-export before retrying.",
                    ),
                )
            ) from error
        with stream:
            self.streams.add(stream)
            try:
                yield _PayloadStream(stream, asset_id)
            finally:
                self.streams.discard(stream)

    def verify_consistency(self):
        if self.closed:
            _refuse("source_changed", "Source session is closed")
        try:
            if (
                _stream_fingerprint(self.source_stream)
                != self.source_identity.source_sha256
                or _fingerprint(self.path) != self.source_identity.source_sha256
            ):
                _refuse("source_changed", "Source changed during conversion")
        except OSError as error:
            _refuse("source_changed", f"Source is no longer readable: {error}")

    def close(self):
        self.closed = True
        issues = []
        for resource in (*tuple(self.streams), self.archive, self.source_stream):
            try:
                resource.close()
            except OSError as error:
                issues.append(
                    Issue(
                        code="session_teardown_failure",
                        phase="session_teardown",
                        message=str(error),
                        guidance="Check source access; any published receipt remains valid.",
                    )
                )
        self.streams.clear()
        if issues:
            raise MigrationFailed(tuple(issues))
