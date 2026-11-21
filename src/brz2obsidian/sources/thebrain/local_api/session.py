"""Private owned capture and pinned integrity behind SourceSession."""

import hashlib
import os
import re
import shutil
import stat
import tempfile
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from threading import Lock

from brz2obsidian.contracts import SourceSnapshot

from .capture import (
    IDENTIFIERS,
    canonical,
    identifiers,
    parse_json,
    qualification_baseline,
    snapshot_projection,
    source_projection,
    validate_binding,
)
from .errors import check_cancel, failure, refuse
from .metadata import AcquisitionAudit, SourceAcquisition
from .read_view import CaptureReadView
from .storage import StagedPayload


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
    Optional exact-bool cancellation controls freezing only; it is not retained
    in the capture or a claim that a decoder can be preempted.
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
        profile_version="1",
        cancel=None,
    ):
        self._identifiers = identifiers(profile_version)
        self._directory = None
        self._closed = False
        self._streams = []
        self._metadata_proof = None
        self._read_lock = Lock()
        self._read_view = None
        try:
            check_cancel(cancel)
            source, projected = self._project_capture(source, snapshot, audit)
            payloads, keys = payloads or {}, storage_keys or {}
            assets, present = self._check_payload_inventory(source, payloads)
            values = self._open_capture_storage(
                source, projected, audit, capture_parent, profile_version
            )
            payload_entries = self._store_payloads(
                source,
                assets,
                present,
                payloads,
                keys,
                values,
                audit,
                profile_version,
                cancel,
            )
            self._seal_capture(
                values,
                payload_entries,
                assets,
                present,
                audit,
            )
            self.verify_consistency()
            check_cancel(cancel)
        except OSError, ValueError, KeyError, TypeError:
            self.close()
            raise failure(
                "api_capture_failed", "The private capture could not be frozen safely"
            ) from None
        except BaseException:
            self.close()
            raise

    def _project_capture(self, source, snapshot, audit):
        self._audit = AcquisitionAudit.model_validate_json(canonical(audit))
        source = source_projection(source)
        if source["identifiers"] != self._identifiers:
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
        return source, projected

    def _check_payload_inventory(self, source, payloads):
        assets = {a.asset_id: a for a in self._snapshot.assets}
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
        return assets, present

    def _open_capture_storage(
        self, source, projected, audit, capture_parent, profile_version
    ):
        self._directory = Path(
            tempfile.mkdtemp(prefix="brz2obsidian-api-", dir=capture_parent)
        )
        self._ownership = self._owner()
        return {
            "source.json": canonical(source),
            "snapshot.json": canonical(projected),
            "metadata.json": canonical(
                {
                    "identifiers": source["identifiers"],
                    "identity": projected["identity"],
                    **qualification_baseline(profile_version),
                }
            ),
            "audit.json": canonical(audit),
        }

    def _payload_input(self, supplied, cap, bounded_icon):
        if bounded_icon and not isinstance(supplied, (Path, StagedPayload)):
            from .icons import encoded_limit

            # Bound the actual buffer before allocating and bypass
            # custom whole-value coercion. Older profiles keep theirs.
            with memoryview(supplied).cast("B") as view:
                cap = encoded_limit(bytes(view[:4]), cap)
                if view.nbytes > cap:
                    refuse(
                        "icon_family storage limit exhausted",
                        "incomplete_source",
                    )
                stream = BytesIO(view)
        else:
            stream = (
                supplied.open("rb")
                if isinstance(supplied, (Path, StagedPayload))
                else BytesIO(bytes(supplied))
            )
        return stream, cap

    def _measure_icon_prefix(self, icon_prefix, chunk, cap, supplied, stream):
        from .icons import encoded_limit

        icon_prefix += chunk[: 4 - len(icon_prefix)]
        if len(icon_prefix) == 4:
            cap = encoded_limit(icon_prefix, cap)
            if (
                isinstance(supplied, (Path, StagedPayload))
                and os.fstat(stream.fileno()).st_size > cap
            ):
                refuse(
                    "icon_family storage limit exhausted",
                    "incomplete_source",
                )
        return icon_prefix, cap

    def _copy_payload(
        self, supplied, target, bounded_icon, limits, stored_size, cancel
    ):
        stream, cap = self._payload_input(
            supplied, limits["max_payload_bytes"], bounded_icon
        )
        length, measured = 0, hashlib.sha256()
        icon_prefix = b""
        with stream, target.open("wb") as destination:
            while True:
                check_cancel(cancel)
                read_limit = min(65536, cap - length + 1)
                if bounded_icon and len(icon_prefix) < 4:
                    read_limit = min(read_limit, 4 - len(icon_prefix))
                chunk = stream.read(read_limit)
                check_cancel(cancel)
                if not chunk:
                    break
                if bounded_icon and len(icon_prefix) < 4:
                    icon_prefix, cap = self._measure_icon_prefix(
                        icon_prefix, chunk, cap, supplied, stream
                    )
                length += len(chunk)
                if length > cap:
                    refuse(
                        "icon_family storage limit exhausted"
                        if cap < limits["max_payload_bytes"]
                        else "max_payload_bytes storage limit exhausted",
                        "incomplete_source",
                    )
                if stored_size + length > limits["max_total_capture_bytes"]:
                    refuse(
                        "max_total_capture_bytes storage limit exhausted",
                        "incomplete_source",
                    )
                measured.update(chunk)
                destination.write(chunk)
                check_cancel(cancel)
        return length, measured

    def _store_payloads(
        self,
        source,
        assets,
        present,
        payloads,
        keys,
        values,
        audit,
        profile_version,
        cancel,
    ):
        self._bindings = {}
        payload_entries = []
        attachment_values = {
            r["value"]["id"]: r["value"]
            for r in source["records"]
            if r["domain"] == "attachment"
        }
        for index, asset_id in enumerate(present, 1):
            key = keys.get(asset_id, f"payload/{index:016x}.bin")
            if (
                not re.fullmatch(r"payload/[0-9a-f]{16}\.bin", key)
                or key in values
                or key in self._bindings.values()
            ):
                refuse("Captured payload storage identity is invalid")
            asset = assets[asset_id]
            target = self._directory / key
            target.parent.mkdir(exist_ok=True)
            supplied = payloads[asset_id]
            bounded_icon = (
                profile_version == "5" and attachment_values[asset_id]["type"] == 5
            )
            length, measured = self._copy_payload(
                supplied,
                target,
                bounded_icon,
                audit["limits"],
                sum(e["actual_length"] for e in payload_entries)
                + sum(map(len, values.values())),
                cancel,
            )
            if (
                length != asset.actual_length
                or measured.hexdigest() != asset.actual_sha256
            ):
                refuse("Captured payload bytes disagree with measured source evidence")
            from .resources import validate_bytes

            validate_bytes(
                attachment_values[asset_id], target, profile_version, cancel=cancel
            )
            payload_entries.append(
                {
                    "role": "payload",
                    "storage_key": key,
                    "actual_length": length,
                    "actual_sha256": measured.hexdigest(),
                }
            )
            self._bindings[asset_id] = key
        return payload_entries

    def _seal_capture(self, values, payload_entries, assets, present, audit):
        self._manifest = {
            "format_id": IDENTIFIERS["format_id"],
            "format_version": "1",
            "source_sha256": self.source_identity.source_sha256,
            "snapshot_digest": self.source_identity.snapshot_digest,
            "files": sorted(
                [
                    {
                        "role": name[:-5],
                        "storage_key": name,
                        "actual_length": len(raw),
                        "actual_sha256": hashlib.sha256(raw).hexdigest(),
                    }
                    for name, raw in values.items()
                ]
                + payload_entries,
                key=lambda entry: entry["storage_key"],
            ),
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
            + sum(e["actual_length"] for e in payload_entries)
            > audit["limits"]["max_total_capture_bytes"]
        ):
            refuse(
                "max_total_capture_bytes storage limit exhausted",
                "incomplete_source",
            )
        for name, raw in values.items():
            target = self._directory / name
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(raw)

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
        try:
            self._verify_consistency()
        except BaseException:
            if self._read_view is not None:
                self._read_view.failed = True
            raise

    def _read_measured_file(self, path, key, entry):
        length, measured = 0, hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(65536):
                length += len(chunk)
                if length > entry["actual_length"]:
                    refuse("Captured source bytes or metadata changed")
                measured.update(chunk)
        if (
            length != entry["actual_length"]
            or measured.hexdigest() != entry["actual_sha256"]
        ):
            refuse("Captured source bytes or metadata changed")
        if key in {
            "source.json",
            "snapshot.json",
            "metadata.json",
            "audit.json",
        }:
            raw = path.read_bytes()
            if (
                len(raw) != entry["actual_length"]
                or hashlib.sha256(raw).hexdigest() != entry["actual_sha256"]
            ):
                refuse("Captured source bytes or metadata changed")
            return raw
        return None

    def _frozen_path_key(self, path):
        info = path.lstat()
        if (
            path.is_symlink()
            or getattr(info, "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            refuse("Captured storage contains an unsafe alias")
        return path.relative_to(self._directory).as_posix()

    def _read_frozen_documents(self):
        if self._owner() != self._ownership:
            refuse("The captured source storage identity changed")
        expected = {e["storage_key"]: e for e in self._manifest["files"]}
        found = set()
        documents = {}
        for path in self._directory.rglob("*"):
            key = self._frozen_path_key(path)
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
                continue
            if key not in expected:
                refuse("Captured storage contains an unexpected file")
            raw = self._read_measured_file(path, key, expected[key])
            if raw is not None:
                documents[key] = raw
        if found != set(expected) | {"manifest.json"}:
            refuse("Captured source files are missing")
        return documents

    def _prove_frozen_metadata(self, documents):
        parsed = {
            key: parse_json(raw.decode("utf-8")) for key, raw in documents.items()
        }
        if any(canonical(parsed[key]) != raw for key, raw in documents.items()):
            refuse("Captured metadata is not canonical UTF-8")
        source = source_projection(parsed["source.json"])
        if (
            source["identifiers"] != self._identifiers
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
            refuse("Recomputed captured content digests disagree with frozen identity")
        audit = AcquisitionAudit.model_validate_json(documents["audit.json"])
        if audit != self._audit:
            refuse("Captured acquisition audit changed")
        validate_binding(source, snapshot, audit)
        metadata = {
            "identifiers": self._identifiers,
            "identity": self.source_identity.model_dump(mode="json"),
            **qualification_baseline(self._identifiers["profile_version"]),
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
        self._metadata_proof = (
            documents,
            (
                self.source_identity,
                self._audit,
                dict(self._identifiers),
                self._root,
                dict(self._bindings),
                parsed["manifest.json"],
            ),
        )

    def _verify_consistency(self):
        if self.closed:
            refuse("The captured source session is closed")
        try:
            documents = self._read_frozen_documents()
            context = (
                self.source_identity,
                self._audit,
                self._identifiers,
                self._root,
                self._bindings,
                self._manifest,
            )
            if self._metadata_proof is not None:
                proven_documents, proven_context = self._metadata_proof
                if documents != proven_documents or context != proven_context:
                    refuse("The pinned capture metadata association changed")
                return
            self._prove_frozen_metadata(documents)
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

    def payload_read_view(self):
        return CaptureReadView(self)

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
