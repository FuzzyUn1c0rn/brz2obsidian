"""Bound review inputs and unsaved decisions survive internal UI transitions."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton

from brz2obsidian.application.checkpoint_contracts import CheckpointRead
from brz2obsidian.application.history_workflow_contracts import HistoryAdmission
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_contracts import UpdateResult
from tests.application.test_update_presentation import literal_operation_result
from tests.gui.test_conversion_window import until, window_text
from tests.gui.test_update_history_controls import native_result
from tests.gui.update_projection_fixture import ReviewControls, ReviewDialogs
from tests.gui.update_worker_fixture import ReviewWorkerTransport

pytestmark = pytest.mark.gui


def review_window(tmp_path):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    source = tmp_path / "Source A.brz"
    source.write_bytes(b"source A")
    vault = tmp_path / "Vault A"
    vault.mkdir()
    second = tmp_path / "Vault B"
    second.mkdir()
    actual = literal_operation_result()
    prepared = actual.preparation.model_copy(update={"vault": str(vault)})
    actual = actual.model_copy(update={"preparation": prepared})

    class NativeInputs(Operations):
        def prepare_update(self, *args, **kwargs):
            return actual

        def read_checkpoint(self, *args, **kwargs):
            return CheckpointRead(
                schema_id="brz2obsidian.checkpoint-read",
                schema_version=1,
                status="valid",
                code="valid",
                locator=prepared.locator,
                manifest=None,
                review=None,
                message="Controlled current checkpoint",
            )

        def save_update(self, *args, **kwargs):
            return UpdateResult(
                status="refused",
                code="save_unavailable",
                kind="source_update",
                summary="Save could not complete. Review is still open.",
                history_retained=True,
                next_actions=("inspect_history",),
            )

        def inspect_history_workflow(self, path):
            assert path == str(vault)
            return HistoryAdmission(
                status="available",
                code="history_available",
                next_actions=("review_update",),
                operation=native_result(),
                checkpoint=prepared.locator,
                history_retained=True,
                recovery_gaps=(),
                findings=(),
                summary="History entered after explicit discard",
                guidance=(),
            )

    transport = ReviewWorkerTransport(NativeInputs())
    dialogs = ReviewDialogs(source, vault)
    window = MainWindow(supervisor=transport, dialogs=dialogs)
    window.show()
    controls = ReviewControls(window, app)
    controls.click("Choose incoming BRZ")
    controls.click("Choose update vault")
    controls.click("Prepare update review")
    controls.select("Other choices")
    until(app, lambda: window_text(window).count("Chosen: current") == 2)
    return app, window, controls, transport, dialogs, source, vault, second


def test_bound_review_locks_prospective_inputs_and_displays_actual_apply_target(
    tmp_path,
):
    app, window, controls, transport, dialogs, source, vault, second = review_window(
        tmp_path
    )
    try:
        controls.select("Archive & vault")
        for name in (
            "Choose update vault",
            "Choose incoming BRZ",
            "Choose original BRZ evidence",
        ):
            button = next(
                w
                for w in window.findChildren(QPushButton)
                if w.accessibleName() == name
            )
            assert not button.isEnabled(), (
                "A bound review must lock prospective " + name
            )
        role = next(
            w
            for w in window.findChildren(QComboBox)
            if w.accessibleName() == "Review operation"
        )
        assert not role.isEnabled()
        dialogs.vault = str(second)
        dialogs.source = str(tmp_path / "Source B.brz")
        controls.button("Choose update vault").click()
        controls.button("Choose incoming BRZ").click()
        app.processEvents()
        assert str(vault) in window_text(window) and str(source) in window_text(window)
        assert str(second) not in window_text(window)
        assert window.runner.session.update_snapshot.binding.vault == str(vault)
        assert "Reviewed vault: " + str(vault) in window_text(window)
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()


def test_inspecting_history_after_failed_save_requires_explicit_preserved_transition(
    tmp_path,
):
    app, window, controls, transport, _dialogs, _source, vault, second = review_window(
        tmp_path
    )
    try:
        before = window.runner.session.update_snapshot.binding
        window.runner.submit_update({"command": "save", "binding": before})
        until(app, lambda: any(r.code == "save_unavailable" for r in transport.replies))
        controls.click("Inspect history and recovery")
        until(
            app,
            lambda: (
                controls.button("Continue review") is not None
                or any(c.command == "close" for c in transport.commands)
            ),
        )
        assert not any(c.command == "close" for c in transport.commands), (
            "Inspect history must not silently discard accepted unsaved decisions"
        )
        controls.click("Continue review")
        controls.select("Other choices")
        assert window_text(window).count("Chosen: current") == 2
        assert window.runner.session.update_snapshot.binding == before
        controls.click("Inspect history and recovery")
        controls.click("Discard review and inspect history")
        until(
            app, lambda: "History entered after explicit discard" in window_text(window)
        )
        commands = [c.command for c in transport.commands]
        assert (
            commands.count("close") == 1
            and commands.count("save") == 1
            and commands.count("history") == 1
        )
        assert all(
            c.choice == "discard" for c in transport.commands if c.command == "close"
        )
        assert list(vault.iterdir()) == [] and list(second.iterdir()) == []
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()
