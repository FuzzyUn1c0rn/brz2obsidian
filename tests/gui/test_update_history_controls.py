"""History and stop/close controls retain the shared producer's truthful state."""

import os
from threading import Event
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QProgressBar

from brz2obsidian.application.checkpoint_contracts import CheckpointRead
from brz2obsidian.application.contracts import WorkerResponse
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_offers import choice_offers
from brz2obsidian.application.transport import Terminal
from brz2obsidian.application.update_context_contracts import (
    UpdateChoiceOffer,
    UpdateContextResult,
)
from brz2obsidian.application.update_contracts import UpdateResult
from brz2obsidian.application.update_history_contracts import (
    HistoryContextBinding,
    UpdateHistoryActionState,
    UpdateHistoryCopyState,
    UpdateHistoryState,
)
from brz2obsidian.application.update_stream import WorkerProgress
from brz2obsidian.application.vault_progress_contracts import VaultProgress
from brz2obsidian.application.vault_repair_contracts import HistoryRepairResult
from brz2obsidian.application.vault_update_contracts import VaultApplyResult
from tests.application.test_update_lifecycle_contracts import preparation
from tests.gui.test_conversion_window import until, window_text
from tests.gui.update_projection_fixture import (
    ProjectedReviewTransport,
    ReviewControls,
    ReviewDialogs,
)
from tests.gui.update_worker_fixture import ReviewWorkerTransport
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import with_review_links

pytestmark = pytest.mark.gui


def native_result(status="refused", *, kind="apply", direction=None):
    terminal = status in ("applied", "undone", "restored")
    partial = status == "incomplete"
    return VaultApplyResult(
        schema_id="brz2obsidian.vault-apply-result",
        schema_version=1,
        status=status,
        code="controlled_" + status,
        operation_id="1" * 32 if terminal or partial else None,
        kind=kind,
        direction=direction,
        generation=1 if terminal or partial else None,
        phase="terminal" if terminal else "publication" if partial else "admission",
        publication="complete" if terminal else "partial" if partial else "not_started",
        history="terminal" if terminal else "intent" if partial else "none",
        planned_files=2 if terminal or partial else 0,
        published_files=2 if terminal else 1 if partial else 0,
        authored_files_changed=bool(terminal or partial),
        checkpoint_commit="b" * 40 if terminal or partial else None,
        intent_commit="c" * 40 if terminal or partial else None,
        result_commit="d" * 40 if terminal else None,
        receipt_commit="e" * 40 if terminal else None,
        recovery_required=partial,
        elapsed_ms=5,
        message="Controlled exact native " + status,
    )


@pytest.mark.parametrize(
    "role", ("setup", "initialization", "recovery", "undo", "repair")
)
def test_history_controls_use_current_admitted_setup_recovery_undo_and_repair(
    tmp_path, role
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "Vault"
    vault.mkdir()
    copy = tmp_path / "Complete matching copy"
    copy.mkdir()

    class Projection:
        binding = None
        action = None

        def __call__(self, actual, callbacks):
            args = actual.arguments
            if args.command == "history":
                self.binding = HistoryContextBinding(
                    context_id=str(uuid4()),
                    selection_id=args.selection_id,
                    vault=str(vault),
                    revision=1,
                    fingerprint="a" * 64,
                    checkpoint_commit="b" * 40 if role == "undo" else None,
                    checkpoint_generation=1 if role == "undo" else None,
                )
                status = {
                    "setup": "setup_required",
                    "initialization": "initialization_required",
                    "recovery": "recovery_required",
                    "undo": "available",
                    "repair": "unavailable",
                }[role]
                operation = (
                    native_result("incomplete")
                    if role == "recovery"
                    else native_result("applied", direction="finish")
                    if role == "undo"
                    else native_result()
                )
                history = UpdateHistoryState(
                    status=status,
                    code="controlled_" + role,
                    operation=operation,
                    history_retained=role in ("undo", "recovery"),
                    recovery_gap_count=0,
                    findings=(),
                    diagnostic_omission=False,
                    summary="Inspect the interrupted operation first."
                    if role == "recovery"
                    else "Controlled " + role + " admission",
                )
                actions = {
                    "setup": ("setup_git",),
                    "initialization": ("initialize_vault",),
                    "recovery": ("review_recovery",),
                    "undo": ("review_undo",),
                    "repair": ("review_history_repair",),
                }[role]
                return UpdateContextResult(
                    status=status,
                    code="controlled_" + role,
                    kind="history",
                    binding=self.binding,
                    history=history,
                    history_retained=history.history_retained,
                    publication=operation.publication,
                    next_actions=actions,
                )
            assert args.binding == self.binding
            if args.command == "initialize_vault":
                assert args.choice == "initialize"
                return UpdateContextResult(
                    status="initialized_review_required",
                    code="initialized_review_required",
                    kind="history",
                    repository_created=True,
                    next_actions=("inspect_history",),
                )
            if args.command == "prepare_history":
                assert args.kind == (
                    "recovery"
                    if role == "recovery"
                    else "undo"
                    if role == "undo"
                    else "repair"
                )
                if role == "repair":
                    assert args.copy_path == str(copy)
                    validation = UpdateHistoryCopyState(
                        status="matching",
                        code="matching",
                        association_id="a" * 64,
                        target_commit="b" * 40,
                        target_generation=1,
                        copy_commit="b" * 40,
                        copy_generation=1,
                        missing_objects=2,
                        damaged_objects=0,
                    )
                    self.action = UpdateHistoryActionState(
                        kind="repair",
                        status="ready",
                        ready=True,
                        available_directions=(),
                        operation=None,
                        summary="Verified matching history copy; authored files will not be restored.",
                        copy_validation=validation,
                    )
                elif role == "recovery" and args.direction is None:
                    self.action = UpdateHistoryActionState(
                        kind="recovery",
                        status="direction_required",
                        ready=False,
                        available_directions=("finish", "restore"),
                        operation=None,
                        summary="Choose finish or restore; later writing needs current review.",
                    )
                else:
                    assert args.direction == ("restore" if role == "recovery" else None)
                    self.binding = self.binding.model_copy(
                        update={
                            "direction": args.direction,
                            "proposal_id": "history-review",
                            "review_generation": 1,
                        }
                    )
                    self.action = UpdateHistoryActionState(
                        kind=role,
                        status="review_required",
                        ready=False,
                        available_directions=("finish", "restore")
                        if role == "recovery"
                        else (),
                        operation=None,
                        summary="Latest Undo protects later writing; current choices may retain imported changes."
                        if role == "undo"
                        else "Review later writing before restoration.",
                    )
            elif args.command in ("page", "history_choices"):
                return self.result(
                    status="available",
                    code="available",
                    offers=(
                        UpdateChoiceOffer(
                            requirement_id="later-writing",
                            change_id="later",
                            domain="reversal",
                            choices=("current", "reverse"),
                            assumptions_digest="a" * 64,
                        ),
                    )
                    if args.command == "history_choices"
                    else (),
                    total_choices=1 if args.command == "history_choices" else 0,
                )
            elif args.command == "choose_history":
                assert (
                    args.choice == "current" and args.requirement_id == "later-writing"
                )
                self.action = self.action.model_copy(
                    update={"status": "ready", "ready": True}
                )
            elif args.command == "execute_history":
                if role == "repair":
                    repair = HistoryRepairResult(
                        schema_id="brz2obsidian.history-repair-result",
                        schema_version=1,
                        status="repaired",
                        code="repaired",
                        history_retained=True,
                        object_storage="verified",
                        objects_written=2,
                        authored_files_changed=False,
                        message="Verified retained history repaired; authored files unchanged.",
                    )
                    action = self.action.model_copy(
                        update={
                            "status": "repaired",
                            "ready": False,
                            "repair": repair,
                            "summary": repair.message,
                        }
                    )
                    return UpdateContextResult(
                        status="repaired",
                        code="repaired",
                        kind="history",
                        history_retained=True,
                        history_action=action,
                        next_actions=("inspect_history",),
                    )
                operation = (
                    native_result("restored", direction="restore")
                    if role == "recovery"
                    else native_result("undone", kind="undo", direction="finish")
                )
                action = self.action.model_copy(
                    update={
                        "status": operation.status,
                        "ready": False,
                        "operation": operation,
                        "summary": operation.message,
                    }
                )
                return UpdateContextResult(
                    status=operation.status,
                    code=operation.code,
                    kind="history",
                    history_retained=True,
                    publication="complete",
                    history_action=action,
                    next_actions=("inspect_history",),
                )
            else:
                raise AssertionError(
                    "Only explicitly admitted history commands are expected"
                )
            self.binding = self.binding.model_copy(
                update={"revision": self.binding.revision + 1}
            )
            return self.result()

        def result(self, status=None, code="controlled_review", **fields):
            ready = self.action.ready
            return UpdateContextResult(
                status=status
                or (
                    "direction_required"
                    if self.action.status == "direction_required"
                    else "prepared_review"
                ),
                code=code,
                kind="history",
                binding=self.binding,
                history_action=self.action,
                ready=ready if status is None else False,
                changes=1 if self.binding.proposal_id is not None else 0,
                unresolved=0 if ready else 1,
                history_retained=role in ("undo", "recovery"),
                publication="partial" if role == "recovery" else "not_started",
                next_actions=("execute_history", "refresh_history")
                if ready
                else ("review_recovery",)
                if self.action.status == "direction_required"
                else ("resolve_history", "refresh_history"),
                **fields,
            )

    projection = Projection()
    transport = ProjectedReviewTransport(projection)
    dialogs = ReviewDialogs(copy, vault)
    window = MainWindow(supervisor=transport, dialogs=dialogs)
    window.show()
    controls = ReviewControls(window, app)
    try:
        controls.click("Choose update vault")
        assert controls.button("Inspect history and recovery") is not None, (
            "History must be reachable before selecting an incoming source"
        )
        controls.click("Inspect history and recovery")
        until(app, lambda: window.runner.session.update_snapshot.reply is not None)
        controls.select("Overview")
        until(app, lambda: "Changes: 0" in window_text(window))
        controls.select("History & recovery")
        if role == "setup":
            until(app, lambda: "Install Git" in window_text(window))
            assert controls.button("Initialize local history") is None
            assert controls.button("Review latest Undo") is None
        elif role == "initialization":
            controls.click("Initialize local history")
            until(
                app,
                lambda: any(
                    c.command == "initialize_vault" for c in transport.commands
                ),
            )
        else:
            if role == "repair":
                dialogs.vault = copy.as_posix()
                controls.click("Choose complete history copy")
                until(app, lambda: copy.name in window_text(window))
                assert str(copy) in window_text(window)
                controls.click("Review matching-history repair")
            else:
                controls.click(
                    "Review interrupted update"
                    if role == "recovery"
                    else "Review latest Undo"
                )
                if role == "recovery":
                    controls.click("Review restore direction")
                controls.select("Overview")
                until(app, lambda: "Changes: 1" in window_text(window))
                assert "Unresolved choices: 1" in window_text(window)
                controls.select("Other choices")
                controls.click("Keep vault version for reversal choice 1")
                controls.select("Overview")
                until(app, lambda: "Unresolved choices: 0" in window_text(window))
                assert "Changes: 1" in window_text(window)
                controls.select("History & recovery")
            controls.click("Execute reviewed " + role)
            until(
                app,
                lambda: (
                    window.runner.session.update_snapshot.reply is not None
                    and window.runner.session.update_snapshot.reply.binding is None
                ),
            )
            expected = {"recovery": "restored", "undo": "undone", "repair": "repaired"}[
                role
            ]
            assert window.runner.session.update_snapshot.reply.status == expected
            terminal_text = {
                "recovery": "Controlled exact native restored",
                "undo": "Controlled exact native undone",
                "repair": "Verified retained history repaired; authored files unchanged.",
            }[role]
            until(
                app,
                lambda: (
                    controls.button("Inspect history and recovery") is not None
                    and controls.button("Inspect history and recovery").isEnabled()
                ),
            )
            assert terminal_text in window_text(window)
            assert not window.runner.session.update_snapshot.ready
        assert list(vault.iterdir()) == [] and list(copy.iterdir()) == []
    finally:
        window.shutdown()
        window.hide()
        window.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("outcome", ("cancelled", "recovery", "unknown"))
def test_progress_safe_stop_and_active_close_keep_owner_until_truthful_terminal(
    tmp_path, outcome
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "Vault"
    vault.mkdir()
    source = tmp_path / "Source.brz"
    source.write_bytes(b"source")
    active, release, cancelled = Event(), Event(), Event()
    requests = []

    class Transport(ProjectedReviewTransport):
        def cancel(self, binding, *, target_request_id):
            assert binding is None and target_request_id == requests[0]
            cancelled.set()
            return Terminal(
                phase="completed",
                response=WorkerResponse(
                    operation="update",
                    request_id=str(uuid4()),
                    sequence=1,
                    result=UpdateContextResult(
                        status="no_content_change",
                        code="cancellation_requested",
                        kind="source_update",
                    ),
                ),
            )

    def project(actual, callbacks):
        if actual.arguments.command == "prepare":
            requests.append(actual.request_id)
            callbacks["on_progress"](
                actual,
                WorkerProgress(
                    request_id=actual.request_id,
                    sequence=actual.sequence,
                    ordinal=1,
                    elapsed_ms=2300,
                    value=VaultProgress(
                        phase="snapshot_preparation",
                        completed_units=2,
                        total_units=5,
                        unit="files",
                    ),
                ),
            )
            active.set()
            assert release.wait(10)
            if outcome == "unknown":
                raise OSError("Controlled lost contact")
            return UpdateContextResult(
                status="cancelled_before_publication"
                if outcome == "cancelled"
                else "recovery_required",
                code="controlled_stopped",
                kind="source_update",
                publication="not_published" if outcome == "cancelled" else "partial",
                history_retained=True,
                next_actions=("inspect_history",),
            )
        raise AssertionError("Only the active preparation may execute")

    transport = Transport(project)
    window = MainWindow(supervisor=transport)
    window.show()
    controls = ReviewControls(window, app)
    try:
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
        until(
            app,
            lambda: (
                active.is_set()
                and window.runner.session.update_snapshot.progress is not None
            ),
        )
        until(app, lambda: "Snapshot preparation" in window_text(window))
        assert "Snapshot preparation" in window_text(window), (
            "The workbench must show the actual producer phase"
        )
        progress = next(
            w
            for w in window.findChildren(QProgressBar)
            if w.accessibleName() == "Update operation progress"
        )
        assert (progress.minimum(), progress.maximum(), progress.value()) == (0, 5, 2)
        window.close()
        app.processEvents()
        controls.click("Keep running in background")
        until(app, window.isMinimized)
        assert window.runner.session.update_snapshot.active_request_id is not None
        window.showNormal()
        window.close()
        app.processEvents()
        controls.click("Request safe stop")
        until(app, cancelled.is_set)
        until(app, lambda: "Cancellation requested" in window_text(window))
        assert (
            window.isVisible()
            and window.runner.session.update_snapshot.active_request_id is not None
        )
        release.set()
        until(
            app, lambda: window.runner.session.update_snapshot.active_request_id is None
        )
        state = window.runner.session.update_snapshot
        assert not state.ready and state.publication == (
            "not_published"
            if outcome == "cancelled"
            else "partial"
            if outcome == "recovery"
            else "unknown"
        )
        assert state.needs_inspection == (outcome != "cancelled")
        assert not transport.closed and window.isVisible()
        assert list(vault.iterdir()) == []
    finally:
        release.set()
        window.shutdown()
        window.hide()
        window.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("draft", ("local_text", "worker_lease"))
def test_window_close_preserves_local_and_worker_drafts_until_explicit_discard(
    tmp_path, draft
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "Vault"
    vault.mkdir()
    source = tmp_path / "Source.brz"
    source.write_bytes(b"source")
    prepared = preparation(with_review_links(request(current=b"Current writing\n")))
    offer = next(o for o in choice_offers(prepared) if o.domain == "text")
    prepared = (
        Operations()
        .resolve_update_choice(
            prepared,
            requirement_id=offer.requirement_id,
            choice="current",
            assumptions_digest=offer.assumptions_digest,
        )
        .preparation
    )
    prepared = prepared.model_copy(update={"vault": str(vault)})

    class NativeInputs(Operations):
        def prepare_update(self, *args, **kwargs):
            return UpdateResult(
                status="prepared_review",
                code="prepared",
                kind="source_update",
                preparation=prepared,
                ready=True,
                changes=1,
                history_retained=True,
                checkpoint_commit=prepared.locator.commit,
                next_actions=("apply_update", "save_update"),
            )

        def read_checkpoint(self, path, **kwargs):
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

    transport = ReviewWorkerTransport(NativeInputs())
    window = MainWindow(supervisor=transport)
    window.show()
    controls = ReviewControls(window, app)
    try:
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
        controls.select("Conflicts")
        controls.click("Edit result for Notes/Opening.md")
        editor = next(
            w
            for w in window.findChildren(QPlainTextEdit)
            if w.accessibleName() == "Edited result for Notes/Opening.md"
        )
        editor.setPlainText("Unsaved writing must stay visible")
        if draft == "worker_lease":
            # Public producer command establishes an idle uncommitted lease without choosing it.
            state = window.runner.session.update_snapshot
            window.runner.submit_update(
                {
                    "command": "begin_edit",
                    "binding": state.binding,
                    "requirement_id": offer.requirement_id,
                    "size": 1,
                    "sha256": "a" * 64,
                }
            )
            until(app, lambda: window.runner.session.update_snapshot.draft_pending)
        window.close()
        QTest.qWait(100)
        app.processEvents()
        assert window.isVisible(), (
            "Closing must present an explicit decision for an unsaved local editor"
        )
        assert (
            controls.button("Save review and close") is None
            or not controls.button("Save review and close").isEnabled()
        )
        assert not any(c.command in ("save", "close") for c in transport.commands)
        controls.click("Continue review")
        assert editor.toPlainText() == "Unsaved writing must stay visible"
        window.close()
        app.processEvents()
        controls.click("Discard review and close")
        until(app, lambda: not window.isVisible())
        assert any(
            c.command == "close" and c.choice == "discard" for c in transport.commands
        )
        assert not any(c.command == "save" for c in transport.commands)
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()
