"""Read finite pages of fully verified retained bytes without granting authority."""

from pathlib import Path

from brz2obsidian.application.checkpoint_contracts import CheckpointLocator
from brz2obsidian.application.checkpoint_payload_contracts import (
    CheckpointPayloadChunk,
    CheckpointPayloadRead,
    CheckpointPayloadRequest,
)
from brz2obsidian.publication.git_payload import verify_blobs
from brz2obsidian.publication.git_read import OUTPUT_BUDGET
from brz2obsidian.publication.vault_admission import _safe_relative
from brz2obsidian.publication.vault_history import _Git, inspect_history
from brz2obsidian.publication.vault_native import (
    available_memory,
    observe_file,
    verify_directory,
)

_ROLES = ("source", "vault", "preimage", "proposed", "review_content")


class _Page:
    """A finite owned sink; unverified bytes never escape this call."""

    def __init__(self, offset, limit):
        self.offset = offset
        self.end = offset + limit
        self.position = 0
        self.data = bytearray()

    def write(self, block):
        end = self.position + len(block)
        start = max(self.offset, self.position)
        stop = min(self.end, end)
        if start < stop:
            self.data.extend(block[start - self.position : stop - self.position])
        self.position = end
        return len(block)


def read_checkpoint_payload(
    vault, *, locator, requests, byte_limit, role="source", git_executable=None
):
    """Return finite pages only after an independent current history inspection."""
    return _read_checkpoint_payload(
        vault,
        locator=locator,
        requests=requests,
        byte_limit=byte_limit,
        role=role,
        git_executable=git_executable,
        _read_history=lambda: inspect_history(vault, git_executable=git_executable),
    )


def _read_checkpoint_payload(
    vault,
    *,
    locator,
    requests,
    byte_limit,
    role="source",
    git_executable=None,
    _read_history,
    _guard=None,
):
    """Return exact byte pages bound to the *current* validated checkpoint.

    ``requests`` is a nonempty finite tuple. Its declared page limits must fit
    the nonnegative caller byte budget and currently available memory. Page size
    does not cap the qualified blob size; continue with each ``next_offset``.
    Every complete blob is hashed before any page is returned. A successful
    read conveys bytes, never review, publication or mutation authority.
    """

    def result(code, *, chunks=(), current=None):
        return CheckpointPayloadRead(
            schema_id="brz2obsidian.checkpoint-payload-read",
            schema_version=1,
            status="available" if code == "verified" else "refused",
            code=code,
            locator=current,
            role=role if role in _ROLES else "source",
            chunks=chunks,
            message=(
                "Retained byte pages verified against the current checkpoint."
                if code == "verified"
                else "Retained byte pages unavailable: " + code.replace("_", " ") + "."
            ),
        )

    try:
        if (
            role not in _ROLES
            or type(byte_limit) is not int
            or not 0 <= byte_limit <= (1 << 63) - 1
            or type(requests) is not tuple
            or not 0 < len(requests) <= OUTPUT_BUDGET // 128
        ):
            return result("invalid_request")
        locator = CheckpointLocator.model_validate(locator)
        requests = tuple(
            CheckpointPayloadRequest.model_validate(row) for row in requests
        )
        if (
            any(not _safe_relative(row.path) for row in requests)
            or sum(len(row.path.encode("utf-8")) + 128 for row in requests)
            > OUTPUT_BUDGET
            or sum(row.limit for row in requests) > byte_limit
        ):
            return result("invalid_request")
        # Page storage plus immutable response copies remain resource-bounded.
        if sum(row.limit for row in requests) > available_memory() // 4:
            return result("insufficient_memory")
        root = Path(vault).absolute()
        observed = _read_history()
        checkpoint = observed.checkpoint
        if (
            observed.status != "intact"
            or checkpoint is None
            or checkpoint.status != "valid"
        ):
            return result("history_unavailable")
        if checkpoint.locator != locator:
            return result("stale_locator")
        rows = {row.path: row for row in getattr(checkpoint.manifest, role)}
        selected = []
        for request in requests:
            row = rows.get(request.path)
            if row is None:
                return result("path_unavailable")
            if request.offset > row.size or (
                request.limit == 0 and request.offset < row.size
            ):
                return result("invalid_range")
            selected.append((request, row, _Page(request.offset, request.limit)))
        git = _Git(root, git_executable)
        verify_blobs(
            [*git.prefix, "cat-file", "--batch"],
            env=git.env,
            objects=tuple(
                (row.object_id, row.size, row.sha256, sink) for _, row, sink in selected
            ),
            timeout=120,
        )
        # Recheck current identity/ref/physical association without repeating the
        # complete graph once per requested file or introducing a trust cache.
        _, _, raw, _ = observe_file(
            root, root / ".brz2obsidian/locator.json", prefix_limit=OUTPUT_BUDGET + 1
        )
        current = CheckpointLocator.model_validate_json(raw)
        association = locator.association
        if (
            current != locator
            or verify_directory(root) != association.vault_anchor
            or verify_directory(root / ".git") != association.git_anchor
            or git.call("rev-parse", "--verify", association.ref).decode().strip()
            != locator.commit
        ):
            return result("stale_locator")
        if _guard is not None:
            _guard()
        chunks = tuple(
            CheckpointPayloadChunk(
                path=row.path,
                mode=row.mode,
                object_id=row.object_id,
                sha256=row.sha256,
                size=row.size,
                offset=request.offset,
                data=bytes(sink.data),
                eof=request.offset + len(sink.data) == row.size,
                omitted=request.offset != 0 or len(sink.data) != row.size,
                next_offset=(
                    request.offset + len(sink.data)
                    if request.offset + len(sink.data) < row.size
                    else None
                ),
            )
            for request, row, sink in selected
        )
        return result("verified", chunks=chunks, current=current)
    except OSError, ValueError, TypeError, OverflowError, MemoryError:
        return result("payload_unavailable")
