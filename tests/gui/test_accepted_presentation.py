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
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabBar,
    QTextEdit,
    QWidget,
)

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
