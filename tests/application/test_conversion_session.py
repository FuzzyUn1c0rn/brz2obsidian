import pytest

from brz2obsidian.application.contracts import (
    ApplyResult,
    ApplyTransportFailure,
    ConvertCommand,
    InspectCommand,
    SelectSource,
    SelectVault,
    SetDestination,
    SimpleCommand,
)
from brz2obsidian.application.operations import (
    ApplicationSession,
    convert_reviewed,
    inspect,
    validate_destination,
)
from tests.application.test_minimal_workflow import make_archive


def complete(session, effect, result, status=0):
    return session.dispatch(
        ApplyResult(
            request_id=effect.request.request_id,
            input_revision=effect.input_revision,
            result=result,
            process_status=status,
        )
    )


def ready_session(source, parent):
    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=str(source)))
    inspected = next(
        effect
        for effect in session.dispatch(InspectCommand()).effects
        if effect.effect == "run_operation"
    )
    result = inspect(source)
    complete(session, inspected, result, 2 if result.outcome == "warnings" else 0)
    validation = next(
        effect
        for effect in session.dispatch(
            SetDestination(parent_or_null=str(parent), vault_name="Fresh vault")
        ).effects
        if effect.effect == "run_operation"
    )
    complete(session, validation, validate_destination(parent, "Fresh vault"))
    return session


def test_native_picker_forward_slash_source_stays_associated_with_worker_review(
    tmp_path,
):
    source = make_archive(tmp_path / "Native archive.brz")
    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=source.as_posix()))
    effect = next(
        effect
        for effect in session.dispatch(InspectCommand()).effects
        if effect.effect == "run_operation"
    )
    result = inspect(source)
    done = complete(session, effect, result)

    assert done.snapshot.reviewed == result.reviewed
    validation = next(
        effect
        for effect in session.dispatch(
            SetDestination(
                parent_or_null=tmp_path.as_posix(), vault_name="Native vault"
            )
        ).effects
        if effect.effect == "run_operation"
    )
    checked = complete(
        session, validation, validate_destination(tmp_path, "Native vault")
    )
    assert checked.snapshot.reviewed == result.reviewed
    assert "convert" in checked.snapshot.allowed_actions


def test_equivalent_native_source_paths_cancel_and_invalid_relative_paths_preserve_review(
    tmp_path,
):
    source = make_archive(tmp_path / "Native archive.brz")
    session = ready_session(source, tmp_path)
    previous = session.snapshot
    assert (
        session.dispatch(SelectSource(path_or_null=source.as_posix())).snapshot
        == previous
    )
    assert (
        session.dispatch(
            SelectSource(path_or_null=source.as_posix().swapcase())
        ).snapshot
        == previous
    )
    assert session.dispatch(SelectSource(path_or_null=None)).snapshot == previous
    for relative in ("archive.brz", "C:archive.brz", "../archive.brz"):
        with pytest.raises(ValueError, match="absolute"):
            session.dispatch(SelectSource(path_or_null=relative))
        assert session.snapshot == previous
    selected = session.dispatch(SelectVault(path_or_null=tmp_path.as_posix()))
    assert selected.snapshot.reviewed == previous.reviewed
    assert "convert" in selected.snapshot.allowed_actions


def test_clean_conversion_admission_survives_unrelated_vault_selection_and_defers_close(
    tmp_path,
):
    source = make_archive(tmp_path / "archive.brz")
    original = source.read_bytes()
    session = ready_session(source, tmp_path)
    reviewed = session.snapshot.reviewed
    session.dispatch(SelectVault(path_or_null=str(tmp_path / "separate check vault")))
    assert session.snapshot.destination_revision < session.snapshot.revision
    assert "convert" in session.snapshot.allowed_actions

    started = session.dispatch(ConvertCommand())
    assert len(started.effects) == 1
    effect = started.effects[0]
    assert effect.request.operation == "convert_reviewed"
    assert effect.request.arguments.reviewed == reviewed
    assert not effect.request.arguments.proceed_with_warnings
    assert started.snapshot.busy_operation == "convert_reviewed"
    assert session.dispatch(ConvertCommand()).effects == ()
    assert session.dispatch(InspectCommand()).effects == ()
    assert session.dispatch(SimpleCommand(command="check_vault")).effects == ()
    assert session.dispatch(
        SelectSource(path_or_null=str(tmp_path / "other.brz"))
    ).snapshot.source == str(source)
    assert (
        session.dispatch(
            SetDestination(parent_or_null=str(tmp_path), vault_name="another")
        ).snapshot.vault_name
        == "Fresh vault"
    )
    closing = session.dispatch(SimpleCommand(command="request_close"))
    assert closing.snapshot.close_pending and closing.effects == ()

    result = convert_reviewed(source, tmp_path, "Fresh vault", reviewed)
    done = complete(session, effect, result)

    assert done.snapshot.result.status == "conversion_created"
    assert done.snapshot.publication == result.publication
    assert done.snapshot.destination == str(tmp_path / "Fresh vault")
    assert done.snapshot.result.counts.actual_notes == 1
    assert [item.effect for item in done.effects] == ["close_window"]
    assert "convert" not in done.snapshot.allowed_actions
    assert session.dispatch(ConvertCommand()).effects == ()
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "failure", ["launch", "crash", "wrong_exit", "wrong_operation"]
)
def test_conversion_terminal_uncertainty_does_not_authorize_retry_or_infer_directory_state(
    tmp_path, failure
):
    from brz2obsidian.application.contracts import ConversionResult, Publication

    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    reviewed = session.snapshot.reviewed
    effect = next(
        effect
        for effect in session.dispatch(ConvertCommand()).effects
        if effect.effect == "run_operation"
    )
    if failure == "crash":
        vault = tmp_path / "Fresh vault"
        vault.mkdir()
        (vault / "unrelated.bin").write_bytes(b"not proof of publication")
    if failure in ("launch", "crash"):
        done = session.dispatch(
            ApplyTransportFailure(
                request_id=effect.request.request_id,
                phase="not_started" if failure == "launch" else "may_have_executed",
                code="launch_failure" if failure == "launch" else "worker_failure",
            )
        )
    else:
        result = (
            inspect(source)
            if failure == "wrong_operation"
            else ConversionResult(
                outcome="failed",
                status="conversion_failed",
                publication=Publication(state="not_published"),
                diagnostic_text="Safe failure",
            )
        )
        done = complete(session, effect, result, 0)

    assert done.snapshot.result is None
    assert done.snapshot.operational_status == (
        "operation_not_started" if failure == "launch" else "publication_unknown"
    )
    assert done.snapshot.publication.state == (
        "not_published" if failure == "launch" else "unknown"
    )
    assert done.effects == () and "convert" not in done.snapshot.allowed_actions
    assert f"Destination: {tmp_path / 'Fresh vault'}" in session.diagnostics_text()
    requested = session.dispatch(ConvertCommand())
    assert [effect.request.operation for effect in requested.effects] == (
        ["validate_destination"] if failure == "launch" else []
    )
    assert (
        session.snapshot.source == str(source)
        and session.snapshot.vault_name == "Fresh vault"
    )
    if failure == "launch":
        assert session.snapshot.reviewed == reviewed
    else:
        assert session.snapshot.reviewed is None and session.snapshot.review_required
        previous = session.snapshot
        assert (
            session.dispatch(
                SetDestination(parent_or_null=str(tmp_path), vault_name="bypass")
            ).snapshot
            == previous
        )
        assert (
            session.dispatch(
                SelectSource(path_or_null=str(tmp_path / "another.brz"))
            ).snapshot
            == previous
        )
        assert (
            session.dispatch(SimpleCommand(command="start_another_conversion")).snapshot
            == previous
        )
        acknowledged = session.dispatch(
            SimpleCommand(command="acknowledge_destination_review")
        )
        assert acknowledged.snapshot.destination_review_acknowledged
        assert acknowledged.snapshot.publication == previous.publication
        assert acknowledged.snapshot.operational_status == "publication_unknown"
        assert [effect.request.operation for effect in acknowledged.effects] == [
            "validate_destination"
        ]
        assert "convert" not in acknowledged.snapshot.allowed_actions


@pytest.mark.parametrize("stale_review", [False, True])
def test_trustworthy_failed_attempt_retains_inputs_and_requires_fresh_destination_validation(
    tmp_path, stale_review
):
    from brz2obsidian.application.contracts import (
        ConversionResult,
        Finding,
        Publication,
    )
    from brz2obsidian.contracts import Counts

    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    reviewed = session.snapshot.reviewed
    effect = next(
        effect
        for effect in session.dispatch(ConvertCommand()).effects
        if effect.effect == "run_operation"
    )
    result = ConversionResult(
        outcome="refused" if stale_review else "failed",
        status="conversion_refused" if stale_review else "conversion_failed",
        publication=Publication(state="not_published"),
        destination=str(tmp_path / "Fresh vault"),
        counts=Counts(planned_notes=1),
        review_required=stale_review,
        findings=(
            Finding(
                code="review_changed" if stale_review else "write_failure",
                severity="error",
                message="Inspect again."
                if stale_review
                else "Review access and the destination.",
            ),
        ),
        diagnostic_text="Safe failure report",
    )
    done = complete(session, effect, result, 1)

    assert (
        done.snapshot.result == result
        and done.snapshot.publication.state == "not_published"
    )
    assert (
        done.snapshot.source == str(source)
        and done.snapshot.vault_name == "Fresh vault"
    )
    assert done.snapshot.reviewed == (None if stale_review else reviewed)
    assert done.snapshot.destination_validation is None and done.effects == ()
    requested = session.dispatch(ConvertCommand())
    if stale_review:
        assert requested.effects == ()
    else:
        validation = requested.effects[0]
        assert validation.request.operation == "validate_destination"
        checked = complete(
            session, validation, validate_destination(tmp_path, "Fresh vault")
        )
        assert checked.effects == ()
    revalidation = session.dispatch(
        SetDestination(parent_or_null=str(tmp_path), vault_name="Corrected vault")
    )
    validation = next(
        effect for effect in revalidation.effects if effect.effect == "run_operation"
    )
    checked = complete(
        session, validation, validate_destination(tmp_path, "Corrected vault")
    )
    assert ("convert" in checked.snapshot.allowed_actions) is not stale_review


def test_published_late_error_retains_receipt_path_and_locks_form_until_recovery_slice(
    tmp_path,
):
    from brz2obsidian.application.contracts import ConversionResult, Publication
    from brz2obsidian.contracts import Counts

    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    effect = next(
        effect
        for effect in session.dispatch(ConvertCommand()).effects
        if effect.effect == "run_operation"
    )
    path = str(tmp_path / "Fresh vault")
    result = ConversionResult(
        outcome="failed",
        status="conversion_created_with_error",
        destination=path,
        publication=Publication(
            state="published_verified", destination=path, receipt_verified=True
        ),
        counts=Counts(planned_notes=1, actual_notes=1),
        diagnostic_text="Verified publication before handled error.",
    )
    done = complete(session, effect, result, 1)

    assert (
        done.snapshot.result == result
        and done.snapshot.publication == result.publication
    )
    assert (
        done.snapshot.destination == path
        and "retry" not in done.snapshot.allowed_actions
    )
    previous = session.snapshot
    assert session.dispatch(ConvertCommand()).snapshot == previous
    assert (
        session.dispatch(
            SetDestination(parent_or_null=str(tmp_path), vault_name="bypass")
        ).snapshot
        == previous
    )
    assert (
        session.dispatch(
            SelectSource(path_or_null=str(tmp_path / "another.brz"))
        ).snapshot
        == previous
    )


def test_warning_session_requires_explicit_authorization_before_admitting_worker(
    tmp_path,
):
    from tests.support.v3_collection import mixed_v3_archive

    source = mixed_v3_archive(tmp_path / "warning archive.brz")
    session = ready_session(source, tmp_path)
    assert session.snapshot.reviewed.outcome == "warnings"
    assert "convert" not in session.snapshot.allowed_actions
    assert "convert_with_warnings" in session.snapshot.allowed_actions
    assert session.dispatch(ConvertCommand()).effects == ()
    admitted = session.dispatch(ConvertCommand(proceed_with_warnings=True))
    effect = next(
        effect for effect in admitted.effects if effect.effect == "run_operation"
    )
    assert effect.request.arguments.proceed_with_warnings is True
    result = convert_reviewed(
        source, tmp_path, "Fresh vault", effect.request.arguments.reviewed, True
    )
    done = complete(session, effect, result, 2)
    assert done.snapshot.result.status == "conversion_created_with_warnings"
    assert done.snapshot.publication.receipt_verified


@pytest.mark.parametrize(
    "behavior",
    ["launch", "crash", "malformed", "receipt_wrong_exit", "missing_receipt_fact"],
)
def test_real_transport_failures_reduce_to_honest_conversion_status_without_retry(
    tmp_path, monkeypatch, behavior
):
    import json
    import subprocess
    import sys
    from pathlib import Path
    from threading import Event

    from brz2obsidian.application.contracts import (
        ConversionResult,
        Publication,
        WorkerResponse,
    )
    from brz2obsidian.application.runner import HostRunner
    from brz2obsidian.application.transport import Supervisor
    from brz2obsidian.contracts import Counts

    source = make_archive(tmp_path / "archive.brz")
    original = source.read_bytes()
    session = ready_session(source, tmp_path)
    script = tmp_path / "controlled conversion child.py"
    path = str(tmp_path / "Fresh vault")
    result = ConversionResult(
        outcome="failed",
        status="conversion_created_with_error",
        publication=Publication(
            state="published_verified", destination=path, receipt_verified=True
        ),
        destination=path,
        counts=Counts(actual_notes=1),
        diagnostic_text="Safe verified late failure report.",
    )
    # The controlled real child gets the exact request identity at runtime.
    response = WorkerResponse(
        request_id="00000000-0000-0000-0000-000000000001",
        operation="convert_reviewed",
        result=result,
    ).model_dump(mode="json", by_alias=True)
    if behavior == "missing_receipt_fact":
        del response["result"]["publication"]["receipt_verified"]
    action = (
        "raise SystemExit(3)"
        if behavior == "crash"
        else "sys.stdout.write('RAW_PRIVATE_CANARY not JSON'); sys.stdout.flush()"
        if behavior == "malformed"
        else f"response = json.loads({json.dumps(response)!r}); response['request_id'] = request['request_id']; print(json.dumps(response), flush=True)"
    )
    script.write_text(
        "import sys, json\nrequest = json.load(sys.stdin)\n" + action, encoding="utf-8"
    )
    real_popen = subprocess.Popen
    calls = []

    def controlled_popen(arguments, **kwargs):
        calls.append(True)
        return real_popen([arguments[0], str(script)], **kwargs)

    if behavior != "launch":
        monkeypatch.setattr(subprocess, "Popen", controlled_popen)
    supervisor = Supervisor(
        tmp_path / "missing-python.exe"
        if behavior == "launch"
        else Path(sys.executable),
        Path(__file__).parents[2] / "src",
    )
    completed = Event()
    updates = []

    def observe(prepared):
        updates.append(prepared.update.snapshot)
        if prepared.update.snapshot.operational_status is not None:
            completed.set()

    runner = HostRunner(supervisor, observe, lambda page: None, session=session)
    try:
        runner.submit(ConvertCommand())
        assert completed.wait(10)
        state = updates[-1]
        assert state.operational_status == (
            "operation_not_started" if behavior == "launch" else "publication_unknown"
        )
        assert state.publication.state == (
            "not_published" if behavior == "launch" else "unknown"
        )
        assert state.result is None and state.active_request_id is None
        assert "RAW_PRIVATE_CANARY" not in session.diagnostics_text()
        requested = session.dispatch(ConvertCommand())
        assert [effect.request.operation for effect in requested.effects] == (
            ["validate_destination"] if behavior == "launch" else []
        )
        assert calls == ([] if behavior == "launch" else [True])
        assert (
            source.read_bytes() == original and not (tmp_path / "Fresh vault").exists()
        )
    finally:
        runner.shutdown()


@pytest.mark.parametrize("terminal", ["published", "launch_failure"])
def test_conversion_expires_old_report_and_closing_releases_current_report(
    tmp_path, terminal
):
    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    old_generation = session.diagnostic_generation
    assert session.admit_diagnostic_report("copy_details", old_generation)
    effect = next(
        effect
        for effect in session.dispatch(ConvertCommand()).effects
        if effect.effect == "run_operation"
    )
    assert session.diagnostic_generation > old_generation
    assert session.admit_diagnostic_report("copy_details", old_generation) is None
    assert session.diagnostics_text() == ""
    if terminal == "published":
        complete(
            session,
            effect,
            convert_reviewed(
                source, tmp_path, "Fresh vault", effect.request.arguments.reviewed
            ),
        )
    else:
        session.dispatch(
            ApplyTransportFailure(
                request_id=effect.request.request_id,
                phase="not_started",
                code="launch_failure",
            )
        )
    generation = session.diagnostic_generation
    report = session.admit_diagnostic_report("save_diagnostic_report", generation)
    assert report and "Operation: convert_reviewed" in report
    assert session.admit_diagnostic_report("copy_details", old_generation) is None
    session.dispatch(SimpleCommand(command="request_close"))
    assert session.diagnostic_generation > generation
    assert session.admit_diagnostic_report("save_diagnostic_report", generation) is None
    assert session.diagnostics_page_if_current(generation) is None
    assert session.diagnostics_text() == ""
    assert "convert" not in session.snapshot.allowed_actions
