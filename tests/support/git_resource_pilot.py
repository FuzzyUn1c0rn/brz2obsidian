"""Strict command observation adapters and fixed synthetic mechanism controls."""

import ctypes
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from ctypes import wintypes as w
from pathlib import Path

MIB = 1024 * 1024
READ_CONSUMERS = ("vault_admission", "vault_attributes", "vault_history")
PAYLOAD_CONSUMERS = (
    "checkpoint_payload", "vault_history", "vault_repair",
    "attachment_ownership", "vault_recovery", "vault_apply",
)


def control_preflight(*, case=None, mode=None):
    """Bind one exclusive control attempt to Root's cumulative reservation."""
    from tests.support.resource_pilot import Evidence, inventory, native_identity, read_control

    manifest_path = Path(os.environ["BRZ_COMMAND_GIT_MANIFEST"])
    raw = read_control(manifest_path)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != os.environ["BRZ_COMMAND_GIT_MANIFEST_SHA256"]:
        raise OSError("Root command manifest differs from its pinned bytes")
    manifest = json.loads(raw)
    fields = {
        "schema_version", "issue", "feature_root", "base_commit", "oracle_commit",
        "role", "mode", "checkout", "attempt_parent", "attempt", "runner_parent",
        "runtime", "artifacts", "time", "charged_paths", "bootstrap",
    }
    if case is not None:
        fields |= {"cases"}
    if mode == "tiny":
        fields |= {"fixture"}
    if mode not in (None, "tiny") or mode is not None and case is not None:
        raise OSError("Unknown bounded control mode")
    if type(manifest) is not dict or set(manifest) != fields:
        raise OSError("Unknown Root command manifest fields")
    root = Path(__file__).resolve().parents[2]
    if (
        manifest["schema_version"] != 1
        or manifest["issue"] != "https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/358"
        or manifest["feature_root"] != "codex/r292-type-tag-support"
        or manifest["base_commit"] != "5378f0b1184bfe8825d6414475adaaa136203e1e"
        or manifest["oracle_commit"] != "94b4abdf536ce396a9f7b0a0591f7627d0b9079f"
        or manifest["role"] != "author"
        or manifest["mode"] != (mode or ("peaks" if case is None else "refusals"))
        or Path(manifest["checkout"]).resolve() != root
    ):
        raise OSError("Root command manifest context mismatch")
    for name in ("attempt_parent", "runner_parent"):
        declaration = manifest[name]
        if type(declaration) is not dict or set(declaration) != {"path", "native_identity"}:
            raise OSError("Unknown native owner declaration")
        if native_identity(Path(declaration["path"])) != declaration["native_identity"]:
            raise OSError("Root-bound native parent identity changed")
    batch = Path(manifest["attempt"])
    batch_started = None
    bootstrap = manifest["bootstrap"]
    if type(bootstrap) is not dict or set(bootstrap) != {"lifetimes", "images"} or bootstrap["lifetimes"] != 2 or bootstrap["images"] != [manifest["runtime"]["native_executable"], "C:/Windows/System32/conhost.exe"]:
        raise OSError("Bootstrap differs from the frozen native control")
    if batch.parent != Path(manifest["attempt_parent"]["path"]):
        raise OSError("Command attempt is outside its assigned parent")
    if case is not None:
        expected_cases = [
            "constructor_partial", "measurement_assign", "product_assign",
            "duplicate_measurement", "duplicate_creation", "registration_ack_lost",
            "family_counter_unavailable", "driver_killed_after_registration",
            "outer_deadline", "duplicate_return", "command_census_bypass",
            "terminal_reserve_exhausted",
        ]
        if manifest["cases"] != expected_cases or case not in expected_cases:
            raise OSError("Unknown refusal batch declaration")
        if batch.exists():
            owner = json.loads(read_control(batch / "batch-owner.json"))
            if set(owner) != {"context", "native_identity", "started_at"} or owner["context"] != digest or owner["native_identity"] != native_identity(batch) or type(owner["started_at"]) not in (int, float):
                raise OSError("Refusal batch native ownership changed")
            batch_started = owner["started_at"]
        attempt = batch / case
    else:
        attempt = batch
    if attempt.exists():
        raise OSError("Command attempt is not an exclusive fresh destination")
    runner = Path(os.environ["BRZ_CHECK_COUNTS"]).parent
    if runner.parent != Path(manifest["runner_parent"]["path"]):
        raise OSError("Runner is outside the assigned native parent")
    runtime = manifest["runtime"]
    if type(runtime) is not dict or set(runtime) != {"venv_executable", "native_executable", "prefix"}:
        raise OSError("Unknown runtime binding declaration")
    for key, actual in (("venv_executable", sys.executable), ("native_executable", sys._base_executable), ("prefix", sys.prefix)):
        if Path(runtime[key]).resolve() != Path(actual).resolve():
            raise OSError("Command runtime differs from Root qualification")
    artifacts = manifest["artifacts"]
    artifact_fields = {"child_cap_bytes", "prior_charged_bytes", "prior_charge_note", "run_reserved_bytes", "observer_bytes", "terminal_bytes", "driver_bytes", "runner_bytes", "allocation_unit_bytes", "minimum_free_bytes"}
    if type(artifacts) is not dict or set(artifacts) != artifact_fields:
        raise OSError("Unknown cumulative artifact declaration")
    if any(type(value) is not int or value <= 0 for key, value in artifacts.items() if key != "prior_charge_note"):
        raise OSError("Invalid cumulative artifact reservation")
    if (
        artifacts["child_cap_bytes"] != 64 * MIB
        or artifacts["observer_bytes"] != 5 * MIB
        or artifacts["terminal_bytes"] != 4 * MIB
        or artifacts["driver_bytes"] != MIB
        or artifacts["runner_bytes"] != 2 * MIB
        or artifacts["run_reserved_bytes"] != 8 * MIB
        or artifacts["prior_charged_bytes"] + artifacts["run_reserved_bytes"] > artifacts["child_cap_bytes"]
        or artifacts["minimum_free_bytes"] < artifacts["run_reserved_bytes"]
        or not artifacts["prior_charge_note"]
    ):
        raise OSError("Root cumulative artifact allowance cannot fit control")
    unit = artifacts["allocation_unit_bytes"]
    paths = manifest["charged_paths"]
    if type(paths) is not list or not 1 <= len(paths) <= 128 or any(type(path) is not str for path in paths):
        raise OSError("Invalid finite charged path inventory")
    charged = 0
    for name in paths:
        path = Path(name)
        if path.is_dir():
            native_identity(path)
            charged += inventory(path, unit=unit)[0]
        else:
            if path.is_symlink():
                raise OSError("Charged artifact is not a physical file")
            charged += max(unit, ((path.stat().st_size + unit - 1) // unit) * unit)
    if charged > artifacts["prior_charged_bytes"]:
        raise OSError("Retained artifact growth exceeded Root's charged block")
    retained_batch = inventory(batch, unit=unit)[0] if batch.exists() else 0
    if artifacts["prior_charged_bytes"] + retained_batch + artifacts["run_reserved_bytes"] > artifacts["child_cap_bytes"]:
        raise OSError("Retained refusal attempts exhausted cumulative artifact credit")
    if inventory(runner, unit=unit)[0] > artifacts["runner_bytes"]:
        raise OSError("Active runner artifact reserve exhausted")
    timing = manifest["time"]
    if type(timing) is not dict or set(timing) != {"child_cap_seconds", "prior_charged_seconds", "run_reserved_seconds", "work_seconds", "cleanup_seconds", "future_reserved_seconds"} or any(type(value) not in (int, float) or not 0 < value <= 460 for value in timing.values()):
        raise OSError("Invalid cumulative time declaration")
    if timing["child_cap_seconds"] != 460 or timing["cleanup_seconds"] != 4 or timing["future_reserved_seconds"] < 320 or timing["work_seconds"] + 4 > timing["run_reserved_seconds"] or timing["prior_charged_seconds"] + timing["run_reserved_seconds"] + timing["future_reserved_seconds"] > 460:
        raise OSError("Required future work no longer fits the child time allowance")
    if batch_started is not None and time.monotonic() - batch_started + timing["work_seconds"] + timing["cleanup_seconds"] + 4 > timing["run_reserved_seconds"]:
        raise OSError("Refusal batch lacks the complete next-work and cleanup reservation")
    for path in (batch.parent, runner):
        if shutil.disk_usage(path).free < artifacts["minimum_free_bytes"]:
            raise OSError("Insufficient physical volume headroom before control")
    if mode == "tiny":
        fixture = manifest["fixture"]
        if type(fixture) is not dict or set(fixture) != {"path", "parent", "owner", "reserve_bytes", "allocation_unit_bytes", "git_executable"}:
            raise OSError("Unknown tiny fixture declaration")
        parent = fixture["parent"]
        if type(parent) is not dict or set(parent) != {"path", "native_identity"}:
            raise OSError("Unknown tiny fixture parent declaration")
        base = Path(parent["path"])
        destination = Path(fixture["path"])
        if base.resolve() != Path(tempfile.gettempdir()).resolve() or native_identity(base) != parent["native_identity"] or destination.parent != base or destination.exists():
            raise OSError("Tiny fixture destination is not fresh in its owned OS-temp parent")
        if type(fixture["owner"]) is not str or not 1 <= len(fixture["owner"]) <= 64 or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in fixture["owner"]) or destination.name != "brz2obsidian-358-" + fixture["owner"]:
            raise OSError("Tiny fixture owner declaration is invalid")
        if fixture["reserve_bytes"] != 32 * MIB or fixture["allocation_unit_bytes"] != unit:
            raise OSError("Tiny fixture exceeds the controls partition")
        if any((ancestor / ".git").exists() for ancestor in (base, *base.parents)):
            raise OSError("OS-temp control is inside an enclosing repository")
        if shutil.disk_usage(base).free < fixture["reserve_bytes"] + artifacts["run_reserved_bytes"]:
            raise OSError("Tiny fixture and artifacts lack actual-volume headroom")
        if Path(shutil.which("git") or "").resolve() != Path(fixture["git_executable"]).resolve():
            raise OSError("Installed Git selection differs from Root's declaration")
        if any(os.environ.get(name) for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")):
            raise OSError("Ambient Git routing conflicts with the exclusively owned fixture")
    if case is not None and not batch.exists():
        batch.mkdir()
        Evidence(limit=65536, terminal_reserve=65536).write(batch / "batch-owner.json", {"context": digest, "native_identity": native_identity(batch), "started_at": time.monotonic()}, terminal=True)
    attempt.mkdir()
    writer = Evidence(limit=MIB, terminal_reserve=65536)
    writer.write(attempt / "owner.json", {"root": str(attempt), "native_identity": native_identity(attempt), "context": digest, "runner": str(runner), "runner_native_identity": native_identity(runner)})
    writer.write(attempt / "disk-before.json", {"charged_bytes": charged, "prior_reserved_bytes": artifacts["prior_charged_bytes"], "retained_batch_bytes": retained_batch, "run_reserved_bytes": artifacts["run_reserved_bytes"], "free_bytes": shutil.disk_usage(attempt).free, "allocation_unit_bytes": unit})
    if mode == "tiny":
        writer.write(attempt / "fixture-request.json", {"context": digest, **manifest["fixture"]})
    if case is not None:
        (attempt / "resume-trace.jsonl").open("xb").close()
    return attempt, manifest


def finish_control(attempt, manifest):
    """Retain rounded control charges; final runner closure remains Root-owned."""
    from tests.support.resource_pilot import Evidence, inventory

    bounds = manifest["artifacts"]
    unit = bounds["allocation_unit_bytes"]
    observer = inventory(attempt / "observer", unit=unit)[0]
    total = inventory(attempt, unit=unit)[0]
    driver = total - observer + unit
    runner = inventory(Path(os.environ["BRZ_CHECK_COUNTS"]).parent, unit=unit)[0]
    record = {"observer_rounded_bytes": observer, "driver_rounded_bytes_with_terminal_reserve": driver + 65536, "runner_rounded_bytes_so_far": runner, "prior_charged_bytes": bounds["prior_charged_bytes"], "final_runner_charge_required": True}
    Evidence(limit=65536, terminal_reserve=65536).write(attempt / "allocation-after.json", record, terminal=True)
    if observer > bounds["observer_bytes"] or driver + 65536 > bounds["driver_bytes"] or runner > bounds["runner_bytes"]:
        raise OSError("Control allocation exceeded its individual physical reserve")


def _exchange(event, expected):
    raw = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    if len(raw.encode()) > 12 * 1024:
        raise OSError("Command control record exceeds its finite bound")
    sys.stdout.write(raw)
    sys.stdout.flush()
    if sys.stdin.readline(65) != expected + "\n":
        raise OSError("Command observer acknowledgment was lost or invalid")


class CommandCalls:
    """Only the actual returned call releases command finalization."""

    def __init__(self, fault=None, attempt=None):
        self.seq = 0
        self.current = None
        self.deadline = float(os.environ["BRZ_COMMAND_DEADLINE"])
        self.fault = fault
        self.attempt = attempt
        self.trace_bytes = 0
        self.product_handles = {}
        self.product_closed = 0
        self.product_close_duplicates = 0
        self.measurement_opened = 0
        self.measurement_closed = 0

    def witness(self, boundary, **details):
        if self.attempt is None:
            raise OSError("Native fault witness has no exclusive owner")
        data = (json.dumps({"boundary": boundary, "seq": self.seq, **details}) + "\n").encode()
        if len(data) > 4096:
            raise OSError("Native fault witness exceeds its reserved bytes")
        with (self.attempt / "fault-witness.json").open("xb") as stream:
            if stream.write(data) != len(data):
                raise OSError("Native fault witness was incomplete")
            stream.flush()
            os.fsync(stream.fileno())

    def resume_witness(self):
        if self.attempt is None:
            return
        data = (json.dumps({"event": "native_resume_attempt", "seq": self.seq}, separators=(",", ":")) + "\n").encode()
        if self.trace_bytes + len(data) > 65536:
            raise OSError("Native resume witness reservation exhausted")
        self.trace_bytes += len(data)
        with (self.attempt / "resume-trace.jsonl").open("ab") as stream:
            if stream.write(data) != len(data):
                raise OSError("Native resume write-ahead trace was incomplete")
            stream.flush()
            os.fsync(stream.fileno())

    def ownership_witness(self):
        if self.attempt is None:
            return
        data = {
            "measurement_opened": self.measurement_opened,
            "measurement_closed": self.measurement_closed,
            "product_opened": len(self.product_handles),
            "product_closed": self.product_closed,
            "product_close_duplicates": self.product_close_duplicates,
        }
        raw = (json.dumps(data) + "\n").encode()
        with (self.attempt / "driver-ownership.json").open("xb") as stream:
            if stream.write(raw) != len(raw):
                raise OSError("Native ownership witness was incomplete")
            stream.flush()
            os.fsync(stream.fileno())

    def exception_witness(self, error):
        if self.attempt is None:
            return
        raw = (json.dumps({"type": type(error).__name__, "message": str(error)}) + "\n").encode()
        if len(raw) > 4096:
            raise OSError("Original exception exceeds its witness reservation")
        with (self.attempt / "original-exception.json").open("xb") as stream:
            if stream.write(raw) != len(raw):
                raise OSError("Original exception witness was incomplete")
            stream.flush()
            os.fsync(stream.fileno())

    @contextmanager
    def native_boundary(self, *, constructor=False):
        calls = self
        original = ctypes.WinDLL

        class NativeFunction:
            def __init__(self, function, name):
                self.function = function
                self.name = name

            @property
            def argtypes(self):
                return self.function.argtypes

            @argtypes.setter
            def argtypes(self, value):
                self.function.argtypes = value

            @property
            def restype(self):
                return self.function.restype

            @restype.setter
            def restype(self, value):
                self.function.restype = value

            def __call__(self, *args):
                if self.name == "ResumeThread":
                    calls.resume_witness()
                if self.name == "SetInformationJobObject" and constructor and calls.fault == "constructor_partial":
                    result = self.function(args[0], -1, *args[2:])
                    error = ctypes.get_last_error()
                    calls.witness("constructor_partial", native_error=error, native_result=bool(result))
                    ctypes.set_last_error(error)
                    return result
                if self.name == "AssignProcessToJobObject" and calls.fault == "product_assign":
                    result = self.function(0, args[1])
                    error = ctypes.get_last_error()
                    calls.witness("product_assign", native_error=error, native_result=bool(result))
                    ctypes.set_last_error(error)
                    return result
                result = self.function(*args)
                if self.name == "CreateJobObjectW" and result:
                    calls.product_handles[int(result)] = False
                elif self.name == "CloseHandle" and int(args[0]) in calls.product_handles:
                    handle = int(args[0])
                    if calls.product_handles[handle]:
                        calls.product_close_duplicates += 1
                    if result:
                        calls.product_handles[handle] = True
                        calls.product_closed += 1
                return result

        class WitnessDLL(original):
            def __getattr__(self, name):
                function = super().__getattr__(name)
                if name in ("ResumeThread", "CreateJobObjectW", "CloseHandle", "SetInformationJobObject", "AssignProcessToJobObject"):
                    function = NativeFunction(function, name)
                    setattr(self, name, function)
                return function

        ctypes.WinDLL = WitnessDLL
        try:
            yield
        finally:
            ctypes.WinDLL = original

    def call(self, kind, function, argv, **kwargs):
        if self.current is not None or self.seq >= 512:
            raise OSError("Concurrent or excessive observed command call")
        if time.monotonic() + kwargs.get("timeout", 30) + 4 >= self.deadline:
            raise OSError("Insufficient remaining owned-family work time")
        self.seq += 1
        seq = self.seq
        _exchange({"event": "command_begin", "seq": seq, "kind": kind, "argv": list(argv)}, f"begin {seq}")
        self.current = {"seq": seq, "created": False, "jobs": []}
        try:
            try:
                result = function(argv, **kwargs)
            except BaseException as original:
                # Original cleanup has completed when the real function raises.
                for job in self.current["jobs"]:
                    try:
                        job.close_measurement()
                    except OSError as error:
                        original.add_note(f"Measurement handle cleanup also failed: {error}")
                try:
                    self.ownership_witness()
                    self.exception_witness(original)
                except OSError as error:
                    original.add_note(f"Ownership witness also failed: {error}")
                try:
                    _exchange({"event": "command_return", "seq": seq, "status": "raised" if self.current["created"] else "not_created"}, f"finalized {seq}")
                except (OSError, ValueError):
                    pass
                raise
            for job in self.current["jobs"]:
                job.close_measurement()
            self.ownership_witness()
            _exchange({"event": "command_return", "seq": seq, "status": "returned"}, f"finalized {seq}")
            return result
        finally:
            self.current = None


@contextmanager
def measured_calls(*, fault=None, attempt=None):
    """Adapt fixed identities and factories without changing product cleanup."""
    from brz2obsidian.publication import git_payload, git_read
    from tools.update_resource_probe import _Windows

    resource_pilot = sys.modules.get("tests.support.resource_pilot")
    calls = CommandCalls(fault, attempt)
    api = _Windows()
    original_read, original_verify = git_read.read_git, git_payload.verify_blobs
    original_job, original_popen = git_read._WindowsJob, git_read._SuspendedPopen
    original_run, original_subprocess_popen = subprocess.run, subprocess.Popen
    changes = []

    def bind(module, name, value):
        changes.append((module, name, getattr(module, name)))
        setattr(module, name, value)

    class MeasuredJob(original_job):
        def __init__(self):
            if calls.current is None:
                raise OSError("Process constructor bypassed command begin")
            self.measurement = api.kernel.CreateJobObjectW(None, None)
            api.require(self.measurement)
            calls.measurement_opened += 1
            calls.current["jobs"].append(self)
            try:
                with calls.native_boundary(constructor=True):
                    super().__init__()
            except BaseException:
                self.close_measurement()
                raise

        def close_measurement(self):
            if self.measurement is not None:
                handle, self.measurement = self.measurement, None
                api.require(api.kernel.CloseHandle(handle))
                calls.measurement_closed += 1

        def attach_handle(self, handle):
            calls.current["created"] = True
            if calls.fault == "measurement_assign":
                result = api.kernel.AssignProcessToJobObject(0, handle)
                error = ctypes.get_last_error()
                calls.witness("measurement_assign", native_error=error, native_result=bool(result))
                ctypes.set_last_error(error)
                api.require(result)
            api.require(api.kernel.AssignProcessToJobObject(self.measurement, handle))
            super().attach_handle(handle)
            seq = calls.current["seq"]
            _exchange({"event": "command_register", "seq": seq, "measurement_handle": self.measurement, "creation_process_handle": int(handle)}, f"registered {seq}")
            # The observer now owns a duplicate. Closing this original does not
            # retain or alter the independently owned product cleanup job.
            self.close_measurement()
            if calls.fault == "outer_deadline":
                calls.witness("outer_deadline", registration_acknowledged=True)
                time.sleep(60)

    class MeasuredPopen(original_popen):
        def _execute_child(self, *args, **kwargs):
            with calls.native_boundary():
                return super()._execute_child(*args, **kwargs)

    def read(argv, **kwargs):
        return calls.call("read", original_read, argv, **kwargs)

    def verify(argv, **kwargs):
        return calls.call("payload", original_verify, argv, **kwargs)

    def fixture(vault, *args):
        def actual(argv, **kwargs):
            job = MeasuredJob()

            class FixturePopen(original_popen):
                def __init__(self, *args, **options):
                    super().__init__(*args, job=job, **options)

            try:
                subprocess.Popen = FixturePopen
                return original_run(argv, **kwargs)
            finally:
                subprocess.Popen = original_subprocess_popen
                job.close()

        return resource_pilot._git_with_runner(vault, args, lambda argv, **kwargs: calls.call("fixture", actual, argv, **kwargs))

    try:
        for module in (git_read, git_payload):
            if module._WindowsJob is not original_job or module._SuspendedPopen is not original_popen:
                raise OSError("Unrecognized Git creation factory")
            bind(module, "_WindowsJob", MeasuredJob)
            bind(module, "_SuspendedPopen", MeasuredPopen)
        for names, attribute, original, replacement in (
            (READ_CONSUMERS, "read_git", original_read, read),
            (PAYLOAD_CONSUMERS, "verify_blobs", original_verify, verify),
        ):
            for name in names:
                module = sys.modules.get("brz2obsidian.publication." + name)
                if module is None:
                    continue
                if getattr(module, attribute, None) is not original:
                    raise OSError("Unrecognized imported Git consumer identity")
                bind(module, attribute, replacement)
        bind(git_read, "read_git", read)
        bind(git_payload, "verify_blobs", verify)
        if resource_pilot is not None:
            bind(resource_pilot, "git", fixture)
        yield calls
    finally:
        for module, name, value in reversed(changes):
            setattr(module, name, value)
        # A fixed consumer imported inside the context inherits the wrapped
        # core function. Restore only this context's known function identities.
        for names, attribute, original, replacement in (
            (READ_CONSUMERS, "read_git", original_read, read),
            (PAYLOAD_CONSUMERS, "verify_blobs", original_verify, verify),
        ):
            for name in names:
                module = sys.modules.get("brz2obsidian.publication." + name)
                if module is not None and getattr(module, attribute, None) is replacement:
                    setattr(module, attribute, original)


class _Memory(ctypes.Structure):
    _fields_ = [("cb", w.DWORD), ("faults", w.DWORD)] + [(name, ctypes.c_size_t) for name in ("peak_ws", "ws", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile", "private")]


class _Region(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("allocation_base", ctypes.c_void_p), ("protection", w.DWORD), ("partition", w.WORD), ("size", ctypes.c_size_t), ("state", w.DWORD), ("protect", w.DWORD), ("type", w.DWORD)]


def _private(handle=-1):
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(_Memory), w.DWORD]
    value = _Memory()
    value.cb = ctypes.sizeof(value)
    if not psapi.GetProcessMemoryInfo(w.HANDLE(handle), ctypes.byref(value), value.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return value.private


def _allocate(size, parent_pid):
    """Trusted control witness; measured process imports only Python stdlib."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, w.DWORD, w.DWORD]
    kernel.VirtualAlloc.restype = ctypes.c_void_p
    kernel.VirtualQuery.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Region), ctypes.c_size_t]
    kernel.VirtualQuery.restype = ctypes.c_size_t
    kernel.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, w.DWORD]
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    before = _private()
    address = kernel.VirtualAlloc(None, size, 0x3000, 4)
    if not address:
        raise ctypes.WinError(ctypes.get_last_error())
    ctypes.memset(address, 0x5A, size)
    region = _Region()
    if kernel.VirtualQuery(address, ctypes.byref(region), ctypes.sizeof(region)) != ctypes.sizeof(region) or region.state != 0x1000 or region.size < size:
        raise OSError("Allocated control region is not fully committed")
    parent = kernel.OpenProcess(0x0410, False, parent_pid)
    if not parent:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        parent_private = _private(parent)
        held = _private()
    finally:
        if not kernel.CloseHandle(parent):
            raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.VirtualFree(address, 0, 0x8000):
        raise ctypes.WinError(ctypes.get_last_error())
    print(json.dumps({"requested_bytes": size, "committed_region_bytes": region.size, "child_before_private_bytes": before, "child_held_private_bytes": held, "parent_private_bytes": parent_private, "released_before_parent_exit": True}), flush=True)
    # The command parent exits while this child still owns stdout. Only normal
    # product cleanup job closure may end it and release the private Git pipes.
    time.sleep(60)


def _parent(size):
    environment = os.environ.copy()
    environment.pop("__PYVENV_LAUNCHER__", None)
    child = subprocess.Popen([sys._base_executable, __file__, "allocate", str(size), str(os.getpid())], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
    raw = child.stdout.readline(4097)
    if not raw.endswith(b"\n") or len(raw) > 4096:
        raise OSError("Missing bounded allocation witness")
    proof = json.loads(raw)
    proof["child_alive_at_parent_exit"] = child.poll() is None
    print(json.dumps(proof), flush=True)
    # Deliberately leave the child alive, with pipes held, for the real cleanup.


def _peaks(attempt):
    from brz2obsidian.publication import git_read
    from tests.support.resource_pilot import Evidence

    witnesses = []
    with measured_calls():
        for size in (32 * MIB, 8 * MIB):
            result = git_read.read_git([sys._base_executable, __file__, "parent", str(size)], env=os.environ.copy(), timeout=5)
            if result.returncode:
                raise OSError("Fixed allocation control failed")
            witnesses.append(json.loads(result.stdout))
    Evidence(limit=MIB - 65536, terminal_reserve=65536).write(attempt / "peaks.json", witnesses)


def _refusal(case, attempt):
    from brz2obsidian.publication import git_read

    with measured_calls(fault=case, attempt=attempt) as calls:
        result = git_read.read_git(
            [sys._base_executable, "-c", "pass"],
            env=os.environ.copy(),
            timeout=0.25,
        )
        if result.returncode:
            raise OSError("Fixed refusal command unexpectedly failed")
        if case == "duplicate_return":
            _exchange({"event": "command_return", "seq": calls.seq, "status": "returned"}, f"finalized {calls.seq}")
        if case == "command_census_bypass":
            subprocess.run(
                [sys._base_executable, "-c", "pass"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=0.25,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )


def _tiny(attempt):
    from brz2obsidian.publication import git_payload, git_read
    from tests.support import resource_pilot

    request = json.loads(resource_pilot.read_control(attempt / "fixture-request.json"))
    raw_manifest = resource_pilot.read_control(Path(os.environ["BRZ_COMMAND_GIT_MANIFEST"]))
    digest = hashlib.sha256(raw_manifest).hexdigest()
    manifest = json.loads(raw_manifest)
    if (
        digest != os.environ["BRZ_COMMAND_GIT_MANIFEST_SHA256"]
        or request != {"context": digest, **manifest["fixture"]}
        or Path(manifest["attempt"]) != attempt
    ):
        raise OSError("Tiny driver request lost its Root binding")
    root = Path(request["path"])
    parent = Path(request["parent"]["path"])
    if (
        root.parent != parent
        or root.exists()
        or resource_pilot.native_identity(parent) != request["parent"]["native_identity"]
        or Path(shutil.which("git") or "").resolve() != Path(request["git_executable"]).resolve()
        or shutil.disk_usage(parent).free < request["reserve_bytes"] + 8 * MIB
    ):
        raise OSError("Tiny driver physical ownership preflight changed")
    oracle_path = Path(__file__).resolve().parents[1] / "fixtures/resource_git/command16-oracles.json"
    raw_oracle = resource_pilot.read_control(oracle_path)
    if hashlib.sha256(raw_oracle).hexdigest() != "8f3cd763911e889f0265e8c046e8375dc136ea3d4b20e3356a3609f5b8e2a850":
        raise OSError("Independent command oracle differs from accepted bytes")
    oracle = json.loads(raw_oracle)["miniatures"]["objects"]["base"]
    raw = bytes.fromhex(oracle["raw_hex"])
    if len(raw) != oracle["size"] or hashlib.sha256(raw).hexdigest() != oracle["sha256"]:
        raise OSError("Independent miniature byte declaration is inconsistent")

    writer = resource_pilot.Evidence(limit=MIB - 65536, terminal_reserve=65536)
    root.mkdir()
    identity = resource_pilot.native_identity(root)
    writer.write(root / "owner.json", {"context": digest, "owner": request["owner"], "native_identity": identity})
    vault = root / "vault"
    template = root / "empty-template"
    for directory in (vault, template, root / "hooks"):
        directory.mkdir()
    with (vault / "tiny.bin").open("xb") as stream:
        if stream.write(raw) != len(raw):
            raise OSError("Tiny fixture byte write was incomplete")

    original_read, original_verify = git_read.read_git, git_payload.verify_blobs
    original_fixture = resource_pilot.git
    factory_modules = (git_read, git_payload)
    originals = [
        (module, module._WindowsJob, module._SuspendedPopen)
        for module in factory_modules
    ]
    original_subprocess = subprocess.Popen
    common = [
        "git", "--no-pager", "-c", "core.bigFileThreshold=1m",
        "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-C", str(vault),
    ]
    settings = ("-c", "core.bigFileThreshold=1m", "-c", "gc.auto=0", "-c", "maintenance.auto=false")
    facts = {"fixture_root": str(root), "fixture_native_identity": identity}
    read_names = ("git_read", *READ_CONSUMERS)
    payload_names = ("git_payload", *PAYLOAD_CONSUMERS)

    class PositionSink:
        def __init__(self):
            self.position = 0

        def write(self, block):
            end = self.position + len(block)
            if end > len(raw) or block != raw[self.position:end]:
                raise OSError("Tiny stream differs from independent positional bytes")
            self.position = end
            return len(block)

    with measured_calls():
        facts["git_version"] = resource_pilot.git(vault, *settings, "--version").decode("ascii").strip()
        resource_pilot.git(
            vault, *settings, "init", "--object-format=sha1", "--ref-format=files",
            "--template=" + str(template),
        )
        oid = resource_pilot.git(vault, *settings, "hash-object", "-w", "tiny.bin").decode("ascii").strip()
        if oid != oracle["git_blob_sha1"]:
            raise OSError("Installed Git miniature differs from independent object ID")
        facts["blob_oid"] = oid
        read_requests = (
            ("object_format", ["rev-parse", "--show-object-format"], "sha1"),
            ("ref_format", ["rev-parse", "--show-ref-format"], "files"),
            ("big_file_threshold", ["config", "--get", "core.bigFileThreshold"], "1m"),
            ("blob_size", ["cat-file", "-s", oid], "8"),
        )
        for name, (key, arguments, expected) in zip(read_names, read_requests, strict=True):
            module = importlib.import_module("brz2obsidian.publication." + name)
            result = module.read_git(common + arguments, env=os.environ.copy())
            value = result.stdout.decode("ascii").strip()
            if result.returncode or value != expected:
                raise OSError("Actual fixed Git read consumer returned unexpected evidence")
            facts[key] = int(value) if key == "blob_size" else value
        verified = []
        for name in payload_names:
            module = importlib.import_module("brz2obsidian.publication." + name)
            sink = PositionSink()
            module.verify_blobs(
                common + ["cat-file", "--batch"], env=os.environ.copy(),
                objects=((oid, oracle["size"], oracle["sha256"], sink),),
            )
            if sink.position != oracle["size"]:
                raise OSError("Actual fixed Git payload consumer did not finish its stream")
            verified.append(sink.position)
    aliases_restored = (
        resource_pilot.git is original_fixture
        and all(sys.modules["brz2obsidian.publication." + name].read_git is original_read for name in read_names)
        and all(sys.modules["brz2obsidian.publication." + name].verify_blobs is original_verify for name in payload_names)
    )
    factories_restored = subprocess.Popen is original_subprocess and all(
        module._WindowsJob is job and module._SuspendedPopen is popen
        for module, job, popen in originals
    )
    if not aliases_restored or not factories_restored:
        raise OSError("Fixed Git adapters did not restore their original identities")
    if resource_pilot.native_identity(root) != identity:
        raise OSError("Tiny fixture native ownership changed during Git calls")
    allocated, rows = resource_pilot.inventory(root, unit=request["allocation_unit_bytes"])
    if allocated > request["reserve_bytes"] or any(row.get("link_not_followed") for row in rows):
        raise OSError("Tiny fixture exceeded its reserved physical inventory")
    facts.update(
        read_consumers=read_names, payload_consumers=payload_names,
        verified_stream_bytes=verified, original_aliases_restored=aliases_restored,
        original_factory_classes_restored=factories_restored,
        fixture_rounded_bytes=allocated, fixture_inventory=rows,
    )
    writer.write(attempt / "tiny.json", facts)


def main():
    mode = sys.argv[1]
    if mode == "allocate":
        _allocate(int(sys.argv[2]), int(sys.argv[3]))
        return
    if mode == "parent":
        _parent(int(sys.argv[2]))
        return
    from tools.update_resource_probe import _runtime_binding

    _exchange({"event": "hello", "pid": os.getpid(), **_runtime_binding()}, "ready")
    if mode == "peaks":
        _peaks(Path(sys.argv[2]))
    elif mode == "refusal":
        _refusal(sys.argv[2], Path(sys.argv[3]))
    elif mode == "tiny":
        _tiny(Path(sys.argv[2]))
    else:
        raise OSError("Unknown fixed command pilot")
    _exchange({"event": "done", "pid": os.getpid(), "ok": True}, "continue")


if __name__ == "__main__":
    main()
