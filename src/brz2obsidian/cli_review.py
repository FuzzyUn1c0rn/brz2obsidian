"""CLI presentation over the shared review lifecycle, separate from worker framing."""

from typing import Literal

from pydantic import Field

from .application.checkpoint_contracts import CheckpointLocator
from .application.operations import Operations
from .application.vault_update_contracts import VaultApplyResult
from .contracts import ReconciliationContract


class CliReviewResult(ReconciliationContract):
    schema_: Literal["brz2obsidian.cli-review-result"] = Field(
        default="brz2obsidian.cli-review-result", alias="schema"
    )
    schema_version: Literal[1] = 1
    command: Literal["status"]
    status: Literal[
        "available",
        "initialization_required",
        "onboarding_required",
        "setup_required",
        "unavailable",
        "recovery_required",
        "unknown",
    ]
    code: str
    ready: Literal[False] = False
    history_retained: bool | None = None
    checkpoint: CheckpointLocator | None = None
    operation: VaultApplyResult | None = None
    recovery_gaps: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()
    summary: str
    guidance: tuple[str, ...]


def report(result, *, json_output):
    exit_code = 0 if result.status == "available" else 2
    if result.status == "unknown" or (
        result.status == "recovery_required"
        and result.operation is not None
        and result.operation.status in ("unknown", "failed")
    ):
        exit_code = 1
    if json_output:
        print(result.model_dump_json(by_alias=True))
        return exit_code
    print(f"review {result.command}: {result.status}")
    print(result.summary)
    if result.checkpoint is not None:
        print(
            f"Checkpoint: {result.checkpoint.commit}; "
            f"generation: {result.checkpoint.generation}"
        )
    if result.operation is not None:
        print(f"Outcome: {result.operation.status}")
        print(
            f"Operation: {result.operation.operation_id or 'none'}; "
            f"generation: {result.operation.generation}; "
            f"publication: {result.operation.publication}; "
            f"history: {result.operation.history}"
        )
    print("Next actions: " + ", ".join(result.next_actions))
    for guidance in result.guidance:
        print(guidance)
    return exit_code


def run(args):
    observed = Operations().inspect_history_workflow(args.vault)
    result = CliReviewResult(
        command="status",
        status=observed.status,
        code=observed.code,
        history_retained=observed.history_retained,
        checkpoint=observed.checkpoint,
        operation=observed.operation,
        recovery_gaps=observed.recovery_gaps,
        findings=observed.findings,
        next_actions=observed.next_actions,
        summary=observed.summary,
        guidance=observed.guidance,
    )
    return report(result, json_output=args.json_output)


def report_failure(args):
    result = CliReviewResult(
        command="status",
        status="unknown",
        code="operation_failure",
        summary="Review status could not be established. The cause is not known.",
        guidance=("Inspect the vault again before starting a change.",),
        next_actions=("inspect_history",),
    )
    return report(result, json_output=args.json_output)
