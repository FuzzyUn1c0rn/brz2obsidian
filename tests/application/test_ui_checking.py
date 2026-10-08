import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from brz2obsidian.application.operations import check_vault


def inventory(vault):
    return {
        path.relative_to(vault).as_posix(): path.read_bytes()
        if path.is_file()
        else None
        for path in vault.rglob("*")
    }


def test_public_check_returns_safe_clean_result_without_changing_vault(tmp_path):
    note = tmp_path / "Manual.md"
    note.write_text(
        "# Manual\nNOTE_BODY_CANARY\n[[Uncreated target]]\n", encoding="utf-8"
    )
    (tmp_path / "caller.bin").write_bytes(b"\x00\xffcaller bytes")
    (tmp_path / "empty caller folder").mkdir()
    before = inventory(tmp_path)

    result = check_vault(tmp_path)

    assert result.operation == "check_vault"
    assert result.status == "check_clean"
    assert result.outcome == "clean"
    assert result.reviewed is None and result.publication is None
    assert result.checked
    assert result.pending == ()
    assert result.counts.inventory_files == 2
    assert result.counts.markdown_files == result.counts.read_markdown_files == 1
    assert result.counts.base_files == result.counts.read_base_files == 0
    assert result.counts.category_notes == result.counts.imported_notes == 0
    assert "read-only" in result.diagnostic_text
    assert "NOTE_BODY_CANARY" not in result.model_dump_json()
    assert inventory(tmp_path) == before


@pytest.mark.parametrize(
    "state, expected_exit", [("clean", 0), ("issues", 2), ("failed", 1)]
)
def test_real_checker_worker_reports_check_outcomes_and_preserves_vault(
    tmp_path, state, expected_exit
):
    from brz2obsidian.application.contracts import CheckArguments, WorkerRequest
    from brz2obsidian.application.transport import Supervisor

    vault = tmp_path / "Été vault"
    if state != "failed":
        vault.mkdir()
        (vault / "Manual.md").write_text(
            "# NOTE_BODY_CANARY\n"
            + ("![[REFERENCE_FRAGMENT_CANARY.png]]\n" if state == "issues" else ""),
            encoding="utf-8",
        )
    before = inventory(tmp_path)
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="check_vault",
        arguments=CheckArguments(vault=str(vault)),
    )

    terminal = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src").run(
        request
    )

    assert terminal.phase == "completed"
    assert terminal.process_status == expected_exit
    assert terminal.response.result.status == "check_" + state
    assert terminal.response.result.operation == "check_vault"
    assert "REFERENCE_FRAGMENT_CANARY" not in terminal.response.model_dump_json()
    assert "NOTE_BODY_CANARY" not in terminal.response.model_dump_json()
    assert inventory(tmp_path) == before


def test_public_check_needs_neither_source_modules_nor_wiring_nor_qt(tmp_path):
    (tmp_path / "Manual.md").write_text("# Manual\n", encoding="utf-8")
    program = """
import importlib.abc, sys
class BlockUnrelated(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('PySide6', 'brz2obsidian_ui',
                                'brz2obsidian.sources',
                                'brz2obsidian.application.wiring')):
            raise ImportError('Unrelated imports are blocked')
sys.meta_path.insert(0, BlockUnrelated())
from pathlib import Path
from brz2obsidian.application.operations import check_vault
assert check_vault(Path(sys.argv[1])).status == 'check_clean'
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("kind", ["missing", "file", "unreadable_note"])
def test_check_failure_preserves_input_and_reports_vault_field_error(tmp_path, kind):
    vault = tmp_path / "selected"
    if kind == "file":
        vault.write_bytes(b"caller file")
    elif kind == "unreadable_note":
        vault.mkdir()
        (vault / "Unreadable.md").write_bytes(b"\xff\xfe\x80")
    before = inventory(tmp_path)

    result = check_vault(vault)

    assert result.status == "check_failed"
    assert result.outcome == "failed"
    assert result.field_errors[0].field == "vault"
    assert result.field_errors[0].code == "read_failure"
    assert "Check the path" in result.field_errors[0].message
    if kind != "unreadable_note":
        assert result.counts.inventory_files is None
        assert result.counts.markdown_files is None
        assert result.counts.category_notes is None
        assert result.counts.read_markdown_files == 0
    assert inventory(tmp_path) == before


def test_check_findings_keep_artifact_context_and_exclude_authored_references(tmp_path):
    note = tmp_path / "Manual.md"
    note.write_text(
        "---\ncategories: [123]\nicon: '[[REFERENCE_FRAGMENT_CANARY.png]]'\n---\n"
        "NOTE_BODY_CANARY\n",
        encoding="utf-8",
    )
    before = inventory(tmp_path)

    result = check_vault(tmp_path)

    assert result.status == "check_issues"
    assert {finding.code for finding in result.findings} == {
        "invalid_property",
        "missing_image",
    }
    assert all(finding.path == "Manual.md" for finding in result.findings)
    assert all(finding.field == "vault" for finding in result.findings)
    assert "Manual.md" in result.diagnostic_text
    assert "REFERENCE_FRAGMENT_CANARY" not in result.model_dump_json()
    assert "NOTE_BODY_CANARY" not in result.model_dump_json()
    assert inventory(tmp_path) == before


def test_failed_check_retains_each_finding_with_one_concise_vault_field_error(tmp_path):
    (tmp_path / "One.md").write_bytes(b"\xff\x80")
    (tmp_path / "Two.md").write_bytes(b"\xff\x80")

    result = check_vault(tmp_path)

    assert len(result.findings) == 2
    assert len(result.field_errors) == 1
    assert result.field_errors[0].field == "vault"


@pytest.mark.parametrize("state", ["clean", "missing"])
def test_checker_wire_roundtrip_retains_nullable_counts_distinct_from_migration(
    tmp_path, state
):
    from brz2obsidian.application.contracts import (
        CheckArguments,
        WorkerRequest,
        WorkerResponse,
    )
    from brz2obsidian.application.protocol import (
        ProtocolFailure,
        decode_response,
        encode_response,
    )

    vault = tmp_path if state == "clean" else tmp_path / "missing"
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="check_vault",
        arguments=CheckArguments(vault=str(vault)),
    )
    wire = encode_response(
        WorkerResponse(
            request_id=request.request_id,
            operation="check_vault",
            result=check_vault(vault),
        )
    )
    decoded = decode_response(wire, request).result
    assert decoded.counts.inventory_files == (0 if state == "clean" else None)
    assert decoded.counts.markdown_files == (0 if state == "clean" else None)
    assert decoded.counts.read_markdown_files == 0
    assert "actual_notes" not in decoded.counts.model_dump()
    for field, value in (
        ("inventory_files", -1),
        ("inventory_files", "1"),
        ("read_markdown_files", True),
        ("planned_notes", 1),
        ("note_bodies", []),
    ):
        malformed = json.loads(wire)
        malformed["result"]["counts"][field] = value
        with pytest.raises(ProtocolFailure):
            decode_response(json.dumps(malformed).encode("utf-8") + b"\n", request)


@pytest.mark.parametrize("control", ["crash", "bad_counts", "wrong_id"])
def test_checker_request_rejects_real_child_protocol_and_crash_failures(
    tmp_path, monkeypatch, control
):
    from brz2obsidian.application.contracts import (
        CheckArguments,
        WorkerRequest,
        WorkerResponse,
    )
    from brz2obsidian.application.protocol import encode_response
    from brz2obsidian.application.transport import Supervisor

    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="check_vault",
        arguments=CheckArguments(vault=str(tmp_path)),
    )
    response = WorkerResponse(
        request_id=str(uuid4()) if control == "wrong_id" else request.request_id,
        operation="check_vault",
        result=check_vault(tmp_path),
    )
    wire = encode_response(response)
    if control == "bad_counts":
        invalid = json.loads(wire)
        invalid["result"]["counts"]["markdown_files"] = "NOTE_BODY_CANARY"
        wire = json.dumps(invalid).encode("utf-8") + b"\n"
    script = tmp_path / "controlled child.py"
    script.write_text(
        "import sys\nsys.stdin.buffer.read()\n"
        + (
            "raise SystemExit(3)\n"
            if control == "crash"
            else f"sys.stdout.buffer.write({wire!r})\n"
        ),
        encoding="utf-8",
    )
    before = inventory(tmp_path)
    popen = subprocess.Popen
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda args, **kwargs: popen([args[0], str(script)], **kwargs),
    )
    terminal = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src").run(
        request
    )
    assert terminal.phase == "may_have_executed"
    assert terminal.response is None
    assert "NOTE_BODY_CANARY" not in repr(terminal)
    assert inventory(tmp_path) == before


def test_checker_launch_failure_is_known_before_execution(tmp_path):
    from brz2obsidian.application.contracts import CheckArguments, WorkerRequest
    from brz2obsidian.application.transport import Supervisor

    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="check_vault",
        arguments=CheckArguments(vault=str(tmp_path)),
    )
    terminal = Supervisor(
        tmp_path / "absent-python.exe", Path(__file__).parents[2] / "src"
    ).run(request)
    assert terminal.phase == "not_started"
    assert terminal.code == "launch_failure"


def test_checker_response_reports_safe_diagnostic_omission_at_response_limit(tmp_path):
    from brz2obsidian.application.contracts import (
        CheckArguments,
        WorkerRequest,
        WorkerResponse,
    )
    from brz2obsidian.application.protocol import (
        RESPONSE_LIMIT,
        decode_response,
        encode_response,
    )

    (tmp_path / "Many.md").write_text(
        "NOTE_BODY_CANARY\n![[REFERENCE_FRAGMENT_CANARY.png]]\n",
        encoding="utf-8",
    )
    before = inventory(tmp_path)
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="check_vault",
        arguments=CheckArguments(vault=str(tmp_path)),
    )
    checked = check_vault(tmp_path)
    # The codec is also a public worker boundary. Amplify only already-safe text
    # to exercise its documented wire limit without thousands of filesystem reads.
    report = checked.model_copy(
        update={"diagnostic_text": checked.diagnostic_text + "x" * RESPONSE_LIMIT}
    )
    wire = encode_response(
        WorkerResponse(
            request_id=request.request_id, operation="check_vault", result=report
        )
    )
    result = decode_response(wire, request).result
    assert result.status == "check_issues"
    assert result.counts.markdown_files == result.counts.read_markdown_files == 1
    assert result.diagnostic_omission.findings_count == 1
    assert result.diagnostic_omission.reason == "response_limit"
    assert "omitted" in result.diagnostic_text
    assert result.findings == ()
    assert len(result.diagnostic_text.encode("utf-8")) < 32768
    assert "NOTE_BODY_CANARY" not in result.model_dump_json()
    assert "REFERENCE_FRAGMENT_CANARY" not in result.model_dump_json()
    assert inventory(tmp_path) == before
