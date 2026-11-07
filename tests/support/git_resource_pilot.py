"""Strict command observation adapters and fixed synthetic mechanism controls."""

import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from ctypes import wintypes as w
from importlib import import_module
from pathlib import Path

MIB = 1024 * 1024


def control_preflight():
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
        "runtime", "artifacts", "time", "charged_paths",
    }
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
        or manifest["mode"] != "peaks"
        or Path(manifest["checkout"]).resolve() != root
    ):
        raise OSError("Root command manifest context mismatch")
    for name in ("attempt_parent", "runner_parent"):
        declaration = manifest[name]
        if type(declaration) is not dict or set(declaration) != {"path", "native_identity"}:
            raise OSError("Unknown native owner declaration")
        if native_identity(Path(declaration["path"])) != declaration["native_identity"]:
            raise OSError("Root-bound native parent identity changed")
    attempt = Path(manifest["attempt"])
    if attempt.parent != Path(manifest["attempt_parent"]["path"]) or attempt.exists():
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
    if inventory(runner, unit=unit)[0] > artifacts["runner_bytes"]:
        raise OSError("Active runner artifact reserve exhausted")
    timing = manifest["time"]
    if type(timing) is not dict or set(timing) != {"child_cap_seconds", "prior_charged_seconds", "run_reserved_seconds", "work_seconds", "cleanup_seconds", "future_reserved_seconds"} or any(type(value) not in (int, float) or not 0 < value <= 400 for value in timing.values()):
        raise OSError("Invalid cumulative time declaration")
    if timing["child_cap_seconds"] != 400 or timing["cleanup_seconds"] != 4 or timing["future_reserved_seconds"] < 320 or timing["work_seconds"] + 4 > timing["run_reserved_seconds"] or timing["prior_charged_seconds"] + timing["run_reserved_seconds"] + timing["future_reserved_seconds"] > 400:
        raise OSError("Required future work no longer fits the child time allowance")
    for path in (attempt.parent, runner):
        if shutil.disk_usage(path).free < artifacts["minimum_free_bytes"]:
            raise OSError("Insufficient physical volume headroom before control")
    attempt.mkdir()
    writer = Evidence(limit=MIB, terminal_reserve=65536)
    writer.write(attempt / "owner.json", {"root": str(attempt), "native_identity": native_identity(attempt), "context": digest, "runner": str(runner), "runner_native_identity": native_identity(runner)})
    writer.write(attempt / "disk-before.json", {"charged_bytes": charged, "prior_reserved_bytes": artifacts["prior_charged_bytes"], "run_reserved_bytes": artifacts["run_reserved_bytes"], "free_bytes": shutil.disk_usage(attempt).free, "allocation_unit_bytes": unit})
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

    def __init__(self):
        self.seq = 0
        self.current = None
        self.deadline = float(os.environ["BRZ_COMMAND_DEADLINE"])

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
                    _exchange({"event": "command_return", "seq": seq, "status": "raised" if self.current["created"] else "not_created"}, f"finalized {seq}")
                except (OSError, ValueError):
                    pass
                raise
            for job in self.current["jobs"]:
                job.close_measurement()
            _exchange({"event": "command_return", "seq": seq, "status": "returned"}, f"finalized {seq}")
            return result
        finally:
            self.current = None


@contextmanager
def measured_calls():
    """Adapt fixed identities and factories without changing product cleanup."""
    from brz2obsidian.publication import git_payload, git_read
    from tests.support import resource_pilot
    from tools.update_resource_probe import _Windows

    calls = CommandCalls()
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
            calls.current["jobs"].append(self)
            try:
                super().__init__()
            except BaseException:
                self.close_measurement()
                raise

        def close_measurement(self):
            if self.measurement is not None:
                handle, self.measurement = self.measurement, None
                api.require(api.kernel.CloseHandle(handle))

        def attach_handle(self, handle):
            calls.current["created"] = True
            api.require(api.kernel.AssignProcessToJobObject(self.measurement, handle))
            super().attach_handle(handle)
            seq = calls.current["seq"]
            _exchange({"event": "command_register", "seq": seq, "measurement_handle": self.measurement, "creation_process_handle": int(handle)}, f"registered {seq}")
            # The observer now owns a duplicate. Closing this original does not
            # retain or alter the independently owned product cleanup job.
            self.close_measurement()

    class MeasuredPopen(original_popen):
        pass

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
            (("vault_admission", "vault_attributes", "vault_history"), "read_git", original_read, read),
            (("checkpoint_payload", "vault_history", "vault_repair", "attachment_ownership", "vault_recovery", "vault_apply"), "verify_blobs", original_verify, verify),
        ):
            for name in names:
                module = import_module("brz2obsidian.publication." + name)
                if getattr(module, attribute, None) is not original:
                    raise OSError("Unrecognized imported Git consumer identity")
                bind(module, attribute, replacement)
        bind(git_read, "read_git", read)
        bind(git_payload, "verify_blobs", verify)
        bind(resource_pilot, "git", fixture)
        yield calls
    finally:
        for module, name, value in reversed(changes):
            setattr(module, name, value)


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
    if mode != "peaks":
        raise OSError("Unknown fixed command pilot")
    _peaks(Path(sys.argv[2]))
    _exchange({"event": "done", "pid": os.getpid(), "ok": True}, "continue")


if __name__ == "__main__":
    main()
