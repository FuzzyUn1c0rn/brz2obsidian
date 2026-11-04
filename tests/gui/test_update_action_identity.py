"""Canonical action destinations are visible beside their offered decisions."""

import os
from contextlib import contextmanager
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from brz2obsidian.application.checkpoint_contracts import CheckpointRead
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_offers import choice_offers
from brz2obsidian.application.update_contracts import UpdateResult
from brz2obsidian.contracts import ExactContent, IdentityTargetFacts
from tests.application.test_update_lifecycle_contracts import preparation
from tests.gui.test_conversion_window import until
from tests.gui.update_projection_fixture import ReviewControls
from tests.gui.update_worker_fixture import ReviewWorkerTransport
from tests.reconciliation.test_absence import facts_for
from tests.reconciliation.test_identity import with_subjects
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, with_review_links

pytestmark = pytest.mark.gui


def text_identity_preparation(paths=("Notes/Opening.md", "Support/Guide.md")):
    facts = request(current=b"Authored opening.\r\n", incoming=b"Incoming opening.\n")
    original = facts.subjects[0]
    first = original.model_copy(
        update={
            "path": paths[0],
            "current": original.current.model_copy(update={"path": paths[0]}),
            "source_target": original.source_target.model_copy(
                update={"normalized_path": paths[0].casefold()}
            ),
        }
    )
    guide = first.model_copy(
        update={
            "item_id": "support:guide",
            "path": paths[1],
            "output_role": "guide",
            "current": first.current.model_copy(
                update={
                    "path": paths[1],
                    "content": ExactContent(data=b"Authored guide.\r\n"),
                }
            ),
            "incoming": ExactContent(data=b"Incoming guide.\n"),
            "source_target": first.source_target.model_copy(
                update={"normalized_path": paths[1].casefold()}
            ),
        }
    )
    original_entry = facts.identity_inventory[0].model_copy(
        update={
            "current": first.current,
            "target": first.source_target,
        }
    )
    guide_entry = original_entry.model_copy(
        update={
            "entry_id": "guide-entry",
            "identity": original_entry.identity.model_copy(
                update={"item_id": guide.item_id}
            ),
            "current": guide.current,
            "target": guide.source_target,
        }
    )
    return preparation(
        with_review_links(
            with_subjects(facts, (first, guide), (original_entry, guide_entry))
        )
    )


@contextmanager
def text_identity_window(tmp_path, prepared):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "vault"
    vault.mkdir()
    source = tmp_path / "incoming.brz"
    source.write_bytes(b"Declared outer preparation input")
    prepared = prepared.model_copy(update={"vault": str(vault)})

    class Inputs(Operations):
        def prepare_update(self, path, incoming, **kwargs):
            assert (path, incoming) == (str(vault), str(source))
            return UpdateResult(
                status="unresolved",
                code="prepared",
                preparation=prepared,
                changes=len(prepared.review.proposal.changes),
                unresolved=len(prepared.review.requirements),
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
                message="Declared current checkpoint",
            )

    transport = ReviewWorkerTransport(Inputs())
    window = MainWindow(supervisor=transport)
    window.resize(644, 852)
    window.show()
    controls = ReviewControls(window, app)
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
        controls.select("Other choices")
        until(
            app,
            lambda: (
                not window.workbench.busy
                and bool(window.runner.session.update_snapshot.reply.offers)
            ),
        )
        until(
            app,
            lambda: any(
                w.isVisible() and w.text() == "Text choice 1"
                for w in window.findChildren(QLabel)
            ),
        )
        yield app, window, controls, transport
        assert list(vault.iterdir()) == []
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()


def test_named_text_actions_bind_ordinary_and_support_files_through_closed_worker(
    tmp_path,
):
    prepared = text_identity_preparation()
    offers = choice_offers(prepared)
    assert [o.domain for o in offers] == ["text", "text"]
    with text_identity_window(tmp_path, prepared) as (app, window, controls, transport):
        labels = [w.text() for w in window.findChildren(QLabel) if w.isVisible()]
        print("Public text disclosures:", [o.disclosure for o in offers])
        assert "Current file: Notes/Opening.md" in labels
        assert "Current file: Support/Guide.md" in labels
        for path in ("Notes/Opening.md", "Support/Guide.md"):
            assert controls.button("Keep vault version for " + path) is not None
            assert controls.button("Use incoming version for " + path) is not None
        controls.click("Review details for text choice 2")
        until(
            app,
            lambda: any(
                w.isVisible() and w.text() == "No additional details for this choice."
                for w in window.findChildren(QLabel)
            ),
        )
        assert window.runner.session.update_snapshot.reply.total_choice_details == 0
        assert controls.button("Keep vault version for Support/Guide.md").isEnabled()
        controls.click("Use incoming version for Notes/Opening.md")
        until(
            app,
            lambda: (
                not window.workbench.busy
                and window.runner.session.update_snapshot.unresolved == 1
            ),
        )
        controls.click("Keep vault version for Support/Guide.md")
        until(
            app,
            lambda: (
                not window.workbench.busy
                and window.runner.session.update_snapshot.ready
            ),
        )
        before = window.runner.session.update_snapshot.binding
        window.runner.submit_update(
            {"command": "page", "binding": before, "offset": 0, "limit": 100}
        )
        until(
            app,
            lambda: (
                not window.workbench.busy
                and window.runner.session.update_snapshot.reply.page is not None
            ),
        )
        assert {
            row.current_path: row.result
            for row in window.runner.session.update_snapshot.reply.page.items
        } == {
            "Notes/Opening.md": b"Incoming opening.\n",
            "Support/Guide.md": b"Authored guide.\r\n",
        }
        window.runner.submit_update(
            {"command": "choices", "binding": before, "offset": 1, "limit": 1}
        )
        until(
            app,
            lambda: (
                not window.workbench.busy
                and window.runner.session.update_snapshot.reply.total_choices == 2
                and len(window.runner.session.update_snapshot.reply.offers) == 1
            ),
        )
        assert window.runner.session.update_snapshot.binding == before
        assert (
            window.runner.session.update_snapshot.reply.offers[0].disclosure
            == "Current file: Support/Guide.md"
        )
        controls.click("Use incoming version for Support/Guide.md")
        until(
            app,
            lambda: (
                not window.workbench.busy
                and window.runner.session.update_snapshot.ready
                and window.runner.session.update_snapshot.binding.revision
                > before.revision
            ),
        )
        controls.select("All changes")
        until(
            app,
            lambda: (
                not window.workbench.busy
                and any(
                    r.page is not None
                    and r.binding == window.runner.session.update_snapshot.binding
                    for r in transport.replies
                )
            ),
        )
        comparison = next(
            r
            for r in reversed(transport.replies)
            if r.page is not None
            and r.binding == window.runner.session.update_snapshot.binding
        )
        assert [o.selected for o in comparison.offers] == ["incoming", "incoming"]
        rows = comparison.page.items
        assert {row.current_path: row.result for row in rows} == {
            "Notes/Opening.md": b"Incoming opening.\n",
            "Support/Guide.md": b"Incoming guide.\n",
        }


def test_accepted_source_rename_text_identity_keeps_actual_current_and_selected_destination(
    tmp_path,
):
    from tests.reconciliation.test_optional_rename_offers import moved_facts

    prepared = preparation(moved_facts())
    rename = next(o for o in choice_offers(prepared) if o.domain == "rename")
    accepted = Operations().resolve_update_choice(
        prepared,
        requirement_id=rename.requirement_id,
        choice="source_path",
        assumptions_digest=rename.assumptions_digest,
    )
    assert accepted.code == "accepted"
    prepared = accepted.preparation
    text = next(o for o in choice_offers(prepared) if o.domain == "text")
    assert (
        text.disclosure
        == "Current file: Authored/Opening.md\nSelected destination: Notes/Opening.md"
    )
    with text_identity_window(tmp_path, prepared) as (app, window, controls, transport):
        assert any(
            w.isVisible()
            and w.text()
            == "Current file: Authored/Opening.md\nSelected destination: Notes/Opening.md"
            for w in window.findChildren(QLabel)
        )
        controls.click(
            "Keep vault version for Authored/Opening.md\nSelected destination: Notes/Opening.md"
        )
        until(
            app,
            lambda: (
                not window.workbench.busy
                and window.runner.session.update_snapshot.ready
            ),
        )
        controls.select("All changes")
        until(
            app,
            lambda: (
                not window.workbench.busy
                and any(
                    r.page is not None
                    and r.binding == window.runner.session.update_snapshot.binding
                    for r in transport.replies
                )
            ),
        )
        comparison = next(
            r
            for r in reversed(transport.replies)
            if r.page is not None
            and r.binding == window.runner.session.update_snapshot.binding
        )
        (row,) = comparison.page.items
        assert (
            row.current_path == "Notes/Opening.md"
            and row.result == b"Independent authored writing.\r\n"
        )
        assert (
            next(o for o in comparison.offers if o.domain == "rename").selected
            == "source_path"
        )


def test_shared_prefix_unicode_text_identity_omission_keeps_actions_unavailable(
    tmp_path,
):
    prefix = "Notes/" + "préfixe & shared/" * 150
    paths = (prefix + "Opening.md", prefix + "Guide.md")
    prepared = text_identity_preparation(paths)
    offers = choice_offers(prepared)
    assert all(o.detail_omitted and len(o.disclosure) == 2048 for o in offers)
    assert offers[0].disclosure == offers[1].disclosure
    assert all(path not in o.disclosure for path in paths for o in offers)
    with text_identity_window(tmp_path, prepared) as (app, window, controls, transport):
        labels = [w for w in window.findChildren(QLabel) if w.isVisible()]
        identity_labels = [w for w in labels if w.text().startswith("Current file: ")]
        assert len(identity_labels) == 2
        assert all(w.textFormat() == Qt.TextFormat.PlainText for w in identity_labels)
        assert "Text actions unavailable: complete file identity is not shown." in [
            w.text() for w in labels
        ]
        actions = [
            w
            for w in window.findChildren(QPushButton)
            if w.isVisible()
            and w.text()
            in ("Keep vault version", "Use incoming version", "Use edited result")
        ]
        assert len(actions) == 4 and all(not w.isEnabled() for w in actions)
        before = window.runner.session.update_snapshot.binding
        controls.click("Review details for text choice 2")
        until(
            app,
            lambda: any(
                w.isVisible() and w.text() == "No additional details for this choice."
                for w in window.findChildren(QLabel)
            ),
        )
        assert window.runner.session.update_snapshot.binding == before
        assert window.runner.session.update_snapshot.unresolved == 2
        assert not window.runner.session.update_snapshot.ready
        assert all(c.command != "choose" for c in transport.commands)


def test_unaccepted_long_source_path_keeps_complete_text_identity_actionable(tmp_path):
    from tests.reconciliation.test_optional_rename_offers import moved_facts

    facts = moved_facts()
    source_path = "Notes/" + "segment/" * 280 + "Opening.md"
    original = facts.subjects[0]
    subject = original.model_copy(
        update={
            "path": source_path,
            "source_target": original.source_target.model_copy(
                update={"normalized_path": source_path.casefold()}
            ),
        }
    )
    prepared = preparation(
        with_review_links(
            facts.model_copy(update={"subjects": (subject,), "link_context": None})
        )
    )
    offers = choice_offers(prepared)
    with text_identity_window(tmp_path, prepared) as (app, window, controls, transport):
        current = next(
            w
            for w in window.findChildren(QPushButton)
            if w.isVisible() and w.text() == "Keep vault version"
        )
        assert current.isEnabled(), "Complete Current identity must remain actionable"
        text = next(o for o in offers if o.domain == "text")
        rename = next(o for o in offers if o.domain == "rename")
        assert text.disclosure == "Current file: Authored/Opening.md"
        assert not text.detail_omitted and rename.detail_omitted
        assert rename.selected is None
        controls.click("Keep vault version for Authored/Opening.md")
        until(
            app,
            lambda: (
                not window.workbench.busy
                and window.runner.session.update_snapshot.ready
            ),
        )
        selected = next(r.offers for r in reversed(transport.replies) if r.offers)
        assert next(o for o in selected if o.domain == "text").selected == "current"
        assert next(o for o in selected if o.domain == "rename").selected is None


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
            normalized_path=destination.casefold(),
            containment="contained",
            status="safe",
        )
        current = facts.subjects[0].current.model_copy(update={"path": deleted})
        subjects.append(
            facts.subjects[0].model_copy(
                update={
                    "item_id": item,
                    "path": destination,
                    "current": current,
                    "source_target": target,
                }
            )
        )
        entries.append(
            facts.identity_inventory[0].model_copy(
                update={
                    "entry_id": item,
                    "identity": facts.identity_inventory[0].identity.model_copy(
                        update={"item_id": item}
                    ),
                    "current": current,
                    "target": target.model_copy(
                        update={"normalized_path": deleted.casefold()}
                    ),
                }
            )
        )
    facts = with_review_links(with_subjects(facts, tuple(subjects), tuple(entries)))
    prepared = preparation(facts).model_copy(update={"vault": str(vault)})
    category = next(
        c for c in prepared.review.proposal.changes if c.item_id == "category"
    )
    # An actual prior path decision makes the restoration destination differ
    # from the deleted location. It does not accept restoration or write files.
    renamed = Operations().resolve_update(
        prepared,
        action(prepared.review, category, domain="rename", choice="source_path"),
    )
    assert renamed.code == "accepted"
    prepared = renamed.preparation
    assert [
        (c.path, c.target_path, c.disposition) for c in prepared.review.proposal.changes
    ] == [
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
                status="unresolved",
                code="prepared",
                preparation=prepared,
                changes=2,
                unresolved=2,
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

    transport = ReviewWorkerTransport(NativeInputs())
    window = MainWindow(supervisor=transport)
    window.resize(644, 852)
    window.show()
    controls = ReviewControls(window, app)
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
        controls.select("Other choices")
        until(
            app,
            lambda: (
                controls.button("Restore incoming version for restoration choice 2")
                is not None
            ),
        )
        QTest.qWait(60)
        all_offers = next(r.offers for r in reversed(transport.replies) if r.offers)
        renames = [row for row in all_offers if row.domain == "rename"]
        assert len(renames) == 1 and renames[0].selected == "source_path"
        assert renames[0].disclosure == (
            "Current path: Deleted/Native category.md\n"
            "Proposed source path: Categories/Native category.md"
        )
        assert len({row.requirement_id for row in all_offers}) == len(all_offers)
        offers = tuple(row for row in all_offers if row.domain == "restoration")
        assert [r.domain for r in offers] == ["restoration", "restoration"]
        assert all(
            r.selected is None
            and r.choices == ("decline_restoration", "restore_incoming")
            for r in offers
        )
        # Literal paths are independently chosen fixture inputs. The disclosure
        # must belong to the matching actionable block, not a separate catalogue.
        labels = [w for w in window.findChildren(QLabel) if w.isVisible()]
        titles = [
            next(w for w in labels if w.text() == f"Restoration choice {n}")
            for n in (1, 2)
        ] + [next(w for w in labels if w.text() == "Rename choice 3")]
        positions = [w.mapTo(window.workbench.workspace, QPoint()).y() for w in titles]
        assert positions[2] > positions[1] > positions[0]
        blocks = [
            "\n".join(
                w.text()
                for w in labels
                if (
                    w.mapTo(window.workbench.workspace, QPoint()).y() >= positions[i]
                    and w.mapTo(window.workbench.workspace, QPoint()).y()
                    < positions[i + 1]
                )
            )
            for i in range(2)
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
        until(
            app,
            lambda: (
                not window.workbench.busy
                and window.runner.session.update_snapshot.reply.total_choice_details
                == 0
            ),
        )
        assert window.runner.session.update_snapshot.binding == binding
        assert window.runner.session.update_snapshot.unresolved == 2
        controls.click("Keep deletion for restoration choice 2")
        until(
            app,
            lambda: (
                not window.workbench.busy
                and window.runner.session.update_snapshot.unresolved == 1
                and any(
                    r.selected == "decline_restoration"
                    for reply in transport.replies
                    for r in reply.offers
                )
            ),
        )
        all_selected = next(r.offers for r in reversed(transport.replies) if r.offers)
        assert (
            next(row for row in all_selected if row.domain == "rename").selected
            == "source_path"
        )
        selected = tuple(row for row in all_selected if row.domain == "restoration")
        assert (
            selected[0].selected is None
            and selected[1].selected == "decline_restoration"
        )
        state = window.runner.session.update_snapshot
        assert not state.ready and state.publication == "not_started"
        assert state.binding.context_id == binding.context_id
        assert state.binding.revision > binding.revision
        assert all(
            c.command in ("prepare", "page", "choices", "choice_details", "choose")
            for c in transport.commands
        )
        assert list(vault.iterdir()) == []
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()


def test_omitted_action_identity_does_not_promise_missing_path_details(tmp_path):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "vault"
    vault.mkdir()
    source = tmp_path / "incoming.brz"
    source.write_bytes(b"Controlled outer preparation input")
    # A valid canonical path is deliberately longer than the existing disclosure
    # cap. No physical file or OS path-limit claim is involved.
    destination = "Categories/" + "segment/" * 280 + "Native category.md"
    facts = facts_for(existence="absent", incoming=b"Changed source body.\n")
    current = facts.subjects[0].current.model_copy(update={"path": destination})
    target = IdentityTargetFacts(
        normalized_path=destination.casefold(), containment="contained", status="safe"
    )
    subject = facts.subjects[0].model_copy(
        update={
            "path": destination,
            "current": current,
            "source_target": target,
        }
    )
    entry = facts.identity_inventory[0].model_copy(
        update={"current": current, "target": target}
    )
    prepared = preparation(
        with_review_links(with_subjects(facts, (subject,), (entry,)))
    ).model_copy(update={"vault": str(vault)})
    assert prepared.review.proposal.changes[0].disposition == "restoration"

    class NativeInputs(Operations):
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

    transport = ReviewWorkerTransport(NativeInputs())
    window = MainWindow(supervisor=transport)
    window.resize(644, 852)
    window.show()
    controls = ReviewControls(window, app)
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
        controls.select("Other choices")
        until(
            app,
            lambda: (
                controls.button("Review details for restoration choice 1") is not None
            ),
        )
        (offer,) = next(r.offers for r in reversed(transport.replies) if r.offers)
        assert offer.detail_omitted and len(offer.disclosure) == 2048
        assert offer.disclosure.startswith("Restore to: Categories/segment/")
        assert "Native category.md" not in offer.disclosure
        assert any(
            w.isVisible() and w.text() == offer.disclosure
            for w in window.findChildren(QLabel)
        )
        binding = window.runner.session.update_snapshot.binding
        previous = window.runner.session.update_snapshot.reply
        controls.click("Review details for restoration choice 1")
        until(
            app,
            lambda: (
                not window.workbench.busy
                and window.runner.session.update_snapshot.reply is not previous
                and any(
                    w.isVisible()
                    and w.text() == "No additional details for this choice."
                    for w in window.findChildren(QLabel)
                )
            ),
        )
        details = window.runner.session.update_snapshot.reply
        assert details.total_choice_details == 0 and details.choice_details == ()
        messages = [w.text() for w in window.findChildren(QLabel) if w.isVisible()]
        assert "No additional details for this choice." in messages
        assert "Some disclosure was omitted from this bounded view." in messages
        assert not any("review the bounded details" in text for text in messages)
        state = window.runner.session.update_snapshot
        assert state.binding == binding and state.unresolved == 1 and not state.ready
        assert state.publication == "not_started" and offer.selected is None
        assert all(
            c.command in ("prepare", "page", "choices", "choice_details")
            for c in transport.commands
        )
        assert list(vault.iterdir()) == []
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()
