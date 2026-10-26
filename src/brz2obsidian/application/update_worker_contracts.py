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
from .update_history_contracts import HistoryContextBinding


class PrepareUpdateCommand(ReconciliationContract):
    command: Literal["prepare"]
    vault: str
    selection_id: str
    kind: Literal[
        "source_update", "onboarding", "format_transition", "attachment_cleanup"
    ]
    source: str | None
    original_source: str | None = None
    _vault = field_validator("vault")(absolute)
    _selection = field_validator("selection_id")(request_identity)

    @field_validator("source", "original_source")
    @classmethod
    def source_path(cls, value):
        return absolute(value) if value is not None else None

    @model_validator(mode="after")
    def original_evidence_role(self):
        if self.original_source is not None and self.kind != "onboarding":
            raise ValueError("Original reference evidence belongs to onboarding")
        return self


class HistoryInspectionCommand(ReconciliationContract):
    command: Literal["history"]
    vault: str
    selection_id: str
    _vault = field_validator("vault")(absolute)
    _selection = field_validator("selection_id")(request_identity)


class InitializeVaultCommand(ReconciliationContract):
    command: Literal["initialize_vault"]
    binding: HistoryContextBinding
    choice: Literal["initialize", "decline"]


class PrepareHistoryCommand(ReconciliationContract):
    command: Literal["prepare_history"]
    binding: HistoryContextBinding
    kind: Literal["recovery", "undo", "repair"]
    direction: Literal["finish", "restore"] | None = None
    copy_path: str | None = None
    _copy = field_validator("copy_path")(
        lambda value: absolute(value) if value is not None else None
    )


class ContinueHistoryCommand(ReconciliationContract):
    command: Literal["refresh_history", "execute_history"]
    binding: HistoryContextBinding


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


class ChoicePageUpdateCommand(ReconciliationContract):
    command: Literal["choices"]
    binding: UpdateContextBinding
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=100)


class ChoiceDetailUpdateCommand(ReconciliationContract):
    command: Literal["choice_details"]
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
    selected_entry_id: str | None = None
    disassociate_entry_ids: tuple[str, ...] = Field(default=(), max_length=100)


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
    binding: UpdateContextBinding | HistoryContextBinding | None = None


class DiscardDraftCommand(ReconciliationContract):
    command: Literal["discard_draft"]
    binding: UpdateContextBinding


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
    binding: UpdateContextBinding | HistoryContextBinding | None
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


def update_control_scope(arguments):
    """Extract only the exact scope of an already validated admitted command."""
    binding = getattr(arguments, "binding", None) or getattr(
        getattr(arguments, "handle", None), "binding", None
    )
    if binding is not None:
        return {"binding": binding}
    if arguments.command in ("prepare", "load", "resume", "history"):
        return {
            "binding": None,
            "vault": arguments.vault,
            "selection_id": arguments.selection_id,
        }
    return None


UpdateCommand = Annotated[
    PrepareUpdateCommand
    | HistoryInspectionCommand
    | InitializeVaultCommand
    | PrepareHistoryCommand
    | ContinueHistoryCommand
    | PageUpdateCommand
    | ReferenceUpdateCommand
    | ChoicePageUpdateCommand
    | ChoiceDetailUpdateCommand
    | ChooseUpdateCommand
    | StageReferencesCommand
    | ConfigurationChoiceCommand
    | BeginEditCommand
    | WriteEditCommand
    | SealEditCommand
    | CloseUpdateCommand
    | DiscardDraftCommand
    | ApplyUpdateCommand
    | SaveUpdateCommand
    | OpenSavedUpdateCommand
    | CancelUpdateCommand,
    Field(discriminator="command"),
]
