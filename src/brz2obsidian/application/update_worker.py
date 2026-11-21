"""Serialized producer work with a separate live cooperative control reader."""

from queue import Full, Queue
from threading import Event, Lock, Thread

from .contracts import ProtocolError, WorkerResponse
from .protocol import REQUEST_LIMIT, ProtocolFailure, decode_request, encode_response
from .update_context import UpdateContext
from .update_context_contracts import UpdateContextResult
from .update_output import UpdateOutput
from .update_stream import encode_end
from .update_worker_contracts import update_control_scope


class UpdateWorker:
    def __init__(self, *, output, context=None):
        self.context = context if context is not None else UpdateContext()
        self.output = output
        self.closed = False
        self._next_sequence = 1
        self._sequence_lock, self._activity = Lock(), Lock()
        self._delivery = None
        self._output_lost = False
        self._active = None
        self._cancel = Event()

    def _accept(self, request):
        with self._sequence_lock:
            if (
                self.closed
                or request.operation != "update"
                or request.sequence != self._next_sequence
            ):
                self.closed = True
                self._cancel.set()
                raise ProtocolFailure("Invalid producer sequence")
            if request.arguments.command != "cancel":
                with self._activity:
                    if self._active is not None:
                        self.closed = True
                        self._cancel.set()
                        raise ProtocolFailure("A producer request is already admitted")
                    self._active = request
                    self._cancel = Event()
            self._next_sequence += 1

    def _reply(self, request, *, result=None, error=None):
        if result is not None:
            pending = self.context.draft_pending
            result = result.model_copy(
                update={
                    "draft_pending": pending,
                    "ready": result.ready and not pending,
                    **(
                        {
                            "next_actions": ("continue_review", "discard_draft")
                            if result.binding is not None
                            else ("continue_review", "discard")
                        }
                        if pending
                        else {}
                    ),
                }
            )
        response = WorkerResponse(
            request_id=request.request_id,
            sequence=request.sequence,
            operation="update",
            result=result,
            protocol_error=error,
        )
        terminal, end = encode_response(response), encode_end(response)
        try:
            self._output().reply(request, terminal, end)
        except OSError:
            self._output_failed()

    def _output(self):
        if self._delivery is None:
            self._delivery = UpdateOutput(
                self.output, failed=self._output_failed, retired=self._retire
            )
        return self._delivery

    def _output_failed(self):
        self._output_lost = True
        self.closed = True
        self._cancel.set()

    def _retire(self, request):
        with self._activity:
            if (
                self._active is not None
                and self._active.request_id == request.request_id
                and self._active.sequence == request.sequence
            ):
                self._active = None

    def _control(self, request):
        args = request.arguments
        with self._activity:
            current = self._active
            scope = (
                {"binding": args.binding}
                if args.binding is not None
                else {
                    "binding": None,
                    "vault": args.vault,
                    "selection_id": args.selection_id,
                }
            )
            matched = (
                current is not None
                and current.request_id == args.target_request_id
                and current.sequence == args.target_sequence
                and update_control_scope(current.arguments) == scope
            )
            kind = (
                current.arguments.kind
                if current is not None and current.arguments.command == "prepare"
                else self.context.kind
            )
            if matched:
                self._cancel.set()
        self._reply(
            request,
            result=UpdateContextResult(
                status="no_content_change" if matched else "refused",
                code="cancellation_requested" if matched else "context_changed",
                kind=kind,
            ),
        )

    def handle(self, request):
        self._output()
        try:
            self._accept(request)
            if request.arguments.command == "cancel":
                self._control(request)
            else:
                self._perform(request)
        finally:
            self._delivery.close()
            self._delivery = None

    def _execute_context_command(self, command, values, request, cancel):
        if command in (
            "history",
            "initialize_vault",
            "prepare_history",
            "refresh_history",
            "execute_history",
            "history_choices",
            "choose_history",
        ):
            return self._perform_history(command, values, request, cancel)
        if command in ("page", "references", "choices", "choice_details"):
            return self._read_review(command, values)
        if command in (
            "choose",
            "keep_current_unresolved",
            "choose_configuration",
            "stage_references",
            "begin_edit",
            "write_edit",
            "seal_edit",
        ):
            return self._edit_review(command, values, cancel)
        if command in (
            "prepare",
            "apply",
            "refresh",
            "save",
            "load",
            "resume",
            "close",
            "discard_draft",
        ):
            return self._perform_update(command, values, request, cancel)
        raise ProtocolFailure("Unsupported producer command")

    def _perform_history(self, command, values, request, cancel):
        if command == "history":
            return self.context.history(**values, cancel=cancel.is_set)
        if command == "initialize_vault":
            return self.context.initialize_vault(**values)
        if command == "prepare_history":
            return self.context.prepare_history(
                **values,
                cancel=cancel.is_set,
                progress=self._output().observer(request),
            )
        if command == "refresh_history":
            return self.context.refresh_history(
                **values,
                cancel=cancel.is_set,
                progress=self._output().observer(request),
            )
        if command == "execute_history":
            return self.context.execute_history(
                **values,
                cancel=cancel.is_set,
                progress=self._output().observer(request),
            )
        if command == "history_choices":
            return self.context.history_choices(**values)
        if command == "choose_history":
            return self.context.choose_history(**values)
        raise ProtocolFailure("Unsupported producer command")

    def _read_review(self, command, values):
        if command == "page":
            return self.context.page(**values)
        if command == "references":
            return self.context.reference_page(**values)
        if command == "choices":
            return self.context.choice_page(**values)
        if command == "choice_details":
            return self.context.choice_details(**values)
        raise ProtocolFailure("Unsupported producer command")

    def _edit_review(self, command, values, cancel):
        if command == "choose":
            return self.context.choose(**values)
        if command == "keep_current_unresolved":
            return self.context.keep_current_unresolved(**values, cancel=cancel.is_set)
        if command == "choose_configuration":
            return self.context.choose_configuration(**values)
        if command == "stage_references":
            return self.context.stage_references(**values)
        if command == "begin_edit":
            return self.context.begin_edit(**values)
        if command == "write_edit":
            return self.context.write_edit(**values)
        if command == "seal_edit":
            return self.context.seal_edit(**values)
        raise ProtocolFailure("Unsupported producer command")

    def _perform_update(self, command, values, request, cancel):
        if command == "prepare":
            return self.context.prepare(
                **values,
                cancel=cancel.is_set,
                progress=self._output().observer(request),
            )
        if command == "apply":
            return self.context.apply(
                **values,
                cancel=cancel.is_set,
                progress=self._output().observer(request),
            )
        if command == "refresh":
            return self.context.refresh(
                **values,
                cancel=cancel.is_set,
                progress=self._output().observer(request),
            )
        if command == "save":
            return self.context.save(
                **values,
                cancel=cancel.is_set,
                progress=self._output().observer(request),
            )
        if command == "load":
            return self.context.load(**values, cancel=cancel.is_set)
        if command == "resume":
            return self.context.resume(**values, cancel=cancel.is_set)
        if command == "close":
            result = self.context.close(**values)
            self.closed = result.code == "context_closed"
            return result
        if command == "discard_draft":
            return self.context.discard_draft(**values)
        raise ProtocolFailure("Unsupported producer command")

    def _perform(self, request):
        args = request.arguments
        with self._activity:
            cancel = self._cancel
        request_owner = (
            self.context._owner if isinstance(self.context, UpdateContext) else None
        )
        if request_owner is not None:
            request_owner._cancel.probe = cancel.is_set
        try:
            values = args.model_dump(exclude={"command"})
            result = self._execute_context_command(
                args.command, values, request, cancel
            )
            self._reply(request, result=result)
        except Exception:  # noqa: BLE001 -- process boundary never exposes exception/source data.
            self.closed = True
            self._cancel.set()
            self._reply(
                request,
                error=ProtocolError(
                    code="internal_error", message="The operation could not complete."
                ),
            )
        finally:
            if request_owner is not None:
                request_owner._cancel.probe = None
                if (
                    request_owner._session is not None
                    and not request_owner._session._closed
                ):
                    request_owner._session._ledger.release_failed()
            with self._activity:
                if (
                    self._active is not None
                    and self._active.request_id == request.request_id
                    and self._active.sequence == request.sequence
                ):
                    self._active = None

            if self.closed and isinstance(self.context, UpdateContext):
                self.context._retire_owner()

    def _read_controls(self, incoming, first, pending, bad_input):
        try:
            request = first
            while not self.closed:
                if request is None:
                    frame = incoming.readline(REQUEST_LIMIT + 1)
                    if not frame:
                        break
                    request = decode_request(frame)
                self._accept(request)
                if request.arguments.command == "cancel":
                    self._control(request)
                else:
                    pending.put_nowait(request)
                request = None
        except OSError, ProtocolFailure, Full:
            bad_input.set()
            self.closed = True
        finally:
            self._cancel.set()
            pending.put(None)

    def serve(self, incoming, *, first=None):
        self._output()
        pending = Queue(maxsize=1)
        bad_input = Event()

        reader = Thread(
            target=self._read_controls,
            args=(incoming, first, pending, bad_input),
            daemon=True,
            name="update-worker-control",
        )
        reader.start()
        while (request := pending.get()) is not None:
            if not bad_input.is_set():
                self._perform(request)
            if self.closed:
                break
        reader.join()
        try:
            if isinstance(self.context, UpdateContext):
                self.context._retire_owner()
        finally:
            self._delivery.close()
        return 1 if bad_input.is_set() or self._output_lost or not self.closed else 0


def serve_updates(first, incoming, outgoing):
    return UpdateWorker(output=outgoing).serve(incoming, first=first)
