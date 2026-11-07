"""The actual Qt adapter shows canonical attachment format restrictions."""

import os
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QLabel

from brz2obsidian.application.checkpoint_contracts import CheckpointRead
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_contracts import UpdateResult
from tests.application.test_format_attachment_choices import (
    format_attachment_preparation,
)
from tests.gui.test_conversion_window import until, window_text
from tests.gui.update_projection_fixture import ReviewControls
from tests.gui.update_worker_fixture import ReviewWorkerTransport

pytestmark = pytest.mark.gui


def test_format_attachment_controls_show_canonical_current_only_guidance(tmp_path):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "Vault"
    vault.mkdir()
    source = tmp_path / "Incoming.brz"
    source.write_bytes(b"Declared outer input; no physical source preparation claimed")
    prepared = format_attachment_preparation().model_copy(update={"vault": str(vault)})

    class Inputs(Operations):
        # Only native preparation/history observations are controlled. Core,
        # canonical pages, persistent worker, codecs, host and Qt stay real.
        def prepare_format_transition(self, path, incoming=None):
            assert (path, incoming) == (str(vault), str(source))
            return UpdateResult(
                status="unresolved",
                code="prepared",
                kind="format_transition",
                preparation=prepared,
                changes=2,
                unresolved=2,
                history_retained=True,
                checkpoint_commit=prepared.locator.commit,
                next_actions=("resolve_update", "save_update"),
            )

        def read_checkpoint(self, path, **kwargs):
            assert path == str(vault)
            return CheckpointRead(
                schema_id="brz2obsidian.checkpoint-read",
                schema_version=1,
                status="valid",
                code="valid",
                locator=prepared.locator,
                manifest=None,
                review=None,
                message="Declared current checkpoint",
            )

    transport = ReviewWorkerTransport(Inputs())
    window = MainWindow(supervisor=transport)
    window.show()
    controls = ReviewControls(window, app)
    try:
        selection = str(uuid4())
        window.runner.select_update(str(vault), selection_id=selection)
        window.runner.submit_update(
            {
                "command": "prepare",
                "kind": "format_transition",
                "source": str(source),
                "vault": str(vault),
                "selection_id": selection,
            }
        )
        until(
            app,
            lambda: (
                window.runner.session.update_snapshot.binding is not None
                and not window.workbench.busy
            ),
        )
        controls.select("Other choices")
        until(
            app,
            lambda: (
                not window.workbench.busy
                and bool(window.runner.session.update_snapshot.reply.offers)
            ),
        )
        title = "format choice 1"
        until(
            app, lambda: controls.button("Keep vault version for " + title) is not None
        )
        assert controls.button("Keep vault version for " + title).isEnabled()
        assert not controls.button("Use incoming version for " + title).isEnabled()
        assert not controls.button("Keep both versions for " + title).isEnabled()
        assert any(
            "keep vault version is required for attachment format review"
            in label.text()
            for label in window.findChildren(QLabel)
            if label.isVisible()
        )
        assert "Recorded output format: 7" in window_text(window)
        assert "Incoming output format: 8" in window_text(window)
        assert not any(row.command == "choose" for row in transport.commands)
        assert list(vault.iterdir()) == []
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()
