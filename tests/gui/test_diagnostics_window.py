"""Diagnostic disclosure and explicit exports through the injected UI seam."""

import os
from pathlib import Path
from threading import Event
from time import monotonic

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from brz2obsidian.application.contracts import (
    InspectCommand,
    SelectSource,
    WorkerResponse,
)
from brz2obsidian.application.operations import inspect
from brz2obsidian.application.transport import Terminal
from brz2obsidian_ui.platform_actions import DiagnosticActions
from brz2obsidian_ui.window import MainWindow

pytestmark = pytest.mark.gui
SOURCE = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()


def until(app, condition):
    deadline = monotonic() + 10
    while not condition():
        app.processEvents()
        if monotonic() > deadline:
            pytest.fail("GUI condition did not complete")


class PreparedSupervisor:
    def __init__(self, text):
        self.text = text

    def run(self, request):
        return Terminal(
            phase="completed",
            process_status=0,
            response=WorkerResponse(
                request_id=request.request_id,
                operation="inspect",
                result=inspect(SOURCE).model_copy(
                    update={"diagnostic_text": self.text}
                ),
            ),
        )


class SaveDialog:
    def save_report(self, callback):
        self.callback = callback


def inspected(app, text, **options):
    supervisor = options.pop("supervisor", PreparedSupervisor(text))
    window = MainWindow(supervisor=supervisor, **options)
    window.show()
    window.submit(SelectSource(path_or_null=str(SOURCE)))
    until(app, lambda: window.snapshot.source is not None)
    window.submit(InspectCommand())
    until(app, lambda: window.snapshot.result is not None)
    return window


def finish(app, window):
    window.close()
    until(app, lambda: not window.isVisible())
    window.shutdown()


def test_disclosure_copy_and_save_export_complete_report_without_rendering_all_pages(
    tmp_path,
):
    app = QApplication.instance() or QApplication([])
    copied = []
    report = (
        "Operation: inspect\n" + "Safe finding café 雪\n" * 300 + "Final guidance\n"
    )
    dialogs = SaveDialog()
    actions = DiagnosticActions(clipboard=lambda text, owner: copied.append(text))
    window = inspected(app, report, dialogs=dialogs, diagnostic_actions=actions)
    try:
        assert not window.diagnostics_expanded
        window.disclosure.click()
        assert window.diagnostics_expanded
        assert window.diagnostic_text.isReadOnly()
        assert len(window.diagnostic_text.toPlainText().splitlines()) <= 100
        assert "Final guidance" not in window.diagnostic_text.toPlainText()
        window.copy.click()
        until(app, lambda: copied == [report])
        until(app, window.save.isEnabled)
        result = window.snapshot.result
        window.save.click()
        destination = tmp_path / "rapport 雪.txt"
        dialogs.callback(str(destination))
        until(app, destination.exists)
        until(app, lambda: "saved" in window.diagnostic_feedback.text())
        assert destination.read_bytes() == report.encode("utf-8")
        assert window.snapshot.result is result
    finally:
        finish(app, window)


def test_save_cancel_and_failed_copy_save_preserve_findings_and_useful_focus(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialogs = SaveDialog()

    def failed_clipboard(text, owner):
        raise OSError("PRIVATE STDERR CANARY")

    window = inspected(
        app,
        "Safe complete report\n",
        dialogs=dialogs,
        diagnostic_actions=DiagnosticActions(clipboard=failed_clipboard),
    )
    try:
        window.disclosure.click()
        result, findings = window.snapshot.result, window.findings.text()
        window.save.click()
        dialogs.callback(None)
        app.processEvents()
        assert window.save.hasFocus()
        assert "canceled" in window.diagnostic_feedback.text()
        assert window.snapshot.result is result
        window.copy.click()
        until(app, lambda: "could not be copied" in window.diagnostic_feedback.text())
        assert "CANARY" not in window.diagnostic_feedback.text()
        assert window.findings.text() == findings
        window.save.click()
        dialogs.callback(str(tmp_path / "absent" / "report.txt"))
        until(app, lambda: "could not be saved" in window.diagnostic_feedback.text())
        assert window.snapshot.result is result
        assert window.findings.text() == findings
        assert not list(tmp_path.iterdir())
    finally:
        finish(app, window)


def test_pending_save_callback_rejects_replaced_result_at_same_input_revision(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialogs = SaveDialog()
    window = inspected(app, "First safe report\n", dialogs=dialogs)
    try:
        window.disclosure.click()
        revision = window.snapshot.revision
        old_result = window.snapshot.result
        window.save.click()
        old_callback = dialogs.callback
        window.submit(InspectCommand())
        until(
            app,
            lambda: (
                window.snapshot.result is not old_result
                and window.snapshot.active_request_id is None
            ),
        )
        assert window.snapshot.revision == revision
        destination = tmp_path / "stale.txt"
        old_callback(str(destination))
        assert "changed" in window.diagnostic_feedback.text()
        assert not destination.exists()
        assert window.save.isEnabled()
    finally:
        finish(app, window)


def test_blocked_report_preparation_processes_input_and_close_before_release():
    from brz2obsidian.application.operations import ApplicationSession

    app = QApplication.instance() or QApplication([])
    entered, release = Event(), Event()
    copied = []

    class SlowPreparation(ApplicationSession):
        def admit_diagnostic_report(self, action, expected_generation):
            entered.set()
            assert release.wait(10)
            return super().admit_diagnostic_report(action, expected_generation)

    window = inspected(
        app,
        "Safe report\n",
        session=SlowPreparation(),
        diagnostic_actions=DiagnosticActions(
            clipboard=lambda text, owner: copied.append(text)
        ),
    )
    try:
        window.disclosure.click()
        window.copy.click()
        until(app, entered.is_set)
        QTimer.singleShot(0, window.disclosure.click)
        until(app, lambda: not window.diagnostics_expanded)
        window.close()
        until(app, lambda: not window.isVisible())
        assert not release.is_set()
        release.set()
        # The report was expired by Close before its delayed admission.
        assert not copied
    finally:
        release.set()
        window.shutdown()


def test_blocked_export_keeps_input_repaint_and_close_responsive(tmp_path):
    app = QApplication.instance() or QApplication([])
    entered, release, finished = Event(), Event(), Event()

    class SlowSave(DiagnosticActions):
        def save_report(self, text, destination):
            entered.set()
            assert release.wait(10)
            outcome = super().save_report(text, destination)
            finished.set()
            return outcome

    dialogs = SaveDialog()
    window = inspected(
        app, "Complete safe report\n", dialogs=dialogs, diagnostic_actions=SlowSave()
    )
    try:
        window.disclosure.click()
        window.save.click()
        destination = tmp_path / "export.txt"
        dialogs.callback(str(destination))
        until(app, entered.is_set)
        QTimer.singleShot(0, window.disclosure.click)
        until(app, lambda: not window.diagnostics_expanded)
        painted = []
        QTimer.singleShot(0, lambda: (window.repaint(), painted.append(True)))
        until(app, lambda: painted)
        window.close()
        until(app, lambda: not window.isVisible())
        assert not release.is_set()
        release.set()
        until(app, finished.is_set)
        assert destination.read_bytes() == b"Complete safe report\n"
    finally:
        release.set()
        window.shutdown()


def test_late_page_callback_does_not_replace_current_report():
    from brz2obsidian.application.operations import ApplicationSession

    app = QApplication.instance() or QApplication([])
    entered, release = Event(), Event()

    class SlowPage(ApplicationSession):
        def diagnostics_page_if_current(self, expected_generation, offset=0, limit=100):
            entered.set()
            assert release.wait(10)
            return super().diagnostics_page_if_current(
                expected_generation, offset, limit
            )

    supervisor = PreparedSupervisor("Old safe line\n" * 250)
    window = inspected(app, supervisor.text, session=SlowPage(), supervisor=supervisor)
    try:
        window.disclosure.click()
        window.next_page.click()
        until(app, entered.is_set)
        old_result = window.snapshot.result
        supervisor.text = "Current safe report\n"
        window.submit(InspectCommand())
        until(
            app,
            lambda: (
                window.snapshot.result is not old_result
                and window.snapshot.active_request_id is None
            ),
        )
        window.disclosure.click()
        assert window.diagnostic_text.toPlainText() == "Current safe report\n"
        release.set()
        app.processEvents()
        assert window.diagnostic_text.toPlainText() == "Current safe report\n"
    finally:
        release.set()
        finish(app, window)


def test_queued_unadmitted_export_does_not_retain_replaced_report(tmp_path):
    from brz2obsidian.application.operations import ApplicationSession

    app = QApplication.instance() or QApplication([])
    entered, release, finished = Event(), Event(), Event()
    copied = []

    def blocked_clipboard(text, owner):
        entered.set()
        assert release.wait(10)
        copied.append(text)
        finished.set()

    supervisor = PreparedSupervisor("First safe report\n")
    session = ApplicationSession()
    window = inspected(
        app,
        supervisor.text,
        supervisor=supervisor,
        session=session,
        diagnostic_actions=DiagnosticActions(clipboard=blocked_clipboard),
    )
    try:
        window.disclosure.click()
        window.copy.click()
        until(app, entered.is_set)
        destination = tmp_path / "queued.txt"
        generation = session.diagnostic_generation
        window.diagnostic_save_selected(generation, str(destination))
        old_result = window.snapshot.result
        supervisor.text = "Replacement report\n"
        window.submit(InspectCommand())
        until(
            app,
            lambda: (
                window.snapshot.result is not old_result
                and window.snapshot.active_request_id is None
            ),
        )
        release.set()
        until(app, finished.is_set)
        # Queue a current export after the stale one to establish both completed.
        window.disclosure.click()
        window.copy.click()
        until(app, lambda: len(copied) == 2)
        assert copied == ["First safe report\n", "Replacement report\n"]
        assert not destination.exists()
        assert "changed" not in window.diagnostic_feedback.text()
        assert window.snapshot.result.diagnostic_text == "Replacement report\n"
    finally:
        release.set()
        finish(app, window)
