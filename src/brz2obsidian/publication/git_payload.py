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
    _SuspendedPopen,
    _WindowsJob,
)

_CHUNK_SIZE = 1024 * 1024
_HEADER_LIMIT = 128
_HEX = frozenset("0123456789abcdefABCDEF")


def verify_blobs(argv, *, env, objects, timeout=30):
    """Verify ordered (SHA1, size, SHA256, sink-or-None) raw batch responses.

    The caller supplies an admitted, untransformed ``cat-file --batch`` command.
    Sinks must be app-owned finite/cancellable writers, never published vault
    files. They remain caller-owned: failure can leave unverified partial bytes
    which must be discarded. Callback termination and sink rollback are not
    promised. Digest-only verification needs no sink or temporary payload store.
    """
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
    used = len(requests)
    lock = Lock()
    failed = Event()
    payload_complete = Event()
    accounted_objects = 0
    failure_reason = None
    process = None
    job = None
    threads = []
    deadline = time.monotonic() + timeout

    def fail(reason):
        nonlocal failure_reason
        with lock:
            if failure_reason is None:
                failure_reason = reason
            failed.set()
        if process is not None:
            try:
                process.kill()
            except OSError:
                pass

    def control(count):
        nonlocal used
        with lock:
            used += count
            overflow = used > OUTPUT_BUDGET
        if overflow:
            raise OSError("Git payload exceeds its control budget")

    def close_worker_stream(stream):
        try:
            stream.close()
        except OSError, ValueError:
            fail("Git payload pipe cleanup failed")

    def payload_reader():
        nonlocal accounted_objects
        stream = process.stdout
        try:
            for oid, size, digest, sink in objects:
                if failed.is_set():
                    return
                header = stream.readline(_HEADER_LIMIT + 1)
                control(len(header))
                expected = f"{oid.lower()} blob {size}\n".encode("ascii")
                if header != expected:
                    raise OSError("Git payload has an invalid batch header")
                sha1 = hashlib.sha1(usedforsecurity=False)
                sha1.update(f"blob {size}\0".encode("ascii"))
                sha256 = hashlib.sha256()
                remaining = size
                while remaining:
                    if failed.is_set():
                        return
                    block = stream.read(min(remaining, _CHUNK_SIZE))
                    if not block:
                        raise OSError("Git payload is truncated")
                    remaining -= len(block)
                    sha1.update(block)
                    sha256.update(block)
                    if sink is not None:
                        try:
                            written = sink.write(block)
                        except Exception:  # noqa: BLE001 - caller callback failure boundary
                            fail("Git payload sink failed")
                            return
                        if type(written) is not int or written != len(block):
                            fail("Git payload sink made an incomplete write")
                            return
                terminator = stream.read(1)
                control(len(terminator))
                if terminator != b"\n":
                    raise OSError("Git payload has an invalid batch terminator")
                if (
                    sha1.hexdigest() != oid.lower()
                    or sha256.hexdigest() != digest.lower()
                ):
                    raise OSError("Git payload digest does not match its declaration")
                accounted_objects += 1
            extra = stream.read(1)
            control(len(extra))
            if extra:
                raise OSError("Git payload contains unexpected extra output")
            payload_complete.set()
        except OSError as error:
            fail(str(error))
        finally:
            close_worker_stream(stream)

    def stderr_reader():
        stream = process.stderr
        try:
            while block := stream.read(65536):
                control(len(block))
                fail("Git payload command reported an error")
        except OSError as error:
            fail(str(error))
        finally:
            close_worker_stream(stream)

    def writer():
        stream = process.stdin
        try:
            for offset in range(0, len(requests), _CHUNK_SIZE):
                if failed.is_set():
                    return
                block = requests[offset : offset + _CHUNK_SIZE]
                if stream.write(block) != len(block):
                    raise OSError("Incomplete Git payload request")
            stream.flush()
        except OSError, ValueError:
            fail("Git payload request stream failed")
        finally:
            close_worker_stream(stream)

    def run_worker(target):
        try:
            target()
        except Exception:  # noqa: BLE001 - daemon errors must fail the calling operation
            fail("Git payload worker failed")

    try:
        job = _WindowsJob() if os.name == "nt" else None
        factory = _SuspendedPopen if job else subprocess.Popen
        process = factory(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
            **({"job": job} if job else {}),
        )
        for target in (payload_reader, stderr_reader, writer):
            thread = Thread(target=run_worker, args=(target,), daemon=True)
            thread.start()
            threads.append(thread)
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            fail("Git payload exceeded its time budget")
        if process.returncode:
            fail("Git payload command failed")
    except OSError, RuntimeError, ValueError, TypeError, OverflowError, MemoryError:
        fail("Git payload process execution failed")
    finally:
        # End the owned tree before waiting for pipe EOF or cancelling I/O.
        if job:
            job.close()
        elif process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process is not None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                fail("Git payload process cleanup failed")
        for thread in threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        survivors = [thread for thread in threads if thread.is_alive()]
        if survivors:
            fail("Git payload exceeded its time budget")
            for thread in survivors:
                _cancel(thread)
            cleanup_deadline = time.monotonic() + 2
            for thread in survivors:
                thread.join(timeout=max(0, cleanup_deadline - time.monotonic()))
        # A live callback can own a buffered pipe lock. Its daemon worker owns
        # closing that pipe; closing it here could make timeout handling block.
        if process is not None and not any(thread.is_alive() for thread in threads):
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
    if any(thread.is_alive() for thread in threads):
        raise OSError("Git payload caller-owned sink did not finish")
    if failed.is_set():
        raise OSError(failure_reason)
    if not payload_complete.is_set() or accounted_objects != len(objects):
        raise OSError("Git payload verification did not complete")
