"""Ephemeral exact-byte transport after existing complete history admission.

The observation still admits legacy reviews eagerly. Neither this session nor a
transport reference grants review, tracking, or publication authority.
"""

import os
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from uuid import uuid4

from brz2obsidian.application.checkpoint_contracts import CheckpointLocator
from brz2obsidian.contracts import ImmutableContentReference
from brz2obsidian.publication.vault_native import observe_file, verify_directory


class _Transfer:
    """Finite cooperative chunk budget; no unbounded caller callbacks."""

    def __init__(self, *, timeout, cancel):
        if type(timeout) not in (int, float) or not 0 < timeout <= 120:
            raise OSError("Content time budget must be finite and at most 120 seconds")
        if cancel is not None and not isinstance(cancel, Event):
            raise OSError("Content cancellation requires an event")
        self.deadline = time.monotonic() + timeout
        self.cancel = cancel
        self.check()

    def check(self):
        if self.cancel is not None and self.cancel.is_set():
            raise OSError("Content transfer cancelled")
        if time.monotonic() >= self.deadline:
            raise OSError("Content transfer exceeded its time budget")

    def sink(self, output, size):
        transfer = self

        class Sink:
            count = 0

            def write(self, block):
                transfer.check()
                if len(block) > 1024 * 1024 or self.count + len(block) > size:
                    raise OSError("Content exceeds its byte budget")
                if output.write(block) != len(block):
                    raise OSError("Incomplete content sink write")
                self.count += len(block)
                transfer.check()
                return len(block)

        return Sink()


class _Discard:
    def write(self, block):
        return len(block)


@dataclass(frozen=True)
class VerifiedStage:
    """Verified disposable stage; valid only while its session remains open."""

    path: Path
    reference: ImmutableContentReference
    mode: str


class ContentSession:
    """Lexical snapshots obtained from a live ``inspect_update_inputs`` reader.

    Origin selectors are requests, never authority. References are registered
    transport values (exact copies are accepted in this session), not a new core
    equality scheme. They retain their original snapshot until close. Each read
    rechecks the observation and the owned backing; a stage is not permission to
    publish it. Calls are serialized, with cooperative cancellation between
    bounded IO chunks and finite Git subprocess timeouts.
    """

    def __init__(self, observation, *, scratch_parent):
        from .vault_history import _UpdateRead

        if type(observation) is not _UpdateRead:
            raise OSError("Live input observation required")
        observation._check()
        parent = Path(scratch_parent).absolute()
        verify_directory(parent)
        if parent.resolve().is_relative_to(observation._root.resolve()):
            raise OSError("Content scratch must be outside the authored vault")
        self._observation = observation
        self._directory = Path(tempfile.mkdtemp(prefix="content-", dir=parent))
        self._anchor = verify_directory(self._directory)
        self._namespace = uuid4().hex
        self._closed = False
        self._files = {}
        self._values = {}
        self._digests = {}

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *exc):
        self.close()

    def _check(self):
        if self._closed:
            raise OSError("Content session is closed")
        self._observation._check()
        if verify_directory(self._directory) != self._anchor:
            raise OSError("Content scratch identity changed")

    def _new_file(self):
        path = self._directory / uuid4().hex
        stream = path.open("xb")
        info = os.fstat(stream.fileno())
        self._files[path] = (info.st_dev, info.st_ino)
        return path, stream

    def acquire(
        self, path, *, byte_limit, role="current", locator=None, timeout=30, cancel=None
    ):
        """Snapshot an admitted origin; caller declarations confer no trust."""
        transfer = _Transfer(timeout=timeout, cancel=cancel)
        self._check()
        transfer.check()
        if role == "current":
            if locator is not None:
                raise OSError("Current content does not accept a checkpoint locator")
            rows = self._observation.history.admission.inventory
        else:
            try:
                locator = CheckpointLocator.model_validate(locator)
            except ValueError as error:
                raise OSError("Invalid retained checkpoint locator") from error
            checkpoint = self._observation.history.checkpoint
            if (
                role
                not in ("source", "vault", "preimage", "proposed", "review_content")
                or locator != checkpoint.locator
            ):
                raise OSError("Current retained role and locator required")
            rows = getattr(checkpoint.manifest, role)
        row = next((row for row in rows if row.path == path), None)
        if row is None or getattr(row, "exclusion", None) in ("cache", "temporary"):
            raise OSError("Content path is unavailable in the admitted origin")
        self._budget(row.size, byte_limit)
        backing, output = self._new_file()
        with output:
            sink = transfer.sink(output, row.size)
            if role == "current":
                info, digest, _, identity = observe_file(
                    self._observation._root,
                    self._observation._root / row.path,
                    prefix_limit=0,
                    sink=sink,
                )
                mode = (
                    "100755"
                    if os.name != "nt" and info.st_mode & stat.S_IXUSR
                    else "100644"
                )
                if (info.st_size, digest, identity, mode) != (
                    row.size,
                    row.sha256,
                    row.identity,
                    row.mode,
                ):
                    raise OSError("Admitted current content changed")
            else:
                from .git_payload import verify_blobs
                from .vault_history import _Git

                git = _Git(
                    self._observation._root, self._observation._inspection.executable
                )
                verify_blobs(
                    [*git.prefix, "cat-file", "--batch"],
                    env=git.env,
                    objects=((row.object_id, row.size, row.sha256, sink),),
                    timeout=max(0.001, transfer.deadline - time.monotonic()),
                )
            output.flush()
            os.fsync(output.fileno())
        self._check()
        transfer.check()
        self._copy(row, backing, _Discard(), transfer)
        previous = self._digests.get(row.sha256)
        if previous is not None:
            previous_ref, previous_backing = previous
            if previous_ref.size != row.size:
                raise OSError("Content digest has contradictory sizes")
            with backing.open("rb") as stream:

                class Compare:
                    def write(self, block):
                        if stream.read(len(block)) != block:
                            raise OSError("Content digest has unequal exact bytes")
                        return len(block)

                self._copy(previous_ref, previous_backing, Compare(), transfer)
                if stream.read(1):
                    raise OSError("Content digest has unequal exact lengths")
            backing.unlink()
            del self._files[backing]
            backing = previous_backing
        reference = ImmutableContentReference(
            content_id=self._namespace + ":" + uuid4().hex,
            sha256=row.sha256,
            size=row.size,
        )
        # Distinct registrations retain their own admitted origin even when
        # equality has proved that an immutable backing can be shared.
        self._values[reference.content_id] = (
            reference,
            backing,
            row.mode,
            (role, path, locator, row),
        )
        self._digests[row.sha256] = (reference, backing)
        return reference

    def _resolve(self, reference):
        self._check()
        if not isinstance(reference, ImmutableContentReference):
            raise OSError("Registered content reference required")
        try:
            reference = ImmutableContentReference.model_validate(reference)
        except ValueError as error:
            raise OSError("Invalid content reference") from error
        value = self._values.get(reference.content_id)
        if value is None or value[0] != reference:
            raise OSError("Content reference is not registered in this session")
        return value[:3]

    def comparison(
        self,
        references,
        *,
        raw_work_limit,
        metadata_limit,
        node_limit,
        timeout=30,
        cancel=None,
    ):
        """Co-admit a fixed set of registered values for exact legacy projection."""
        from .legacy_content import ContentComparison

        return ContentComparison(
            self,
            references,
            raw_work_limit=raw_work_limit,
            metadata_limit=metadata_limit,
            node_limit=node_limit,
            timeout=timeout,
            cancel=cancel,
        )

    def _copy(self, reference, backing, sink, transfer):
        info, digest, _, _ = observe_file(
            self._directory,
            backing,
            prefix_limit=0,
            sink=transfer.sink(sink, reference.size),
        )
        if (info.st_dev, info.st_ino) != self._files.get(backing):
            raise OSError("Owned content backing identity changed")
        if (info.st_size, digest) != (reference.size, reference.sha256):
            raise OSError("Registered content integrity failed")
        self._check()
        transfer.check()

    def page(self, reference, *, offset, limit, timeout=30, cancel=None):
        """Return a finite display page only after full backing verification."""
        from .checkpoint_payload import _Page

        transfer = _Transfer(timeout=timeout, cancel=cancel)
        reference, backing, _ = self._resolve(reference)
        transfer.check()
        if (
            type(offset) is not int
            or type(limit) is not int
            or not 0 <= offset <= reference.size
            or not 0 <= limit <= 65536
            or limit == 0
            and offset < reference.size
        ):
            raise OSError("Invalid content page range")
        sink = _Page(offset, limit)
        self._copy(reference, backing, sink, transfer)
        return bytes(sink.data)

    def _budget(self, size, byte_limit):
        if type(byte_limit) is not int or not 0 <= size <= byte_limit <= (1 << 63) - 1:
            raise OSError("Content exceeds its byte budget")
        if shutil.disk_usage(self._directory).free < size:
            raise OSError("Content scratch disk budget unavailable")

    def stage(self, reference, *, byte_limit, timeout=30, cancel=None):
        """Copy to newly owned scratch; never accept an authored output path."""
        transfer = _Transfer(timeout=timeout, cancel=cancel)
        reference, backing, mode = self._resolve(reference)
        transfer.check()
        self._budget(reference.size, byte_limit)
        path, output = self._new_file()
        with output:
            self._copy(reference, backing, output, transfer)
            output.flush()
            os.fsync(output.fileno())
        self._copy(reference, path, _Discard(), transfer)
        return VerifiedStage(path, reference, mode)

    def close(self):
        """Invalidate availability and retire only owned disposable files."""
        self._closed = True
        self._values.clear()
        self._digests.clear()
        if not self._directory.exists():
            return
        try:
            if verify_directory(self._directory) != self._anchor:
                raise OSError("Content scratch identity changed")
            for path, identity in tuple(self._files.items()):
                if not path.exists():
                    continue
                info = path.lstat()
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or (info.st_dev, info.st_ino) != identity
                ):
                    raise OSError("Owned content file identity changed")
                path.unlink()
                del self._files[path]
            self._directory.rmdir()
        except OSError as error:
            raise OSError(
                f"Owned content scratch retained at {self._directory}"
            ) from error
