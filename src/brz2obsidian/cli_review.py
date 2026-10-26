"""CLI presentation over the shared review lifecycle, separate from worker framing."""

from typing import Literal

from pydantic import Field

from .application.checkpoint_contracts import CheckpointLocator
from .application.operations import Operations
from .application.review_offers import choice_page
from .application.update_context_contracts import UpdateChoiceOffer
from .application.update_contracts import UpdateReviewPage
from .application.vault_update_contracts import VaultApplyResult
from .contracts import OutputIdentity, ReconciliationContract, SourceIdentity


class CliReviewResult(ReconciliationContract):
    schema_: Literal["brz2obsidian.cli-review-result"] = Field(
        default="brz2obsidian.cli-review-result", alias="schema"
    )
    schema_version: Literal[1] = 1
    command: Literal["status", "inspect", "apply"]
    status: Literal[
        "available",
        "initialization_required",
        "onboarding_required",
        "setup_required",
        "unavailable",
        "recovery_required",
        "unknown",
        "prepared_review",
        "unresolved",
        "stale_review",
        "refused",
        "failed",
        "publication_unknown",
        "applied",
        "no_content_change",
        "cancelled_before_publication",
    ]
    code: str
    ready: bool = False
    proposal_id: str | None = None
    generation: int | None = Field(default=None, ge=1)
    source: SourceIdentity | None = None
    output_identity: OutputIdentity | None = None
    changes: int | None = Field(default=None, ge=0)
    unresolved: int | None = Field(default=None, ge=0)
    stale: int | None = Field(default=None, ge=0)
    publication: (
        Literal["not_started", "not_published", "partial", "complete", "unknown"] | None
    ) = None
    page: UpdateReviewPage | None = None
    choices: tuple[UpdateChoiceOffer, ...] = ()
    choices_total: int | None = Field(default=None, ge=0)
    choices_next_offset: int | None = Field(default=None, ge=0)
    omissions: tuple[str, ...] = ()
    history_retained: bool | None = None
    checkpoint: CheckpointLocator | None = None
    checkpoint_commit: str | None = None
    operation: VaultApplyResult | None = None
    recovery_gaps: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()
    summary: str
    guidance: tuple[str, ...]


def report(result, *, json_output):
    exit_code = (
        0
        if result.status == "available"
        or (result.command == "inspect" and result.status == "prepared_review")
        or (
            result.command == "apply"
            and result.status in ("applied", "no_content_change")
        )
        else 2
    )
    if result.status in ("unknown", "failed", "publication_unknown") or (
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
    if result.source is not None:
        print(
            f"Source: {result.source.source_id}; module: {result.source.module_id} {result.source.module_version}; format: {result.source.format_version}"
        )
    if result.proposal_id is not None:
        print(
            f"Proposal: {result.proposal_id}; generation: {result.generation}; ready: {result.ready}"
        )
        print(
            f"Review changes: {result.changes}; unresolved: {result.unresolved}; stale: {result.stale}"
        )
    if result.publication is not None:
        print(
            f"Publication: {result.publication}; retained history: {result.history_retained}"
        )
    if result.page is not None:
        print(
            f"Review page: {result.page.offset}; total: {result.page.total}; next: {result.page.next_offset}; omitted: {result.page.omitted}"
        )
    if result.omissions:
        print("Omitted detail: " + ", ".join(result.omissions))
    if result.checkpoint is not None:
        print(
            f"Checkpoint: {result.checkpoint.commit}; "
            f"generation: {result.checkpoint.generation}"
        )
    elif result.checkpoint_commit is not None:
        print(f"Checkpoint commit: {result.checkpoint_commit}")
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
    if args.review_command == "apply":
        return report(_apply(args), json_output=args.json_output)
    if args.review_command == "inspect":
        return report(_inspect(args), json_output=args.json_output)
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


def _update_result(observed, **changes):
    preparation = observed.preparation
    values = {
        "command": "inspect",
        "status": observed.status,
        "code": observed.code,
        "ready": observed.ready,
        "proposal_id": observed.operation_id,
        "generation": observed.generation,
        "source": preparation.observed_source if preparation else None,
        "output_identity": preparation.review.facts.incoming_identity
        if preparation
        else None,
        "changes": observed.changes,
        "unresolved": observed.unresolved,
        "stale": observed.stale,
        "publication": observed.publication,
        "history_retained": observed.history_retained,
        "checkpoint": preparation.locator
        if preparation is not None
        else observed.checkpoint,
        "checkpoint_commit": observed.checkpoint_commit,
        "operation": observed.application,
        "recovery_gaps": observed.recovery_gaps,
        "findings": observed.findings,
        "next_actions": observed.next_actions,
        "summary": observed.summary,
        "guidance": (observed.guidance,),
    }
    values.update(changes)
    return CliReviewResult(**values)


def _inspect(args):
    if not (
        args.offset >= 0
        and 1 <= args.limit <= 100
        and args.byte_offset >= 0
        and 0 <= args.byte_limit <= 65536
        and (args.generation is None or args.generation >= 1)
    ):
        return CliReviewResult(
            command="inspect",
            status="refused",
            code="invalid_review_arguments",
            summary="Review bounds or generation are invalid.",
            guidance=(
                "Use a positive generation, up to 100 changes, and at most 65536 content bytes.",
            ),
        )
    operations = Operations()
    loaded = operations.load_update(args.vault)
    if loaded.loaded is None:
        return _update_result(loaded)
    if (
        (args.proposal_id is not None and args.proposal_id != loaded.operation_id)
        or (args.generation is not None and args.generation != loaded.generation)
        or (
            args.checkpoint is not None
            and (
                loaded.checkpoint is None or args.checkpoint != loaded.checkpoint.commit
            )
        )
    ):
        return _update_result(
            loaded,
            status="stale_review",
            code="review_identity_changed",
            ready=False,
            next_actions=("inspect_saved_review",),
        )
    current = operations.resume_update(args.vault)
    if current.preparation is None:
        return _update_result(current)
    if (current.operation_id, current.generation, current.preparation.locator) != (
        loaded.operation_id,
        loaded.generation,
        loaded.checkpoint,
    ):
        return _update_result(
            current,
            status="stale_review",
            code="review_identity_changed",
            ready=False,
            next_actions=("review_update",),
        )
    page = operations.inspect_update_review(
        current.preparation,
        proposal_id=current.operation_id,
        generation=current.generation,
        offset=args.offset,
        limit=args.limit,
        byte_offset=args.byte_offset,
        byte_limit=args.byte_limit,
    )
    if page.status != "available":
        return _update_result(
            current,
            status="refused",
            code=page.code,
            ready=False,
            next_actions=("inspect_saved_review",),
        )
    choices, total, following = choice_page(
        current.preparation, offset=args.offset, limit=args.limit
    )
    return _update_result(
        current,
        page=page,
        choices=choices,
        choices_total=total,
        choices_next_offset=following,
        omissions=("attachment_alternative_outputs",),
    )


def _apply(args):
    if args.generation < 1:
        return CliReviewResult(
            command="apply",
            status="refused",
            code="invalid_review_arguments",
            summary="Review generation must be positive.",
            guidance=("Inspect the saved proposal before applying it.",),
        )
    operations = Operations()
    loaded = operations.load_update(args.vault)
    if loaded.loaded is None:
        return _update_result(loaded, command="apply")
    if (
        args.proposal_id != loaded.operation_id
        or args.generation != loaded.generation
        or loaded.checkpoint is None
        or args.checkpoint != loaded.checkpoint.commit
    ):
        return _update_result(
            loaded,
            command="apply",
            status="stale_review",
            code="review_identity_changed",
            ready=False,
            next_actions=("inspect_saved_review",),
        )
    current = operations.resume_update(args.vault)
    if current.preparation is None:
        return _update_result(current, command="apply")
    if (current.operation_id, current.generation, current.preparation.locator) != (
        loaded.operation_id,
        loaded.generation,
        loaded.checkpoint,
    ):
        return _update_result(
            current,
            command="apply",
            status="stale_review",
            code="review_identity_changed",
            ready=False,
            next_actions=("review_update",),
        )
    if not current.ready:
        return _update_result(
            current,
            command="apply",
            status="unresolved",
            code="review_not_ready",
            ready=False,
            next_actions=("resolve_update", "save_update"),
        )
    applied = operations.apply_update(current.preparation)
    return _update_result(
        applied,
        command="apply",
        proposal_id=current.operation_id,
        generation=current.generation,
        source=current.preparation.observed_source,
        output_identity=current.preparation.review.facts.incoming_identity,
    )


def report_failure(args):
    result = CliReviewResult(
        command=args.review_command,
        status="unknown",
        code="operation_failure",
        publication="unknown" if args.review_command == "apply" else None,
        summary="The review operation could not complete. The cause is not known.",
        guidance=("Inspect the vault again before starting a change.",),
        next_actions=("inspect_history",),
    )
    return report(result, json_output=args.json_output)
