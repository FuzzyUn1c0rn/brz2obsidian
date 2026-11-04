"""Persistent hidden child with bounded work/control slots and output drainage."""

import json
import os
import subprocess
from dataclasses import dataclass, replace
from queue import Queue
from threading import Lock, Thread
from typing import Literal
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


@dataclass(frozen=True, slots=True)
class UpdateDiagnostics:
    """Bounded observations, without worker content or causal conclusions.

    Byte counts include drainage after poisoning. Frame counts and largest size
    describe bounded stdout readline observations; subsequent bulk drainage
    contributes only bytes. Counts saturate at 2**63 - 1. First failure records
    observed ordering without a causal diagnosis. Stderr completion includes
    error completion, distinguished by stderr_drain_error.
    """

    first_failure: (
        Literal[
            "oversized_frame",
            "invalid_outer_frame",
            "unexpected_request",
            "decoder_rejected",
            "unexpected_eof",
            "stdout_io",
            "stderr_io",
            "dispatch_failure",
            "observer_failure",
            "worker_protocol_error",
            "caller_close",
        ]
        | None
    ) = None
    stdout_bytes: int = 0
    stdout_frames: int = 0
    largest_frame_bytes: int = 0
    stderr_bytes: int = 0
    stderr_drain_finished: bool = False
    stderr_drain_error: bool = False
    worker_protocol_error: (
        Literal["invalid_request", "operation_unavailable", "internal_error"] | None
    ) = None


class UpdateChannel:
    def __init__(self, interpreter, source_root, *, on_uncertain=None):
        self._on_uncertain = on_uncertain or (lambda: None)
        self._serial, self._controls = Lock(), Lock()
        self._state, self._writer = Lock(), Lock()
        self._diagnostics = UpdateDiagnostics()
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

    @property
    def diagnostics(self):
        """Return an immutable observation without changing channel authority."""
        with self._state:
            return self._diagnostics

    def _observe_stdout(self, data, *, frame=False):
        with self._state:
            prior = self._diagnostics
            self._diagnostics = replace(
                prior,
                stdout_bytes=min(2**63 - 1, prior.stdout_bytes + len(data)),
                stdout_frames=min(2**63 - 1, prior.stdout_frames + int(frame)),
                largest_frame_bytes=max(
                    prior.largest_frame_bytes, len(data) if frame else 0
                ),
            )

    def _poison(self, category, *, stderr_error=False):
        with self._state:
            prior = self._diagnostics
            if prior.first_failure is None or stderr_error:
                self._diagnostics = replace(
                    prior,
                    first_failure=prior.first_failure or category,
                    stderr_drain_error=prior.stderr_drain_error or stderr_error,
                )
            if self.poisoned:
                return
            self.poisoned = True
            for _, answers, _ in self._pending.values():
                if answers.empty():
                    answers.put_nowait(None)
        self._on_uncertain()

    def _read(self):
        try:
            while True:
                if self.poisoned:
                    # Unknown authority is permanent, but every remaining byte
                    # must still be drained so a writing child can terminate.
                    remaining = self._process.stdout.read(65536)
                    self._observe_stdout(remaining)
                    if not remaining:
                        break
                    continue
                frame = self._process.stdout.readline(RESPONSE_LIMIT + 1)
                if not frame:
                    break
                self._observe_stdout(frame, frame=True)
                category = "oversized_frame"
                try:
                    if len(frame) > RESPONSE_LIMIT:
                        raise ProtocolFailure("Oversized worker frame")
                    category = "invalid_outer_frame"
                    value = json.loads(frame.decode("utf-8"), object_pairs_hook=_pairs)
                    category = "unexpected_request"
                    identity = (
                        value.get("request_id") if isinstance(value, dict) else None
                    )
                    observation = None
                    with self._state:
                        pending = self._pending.get(identity)
                        if pending is None:
                            raise ProtocolFailure("Unexpected worker frame")
                        category = "decoder_rejected"
                        decoder, answers, observer = pending
                        response = decoder.feed(frame)
                        if decoder.progress is not None and observer is not None:
                            observation = (observer, decoder.request, decoder.progress)
                        if response is not None:
                            del self._pending[identity]
                            if response.protocol_error is not None:
                                self._diagnostics = replace(
                                    self._diagnostics,
                                    first_failure=(
                                        self._diagnostics.first_failure
                                        or "worker_protocol_error"
                                    ),
                                    worker_protocol_error=(
                                        self._diagnostics.worker_protocol_error
                                        or response.protocol_error.code
                                    ),
                                )
                            if (
                                response.result is not None
                                and response.result.code == "context_closed"
                            ):
                                self._expected_eof = True
                            answers.put_nowait(response)
                    if observation is not None:
                        callback, actual, progress = observation
                        category = "observer_failure"
                        # User presentation must never run under transport locks.
                        try:
                            callback(actual, progress)
                        except Exception:  # noqa: BLE001 -- loss of observation delivery cannot confer authority.
                            raise ProtocolFailure("Progress delivery failed") from None
                except ValueError, TypeError, KeyError, RecursionError:
                    self._poison(category)
            if not self._expected_eof:
                self._poison("unexpected_eof")
        except OSError:
            self._poison("stdout_io")

    def _drain_stderr(self):
        retained = bytearray()
        finished = False
        try:
            while chunk := self._process.stderr.read(65536):
                with self._state:
                    self._diagnostics = replace(
                        self._diagnostics,
                        stderr_bytes=min(
                            2**63 - 1, self._diagnostics.stderr_bytes + len(chunk)
                        ),
                    )
                retained.extend(chunk[: max(0, STDERR_LIMIT - len(retained))])
            finished = True
        except OSError:
            finished = True
            self._poison("stderr_io", stderr_error=True)
        finally:
            retained.clear()
            if finished:
                with self._state:
                    self._diagnostics = replace(
                        self._diagnostics, stderr_drain_finished=True
                    )

    def _exchange(self, request, *, on_dispatched=None, on_progress=None):
        category = "dispatch_failure"
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
                        on_progress,
                    )
                self._process.stdin.write(wire)
                self._process.stdin.flush()
            if on_dispatched is not None:
                category = "observer_failure"
                on_dispatched(request)
            response = answers.get()
            if response is None or self.poisoned:
                return Terminal(phase="may_have_executed", code="protocol_failure")
            if response.protocol_error is not None:
                self._poison("worker_protocol_error")
                return Terminal(phase="may_have_executed", code="worker_failure")
            return Terminal(phase="completed", response=response)
        except OSError, ValueError:
            self._poison(category)
            return Terminal(phase="may_have_executed", code="protocol_failure")

    def run(self, request, *, on_dispatched=None, on_progress=None):
        with self._serial:
            return self._exchange(
                request, on_dispatched=on_dispatched, on_progress=on_progress
            )

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
            self._poison("caller_close")
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
