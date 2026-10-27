"""Safe producer findings remain useful through the actual review worker boundary."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_contracts import UpdateResult
from brz2obsidian.application.update_context_contracts import UpdateContextBinding, UpdateContextResult
from brz2obsidian.application.update_history_contracts import HistoryContextBinding, UpdateHistoryState
from tests.gui.test_conversion_window import until, window_text
from tests.gui.update_projection_fixture import ProjectedReviewTransport, ReviewControls, ReviewDialogs
from tests.gui.update_worker_fixture import ReviewWorkerTransport
from tests.gui.test_update_history_controls import native_result
from uuid import uuid4

pytestmark = pytest.mark.gui


@pytest.mark.parametrize("failure", ("source", "storage", "transport"))
def test_review_feedback_explains_safe_reason_and_actual_history_publication_limits(tmp_path, failure):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    source = tmp_path / "Incoming.brz"; source.write_bytes(b"controlled source")
    vault = tmp_path / "Vault"; vault.mkdir()
    reasons = {
        "source": "This BRZ belongs to another source collection. Select an export from this vault's imported Brain.",
        "storage": "This vault uses an unsupported storage filter. Review its storage policy before continuing.",
    }
    class NativeInputs(Operations):
        def prepare_update(self, *args, **kwargs):
            return UpdateResult(status="refused", code="association_mismatch" if failure == "source" else "history_unavailable", kind="source_update",
                summary=reasons[failure] + (" Safe bounded diagnostic."*120 if failure == "storage" else ""),
                findings=tuple("finding_"+str(i) + ("x"*170 if i==0 else "") for i in range(25)) if failure == "storage" else (),
                recovery_gaps=("excluded authored content",) if failure == "storage" else (),
                diagnostic_omission=False, history_retained=failure == "source", publication="not_started",
                next_actions=("inspect_history",))
    def lost(actual, callbacks):
        raise OSError("Controlled worker contact loss; private exception text must not appear")
    transport = ProjectedReviewTransport(lost) if failure == "transport" else ReviewWorkerTransport(NativeInputs())
    window = MainWindow(supervisor=transport, dialogs=ReviewDialogs(source,vault)); window.show()
    controls = ReviewControls(window,app)
    try:
        controls.click("Choose incoming BRZ"); controls.click("Choose update vault"); controls.click("Prepare update review")
        title = "Connection lost" if failure == "transport" else "Review could not continue"
        until(app,lambda:window.workbench.snapshot is not None and window.workbench.snapshot.transport_phase is not None and not window.workbench.snapshot.active_request_id)
        until(app,lambda:controls.button("Show review details") is not None)
        assert title in window_text(window)
        if failure == "transport":
            assert "Publication is unknown" in window_text(window)
            assert "private exception text" not in window_text(window)
            for name in ("Choose update vault","Choose incoming BRZ","Choose original BRZ evidence"):
                assert not next(w for w in window.findChildren(QPushButton) if w.accessibleName()==name).isEnabled()
            assert not next(w for w in window.findChildren(QComboBox) if w.accessibleName()=="Review operation").isEnabled()
            assert controls.button("Inspect history and recovery").isEnabled(), "The current target must remain inspectable after lost contact"
        else:
            assert reasons[failure] in window_text(window)
            assert "File publication: not started" in window_text(window)
            assert ("Saved converter history: retained" if failure == "source" else "Saved converter history: not established") in window_text(window)
        controls.click("Show review details")
        if failure == "storage":
            until(app,lambda:"finding_19" in window_text(window))
            assert "finding_20" not in window_text(window)
            assert "Some review diagnostics were omitted" in window_text(window)
            assert "Recovery gaps: 1" in window_text(window)
            summary = next(row.text() for row in window.findChildren(QLabel) if row.accessibleName()=="Review diagnostic summary")
            assert len(summary)<=2048
        assert controls.button("Inspect history and recovery") is not None
        assert list(vault.iterdir())==[] and source.read_bytes()==b"controlled source"
    finally:
        window.shutdown(); transport.close(); window.hide(); window.deleteLater(); app.processEvents()


def test_switching_vault_and_review_role_retires_cached_history_presentation(tmp_path):
    from brz2obsidian_ui.window import MainWindow

    app=QApplication.instance() or QApplication([])
    first=tmp_path/"First"; first.mkdir(); second=tmp_path/"Second"; second.mkdir()
    source=tmp_path/"Source.brz"; source.write_bytes(b"source")
    class Projection:
        binding=None
        def __call__(self,actual,callbacks):
            args=actual.arguments
            if args.command=="history":
                self.binding=HistoryContextBinding(context_id=str(uuid4()),selection_id=args.selection_id,vault=str(first),revision=1,fingerprint="a"*64)
                history=UpdateHistoryState(status="available",code="history_available",operation=native_result("applied",direction="finish"),history_retained=True,
                    recovery_gap_count=0,findings=(),diagnostic_omission=False,summary="First vault historical context only")
                return UpdateContextResult(status="available",code="history_available",kind="history",binding=self.binding,history_retained=True,publication="complete",history=history,next_actions=("review_update",))
            if args.command=="close":
                assert args.binding==self.binding and args.choice=="discard"
                return UpdateContextResult(status="no_content_change",code="context_closed",kind="history")
            if args.command=="prepare":
                assert args.vault==str(second)
                self.binding=UpdateContextBinding(context_id=str(uuid4()),selection_id=args.selection_id,vault=str(second),revision=1,association_id="b"*64,
                    checkpoint_commit="b"*40,checkpoint_generation=1,proposal_id="second-review",generation=1)
                return UpdateContextResult(status="unresolved",code="prepared",kind="source_update",binding=self.binding,unresolved=1,next_actions=("save_update","refresh_update"))
            assert args.binding==self.binding
            return UpdateContextResult(status="available",code="available",kind="source_update",binding=self.binding)
    transport=ProjectedReviewTransport(Projection()); dialogs=ReviewDialogs(source,first)
    window=MainWindow(supervisor=transport,dialogs=dialogs); window.show(); controls=ReviewControls(window,app)
    try:
        controls.click("Choose update vault"); controls.click("Inspect history and recovery")
        until(app,lambda:"First vault historical context only" in window_text(window))
        controls.click("Choose incoming source update")
        until(app,lambda:controls.button("Choose update vault") is not None and controls.button("Choose update vault").isEnabled())
        dialogs.vault=str(second)
        controls.click("Choose update vault"); controls.click("Choose incoming BRZ"); controls.click("Prepare update review")
        until(app,lambda:window.workbench.snapshot is not None and window.workbench.snapshot.binding is not None and window.workbench.snapshot.binding.vault==str(second))
        until(app,lambda:not window.workbench.busy)
        controls.select("History & recovery")
        until(app,lambda:any(w.isVisible() and w.text()=="History & recovery" for w in window.findChildren(QLabel)))
        assert "First vault historical context only" not in window_text(window)
        assert "Controlled exact native applied" not in window_text(window)
    finally:
        window.shutdown(); transport.close(); window.hide(); window.deleteLater(); app.processEvents()


def test_worker_launch_failure_explains_setup_and_allows_retry_without_false_publication_claims(tmp_path):
    from brz2obsidian_ui.window import MainWindow

    app=QApplication.instance() or QApplication([])
    source=tmp_path/"Source.brz"; source.write_bytes(b"source")
    vault=tmp_path/"Vault"; vault.mkdir()
    class Supervisor:
        opens=0
        def open_update(self,**kwargs):
            self.opens+=1
            raise OSError("private_launch_detail must not appear")
        def run(self,*args,**kwargs):
            raise AssertionError("No legacy request is part of this launch")
    supervisor=Supervisor()
    window=MainWindow(supervisor=supervisor,dialogs=ReviewDialogs(source,vault)); window.show(); controls=ReviewControls(window,app)
    try:
        controls.click("Choose incoming BRZ"); controls.click("Choose update vault"); controls.click("Prepare update review")
        until(app,lambda:window.workbench.snapshot is not None and window.workbench.snapshot.transport_phase=="not_started")
        presented=[]
        QTimer.singleShot(0,lambda:presented.append(True))
        until(app,lambda:presented and controls.button("Prepare update review").isEnabled())
        assert "Review could not start" in window_text(window)
        text=window_text(window)
        assert "Python environment" in text and "try again" in text
        assert "File publication: not started" in text
        assert all(word not in text.lower() for word in ("private_launch_detail","publication is unknown","rollback","nothing changed"))
        assert not window.workbench.snapshot.needs_inspection
        assert controls.button("Choose update vault").isEnabled() and controls.button("Choose incoming BRZ").isEnabled()
        assert controls.button("Prepare update review").isEnabled()
        assert supervisor.opens==1 and list(vault.iterdir())==[] and source.read_bytes()==b"source"
    finally:
        window.shutdown(); window.hide(); window.deleteLater(); app.processEvents()
