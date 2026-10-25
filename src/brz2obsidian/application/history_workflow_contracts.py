"""Closed shared history routing facts; physical authority remains with S2."""

from typing import Literal

from pydantic import Field, model_validator

from brz2obsidian.application.checkpoint_contracts import CheckpointLocator
from brz2obsidian.application.vault_recovery_contracts import VaultRecoveryPreparation
from brz2obsidian.application.vault_repair_contracts import (
    HistoryCopyValidation,
    HistoryRepairPreparation,
    HistoryRepairResult,
)
from brz2obsidian.application.vault_undo_contracts import VaultUndoPreparation
from brz2obsidian.application.vault_update_contracts import VaultApplyResult
from brz2obsidian.contracts import ReconciliationContract

type HistoryNextAction = Literal[
    "review_recovery",
    "review_undo",
    "review_history_repair",
    "review_onboarding",
    "review_update",
    "resume_update",
    "setup_git",
    "initialize_vault",
    "inspect_history",
    "refresh_history",
    "resolve_history",
    "execute_history",
]


class HistoryAdmission(ReconciliationContract):
    schema_id: Literal["brz2obsidian.history-admission"] = (
        "brz2obsidian.history-admission"
    )
    schema_version: Literal[1] = 1
    status: Literal[
        "recovery_required",
        "available",
        "onboarding_required",
        "unavailable",
        "setup_required",
        "initialization_required",
    ]
    code: Literal[
        "recovery_first",
        "history_available",
        "onboarding_required",
        "history_unavailable",
        "git_setup_required",
        "repository_initialization_required",
    ]
    next_actions: tuple[HistoryNextAction, ...]
    operation: VaultApplyResult
    checkpoint: CheckpointLocator | None
    history_retained: bool
    recovery_gaps: tuple[str, ...]
    findings: tuple[str, ...]
    summary: str
    guidance: tuple[str, ...]

    @model_validator(mode="after")
    def truthful_routes(self):
        if len(set(self.next_actions)) != len(self.next_actions):
            raise ValueError("History actions must be distinct")
        if self.status == "recovery_required" and (
            "review_recovery" not in self.next_actions
            or set(self.next_actions)
            - {"review_recovery", "setup_git", "review_history_repair"}
        ):
            raise ValueError(
                "Unresolved operation state permits only recovery/setup routing"
            )
        if (
            self.status == "recovery_required"
            and "review_history_repair" in self.next_actions
            and (
                self.operation.status != "unknown"
                or self.operation.operation_id is not None
            )
        ):
            raise ValueError(
                "Known incomplete operations require recovery before copy repair"
            )
        if self.status == "available" and (
            self.checkpoint is None or not self.history_retained
        ):
            raise ValueError(
                "Available history requires its validated current checkpoint"
            )
        if self.status == "onboarding_required" and (
            self.checkpoint is not None or self.history_retained
        ):
            raise ValueError("Absent history cannot claim a retained checkpoint")
        if self.status == "initialization_required" and (
            self.next_actions != ("initialize_vault",)
            or self.checkpoint is not None
            or self.history_retained
            or self.operation.operation_id is not None
            or self.operation.intent_commit is not None
        ):
            raise ValueError(
                "Initialization routing requires explicit repository absence"
            )
        return self


class HistoryWorkflowPreparation(ReconciliationContract):
    """One native preparation and its caller locations, never independent authority."""

    schema_id: Literal["brz2obsidian.history-workflow-preparation"] = (
        "brz2obsidian.history-workflow-preparation"
    )
    schema_version: Literal[1] = 1
    kind: Literal["recovery", "undo", "repair"]
    vault: str = Field(min_length=1)
    copy_path: str | None = None
    native: (
        VaultRecoveryPreparation | VaultUndoPreparation | HistoryRepairPreparation
    ) = Field(discriminator="schema_id")

    @model_validator(mode="after")
    def native_role(self):
        if self.kind == "recovery":
            valid = isinstance(
                self.native, VaultRecoveryPreparation
            ) and self.native.status in ("offered", "cleanup")
        elif self.kind == "undo":
            valid = (
                isinstance(self.native, VaultUndoPreparation)
                and self.native.status == "offered"
            )
        else:
            valid = (
                isinstance(self.native, HistoryRepairPreparation)
                and self.native.status == "prepared"
                and self.native.validation.status == "matching"
                and bool(self.copy_path)
            )
        if not valid or self.kind != "repair" and self.copy_path is not None:
            raise ValueError(
                "History workflow must retain the exact admitted native role"
            )
        return self

    @property
    def ready(self):
        if isinstance(self.native, HistoryRepairPreparation):
            return True
        if (
            isinstance(self.native, VaultRecoveryPreparation)
            and self.native.status == "cleanup"
        ):
            return True
        return self.native.review is not None and self.native.review.ready


class HistoryWorkflowResult(ReconciliationContract):
    schema_id: Literal["brz2obsidian.history-workflow-result"] = (
        "brz2obsidian.history-workflow-result"
    )
    schema_version: Literal[1] = 1
    kind: Literal["recovery", "undo", "repair"] | None = None
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
    code: str
    summary: str
    next_actions: tuple[HistoryNextAction, ...]
    preparation: HistoryWorkflowPreparation | None = None
    operation: VaultApplyResult | None = None
    repair: HistoryRepairResult | None = None
    copy_validation: HistoryCopyValidation | None = None
    publication: (
        Literal["not_started", "not_published", "partial", "complete", "unknown"] | None
    ) = None
    history_retained: bool | None = None
    recovery_gaps: tuple[str, ...] | None = None
    guidance: tuple[str, ...]

    @model_validator(mode="after")
    def native_truth(self):
        if self.operation is not None and self.repair is not None:
            raise ValueError("A history action has one native execution result")
        if self.publication != (
            None if self.operation is None else self.operation.publication
        ):
            raise ValueError(
                "Publication describes the observed native file operation only"
            )
        if self.status in ("direction_required", "review_required", "ready"):
            if (
                self.preparation is None
                or (self.status == "ready") != self.preparation.ready
            ):
                raise ValueError(
                    "Review readiness must come from the admitted native preparation"
                )
            if self.kind != self.preparation.kind:
                raise ValueError("History result must preserve its preparation role")
            if self.status == "direction_required" and not (
                isinstance(self.preparation.native, VaultRecoveryPreparation)
                and self.preparation.native.review is None
            ):
                raise ValueError(
                    "Only an unselected recovery direction needs a direction choice"
                )
        elif self.preparation is not None:
            raise ValueError(
                "A completed or refused action cannot carry live preparation authority"
            )
        before_repair_cancel = (
            self.status == "cancelled"
            and self.kind == "repair"
            and self.code == "repair_cancelled_before_start"
            and self.operation is None
            and self.repair is None
            and self.history_retained is None
        )
        if (
            self.status
            in (
                "applied",
                "no_content_change",
                "undone",
                "restored",
                "cancelled",
                "incomplete",
                "content_complete",
            )
            and not before_repair_cancel
            and (self.operation is None or self.operation.status != self.status)
        ):
            raise ValueError("Operation outcomes must retain their exact native result")
        if self.status == "repaired" and (
            self.repair is None or self.repair.status != "repaired"
        ):
            raise ValueError(
                "Repaired history requires the verified native repair result"
            )
        if self.repair is not None and self.kind != "repair":
            raise ValueError("Native repair outcome requires the repair workflow role")
        return self
