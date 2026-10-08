"""Independent expectations from #92 and accepted C, authored by /root.

Public MainWindow, session commands and Qt controls are the observation seams.
Expected presentation values come from the accepted contract, not renderer tables.
Native checks separately assess appearance and actual Windows scaling.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabBar,
)

from brz2obsidian.application.contracts import (
    ApplyTransportFailure,
    ConversionResult,
    ConvertCommand,
    InspectCommand,
    InspectionResult,
    Publication,
    SelectSource,
    SelectVault,
    SimpleCommand,
)
from brz2obsidian.application.operations import ApplicationSession, check_vault, inspect
from brz2obsidian_ui.window import MainWindow
from tests.application.test_completion_session import published_session
from tests.application.test_conversion_session import complete, ready_session
from tests.application.test_minimal_workflow import make_archive
from tests.gui.test_conversion_window import until

pytestmark = pytest.mark.gui


def finish(app, window):
    window.close()
    until(app, lambda: not window.isVisible())
    window.shutdown()


def visible_label(window, text):
    matches = [
        item
        for item in window.findChildren(QLabel)
        if item.isVisible() and item.text() == text
    ]
    assert len(matches) == 1, f"Expected one visible {text!r} label"
    return matches[0]


def top(window, widget):
    return widget.mapTo(window, widget.rect().topLeft()).y()


def named(window, kind, accessible):
    matches = [
        item
        for item in window.findChildren(kind)
        if item.accessibleName() == accessible
    ]
    assert len(matches) == 1, f"Expected one named {accessible!r} control"
    return matches[0]


def assert_operation_header(window):
    tabs = window.findChild(QTabBar)
    assert tabs.accessibleName() == "Operation"
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "Convert",
        "Inspect",
        "Check vault",
    ]
    identity = visible_label(window, "brz2obsidian")
    heading = visible_label(
        window, ("Convert", "Inspect", "Check vault")[tabs.currentIndex()]
    )
    assert top(window, identity) < top(window, heading) < top(window, tabs)
    explanations = [
        item
        for item in window.findChildren(QLabel)
        if item.isVisible()
        and item.text().strip()
        and top(window, heading) < top(window, item) < top(window, tabs)
    ]
    assert len(explanations) == 1
    assert len(window.findChildren(QScrollArea)) == 1


def test_operation_header_and_keyboard_tabs_follow_the_accepted_task_order():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    try:
        app.processEvents()
        assert_operation_header(window)
        tabs = window.findChild(QTabBar)
        tabs.setFocus()
        for expected in (1, 2):
            QTest.keyClick(tabs, Qt.Key.Key_Right)
            app.processEvents()
            assert tabs.currentIndex() == expected
            assert_operation_header(window)
        QTest.keyClick(tabs, Qt.Key.Key_Left)
        app.processEvents()
        assert tabs.currentIndex() == 1
        assert_operation_header(window)
        tabs.setTabText(0, "Inspect")
        tabs.setTabText(1, "Convert")
        with pytest.raises(AssertionError):
            assert_operation_header(window)
    finally:
        finish(app, window)


def test_diagnostic_disclosure_keyboard_selection_and_exports_follow_reading_order(
    tmp_path,
):
    app = QApplication.instance() or QApplication([])
    source = make_archive(tmp_path / "archive.brz")
    window = MainWindow(session=ready_session(source, tmp_path))
    window.show()
    window.submit(SelectVault(path_or_null=None))
    try:
        until(app, lambda: window.snapshot.result is not None)
        disclosure = named(window, QPushButton, "Diagnostic details")
        report = named(window, QPlainTextEdit, "Diagnostic report page")
        copy = named(window, QPushButton, "Copy details")
        save = named(window, QPushButton, "Save diagnostic report")
        assert not report.isVisible() and not copy.isVisible() and not save.isVisible()
        assert top(window, visible_label(window, "Findings")) < top(window, disclosure)
        disclosure.setFocus()
        QTest.keyClick(disclosure, Qt.Key.Key_Space)
        app.processEvents()
        assert report.isVisible() and copy.isVisible() and save.isVisible()
        assert report.isReadOnly() and report.toPlainText().strip()
        QTest.keyClick(disclosure, Qt.Key.Key_Tab)
        app.processEvents()
        assert app.focusWidget() is report
        QTest.keyClick(report, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        assert report.textCursor().hasSelection()
        assert report.textCursor().selectedText().strip()
        QTest.keyClick(report, Qt.Key.Key_Tab)
        app.processEvents()
        assert app.focusWidget() is copy, (
            "Copy must follow the report, before destination"
        )
        QTest.keyClick(copy, Qt.Key.Key_Tab)
        app.processEvents()
        assert app.focusWidget() is save
        QTest.keyClick(save, Qt.Key.Key_Backtab)
        app.processEvents()
        assert app.focusWidget() is copy
    finally:
        finish(app, window)


def assert_published_contract(window, expected_title):
    findings = named(window, QLabel, "Inspection findings")
    assert findings.isVisible() and findings.text().startswith(expected_title + "\n")
    published = visible_label(window, "Published vault")
    path = named(window, QLabel, "Published vault path")
    assert path.isVisible() and path.text().strip()
    assert path.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByKeyboard
    assert top(window, visible_label(window, "Source archive")) < top(window, findings)
    assert top(window, findings) < top(window, published) < top(window, path)
    assert not named(window, QLineEdit, "Vault name").isVisible()
    assert not named(window, QLineEdit, "Output parent folder").isVisible()
    scroll = window.findChild(QScrollArea)
    for accessible, text in (
        ("Open folder", "Open folder"),
        ("Open migration report", "Open migration report"),
        ("Open in Obsidian", "Open in Obsidian"),
        ("Check published vault", "Check vault"),
    ):
        action = named(window, QPushButton, accessible)
        assert action.isVisible() and action.isEnabled() and action.text() == text
        assert scroll.widget().isAncestorOf(action)
        assert top(window, path) < top(window, action)
    close = next(
        button
        for button in window.findChildren(QPushButton)
        if button.text() == "Close"
    )
    fresh = named(window, QPushButton, "Start another conversion")
    assert close.isVisible() and fresh.isVisible()
    assert not scroll.widget().isAncestorOf(close)
    assert not scroll.widget().isAncestorOf(fresh)
    assert (
        close.mapTo(window, close.rect().topLeft()).x()
        < fresh.mapTo(window, fresh.rect().topLeft()).x()
    )
    assert scroll.mapTo(window, scroll.rect().bottomLeft()).y() <= top(window, close)


@pytest.mark.parametrize(
    "outcome,title",
    [
        ("clean", "Vault created"),
        ("warnings", "Vault created with warnings"),
        ("failed", "Vault created; a follow-up error occurred"),
    ],
)
def test_verified_result_replaces_editors_and_contains_optional_actions_with_anchored_footer(
    tmp_path, outcome, title
):
    app = QApplication.instance() or QApplication([])
    session, destination = published_session(tmp_path, outcome)
    window = MainWindow(session=session)
    window.show()
    window.submit(SelectVault(path_or_null=None))
    try:
        until(app, lambda: window.snapshot.publication is not None)
        app.processEvents()
        assert_published_contract(window, title)
        assert named(window, QLabel, "Published vault path").text() == str(destination)
        findings = named(window, QLabel, "Inspection findings")
        original = findings.text()
        findings.setText("Publication status unknown\nWrong presentation")
        with pytest.raises(AssertionError):
            assert_published_contract(window, title)
        findings.setText(original)
        action = named(window, QPushButton, "Open migration report")
        action.hide()
        with pytest.raises(AssertionError):
            assert_published_contract(window, title)
        action.show()
        assert_published_contract(window, title)
    finally:
        finish(app, window)


def keyboard_control_order(app, window, backwards=False):
    start = window.findChild(QTabBar)
    start.setFocus()
    app.processEvents()
    assert app.focusWidget() is start
    result = ["Operation"]
    for _ in range(120):
        focus = app.focusWidget()
        assert focus is not None
        QTest.keyClick(focus, Qt.Key.Key_Backtab if backwards else Qt.Key.Key_Tab)
        app.processEvents()
        focus = app.focusWidget()
        if focus is start:
            return result
        if isinstance(focus, (QPushButton, QLineEdit, QPlainTextEdit)):
            result.append(focus.accessibleName() or focus.text())
    pytest.fail("Keyboard focus failed to return to the operation tabs")


@pytest.mark.parametrize("published", [False, True])
def test_forward_and_reverse_control_focus_follow_task_reading_order(
    tmp_path, published
):
    app = QApplication.instance() or QApplication([])
    if published:
        session, _ = published_session(tmp_path)
        expected = [
            "Operation",
            "Diagnostic details",
            "Open folder",
            "Open migration report",
            "Open in Obsidian",
            "Check published vault",
            "Close",
            "Start another conversion",
        ]
    else:
        source = make_archive(tmp_path / "archive.brz")
        session = ready_session(source, tmp_path)
        expected = [
            "Operation",
            "Choose source archive",
            "Diagnostic details",
            "Output parent folder",
            "Choose output parent folder",
            "Vault name",
            "Close",
            "Convert",
        ]
    window = MainWindow(session=session)
    window.show()
    window.submit(SelectVault(path_or_null=None))
    try:
        until(app, lambda: window.snapshot.result is not None)
        assert keyboard_control_order(app, window) == expected
        assert keyboard_control_order(app, window, backwards=True) == [
            expected[0],
            *reversed(expected[1:]),
        ]
    finally:
        finish(app, window)


def test_narrow_long_path_and_adjacent_name_error_scroll_without_covering_footer(
    tmp_path,
):
    app = QApplication.instance() or QApplication([])
    source_directory = (
        tmp_path
        / "Long source folder with context"
        / "Another source folder with context"
    )
    source_directory.mkdir(parents=True)
    source = make_archive(source_directory / "Archive café.brz")
    window = MainWindow(session=ready_session(source, tmp_path))
    window.show()
    window.submit(SelectVault(path_or_null=None))
    try:
        until(app, lambda: window.snapshot.result is not None)
        parent = named(window, QLineEdit, "Output parent folder")
        name = named(window, QLineEdit, "Vault name")
        source_path = named(window, QLabel, "Selected archive path")
        complete_path = named(window, QLabel, "Complete destination path")
        assert source_path.text() == str(source) and source_path.wordWrap()
        assert (
            source_path.textInteractionFlags()
            & Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        assert abs(top(window, parent) - top(window, name)) <= 4
        assert (
            parent.mapTo(window, parent.rect().topLeft()).x()
            < name.mapTo(window, name.rect().topLeft()).x()
        )
        window.resize(460, 540)
        app.processEvents()
        assert top(window, parent) < top(window, name) < top(window, complete_path)
        name.setFocus()
        QTest.keyClick(name, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(name, Qt.Key.Key_Backspace)
        until(
            app,
            lambda: (
                bool(window.snapshot.field_errors)
                and not window.snapshot.validation_pending
            ),
        )
        error = named(window, QLabel, "Vault name error")
        assert error.isVisible() and error.text().strip()
        assert top(window, name) < top(window, error) < top(window, complete_path)
        assert not named(window, QPushButton, "Convert").isEnabled()
        assert window.snapshot.result is not None
        scroll = window.findChild(QScrollArea)
        bar = scroll.verticalScrollBar()
        assert bar.maximum() > 0
        bar.setValue(bar.maximum())
        app.processEvents()
        close = next(
            button
            for button in window.findChildren(QPushButton)
            if button.text() == "Close"
        )
        primary = named(window, QPushButton, "Convert")
        assert scroll.mapTo(window, scroll.rect().bottomLeft()).y() <= top(
            window, close
        )
        assert close.isVisible() and primary.isVisible()
        assert top(window, close) + close.height() < window.height()
        assert top(window, primary) + primary.height() < window.height()
        assert not scroll.widget().isAncestorOf(close)
        assert not scroll.widget().isAncestorOf(primary)
    finally:
        finish(app, window)


@pytest.mark.parametrize(
    "operation,outcome,title",
    [
        ("inspect", "clean", "Inspection completed — ready for review"),
        ("inspect", "warnings", "Inspection completed — source warnings"),
        ("inspect", "refused", "Archive cannot be used"),
        ("inspect", "failed", "Inspection could not complete"),
        ("convert", "refused", "Conversion could not proceed"),
        ("convert", "failed", "Conversion could not complete"),
        ("transport", "not_started", "The operation could not start"),
        ("transport", "unknown", "Publication status unknown"),
        ("check", "clean", "Check completed — no issues found"),
        ("check", "issues", "Check completed — issues found"),
        ("check", "failed", "Check could not complete"),
    ],
)
def test_nonpublished_outcomes_have_distinct_textual_meaning_and_no_completion_actions(
    tmp_path, operation, outcome, title
):
    app = QApplication.instance() or QApplication([])
    source = make_archive(tmp_path / "archive.brz")
    session = ApplicationSession()
    if operation == "inspect":
        session.dispatch(SelectSource(path_or_null=str(source)))
        effect = session.dispatch(InspectCommand()).effects[0]
        original = inspect(source)
        data = original.model_dump(by_alias=True)
        data.update(outcome=outcome, status="inspection_" + outcome)
        if outcome in ("clean", "warnings"):
            data["reviewed"]["outcome"] = outcome
        else:
            data["reviewed"] = None
        result = InspectionResult.model_validate(data)
        complete(
            session,
            effect,
            result,
            0 if outcome == "clean" else 2 if outcome == "warnings" else 1,
        )
    elif operation in ("convert", "transport"):
        session = ready_session(source, tmp_path)
        effect = session.dispatch(ConvertCommand()).effects[0]
        if operation == "transport":
            session.dispatch(
                ApplyTransportFailure(
                    request_id=effect.request.request_id,
                    phase="not_started"
                    if outcome == "not_started"
                    else "may_have_executed",
                    code="launch_failure"
                    if outcome == "not_started"
                    else "protocol_failure",
                )
            )
        else:
            result = ConversionResult(
                outcome=outcome,
                status="conversion_" + outcome,
                publication=Publication(state="not_published"),
                diagnostic_text="Safe failure guidance.",
            )
            complete(session, effect, result, 1)
    else:
        vault = tmp_path / "Selected vault"
        if outcome != "failed":
            vault.mkdir()
            if outcome == "issues":
                (vault / "Manual.md").write_text("![[Missing.png]]\n", encoding="utf-8")
        session.dispatch(SelectVault(path_or_null=str(vault)))
        effect = session.dispatch(SimpleCommand(command="check_vault")).effects[0]
        result = check_vault(vault)
        complete(
            session,
            effect,
            result,
            0 if outcome == "clean" else 2 if outcome == "issues" else 1,
        )
    window = MainWindow(session=session)
    window.show()
    window.submit(SelectVault(path_or_null=None))
    try:
        until(
            app,
            lambda: (
                window.snapshot.result is not None
                or window.snapshot.operational_status is not None
            ),
        )
        if operation == "check":
            window.findChild(QTabBar).setCurrentIndex(2)
        app.processEvents()
        findings = named(
            window,
            QLabel,
            "Check findings" if operation == "check" else "Inspection findings",
        )
        assert findings.isVisible() and title in findings.text()
        assert not named(window, QLabel, "Published vault path").isVisible()
        for action in (
            "Open folder",
            "Open migration report",
            "Open in Obsidian",
            "Check published vault",
        ):
            assert not named(window, QPushButton, action).isVisible()
        if operation == "check":
            assert "read-only" in findings.text()
            assert (
                "does not repair files or prove preservation of source content"
                in findings.text()
            )
        else:
            assert named(window, QLineEdit, "Vault name").isVisible()
            text = "\n".join(
                label.text()
                for label in window.findChildren(QLabel)
                if label.isVisible()
            )
            if operation == "transport":
                assert "Actual notes: 0" not in text
            else:
                assert "Actual notes: unavailable" in text
    finally:
        finish(app, window)
