import os
from pathlib import Path
from threading import Event

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QTextEdit

from tests.gui.test_inspection_window import until

pytestmark = pytest.mark.gui


def control(window, kind, name):
    return next(
        widget
        for widget in window.findChildren(kind)
        if widget.accessibleName() == name
    )


@pytest.mark.parametrize("published", [False, True])
@pytest.mark.parametrize("separator", ["", "\u00a0", "\u2028", "\u2029", "😀"])
def test_narrow_paths_wrap_unbroken_segments_and_preserve_exact_selected_text(
    tmp_path,
    published,
    separator,
):
    from brz2obsidian.application.contracts import SelectVault
    from brz2obsidian_ui.window import MainWindow
    from tests.application.test_completion_session import published_session
    from tests.application.test_conversion_session import ready_session
    from tests.application.test_minimal_workflow import make_archive

    app = QApplication.instance() or QApplication([])
    parent = tmp_path / ("UnbrokenWindowsPathSegment" * 2 + separator + "UnbrokenEnd")
    parent.mkdir()
    source = make_archive(parent / "Archive café.brz")
    if published:
        session, destination = published_session(parent)
        paths = {"Published vault path": str(destination)}
    else:
        session = ready_session(source, parent)
        paths = {
            "Selected archive path": str(source),
            "Complete destination path": str(parent / "Fresh vault"),
        }
    window = MainWindow(session=session)
    window.resize(453, 852)
    window.show()
    window.submit(SelectVault(path_or_null=None))
    try:
        until(app, lambda: window.snapshot.result is not None)
        for accessible, expected in paths.items():
            path = control(window, QTextEdit, accessible)
            assert path.isVisible() and path.isReadOnly()
            assert path.toPlainText() == expected
            path.setFocus()
            QTest.keyClick(path, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
            assert path.textCursor().selectedText() == expected
            assert path.createMimeDataFromSelection().text() == expected
            window.tabs.setCurrentIndex(1)
            window.tabs.setCurrentIndex(0)
            assert path.textCursor().selectedText() == expected
            path.setFocus()
            QTest.keyClick(path, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
            tail = (
                "Archive café.brz"
                if accessible == "Selected archive path"
                else "Fresh vault"
            )
            for _ in tail:
                QTest.keyClick(path, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
            assert path.createMimeDataFromSelection().text() == tail
            app.processEvents()
            document = path.document()
            assert (
                document.documentLayout().documentSize().height()
                <= path.viewport().height()
            )
            layout = document.firstBlock().layout()
            assert layout.lineCount() > 1
            assert all(
                layout.lineAt(index).naturalTextWidth() <= path.viewport().width()
                for index in range(layout.lineCount())
            )
    finally:
        window.close()
        until(app, lambda: not window.isVisible())
        window.shutdown()


def test_destination_form_presents_backend_path_errors_order_and_picker_cancel(
    tmp_path,
):
    from brz2obsidian.application.contracts import (
        InspectCommand,
        SelectSource,
        WorkerResponse,
    )
    from brz2obsidian.application.operations import inspect, validate_destination
    from brz2obsidian.application.transport import Terminal
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()

    class Supervisor:
        def run(self, request):
            result = (
                inspect(source)
                if request.operation == "inspect"
                else validate_destination(
                    Path(request.arguments.parent), request.arguments.vault_name
                )
            )
            return Terminal(
                phase="completed",
                process_status=0 if result.outcome in ("clean", "valid") else 1,
                response=WorkerResponse(
                    request_id=request.request_id,
                    operation=request.operation,
                    result=result,
                ),
            )

    class Picker:
        selected = str(tmp_path)

        def choose_parent(self, callback):
            QTimer.singleShot(0, lambda: callback(self.selected))

    picker = Picker()
    window = MainWindow(supervisor=Supervisor(), dialogs=picker)
    window.show()
    window.submit(SelectSource(path_or_null=str(source)))
    until(app, lambda: window.snapshot.source == str(source))
    name = control(window, QLineEdit, "Vault name")
    assert name.text() == "minimal"
    parent_field = control(window, QLineEdit, "Output parent folder")
    assert (
        abs(
            parent_field.mapTo(window, parent_field.rect().topLeft()).y()
            - name.mapTo(window, name.rect().topLeft()).y()
        )
        <= 4
    )
    window.submit(InspectCommand())
    until(app, lambda: window.snapshot.reviewed is not None)
    retained = window.snapshot.result
    control(window, QPushButton, "Choose output parent folder").click()
    until(app, lambda: window.snapshot.destination == str(tmp_path / "minimal"))
    assert control(window, QTextEdit, "Complete destination path").toPlainText() == str(
        tmp_path / "minimal"
    )
    sections = [
        widget
        for widget in window.findChildren(QLabel)
        if widget.text() in ("Source archive", "Findings", "Destination")
    ]
    assert [
        widget.text()
        for widget in sorted(
            sections,
            key=lambda widget: widget.mapTo(window, widget.rect().topLeft()).y(),
        )
    ] == ["Source archive", "Findings", "Destination"]
    name.setText("CON")
    name.textEdited.emit("CON")
    until(
        app,
        lambda: (
            bool(window.snapshot.field_errors)
            and not window.snapshot.validation_pending
        ),
    )
    assert "Windows" in control(window, QLabel, "Vault name error").text()
    assert (
        abs(
            parent_field.mapTo(window, parent_field.rect().topLeft()).y()
            - name.mapTo(window, name.rect().topLeft()).y()
        )
        <= 4
    )
    assert (
        not control(window, QTextEdit, "Complete destination path")
        .toPlainText()
        .endswith("CON")
    )
    assert window.snapshot.result is retained
    assert not window.primary.isEnabled()
    picker.selected = None
    before = window.snapshot
    control(window, QPushButton, "Choose output parent folder").click()
    app.processEvents()
    assert window.snapshot is before
    assert name.text() == "CON"
    assert control(window, QPushButton, "Choose output parent folder").hasFocus()
    parent_field = control(window, QLineEdit, "Output parent folder")
    assert (
        parent_field.mapTo(window, parent_field.rect().topLeft()).x()
        < name.mapTo(window, name.rect().topLeft()).x()
    )
    window.resize(500, 820)
    app.processEvents()
    assert (
        parent_field.mapTo(window, parent_field.rect().topLeft()).y()
        < name.mapTo(window, name.rect().topLeft()).y()
    )
    assert window.close_button.isVisible()
    window.close()
    until(app, lambda: not window.isVisible())
    window.shutdown()


def test_slow_validation_coalesces_edited_form_while_inspection_and_gui_continue(
    tmp_path,
    monkeypatch,
):
    from brz2obsidian.application.contracts import (
        InspectCommand,
        SelectSource,
        SetDestination,
        WorkerResponse,
    )
    from brz2obsidian.application.operations import inspect, validate_destination
    from brz2obsidian.application.transport import Terminal
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    clock = [0.0]
    monkeypatch.setattr("brz2obsidian_ui.window.monotonic", lambda: clock[0])
    entered, release = Event(), Event()
    validations = []

    class Supervisor:
        def run(self, request):
            if request.operation == "validate_destination":
                name = request.arguments.vault_name
                validations.append(name)
                if name == "First":
                    entered.set()
                    assert release.wait(10)
                result = validate_destination(Path(request.arguments.parent), name)
            else:
                result = inspect(source)
            return Terminal(
                phase="completed",
                process_status=0,
                response=WorkerResponse(
                    request_id=request.request_id,
                    operation=request.operation,
                    result=result,
                ),
            )

    window = MainWindow(supervisor=Supervisor())
    window.show()
    try:
        window.submit(SelectSource(path_or_null=str(source)))
        until(app, lambda: window.snapshot.source is not None)
        window.submit(SetDestination(parent_or_null=str(tmp_path), vault_name="First"))
        until(
            app,
            lambda: (
                entered.is_set() and window.snapshot.validation_request_id is not None
            ),
        )
        clock[0] = 10.0
        window.submit(InspectCommand())
        until(app, lambda: window.snapshot.reviewed is not None)
        retained = window.snapshot.result
        clock[0] = 12.0
        until(app, lambda: "0:12 elapsed" in window.guidance.text())
        QTimer.singleShot(0, window.disclosure.click)
        until(app, lambda: window.diagnostics_expanded)
        assert "inspection_clean" not in window.findings.text()
        assert "ready for review" in window.findings.text()
        name = control(window, QLineEdit, "Vault name")
        for text in ("Second", "Latest"):
            name.setText(text)
            name.textEdited.emit(text)
        until(app, lambda: window.snapshot.vault_name == "Latest")
        assert validations == ["First"]
        assert window.snapshot.destination is None
        assert not window.primary.isEnabled()
        assert "Validating destination" in window.guidance.text()
        assert not release.is_set()
        release.set()
        until(app, lambda: window.snapshot.destination == str(tmp_path / "Latest"))
        assert validations == ["First", "Latest"]
        assert window.snapshot.result is retained
        assert name.text() == "Latest"
    finally:
        release.set()
        window.close()
        until(app, lambda: not window.isVisible())
        window.shutdown()
