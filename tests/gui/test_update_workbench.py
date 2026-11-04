"""Accepted B navigation presents the shared review without changing decisions."""

import os
from time import monotonic
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QLabel,
    QPlainTextEdit,
    QTabBar,
    QTextEdit,
    QWidget,
)

from brz2obsidian.application.contracts import WorkerResponse
from brz2obsidian.application.transport import Terminal
from brz2obsidian.application.update_context_contracts import (
    UpdateChoiceOffer,
    UpdateContextBinding,
    UpdateContextResult,
)
from brz2obsidian.application.update_contracts import UpdateComparison, UpdateReviewPage

pytestmark = pytest.mark.gui


def _until(app, condition):
    deadline = monotonic() + 5
    while not condition():
        app.processEvents()
        if monotonic() > deadline:
            pytest.fail("The workbench did not present the shared review")


def _visible_text(region):
    labels = [row.text() for row in region.findChildren(QLabel) if row.isVisible()]
    editors = [
        row.toPlainText()
        for kind in (QTextEdit, QPlainTextEdit)
        for row in region.findChildren(kind)
        if row.isVisible()
    ]
    return "\n".join(labels + editors)


def test_review_queue_stays_left_while_workspace_selection_retains_review(tmp_path):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "vault"
    vault.mkdir()
    source = tmp_path / "incoming.brz"
    source.write_bytes(b"Controlled worker transport input")
    context_id = str(uuid4())
    proposal = "retained-proposal"
    kept_decision = "explicit-keep-local"
    calls = []

    class ReviewChannel:
        # Typed controlled worker transport; the real HostRunner/session and
        # actual Qt presentation are exercised. No Native planner is repeated.
        closed = False
        poisoned = False
        binding = None

        def run(self, request, **callbacks):
            dispatched = callbacks.get("on_dispatched")
            if dispatched is not None:
                dispatched(request)
            arguments = request.arguments
            calls.append(arguments.command)
            if arguments.command == "prepare":
                self.binding = UpdateContextBinding(
                    context_id=context_id,
                    selection_id=arguments.selection_id,
                    vault=str(vault),
                    association_id="a" * 64,
                    checkpoint_commit="b" * 40,
                    checkpoint_generation=2,
                    proposal_id=proposal,
                    generation=3,
                    revision=1,
                )
                result = UpdateContextResult(
                    status="prepared_review",
                    code="prepared",
                    kind="source_update",
                    binding=self.binding,
                    changes=2,
                    unresolved=1,
                    history_retained=True,
                    checkpoint_commit="b" * 40,
                    next_actions=("resolve_update", "save_update"),
                )
            elif arguments.command == "page":
                comparisons = (
                    UpdateComparison(
                        change_id="kept-row",
                        item_id="kept-item",
                        facet="content",
                        current_path="Notes/Kept.md",
                        incoming_path="Notes/Kept.md",
                        disposition="unresolved",
                        original=b"Original paragraph.\r\n",
                        current=b"Kept local paragraph.\r\n",
                        incoming=b"Source paragraph.\r\n",
                        result=b"Kept local paragraph.\r\n",
                        offset=0,
                        omitted=False,
                    ),
                    UpdateComparison(
                        change_id="conflict-row",
                        item_id="conflict-item",
                        facet="content",
                        current_path="Notes/Conflict.md",
                        incoming_path="Notes/Conflict.md",
                        disposition="unresolved",
                        original=b"Earlier writing.\r\n",
                        current=b"Private writing stays.\r\n",
                        incoming=b"Incoming source differs.\r\n",
                        result=None,
                        offset=0,
                        omitted=False,
                    ),
                )
                offset, limit = arguments.offset, arguments.limit
                items = comparisons[offset : offset + limit]
                following = offset + len(items)
                result = UpdateContextResult(
                    status="available",
                    code="available",
                    kind="source_update",
                    binding=self.binding,
                    page=UpdateReviewPage(
                        status="available",
                        code="available",
                        proposal_id=proposal,
                        generation=3,
                        total=2,
                        offset=offset,
                        next_offset=following if following < 2 else None,
                        items=items,
                        omitted=False,
                    ),
                )
            elif arguments.command == "choices":
                result = UpdateContextResult(
                    status="available",
                    code="available",
                    kind="source_update",
                    binding=self.binding,
                    offers=(
                        UpdateChoiceOffer(
                            requirement_id="kept-offer",
                            change_id="kept-row",
                            domain="text",
                            choices=("current", "incoming", "edited"),
                            assumptions_digest="c" * 64,
                            selected="current",
                            decision_id=kept_decision,
                        ),
                        UpdateChoiceOffer(
                            requirement_id="conflict-offer",
                            change_id="conflict-row",
                            domain="text",
                            choices=("current", "incoming", "edited"),
                            assumptions_digest="d" * 64,
                        ),
                    ),
                    total_choices=2,
                )
            else:
                raise AssertionError("Navigation must only inspect the shared review")
            return Terminal(
                phase="completed",
                response=WorkerResponse(
                    operation="update",
                    request_id=request.request_id,
                    sequence=request.sequence,
                    result=result,
                ),
            )

        def close(self):
            self.closed = True

    channel = ReviewChannel()

    class WorkerTransport:
        def open_update(self, **kwargs):
            return channel

        def run(self, request):
            raise AssertionError("Review must use the persistent update transport")

    window = MainWindow(supervisor=WorkerTransport())
    window.show()
    try:
        tabs = window.findChild(QTabBar)
        index = next(
            (i for i in range(tabs.count()) if tabs.tabText(i) == "Update vault"), None
        )
        assert index is not None, "The accepted review workbench must be reachable"
        tabs.setCurrentIndex(index)
        selection = str(uuid4())
        window.runner.select_update(str(vault), selection_id=selection)
        window.runner.submit_update(
            {
                "command": "prepare",
                "kind": "source_update",
                "vault": str(vault),
                "source": str(source),
                "selection_id": selection,
            }
        )
        queue = next(
            (
                row
                for row in window.findChildren(QAbstractItemView)
                if row.accessibleName() == "Review queue"
            ),
            None,
        )
        workspace = next(
            (
                row
                for row in window.findChildren(QWidget)
                if row.accessibleName() == "Decision workspace"
            ),
            None,
        )
        assert queue is not None and workspace is not None
        _until(app, lambda: "Review the whole update" in _visible_text(workspace))
        _until(app, lambda: window.runner.session.update_snapshot.binding is not None)
        binding = window.runner.session.update_snapshot.binding
        assert binding.proposal_id == proposal and binding.generation == 3

        def select(text):
            model = queue.model()
            chosen = next(
                model.index(i, 0)
                for i in range(model.rowCount())
                if str(model.index(i, 0).data()).startswith(text)
            )
            QTest.mouseClick(
                queue.viewport(),
                Qt.MouseButton.LeftButton,
                pos=queue.visualRect(chosen).center(),
            )
            app.processEvents()

        before_navigation = len(calls)
        select("Conflicts")
        _until(app, lambda: "Notes/Conflict.md" in _visible_text(workspace))
        assert "Private writing stays." in _visible_text(workspace)
        assert "Incoming source differs." in _visible_text(workspace)
        select("Overview")
        _until(app, lambda: "Review the whole update" in _visible_text(workspace))
        select("Conflicts")
        _until(app, lambda: "Notes/Conflict.md" in _visible_text(workspace))
        assert window.runner.session.update_snapshot.binding == binding
        assert all(
            command in ("page", "choices", "choice_details")
            for command in calls[before_navigation:]
        )
        window.runner.submit_update({"command": "choices", "binding": binding})
        _until(
            app,
            lambda: (
                window.runner.session.update_snapshot.reply is not None
                and bool(window.runner.session.update_snapshot.reply.offers)
            ),
        )
        retained = window.runner.session.update_snapshot.reply.offers[0]
        assert retained.selected == "current" and retained.decision_id == kept_decision
        for width in (780, 520):
            window.resize(width, 760)
            app.processEvents()
            assert queue.isVisible() and workspace.isVisible()
            assert (
                queue.mapTo(window, QPoint(queue.width(), 0)).x()
                <= workspace.mapTo(window, QPoint(0, 0)).x()
            )
        assert (
            list(vault.iterdir()) == []
            and source.read_bytes() == b"Controlled worker transport input"
        )
    finally:
        window.shutdown()
        window.hide()
        window.deleteLater()
        app.processEvents()
