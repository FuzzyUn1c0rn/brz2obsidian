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
                        {"next_actions": ("continue_review", "discard_draft")}
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
            # A lost output channel cannot report even the actual native result.
            # Keep its stream unsealed and request the existing safe stop.
            self._output_failed()

    def _output(self):
        # Started before reader/producer concurrency in serve, or by handle.
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

    def _perform(self, request):
        args = request.arguments
        with self._activity:
            cancel = self._cancel
        try:
            values = args.model_dump(exclude={"command"})
            if args.command == "prepare":
                result = self.context.prepare(
                    **values,
                    cancel=cancel.is_set,
                    progress=self._output().observer(request),
                )
            elif args.command == "history":
                result = self.context.history(**values, cancel=cancel.is_set)
            elif args.command == "initialize_vault":
                result = self.context.initialize_vault(**values)
            elif args.command == "prepare_history":
                result = self.context.prepare_history(
                    **values, cancel=cancel.is_set, progress=self._output().observer(request)
                )
            elif args.command == "refresh_history":
                result = self.context.refresh_history(
                    **values, cancel=cancel.is_set, progress=self._output().observer(request)
                )
            elif args.command == "execute_history":
                result = self.context.execute_history(
                    **values,
                    cancel=cancel.is_set,
                    progress=self._output().observer(request),
                )
            elif args.command == "history_choices":
                result = self.context.history_choices(**values)
            elif args.command == "choose_history":
                result = self.context.choose_history(**values)
            elif args.command == "page":
                result = self.context.page(**values)
            elif args.command == "references":
                result = self.context.reference_page(**values)
            elif args.command == "choices":
                result = self.context.choice_page(**values)
            elif args.command == "choice_details":
                result = self.context.choice_details(**values)
            elif args.command == "choose":
                result = self.context.choose(**values)
            elif args.command == "choose_configuration":
                result = self.context.choose_configuration(**values)
            elif args.command == "stage_references":
                result = self.context.stage_references(**values)
            elif args.command == "begin_edit":
                result = self.context.begin_edit(**values)
            elif args.command == "write_edit":
                result = self.context.write_edit(**values)
            elif args.command == "seal_edit":
                result = self.context.seal_edit(**values)
            elif args.command == "apply":
                result = self.context.apply(
                    **values,
                    cancel=cancel.is_set,
                    progress=self._output().observer(request),
                )
            elif args.command == "refresh":
                result = self.context.refresh(**values, cancel=cancel.is_set, progress=self._output().observer(request))
            elif args.command == "save":
                result = self.context.save(
                    **values,
                    cancel=cancel.is_set,
                    progress=self._output().observer(request),
                )
            elif args.command == "load":
                result = self.context.load(**values, cancel=cancel.is_set)
            elif args.command == "resume":
                result = self.context.resume(**values, cancel=cancel.is_set)
            elif args.command == "close":
                result = self.context.close(**values)
                self.closed = result.code == "context_closed"
            elif args.command == "discard_draft":
                result = self.context.discard_draft(**values)
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
            with self._activity:
                if (
                    self._active is not None
                    and self._active.request_id == request.request_id
                    and self._active.sequence == request.sequence
                ):
                    self._active = None

    def serve(self, incoming, *, first=None):
        self._output()
        pending = Queue(maxsize=1)
        bad_input = Event()

        def read():
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

        reader = Thread(target=read, daemon=True, name="update-worker-control")
        reader.start()
        while (request := pending.get()) is not None:
            if not bad_input.is_set():
                self._perform(request)
            if self.closed:
                break
        # The sealed close reply lets the parent release stdin. Join before
        # interpreter shutdown so no thread still owns buffered standard I/O.
        reader.join()
        self._delivery.close()
        return 1 if bad_input.is_set() or self._output_lost or not self.closed else 0


def serve_updates(first, incoming, outgoing):
    return UpdateWorker(output=outgoing).serve(incoming, first=first)
