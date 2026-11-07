"""One16MiB public capture/admission/transport observation, without saved review."""

import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from tests.support.resource_pilot import PHASES
from tools.update_resource_probe import observe_phases

ROOT = Path(__file__).resolve().parents[2]


def test_driver_evidence_reserves_failure_record_within_aggregate_cap():
    from tests.support.resource_pilot import Evidence

    output = ROOT / "tmp" / "resource-probe" / uuid4().hex
    output.mkdir(parents=True)
    writer = Evidence(limit=128, terminal_reserve=64)
    writer.write(output / "first.json", {"note": "a" * 30})
    with pytest.raises(OSError, match="aggregate"):
        writer.write(output / "overflow.json", {"note": "b" * 30})
    writer.write(output / "failure.json", {"status": "failed"}, terminal=True)

    assert not (output / "overflow.json").exists()
    assert json.loads((output / "failure.json").read_text()) == {"status": "failed"}
    assert sum(path.stat().st_size for path in output.iterdir()) <= 128
    with pytest.raises(OSError, match="1 MiB"):
        Evidence().write(output / "large.json", {"value": "x" * 1048576})
    assert not (output / "large.json").exists()


def test_public_sixteen_mib_capture_and_admitted_content_pilot():
    namespace = ROOT / "tmp" / "resource-pilot"
    ledger = os.environ.get("BRZ_RESOURCE_PILOT_LEDGER")
    if ledger:
        ledger_sha = os.environ["BRZ_RESOURCE_PILOT_LEDGER_SHA256"]
    else:
        namespace = namespace / uuid4().hex
        namespace.mkdir(parents=True)
        ledger = namespace / "context.json"
        data = {
            "roots": [],
            "prior_reserved_bytes": 0,
            "ledger_and_later_small_report_reserve_bytes": 16777216,
            "global_synthetic_cap_bytes": 4294967296,
            "phase_only_artifact_reserve_bytes": 268435456,
            "future_verifier_reserve_bytes": 1073741824,
            "allowed_runner_roots": [str(ROOT / "tmp" / "checks")],
            "allowed_future_artifact_roots": [
                {"path": str(namespace)},
                {"path": str(namespace / "verifier")},
            ],
        }
        raw = json.dumps(data).encode()
        ledger.write_bytes(raw)
        ledger_sha = hashlib.sha256(raw).hexdigest()
    evidence = namespace / uuid4().hex
    evidence.mkdir(parents=True)
    result = observe_phases(
        [
            sys.executable,
            "-m",
            "tests.support.resource_pilot",
            str(evidence),
            str(ledger),
            ledger_sha,
        ],
        evidence / "observer",
        phases=PHASES,
    )

    assert result["status"] == "completed", result
    assert result["final_job"]["ActiveProcesses"] == 0
    assert result["limits"]["artifact_bytes"] == 60 * 1024 * 1024
    artifact_bytes = sum(
        path.stat().st_size for path in evidence.rglob("*") if path.is_file()
    )
    assert artifact_bytes <= 64 * 1024 * 1024
    assert result["phases"] == [
        "setup",
        "inspect",
        "capture",
        "admission",
        "current",
        "retained",
        "pages",
        "stage_current",
        "stage_retained",
        "verify",
        "close",
        "preservation",
    ]
    facts = json.loads((evidence / "pilot.json").read_text())
    assert facts["status"] == "completed"
    assert facts["opaque_input_bytes"] == 16777216
    assert facts["payload_sha256"] == (
        "341aacac661ccb210720bedaa9ead5d668fe5ea41a73532fc147c71e34040df1"
    )
    assert facts["pages"] == ["ff000102", "fcfdfeff"] * 2
    assert facts["stages_verified"] == 2
    assert facts["stages_removed"] is True
    assert facts["saved_review_present"] is False
    assert facts["before"]["authored"] == facts["after"]["authored"]
    assert facts["before"]["head"] == facts["after"]["head"]
    assert facts["before"]["index"] == facts["after"]["index"]
    assert facts["before"]["user_refs"] == facts["after"]["user_refs"]
    assert facts["converter_refs_after_capture"] == facts["after"]["converter_refs"]
    assert Path(facts["root"]).is_relative_to(Path(facts["temp_base"]))
    assert not Path(facts["root"]).is_relative_to(ROOT)
