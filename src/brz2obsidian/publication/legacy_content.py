"""Bounded old JSON proof projections over one co-admitted content closure.

Names and projection hashes are values, never availability or review authority.
The core receives no reader, callback, or serialized admission capability.

Opaque buffer bound: at most two transient 64 KiB read blocks, a 64 KiB+2
combined block and slice, two <88 KiB base64/translation temporaries, two
64 KiB preview copies and two residual bytes: less than 1 MiB. A two-stream
comparison needs at most four 64 KiB transient blocks and runs separately.
Metadata tokens/sorting are explicitly budgeted M; no payload queue is retained.
"""

import base64
import hashlib
import json
from contextlib import closing
from dataclasses import dataclass
from itertools import zip_longest

from brz2obsidian.content_fingerprints import LegacyObject
from brz2obsidian.contracts import ContentIdentity, ImmutableContentReference
from brz2obsidian.publication.content_session import (
    ContentSession,
    _MemoryBacking,
    _Transfer,
)
from brz2obsidian.publication.vault_native import _observed_chunks

_MAX = (1 << 63) - 1
_CHUNK = 65536


def _limit(value, name, *, minimum=0, maximum=_MAX):
    if type(value) is not int or not minimum <= value <= maximum:
        raise OSError(f"Invalid {name} budget")
    return value


@dataclass(frozen=True)
class LegacyContentSlot:
    transport_reference: ImmutableContentReference
    legacy_reference: ImmutableContentReference | None


@dataclass(frozen=True)
class LegacyProjectionEvidence:
    dialect: str
    sha256: str
    encoded_size: int
    preview: bytes


class _RawWork:
    def __init__(self, limit, ledger=None):
        self.ledger = ledger
        self.remaining = _limit(limit, "raw work")

    def reserve(self, size):
        if size + 1 > self.remaining:
            raise OSError("Raw work budget exhausted")
        if self.ledger is not None:
            self.ledger.raw_pass(size)
        self.remaining -= size + 1


def _reference(value):
    if type(value) is not ImmutableContentReference:
        raise OSError("An exact registered reference value is required")
    try:
        return ImmutableContentReference.model_validate(value)
    except ValueError as error:
        raise OSError("Invalid reference value") from error


def _reference_node(reference):
    return LegacyObject(
        (
            ("content_id", reference.content_id),
            ("sha256", reference.sha256),
            ("size", reference.size),
        )
    )


class _Projection:
    """Snapshot bounded metadata tokens and registered slots before any reads."""

    def __init__(
        self,
        root,
        member,
        transfer,
        *,
        metadata_limit,
        node_limit,
        depth_limit,
        dialect="Jc",
        ledger=None,
        _native=False,
    ):
        self.ledger = ledger
        self.maximum = _limit(metadata_limit, "metadata")
        self.nodes_left = _limit(node_limit, "node", minimum=1)
        self.depth = _limit(
            depth_limit, "depth", minimum=1, maximum=_MAX if _native else 256
        )
        self.metadata = self.payload = 0
        self.tokens = []
        self.active = set()
        self.member = member
        self.transfer = transfer
        self.dialect = dialect
        self.comma = b"," if dialect == "Jc" else b", "
        self.colon = b":" if dialect == "Jc" else b": "
        self.walk(root, 1)

    def emit(self, data):
        self.transfer.check()
        if self.metadata + len(data) > self.maximum:
            raise OSError("Metadata budget exhausted")
        if self.ledger is not None:
            self.ledger.retain_metadata(len(data) + 16)
        self.metadata += len(data)
        self.tokens.append(data)

    def string(self, value):
        if len(value) + 2 > self.maximum - self.metadata:
            raise OSError("Metadata budget exhausted")
        self.emit(b'"')
        for start in range(0, len(value), 4096):
            self.emit(
                json.dumps(value[start : start + 4096], ensure_ascii=True)[1:-1].encode(
                    "ascii"
                )
            )
        self.emit(b'"')

    def walk(self, value, depth):
        self.transfer.check()
        if depth > self.depth or self.nodes_left == 0:
            raise OSError("Node or depth budget exhausted")
        self.nodes_left -= 1
        if self.ledger is not None:
            self.ledger.node(depth)
        kind = type(value)
        if value is None:
            self.emit(b"null")
        elif kind is bool:
            self.emit(b"true" if value else b"false")
        elif kind is int:
            # Decimal length is at least (bit_length-1)/4. Reject before str().
            if max(1, (value.bit_length() - 1) // 4) > self.maximum - self.metadata:
                raise OSError("Integer metadata budget exhausted")
            try:
                self.emit(str(value).encode("ascii"))
            except ValueError as error:
                raise OSError("Integer metadata is not encodable") from error
        elif kind is str:
            self.string(value)
        elif kind in (tuple, LegacyObject):
            identity = id(value)
            if identity in self.active:
                raise OSError("Cyclic legacy metadata")
            self.active.add(identity)
            try:
                if kind is tuple:
                    if len(value) > self.nodes_left:
                        raise OSError("Node budget exhausted")
                    self.emit(b"[")
                    for index, child in enumerate(value):
                        if index:
                            self.emit(self.comma)
                        self.walk(child, depth + 1)
                    self.emit(b"]")
                else:
                    fields = value.fields
                    if type(fields) is not tuple or len(fields) > self.nodes_left:
                        raise OSError("Invalid bounded legacy object")
                    keys = set()
                    key_bytes = 0
                    for pair in fields:
                        if (
                            type(pair) is not tuple
                            or len(pair) != 2
                            or type(pair[0]) is not str
                        ):
                            raise OSError("Invalid legacy object field")
                        key_bytes += len(pair[0]) + 2
                        if key_bytes > self.maximum - self.metadata:
                            raise OSError("Object key metadata budget exhausted")
                        if pair[0] in keys:
                            raise OSError("Duplicate legacy object key")
                        keys.add(pair[0])
                    self.emit(b"{")
                    ordered = (
                        fields
                        if self.dialect == "Ju"
                        else sorted(fields, key=lambda p: p[0])
                    )
                    for index, (key, child) in enumerate(ordered):
                        if index:
                            self.emit(self.comma)
                        self.string(key)
                        self.emit(self.colon)
                        self.walk(child, depth + 1)
                    self.emit(b"}")
            finally:
                self.active.remove(identity)
        elif kind is LegacyContentSlot:
            reference = self.member(value.transport_reference)
            historical = value.legacy_reference
            if historical is not None:
                historical = _reference(historical)
                if (historical.size, historical.sha256) != (
                    reference.size,
                    reference.sha256,
                ):
                    raise OSError("Historical reference differs from admitted content")
            self.emit(b'{"data"' + self.colon + b'"')
            self.tokens.append(reference)
            self.payload += 4 * ((reference.size + 2) // 3)
            self.emit(b'"' + self.comma + b'"reference"' + self.colon)
            self.walk(
                None if historical is None else _reference_node(historical), depth + 1
            )
            self.emit(b"}")
        else:
            raise OSError("Unsupported legacy node type")


class ContentComparison:
    """Fixed registered-value closure; identity lookup promises no live bytes."""

    def __init__(
        self,
        session,
        references,
        *,
        raw_work_limit,
        metadata_limit,
        node_limit,
        timeout=30,
        cancel=None,
        _ledger=None,
        _scope=None,
    ):
        if type(session) is not ContentSession:
            raise OSError("Live content session required")
        self._session = session
        self._ledger = _ledger
        self._scope = _scope
        if _scope is not None:
            _scope.check(session)
        transfer = _Transfer(
            timeout=timeout,
            cancel=cancel,
            _native=_ledger is not None and _scope is not None,
        )
        work = _RawWork(raw_work_limit, _ledger)
        _limit(node_limit, "node", minimum=1)
        if type(references) is not tuple or 1 + 4 * len(references) > node_limit:
            raise OSError("Invalid bounded comparison references")
        remaining_metadata = _limit(metadata_limit, "metadata") - 2  # Array brackets.
        if remaining_metadata < 0:
            raise OSError("Metadata budget exhausted")
        admitted = []
        for index, value in enumerate(references):
            if index:
                remaining_metadata -= 1  # Compact comma, including duplicate entries.
            if remaining_metadata < 0:
                raise OSError("Metadata budget exhausted")
            # Admit each three-field copy before retaining the next one. The
            # reference graph is bounded by M plus one constant-sized model.
            value = _reference(value)
            fragment = _Projection(
                _reference_node(value),
                None,
                transfer,
                metadata_limit=remaining_metadata,
                node_limit=4,
                depth_limit=2,
            )
            remaining_metadata -= fragment.metadata
            admitted.append(value)
        resolved = [self._resolve(value) for value in admitted]
        self._members = {value.content_id: value for value, _, _ in resolved}
        self._backings = {value.content_id: backing for value, backing, _ in resolved}
        self._identities = {}
        verified = set()
        digests = {}
        for reference, backing, _ in resolved:
            if backing not in verified:
                with closing(self._read(reference, work, transfer)) as chunks:
                    for _ in chunks:
                        pass
                previous = digests.get(reference.sha256)
                if previous is not None:
                    if previous.size != reference.size:
                        raise OSError("Content digest has contradictory sizes")
                    with (
                        closing(self._read(previous, work, transfer)) as left,
                        closing(self._read(reference, work, transfer)) as right,
                    ):
                        for a, b in zip_longest(left, right):
                            if a != b:
                                raise OSError("Content digest has unequal exact bytes")
                digests[reference.sha256] = reference
                verified.add(backing)
            self._identities[reference.content_id] = ContentIdentity(
                content_id=f"sha256:{reference.sha256}:{reference.size}",
                sha256=reference.sha256,
                size=reference.size,
            )
        self._check()
        transfer.check()

    def _check(self):
        if self._scope is None:
            self._session._check()
        else:
            self._scope.check(self._session)

    def _resolve(self, reference):
        return (
            self._session._resolve(reference)
            if self._scope is None
            else self._scope.resolve(reference)
        )

    def _member(self, reference):
        reference = _reference(reference)
        if self._members.get(reference.content_id) != reference:
            raise OSError("Content is outside this comparison closure")
        self._resolve(reference)
        return reference

    def identity(self, reference):
        reference = self._member(reference)
        return self._identities[reference.content_id]

    def _read(self, reference, work, transfer):
        transfer.check()
        backing = self._backings[reference.content_id]
        if type(backing) is _MemoryBacking:
            self._scope._check_live(self._session)
            work.reserve(reference.size)
            return self._session._read_memory_backing(
                backing, reference, self._scope, transfer.check
            )
        self._check()
        work.reserve(reference.size)

        def chunks():
            transfer.check()
            if self._scope is None:
                self._check()
            else:
                self._scope._check_live(self._session)
            expected = self._session._files.get(backing)
            if self._scope is None:
                before = backing.lstat()
                if (before.st_dev, before.st_ino) != expected:
                    raise OSError("Owned backing identity changed")
                owned_identity = None
            else:
                if expected is None:
                    raise OSError("Owned backing identity changed")
                owned_identity = (self._session._anchor, expected)
            with closing(
                _observed_chunks(
                    self._session._directory,
                    backing,
                    expected_size=reference.size,
                    read_chunk_limit=_CHUNK,
                    owned_identity=owned_identity,
                )
            ) as observed:
                while True:
                    transfer.check()
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
            self._check()
            transfer.check()

        # Eager reservation lets paired comparisons fund both full reads before
        # either iterator performs native IO; closing an unstarted one is safe.
        return chunks()

    def project_legacy(
        self,
        root,
        *,
        dialect,
        raw_work_limit,
        encoded_byte_limit,
        metadata_limit,
        node_limit,
        depth_limit,
        preview_limit=0,
        timeout=30,
        cancel=None,
        _ledger=None,
    ):
        transfer = _Transfer(
            timeout=timeout,
            cancel=cancel,
            _native=_ledger is not None and self._scope is not None,
        )
        work = _RawWork(raw_work_limit, _ledger)
        maximum = _limit(encoded_byte_limit, "encoded output")
        preview_limit = _limit(preview_limit, "preview", maximum=65536)
        if type(dialect) is not str or dialect not in ("Jc", "Js", "Ju"):
            raise OSError("Unsupported legacy dialect")
        self._check()
        plan = _Projection(
            root,
            self._member,
            transfer,
            metadata_limit=metadata_limit,
            node_limit=node_limit,
            depth_limit=depth_limit,
            dialect=dialect,
            ledger=_ledger,
            _native=_ledger is not None and self._scope is not None,
        )
        expected_size = plan.metadata + plan.payload
        if expected_size > maximum:
            raise OSError("Encoded output budget exhausted")
        if _ledger is not None:
            _ledger.take("encoded", expected_size)
        digest, preview, count = hashlib.sha256(), bytearray(), 0

        def emit(data):
            nonlocal count
            transfer.check()
            if len(data) > 1024 * 1024 or count + len(data) > maximum:
                raise OSError("Encoded output budget exhausted")
            digest.update(data)
            count += len(data)
            preview.extend(data[: max(0, preview_limit - len(preview))])

        for token in plan.tokens:
            if type(token) is bytes:
                emit(token)
            else:
                residual = b""
                with closing(self._read(token, work, transfer)) as chunks:
                    for block in chunks:
                        combined = residual + block
                        end = len(combined) - len(combined) % 3
                        emit(base64.urlsafe_b64encode(combined[:end]))
                        residual = combined[end:]
                if residual:
                    emit(base64.urlsafe_b64encode(residual))
        if count != expected_size:
            raise OSError("Projection encoded length differs from preflight")
        self._check()
        transfer.check()
        return LegacyProjectionEvidence(
            dialect, digest.hexdigest(), count, bytes(preview)
        )
