"""Diagnostic disclosure and explicit exports through the injected UI seam."""

import os
from pathlib import Path
from threading import Event
from time import monotonic

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent, QSettings, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QTextEdit

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


def test_readonly_diagnostics_allow_partial_keyboard_selection():
    app = QApplication.instance() or QApplication([])
    window = inspected(app, "Safe diagnostics café 😀 tail")
    try:
        window.disclosure.click()
        window.diagnostic_text.setFocus()
        QTest.keyClick(
            window.diagnostic_text, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier
        )
        for _ in "tail":
            QTest.keyClick(
                window.diagnostic_text,
                Qt.Key.Key_Left,
                Qt.KeyboardModifier.ShiftModifier,
            )
        assert window.diagnostic_text.isReadOnly()
        assert window.diagnostic_text.textCursor().selectedText() == "tail"
    finally:
        finish(app, window)


def test_save_dialog_starts_in_absolute_home_independently_of_working_directory(
    tmp_path,
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    previous_native = app.testAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    previous_format = QSettings.defaultFormat()
    previous_ini_root = Path(
        QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            "brz2obsidian-test-probe",
            "save-dialog",
        ).fileName()
    ).parent.parent
    app.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_path / "qt-settings"),
    )
    unrelated = tmp_path / "Unrelated working folder café"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    window = inspected(app, "Safe complete report\n")
    dialog = None
    try:
        window.disclosure.click()
        result, findings = window.snapshot.result, window.findings.toPlainText()
        window.save.setFocus()
        QTest.keyClick(window.save, Qt.Key.Key_Space)
        dialog = window.findChild(QFileDialog)
        assert dialog is not None and dialog.isVisible()
        expected = Path.home()
        assert expected.is_absolute() and expected != unrelated
        assert Path(dialog.directory().absolutePath()) == expected
        assert [Path(path) for path in dialog.selectedFiles()] == [
            expected / "brz2obsidian-diagnostic-report.txt"
        ]
        assert dialog.acceptMode() == QFileDialog.AcceptMode.AcceptSave
        assert dialog.defaultSuffix() == "txt"
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        until(app, window.save.isEnabled)
        assert window.save.hasFocus()
        assert (
            window.snapshot.result is result
            and window.findings.toPlainText() == findings
        )
        assert "canceled" in window.diagnostic_feedback.text()
        assert list(unrelated.iterdir()) == []
    finally:
        pending_dialog = window.findChild(QFileDialog)
        if pending_dialog is not None:
            if pending_dialog.isVisible():
                pending_dialog.reject()
            pending_dialog.deleteLater()
            app.sendPostedEvents(pending_dialog, QEvent.Type.DeferredDelete)
        finish(app, window)
        QSettings.setPath(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            str(previous_ini_root),
        )
        QSettings.setDefaultFormat(previous_format)
        app.setAttribute(
            Qt.ApplicationAttribute.AA_DontUseNativeDialogs, previous_native
        )


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
        result, findings = window.snapshot.result, window.findings.toPlainText()
        window.save.click()
        dialogs.callback(None)
        app.processEvents()
        assert window.save.hasFocus()
        assert "canceled" in window.diagnostic_feedback.text()
        assert window.snapshot.result is result
        window.copy.click()
        until(app, lambda: "could not be copied" in window.diagnostic_feedback.text())
        assert "CANARY" not in window.diagnostic_feedback.text()
        assert window.findings.toPlainText() == findings
        window.save.click()
        dialogs.callback(str(tmp_path / "absent" / "report.txt"))
        until(app, lambda: "could not be saved" in window.diagnostic_feedback.text())
        assert window.snapshot.result is result
        assert window.findings.toPlainText() == findings
        assert not list(tmp_path.iterdir())
    finally:
        finish(app, window)


@pytest.mark.parametrize("operation", ["inspection", "conversion", "check"])
@pytest.mark.parametrize("failure", ["replace", "outer_exception"])
def test_failed_save_keeps_exact_copyable_target_and_current_result(
    tmp_path, monkeypatch, operation, failure
):
    app = QApplication.instance() or QApplication([])
    destination = (
        tmp_path
        / "Été destination with a long selected folder name and spaces"
        / "Diagnostic report with readable Unicode 雪 and spaces.txt"
    )
    destination.parent.mkdir()
    destination.write_bytes(b"Previous report remains")

    def denied(source, target):
        raise PermissionError("PRIVATE exception canary")

    monkeypatch.setattr("os.replace", denied)
    dialogs = SaveDialog()

    class UnexpectedSave(DiagnosticActions):
        def save_report(self, text, destination):
            raise OSError("PRIVATE exception canary")

    options = {
        "dialogs": dialogs,
        "diagnostic_actions": DiagnosticActions()
        if failure == "replace"
        else UnexpectedSave(),
    }
    if operation == "inspection":
        window = inspected(app, "Safe complete report\n", **options)
    else:
        from brz2obsidian.application.contracts import (
            ApplyResult,
            SelectVault,
            SimpleCommand,
        )
        from brz2obsidian.application.operations import ApplicationSession, check_vault
        from tests.application.test_completion_session import published_session

        if operation == "conversion":
            prepared = tmp_path / "prepared conversion"
            prepared.mkdir()
            session, _ = published_session(prepared)
        else:
            vault = tmp_path / "checked vault"
            vault.mkdir()
            (vault / "Manual.md").write_text("# Safe manual\n", encoding="utf-8")
            session = ApplicationSession()
            session.dispatch(SelectVault(path_or_null=str(vault)))
            effect = session.dispatch(SimpleCommand(command="check_vault")).effects[0]
            session.dispatch(
                ApplyResult(
                    request_id=effect.request.request_id,
                    input_revision=effect.input_revision,
                    result=check_vault(vault),
                    process_status=0,
                )
            )
        window = MainWindow(session=session, **options)
        window.show()
        if operation == "check":
            window.tabs.setCurrentIndex(2)
        window.submit(SelectVault(path_or_null=None))
        until(app, lambda: window.snapshot.result is not None)
    window.resize(453, 850)
    try:
        window.disclosure.click()
        result = window.snapshot.result
        findings = window.findings.toPlainText()
        actions = window.snapshot.allowed_actions
        window.save.click()
        dialogs.callback(str(destination))
        until(app, lambda: "could not" in window.diagnostic_feedback.text())
        path = next(
            (
                widget
                for widget in window.findChildren(QTextEdit)
                if widget.isVisible() and widget.toPlainText() == str(destination)
            ),
            None,
        )
        assert path is not None, "Failed Save must show its exact selectable target"
        assert path.isReadOnly()
        path.setFocus()
        QTest.keyClick(path, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        assert path.textCursor().selectedText() == str(destination)
        assert path.createMimeDataFromSelection().text() == str(destination)
        visible = "\n".join(widget.text() for widget in window.findChildren(QLabel))
        visible += "\n".join(
            widget.toPlainText() for widget in window.findChildren(QTextEdit)
        )
        assert "PRIVATE" not in visible
        assert window.snapshot.result is result
        assert window.snapshot.allowed_actions == actions
        assert window.findings.toPlainText() == findings
        assert window.copy.isEnabled() and window.save.isEnabled()
        assert destination.read_bytes() == b"Previous report remains"
        assert list(destination.parent.iterdir()) == [destination]
    finally:
        finish(app, window)


@pytest.mark.parametrize(
    "next_action", ["copy", "cancel", "save", "new_result", "identical_result"]
)
def test_save_failure_target_expires_for_the_next_action_or_result(
    tmp_path, next_action
):
    app = QApplication.instance() or QApplication([])
    dialogs = SaveDialog()
    copied = []
    supervisor = PreparedSupervisor("Current safe report\n")
    window = inspected(
        app,
        supervisor.text,
        supervisor=supervisor,
        dialogs=dialogs,
        diagnostic_actions=DiagnosticActions(
            clipboard=lambda text, owner: copied.append(text)
        ),
    )
    try:
        window.disclosure.click()
        old_result = window.snapshot.result
        window.save.click()
        target = tmp_path / "absent Café" / "old target 雪.txt"
        dialogs.callback(str(target))
        until(app, lambda: "could not be saved" in window.diagnostic_feedback.text())
        path = next(
            widget
            for widget in window.findChildren(QTextEdit)
            if widget.toPlainText() == str(target)
        )
        assert path.isVisible()
        if next_action == "copy":
            window.copy.click()
            assert path.toPlainText() == "" and not path.isVisible()
            until(app, lambda: bool(copied))
            assert copied == ["Current safe report\n"]
            until(app, lambda: "copied" in window.diagnostic_feedback.text())
        elif next_action in {"cancel", "save"}:
            window.save.click()
            assert path.toPlainText() == "" and not path.isVisible()
            destination = (
                tmp_path / "new report 雪.txt" if next_action == "save" else None
            )
            dialogs.callback(str(destination) if destination else None)
            until(
                app,
                lambda: (
                    ("saved" if destination else "canceled")
                    in window.diagnostic_feedback.text()
                ),
            )
            if destination:
                assert destination.read_bytes() == b"Current safe report\n"
        else:
            revision = window.snapshot.revision
            if next_action == "new_result":
                supervisor.text = "Replacement safe report\n"
            window.submit(InspectCommand())
            until(
                app,
                lambda: (
                    window.snapshot.result is not old_result
                    and window.snapshot.active_request_id is None
                ),
            )
            assert window.snapshot.revision == revision
            assert (window.snapshot.result == old_result) is (
                next_action == "identical_result"
            )
            assert window.diagnostic_feedback.text() == ""
        assert path.toPlainText() == "" and not path.isVisible()
        assert not target.exists() and not target.parent.exists()
        assert window.copy.isEnabled() and window.save.isEnabled()
        if next_action not in {"new_result", "identical_result"}:
            assert window.snapshot.result is old_result
    finally:
        finish(app, window)


@pytest.mark.parametrize("identical_result", [False, True])
def test_delayed_save_exception_cannot_restore_old_target_after_result_replacement(
    tmp_path, identical_result
):
    app = QApplication.instance() or QApplication([])
    entered, release = Event(), Event()
    delivered = []

    class SlowUnexpectedSave(DiagnosticActions):
        def save_report(self, text, destination):
            entered.set()
            assert release.wait(10)
            raise OSError("PRIVATE delayed exception canary")

    dialogs = SaveDialog()
    supervisor = PreparedSupervisor("Old safe report\n")
    window = inspected(
        app,
        supervisor.text,
        supervisor=supervisor,
        dialogs=dialogs,
        diagnostic_actions=SlowUnexpectedSave(),
    )
    window.diagnostic_action_ready.connect(delivered.append)
    try:
        window.disclosure.click()
        old_result = window.snapshot.result
        revision = window.snapshot.revision
        window.save.click()
        target = tmp_path / "old selected target Café 雪.txt"
        dialogs.callback(str(target))
        until(app, entered.is_set)
        if not identical_result:
            supervisor.text = "New safe report\n"
        window.submit(InspectCommand())
        until(
            app,
            lambda: (
                window.snapshot.result is not old_result
                and window.snapshot.active_request_id is None
            ),
        )
        replacement = window.snapshot.result
        assert window.snapshot.revision == revision
        assert (replacement == old_result) is identical_result
        release.set()
        until(app, lambda: bool(delivered))
        assert delivered[-1].path == str(target)
        assert not any(
            widget.toPlainText() == str(target)
            for widget in window.findChildren(QTextEdit)
        )
        assert window.diagnostic_feedback.text() == ""
        assert window.snapshot.result is replacement
        assert window.copy.isEnabled() and window.save.isEnabled()
        assert not target.exists()
    finally:
        release.set()
        finish(app, window)


@pytest.mark.parametrize("move_focus", [False, True])
@pytest.mark.parametrize("action", ["copy", "save"])
def test_background_export_returns_keyboard_focus_without_overriding_user_navigation(
    tmp_path,
    move_focus,
    action,
):
    app = QApplication.instance() or QApplication([])
    entered, release = Event(), Event()

    def blocked_clipboard(text, owner):
        entered.set()
        assert release.wait(10)

    class SlowActions(DiagnosticActions):
        def save_report(self, text, destination):
            entered.set()
            assert release.wait(10)
            return super().save_report(text, destination)

    dialogs = SaveDialog()

    window = inspected(
        app,
        "Safe complete report\n",
        dialogs=dialogs,
        diagnostic_actions=SlowActions(clipboard=blocked_clipboard),
    )
    try:
        window.disclosure.click()
        origin = window.copy if action == "copy" else window.save
        origin.setFocus()
        app.processEvents()
        QTest.keyClick(origin, Qt.Key.Key_Space)
        if action == "save":
            dialogs.callback(str(tmp_path / "report.txt"))
        until(app, entered.is_set)
        if move_focus:
            window.disclosure.setFocus()
            app.processEvents()
        expected = window.disclosure if move_focus else origin
        release.set()
        until(
            app,
            lambda: (
                ("copied" if action == "copy" else "saved")
                in window.diagnostic_feedback.text()
            ),
        )
        assert app.focusWidget() is expected
    finally:
        release.set()
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
        feedback = window.diagnostic_feedback.text()
        old_callback(str(destination))
        assert window.diagnostic_feedback.text() == feedback
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


def test_old_save_callback_preserves_current_export_progress_disabled_actions_and_focus(
    tmp_path,
):
    app = QApplication.instance() or QApplication([])
    entered, release, finished = Event(), Event(), Event()

    def blocked_clipboard(text, owner):
        entered.set()
        assert release.wait(10)
        finished.set()

    dialogs = SaveDialog()
    supervisor = PreparedSupervisor("Old safe report\n")
    window = inspected(
        app,
        supervisor.text,
        dialogs=dialogs,
        supervisor=supervisor,
        diagnostic_actions=DiagnosticActions(clipboard=blocked_clipboard),
    )
    try:
        window.disclosure.click()
        window.save.click()
        old_callback = dialogs.callback
        old_result = window.snapshot.result
        revision = window.snapshot.revision
        supervisor.text = "Current safe report\n"
        window.submit(InspectCommand())
        until(
            app,
            lambda: (
                window.snapshot.result is not old_result
                and window.snapshot.active_request_id is None
            ),
        )
        assert window.snapshot.revision == revision
        window.disclosure.click()
        window.copy.click()
        until(app, entered.is_set)
        progress = window.diagnostic_feedback.text()
        window.disclosure.setFocus()
        focus = window.focusWidget()
        destination = tmp_path / "old-dialog.txt"

        old_callback(str(destination))

        assert window.diagnostic_feedback.text() == progress
        assert not window.copy.isEnabled()
        assert not window.save.isEnabled()
        assert window.focusWidget() is focus
        assert not destination.exists()
        release.set()
        until(app, finished.is_set)
        until(app, lambda: "copied" in window.diagnostic_feedback.text())
    finally:
        release.set()
        finish(app, window)
