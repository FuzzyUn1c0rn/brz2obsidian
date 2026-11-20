"""Qualify the owned observer with independently specified Windows allocations."""

import ctypes
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from tools.update_resource_probe import observe, observe_commands, observe_phases

ROOT = Path(__file__).resolve().parents[2]


def test_owned_family_peak_survives_short_lived_descendant():
    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    result = observe(
        [
            sys.executable,
            str(ROOT / "tests/local_acceptance/resource_calibration.py"),
            "normal",
        ],
        output,
        timeout=15,
    )

    assert result["status"] == "completed", result
    assert result["final_job"]["ActiveProcesses"] == 0
    assert result["final_job"]["TotalProcesses"] >= 2
    assert result["observer_pid"] not in result["observed_pids"]
    assert result["observer_in_measured_job"] is False
    assert result["final_job"]["JobMemoryLimit"] == 512 * 1024 * 1024
    assert result["final_job"]["LimitFlags"] == 0x2208
    assert result["per_git_lifetime_attribution"] == "unqualified"
    frames = [
        json.loads(line) for line in (output / "frames.jsonl").read_text().splitlines()
    ]
    baseline = next(frame for frame in frames if frame["phase"] == "baseline")
    held = next(frame for frame in frames if frame["phase"] == "held")
    deltas = sorted(result["allocation_private_deltas"].values())
    assert deltas[0] >= 8 * 1024 * 1024
    assert deltas[1] >= 16 * 1024 * 1024
    assert {row["pid"] for row in baseline["processes"]} == {
        row["pid"] for row in held["processes"]
    }
    assert held["sampled_family_private_bytes"] >= 24 * 1024 * 1024
    assert len(held["processes"]) >= 2
    assert result["final_job"]["PeakJobMemoryUsed"] >= (
        held["job"]["PeakJobMemoryUsed"] + 8 * 1024 * 1024
    )
    assert result["calibration"]["requested_bytes"] == 56 * 1024 * 1024
    assert result["calibration"]["short_allocation_released"] is True
    assert all(
        row["PrivateUsage"] <= row["PeakPagefileUsage"] for row in held["processes"]
    )
    assert held["system"]["CommitLimit_bytes"] > held["system"]["CommitTotal_bytes"] > 0
    assert held["system"]["process_available_commit_bytes"] > 0
    assert held["observer"]["PrivateUsage"] > 0
    assert result["max_sample_gap_seconds"] > 0
    released = next(frame for frame in frames if frame["phase"] == "done")
    parent = next(
        row
        for row in released["processes"]
        if row["pid"] == result["calibration"]["pid"]
    )
    assert parent["PrivateUsage"] < parent["PeakPagefileUsage"]
    for frame in frames:
        assert frame["sampled_family_private_bytes"] == sum(
            row["PrivateUsage"] for row in frame["processes"]
        )
        assert frame["sampled_family_working_set_bytes"] == sum(
            row["WorkingSetSize"] for row in frame["processes"]
        )
        system = frame["system"]
        assert (
            system["CommitTotal_bytes"]
            == system["CommitTotal_pages"] * system["PageSize_bytes"]
        )
        assert (
            system["system_available_commit_bytes"]
            == system["CommitLimit_bytes"] - system["CommitTotal_bytes"]
        )
        assert frame["sample_started"] <= frame["sample_finished"]
    assert json.loads((output / "report.json").read_text()) == result


def test_completed_process_cannot_substitute_invalid_allocation_evidence():
    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    result = observe(
        [
            sys.executable,
            str(ROOT / "tests/local_acceptance/resource_calibration.py"),
            "invalid-done",
        ],
        output,
        timeout=15,
    )

    assert result["status"] == "failed"
    assert "allocation evidence" in result["error"]
    assert result["final_job"]["ActiveProcesses"] == 0
    assert b'"requested_bytes": 0' in (output / "protocol.bin").read_bytes()


def test_truthful_looking_markers_cannot_replace_observed_committed_allocations():
    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    result = observe(
        [
            sys.executable,
            str(ROOT / "tests/local_acceptance/resource_calibration.py"),
            "false-allocation",
        ],
        output,
        timeout=15,
    )

    assert result["status"] == "failed"
    assert "OS private-commit delta" in result["error"]
    assert result["final_job"]["ActiveProcesses"] == 0


def test_timeout_reaps_all_owned_descendants_and_preserves_measurements():
    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    result = observe(
        [
            sys.executable,
            str(ROOT / "tests/local_acceptance/resource_calibration.py"),
            "timeout",
        ],
        output,
        timeout=2,
    )

    assert result["status"] == "timeout"
    assert result["elapsed_seconds"] < 5
    assert result["phases"] == ["baseline", "held"]
    assert result["final_job"]["ActiveProcesses"] == 0
    assert result["final_job"]["TotalProcesses"] >= 2
    assert result["final_job"]["PeakJobMemoryUsed"] > 24 * 1024 * 1024
    direct = [
        row for row in result["attribution"] if row["origin"] == "direct-before-resume"
    ]
    assert len(direct) == 1
    assert direct[0]["creation_filetime_100ns"] > 0
    assert direct[0]["handle_retained"]
    assert direct[0]["image"].lower().endswith("python.exe")
    assert (output / "protocol.bin").stat().st_size > 0


def test_missing_executable_fails_before_any_process_enters_owned_job():
    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    result = observe([str(output / "missing.exe")], output)

    assert result["status"] == "failed"
    assert result["final_job"]["TotalProcesses"] == 0
    assert result["final_job"]["ActiveProcesses"] == 0
    assert result["observed_pids"] == []


@pytest.mark.parametrize(
    "limits",
    [
        {"timeout": 27},
        {"memory_limit": 513 * 1024 * 1024},
        {"artifact_limit": 65 * 1024 * 1024},
        {"timeout": True},
        {"timeout": "1"},
        {"timeout": float("nan")},
        {"memory_limit": float(512 * 1024 * 1024)},
        {"artifact_limit": True},
    ],
)
def test_unapproved_limit_is_refused_without_creating_artifacts(limits):
    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    with pytest.raises(ValueError, match="approved finite bounds"):
        observe([sys.executable], output, **limits)
    assert not output.exists()


def test_unavailable_live_process_counter_cannot_qualify_a_family(monkeypatch):
    original = ctypes.WinDLL
    kernel = original("kernel32", use_last_error=True)
    kernel.GetProcessId.argtypes = [ctypes.c_void_p]
    failed = []

    def load(name, *args, **kwargs):
        dll = original(name, *args, **kwargs)
        if name == "psapi":
            read = dll.GetProcessMemoryInfo

            def unavailable(handle, counters, size):
                if not failed and kernel.GetProcessId(handle) != os.getpid():
                    failed.append(True)
                    ctypes.set_last_error(5)
                    return 0
                return read(handle, counters, size)

            read.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
            dll.GetProcessMemoryInfo = unavailable
        return dll

    monkeypatch.setattr(ctypes, "WinDLL", load)
    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    result = observe(
        [
            sys.executable,
            str(ROOT / "tests/local_acceptance/resource_calibration.py"),
            "normal",
        ],
        output,
    )

    assert failed
    assert result["status"] == "failed"
    assert "process counters unavailable" in result["error"]
    assert result["final_job"]["ActiveProcesses"] == 0


@pytest.mark.parametrize(
    "fault",
    [
        "known-exit",
        "unknown-exit",
        "census-open",
        "census-times",
        "census-image",
        "membership-error",
        "membership-false",
        "census-close-error",
        "direct-times-error",
    ],
)
def test_command_family_survives_optional_live_descendant_memory_gap(
    monkeypatch, fault
):
    exit_unavailable = fault == "unknown-exit"
    census_unavailable = fault == "census-open"
    creation_unavailable = fault in ("census-times", "census-close-error")
    image_unavailable = fault == "census-image"
    membership_fault = fault in ("membership-error", "membership-false")
    fatal = membership_fault or fault in ("census-close-error", "direct-times-error")
    attempt = ROOT / "tmp" / "command-git-proof" / "repair" / uuid4().hex
    attempt.mkdir(parents=True)
    marker, release = attempt / "descendant.json", attempt / "release"
    reached = []
    census_job = []
    proof_handles, closed_proof_handles = [], []
    selected_census_handle, closed_census_handles = [], []
    census_close_attempts, selected_census_lifetime_active = [], []
    selected_times_success = []
    direct_handle = []
    original = ctypes.WinDLL
    kernel = original("kernel32", use_last_error=True)
    kernel.GetProcessId.argtypes = [ctypes.c_void_p]
    kernel.GetProcessId.restype = ctypes.c_ulong
    kernel.GetExitCodeProcess.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    kernel.GetExitCodeProcess.restype = ctypes.c_int
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.IsProcessInJob.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int),
    ]
    kernel.IsProcessInJob.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int

    def load(name, *args, **kwargs):
        dll = original(name, *args, **kwargs)
        if name == "kernel32":
            if fault == "direct-times-error":
                assign = dll.AssignProcessToJobObject
                assign.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                assign.restype = ctypes.c_int

                def retain_direct(job, handle):
                    value = assign(job, handle)
                    if value and not direct_handle:
                        direct_handle[:] = [int(handle), int(job)]
                    return value

                dll.AssignProcessToJobObject = retain_direct
                direct_times = dll.GetProcessTimes
                direct_times.argtypes = [ctypes.c_void_p] * 5
                direct_times.restype = ctypes.c_int

                def unavailable_direct_times(handle, *values):
                    if (
                        not reached
                        and direct_handle
                        and int(handle) == direct_handle[0]
                    ):
                        pid = kernel.GetProcessId(handle)
                        code, member = ctypes.c_ulong(), ctypes.c_int()
                        assert pid and kernel.GetExitCodeProcess(
                            handle, ctypes.byref(code)
                        )
                        assert code.value == 259
                        assert kernel.IsProcessInJob(
                            handle, direct_handle[1], ctypes.byref(member)
                        )
                        assert member.value
                        reached.append(
                            {
                                "pid": pid,
                                "handle": int(handle),
                                "operation": "GetProcessTimes",
                                "native_error": 5,
                                "exit_code_before_failure": code.value,
                                "owned_job_member": bool(member.value),
                                "assigned_handle": direct_handle[0],
                            }
                        )
                        ctypes.set_last_error(5)
                        return 0
                    return direct_times(handle, *values)

                dll.GetProcessTimes = unavailable_direct_times
            if (
                census_unavailable
                or creation_unavailable
                or image_unavailable
                or membership_fault
            ):
                query = dll.QueryInformationJobObject
                query.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_int,
                    ctypes.c_void_p,
                    ctypes.c_ulong,
                    ctypes.c_void_p,
                ]
                query.restype = ctypes.c_int

                def retain_census_job(job, kind, buffer, size, returned):
                    value = query(job, kind, buffer, size, returned)
                    if value and kind == 3:
                        count = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ulong))[1]
                        assert count <= 16
                        assert size >= 8 + count * ctypes.sizeof(ctypes.c_size_t)
                        members = ctypes.cast(
                            ctypes.cast(buffer, ctypes.c_void_p).value + 8,
                            ctypes.POINTER(ctypes.c_size_t),
                        )[:count]
                        census_job[:] = [int(job), tuple(members)]
                    return value

                dll.QueryInformationJobObject = retain_census_job
                open_process = dll.OpenProcess
                open_process.argtypes = kernel.OpenProcess.argtypes
                open_process.restype = ctypes.c_void_p

                def unavailable_open(access, inherit, pid):
                    if not reached and not marker.exists():
                        events_path = attempt / "observer" / "events.jsonl"
                        if events_path.exists():
                            assert events_path.stat().st_size <= 128 * 1024
                            events = [
                                json.loads(line)
                                for line in events_path.read_text().splitlines()
                            ]
                            if any(
                                event["event"] == "command_register" for event in events
                            ):
                                # First census discovery can precede the child's
                                # marker write. Await that event before deciding
                                # whether this PID is the selected descendant.
                                deadline = time.monotonic() + 0.5
                                while (
                                    not marker.exists() and time.monotonic() < deadline
                                ):
                                    time.sleep(0.005)
                    if not reached and marker.exists():
                        assert marker.stat().st_size <= 64
                        target = json.loads(marker.read_text())["pid"]
                        if pid == target:
                            assert census_job
                            assert target in census_job[1]
                            proof_handle = kernel.OpenProcess(access, inherit, pid)
                            assert proof_handle
                            proof_handles.append(int(proof_handle))
                            try:
                                assert kernel.GetProcessId(proof_handle) == target
                                code, member = ctypes.c_ulong(), ctypes.c_int()
                                assert kernel.GetExitCodeProcess(
                                    proof_handle, ctypes.byref(code)
                                )
                                assert code.value == 259
                                assert kernel.IsProcessInJob(
                                    proof_handle, census_job[0], ctypes.byref(member)
                                )
                                assert member.value
                            finally:
                                assert kernel.CloseHandle(proof_handle)
                                closed_proof_handles.append(int(proof_handle))
                            if (
                                creation_unavailable
                                or image_unavailable
                                or membership_fault
                            ):
                                handle = open_process(access, inherit, pid)
                                assert handle
                                selected_census_handle[:] = [int(handle), pid]
                                selected_census_lifetime_active[:] = [True]
                                return handle
                            reached.append(
                                {
                                    "pid": target,
                                    "handle": int(proof_handle),
                                    "operation": "OpenProcess",
                                    "native_error": 5,
                                    "observed_at": time.monotonic(),
                                    "exit_code_before_failure": code.value,
                                    "census_job": census_job[0],
                                    "owned_job_member": bool(member.value),
                                    "temporary_handles_opened": len(proof_handles),
                                    "temporary_handles_closed": len(
                                        closed_proof_handles
                                    ),
                                }
                            )
                            release.write_text("continue\n")
                            ctypes.set_last_error(5)
                            return 0
                    handle = open_process(access, inherit, pid)
                    if (
                        handle
                        and selected_census_handle
                        and int(handle) == selected_census_handle[0]
                    ):
                        selected_census_lifetime_active[:] = [False]
                    return handle

                dll.OpenProcess = unavailable_open
                if creation_unavailable or image_unavailable or membership_fault:
                    if membership_fault:
                        membership = dll.IsProcessInJob
                        membership.argtypes = kernel.IsProcessInJob.argtypes
                        membership.restype = ctypes.c_int

                        def unavailable_membership(handle, job, member):
                            if (
                                not reached
                                and selected_census_handle
                                and int(handle) == selected_census_handle[0]
                                and kernel.GetProcessId(handle)
                                == selected_census_handle[1]
                            ):
                                actual, code = ctypes.c_int(), ctypes.c_ulong()
                                assert kernel.GetExitCodeProcess(
                                    handle, ctypes.byref(code)
                                )
                                assert code.value == 259
                                assert kernel.IsProcessInJob(
                                    handle, job, ctypes.byref(actual)
                                )
                                assert actual.value
                                reached.append(
                                    {
                                        "pid": selected_census_handle[1],
                                        "handle": int(handle),
                                        "operation": "IsProcessInJob",
                                        "native_error": 5
                                        if fault == "membership-error"
                                        else 0,
                                        "exit_code_before_failure": code.value,
                                        "owned_job_member": bool(actual.value),
                                        "injected_return": 0
                                        if fault == "membership-error"
                                        else 1,
                                        "injected_member": None
                                        if fault == "membership-error"
                                        else False,
                                    }
                                )
                                release.write_text("continue\n")
                                if fault == "membership-error":
                                    ctypes.set_last_error(5)
                                    return 0
                                ctypes.cast(member, ctypes.POINTER(ctypes.c_int))[0] = 0
                                return 1
                            return membership(handle, job, member)

                        dll.IsProcessInJob = unavailable_membership
                    times = dll.GetProcessTimes
                    times.argtypes = [ctypes.c_void_p] * 5
                    times.restype = ctypes.c_int

                    def unavailable_times(handle, *values):
                        if image_unavailable:
                            value = times(handle, *values)
                            if (
                                value
                                and not reached
                                and selected_census_handle
                                and int(handle) == selected_census_handle[0]
                                and kernel.GetProcessId(handle)
                                == selected_census_handle[1]
                            ):
                                selected_times_success.append(int(handle))
                            return value
                        if (
                            not reached
                            and selected_census_handle
                            and int(handle) == selected_census_handle[0]
                            and kernel.GetProcessId(handle) == selected_census_handle[1]
                        ):
                            code, member = ctypes.c_ulong(), ctypes.c_int()
                            assert kernel.GetExitCodeProcess(handle, ctypes.byref(code))
                            assert code.value == 259
                            assert kernel.IsProcessInJob(
                                handle, census_job[0], ctypes.byref(member)
                            )
                            assert member.value
                            reached.append(
                                {
                                    "pid": selected_census_handle[1],
                                    "handle": int(handle),
                                    "operation": "GetProcessTimes",
                                    "native_error": 5,
                                    "observed_at": time.monotonic(),
                                    "exit_code_before_failure": code.value,
                                    "census_job": census_job[0],
                                    "owned_job_member": bool(member.value),
                                    "temporary_handles_opened": len(proof_handles),
                                    "temporary_handles_closed": len(
                                        closed_proof_handles
                                    ),
                                }
                            )
                            release.write_text("continue\n")
                            ctypes.set_last_error(5)
                            return 0
                        return times(handle, *values)

                    dll.GetProcessTimes = unavailable_times
                    if image_unavailable:
                        image = dll.QueryFullProcessImageNameW
                        image.argtypes = [
                            ctypes.c_void_p,
                            ctypes.c_ulong,
                            ctypes.c_wchar_p,
                            ctypes.POINTER(ctypes.c_ulong),
                        ]
                        image.restype = ctypes.c_int

                        def unavailable_image(handle, flags, buffer, size):
                            if (
                                not reached
                                and selected_census_handle
                                and int(handle) == selected_census_handle[0]
                                and kernel.GetProcessId(handle)
                                == selected_census_handle[1]
                            ):
                                assert selected_times_success == [int(handle)]
                                code, member = ctypes.c_ulong(), ctypes.c_int()
                                assert kernel.GetExitCodeProcess(
                                    handle, ctypes.byref(code)
                                )
                                assert code.value == 259
                                assert kernel.IsProcessInJob(
                                    handle, census_job[0], ctypes.byref(member)
                                )
                                assert member.value
                                reached.append(
                                    {
                                        "pid": selected_census_handle[1],
                                        "handle": int(handle),
                                        "operation": "QueryFullProcessImageNameW",
                                        "native_error": 5,
                                        "observed_at": time.monotonic(),
                                        "exit_code_before_failure": code.value,
                                        "census_job": census_job[0],
                                        "owned_job_member": bool(member.value),
                                        "temporary_handles_opened": len(proof_handles),
                                        "temporary_handles_closed": len(
                                            closed_proof_handles
                                        ),
                                        "get_process_times_succeeded": True,
                                    }
                                )
                                release.write_text("continue\n")
                                ctypes.set_last_error(5)
                                return 0
                            return image(handle, flags, buffer, size)

                        dll.QueryFullProcessImageNameW = unavailable_image
                    close = dll.CloseHandle
                    close.argtypes = kernel.CloseHandle.argtypes
                    close.restype = ctypes.c_int

                    def retain_census_close(handle):
                        value = close(handle)
                        if (
                            selected_census_handle
                            and int(handle) == selected_census_handle[0]
                            and selected_census_lifetime_active[0]
                        ):
                            attempt_row = {
                                "handle": int(handle),
                                "success": bool(value),
                                "native_error": 0 if value else ctypes.get_last_error(),
                            }
                            if fault == "census-close-error" and reached:
                                attempt_row.update(
                                    actual_success=bool(value),
                                    injected_return=False,
                                    injected_error=6,
                                )
                            census_close_attempts.append(attempt_row)
                            if value:
                                closed_census_handles.append(int(handle))
                            if reached:
                                reached[0]["census_handle_close_count"] = len(
                                    closed_census_handles
                                )
                                reached[0]["census_handle_close_attempts"] = list(
                                    census_close_attempts
                                )
                            if fault == "census-close-error" and reached:
                                ctypes.set_last_error(6)
                                return 0
                        return value

                    dll.CloseHandle = retain_census_close
            exit_read = dll.GetExitCodeProcess
            exit_read.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            exit_read.restype = ctypes.c_int

            def exit_then_release(handle, code):
                value = exit_read(handle, code)
                if (
                    not (
                        census_unavailable
                        or creation_unavailable
                        or image_unavailable
                        or membership_fault
                        or fatal
                    )
                    and reached
                    and not release.exists()
                    and kernel.GetProcessId(handle) == reached[0]["pid"]
                    and int(handle) == reached[0]["handle"]
                ):
                    assert value
                    assert ctypes.cast(code, ctypes.POINTER(ctypes.c_ulong))[0] == 259
                    if exit_unavailable:
                        reached[0]["exit_failure"] = {
                            "pid": kernel.GetProcessId(handle),
                            "handle": int(handle),
                            "operation": "GetExitCodeProcess",
                            "native_error": 6,
                            "observed_at": time.monotonic(),
                        }
                    release.write_text("continue\n")
                    if exit_unavailable:
                        ctypes.set_last_error(6)
                        return 0
                return value

            dll.GetExitCodeProcess = exit_then_release
        if name == "psapi":
            read = dll.GetProcessMemoryInfo
            read.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]

            def unavailable(handle, counters, size):
                if (
                    not (
                        census_unavailable
                        or creation_unavailable
                        or image_unavailable
                        or membership_fault
                        or fatal
                    )
                    and not reached
                    and marker.exists()
                ):
                    assert marker.stat().st_size <= 64
                    target = json.loads(marker.read_text())["pid"]
                    if kernel.GetProcessId(handle) == target:
                        code = ctypes.c_ulong()
                        assert kernel.GetExitCodeProcess(handle, ctypes.byref(code))
                        assert code.value == 259
                        reached.append(
                            {
                                "pid": target,
                                "handle": int(handle),
                                "operation": "GetProcessMemoryInfo",
                                "native_error": 5,
                                "observed_at": time.monotonic(),
                                "exit_code_before_failure": code.value,
                            }
                        )
                        # Release follows the observer's real exit-status read,
                        # so a live gap cannot race into an exited gap.
                        ctypes.set_last_error(5)
                        return 0
                return read(handle, counters, size)

            dll.GetProcessMemoryInfo = unavailable
        return dll

    descendant = """import json,os,sys,time
from pathlib import Path
marker,release=map(Path,sys.argv[1:])
temporary=marker.with_suffix('.pending')
temporary.write_text(json.dumps(dict(pid=os.getpid())))
os.replace(temporary,marker)
deadline=time.monotonic()+1.5
while not release.exists():
 if time.monotonic()>=deadline:
  raise TimeoutError('Optional memory operation was not reached')
 time.sleep(0.005)
"""
    command = (
        "import subprocess,sys\n"
        f"subprocess.run([sys._base_executable,'-c',{descendant!r},"
        f"{str(marker)!r},{str(release)!r}],check=True,timeout=2,"
        "creationflags=subprocess.CREATE_NO_WINDOW)\n"
    )
    driver = (
        "import importlib.util,json,os,sys\n"
        "from pathlib import Path\n"
        "from tests.support.git_resource_pilot import measured_calls\n"
        "from brz2obsidian.publication import git_read\n"
        "def exchange(value,expected):\n"
        " print(json.dumps(value),flush=True)\n"
        " assert sys.stdin.readline(65)==expected+'\\n'\n"
        "exchange(dict(event='hello',pid=os.getpid(),executable=sys.executable,"
        "base_executable=sys._base_executable,prefix=sys.prefix,"
        "base_prefix=sys.base_prefix,version=sys.version,origins=["
        "importlib.util.find_spec(name).origin for name in "
        "('brz2obsidian','tests.support.resource_pilot','pydantic')]),'ready')\n"
        f"with measured_calls(attempt=Path({str(attempt)!r})):\n"
        f" result=git_read.read_git([sys._base_executable,'-c',{command!r}],"
        "env=os.environ.copy(),timeout=2)\n"
        " assert result.returncode==0,(result.returncode,result.stderr)\n"
        "exchange(dict(event='done',pid=os.getpid(),ok=True),'continue')\n"
    )
    monkeypatch.setattr(ctypes, "WinDLL", load)
    result = observe_commands(
        [sys.executable, "-c", driver],
        attempt / "observer",
        artifact_limit=4 * 1024 * 1024 + 512 * 1024,
        bootstrap={
            "lifetimes": 2,
            "images": [
                sys._base_executable,
                str(Path(os.environ["SystemRoot"]) / "System32" / "conhost.exe"),
            ],
        },
        work_timeout=8,
    )
    (attempt / "memory-gap-witness.json").write_text(json.dumps(reached))

    assert len(reached) == 1, result
    witness = reached[0]
    assert witness["exit_code_before_failure"] == 259
    if fatal:
        assert witness["owned_job_member"] is True
        assert result["status"] == "failed", result
        assert result["command_family_coverage"] == "incomplete"
        assert result["final_job"] is not None
        assert result["final_job"]["ActiveProcesses"] == 0
        assert json.loads((attempt / "observer" / "report.json").read_text()) == result
        events_path = attempt / "observer" / "events.jsonl"
        events = (
            [json.loads(line) for line in events_path.read_text().splitlines()]
            if events_path.exists()
            else []
        )
        assert not any(event["event"] == "done" for event in events)
        if fault == "direct-times-error":
            assert witness["operation"] == "GetProcessTimes"
            assert witness["native_error"] == 5
            assert witness["handle"] == witness["assigned_handle"] == direct_handle[0]
            assert str(ctypes.WinError(5)) in result["error"]
            assert not any(
                event["event"] in ("hello", "command_register") for event in events
            )
        else:
            assert release.read_text() == "continue\n"
            assert proof_handles == closed_proof_handles and len(proof_handles) == 1
            assert closed_census_handles == [witness["handle"]]
            attempts = witness["census_handle_close_attempts"]
            assert witness["census_handle_close_count"] == 1
            assert len(attempts) == 1 and attempts[0]["handle"] == witness["handle"]
            assert attempts[0]["success"] is True
            if fault == "census-close-error":
                assert witness["operation"] == "GetProcessTimes"
                assert witness["native_error"] == 5
                assert attempts[0]["actual_success"] is True
                assert attempts[0]["injected_return"] is False
                assert attempts[0]["injected_error"] == 6
                assert str(ctypes.WinError(6)) in result["error"]
                frames_path = attempt / "observer" / "frames.jsonl"
                frames = (
                    [json.loads(line) for line in frames_path.read_text().splitlines()]
                    if frames_path.exists()
                    else []
                )
                assert not any(
                    gap["pid"] == witness["pid"]
                    for frame in frames
                    for gap in frame["missing_processes"]
                )
            else:
                assert witness["operation"] == "IsProcessInJob"
                assert witness["injected_return"] == (
                    0 if fault == "membership-error" else 1
                )
                if fault == "membership-error":
                    assert witness["native_error"] == 5
                    assert str(ctypes.WinError(5)) in result["error"]
                else:
                    assert witness["injected_member"] is False
                    assert "Process is not in the owned job" in result["error"]
        return
    assert release.read_text() == "continue\n"
    if census_unavailable:
        assert witness["operation"] == "OpenProcess"
        assert witness["native_error"] == 5
        assert witness["owned_job_member"] is True
        assert witness["temporary_handles_opened"] == 1
        assert witness["temporary_handles_closed"] == 1
        assert proof_handles == closed_proof_handles == [witness["handle"]]
    if creation_unavailable or image_unavailable:
        assert witness["operation"] == (
            "QueryFullProcessImageNameW" if image_unavailable else "GetProcessTimes"
        )
        if image_unavailable:
            assert witness["get_process_times_succeeded"] is True
            assert selected_times_success == [witness["handle"]]
        assert witness["native_error"] == 5
        assert witness["owned_job_member"] is True
        assert witness["temporary_handles_opened"] == 1
        assert witness["temporary_handles_closed"] == 1
        assert proof_handles == closed_proof_handles
        assert closed_census_handles == [witness["handle"]]
        assert witness["census_handle_close_count"] == 1
        assert witness["census_handle_close_attempts"] == [
            {"handle": witness["handle"], "success": True, "native_error": 0}
        ]
    if exit_unavailable:
        exit_witness = witness["exit_failure"]
        assert exit_witness["pid"] == witness["pid"]
        assert exit_witness["handle"] == witness["handle"]
        assert exit_witness["operation"] == "GetExitCodeProcess"
        assert exit_witness["native_error"] == 6
        assert exit_witness["observed_at"] >= witness["observed_at"]
    assert result["status"] == "completed", result
    assert result["command_family_coverage"] == "complete"
    assert result["individual_sampling_policy"] == "regular"
    assert result["final_job"]["ActiveProcesses"] == 0
    assert result["cleanup_errors"] == []
    assert result["proof_handles_remaining"] == 0
    assert result["measurement_handles_remaining"] == 0
    assert result["handle_close_duplicates"] == 0
    assert result["outer_termination_calls"] == 0
    assert result["census"]["bootstrap_lifetimes"] == 2
    assert result["census"]["command_lifetimes"] >= 2
    assert result["census"]["unaccounted_lifetimes"] == 0
    commands = [row for row in result["inventory"] if row["kind"] == "command"]
    assert len(commands) == 1
    assert commands[0]["state"] == "finalized"
    assert commands[0]["normal_cleanup_complete"] is True
    assert commands[0]["final_job"]["TotalProcesses"] >= 2
    assert commands[0]["final_job"]["ActiveProcesses"] == 0
    assert commands[0]["individual_sampling"]["omitted_interval_seconds"] == 0
    if not (census_unavailable or creation_unavailable or image_unavailable):
        identity = next(
            row for row in result["inventory"] if row.get("pid") == witness["pid"]
        )
        assert identity["origin"] == "job-census"
        assert identity["creation_filetime_100ns"] > 0
        assert identity["handle_retained"] is True
    frames = [
        json.loads(line)
        for line in (attempt / "observer" / "frames.jsonl").read_text().splitlines()
    ]
    assert result["exited_counter_gap_observations"] == sum(
        gap["exited"] is True for frame in frames for gap in frame["missing_processes"]
    )
    frame, gap = next(
        (frame, gap)
        for frame in frames
        for gap in frame["missing_processes"]
        if gap["pid"] == witness["pid"]
    )
    assert gap["operation"] == witness["operation"]
    assert gap["native_error"] == witness["native_error"]
    assert gap["error"] == str(ctypes.WinError(5))
    if census_unavailable or creation_unavailable or image_unavailable:
        assert gap["exited"] is None
        assert gap["identity_unavailable"] is True
        assert "creation_filetime_100ns" not in gap
        assert "image" not in gap
        assert "exit_error" not in gap
    elif exit_unavailable:
        assert gap["exited"] is None
        exit_error = gap["exit_error"]
        assert exit_error["operation"] == exit_witness["operation"]
        assert exit_error["native_error"] == exit_witness["native_error"]
        assert exit_error["error"] == str(ctypes.WinError(6))
        assert (
            exit_witness["observed_at"]
            <= exit_error["observed_at"]
            <= frame["sample_finished"]
        )
    else:
        assert gap["exited"] is False
        assert "exit_error" not in gap
    assert witness["observed_at"] <= gap["observed_at"] <= frame["sample_finished"]
    assert frame["sampled_family_private_bytes_complete"] is False
    assert frame["sampled_family_working_set_bytes_complete"] is False
    assert all(row["pid"] != witness["pid"] for row in frame["processes"])
    assert frame["sampled_family_private_bytes"] == sum(
        row["PrivateUsage"] for row in frame["processes"]
    )
    assert frame["sampled_family_working_set_bytes"] == sum(
        row["WorkingSetSize"] for row in frame["processes"]
    )
    events = [
        json.loads(line)
        for line in (attempt / "observer" / "events.jsonl").read_text().splitlines()
    ]
    driver_pid = next(event["pid"] for event in events if event["event"] == "hello")
    assert any(row["pid"] == driver_pid for row in frame["processes"])
    assert frame["job"]["PeakJobMemoryUsed"] > 0
    assert not frame.get("individual_samples_omitted", False)
    assert json.loads((attempt / "observer" / "report.json").read_text()) == result


@pytest.mark.parametrize(
    "mode", ["malformed", "incomplete", "overflow", "missing-attribution"]
)
def test_incomplete_or_unattributed_protocol_retains_failed_control(mode):
    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    result = observe(
        [
            sys.executable,
            str(ROOT / "tests/local_acceptance/resource_calibration.py"),
            mode,
        ],
        output,
    )

    assert result["status"] == "failed"
    assert result["error"]
    assert result["final_job"]["ActiveProcesses"] == 0
    assert result["cleanup_errors"] == []
    if mode != "incomplete":
        assert (output / "protocol.bin").stat().st_size > 0


def test_artifact_budget_stops_owned_family_before_exceeding_disk_cap():
    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    result = observe(
        [
            sys.executable,
            str(ROOT / "tests/local_acceptance/resource_calibration.py"),
            "timeout",
        ],
        output,
        timeout=5,
        artifact_limit=256 * 1024,
    )

    assert result["status"] == "failed"
    assert "artifact budget" in result["error"]
    assert result["final_job"]["ActiveProcesses"] == 0
    assert sum(path.stat().st_size for path in output.iterdir()) <= 256 * 1024


def test_job_assignment_refusal_never_resumes_the_synthetic_command(monkeypatch):
    original = ctypes.WinDLL

    def load(name, *args, **kwargs):
        dll = original(name, *args, **kwargs)
        if name == "kernel32":

            def refuse(job, process):
                ctypes.set_last_error(5)
                return 0

            dll.AssignProcessToJobObject = refuse
        return dll

    monkeypatch.setattr(ctypes, "WinDLL", load)
    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    result = observe(
        [
            sys.executable,
            str(ROOT / "tests/local_acceptance/resource_calibration.py"),
            "normal",
        ],
        output,
    )

    assert result["status"] == "failed"
    assert result["final_job"]["TotalProcesses"] == 0
    assert result["final_job"]["ActiveProcesses"] == 0
    assert result["observed_pids"] == []
    assert not (output / "protocol.bin").exists()


def test_nested_terminal_metadata_cannot_escape_aggregate_artifact_budget():
    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    result = observe(
        [
            sys.executable,
            str(ROOT / "tests/local_acceptance/resource_calibration.py"),
            "nested-done",
        ],
        output,
        artifact_limit=262144,
    )

    assert sum(path.stat().st_size for path in output.iterdir()) <= 262144
    assert result["status"] == "failed"
    assert result["error"] == "Unsupported calibration event fields"
    assert result["final_job"]["ActiveProcesses"] == 0
    assert b'"extra": [' in (output / "protocol.bin").read_bytes()
    assert json.loads((output / "report.json").read_text()) == result


def test_phase_observer_records_more_than_sixteen_lifetime_children():
    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    driver = """import json,os,subprocess,sys
def event(**value):
 print(json.dumps(dict(pid=os.getpid(),**value)),flush=True)
 assert sys.stdin.readline()=='continue\\n'
event(event='phase',name='ready')
for _ in range(17):
 subprocess.run([sys.executable,'-c','pass'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
event(event='phase',name='work')
event(event='done',ok=True)
"""
    result = observe_phases(
        [sys.executable, "-c", driver],
        output,
        phases=("ready", "work"),
        work_timeout=10,
    )

    assert result["status"] == "completed", result
    assert result["phases"] == ["ready", "work"]
    assert result["final_job"]["TotalProcesses"] > 17
    assert result["final_job"]["ActiveProcesses"] == 0
    assert result["final_job"]["ActiveProcessLimit"] == 16
    assert result["final_job"]["JobMemoryLimit"] == 2 * 1024 * 1024 * 1024
    assert result["limits"]["lifetime_processes"] == 512
    assert result["per_git_lifetime_attribution"] == "unqualified"
    assert json.loads((output / "report.json").read_text()) == result


@pytest.mark.parametrize(
    "fault",
    [
        "order",
        "extra",
        "nested",
        "foreign",
        "incomplete",
        "early-done",
        "nontrue-done",
        "duplicate-done",
    ],
)
def test_phase_protocol_refuses_untrusted_or_incomplete_boundaries(fault):
    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    event = {"event": "phase", "name": "ready"}
    if fault == "order":
        event["name"] = "later"
    elif fault == "extra":
        event["extra"] = ["unsupported"]
    elif fault == "nested":
        event["name"] = {"nested": "ready"}
    elif fault == "early-done":
        event = {"event": "done", "ok": True}
    driver = (
        "import json,os,sys\n"
        f"event=json.loads({json.dumps(event)!r})\n"
        f"event['pid']={os.getpid() if fault == 'foreign' else 'os.getpid()'}\n"
        "print(json.dumps(event),flush=True)\n"
        "sys.stdin.readline()\n"
    )
    if fault in {"nontrue-done", "duplicate-done"}:
        done_ok = "1" if fault == "nontrue-done" else "True"
        driver += (
            f"done=dict(event='done',pid=os.getpid(),ok={done_ok})\n"
            "print(json.dumps(done),flush=True)\n"
            "sys.stdin.readline()\n"
        )
        if fault == "duplicate-done":
            driver += "print(json.dumps(done),flush=True)\nsys.stdin.readline()\n"
    result = observe_phases(
        [sys.executable, "-c", driver], output, phases=("ready",), work_timeout=5
    )

    assert result["status"] == "failed", result
    assert result["final_job"]["ActiveProcesses"] == 0
    assert (output / "protocol.bin").stat().st_size > 0
    if fault in {"early-done", "nontrue-done"}:
        assert result["error"] == "Incomplete phase terminal outcome"
    elif fault == "duplicate-done":
        assert result["error"] == "Malformed phase event"


def test_phase_timeout_cleans_the_owned_family():
    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    driver = """import json,os,sys,time
print(json.dumps(dict(event='phase',name='ready',pid=os.getpid())),flush=True)
sys.stdin.readline()
time.sleep(30)
"""
    result = observe_phases(
        [sys.executable, "-c", driver], output, phases=("ready",), work_timeout=1
    )

    assert result["status"] == "timeout"
    assert result["final_job"]["ActiveProcesses"] == 0
    assert result["elapsed_seconds"] < 5


@pytest.mark.parametrize(
    "phases",
    [[], (), ("same", "same"), ("é",), ("x" * 33,), tuple(str(i) for i in range(17))],
)
def test_invalid_phase_declarations_refuse_before_artifacts(phases):
    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    with pytest.raises(ValueError, match="phase declaration"):
        observe_phases([sys.executable], output, phases=phases)
    assert not output.exists()
