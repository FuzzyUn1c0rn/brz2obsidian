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
    page_queues = []

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
                page_queues.append(arguments.queue)
                if arguments.queue == "unresolved":
                    comparisons = (comparisons[1],)
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
                        total=len(comparisons),
                        offset=offset,
                        next_offset=following if following < len(comparisons) else None,
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
        assert "Prepared changes: 2" in _visible_text(workspace)
        assert "Unresolved choices: 1" in _visible_text(workspace)
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
        _until(app, lambda: "unresolved" in page_queues)
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
        _until(app, lambda: "Notes/Conflict.md" in _visible_text(workspace))
        assert "Notes/Kept.md" not in _visible_text(workspace)
        select("All changes")
        _until(app, lambda: "Notes/Kept.md" in _visible_text(workspace))
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


@pytest.mark.parametrize("exceptions", (0, 1))
def test_bulk_keep_current_sends_one_bound_group_request(tmp_path, exceptions):
    from PySide6.QtWidgets import QPushButton

    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "vault"
    vault.mkdir()
    source = tmp_path / "incoming.brz"
    source.write_bytes(b"source")
    group_id = "e" * 64
    calls = []

    class ReviewChannel:
        closed = False
        poisoned = False
        binding = None

        def run(self, request, **callbacks):
            if callbacks.get("on_dispatched"):
                callbacks["on_dispatched"](request)
            args = request.arguments
            calls.append(args)
            if args.command == "prepare":
                self.binding = UpdateContextBinding(
                    context_id=str(uuid4()),
                    selection_id=args.selection_id,
                    vault=str(vault),
                    association_id="a" * 64,
                    checkpoint_commit="b" * 40,
                    checkpoint_generation=2,
                    proposal_id="mixed-proposal",
                    generation=3,
                    revision=1,
                )
                result = UpdateContextResult(
                    status="prepared_review",
                    code="prepared",
                    kind="source_update",
                    binding=self.binding,
                    changes=5,
                    unresolved=3 + 2 * exceptions,
                    unresolved_conflicts=3 + exceptions,
                    unresolved_exceptions=exceptions,
                    keep_current_count=3,
                    keep_current_group_id=group_id,
                    history_retained=True,
                    checkpoint_commit="b" * 40,
                    next_actions=("resolve_update", "save_update"),
                )
            elif args.command == "keep_current_unresolved":
                result = UpdateContextResult(
                    status="prepared_review",
                    code="accepted",
                    kind="source_update",
                    binding=self.binding,
                    changes=5,
                    unresolved=2 * exceptions,
                    ready=not exceptions,
                    unresolved_exceptions=exceptions,
                    affected_conflicts=3,
                    history_retained=True,
                    checkpoint_commit="b" * 40,
                    next_actions=("resolve_update", "save_update")
                    if exceptions
                    else ("apply_update", "save_update"),
                )
            elif args.command == "page":
                offer = UpdateChoiceOffer(
                    requirement_id="draft-offer",
                    change_id="draft-row",
                    domain="text",
                    choices=("current", "incoming", "edited"),
                    assumptions_digest="d" * 64,
                )
                row = UpdateComparison(
                    change_id="draft-row",
                    item_id="draft-item",
                    facet="content",
                    current_path="Notes/Draft.md",
                    incoming_path="Notes/Draft.md",
                    disposition="unresolved",
                    original=b"Original",
                    current=b"Current",
                    incoming=b"Incoming",
                    result=None,
                    offset=0,
                    omitted=False,
                )
                result = UpdateContextResult(
                    status="available",
                    code="available",
                    kind="source_update",
                    binding=self.binding,
                    page=UpdateReviewPage(
                        status="available",
                        code="available",
                        proposal_id="mixed-proposal",
                        generation=3,
                        total=1,
                        offset=0,
                        next_offset=None,
                        items=(row,),
                        omitted=False,
                    ),
                    offers=(offer,),
                )
            elif args.command == "choices":
                result = UpdateContextResult(
                    status="available",
                    code="available",
                    kind="source_update",
                    binding=self.binding,
                    offers=(),
                    total_choices=0,
                )
            else:
                raise AssertionError(args.command)
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
            raise AssertionError("Review must use persistent transport")

    window = MainWindow(supervisor=WorkerTransport())
    window.show()
    try:
        tabs = window.findChild(QTabBar)
        tabs.setCurrentIndex(
            next(i for i in range(tabs.count()) if tabs.tabText(i) == "Update vault")
        )
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

        def group_button():
            return next(
                (
                    b
                    for b in window.findChildren(QPushButton)
                    if b.isVisible()
                    and b.text().startswith("Keep current for all unresolved conflicts")
                ),
                None,
            )

        _until(app, lambda: window.runner.session.update_snapshot.binding is not None)
        assert (
            window.runner.session.update_snapshot.last_operation.keep_current_count == 3
        )
        _until(
            app, lambda: window.runner.session.update_snapshot.active_request_id is None
        )
        assert not window.runner.session.update_snapshot.needs_inspection
        _until(app, lambda: group_button() is not None and group_button().isEnabled())
        assert "3" in group_button().text()
        assert f"Unresolved conflicts: {3 + exceptions}" in _visible_text(window)
        if exceptions:
            assert "Other choices requiring attention: 1" in _visible_text(window)
            assert "Other conflicts require individual resolution." in _visible_text(
                window
            )

        if not exceptions:
            queue = next(
                row
                for row in window.findChildren(QAbstractItemView)
                if row.accessibleName() == "Review queue"
            )

            def select_queue(name):
                model = queue.model()
                index = next(
                    model.index(i, 0)
                    for i in range(model.rowCount())
                    if model.index(i, 0).data() == name
                )
                QTest.mouseClick(
                    queue.viewport(),
                    Qt.MouseButton.LeftButton,
                    pos=queue.visualRect(index).center(),
                )

            select_queue("Conflicts")

            def edit_button():
                return next(
                    (
                        b
                        for b in window.findChildren(QPushButton)
                        if b.isVisible()
                        and b.accessibleName() == "Edit result for Notes/Draft.md"
                    ),
                    None,
                )

            _until(app, lambda: edit_button() is not None and edit_button().isEnabled())
            edit_button().click()
            editor = next(
                row
                for row in window.findChildren(QPlainTextEdit)
                if row.accessibleName() == "Edited result for Notes/Draft.md"
            )
            editor.setPlainText("My unfinished draft")
            select_queue("Overview")
            _until(app, lambda: group_button() is not None)
            assert not group_button().isEnabled()
            assert editor.toPlainText() == "My unfinished draft"
            discard = next(
                b
                for b in window.findChildren(QPushButton)
                if b.isVisible() and b.accessibleName() == "Discard edited result"
            )
            discard.click()
            _until(
                app, lambda: group_button() is not None and group_button().isEnabled()
            )
        QTest.mouseClick(group_button(), Qt.MouseButton.LeftButton)
        _until(app, lambda: any(c.command == "keep_current_unresolved" for c in calls))
        groups = [c for c in calls if c.command == "keep_current_unresolved"]
        assert len(groups) == 1
        assert groups[0].binding == channel.binding and groups[0].group_id == group_id
        assert not any(c.command == "choose" for c in calls)
        _until(
            app,
            lambda: (
                window.runner.session.update_snapshot.last_operation.affected_conflicts
                == 3
            ),
        )
        assert window.runner.session.update_snapshot.ready is (not exceptions)
    finally:
        window.shutdown()
        window.hide()
        window.deleteLater()
        app.processEvents()


def test_ready_first_setup_can_apply_without_manual_save(tmp_path):
    from PySide6.QtWidgets import QPushButton

    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "vault"
    vault.mkdir()
    source = tmp_path / "incoming.brz"
    source.write_bytes(b"source")
    commands = []

    class Channel:
        closed = False
        poisoned = False
        binding = None

        def run(self, request, **callbacks):
            if callbacks.get("on_dispatched"):
                callbacks["on_dispatched"](request)
            args = request.arguments
            commands.append(args.command)
            if args.command == "prepare":
                self.binding = UpdateContextBinding(
                    context_id=str(uuid4()),
                    selection_id=args.selection_id,
                    vault=str(vault),
                    association_id=None,
                    proposal_id="setup",
                    generation=1,
                    revision=1,
                )
                result = UpdateContextResult(
                    status="prepared_review",
                    code="prepared",
                    kind="onboarding",
                    binding=self.binding,
                    changes=1,
                    ready=True,
                    next_actions=("apply_update", "save_update"),
                )
            elif args.command in ("page", "choices"):
                result = UpdateContextResult(
                    status="available",
                    code="available",
                    kind="onboarding",
                    binding=self.binding,
                    page=UpdateReviewPage(
                        status="available",
                        code="available",
                        proposal_id="setup",
                        generation=1,
                        total=0,
                        offset=0,
                        next_offset=None,
                        items=(),
                        omitted=False,
                    )
                    if args.command == "page"
                    else None,
                )
            elif args.command == "apply":
                result = UpdateContextResult(
                    status="refused",
                    code="controlled",
                    kind="onboarding",
                    binding=self.binding,
                )
            else:
                raise AssertionError(args.command)
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

    channel = Channel()

    class Transport:
        def open_update(self, **kwargs):
            return channel

    window = MainWindow(supervisor=Transport())
    window.show()
    try:
        tabs = window.findChild(QTabBar)
        tabs.setCurrentIndex(
            next(i for i in range(tabs.count()) if tabs.tabText(i) == "Update vault")
        )
        selection = str(uuid4())
        window.runner.select_update(str(vault), selection_id=selection)
        window.runner.submit_update(
            {
                "command": "prepare",
                "kind": "onboarding",
                "vault": str(vault),
                "source": str(source),
                "selection_id": selection,
            }
        )

        def apply_button():
            return next(
                (
                    b
                    for b in window.findChildren(QPushButton)
                    if b.isVisible() and b.accessibleName() == "Apply update"
                ),
                None,
            )

        _until(app, lambda: apply_button() is not None and apply_button().isEnabled())
        assert channel.binding.checkpoint_commit is None
        apply_button().click()
        _until(app, lambda: "apply" in commands)
        assert "save" not in commands
    finally:
        window.shutdown()
        window.hide()
        window.deleteLater()
        app.processEvents()
