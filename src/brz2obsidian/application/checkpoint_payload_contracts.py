"""Closed immutable values for association-bound retained byte pages."""

from typing import Literal

from pydantic import Field, model_validator

from brz2obsidian.application.checkpoint_contracts import CheckpointLocator
from brz2obsidian.contracts import ReconciliationContract

CheckpointPayloadRole = Literal[
    "source",
    "vault",
    "preimage",
    "proposed",
    "review_content",
]


class CheckpointPayloadRequest(ReconciliationContract):
    path: str = Field(min_length=1)
    offset: int = Field(default=0, ge=0, le=(1 << 63) - 1)
    limit: int = Field(ge=0, le=(1 << 63) - 1)


class CheckpointPayloadChunk(ReconciliationContract):
    path: str
    mode: Literal["100644", "100755"]
    object_id: str = Field(pattern=r"^[0-9a-f]{40}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)
    offset: int = Field(ge=0)
    data: bytes
    eof: bool
    omitted: bool
    next_offset: int | None = Field(ge=0)

    @model_validator(mode="after")
    def coherent_range(self):
        end = self.offset + len(self.data)
        if (
            end > self.size
            or self.eof != (end == self.size)
            or self.omitted != (self.offset != 0 or len(self.data) != self.size)
            or self.next_offset != (end if end < self.size else None)
        ):
            raise ValueError("Byte page metadata must describe its exact range")
        return self


class CheckpointPayloadRead(ReconciliationContract):
    schema_id: Literal["brz2obsidian.checkpoint-payload-read"]
    schema_version: Literal[1]
    status: Literal["available", "refused"]
    code: Literal[
        "verified",
        "invalid_request",
        "insufficient_memory",
        "history_unavailable",
        "stale_locator",
        "path_unavailable",
        "invalid_range",
        "payload_unavailable",
    ]
    locator: CheckpointLocator | None
    role: CheckpointPayloadRole
    chunks: tuple[CheckpointPayloadChunk, ...]
    message: str

    @model_validator(mode="after")
    def coherent_read(self):
        if self.status == "available":
            if self.code != "verified" or self.locator is None or not self.chunks:
                raise ValueError("Available pages require verified checkpoint identity")
        elif self.code == "verified" or self.locator is not None or self.chunks:
            raise ValueError("Refused byte reads cannot release identity or content")
        return self
