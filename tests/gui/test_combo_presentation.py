"""Shared selector presentation and interaction through MainWindow controls."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox

from brz2obsidian_ui.window import MainWindow
from tests.gui.test_local_api_source_window import control, until

pytestmark = pytest.mark.gui


@pytest.mark.parametrize("name", ["Source kind", "Accessible Brains"])
def test_selectors_keep_matching_field_edges_and_visible_indicators(name):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    try:
        source = control(window, QComboBox, "Source kind")
        source.setFocus()
        QTest.keyClick(source, Qt.Key.Key_Down)
        until(app, lambda: window.snapshot.source_kind == "local-api")
        combo = control(window, QComboBox, name)
        combo.clearFocus()
        app.processEvents()
        image = combo.grab().toImage()
        scale = image.devicePixelRatio()
        # The button must follow the field's border treatment. Its native
        # rectangular edge must not overwrite the rounded field on the right.
        assert all(
            image.pixelColor(x, y) == image.pixelColor(image.width() - 1 - x, y)
            for x in range(round(3 * scale))
            for y in range(round(8 * scale), image.height() - round(8 * scale))
        ), "The arrow button must share the field border without a native box edge"
        assert any(
            image.pixelColor(x, y).lightness() < 200
            for x in range(
                round((combo.width() - 30) * scale),
                round((combo.width() - 4) * scale),
            )
            for y in range(round(8 * scale), image.height() - round(8 * scale))
        ), "A visible dropdown indicator must remain inside the field"
    finally:
        window.close()
        window.shutdown()


def test_source_options_remain_selectable_by_arrow_button_and_keyboard():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    try:
        combo = control(window, QComboBox, "Source kind")
        app.processEvents()
        assert [combo.itemText(row) for row in range(combo.count())] == [
            "BRZ archive",
            "TheBrain local API",
        ]
        for row, kind in ((1, "local-api"), (0, "brz")):
            QTest.mouseClick(
                combo,
                Qt.MouseButton.LeftButton,
                pos=QPoint(combo.width() - 16, combo.height() // 2),
            )
            app.processEvents()
            view = combo.view()
            assert view.isVisible()
            QTest.qWait(QApplication.doubleClickInterval())
            QTest.mouseClick(
                view.viewport(),
                Qt.MouseButton.LeftButton,
                pos=view.visualRect(view.model().index(row, 0)).center(),
            )
            until(app, lambda kind=kind: window.snapshot.source_kind == kind)
            assert combo.currentIndex() == row and not view.isVisible()
        combo.setFocus()
        for key, kind in ((Qt.Key.Key_Down, "local-api"), (Qt.Key.Key_Up, "brz")):
            QTest.keyClick(combo, key)
            until(app, lambda kind=kind: window.snapshot.source_kind == kind)
    finally:
        combo.hidePopup() if "combo" in locals() else None
        window.close()
        window.shutdown()
