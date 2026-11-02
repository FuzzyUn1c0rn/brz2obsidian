"""Bounded pure replay values; no validation verdict or current-state authority."""

from collections import OrderedDict
from hashlib import sha256
from threading import Lock
from typing import NamedTuple
from zlib import compress, decompressobj
from zlib import error as CodecError

from pydantic import TypeAdapter

from brz2obsidian.contracts import (
    ReconciliationInput,
    ReviewAction,
    ReviewPlan,
    ReviewPreflight,
    ReviewRefreshEvent,
)

_FACTS = TypeAdapter(ReconciliationInput)
_PREFLIGHT = TypeAdapter(ReviewPreflight)
_EVENT = TypeAdapter(ReviewAction | ReviewRefreshEvent)
_PLAN = TypeAdapter(ReviewPlan)


class _Entry(NamedTuple):
    key: bytes
    value: bytes
    raw_key_size: int
    raw_value_size: int

    @property
    def size(self):
        return len(self.key) + len(self.value)


class _ReplayMemo:
    """The replay implementation owns this instance for its stable loaded lifetime.

    Entries contain only immutable encoded inputs and computed canonical values.
    The digest is an index: a hit also requires the complete exact input bytes.
    No live result object or raw payload is retained. Serialization, codecs and
    replay stay outside the lock; overlapping callers may duplicate computation.
    Snapshot references can transiently keep evicted entries alive. Raw scratch,
    decoded bytes and returned models are outside the retained-map byte cap.
    """

    def __init__(self):
        self._entries = OrderedDict()
        self._lock = Lock()
        self._retained_bytes = 0
        self._maximum_entries = 32
        self._maximum_bytes = 64 * 1024 * 1024

    def prefixes(self, history):
        """Frame the already validated typed inputs, retaining one scratch key.

        Each yielded buffer is local to this traversal and grows on the next
        iteration. Consumers must use it synchronously, never retain that buffer.
        Oversized keys stop memo probing/storage, not actual historical replay.
        Input/value encoding and decoding allocate transient memory beyond the
        explicitly bounded retained serialized bytes.
        """
        key = bytearray(b"brz2obsidian.core.replay-prefix.1\0")
        digest = sha256(key)

        def append(raw):
            if len(key) + 8 + len(raw) > self._maximum_bytes:
                return False
            length = len(raw).to_bytes(8, "big")
            key.extend(length)
            key.extend(raw)
            digest.update(length)
            digest.update(raw)
            return True

        if not append(_FACTS.dump_json(history.initial_facts, round_trip=True)):
            return
        if not append(_PREFLIGHT.dump_json(history.initial_preflight, round_trip=True)):
            return
        yield 0, key, digest.digest()
        for count, event in enumerate(history.events, 1):
            if not append(_EVENT.dump_json(event, round_trip=True)):
                return
            yield count, key, digest.digest()

    def _decode(self, encoded, size):
        if not 0 <= size <= self._maximum_bytes:
            return None
        try:
            decoder = decompressobj()
            raw = decoder.decompress(encoded, size + 1)
        except CodecError:
            return None
        if (
            len(raw) != size
            or not decoder.eof
            or decoder.unconsumed_tail
            or decoder.unused_data
        ):
            return None
        return raw

    def _discard(self, fingerprint, entry):
        with self._lock:
            if self._entries.get(fingerprint) is entry:
                del self._entries[fingerprint]
                self._retained_bytes -= entry.size

    def longest_prefix(self, history):
        with self._lock:
            snapshot = dict(self._entries)
        candidates = []
        key = None
        for count, key, fingerprint in self.prefixes(history):
            entry = snapshot.get(fingerprint)
            if entry is not None and entry.raw_key_size == len(key):
                # Framed prefix lengths strictly increase: at most 32 candidates.
                candidates.append((count, fingerprint, entry))
        if key is None:
            return None
        for count, fingerprint, entry in reversed(candidates):
            raw_key = self._decode(entry.key, entry.raw_key_size)
            if raw_key is None:
                self._discard(fingerprint, entry)
                continue
            if raw_key != memoryview(key)[: entry.raw_key_size]:
                continue
            value = self._decode(entry.value, entry.raw_value_size)
            if value is None:
                self._discard(fingerprint, entry)
                continue
            with self._lock:
                if self._entries.get(fingerprint) is entry:
                    self._entries.move_to_end(fingerprint)
            return count, value
        return None

    def retain(self, prefix, canonical):
        """Only the replay implementation supplies a successfully computed state."""
        if prefix is None:
            return
        _, key, fingerprint = prefix
        value = _PLAN.dump_json(canonical, round_trip=True)
        if len(key) + len(value) > self._maximum_bytes:
            return
        try:
            entry = _Entry(compress(key, 6), compress(value, 6), len(key), len(value))
        except CodecError:
            return
        if entry.size > self._maximum_bytes:
            return
        with self._lock:
            previous = self._entries.pop(fingerprint, None)
            if previous is not None:
                self._retained_bytes -= previous.size
            while self._entries and (
                len(self._entries) >= self._maximum_entries
                or self._retained_bytes + entry.size > self._maximum_bytes
            ):
                _, removed = self._entries.popitem(last=False)
                self._retained_bytes -= removed.size
            self._entries[fingerprint] = entry
            self._retained_bytes += entry.size
