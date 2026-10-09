"""A test-only file-backed format with opaque item keys and explicit entry.

Folio JSON has named entries, connections, documents and local payload files.
It knows no Brain metadata, UUID conventions or numeric source enums. Its
declared references are already traced spans, as a compatible source requires.
Optional assignments pair named classification connections with definitions and
members. Appearance and video values are explicit Folio declarations; calendar
dates are Folio year/month/day triplets, independently of source timestamps.
"""

import hashlib
import json
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from brz2obsidian.contracts import (
    AccountingEntry,
    Asset,
    CalendarDates,
    ClassificationAssignment,
    DeclaredAppearance,
    Document,
    Issue,
    Item,
    MigrationRefused,
    OriginalEvidence,
    ReferenceSpan,
    Relationship,
    SourceAccounting,
    SourceFinding,
    SourceIdentity,
    SourcePolicy,
    SourceSnapshot,
    VideoPresentation,
)

FOLIO_POLICY = SourcePolicy(
    profile_id="synthetic-folio-reviewed",
    profile_version="3",
    module_id="synthetic-folio",
    module_version="3",
    format_version="folio/1",
    contract_version=4,
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_changed():
    return MigrationRefused(
        (
            Issue(
                code="source_changed",
                phase="source",
                message="Folio source changed during its scoped session",
                guidance="Reopen the source and repeat conversion.",
            ),
        )
    )


class FolioSession:
    def __init__(
        self, path, *, stream_failure=False, read_failure=False, mutate_on_payload=False
    ):
        self.path = Path(path)
        self.closed = False
        self.stream_failure = stream_failure
        self.read_failure = read_failure
        self.mutate_on_payload = mutate_on_payload
        self.streams = []
        raw = self.path.read_bytes()
        data = json.loads(raw)
        self.local_paths = {
            entry["key"]: self.path.parent / entry["file"]
            for entry in data["assets"]
            if "file" in entry
        }
        self.original_bytes = {
            key: p.read_bytes() for key, p in self.local_paths.items()
        }
        self.source_bytes = raw
        assets = tuple(
            Asset(
                asset_id=a["key"],
                owner=a["owner"],
                naming_seed=a["seed"],
                original_name=a["name"],
                display_name=a.get("label"),
                role=a["role"],
                availability="present" if "file" in a else "external",
                actual_length=len(self.original_bytes[a["key"]])
                if "file" in a
                else None,
                actual_sha256=digest(self.original_bytes[a["key"]])
                if "file" in a
                else None,
                external_uri=a.get("uri"),
                evidence=("folio.json",),
                video_presentation=VideoPresentation(**a["video"])
                if a.get("video")
                else None,
            )
            for a in data["assets"]
        )
        documents = []
        for d in data["documents"]:
            text = self.original_bytes[d["original"]].decode("utf-8")
            text_digest = digest(text.encode("utf-8"))
            references = tuple(
                ReferenceSpan(**r, document_digest=text_digest)
                for r in d.get("references", [])
            )
            documents.append(
                Document(
                    key=d["key"],
                    owner=d["owner"],
                    text=text,
                    text_digest=text_digest,
                    original_asset_id=d["original"],
                    references=references,
                    evidence=("folio.json",),
                )
            )
        items = tuple(
            Item(
                key=i["key"],
                original_identity=i["key"],
                naming_seed=i["seed"],
                title=i["title"],
                label=i.get("label"),
                role=i.get("role", "ordinary"),
                document_ids=tuple(d.key for d in documents if d.owner == i["key"]),
                resource_ids=tuple(a.asset_id for a in assets if a.owner == i["key"]),
                declared_appearance=DeclaredAppearance(**i["appearance"])
                if i.get("appearance")
                else None,
                calendar_dates=CalendarDates(
                    **{
                        field: date(*parts) if parts is not None else None
                        for field, parts in i["calendar"].items()
                    }
                )
                if i.get("calendar")
                else None,
                evidence=("folio.json",),
            )
            for i in data["entries"]
        )
        relationships = tuple(
            Relationship(**r, evidence=("folio.json",)) for r in data["connections"]
        )
        identity = SourceIdentity(
            source_id=data["collection"],
            module_id="synthetic-folio",
            module_version="3",
            format_version="folio/1",
            source_sha256=digest(raw),
            snapshot_digest="",
        )
        snapshot = SourceSnapshot(
            contract_version=4,
            identity=identity,
            collection_title=data["collection"],
            entry_key=data["start"],
            items=items,
            documents=tuple(documents),
            assets=assets,
            relationships=relationships,
            classification_assignments=tuple(
                ClassificationAssignment(**assignment, evidence=("folio.json",))
                for assignment in data.get("assignments", [])
            ),
            findings=tuple(
                SourceFinding(
                    **{key: value for key, value in f.items() if key != "affected"},
                    affected=tuple(f.get("affected", ())),
                    evidence=("folio.json",),
                )
                for f in data.get("findings", [])
            ),
            original_evidence=(
                OriginalEvidence(
                    key="folio.json", kind="records", original_json=raw.decode()
                ),
            ),
            accounting=SourceAccounting(
                entries=(
                    AccountingEntry(
                        identity="folio.json",
                        disposition="normalized",
                        references=tuple(i.key for i in items)
                        + tuple(a.asset_id for a in assets)
                        + tuple(r.key for r in relationships),
                    ),
                )
            ),
        )
        self.source_identity = identity.model_copy(
            update={"snapshot_digest": digest(snapshot.model_dump_json().encode())}
        )
        self.snapshot = snapshot.model_copy(update={"identity": self.source_identity})

    def verify_consistency(self):
        if self.closed:
            raise OSError("Folio source session is closed")
        if self.path.read_bytes() != self.source_bytes or any(
            p.read_bytes() != self.original_bytes[key]
            for key, p in self.local_paths.items()
        ):
            raise source_changed()

    @contextmanager
    def open_payload(self, asset_id):
        self.verify_consistency()
        if self.stream_failure:
            raise OSError("Folio payload stream cannot be opened")
        with self.local_paths[asset_id].open("rb") as stream:
            self.streams.append(stream)
            if self.mutate_on_payload:
                self.path.write_bytes(self.source_bytes + b"\n")
            yield InterruptedRead(stream) if self.read_failure else stream
        self.verify_consistency()

    def close(self):
        self.closed = True
        for stream in self.streams:
            stream.close()


class FolioSourceModule:
    def __init__(self, *, teardown_failure=False, **session_options):
        self.teardown_failure = teardown_failure
        self.session_options = session_options

    @contextmanager
    def open(self, source_ref):
        session = FolioSession(source_ref, **self.session_options)
        try:
            yield session
        finally:
            session.close()
            if self.teardown_failure:
                raise OSError("Folio source cannot finish session teardown")


class InterruptedRead:
    """A boundary failure after copying actual bytes from a real payload file."""

    def __init__(self, stream):
        self.stream = stream
        self.started = False

    def read(self, size=-1):
        if self.started:
            raise OSError("Folio payload became unreadable after its first bytes")
        self.started = True
        return self.stream.read(2)
