"""Explicit review tasks become reachable without moving ordinary read positions."""

import os
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QPushButton, QTabBar

from brz2obsidian.application.checkpoint_contracts import CheckpointRead
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_contracts import UpdateResult
from brz2obsidian.contracts import ExactContent
from tests.application.test_update_lifecycle_contracts import preparation
from tests.gui.test_conversion_window import until
from tests.gui.update_worker_fixture import ReviewWorkerTransport
from tests.reconciliation.test_refresh import two_items
from tests.reconciliation.test_resolution import with_review_links

pytestmark = pytest.mark.gui


@pytest.mark.parametrize("task", ("editor", "close"))
def test_explicit_review_task_is_revealed_after_layout_without_later_scroll_jump(tmp_path, task):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "vault"
    vault.mkdir()
    source = tmp_path / "incoming.brz"
    source.write_bytes(b"Controlled outer preparation input")
    facts = two_items()
    current = tuple(row.current.model_copy(update={"content": ExactContent(data=raw)})
                    for row, raw in zip(facts.subjects, (b"Local first.\r\n", b"Local second.\r\n"), strict=True))
    facts = with_review_links(facts.model_copy(update={
        "subjects": tuple(row.model_copy(update={"current": value}) for row, value in zip(facts.subjects, current, strict=True)),
        "identity_inventory": tuple(row.model_copy(update={"current": value}) for row, value in zip(facts.identity_inventory, current, strict=True)),
    }))
    prepared = preparation(facts).model_copy(update={"vault": str(vault)})

    class NativeInputs(Operations):
        # Declared outer inputs only; real Core, Context, worker and host render.
        def prepare_update(self, path, incoming, **kwargs):
            assert (path, incoming) == (str(vault), str(source))
            return UpdateResult(status="unresolved", code="prepared", preparation=prepared,
                                changes=2, unresolved=2, history_retained=True,
                                checkpoint_commit=prepared.locator.commit,
                                next_actions=("resolve_update", "save_update"))

        def read_checkpoint(self, path, **kwargs):
            assert path == str(vault)
            return CheckpointRead(schema_id="brz2obsidian.checkpoint-read", schema_version=1,
                                  status="valid", code="valid", locator=prepared.locator,
                                  manifest=None, review=None, message="Controlled retained checkpoint")

        def save_update(self, *args, **kwargs):
            raise AssertionError("An unsubmitted local draft must not Save")

        def apply_update(self, *args, **kwargs):
            raise AssertionError("Visibility tasks must not publish")

    transport = ReviewWorkerTransport(NativeInputs())
    window = MainWindow(supervisor=transport)
    window.resize(653, 852)
    window.show()

    def button(name):
        return next((row for row in window.findChildren(QPushButton)
                     if row.isVisible() and row.accessibleName() == name), None)

    def settled():
        QTest.qWait(60)
        app.processEvents()

    def intersects(widget):
        viewport = window.workbench.scroll.viewport()
        rectangle = QRect(widget.mapTo(viewport, QPoint()), widget.size())
        return viewport.rect().intersects(rectangle)

    try:
        tabs = window.findChild(QTabBar)
        tabs.setCurrentIndex(next(i for i in range(tabs.count()) if tabs.tabText(i) == "Update vault"))
        selection = str(uuid4())
        window.runner.select_update(str(vault), selection_id=selection)
        window.runner.submit_update({"command": "prepare", "kind": "source_update",
                                     "source": str(source), "vault": str(vault), "selection_id": selection})
        until(app, lambda: button("Prepare update review") is not None and not window.workbench.busy
              and window.runner.session.update_snapshot.binding is not None)
        queue = window.workbench.queue
        queue.setCurrentRow(next(i for i in range(queue.count()) if queue.item(i).text() == "All changes"))
        until(app, lambda: button("Edit result for Notes/Opening.md") is not None
              and button("Edit result for Notes/Opening.md").isEnabled() and not window.workbench.busy)
        settled()
        scroll = window.workbench.scroll.verticalScrollBar()
        assert scroll.maximum() > 800
        binding = window.runner.session.update_snapshot.binding
        scroll.setValue(0)
        button("Edit result for Notes/Opening.md").click()
        editor = next(row for row in window.findChildren(QPlainTextEdit)
                      if row.accessibleName() == "Edited result for Notes/Opening.md")
        settled()
        draft = "Exact local draft\nRetain this line.\r\n"
        if task == "editor":
            assert intersects(editor) and intersects(button("Use edited result"))
            assert editor.hasFocus()
            QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
            QTest.keyClicks(editor, "Keyboard draft")
            assert editor.toPlainText() == "Keyboard draft" and editor.hasFocus()
            discard = button("Discard edited result")
            discard.click()
            until(app, lambda: button("Edit result for Notes/Opening.md") is not None
                  and button("Edit result for Notes/Opening.md").isEnabled())
            button("Edit result for Notes/Opening.md").click()
            # Replace this task before its deferred layout/reveal can run.
            queue.setCurrentRow(next(i for i in range(queue.count()) if queue.item(i).text() == "Overview"))
            queue.setFocus()
            settled()
            assert queue.currentItem().text() == "Overview" and queue.hasFocus()
            assert scroll.value() == 0
            assert any(row.isVisible() and row.text() == "Review the whole update"
                       for row in window.findChildren(QLabel))
            discard.click()
            queue.setCurrentRow(next(i for i in range(queue.count()) if queue.item(i).text() == "All changes"))
            until(app, lambda: button("Edit result for Notes/Opening.md") is not None)
            settled()
        else:
            editor.setPlainText(draft)
            expected = editor.toPlainText()
            scroll.setValue(0)
            window.close()
            until(app, lambda: button("Continue review") is not None)
            settled()
            warning = next(row for row in window.findChildren(QLabel)
                           if row.isVisible() and row.text().startswith("Your draft is uncommitted."))
            assert intersects(warning) and intersects(button("Continue review"))
            assert button("Save review and close") is None
            button("Continue review").click()
            settled()
            assert window.isVisible() and editor.toPlainText() == expected
            assert window.runner.session.update_snapshot.binding == binding
            button("Discard edited result").click()
        scroll.setValue(300)
        previous = window.runner.session.update_snapshot.reply
        window.runner.submit_update({"command": "page", "binding": binding, "offset": 0, "limit": 100})
        until(app, lambda: window.runner.session.update_snapshot.reply is not previous
              and not window.workbench.busy and window.runner.session.update_snapshot.reply.page is not None)
        settled()
        assert scroll.value() == 300, "An ordinary comparison read must retain the reading position"
        assert not any(row.command in ("save", "apply", "begin_edit") for row in transport.commands)
        assert list(vault.iterdir()) == [] and source.read_bytes() == b"Controlled outer preparation input"
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()
