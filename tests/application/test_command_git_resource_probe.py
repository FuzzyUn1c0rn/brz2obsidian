"""Qualify fresh command-family counters through the bounded observer API."""

import json
import sys
from pathlib import Path

import pytest

from tests.support.git_resource_pilot import control_preflight, finish_control
from tools import update_resource_probe

ROOT = Path(__file__).resolve().parents[2]
MIB = 1024 * 1024
REFUSALS = (
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
        bootstrap=manifest["bootstrap"],
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


@pytest.mark.parametrize("case", REFUSALS)
def test_command_job_refusals_preserve_cleanup_and_failure_evidence(case, request):
    try:
        attempt, manifest = control_preflight(case=case)
        result = update_resource_probe.observe_commands(
            [
                sys.executable,
                "-m",
                "tests.support.git_resource_pilot",
                "refusal",
                case,
                str(attempt),
            ],
            attempt / "observer",
            phases=(),
            work_timeout=manifest["time"]["work_seconds"],
            artifact_limit=manifest["artifacts"]["observer_bytes"] - 65536,
            fault=case,
            bootstrap=manifest["bootstrap"],
        )
        finish_control(attempt, manifest)
        assert result["status"] == (
            "timeout" if case == "outer_deadline" else "failed"
        ), result
        assert result["fault"] == case
        assert result["error"]
        assert result["elapsed_seconds"] <= manifest["time"]["work_seconds"] + 4
        assert result["final_job"]["ActiveProcesses"] == 0
        if case != "family_counter_unavailable":
            assert result["cleanup_errors"] == []
        assert result["command_family_coverage"] == "incomplete"
        assert result["outer_termination_calls"] <= 1
        assert result["handle_close_duplicates"] == 0
        assert result["measurement_handles_remaining"] == 0
        assert result["proof_handles_remaining"] == 0
        assert len(result["inventory"]) <= 512
        assert result["protocol_events"] <= 1553
        assert result["protocol_acks"] <= 1553
        calls = [row for row in result["inventory"] if "seq" in row]
        assert len(calls) == 1
        if case in ("constructor_partial", "measurement_assign", "product_assign"):
            boundary = json.loads((attempt / "fault-witness.json").read_text())
            assert boundary["boundary"] == case
            assert boundary["native_result"] is False
            assert boundary["native_error"] > 0
            original = json.loads((attempt / "original-exception.json").read_text())
            assert original["type"] == "OSError"
            assert original["message"]
        else:
            assert result["fault_reached"] is True
        trace = (attempt / "resume-trace.jsonl").read_bytes()
        if case in (
            "constructor_partial",
            "measurement_assign",
            "product_assign",
            "duplicate_measurement",
            "duplicate_creation",
            "registration_ack_lost",
            "family_counter_unavailable",
            "driver_killed_after_registration",
            "outer_deadline",
            "terminal_reserve_exhausted",
        ):
            # The write-ahead witness surrounds the actual native ResumeThread
            # call. An accidental early resume therefore cannot hide behind a
            # missing ACK or the command's failure to emit application output.
            assert trace == b""
        else:
            resumed = [json.loads(line) for line in trace.splitlines()]
            assert len(resumed) == 1
            assert resumed[0]["seq"] == 1
            assert resumed[0]["event"] == "native_resume_attempt"
        if case == "constructor_partial":
            assert result["final_job"]["TotalProcesses"] == 2
            assert calls[0]["state"] == "finalized"
            assert calls[0]["return_status"] == "not_created"
            assert calls[0]["normal_cleanup_complete"] is True
            ownership = json.loads((attempt / "driver-ownership.json").read_text())
            assert ownership == {
                "measurement_opened": 1,
                "measurement_closed": 1,
                "product_opened": 1,
                "product_closed": 1,
                "product_close_duplicates": 0,
            }
        elif case in ("duplicate_return", "command_census_bypass"):
            assert calls[0]["state"] == "finalized"
            assert calls[0]["final_job"]["ActiveProcesses"] == 0
            assert calls[0]["normal_cleanup_complete"] is True
        else:
            assert calls[0]["state"] in ("aborted", "incomplete")
            assert calls[0]["normal_cleanup_complete"] is False
        if case == "family_counter_unavailable":
            assert calls[0]["counter_error"]
            assert result["cleanup_errors"] == [calls[0]["counter_error"]]
        if case == "outer_deadline":
            boundary = json.loads((attempt / "fault-witness.json").read_text())
            assert boundary["boundary"] == case
            assert boundary["registration_acknowledged"] is True
        if case == "command_census_bypass":
            assert result["census"]["unaccounted_lifetimes"] > 0
        assert json.loads((attempt / "observer" / "report.json").read_text()) == result
    except BaseException:
        request.session.shouldstop = "Unexpected command refusal outcome; Root assessment required"
        raise
