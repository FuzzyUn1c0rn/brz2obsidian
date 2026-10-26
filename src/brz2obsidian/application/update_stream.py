"""End-sealed finite response decoding for a persistent private producer."""

import json
from hashlib import sha256
from typing import Literal

from pydantic import Field

from .contracts import WorkerEnvelope
from .protocol import (
    RESPONSE_LIMIT,
    ProtocolFailure,
    _pairs,
    decode_response,
    encode_response,
)
from .vault_progress_contracts import VaultProgress


class WorkerEnd(WorkerEnvelope):
    schema_: Literal["brz2obsidian.worker-end"] = Field(
        default="brz2obsidian.worker-end", alias="schema"
    )
    request_id: str
    sequence: int = Field(ge=1)
    operation: Literal["update"] = "update"
    terminal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class WorkerProgress(WorkerEnvelope):
    schema_: Literal["brz2obsidian.worker-progress"] = Field(
        default="brz2obsidian.worker-progress", alias="schema"
    )
    operation: Literal["update"] = "update"
    request_id: str
    sequence: int = Field(ge=1)
    ordinal: int = Field(ge=1, le=9223372036854775807)
    elapsed_ms: int = Field(default=0, ge=0)
    value: VaultProgress


def encode_progress(progress):
    frame = progress.model_dump_json(by_alias=True).encode("utf-8") + b"\n"
    if len(frame) > RESPONSE_LIMIT:
        raise ProtocolFailure("Oversized progress frame")
    return frame


def encode_end(response):
    return (
        WorkerEnd(
            request_id=response.request_id,
            sequence=response.sequence,
            terminal_sha256=sha256(encode_response(response)).hexdigest(),
        )
        .model_dump_json(by_alias=True)
        .encode("utf-8")
        + b"\n"
    )


class WorkerStreamDecoder:
    """A terminal is provisional until sealed; every later fault poisons it."""

    def __init__(self, request):
        if request.operation != "update":
            raise ValueError("A persistent update request is required")
        self.request = request
        self._terminal = None
        self._digest = None
        self.progress = None
        self._progress_ordinal = 0
        self.sealed = self.poisoned = False

    def feed(self, frame):
        try:
            if (
                self.poisoned
                or self.sealed
                or len(frame) > RESPONSE_LIMIT
                or not frame.endswith(b"\n")
                or frame.count(b"\n") != 1
            ):
                raise ProtocolFailure("Invalid stream framing")
            raw = json.loads(frame.decode("utf-8"), object_pairs_hook=_pairs)
            if (
                isinstance(raw, dict)
                and raw.get("schema") == "brz2obsidian.worker-progress"
            ):
                if (
                    self._terminal is not None
                    or self.request.arguments.command == "cancel"
                    or set(raw)
                    != {
                        "schema",
                        "schema_version",
                        "operation",
                        "request_id",
                        "sequence",
                        "ordinal",
                        "elapsed_ms",
                        "value",
                    }
                    or not isinstance(raw.get("value"), dict)
                    or set(raw["value"]) != set(VaultProgress.model_fields)
                ):
                    raise ProtocolFailure("Invalid progress framing")
                progress = WorkerProgress.model_validate_json(frame)
                if (
                    progress.request_id != self.request.request_id
                    or progress.sequence != self.request.sequence
                    or progress.ordinal != self._progress_ordinal + 1
                ):
                    raise ProtocolFailure("Invalid progress correlation")
                self.progress = progress
                self._progress_ordinal = progress.ordinal
                return None
            if self._terminal is None:
                self._terminal = decode_response(frame, self.request)
                self._digest = sha256(encode_response(self._terminal)).hexdigest()
                self.progress = None
                return None
            if not isinstance(raw, dict) or set(raw) != {
                "schema",
                "schema_version",
                "request_id",
                "operation",
                "sequence",
                "terminal_sha256",
            }:
                raise ProtocolFailure("Invalid end frame")
            end = WorkerEnd.model_validate_json(frame)
            if (
                end.request_id != self.request.request_id
                or end.sequence != self.request.sequence
                or end.terminal_sha256 != self._digest
            ):
                raise ProtocolFailure("Invalid end correlation")
            self.sealed = True
            return self._terminal
        except ValueError, TypeError, KeyError, RecursionError:
            self.poisoned, self.sealed = True, False
            self._terminal = self._digest = None
            self.progress = None
            raise ProtocolFailure("Untrustworthy worker stream") from None

    def eof(self):
        if not self.sealed:
            self.poisoned = True
            self._terminal = None
            self.progress = None
            raise ProtocolFailure("Unsealed worker stream")
