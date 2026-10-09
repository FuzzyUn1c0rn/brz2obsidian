"""Completion admission through public host-session controls."""

from pathlib import Path

import pytest

from brz2obsidian.application.contracts import (
    ApplyTransportFailure,
    ConversionResult,
    ConvertCommand,
    Publication,
    SelectVault,
    SimpleCommand,
)
from brz2obsidian.application.operations import ApplicationSession, check_vault
from tests.application.test_conversion_session import complete, ready_session
from tests.application.test_minimal_workflow import make_archive

OPEN_ACTIONS = ("open_folder", "open_migration_report", "open_in_obsidian")


def published_session(tmp_path, outcome="clean"):
    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    effect = session.dispatch(ConvertCommand()).effects[0]
    destination = tmp_path / "Fresh vault"
    result = ConversionResult(
        outcome=outcome,
        status={
            "clean": "conversion_created",
            "warnings": "conversion_created_with_warnings",
            "failed": "conversion_created_with_error",
        }[outcome],
        destination=str(destination),
        publication=Publication(
            state="published_verified",
            receipt_verified=True,
            destination=str(destination),
        ),
        diagnostic_text="Verified publication. The generated vault has not been checked.",
    )
    complete(session, effect, result, {"clean": 0, "warnings": 2, "failed": 1}[outcome])
    return session, destination


@pytest.mark.parametrize("outcome", ["clean", "warnings", "failed"])
def test_verified_publication_admits_only_current_derived_completion_targets(
    tmp_path, outcome
):
    session, destination = published_session(tmp_path, outcome)
    previous = session.snapshot
    generation = session.diagnostic_generation

    assert {*OPEN_ACTIONS, "check_vault"} <= set(previous.allowed_actions)
    for action in OPEN_ACTIONS:
        target = session.admit_completion_action(action, generation)
        assert target.action == action
        assert Path(target.path) == (
            destination
            if action == "open_folder"
            else destination / "MIGRATION REPORT.md"
        )
        assert Path(target.path).is_absolute()
    assert session.snapshot == previous
    assert (
        not destination.exists()
    )  # Admission uses backend receipt, never disk inference.


def test_no_completion_permission_from_unknown_publication_or_idle_session(tmp_path):
    idle = ApplicationSession()
    for action in OPEN_ACTIONS:
        assert idle.admit_completion_action(action, idle.diagnostic_generation) is None
    assert idle.check_published_vault(idle.diagnostic_generation).effects == ()

    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    effect = session.dispatch(ConvertCommand()).effects[0]
    destination = tmp_path / "Fresh vault"
    destination.mkdir()
    (destination / "MIGRATION REPORT.md").write_text("not proof", encoding="utf-8")
    session.dispatch(
        ApplyTransportFailure(
            request_id=effect.request.request_id,
            phase="may_have_executed",
            code="worker_failure",
        )
    )
    assert session.snapshot.publication.state == "unknown"
    for action in OPEN_ACTIONS:
        assert action not in session.snapshot.allowed_actions
        assert (
            session.admit_completion_action(action, session.diagnostic_generation)
            is None
        )
    assert session.check_published_vault(session.diagnostic_generation).effects == ()
    assert (destination / "MIGRATION REPORT.md").read_text(
        encoding="utf-8"
    ) == "not proof"


def test_explicit_published_check_atomically_selects_receipt_destination(tmp_path):
    session, destination = published_session(tmp_path)
    generation = session.diagnostic_generation
    # Existing independent selection must not divert the result-area action.
    session.dispatch(SelectVault(path_or_null=str(tmp_path / "independent")))
    generation = session.diagnostic_generation
    started = session.check_published_vault(generation)

    assert started.snapshot.vault == str(destination)
    assert started.snapshot.busy_operation == "check_vault"
    assert len(started.effects) == 1
    effect = started.effects[0]
    assert effect.request.operation == "check_vault"
    assert effect.request.arguments.vault == str(destination)
    assert session.check_published_vault(generation).effects == ()
    assert session.snapshot.publication.receipt_verified
    result = check_vault(destination)
    finished = complete(session, effect, result, 1)
    assert finished.snapshot.result.status == "check_failed"
    assert finished.snapshot.publication.receipt_verified
    assert "open_folder" in finished.snapshot.allowed_actions
    assert session.admit_completion_action("open_folder", session.diagnostic_generation)


def test_stale_busy_and_closed_completion_intents_do_not_dispatch(tmp_path):
    session, destination = published_session(tmp_path)
    stale = session.diagnostic_generation
    session.dispatch(SelectVault(path_or_null=str(tmp_path / "other")))
    for action in OPEN_ACTIONS:
        assert session.admit_completion_action(action, stale) is None
    assert session.check_published_vault(stale).effects == ()
    current = session.diagnostic_generation
    started = session.check_published_vault(current)
    for action in OPEN_ACTIONS:
        assert (
            session.admit_completion_action(action, session.diagnostic_generation)
            is None
        )
    closing = session.dispatch(SimpleCommand(command="request_close"))
    assert closing.snapshot.close_pending
    result = check_vault(destination)
    done = complete(session, started.effects[0], result, 1)
    assert [effect.effect for effect in done.effects] == ["close_window"]
    for action in OPEN_ACTIONS:
        assert (
            session.admit_completion_action(action, session.diagnostic_generation)
            is None
        )
    assert session.check_published_vault(session.diagnostic_generation).effects == ()


def test_completion_host_admission_rejects_invalid_generation_and_action():
    session = ApplicationSession()
    for generation in (True, -1, "0", 1.5):
        with pytest.raises(ValueError):
            session.admit_completion_action("open_folder", generation)
        with pytest.raises(ValueError):
            session.check_published_vault(generation)
    with pytest.raises(ValueError):
        session.admit_completion_action("copy_details", session.diagnostic_generation)


def test_empty_independent_selection_requires_explicit_published_check(tmp_path):
    session, destination = published_session(tmp_path)
    previous = session.snapshot
    generation = session.diagnostic_generation
    assert previous.vault is None
    assert not previous.can_check_selected_vault
    assert "check_vault" in previous.allowed_actions

    rejected = session.dispatch(SimpleCommand(command="check_vault"))

    assert rejected.effects == ()
    assert rejected.snapshot == previous
    assert session.diagnostic_generation == generation
    explicit = session.check_published_vault(generation)
    assert explicit.snapshot.vault == str(destination)
    assert explicit.effects[0].request.arguments.vault == str(destination)
