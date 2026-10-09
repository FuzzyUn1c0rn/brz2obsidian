"""Deliberate conversion recovery through the public application session."""

from pathlib import Path

import pytest

from brz2obsidian.application.contracts import (
    ApplyResult,
    ApplyTransportFailure,
    ConvertCommand,
    InspectCommand,
    SelectSource,
    SetDestination,
    SimpleCommand,
)
from brz2obsidian.application.operations import (
    convert_reviewed,
    inspect,
    validate_destination,
)
from tests.application.test_conversion_session import ready_session
from tests.application.test_minimal_workflow import make_archive


def operation(update):
    return next(effect for effect in update.effects if effect.effect == "run_operation")


def complete(session, effect, result, status=0):
    return session.dispatch(
        ApplyResult(
            request_id=effect.request.request_id,
            input_revision=effect.input_revision,
            result=result,
            process_status=status,
        )
    )


def inventory(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("late_error", [False, True])
def test_verified_vault_requires_deliberate_new_attempt_and_stays_unchanged(
    tmp_path, late_error
):
    source = make_archive(tmp_path / "archive.brz")
    source_bytes = source.read_bytes()
    session = ready_session(source, tmp_path)
    conversion = operation(session.dispatch(ConvertCommand()))
    if late_error:
        from brz2obsidian.application.operations import Operations
        from brz2obsidian.application.wiring import default_workflow
        from brz2obsidian.contracts import Issue, MigrationFailed

        workflow = default_workflow()
        publisher = workflow.publisher

        class FailureAfterPublication:
            def publish(self, artifacts, opened_source, destination):
                receipt = publisher.publish(artifacts, opened_source, destination)
                raise MigrationFailed(
                    (
                        Issue(
                            code="operation_failure",
                            phase="publication",
                            message="Synthetic later error",
                            guidance="Review the published vault.",
                        ),
                    ),
                    receipt=receipt,
                )

        workflow.publisher = FailureAfterPublication()
        published = Operations(workflow).convert_reviewed(
            source, tmp_path, "Fresh vault", conversion.request.arguments.reviewed
        )
        assert published.status == "conversion_created_with_error", published
    else:
        published = convert_reviewed(
            source, tmp_path, "Fresh vault", conversion.request.arguments.reviewed
        )
    done = complete(session, conversion, published, 1 if late_error else 0)
    original = inventory(tmp_path / "Fresh vault")
    assert done.snapshot.publication.receipt_verified
    assert "start_another_conversion" in done.snapshot.allowed_actions
    assert "retry" not in done.snapshot.allowed_actions
    assert done.effects == ()
    assert session.dispatch(ConvertCommand()).snapshot == done.snapshot
    assert (
        session.dispatch(
            SetDestination(parent_or_null=str(tmp_path), vault_name="Bypassed")
        ).snapshot
        == done.snapshot
    )
    assert (
        session.dispatch(
            SelectSource(path_or_null=str(tmp_path / "bypass.brz"))
        ).snapshot
        == done.snapshot
    )

    fresh = session.dispatch(SimpleCommand(command="start_another_conversion"))
    assert fresh.snapshot.publication is None and fresh.snapshot.result is None
    assert fresh.snapshot.source == str(source)
    assert fresh.snapshot.parent == str(tmp_path)
    assert fresh.snapshot.vault_name == ""
    assert fresh.snapshot.destination_validation is None
    assert fresh.snapshot.reviewed is None and fresh.snapshot.review_required
    assert "convert" not in fresh.snapshot.allowed_actions
    assert fresh.effects == ()

    inspection = operation(session.dispatch(InspectCommand()))
    complete(session, inspection, inspect(source))

    populated = operation(
        session.dispatch(
            SetDestination(parent_or_null=str(tmp_path), vault_name="Fresh vault")
        )
    )
    refused = complete(
        session, populated, validate_destination(tmp_path, "Fresh vault"), 1
    )
    assert refused.snapshot.destination_validation.outcome == "invalid"
    assert session.dispatch(ConvertCommand()).effects == ()

    validation = operation(
        session.dispatch(
            SetDestination(parent_or_null=str(tmp_path), vault_name="Another vault")
        )
    )
    checked = complete(
        session, validation, validate_destination(tmp_path, "Another vault")
    )
    assert "convert" in checked.snapshot.allowed_actions
    conversion = operation(session.dispatch(ConvertCommand()))
    second = convert_reviewed(
        source, tmp_path, "Another vault", conversion.request.arguments.reviewed
    )
    completed = complete(session, conversion, second)
    assert completed.snapshot.publication.receipt_verified
    assert completed.snapshot.destination == str(tmp_path / "Another vault")
    assert inventory(tmp_path / "Fresh vault") == original
    assert (tmp_path / "Another vault/migration-record.json").is_file()
    assert source.read_bytes() == source_bytes


@pytest.mark.parametrize("failure", ["not_started", "write"])
def test_deliberate_retry_validates_first_then_requires_another_convert_click(
    tmp_path, monkeypatch, failure
):
    source = make_archive(tmp_path / "archive.brz")
    original = source.read_bytes()
    session = ready_session(source, tmp_path)
    conversion = operation(session.dispatch(ConvertCommand()))
    if failure == "not_started":
        failed = session.dispatch(
            ApplyTransportFailure(
                request_id=conversion.request.request_id,
                phase="not_started",
                code="launch_failure",
            )
        )
        assert failed.snapshot.operational_status == "operation_not_started"
    else:
        original_open = Path.open

        def deny_staged_write(path, mode="r", *args, **kwargs):
            if mode == "xb" and any(
                part.startswith(".brz2obsidian-") for part in path.parts
            ):
                raise PermissionError("Synthetic denied write")
            return original_open(path, mode, *args, **kwargs)

        with monkeypatch.context() as fault:
            fault.setattr(Path, "open", deny_staged_write)
            result = convert_reviewed(
                source, tmp_path, "Fresh vault", conversion.request.arguments.reviewed
            )
        failed = complete(session, conversion, result, 1)
        assert failed.snapshot.result.status == "conversion_failed"
    assert failed.snapshot.publication.state == "not_published"
    assert "retry" in failed.snapshot.allowed_actions
    assert failed.snapshot.retry_operation == "convert_reviewed"
    assert failed.effects == ()
    assert not (tmp_path / "Fresh vault").exists()
    requested = session.dispatch(ConvertCommand())
    validation = operation(requested)
    assert validation.request.operation == "validate_destination"
    assert requested.snapshot.result == failed.snapshot.result
    assert requested.snapshot.publication == failed.snapshot.publication
    assert "retry" not in requested.snapshot.allowed_actions
    assert session.dispatch(ConvertCommand()).effects == ()
    checked = complete(
        session, validation, validate_destination(tmp_path, "Fresh vault")
    )
    assert checked.effects == () and "convert" in checked.snapshot.allowed_actions
    assert not (tmp_path / "Fresh vault").exists()
    conversion = operation(session.dispatch(ConvertCommand()))
    assert conversion.request.operation == "convert_reviewed"
    result = convert_reviewed(
        source, tmp_path, "Fresh vault", conversion.request.arguments.reviewed
    )
    assert result.status == "conversion_created", result.diagnostic_text
    assert complete(session, conversion, result).snapshot.publication.receipt_verified
    assert source.read_bytes() == original


def test_checker_retry_retains_an_existing_verified_conversion_receipt(tmp_path):
    from brz2obsidian.application.contracts import SelectVault
    from brz2obsidian.application.operations import check_vault

    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    conversion = operation(session.dispatch(ConvertCommand()))
    complete(
        session,
        conversion,
        convert_reviewed(
            source, tmp_path, "Fresh vault", conversion.request.arguments.reviewed
        ),
    )
    publication = session.snapshot.publication
    checked_vault = tmp_path / "Check independently"
    checked_vault.mkdir()
    (checked_vault / "Manual.md").write_text("![[Missing.png]]", encoding="utf-8")
    session.dispatch(SelectVault(path_or_null=str(checked_vault)))
    check = operation(session.dispatch(SimpleCommand(command="check_vault")))
    done = complete(session, check, check_vault(checked_vault), 2)
    assert done.snapshot.publication == publication
    assert done.snapshot.retry_operation == "check_vault"
    assert "retry" in done.snapshot.allowed_actions
    assert "start_another_conversion" in done.snapshot.allowed_actions


@pytest.mark.parametrize("populated", [False, True])
def test_unknown_acknowledgment_keeps_original_path_and_requires_current_validation(
    tmp_path, populated
):
    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    conversion = operation(session.dispatch(ConvertCommand()))
    previous_path = tmp_path / "Fresh vault"
    if populated:
        previous_path.mkdir()
        (previous_path / "caller.bin").write_bytes(b"existence proves no outcome")
    failed = session.dispatch(
        ApplyTransportFailure(
            request_id=conversion.request.request_id,
            phase="may_have_executed",
            code="worker_failure",
        )
    )
    publication = failed.snapshot.publication
    assert publication.state == "unknown" and publication.destination == str(
        previous_path
    )
    assert failed.snapshot.operational_status == "publication_unknown"
    assert "review_destination" in failed.snapshot.allowed_actions
    assert "retry" not in failed.snapshot.allowed_actions
    assert session.dispatch(ConvertCommand()).snapshot == failed.snapshot
    assert session.dispatch(InspectCommand()).snapshot == failed.snapshot
    assert (
        session.dispatch(SimpleCommand(command="start_another_conversion")).snapshot
        == failed.snapshot
    )
    acknowledged = session.dispatch(
        SimpleCommand(command="acknowledge_destination_review")
    )
    assert acknowledged.snapshot.destination_review_acknowledged
    assert acknowledged.snapshot.publication == publication
    assert acknowledged.snapshot.operational_status == "publication_unknown"
    assert acknowledged.snapshot.reviewed is None
    validation = operation(acknowledged)
    assert validation.request.operation == "validate_destination"

    edited = session.dispatch(
        SetDestination(parent_or_null=str(tmp_path), vault_name="Reviewed fresh")
    )
    assert edited.snapshot.publication == publication and edited.effects == ()
    stale = complete(
        session,
        validation,
        validate_destination(tmp_path, "Fresh vault"),
        1 if populated else 0,
    )
    assert stale.snapshot.destination_validation is None
    assert "convert" not in stale.snapshot.allowed_actions
    assert session.dispatch(ConvertCommand()).effects == ()
    current_validation = operation(stale)
    checked = complete(
        session,
        current_validation,
        validate_destination(tmp_path, "Reviewed fresh"),
    )
    assert checked.effects == () and checked.snapshot.publication == publication
    inspection = operation(session.dispatch(InspectCommand()))
    assert session.snapshot.publication == publication
    inspected = complete(session, inspection, inspect(source))
    assert inspected.snapshot.publication == publication
    assert "convert" in inspected.snapshot.allowed_actions
    conversion = operation(session.dispatch(ConvertCommand()))
    not_started = session.dispatch(
        ApplyTransportFailure(
            request_id=conversion.request.request_id,
            phase="not_started",
            code="launch_failure",
        )
    )
    assert not_started.snapshot.operational_status == "operation_not_started"
    assert not_started.snapshot.publication == publication
    assert not_started.snapshot.destination_review_acknowledged
    assert "retry" in not_started.snapshot.allowed_actions
    assert (
        session.dispatch(ConvertCommand()).effects[0].request.operation
        == "validate_destination"
    )
    if populated:
        assert (
            previous_path / "caller.bin"
        ).read_bytes() == b"existence proves no outcome"


def test_retry_refuses_changed_review_then_requires_fresh_inspection(tmp_path):
    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    initial = operation(session.dispatch(ConvertCommand()))
    session.dispatch(
        ApplyTransportFailure(
            request_id=initial.request.request_id,
            phase="not_started",
            code="launch_failure",
        )
    )
    # ZIP trailers are accepted archive bytes, but change the reviewed identity.
    source.write_bytes(source.read_bytes() + b"synthetic corrected export trailer")
    validation = operation(session.dispatch(ConvertCommand()))
    complete(session, validation, validate_destination(tmp_path, "Fresh vault"))
    conversion = operation(session.dispatch(ConvertCommand()))
    result = convert_reviewed(
        source, tmp_path, "Fresh vault", conversion.request.arguments.reviewed
    )
    assert result.status == "conversion_refused" and result.review_required
    failed = complete(session, conversion, result, 1)
    assert failed.snapshot.reviewed is None and failed.snapshot.review_required
    assert failed.snapshot.retry_operation == "inspect"
    assert "retry" in failed.snapshot.allowed_actions
    assert session.dispatch(ConvertCommand()).effects == ()
    assert not (tmp_path / "Fresh vault").exists()
    inspected = operation(session.dispatch(InspectCommand()))
    complete(session, inspected, inspect(source))
    assert session.snapshot.reviewed is not None
    assert "convert" not in session.snapshot.allowed_actions
    validation = operation(
        session.dispatch(
            SetDestination(parent_or_null=str(tmp_path), vault_name="Corrected")
        )
    )
    complete(session, validation, validate_destination(tmp_path, "Corrected"))
    conversion = operation(session.dispatch(ConvertCommand()))
    result = convert_reviewed(
        source, tmp_path, "Corrected", conversion.request.arguments.reviewed
    )
    assert complete(session, conversion, result).snapshot.publication.receipt_verified


def test_cleanup_leftover_remains_reported_through_correction_and_reinspection(
    tmp_path, monkeypatch
):
    import shutil

    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    conversion = operation(session.dispatch(ConvertCommand()))
    original_open, original_rmtree = Path.open, shutil.rmtree

    def deny_write(path, mode="r", *args, **kwargs):
        if mode == "xb" and any(
            part.startswith(".brz2obsidian-") for part in path.parts
        ):
            raise PermissionError("Synthetic write failure")
        return original_open(path, mode, *args, **kwargs)

    def deny_owned_cleanup(path, *args, **kwargs):
        if Path(path).name.startswith(".brz2obsidian-"):
            raise PermissionError("Synthetic owned cleanup failure")
        return original_rmtree(path, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(Path, "open", deny_write)
        fault.setattr(shutil, "rmtree", deny_owned_cleanup)
        result = convert_reviewed(
            source, tmp_path, "Fresh vault", conversion.request.arguments.reviewed
        )
    failed = complete(session, conversion, result, 1)
    old_generation = session.diagnostic_generation
    assert session.admit_diagnostic_report("copy_details", old_generation)
    leftover = next(
        finding for finding in result.findings if finding.code == "cleanup_failure"
    )
    actual_leftover = Path(leftover.path)
    assert actual_leftover.is_dir()
    before = inventory(actual_leftover)
    assert failed.snapshot.recovery_findings == (leftover,)
    validation = operation(
        session.dispatch(
            SetDestination(parent_or_null=str(tmp_path), vault_name="Corrected")
        )
    )
    complete(session, validation, validate_destination(tmp_path, "Corrected"))
    inspection = operation(session.dispatch(InspectCommand()))
    inspected = complete(session, inspection, inspect(source))
    assert inspected.snapshot.result.operation == "inspect"
    assert inspected.snapshot.recovery_findings == (leftover,)
    assert session.admit_diagnostic_report("copy_details", old_generation) is None
    assert (
        session.admit_diagnostic_report("save_diagnostic_report", old_generation)
        is None
    )
    for action in ("copy_details", "save_diagnostic_report"):
        current = session.admit_diagnostic_report(action, session.diagnostic_generation)
        assert "Operation: inspect" in current
        assert "Operation: convert_reviewed" not in current
    assert "will not delete" in leftover.message
    assert actual_leftover.is_dir() and inventory(actual_leftover) == before
    assert not (tmp_path / "Fresh vault").exists()


def test_warning_retry_does_not_replay_prior_authorization(tmp_path):
    from tests.support.v3_collection import mixed_v3_archive

    source = mixed_v3_archive(tmp_path / "warnings.brz")
    session = ready_session(source, tmp_path)
    initial = operation(session.dispatch(ConvertCommand(proceed_with_warnings=True)))
    session.dispatch(
        ApplyTransportFailure(
            request_id=initial.request.request_id,
            phase="not_started",
            code="launch_failure",
        )
    )
    validation = operation(session.dispatch(ConvertCommand()))
    assert validation.request.operation == "validate_destination"
    checked = complete(
        session, validation, validate_destination(tmp_path, "Fresh vault")
    )
    assert checked.effects == ()
    assert "convert_with_warnings" in checked.snapshot.allowed_actions
    assert "convert" not in checked.snapshot.allowed_actions
    assert session.dispatch(ConvertCommand()).effects == ()
    admitted = operation(session.dispatch(ConvertCommand(proceed_with_warnings=True)))
    assert admitted.request.arguments.proceed_with_warnings is True
    assert not (tmp_path / "Fresh vault").exists()
