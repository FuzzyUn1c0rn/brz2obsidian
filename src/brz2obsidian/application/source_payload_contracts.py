"""Outer binding between one S1 review generation and complete source payload."""

import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator

from brz2obsidian.contracts import OutputIdentity, ReconciliationContract


class SourcePayloadFile(ReconciliationContract):
    path: str
    mode: Literal["100644", "100755"]
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReviewedSourceBinding(ReconciliationContract):
    """Complete observed converted payload paired with a prepared S1 generation."""

    schema_id: Literal["brz2obsidian.reviewed-source-binding"]
    schema_version: Literal[1]
    proposal_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    incoming_identity: OutputIdentity
    target_source_version: str | None
    source_anchor: str = Field(min_length=1)
    files: tuple[SourcePayloadFile, ...]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @staticmethod
    def digest(files):
        rows = [(row.path, row.mode, row.size, row.sha256) for row in files]
        return hashlib.sha256(
            json.dumps(rows, ensure_ascii=True, separators=(",", ":")).encode()
        ).hexdigest()

    @model_validator(mode="after")
    def complete_inventory(self):
        paths = [row.path for row in self.files]
        if paths != sorted(set(paths)):
            raise ValueError("Source payload paths must be unique and sorted")
        for path in paths:
            self.relative_vault_path(path)
        if self.fingerprint != self.digest(self.files):
            raise ValueError("Source payload digest does not match complete inventory")
        return self
