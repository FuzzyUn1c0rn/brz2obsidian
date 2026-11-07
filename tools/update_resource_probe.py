"""Observe an explicitly owned, trusted, stdio-only Windows calibration family.

This proof tool does not admit product work or qualify Git attribution. Commands
must implement the finite calibration barrier protocol and check allocation
failures. It bounds its own artifacts, not arbitrary filesystem writes by a
hostile executable. All memory counters are bytes unless named *_pages.
"""

import ctypes
import json
import os
import subprocess
import time
from ctypes import wintypes as w
from itertools import pairwise
from pathlib import Path

from brz2obsidian.publication.git_read import _SuspendedPopen

MIB = 1024 * 1024


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("ProcessTime", ctypes.c_int64),
        ("JobTime", ctypes.c_int64),
        ("LimitFlags", w.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", w.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", w.DWORD),
        ("SchedulingClass", w.DWORD),
    ]


class _Limits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", ctypes.c_uint64 * 6),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _Accounting(ctypes.Structure):
    _fields_ = [
        ("UserTime", ctypes.c_int64),
        ("KernelTime", ctypes.c_int64),
        ("PeriodUserTime", ctypes.c_int64),
        ("PeriodKernelTime", ctypes.c_int64),
        ("PageFaults", w.DWORD),
        ("TotalProcesses", w.DWORD),
        ("ActiveProcesses", w.DWORD),
        ("TotalTerminatedProcesses", w.DWORD),
    ]


class _Pids(ctypes.Structure):
    _fields_ = [
        ("assigned", w.DWORD),
        ("count", w.DWORD),
        ("pids", ctypes.c_size_t * 16),
    ]


class _Memory(ctypes.Structure):
    _fields_ = [("cb", w.DWORD), ("PageFaultCount", w.DWORD)] + [
        (name, ctypes.c_size_t)
        for name in (
            "PeakWorkingSetSize",
            "WorkingSetSize",
            "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage",
            "PagefileUsage",
            "PeakPagefileUsage",
            "PrivateUsage",
        )
    ]


class _Performance(ctypes.Structure):
    _fields_ = (
        [("cb", w.DWORD)]
        + [
            (name, ctypes.c_size_t)
            for name in (
                "CommitTotal",
                "CommitLimit",
                "CommitPeak",
                "PhysicalTotal",
                "PhysicalAvailable",
                "SystemCache",
                "KernelTotal",
                "KernelPaged",
                "KernelNonpaged",
                "PageSize",
            )
        ]
        + [(name, w.DWORD) for name in ("HandleCount", "ProcessCount", "ThreadCount")]
    )


class _Status(ctypes.Structure):
    _fields_ = [("dwLength", w.DWORD), ("dwMemoryLoad", w.DWORD)] + [
        (name, ctypes.c_uint64)
        for name in (
            "ullTotalPhys",
            "ullAvailPhys",
            "ullTotalPageFile",
            "ullAvailPageFile",
            "ullTotalVirtual",
            "ullAvailVirtual",
            "ullAvailExtendedVirtual",
        )
    ]


class _Windows:
    def __init__(self):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.psapi = ctypes.WinDLL("psapi", use_last_error=True)
        for name, args, result in (
            ("CreateJobObjectW", [ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
            (
                "SetInformationJobObject",
                [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD],
                w.BOOL,
            ),
            (
                "QueryInformationJobObject",
                [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p],
                w.BOOL,
            ),
            ("AssignProcessToJobObject", [w.HANDLE, w.HANDLE], w.BOOL),
            ("IsProcessInJob", [w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)], w.BOOL),
            ("TerminateJobObject", [w.HANDLE, w.UINT], w.BOOL),
            ("CloseHandle", [w.HANDLE], w.BOOL),
            ("OpenProcess", [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            ("GetProcessId", [w.HANDLE], w.DWORD),
            ("GetProcessTimes", [w.HANDLE] + [ctypes.c_void_p] * 4, w.BOOL),
            (
                "QueryFullProcessImageNameW",
                [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)],
                w.BOOL,
            ),
            ("GetExitCodeProcess", [w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
            ("GlobalMemoryStatusEx", [ctypes.POINTER(_Status)], w.BOOL),
            (
                "PeekNamedPipe",
                [
                    w.HANDLE,
                    ctypes.c_void_p,
                    w.DWORD,
                    ctypes.c_void_p,
                    ctypes.POINTER(w.DWORD),
                    ctypes.c_void_p,
                ],
                w.BOOL,
            ),
        ):
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = args, result
        self.psapi.GetProcessMemoryInfo.argtypes = [
            w.HANDLE,
            ctypes.POINTER(_Memory),
            w.DWORD,
        ]
        self.psapi.GetPerformanceInfo.argtypes = [ctypes.POINTER(_Performance), w.DWORD]

    def require(self, result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())

    def query(self, job, kind, value):
        self.require(
            self.kernel.QueryInformationJobObject(
                job, kind, ctypes.byref(value), ctypes.sizeof(value), None
            )
        )
        return value

    def memory(self, handle):
        value = _Memory()
        value.cb = ctypes.sizeof(value)
        self.require(
            self.psapi.GetProcessMemoryInfo(handle, ctypes.byref(value), value.cb)
        )
        return {
            name: getattr(value, name)
            for name in (
                "PrivateUsage",
                "PeakPagefileUsage",
                "WorkingSetSize",
                "PeakWorkingSetSize",
            )
        }

    def system(self):
        value, status = _Performance(), _Status()
        value.cb, status.dwLength = ctypes.sizeof(value), ctypes.sizeof(status)
        self.require(self.psapi.GetPerformanceInfo(ctypes.byref(value), value.cb))
        self.require(self.kernel.GlobalMemoryStatusEx(ctypes.byref(status)))
        return {
            "CommitTotal_pages": value.CommitTotal,
            "CommitLimit_pages": value.CommitLimit,
            "CommitPeak_since_boot_pages": value.CommitPeak,
            "PageSize_bytes": value.PageSize,
            "CommitTotal_bytes": value.CommitTotal * value.PageSize,
            "CommitLimit_bytes": value.CommitLimit * value.PageSize,
            "system_available_commit_bytes": (value.CommitLimit - value.CommitTotal)
            * value.PageSize,
            "process_available_commit_bytes": status.ullAvailPageFile,
        }


class _Job:
    def __init__(self, api, ceiling, *, lifetime_limit=16):
        self.api, self.handles, self.attribution = api, {}, []
        self.lifetime_limit = lifetime_limit
        self.handle = api.kernel.CreateJobObjectW(None, None)
        api.require(self.handle)
        try:
            value = _Limits()
            # KILL_ON_JOB_CLOSE | JOB_MEMORY | ACTIVE_PROCESS; no breakaway flags.
            value.BasicLimitInformation.LimitFlags = 0x2000 | 0x200 | 0x8
            value.BasicLimitInformation.ActiveProcessLimit = 16
            value.JobMemoryLimit = ceiling
            api.require(
                api.kernel.SetInformationJobObject(
                    self.handle, 9, ctypes.byref(value), ctypes.sizeof(value)
                )
            )
        except BaseException:
            self.close()
            raise

    def attach_handle(self, handle):
        self.api.require(self.api.kernel.AssignProcessToJobObject(self.handle, handle))
        self.track(self.api.kernel.GetProcessId(handle), "direct-before-resume")

    def track(self, pid, origin):
        if pid in self.handles:
            return
        if len(self.handles) >= self.lifetime_limit:
            raise OSError("Lifetime process attribution budget exhausted")
        api = self.api
        handle = api.kernel.OpenProcess(0x0410, False, pid)
        api.require(handle)
        try:
            member = w.BOOL()
            api.require(
                api.kernel.IsProcessInJob(handle, self.handle, ctypes.byref(member))
            )
            if not member.value:
                raise OSError("Process is not in the owned job")
            times = [ctypes.c_uint64() for _ in range(4)]
            api.require(
                api.kernel.GetProcessTimes(
                    handle, *(ctypes.byref(item) for item in times)
                )
            )
            length = w.DWORD(32768)
            image = ctypes.create_unicode_buffer(length.value)
            api.require(
                api.kernel.QueryFullProcessImageNameW(
                    handle, 0, image, ctypes.byref(length)
                )
            )
            if len(image.value.encode("utf-8")) > 2048:
                raise OSError("Process image attribution exceeds its finite budget")
            self.attribution.append(
                {
                    "pid": pid,
                    "origin": origin,
                    "creation_filetime_100ns": times[0].value,
                    "image": image.value,
                    "handle_retained": True,
                    "observed_at": time.monotonic(),
                }
            )
            self.handles[pid] = handle
        except BaseException:
            api.kernel.CloseHandle(handle)
            raise

    def census(self):
        value = self.api.query(self.handle, 1, _Accounting())
        limits = self.api.query(self.handle, 9, _Limits())
        return {
            **{
                name: getattr(value, name)
                for name in (
                    "TotalProcesses",
                    "ActiveProcesses",
                    "TotalTerminatedProcesses",
                )
            },
            **{
                name: getattr(limits, name)
                for name in ("PeakJobMemoryUsed", "PeakProcessMemoryUsed")
            },
            "LimitFlags": limits.BasicLimitInformation.LimitFlags,
            "JobMemoryLimit": limits.JobMemoryLimit,
            "ActiveProcessLimit": limits.BasicLimitInformation.ActiveProcessLimit,
        }

    def sample(self, phase, observer, *, allow_exited_gaps=False):
        started = time.monotonic()
        pids = self.api.query(self.handle, 3, _Pids())
        if pids.assigned > 16 or pids.count > 16:
            raise OSError("Process census exceeded its finite capacity")
        rows, missing = [], []
        for pid in pids.pids[: pids.count]:
            try:
                self.track(pid, "job-census")
                rows.append(
                    {
                        "pid": pid,
                        **self.api.memory(self.handles[pid]),
                        "sampled_at": time.monotonic(),
                    }
                )
            except OSError as error:
                exited = False
                if allow_exited_gaps:
                    if pid in self.handles:
                        code = w.DWORD()
                        self.api.require(
                            self.api.kernel.GetExitCodeProcess(
                                self.handles[pid], ctypes.byref(code)
                            )
                        )
                        exited = code.value != 259
                    elif getattr(error, "winerror", None) == 87:
                        current = self.api.query(self.handle, 3, _Pids())
                        exited = pid not in current.pids[: current.count]
                missing.append({"pid": pid, "error": str(error), "exited": exited})
        frame = {
            "sample_started": started,
            "phase": phase,
            "job": self.census(),
            "processes": rows,
            "missing_processes": missing,
            "sampled_family_private_bytes": sum(row["PrivateUsage"] for row in rows),
            "sampled_family_working_set_bytes": sum(
                row["WorkingSetSize"] for row in rows
            ),
            "system": self.api.system(),
            "observer": self.api.memory(observer),
        }
        frame["sample_finished"] = time.monotonic()
        return frame

    def close(self):
        errors = []
        if self.handle:
            if not self.api.kernel.CloseHandle(self.handle):
                errors.append("Owned job handle closure failed")
            self.handle = None
        for handle in self.handles.values():
            if not self.api.kernel.CloseHandle(handle):
                errors.append("Owned process handle closure failed")
        self.handles.clear()
        return errors


def observe(
    command, output, *, timeout=15, memory_limit=512 * MIB, artifact_limit=64 * MIB
):
    """Return and persist raw evidence, including failures; never relax admission.

    The fixed protocol is baseline -> held -> done, with a small
    newline JSON event at each barrier. This observer releases each barrier only
    after recording a frame. Work is at most 26s, reserving two finite 2s cleanup
    waits within the 30s family bound. Synchronous OS-call latency is observed,
    not guaranteed by the proposed 10ms sampling interval.
    Polling cannot establish every descendant lifetime peak. Sampled sums cover
    a frame interval rather than an atomic instant; raw OS job peaks supplement
    them. A report status of completed means protocol completion only.
    Events have fixed shallow fields; unsupported metadata fails qualification.
    The aggregate artifact budget includes the terminal report serialization.
    """
    return _observe(
        command,
        output,
        timeout=timeout,
        memory_limit=memory_limit,
        artifact_limit=artifact_limit,
    )


def observe_phases(command, output, *, phases, work_timeout=116):
    """Record declared phase barriers under the fixed one-point pilot limits.

    Names are unique ordered ASCII strings, at most sixteen of length 1..32.
    This records whole-job peaks and sampled intervals; it supplies no allocation
    oracle, isolated phase OS peaks, scaling or per-Git lifetime qualification.
    Observer artifacts are capped at 60 MiB, leaving 4 MiB for the pilot driver's
    separately charged control evidence within the 64 MiB attempt ceiling.
    """
    if (
        type(phases) is not tuple
        or not 1 <= len(phases) <= 16
        or not all(
            type(name) is str and 1 <= len(name) <= 32 and name.isascii()
            for name in phases
        )
        or len(set(phases)) != len(phases)
    ):
        raise ValueError("Invalid bounded phase declaration")
    return _observe(
        command,
        output,
        timeout=work_timeout,
        memory_limit=2048 * MIB,
        artifact_limit=60 * MIB,
        phase_names=phases,
    )


def _observe(
    command, output, *, timeout, memory_limit, artifact_limit, phase_names=None
):
    phase_mode = phase_names is not None
    work_limit = 116 if phase_mode else 26
    commit_limit = 2048 * MIB if phase_mode else 512 * MIB
    lifetime_limit = 512 if phase_mode else 16
    terminal_reserve = 4 * MIB if phase_mode else 128 * 1024
    if os.name != "nt":
        raise OSError("Windows resource observation is unavailable")
    if (
        type(timeout) not in (int, float)
        or type(memory_limit) is not int
        or type(artifact_limit) is not int
        or not 0 < timeout <= work_limit
        or not 0 < memory_limit <= commit_limit
        or not 256 * 1024 <= artifact_limit <= 64 * MIB
    ):
        raise ValueError("Calibration limits exceed the approved finite bounds")
    if (
        not isinstance(command, list)
        or not command
        or not all(
            isinstance(value, str) and value and "\0" not in value for value in command
        )
    ):
        raise ValueError("An explicit command argument list is required")
    if len(json.dumps(command).encode()) > 8192:
        raise ValueError("Command attribution exceeds its finite budget")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {
        "status": "incomplete",
        "observer_pid": os.getpid(),
        "command": command,
        "started": started,
        "requested_interval_seconds": 0.01,
        "per_git_lifetime_attribution": "unqualified",
        "limitations": [
            "Polling may miss short-lived descendants and their individual peaks",
            "Sampled current sums span a non-atomic frame interval",
            "No Git or payload-scaling qualification",
        ],
        "calibration": {},
        "job_peak_scope": "whole owned job since launch; not phase-local",
        "final_job": None,
        "limits": {
            "family_commit_bytes": memory_limit,
            "artifact_bytes": artifact_limit,
            "work_seconds": timeout,
            "family_seconds": timeout + 4,
            "cleanup_seconds": 4,
            "lifetime_processes": lifetime_limit,
            "terminal_reserve_bytes": terminal_reserve,
        },
    }
    api = job = process = observer = None
    frames, phases, used = [], [], 0
    baseline = held_frame = None
    driver_pid = None
    terminal_received = False
    exited_counter_gaps = 0

    def write(name, value, *, terminal=False):
        nonlocal used
        data = (
            value
            if isinstance(value, bytes)
            else (
                json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
            ).encode()
        )
        limit = artifact_limit if terminal else artifact_limit - terminal_reserve
        if used + len(data) > limit:
            raise OSError("Calibration artifact budget exhausted")
        # Charge before I/O, including any partial write followed by failure.
        used += len(data)
        with (output / name).open("xb" if terminal else "ab") as stream:
            stream.write(data)

    def sample(phase):
        nonlocal exited_counter_gaps
        frame = job.sample(phase, observer, allow_exited_gaps=phase_mode)
        write("frames.jsonl", frame)
        frames.append(frame["sample_started"])
        exited_counter_gaps += sum(row["exited"] for row in frame["missing_processes"])
        if any(not row["exited"] for row in frame["missing_processes"]):
            raise OSError("Owned process counters unavailable; frame is incomplete")
        if frame["job"]["TotalProcesses"] > lifetime_limit:
            raise OSError("Lifetime process census budget exhausted")
        return frame

    try:
        api = _Windows()
        observer = api.kernel.OpenProcess(0x0410, False, os.getpid())
        api.require(observer)
        job = _Job(api, memory_limit, lifetime_limit=lifetime_limit)
        member = w.BOOL()
        api.require(
            api.kernel.IsProcessInJob(observer, job.handle, ctypes.byref(member))
        )
        report["observer_in_measured_job"] = bool(member.value)
        if member.value:
            raise OSError("Observer is unexpectedly in the measured family")
        process = _SuspendedPopen(
            command,
            job=job,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        import msvcrt

        pipe = msvcrt.get_osfhandle(process.stdout.fileno())
        pending, received = b"", 0
        while True:
            if time.monotonic() - started >= timeout:
                raise TimeoutError("Calibration family deadline exhausted")
            available = w.DWORD()
            ready = api.kernel.PeekNamedPipe(
                pipe, None, 0, None, ctypes.byref(available), None
            )
            if not ready and ctypes.get_last_error() != 109:
                api.require(ready)
            if available.value:
                block = os.read(process.stdout.fileno(), min(available.value, 4096))
                write("protocol.bin", block)
                received += len(block)
                pending += block
                if received > 65536 or len(pending) > 16384:
                    raise OSError("Calibration protocol output budget exhausted")
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                event = json.loads(line)
                if phase_mode:
                    if not isinstance(event, dict) or terminal_received:
                        raise ValueError("Malformed phase event")
                    terminal = event.get("event") == "done"
                    fields = {"event", "pid", "ok" if terminal else "name"}
                    if set(event) != fields or type(event["pid"]) is not int:
                        raise ValueError("Unsupported phase event fields or identity")
                    if terminal:
                        if len(phases) != len(phase_names) or event["ok"] is not True:
                            raise ValueError("Incomplete phase terminal outcome")
                        phase = "terminal"
                    else:
                        if (
                            event["event"] != "phase"
                            or len(phases) >= len(phase_names)
                            or event["name"] != phase_names[len(phases)]
                        ):
                            raise ValueError("Unexpected phase sequence")
                        phase = event["name"]
                    frame = sample(phase)
                    if (
                        event["pid"] not in {row["pid"] for row in frame["processes"]}
                        or driver_pid is not None
                        and driver_pid != event["pid"]
                    ):
                        raise ValueError("Phase driver is not the same owned process")
                    driver_pid = event["pid"]
                    write("events.jsonl", {"observed_at": time.monotonic(), **event})
                    if terminal:
                        terminal_received = True
                    else:
                        phases.append(phase)
                    process.stdin.write(b"continue\n")
                    process.stdin.flush()
                    continue
                expected = ("baseline", "held", "done")
                if (
                    not isinstance(event, dict)
                    or len(phases) >= 3
                    or event.get("phase") != expected[len(phases)]
                ):
                    raise ValueError("Malformed calibration phase sequence")
                phase = event["phase"]
                fields = {"phase", "pid"} | {
                    "baseline": {"descendant_pid"},
                    "held": {"descendant_pid", "requested_bytes"},
                    "done": {"requested_bytes", "short_allocation_released"},
                }[phase]
                if set(event) != fields:
                    raise ValueError("Unsupported calibration event fields")
                for field in fields & {"pid", "descendant_pid"}:
                    if (
                        type(event[field]) is not int
                        or not 0 < event[field] <= 0xFFFFFFFF
                    ):
                        raise ValueError("Invalid calibration process identity")
                if phase != "baseline" and (
                    type(event.get("requested_bytes")) is not int
                    or event["requested_bytes"]
                    != {"held": 24 * MIB, "done": 56 * MIB}[phase]
                    or (
                        phase == "done"
                        and event.get("short_allocation_released") is not True
                    )
                ):
                    raise ValueError("Invalid calibration allocation evidence")
                phases.append(phase)
                write("events.jsonl", {"observed_at": time.monotonic(), **event})
                frame = sample(phase)
                if phase == "baseline":
                    if event.get("pid") == event.get("descendant_pid"):
                        raise ValueError("Allocating process attribution is incomplete")
                    baseline = (event, frame)
                elif phase == "held":
                    original, initial = baseline
                    before = {
                        row["pid"]: row["PrivateUsage"] for row in initial["processes"]
                    }
                    after = {
                        row["pid"]: row["PrivateUsage"] for row in frame["processes"]
                    }
                    if (
                        before.keys() != after.keys()
                        or initial["missing_processes"]
                        or frame["missing_processes"]
                        or initial["job"]["TotalProcesses"]
                        != frame["job"]["TotalProcesses"]
                    ):
                        raise ValueError("Allocation baseline process census changed")
                    deltas = {}
                    for field, minimum in (
                        ("pid", 8 * MIB),
                        ("descendant_pid", 16 * MIB),
                    ):
                        pid = event.get(field)
                        if (
                            type(pid) is not int
                            or pid != original.get(field)
                            or pid not in before
                        ):
                            raise ValueError(
                                "Allocating process attribution is incomplete"
                            )
                        deltas[str(pid)] = after[pid] - before[pid]
                        if deltas[str(pid)] < minimum:
                            raise ValueError(
                                "OS private-commit delta does not establish allocation"
                            )
                    report["allocation_private_deltas"] = deltas
                    held_frame = frame
                if phase == "done":
                    if (
                        frame["job"]["PeakJobMemoryUsed"]
                        < held_frame["job"]["PeakJobMemoryUsed"] + 8 * MIB
                    ):
                        raise ValueError(
                            "OS job peak does not establish short allocation"
                        )
                    report["calibration"] = event
                process.stdin.write(b"continue\n")
                process.stdin.flush()
            frame = sample(phases[-1] if phase_mode and phases else "sampling")
            if frame["job"]["PeakJobMemoryUsed"] >= memory_limit:
                raise OSError("Calibration reached the family commit ceiling")
            if process.poll() is not None and frame["job"]["ActiveProcesses"] == 0:
                if (
                    process.returncode != 0
                    or pending
                    or (
                        not terminal_received
                        if phase_mode
                        else phases != ["baseline", "held", "done"]
                    )
                ):
                    raise ValueError(
                        "Calibration output or terminal outcome is incomplete"
                    )
                report["status"] = "completed"
                break
            time.sleep(0.01)
    except (
        OSError,
        ValueError,
        RecursionError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ) as error:
        report["error"] = str(error)
        report["status"] = "timeout" if isinstance(error, TimeoutError) else "failed"
    finally:
        cleanup_errors = []
        if job is not None:
            try:
                if job.census()["ActiveProcesses"]:
                    api.require(api.kernel.TerminateJobObject(job.handle, 1))
                deadline = time.monotonic() + 2
                while job.census()["ActiveProcesses"] and time.monotonic() < deadline:
                    time.sleep(0.01)
                report["final_job"] = job.census()
                if report["final_job"]["ActiveProcesses"]:
                    cleanup_errors.append("Owned descendants remain active")
            except OSError as error:
                cleanup_errors.append(str(error))
            finally:
                report["attribution"] = job.attribution
                report["observed_pids"] = sorted(job.handles)
                if report["final_job"] is not None:
                    report["unattributed_process_count"] = max(
                        0, report["final_job"]["TotalProcesses"] - len(job.handles)
                    )
                cleanup_errors.extend(job.close())
        if process is not None:
            try:
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired) as error:
                cleanup_errors.append(str(error))
            finally:
                for stream in (process.stdin, process.stdout):
                    try:
                        stream.close()
                    except OSError as error:
                        cleanup_errors.append(str(error))
                try:
                    process._handle.Close()
                except OSError as error:
                    cleanup_errors.append(str(error))
        if observer and not api.kernel.CloseHandle(observer):
            cleanup_errors.append("Observer process handle closure failed")
        report["cleanup_errors"] = cleanup_errors
        if cleanup_errors:
            report["status"] = "failed"
    report.update(
        elapsed_seconds=time.monotonic() - started,
        max_sample_gap_seconds=max(
            (later - earlier for earlier, later in pairwise(frames)), default=0
        ),
        phases=phases,
        exited_counter_gap_observations=exited_counter_gaps,
    )
    try:
        write("report.json", report, terminal=True)
    except OSError:
        if (output / "report.json").exists():
            # A filesystem write failure cannot establish complete evidence.
            raise
        report = {
            "status": "failed",
            "error": "Terminal report could not fit or be written; details omitted",
            "final_job": report["final_job"],
            "cleanup_errors": report["cleanup_errors"],
            "per_git_lifetime_attribution": "unqualified",
            "elapsed_seconds": report["elapsed_seconds"],
            "artifact_limit": artifact_limit,
        }
        # Observations reserve 128 KiB, but both full and fallback reports still
        # pass the same aggregate byte check. No overwrite or clipped PASS.
        write("report.json", report, terminal=True)
    return report
