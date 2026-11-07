"""Observe trusted Windows calibration and registered command families.

Drivers implement finite stdio protocols and check their allocation failures.
The command policy retains OS family peaks; individually missed helper identities
and peaks remain explicit gaps. This tool does not change product admission.
It bounds its own artifacts, not arbitrary writes by a hostile executable.
All memory counters are bytes unless named *_pages.
"""

import ctypes
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
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
            ("GetCurrentProcess", [], w.HANDLE),
            (
                "DuplicateHandle",
                [
                    w.HANDLE,
                    w.HANDLE,
                    w.HANDLE,
                    ctypes.POINTER(w.HANDLE),
                    w.DWORD,
                    w.BOOL,
                    w.DWORD,
                ],
                w.BOOL,
            ),
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

    def identity(self, handle):
        pid = self.kernel.GetProcessId(handle)
        self.require(pid)
        times = [ctypes.c_uint64() for _ in range(4)]
        self.require(
            self.kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in times))
        )
        length = w.DWORD(1024)
        image = ctypes.create_unicode_buffer(length.value)
        self.require(
            self.kernel.QueryFullProcessImageNameW(
                handle, 0, image, ctypes.byref(length)
            )
        )
        if len(image.value.encode("utf-8")) > 2048:
            raise OSError("Process image attribution exceeds its finite budget")
        return {
            "pid": pid,
            "creation_filetime_100ns": times[0].value,
            "image": image.value,
        }

    def duplicate(self, source, handle, *, access=None):
        duplicate = w.HANDLE()
        self.require(
            self.kernel.DuplicateHandle(
                source,
                handle,
                self.kernel.GetCurrentProcess(),
                ctypes.byref(duplicate),
                0 if access is None else access,
                False,
                2 if access is None else 0,
            )
        )
        return duplicate.value

    def member(self, process, job):
        member = w.BOOL()
        self.require(self.kernel.IsProcessInJob(process, job, ctypes.byref(member)))
        if not member.value:
            raise OSError("Creation process is outside a required owned job")

    def accounting(self, handle):
        value = self.query(handle, 1, _Accounting())
        limits = self.query(handle, 9, _Limits())
        return {
            name: getattr(value, name)
            for name in (
                "TotalProcesses",
                "ActiveProcesses",
                "TotalTerminatedProcesses",
            )
        } | {
            name: getattr(limits, name)
            for name in ("PeakJobMemoryUsed", "PeakProcessMemoryUsed")
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


def _runtime_binding():
    return {
        "executable": sys.executable,
        "base_executable": sys._base_executable,
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "version": sys.version,
        "origins": [
            importlib.util.find_spec(name).origin
            for name in (
                "brz2obsidian",
                "tests.support.resource_pilot",
                "pydantic",
            )
        ],
    }


def _command_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate command protocol field")
        result[name] = value
    return result


class _CommandJob(_Job):
    """Outer census shares canonical handles and normalized rows with commands."""

    def __init__(self, api, ceiling, policy):
        self.policy = policy
        self.borrowed = set()
        self.initializing = True
        super().__init__(api, ceiling, lifetime_limit=512)
        self.policy.retain(self.handle)
        self.initializing = False

    def attach_handle(self, handle):
        self.api.require(self.api.kernel.AssignProcessToJobObject(self.handle, handle))
        identity = self.api.identity(handle)
        self.policy.reserve_row()
        row = {
            "kind": "process",
            "origin": "direct-before-resume",
            **identity,
            "handle_retained": True,
            "observed_at": time.monotonic(),
        }
        self.policy.check_row(row)
        self.policy.inventory.append(row)
        self.handles[identity["pid"]] = handle
        self.borrowed.add(handle)
        self.policy.retain(handle)

    def track(self, pid, origin):
        if pid in self.handles:
            return
        self.policy.reserve_row()
        super().track(pid, origin)
        self.policy.retain(self.handles[pid])
        row = self.attribution.pop()
        row["kind"] = "process"
        self.policy.check_row(row)
        self.policy.inventory.append(row)

    def close(self):
        errors = []
        handles = [
            handle for handle in self.handles.values() if handle not in self.borrowed
        ]
        if self.handle:
            if self.initializing and self.handle not in self.policy.owned:
                self.policy.retain(self.handle)
            handles.append(self.handle)
        for handle in handles:
            try:
                self.policy.close(self.api, handle)
            except OSError as error:
                errors.append(str(error))
        self.handle = None
        self.handles.clear()
        return errors


class _Commands:
    """Synchronous, fail-closed ownership state for one declared driver."""

    def __init__(self, phases, individual_samples, fault, bootstrap):
        self.phases = phases
        self.individual_samples = individual_samples
        self.inventory = []
        self.commands = {}
        self.measurements = {}
        self.events = 0
        self.acks = 0
        self.hello = False
        self.terminal = False
        self.bootstrap = None
        self.expected_runtime = _runtime_binding()
        self.active = None
        self.fault = fault
        self.bootstrap_expected = bootstrap
        self.fault_reached = False
        self.owned = set()
        self.close_duplicates = 0
        self.closed_count = 0
        self.terminal_credit = 4 * MIB

    def retain(self, handle):
        handle = int(handle)
        if handle in self.owned or len(self.owned) >= 1036:
            raise OSError("Proof handle ownership reservation exhausted or duplicate")
        self.owned.add(handle)

    def close(self, api, handle, closer=None):
        handle = int(handle)
        if handle not in self.owned:
            self.close_duplicates += 1
            raise OSError("Proof handle close requested more than once")
        if closer is None:
            api.require(api.kernel.CloseHandle(handle))
        else:
            closer()
        self.owned.remove(handle)
        self.closed_count += 1

    def reserve_row(self):
        if len(self.inventory) >= 512:
            raise OSError("Normalized inventory capacity exhausted before registration")

    def check_row(self, row):
        limit = 6 * 1024 if row["kind"] == "command" else 4 * 1024
        if (
            len(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode())
            > limit
        ):
            raise OSError("Normalized terminal row reservation exhausted")

    def check_terminal(self):
        # The 64 KiB summary reservation is separate from bounded row encodings.
        if (
            len(
                json.dumps(
                    self.inventory, ensure_ascii=False, separators=(",", ":")
                ).encode()
            )
            + 65536
            > self.terminal_credit
        ):
            raise OSError("Aggregate terminal inventory reservation exhausted")

    def ack(self, process, value, write):
        encoded = value.encode("ascii") + b"\n"
        if len(encoded) > 64 or self.acks >= 1553:
            raise OSError("Command ACK budget exhausted")
        self.check_terminal()
        write("acks.bin", encoded)
        self.acks += 1
        process.stdin.write(encoded)
        process.stdin.flush()

    def event(self, event, raw, job, process, write, phases):
        if (
            type(event) is not dict
            or self.terminal
            or self.events >= 1553
            or len(raw) > 12 * 1024
        ):
            raise ValueError("Malformed or excessive command protocol event")
        self.events += 1
        name = event.get("event")
        if not self.hello:
            expected = {
                "event": "hello",
                "pid": job.api.kernel.GetProcessId(process._handle),
                **self.expected_runtime,
            }
            if event != expected:
                raise ValueError("Driver runtime or actual creation identity mismatch")
            job.api.member(process._handle, job.handle)
            self.bootstrap = job.census()["TotalProcesses"]
            # Direct-native Python plus its console host is the only accepted
            # bootstrap shape; the exact observed count is retained per run.
            if self.bootstrap not in (1, 2):
                raise ValueError("Unexpected direct-driver bootstrap family")
            if self.bootstrap_expected is not None:
                members = job.api.query(job.handle, 3, _Pids())
                if members.assigned != 2 or members.count != 2:
                    raise ValueError("Frozen bootstrap processes are not both present")
                for pid in members.pids[: members.count]:
                    job.track(pid, "bootstrap-census")
                images = sorted(
                    os.path.normcase(os.path.normpath(row["image"]))
                    for row in self.inventory
                )
                wanted = sorted(
                    os.path.normcase(os.path.normpath(value))
                    for value in self.bootstrap_expected["images"]
                )
                if (
                    self.bootstrap != self.bootstrap_expected["lifetimes"]
                    or images != wanted
                ):
                    raise ValueError("Native bootstrap differs from the frozen control")
            self.hello = True
            write("events.jsonl", event)
            self.ack(process, "ready", write)
            return
        if name == "phase":
            if (
                set(event) != {"event", "pid", "name"}
                or event["pid"] != job.api.kernel.GetProcessId(process._handle)
                or len(phases) >= len(self.phases)
                or event["name"] != self.phases[len(phases)]
                or self.active is not None
            ):
                raise ValueError("Unexpected command-driver phase")
            phases.append(event["name"])
            write("events.jsonl", event)
            self.ack(process, "continue", write)
            return
        if name == "done":
            if (
                event
                != {
                    "event": "done",
                    "pid": job.api.kernel.GetProcessId(process._handle),
                    "ok": True,
                }
                or len(phases) != len(self.phases)
                or self.active is not None
                or any(row["state"] != "finalized" for row in self.commands.values())
            ):
                raise ValueError("Incomplete command-driver terminal outcome")
            self.reconcile(job)
            write("events.jsonl", event)
            self.terminal = True
            self.ack(process, "continue", write)
            return
        seq = event.get("seq")
        if type(seq) is not int or not 1 <= seq <= 512:
            raise ValueError("Invalid command sequence")
        if name == "command_begin":
            if self.events + 3 > 1553 or self.acks + 4 > 1553:
                raise OSError("Command lifecycle cannot fit remaining protocol credit")
            if (
                set(event) != {"event", "seq", "kind", "argv"}
                or seq != len(self.commands) + 1
                or self.active is not None
                or event["kind"] not in ("read", "payload", "fixture")
            ):
                raise ValueError("Unexpected command begin")
            argv = event["argv"]
            encoded = json.dumps(
                argv, ensure_ascii=False, separators=(",", ":")
            ).encode()
            if (
                type(argv) is not list
                or not 1 <= len(argv) <= 128
                or any(type(arg) is not str or "\0" in arg for arg in argv)
                or len(encoded) > 6144
            ):
                raise ValueError("Command argv exceeds its declaration")
            self.reserve_row()
            offset = write("events.jsonl", event)
            row = {
                "kind": "command",
                "seq": seq,
                "call_kind": event["kind"],
                "state": "begun",
                "begin_event": offset,
                "argv_sha256": hashlib.sha256(encoded).hexdigest(),
                "begun_at": time.monotonic(),
                "outer_lifetimes_at_begin": job.census()["TotalProcesses"],
            }
            self.check_row(row)
            self.inventory.append(row)
            self.commands[seq] = row
            self.active = seq
            self.ack(process, f"begin {seq}", write)
            return
        if seq != self.active or seq not in self.commands:
            if (
                self.fault == "duplicate_return"
                and name == "command_return"
                and seq in self.commands
                and self.commands[seq]["state"] == "finalized"
            ):
                self.fault_reached = True
            raise ValueError("Unknown or repeated command sequence")
        row = self.commands[seq]
        if name == "command_register":
            if (
                set(event)
                != {"event", "seq", "measurement_handle", "creation_process_handle"}
                or row["state"] != "begun"
                or any(
                    type(event[key]) is not int or not 0 < event[key] < 1 << 64
                    for key in ("measurement_handle", "creation_process_handle")
                )
            ):
                raise ValueError("Invalid command registration")
            measurement = creation = None
            try:
                measurement = job.api.duplicate(
                    process._handle,
                    0x7FFFFFFC
                    if self.fault == "duplicate_measurement"
                    else event["measurement_handle"],
                )
                self.retain(measurement)
                creation = job.api.duplicate(
                    process._handle,
                    0x7FFFFFFC
                    if self.fault == "duplicate_creation"
                    else event["creation_process_handle"],
                )
                self.retain(creation)
                identity = job.api.identity(creation)
                job.api.member(creation, job.handle)
                job.api.member(creation, measurement)
                initial = job.api.accounting(measurement)
                if initial["TotalProcesses"] != 1 or initial["ActiveProcesses"] != 1:
                    raise ValueError(
                        "Command registration is not a fresh suspended family"
                    )
                prior = next(
                    (
                        item
                        for item in self.inventory
                        if item.get("pid") == identity["pid"]
                    ),
                    None,
                )
                if prior is not None and (
                    prior["kind"] != "process"
                    or any(prior[key] != value for key, value in identity.items())
                ):
                    raise ValueError("Creation identity conflicts with prior census")
                updated = {
                    **row,
                    **identity,
                    "state": "registered",
                    "registered_at": time.monotonic(),
                    "origin": "creation-handle",
                    "handle_retained": True,
                    "initial_job": initial,
                    "initial_process": job.api.memory(creation),
                }
                if prior is not None:
                    updated["prior_discovery"] = {
                        key: prior[key] for key in ("origin", "observed_at")
                    }
                self.check_row(updated)
                if self.fault == "terminal_reserve_exhausted":
                    self.fault_reached = True
                    self.terminal_credit = 65536
                self.check_terminal()
                old = job.handles.get(identity["pid"])
                if old is not None:
                    self.close(job.api, old)
                job.handles[identity["pid"]] = creation
                creation = None
                if prior is not None:
                    self.inventory.remove(prior)
                row.clear()
                row.update(updated)
                self.measurements[seq] = measurement
                measurement = None
                write("events.jsonl", {**event, "accepted_identity": identity})
                if self.fault == "registration_ack_lost":
                    self.fault_reached = True
                    process.stdin.close()
                    raise OSError("Injected registration acknowledgment loss")
                if self.fault == "driver_killed_after_registration":
                    import _winapi

                    _winapi.TerminateProcess(process._handle, 1)
                    self.fault_reached = True
                    raise OSError("Actual registered driver was killed by control")
                if self.fault == "family_counter_unavailable":
                    # Retain a real duplicate of this same measurement job with
                    # terminate-only rights. Querying that owned handle must
                    # now fail natively; no fabricated counter is substituted.
                    limited = job.api.duplicate(
                        job.api.kernel.GetCurrentProcess(),
                        self.measurements[seq],
                        access=0x0008,
                    )
                    self.retain(limited)
                    try:
                        self.close(job.api, self.measurements[seq])
                    except OSError:
                        self.close(job.api, limited)
                        raise
                    self.measurements[seq] = limited
                    self.fault_reached = True
                    job.api.accounting(limited)
                self.ack(process, f"registered {seq}", write)
            except OSError:
                if self.fault in ("duplicate_measurement", "duplicate_creation"):
                    self.fault_reached = True
                raise
            finally:
                for handle in (measurement, creation):
                    if handle is not None:
                        self.close(job.api, handle)
            return
        if (
            name != "command_return"
            or set(event) != {"event", "seq", "status"}
            or event["status"] not in ("returned", "raised", "not_created")
        ):
            raise ValueError("Invalid command return")
        if row["state"] == "begun":
            if event["status"] != "not_created":
                raise ValueError("Created command lacks registered ownership")
            if job.census()["TotalProcesses"] != row["outer_lifetimes_at_begin"]:
                raise ValueError("Unregistered lifetime during failed constructor")
            row.update(
                kind="failed_intent",
                state="finalized",
                return_status="not_created",
                normal_cleanup_complete=True,
            )
        else:
            self.finalize(seq, job, aborted=False, status=event["status"])
            if row["final_job"]["ActiveProcesses"]:
                raise OSError("Returned product call left an active command family")
        self.check_row(row)
        write("events.jsonl", event)
        self.active = None
        self.ack(process, f"finalized {seq}", write)
        if event["status"] != "returned":
            raise OSError("Actual command call failed")

    def finalize(self, seq, job, *, aborted, status):
        row = self.commands[seq]
        handle = self.measurements.get(seq)
        if handle is None:
            return
        # An unfinished family remains observer-owned through the single
        # outer abort, allowing its final zero-active counters to survive.
        if not aborted and job.api.accounting(handle)["ActiveProcesses"]:
            raise OSError("Returned product call left an active command family")
        try:
            final = job.api.accounting(handle)
            row.update(
                final_job=final,
                outer_at_return=job.census(),
                state="aborted" if aborted else "finalized",
                return_status=status,
                normal_cleanup_complete=not aborted,
                individual_sampling={
                    "mode": self.individual_samples,
                    "omitted_interval_seconds": time.monotonic() - row["registered_at"]
                    if self.individual_samples == "command-boundaries"
                    else 0,
                },
            )
            try:
                row["final_process"] = job.api.memory(job.handles[row["pid"]])
            except OSError as error:
                row["final_process_unavailable"] = str(error)
        except OSError as error:
            row.update(
                state="incomplete",
                counter_error=str(error),
                normal_cleanup_complete=False,
            )
            raise
        finally:
            del self.measurements[seq]
            self.close(job.api, handle)
            row["measurement_handle_closed"] = True

    def reconcile(self, job):
        total = job.census()["TotalProcesses"]
        commands = sum(
            row.get("final_job", {}).get("TotalProcesses", 0)
            for row in self.commands.values()
        )
        value = {
            "bootstrap_lifetimes": self.bootstrap,
            "command_lifetimes": commands,
            "outer_lifetimes": total,
            "unaccounted_lifetimes": total - self.bootstrap - commands,
        }
        if value["unaccounted_lifetimes"] != 0:
            self.census_failure = value
            if self.fault == "command_census_bypass":
                self.fault_reached = True
            raise OSError("Unregistered command-family lifetime in final census")
        return value


def observe_commands(
    command,
    output,
    *,
    artifact_limit,
    bootstrap,
    phases=(),
    work_timeout=116,
    individual_samples="regular",
    fault=None,
):
    """Observe actual command creation handles and disjoint nested job peaks."""
    if (
        type(phases) is not tuple
        or len(phases) > 16
        or len(set(phases)) != len(phases)
        or any(
            type(name) is not str or not 1 <= len(name) <= 32 or not name.isascii()
            for name in phases
        )
    ):
        raise ValueError("Invalid bounded command phase declaration")
    if individual_samples not in ("regular", "command-boundaries"):
        raise ValueError("Unknown individual sampling policy")
    if type(artifact_limit) is not int or not 4 * MIB < artifact_limit <= 60 * MIB:
        raise ValueError("Command artifact credit lacks its complete terminal reserve")
    if individual_samples == "command-boundaries" and (
        len(command) < 5
        or command[1:4] != ["-m", "tests.support.git_resource_pilot", "peaks"]
    ):
        raise ValueError("Sampling omission is restricted to the fixed peak control")
    if not command or os.path.normcase(command[0]) != os.path.normcase(sys.executable):
        raise ValueError("Command driver must use the qualified current interpreter")
    if fault is not None and (
        fault
        not in (
            "constructor_partial",
            "measurement_assign",
            "product_assign",
            "duplicate_measurement",
            "duplicate_creation",
            "registration_ack_lost",
            "family_counter_unavailable",
            "driver_killed_after_registration",
            "outer_deadline",
            "duplicate_return",
            "command_census_bypass",
            "terminal_reserve_exhausted",
        )
        or command[1:5] != ["-m", "tests.support.git_resource_pilot", "refusal", fault]
    ):
        raise ValueError("Fault injection is restricted to declared refusal controls")
    if (
        type(bootstrap) is not dict
        or set(bootstrap) != {"lifetimes", "images"}
        or bootstrap["lifetimes"] != 2
        or type(bootstrap["images"]) is not list
        or len(bootstrap["images"]) != 2
        or any(type(value) is not str for value in bootstrap["images"])
    ):
        raise ValueError("Invalid frozen native bootstrap declaration")
    policy = _Commands(phases, individual_samples, fault, bootstrap)
    return _observe(
        command,
        output,
        timeout=work_timeout,
        memory_limit=2048 * MIB,
        artifact_limit=artifact_limit,
        phase_names=phases,
        command_policy=policy,
    )


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
    command,
    output,
    *,
    timeout,
    memory_limit,
    artifact_limit,
    phase_names=None,
    command_policy=None,
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
    if command_policy:
        report["limitations"] = [
            "Polling may miss individual descendant identities and peaks",
            "Sampled current sums span a non-atomic frame interval",
            "Command-family accounting does not establish payload scaling",
        ]
        report["command_family_coverage"] = "incomplete"
        report["individual_sampling_policy"] = command_policy.individual_samples
        report["limits"].update(
            command_sequences=512,
            normalized_rows=512,
            protocol_events=1553,
            protocol_acks=1553,
            observer_proof_handles=1036,
        )
    api = job = process = observer = None
    frames, phases, used = [], [], 0
    baseline = held_frame = None
    driver_pid = None
    terminal_received = False
    exited_counter_gaps = 0

    offsets = {}

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
        if command_policy and (
            terminal
            and len(data) > terminal_reserve
            or name == "frames.jsonl"
            and len(data) > 12 * 1024
        ):
            raise OSError("Encoded command evidence exceeds its reserved record")
        if used + len(data) > limit:
            raise OSError("Calibration artifact budget exhausted")
        # Charge before I/O, including any partial write followed by failure.
        used += len(data)
        offset = offsets.get(name, 0)
        with (output / name).open("xb" if terminal else "ab") as stream:
            if stream.write(data) != len(data):
                raise OSError("Observer evidence write was incomplete")
        offsets[name] = offset + len(data)
        return {"offset": offset, "length": len(data)}

    def sample(phase):
        nonlocal exited_counter_gaps
        omitted = (
            command_policy is not None
            and command_policy.individual_samples == "command-boundaries"
            and command_policy.active is not None
        )
        if omitted:
            now = time.monotonic()
            frame = {
                "sample_started": now,
                "sample_finished": now,
                "phase": phase,
                "job": job.census(),
                "processes": [],
                "missing_processes": [],
                "individual_samples_omitted": True,
                "system": api.system(),
                "observer": api.memory(observer),
            }
        else:
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
        if command_policy:
            command_policy.retain(observer)
        job = (
            _CommandJob(api, memory_limit, command_policy)
            if command_policy
            else _Job(api, memory_limit, lifetime_limit=lifetime_limit)
        )
        member = w.BOOL()
        api.require(
            api.kernel.IsProcessInJob(observer, job.handle, ctypes.byref(member))
        )
        report["observer_in_measured_job"] = bool(member.value)
        if member.value:
            raise OSError("Observer is unexpectedly in the measured family")
        launch = command
        environment = None
        if command_policy:
            launch = [sys._base_executable, *command[1:]]
            environment = {
                **os.environ,
                "__PYVENV_LAUNCHER__": sys.executable,
                "BRZ_COMMAND_DEADLINE": str(started + timeout),
            }
            report["native_driver_command"] = launch
        process = _SuspendedPopen(
            launch,
            job=job,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
            env=environment,
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
                if not command_policy:
                    write("protocol.bin", block)
                elif len(pending) + len(block) > 12 * 1024:
                    write("protocol-refusal.bin", pending)
                    raise OSError("Command protocol line exceeds its finite bound")
                received += len(block)
                pending += block
                if (
                    received > (1553 * 12 * 1024 if command_policy else 65536)
                    or len(pending) > 16384
                ):
                    raise OSError("Calibration protocol output budget exhausted")
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if command_policy:
                    before = offsets.get("events.jsonl", 0)
                    try:
                        event = json.loads(line, object_pairs_hook=_command_object)
                        command_policy.event(event, line, job, process, write, phases)
                    except (OSError, ValueError, RecursionError) as error:
                        if offsets.get("events.jsonl", 0) == before:
                            write("protocol-refusal.bin", line + b"\n")
                        write("protocol-error.jsonl", {"error": str(error)})
                        raise
                    terminal_received = command_policy.terminal
                    continue
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
                if command_policy:
                    report["census"] = command_policy.reconcile(job)
                    report["command_family_coverage"] = "complete"
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
        if (
            command_policy
            and command_policy.fault == "outer_deadline"
            and isinstance(error, TimeoutError)
            and command_policy.measurements
        ):
            command_policy.fault_reached = True
    finally:
        cleanup_errors = []
        termination_calls = 0
        cleanup_deadline = (
            min(time.monotonic() + 4, started + timeout + 4)
            if command_policy
            else time.monotonic() + 4
        )
        if job is not None:
            try:
                if job.census()["ActiveProcesses"]:
                    termination_calls += 1
                    api.require(api.kernel.TerminateJobObject(job.handle, 1))
                deadline = cleanup_deadline if command_policy else time.monotonic() + 2
                while job.census()["ActiveProcesses"] and time.monotonic() < deadline:
                    time.sleep(0.01)
                report["final_job"] = job.census()
                if report["final_job"]["ActiveProcesses"]:
                    cleanup_errors.append("Owned descendants remain active")
            except OSError as error:
                cleanup_errors.append(str(error))
            finally:
                if command_policy:
                    for seq in tuple(command_policy.measurements):
                        try:
                            command_policy.finalize(
                                seq, job, aborted=True, status="observer_abort"
                            )
                        except OSError as error:
                            cleanup_errors.append(str(error))
                    for row in command_policy.commands.values():
                        if row["state"] == "begun":
                            row.update(
                                state="incomplete", normal_cleanup_complete=False
                            )
                    report["inventory"] = command_policy.inventory
                    report["protocol_events"] = command_policy.events
                    report["protocol_acks"] = command_policy.acks
                    report["runtime_binding"] = command_policy.expected_runtime
                    report.setdefault("command_family_coverage", "incomplete")
                else:
                    report["attribution"] = job.attribution
                    report["observed_pids"] = sorted(job.handles)
                if report["final_job"] is not None:
                    report["unattributed_process_count"] = max(
                        0, report["final_job"]["TotalProcesses"] - len(job.handles)
                    )
                cleanup_errors.extend(job.close())
        if process is not None:
            try:
                process.wait(
                    timeout=max(0, cleanup_deadline - time.monotonic())
                    if command_policy
                    else 2
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                cleanup_errors.append(str(error))
            finally:
                for stream in (process.stdin, process.stdout):
                    try:
                        stream.close()
                    except OSError as error:
                        cleanup_errors.append(str(error))
                try:
                    if command_policy:
                        command_policy.close(
                            api, process._handle, process._handle.Close
                        )
                    else:
                        process._handle.Close()
                except OSError as error:
                    cleanup_errors.append(str(error))
        if observer:
            try:
                if command_policy:
                    command_policy.close(api, observer)
                elif not api.kernel.CloseHandle(observer):
                    cleanup_errors.append("Observer process handle closure failed")
            except OSError as error:
                cleanup_errors.append(str(error))
        if command_policy:
            report.update(
                fault=command_policy.fault,
                fault_reached=command_policy.fault_reached,
                outer_termination_calls=termination_calls,
                handle_close_duplicates=command_policy.close_duplicates,
                proof_handles_closed=command_policy.closed_count,
                proof_handles_remaining=len(command_policy.owned),
                measurement_handles_remaining=len(command_policy.measurements),
            )
            if hasattr(command_policy, "census_failure"):
                report["census"] = command_policy.census_failure
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
