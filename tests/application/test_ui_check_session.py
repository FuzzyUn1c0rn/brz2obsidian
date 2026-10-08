from pathlib import Path
from uuid import uuid4

import pytest

from brz2obsidian.application.contracts import (
    ApplyResult,
    ApplyTransportFailure,
    InspectCommand,
    SelectSource,
    SelectVault,
    SimpleCommand,
)
from brz2obsidian.application.operations import ApplicationSession, check_vault, inspect


def selected_session(vault):
    session = ApplicationSession()
    session.dispatch(SelectVault(path_or_null=str(vault)))
    return session


def complete(session, effect, result, status):
    return session.dispatch(
        ApplyResult(
            request_id=effect.request.request_id,
            input_revision=effect.input_revision,
            result=result,
            process_status=status,
        )
    )


def test_check_selection_admission_readonly_completion_cancellation_and_retry(tmp_path):
    (tmp_path / "Manual.md").write_text("![[Missing.png]]\n", encoding="utf-8")
    session = selected_session(tmp_path)
    assert "check_vault" in session.snapshot.allowed_actions
    effect = session.dispatch(SimpleCommand(command="check_vault")).effects[0]
    assert effect.request.operation == "check_vault"
    assert effect.request.arguments.vault == str(tmp_path)
    assert session.snapshot.busy_operation == "check_vault"
    assert session.dispatch(SimpleCommand(command="check_vault")).effects == ()
    assert session.dispatch(InspectCommand()).effects == ()
    assert session.dispatch(
        SelectVault(path_or_null=str(tmp_path / "other"))
    ).snapshot.vault == str(tmp_path)
    assert (
        session.dispatch(
            SelectSource(path_or_null=str(tmp_path / "other.brz"))
        ).snapshot.source
        is None
    )

    done = complete(session, effect, check_vault(tmp_path), 2)
    assert done.snapshot.result.status == "check_issues"
    assert "check_vault" in done.snapshot.allowed_actions
    assert "retry" in done.snapshot.allowed_actions
    assert "copy_details" in done.snapshot.allowed_actions
    previous = session.snapshot
    text = session.diagnostics_text()
    assert session.dispatch(SelectVault(path_or_null=None)).snapshot == previous
    assert (
        session.dispatch(SelectVault(path_or_null=str(tmp_path))).snapshot == previous
    )
    assert session.diagnostics_text() == text
    (tmp_path / "Manual.md").write_text("# Corrected\n", encoding="utf-8")
    assert session.snapshot.result.status == "check_issues"  # No automatic retry.
    retry = session.dispatch(SimpleCommand(command="check_vault")).effects[0]
    assert retry.request.request_id != effect.request.request_id
    clean = complete(session, retry, check_vault(tmp_path), 0)
    assert clean.snapshot.result.status == "check_clean"


def test_changed_vault_expires_result_diagnostics_and_old_response(tmp_path):
    session = selected_session(tmp_path)
    effect = session.dispatch(SimpleCommand(command="check_vault")).effects[0]
    old = check_vault(tmp_path)
    complete(session, effect, old, 0)
    selected = session.dispatch(SelectVault(path_or_null=str(tmp_path / "another")))
    assert selected.snapshot.result is None
    assert session.diagnostics_text() == ""
    assert "copy_details" not in selected.snapshot.allowed_actions
    assert complete(session, effect, old, 0).snapshot == selected.snapshot


def test_check_keeps_unchanged_source_review_but_replaces_current_diagnostics(tmp_path):
    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=str(source)))
    first = session.dispatch(InspectCommand()).effects[0]
    inspected = complete(session, first, inspect(source), 0)
    review = inspected.snapshot.reviewed
    assert review is not None
    session.dispatch(SelectVault(path_or_null=str(tmp_path)))
    checking = session.dispatch(SimpleCommand(command="check_vault")).effects[0]
    checked = complete(session, checking, check_vault(tmp_path), 0)
    assert checked.snapshot.reviewed is review
    assert "convert_this_archive" in checked.snapshot.allowed_actions
    assert "Operation: check_vault" in session.diagnostics_text()
    assert "Operation: inspect" not in session.diagnostics_text()
    inspection = session.dispatch(InspectCommand()).effects[0]
    complete(session, inspection, inspect(source), 0)
    assert "Operation: inspect" in session.diagnostics_text()
    assert "Operation: check_vault" not in session.diagnostics_text()


@pytest.mark.parametrize(
    "failure", ["launch", "protocol", "wrong_exit", "wrong_operation"]
)
def test_check_operational_failures_are_honest_deliberate_and_close_is_deferred(
    tmp_path, failure
):
    session = selected_session(tmp_path)
    effect = session.dispatch(SimpleCommand(command="check_vault")).effects[0]
    assert session.dispatch(
        SimpleCommand(command="request_close")
    ).snapshot.close_pending
    assert session.dispatch(SimpleCommand(command="check_vault")).effects == ()
    assert (
        session.dispatch(
            ApplyTransportFailure(
                request_id=str(uuid4()),
                phase="may_have_executed",
                code="protocol_failure",
            )
        ).snapshot.active_request_id
        == effect.request.request_id
    )
    if failure in ("launch", "protocol"):
        done = session.dispatch(
            ApplyTransportFailure(
                request_id=effect.request.request_id,
                phase="not_started" if failure == "launch" else "may_have_executed",
                code="launch_failure" if failure == "launch" else "protocol_failure",
            )
        )
    else:
        result = (
            inspect((Path(__file__).parents[1] / "fixtures/minimal.brz").absolute())
            if failure == "wrong_operation"
            else check_vault(tmp_path)
        )
        done = complete(session, effect, result, 2 if failure == "wrong_exit" else 0)
    assert done.snapshot.result is None
    assert "Check could not complete" in done.snapshot.feedback
    assert "Publication status unknown" not in done.snapshot.feedback
    assert str(tmp_path) in session.diagnostics_text()
    assert [item.effect for item in done.effects] == ["close_window"]


def test_failed_check_keeps_source_review_and_retry_requires_an_explicit_command(
    tmp_path,
):
    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=str(source)))
    effect = session.dispatch(InspectCommand()).effects[0]
    complete(session, effect, inspect(source), 0)
    review = session.snapshot.reviewed
    session.dispatch(SelectVault(path_or_null=str(tmp_path)))
    checking = session.dispatch(SimpleCommand(command="check_vault")).effects[0]
    failed = session.dispatch(
        ApplyTransportFailure(
            request_id=checking.request.request_id,
            phase="may_have_executed",
            code="protocol_failure",
        )
    )
    assert failed.snapshot.reviewed is review
    assert failed.effects == ()
    assert "check_vault" in failed.snapshot.allowed_actions
    assert "retry" in failed.snapshot.allowed_actions
    assert "Operation: check_vault" in session.diagnostics_text()
    retry = session.dispatch(SimpleCommand(command="check_vault"))
    assert retry.effects[0].request.request_id != checking.request.request_id


def test_checker_host_diagnostic_pages_are_bounded_complete_and_safe(tmp_path):
    (tmp_path / "Many.md").write_text(
        "NOTE_BODY_CANARY\n" + "![[REFERENCE_FRAGMENT_CANARY.png]]\n" * 500,
        encoding="utf-8",
    )
    session = selected_session(tmp_path)
    effect = session.dispatch(SimpleCommand(command="check_vault")).effects[0]
    result = check_vault(tmp_path)
    complete(session, effect, result, 2)
    offset, parts = 0, []
    while True:
        page = session.diagnostics_page(offset)
        assert len(page.lines) <= 100
        assert len(page.text.encode("utf-8")) <= 32768
        parts.append(page.text)
        if page.next_offset is None:
            break
        offset = page.next_offset
    assert "".join(parts) == result.diagnostic_text
    assert len(parts) > 1
    assert "NOTE_BODY_CANARY" not in "".join(parts)
    assert "REFERENCE_FRAGMENT_CANARY" not in "".join(parts)
