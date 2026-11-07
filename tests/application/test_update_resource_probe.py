"""Qualify the owned observer with independently specified Windows allocations."""

import ctypes
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from tools.update_resource_probe import observe

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

            # The external Win32 API is unavailable once for a live owned child.
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
