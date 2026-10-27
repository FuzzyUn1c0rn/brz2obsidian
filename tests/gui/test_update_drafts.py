"""Owned editor/reference drafts cross the real worker/Core boundary."""

import json
import os
from threading import Event
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QAbstractItemView, QComboBox, QPlainTextEdit, QPushButton, QTabBar

from brz2obsidian.application.checkpoint_contracts import CheckpointRead
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_offers import choice_offers
from brz2obsidian.application.update_contracts import UpdateResult
from tests.application.test_update_lifecycle_contracts import preparation
from tests.gui.test_conversion_window import until, window_text
from tests.gui.update_worker_fixture import ReviewWorkerTransport
from tests.reconciliation.test_attachments import linked_attachment_request
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import with_review_links

pytestmark = pytest.mark.gui


@pytest.mark.parametrize("draft_kind", ("edited_text", "binary_references"))
def test_owned_draft_preserves_review_until_explicit_commit_or_discard(tmp_path, draft_kind):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "Vault"
    vault.mkdir()
    source = tmp_path / "Incoming.brz"
    source.write_bytes(b"Controlled preparation input")
    if draft_kind == "edited_text":
        prepared = preparation(with_review_links(request(current=b"Vault writing.\r\n")))
        offer = next(row for row in choice_offers(prepared) if row.domain == "text")
        resolved = Operations().resolve_update_choice(
            prepared, requirement_id=offer.requirement_id, choice="current",
            assumptions_digest=offer.assumptions_digest,
        )
        assert resolved.ready
        prepared = resolved.preparation
    else:
        raw = b" and ".join(f"[[Assets/data.bin|Ref {number}]]".encode() for number in range(101))
        prepared = preparation(linked_attachment_request(raw=raw))
    prepared = prepared.model_copy(update={"vault": str(vault)})

    class NativeInputs(Operations):
        # Only outer preparation and current-checkpoint observation are controlled.
        # Core offers, draft leases, reference staging and choices remain real.
        def prepare_update(self, path, incoming, **kwargs):
            assert (path, incoming) == (str(vault), str(source))
            return UpdateResult(
                status="prepared_review" if prepared.review.ready else "unresolved",
                code="prepared", kind="source_update", preparation=prepared,
                ready=prepared.review.ready, changes=len(prepared.review.proposal.changes),
                unresolved=len(prepared.review.requirements), history_retained=True,
                checkpoint_commit=prepared.locator.commit,
                next_actions=("apply_update",) if prepared.review.ready else ("resolve_update", "save_update"),
            )

        def read_checkpoint(self, path, **kwargs):
            assert path == str(vault)
            return CheckpointRead(
                schema_id="brz2obsidian.checkpoint-read", schema_version=1,
                status="valid", code="valid", locator=prepared.locator,
                manifest=None, review=None, message="Controlled current checkpoint",
            )

        def apply_update(self, preparation, **kwargs):
            raise AssertionError("Draft review must never publish automatically")

    writing, release = Event(), Event()

    def before_request(actual):
        if actual.arguments.command == "write_edit" and not writing.is_set():
            writing.set()
            assert release.wait(timeout=10), "The test must release its controlled transport pause"

    transport = ReviewWorkerTransport(NativeInputs(), before_request=before_request)
    window = MainWindow(supervisor=transport)
    window.show()

    def button(name):
        return next((row for row in window.findChildren(QPushButton) if row.isVisible() and row.accessibleName() == name), None)

    def click(name):
        until(app, lambda: button(name) is not None and button(name).isEnabled())
        button(name).click()

    def select(name):
        queue = next(row for row in window.findChildren(QAbstractItemView) if row.accessibleName() == "Review queue")
        index = next(queue.model().index(i, 0) for i in range(queue.model().rowCount()) if queue.model().index(i, 0).data() == name)
        QTest.mouseClick(queue.viewport(), Qt.MouseButton.LeftButton, pos=queue.visualRect(index).center())

    def selected(choice):
        state = window.runner.session.update_snapshot
        return bool(state.reply and any(row.selected == choice for row in state.reply.offers))

    try:
        tabs = window.findChild(QTabBar)
        tabs.setCurrentIndex(next(i for i in range(tabs.count()) if tabs.tabText(i) == "Update vault"))
        selection = str(uuid4())
        window.runner.select_update(str(vault), selection_id=selection)
        window.runner.submit_update({"command": "prepare", "kind": "source_update", "vault": str(vault),
                                     "source": str(source), "selection_id": selection})
        if draft_kind == "edited_text":
            until(app, lambda: selected("current"))
            current_decision = next(row.decision_id for row in window.runner.session.update_snapshot.reply.offers if row.selected == "current")
            select("Conflicts")
            until(app, lambda: button("Keep vault version for Notes/Opening.md") is not None)
            edit = button("Edit result for Notes/Opening.md")
            assert edit is not None, "The workspace must offer an editor for its admitted Edited result"
            click("Edit result for Notes/Opening.md")
            editor = next(row for row in window.findChildren(QPlainTextEdit) if row.accessibleName() == "Edited result for Notes/Opening.md")
            editor.setPlainText("Discard this local draft")
            assert not button("Apply update").isEnabled()
            click("Discard edited result")
            until(app, lambda: button("Apply update") is not None and button("Apply update").isEnabled())
            assert not any(row.command == "begin_edit" for row in transport.commands)
            assert not any(row.command == "choose" for row in transport.commands)
            assert next(row.decision_id for row in window.runner.session.update_snapshot.reply.offers if row.selected == "current") == current_decision
            click("Edit result for Notes/Opening.md")
            editor = next(row for row in window.findChildren(QPlainTextEdit) if row.accessibleName() == "Edited result for Notes/Opening.md")
            edited = "# Edited\n" + "User result.\n" * 3000
            editor.setPlainText(edited)
            click("Use edited result")
            until(app, writing.is_set)
            app.processEvents()
            assert not button("Apply update").isEnabled()
            assert window.isVisible()
            release.set()
            until(app, lambda: selected("edited") and window.runner.session.update_snapshot.ready)
            click_ready = lambda: button("Apply update") is not None and button("Apply update").isEnabled()
            until(app, click_ready)
            assert sum(row.command == "begin_edit" for row in transport.commands) == 1
            writes = [row for row in transport.commands if row.command == "write_edit"]
            assert [row.offset for row in writes] == [0, 32768]
            assert b"".join(row.data for row in writes) == edited.encode()
            assert sum(row.command == "seal_edit" for row in transport.commands) == 1
            chunks, byte_offset = [], 0
            while True:
                state = window.runner.session.update_snapshot
                prior_reply = state.reply
                window.runner.submit_update({"command": "page", "binding": state.binding,
                                             "offset": 0, "limit": 1, "byte_offset": byte_offset})
                until(app, lambda: window.runner.session.update_snapshot.reply is not prior_reply
                      and window.runner.session.update_snapshot.reply.page is not None
                      and not window.runner.session.update_snapshot.active_request_id
                      and window.runner.session.update_snapshot.reply.page.items[0].offset == byte_offset)
                row = window.runner.session.update_snapshot.reply.page.items[0]
                chunks.append(row.result)
                if row.next_byte_offset is None:
                    break
                byte_offset = row.next_byte_offset
            assert b"".join(chunks) == edited.encode()
        else:
            select("Other choices")
            click("Review details for attachment choice 1")
            until(app, lambda: "Output for: Vault version" in window_text(window))
            assert "Output for: Incoming version" in window_text(window)
            assert "Output for: Both versions" in window_text(window)
            click("Review references for attachment choice 1")
            until(app, lambda: len([row for row in window.findChildren(QComboBox) if row.isVisible()]) == 100)
            for combo in (row for row in window.findChildren(QComboBox) if row.isVisible()):
                combo.setCurrentIndex(combo.findData("keep_current"))
            click("Stage reference choices")
            until(app, lambda: window.runner.session.update_snapshot.draft_pending)
            assert not window.runner.session.update_snapshot.ready
            click("Next reference page")
            until(app, lambda: "Reference text: Ref 100" in window_text(window))
            combo = next(row for row in window.findChildren(QComboBox) if row.isVisible())
            assert combo.findData("use_secondary") >= 0
            combo.setCurrentIndex(combo.findData("use_secondary"))
            click("Stage reference choices")
            until(app, lambda: sum(row.command == "stage_references" for row in transport.commands) == 2)
            click("Keep both versions for attachment choice 1")
            until(app, lambda: selected("both") and window.runner.session.update_snapshot.ready)
            staged = [row for row in transport.commands if row.command == "stage_references"]
            assert [len(row.choices) for row in staged] == [100, 1]
            assert len({choice.reference_id for row in staged for choice in row.choices}) == 101
            assert {choice.choice for choice in staged[0].choices} == {"keep_current"}
            assert staged[1].choices[0].choice == "use_secondary"
            assert staged[1].binding.revision > staged[0].binding.revision
        assert not window.runner.session.update_snapshot.draft_pending
        assert not any(row.command == "apply" for row in transport.commands)
        assert list(vault.iterdir()) == [] and source.read_bytes() == b"Controlled preparation input"
    finally:
        release.set()
        state = window.runner.session.update_snapshot
        (tmp_path / "draft-diagnostic.json").write_text(json.dumps({
            "commands": [row.model_dump(mode="json", exclude={"data"}) for row in transport.commands],
            "replies": [{"code": row.code, "status": row.status, "draft_pending": row.draft_pending,
                         "binding": row.binding.model_dump(mode="json") if row.binding else None} for row in transport.replies],
            "snapshot": {name: getattr(state, name) for name in ("revision", "draft_pending", "active_request_id", "needs_inspection", "transport_phase", "transport_code")},
        }, indent=2), encoding="utf-8")
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()
