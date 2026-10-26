"""Small volatile history handles; native preparations remain inside the producer."""

from typing import Literal

from pydantic import Field, field_validator, model_validator

from brz2obsidian.contracts import ReconciliationContract

from .contract_values import absolute, request_identity
from .vault_repair_contracts import HistoryRepairResult
from .vault_update_contracts import VaultApplyResult


class UpdateHistoryCopyState(ReconciliationContract):
    status: Literal["matching", "refused", "unavailable"]
    code: str
    association_id: str | None
    target_commit: str | None
    target_generation: int | None
    copy_commit: str | None
    copy_generation: int | None
    missing_objects: int = Field(ge=0)
    damaged_objects: int = Field(ge=0)


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
    copy_validation: UpdateHistoryCopyState | None = None
    repair: HistoryRepairResult | None = None

    @model_validator(mode="after")
    def declared_readiness(self):
        if self.ready != (self.status == "ready"):
            raise ValueError("History action readiness must match its status")
        if self.status == "direction_required" and (
            self.kind != "recovery" or not self.available_directions
        ):
            raise ValueError("Only an offered recovery direction requires selection")
        if self.repair is not None and (
            self.kind != "repair"
            or self.status != self.repair.status
            or self.operation is not None
        ):
            raise ValueError(
                "Repair outcomes must keep their actual native role/result"
            )
        if self.status == "repaired" and self.repair is None:
            raise ValueError("Repaired requires verified native object storage")
        return self


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
    target_receipt_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
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
