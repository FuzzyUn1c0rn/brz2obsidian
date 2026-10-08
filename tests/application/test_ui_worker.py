import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from brz2obsidian.application.contracts import InspectArguments, WorkerRequest


def test_real_hidden_worker_roundtrip_unicode_unrelated_working_directory(tmp_path):
    from brz2obsidian.application.transport import Supervisor

    source = tmp_path / "Été source.BRZ"
    source.write_bytes(
        (Path(__file__).parents[1] / "fixtures/minimal.brz").read_bytes()
    )
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="inspect",
        arguments=InspectArguments(source=str(source)),
    )
    terminal = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src").run(
        request
    )
    assert terminal.phase == "completed"
    assert terminal.process_status == 0
    assert terminal.response.request_id == request.request_id
    assert terminal.response.result.status == "inspection_clean"
    assert "Authored body" not in terminal.response.model_dump_json()


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_id",
        "wrong_operation",
        "wrong_schema",
        "wrong_version",
        "extra_field",
        "duplicate",
        "extra_json",
        "missing_newline",
        "missing_schema",
        "invalid_utf8",
        "bool_version",
        "negative_count",
        "wrong_status",
        "mutable_list",
        "failed_review",
    ],
)
def test_wire_rejects_untrustworthy_terminal_results(mutation):
    from brz2obsidian.application.contracts import WorkerResponse
    from brz2obsidian.application.operations import inspect
    from brz2obsidian.application.protocol import (
        ProtocolFailure,
        decode_response,
        encode_response,
    )

    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="inspect",
        arguments=InspectArguments(source=str(source)),
    )
    data = json.loads(
        encode_response(
            WorkerResponse(
                request_id=request.request_id,
                operation="inspect",
                result=inspect(source),
            )
        )
    )
    if mutation == "wrong_id":
        data["request_id"] = str(uuid4())
    elif mutation == "wrong_operation":
        data["operation"] = "check_vault"
    elif mutation == "wrong_schema":
        data["schema"] = "wrong"
    elif mutation == "wrong_version":
        data["schema_version"] = 2
    elif mutation == "extra_field":
        data["result"]["source_tree"] = {}
    elif mutation == "missing_schema":
        del data["schema"]
    elif mutation == "bool_version":
        data["schema_version"] = True
    elif mutation == "negative_count":
        data["result"]["counts"]["planned_notes"] = -1
    elif mutation == "wrong_status":
        data["result"]["status"] = "inspection_failed"
    elif mutation == "mutable_list":
        data["result"]["counts"]["planned_notes"] = []
    elif mutation == "failed_review":
        data["result"]["reviewed"]["outcome"] = "failed"
    wire = json.dumps(data).encode() + b"\n"
    if mutation == "duplicate":
        wire = wire.replace(
            b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1', 1
        )
    elif mutation == "extra_json":
        wire += b"{}\n"
    elif mutation == "missing_newline":
        wire = wire[:-1]
    elif mutation == "invalid_utf8":
        wire = b"\xff\n"
    with pytest.raises(ProtocolFailure):
        decode_response(wire, request)


@pytest.mark.parametrize(
    "behavior",
    [
        "crash",
        "missing",
        "oversized",
        "flood_stderr",
        "wrong_id",
        "missing_result_field",
    ],
)
def test_supervisor_drains_real_child_pipes_and_rejects_bad_results(
    tmp_path, monkeypatch, behavior
):
    from brz2obsidian.application.contracts import WorkerResponse
    from brz2obsidian.application.operations import inspect
    from brz2obsidian.application.protocol import RESPONSE_LIMIT, encode_response
    from brz2obsidian.application.transport import Supervisor

    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="inspect",
        arguments=InspectArguments(source=str(source)),
    )
    response = encode_response(
        WorkerResponse(
            request_id=str(uuid4()) if behavior == "wrong_id" else request.request_id,
            operation="inspect",
            result=inspect(source),
        )
    )
    if behavior == "missing_result_field":
        partial = json.loads(response)
        del partial["result"]["counts"]
        response = json.dumps(partial).encode() + b"\n"
    script = tmp_path / "controlled child.py"
    action = {
        "crash": "raise SystemExit(3)",
        "missing": "pass",
        "oversized": f"sys.stdout.buffer.write(b'x' * {RESPONSE_LIMIT + 1}); sys.stdout.buffer.flush()",
        "flood_stderr": f"sys.stderr.buffer.write(b'RAW_PRIVATE_CANARY' * 100000); sys.stderr.buffer.flush(); sys.stdout.buffer.write({response!r})",
        "wrong_id": f"sys.stdout.buffer.write({response!r})",
        "missing_result_field": f"sys.stdout.buffer.write({response!r})",
    }[behavior]
    script.write_text(
        "import sys\nsys.stdin.buffer.read()\n" + action, encoding="utf-8"
    )
    real_popen = subprocess.Popen
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda arguments, **kwargs: real_popen([arguments[0], str(script)], **kwargs),
    )
    terminal = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src").run(
        request
    )
    if behavior == "flood_stderr":
        assert terminal.phase == "completed"
        assert "RAW_PRIVATE_CANARY" not in repr(terminal)
    else:
        assert terminal.phase == "may_have_executed"
        assert terminal.response is None


def test_launch_failure_precedes_worker_execution(tmp_path):
    from brz2obsidian.application.transport import Supervisor

    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="inspect",
        arguments=InspectArguments(source=str(tmp_path / "source.brz")),
    )
    terminal = Supervisor(
        tmp_path / "absent-python.exe", Path(__file__).parents[2] / "src"
    ).run(request)
    assert terminal.phase == "not_started"
    assert terminal.code == "launch_failure"


@pytest.mark.parametrize(
    "control", ["bad_schema", "extra_argument", "extra_json", "oversized_request"]
)
def test_real_worker_rejects_invalid_requests_without_inspection_success(
    tmp_path, control
):
    from brz2obsidian.application.protocol import REQUEST_LIMIT, decode_response

    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="inspect",
        arguments=InspectArguments(source=str(tmp_path / "not-opened.brz")),
    )
    data = request.model_dump(by_alias=True)
    if control == "bad_schema":
        data["schema"] = "unsupported"
    elif control == "extra_argument":
        data["arguments"]["payload"] = "PRIVATE_CANARY"
    wire = json.dumps(data).encode() + b"\n"
    if control == "extra_json":
        wire += b"{}\n"
    elif control == "oversized_request":
        wire = b"x" * (REQUEST_LIMIT + 1)
    result = subprocess.run(
        [sys.executable, "-m", "brz2obsidian.worker"],
        input=wire,
        capture_output=True,
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == 1
    if control in ("bad_schema", "extra_argument"):
        response = decode_response(result.stdout, request)
        assert response.result is None
        assert response.protocol_error.code == "invalid_request"
    else:
        assert result.stdout == b""
    assert b"PRIVATE_CANARY" not in result.stderr + result.stdout


def test_real_warning_inspection_keeps_warning_semantics_and_readonly_inventory(
    tmp_path,
):
    from brz2obsidian.application.transport import Supervisor
    from tests.support.v3_collection import mixed_v3_archive

    source = mixed_v3_archive(tmp_path / "warning source.BRZ")
    before = {
        str(file.relative_to(tmp_path)): file.read_bytes()
        for file in tmp_path.rglob("*")
        if file.is_file()
    }
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="inspect",
        arguments=InspectArguments(source=str(source)),
    )
    terminal = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src").run(
        request
    )
    assert terminal.phase == "completed"
    assert terminal.process_status == 2
    assert terminal.response.result.status == "inspection_warnings"
    assert terminal.response.result.reviewed.outcome == "warnings"
    assert any(
        finding.code == "approved_source_gap"
        for finding in terminal.response.result.findings
    )
    assert {
        str(file.relative_to(tmp_path)): file.read_bytes()
        for file in tmp_path.rglob("*")
        if file.is_file()
    } == before


def test_response_limit_omission_preserves_authoritative_review_and_counts():
    from brz2obsidian.application.contracts import Finding, WorkerResponse
    from brz2obsidian.application.operations import inspect
    from brz2obsidian.application.protocol import (
        RESPONSE_LIMIT,
        decode_response,
        encode_response,
    )

    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="inspect",
        arguments=InspectArguments(source=str(source)),
    )
    original = inspect(source)
    huge = original.model_copy(
        update={
            "findings": (
                Finding(code="source_gap", severity="warning", message="Safe warning"),
            )
            * 120000,
            "diagnostic_text": "Safe diagnostic\n" * 2000000,
        }
    )
    wire = encode_response(
        WorkerResponse(request_id=request.request_id, operation="inspect", result=huge)
    )
    assert len(wire) <= RESPONSE_LIMIT
    result = decode_response(wire, request).result
    assert result.reviewed == original.reviewed
    assert result.counts == original.counts
    assert result.diagnostic_omission.findings_count == 120000
    assert "omitted" in result.diagnostic_text


@pytest.mark.parametrize(
    "field",
    [
        "counts",
        "findings",
        "field_errors",
        "reviewed",
        "publication",
        "destination",
        "checked",
        "pending",
        "review_required",
        "diagnostic_text",
        "diagnostic_omission",
    ],
)
def test_wire_never_invents_missing_minimum_safe_result_facts(field):
    from brz2obsidian.application.contracts import WorkerResponse
    from brz2obsidian.application.operations import inspect
    from brz2obsidian.application.protocol import (
        ProtocolFailure,
        decode_response,
        encode_response,
    )

    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="inspect",
        arguments=InspectArguments(source=str(source)),
    )
    data = json.loads(
        encode_response(
            WorkerResponse(
                request_id=request.request_id,
                operation="inspect",
                result=inspect(source),
            )
        )
    )
    del data["result"][field]
    with pytest.raises(ProtocolFailure):
        decode_response(json.dumps(data).encode() + b"\n", request)
