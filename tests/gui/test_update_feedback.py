"""Safe producer findings remain useful through the actual review worker boundary."""

import os
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context_contracts import (
    UpdateContextBinding,
    UpdateContextResult,
)
from brz2obsidian.application.update_contracts import UpdateResult
from brz2obsidian.application.update_history_contracts import (
    HistoryContextBinding,
    UpdateHistoryState,
)
from tests.gui.test_conversion_window import until, window_text
from tests.gui.test_update_history_controls import native_result
from tests.gui.update_projection_fixture import (
    ProjectedReviewTransport,
    ReviewControls,
    ReviewDialogs,
)
from tests.gui.update_worker_fixture import ReviewWorkerTransport

pytestmark = pytest.mark.gui


def test_missing_references_explain_staging_without_refresh_or_automatic_targets(
    tmp_path,
):
    from brz2obsidian_ui.window import MainWindow
    from tests.application.test_update_context import replacement_context_case

    app = QApplication.instance() or QApplication([])
    _, operations, current = replacement_context_case(tmp_path)
    source = tmp_path / "incoming.brz"
    source.write_bytes(b"controlled native-input port")
    transport = ReviewWorkerTransport(operations)
    window = MainWindow(supervisor=transport, dialogs=ReviewDialogs(source, tmp_path))
    window.show()
    controls = ReviewControls(window, app)
    try:
        controls.click("Choose incoming BRZ")
        controls.click("Choose update vault")
        controls.click("Prepare update review")
        until(
            app,
            lambda: (
                window.workbench.snapshot is not None
                and window.workbench.snapshot.binding is not None
            ),
        )
        controls.select("Other choices")
        until(
            app,
            lambda: (
                controls.button("Use incoming version for attachment choice 1")
                is not None
            ),
        )
        binding = window.workbench.snapshot.binding
        controls.click("Use incoming version for attachment choice 1")
        until(
            app,
            lambda: any(
                r.code == "reference_choices_required" for r in transport.replies
            ),
        )
        until(
            app,
            lambda: (
                "Review references and stage a choice for every occurrence before choosing this version."
                in window_text(window)
            ),
        )
        assert window.workbench.snapshot.binding == binding
        assert not window.workbench.snapshot.ready
        assert "This choice changed" not in window_text(window)
        assert "File publication: not started" in window_text(window)
        assert "Saved converter history: retained" in window_text(window)
        controls.click("Review references for attachment choice 1")
        until(
            app,
            lambda: (
                len(
                    [
                        w
                        for w in window.findChildren(QComboBox)
                        if w.isVisible()
                        and w.accessibleName().startswith("Reference target for ")
                    ]
                )
                == 2
            ),
        )
        targets = [
            w
            for w in window.findChildren(QComboBox)
            if w.isVisible() and w.accessibleName().startswith("Reference target for ")
        ]
        assert all(w.currentData() is None for w in targets)
        assert not controls.button("Stage reference choices").isEnabled()
        assert not any(
            c.command in ("refresh", "stage_references", "apply")
            for c in transport.commands
        )
        assert {name: (tmp_path / name).read_bytes() for name in current} == current
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("failure", ("source", "storage", "transport"))
def test_review_feedback_explains_safe_reason_and_actual_history_publication_limits(
    tmp_path, failure
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    source = tmp_path / "Incoming.brz"
    source.write_bytes(b"controlled source")
    vault = tmp_path / "Vault"
    vault.mkdir()
    reasons = {
        "source": "This BRZ belongs to another source collection. Select an export from this vault's imported Brain.",
        "storage": "This vault uses an unsupported storage filter. Review its storage policy before continuing.",
    }

    class NativeInputs(Operations):
        def prepare_update(self, *args, **kwargs):
            return UpdateResult(
                status="refused",
                code="association_mismatch"
                if failure == "source"
                else "history_unavailable",
                kind="source_update",
                summary=reasons[failure]
                + (" Safe bounded diagnostic." * 120 if failure == "storage" else ""),
                findings=tuple(
                    "finding_" + str(i) + ("x" * 170 if i == 0 else "")
                    for i in range(25)
                )
                if failure == "storage"
                else (),
                recovery_gaps=("excluded authored content",)
                if failure == "storage"
                else (),
                diagnostic_omission=False,
                history_retained=failure == "source",
                publication="not_started",
                next_actions=("inspect_history",),
            )

    def lost(actual, callbacks):
        raise OSError(
            "Controlled worker contact loss; private exception text must not appear"
        )

    transport = (
        ProjectedReviewTransport(lost)
        if failure == "transport"
        else ReviewWorkerTransport(NativeInputs())
    )
    window = MainWindow(supervisor=transport, dialogs=ReviewDialogs(source, vault))
    window.show()
    controls = ReviewControls(window, app)
    try:
        controls.click("Choose incoming BRZ")
        controls.click("Choose update vault")
        controls.click("Prepare update review")
        title = (
            "Connection lost" if failure == "transport" else "Review could not continue"
        )
        until(
            app,
            lambda: (
                window.workbench.snapshot is not None
                and window.workbench.snapshot.transport_phase is not None
                and not window.workbench.snapshot.active_request_id
            ),
        )
        until(app, lambda: controls.button("Show review details") is not None)
        assert title in window_text(window)
        if failure == "transport":
            assert "Publication is unknown" in window_text(window)
            assert "private exception text" not in window_text(window)
            for name in (
                "Choose update vault",
                "Choose incoming BRZ",
                "Choose original BRZ evidence",
            ):
                assert not next(
                    w
                    for w in window.findChildren(QPushButton)
                    if w.accessibleName() == name
                ).isEnabled()
            assert not next(
                w
                for w in window.findChildren(QComboBox)
                if w.accessibleName() == "Review operation"
            ).isEnabled()
            assert controls.button("Inspect history and recovery").isEnabled(), (
                "The current target must remain inspectable after lost contact"
            )
        else:
            assert reasons[failure] in window_text(window)
            assert "File publication: not started" in window_text(window)
            assert (
                "Saved converter history: retained"
                if failure == "source"
                else "Saved converter history: not established"
            ) in window_text(window)
        controls.click("Show review details")
        if failure == "storage":
            until(app, lambda: "finding_19" in window_text(window))
            assert "finding_20" not in window_text(window)
            assert "Some review diagnostics were omitted" in window_text(window)
            assert "Recovery gaps: 1" in window_text(window)
            summary = next(
                row.text()
                for row in window.findChildren(QLabel)
                if row.accessibleName() == "Review diagnostic summary"
            )
            assert len(summary) <= 2048
        assert controls.button("Inspect history and recovery") is not None
        assert (
            list(vault.iterdir()) == [] and source.read_bytes() == b"controlled source"
        )
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()


def test_switching_vault_and_review_role_retires_cached_history_presentation(tmp_path):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    first = tmp_path / "First"
    first.mkdir()
    second = tmp_path / "Second"
    second.mkdir()
    source = tmp_path / "Source.brz"
    source.write_bytes(b"source")

    class Projection:
        binding = None

        def __call__(self, actual, callbacks):
            args = actual.arguments
            if args.command == "history":
                self.binding = HistoryContextBinding(
                    context_id=str(uuid4()),
                    selection_id=args.selection_id,
                    vault=str(first),
                    revision=1,
                    fingerprint="a" * 64,
                )
                history = UpdateHistoryState(
                    status="available",
                    code="history_available",
                    operation=native_result("applied", direction="finish"),
                    history_retained=True,
                    recovery_gap_count=0,
                    findings=(),
                    diagnostic_omission=False,
                    summary="First vault historical context only",
                )
                return UpdateContextResult(
                    status="available",
                    code="history_available",
                    kind="history",
                    binding=self.binding,
                    history_retained=True,
                    publication="complete",
                    history=history,
                    next_actions=("review_update",),
                )
            if args.command == "close":
                assert args.binding == self.binding and args.choice == "discard"
                return UpdateContextResult(
                    status="no_content_change", code="context_closed", kind="history"
                )
            if args.command == "prepare":
                assert args.vault == str(second)
                self.binding = UpdateContextBinding(
                    context_id=str(uuid4()),
                    selection_id=args.selection_id,
                    vault=str(second),
                    revision=1,
                    association_id="b" * 64,
                    checkpoint_commit="b" * 40,
                    checkpoint_generation=1,
                    proposal_id="second-review",
                    generation=1,
                )
                return UpdateContextResult(
                    status="unresolved",
                    code="prepared",
                    kind="source_update",
                    binding=self.binding,
                    unresolved=1,
                    next_actions=("save_update", "refresh_update"),
                )
            assert args.binding == self.binding
            return UpdateContextResult(
                status="available",
                code="available",
                kind="source_update",
                binding=self.binding,
            )

    transport = ProjectedReviewTransport(Projection())
    dialogs = ReviewDialogs(source, first)
    window = MainWindow(supervisor=transport, dialogs=dialogs)
    window.show()
    controls = ReviewControls(window, app)
    try:
        controls.click("Choose update vault")
        controls.click("Inspect history and recovery")
        until(app, lambda: "First vault historical context only" in window_text(window))
        controls.click("Choose incoming source update")
        until(
            app,
            lambda: (
                controls.button("Choose update vault") is not None
                and controls.button("Choose update vault").isEnabled()
            ),
        )
        dialogs.vault = str(second)
        controls.click("Choose update vault")
        controls.click("Choose incoming BRZ")
        controls.click("Prepare update review")
        until(
            app,
            lambda: (
                window.workbench.snapshot is not None
                and window.workbench.snapshot.binding is not None
                and window.workbench.snapshot.binding.vault == str(second)
            ),
        )
        until(app, lambda: not window.workbench.busy)
        controls.select("History & recovery")
        until(
            app,
            lambda: any(
                w.isVisible() and w.text() == "History & recovery"
                for w in window.findChildren(QLabel)
            ),
        )
        assert "First vault historical context only" not in window_text(window)
        assert "Controlled exact native applied" not in window_text(window)
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()


def test_worker_launch_failure_explains_setup_and_allows_retry_without_false_publication_claims(
    tmp_path,
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    source = tmp_path / "Source.brz"
    source.write_bytes(b"source")
    vault = tmp_path / "Vault"
    vault.mkdir()

    class Supervisor:
        opens = 0

        def open_update(self, **kwargs):
            self.opens += 1
            raise OSError("private_launch_detail must not appear")

        def run(self, *args, **kwargs):
            raise AssertionError("No legacy request is part of this launch")

    supervisor = Supervisor()
    window = MainWindow(supervisor=supervisor, dialogs=ReviewDialogs(source, vault))
    window.show()
    controls = ReviewControls(window, app)
    try:
        controls.click("Choose incoming BRZ")
        controls.click("Choose update vault")
        controls.click("Prepare update review")
        until(
            app,
            lambda: (
                window.workbench.snapshot is not None
                and window.workbench.snapshot.transport_phase == "not_started"
            ),
        )
        presented = []
        QTimer.singleShot(0, lambda: presented.append(True))
        until(
            app,
            lambda: presented and controls.button("Prepare update review").isEnabled(),
        )
        assert "Review could not start" in window_text(window)
        text = window_text(window)
        assert "Python environment" in text and "try again" in text
        assert "File publication: not started" in text
        assert all(
            word not in text.lower()
            for word in (
                "private_launch_detail",
                "publication is unknown",
                "rollback",
                "nothing changed",
            )
        )
        assert not window.workbench.snapshot.needs_inspection
        assert (
            controls.button("Choose update vault").isEnabled()
            and controls.button("Choose incoming BRZ").isEnabled()
        )
        assert controls.button("Prepare update review").isEnabled()
        assert (
            supervisor.opens == 1
            and list(vault.iterdir()) == []
            and source.read_bytes() == b"source"
        )
    finally:
        window.shutdown()
        window.hide()
        window.deleteLater()
        app.processEvents()


def test_completed_unknown_history_keeps_current_recovery_route_and_retention(tmp_path):
    from brz2obsidian_ui.window import MainWindow
    from tests.application.test_history_workflow import (
        intact_local_history,
        operation_state,
    )

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "Vault"
    vault.mkdir()

    class NativeInputs(Operations):
        def inspect_update_status(self, vault):
            return operation_state("unknown")

        def inspect_history(self, vault):
            return intact_local_history()

    transport = ReviewWorkerTransport(NativeInputs())
    window = MainWindow(supervisor=transport, dialogs=ReviewDialogs(vault, vault))
    window.show()
    controls = ReviewControls(window, app)
    try:
        controls.click("Choose update vault")
        controls.click("Inspect history and recovery")
        until(app, lambda: controls.button("Review interrupted update") is not None)
        state = window.runner.session.update_snapshot
        assert state.transport_phase == "completed"
        assert isinstance(state.binding, HistoryContextBinding)
        assert state.publication == "unknown" and state.needs_inspection
        assert not state.ready
        assert controls.button("Review interrupted update").isEnabled()
        assert controls.button("Execute") is None
        text = window_text(window)
        assert "Connection lost" not in text
        assert "Publication is unknown" in text
        assert "Saved converter history: retained" in text
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()


def test_unready_review_explains_blocker_after_read_and_vault_change(tmp_path):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "First vault"
    vault.mkdir()
    other = tmp_path / "Other vault"
    other.mkdir()
    source = tmp_path / "incoming.brz"
    source.write_bytes(b"source")
    dialogs = ReviewDialogs(source, vault)

    class Projection:
        binding = None

        def __call__(self, actual, callbacks):
            args = actual.arguments
            if args.command == "prepare":
                self.binding = UpdateContextBinding(
                    context_id=str(uuid4()),
                    selection_id=args.selection_id,
                    vault=str(vault),
                    association_id="a" * 64,
                    checkpoint_commit="b" * 40,
                    checkpoint_generation=1,
                    proposal_id="blocked-review",
                    generation=1,
                    revision=1,
                )
                return UpdateContextResult(
                    status="unresolved",
                    code="review_blocked",
                    kind="source_update",
                    binding=self.binding,
                    changes=3,
                    unresolved=0,
                    ready=False,
                    summary="A selected attachment conflicts with its reference.",
                    findings=("The selected link target cannot be verified.",),
                    guidance="Review the attachment and its references before applying.",
                    next_actions=("resolve_update", "save_update"),
                )
            if args.command == "close":
                return UpdateContextResult(
                    status="no_content_change",
                    code="context_closed",
                    kind="source_update",
                )
            assert args.command in ("page", "choices")
            return UpdateContextResult(
                status="available",
                code="available",
                kind="source_update",
                binding=self.binding,
                summary="Generic available page.",
            )

    transport = ProjectedReviewTransport(Projection())
    window = MainWindow(supervisor=transport, dialogs=dialogs)
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
                window.workbench.snapshot is not None
                and window.workbench.snapshot.reply is not None
                and window.workbench.snapshot.reply.code == "available"
                and not window.workbench.busy
            ),
        )
        assert window.workbench.snapshot.binding == transport.projection.binding
        assert window.workbench.snapshot.unresolved == 0
        assert not controls.button("Apply update").isEnabled()
        until(app, lambda: "Prepared changes: 3" in window_text(window))
        text = window_text(window)
        assert "A selected attachment conflicts with its reference." in text
        assert "The selected link target cannot be verified." in text
        assert "Review the attachment and its references before applying." in text
        assert "Generic available page." not in text
        assert controls.button("Show review details") is not None
        window.runner.select_update(str(other), selection_id=str(uuid4()))
        until(app, lambda: window.workbench.snapshot.vault == str(other))
        assert "A selected attachment conflicts with its reference." not in window_text(
            window
        )
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("followup", ("refresh", "refused", "recovery", "other_vault"))
def test_stale_apply_explanation_survives_read_and_retires_on_new_state(
    tmp_path, followup
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "Vault"
    vault.mkdir()
    other = tmp_path / "Other"
    other.mkdir()
    source = tmp_path / "incoming.brz"
    source.write_bytes(b"source")

    class Projection:
        binding = None
        stale = False

        def __call__(self, actual, callbacks):
            args = actual.arguments
            if args.command == "prepare":
                self.binding = UpdateContextBinding(
                    context_id=str(uuid4()),
                    selection_id=args.selection_id,
                    vault=str(vault),
                    association_id="a" * 64,
                    checkpoint_commit="b" * 40,
                    checkpoint_generation=1,
                    proposal_id="review",
                    generation=1,
                    revision=1,
                )
                return UpdateContextResult(
                    status="prepared_review",
                    code="prepared",
                    kind="source_update",
                    binding=self.binding,
                    changes=2,
                    ready=True,
                    next_actions=("apply_update", "save_update"),
                )
            if args.command == "apply":
                assert args.binding == self.binding
                self.stale = True
                self.binding = self.binding.model_copy(update={"revision": 2})
                return UpdateContextResult(
                    status="stale_review",
                    code="current_facts_changed",
                    kind="source_update",
                    binding=self.binding,
                    changes=2,
                    unresolved=0,
                    ready=False,
                    summary="2 comparisons; 0 choices remain.",
                    next_actions=("refresh_update", "save_update"),
                )
            if args.command == "refresh":
                assert args.binding == self.binding
                if followup == "refused":
                    return UpdateContextResult(
                        status="refused",
                        code="controlled_refusal",
                        kind="source_update",
                        binding=self.binding,
                        summary="A newer refusal needs attention.",
                    )
                if followup == "recovery":
                    return UpdateContextResult(
                        status="recovery_required",
                        code="controlled_recovery",
                        kind="source_update",
                        summary="A newer recovery needs attention.",
                        publication="partial",
                    )
                self.binding = self.binding.model_copy(update={"revision": 3})
                self.stale = False
                return UpdateContextResult(
                    status="prepared_review",
                    code="refreshed",
                    kind="source_update",
                    binding=self.binding,
                    changes=2,
                    ready=True,
                    next_actions=("apply_update", "save_update"),
                )
            assert args.command in ("page", "choices")
            return UpdateContextResult(
                status="available",
                code="available",
                kind="source_update",
                binding=self.binding,
                summary="Generic page available.",
            )

    transport = ProjectedReviewTransport(Projection())
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
                controls.button("Apply update") is not None
                and controls.button("Apply update").isEnabled()
            ),
        )
        controls.select("Other choices")
        controls.click("Apply update")
        until(
            app,
            lambda: (
                window.workbench.snapshot is not None
                and window.workbench.snapshot.last_operation is not None
                and window.workbench.snapshot.last_operation.status == "stale_review"
                and window.workbench.snapshot.reply is not None
                and window.workbench.snapshot.reply.code == "available"
                and not window.workbench.busy
            ),
        )
        assert window.workbench.snapshot.unresolved == 0
        assert not controls.button("Apply update").isEnabled()
        assert window.workbench.queue.currentIndex().data() == "Other choices"
        controls.select("Overview")
        until(app, lambda: "Prepared changes: 2" in window_text(window))
        text = window_text(window)
        assert "The review inputs changed. Refresh review before applying." in text
        assert "2 comparisons; 0 choices remain." in text
        assert "Generic page available." not in text
        assert controls.button("Refresh review").isEnabled()
        if followup == "other_vault":
            window.runner.select_update(str(other), selection_id=str(uuid4()))
            until(app, lambda: window.workbench.snapshot.vault == str(other))
        else:
            controls.click("Refresh review")
            until(
                app,
                lambda: (
                    window.workbench.snapshot.last_operation is not None
                    and window.workbench.snapshot.last_operation.status
                    != "stale_review"
                    and not window.workbench.busy
                ),
            )
            if followup == "refresh":
                until(app, lambda: controls.button("Apply update").isEnabled())
            else:
                expected = "refusal" if followup == "refused" else "recovery"
                until(
                    app,
                    lambda: (
                        "A newer " + expected + " needs attention."
                        in window_text(window)
                    ),
                )
        assert (
            "The review inputs changed. Refresh review before applying."
            not in window_text(window)
        )
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()
