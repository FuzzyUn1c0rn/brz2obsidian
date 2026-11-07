"""Qualify fresh command-family counters through the bounded observer API."""

import json
import sys
from pathlib import Path

from tests.support.git_resource_pilot import control_preflight, finish_control
from tools import update_resource_probe

ROOT = Path(__file__).resolve().parents[2]
MIB = 1024 * 1024


def test_command_jobs_retain_short_descendant_peaks_after_exit():
    attempt, manifest = control_preflight()
    result = update_resource_probe.observe_commands(
        [
            sys.executable,
            "-m",
            "tests.support.git_resource_pilot",
            "peaks",
            str(attempt),
        ],
        attempt / "observer",
        phases=(),
        work_timeout=manifest["time"]["work_seconds"],
        artifact_limit=manifest["artifacts"]["observer_bytes"] - 65536,
        individual_samples="command-boundaries",
    )
    finish_control(attempt, manifest)

    assert result["status"] == "completed", result
    assert result["cleanup_errors"] == []
    assert result["final_job"]["ActiveProcesses"] == 0
    assert result["command_family_coverage"] == "complete"
    commands = [row for row in result["inventory"] if row["kind"] == "command"]
    assert len(commands) == 2
    witness = json.loads((attempt / "peaks.json").read_text())
    assert [row["requested_bytes"] for row in witness] == [32 * MIB, 8 * MIB]
    for row, proof in zip(commands, witness, strict=True):
        assert row["state"] == "finalized"
        assert row["return_status"] == "returned"
        assert row["normal_cleanup_complete"] is True
        assert row["final_job"]["ActiveProcesses"] == 0
        assert proof["committed_region_bytes"] >= proof["requested_bytes"]
        assert proof["child_held_private_bytes"] >= (
            proof["child_before_private_bytes"] + proof["requested_bytes"]
        )
        assert proof["child_held_private_bytes"] > proof["parent_private_bytes"]
        assert proof["released_before_parent_exit"] is True
        assert proof["child_alive_at_parent_exit"] is True
        assert row["final_job"]["PeakJobMemoryUsed"] >= (
            proof["child_held_private_bytes"] + proof["parent_private_bytes"]
        )
        assert row["final_job"]["PeakProcessMemoryUsed"] >= proof[
            "child_held_private_bytes"
        ]
        assert row["individual_sampling"]["mode"] == "command-boundaries"
        assert row["individual_sampling"]["omitted_interval_seconds"] > 0
    for counter in ("PeakJobMemoryUsed", "PeakProcessMemoryUsed"):
        assert commands[1]["final_job"][counter] < commands[0]["final_job"][counter]
        assert result["final_job"][counter] >= commands[0]["outer_at_return"][counter]
        assert commands[1]["outer_at_return"][counter] >= commands[0][
            "outer_at_return"
        ][counter]
    assert result["census"]["unaccounted_lifetimes"] == 0
    assert json.loads((attempt / "observer" / "report.json").read_text()) == result
