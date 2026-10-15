"""Observable source controls with real worker and independently served HTTP."""

import os
from threading import Event
from time import monotonic

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontMetrics
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLineEdit,
    QPushButton,
    QStyle,
    QStyleOptionViewItem,
)

from tests.support.local_api import BRAIN, HOME, KEY, api_server

pytestmark = pytest.mark.gui


def until(app, condition):
    deadline = monotonic() + 15
    while not condition():
        app.processEvents()
        if monotonic() > deadline:
            pytest.fail("API GUI condition did not complete")


def control(window, kind, name):
    return next(w for w in window.findChildren(kind) if w.accessibleName() == name)


def test_source_choices_refresh_and_inspect_an_explicit_brain_with_real_worker(
    monkeypatch,
):
    from brz2obsidian_ui.window import MainWindow

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    app = QApplication.instance() or QApplication([])
    with api_server() as (api, address):
        other = "44444444-4444-4444-8444-444444444444"
        api.overrides["/api/brains"] = (
            200,
            [
                {"id": BRAIN, "name": "Duplicate", "homeThoughtId": HOME},
                {"id": other, "name": "Duplicate", "homeThoughtId": HOME},
            ],
        )
        api.overrides[f"/api/brains/{BRAIN}"] = (
            200,
            {"id": BRAIN, "name": "Duplicate", "homeThoughtId": HOME},
        )
        window = MainWindow()
        window.show()
        try:
            source = control(window, QComboBox, "Source kind")
            assert [source.itemText(i) for i in range(source.count())] == [
                "BRZ archive",
                "TheBrain local API",
            ]
            source.setCurrentIndex(1)
            address_field = control(window, QLineEdit, "Local API address")
            address_field.setText(address)
            until(app, lambda: window.snapshot.api_config.api_url == address)
            refresh = control(window, QPushButton, "Refresh accessible Brains")
            refresh.click()
            until(app, lambda: window.snapshot.brain_list_status == "ready")
            assert window.snapshot.source_selection is None
            brains = control(window, QComboBox, "Accessible Brains")
            assert BRAIN in brains.itemText(1)
            assert "Duplicate" in brains.itemText(1) and "Duplicate" in brains.itemText(
                2
            )
            assert other in brains.itemText(2)
            brains.setCurrentIndex(2)
            until(app, lambda: window.snapshot.source_selection is not None)
            assert window.snapshot.source_selection.brain_id == other
            brains.setCurrentIndex(1)
            until(app, lambda: window.snapshot.source_selection.brain_id == BRAIN)
            assert window.snapshot.source_selection.brain_id == BRAIN
            control(window, QPushButton, "Inspect Brain").click()
            until(app, lambda: window.snapshot.reviewed is not None)
            assert window.snapshot.result.status == "inspection_clean"
            address_field.setText("http://127.0.0.1:11523/api")
            until(app, lambda: window.snapshot.reviewed is None)
            assert window.snapshot.source_selection is None
        finally:
            window.shutdown()
            window.deleteLater()


def test_advanced_defaults_validation_and_delayed_listing_stay_responsive(monkeypatch):
    from brz2obsidian_ui.window import MainWindow

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    app = QApplication.instance() or QApplication([])
    entered, release = Event(), Event()
    with api_server() as (api, address):

        def delayed(_query):
            entered.set()
            release.wait(10)
            return 200, []

        api.overrides["/api/brains"] = delayed
        window = MainWindow()
        window.show()
        try:
            kind = control(window, QComboBox, "Source kind")
            kind.setCurrentIndex(1)
            until(app, lambda: window.snapshot.source_kind == "local-api")
            control(window, QLineEdit, "Local API address").setText(address)
            advanced = control(window, QPushButton, "Advanced API search limits")
            assert not control(window, QLineEdit, "Initial result limit").isVisible()
            advanced.click()
            assert control(window, QLineEdit, "Initial result limit").text() == "5000"
            assert control(window, QLineEdit, "Total search seconds").text() == "300"
            assert (
                control(window, QLineEdit, "Maximum search response bytes").text()
                == "128000000"
            )
            maximum = control(
                window, QLineEdit, "Maximum results (blank disables ceiling)"
            )
            assert maximum.text() == ""
            maximum.setText("-1")
            until(app, lambda: window.snapshot.api_config is None)
            refresh = control(window, QPushButton, "Refresh accessible Brains")
            assert not refresh.isEnabled()
            maximum.clear()
            until(app, lambda: window.snapshot.api_config is not None)
            refresh.click()
            until(
                app,
                lambda: (
                    entered.is_set() and window.snapshot.busy_operation == "list_brains"
                ),
            )
            assert not refresh.isEnabled() and not kind.isEnabled()
            heartbeat = []
            QTimer.singleShot(0, lambda: heartbeat.append(True))
            until(app, lambda: heartbeat)
            release.set()
            until(app, lambda: window.snapshot.brain_list_status == "empty")
            assert refresh.isEnabled()
            assert window.snapshot.source_selection is None
            assert "not an atomic snapshot" in window.api_consistency.text()
            assert "Conversion acquires again" in window.api_consistency.text()
            kind.setCurrentIndex(0)
            until(app, lambda: window.snapshot.source_kind == "brz")
            assert control(window, QPushButton, "Choose source archive").isVisible()
        finally:
            release.set()
            window.shutdown()
            window.deleteLater()


def test_real_worker_gui_publishes_only_after_api_review_and_destination(
    tmp_path, monkeypatch
):
    from brz2obsidian_ui.window import MainWindow

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    app = QApplication.instance() or QApplication([])
    with api_server() as (_, address):
        window = MainWindow()
        window.show()
        try:
            control(window, QComboBox, "Source kind").setCurrentIndex(1)
            until(app, lambda: window.snapshot.source_kind == "local-api")
            control(window, QLineEdit, "Local API address").setText(address)
            until(app, lambda: window.snapshot.api_config.api_url == address)
            control(window, QPushButton, "Refresh accessible Brains").click()
            until(app, lambda: window.snapshot.brain_list_status == "ready")
            control(window, QComboBox, "Accessible Brains").setCurrentIndex(1)
            until(app, lambda: window.snapshot.source_selection is not None)
            control(window, QPushButton, "Inspect Brain").click()
            until(app, lambda: window.snapshot.reviewed is not None)
            window.parent_selected(str(tmp_path))
            name = control(window, QLineEdit, "Vault name")
            QTest.keyClicks(name, "API GUI vault")
            until(app, lambda: "convert" in window.snapshot.allowed_actions)
            control(window, QPushButton, "Convert").click()
            until(app, lambda: window.snapshot.publication is not None)
            assert window.snapshot.publication.receipt_verified
            assert window.snapshot.result.status == "conversion_created"
            assert (tmp_path / "API GUI vault/migration-record.json").is_file()
            assert KEY not in window.snapshot.model_dump_json()
        finally:
            window.shutdown()
            window.deleteLater()


def test_real_worker_gui_graph_review_reacquires_and_publishes_literal_facts(
    tmp_path, monkeypatch
):
    from brz2obsidian_ui.window import MainWindow
    from tests.support.local_api_graph import (
        ONE_WAY_FORWARD,
        CompleteGraphApi,
        assert_published_graph,
    )

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    app = QApplication.instance() or QApplication([])
    with api_server(CompleteGraphApi()) as (api, address):
        window = MainWindow()
        window.show()
        try:
            control(window, QComboBox, "Source kind").setCurrentIndex(1)
            until(app, lambda: window.snapshot.source_kind == "local-api")
            control(window, QLineEdit, "Local API address").setText(address)
            until(app, lambda: window.snapshot.api_config.api_url == address)
            control(window, QPushButton, "Refresh accessible Brains").click()
            until(app, lambda: window.snapshot.brain_list_status == "ready")
            control(window, QComboBox, "Accessible Brains").setCurrentIndex(1)
            until(app, lambda: window.snapshot.source_selection is not None)
            control(window, QPushButton, "Inspect Brain").click()
            until(app, lambda: window.snapshot.reviewed is not None)
            window.parent_selected(str(tmp_path))
            QTest.keyClicks(control(window, QLineEdit, "Vault name"), "Graph GUI vault")
            until(app, lambda: "convert" in window.snapshot.allowed_actions)
            # A qualified arrow change is a real content change, even though its
            # canonical navigation remains related(A,B). Fresh review is needed.
            api.links[ONE_WAY_FORWARD]["direction"] = 3
            control(window, QPushButton, "Convert").click()
            until(
                app,
                lambda: (
                    window.snapshot.result.status == "conversion_refused"
                    and not window.snapshot.busy_operation
                ),
            )
            assert window.snapshot.publication.state == "not_published"
            assert not (tmp_path / "Graph GUI vault").exists()
            assert "inspect" in window.findings.toPlainText().lower()
            api.links[ONE_WAY_FORWARD]["direction"] = 5
            next(
                button
                for button in window.findChildren(QPushButton)
                if button.text() == "Inspect again"
            ).click()
            until(
                app,
                lambda: (
                    window.snapshot.reviewed is not None
                    and not window.snapshot.busy_operation
                ),
            )
            name = control(window, QLineEdit, "Vault name")
            name.selectAll()
            QTest.keyClicks(name, "Reviewed graph vault")
            until(app, lambda: "convert" in window.snapshot.allowed_actions)
            control(window, QPushButton, "Convert").click()
            until(
                app,
                lambda: (
                    window.snapshot.publication is not None
                    and window.snapshot.publication.receipt_verified
                ),
            )
            assert window.snapshot.publication.receipt_verified
            assert_published_graph(tmp_path / "Reviewed graph vault")
            assert "CANARY" not in window.snapshot.model_dump_json()
        finally:
            window.shutdown()
            window.deleteLater()


def test_failed_api_refresh_shows_safe_guidance_and_retries_same_selection(monkeypatch):
    from brz2obsidian_ui.window import MainWindow

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    app = QApplication.instance() or QApplication([])
    with api_server() as (api, address):
        window = MainWindow()
        window.show()
        try:
            control(window, QComboBox, "Source kind").setCurrentIndex(1)
            until(app, lambda: window.snapshot.source_kind == "local-api")
            control(window, QLineEdit, "Local API address").setText(address)
            until(app, lambda: window.snapshot.api_config.api_url == address)
            refresh = control(window, QPushButton, "Refresh accessible Brains")
            refresh.click()
            until(app, lambda: window.snapshot.brain_list_status == "ready")
            control(window, QComboBox, "Accessible Brains").setCurrentIndex(1)
            until(app, lambda: window.snapshot.source_selection is not None)
            api.overrides["/api/brains"] = (401, b"REMOTE_SERVICE_TOKEN_CANARY")
            refresh.click()
            until(app, lambda: window.snapshot.brain_list_status == "failed")
            assert window.snapshot.source_selection.brain_id == BRAIN
            assert not control(window, QPushButton, "Inspect Brain").isEnabled()
            assert "denied access" in window.findings.toPlainText()
            assert (
                "CANARY"
                not in window.findings.toPlainText() + window.snapshot.model_dump_json()
            )
            del api.overrides["/api/brains"]
            refresh.click()
            until(app, lambda: window.snapshot.brain_list_status == "ready")
            assert window.snapshot.source_selection.brain_id == BRAIN
            assert control(window, QPushButton, "Inspect Brain").isEnabled()
        finally:
            window.shutdown()
            window.deleteLater()


def test_narrow_popup_keeps_complete_distinct_ids_before_eliding_duplicate_names(
    monkeypatch,
):
    from brz2obsidian_ui.window import MainWindow

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    app = QApplication.instance() or QApplication([])
    ids = [
        BRAIN,
        "00000002-1111-4111-8111-111111111111",
        "00000003-1111-4111-8111-111111111111",
    ]
    with api_server() as (api, address):
        api.overrides["/api/brains"] = (
            200,
            [
                {
                    "id": key,
                    "name": "Synthetic duplicate Brain " * 8,
                    "homeThoughtId": HOME,
                }
                for key in ids
            ],
        )
        window = MainWindow()
        window.resize(440, 570)
        window.show()
        try:
            control(window, QComboBox, "Source kind").setCurrentIndex(1)
            until(app, lambda: window.snapshot.source_kind == "local-api")
            control(window, QLineEdit, "Local API address").setText(address)
            until(app, lambda: window.snapshot.api_config.api_url == address)
            control(window, QPushButton, "Refresh accessible Brains").click()
            until(app, lambda: window.snapshot.brain_list_status == "ready")
            brains = control(window, QComboBox, "Accessible Brains")
            brains.showPopup()
            app.processEvents()
            view = brains.view()
            assert view.isVisible() and window.width() == 440
            rendered = []
            for row, brain_id in enumerate(ids, start=1):
                index = view.model().index(row, 0)
                option = QStyleOptionViewItem()
                option.initFrom(view)
                option.rect = view.visualRect(index)
                option.textElideMode = view.textElideMode()
                option.font = view.font()
                option.text = index.data(Qt.ItemDataRole.DisplayRole)
                text_rect = view.style().subElementRect(
                    QStyle.SubElement.SE_ItemViewItemText, option, view
                )
                shown = QFontMetrics(option.font).elidedText(
                    option.text, option.textElideMode, text_rect.width()
                )
                assert brain_id in shown
                rendered.append(shown)
            assert len(set(rendered)) == 3
            QTest.mouseClick(
                view.viewport(),
                Qt.MouseButton.LeftButton,
                pos=view.visualRect(view.model().index(2, 0)).center(),
            )
            until(app, lambda: window.snapshot.source_selection is not None)
            assert window.snapshot.source_selection.brain_id == ids[1]
        finally:
            brains.hidePopup() if "brains" in locals() else None
            window.shutdown()
            window.deleteLater()
