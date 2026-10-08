"""Independent expectations from #92 and accepted C, authored by /root.

Public MainWindow, session commands and Qt controls are the observation seams.
Expected presentation values come from the accepted contract, not renderer tables.
Native checks separately assess appearance and actual Windows scaling.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabBar,
    QTextEdit,
    QWidget,
)

from brz2obsidian.application.contracts import (
    ApplyTransportFailure,
    ConversionResult,
    ConvertCommand,
    Finding,
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


def path_text(control):
    if isinstance(control, QLabel):
        return control.text()
    assert isinstance(control, QTextEdit) and control.isReadOnly()
    return control.toPlainText()


def assert_path_fits(control, expected):
    assert path_text(control) == expected
    if isinstance(control, QLabel):
        assert (
            control.textInteractionFlags()
            & Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        flags = Qt.TextFlag.TextWordWrap if control.wordWrap() else 0
        bounds = control.fontMetrics().boundingRect(
            QRect(0, 0, control.contentsRect().width(), 10000), flags, expected
        )
        assert bounds.width() <= control.contentsRect().width(), (
            "An unbroken path segment clips horizontally"
        )
        assert bounds.height() <= control.contentsRect().height(), (
            "Wrapped path lines clip vertically"
        )
    else:
        document = control.document()
        assert document.size().height() <= control.viewport().height() + 1
        block = document.begin()
        while block.isValid():
            layout = block.layout()
            for index in range(layout.lineCount()):
                assert (
                    layout.lineAt(index).naturalTextWidth()
                    <= control.viewport().width()
                )
            block = block.next()
        control.selectAll()
        assert control.textCursor().selectedText() == expected
        assert control.horizontalScrollBar().maximum() == 0
        assert control.verticalScrollBar().maximum() == 0


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
    findings = named(window, QWidget, "Inspection findings")
    assert findings.isVisible() and path_text(findings).startswith(
        expected_title + "\n"
    )
    published = visible_label(window, "Published vault")
    path = named(window, QWidget, "Published vault path")
    assert path.isVisible() and path_text(path).strip()
    assert_path_fits(path, path_text(path))
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
        assert path_text(named(window, QWidget, "Published vault path")) == str(
            destination
        )
        findings = named(window, QWidget, "Inspection findings")
        original = path_text(findings)
        replace_text = (
            findings.setText if isinstance(findings, QLabel) else findings.setPlainText
        )
        replace_text("Publication status unknown\nWrong presentation")
        with pytest.raises(AssertionError):
            assert_published_contract(window, title)
        replace_text(original)
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
        source_path = named(window, QWidget, "Selected archive path")
        complete_path = named(window, QWidget, "Complete destination path")
        assert path_text(source_path) == str(source)
        assert abs(top(window, parent) - top(window, name)) <= 4
        assert (
            parent.mapTo(window, parent.rect().topLeft()).x()
            < name.mapTo(window, name.rect().topLeft()).x()
        )
        window.resize(460, 540)
        app.processEvents()
        assert_path_fits(source_path, str(source))
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
            QWidget,
            "Check findings" if operation == "check" else "Inspection findings",
        )
        assert findings.isVisible() and title in path_text(findings)
        assert not named(window, QWidget, "Published vault path").isVisible()
        for action in (
            "Open folder",
            "Open migration report",
            "Open in Obsidian",
            "Check published vault",
        ):
            assert not named(window, QPushButton, action).isVisible()
        if operation == "check":
            assert "read-only" in path_text(findings)
            assert (
                "does not repair files or prove preservation of source content"
                in path_text(findings)
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


def test_unbroken_source_path_remains_fully_readable_and_exact_when_narrow(tmp_path):
    app = QApplication.instance() or QApplication([])
    folder = tmp_path / ("Unbroken" * 12)
    folder.mkdir()
    source = make_archive(folder / "Exact_café_source.brz")
    window = MainWindow(session=ready_session(source, tmp_path))
    window.show()
    window.submit(SelectVault(path_or_null=None))
    try:
        until(app, lambda: window.snapshot.result is not None)
        window.resize(460, 540)
        app.processEvents()
        path = named(window, QWidget, "Selected archive path")
        assert_path_fits(path, str(source))
    finally:
        finish(app, window)


def test_source_and_independent_checker_use_one_adjacent_identity_selector(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = make_archive(tmp_path / "Selected archive.brz")
    vault = tmp_path / "Selected vault"
    vault.mkdir()
    window = MainWindow(session=ready_session(source, tmp_path))
    window.show()
    window.submit(SelectVault(path_or_null=str(vault)))
    try:
        until(app, lambda: window.snapshot.vault == str(vault))
        tabs = window.findChild(QTabBar)
        for mode, title, name, path_name, action_name, expected in (
            (
                0,
                "Source archive",
                source.name,
                "Selected archive path",
                "Choose source archive",
                str(source),
            ),
            (
                2,
                "Vault to check",
                vault.name,
                "Selected vault path",
                "Choose vault folder",
                str(vault),
            ),
        ):
            tabs.setCurrentIndex(mode)
            app.processEvents()
            heading = visible_label(window, title)
            identity = visible_label(window, name)
            path = named(window, QWidget, path_name)
            choose = named(window, QPushButton, action_name)
            assert path_text(path) == expected
            assert choose.text() == "Change…" and choose.isEnabled()
            assert top(window, heading) < top(window, identity) < top(window, path)
            assert (
                path.mapTo(window, path.rect().topRight()).x()
                < choose.mapTo(window, choose.rect().topLeft()).x()
            )
            icons = [
                label
                for label in window.findChildren(QLabel)
                if label.isVisible() and label.pixmap() and not label.pixmap().isNull()
            ]
            assert len(icons) == 1
            assert (
                icons[0].mapTo(window, icons[0].rect().topRight()).x()
                < identity.mapTo(window, identity.rect().topLeft()).x()
            )
            dividers = [
                frame
                for frame in window.findChildren(QFrame)
                if frame.isVisible() and frame.frameShape() == QFrame.Shape.HLine
            ]
            assert any(
                top(window, path)
                < top(window, divider)
                < top(window, visible_label(window, "Findings"))
                for divider in dividers
            )
    finally:
        finish(app, window)


def assert_readable_text(control, expected):
    """Public text/layout observation; permit labels or read-only documents."""
    assert path_text(control) == expected
    if isinstance(control, QTextEdit):
        document = control.document()
        assert document.size().height() <= control.viewport().height() + 1
        block = document.begin()
        while block.isValid():
            layout = block.layout()
            for index in range(layout.lineCount()):
                assert (
                    layout.lineAt(index).naturalTextWidth()
                    <= control.viewport().width()
                )
            block = block.next()
        control.selectAll()
        # QTextCursor represents paragraph breaks as U+2029; observe exact
        # outward copy text instead, without writing to the OS clipboard.
        assert control.createMimeDataFromSelection().text() == expected
        assert control.horizontalScrollBar().maximum() == 0
        assert control.verticalScrollBar().maximum() == 0
        return
    flags = Qt.TextFlag.TextWordWrap if control.wordWrap() else 0
    bounds = control.fontMetrics().boundingRect(
        QRect(0, 0, control.contentsRect().width(), 10000), flags, expected
    )
    assert bounds.width() <= control.contentsRect().width(), (
        "Recovery text clips horizontally",
        bounds.width(),
        control.contentsRect().width(),
    )
    assert bounds.height() <= control.contentsRect().height(), (
        "Recovery text clips vertically",
        bounds.height(),
        control.contentsRect().height(),
    )


def test_narrow_unknown_recovery_keeps_footer_guidance_and_previous_destination_readable(
    tmp_path,
):
    # #92 UI-U02/P04/P08: recovery text and contextual footer stay readable.
    # Expectation recorded from the native453px failure before renderer inspection.
    app = QApplication.instance() or QApplication([])
    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    effect = session.dispatch(ConvertCommand()).effects[0]
    session.dispatch(
        ApplyTransportFailure(
            request_id=effect.request.request_id,
            phase="may_have_executed",
            code="protocol_failure",
        )
    )
    window = MainWindow(session=session)
    window.resize(453, 540)
    window.show()
    window.submit(SelectVault(path_or_null=None))
    try:
        until(app, lambda: window.snapshot.operational_status is not None)
        app.processEvents()
        footer_text = (
            "Review the destination before another attempt. "
            "Publication could not be established."
        )
        footer_hint = visible_label(window, footer_text)
        assert_readable_text(footer_hint, footer_text)
        scroll = window.findChild(QScrollArea)
        assert not scroll.widget().isAncestorOf(footer_hint)
        for label in ("Close", "I reviewed the destination", "Inspect archive"):
            button = next(
                item
                for item in window.findChildren(QPushButton)
                if item.isVisible() and item.text() == label
            )
            bounds = button.mapTo(window, button.rect().topLeft())
            assert bounds.x() >= 0 and bounds.y() >= 0
            assert bounds.x() + button.width() <= window.width()
            assert bounds.y() + button.height() <= window.height()
        recovery = named(window, QWidget, "Conversion recovery guidance")
        text = path_text(recovery)
        assert str(tmp_path) in text
        assert "Acknowledgment does not establish publication." in text
        assert_readable_text(recovery, text)
        scroll.ensureWidgetVisible(recovery)
        app.processEvents()
        assert scroll.mapTo(window, scroll.rect().bottomLeft()).y() <= top(
            window, footer_hint
        )
    finally:
        finish(app, window)


def test_narrow_failed_findings_and_owned_leftover_guidance_remain_readable(tmp_path):
    # #92 UI-U02/P06: every visible findings message must fit its allocated area.
    # A reported path may be in the panel or adjacent recovery content; it must
    # remain exact and readable wherever displayed, without requiring duplication.
    app = QApplication.instance() or QApplication([])
    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    effect = session.dispatch(ConvertCommand()).effects[0]
    leftover = str(tmp_path / (".brz2obsidian-" + "Unbroken" * 6))
    message = "Owned staging cleanup did not complete. Review the reported leftover."
    result = ConversionResult(
        outcome="failed",
        status="conversion_failed",
        publication=Publication(state="not_published"),
        findings=(
            Finding(
                code="cleanup_failure",
                severity="error",
                message=message,
                path=leftover,
            ),
        ),
        diagnostic_text="Safe synthetic owned cleanup guidance.",
    )
    complete(session, effect, result, 1)
    window = MainWindow(session=session)
    window.resize(453, 700)
    window.show()
    window.submit(SelectVault(path_or_null=None))
    try:
        until(app, lambda: window.snapshot.result is not None)
        app.processEvents()
        findings = named(window, QWidget, "Inspection findings")
        text = path_text(findings)
        assert text.startswith("Conversion could not complete\n")
        assert message in text
        assert_readable_text(findings, text)
        recovery = named(window, QWidget, "Conversion recovery guidance")
        recovery_text = path_text(recovery)
        assert leftover in recovery_text
        assert_readable_text(recovery, recovery_text)
        assert not named(window, QWidget, "Published vault path").isVisible()
        assert named(window, QPushButton, "Retry conversion").isEnabled()
    finally:
        finish(app, window)


def test_narrow_checker_identifies_a_long_reported_file_without_clipping(tmp_path):
    # A real read-only checker file finding is not a staging-cleanup leftover.
    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "v"
    vault.mkdir()
    note = vault / ("Unbroken" * 10 + ".md")
    note.write_text("![[Missing.png]]\n", encoding="utf-8")
    result = check_vault(vault)
    assert result.status == "check_issues"
    assert any(finding.path == note.name for finding in result.findings)
    session = ApplicationSession()
    session.dispatch(SelectVault(path_or_null=str(vault)))
    effect = session.dispatch(SimpleCommand(command="check_vault")).effects[0]
    complete(session, effect, result, 2)
    window = MainWindow(session=session)
    window.resize(453, 700)
    window.show()
    window.submit(SimpleCommand(command="carry_inspection_to_convert"))
    try:
        until(app, lambda: window.snapshot.result is not None)
        window.findChild(QTabBar).setCurrentIndex(2)
        app.processEvents()
        findings = named(window, QWidget, "Check findings")
        text = path_text(findings)
        assert text.startswith("Check completed — issues found\n")
        assert note.name in text and "read-only" in text
        assert_readable_text(findings, text)
        assert "Reported leftover" not in text
        assert "Staging" not in text and "staging" not in text
        retry = named(window, QPushButton, "Retry check")
        assert retry.isVisible() and retry.isEnabled()
    finally:
        finish(app, window)
