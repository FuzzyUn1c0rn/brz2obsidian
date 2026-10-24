"""Approved #279 copy and correction behavior through the real Qt controls."""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QLineEdit

from brz2obsidian_ui.window import MainWindow
from tests.gui.test_conversion_window import window_text
from tests.gui.test_inspection_window import until

pytestmark = pytest.mark.gui


def control(window, kind, name):
    return next(w for w in window.findChildren(kind) if w.accessibleName() == name)


def test_api_errors_identify_the_field_and_clear_after_correction():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    try:
        control(window, QComboBox, "Source kind").setCurrentIndex(1)
        until(app, lambda: window.snapshot.source_kind == "local-api")
        address = control(window, QLineEdit, "Local API address")
        address.setText("https://example.com/api")
        until(app, lambda: window.snapshot.api_config is None)
        errors = [
            w
            for w in window.findChildren(QLabel)
            if w.isVisible() and w.text() == "Enter TheBrain’s local API address."
        ]
        assert len(errors) == 1
        address.setText("http://127.0.0.1:11522/api")
        until(app, lambda: window.snapshot.api_config is not None)
        assert not errors[0].isVisible()
    finally:
        window.close()
        until(app, lambda: not window.isVisible())
        window.shutdown()


def test_api_limits_have_specific_feedback_and_reveal_collapsed_fields():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    try:
        window.source_kind.setCurrentIndex(1)
        until(app, lambda: window.snapshot.source_kind == "local-api")
        cases = [
            (
                "Local API address",
                "http://user:secret@localhost:11522/api",
                "Remove the username and password from the address.",
                "http://localhost:11522/api",
            ),
            ("Initial result limit", "0", "Enter a positive whole number.", "5000"),
            (
                "Initial result limit",
                "2147483648",
                "Enter 2,147,483,647 or less.",
                "2147483647",
            ),
            ("Total search seconds", "NaN", "Enter 0.001–86,400 seconds.", "0.001"),
            (
                "Total search seconds",
                "0.0011",
                "Use up to three decimal places.",
                "86400",
            ),
            (
                "Maximum search response bytes",
                "",
                "Enter a positive whole number of bytes.",
                "1",
            ),
            (
                "Maximum search response bytes",
                "9223372036854775808",
                "This value exceeds the supported limit.",
                "9223372036854775807",
            ),
            (
                "Maximum results (blank disables ceiling)",
                "-1",
                "Enter a positive whole number, or leave blank.",
                "",
            ),
            (
                "Maximum results (blank disables ceiling)",
                "2147483648",
                "Enter 2,147,483,647 or less, or leave blank.",
                "",
            ),
        ]
        for name, bad, message, good in cases:
            window.api_advanced_toggle.setChecked(False)
            field = control(window, QLineEdit, name)
            field.setText(bad)
            until(app, lambda: window.snapshot.api_config is None)
            error = control(window, QLabel, name + " error")
            assert error.isVisible() and error.text() == message
            assert window_text(window).count(message) == 1
            assert not window.api_refresh.isEnabled()
            if name != "Local API address":
                assert window.api_advanced.isVisible()
                assert field.toolTip()
                window.api_advanced_toggle.setChecked(False)
                assert window.api_advanced.isVisible()
            field.setText(good)
            until(app, lambda: window.snapshot.api_config is not None)
            assert not error.isVisible()
        assert window.snapshot.api_config.search_max_results is None
    finally:
        window.close()
        until(app, lambda: not window.isVisible())
        window.shutdown()


def test_vault_name_paste_feedback_is_immediate_and_conversion_waits_for_correction(
    tmp_path,
):
    from brz2obsidian.application.contracts import InspectCommand, SelectSource

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    try:
        name = control(window, QLineEdit, "Vault name")
        name.setFocus()
        app.clipboard().setText("bad?name")
        QTest.keyClick(name, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        # No event-loop turn or selected parent is needed for name feedback.
        error = control(window, QLabel, "Vault name error")
        assert error.isVisible() and error.text() == "Remove “?” from the vault name."
        source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
        window.submit(SelectSource(path_or_null=str(source)))
        until(app, lambda: window.snapshot.source == str(source))
        window.submit(InspectCommand())
        until(app, lambda: window.snapshot.reviewed is not None)
        window.parent_selected(str(tmp_path))
        until(app, lambda: "convert" in window.snapshot.allowed_actions)
        assert window.primary.isEnabled()
        name.setFocus()
        name.selectAll()
        QTest.keyClicks(name, "CON")
        assert error.text() == "“CON” is reserved. Choose another name."
        assert not window.primary.isEnabled()
        for value, message in [
            ("tail.", "Remove the final dot."),
            ("tail ", "Remove the space at the end."),
            ("", "Enter a vault name."),
            ("bad\x01name", "Remove hidden control characters."),
        ]:
            name.selectAll()
            app.clipboard().setText(value)
            if value:
                QTest.keyClick(name, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
            else:
                QTest.keyClick(name, Qt.Key.Key_Backspace)
            assert error.isVisible() and error.text() == message
        name.selectAll()
        QTest.keyClicks(name, "Corrected vault")
        until(
            app,
            lambda: (
                window.snapshot.vault_name == "Corrected vault"
                and "convert" in window.snapshot.allowed_actions
            ),
        )
        assert not error.isVisible()
        assert window.primary.isEnabled()
        assert (
            window.validation_status.text()
            == "Destination looks valid. Final checks run during conversion."
        )
        assert not (tmp_path / "Corrected vault").exists()
        details_toggle = window.destination_details_toggle
        assert not window.destination_details.isVisible()
        details_toggle.setFocus()
        QTest.keyClick(details_toggle, Qt.Key.Key_Space)
        assert window.destination_details.isVisible()
        assert (
            "Existing contents are never removed" in window.destination_details.text()
        )
        assert "240 UTF-16-unit" in window.destination_details.text()
        QTest.keyClick(details_toggle, Qt.Key.Key_Space)
        assert not window.destination_details.isVisible()
    finally:
        window.close()
        until(app, lambda: not window.isVisible())
        window.shutdown()


def test_failed_vault_check_error_occurs_once_and_keeps_detailed_guidance(tmp_path):
    from brz2obsidian.application.contracts import SelectVault, SimpleCommand

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.tabs.setCurrentIndex(2)
    window.show()
    try:
        window.submit(SelectVault(path_or_null=str(tmp_path / "missing")))
        until(app, lambda: window.snapshot.vault is not None)
        window.submit(SimpleCommand(command="check_vault"))
        until(app, lambda: window.snapshot.result is not None)
        assert (
            window_text(window).count("Couldn’t read the vault. Check folder access.")
            == 1
        )
        assert not control(window, QLabel, "Vault folder error").isVisible()
        window.disclosure.click()
        until(app, lambda: bool(window.diagnostic_text.toPlainText()))
        assert (
            "Check the path, permissions and text encoding"
            in window.diagnostic_text.toPlainText()
        )
        assert str(tmp_path / "missing") in window.diagnostic_text.toPlainText()
    finally:
        window.close()
        until(app, lambda: not window.isVisible())
        window.shutdown()
