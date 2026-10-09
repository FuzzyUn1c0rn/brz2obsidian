"""Completion intent through the non-GUI runner and real outer adapter."""

from threading import Event, get_ident
from types import SimpleNamespace

import pytest

from brz2obsidian.application.contracts import SelectVault
from brz2obsidian.application.runner import HostRunner
from tests.application.test_completion_session import published_session

platform_actions = pytest.importorskip("brz2obsidian_ui.platform_actions")
CompletionActions, CompletionOutcome = (
    platform_actions.CompletionActions,
    platform_actions.CompletionOutcome,
)


def test_completion_runner_uses_background_current_target_and_safe_feedback_path(
    tmp_path,
):
    session, destination = published_session(tmp_path)
    received, feedback = [], []
    finished = Event()
    main_thread = get_ident()

    def perform(target, admit):
        received.append((target, get_ident(), admit()))
        return CompletionOutcome(
            True, "Opening requested.", "not backend-authoritative"
        )

    def completed(value):
        feedback.append(value)
        finished.set()

    runner = HostRunner(
        SimpleNamespace(),
        lambda update: None,
        lambda page: None,
        session=session,
        on_completion_feedback=completed,
    )
    try:
        runner.request_completion_action(
            "open_folder", session.diagnostic_generation, perform
        )
        assert finished.wait(5)
        target, thread, allowed = received[0]
        assert allowed and thread != main_thread
        assert target.path == str(destination)
        assert feedback[0].succeeded
        assert feedback[0].path == str(destination)
        assert session.snapshot.result.status == "conversion_created"
        assert "open_in_obsidian" in session.snapshot.allowed_actions
    finally:
        runner.shutdown()


@pytest.mark.parametrize("failure", [False, True])
def test_obsidian_feedback_uses_admitted_folder_despite_untrusted_adapter_path(
    tmp_path, failure
):
    session, destination = published_session(tmp_path)
    feedback, received = [], []
    finished = Event()

    def perform(target, admit):
        received.append((target.path, admit(), get_ident()))
        if failure:
            raise OSError("PRIVATE native error")
        return CompletionOutcome(True, "Vault manager requested.", "untrusted path")

    def completed(value):
        feedback.append(value)
        finished.set()

    runner = HostRunner(
        SimpleNamespace(),
        lambda update: None,
        lambda page: None,
        session=session,
        on_completion_feedback=completed,
    )
    previous = session.snapshot.result
    try:
        runner.request_completion_action(
            "open_in_obsidian", session.diagnostic_generation, perform
        )
        assert finished.wait(5)
        path, admitted, thread = received[0]
        assert path == str(destination / "MIGRATION REPORT.md")
        assert admitted and thread != get_ident()
        assert feedback[0].path == str(destination)
        assert feedback[0].succeeded is not failure
        assert "PRIVATE" not in feedback[0].message
        assert session.snapshot.result is previous
        assert session.snapshot.publication.receipt_verified
    finally:
        runner.shutdown()


def test_runner_rejects_stale_permission_after_blocked_filesystem_check(
    tmp_path, monkeypatch
):
    import os
    from pathlib import Path

    session, destination = published_session(tmp_path)
    destination.mkdir()
    report = destination / "MIGRATION REPORT.md"
    report.write_bytes(b"generated report")
    started, release, finished = Event(), Event(), Event()
    original_isfile = os.path.isfile
    launched, feedback = [], []

    def blocked_isfile(path):
        if Path(path) == report:
            started.set()
            assert release.wait(5)
        return original_isfile(path)

    monkeypatch.setattr(os.path, "isfile", blocked_isfile)
    actions = CompletionActions(launch=launched.append)

    def completed(value):
        feedback.append(value)
        finished.set()

    runner = HostRunner(
        SimpleNamespace(),
        lambda update: None,
        lambda page: None,
        session=session,
        on_completion_feedback=completed,
    )
    generation = session.diagnostic_generation
    try:
        runner.request_completion_action(
            "open_migration_report",
            generation,
            lambda target, admit: actions.open_report(target.path, admit=admit),
        )
        assert started.wait(5)
        session.dispatch(SelectVault(path_or_null=str(tmp_path / "independent")))
        release.set()
        assert finished.wait(5)
        assert launched == []
        assert not feedback[0].succeeded and feedback[0].generation == generation
        assert session.snapshot.publication.receipt_verified
        assert report.read_bytes() == b"generated report"
    finally:
        release.set()
        runner.shutdown()


def test_runner_denies_stale_intent_before_adapter_and_safely_contains_adapter_error(
    tmp_path,
):
    session, destination = published_session(tmp_path)
    generation = session.diagnostic_generation
    session.dispatch(SelectVault(path_or_null=str(tmp_path / "independent")))
    calls, feedback = [], []
    finished = Event()

    def perform(target, admit):
        calls.append(target)
        raise OSError("PRIVATE native failure canary")

    def completed(value):
        feedback.append(value)
        finished.set()

    runner = HostRunner(
        SimpleNamespace(),
        lambda update: None,
        lambda page: None,
        session=session,
        on_completion_feedback=completed,
    )
    try:
        runner.request_completion_action("open_folder", generation, perform)
        assert finished.wait(5)
        assert calls == [] and not feedback[0].succeeded
        finished.clear()
        runner.request_completion_action(
            "open_folder", session.diagnostic_generation, perform
        )
        assert finished.wait(5)
        assert len(calls) == 1
        assert not feedback[-1].succeeded
        assert "PRIVATE" not in feedback[-1].message
        assert feedback[-1].path == str(destination)
        assert session.snapshot.publication.receipt_verified
        assert "open_in_obsidian" in session.snapshot.allowed_actions
    finally:
        runner.shutdown()
