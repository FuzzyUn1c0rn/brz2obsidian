"""Shared current history actions composed from existing S2 public operations."""

from pathlib import Path

from .checkpoint_contracts import VaultHistoryInspection
from .history_workflow_contracts import (
    HistoryAdmission,
    HistoryWorkflowPreparation,
    HistoryWorkflowResult,
)
from .vault_recovery_contracts import VaultRecoveryPreparation
from .vault_repair_contracts import HistoryRepairResult
from .vault_update_contracts import VaultApplyResult

_GUIDANCE = (
    "Keep the vault idle while an operation runs; review later edits between stopped operations.",
    "Converter history is retained locally and grows as operations are saved; history cleanup is unavailable.",
    "Keep a complete local vault copy including hidden .git and .brz2obsidian content. Supply its local folder for independent matching-history validation; a copied marker alone proves no ownership.",
    "Matching-copy repair restores verified retained history only, not authored files or saved write authority. A sync, clone or copied note folder is not a guarantee that converter history is complete; remote transport is unavailable.",
    "Install Git with the required local storage commands, make git available to the application, and restart the converter. No Git account or command-line experience is required.",
    "Undo reviews only the latest eligible completed import/update. Keeping current content may retain imported changes while reversing eligible others; older operations are not selected past maintenance.",
    "Repair accepts cancellation before native object storage starts; it does not interrupt the native repair partway through verification.",
)


def history_admission(
    history: VaultHistoryInspection, operation: VaultApplyResult
) -> HistoryAdmission:
    """Describe supplied observations; callers cannot turn this value into write authority."""
    history = VaultHistoryInspection.model_validate(history)
    operation = VaultApplyResult.model_validate(operation)
    admission = history.admission
    checkpoint = history.checkpoint
    locator = (
        checkpoint.locator
        if checkpoint is not None
        and checkpoint.status == "valid"
        and checkpoint.manifest is not None
        else None
    )
    retained = history.status == "intact" and locator is not None
    git_setup = any(f.policy == "git" for f in admission.findings)
    if (
        history.status == "unavailable"
        and checkpoint is None
        and admission.status == "supported"
        and admission.repository.kind == "none"
        and admission.admitted_actions == ("review_initialization",)
        and not admission.findings
        and operation.operation_id is None
        and operation.intent_commit is None
        and operation.code in ("operation_history_invalid", "operation_absent")
    ):
        status, code = "initialization_required", "repository_initialization_required"
        actions = ("initialize_vault",)
        summary = "Review explicit repository initialization, then inspect onboarding; no repository has been created."
    elif (
        operation.recovery_required
        or operation.status in ("incomplete", "content_complete", "unknown")
        or operation.publication in ("partial", "unknown")
        or admission.status == "recovery_first"
    ):
        status, code = "recovery_required", "recovery_first"
        actions = (
            ("setup_git", "review_recovery") if git_setup else ("review_recovery",)
        )
        if (
            operation.status == "unknown"
            and operation.operation_id is None
            and admission.repository.kind == "root"
        ):
            # This opens read-only matching-copy validation, not repair
            # permission. Native S2 alone can prove terminal missing payloads
            # independently of incompatible incomplete/corrupt metadata.
            actions += ("review_history_repair",)
        summary = "Inspect the retained or suspected operation before starting another vault change."
    elif git_setup:
        status, code, actions = "setup_required", "git_setup_required", ("setup_git",)
        summary = "Complete supported Git setup, then inspect the vault again."
    elif retained and admission.status == "supported":
        status, code = "available", "history_available"
        actions = (
            ("resume_update",)
            if checkpoint.manifest.boundary in ("local", "prepared")
            and checkpoint.review is not None
            else ("review_update",)
        )
        if (
            checkpoint.manifest.boundary == "result"
            and checkpoint.review is not None
            and checkpoint.review.saved.plan.facts.format_operation.kind
            in ("source_update", "onboarding")
            and operation.status == "applied"
            and operation.kind == "apply"
            and operation.result_commit == locator.commit
            and operation.intent_commit == checkpoint.manifest.operation_intent_commit
        ):
            actions += ("review_undo",)
        summary = "Current retained history is available for a fresh reviewed action."
    elif history.status == "absent" and admission.status == "supported":
        status, code, actions = (
            "onboarding_required",
            "onboarding_required",
            ("review_onboarding",),
        )
        summary = "No supported retained baseline is available; review onboarding before a new change."
    else:
        status, code = "unavailable", "history_unavailable"
        actions = (
            ("review_history_repair", "review_onboarding")
            if admission.status == "supported"
            else ("inspect_history",)
        )
        summary = "Retained history is unavailable; inspect matching-copy repair or the offered onboarding route."
    return HistoryAdmission(
        status=status,
        code=code,
        next_actions=actions,
        operation=operation,
        checkpoint=locator,
        history_retained=retained,
        recovery_gaps=admission.recovery_gaps,
        findings=tuple(f.code for f in admission.findings),
        summary=summary,
        guidance=_GUIDANCE,
        initialization_fingerprint=admission.observation_fingerprint
        if status == "initialization_required"
        else None,
    )


def inspect_history_workflow(operations, vault):
    """Obtain restart observations directly; a supplied projection is never admitted."""
    operation = operations.inspect_update_status(vault)
    history = operations.inspect_history(vault)
    return history_admission(history, operation)


def _refused(code, *, operation=None, recovery=False, validation=None):
    return HistoryWorkflowResult(
        status="recovery_required" if recovery else "refused",
        code=code,
        summary="Inspect current retained history before continuing this action.",
        next_actions=("review_recovery",) if recovery else ("inspect_history",),
        operation=operation,
        copy_validation=validation,
        publication=None if operation is None else operation.publication,
        history_retained=None
        if operation is None or operation.history == "unknown"
        else operation.history != "none",
        guidance=_GUIDANCE,
    )


def _prepared(vault, kind, native, *, copy=None):
    admitted = (
        native.status in ("offered", "cleanup")
        if kind == "recovery"
        else native.status == "offered"
        if kind == "undo"
        else native.status == "prepared"
    )
    if not admitted:
        return _refused(
            native.code,
            recovery=native.status == "recovery_required"
            or kind == "recovery"
            and native.status == "unavailable",
        )
    preparation = HistoryWorkflowPreparation(
        kind=kind,
        vault=str(Path(vault).absolute()),
        copy_path=None if copy is None else str(Path(copy).absolute()),
        native=native,
    )
    direction_required = (
        isinstance(native, VaultRecoveryPreparation)
        and native.status == "offered"
        and native.review is None
    )
    status = (
        "ready"
        if preparation.ready
        else "direction_required"
        if direction_required
        else "review_required"
    )
    return HistoryWorkflowResult(
        status=status,
        kind=kind,
        code=native.code,
        preparation=preparation,
        summary="Review the whole latest operation; current choices can retain imported and later content."
        if kind == "undo"
        else "Review the current native history preparation before execution.",
        next_actions=("execute_history", "refresh_history")
        if preparation.ready
        else ("review_recovery",)
        if direction_required
        else ("resolve_history", "refresh_history"),
        copy_validation=native.validation if kind == "repair" else None,
        guidance=_GUIDANCE,
    )


def prepare_history_workflow(operations, vault, *, kind, direction=None, copy=None):
    """Prepare one existing native role, preserving its current physical admission."""
    if kind == "recovery" and copy is None and direction in (None, "finish", "restore"):
        return _prepared(
            vault, kind, operations.prepare_recovery(vault, direction=direction)
        )
    if kind == "undo" and direction is None and copy is None:
        return _prepared(vault, kind, operations.prepare_undo(vault))
    if kind == "repair" and direction is None and copy is not None:
        # This engine independently distinguishes compatible terminal missing
        # payload repair from unknown/incomplete operation metadata. A broad
        # status projection must not suppress that stronger current proof.
        validation = operations.validate_history_copy(vault, copy)
        if validation.status != "matching":
            return _refused(
                validation.code,
                recovery=validation.code == "recovery_first",
                validation=validation,
            )
        return _prepared(
            vault,
            kind,
            operations.prepare_history_repair(vault, copy, validation),
            copy=copy,
        )
    return _refused("unsupported_history_request")


def _current_recovery(operations, preparation):
    native = preparation.native
    observed = operations.inspect_update_status(preparation.vault)
    if (
        not observed.recovery_required
        or (
            observed.operation_id,
            observed.kind,
            observed.generation,
            observed.intent_commit,
        )
        != (native.operation_id, native.kind, native.generation, native.intent_commit)
        or observed.review_generation is not None
        and observed.direction != native.direction
    ):
        return observed, _refused("history_authority_changed", operation=observed)
    return observed, None


def refresh_history_workflow(operations, preparation):
    try:
        saved = HistoryWorkflowPreparation.model_validate(preparation)
    except ValueError, TypeError:
        return _refused("invalid_history_preparation")
    if saved.kind == "recovery":
        _, blocked = _current_recovery(operations, saved)
        if blocked is not None:
            return blocked
        native = operations.refresh_recovery(saved.vault, saved.native)
    elif saved.kind == "undo":
        native = operations.prepare_undo(saved.vault, previous=saved.native)
    else:
        native = operations.prepare_history_repair(
            saved.vault, saved.copy_path, saved.native.validation
        )
    return _prepared(saved.vault, saved.kind, native, copy=saved.copy_path)


def resolve_history_workflow(operations, preparation, action):
    try:
        saved = HistoryWorkflowPreparation.model_validate(preparation)
    except ValueError, TypeError:
        return _refused("invalid_history_preparation")
    if saved.kind == "recovery":
        _, blocked = _current_recovery(operations, saved)
        if blocked is not None:
            return blocked
        native = operations.resolve_recovery(saved.vault, saved.native, action)
    elif saved.kind == "undo":
        native = operations.resolve_undo(saved.vault, saved.native, action)
    else:
        return _refused("history_action_not_reviewable")
    return _prepared(saved.vault, saved.kind, native)


def _executed(native, kind):
    if isinstance(native, HistoryRepairResult):
        return HistoryWorkflowResult(
            status=native.status,
            kind=kind,
            code=native.code,
            repair=native,
            summary="Verified converter history was repaired; authored files were not restored."
            if native.status == "repaired"
            else "Inspect matching-history repair before continuing; authored files were not restored.",
            next_actions=("inspect_history",),
            history_retained=native.history_retained,
            guidance=_GUIDANCE,
        )
    summaries = {
        "applied": "The reviewed operation was applied.",
        "no_content_change": "The reviewed operation completed without changing authored files.",
        "undone": "Latest reviewed Undo completed; current choices may retain imported or later content while reversing eligible other changes.",
        "restored": "Reviewed restoration completed; retained current choices can preserve later edits.",
        "content_complete": "File publication is complete but terminal history/reporting is incomplete; inspect recovery.",
        "unknown": "The operation outcome is uncertain; inspect current retained history before continuing.",
    }
    recovery = native.recovery_required or native.status in (
        "unknown",
        "incomplete",
        "content_complete",
    )
    return HistoryWorkflowResult(
        status=native.status,
        kind=kind,
        code=native.code,
        operation=native,
        publication=native.publication,
        history_retained=None
        if native.history == "unknown"
        else native.history != "none",
        summary=summaries.get(
            native.status,
            "The operation stopped; inspect its current publication and recovery state.",
        ),
        next_actions=("review_recovery",) if recovery else ("inspect_history",),
        guidance=_GUIDANCE,
    )


def execute_history_workflow(operations, preparation, *, cancel=None):
    try:
        saved = HistoryWorkflowPreparation.model_validate(preparation)
    except ValueError, TypeError:
        return _refused("invalid_history_preparation")
    if not saved.ready:
        return _refused("history_review_required")
    if saved.kind == "recovery":
        observed, blocked = _current_recovery(operations, saved)
        if blocked is not None:
            return blocked
        native = operations.execute_recovery(saved.vault, saved.native, cancel=cancel)
        if (native.operation_id, native.kind) == (observed.operation_id, observed.kind):
            # The role comes from this wrapper's actual fresh native
            # observation, never from caller-supplied preparation metadata.
            native = native.model_copy(update={"origin_role": observed.origin_role})
    elif saved.kind == "undo":
        native = operations.execute_undo(saved.vault, saved.native, cancel=cancel)
    else:
        if cancel is not None and not callable(cancel):
            return _refused("invalid_history_cancellation")
        if cancel is not None and cancel():
            return HistoryWorkflowResult(
                status="cancelled",
                kind="repair",
                code="repair_cancelled_before_start",
                summary="Repair was cancelled before native object storage started.",
                next_actions=("inspect_history",),
                copy_validation=saved.native.validation,
                guidance=_GUIDANCE,
            )
        native = operations.execute_history_repair(
            saved.vault, saved.copy_path, saved.native
        )
    return _executed(native, saved.kind)
