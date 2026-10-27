"""Controlled transport plumbing around a real persistent update producer."""

import io
from itertools import count
from threading import RLock
from uuid import uuid4

from brz2obsidian.application.contracts import WorkerRequest
from brz2obsidian.application.protocol import decode_request, encode_request
from brz2obsidian.application.transport import Terminal
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.update_stream import WorkerStreamDecoder
from brz2obsidian.application.update_worker import UpdateWorker


class ReviewWorkerTransport:
    def __init__(self, operations, *, before_request=None):
        self.closed = False
        self.poisoned = False
        self.commands = []
        self.replies = []
        self.binding = None
        self._output = io.BytesIO()
        self._worker = UpdateWorker(context=UpdateContext(operations=operations), output=self._output)
        self._sequence = count(1)
        self._lock = RLock()
        self._before_request = before_request

    def open_update(self, **kwargs):
        return self

    def run(self, request, **callbacks):
        with self._lock:
            actual = request.model_copy(update={"sequence": next(self._sequence)})
            if callbacks.get("on_dispatched") is not None:
                callbacks["on_dispatched"](actual)
            self.commands.append(actual.arguments)
            if self._before_request is not None:
                self._before_request(actual)
            self._worker.handle(decode_request(encode_request(actual)))
            decoder = WorkerStreamDecoder(actual)
            terminal = None
            for frame in self._output.getvalue().splitlines(keepends=True):
                received = decoder.feed(frame)
                if received is not None:
                    terminal = received
            decoder.eof()
            assert terminal is not None and decoder.sealed and not decoder.poisoned
            self._output.seek(0)
            self._output.truncate()
            if terminal.result is not None:
                self.binding = terminal.result.binding
                self.replies.append(terminal.result)
            return Terminal(phase="completed", response=terminal)

    def close(self):
        with self._lock:
            if not self._worker.closed:
                self.run(WorkerRequest(
                    operation="update", request_id=str(uuid4()), sequence=1,
                    arguments={"command": "close", "binding": self.binding, "choice": "discard"},
                ))
            self.closed = True
