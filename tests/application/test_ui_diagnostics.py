"""Safe report lifetime and admission through the public host session."""

from pathlib import Path

from brz2obsidian.application.contracts import ApplyResult, InspectCommand, SelectSource
from brz2obsidian.application.operations import ApplicationSession, inspect

SOURCE = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()


def complete_inspection(session, text="Safe report\n"):
    if session.snapshot.source is None:
        session.dispatch(SelectSource(path_or_null=str(SOURCE)))
    started = session.dispatch(InspectCommand()).effects[0]
    result = inspect(SOURCE).model_copy(update={"diagnostic_text": text})
    return session.dispatch(
        ApplyResult(
            request_id=started.request.request_id,
            input_revision=started.input_revision,
            result=result,
            process_status=0,
        )
    )


def test_repeated_inspection_expires_prior_report_at_same_input_revision():
    session = ApplicationSession()
    complete_inspection(session, "First report\n")
    generation, revision = session.diagnostic_generation, session.snapshot.revision
    assert (
        session.admit_diagnostic_report("copy_details", generation) == "First report\n"
    )

    complete_inspection(session, "Second report\n")

    assert session.snapshot.revision == revision
    assert session.diagnostic_generation > generation
    assert session.admit_diagnostic_report("save_diagnostic_report", generation) is None
    assert session.diagnostics_page_if_current(generation) is None
    assert (
        session.admit_diagnostic_report("copy_details", session.diagnostic_generation)
        == "Second report\n"
    )
    current = session.diagnostic_generation
    complete_inspection(session, "Second report\n")
    assert session.diagnostic_generation > current
    assert session.admit_diagnostic_report("copy_details", current) is None


def test_source_change_and_close_expire_current_diagnostics(tmp_path):
    from brz2obsidian.application.contracts import SimpleCommand

    session = ApplicationSession()
    complete_inspection(session)
    generation = session.diagnostic_generation
    session.dispatch(SelectSource(path_or_null=str(tmp_path / "other.brz")))
    assert session.admit_diagnostic_report("copy_details", generation) is None
    assert session.diagnostics_text() == ""
    assert session.snapshot.result is None

    complete_inspection(session)
    generation = session.diagnostic_generation
    session.dispatch(SimpleCommand(command="request_close"))
    assert session.admit_diagnostic_report("copy_details", generation) is None
    assert session.diagnostics_page_if_current(session.diagnostic_generation) is None
    assert session.diagnostics_text() == ""
    assert session.snapshot.result.diagnostic_text == ""


def test_unsafe_or_invalid_diagnostic_admission_is_rejected():
    import pytest

    session = ApplicationSession()
    complete_inspection(session)
    for generation in (True, -1, 1.5, "1"):
        with pytest.raises(ValueError):
            session.admit_diagnostic_report("copy_details", generation)
        with pytest.raises(ValueError):
            session.diagnostics_page_if_current(generation)
    with pytest.raises(ValueError):
        session.admit_diagnostic_report("inspect", session.diagnostic_generation)
    generation = session.diagnostic_generation
    session.dispatch(InspectCommand())
    assert session.admit_diagnostic_report("copy_details", generation) is None
    assert (
        session.admit_diagnostic_report("copy_details", session.diagnostic_generation)
        is None
    )


def test_complete_report_is_exportable_without_rendering_its_bounded_pages(tmp_path):
    from brz2obsidian_ui.platform_actions import DiagnosticActions

    session = ApplicationSession()
    report = (
        "Operation: inspect\n" + "Safe finding café 雪\n" * 400 + "Final guidance\n"
    )
    complete_inspection(session, report)
    generation = session.diagnostic_generation
    first = session.diagnostics_page_if_current(generation)
    assert len(first.lines) == 100
    assert first.next_offset is not None
    assert len(first.text.encode("utf-8")) <= 32768
    destination = tmp_path / "safe report.txt"
    text = session.admit_diagnostic_report("save_diagnostic_report", generation)
    assert DiagnosticActions().save_report(text, destination).succeeded
    assert destination.read_bytes() == report.encode("utf-8")


def test_explicit_omission_survives_complete_copy_and_utf8_save(tmp_path):
    from brz2obsidian.application.contracts import DiagnosticOmission
    from brz2obsidian_ui.platform_actions import DiagnosticActions

    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=str(SOURCE)))
    effect = session.dispatch(InspectCommand()).effects[0]
    text = "Operation: inspect\nOutcome: warnings\n17 diagnostic findings omitted; reason: response_limit.\nReview the export.\n"
    original = inspect(SOURCE)
    result = original.model_copy(
        update={
            "diagnostic_text": text,
            "diagnostic_omission": DiagnosticOmission(findings_count=17),
        }
    )
    session.dispatch(
        ApplyResult(
            request_id=effect.request.request_id,
            input_revision=effect.input_revision,
            result=result,
            process_status=0,
        )
    )
    copied = []
    actions = DiagnosticActions(clipboard=lambda report, owner: copied.append(report))
    generation = session.diagnostic_generation
    assert actions.copy_report(
        session.admit_diagnostic_report("copy_details", generation), 123
    ).succeeded
    destination = tmp_path / "omission.txt"
    assert actions.save_report(
        session.admit_diagnostic_report("save_diagnostic_report", generation),
        destination,
    ).succeeded
    assert copied == [text]
    assert destination.read_bytes() == text.encode("utf-8")
    assert session.snapshot.result.diagnostic_omission.findings_count == 17


def test_worker_failure_report_identity_expires_even_when_result_remains_null():
    from brz2obsidian.application.contracts import ApplyTransportFailure

    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=str(SOURCE)))
    tokens = []
    for _ in range(2):
        effect = session.dispatch(InspectCommand()).effects[0]
        session.dispatch(
            ApplyTransportFailure(
                request_id=effect.request.request_id,
                phase="not_started",
                code="launch_failure",
            )
        )
        assert session.snapshot.result is None
        tokens.append(session.diagnostic_generation)
    assert tokens[1] > tokens[0]
    assert session.admit_diagnostic_report("copy_details", tokens[0]) is None
    assert "launch_failure" in session.admit_diagnostic_report(
        "copy_details", tokens[1]
    )


def test_report_survives_actual_worker_exit_and_exports_on_outer_thread(tmp_path):
    import sys
    from threading import Event, get_ident

    from brz2obsidian.application.runner import HostRunner
    from brz2obsidian.application.transport import Supervisor
    from brz2obsidian_ui.platform_actions import DiagnosticActions

    completed, exported = Event(), Event()
    presented, feedback = [], []
    main_thread = get_ident()

    def on_update(prepared):
        presented.append(prepared)
        if prepared.update.snapshot.result is not None:
            completed.set()

    def on_feedback(outcome):
        feedback.append(outcome)
        exported.set()

    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=str(SOURCE)))
    runner = HostRunner(
        Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src"),
        on_update,
        lambda page: None,
        session=session,
        on_diagnostic_feedback=on_feedback,
    )
    destination = tmp_path / "worker-report.txt"
    threads = []

    def save(text):
        threads.append(get_ident())
        return DiagnosticActions().save_report(text, destination)

    try:
        runner.submit(InspectCommand())
        assert completed.wait(10)
        assert session.snapshot.active_request_id is None
        generation = session.diagnostic_generation
        expected = inspect(SOURCE).diagnostic_text
        assert session.diagnostics_text() == expected
        runner.request_diagnostic_export("save_diagnostic_report", generation, save)
        assert exported.wait(10)
        assert feedback[0].succeeded
        assert threads[0] != main_thread
        assert destination.read_bytes() == expected.encode("utf-8")
        assert presented[-1].diagnostic_generation == generation
    finally:
        runner.shutdown()


def test_selecting_checker_vault_expires_the_current_inspection_report(tmp_path):
    from brz2obsidian.application.contracts import SelectVault, SimpleCommand

    session = ApplicationSession()
    complete_inspection(session)
    generation = session.diagnostic_generation
    session.dispatch(SelectVault(path_or_null=str(tmp_path)))
    assert session.diagnostic_generation > generation
    assert session.admit_diagnostic_report("save_diagnostic_report", generation) is None
    assert session.diagnostics_text() == ""
    generation = session.diagnostic_generation
    session.dispatch(SimpleCommand(command="check_vault"))
    assert session.diagnostic_generation > generation
    assert session.admit_diagnostic_report("copy_details", generation) is None


def test_safe_inspection_report_includes_plain_language_guidance():
    report = inspect(SOURCE).diagnostic_text
    assert (
        "Guidance: Review the planned contents and pending checks before conversion."
        in report
    )
    assert "Counts are planned; actual publication counts are unavailable." in report
    assert "actual_notes: unavailable" in report
