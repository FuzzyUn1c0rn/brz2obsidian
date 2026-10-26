"""Persistent hidden child with bounded work/control slots and output drainage."""

import json
import os
import subprocess
from queue import Queue
from threading import Lock, Thread
from uuid import uuid4

from .contracts import WorkerRequest
from .protocol import (
    RESPONSE_LIMIT,
    STDERR_LIMIT,
    ProtocolFailure,
    _pairs,
    encode_request,
)
from .transport import Terminal
from .update_stream import WorkerStreamDecoder
from .update_worker_contracts import update_control_scope


class UpdateChannel:
    def __init__(self, interpreter, source_root, *, on_uncertain=None):
        self._on_uncertain = on_uncertain or (lambda: None)
        self._serial, self._controls = Lock(), Lock()
        self._state, self._writer = Lock(), Lock()
        self._pending = {}
        self._next_sequence = 1
        self._expected_eof = False
        self.poisoned = self.closed = False
        env = os.environ.copy()
        env.update(PYTHONPATH=str(source_root), PYTHONIOENCODING="utf-8")
        self._process = subprocess.Popen(
            [str(interpreter), "-m", "brz2obsidian.worker"],
            cwd=str(source_root.parent),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self._reader = Thread(
            target=self._read, daemon=True, name="update-worker-output"
        )
        self._stderr = Thread(
            target=self._drain_stderr, daemon=True, name="update-worker-stderr"
        )
        self._reader.start()
        self._stderr.start()

    @property
    def pid(self):
        return self._process.pid

    @property
    def process_status(self):
        return self._process.poll()

    def _poison(self):
        with self._state:
            if self.poisoned:
                return
            self.poisoned = True
            for _, answers in self._pending.values():
                if answers.empty():
                    answers.put_nowait(None)
        self._on_uncertain()

    def _read(self):
        try:
            while True:
                if self.poisoned:
                    # Unknown authority is permanent, but every remaining byte
                    # must still be drained so a writing child can terminate.
                    if not self._process.stdout.read(65536):
                        break
                    continue
                frame = self._process.stdout.readline(RESPONSE_LIMIT + 1)
                if not frame:
                    break
                try:
                    if len(frame) > RESPONSE_LIMIT:
                        raise ProtocolFailure("Oversized worker frame")
                    value = json.loads(frame.decode("utf-8"), object_pairs_hook=_pairs)
                    identity = (
                        value.get("request_id") if isinstance(value, dict) else None
                    )
                    with self._state:
                        pending = self._pending.get(identity)
                        if pending is None:
                            raise ProtocolFailure("Unexpected worker frame")
                        decoder, answers = pending
                        response = decoder.feed(frame)
                        if response is not None:
                            del self._pending[identity]
                            if (
                                response.result is not None
                                and response.result.code == "context_closed"
                            ):
                                self._expected_eof = True
                            answers.put_nowait(response)
                except ValueError, TypeError, KeyError, RecursionError:
                    self._poison()
            if not self._expected_eof:
                self._poison()
        except OSError:
            self._poison()

    def _drain_stderr(self):
        retained = bytearray()
        try:
            while chunk := self._process.stderr.read(65536):
                retained.extend(chunk[: max(0, STDERR_LIMIT - len(retained))])
        except OSError:
            self._poison()
        finally:
            retained.clear()

    def _exchange(self, request, *, on_dispatched=None):
        try:
            if request.operation != "update":
                raise ProtocolFailure("Wrong producer operation")
            answers = Queue(maxsize=1)
            with self._writer:
                with self._state:
                    if (
                        self.poisoned
                        or self.closed
                        or self._expected_eof
                        or len(self._pending) >= 2
                        or request.request_id in self._pending
                    ):
                        return Terminal(
                            phase="may_have_executed", code="protocol_failure"
                        )
                    # This stream owns sequence allocation. Caller values carry
                    # no sequencing authority into the persistent worker.
                    request = WorkerRequest.model_validate(
                        request.model_dump(by_alias=True)
                        | {"sequence": self._next_sequence}
                    )
                    wire = encode_request(request)
                    self._next_sequence += 1
                    self._pending[request.request_id] = (
                        WorkerStreamDecoder(request),
                        answers,
                    )
                self._process.stdin.write(wire)
                self._process.stdin.flush()
            if on_dispatched is not None:
                on_dispatched(request)
            response = answers.get()
            if response is None or self.poisoned:
                return Terminal(phase="may_have_executed", code="protocol_failure")
            if response.protocol_error is not None:
                self._poison()
                return Terminal(phase="may_have_executed", code="worker_failure")
            return Terminal(phase="completed", response=response)
        except OSError, ValueError:
            self._poison()
            return Terminal(phase="may_have_executed", code="protocol_failure")

    def run(self, request, *, on_dispatched=None):
        with self._serial:
            return self._exchange(request, on_dispatched=on_dispatched)

    def cancel(self, binding, *, target_request_id):
        with self._controls:
            with self._state:
                pending = self._pending.get(target_request_id)
                if pending is None:
                    return Terminal(phase="not_started", code="protocol_failure")
                active = pending[0].request
                scope = update_control_scope(active.arguments)
                if scope is None or binding is not None and binding != scope["binding"]:
                    return Terminal(phase="not_started", code="protocol_failure")
            request = WorkerRequest(
                request_id=str(uuid4()),
                sequence=1,
                operation="update",
                arguments={
                    "command": "cancel",
                    "target_request_id": target_request_id,
                    "target_sequence": active.sequence,
                    **scope,
                },
            )
            return self._exchange(request)

    def close(self):
        """Wait for actual exit; never kill a potentially active publisher."""
        if self.closed:
            return
        if not self._expected_eof:
            self._poison()
        try:
            self._process.stdin.close()
        except OSError:
            pass
        self._process.wait()
        self._reader.join()
        self._stderr.join()
        self._process.stdout.close()
        self._process.stderr.close()
        self.closed = True
