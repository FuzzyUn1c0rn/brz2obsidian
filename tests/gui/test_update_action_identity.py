"""Canonical action destinations are visible beside their offered decisions."""

import os
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from brz2obsidian.application.checkpoint_contracts import CheckpointRead
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_contracts import UpdateResult
from brz2obsidian.contracts import IdentityTargetFacts
from tests.application.test_update_lifecycle_contracts import preparation
from tests.gui.test_conversion_window import until
from tests.gui.update_projection_fixture import ReviewControls
from tests.gui.update_worker_fixture import ReviewWorkerTransport
from tests.reconciliation.test_absence import facts_for
from tests.reconciliation.test_identity import with_subjects
from tests.reconciliation.test_resolution import action, with_review_links


pytestmark = pytest.mark.gui


def test_restoration_actions_identify_distinct_destinations_through_closed_worker(
    tmp_path,
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "vault"
    vault.mkdir()
    source = tmp_path / "incoming.brz"
    source.write_bytes(b"Controlled outer preparation input")
    facts = facts_for(existence="absent", incoming=b"Changed source body.\n")
    subjects, entries = [], []
    for item, destination, deleted in (
        ("category", "Categories/Native category.md", "Deleted/Native category.md"),
        ("template", "Templates/Native category.md", "Templates/Native category.md"),
    ):
        target = IdentityTargetFacts(
            normalized_path=destination.casefold(), containment="contained", status="safe"
        )
        current = facts.subjects[0].current.model_copy(update={"path": deleted})
        subjects.append(facts.subjects[0].model_copy(update={
            "item_id": item, "path": destination, "current": current,
            "source_target": target,
        }))
        entries.append(facts.identity_inventory[0].model_copy(update={
            "entry_id": item, "identity": facts.identity_inventory[0].identity.model_copy(
                update={"item_id": item}
            ), "current": current,
            "target": target.model_copy(update={"normalized_path": deleted.casefold()}),
        }))
    facts = with_review_links(with_subjects(facts, tuple(subjects), tuple(entries)))
    prepared = preparation(facts).model_copy(update={"vault": str(vault)})
    category = next(c for c in prepared.review.proposal.changes if c.item_id == "category")
    # An actual prior path decision makes the restoration destination differ
    # from the deleted location. It does not accept restoration or write files.
    renamed = Operations().resolve_update(
        prepared,
        action(prepared.review, category, domain="rename", choice="source_path"),
    )
    assert renamed.code == "accepted"
    prepared = renamed.preparation
    assert [(c.path, c.target_path, c.disposition) for c in prepared.review.proposal.changes] == [
        ("Deleted/Native category.md", "Categories/Native category.md", "restoration"),
        ("Templates/Native category.md", "Templates/Native category.md", "restoration"),
    ]
    assert len(prepared.review.requirements) == 2 and not prepared.review.ready

    class NativeInputs(Operations):
        # Only outer preparation/checkpoint observations are controlled.
        # Core offers, Context, closed worker, Host and GUI are production code.
        def prepare_update(self, path, incoming, **kwargs):
            assert (path, incoming) == (str(vault), str(source))
            return UpdateResult(
                status="unresolved", code="prepared", preparation=prepared,
                changes=2, unresolved=2, history_retained=True,
                checkpoint_commit=prepared.locator.commit,
                next_actions=("resolve_update", "save_update"),
            )

        def read_checkpoint(self, path, **kwargs):
            assert path == str(vault)
            return CheckpointRead(
                schema_id="brz2obsidian.checkpoint-read", schema_version=1,
                status="valid", code="valid", locator=prepared.locator,
                manifest=None, review=None, message="Controlled retained checkpoint",
            )

    transport = ReviewWorkerTransport(NativeInputs())
    window = MainWindow(supervisor=transport)
    window.resize(644, 852)
    window.show()
    controls = ReviewControls(window, app)
    try:
        selection = str(uuid4())
        window.runner.select_update(str(vault), selection_id=selection)
        window.runner.submit_update({
            "command": "prepare", "kind": "source_update", "source": str(source),
            "vault": str(vault), "selection_id": selection,
        })
        until(app, lambda: (
            window.runner.session.update_snapshot.binding is not None
            and not window.workbench.busy
        ))
        controls.select("Other choices")
        until(app, lambda: controls.button("Restore incoming version for restoration choice 2") is not None)
        QTest.qWait(60)
        offers = next(r.offers for r in reversed(transport.replies) if r.offers)
        assert [r.domain for r in offers] == ["restoration", "restoration"]
        assert all(r.selected is None and r.choices == (
            "decline_restoration", "restore_incoming"
        ) for r in offers)
        # Literal paths are independently chosen fixture inputs. The disclosure
        # must belong to the matching actionable block, not a separate catalogue.
        labels = [w for w in window.findChildren(QLabel) if w.isVisible()]
        titles = [next(w for w in labels if w.text() == f"Restoration choice {n}") for n in (1, 2)]
        positions = [w.mapTo(window.workbench.workspace, QPoint()).y() for w in titles]
        assert positions[1] > positions[0]
        blocks = [
            "\n".join(w.text() for w in labels if (
                w.mapTo(window.workbench.workspace, QPoint()).y() >= positions[i]
                and (i == 1 or w.mapTo(window.workbench.workspace, QPoint()).y() < positions[1])
            )) for i in range(2)
        ]
        assert "Restore to: Categories/Native category.md" in blocks[0]
        assert "Deleted path: Deleted/Native category.md" in blocks[0]
        assert "Templates/Native category.md" not in blocks[0]
        assert "Restore to: Templates/Native category.md" in blocks[1]
        assert "Categories/Native category.md" not in blocks[1]
        assert [r.disclosure for r in offers] == [
            "Restore to: Categories/Native category.md\nDeleted path: Deleted/Native category.md",
            "Restore to: Templates/Native category.md",
        ]
        assert all(not r.detail_omitted for r in offers)
        binding = window.runner.session.update_snapshot.binding
        controls.click("Review details for restoration choice 1")
        until(app, lambda: (
            not window.workbench.busy
            and window.runner.session.update_snapshot.reply.total_choice_details == 0
        ))
        assert window.runner.session.update_snapshot.binding == binding
        assert window.runner.session.update_snapshot.unresolved == 2
        controls.click("Keep deletion for restoration choice 2")
        until(app, lambda: (
            not window.workbench.busy
            and window.runner.session.update_snapshot.unresolved == 1
            and any(r.selected == "decline_restoration" for reply in transport.replies for r in reply.offers)
        ))
        selected = next(r.offers for r in reversed(transport.replies) if r.offers)
        assert selected[0].selected is None and selected[1].selected == "decline_restoration"
        state = window.runner.session.update_snapshot
        assert not state.ready and state.publication == "not_started"
        assert state.binding.context_id == binding.context_id
        assert state.binding.revision > binding.revision
        assert all(c.command in ("prepare", "page", "choices", "choice_details", "choose") for c in transport.commands)
        assert list(vault.iterdir()) == []
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()
