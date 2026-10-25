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


class WorkerEnd(WorkerEnvelope):
    schema_: Literal["brz2obsidian.worker-end"] = Field(
        default="brz2obsidian.worker-end", alias="schema"
    )
    request_id: str
    sequence: int = Field(ge=1)
    operation: Literal["update"] = "update"
    terminal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


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
            if self._terminal is None:
                self._terminal = decode_response(frame, self.request)
                self._digest = sha256(encode_response(self._terminal)).hexdigest()
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
            raise ProtocolFailure("Untrustworthy worker stream") from None

    def eof(self):
        if not self.sealed:
            self.poisoned = True
            self._terminal = None
            raise ProtocolFailure("Unsealed worker stream")
