import os
from pathlib import Path
from time import monotonic

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QPushButton

from tests.gui.test_conversion_window import window_text

pytestmark = pytest.mark.gui


def until(app, condition):
    deadline = monotonic() + 10
    while not condition():
        app.processEvents()
        if monotonic() > deadline:
            pytest.fail("GUI condition did not complete")


@pytest.mark.parametrize(
    "outcome,title",
    [
        ("clean", "ready for review"),
        ("warnings", "source warnings"),
        ("refused", "Inspection could not continue"),
        ("failed", "Inspection could not complete"),
    ],
)
def test_injected_safe_outcomes_and_async_picker_cancellation(outcome, title):
    from brz2obsidian.application.contracts import (
        InspectCommand,
        SelectSource,
        WorkerResponse,
    )
    from brz2obsidian.application.operations import inspect
    from brz2obsidian.application.transport import Terminal
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    original = inspect(source)
    result = original.model_copy(
        update={
            "outcome": outcome,
            "status": "inspection_" + outcome,
            "reviewed": original.reviewed.model_copy(update={"outcome": outcome})
            if outcome in ("clean", "warnings")
            else None,
        }
    )

    class InjectedRunner:
        def run(self, request):
            return Terminal(
                phase="completed",
                process_status=0
                if outcome == "clean"
                else 2
                if outcome == "warnings"
                else 1,
                response=WorkerResponse(
                    request_id=request.request_id, operation="inspect", result=result
                ),
            )

    class AsyncPicker:
        def choose_source(self, callback):
            QTimer.singleShot(0, lambda: callback(None))

    window = MainWindow(supervisor=InjectedRunner(), dialogs=AsyncPicker())
    window.show()
    window.submit(SelectSource(path_or_null=str(source)))
    until(app, lambda: window.snapshot.source == str(source))
    window.submit(InspectCommand())
    until(app, lambda: window.snapshot.result is not None)
    displayed = window_text(window)
    assert title in displayed
    assert "Actual notes: unavailable" in displayed
    retained = window.snapshot.result
    window.choose_source()
    app.processEvents()
    assert window.snapshot.result is retained
    assert not window.diagnostics_expanded
    window.findChild(QPushButton, "diagnosticDisclosure").click()
    assert "Authored body" not in window.findChild(QPlainTextEdit).toPlainText()
    window.close()
    until(app, lambda: not window.isVisible())
    window.shutdown()
