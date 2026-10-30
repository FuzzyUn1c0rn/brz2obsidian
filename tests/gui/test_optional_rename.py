"""Optional path actions coexist with primary comparisons through the real worker."""

import os
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit

from brz2obsidian.application.checkpoint_contracts import CheckpointRead
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_contracts import UpdateResult
from tests.application.test_update_lifecycle_contracts import preparation
from tests.gui.test_conversion_window import until
from tests.gui.update_projection_fixture import ReviewControls
from tests.gui.update_worker_fixture import ReviewWorkerTransport
from tests.reconciliation.test_optional_rename_offers import (
    AUTHORED,
    INCOMING,
    moved_facts,
)
from tests.reconciliation.test_resolution import with_review_links

pytestmark = pytest.mark.gui


@pytest.mark.parametrize("scenario", ("conflict", "compatible", "omitted"))
def test_optional_path_replacements_preserve_primary_controls_and_chosen_caption(
    tmp_path,
    scenario,
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    conflict = scenario != "compatible"
    vault = tmp_path / "vault"
    vault.mkdir()
    source = tmp_path / "incoming.brz"
    source.write_bytes(b"Controlled outer preparation")
    facts = moved_facts(conflict=conflict)
    if scenario == "omitted":
        destination = "Notes/" + "segment/" * 280 + "Opening.md"
        subject = facts.subjects[0].model_copy(
            update={
                "path": destination,
                "source_target": facts.subjects[0].source_target.model_copy(
                    update={"normalized_path": destination.casefold()}
                ),
            }
        )
        facts = with_review_links(
            facts.model_copy(
                update={
                    "subjects": (subject,),
                    "link_context": None,
                }
            )
        )
    prepared = preparation(facts).model_copy(update={"vault": str(vault)})

    class Inputs(Operations):
        def prepare_update(self, path, incoming, **kwargs):
            assert (path, incoming) == (str(vault), str(source))
            return UpdateResult(
                status="unresolved",
                code="prepared",
                preparation=prepared,
                changes=1,
                unresolved=1,
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
                code="controlled_current",
                locator=prepared.locator,
                manifest=None,
                review=None,
                message="Controlled current checkpoint",
            )

        def capture_checkpoint(self, *args, **kwargs):
            raise AssertionError("Optional path review must not Save automatically")

        def apply_reviewed_update(self, *args, **kwargs):
            raise AssertionError("Optional path review must not publish automatically")

    transport = ReviewWorkerTransport(Inputs())
    window = MainWindow(supervisor=transport)
    window.resize(750, 900)
    window.show()
    controls = ReviewControls(window, app)

    def labels():
        return [row.text() for row in window.findChildren(QLabel) if row.isVisible()]

    def latest_comparison():
        return next(
            reply
            for reply in reversed(transport.replies)
            if reply.page is not None and reply.offers
        )

    try:
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
        pane = "Conflicts" if conflict else "Compatible changes"
        controls.select(pane)
        until(
            app,
            lambda: (
                window.workbench.snapshot == window.runner.session.update_snapshot
                and not window.workbench.busy
                and pane in labels()
                and any(
                    row.isVisible()
                    and row.accessibleName() == "Original version"
                    and row.toPlainText() == "Original source writing.\n"
                    for row in window.findChildren(QPlainTextEdit)
                )
                and any(
                    row.isVisible()
                    and row.accessibleName() == "Current version"
                    and row.toPlainText()
                    == (
                        "Independent authored writing.\n"
                        if conflict
                        else "Original source writing.\n"
                    )
                    for row in window.findChildren(QPlainTextEdit)
                )
            ),
        )
        # The same change has two canonical offered domains. The optional row
        # must not overwrite its primary comparison actions or chosen caption.
        assert controls.button("Keep vault version for Authored/Opening.md") is not None
        assert (
            controls.button("Use incoming version for Authored/Opening.md") is not None
        )
        assert controls.button("Edit result for Authored/Opening.md") is not None
        if scenario == "omitted":
            rename = next(
                row for row in latest_comparison().offers if row.domain == "rename"
            )
            assert rename.detail_omitted and len(rename.disclosure) == 2048
            assert rename.disclosure.startswith(
                "Current path: Authored/Opening.md\nProposed source path: Notes/segment/"
            )
            assert (
                "Opening.md" not in rename.disclosure.split("Proposed source path: ")[1]
            )
            assert rename.disclosure in labels()
            assert "Conflicts" in labels() and "Source path" in labels()
            assert "Review choices" not in labels()
            assert "Some disclosure was omitted from this bounded view." in labels()
            assert not window.runner.session.update_snapshot.ready
            assert window.runner.session.update_snapshot.unresolved == 1
            assert list(vault.iterdir()) == []
            return
        assert "Current path: Authored/Opening.md" in "\n".join(labels())
        assert "Proposed source path: Notes/Opening.md" in "\n".join(labels())
        assert not window.runner.session.update_snapshot.ready
        for button, selected, caption, target in (
            (
                "Keep current path for Authored/Opening.md",
                "keep_path",
                "Keep current path",
                "Authored/Opening.md",
            ),
            (
                "Use incoming path for Authored/Opening.md",
                "source_path",
                "Use incoming path",
                "Notes/Opening.md",
            ),
            (
                "Keep current path for Notes/Opening.md",
                "keep_path",
                "Keep current path",
                "Authored/Opening.md",
            ),
        ):
            before = window.runner.session.update_snapshot.binding
            controls.click(button)
            until(
                app,
                lambda before=before, caption=caption: (
                    not window.workbench.busy
                    and window.runner.session.update_snapshot.binding.revision
                    > before.revision
                    and "Chosen path: " + caption in labels()
                ),
            )
            reply = latest_comparison()
            rename = next(row for row in reply.offers if row.domain == "rename")
            primary = next(row for row in reply.offers if row.domain == "text")
            assert rename.selected == selected and primary.selected is None
            assert "Current path: Authored/Opening.md" in rename.disclosure
            assert "Proposed source path: Notes/Opening.md" in rename.disclosure
            assert "Chosen: " + selected not in labels()
            state = window.runner.session.update_snapshot
            assert not state.ready and state.unresolved == 1
            assert controls.button("Keep vault version for " + target) is not None
        if conflict:
            controls.click("Keep vault version for Authored/Opening.md")
            expected, primary_choice = AUTHORED, "current"
        else:
            controls.select("Other choices")
            until(app, lambda: not window.workbench.busy)
            controls.click("Approve compatible group")
            expected, primary_choice = INCOMING, "approve"
        until(
            app,
            lambda: (
                window.runner.session.update_snapshot.ready
                and not window.workbench.busy
            ),
        )
        controls.select(pane)
        until(
            app,
            lambda: (
                not window.workbench.busy and "Chosen: " + primary_choice in labels()
            ),
        )
        assert "Chosen path: Keep current path" in labels()
        reply = latest_comparison()
        assert (
            next(row for row in reply.offers if row.domain == "text").selected
            == primary_choice
        )
        assert (
            next(row for row in reply.offers if row.domain == "rename").selected
            == "keep_path"
        )
        (row,) = reply.page.items
        assert row.current_path == "Authored/Opening.md" and row.result == expected
        assert window.runner.session.update_snapshot.unresolved == 0
        assert window.runner.session.update_snapshot.publication == "not_started"
        assert list(vault.iterdir()) == []
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()
