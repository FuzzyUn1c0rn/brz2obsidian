"""Closed small worker commands; no canonical review or candidate on the wire."""

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from brz2obsidian.contracts import ReconciliationContract, ReviewChoice

from .contract_values import absolute, request_identity
from .update_context_contracts import (
    UpdateContextBinding,
    UpdateEditHandle,
    UpdateReferenceChoice,
)


class PrepareUpdateCommand(ReconciliationContract):
    command: Literal["prepare"]
    vault: str
    selection_id: str
    kind: Literal[
        "source_update", "onboarding", "format_transition", "attachment_cleanup"
    ]
    source: str | None
    _vault = field_validator("vault")(absolute)
    _selection = field_validator("selection_id")(request_identity)

    @field_validator("source")
    @classmethod
    def source_path(cls, value):
        return absolute(value) if value is not None else None


class PageUpdateCommand(ReconciliationContract):
    command: Literal["page"]
    binding: UpdateContextBinding
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=100)
    byte_offset: int = Field(default=0, ge=0)
    byte_limit: int = Field(default=65536, ge=0, le=65536)


class ReferenceUpdateCommand(ReconciliationContract):
    command: Literal["references"]
    binding: UpdateContextBinding
    requirement_id: str
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=100)


class ChooseUpdateCommand(ReconciliationContract):
    command: Literal["choose"]
    binding: UpdateContextBinding
    requirement_id: str
    choice: ReviewChoice
    assumptions_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    references: tuple[UpdateReferenceChoice, ...] | None = Field(
        default=None, max_length=100
    )
    edit_handle: UpdateEditHandle | None = None


class BeginEditCommand(ReconciliationContract):
    command: Literal["begin_edit"]
    binding: UpdateContextBinding
    requirement_id: str
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class WriteEditCommand(ReconciliationContract):
    command: Literal["write_edit"]
    handle: UpdateEditHandle
    offset: int = Field(ge=0)
    data: bytes = Field(min_length=1, max_length=32768)


class SealEditCommand(ReconciliationContract):
    command: Literal["seal_edit"]
    handle: UpdateEditHandle


class StageReferencesCommand(ReconciliationContract):
    command: Literal["stage_references"]
    binding: UpdateContextBinding
    requirement_id: str
    choices: tuple[UpdateReferenceChoice, ...] = Field(min_length=1, max_length=100)


class ConfigurationChoiceCommand(ReconciliationContract):
    command: Literal["choose_configuration"]
    binding: UpdateContextBinding
    group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    choice: Literal["current", "incoming"]


class CloseUpdateCommand(ReconciliationContract):
    command: Literal["close"]
    choice: Literal["continue", "save", "discard"]
    binding: UpdateContextBinding | None = None


class ApplyUpdateCommand(ReconciliationContract):
    command: Literal["apply"]
    binding: UpdateContextBinding


class SaveUpdateCommand(ReconciliationContract):
    command: Literal["save"]
    binding: UpdateContextBinding


class OpenSavedUpdateCommand(ReconciliationContract):
    command: Literal["load", "resume"]
    vault: str
    selection_id: str
    _vault = field_validator("vault")(absolute)
    _selection = field_validator("selection_id")(request_identity)


class CancelUpdateCommand(ReconciliationContract):
    command: Literal["cancel"]
    binding: UpdateContextBinding | None
    target_request_id: str
    target_sequence: int = Field(ge=1)
    vault: str | None = None
    selection_id: str | None = None
    _identity = field_validator("target_request_id")(request_identity)

    @model_validator(mode="after")
    def scope(self):
        if self.binding is None:
            if type(self.vault) is not str or type(self.selection_id) is not str:
                raise ValueError(
                    "Preparation cancellation requires its actual selection"
                )
            absolute(self.vault)
            request_identity(self.selection_id)
        elif self.vault is not None or self.selection_id is not None:
            raise ValueError("Choose the actual preparation or review scope")
        return self


UpdateCommand = Annotated[
    PrepareUpdateCommand
    | PageUpdateCommand
    | ReferenceUpdateCommand
    | ChooseUpdateCommand
    | StageReferencesCommand
    | ConfigurationChoiceCommand
    | BeginEditCommand
    | WriteEditCommand
    | SealEditCommand
    | CloseUpdateCommand
    | ApplyUpdateCommand
    | SaveUpdateCommand
    | OpenSavedUpdateCommand
    | CancelUpdateCommand,
    Field(discriminator="command"),
]
