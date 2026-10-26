"""Small volatile history handles; native preparations remain inside the producer."""

from typing import Literal

from pydantic import Field, field_validator

from brz2obsidian.contracts import ReconciliationContract

from .contract_values import absolute, request_identity
from .vault_update_contracts import VaultApplyResult


class UpdateHistoryActionState(ReconciliationContract):
    kind: Literal["recovery", "undo", "repair"] | None
    status: Literal[
        "direction_required",
        "review_required",
        "ready",
        "recovery_required",
        "applied",
        "no_content_change",
        "undone",
        "restored",
        "repaired",
        "refused",
        "failed",
        "cancelled",
        "incomplete",
        "content_complete",
        "unknown",
        "unavailable",
    ]
    ready: bool
    available_directions: tuple[Literal["finish", "restore"], ...]
    operation: VaultApplyResult | None
    summary: str = Field(max_length=2048)


class HistoryContextBinding(ReconciliationContract):
    context_type: Literal["history"] = "history"
    context_id: str
    selection_id: str
    vault: str
    revision: int = Field(ge=1)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    operation_generation: int | None = Field(default=None, ge=1)
    intent_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    direction: Literal["finish", "restore"] | None = None
    proposal_id: str | None = None
    review_generation: int | None = Field(default=None, ge=1)
    association_id: str | None = None
    checkpoint_commit: str | None = None
    checkpoint_generation: int | None = Field(default=None, ge=1)
    _ids = field_validator("context_id", "selection_id")(request_identity)
    _vault = field_validator("vault")(absolute)


class UpdateHistoryState(ReconciliationContract):
    status: Literal[
        "recovery_required",
        "available",
        "onboarding_required",
        "unavailable",
        "setup_required",
        "initialization_required",
    ]
    code: str
    operation: VaultApplyResult
    history_retained: bool
    recovery_gap_count: int = Field(ge=0)
    findings: tuple[str, ...]
    diagnostic_omission: bool
    summary: str = Field(max_length=2048)
