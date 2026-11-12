"""Ephemeral exact-byte transport after existing complete history admission.

The observation still admits legacy reviews eagerly. Neither this session nor a
transport reference grants review, tracking, or publication authority.
"""

import hashlib
import os
import shutil
import stat
import tempfile
import time
from contextlib import ExitStack, closing
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path
from threading import TIMEOUT_MAX, Event
from types import MappingProxyType
from uuid import uuid4

from brz2obsidian.application.checkpoint_contracts import CheckpointLocator
from brz2obsidian.contracts import ImmutableContentReference
from brz2obsidian.publication.vault_native import (
    _observed_chunks,
    observe_file,
    verify_directory,
)


class _Transfer:
    """Finite cooperative chunk budget; no unbounded caller callbacks."""

    def __init__(self, *, timeout, cancel, _native=False):
        maximum = TIMEOUT_MAX if _native else 120
        if type(timeout) not in (int, float) or not 0 < timeout <= maximum:
            raise OSError(
                f"Content time budget must be finite and at most {maximum} seconds"
            )
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


@dataclass(frozen=True, eq=False)
class _PreparedRegistration:
    session: object
    reference: ImmutableContentReference
    backing: Path
    mode: str
    origin: tuple
    published_input: bool = False


@dataclass(frozen=True, init=False)
class _RegistrationView:
    """Closed view of actual owner-minted records, never caller path mappings."""

    session: object
    scope: object
    records: object

    def __init__(self, session, records, scope):
        if type(session) is not ContentSession:
            raise OSError("Actual content owner required")
        session._require_private_scope(scope)
        rows = {}
        for record in records:
            session._check_prepared(record, scope)
            previous = rows.get(record.reference.content_id)
            if previous is not None and previous is not record:
                raise OSError("Conflicting prepared registration")
            rows[record.reference.content_id] = record
        object.__setattr__(self, "session", session)
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "records", MappingProxyType(rows))

    def check(self, session):
        if session is not self.session:
            raise OSError("Registration view belongs to another owner")
        self.session._require_private_scope(self.scope)

    def resolve(self, reference):
        self.check(self.session)
        record = self.records.get(reference.content_id)
        if record is None or record.reference != reference:
            raise OSError("Content is outside the verified registration view")
        self.session._check_prepared(record, self.scope)
        return record.reference, record.backing, record.mode


class _RetainedReviewRead:
    """Owned retained bytes during admission, never current-vault authority."""

    def __init__(self, git, manifest, commit, *, capacity, envelope_size):
        from brz2obsidian.application.checkpoint_contracts import CheckpointManifest

        from .vault_history import _Git

        if (
            type(git) is not _Git
            or type(manifest) is not CheckpointManifest
            or type(commit) is not str
            or len(commit) != 40
            or set(commit) - set("0123456789abcdef")
            or type(capacity) is not int
            or capacity < 0
        ):
            raise OSError("Actual retained Git reader required")
        self._root = git.root
        self._anchors = (
            verify_directory(self._root),
            verify_directory(self._root / ".git"),
        )
        self.git, self.manifest, self.commit = git, manifest, commit
        self.capacity, self.envelope_size = capacity, envelope_size
        self.semantic_size = 0
        self._open = True

    def _check(self):
        if not self._open or self._anchors != (
            verify_directory(self._root),
            verify_directory(self._root / ".git"),
        ):
            raise OSError("Retained review byte owner is no longer live")

    def reserve_semantic(self, size):
        if (
            4 * self.envelope_size + 9 * (self.semantic_size + size) + 64 * 1024 * 1024
            > self.capacity
        ):
            raise OSError("Insufficient current memory for retained semantic bytes")
        self.semantic_size += size


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
        self._initialize(observation, scratch_parent)

    def _initialize(self, observation, scratch_parent):
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
        self._private_operation = None
        self._prepared = {}
        self._prepared_digests = {}
        self._retained_semantic = {}

    @classmethod
    def _retained_review(cls, git, manifest, commit, *, capacity, envelope_size):
        observation = _RetainedReviewRead(
            git,
            manifest,
            commit,
            capacity=capacity,
            envelope_size=envelope_size,
        )
        parent = git.inspection.temporary_base()
        if parent is None:
            raise OSError("Retained review temporary storage unavailable")
        result = cls.__new__(cls)
        result._initialize(observation, parent)
        return result

    def _prepare_retained(self, available, references, ledger, scope):
        """Mint records only after real Git has streamed and verified every file."""
        from .git_payload import verify_blobs

        self._require_private_scope(scope, ledger)
        source = self._observation
        if type(source) is not _RetainedReviewRead:
            raise OSError("Retained review byte owner required")
        self._budget(sum(available[sha][1] for sha in references), (1 << 63) - 1)

        class Sink:
            def __init__(self, output):
                self.output = output

            def write(self, block):
                ledger.check()
                written = self.output.write(block)
                ledger.check()
                return written

        paths = {}
        ordered = sorted(references)
        for offset in range(0, len(ordered), 32):
            batch, outputs = ordered[offset : offset + 32], {}
            with ExitStack() as streams:
                for sha in batch:
                    ledger.reserve_file_cleanup()
                    ledger.retain_metadata(848)
                    ledger.raw_pass(available[sha][1])
                    paths[sha], outputs[sha] = self._new_file()
                    streams.callback(outputs[sha].close)
                verify_blobs(
                    [*source.git.prefix, "cat-file", "--batch"],
                    env=source.git.env,
                    objects=tuple(
                        (available[sha][0], available[sha][1], sha, Sink(outputs[sha]))
                        for sha in batch
                    ),
                    timeout=min(120, max(0.001, ledger.deadline - time.monotonic())),
                )
                for output in outputs.values():
                    ledger.check()
                    output.flush()
                    os.fsync(output.fileno())
        records = {}
        for sha in sorted(references):
            oid, size = available[sha]
            reference = ImmutableContentReference(
                content_id=self._namespace + ":" + uuid4().hex,
                sha256=sha,
                size=size,
            )
            roles = tuple(
                (role, row.path)
                for role in (
                    "source",
                    "vault",
                    "preimage",
                    "proposed",
                    "review_content",
                )
                for row in getattr(source.manifest, role)
                if row.object_id == oid
            )
            origin = (
                "retained_git_review",
                source.manifest.association_id,
                source.commit,
                roles,
                oid,
            )
            record = _PreparedRegistration(
                self, reference, paths[sha], "100644", origin
            )
            self._prepared[reference.content_id] = record
            records[sha] = record
        return records

    def _retained_semantic_bytes(self, registration, ledger, scope):
        if type(self._observation) is not _RetainedReviewRead:
            return None
        try:
            self._check_prepared(registration, scope)
            backing, reference = registration.backing, registration.reference
            if backing in self._retained_semantic:
                # A cached value is available only after another complete read
                # proves its correspondence with this exact owned backing.
                data = self._retained_semantic[backing]
                position, equal = 0, True
                with closing(
                    self._read_owned(backing, reference, ledger, scope)
                ) as chunks:
                    for block in chunks:
                        equal = (
                            data[position : position + len(block)] == block
                        ) and equal
                        position += len(block)
                if not equal or position != len(data):
                    raise OSError("Cached semantic bytes differ from owned backing")
                return data, False
            self._observation.reserve_semantic(reference.size)
            raw = bytearray()
            with closing(self._read_owned(backing, reference, ledger, scope)) as chunks:
                for block in chunks:
                    raw.extend(block)
            data = bytes(raw)
            self._retained_semantic[backing] = data
            return data, True
        except BaseException:
            self._retained_semantic.clear()
            raise

    def _clear_retained_semantic(self):
        self._retained_semantic.clear()

    def _discard_fresh_scope(self):
        if type(self._observation) not in (_RetainedReviewRead, _ContentOnlyRead):
            self._observation._discard_fresh_scope()

    def _require_current_observation(self):
        from .vault_history import _UpdateRead

        if type(self._observation) is not _UpdateRead:
            raise OSError(
                "Retained review bytes confer no current observation authority"
            )
        return self._observation

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
        stream = path.open("xb", buffering=0)
        info = os.fstat(stream.fileno())
        self._files[path] = (info.st_dev, info.st_ino)
        return path, stream

    def _import_physical(self, root, row, ledger, scope):
        """Register an actual rendered file; a declaration alone is insufficient."""
        self._require_private_scope(scope, ledger)
        root = Path(root).absolute()
        anchor = verify_directory(root)
        ledger.reserve_file_cleanup()
        backing, output = self._new_file()
        transfer = _Transfer(
            timeout=min(120, max(0.001, ledger.deadline - time.monotonic())),
            cancel=ledger.budget.cancel,
        )
        ledger.raw_pass(row.size)
        with output:
            info, sha, _, identity = observe_file(
                root,
                root / row.path,
                prefix_limit=0,
                sink=transfer.sink(output, row.size),
                expected_size=row.size,
                read_chunk_limit=65536,
            )
            output.flush()
            os.fsync(output.fileno())
        mode = "100755" if os.name != "nt" and info.st_mode & stat.S_IXUSR else "100644"
        if (info.st_size, sha, mode) != (
            row.size,
            row.sha256,
            getattr(row, "mode", mode),
        ) or verify_directory(root) != anchor:
            raise OSError("Rendered input changed during owned acquisition")
        reference = ImmutableContentReference(
            content_id=self._namespace + ":" + uuid4().hex,
            sha256=sha,
            size=info.st_size,
        )
        self._values[reference.content_id] = (
            reference,
            backing,
            mode,
            ("rendered_source", str(root), anchor, row.path, identity, row),
        )
        with closing(self._read_owned(backing, reference, ledger, scope)) as chunks:
            for _ in chunks:
                pass
        return reference

    def _detach(self):
        if self._private_operation is not None:
            raise OSError("Content must leave its operation before publication")
        self._check()
        self._observation.__exit__()
        self._observation = _ContentOnlyRead(self)

    def _attach(self, observed):
        from .vault_history import _UpdateRead

        if self._private_operation is not None or type(observed) is not _UpdateRead:
            raise OSError("Actual idle observation required for owner handoff")
        self._check()
        observed._check()
        if self._observation._root != observed._root:
            raise OSError("Content owner cannot change vault")
        self._observation._open = False
        self._observation = observed

    def _operation(self, ledger):
        return _PrivateOperation(self, ledger)

    def _begin_decoded(self, record, occurrence, ledger, scope):
        """Private untrusted-byte ingress, never a path/manifest admission API."""
        scope.check(self)
        ledger.check()
        if type(record) is not str or not record or type(occurrence) is not tuple:
            raise OSError("Invalid decoded-input origin")
        return _DecodedImport(self, record, occurrence, ledger, scope)

    def _prepare_decoded(self, record, occurrence, ledger, scope):
        self._require_private_scope(scope, ledger)
        if type(record) is not str or not record or type(occurrence) is not tuple:
            raise OSError("Invalid decoded-input origin")
        return _DecodedImport(self, record, occurrence, ledger, scope, prepare=True)

    def _begin_created(self, request, occurrence, ledger, scope):
        from brz2obsidian.content_fingerprints import CreatedRequest

        self._require_private_scope(scope, ledger)
        if type(request) is not CreatedRequest or request.token.kind != "created":
            raise OSError("Actual Created request required")
        if type(request.size) is not int or not 0 <= request.size <= ledger.remaining(
            "decoded"
        ):
            raise OSError("Created output exceeds remaining generated-byte credit")
        self._budget(request.size, request.size)
        return _DecodedImport(
            self, "created", occurrence, ledger, scope, prepare=True, created=request
        )

    def _check_prepared(self, record, scope):
        self._require_private_scope(scope)
        if (
            type(record) is not _PreparedRegistration
            or record.session is not self
            or self._prepared.get(record.reference.content_id) is not record
        ):
            raise OSError("Registration was not prepared by this content owner")
        info = record.backing.lstat()
        if self._files.get(record.backing) != (info.st_dev, info.st_ino):
            raise OSError("Prepared backing identity changed")
        if record.published_input and self._values.get(record.reference.content_id) != (
            record.reference,
            record.backing,
            record.mode,
            record.origin,
        ):
            raise OSError("Physical registration origin changed")

    def _prepare_registered(self, reference, ledger, scope):
        self._require_private_scope(scope, ledger)
        self._registered(reference)
        previous = self._prepared.get(reference.content_id)
        if previous is not None:
            self._check_prepared(previous, scope)
            return previous
        ledger.retain_metadata(512)
        row = self._values[reference.content_id]
        record = _PreparedRegistration(self, *row, published_input=True)
        self._prepared[reference.content_id] = record
        return record

    def _registration_view(self, records, ledger, scope):
        self._require_private_scope(scope, ledger)
        ledger.retain_metadata(512 + 80 * len(records))
        return _RegistrationView(self, records, scope)

    def _require_private_scope(self, scope, ledger=None):
        if (
            type(self) is not ContentSession
            or type(scope) is not _PrivateOperation
            or scope.session is not self
            or ledger is not None
            and scope.ledger is not ledger
        ):
            raise OSError("Actual live owned content operation required")
        scope.check(self)

    def _read_owned(self, backing, reference, ledger, scope):
        if type(scope) is _PrivateOperation:
            scope._check_live(self)
        else:
            scope.check(self)
        ledger.check()
        ledger.raw_pass(reference.size)

        def chunks():
            scope.check(self)
            ledger.check()
            expected = self._files.get(backing)
            info = backing.lstat()
            if (info.st_dev, info.st_ino) != expected:
                raise OSError("Owned backing identity changed")
            with closing(
                _observed_chunks(
                    self._directory,
                    backing,
                    expected_size=reference.size,
                    read_chunk_limit=65536,
                )
            ) as observed:
                while True:
                    ledger.check()
                    try:
                        block = next(observed)
                    except StopIteration as complete:
                        info, digest, _ = complete.value
                        if (
                            info.st_dev,
                            info.st_ino,
                        ) != expected or digest != reference.sha256:
                            raise OSError("Registered content integrity failed")
                        break
                    yield block
            scope.check(self)
            ledger.check()

        # Reserve this complete pass at construction, including when a second
        # reader will be constructed before either stream starts consuming.
        return chunks()

    def _stage_decoded(self, reference, ledger, scope):
        reference, backing, mode = scope.resolve(reference)
        self._budget(reference.size, reference.size)
        ledger.reserve_file_cleanup()
        path, output = self._new_file()
        with (
            output,
            closing(self._read_owned(backing, reference, ledger, scope)) as chunks,
        ):
            for block in chunks:
                if output.write(block) != len(block):
                    raise OSError("Incomplete stage write")
            output.flush()
            os.fsync(output.fileno())
        with closing(self._read_owned(path, reference, ledger, scope)) as chunks:
            for _ in chunks:
                pass
        return VerifiedStage(path, reference, mode)

    def acquire(
        self, path, *, byte_limit, role="current", locator=None, timeout=30, cancel=None
    ):
        """Snapshot an admitted origin; caller declarations confer no trust."""
        return self._acquire(
            path,
            byte_limit=byte_limit,
            role=role,
            locator=locator,
            timeout=timeout,
            cancel=cancel,
        )

    def _acquire_current(self, path, ledger, scope):
        """Current acquisition with cumulative native read-capacity accounting."""
        scope.check(self)
        return self._acquire(
            path,
            byte_limit=ledger.remaining("raw_work"),
            role="current",
            timeout=min(120, max(0.001, ledger.deadline - time.monotonic())),
            cancel=ledger.budget.cancel,
            ledger=ledger,
            scope=scope,
        )

    def _acquire(
        self,
        path,
        *,
        byte_limit,
        role,
        locator=None,
        timeout=30,
        cancel=None,
        ledger=None,
        scope=None,
    ):
        if type(self._observation) in (_RetainedReviewRead, _ContentOnlyRead):
            raise OSError(
                "Retained review bytes confer no current acquisition authority"
            )
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
                checkpoint is None
                or checkpoint.status != "valid"
                or role
                not in ("source", "vault", "preimage", "proposed", "review_content")
                or locator != checkpoint.locator
            ):
                raise OSError("Current retained role and locator required")
            rows = getattr(checkpoint.manifest, role)
        row = next((row for row in rows if row.path == path), None)
        if row is None or getattr(row, "exclusion", None) in ("cache", "temporary"):
            raise OSError("Content path is unavailable in the admitted origin")
        self._budget(row.size, byte_limit)
        if ledger is not None:
            ledger.reserve_file_cleanup()
        backing, output = self._new_file()
        with output:
            sink = transfer.sink(output, row.size)
            if role == "current":
                bounded = {}
                if ledger is not None:
                    ledger.raw_pass(row.size)
                    bounded = {"expected_size": row.size, "read_chunk_limit": 65536}
                info, digest, _, identity = observe_file(
                    self._observation._root,
                    self._observation._root / row.path,
                    prefix_limit=0,
                    sink=sink,
                    **bounded,
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
                    timeout=min(120, max(0.001, transfer.deadline - time.monotonic())),
                )
            output.flush()
            os.fsync(output.fileno())
        self._check()
        transfer.check()
        if ledger is None:
            self._copy(row, backing, _Discard(), transfer)
        else:
            with closing(self._read_owned(backing, row, ledger, scope)) as chunks:
                for _ in chunks:
                    pass
        previous = self._digests.get(row.sha256)
        if previous is not None:
            previous_ref, previous_backing = previous
            if previous_ref.size != row.size:
                raise OSError("Content digest has contradictory sizes")
            if ledger is not None:
                with (
                    closing(self._read_owned(backing, row, ledger, scope)) as left,
                    closing(
                        self._read_owned(previous_backing, previous_ref, ledger, scope)
                    ) as right,
                ):
                    for a, b in zip_longest(left, right):
                        if a != b:
                            raise OSError("Content digest has unequal exact bytes")
            else:
                self._compare_backings(
                    backing, previous_ref, previous_backing, transfer
                )
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

    def _compare_backings(self, backing, previous_ref, previous_backing, transfer):
        with backing.open("rb") as stream:

            class Compare:
                def write(self, block):
                    if stream.read(len(block)) != block:
                        raise OSError("Content digest has unequal exact bytes")
                    return len(block)

            self._copy(previous_ref, previous_backing, Compare(), transfer)
            if stream.read(1):
                raise OSError("Content digest has unequal exact lengths")

    def _resolve(self, reference):
        self._check()
        return self._registered(reference)

    def _registered(self, reference):
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
        self._clear_retained_semantic()
        if type(self._observation) is _RetainedReviewRead:
            self._observation._open = False
        if self._private_operation is not None:
            self._private_operation.active = False
            self._private_operation = None
        self._values.clear()
        self._digests.clear()
        self._prepared.clear()
        self._prepared_digests.clear()
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


class _DecodedImport:
    """One owned transaction; declarations never determine its byte identity."""

    def __init__(
        self, session, record, occurrence, ledger, scope, *, prepare=False, created=None
    ):
        if prepare:
            session._require_private_scope(scope, ledger)
            ledger.retain_metadata(848)
        self.session, self.record, self.occurrence, self.ledger = (
            session,
            record,
            occurrence,
            ledger,
        )
        ledger.reserve_file_cleanup()
        self.path, self.stream = session._new_file()
        self.digest, self.size = hashlib.sha256(), 0
        self.finished = False
        self.scope = scope
        self.prepare, self.created = prepare, created

    def write(self, block):
        self.scope.check(self.session)
        self.ledger.check()
        if self.finished or type(block) is not bytes or len(block) > 65536:
            raise OSError("Invalid decoded-input chunk")
        if self.created is not None and self.size + len(block) > self.created.size:
            raise OSError("Created write exceeds its exact recipe size")
        self.ledger.take("decoded", len(block))
        self.session._budget(len(block), len(block))
        if self.stream.write(block) != len(block):
            raise OSError("Incomplete decoded-input write")
        self.digest.update(block)
        self.size += len(block)

    def finish(self, historical_reference):
        self.scope.check(self.session)
        if self.finished:
            raise OSError("Decoded-input transaction is finished")
        self.finished = True
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.stream.close()
        digest = self.digest.hexdigest()
        if historical_reference is not None and (
            historical_reference.size != self.size
            or historical_reference.sha256 != digest
        ):
            raise OSError("Historical reference differs from decoded bytes")
        reference = ImmutableContentReference(
            content_id=self.session._namespace + ":" + uuid4().hex,
            sha256=digest,
            size=self.size,
        )
        with closing(
            self.session._read_owned(self.path, reference, self.ledger, self.scope)
        ) as chunks:
            for _ in chunks:
                pass
        backing = self.path
        if self.prepare:
            if self.created is not None and self.size != self.created.size:
                raise OSError("Created output differs from its recipe size")
            origin = (
                ("CREATED", self.created, self.occurrence)
                if self.created is not None
                else ("untrusted_review_input", self.record, self.occurrence)
            )
            previous = self.session._prepared_digests.get(digest)
            if previous is not None:
                self.session._check_prepared(previous, self.scope)
                if previous.reference.size != self.size:
                    raise OSError("Prepared digest has contradictory sizes")
                with (
                    closing(
                        self.session._read_owned(
                            previous.backing,
                            previous.reference,
                            self.ledger,
                            self.scope,
                        )
                    ) as left,
                    closing(
                        self.session._read_owned(
                            backing,
                            reference,
                            self.ledger,
                            self.scope,
                        )
                    ) as right,
                ):
                    for a, b in zip_longest(left, right):
                        if a != b:
                            raise OSError("Prepared digest has unequal exact bytes")
                backing = previous.backing
            record = _PreparedRegistration(
                self.session, reference, backing, "100644", origin
            )
            if reference.content_id in self.session._prepared:
                raise OSError("Prepared registration identity was already used")
            self.session._prepared[reference.content_id] = record
            self.session._prepared_digests[digest] = record
            return record
        previous = self.session._digests.get(digest)
        if previous is not None:
            prior, prior_backing = previous
            if prior.size != self.size:
                raise OSError("Content digest has contradictory sizes")
            with (
                closing(
                    self.session._read_owned(
                        prior_backing, prior, self.ledger, self.scope
                    )
                ) as left,
                closing(
                    self.session._read_owned(
                        backing, reference, self.ledger, self.scope
                    )
                ) as right,
            ):
                for a, b in zip_longest(left, right):
                    if a != b:
                        raise OSError("Content digest has unequal exact bytes")
            backing = prior_backing
        self.session._values[reference.content_id] = (
            reference,
            backing,
            "100644",
            ("untrusted_review_input", self.record, self.occurrence),
        )
        self.session._digests[digest] = reference, backing
        return reference

    def abort(self):
        self.finished = True
        self.stream.close()


class _ContentOnlyRead:
    """Availability of the same owned files, with no native acquisition grant."""

    def __init__(self, owner):
        self._owner = owner
        self._root = owner._observation._root
        self._open = True

    def _check(self):
        if (
            not self._open
            or self._owner._closed
            or verify_directory(self._owner._directory) != self._owner._anchor
        ):
            raise OSError("Owned content-only snapshot is unavailable")


class _PrivateOperation:
    """One non-reentrant scratch operation, bracketed by live observation checks.

    Public ContentSession operations never consult or inherit this capability.
    It cannot refresh a source observation or authorize an origin acquisition.
    """

    def __init__(self, session, ledger):
        if session._private_operation is not None:
            raise OSError("Nested private content operation")
        session._check()
        ledger.check()
        self.session, self.ledger, self.active = session, ledger, True
        session._private_operation = self

    def __enter__(self):
        self.check(self.session)
        return self

    def _check_live(self, session):
        """Check lexical identity and cancellation without filesystem IO."""
        if (
            session is not self.session
            or not self.active
            or session._closed
            or session._private_operation is not self
            or not session._observation._open
        ):
            raise OSError("Private content operation is no longer live")
        self.ledger.check()

    def check(self, session):
        self._check_live(session)
        if verify_directory(session._directory) != session._anchor:
            raise OSError("Content scratch identity changed")

    def resolve(self, reference):
        self.check(self.session)
        return self.session._registered(reference)

    def __exit__(self, kind, error, traceback):
        try:
            if kind is None:
                self.check(self.session)
                self.session._check()
                self.ledger.check()
        finally:
            self.active = False
            self.session._private_operation = None
