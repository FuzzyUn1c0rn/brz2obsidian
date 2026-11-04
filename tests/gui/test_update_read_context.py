"""A focused public read retains its named context while pending and completed."""

import json
import os
from hashlib import sha256
from threading import Event
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTabBar

from brz2obsidian.application.checkpoint_contracts import CheckpointRead
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_offers import choice_offers
from brz2obsidian.application.update_contracts import UpdateResult
from brz2obsidian.application.update_facts import assemble_facts
from tests.application.test_update_lifecycle_admission import payload
from tests.application.test_update_lifecycle_contracts import preparation
from tests.gui.test_conversion_window import until
from tests.gui.update_worker_fixture import ReviewWorkerTransport

pytestmark = pytest.mark.gui


@pytest.mark.parametrize(
    "replace_context", (False, True), ids=("retained", "overview_replaced")
)
def test_choice_details_button_retains_requested_context_while_pending_and_completed(
    tmp_path,
    replace_context,
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "vault"
    vault.mkdir()
    source = tmp_path / "incoming.brz"
    source.write_bytes(b"Controlled outer preparation input")
    assets = (
        ("a-before", "Assets/Before.png"),
        ("b-map", "Assets/Map.png"),
        ("c-after", "Assets/After-one.png"),
        ("d-after", "Assets/After-two.png"),
    )
    baseline = payload("a", "Unchanged note.")
    incoming = payload("b", "Unchanged note.")
    for received in (baseline, incoming):
        record = json.loads(received["migration-record.json"])
        record["asset_targets"] = [
            {"asset_id": item, "relative_path": path} for item, path in assets
        ]
        received["migration-record.json"] = json.dumps(record).encode()
    baseline.update({path: b"\x00original" for _, path in assets})
    incoming.update({path: b"abc" for _, path in assets})
    current = incoming | {path: b"\x00authored" for _, path in assets}
    facts = assemble_facts(
        baseline, incoming, current, proposal_id="review:read-context", generation=1
    )
    prepared = preparation(facts).model_copy(update={"vault": str(vault)})
    map_change = next(
        row for row in prepared.review.proposal.changes if row.item_id == "b-map"
    )
    offer = next(
        row for row in choice_offers(prepared) if row.change_id == map_change.change_id
    )
    chosen = Operations().resolve_update_choice(
        prepared,
        requirement_id=offer.requirement_id,
        choice="both",
        assumptions_digest=offer.assumptions_digest,
    )
    assert chosen.code == "accepted" and not chosen.ready
    prepared = chosen.preparation
    offers = choice_offers(prepared)
    ordinal = next(
        index
        for index, row in enumerate(offers, 1)
        if row.change_id == map_change.change_id
    )
    assert 1 < ordinal < len(offers)
    assert len(prepared.review.requirements) == 3
    assert (
        next(
            row for row in offers if row.requirement_id == offer.requirement_id
        ).selected
        == "both"
    )

    class NativeInputs(Operations):
        # Only outer preparation/current-checkpoint inputs are controlled.
        # Core selection, bounded details, closed worker and Host remain real.
        def prepare_update(self, path, archive, **kwargs):
            assert (path, archive) == (str(vault), str(source))
            return UpdateResult(
                status="unresolved",
                code="prepared",
                preparation=prepared,
                changes=len(prepared.review.proposal.changes),
                unresolved=3,
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
                message="Controlled retained checkpoint",
            )

        def save_update(self, *args, **kwargs):
            raise AssertionError("Reading details must not Save")

        def apply_update(self, *args, **kwargs):
            raise AssertionError("Reading details must not publish")

    held, release = Event(), Event()

    class HeldReplyTransport(ReviewWorkerTransport):
        completed_details = None

        def run(self, operation, **callbacks):
            terminal = super().run(operation, **callbacks)
            args = operation.arguments
            if (
                args.command == "choice_details"
                and args.requirement_id == offer.requirement_id
            ):
                # Hold only the outer return, after actual closed production output.
                self.completed_details = terminal
                held.set()
                assert release.wait(timeout=12), "Release the owned completed read"
            return terminal

    transport = HeldReplyTransport(NativeInputs())
    window = MainWindow(supervisor=transport)
    window.resize(644, 852)
    window.show()
    observations = {}

    def button(name):
        return next(
            (
                row
                for row in window.findChildren(QPushButton)
                if row.isVisible() and row.accessibleName() == name
            ),
            None,
        )

    def label(text):
        return next(
            (
                row
                for row in window.findChildren(QLabel)
                if row.isVisible() and row.text() == text
            ),
            None,
        )

    def rectangle(widget):
        if widget is None:
            return QRect()
        return QRect(
            widget.mapTo(window.workbench.scroll.viewport(), QPoint()), widget.size()
        )

    def visible(widget):
        return window.workbench.scroll.viewport().rect().intersects(rectangle(widget))

    def observe():
        focused = app.focusWidget()
        state = window.runner.session.update_snapshot
        anchor = label(f"Attachment choice {ordinal}")
        return {
            "scroll": window.workbench.scroll.verticalScrollBar().value(),
            "queue": window.workbench.queue.currentItem().text(),
            "queue_focus": window.workbench.queue.hasFocus(),
            "focus": None
            if focused is None
            else focused.accessibleName() or focused.objectName(),
            "anchor_rectangle": rectangle(anchor).getRect(),
            "anchor_visible": visible(anchor),
            "binding": None if state.binding is None else state.binding.model_dump(),
            "active_command": state.active_command,
        }

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
                "source": str(source),
                "vault": str(vault),
                "selection_id": selection,
            }
        )
        until(
            app,
            lambda: (
                window.runner.session.update_snapshot.binding is not None
                and not window.workbench.busy
            ),
        )
        queue = window.workbench.queue
        queue.setCurrentRow(
            next(
                i
                for i in range(queue.count())
                if queue.item(i).text() == "Other choices"
            )
        )
        origin_name = f"Review details for attachment choice {ordinal}"
        until(
            app,
            lambda: (
                button(origin_name) is not None
                and button(origin_name).isEnabled()
                and not window.workbench.busy
            ),
        )
        QTest.qWait(60)
        anchor = label(f"Attachment choice {ordinal}")
        assert anchor is not None and label("Chosen: both") is not None
        scroll = window.workbench.scroll.verticalScrollBar()
        scroll.setValue(anchor.mapTo(window.workbench.workspace, QPoint()).y() - 16)
        QTest.qWait(40)
        origin = button(origin_name)
        assert visible(anchor) and visible(origin)
        assert 0 < scroll.value() < scroll.maximum()
        assert (
            window.workbench.scroll.viewport()
            .rect()
            .contains(rectangle(origin).center())
        )
        binding = window.runner.session.update_snapshot.binding
        observations["before"] = observe()

        QTest.mousePress(origin, Qt.MouseButton.LeftButton, pos=origin.rect().center())
        assert origin.hasFocus(), (
            "The actual read control must own mouse focus before activation"
        )
        QTest.mouseRelease(
            origin, Qt.MouseButton.LeftButton, pos=origin.rect().center()
        )
        until(
            app,
            lambda: (
                held.is_set()
                and window.runner.session.update_snapshot.active_request_id is not None
            ),
        )
        assert transport.completed_details.response.protocol_error is None
        assert transport.completed_details.response.result.status == "available"
        QTest.qWait(60)
        observations["pending"] = observe()
        pending_visible = visible(label(f"Attachment choice {ordinal}"))
        assert queue.currentItem().text() == "Other choices"
        assert window.runner.session.update_snapshot.binding == binding
        assert not button(origin_name).isEnabled()

        if replace_context:
            overview = next(
                queue.item(i)
                for i in range(queue.count())
                if queue.item(i).text() == "Overview"
            )
            QTest.mouseClick(
                queue.viewport(),
                Qt.MouseButton.LeftButton,
                pos=queue.visualItemRect(overview).center(),
            )
            QTest.qWait(60)
            assert queue.currentItem().text() == "Overview" and queue.hasFocus()
            assert visible(label("Review the whole update"))
            replacement_position = scroll.value()
            assert replacement_position == 0
            observations["replacement"] = observe()

        release.set()
        until(
            app,
            lambda: (
                not window.workbench.busy
                and window.runner.session.update_snapshot.reply.choice_details
            ),
        )
        QTest.qWait(60)
        reply = window.runner.session.update_snapshot.reply
        local_sha = sha256(b"\x00authored").hexdigest()
        incoming_sha = (
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )
        assert [(row.choice, row.path, row.sha256) for row in reply.choice_details] == [
            ("current", "Assets/Map.png", local_sha),
            ("incoming", "Assets/Map.png", incoming_sha),
            ("both", "Assets/Map.png", local_sha),
            ("both", "Assets/Map (incoming-ba7816bf).png", incoming_sha),
        ]
        if replace_context:
            observations["settled"] = observe()
            assert pending_visible, observations
            assert queue.currentItem().text() == "Overview" and queue.hasFocus()
            assert visible(label("Review the whole update"))
            assert scroll.value() == replacement_position, observations
            # Normal local navigation still exposes the recorded Both decision.
            other = next(
                queue.item(i)
                for i in range(queue.count())
                if queue.item(i).text() == "Other choices"
            )
            QTest.mouseClick(
                queue.viewport(),
                Qt.MouseButton.LeftButton,
                pos=queue.visualItemRect(other).center(),
            )
            until(app, lambda: label("Chosen: both") is not None)
            QTest.mouseClick(
                queue.viewport(),
                Qt.MouseButton.LeftButton,
                pos=queue.visualItemRect(overview).center(),
            )
            QTest.qWait(60)
            assert queue.currentItem().text() == "Overview" and queue.hasFocus()
        else:
            metadata = next(
                row
                for row in window.findChildren(QLabel)
                if row.isVisible()
                and "Assets/Map.png" in row.text()
                and local_sha in row.text()
            )
            observations["settled"] = observe() | {
                "metadata_rectangle": rectangle(metadata).getRect(),
                "metadata_visible": visible(metadata),
            }
            assert {
                "pending_named_context": pending_visible,
                "settled_requested_metadata": visible(metadata),
            } == {"pending_named_context": True, "settled_requested_metadata": True}, (
                observations
            )
        state = window.runner.session.update_snapshot
        assert state.binding == binding and queue.currentItem().text() == (
            "Overview" if replace_context else "Other choices"
        )
        assert state.unresolved == 3 and not state.ready
        if not replace_context:
            assert label("Chosen: both") is not None
        assert state.publication == "not_started" and state.history_retained is True
        assert sum(row.command == "choice_details" for row in transport.commands) == 1
        assert all(
            row.command in ("prepare", "page", "choices", "choice_details")
            for row in transport.commands
        )
        assert (
            list(vault.iterdir()) == []
            and source.read_bytes() == b"Controlled outer preparation input"
        )
    finally:
        release.set()
        (tmp_path / "read-context-observations.json").write_text(
            json.dumps(observations, indent=2), encoding="utf-8"
        )
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()
