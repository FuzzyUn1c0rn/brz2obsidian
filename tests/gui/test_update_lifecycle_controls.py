"""Preparation and saved-review controls consume current shared admission facts."""

import os
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox

from brz2obsidian.application.checkpoint_contracts import CheckpointRead
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_offers import choice_offers
from brz2obsidian.application.update_context_contracts import UpdateChoiceOffer, UpdateConfigurationOffer, UpdateContextBinding, UpdateContextResult
from brz2obsidian.application.update_contracts import UpdateResult
from tests.application.test_update_lifecycle_contracts import preparation
from tests.gui.test_conversion_window import until, window_text
from tests.gui.update_projection_fixture import ProjectedReviewTransport, ReviewControls, ReviewDialogs
from tests.gui.update_worker_fixture import ReviewWorkerTransport
from tests.reconciliation.test_identity import inventory_item
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import with_review_links

pytestmark = pytest.mark.gui


@pytest.mark.parametrize("role", ("onboarding_known", "onboarding_unknown", "format_transition", "attachment_cleanup"))
def test_preparation_roles_use_explicit_source_and_original_evidence(tmp_path, role):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    source = tmp_path / "Incoming.brz"
    original = tmp_path / "Original.brz"
    source.write_bytes(b"incoming")
    original.write_bytes(b"trusted original")
    vault = tmp_path / "Vault"
    vault.mkdir()
    def project(actual, callbacks):
        return UpdateContextResult(status="refused", code="controlled_role_received", kind=actual.arguments.kind)
    transport = ProjectedReviewTransport(project)
    dialogs = ReviewDialogs(source, vault)
    window = MainWindow(supervisor=transport, dialogs=dialogs)
    window.show()
    controls = ReviewControls(window, app)
    try:
        control = next((w for w in window.findChildren(QComboBox) if w.accessibleName() == "Review operation"), None)
        assert control is not None, "Review preparation must expose the supported operation roles"
        kind = "onboarding" if role.startswith("onboarding") else role
        control.setCurrentIndex(control.findData(kind))
        controls.click("Choose update vault")
        if kind != "attachment_cleanup":
            controls.click("Choose incoming BRZ")
        if role == "onboarding_known":
            dialogs.source = str(original)
            controls.click("Choose original BRZ evidence")
        controls.click("Prepare update review")
        until(app, lambda: len(transport.commands) == 1)
        args = transport.commands[0]
        assert (args.command, args.kind, args.vault) == ("prepare", kind, str(vault))
        assert args.source == (None if kind == "attachment_cleanup" else str(source))
        assert args.original_source == (str(original) if role == "onboarding_known" else None)
        assert list(vault.iterdir()) == []
        assert source.read_bytes() == b"incoming" and original.read_bytes() == b"trusted original"
    finally:
        window.shutdown(); window.hide(); window.deleteLater(); app.processEvents()


def test_identity_association_uses_selected_offered_entries_and_keeps_repair_unresolved(tmp_path):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    source = tmp_path / "Incoming.brz"; source.write_bytes(b"source")
    vault = tmp_path / "Vault"; vault.mkdir()
    facts = request().model_copy(update={"identity_inventory": (
        inventory_item("copy-a", "entry:opening", "A.md", b"copy A"),
        inventory_item("copy-b", "entry:opening", "B.md", b"copy B"),
    )})
    prepared = preparation(with_review_links(facts)).model_copy(update={"vault": str(vault)})
    class NativeInputs(Operations):
        def prepare_update(self, *args, **kwargs):
            return UpdateResult(status="unresolved", code="prepared", kind="source_update", preparation=prepared,
                                changes=1, unresolved=1, history_retained=True, checkpoint_commit=prepared.locator.commit)
        def read_checkpoint(self, path, **kwargs):
            return CheckpointRead(schema_id="brz2obsidian.checkpoint-read", schema_version=1, status="valid", code="valid",
                                  locator=prepared.locator, manifest=None, review=None, message="Controlled checkpoint")
    transport = ReviewWorkerTransport(NativeInputs())
    window = MainWindow(supervisor=transport); window.show()
    controls = ReviewControls(window, app)
    try:
        selection = str(uuid4()); window.runner.select_update(str(vault), selection_id=selection)
        window.runner.submit_update({"command":"prepare", "kind":"source_update", "vault":str(vault), "source":str(source), "selection_id":selection})
        controls.select("Other choices")
        controls.click("Review details for identity choice 1")
        until(app, lambda: "A.md" in window_text(window) and "B.md" in window_text(window))
        select = next((w for w in window.findChildren(QComboBox) if w.isVisible() and w.accessibleName() == "Selected identity for identity choice 1"), None)
        assert select is not None, "Association must select an actual offered inventory entry"
        select.setCurrentIndex(select.findData("copy-b"))
        clear = next(w for w in window.findChildren(QCheckBox) if w.accessibleName() == "Disassociate identity from A.md")
        assert not clear.isChecked()
        clear.setChecked(True)
        controls.click("Associate selected identity for identity choice 1")
        until(app, lambda: any(c.command == "choose" for c in transport.commands))
        chosen = next(c for c in transport.commands if c.command == "choose")
        assert chosen.choice == "associate" and chosen.selected_entry_id == "copy-b" and chosen.disassociate_entry_ids == ("copy-a",)
        until(app, lambda: any(r.code == "accepted" for r in transport.replies))
        assert not window.runner.session.update_snapshot.ready
        assert list(vault.iterdir()) == []
    finally:
        window.shutdown(); transport.close(); window.hide(); window.deleteLater(); app.processEvents()


def test_saved_review_configuration_and_selective_refresh_use_current_binding(tmp_path):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "Vault"; vault.mkdir()
    source = tmp_path / "Incoming.brz"; source.write_bytes(b"unchanged source")
    offered = tuple(UpdateChoiceOffer(requirement_id=f"requirement-{i}", change_id=f"change-{i}", domain="text",
                                    choices=("current", "incoming"), assumptions_digest=str(i)*64,
                                    selected="current", decision_id=f"retained-{i}") for i in (1,2))
    class Projection:
        binding = None
        refreshed = False
        config = UpdateConfigurationOffer(group_id="a"*64, member_count=2, choices=("current", "incoming"), selected=None)
        def __call__(self, actual, callbacks):
            args = actual.arguments
            if args.command == "load":
                return UpdateContextResult(status="unresolved", code="revalidation_required", kind="format_transition",
                                           history_retained=True, checkpoint_commit="b"*40, next_actions=("resume_update",))
            if args.command == "resume":
                self.binding = UpdateContextBinding(context_id=str(uuid4()), selection_id=args.selection_id, vault=str(vault),
                                                     association_id="a"*64, checkpoint_commit="b"*40, checkpoint_generation=1,
                                                     proposal_id="saved-review", generation=1, revision=1)
                return self.review()
            assert args.binding == self.binding
            if args.command == "page":
                return UpdateContextResult(status="available", code="available", kind="format_transition", binding=self.binding, configuration=self.config)
            if args.command == "choices":
                rows = (offered[0], offered[1].model_copy(update={"selected":None, "decision_id":None})) if self.refreshed else offered
                return UpdateContextResult(status="available", code="available", kind="format_transition", binding=self.binding, offers=rows, total_choices=2)
            if args.command == "choose_configuration":
                assert (args.group_id, args.choice) == ("a"*64, "current")
                self.config = self.config.model_copy(update={"selected":"current"})
            elif args.command == "save":
                pass
            elif args.command == "refresh":
                self.refreshed = True
            else:
                raise AssertionError("Only current admitted lifecycle commands are expected")
            self.binding = self.binding.model_copy(update={"revision":self.binding.revision+1})
            return self.review("saved" if args.command == "save" else "refreshed" if self.refreshed else "accepted")
        def review(self, code="resumed"):
            unresolved = 1 if self.refreshed or self.config.selected is None else 0
            return UpdateContextResult(status="stale_review" if self.refreshed else "prepared_review", code=code, kind="format_transition", binding=self.binding,
                                       ready=not unresolved, changes=2, unresolved=unresolved, stale=1 if self.refreshed else 0,
                                       history_retained=True, checkpoint_commit="b"*40,
                                       next_actions=("save_update", "refresh_update") if unresolved else ("apply_update", "save_update", "refresh_update"))
    projection = Projection(); transport = ProjectedReviewTransport(projection)
    window = MainWindow(supervisor=transport, dialogs=ReviewDialogs(source,vault)); window.show()
    controls = ReviewControls(window, app)
    try:
        controls.click("Choose update vault")
        assert controls.button("Reopen saved review") is not None, "Saved review must be reachable without selecting another source"
        controls.click("Reopen saved review")
        until(app, lambda: window.runner.session.update_snapshot.reply is not None)
        assert not window.runner.session.update_snapshot.ready
        controls.click("Resume saved review")
        controls.select("Other choices")
        until(app, lambda: window_text(window).count("Chosen: current") == 2)
        assert "Incoming source: retained from the saved review" in window_text(window)
        role_control = next(w for w in window.findChildren(QComboBox) if w.accessibleName()=="Review operation")
        assert role_control.currentData()=="format_transition" and not role_control.isEnabled()
        assert not controls.button("Apply update").isEnabled()
        controls.select("Overview")
        controls.click("Keep current configuration")
        until(app, lambda: projection.config.selected == "current")
        until(app, lambda: controls.button("Apply update").isEnabled())
        controls.click("Save review")
        until(app, lambda: any(c.command == "save" for c in transport.commands))
        controls.click("Refresh review")
        until(app, lambda: projection.refreshed and not window.runner.session.update_snapshot.active_request_id)
        controls.select("Other choices")
        until(app, lambda: window_text(window).count("Chosen: current") == 1)
        assert "retained-1" in str(window.runner.session.update_snapshot.reply.offers)
        assert not controls.button("Apply update").isEnabled()
        assert [c.command for c in transport.commands if c.command in ("load", "resume", "choose_configuration", "save", "refresh")] == ["load", "resume", "choose_configuration", "save", "refresh"]
        assert list(vault.iterdir()) == [] and source.read_bytes() == b"unchanged source"
    finally:
        window.shutdown(); window.hide(); window.deleteLater(); app.processEvents()
