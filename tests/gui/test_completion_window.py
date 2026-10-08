"""Published completion actions through the injected MainWindow seam."""

import os
from threading import Event, get_ident

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QTextEdit

from brz2obsidian.application.contracts import SelectVault
from brz2obsidian_ui.platform_actions import CompletionActions
from brz2obsidian_ui.window import MainWindow
from tests.application.test_completion_session import published_session
from tests.gui.test_conversion_window import button, until

pytestmark = pytest.mark.gui


def finish(app, window):
    window.close()
    until(app, lambda: not window.isVisible())
    window.shutdown()


def named_label(window, accessible):
    return next(
        widget
        for widget in window.findChildren(QLabel)
        if widget.accessibleName() == accessible
    )


def path_text(window, accessible):
    return next(
        widget.toPlainText()
        for widget in window.findChildren(QTextEdit)
        if widget.accessibleName() == accessible
    )


@pytest.mark.parametrize("outcome", ["clean", "warnings", "failed"])
def test_published_result_shows_four_explicit_actions_and_retains_result_on_open_failure(
    tmp_path, outcome
):
    app = QApplication.instance() or QApplication([])
    session, destination = published_session(tmp_path, outcome)
    destination.mkdir()
    report = destination / "MIGRATION REPORT.md"
    report.write_bytes(b"generated report")
    requested = []

    def unavailable(target):
        requested.append((target, get_ident()))
        raise OSError("PRIVATE OS error canary")

    window = MainWindow(
        session=session, completion_actions=CompletionActions(launch=unavailable)
    )
    window.show()
    window.submit(SelectVault(path_or_null=None))
    try:
        until(app, lambda: window.snapshot.publication is not None)
        previous = window.snapshot.result
        assert requested == []
        for name in (
            "Open folder",
            "Open migration report",
            "Open in Obsidian",
            "Check published vault",
        ):
            assert button(window, name).isVisible() and button(window, name).isEnabled()
        assert path_text(window, "Published vault path") == str(destination)
        button(window, "Open in Obsidian").click()
        feedback = named_label(window, "Completion action feedback")
        until(app, lambda: "could not be opened" in feedback.text())
        assert "PRIVATE" not in feedback.text()
        assert "Open folder as vault" in feedback.text()
        assert window.snapshot.result is previous
        assert window.snapshot.publication.receipt_verified
        assert path_text(window, "Completion action path") == str(report)
        assert requested[0][0].startswith("obsidian://open?path=")
        assert requested[0][1] != get_ident()
        assert button(window, "Open folder").isEnabled()
        assert button(window, "Check published vault").isEnabled()
        assert report.read_bytes() == b"generated report"
    finally:
        finish(app, window)


def test_missing_report_feedback_leaves_folder_and_check_actions_available(tmp_path):
    app = QApplication.instance() or QApplication([])
    session, destination = published_session(tmp_path)
    destination.mkdir()
    requested = []
    window = MainWindow(
        session=session, completion_actions=CompletionActions(launch=requested.append)
    )
    window.show()
    window.submit(SelectVault(path_or_null=None))
    try:
        until(app, lambda: window.snapshot.publication is not None)
        previous = window.snapshot.result
        button(window, "Open migration report").click()
        until(
            app,
            lambda: (
                "unavailable"
                in named_label(window, "Completion action feedback").text()
            ),
        )
        assert window.snapshot.result is previous
        assert requested == []
        assert path_text(window, "Completion action path") == str(
            destination / "MIGRATION REPORT.md"
        )
        assert button(window, "Open folder").isEnabled()
        assert button(window, "Check published vault").isEnabled()
    finally:
        finish(app, window)


def test_slow_os_dispatch_keeps_qt_events_and_disclosure_responsive(tmp_path):
    app = QApplication.instance() or QApplication([])
    session, destination = published_session(tmp_path)
    destination.mkdir()
    entered, release = Event(), Event()

    def blocked(target):
        entered.set()
        assert release.wait(10)

    window = MainWindow(
        session=session, completion_actions=CompletionActions(launch=blocked)
    )
    window.show()
    window.submit(SelectVault(path_or_null=None))
    try:
        until(app, lambda: window.snapshot.publication is not None)
        previous = window.snapshot.result
        button(window, "Open folder").click()
        until(app, entered.is_set)
        QTimer.singleShot(0, button(window, "Diagnostic details").click)
        until(app, lambda: window.diagnostics_expanded)
        repainted = []
        QTimer.singleShot(0, lambda: repainted.append(not window.grab().isNull()))
        until(app, lambda: bool(repainted))
        assert repainted == [True] and not release.is_set()
        assert window.snapshot.result is previous
        assert button(window, "Check published vault").isEnabled()
        release.set()
        until(
            app,
            lambda: (
                "requested" in named_label(window, "Completion action feedback").text()
            ),
        )
    finally:
        release.set()
        finish(app, window)


@pytest.mark.parametrize("move_focus", ["unchanged", "disclosure", "away_and_back"])
def test_open_completion_returns_keyboard_focus_unless_user_moves_it(
    tmp_path, move_focus
):
    app = QApplication.instance() or QApplication([])
    session, destination = published_session(tmp_path)
    destination.mkdir()
    entered, release = Event(), Event()

    def blocked(target):
        entered.set()
        assert release.wait(10)

    window = MainWindow(
        session=session, completion_actions=CompletionActions(launch=blocked)
    )
    window.show()
    window.submit(SelectVault(path_or_null=None))
    try:
        until(app, lambda: window.snapshot.publication is not None)
        origin = button(window, "Open folder")
        origin.setFocus()
        app.processEvents()
        assert app.focusWidget() is origin
        QTest.keyClick(origin, Qt.Key.Key_Space)
        until(app, entered.is_set)
        if move_focus != "unchanged":
            automatic_focus = app.focusWidget()
            disclosure = button(window, "Diagnostic details")
            disclosure.setFocus()
            QTest.keyClick(disclosure, Qt.Key.Key_Space)
            app.processEvents()
            expected = disclosure
            if move_focus == "away_and_back":
                automatic_focus.setFocus()
                expected = automatic_focus
        else:
            expected = origin
        release.set()
        until(
            app,
            lambda: (
                "requested" in named_label(window, "Completion action feedback").text()
            ),
        )
        assert app.focusWidget() is expected
        assert window.snapshot.publication.receipt_verified
    finally:
        release.set()
        finish(app, window)


@pytest.mark.parametrize("outcome", ["clean", "failed"])
def test_post_conversion_check_uses_published_folder_with_real_worker(
    tmp_path, outcome
):
    app = QApplication.instance() or QApplication([])
    session, destination = published_session(tmp_path, outcome)
    destination.mkdir()
    note = destination / "Control.md"
    note.write_text(
        "---\ncategories: 42\n---\nBODY canary must stay local\n", encoding="utf-8"
    )
    original = note.read_bytes()
    requested = []
    window = MainWindow(
        session=session, completion_actions=CompletionActions(launch=requested.append)
    )
    window.show()
    window.submit(
        SelectVault(path_or_null=str(tmp_path / "other independent selection"))
    )
    try:
        until(app, lambda: window.snapshot.publication is not None)
        assert requested == []
        button(window, "Check published vault").click()
        until(
            app,
            lambda: (
                window.snapshot.result is not None
                and window.snapshot.result.operation == "check_vault"
            ),
        )
        assert window.snapshot.vault == str(destination)
        assert window.snapshot.result.status == "check_issues"
        assert window.snapshot.publication.receipt_verified
        assert note.read_bytes() == original
        text = "\n".join(label.text() for label in window.findChildren(QLabel))
        assert "Check completed — issues found" in text
        assert "BODY canary" not in text
        assert requested == []
    finally:
        finish(app, window)


def test_empty_independent_selector_does_not_check_published_vault_implicitly(tmp_path):
    from brz2obsidian.application.contracts import SimpleCommand

    app = QApplication.instance() or QApplication([])
    session, destination = published_session(tmp_path)
    requested = []
    window = MainWindow(
        session=session, completion_actions=CompletionActions(launch=requested.append)
    )
    window.show()
    window.submit(SelectVault(path_or_null=None))
    try:
        until(app, lambda: window.snapshot.publication is not None)
        window.tabs.setCurrentIndex(2)
        assert not button(window, "Check vault").isEnabled()
        assert path_text(window, "Selected vault path") == "No vault selected"
        previous = window.snapshot
        window.submit(SimpleCommand(command="check_vault"))
        until(app, lambda: window.snapshot is not previous)
        assert window.snapshot.result is previous.result
        assert window.snapshot.active_request_id is None
        assert window.snapshot.vault is None
        assert requested == []
        window.tabs.setCurrentIndex(0)
        assert button(window, "Check published vault").isEnabled()
        assert path_text(window, "Published vault path") == str(destination)
    finally:
        finish(app, window)


@pytest.mark.parametrize("close_pending", [False, True])
def test_conversion_completion_never_automatically_opens_or_checks(
    tmp_path, close_pending
):
    from brz2obsidian.application.contracts import WorkerResponse
    from brz2obsidian.application.operations import convert_reviewed
    from brz2obsidian.application.transport import Terminal
    from tests.application.test_conversion_session import ready_session
    from tests.application.test_minimal_workflow import make_archive

    app = QApplication.instance() or QApplication([])
    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    entered, release = Event(), Event()
    requests, opens = [], []

    class ControlledConversion:
        def run(self, request):
            requests.append(request.operation)
            assert request.operation == "convert_reviewed"
            entered.set()
            assert release.wait(10)
            args = request.arguments
            result = convert_reviewed(source, tmp_path, args.vault_name, args.reviewed)
            return Terminal(
                phase="completed",
                process_status=0,
                response=WorkerResponse(
                    request_id=request.request_id,
                    operation=request.operation,
                    result=result,
                ),
            )

    window = MainWindow(
        session=session,
        supervisor=ControlledConversion(),
        completion_actions=CompletionActions(launch=opens.append),
    )
    window.show()
    window.submit(SelectVault(path_or_null=None))
    try:
        until(app, lambda: window.snapshot.reviewed is not None)
        button(window, "Convert").click()
        until(app, entered.is_set)
        if close_pending:
            window.close()
            until(app, lambda: window.snapshot.close_pending)
        release.set()
        until(app, lambda: window.snapshot.publication is not None)
        if close_pending:
            until(app, lambda: not window.isVisible())
        assert window.snapshot.result.status == "conversion_created"
        assert window.snapshot.publication.receipt_verified
        assert window.snapshot.vault is None
        assert requests == ["convert_reviewed"]
        assert opens == []
    finally:
        release.set()
        finish(app, window)
