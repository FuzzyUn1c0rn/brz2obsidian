"""Serialized host reduction; worker and native validators retain authority."""

from dataclasses import dataclass, replace
from uuid import uuid4

from .contract_values import absolute, request_identity
from .contracts import WorkerRequest
from .update_context_contracts import UpdateContextBinding, UpdateContextResult
from .update_history_contracts import HistoryContextBinding
from .update_stream import WorkerProgress

_CONTENT = frozenset(
    (
        "page",
        "references",
        "choices",
        "choice_details",
        "begin_edit",
        "write_edit",
        "seal_edit",
        "stage_references",
        "history_choices",
    )
)


@dataclass(frozen=True)
class UpdateSessionSnapshot:
    revision: int = 0
    vault: str | None = None
    selection_id: str | None = None
    binding: UpdateContextBinding | HistoryContextBinding | None = None
    review_ready: bool = False
    draft_pending: bool = False
    needs_inspection: bool = False
    changes: int = 0
    unresolved: int = 0
    stale: int = 0
    history_retained: bool | None = False
    checkpoint_commit: str | None = None
    publication: str = "not_started"
    transport_phase: str | None = None
    transport_code: str | None = None
    next_actions: tuple[str, ...] = ()
    active_request_id: str | None = None
    active_command: str | None = None
    close_disposition: str | None = None
    control_code: str | None = None
    worker_epoch: str | None = None
    progress: WorkerProgress | None = None
    reply: UpdateContextResult | None = None
    last_operation: UpdateContextResult | None = None
    last_operation_vault: str | None = None

    @property
    def ready(self):
        return (
            self.review_ready
            and self.binding is not None
            and not (
                self.active_request_id or self.draft_pending or self.needs_inspection
            )
        )

    @property
    def close_options(self):
        if self.active_request_id is not None:
            return ("continue", "background", "wait", "safe_stop")
        if self.draft_pending:
            return ("continue", "discard")
        if self.binding is not None:
            return (
                ("continue", "save", "discard")
                if (
                    isinstance(self.binding, UpdateContextBinding)
                    and not self.draft_pending
                )
                else ("continue", "discard")
            )
        return ("close",)


class UpdateSession:
    def __init__(self):
        self.snapshot = UpdateSessionSnapshot()
        self._selection_revision = 0
        self._active = None
        self._worker_id = None
        self._poisoned = False

    def bind_worker(self, worker_id):
        if self._worker_id != worker_id:
            self._worker_id, self._poisoned = worker_id, False
            self.snapshot = replace(
                self.snapshot, worker_epoch=worker_id, progress=None
            )

    def observe(self, worker_id, actual, progress):
        progress = WorkerProgress.model_validate(progress)
        if self._active is None or self._poisoned:
            return self.snapshot
        request, selection_revision = self._active
        previous = self.snapshot.progress
        if (
            worker_id != self._worker_id
            or selection_revision != self._selection_revision
            or actual.request_id != request.request_id
            or actual.arguments != request.arguments
            or progress.request_id != actual.request_id
            or progress.sequence != actual.sequence
            or previous is not None
            and (
                progress.ordinal <= previous.ordinal
                or progress.elapsed_ms < previous.elapsed_ms
            )
        ):
            return self.snapshot
        self.snapshot = replace(self.snapshot, progress=progress)
        return self.snapshot

    def queue_cancel(self, request_id):
        if self._active is not None and self._active[0].request_id == request_id:
            self.snapshot = replace(self.snapshot, control_code="cancellation_queued")
        return self.snapshot

    def request_close(self, choice, *, expected_revision):
        state = self.snapshot
        if (
            type(expected_revision) is not int
            or expected_revision != state.revision
            or choice not in state.close_options
        ):
            return False
        self.snapshot = replace(
            state, revision=state.revision + 1, close_disposition=choice
        )
        return True

    def uncertain(self, worker_id):
        if worker_id == self._worker_id:
            self._poisoned = True
            self.snapshot = replace(
                self.snapshot,
                binding=None,
                review_ready=False,
                needs_inspection=True,
                progress=None,
                publication="unknown",
                next_actions=("inspect_update_status",),
                reply=None,
            )
        return self.snapshot

    def control(self, request_id, terminal):
        if self._active is not None and self._active[0].request_id == request_id:
            response = terminal.response
            code = (
                response.result.code
                if terminal.phase == "completed"
                and response is not None
                and response.result is not None
                else "control_unavailable"
            )
            self.snapshot = replace(self.snapshot, control_code=code)
        return self.snapshot

    def select(self, vault, *, selection_id):
        vault, selection_id = absolute(vault), request_identity(selection_id)
        self._selection_revision += 1
        previous = self.snapshot
        self.snapshot = UpdateSessionSnapshot(
            revision=previous.revision + 1,
            vault=vault,
            selection_id=selection_id,
            active_request_id=previous.active_request_id,
            active_command=previous.active_command,
            last_operation=previous.last_operation,
            last_operation_vault=previous.last_operation_vault,
            worker_epoch=previous.worker_epoch,
        )
        return self.snapshot

    def start(self, arguments):
        state = self.snapshot
        request = WorkerRequest(
            operation="update", request_id=str(uuid4()), sequence=1, arguments=arguments
        )
        args = request.arguments
        if self._active is not None:
            return None
        binding = getattr(
            args, "binding", getattr(getattr(args, "handle", None), "binding", None)
        )
        if args.command == "close" and binding is None and state.binding is not None:
            return None
        if binding is not None and binding != state.binding:
            # A stale selection may retain a prior operation's close capability,
            # but it cannot use that capability to publish another operation.
            prior = state.last_operation
            if not (
                args.command == "close"
                and prior is not None
                and binding == prior.binding
            ):
                return None
        if args.command in ("prepare", "load", "resume", "history") and (
            args.vault != state.vault
            or args.selection_id != state.selection_id
            or state.binding is not None
        ):
            return None
        self._active = request, self._selection_revision
        self.snapshot = replace(
            state,
            revision=state.revision + 1,
            active_request_id=request.request_id,
            active_command=args.command,
            close_disposition=None,
            control_code=None,
            progress=None,
            transport_phase=None,
            transport_code=None,
        )
        return request

    def complete(self, request_id, terminal):
        if self._active is None or self._active[0].request_id != request_id:
            return self.snapshot
        request, selection_revision = self._active
        self._active = None
        state = self.snapshot
        self.snapshot = replace(
            state,
            revision=state.revision + 1,
            active_request_id=None,
            active_command=None,
            close_disposition=None,
            progress=None,
            control_code=None,
            transport_phase=terminal.phase,
            transport_code=terminal.code,
        )
        response = terminal.response
        if (
            self._poisoned
            or terminal.phase != "completed"
            or response is None
            or response.protocol_error is not None
            or response.request_id != request_id
            or response.operation != "update"
        ):
            self.snapshot = replace(
                self.snapshot,
                binding=None,
                review_ready=False,
                needs_inspection=state.needs_inspection
                or terminal.phase != "not_started",
                publication="unknown"
                if terminal.phase != "not_started"
                else state.publication,
                next_actions=("inspect_update_status",),
            )
            return self.snapshot
        result = UpdateContextResult.model_validate(response.result)
        binding = getattr(request.arguments, "binding", None)
        vault = getattr(
            request.arguments, "vault", binding.vault if binding else state.vault
        )
        self.snapshot = replace(
            self.snapshot, last_operation=result, last_operation_vault=vault
        )
        if selection_revision != self._selection_revision:
            return self.snapshot
        if result.binding is not None and (
            result.binding.vault != state.vault
            or result.binding.selection_id != state.selection_id
        ):
            self.snapshot = replace(
                self.snapshot,
                binding=None,
                review_ready=False,
                needs_inspection=True,
                publication="unknown",
                next_actions=("inspect_update_status",),
            )
            return self.snapshot
        if request.arguments.command in _CONTENT and result.status == "available":
            if (
                state.binding is None
                or result.binding is None
                or result.binding.model_dump(exclude={"revision"})
                != state.binding.model_dump(exclude={"revision"})
                or result.binding.revision < state.binding.revision
            ):
                self.snapshot = replace(
                    self.snapshot,
                    binding=None,
                    review_ready=False,
                    needs_inspection=True,
                    publication="unknown",
                    next_actions=("inspect_update_status",),
                )
                return self.snapshot
            self.snapshot = replace(
                self.snapshot,
                binding=result.binding,
                reply=result,
                draft_pending=result.draft_pending,
            )
            return self.snapshot
        reviewed_history = (
            isinstance(result.binding, HistoryContextBinding)
            and result.history_action is not None
            and result.history_action.status
            in ("direction_required", "review_required", "ready")
        )
        qualified = (
            reviewed_history
            or result.history is not None
            or bool(result.history_action and result.history_action.operation)
            or (
                request.arguments.command in ("prepare", "resume", "refresh")
                and isinstance(result.binding, UpdateContextBinding)
                and result.status in ("prepared_review", "unresolved", "stale_review")
            )
            or (
                request.arguments.command == "load"
                and result.code == "revalidation_required"
                and result.history_retained is True
                and result.checkpoint_commit is not None
            )
        )
        pending_inspection = state.needs_inspection and not qualified
        self.snapshot = replace(
            self.snapshot,
            binding=None if pending_inspection else result.binding,
            review_ready=result.ready and not pending_inspection,
            draft_pending=result.draft_pending,
            needs_inspection=False
            if reviewed_history
            else pending_inspection
            or result.status
            in (
                "publication_unknown",
                "recovery_required",
                "unknown",
                "incomplete",
                "content_complete",
            )
            or result.publication in ("partial", "unknown")
            or bool(
                result.history_action
                and result.history_action.operation
                and result.history_action.operation.recovery_required
            ),
            changes=result.changes,
            unresolved=result.unresolved,
            stale=result.stale,
            history_retained=state.history_retained
            if pending_inspection
            else result.history_retained,
            checkpoint_commit=state.checkpoint_commit
            if pending_inspection
            else result.checkpoint_commit,
            publication=state.publication if pending_inspection else result.publication,
            next_actions=("continue_review", "discard")
            if pending_inspection and result.draft_pending and result.binding is None
            else ("inspect_history",)
            if pending_inspection
            else result.next_actions,
            reply=result,
        )
        return self.snapshot
