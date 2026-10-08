from pathlib import Path

import pytest

from brz2obsidian.application.operations import validate_destination


def inventory(root):
    return {
        str(path.relative_to(root)): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


def run_effect(update):
    return next(effect for effect in update.effects if effect.effect == "run_operation")


def test_preliminary_destination_is_readonly_and_discloses_unchecked_scope(tmp_path):
    (tmp_path / "source.brz").write_bytes(b"selected source stays unchanged")
    before = inventory(tmp_path)
    result = validate_destination(tmp_path, "Été vault")
    assert result.status == "destination_valid"
    assert result.destination == str(tmp_path / "Été vault")
    assert result.field_errors == ()
    assert "destination_absent_or_empty" in result.checked
    assert "generated_paths" in result.pending
    assert "write_success" in result.pending
    assert "240" in result.diagnostic_text
    assert inventory(tmp_path) == before


@pytest.mark.parametrize(
    "target_kind", ["absent", "empty", "populated", "file", "missing_parent"]
)
def test_existing_parent_and_fresh_target_are_observed_without_mutation(
    tmp_path, target_kind
):
    parent = tmp_path / "missing" if target_kind == "missing_parent" else tmp_path
    target = parent / "Vault"
    if target_kind in ("empty", "populated"):
        target.mkdir()
    if target_kind == "populated":
        (target / "keep.md").write_bytes(b"retained vault contents")
    if target_kind == "file":
        target.write_bytes(b"retained caller file")
    before = inventory(tmp_path)
    result = validate_destination(parent, "Vault")
    assert result.destination == str(target)
    assert result.outcome == (
        "valid" if target_kind in ("absent", "empty") else "invalid"
    )
    if target_kind == "missing_parent":
        assert result.field_errors[0].field == "parent"
    if target_kind in ("populated", "file"):
        assert result.field_errors[0].code == "destination_not_empty"
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("scope", ["parent", "ancestor", "target"])
def test_reparse_path_has_adjacent_error_without_following_it(tmp_path, scope):
    import os
    import subprocess

    if os.name != "nt":
        pytest.skip("Windows junction control")
    caller = tmp_path / "caller"
    caller.mkdir()
    (caller / "keep.md").write_bytes(b"caller owned")
    junction = tmp_path / "redirect"
    subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(caller)],
        check=True,
        capture_output=True,
    )
    try:
        parent = (
            junction
            if scope == "parent"
            else junction / "inside"
            if scope == "ancestor"
            else tmp_path
        )
        if scope == "ancestor":
            (caller / "inside").mkdir()
        result = validate_destination(
            parent, "redirect" if scope == "target" else "Vault"
        )
        assert result.outcome == "invalid"
        assert result.field_errors[0].field == (
            "destination" if scope == "target" else "parent"
        )
        assert not (caller / "Vault").exists()
        assert (caller / "keep.md").read_bytes() == b"caller owned"
    finally:
        junction.rmdir()


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        ".",
        "..",
        "CON",
        "nul.txt",
        "LPT9",
        "COM¹",
        "con .txt",
        "CONIN$",
        "CONOUT$",
        "bad?name",
        "bad\x00name",
        "tail.",
        "tail ",
        "nested/vault",
        "nested\\vault",
        "../escape",
        "C:\\escape",
        "C:escape",
        "\\\\server\\share",
        "/rooted",
        "vault:stream",
    ],
)
def test_names_cannot_redirect_or_normalize_destination_intent(tmp_path, name):
    before = inventory(tmp_path)
    result = validate_destination(tmp_path, name)
    assert result.outcome == "invalid"
    assert result.destination is None
    assert any(error.field == "vault_name" for error in result.field_errors)
    assert inventory(tmp_path) == before


def test_session_coalesces_destination_revisions_and_retains_inspection(tmp_path):
    from brz2obsidian.application.contracts import (
        ApplyResult,
        InspectCommand,
        SelectSource,
        SetDestination,
    )
    from brz2obsidian.application.operations import ApplicationSession, inspect

    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=str(source)))
    inspection = run_effect(session.dispatch(InspectCommand()))
    result = inspect(source)
    session.dispatch(
        ApplyResult(
            request_id=inspection.request.request_id,
            input_revision=inspection.input_revision,
            result=result,
            process_status=0,
        )
    )
    report = session.diagnostics_text()
    first = session.dispatch(
        SetDestination(parent_or_null=str(tmp_path), vault_name="First")
    )
    pending = run_effect(first)
    assert first.snapshot.validation_pending
    assert "convert" not in first.snapshot.allowed_actions
    assert first.snapshot.result is result
    assert first.snapshot.reviewed is result.reviewed
    assert (
        session.dispatch(
            SetDestination(parent_or_null=str(tmp_path), vault_name="Second")
        ).effects
        == ()
    )
    assert (
        session.dispatch(
            SetDestination(parent_or_null=str(tmp_path), vault_name="Latest")
        ).effects
        == ()
    )
    late = session.dispatch(
        ApplyResult(
            request_id=pending.request.request_id,
            input_revision=pending.input_revision,
            result=validate_destination(tmp_path, "First"),
            process_status=0,
        )
    )
    assert late.snapshot.destination is None
    assert late.snapshot.validation_pending
    assert "convert" not in late.snapshot.allowed_actions
    assert len(late.effects) == 1
    latest = run_effect(late)
    assert latest.request.arguments.vault_name == "Latest"
    done = session.dispatch(
        ApplyResult(
            request_id=latest.request.request_id,
            input_revision=latest.input_revision,
            result=validate_destination(tmp_path, "Latest"),
            process_status=0,
        )
    )
    assert done.snapshot.destination == str(tmp_path / "Latest")
    assert not done.snapshot.validation_pending
    assert done.snapshot.result is result
    assert done.snapshot.reviewed is result.reviewed
    assert session.diagnostics_text() == report
    assert "convert" in done.snapshot.allowed_actions


def test_readonly_preflight_reports_io_failure_without_raw_exception(
    tmp_path, monkeypatch
):
    target = tmp_path / "Vault"
    target.mkdir()
    original = Path.iterdir

    def denied(path):
        if path == target:
            raise PermissionError("PRIVATE_EXCEPTION_CANARY")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", denied)
    result = validate_destination(tmp_path, "Vault")
    assert result.outcome == "failed"
    assert result.destination == str(target)
    assert result.field_errors[0].field == "destination"
    assert "CANARY" not in result.model_dump_json()


def test_preflight_never_attempts_write_probe_or_staging(tmp_path, monkeypatch):
    def unexpected_write(*args, **kwargs):
        pytest.fail("Preliminary validation attempted filesystem mutation")

    for method in ("mkdir", "rmdir", "unlink", "open", "rename"):
        monkeypatch.setattr(Path, method, unexpected_write)
    assert validate_destination(tmp_path, "Vault").outcome == "valid"


def test_destination_valid_requires_a_constructed_path_and_no_field_errors():
    from pydantic import ValidationError

    from brz2obsidian.application.contracts import DestinationValidation, Finding

    with pytest.raises(ValidationError):
        DestinationValidation(outcome="valid", status="destination_valid")
    with pytest.raises(ValidationError):
        DestinationValidation(
            outcome="valid",
            status="destination_valid",
            destination=str(Path.cwd() / "Vault"),
            field_errors=(
                Finding(
                    code="invalid",
                    severity="error",
                    message="Invalid",
                    field="vault_name",
                ),
            ),
        )


@pytest.mark.parametrize(
    "mismatch", ["wrong_revision", "wrong_operation", "wrong_exit", "transport_failure"]
)
def test_validation_failure_or_mismatched_terminal_never_replaces_primary_result(
    tmp_path, mismatch
):
    from brz2obsidian.application.contracts import (
        ApplyResult,
        ApplyTransportFailure,
        InspectCommand,
        SelectSource,
        SetDestination,
    )
    from brz2obsidian.application.operations import ApplicationSession, inspect

    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=str(source)))
    inspected = run_effect(session.dispatch(InspectCommand()))
    primary = inspect(source)
    session.dispatch(
        ApplyResult(
            request_id=inspected.request.request_id,
            input_revision=inspected.input_revision,
            result=primary,
            process_status=0,
        )
    )
    validating = run_effect(
        session.dispatch(
            SetDestination(parent_or_null=str(tmp_path), vault_name="Vault")
        )
    )
    if mismatch == "transport_failure":
        command = ApplyTransportFailure(
            request_id=validating.request.request_id,
            phase="may_have_executed",
            code="protocol_failure",
        )
    else:
        command = ApplyResult(
            request_id=validating.request.request_id,
            input_revision=validating.input_revision
            + (1 if mismatch == "wrong_revision" else 0),
            result=primary
            if mismatch == "wrong_operation"
            else validate_destination(tmp_path, "Vault"),
            process_status=1 if mismatch == "wrong_exit" else 0,
        )
    done = session.dispatch(command)
    assert done.snapshot.destination is None
    assert done.snapshot.destination_validation.outcome == "failed"
    assert done.snapshot.result is primary
    assert session.diagnostics_text() == primary.diagnostic_text
    assert done.effects == ()  # No automatic retry of failed validation.
    retry = session.dispatch(
        SetDestination(parent_or_null=str(tmp_path), vault_name="Vault")
    )
    assert len(retry.effects) == 1  # Explicit choose/edit can request a fresh check.


def test_real_destination_worker_and_cli_missing_parent_remain_compatible(
    tmp_path, capsys
):
    import json
    import sys
    from uuid import uuid4

    from brz2obsidian.application.contracts import DestinationArguments, WorkerRequest
    from brz2obsidian.application.transport import Supervisor
    from brz2obsidian.cli import main

    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    before = source.read_bytes()
    supervisor = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src")
    for name, expected in (("Été vault", "valid"), ("CON", "invalid")):
        terminal = supervisor.run(
            WorkerRequest(
                request_id=str(uuid4()),
                operation="validate_destination",
                arguments=DestinationArguments(parent=str(tmp_path), vault_name=name),
            )
        )
        assert terminal.phase == "completed"
        assert terminal.response.result.outcome == expected
        assert terminal.process_status == (0 if expected == "valid" else 1)
    missing = tmp_path / "new parent"
    assert validate_destination(missing, "Vault").outcome == "invalid"
    assert not missing.exists()
    assert main(["convert", str(source), str(missing / "Vault"), "--json"]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["receipt"]["published"] is True
    assert (missing / "Vault/MIGRATION REPORT.md").is_file()
    assert source.read_bytes() == before


def test_close_waits_for_primary_and_validation_without_starting_queued_checks(
    tmp_path,
):
    from brz2obsidian.application.contracts import (
        ApplyResult,
        InspectCommand,
        SelectSource,
        SetDestination,
        SimpleCommand,
    )
    from brz2obsidian.application.operations import ApplicationSession, inspect

    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=str(source)))
    validation = run_effect(
        session.dispatch(
            SetDestination(parent_or_null=str(tmp_path), vault_name="First")
        )
    )
    session.dispatch(SetDestination(parent_or_null=str(tmp_path), vault_name="Latest"))
    primary = run_effect(session.dispatch(InspectCommand()))
    closing = session.dispatch(SimpleCommand(command="request_close"))
    assert closing.snapshot.close_pending
    assert closing.effects == ()
    inspected = session.dispatch(
        ApplyResult(
            request_id=primary.request.request_id,
            input_revision=primary.input_revision,
            result=inspect(source),
            process_status=0,
        )
    )
    assert inspected.effects == ()
    assert inspected.snapshot.close_pending
    assert inspected.snapshot.result.status == "inspection_clean"
    done = session.dispatch(
        ApplyResult(
            request_id=validation.request.request_id,
            input_revision=validation.input_revision,
            result=validate_destination(tmp_path, "First"),
            process_status=0,
        )
    )
    assert [effect.effect for effect in done.effects] == ["close_window"]
    assert done.snapshot.result.model_dump(
        exclude={"diagnostic_text"}
    ) == inspected.snapshot.result.model_dump(exclude={"diagnostic_text"})
    assert done.snapshot.result.diagnostic_text == ""
    assert done.snapshot.destination is None


def test_source_change_invalidates_review_even_while_destination_validation_waits(
    tmp_path,
):
    from brz2obsidian.application.contracts import (
        ApplyResult,
        InspectCommand,
        SelectSource,
        SetDestination,
    )
    from brz2obsidian.application.operations import ApplicationSession, inspect

    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    another = tmp_path / "Another.BRZ"
    another.write_bytes(source.read_bytes())
    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=str(source)))
    primary = run_effect(session.dispatch(InspectCommand()))
    session.dispatch(
        ApplyResult(
            request_id=primary.request.request_id,
            input_revision=primary.input_revision,
            result=inspect(source),
            process_status=0,
        )
    )
    checking = run_effect(
        session.dispatch(SetDestination(parent_or_null=str(tmp_path), vault_name="Old"))
    )
    changed = session.dispatch(SelectSource(path_or_null=str(another)))
    assert changed.snapshot.reviewed is None
    assert changed.snapshot.result is None
    assert changed.snapshot.vault_name == "Another"
    assert "convert_this_archive" not in changed.snapshot.allowed_actions
    late = session.dispatch(
        ApplyResult(
            request_id=checking.request.request_id,
            input_revision=checking.input_revision,
            result=validate_destination(tmp_path, "Old"),
            process_status=0,
        )
    )
    assert late.snapshot.destination is None
    assert late.snapshot.reviewed is None
    assert run_effect(late).request.arguments.vault_name == "Another"
    assert session.diagnostics_text() == ""
