"""One creator-owned volatile byte lease; it carries no publication authority."""

import tempfile
from contextlib import ExitStack
from hashlib import sha256

from brz2obsidian.publication.vault_native import available_memory

from .update_context_contracts import UpdateEditState


class EditFailure(ValueError):
    """Closed producer failure code, never file or exception data."""


class EditLease:
    def __init__(self, handle):
        if handle.size > available_memory() // 16:
            raise EditFailure("edit_budget_exceeded")
        self.handle = handle
        self.received = 0
        self.sealed = False
        self._lifetime = ExitStack()
        # The creator-owned lifetime spans multiple bounded worker commands.
        self._file = self._lifetime.enter_context(tempfile.TemporaryFile(mode="w+b"))  # noqa: SIM115 -- closed by resolve/discard through this lease's ExitStack.

    @property
    def state(self):
        return UpdateEditState(
            handle=self.handle, received_bytes=self.received, sealed=self.sealed
        )

    def write(self, *, offset, data):
        if self.sealed:
            raise EditFailure("edit_changed")
        if (
            type(offset) is not int
            or offset != self.received
            or self._file.tell() != self.received
        ):
            raise EditFailure("edit_offset_changed")
        if (
            type(data) is not bytes
            or not data
            or len(data) > 32768
            or offset + len(data) > self.handle.size
        ):
            raise EditFailure("invalid_edit_chunk")
        if self._file.write(data) != len(data):
            raise OSError("Incomplete owned edit write")
        self.received += len(data)

    def seal(self):
        if self.received != self.handle.size:
            raise EditFailure("edit_incomplete")
        digest = sha256()
        self._file.seek(0)
        while chunk := self._file.read(65536):
            digest.update(chunk)
        if digest.hexdigest() != self.handle.sha256:
            raise EditFailure("edit_checksum_mismatch")
        self.sealed = True

    def content(self):
        if not self.sealed:
            raise EditFailure("edit_unsealed")
        if self.handle.size > available_memory() // 16:
            raise EditFailure("edit_budget_exceeded")
        self._file.seek(0)
        raw = self._file.read(self.handle.size + 1)
        if (
            len(raw) != self.handle.size
            or sha256(raw).hexdigest() != self.handle.sha256
        ):
            raise EditFailure("edit_checksum_mismatch")
        return raw

    def close(self):
        self._lifetime.close()
