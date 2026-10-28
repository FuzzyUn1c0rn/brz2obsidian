"""Native Windows picker spelling preserves target authority at the UI boundary."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from brz2obsidian.application.checkpoint_contracts import CheckpointRead
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_contracts import UpdateResult
from tests.application.test_update_lifecycle_contracts import preparation
from tests.gui.test_conversion_window import until
from tests.gui.update_projection_fixture import ReviewControls, ReviewDialogs
from tests.gui.update_worker_fixture import ReviewWorkerTransport

pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(os.name != "nt", reason="Windows native picker spellings"),
]


def picker_case(tmp_path, spelling, *, foreign=False):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "Selected vault"
    other = tmp_path / "Foreign vault"
    vault.mkdir()
    other.mkdir()
    source = tmp_path / "Incoming export.brz"
    source.write_bytes(b"Controlled source is not opened by the outer port")
    (vault / "Personal.md").write_bytes(b"Selected authored bytes\r\n")
    (other / "Personal.md").write_bytes(b"Foreign authored bytes\r\n")
    # The canonical producer target is independently supplied by this outer port.
    prepared = preparation().model_copy(
        update={"vault": str(other if foreign else vault)}
    )
    calls = []

    class NativeInputs(Operations):
        def prepare_update(self, path, incoming):
            calls.append((path, incoming))
            return UpdateResult(
                status="prepared_review",
                code="prepared",
                kind="source_update",
                preparation=prepared,
                ready=False,
                changes=1,
                unresolved=1,
                history_retained=True,
                checkpoint_commit=prepared.locator.commit,
                next_actions=("resolve_update", "save_update"),
            )

        def read_checkpoint(self, path, **kwargs):
            assert path == prepared.vault
            return CheckpointRead(
                schema_id="brz2obsidian.checkpoint-read",
                schema_version=1,
                status="valid",
                code="valid",
                locator=prepared.locator,
                manifest=None,
                review=None,
                message="Controlled current checkpoint observation",
            )

        def apply_update(self, *args, **kwargs):
            raise AssertionError("Picker review cannot publish automatically")

    def path(value):
        return value.as_posix() if spelling == "native_slashes" else str(value)

    dialogs = ReviewDialogs(path(source), path(vault))
    transport = ReviewWorkerTransport(NativeInputs())
    window = MainWindow(supervisor=transport, dialogs=dialogs)
    window.show()
    controls = ReviewControls(window, app)
    return app, window, controls, transport, calls, vault, other, source


def prepare_from_pickers(app, window, controls, transport):
    controls.click("Choose incoming BRZ")
    controls.click("Choose update vault")
    controls.click("Prepare update review")
    until(
        app,
        lambda: (
            bool(transport.replies)
            and window.workbench.snapshot is not None
            and window.workbench.snapshot == window.runner.session.update_snapshot
            and window.workbench.snapshot.transport_phase is not None
            and window.workbench.snapshot.active_request_id is None
            and not window.workbench.busy
        ),
    )


@pytest.mark.parametrize("spelling", ("native_slashes", "windows"))
def test_picker_spelling_retains_canonical_prepared_target_without_unknown(
    tmp_path, spelling
):
    app, window, controls, transport, calls, vault, other, source = picker_case(
        tmp_path, spelling
    )
    try:
        prepare_from_pickers(app, window, controls, transport)
        state = window.runner.session.update_snapshot
        assert state.binding is not None, (
            "A native separator spelling must retain the actual prepared target"
        )
        assert state.binding.vault == state.vault == str(vault)
        assert not state.needs_inspection and state.publication == "not_started"
        assert not state.ready and state.unresolved == 1
        assert calls == [(str(vault), str(source))]
        assert any(row.command == "page" for row in transport.commands)
        assert any(row.command == "choices" for row in transport.commands)
        assert not any(row.command in ("apply", "save") for row in transport.commands)
        assert (vault / "Personal.md").read_bytes() == b"Selected authored bytes\r\n"
        assert (other / "Personal.md").read_bytes() == b"Foreign authored bytes\r\n"
        assert (
            source.read_bytes() == b"Controlled source is not opened by the outer port"
        )
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()


def test_picker_normalization_does_not_admit_a_foreign_producer_target(tmp_path):
    app, window, controls, transport, _calls, vault, other, source = picker_case(
        tmp_path, "native_slashes", foreign=True
    )
    try:
        prepare_from_pickers(app, window, controls, transport)
        assert transport.replies[0].binding.vault == str(other)
        state = window.runner.session.update_snapshot
        assert state.binding is None and state.needs_inspection
        assert state.publication == "unknown" and not state.ready
        assert state.last_operation.binding.vault == str(other)
        assert not any(
            row.command in ("page", "choices", "apply", "save")
            for row in transport.commands
        )
        assert (vault / "Personal.md").read_bytes() == b"Selected authored bytes\r\n"
        assert (other / "Personal.md").read_bytes() == b"Foreign authored bytes\r\n"
        assert (
            source.read_bytes() == b"Controlled source is not opened by the outer port"
        )
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()
