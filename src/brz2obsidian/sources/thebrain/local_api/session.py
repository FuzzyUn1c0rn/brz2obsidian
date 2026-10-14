"""Private owned capture and pinned integrity behind SourceSession."""

import hashlib
import re
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

from brz2obsidian.contracts import SourceSnapshot

from .capture import (
    DESKTOP_BUILD,
    IDENTIFIERS,
    SCHEMA_SHA256,
    canonical,
    parse_json,
    snapshot_projection,
    source_projection,
    validate_binding,
)
from .errors import failure, refuse
from .metadata import AcquisitionAudit, SourceAcquisition


def digest(domain, value):
    return hashlib.sha256(
        ("brz2obsidian.local-api." + domain + ".v1\n").encode("ascii")
        + canonical(value)
    ).hexdigest()


class CapturedStream:
    def __init__(self, raw, session):
        self.raw, self.session = raw, session

    @property
    def closed(self):
        return self.raw.closed

    def read(self, size=-1):
        if self.session.closed or self.closed:
            refuse("The captured payload stream is closed")
        try:
            return self.raw.read(size)
        except OSError, ValueError:
            raise failure(
                "api_payload_read_failed", "Captured payload could not be read safely"
            ) from None

    def close(self):
        try:
            self.raw.close()
        except OSError:
            raise failure(
                "api_payload_read_failed",
                "Captured payload stream could not close safely",
            ) from None


class LocalApiSession:
    """A frozen capture with content identity and a separately pinned manifest.

    Acquisition is non-atomic; integrity verification reads only this owned copy.
    Use SourceModule.open for live acquisition. Direct construction takes already
    qualified scoped facts, normalized snapshot and measured payload bytes. Close
    revokes streams and releases only session-owned storage.
    """

    def __init__(
        self,
        *,
        source,
        snapshot,
        audit,
        payloads=None,
        capture_parent=None,
        storage_keys=None,
    ):
        self._directory = None
        self._closed = False
        self._streams = []
        try:
            self._audit = AcquisitionAudit.model_validate_json(canonical(audit))
            source = source_projection(source)
            if source["identifiers"] != IDENTIFIERS:
                refuse("Capture identifiers do not match the reviewed profile")
            source_hash = digest("source", source)
            projected = snapshot_projection(snapshot)
            projected["identity"]["source_sha256"] = source_hash
            projected["identity"].pop("snapshot_digest")
            snapshot_hash = digest("snapshot", projected)
            projected["identity"]["snapshot_digest"] = snapshot_hash
            if (
                snapshot.identity.source_sha256
                and snapshot.identity.source_sha256 != source_hash
            ):
                refuse("Snapshot source identity disagrees with captured facts")
            if (
                snapshot.identity.snapshot_digest
                and snapshot.identity.snapshot_digest != snapshot_hash
            ):
                refuse("Snapshot identity disagrees with normalized captured facts")
            self._snapshot = SourceSnapshot.model_validate_json(canonical(projected))
            validate_binding(source, self._snapshot, self._audit)
            assets = {a.asset_id: a for a in self._snapshot.assets}
            payloads = payloads or {}
            keys = storage_keys or {}
            present = sorted(
                a.asset_id for a in assets.values() if a.availability == "present"
            )
            if set(payloads) != set(present):
                refuse("Captured payload inventory is incomplete or foreign")
            if len(source["payloads"]) != len(assets):
                refuse("Source and snapshot payload inventories disagree")
            for fact in source["payloads"]:
                asset = assets.get(fact["asset_id"])
                if asset is None or fact != {
                    "asset_id": asset.asset_id,
                    "owner_id": asset.owner,
                    "availability": asset.availability,
                    "actual_length": asset.actual_length,
                    "actual_sha256": asset.actual_sha256,
                    "external_uri": asset.external_uri,
                }:
                    refuse("Captured payload ownership or measurement disagrees")
            self._directory = Path(
                tempfile.mkdtemp(prefix="brz2obsidian-api-", dir=capture_parent)
            )
            self._ownership = self._owner()
            values = {
                "source.json": canonical(source),
                "snapshot.json": canonical(projected),
                "metadata.json": canonical(
                    {
                        "identifiers": source["identifiers"],
                        "identity": projected["identity"],
                        "schema_sha256": SCHEMA_SHA256,
                        "desktop_build": DESKTOP_BUILD,
                    }
                ),
                "audit.json": canonical(audit),
            }
            self._bindings = {}
            for index, asset_id in enumerate(present, 1):
                key = keys.get(asset_id, f"payload/{index:016x}.bin")
                if not re.fullmatch(r"payload/[0-9a-f]{16}\.bin", key) or key in values:
                    refuse("Captured payload storage identity is invalid")
                raw = bytes(payloads[asset_id])
                asset = assets[asset_id]
                if (
                    len(raw) != asset.actual_length
                    or hashlib.sha256(raw).hexdigest() != asset.actual_sha256
                ):
                    refuse(
                        "Captured payload bytes disagree with measured source evidence"
                    )
                values[key] = raw
                self._bindings[asset_id] = key
            self._manifest = {
                "format_id": IDENTIFIERS["format_id"],
                "format_version": "1",
                "source_sha256": source_hash,
                "snapshot_digest": snapshot_hash,
                "files": [
                    {
                        "role": "payload" if name.startswith("payload/") else name[:-5],
                        "storage_key": name,
                        "actual_length": len(raw),
                        "actual_sha256": hashlib.sha256(raw).hexdigest(),
                    }
                    for name, raw in sorted(values.items())
                ],
                "payload_bindings": [
                    {
                        "asset_id": asset_id,
                        "owner_id": assets[asset_id].owner,
                        "storage_key": self._bindings[asset_id],
                    }
                    for asset_id in present
                ],
            }
            self._root = digest("integrity", self._manifest)
            self._manifest["integrity_sha256"] = self._root
            self._manifest_bytes = canonical(self._manifest)
            values["manifest.json"] = self._manifest_bytes
            if (
                sum(len(raw) for raw in values.values())
                > audit["limits"]["max_total_capture_bytes"]
            ):
                refuse(
                    "max_total_capture_bytes storage limit exhausted",
                    "incomplete_source",
                )
            if any(
                len(payloads[key]) > audit["limits"]["max_payload_bytes"]
                for key in payloads
            ):
                refuse("max_payload_bytes storage limit exhausted", "incomplete_source")
            for name, raw in values.items():
                target = self._directory / name
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(raw)
            self.verify_consistency()
        except OSError, ValueError, KeyError, TypeError:
            self.close()
            raise failure(
                "api_capture_failed", "The private capture could not be frozen safely"
            ) from None
        except BaseException:
            self.close()
            raise

    @property
    def snapshot(self):
        return self._snapshot

    @property
    def source_identity(self):
        return self._snapshot.identity

    @property
    def closed(self):
        return self._closed

    @property
    def acquisition(self):
        self.verify_consistency()
        return SourceAcquisition(audit=self._audit, integrity_sha256=self._root)

    def _owner(self):
        info = self._directory.lstat()
        if (
            self._directory.is_symlink()
            or getattr(info, "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            refuse("The private capture storage is an unsafe alias")
        return info.st_dev, info.st_ino

    def verify_consistency(self):
        if self.closed:
            refuse("The captured source session is closed")
        try:
            if self._owner() != self._ownership:
                refuse("The captured source storage identity changed")
            expected = {e["storage_key"]: e for e in self._manifest["files"]}
            found = set()
            documents = {}
            for path in self._directory.rglob("*"):
                info = path.lstat()
                if (
                    path.is_symlink()
                    or getattr(info, "st_file_attributes", 0)
                    & stat.FILE_ATTRIBUTE_REPARSE_POINT
                ):
                    refuse("Captured storage contains an unsafe alias")
                key = path.relative_to(self._directory).as_posix()
                if path.is_dir():
                    if key != "payload":
                        refuse("Captured storage contains an unexpected directory")
                    continue
                found.add(key)
                if key == "manifest.json":
                    raw = path.read_bytes()
                    if raw != self._manifest_bytes:
                        refuse("The pinned capture manifest changed")
                    documents[key] = raw
                elif key not in expected:
                    refuse("Captured storage contains an unexpected file")
                else:
                    raw = path.read_bytes()
                    entry = expected[key]
                    if (
                        len(raw) != entry["actual_length"]
                        or hashlib.sha256(raw).hexdigest() != entry["actual_sha256"]
                    ):
                        refuse("Captured source bytes or metadata changed")
                    if key in {
                        "source.json",
                        "snapshot.json",
                        "metadata.json",
                        "audit.json",
                    }:
                        documents[key] = raw
            if found != set(expected) | {"manifest.json"}:
                refuse("Captured source files are missing")
            parsed = {
                key: parse_json(raw.decode("utf-8")) for key, raw in documents.items()
            }
            if any(canonical(parsed[key]) != raw for key, raw in documents.items()):
                refuse("Captured metadata is not canonical UTF-8")
            source = source_projection(parsed["source.json"])
            if (
                source["identifiers"] != IDENTIFIERS
                or canonical(source) != documents["source.json"]
            ):
                refuse("Captured source compatibility or canonical ordering changed")
            snapshot = SourceSnapshot.model_validate_json(documents["snapshot.json"])
            projected = snapshot_projection(snapshot)
            if (
                canonical(projected) != documents["snapshot.json"]
                or snapshot.identity != self.source_identity
            ):
                refuse("Captured snapshot shape or frozen identity changed")
            source_hash = digest("source", source)
            projected["identity"].pop("snapshot_digest")
            snapshot_hash = digest("snapshot", projected)
            if (source_hash, snapshot_hash) != (
                self.source_identity.source_sha256,
                self.source_identity.snapshot_digest,
            ):
                refuse(
                    "Recomputed captured content digests disagree with frozen identity"
                )
            audit = AcquisitionAudit.model_validate_json(documents["audit.json"])
            if audit != self._audit:
                refuse("Captured acquisition audit changed")
            validate_binding(source, snapshot, audit)
            metadata = {
                "identifiers": IDENTIFIERS,
                "identity": self.source_identity.model_dump(mode="json"),
                "schema_sha256": SCHEMA_SHA256,
                "desktop_build": DESKTOP_BUILD,
            }
            if parsed["metadata.json"] != metadata:
                refuse("Captured metadata compatibility or identity changed")
            manifest = parsed["manifest.json"]
            if (
                digest(
                    "integrity",
                    {k: v for k, v in manifest.items() if k != "integrity_sha256"},
                )
                != self._root
            ):
                refuse("The pinned capture association changed")
        except OSError, ValueError, KeyError, TypeError, RecursionError:
            raise failure(
                "api_capture_read_failed",
                "Captured source integrity could not be checked safely",
            ) from None

    @contextmanager
    def open_payload(self, asset_id):
        if self.closed or asset_id not in self._bindings:
            refuse("The requested captured payload is unknown or unavailable")
        self.verify_consistency()
        try:
            stream = CapturedStream(
                (self._directory / self._bindings[asset_id]).open("rb"), self
            )
        except OSError:
            raise failure(
                "api_payload_read_failed", "Captured payload could not be opened safely"
            ) from None
        self._streams.append(stream)
        try:
            yield stream
        finally:
            stream.close()
            self._streams.remove(stream)

    def close(self):
        if self.closed:
            return
        self._closed = True
        failed = False
        for stream in self._streams:
            try:
                stream.close()
            except Exception:  # noqa: BLE001 - teardown retains only the safe finite failure classification.
                failed = True
        if self._directory is not None:
            try:
                if self._owner() != self._ownership:
                    failed = True
                else:
                    shutil.rmtree(self._directory)
            except Exception:  # noqa: BLE001 - filesystem teardown must not expose arbitrary exception text.
                failed = True
        if failed:
            raise failure(
                "api_capture_cleanup_failed",
                "The owned private capture could not be cleaned safely",
            )
