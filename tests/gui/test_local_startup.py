import os
from functools import partial
from pathlib import Path
from threading import Event

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from tests.gui.test_inspection_window import until

pytestmark = pytest.mark.gui


def test_slow_preferences_leave_queued_gui_events_and_newer_edits_responsive(tmp_path):
    from brz2obsidian.application.contracts import SetDestination
    from brz2obsidian_ui.__main__ import LocalApplication
    from brz2obsidian_ui.instance import LocalInstance
    from brz2obsidian_ui.preferences import ParentPreferences
    from brz2obsidian_ui.startup import StartupCoordinator

    class App(QObject):
        aboutToQuit = Signal()

        def quit(self):
            pass

    app = QApplication.instance() or QApplication([])
    loading, release, heartbeat, restored = Event(), Event(), Event(), Event()
    store = ParentPreferences(tmp_path / "preferences")
    store.save(str(tmp_path / "Old parent"))

    class Preferences:
        def load(self):
            loading.set()
            assert release.wait(5)
            result = store.load()
            restored.set()
            return result

        def save(self, parent):
            return store.save(parent)

    local = LocalApplication(
        App(),
        None,
        None,
        coordinator_factory=partial(
            StartupCoordinator,
            instance_factory=lambda root, callback: LocalInstance(
                tmp_path / "instance", callback
            ),
        ),
        preferences=Preferences(),
    )
    try:
        local.start()
        until(app, lambda: local.window is not None and loading.is_set())
        window = local.window
        QTimer.singleShot(0, heartbeat.set)
        window.submit(
            SetDestination(parent_or_null=str(tmp_path / "New parent"), vault_name="")
        )
        until(
            app,
            lambda: (
                heartbeat.is_set()
                and window.snapshot.parent == str(tmp_path / "New parent")
            ),
        )
        assert not restored.is_set()
        updates = []
        window.prepared.connect(updates.append)
        release.set()
        until(app, lambda: restored.is_set() and bool(updates))
        assert window.snapshot.parent == str(tmp_path / "New parent")
        assert window.snapshot.source is None
        assert window.snapshot.result is None
        assert window.snapshot.reviewed is None
        assert window.snapshot.vault is None
    finally:
        release.set()
        local.coordinator.shutdown()
        if local.window is not None:
            local.window.shutdown()
            local.window.hide()
            local.window.deleteLater()


def test_unavailable_preferences_do_not_bypass_or_prevent_instance_ownership(
    tmp_path, monkeypatch
):
    from brz2obsidian_ui.__main__ import LocalApplication
    from brz2obsidian_ui.instance import InstanceResult
    from brz2obsidian_ui.preferences import ParentPreferences
    from brz2obsidian_ui.startup import StartupCoordinator

    class App(QObject):
        aboutToQuit = Signal()

        def __init__(self):
            super().__init__()
            self.exited = Event()

        def quit(self):
            self.exited.set()

    # The default coordination resolver uses this disposable user-profile root.
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "Profile"))
    app = QApplication.instance() or QApplication([])
    blocked = tmp_path / "Unavailable preferences"
    blocked.write_text("retained", "utf-8")
    preferences = ParentPreferences(blocked)

    class Activator:
        def activate(self, hwnd):
            return InstanceResult(
                "attention_requested",
                "The app is already open. Select it from the taskbar.",
            )

    coordinator = partial(StartupCoordinator, activator_factory=Activator)
    first_app, second_app = App(), App()
    first = LocalApplication(
        first_app, None, None, preferences=preferences, coordinator_factory=coordinator
    )
    second = LocalApplication(
        second_app, None, None, preferences=preferences, coordinator_factory=coordinator
    )
    try:
        first.start()
        until(
            app,
            lambda: (
                first.window is not None
                and bool(first.window.statusBar().currentMessage())
            ),
        )
        assert first.window.snapshot.parent is None
        assert "could not be read" in first.window.statusBar().currentMessage()
        second.start()
        until(app, second_app.exited.is_set)
        assert second.window is None
        assert first.window.isVisible()
        assert blocked.read_text("utf-8") == "retained"
    finally:
        second.coordinator.shutdown()
        first.coordinator.shutdown()
        if first.window is not None:
            first.window.shutdown()
            first.window.hide()
            first.window.deleteLater()


def test_fresh_launch_restores_parent_but_discards_populated_session_and_geometry(
    tmp_path,
):
    from brz2obsidian.application.contracts import (
        InspectCommand,
        SelectSource,
        SelectVault,
        SetDestination,
    )
    from brz2obsidian_ui.__main__ import LocalApplication
    from brz2obsidian_ui.preferences import ParentPreferences

    class App(QObject):
        aboutToQuit = Signal()

    class Coordinator:
        def __init__(self, root, primary, exiting, feedback):
            self.primary = primary

        def begin(self):
            self.primary()

        def window_ready(self, hwnd):
            pass

        def shutdown(self):
            pass

    app = QApplication.instance() or QApplication([])
    store = ParentPreferences(tmp_path / "Preferences")
    first = LocalApplication(
        App(), None, None, coordinator_factory=Coordinator, preferences=store
    )
    fresh = LocalApplication(
        App(), None, None, coordinator_factory=Coordinator, preferences=store
    )
    try:
        first.start()
        source = str((Path(__file__).parents[1] / "fixtures/minimal.brz").absolute())
        first.window.submit(SelectSource(path_or_null=source))
        until(app, lambda: first.window.snapshot.source == source)
        first.window.submit(SelectVault(path_or_null=str(tmp_path)))
        first.window.submit(
            SetDestination(parent_or_null=str(tmp_path), vault_name="Saved name")
        )
        until(
            app,
            lambda: (
                not first.window.snapshot.validation_request_id
                and first.window.snapshot.parent == str(tmp_path)
            ),
        )
        first.window.submit(InspectCommand())
        until(app, lambda: first.window.snapshot.reviewed is not None)
        assert first.window.snapshot.result is not None
        assert first.window.runner.session.diagnostics_page().text
        first.window.resize(555, 600)
        changed_geometry = first.window.size()
        until(app, lambda: store.load().parent == str(tmp_path))
        first.window.shutdown()
        first.window.hide()
        fresh.start()
        until(app, lambda: fresh.window.snapshot.parent == str(tmp_path))
        snapshot = fresh.window.snapshot
        assert snapshot.source is None and snapshot.vault is None
        assert snapshot.vault_name == ""
        assert snapshot.reviewed is None and snapshot.result is None
        assert fresh.window.runner.session.diagnostics_page().text == ""
        assert fresh.window.size() != changed_geometry
    finally:
        for local in (first, fresh):
            if local.window is not None:
                local.window.shutdown()
                local.window.hide()
                local.window.deleteLater()
