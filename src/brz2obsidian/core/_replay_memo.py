"""Bounded pure replay values; no validation verdict or current-state authority."""

from collections import OrderedDict
from hashlib import sha256
from threading import Lock

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


class _ReplayMemo:
    """The replay implementation owns this instance for its stable loaded lifetime.

    Entries contain only immutable encoded inputs and computed canonical values.
    The digest is an index: a hit also requires the complete exact input bytes.
    No live result object is retained. Serialization and replay stay outside the
    lock; overlapping callers may independently compute the same prefix.
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

    def longest_prefix(self, history):
        found = None
        for count, key, fingerprint in self.prefixes(history):
            with self._lock:
                entry = self._entries.get(fingerprint)
                if entry is not None and entry[0] == key:
                    self._entries.move_to_end(fingerprint)
                    found = count, entry[1]
        return found

    def retain(self, prefix, canonical):
        """Only the replay implementation supplies a successfully computed state."""
        if prefix is None:
            return
        _, key, fingerprint = prefix
        value = _PLAN.dump_json(canonical, round_trip=True)
        size = len(key) + len(value)
        if size > self._maximum_bytes:
            return
        with self._lock:
            previous = self._entries.pop(fingerprint, None)
            if previous is not None:
                self._retained_bytes -= len(previous[0]) + len(previous[1])
            while self._entries and (
                len(self._entries) >= self._maximum_entries
                or self._retained_bytes + size > self._maximum_bytes
            ):
                _, removed = self._entries.popitem(last=False)
                self._retained_bytes -= len(removed[0]) + len(removed[1])
            self._entries[fingerprint] = bytes(key), value
            self._retained_bytes += size
