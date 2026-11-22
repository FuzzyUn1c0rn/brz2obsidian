"""Bounded, noninteractive read-process execution for local Git observations."""

import ctypes
import errno
import os
import signal
import subprocess
from threading import Event, Lock, Thread

OUTPUT_BUDGET = 16 * 1024 * 1024
CREATE_SUSPENDED = 0x00000004
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
RESUME_THREAD_FAILED = 0xFFFFFFFF
THREAD_TERMINATE = 0x0001


class _WindowsJob:
    """Close the owned process tree, including descendants retaining pipes."""

    def __init__(self):
        from ctypes import wintypes as w

        class Limits(ctypes.Structure):
            _fields_ = [
                ("user", ctypes.c_int64),
                ("job", ctypes.c_int64),
                ("flags", w.DWORD),
                ("minimum", ctypes.c_size_t),
                ("maximum", ctypes.c_size_t),
                ("active", w.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", w.DWORD),
                ("scheduling", w.DWORD),
            ]

        class Information(ctypes.Structure):
            _fields_ = [
                ("basic", Limits),
                ("io", ctypes.c_uint64 * 6),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [
            w.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            w.DWORD,
        ]
        self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        information = Information()
        information.basic.flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(
            self.handle,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            self.close()
            raise OSError("Owned process cleanup capability unavailable")

    def attach_handle(self, handle):
        if not self.kernel.AssignProcessToJobObject(self.handle, handle):
            raise OSError("Owned process cleanup capability unavailable")

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class _SuspendedPopen(subprocess.Popen):
    """Python 3.14 Windows pipe setup with assign-before-resume job ownership."""

    def __init__(self, *args, job, **kwargs):
        self.owned_job = job
        super().__init__(*args, **kwargs)

    def _execute_child(
        self,
        args,
        executable,
        preexec_fn,
        close_fds,
        pass_fds,
        cwd,
        env,
        startupinfo,
        creationflags,
        shell,
        p2cread,
        p2cwrite,
        c2pread,
        c2pwrite,
        errread,
        errwrite,
        *unused,
    ):
        import _winapi
        from ctypes import wintypes as w

        # This narrow adapter never accepts a shell or unrelated inherited fds.
        if shell or pass_fds or startupinfo is not None or preexec_fn is not None:
            raise OSError("Unsupported read-process launch parameters")
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= _winapi.STARTF_USESTDHANDLES
        startup.hStdInput = p2cread
        startup.hStdOutput = c2pwrite
        startup.hStdError = errwrite
        startup.lpAttributeList = {
            "handle_list": self._filter_handle_list(
                [int(p2cread), int(c2pwrite), int(errwrite)]
            )
        }
        thread = None
        try:
            process, thread, pid, _ = _winapi.CreateProcess(
                executable,
                subprocess.list2cmdline(args),
                None,
                None,
                True,
                creationflags | CREATE_SUSPENDED,
                env,
                cwd,
                startup,
            )
            self._child_created = True
            self._handle = subprocess.Handle(process)
            self.pid = pid
            try:
                self.owned_job.attach_handle(process)
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.ResumeThread.argtypes = [w.HANDLE]
                kernel.ResumeThread.restype = w.DWORD
                if kernel.ResumeThread(thread) == RESUME_THREAD_FAILED:
                    raise OSError("Owned process could not be resumed")
            except BaseException:
                _winapi.TerminateProcess(process, 1)
                _winapi.WaitForSingleObject(process, 5000)
                self.returncode = 1
                raise
        finally:
            if thread is not None:
                _winapi.CloseHandle(thread)
            self._close_pipe_fds(
                p2cread, p2cwrite, c2pread, c2pwrite, errread, errwrite
            )


def _cancel(thread):
    if os.name == "nt" and thread.is_alive():
        from ctypes import wintypes as w

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenThread.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        kernel.OpenThread.restype = w.HANDLE
        kernel.CancelSynchronousIo.argtypes = [w.HANDLE]
        kernel.CloseHandle.argtypes = [w.HANDLE]
        handle = kernel.OpenThread(THREAD_TERMINATE, False, thread.native_id)
        if handle:
            try:
                kernel.CancelSynchronousIo(handle)
            finally:
                kernel.CloseHandle(handle)


class _GitTimeout(OSError):
    """The owned Git process reached its observation deadline."""

    def __init__(self, message, *, stdout=b""):
        super().__init__(message)
        self.stdout = stdout


class _ObservationPipes:
    def __init__(self, input):
        self.input = input
        self.process = None
        self.overflow = Event()
        self.timed_out = False
        self.lock = Lock()
        self.used = len(input) if input is not None else 0
        self.failures = []
        self.outputs = [bytearray(), bytearray()]

    def failure(self, error):
        with self.lock:
            self.failures.append(error)
        if self.process.poll() is None:
            self.process.kill()

    def reader(self, stream, output):
        try:
            while block := stream.read(65536):
                with self.lock:
                    remaining = OUTPUT_BUDGET - self.used
                    output.extend(block[:remaining])
                    self.used += min(remaining, len(block))
                    if len(block) > remaining:
                        self.overflow.set()
                        self.process.kill()
        except (OSError, ValueError) as error:
            self.failure(error)
        finally:
            stream.close()

    def input_failure(self, error):
        if (
            self.timed_out
            and isinstance(error, OSError)
            and (
                error.errno == errno.EPIPE
                or os.name == "nt"
                and error.errno == errno.EINVAL
            )
        ):
            return
        self.failure(error)

    def writer(self):
        try:
            if self.process.stdin.write(self.input) != len(self.input):
                raise OSError("Incomplete Git observation input")
            self.process.stdin.flush()
        except (OSError, ValueError) as error:
            self.input_failure(error)
        finally:
            try:
                self.process.stdin.close()
            except (OSError, ValueError) as error:
                self.input_failure(error)


def _stop_observation(job, process, threads):
    if job:
        job.close()
    elif process is not None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process is not None:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=2)
        _cancel(thread)
        thread.join(timeout=2)
    if process is not None:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


def read_git(argv, *, env, input=None, timeout=30):
    """Bound aggregate input/output and terminate owned work on every exit."""
    if input is not None and len(input) > OUTPUT_BUDGET:
        raise OSError("Git observation input exceeds its safe resource budget")
    job = _WindowsJob() if os.name == "nt" else None
    process = None
    threads = []
    pipes = _ObservationPipes(input)

    try:
        factory = _SuspendedPopen if job else subprocess.Popen
        process = factory(
            argv,
            stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
            **({"job": job} if job else {}),
        )
        pipes.process = process
        threads = [
            Thread(
                target=pipes.reader,
                args=(process.stdout, pipes.outputs[0]),
                daemon=True,
            ),
            Thread(
                target=pipes.reader,
                args=(process.stderr, pipes.outputs[1]),
                daemon=True,
            ),
        ]
        if input is not None:
            threads.append(Thread(target=pipes.writer, daemon=True))
        for thread in threads:
            thread.start()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pipes.timed_out = True
    finally:
        _stop_observation(job, process, threads)
    if (
        pipes.overflow.is_set()
        or pipes.failures
        or any(thread.is_alive() for thread in threads)
    ):
        raise OSError("Git observation exceeds its safe resource budget")
    if pipes.timed_out:
        if pipes.outputs[1]:
            raise OSError("Git reported an error before its observation timed out")
        raise _GitTimeout(
            "Git observation exceeded its safe time budget",
            stdout=bytes(pipes.outputs[0]),
        )
    return subprocess.CompletedProcess(
        argv, process.returncode, bytes(pipes.outputs[0]), bytes(pipes.outputs[1])
    )
