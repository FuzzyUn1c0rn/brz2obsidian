"""Recovery controls render backend admission and retain honest outcome facts."""

import os
from threading import Event
from time import monotonic

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QTabBar

from brz2obsidian.application.contracts import (
    ApplyTransportFailure,
    ConvertCommand,
    SelectVault,
    SimpleCommand,
    WorkerResponse,
)
from brz2obsidian.application.operations import (
    check_vault,
    convert_reviewed,
    inspect,
    validate_destination,
)
from brz2obsidian.application.transport import Terminal
from brz2obsidian_ui.platform_actions import DiagnosticActions
from brz2obsidian_ui.window import MainWindow
from tests.application.test_conversion_recovery import complete, inventory, operation
from tests.application.test_conversion_session import ready_session
from tests.application.test_minimal_workflow import make_archive

pytestmark = pytest.mark.gui


def until(app, condition):
    deadline = monotonic() + 10
    while not condition():
        app.processEvents()
        if monotonic() > deadline:
            pytest.fail("GUI condition did not complete")


def button(window, accessible):
    return next(
        widget
        for widget in window.findChildren(QPushButton)
        if widget.accessibleName() == accessible and widget.isVisible()
    )


def text(window):
    return "\n".join(
        label.text() for label in window.findChildren(QLabel) if label.isVisible()
    )


def finish(app, window):
    window.close()
    until(app, lambda: not window.isVisible())
    window.shutdown()


def test_published_ui_requires_new_attempt_before_editing_and_creates_another_vault(
    tmp_path,
):
    app = QApplication.instance() or QApplication([])
    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    effect = operation(session.dispatch(ConvertCommand()))
    result = convert_reviewed(
        source, tmp_path, "Fresh vault", effect.request.arguments.reviewed
    )
    complete(session, effect, result)
    original = inventory(tmp_path / "Fresh vault")
    window = MainWindow(session=session)
    window.show()
    try:
        window.submit(SimpleCommand(command="carry_inspection_to_convert"))
        until(app, lambda: window.snapshot.publication is not None)
        assert str(tmp_path / "Fresh vault") in text(window)
        button(window, "Start another conversion").click()
        until(app, lambda: window.snapshot.publication is None)
        assert window.snapshot.source == str(source)
        name = next(
            field
            for field in window.findChildren(QLineEdit)
            if field.accessibleName() == "Vault name"
        )
        assert name.isEnabled() and name.text() == ""
        button(window, "Inspect archive").click()
        until(app, lambda: window.snapshot.reviewed is not None)
        name.setFocus()
        QTest.keyClicks(name, "Another vault")
        until(app, lambda: "convert" in window.snapshot.allowed_actions)
        button(window, "Convert").click()
        until(app, lambda: window.snapshot.publication is not None)
        assert window.snapshot.publication.receipt_verified, window.snapshot.result
        assert window.snapshot.destination == str(tmp_path / "Another vault")
        assert inventory(tmp_path / "Fresh vault") == original
    finally:
        finish(app, window)


def test_unknown_ui_acknowledgment_retains_path_during_edits_and_failed_exports(
    tmp_path,
):
    app = QApplication.instance() or QApplication([])
    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    effect = operation(session.dispatch(ConvertCommand()))
    session.dispatch(
        ApplyTransportFailure(
            request_id=effect.request.request_id,
            phase="may_have_executed",
            code="worker_failure",
        )
    )
    publication = session.snapshot.publication
    entered, release = Event(), Event()
    copied = []

    class ControlledSupervisor:
        def run(self, request):
            if request.operation == "validate_destination":
                entered.set()
                assert release.wait(10)
                result = validate_destination(tmp_path, request.arguments.vault_name)
            else:
                assert request.operation == "inspect"
                result = inspect(source)
            return Terminal(
                phase="completed",
                process_status=0,
                response=WorkerResponse(
                    request_id=request.request_id,
                    operation=request.operation,
                    result=result,
                ),
            )

    def denied_clipboard(report, owner):
        copied.append(report)
        raise OSError("Synthetic unavailable clipboard")

    class SaveDialog:
        def save_report(self, callback):
            self.callback = callback

    dialogs = SaveDialog()

    window = MainWindow(
        session=session,
        supervisor=ControlledSupervisor(),
        diagnostic_actions=DiagnosticActions(clipboard=denied_clipboard),
        dialogs=dialogs,
    )
    window.show()
    try:
        window.submit(SimpleCommand(command="carry_inspection_to_convert"))
        until(app, lambda: window.snapshot.publication is not None)
        assert "Publication status unknown" in text(window)
        name = next(
            field
            for field in window.findChildren(QLineEdit)
            if field.accessibleName() == "Vault name"
        )
        assert not name.isEnabled()
        button(window, "I reviewed the destination").click()
        until(app, entered.is_set)
        until(app, lambda: window.snapshot.destination_review_acknowledged)
        painted = []
        QTimer.singleShot(0, lambda: painted.append(not window.grab().isNull()))
        name.setFocus()
        name.selectAll()
        QTest.keyClicks(name, "Corrected")
        until(app, lambda: window.snapshot.vault_name == "Corrected" and bool(painted))
        assert not release.is_set()
        assert publication.destination in text(window)
        assert window.snapshot.publication == publication
        release.set()
        until(
            app,
            lambda: (
                window.snapshot.destination_validation is not None
                and not window.snapshot.validation_request_id
            ),
        )
        assert "convert" not in window.snapshot.allowed_actions
        button(window, "Inspect again").click()
        until(app, lambda: window.snapshot.reviewed is not None)
        assert publication.destination in text(window)
        assert "Publication status unknown" in text(window)
        assert "convert" in window.snapshot.allowed_actions
        button(window, "Diagnostic details").click()
        button(window, "Copy details").click()
        until(
            app,
            lambda: (
                bool(copied)
                and any(
                    label.accessibleName() == "Diagnostic action feedback"
                    and "could not" in label.text().lower()
                    for label in window.findChildren(QLabel)
                )
            ),
        )
        assert "Operation: inspect" in copied[0]
        assert "Operation: convert_reviewed" not in copied[0]
        assert window.snapshot.publication == publication
        assert publication.destination in text(window)
        button(window, "Save diagnostic report").click()
        dialogs.callback(str(tmp_path))  # A directory cannot be replaced by a report.
        until(
            app,
            lambda: any(
                label.accessibleName() == "Diagnostic action feedback"
                and "could not be saved" in label.text().lower()
                for label in window.findChildren(QLabel)
            ),
        )
        assert window.snapshot.publication == publication
        assert publication.destination in text(window)
    finally:
        release.set()
        finish(app, window)


@pytest.mark.parametrize("close_pending", [False, True])
def test_retry_control_validates_without_automatic_conversion_or_close_side_effects(
    tmp_path, close_pending
):
    app = QApplication.instance() or QApplication([])
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
    entered, release = Event(), Event()
    operations = []

    class ControlledSupervisor:
        def run(self, request):
            operations.append(request.operation)
            if request.operation == "validate_destination":
                entered.set()
                assert release.wait(10)
                result = validate_destination(tmp_path, "Fresh vault")
            else:
                assert request.operation == "convert_reviewed"
                result = convert_reviewed(
                    source, tmp_path, "Fresh vault", request.arguments.reviewed
                )
            return Terminal(
                phase="completed",
                process_status=0,
                response=WorkerResponse(
                    request_id=request.request_id,
                    operation=request.operation,
                    result=result,
                ),
            )

    window = MainWindow(session=session, supervisor=ControlledSupervisor())
    window.show()
    try:
        window.submit(SimpleCommand(command="carry_inspection_to_convert"))
        until(app, lambda: window.snapshot.publication is not None)
        button(window, "Retry conversion").click()
        until(app, entered.is_set)
        until(app, lambda: window.snapshot.validation_request_id is not None)
        if close_pending:
            window.close()
            until(app, lambda: window.snapshot.close_pending)
            assert window.isVisible()
        release.set()
        until(app, lambda: not window.snapshot.validation_request_id)
        assert operations == ["validate_destination"]
        assert not (tmp_path / "Fresh vault").exists()
        if close_pending:
            until(app, lambda: not window.isVisible())
        else:
            button(window, "Convert").click()
            until(app, lambda: window.snapshot.publication.receipt_verified)
            assert operations == ["validate_destination", "convert_reviewed"]
    finally:
        release.set()
        finish(app, window)


def test_checker_retry_button_does_not_start_another_conversion(tmp_path):
    app = QApplication.instance() or QApplication([])
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
    original = inventory(tmp_path / "Fresh vault")
    checked = tmp_path / "Independent check"
    checked.mkdir()
    (checked / "Manual.md").write_text("![[Missing.png]]", encoding="utf-8")
    session.dispatch(SelectVault(path_or_null=str(checked)))
    effect = operation(session.dispatch(SimpleCommand(command="check_vault")))
    complete(session, effect, check_vault(checked), 2)
    called = Event()

    class Checker:
        def run(self, request):
            assert request.operation == "check_vault"
            called.set()
            return Terminal(
                phase="completed",
                process_status=2,
                response=WorkerResponse(
                    request_id=request.request_id,
                    operation=request.operation,
                    result=check_vault(checked),
                ),
            )

    window = MainWindow(session=session, supervisor=Checker())
    window.show()
    try:
        window.submit(SimpleCommand(command="carry_inspection_to_convert"))
        until(app, lambda: window.snapshot.publication is not None)
        tabs = next(
            tab
            for tab in window.findChildren(QTabBar)
            if tab.accessibleName() == "Operation"
        )
        tabs.setCurrentIndex(2)
        button(window, "Retry check").click()
        until(app, lambda: called.is_set() or window.snapshot.publication is None)
        assert called.is_set()
        assert window.snapshot.publication == publication
        assert inventory(tmp_path / "Fresh vault") == original
    finally:
        finish(app, window)
