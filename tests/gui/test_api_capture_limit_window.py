"""The existing advanced controls expose a finite, exact 64-bit capture budget."""

import json

import pytest

pytest.importorskip("PySide6")
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QLineEdit, QPushButton

from brz2obsidian.application.operations import Operations
from brz2obsidian_ui.window import MainWindow
from tests.gui.test_local_api_source_window import control, until
from tests.support.local_api import KEY, api_server

pytestmark = pytest.mark.gui


def test_total_capture_field_preserves_large_values_and_requires_correction():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    try:
        control(window, QComboBox, "Source kind").setCurrentIndex(1)
        until(app, lambda: window.snapshot.source_kind == "local-api")
        field = control(window, QLineEdit, "Maximum total capture bytes")
        toggle = control(window, QPushButton, "Advanced API limits")
        assert not field.isVisible()
        toggle.click()
        assert field.isVisible() and field.text() == "1000000000"
        assert "9,223,372,036,854,775,807" in field.toolTip()
        for value in ("4294967296", "9223372036854775807"):
            field.setText(value)
            until(
                app,
                lambda value=value: (
                    window.snapshot.api_config is not None
                    and window.snapshot.api_config.max_total_capture_bytes == int(value)
                ),
            )
            assert window.snapshot.api_config.max_total_capture_bytes == int(value)
            assert field.text() == value
        for value in ("", "0", "-1", "1.5", "9223372036854775808"):
            field.setText(value)
            until(app, lambda: window.snapshot.api_config is None)
            error = control(window, QLabel, "Maximum total capture bytes error")
            assert error.isVisible() and error.text()
            assert field.text() == value
            assert not control(
                window, QPushButton, "Refresh accessible Brains"
            ).isEnabled()
        field.setText("1000000000")
        until(app, lambda: window.snapshot.api_config is not None)
        assert not error.isVisible()
    finally:
        window.shutdown()
        window.deleteLater()


def test_capture_setting_retires_review_and_reinspection_binds_new_budget(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    app = QApplication.instance() or QApplication([])
    with api_server() as (api, address):
        window = MainWindow()
        window.show()
        try:
            control(window, QComboBox, "Source kind").setCurrentIndex(1)
            until(app, lambda: window.snapshot.source_kind == "local-api")
            control(window, QLineEdit, "Local API address").setText(address)

            def inspect_selected():
                control(window, QPushButton, "Refresh accessible Brains").click()
                until(app, lambda: window.snapshot.brain_list_status == "ready")
                control(window, QComboBox, "Accessible Brains").setCurrentIndex(1)
                until(app, lambda: window.snapshot.source_selection is not None)
                control(window, QPushButton, "Inspect Brain").click()
                until(app, lambda: window.snapshot.reviewed is not None)

            until(app, lambda: window.snapshot.api_config.api_url == address)
            inspect_selected()
            original = window.snapshot.reviewed
            assert (
                original.source_selection.config.max_total_capture_bytes == 1000000000
            )
            control(window, QPushButton, "Advanced API limits").click()
            control(window, QLineEdit, "Maximum total capture bytes").setText(
                "4294967296"
            )
            until(app, lambda: window.snapshot.reviewed is None)
            assert window.snapshot.review_required
            assert window.snapshot.source_selection is None
            assert "convert" not in window.snapshot.allowed_actions
            assert not control(window, QPushButton, "Inspect Brain").isEnabled()
            inspect_selected()
            selected = window.snapshot.source_selection
            assert selected.config.max_total_capture_bytes == 4294967296
            assert window.snapshot.reviewed.source_selection == selected
            before_requests = list(api.requests)
            stale = Operations().convert_reviewed(selected, tmp_path, "stale", original)
            assert stale.outcome == "refused" and stale.review_required
            assert api.requests == before_requests and not (tmp_path / "stale").exists()
            window.parent_selected(str(tmp_path))
            name = control(window, QLineEdit, "Vault name")
            name.selectAll()
            QTest.keyClicks(name, "current")
            until(app, lambda: "convert" in window.snapshot.allowed_actions)
            control(window, QPushButton, "Convert").click()
            until(app, lambda: window.snapshot.publication is not None)
            assert window.snapshot.publication.receipt_verified
            record = json.loads(
                (tmp_path / "current/migration-record.json").read_bytes()
            )
            assert (
                record["run_metadata"]["source_acquisition"]["audit"]["limits"][
                    "max_total_capture_bytes"
                ]
                == 4294967296
            )
        finally:
            window.shutdown()
            window.deleteLater()
