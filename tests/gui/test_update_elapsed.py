"""Visible elapsed time advances independently of worker progress authority."""

import os
import re
from threading import Event
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QProgressBar

from brz2obsidian.application.update_context_contracts import UpdateContextResult
from brz2obsidian.application.update_stream import WorkerProgress
from brz2obsidian.application.vault_progress_contracts import VaultProgress
from tests.gui.test_conversion_window import until, window_text
from tests.gui.update_projection_fixture import ProjectedReviewTransport, ReviewControls

pytestmark = pytest.mark.gui


def elapsed_seconds(window):
    match = re.search(r" · (\d+):(\d{2}) elapsed", window_text(window))
    assert match is not None, "The active request must display elapsed time"
    return int(match[1]) * 60 + int(match[2])


def test_elapsed_advances_between_observations_without_changing_operation_truth(
    tmp_path,
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "Vault"
    vault.mkdir()
    source = tmp_path / "Source.brz"
    source.write_bytes(b"source")
    next_frame, reported, release, second_active, second_release = (
        Event() for _ in range(5)
    )
    requests = []

    def project(actual, callbacks):
        assert actual.arguments.command == "prepare"
        requests.append(actual)
        if len(requests) == 1:
            for ordinal, milliseconds in ((1, 2300), (2, 2400)):
                if ordinal == 2:
                    assert next_frame.wait(10)
                callbacks["on_progress"](
                    actual,
                    WorkerProgress(
                        request_id=actual.request_id,
                        sequence=actual.sequence,
                        ordinal=ordinal,
                        elapsed_ms=milliseconds,
                        value=VaultProgress(
                            phase="snapshot_preparation",
                            completed_units=2,
                            total_units=5,
                            unit="files",
                        ),
                    ),
                )
            reported.set()
            assert release.wait(10)
        else:
            second_active.set()
            assert second_release.wait(10)
        return UpdateContextResult(
            status="cancelled_before_publication",
            code="controlled_stopped",
            kind="source_update",
            publication="not_published",
            history_retained=True,
            next_actions=("inspect_history",),
        )

    window = MainWindow(supervisor=ProjectedReviewTransport(project))
    window.show()
    ReviewControls(window, app)
    try:
        selection = str(uuid4())
        window.runner.select_update(str(vault), selection_id=selection)
        command = {
            "command": "prepare",
            "kind": "source_update",
            "vault": str(vault),
            "source": str(source),
            "selection_id": selection,
        }
        window.runner.submit_update(command)
        until(app, lambda: "Snapshot preparation" in window_text(window))
        initial = elapsed_seconds(window)
        assert initial >= 2
        state = window.runner.session.update_snapshot
        assert state.active_request_id == requests[0].request_id
        assert state.reply is None and not state.ready
        progress = next(
            widget
            for widget in window.findChildren(QProgressBar)
            if widget.accessibleName() == "Update operation progress"
        )
        assert (progress.minimum(), progress.maximum(), progress.value()) == (0, 5, 2)

        # Real Qt time, one retained nonzero observation; no private clock seam.
        QTest.qWait(1400)
        advanced = elapsed_seconds(window)
        assert advanced > initial, "Elapsed must advance without another worker frame"
        assert window.runner.session.update_snapshot == state
        assert "Snapshot preparation" in window_text(window)
        assert "2 of 5 files" in window_text(window)
        assert (progress.minimum(), progress.maximum(), progress.value()) == (0, 5, 2)

        next_frame.set()
        until(app, lambda: reported.is_set())
        until(app, lambda: window.runner.session.update_snapshot.progress.ordinal == 2)
        QTest.qWait(300)
        assert elapsed_seconds(window) >= advanced, "Later observations must not rewind elapsed"
        assert window.runner.session.update_snapshot.active_request_id == state.active_request_id
        assert window.runner.session.update_snapshot.reply is None
        assert not window.runner.session.update_snapshot.ready
        assert "Snapshot preparation" in window_text(window)
        assert "2 of 5 files" in window_text(window)

        release.set()
        until(app, lambda: window.runner.session.update_snapshot.active_request_id is None)
        until(app, lambda: "Stopped before file publication" in window_text(window))
        assert " elapsed" not in window_text(window)
        assert window.runner.session.update_snapshot.publication == "not_published"

        window.runner.submit_update(command)
        until(app, lambda: second_active.is_set())
        until(app, lambda: "Running prepare" in window_text(window))
        assert elapsed_seconds(window) < initial, "A new request must reset its elapsed clock"
        assert window.runner.session.update_snapshot.progress is None
        assert window.runner.session.update_snapshot.active_request_id == requests[1].request_id
        assert requests[1].request_id != requests[0].request_id
        second_release.set()
        until(app, lambda: window.runner.session.update_snapshot.active_request_id is None)
        window.runner.select_update(str(vault), selection_id=str(uuid4()))
        app.processEvents()
        assert " elapsed" not in window_text(window)
        assert list(vault.iterdir()) == []
    finally:
        next_frame.set()
        release.set()
        second_release.set()
        window.shutdown()
        window.hide()
        window.deleteLater()
        app.processEvents()
