"""One physical writer with finite observation and terminal retention."""

from threading import Condition, Event, Thread
from time import monotonic

from .update_stream import WorkerProgress, encode_progress


class UpdateOutput:
    def __init__(self, output, *, failed, retired):
        self._output, self._failed, self._retired = output, failed, retired
        self._condition = Condition()
        self._latest = self._work = self._control = None
        self._stopping = self._broken = False
        self._ordinal = 0
        self._scope = None
        self._next_progress_at = 0.0
        self._thread = Thread(
            target=self._write, daemon=True, name="update-worker-output"
        )
        self._thread.start()

    def observer(self, request):
        started = monotonic()

        def observe(value):
            # Never perform physical I/O or wait for output from native work.
            with self._condition:
                if self._broken or self._stopping:
                    return
                wake = self._latest is None
                self._latest = (request, value, started)
                if wake:
                    self._condition.notify()

        return observe

    def reply(self, request, terminal, end):
        done = Event()
        control = request.arguments.command == "cancel"
        with self._condition:
            if self._broken or self._stopping:
                raise OSError("Worker output is unavailable")
            slot = "_control" if control else "_work"
            if getattr(self, slot) is not None:
                raise OSError("Worker output admission is full")
            setattr(self, slot, (request, terminal, end, done))
            if not control:
                self._latest = None
            self._condition.notify()
        # The independent control reader must remain available while stdout
        # is blocked. The serialized producer waits for its own sealed reply.
        if not control:
            done.wait()
            if self._broken:
                raise OSError("Worker output is unavailable")

    def close(self):
        with self._condition:
            self._stopping = True
            self._latest = None
            self._condition.notify()
        self._thread.join()

    def _write(self):
        current = None
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(
                        lambda: (
                            self._stopping
                            or self._control is not None
                            or self._work is not None
                            or self._latest is not None
                        )
                    )
                    current = self._control or self._work
                    if current is not None:
                        if self._control is current:
                            self._control = None
                        else:
                            self._work = None
                        observation = None
                    elif self._latest is not None:
                        delay = self._next_progress_at - monotonic()
                        if delay > 0:
                            # Only observations wait. A terminal/control wakes
                            # this wait and is always selected first.
                            self._condition.wait(timeout=delay)
                            continue
                        observation, self._latest = self._latest, None
                    elif self._stopping:
                        return
                if current is not None:
                    request, terminal, end, done = current
                    self._output.write(terminal)
                    self._retired(request)
                    self._output.write(end)
                    self._output.flush()
                    done.set()
                    current = None
                else:
                    request, value, started = observation
                    elapsed = int((monotonic() - started) * 1000)
                    scope = (request.request_id, request.sequence)
                    if scope != self._scope:
                        self._scope, self._ordinal = scope, 0
                    self._ordinal += 1
                    self._output.write(
                        encode_progress(
                            WorkerProgress(
                                request_id=request.request_id,
                                sequence=request.sequence,
                                ordinal=self._ordinal,
                                elapsed_ms=elapsed,
                                value=value,
                            )
                        )
                    )
                    self._output.flush()
                    self._next_progress_at = monotonic() + 0.1
        except Exception:  # noqa: BLE001 -- I/O observation cannot grant publication authority.
            with self._condition:
                self._broken = True
                self._latest = None
                for job in (current, self._control, self._work):
                    if job is not None:
                        job[3].set()
                self._control = self._work = None
            self._failed()
