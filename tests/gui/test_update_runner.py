"""Actual Qt events and a hidden persistent producer during blocked native I/O."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from threading import Event

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication, QPushButton

from brz2obsidian.application.runner import HostRunner
from brz2obsidian.application.transport import Supervisor

pytestmark = pytest.mark.gui


def test_host_reports_external_launch_failure_as_not_started(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "unmodified-vault"
    vault.mkdir()
    (vault / "Personal.md").write_bytes(b"Personal exact\r\n")
    views, launches = [], []

    def unavailable(*args, **kwargs):
        launches.append(True)
        raise OSError("private external launch detail")

    monkeypatch.setattr(subprocess, "Popen", unavailable)

    class Bridge(QObject):
        changed = Signal(object)

        @Slot(object)
        def receive(self, state):
            assert QThread.currentThread() == app.thread()
            views.append(state)

    bridge = Bridge()
    bridge.changed.connect(bridge.receive)
    runner = HostRunner(
        Supervisor(Path(sys.executable), Path(__file__).resolve().parents[2] / "src"),
        on_update=lambda value: None,
        on_page=lambda value: None,
        on_update_review=bridge.changed.emit,
    )
    try:
        selection = "11111111-1111-4111-8111-111111111111"
        runner.select_update(str(vault), selection_id=selection)
        runner.submit_update(
            {
                "command": "prepare",
                "vault": str(vault),
                "selection_id": selection,
                "kind": "onboarding",
                "source": None,
            }
        )
        deadline = time.monotonic() + 5
        while not (
            launches
            and any(view.active_request_id is not None for view in views)
            and views[-1].active_request_id is None
        ):
            assert time.monotonic() < deadline, (
                "Owned launch-failure diagnostic exhausted"
            )
            app.processEvents()
            time.sleep(0.005)
        state = views[-1]
        assert state.publication == "not_started" and not state.needs_inspection
        assert (
            state.transport_phase == "not_started"
            and state.transport_code == "launch_failure"
        )
        assert state.binding is None and not state.ready and not state.history_retained
        assert "private external launch detail" not in repr(state)
        assert (vault / "Personal.md").read_bytes() == b"Personal exact\r\n"
        assert sorted(path.name for path in vault.iterdir()) == ["Personal.md"]
    finally:
        runner.shutdown()


_NATIVE_READER = """import sys, time
from pathlib import Path
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_worker import UpdateWorker
entered, release, expected = map(Path, sys.argv[1:])
native = Operations.inspect_history
def blocked(self, vault, **kwargs):
    assert Path(vault).resolve() == expected.resolve()
    entered.write_text('actual native I/O entry', encoding='utf-8')
    deadline = time.monotonic() + 20
    while not release.exists():
        if time.monotonic() >= deadline:
            raise OSError('owned diagnostic barrier exhausted')
        time.sleep(.01)
    return native(self, vault, **kwargs)
Operations.inspect_history = blocked
UpdateWorker(output=sys.stdout.buffer).serve(sys.stdin.buffer)
"""


def test_qt_host_uses_live_control_while_real_persistent_worker_waits_for_native_io(
    tmp_path, monkeypatch
):
    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "vault"
    vault.mkdir()
    entered, release = tmp_path / "native-entered", tmp_path / "native-release"
    driver = tmp_path / "blocked-native-reader.py"
    driver.write_text(_NATIVE_READER, encoding="utf-8")
    children = []
    launch = subprocess.Popen

    def real_hidden_child(argv, *args, **kwargs):
        assert argv[1:] == ["-m", "brz2obsidian.worker"]
        child = launch(
            [argv[0], "-u", str(driver), str(entered), str(release), str(vault)],
            *args,
            **kwargs,
        )
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", real_hidden_child)
    views, ticks, clicks = [], [], []

    class Bridge(QObject):
        changed = Signal(object)

        @Slot(object)
        def receive(self, state):
            assert QThread.currentThread() == app.thread()
            views.append(state)
            if state.control_code == "cancellation_requested" and not release.exists():
                assert entered.exists() and state.active_request_id is not None
                release.write_text(
                    "control delivered before native I/O returned", encoding="utf-8"
                )

    bridge = Bridge()
    bridge.changed.connect(bridge.receive)
    runner = HostRunner(
        Supervisor(Path(sys.executable), Path(__file__).resolve().parents[2] / "src"),
        on_update=lambda value: None,
        on_page=lambda value: None,
        on_update_review=bridge.changed.emit,
    )
    button = QPushButton("Stop safely")
    button.clicked.connect(lambda: (clicks.append(True), runner.cancel_update()))
    scheduled = []
    timer = QTimer()

    def heartbeat():
        if entered.exists() and not release.exists():
            ticks.append(True)
            if not scheduled:
                scheduled.append(True)
                QTimer.singleShot(0, button.click)

    timer.timeout.connect(heartbeat)
    timer.start(5)

    def pump_until(predicate, timeout=25):
        deadline = time.monotonic() + timeout
        while not predicate():
            assert time.monotonic() < deadline, "Owned Qt/worker diagnostic exhausted"
            app.processEvents()
            time.sleep(0.005)

    try:
        selection = "11111111-1111-4111-8111-111111111111"
        runner.select_update(str(vault), selection_id=selection)
        runner.submit_update(
            {"command": "close", "binding": None, "choice": "continue"}
        )
        pump_until(
            lambda: bool(
                views
                and views[-1].reply
                and views[-1].reply.code == "continue_review"
                and views[-1].active_request_id is None
            )
        )
        runner.submit_update(
            {
                "command": "prepare",
                "vault": str(vault),
                "selection_id": selection,
                "kind": "onboarding",
                "source": None,
            }
        )
        pump_until(
            lambda: bool(
                views
                and views[-1].reply
                and views[-1].reply.kind == "onboarding"
                and views[-1].active_request_id is None
            )
        )
        state = views[-1]
        assert state.reply.status == "cancelled_before_publication"
        assert state.reply.publication == "not_published" and not state.ready
        assert ticks and clicks and release.exists()
        assert len(children) == 1 and children[0].poll() is None
        runner.submit_update(
            {"command": "close", "binding": state.binding, "choice": "discard"}
        )
        pump_until(
            lambda: bool(views[-1].reply and views[-1].reply.code == "context_closed")
        )
        assert children[0].poll() == 0
        assert list(vault.iterdir()) == []
    finally:
        release.touch()
        timer.stop()
        runner.shutdown()
        button.close()
        # This owned child can only inspect; EOF cleanup cannot stop a publisher.
        for child in children:
            if child.poll() is None:
                if not child.stdin.closed:
                    child.stdin.close()
                child.wait(timeout=10)


@pytest.mark.parametrize("boundary", ("launch", "admission"))
def test_qt_host_preserves_queued_cancel_and_fresh_child_epoch(
    tmp_path, monkeypatch, boundary
):
    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "vault"
    vault.mkdir()
    entered, release_native = tmp_path / "entered", tmp_path / "release-native"
    driver = tmp_path / "reader.py"
    driver.write_text(_NATIVE_READER, encoding="utf-8")
    at_boundary, release_boundary = Event(), Event()
    launch = subprocess.Popen
    children, views = [], []

    class AdmissionPipe:
        def __init__(self, actual):
            self.actual = actual

        def write(self, data):
            if json.loads(data)["arguments"]["command"] == "prepare":
                at_boundary.set()
                assert release_boundary.wait(10), "Owned admission barrier exhausted"
            return self.actual.write(data)

        def __getattr__(self, name):
            return getattr(self.actual, name)

    def real_child(argv, *args, **kwargs):
        if boundary == "launch" and not children:
            at_boundary.set()
            assert release_boundary.wait(10), "Owned launch barrier exhausted"
        child = launch(
            [argv[0], "-u", str(driver), str(entered), str(release_native), str(vault)],
            *args,
            **kwargs,
        )
        if boundary == "admission":
            child.stdin = AdmissionPipe(child.stdin)
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", real_child)

    class Bridge(QObject):
        changed = Signal(object)

        @Slot(object)
        def receive(self, state):
            assert QThread.currentThread() == app.thread()
            views.append(state)
            if state.control_code == "cancellation_queued":
                release_boundary.set()
            if state.control_code == "cancellation_requested":
                release_native.touch()

    bridge = Bridge()
    bridge.changed.connect(bridge.receive)
    runner = HostRunner(
        Supervisor(Path(sys.executable), Path(__file__).resolve().parents[2] / "src"),
        on_update=lambda value: None,
        on_page=lambda value: None,
        on_update_review=bridge.changed.emit,
    )

    def pump_until(predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while not predicate():
            assert time.monotonic() < deadline, (
                "Owned launch/control diagnostic exhausted"
            )
            app.processEvents()
            time.sleep(0.005)

    try:
        selection = "11111111-1111-4111-8111-111111111111"
        runner.select_update(str(vault), selection_id=selection)
        runner.submit_update(
            {
                "command": "prepare",
                "vault": str(vault),
                "selection_id": selection,
                "kind": "onboarding",
                "source": None,
            }
        )
        pump_until(at_boundary.is_set)
        runner.cancel_update()
        pump_until(
            lambda: bool(
                views and views[-1].reply and views[-1].active_request_id is None
            )
        )
        state = views[-1]
        assert state.reply.status == "cancelled_before_publication" and not state.ready
        assert state.reply.publication == "not_published"
        assert release_boundary.is_set()
        if boundary == "launch":
            assert not entered.exists(), (
                "A queued cancellation must precede native dispatch"
            )
        elif entered.exists():
            assert entered.exists() and release_native.exists()
        else:
            assert state.reply.code == "cancelled_before_preparation"
        old_epoch = state.worker_epoch
        runner.submit_update(
            {"command": "close", "binding": state.binding, "choice": "discard"}
        )
        pump_until(lambda: views[-1].reply.code == "context_closed")
        assert children[0].poll() == 0
        runner.submit_update(
            {"command": "close", "binding": None, "choice": "continue"}
        )
        pump_until(lambda: views[-1].reply.code == "continue_review")
        assert views[-1].worker_epoch != old_epoch and len(children) == 2
        runner.submit_update({"command": "close", "binding": None, "choice": "discard"})
        pump_until(lambda: views[-1].reply.code == "context_closed")
        assert children[1].poll() == 0 and list(vault.iterdir()) == []
    finally:
        release_boundary.set()
        release_native.touch()
        runner.shutdown()
        for child in children:
            if child.poll() is None:
                if not child.stdin.closed:
                    child.stdin.close()
                child.wait(timeout=10)
