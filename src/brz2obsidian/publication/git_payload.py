"""Verify raw Git blob streams without buffering complete payloads."""

import hashlib
import math
import os
import signal
import subprocess
import time
from threading import Event, Lock, Thread

from brz2obsidian.publication.git_read import (
    OUTPUT_BUDGET,
    _cancel,
    _GitTimeout,
    _SuspendedPopen,
    _WindowsJob,
)

_CHUNK_SIZE = 1024 * 1024
_HEX = frozenset("0123456789abcdefABCDEF")
_TIMEOUT = "Git payload exceeded its time budget"


def _batch_requests(objects, timeout):
    try:
        valid_timeout = (
            type(timeout) in (int, float) and math.isfinite(timeout) and timeout > 0
        )
    except OverflowError:
        valid_timeout = False
    if not valid_timeout:
        raise OSError("Invalid Git payload time budget")
    if not isinstance(objects, tuple) or len(objects) > OUTPUT_BUDGET // 41:
        raise OSError("Git payload requests exceed their control budget")
    for record in objects:
        if not isinstance(record, tuple) or len(record) != 4:
            raise OSError("Invalid Git payload declaration")
        oid, size, digest, sink = record
        if (
            not isinstance(oid, str)
            or len(oid) != 40
            or not all(character in _HEX for character in oid)
            or type(size) is not int
            or not 0 <= size <= (1 << 63) - 1
            or not isinstance(digest, str)
            or len(digest) != 64
            or not all(character in _HEX for character in digest)
            or (sink is not None and not callable(getattr(sink, "write", None)))
        ):
            raise OSError("Invalid Git payload declaration")
    requests = b"".join(record[0].lower().encode("ascii") + b"\n" for record in objects)
    return requests


class _PayloadBatch:
    def __init__(self, requests, objects, timeout):
        self.requests = requests
        self.objects = objects
        self.used = len(requests)
        self.lock = Lock()
        self.failed = Event()
        self.payload_complete = Event()
        self.accounted_objects = 0
        self.failure_reason = None
        self.process = None
        self.process_reaped = False
        self.control_overflow = False
        self.diagnostic_output = False
        self.observed_integrity_failure = False
        self.job = None
        self.threads = []
        self.deadline = time.monotonic() + timeout

    def fail(self, reason):
        with self.lock:
            if self.failure_reason is None:
                self.failure_reason = reason
            self.failed.set()
        if self.process is not None:
            try:
                self.process.kill()
            except OSError:
                pass

    def control(self, count):
        with self.lock:
            self.used += count
            self.control_overflow = self.used > OUTPUT_BUDGET
        if self.control_overflow:
            raise OSError("Git payload exceeds its control budget")

    def close_worker_stream(self, stream):
        try:
            stream.close()
        except OSError, ValueError:
            self.fail("Git payload pipe cleanup failed")

    def payload_reader(self):
        stream = self.process.stdout
        try:
            for oid, size, digest, sink in self.objects:
                if self.failed.is_set():
                    return
                self._read_header(stream, oid, size)
                if not self._read_blob(stream, oid, size, digest, sink):
                    return
                self.accounted_objects += 1
            extra = stream.read(1)
            self.control(len(extra))
            if extra:
                self.observed_integrity_failure = True
                raise OSError("Git payload contains unexpected extra output")
            self.payload_complete.set()
        except OSError as error:
            self.fail(str(error))
        finally:
            self.close_worker_stream(stream)

    def stderr_reader(self):
        stream = self.process.stderr
        try:
            while block := stream.read(65536):
                self.diagnostic_output = True
                self.control(len(block))
                self.fail("Git payload command reported an error")
        except OSError as error:
            self.fail(str(error))
        finally:
            self.close_worker_stream(stream)

    def writer(self):
        stream = self.process.stdin
        try:
            for offset in range(0, len(self.requests), _CHUNK_SIZE):
                if self.failed.is_set():
                    return
                block = self.requests[offset : offset + _CHUNK_SIZE]
                if stream.write(block) != len(block):
                    raise OSError("Incomplete Git payload request")
            stream.flush()
        except OSError, ValueError:
            self.fail("Git payload request stream failed")
        finally:
            self.close_worker_stream(stream)

    def run_worker(self, target):
        try:
            target()
        except Exception:  # noqa: BLE001 - daemon errors must fail the calling operation
            self.fail("Git payload worker failed")

    def _read_header(self, stream, oid, size):
        expected = f"{oid.lower()} blob {size}\n".encode("ascii")
        offset = 0
        while offset < len(expected):
            # A buffered readline can lose a partial line when a
            # deadline cancels the pipe read. Check each prefix first.
            block = stream.read1(len(expected) - offset)
            self.control(len(block))
            if not block:
                raise OSError("Git payload has a truncated batch header")
            if not expected.startswith(block, offset):
                self.observed_integrity_failure = True
                raise OSError("Git payload has an invalid batch header")
            offset += len(block)

    def _read_blob(self, stream, oid, size, digest, sink):
        sha1 = hashlib.sha1(usedforsecurity=False)
        sha1.update(f"blob {size}\0".encode("ascii"))
        sha256 = hashlib.sha256()
        remaining = size
        read_block = stream.read if sink is None else stream.read1
        while remaining:
            if self.failed.is_set():
                return False
            block = read_block(min(remaining, _CHUNK_SIZE))
            if not block:
                raise OSError("Git payload is truncated")
            remaining -= len(block)
            sha1.update(block)
            sha256.update(block)
            if sink is not None and not self._write_sink(sink, block):
                return False
        if sha1.hexdigest() != oid.lower() or sha256.hexdigest() != digest.lower():
            self.observed_integrity_failure = True
            raise OSError("Git payload digest does not match its declaration")
        terminator = stream.read(1)
        self.control(len(terminator))
        if terminator != b"\n":
            self.observed_integrity_failure = bool(terminator)
            raise OSError("Git payload has an invalid batch terminator")
        return True

    def _write_sink(self, sink, block):
        try:
            written = sink.write(block)
        except Exception:  # noqa: BLE001 - caller callback failure boundary
            self.observed_integrity_failure = True
            self.fail("Git payload sink failed")
            return False
        if type(written) is not int or written != len(block):
            self.observed_integrity_failure = True
            self.fail("Git payload sink made an incomplete write")
            return False
        return True

    def run(self, argv, env):
        try:
            self.job = _WindowsJob() if os.name == "nt" else None
            factory = _SuspendedPopen if self.job else subprocess.Popen
            self.process = factory(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                start_new_session=os.name != "nt",
                **({"job": self.job} if self.job else {}),
            )
            for target in (self.payload_reader, self.stderr_reader, self.writer):
                thread = Thread(target=self.run_worker, args=(target,), daemon=True)
                thread.start()
                self.threads.append(thread)
            try:
                self.process.wait(timeout=max(0, self.deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                self.fail(_TIMEOUT)
            if self.process.returncode:
                self.fail("Git payload command failed")
        except OSError, RuntimeError, ValueError, TypeError, OverflowError, MemoryError:
            self.fail("Git payload process execution failed")
        finally:
            self._cleanup()

    def _cleanup(self):
        # End the owned tree before waiting for pipe EOF or cancelling I/O.
        if self.job:
            self.job.close()
        elif self.process is not None:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if self.process is not None:
            try:
                self.process.wait(timeout=5)
                self.process_reaped = True
            except subprocess.TimeoutExpired:
                self.fail("Git payload process cleanup failed")
        self._finish_pipes()

    def _finish_pipes(self):
        for thread in self.threads:
            thread.join(timeout=max(0, self.deadline - time.monotonic()))
        survivors = [thread for thread in self.threads if thread.is_alive()]
        if survivors:
            self.fail(_TIMEOUT)
            for thread in survivors:
                _cancel(thread)
            cleanup_deadline = time.monotonic() + 2
            for thread in survivors:
                thread.join(timeout=max(0, cleanup_deadline - time.monotonic()))
        # A live callback can own a buffered pipe lock. Its daemon worker owns
        # closing that pipe; closing it here could make timeout handling block.
        if self.process is not None and not any(
            thread.is_alive() for thread in self.threads
        ):
            for stream in (
                self.process.stdin,
                self.process.stdout,
                self.process.stderr,
            ):
                if stream is not None and not stream.closed:
                    stream.close()

    def require_verified(self):
        if any(thread.is_alive() for thread in self.threads):
            raise OSError("Git payload caller-owned sink did not finish")
        if self.failed.is_set():
            if (
                self.failure_reason == _TIMEOUT
                and self.process_reaped
                and not self.control_overflow
                and not self.diagnostic_output
                and not self.observed_integrity_failure
            ):
                raise _GitTimeout(self.failure_reason)
            raise OSError(self.failure_reason)
        if not self.payload_complete.is_set() or self.accounted_objects != len(
            self.objects
        ):
            raise OSError("Git payload verification did not complete")


def verify_blobs(argv, *, env, objects, timeout=30):
    """Verify ordered (SHA1, size, SHA256, sink-or-None) raw batch responses.

    The caller supplies an admitted, untransformed ``cat-file --batch`` command.
    Sinks must be app-owned finite/cancellable writers, never published vault
    files. They remain caller-owned: failure can leave unverified partial bytes
    which must be discarded. Callback termination and sink rollback are not
    promised. Digest-only verification needs no sink or temporary payload store.
    """
    requests = _batch_requests(objects, timeout)
    batch = _PayloadBatch(requests, objects, timeout)
    batch.run(argv, env)
    batch.require_verified()
