"""Actual Core choices retain independent decisions and gate whole-review Apply."""

import io
import json
import os
from itertools import count
from threading import RLock
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabBar,
)

from brz2obsidian.application.checkpoint_contracts import CheckpointRead
from brz2obsidian.application.contracts import WorkerRequest
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.protocol import decode_request, encode_request
from brz2obsidian.application.transport import Terminal
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.update_contracts import UpdateResult
from brz2obsidian.application.update_stream import WorkerStreamDecoder
from brz2obsidian.application.update_worker import UpdateWorker
from brz2obsidian.application.vault_update_contracts import VaultApplyResult
from brz2obsidian.contracts import ExactContent
from tests.application.test_minimal_workflow import make_archive
from tests.application.test_update_lifecycle_contracts import preparation
from tests.gui.test_conversion_window import until, window_text
from tests.reconciliation.test_refresh import two_items
from tests.reconciliation.test_resolution import with_review_links

pytestmark = pytest.mark.gui


def test_current_and_incoming_choices_retain_decision_and_gate_whole_review_apply(
    tmp_path,
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    source = make_archive(tmp_path / "Incoming.brz")
    original = source.read_bytes()
    vault = tmp_path / "Vault"
    vault.mkdir()
    facts = two_items()
    current_versions = tuple(
        subject.current.model_copy(update={"content": ExactContent(data=raw)})
        for subject, raw in zip(
            facts.subjects, (b"Local first.\r\n", b"Local second.\r\n"), strict=True
        )
    )
    facts = with_review_links(
        facts.model_copy(
            update={
                "subjects": tuple(
                    row.model_copy(update={"current": current})
                    for row, current in zip(
                        facts.subjects, current_versions, strict=True
                    )
                ),
                "identity_inventory": tuple(
                    row.model_copy(update={"current": current})
                    for row, current in zip(
                        facts.identity_inventory, current_versions, strict=True
                    )
                ),
            }
        )
    )
    prepared = preparation(facts).model_copy(update={"vault": str(vault)})
    assert len(prepared.review.requirements) == 2 and not prepared.review.ready
    calls = []
    observations = []
    publications = []

    class NativeInputs(Operations):
        # These outer Native ports supply declared preparation/checkpoint
        # observations and a typed publication outcome. Real Core resolution,
        # paging, worker codecs and host reduction remain exercised; the
        # publication port performs no writes and proves no Native publication.
        def prepare_update(self, path, incoming, **kwargs):
            assert (path, incoming) == (str(vault), str(source))
            return UpdateResult(
                status="unresolved",
                code="prepared",
                kind="source_update",
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
                message="Controlled current checkpoint",
            )

        def apply_update(self, preparation, **kwargs):
            assert preparation.review.ready
            paths = {
                row.change_id: row.path for row in preparation.review.proposal.changes
            }
            publications.append(
                {
                    paths[row.change_id]: row.result.data
                    for row in preparation.review.approvals
                    if row.domain == "text"
                }
            )
            operation = VaultApplyResult(
                schema_id="brz2obsidian.vault-apply-result",
                schema_version=1,
                status="applied",
                code="applied",
                operation_id="controlled-publication",
                kind="apply",
                origin_role="source_update",
                generation=2,
                review_generation=1,
                phase="terminal",
                publication="complete",
                history="terminal",
                planned_files=1,
                published_files=1,
                authored_files_changed=True,
                checkpoint_commit="d" * 40,
                intent_commit="c" * 40,
                result_commit="e" * 40,
                receipt_commit="d" * 40,
                recovery_required=False,
                elapsed_ms=1,
                message="Update applied.",
            )
            return UpdateResult(
                status="applied",
                code="applied",
                kind="source_update",
                application=operation,
                history_retained=True,
                checkpoint_commit="d" * 40,
                publication="complete",
                changes=2,
                next_actions=("inspect_history",),
            )

    class Channel:
        closed = False
        poisoned = False

        def __init__(self):
            self.output = io.BytesIO()
            self.worker = UpdateWorker(
                context=UpdateContext(operations=NativeInputs()), output=self.output
            )
            self.sequence = count(1)
            self.binding = None
            self.lock = RLock()

        def run(self, request, **callbacks):
            with self.lock:
                actual = request.model_copy(update={"sequence": next(self.sequence)})
                if callbacks.get("on_dispatched") is not None:
                    callbacks["on_dispatched"](actual)
                calls.append(actual.arguments.command)
                self.worker.handle(decode_request(encode_request(actual)))
                decoder = WorkerStreamDecoder(actual)
                terminal = None
                for frame in self.output.getvalue().splitlines(keepends=True):
                    received = decoder.feed(frame)
                    if received is not None:
                        terminal = received
                decoder.eof()
                assert terminal is not None and decoder.sealed and not decoder.poisoned
                if terminal.result is not None:
                    result = terminal.result
                    observations.append(
                        {
                            "command": actual.arguments.command,
                            "status": result.status,
                            "code": result.code,
                            "page": None
                            if result.page is None
                            else result.page.model_dump(),
                            "offers": tuple(
                                (row.domain, row.choices) for row in result.offers
                            ),
                        }
                    )
                self.output.seek(0)
                self.output.truncate()
                if terminal.result is not None:
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
            raise AssertionError("Review choices must use their admitted worker route")

    class Dialogs:
        def choose_source(self, callback):
            callback(str(source))

        def choose_vault(self, callback):
            callback(str(vault))

    window = MainWindow(supervisor=WorkerTransport(), dialogs=Dialogs())
    window.show()

    def button(name):
        return next(
            (
                row
                for row in window.findChildren(QPushButton)
                if row.accessibleName() == name and row.isVisible()
            ),
            None,
        )

    def offers_when_idle():
        state = window.runner.session.update_snapshot
        return (
            state.reply.offers
            if not state.active_request_id and state.reply is not None
            else ()
        )

    def visible_comparisons():
        return "\n".join(
            row.toPlainText()
            for row in window.findChildren(QPlainTextEdit)
            if row.isVisible()
        )

    try:
        tabs = window.findChild(QTabBar)
        tabs.setCurrentIndex(
            next(i for i in range(tabs.count()) if tabs.tabText(i) == "Update vault")
        )
        button("Choose incoming BRZ").click()
        button("Choose update vault").click()
        button("Prepare update review").click()
        until(app, lambda: len(offers_when_idle()) == 2)
        queue = next(
            row
            for row in window.findChildren(QAbstractItemView)
            if row.accessibleName() == "Review queue"
        )
        model = queue.model()
        conflicts = next(
            model.index(i, 0)
            for i in range(model.rowCount())
            if model.index(i, 0).data() == "Conflicts"
        )
        QTest.mouseClick(
            queue.viewport(),
            Qt.MouseButton.LeftButton,
            pos=queue.visualRect(conflicts).center(),
        )
        until(
            app,
            lambda: (
                "Local first." in visible_comparisons()
                and "Local second." in visible_comparisons()
                and "incoming" in visible_comparisons()
            ),
        )

        current = button("Keep vault version for Notes/Opening.md")
        (tmp_path / "public-review-observations.json").write_text(
            json.dumps(
                {"queue": queue.currentIndex().data(), "observations": observations},
                default=repr,
                indent=2,
            ),
            encoding="utf-8",
        )
        assert current is not None, (
            "A text conflict must offer its admitted Current choice",
            queue.currentIndex().row(),
            queue.currentIndex().data(),
            [
                row.accessibleName()
                for row in window.findChildren(QPushButton)
                if row.isVisible()
            ],
            observations,
        )
        visible = visible_comparisons()
        assert (
            "Local first." in visible
            and "Local second." in visible
            and "incoming" in visible
        )
        until(
            app,
            lambda: (
                button("Keep vault version for Notes/Opening.md") is not None
                and button("Keep vault version for Notes/Opening.md").isEnabled()
            ),
        )
        current = button("Keep vault version for Notes/Opening.md")
        apply = button("Apply update")
        assert apply is not None and not apply.isEnabled()
        current.click()
        until(app, lambda: any(row.selected == "current" for row in offers_when_idle()))
        chosen = next(row for row in offers_when_idle() if row.selected == "current")
        assert chosen.decision_id is not None
        first_binding = window.runner.session.update_snapshot.binding
        assert window.runner.session.update_snapshot.unresolved == 1
        assert not window.runner.session.update_snapshot.ready
        assert not button("Apply update").isEnabled() and "apply" not in calls
        until(app, lambda: "Chosen: current" in window_text(window))
        captions = [
            row.text() for row in window.findChildren(QLabel) if row.isVisible()
        ]
        assert captions.count("Unresolved") == 1
        assert "Chosen: current" in captions

        until(
            app,
            lambda: (
                button("Use incoming version for Notes/Second.md") is not None
                and button("Use incoming version for Notes/Second.md").isEnabled()
            ),
        )
        incoming = button("Use incoming version for Notes/Second.md")
        assert incoming is not None, (
            "The independent conflict must offer its admitted Incoming choice"
        )
        incoming.click()
        until(
            app,
            lambda: (
                len(offers_when_idle()) == 2
                and window.runner.session.update_snapshot.ready
            ),
        )
        until(
            app,
            lambda: (
                button("Apply update") is not None
                and button("Apply update").isEnabled()
            ),
        )
        state = window.runner.session.update_snapshot
        retained = next(
            row
            for row in offers_when_idle()
            if row.requirement_id == chosen.requirement_id
        )
        assert (retained.selected, retained.decision_id) == (
            "current",
            chosen.decision_id,
        )
        assert {row.selected for row in offers_when_idle()} == {"current", "incoming"}
        assert state.binding.proposal_id == first_binding.proposal_id
        assert state.binding.revision > first_binding.revision
        assert state.unresolved == 0 and "apply_update" in state.next_actions
        assert button("Apply update").isEnabled()
        assert "apply" not in calls
        window.runner.submit_update(
            {"command": "page", "binding": state.binding, "offset": 0, "limit": 100}
        )
        until(
            app,
            lambda: (
                window.runner.session.update_snapshot.reply.page is not None
                and window.runner.session.update_snapshot.active_request_id is None
            ),
        )
        page = window.runner.session.update_snapshot.reply.page
        assert {row.current_path: row.result for row in page.items} == {
            "Notes/Opening.md": b"Local first.\r\n",
            "Notes/Second.md": b"incoming\n",
        }
        until(
            app,
            lambda: (
                button("Apply update") is not None
                and button("Apply update").isEnabled()
            ),
        )
        assert (
            window.runner.session.update_snapshot.ready
            and button("Apply update").isEnabled()
        )
        button("Apply update").click()
        until(app, lambda: bool(publications))
        assert publications == [
            {
                "Notes/Opening.md": b"Local first.\r\n",
                "Notes/Second.md": b"incoming\n",
            }
        ]
        until(
            app, lambda: window.runner.session.update_snapshot.reply.status == "applied"
        )
        until(app, lambda: "Update applied" in window_text(window))
        applied = window.runner.session.update_snapshot
        assert applied.binding is None and not applied.ready
        assert applied.publication == "complete" and applied.history_retained is True
        assert applied.checkpoint_commit == "d" * 40
        assert applied.reply.operation.status == "applied"
        assert button("Apply update") is None or not button("Apply update").isEnabled()
        assert calls.count("apply") == 1
        assert source.read_bytes() == original and list(vault.iterdir()) == []
    finally:
        final = window.runner.session.update_snapshot
        (tmp_path / "public-apply-observations.json").write_text(
            json.dumps(
                {
                    "commands": calls,
                    "publications": publications,
                    "revision": final.revision,
                    "ready": final.ready,
                    "active_command": final.active_command,
                    "binding": None
                    if final.binding is None
                    else final.binding.model_dump(),
                    "reply": None if final.reply is None else final.reply.model_dump(),
                    "buttons": [
                        (row.accessibleName(), row.isEnabled())
                        for row in window.findChildren(QPushButton)
                        if row.isVisible()
                    ],
                },
                default=repr,
                indent=2,
            ),
            encoding="utf-8",
        )
        window.shutdown()
        channel.close()
        window.hide()
        window.deleteLater()
        app.processEvents()
