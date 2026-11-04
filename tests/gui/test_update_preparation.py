"""BRZ/vault selection requests a shared preparation through the real UI host."""

import io
import os
from itertools import count
from threading import RLock
from typing import ClassVar
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QApplication, QPushButton, QTabBar

from brz2obsidian.application.contracts import WorkerRequest
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.protocol import decode_request, encode_request
from brz2obsidian.application.transport import Terminal
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.update_contracts import UpdateResult
from brz2obsidian.application.update_stream import WorkerStreamDecoder
from brz2obsidian.application.update_worker import UpdateWorker
from tests.application.test_minimal_workflow import make_archive
from tests.application.test_update_lifecycle_contracts import preparation
from tests.gui.test_conversion_window import until, window_text

pytestmark = pytest.mark.gui


def test_incoming_brz_and_vault_picker_prepare_the_bound_review_without_writes(
    tmp_path,
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    source = make_archive(tmp_path / "Older scoped export.brz")
    original = source.read_bytes()
    vault = tmp_path / "Existing vault"
    vault.mkdir()
    prepared = preparation().model_copy(update={"vault": str(vault)})
    native_calls = []

    class NativePreparation(Operations):
        # Only this outer Native preparation port is controlled. Canonical
        # choices/pages, persistent worker codecs and the GUI host are real.
        def prepare_update(self, path, incoming, **kwargs):
            native_calls.append((path, incoming))
            return UpdateResult(
                status="prepared_review",
                code="prepared",
                kind="source_update",
                preparation=prepared,
                changes=1,
                unresolved=1,
                history_retained=True,
                checkpoint_commit=prepared.locator.commit,
            )

    class Channel:
        closed = False
        poisoned = False

        def __init__(self):
            self.output = io.BytesIO()
            self.worker = UpdateWorker(
                context=UpdateContext(operations=NativePreparation()),
                output=self.output,
            )
            self.sequence = count(1)
            self.binding = None
            self.lock = RLock()

        def run(self, request, **callbacks):
            with self.lock:
                actual = request.model_copy(update={"sequence": next(self.sequence)})
                if callbacks.get("on_dispatched") is not None:
                    callbacks["on_dispatched"](actual)
                self.worker.handle(decode_request(encode_request(actual)))
                decoder = WorkerStreamDecoder(actual)
                terminal = None
                for frame in self.output.getvalue().splitlines(keepends=True):
                    received = decoder.feed(frame)
                    if received is not None:
                        terminal = received
                decoder.eof()
                assert terminal is not None and decoder.sealed and not decoder.poisoned
                self.output.seek(0)
                self.output.truncate()
                if terminal.result is not None and terminal.result.binding is not None:
                    self.binding = terminal.result.binding
                return Terminal(phase="completed", response=terminal)

        def close(self):
            with self.lock:
                if not self.worker.closed:
                    self.run(
                        WorkerRequest(
                            operation="update",
                            request_id=str(uuid4()),
                            sequence=1,
                            arguments={
                                "command": "close",
                                "binding": self.binding,
                                "choice": "discard",
                            },
                        )
                    )
                self.closed = True

    channel = Channel()

    class WorkerTransport:
        def open_update(self, **kwargs):
            return channel

        def run(self, request):
            raise AssertionError(
                "Update preparation must use its admitted worker route"
            )

    class Dialogs:
        sources: ClassVar[list] = []
        vaults: ClassVar[list] = []

        def choose_source(self, callback):
            self.sources.append(callback)

        def choose_vault(self, callback):
            self.vaults.append(callback)

    dialogs = Dialogs()
    window = MainWindow(supervisor=WorkerTransport(), dialogs=dialogs)
    window.show()
    try:
        tabs = window.findChild(QTabBar)
        tabs.setCurrentIndex(
            next(i for i in range(tabs.count()) if tabs.tabText(i) == "Update vault")
        )
        queue = next(
            row
            for row in window.findChildren(QAbstractItemView)
            if row.accessibleName() == "Review queue"
        )
        model = queue.model()
        archive = next(
            (
                model.index(i, 0)
                for i in range(model.rowCount())
                if str(model.index(i, 0).data()) == "Archive & vault"
            ),
            None,
        )
        assert archive is not None, (
            "The review must offer incoming BRZ and vault selection"
        )
        QTest.mouseClick(
            queue.viewport(),
            Qt.MouseButton.LeftButton,
            pos=queue.visualRect(archive).center(),
        )
        app.processEvents()

        def button(name):
            return next(
                (
                    row
                    for row in window.findChildren(QPushButton)
                    if row.accessibleName() == name
                ),
                None,
            )

        choose_source = button("Choose incoming BRZ")
        choose_vault = button("Choose update vault")
        prepare = button("Prepare update review")
        assert (
            choose_source is not None
            and choose_vault is not None
            and prepare is not None
        )
        assert not prepare.isEnabled()
        choose_source.click()
        assert len(dialogs.sources) == 1
        dialogs.sources.pop()(None)
        app.processEvents()
        assert not prepare.isEnabled() and native_calls == []
        choose_source.click()
        dialogs.sources.pop()(str(source))
        choose_vault.click()
        assert len(dialogs.vaults) == 1
        dialogs.vaults.pop()(str(vault))
        app.processEvents()
        assert str(source) in window_text(window) and str(vault) in window_text(window)
        assert prepare.isEnabled()
        prepare.click()
        until(app, lambda: native_calls == [(str(vault), str(source))])
        until(app, lambda: window.runner.session.update_snapshot.binding is not None)
        state = window.runner.session.update_snapshot
        assert state.vault == str(vault) and state.binding.vault == str(vault)
        assert state.binding.proposal_id == prepared.review.proposal.proposal_id
        assert not state.ready and state.unresolved == 1
        assert list(vault.iterdir()) == [] and source.read_bytes() == original
    finally:
        window.shutdown()
        window.hide()
        window.deleteLater()
        app.processEvents()
