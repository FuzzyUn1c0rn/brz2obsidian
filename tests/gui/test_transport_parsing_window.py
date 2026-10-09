import os
import sys
from pathlib import Path
from threading import Event

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication

from tests.gui.test_inspection_window import until

pytestmark = pytest.mark.gui


def test_real_response_parsing_keeps_queued_input_repaint_and_close_responsive(
    tmp_path, monkeypatch
):
    from brz2obsidian.application import transport
    from brz2obsidian.application.contracts import InspectCommand, SelectSource
    from brz2obsidian.application.protocol import RESPONSE_LIMIT, decode_response
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    source = tmp_path / "Été selected archive.brz"
    original = (Path(__file__).parents[1] / "fixtures/minimal.brz").read_bytes()
    source.write_bytes(original)
    inventory = sorted(path.name for path in tmp_path.iterdir())
    entered, release, heartbeat = Event(), Event(), Event()
    observed = {}

    def held_decode(data, request):
        # Supervisor has already waited for its real child and drained both pipes.
        # Hold the accepted public decoder boundary, then use its real validation.
        assert request.operation == "inspect"
        assert 0 < len(data) <= RESPONSE_LIMIT
        assert data.endswith(b"\n")
        observed["request_id"] = request.request_id
        observed["qt_thread"] = QThread.currentThread() == app.thread()
        entered.set()
        assert release.wait(20), "Response decoder was not released by the test"
        response = decode_response(data, request)
        observed["response_id"] = response.request_id
        observed["operation"] = response.operation
        observed["status"] = response.result.status
        return response

    # Wrap where the public callable is consumed, without replacing the worker.
    monkeypatch.setattr(transport, "decode_response", held_decode)
    window = MainWindow(
        supervisor=transport.Supervisor(
            Path(sys.executable).absolute(), Path(__file__).parents[2] / "src"
        )
    )
    window.show()
    try:
        window.submit(SelectSource(path_or_null=str(source)))
        until(app, lambda: window.snapshot.source == str(source))
        window.submit(InspectCommand())
        until(app, entered.is_set)
        until(app, lambda: window.snapshot.busy_operation == "inspect")
        assert observed["qt_thread"] is False
        assert window.snapshot.active_request_id == observed["request_id"]
        assert window.snapshot.result is None
        assert not window.primary.isEnabled()
        assert not window.choose.isEnabled()
        assert not window.tabs.isEnabled()
        assert "Inspecting archive" in window.guidance.text()
        QTimer.singleShot(0, heartbeat.set)
        QTimer.singleShot(0, window.disclosure.click)
        until(app, lambda: heartbeat.is_set() and window.diagnostics_expanded)
        painted = []
        QTimer.singleShot(
            0, lambda: (window.repaint(), painted.append(not window.grab().isNull()))
        )
        until(app, lambda: bool(painted))
        assert painted == [True]
        assert window.snapshot.source == str(source)
        assert window.source_path.toPlainText() == str(source)
        assert window.snapshot.result is None
        assert not release.is_set()
        window.close()
        until(app, lambda: window.snapshot.close_pending)
        assert window.isVisible() and not release.is_set()
        assert window.snapshot.result is None
        release.set()
        until(app, lambda: not window.isVisible())
        assert observed["response_id"] == observed["request_id"]
        assert observed["operation"] == "inspect"
        assert observed["status"] == "inspection_clean"
        assert window.snapshot.result.status == "inspection_clean"
        assert source.read_bytes() == original
        assert sorted(path.name for path in tmp_path.iterdir()) == inventory
    finally:
        release.set()
        window.close()
        until(app, lambda: not window.isVisible())
        window.shutdown()
