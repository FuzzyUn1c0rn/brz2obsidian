import os
from time import monotonic

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTabBar, QTextEdit

from tests.gui.test_conversion_window import window_text

pytestmark = pytest.mark.gui


def until(app, condition):
    deadline = monotonic() + 10
    while not condition():
        app.processEvents()
        if monotonic() > deadline:
            pytest.fail("GUI condition did not complete")


def button(window, accessible):
    return next(
        widget
        for widget in window.findChildren(QPushButton)
        if widget.accessibleName() == accessible
    )


def test_check_tab_async_selection_real_worker_clean_result_and_cancel_preserve_state(
    tmp_path,
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    (tmp_path / "Manual.md").write_text(
        "# Manual\nNOTE_BODY_CANARY\n", encoding="utf-8"
    )
    callbacks = []

    class Dialogs:
        def choose_vault(self, callback):
            callbacks.append(callback)

    window = MainWindow(dialogs=Dialogs())
    window.show()
    window.findChild(QTabBar).setCurrentIndex(2)
    assert any(
        widget.accessibleName() == "Check findings"
        for widget in window.findChildren(QTextEdit)
    )
    assert "Check an existing vault without changing it." in [
        widget.text() for widget in window.findChildren(QLabel)
    ]
    button(window, "Choose vault folder").click()
    assert len(callbacks) == 1
    callbacks.pop()(str(tmp_path))
    until(app, lambda: window.snapshot.vault == str(tmp_path))
    button(window, "Check vault").click()
    until(app, lambda: window.snapshot.result is not None)
    text = window_text(window)
    assert "Check completed — no issues found" in text
    assert "read-only" in text
    assert "Inventory files: 1" in text
    assert "Planned notes" not in text
    assert "NOTE_BODY_CANARY" not in text
    previous = window.snapshot
    button(window, "Choose vault folder").click()
    callbacks.pop()(None)
    app.processEvents()
    assert window.snapshot == previous
    window.close()
    until(app, lambda: not window.isVisible())
    window.shutdown()


@pytest.mark.parametrize(
    "state, title",
    [
        ("issues", "Check completed — issues found"),
        ("failed", "Check could not complete"),
    ],
)
def test_real_check_outcome_titles_findings_and_unavailable_counts(
    tmp_path, state, title
):
    from brz2obsidian.application.contracts import SelectVault, SimpleCommand
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "selected"
    if state == "issues":
        vault.mkdir()
        (vault / "Manual.md").write_text(
            "![[REFERENCE_CANARY.png]]\n", encoding="utf-8"
        )
    window = MainWindow()
    window.show()
    window.findChild(QTabBar).setCurrentIndex(2)
    window.submit(SelectVault(path_or_null=str(vault)))
    until(app, lambda: window.snapshot.vault is not None)
    window.submit(SimpleCommand(command="check_vault"))
    until(app, lambda: window.snapshot.result is not None)
    text = window_text(window)
    assert title in text
    assert "REFERENCE_CANARY" not in text
    assert "conversion failure" not in text.lower()
    if state == "failed":
        assert "Inventory files: unavailable" in text
        assert "Check the path" in text
    window.close()
    until(app, lambda: not window.isVisible())
    window.shutdown()
