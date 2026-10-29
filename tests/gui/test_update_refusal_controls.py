"""The actual workbench can recover a retained review after a refused offer."""

import os
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTabBar

from tests.application.test_update_refusal_state import refusal_case
from tests.gui.test_conversion_window import until, window_text
from tests.gui.update_worker_fixture import ReviewWorkerTransport

pytestmark = pytest.mark.gui


def test_bound_refusal_keeps_known_overview_and_reachable_refresh_without_apply(
    tmp_path, request
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    case = refusal_case(tmp_path, request)
    worker = ReviewWorkerTransport(case.operations)
    window = MainWindow(supervisor=worker)
    window.show()

    def button(name):
        return next(
            (
                row
                for row in window.findChildren(QPushButton)
                if row.isVisible() and row.accessibleName() == name
            ),
            None,
        )

    try:
        tabs = window.findChild(QTabBar)
        tabs.setCurrentIndex(
            next(i for i in range(tabs.count()) if tabs.tabText(i) == "Update vault")
        )
        selection = str(uuid4())
        window.runner.select_update(case.prepared.vault, selection_id=selection)
        window.runner.submit_update(
            {
                "command": "prepare",
                "kind": "source_update",
                "source": str(case.source),
                "vault": case.prepared.vault,
                "selection_id": selection,
            }
        )
        until(
            app,
            lambda: (
                window.runner.session.update_snapshot.binding is not None
                and not window.workbench.busy
                and "Unresolved choices: 1" in window_text(window)
            ),
        )
        binding = window.runner.session.update_snapshot.binding
        window.runner.submit_update(
            {
                "command": "choose",
                "binding": binding,
                "requirement_id": "retired-offer",
                "choice": "current",
                "assumptions_digest": "0" * 64,
            }
        )
        until(
            app,
            lambda: (
                not window.workbench.busy
                and "This choice changed. Refresh the current review"
                in window_text(window)
            ),
        )
        captions = [
            row.text() for row in window.findChildren(QLabel) if row.isVisible()
        ]
        assert "Changes: 3    Unresolved choices: 1" in captions
        assert (
            button("Apply update") is not None
            and not button("Apply update").isEnabled()
        )
        refresh = button("Refresh review")
        assert refresh is not None and refresh.isEnabled()
        before = window.runner.session.update_snapshot.revision
        refresh.click()
        until(
            app,
            lambda: (
                window.runner.session.update_snapshot.revision > before
                and not window.workbench.busy
                and window.runner.session.update_snapshot.reply.code != "offer_changed"
            ),
        )
        state = window.runner.session.update_snapshot
        assert state.changes == 3 and state.unresolved == 1 and not state.ready
        assert state.history_retained is True and state.publication == "not_started"
        assert any(row.command == "refresh" for row in worker.commands)
        assert not any(row.command in ("save", "apply") for row in worker.commands)
        assert case.prepared.review.approvals == (case.guide,)
    finally:
        window.shutdown()
        worker.close()
        window.hide()
        window.deleteLater()
        app.processEvents()
