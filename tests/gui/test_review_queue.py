"""Offscreen rendering and navigation of the Update vault review sidebar."""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QListWidget, QStyleFactory

from brz2obsidian_ui.window import STYLE, PathText
from brz2obsidian_ui.workbench import UpdateWorkbench

pytestmark = pytest.mark.gui


@pytest.fixture
def review_workbench():
    app = QApplication.instance() or QApplication([])
    workbench = UpdateWorkbench(
        None, select=None, pick_source=None, pick_vault=None, path_widget=PathText
    )
    workbench.setStyleSheet(STYLE)
    try:
        yield app, workbench, workbench.findChild(QListWidget, "reviewQueue")
    finally:
        workbench.close()
        workbench.deleteLater()
        app.processEvents()


def test_active_and_hovered_rows_leave_review_queue_focus_border_continuous(
    review_workbench,
):
    app, workbench, queue = review_workbench
    workbench.resize(730, 430)
    workbench.show()
    app.processEvents()
    overview = queue.findItems("Overview", Qt.MatchFlag.MatchExactly)[0]
    history = queue.findItems("History & recovery", Qt.MatchFlag.MatchExactly)[0]
    conflicts = queue.findItems("Conflicts", Qt.MatchFlag.MatchExactly)[0]
    workbench.focusNextChild()
    assert not queue.hasFocus()
    QTest.mouseClick(
        queue.viewport(),
        Qt.MouseButton.LeftButton,
        pos=queue.visualItemRect(overview).center(),
    )
    app.processEvents()
    assert queue.hasFocus()
    assert queue.currentItem() == overview
    assert any(
        label.isVisible() and label.text() == "Review the whole update"
        for label in workbench.findChildren(QLabel, "sectionTitle")
    )

    history_rect = queue.visualItemRect(history)
    QTest.mouseMove(queue.viewport(), history_rect.center())
    app.processEvents()
    rendered = queue.grab().toImage()
    scale = rendered.devicePixelRatio()

    def row_color(item):
        row = queue.visualItemRect(item)
        sample = queue.viewport().mapTo(queue, row.center())
        # Use the background beyond the labels and inside the row.
        return rendered.pixelColor(
            round((sample.x() + row.width() // 3) * scale),
            round(sample.y() * scale),
        )

    assert row_color(overview) != row_color(history)
    assert row_color(history) != row_color(conflicts)
    assert queue.currentItem() == overview
    for x in (0, rendered.width() - 1):
        edge_color = rendered.pixelColor(x, 0)
        assert edge_color != row_color(conflicts)
        assert all(
            rendered.pixelColor(x, y) == edge_color for y in range(rendered.height())
        ), "Highlighted rows interrupt the sidebar focus border"

    QTest.keyClick(queue, Qt.Key.Key_Down)
    app.processEvents()
    assert queue.hasFocus()
    assert queue.currentItem() == conflicts
    assert any(
        label.isVisible() and label.text() == "Conflicts"
        for label in workbench.findChildren(QLabel, "sectionTitle")
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows 11 sidebar geometry")
def test_short_windows_review_queue_keeps_the_keyboard_focused_row_in_view(
    review_workbench,
):
    app, workbench, queue = review_workbench
    style = QStyleFactory.create("windows11")
    if style is None:
        pytest.skip("Qt Windows 11 style unavailable")
    style.setParent(queue)
    queue.setStyle(style)
    # The offscreen plugin can omit Windows system fonts from its font database.
    font_id = QFontDatabase.addApplicationFont(
        str(Path(os.environ["WINDIR"]) / "Fonts" / "segoeui.ttf")
    )
    assert font_id >= 0
    try:
        workbench.resize(440, 330)
        workbench.show()
        app.processEvents()

        queue.setFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(queue, Qt.Key.Key_End)
        QTest.keyClick(queue, Qt.Key.Key_Up)
        app.processEvents()
        assert queue.hasFocus()
        assert queue.currentItem().text() == "Compatible changes"
        assert queue.verticalScrollBar().maximum() > 0
        assert queue.horizontalScrollBar().maximum() == 0
        assert (
            queue.viewport().rect().contains(queue.visualItemRect(queue.currentItem()))
        )
    finally:
        QFontDatabase.removeApplicationFont(font_id)
