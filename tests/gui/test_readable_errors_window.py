"""Readable failure text remains literal in the actual Qt widgets."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextOption

from brz2obsidian.application.contracts import (
    ApiAcquisitionConfig,
    InspectCommand,
    LocalApiSourceSelection,
    SelectSource,
    WorkerResponse,
)
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.transport import Terminal
from brz2obsidian_ui.window import MainWindow
from tests.gui.test_inspection_window import until
from tests.support.local_api import BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import NOTE, PayloadApi

pytestmark = pytest.mark.gui


def test_converter_limitation_has_operation_title_and_literal_safe_item_context():
    api = PayloadApi()
    api.thoughts[HOME]["name"] = "Create <b>Link & path</b>\n\x1b[31m\u202e"
    api.payloads[NOTE] = b"<script>NOTE_BODY_CANARY</script>"
    api.attachments[NOTE]["dataLength"] = len(api.payloads[NOTE])
    with api_server(api) as (_, address):
        selection = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        result = Operations(credentials=lambda: KEY).inspect(selection)

    class PreparedRunner:
        def run(self, request):
            return Terminal(
                phase="completed",
                process_status=1,
                response=WorkerResponse(
                    request_id=request.request_id, operation="inspect", result=result
                ),
            )

    app = QApplication.instance() or QApplication([])
    window = MainWindow(supervisor=PreparedRunner())
    window.tabs.setCurrentIndex(1)
    window.show()
    window.submit(SelectSource(source_selection=selection))
    window.submit(InspectCommand())
    until(app, lambda: window.snapshot.result is not None)
    try:
        shown = window.findings.toPlainText()
        assert "Inspection could not continue" in shown
        assert "does not support this HTML" in shown
        assert 'Thought note: "Create <b>Link & path</b>[31m".' in shown
        assert "Source cannot be used" not in shown
        assert "planned contents" not in shown
        assert (
            window.findings.wordWrapMode()
            == QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere
        )
        assert "\x1b" not in shown and "\u202e" not in shown
        window.disclosure.click()
        until(app, lambda: bool(window.diagnostic_text.toPlainText()))
        assert result.findings[0].message in window.diagnostic_text.toPlainText()
        assert "CANARY" not in shown + window.diagnostic_text.toPlainText()
        assert (
            "Guidance: Review the planned contents"
            not in window.diagnostic_text.toPlainText()
        )
    finally:
        window.close()
        until(app, lambda: not window.isVisible())
        window.shutdown()
