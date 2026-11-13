"""Finite owned-capture reads, separate from forceful standalone verification."""

import hashlib
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass, replace
from threading import get_ident

from brz2obsidian.contracts import MigrationFailed, MigrationRefused

from .capture import canonical, parse_json
from .errors import failure, refuse


def with_secondary(primary, secondary):
    """Retain the primary class and ordered safe findings during finalization.

    Only source-owned typed failures are supplied as secondary errors. Caller
    exceptions and control signals retain their identity with safe code notes;
    arbitrary underlying exception text is never included.
    """
    if isinstance(primary, (MigrationFailed, MigrationRefused)):
        return type(primary)(primary.issues + secondary.issues, primary.receipt)
    primary.add_note(
        "Additional captured-source failure: "
        + ", ".join(issue.code for issue in secondary.issues)
    )
    return primary


def _context_values(session):
    return {
        "snapshot": session.snapshot.model_dump(mode="json"),
        "audit": session._audit.model_dump(mode="json"),
        "identifiers": session._identifiers,
        "root": session._root,
        "bindings": session._bindings,
        "manifest": session._manifest,
        "manifest_bytes": session._manifest_bytes,
    }


def _encode_context(values):
    return canonical({**values, "manifest_bytes": values["manifest_bytes"].hex()})


def context_bytes(session):
    return _encode_context(_context_values(session))


def _freeze_context(value):
    kind = type(value)
    if kind in (type(None), bool, int, str, bytes):
        return kind, value
    if kind is list:
        return tuple, tuple(_freeze_context(child) for child in value)
    if kind is dict and all(type(key) is str for key in value):
        return dict, tuple(
            (key, _freeze_context(child)) for key, child in value.items()
        )
    raise TypeError("Unsupported comparison pin")


def _comparison_pin(context):
    try:
        # Derive both proofs from the exact same immutable admitted bytes, not
        # another observation of mutable session fields or an aliased dictionary.
        values = parse_json(context.decode("utf-8"))
        manifest = bytes.fromhex(values["manifest_bytes"])
        if manifest.hex() != values["manifest_bytes"]:
            return None
        values["manifest_bytes"] = manifest
        return _freeze_context(values)
    except Exception:  # noqa: BLE001 - An unavailable optimization retains the original byte pin.
        return None


def _matches_context(value, pin):
    kind, expected = pin
    if kind is tuple:
        return (
            type(value) in (list, tuple)
            and len(value) == len(expected)
            and all(
                _matches_context(child, frozen)
                for child, frozen in zip(value, expected)
            )
        )
    if kind is dict:
        return (
            type(value) is dict
            and len(value) == len(expected)
            and all(type(key) is str for key in value)
            and all(
                key in value and _matches_context(value[key], child)
                for key, child in expected
            )
        )
    return type(value) is kind and value == expected


def _context_unchanged(session, pins):
    # Model projection remains fresh, once per check. Projection failures retain
    # their old failure path rather than being retried by the optimization.
    values = _context_values(session)
    if pins.comparison is not None:
        try:
            if _matches_context(values, pins.comparison):
                return True
        except Exception:  # noqa: BLE001 - Only comparison errors fall back; fresh model projection is outside this handler.
            pass
    return _encode_context(values) == pins.context


def ordinary(path, *, directory=False):
    info = path.lstat()
    if (
        path.is_symlink()
        or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
    ):
        refuse("The captured read path is not safe")
    return info.st_dev, info.st_ino


@dataclass(frozen=True)
class ReadPins:
    directory: object
    owner: tuple
    payload_owner: tuple | None
    context: bytes
    documents: tuple
    bindings: tuple
    files: tuple
    comparison: tuple | None = None


class CaptureReadView:
    """One sequential, thread-owned read interval with entry/exit full scans.

    Metadata is checked at use; payload bytes are hashed as actually returned.
    A transient change to an unread payload between complete checks is outside
    this capability's observation boundary. No payload contents are cached.
    """

    def __init__(self, session):
        self.session = session
        self.entered = self.closed = self.failed = False
        self.stream = None

    def __enter__(self):
        if self.entered or self.closed or self.failed or self.session.closed:
            self.failed = True
            refuse("The captured read view cannot be reused")
        if not self.session._read_lock.acquire(blocking=False):
            self.failed = self.closed = True
            refuse("Nested or concurrent captured read views are unsupported")
        self.entered = True
        self.thread = get_ident()
        self.session._read_view = self
        try:
            self.session.verify_consistency()
            directory = self.session._directory
            pins = ReadPins(
                directory,
                self.session._ownership,
                ordinary(directory / "payload", directory=True)
                if self.session._bindings
                else None,
                context_bytes(self.session),
                tuple(self.session._metadata_proof[0].items()),
                tuple(self.session._bindings.items()),
                tuple(
                    (
                        entry["storage_key"],
                        (entry["actual_length"], entry["actual_sha256"]),
                    )
                    for entry in self.session._manifest["files"]
                ),
            )
            self.pins = replace(pins, comparison=_comparison_pin(pins.context))
            return self
        except BaseException as error:
            self.failed = self.closed = True
            self.session._read_view = None
            self.session._read_lock.release()
            if isinstance(
                error, (OSError, ValueError, KeyError, TypeError, RecursionError)
            ):
                raise failure(
                    "api_capture_read_failed",
                    "Captured read view could not be opened safely",
                ) from None
            raise

    def check(self):
        try:
            if (
                not self.entered
                or self.closed
                or self.failed
                or self.session.closed
                or self.session._read_view is not self
                or self.thread != get_ident()
            ):
                refuse("The captured read view is closed, failed or unavailable")
            if (
                self.session._directory != self.pins.directory
                or self.session._ownership != self.pins.owner
                or ordinary(self.pins.directory, directory=True) != self.pins.owner
                or not _context_unchanged(self.session, self.pins)
            ):
                refuse("The pinned capture association changed")
            for name, expected in self.pins.documents:
                path = self.pins.directory / name
                ordinary(path)
                # Read at most the pinned length plus one, never unbounded
                # replacement metadata supplied after view admission.
                with path.open("rb") as stream:
                    if stream.read(len(expected) + 1) != expected:
                        refuse("The pinned capture metadata changed")
        except OSError, ValueError, KeyError, TypeError, RecursionError:
            self.failed = True
            raise failure(
                "api_capture_read_failed",
                "Captured read pins could not be checked safely",
            ) from None
        except BaseException:
            self.failed = True
            raise

    @contextmanager
    def open_payload(self, asset_id):
        self.check()
        try:
            if self.stream is not None:
                refuse("Concurrent captured payload reads are unsupported")
            key = dict(self.pins.bindings).get(asset_id)
            if key is None:
                refuse("The requested captured payload is unknown or unavailable")
            # Keys were qualified at capture construction and the entire
            # binding/manifest context is pinned above; check real path owners.
            if (
                ordinary(self.pins.directory / "payload", directory=True)
                != self.pins.payload_owner
            ):
                refuse("The captured payload directory changed")
            path = self.pins.directory / key
            owner = ordinary(path)
            raw = path.open("rb")
            try:
                opened = os.fstat(raw.fileno())
                if (
                    ordinary(path) != owner
                    or (opened.st_dev, opened.st_ino) != owner
                    or not stat.S_ISREG(opened.st_mode)
                ):
                    refuse("The selected captured payload changed while opening")
            except BaseException:
                raw.close()
                raise
            self.stream = stream = VerifiedStream(
                raw, self, path, owner, dict(self.pins.files)[key]
            )
            self.session._streams.append(stream)
        except OSError, ValueError, KeyError, TypeError:
            self.failed = True
            raise failure(
                "api_payload_read_failed", "Captured payload could not be used safely"
            ) from None
        except BaseException:
            self.failed = True
            raise
        try:
            try:
                yield stream
            except BaseException as primary:
                self.failed = True
                try:
                    stream.close()
                except (MigrationFailed, MigrationRefused) as secondary:
                    raise with_secondary(primary, secondary) from None
                raise
            else:
                stream.close()
        finally:
            # A failed close can leave the descriptor open. Keep it registered
            # so session teardown can revoke/retry it.
            if stream.closed:
                self.session._streams.remove(stream)
            self.stream = None

    def __exit__(self, *exc):
        if not self.entered or self.closed or self.thread != get_ident():
            self.failed = True
            refuse("The captured read view cannot close from this context")
        primary = exc[1]
        try:
            if exc[0] is not None:
                self.failed = True
            try:
                if self.stream is not None:
                    self.failed = True
                    self.stream.close()
            except BaseException as closing:  # noqa: BLE001 - retain the primary/control exception while forcing complete final verification.
                primary = (
                    with_secondary(primary, closing)
                    if primary is not None
                    and isinstance(closing, (MigrationFailed, MigrationRefused))
                    else closing
                )
                raise primary from None
            finally:
                # Also verify after stream-close failures; output validation
                # cannot begin until this original complete check finishes.
                try:
                    self.session.verify_consistency()
                except (MigrationFailed, MigrationRefused) as secondary:
                    if primary is not None:
                        raise with_secondary(primary, secondary) from None
                    raise
            if self.failed and exc[0] is None:
                refuse("The captured read view failed and cannot be reused")
        finally:
            self.closed = True
            self.session._read_view = None
            self.session._read_lock.release()


class VerifiedStream:
    def __init__(self, raw, view, path, owner, expected):
        self.raw, self.view, self.path, self.owner = raw, view, path, owner
        self.length, self.sha256 = expected
        self.count, self.hasher = 0, hashlib.sha256()
        self.finished = False

    @property
    def closed(self):
        return self.raw.closed

    def read(self, size=-1):
        try:
            self.view.check()
            if self.closed or ordinary(self.path) != self.owner:
                refuse("The captured payload stream is closed or changed")
            # Never ask the underlying file for more than a bounded block.
            # An unbounded caller read still requests an assembled bytes result;
            # the publisher uses fixed-size reads and retains no payload cache.
            chunks = []
            remaining = size
            while remaining != 0:
                block = self.raw.read(65536 if remaining < 0 else min(65536, remaining))
                self.count += len(block)
                self.hasher.update(block)
                if self.count > self.length:
                    refuse("Captured payload length changed")
                if not block:
                    if (
                        self.count != self.length
                        or self.hasher.hexdigest() != self.sha256
                    ):
                        refuse("Captured payload bytes changed")
                    self.finished = True
                    break
                chunks.append(block)
                if remaining > 0:
                    remaining -= len(block)
            return b"".join(chunks)
        except OSError, ValueError:
            self.view.failed = True
            raise failure(
                "api_payload_read_failed", "Captured payload could not be read safely"
            ) from None
        except BaseException:
            self.view.failed = True
            raise

    def close(self):
        if self.closed:
            return
        try:
            # An early close still checks the consumed prefix and boundedly
            # drains the remaining bytes. A revoked/failed view cannot succeed.
            if self.view.session.closed or self.view.failed:
                self.view.failed = True
            else:
                while not self.finished:
                    self.read(65536)
        finally:
            try:
                self.raw.close()
            except OSError, ValueError:
                self.view.failed = True
                raise failure(
                    "api_payload_read_failed",
                    "Captured payload stream could not close safely",
                ) from None
