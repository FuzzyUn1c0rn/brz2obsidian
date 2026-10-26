"""Serialized producer work with a separate live cooperative control reader."""

from queue import Full, Queue
from threading import Event, Lock, Thread

from .contracts import ProtocolError, WorkerResponse
from .protocol import REQUEST_LIMIT, ProtocolFailure, decode_request, encode_response
from .update_context import UpdateContext
from .update_context_contracts import UpdateContextResult
from .update_stream import encode_end


class UpdateWorker:
    def __init__(self, *, output, context=None):
        self.context = context if context is not None else UpdateContext()
        self.output = output
        self.closed = False
        self._next_sequence = 1
        self._sequence_lock, self._activity, self._writer = Lock(), Lock(), Lock()
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
        with self._writer:
            self.output.write(terminal)
            with self._activity:
                if (
                    self._active is not None
                    and self._active.request_id == request.request_id
                    and self._active.sequence == request.sequence
                ):
                    self._active = None
            self.output.write(end)
            self.output.flush()

    def _control(self, request):
        args = request.arguments
        with self._activity:
            current = self._active
            matched = (
                current is not None
                and current.request_id == args.target_request_id
                and current.sequence == args.target_sequence
                and (
                    (
                        args.binding is not None
                        and getattr(current.arguments, "binding", None) == args.binding
                    )
                    or (
                        args.binding is None
                        and current.arguments.command == "prepare"
                        and current.arguments.vault == args.vault
                        and current.arguments.selection_id == args.selection_id
                    )
                )
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
        self._accept(request)
        if request.arguments.command == "cancel":
            self._control(request)
        else:
            self._perform(request)

    def _perform(self, request):
        args = request.arguments
        with self._activity:
            cancel = self._cancel
        try:
            values = args.model_dump(exclude={"command"})
            if args.command == "prepare":
                result = self.context.prepare(**values, cancel=cancel.is_set)
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
                result = self.context.apply(**values, cancel=cancel.is_set)
            elif args.command == "save":
                result = self.context.save(**values)
            elif args.command == "load":
                result = self.context.load(**values)
            elif args.command == "resume":
                result = self.context.resume(**values)
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
        return 1 if bad_input.is_set() or not self.closed else 0


def serve_updates(first, incoming, outgoing):
    return UpdateWorker(output=outgoing).serve(incoming, first=first)
