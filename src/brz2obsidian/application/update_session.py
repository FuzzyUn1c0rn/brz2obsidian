"""Serialized host reduction; worker and native validators retain authority."""

from dataclasses import dataclass, replace
from uuid import uuid4

from .contract_values import absolute, request_identity
from .contracts import WorkerRequest
from .update_context_contracts import UpdateContextBinding, UpdateContextResult
from .update_history_contracts import HistoryContextBinding

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
    control_code: str | None = None
    worker_epoch: str | None = None
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
            self.snapshot = replace(self.snapshot, worker_epoch=worker_id)

    def queue_cancel(self, request_id):
        if self._active is not None and self._active[0].request_id == request_id:
            self.snapshot = replace(self.snapshot, control_code="cancellation_queued")
        return self.snapshot

    def uncertain(self, worker_id):
        if worker_id == self._worker_id:
            self._poisoned = True
            self.snapshot = replace(
                self.snapshot,
                binding=None,
                review_ready=False,
                needs_inspection=True,
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
            control_code=None,
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
                needs_inspection=terminal.phase != "not_started",
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
        self.snapshot = replace(
            self.snapshot,
            binding=result.binding,
            review_ready=result.ready,
            draft_pending=result.draft_pending,
            needs_inspection=result.status
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
            history_retained=result.history_retained,
            checkpoint_commit=result.checkpoint_commit,
            publication=result.publication,
            next_actions=result.next_actions,
            reply=result,
        )
        return self.snapshot
