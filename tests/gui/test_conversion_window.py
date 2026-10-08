import os
from threading import Event
from time import monotonic

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QTextEdit

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


def test_native_picker_path_representation_guided_real_worker_conversion(tmp_path):
    from brz2obsidian_ui.window import MainWindow
    from tests.application.test_minimal_workflow import make_archive

    app = QApplication.instance() or QApplication([])
    source = make_archive(tmp_path / "Native archive.brz")
    original = source.read_bytes()
    parent = tmp_path / "Destination Café"
    parent.mkdir()
    callbacks = {}

    class Dialogs:
        def choose_source(self, callback):
            callbacks["source"] = callback

        def choose_parent(self, callback):
            callbacks["parent"] = callback

    window = MainWindow(dialogs=Dialogs())
    window.show()
    try:
        button(window, "Choose source archive").click()
        callbacks["source"](source.as_posix())
        until(app, lambda: window.snapshot.source is not None)
        button(window, "Inspect archive").click()
        until(app, lambda: window.snapshot.result is not None)
        assert window.snapshot.reviewed is not None
        assert not button(window, "Convert").isEnabled()
        button(window, "Choose output parent folder").click()
        callbacks["parent"](parent.as_posix())
        until(app, lambda: window.snapshot.destination_validation is not None)
        assert button(window, "Convert").isEnabled()
        button(window, "Convert").click()
        until(app, lambda: window.snapshot.publication is not None)
        assert window.snapshot.result.status == "conversion_created"
        path = parent / "Native archive"
        assert window.snapshot.destination == str(path)
        assert (path / "migration-record.json").is_file()
        assert any(
            widget.isVisible() and widget.toPlainText() == str(path)
            for widget in window.findChildren(QTextEdit)
        )
        assert source.read_bytes() == original
    finally:
        window.close()
        until(app, lambda: not window.isVisible())
        window.shutdown()


def test_conversion_processes_queued_gui_events_locks_inputs_and_defers_close(
    tmp_path, monkeypatch
):
    import brz2obsidian_ui.window as window_module
    from brz2obsidian.application.contracts import SimpleCommand, WorkerResponse
    from brz2obsidian.application.operations import convert_reviewed
    from brz2obsidian.application.transport import Terminal
    from brz2obsidian_ui.window import MainWindow
    from tests.application.test_conversion_session import ready_session
    from tests.application.test_minimal_workflow import make_archive

    app = QApplication.instance() or QApplication([])
    source = make_archive(tmp_path / "archive.brz")
    original = source.read_bytes()
    session = ready_session(source, tmp_path)
    entered, release = Event(), Event()
    clock = [100.0]
    monkeypatch.setattr(window_module, "monotonic", lambda: clock[0])

    class BlockedConversion:
        def run(self, request):
            assert request.operation == "convert_reviewed"
            entered.set()
            assert release.wait(10)
            arguments = request.arguments
            result = convert_reviewed(
                source, tmp_path, arguments.vault_name, arguments.reviewed
            )
            return Terminal(
                phase="completed",
                process_status=0,
                response=WorkerResponse(
                    request_id=request.request_id,
                    operation=request.operation,
                    result=result,
                ),
            )

    window = MainWindow(supervisor=BlockedConversion(), session=session)
    window.show()
    try:
        window.submit(SimpleCommand(command="carry_inspection_to_convert"))
        until(app, lambda: window.snapshot.reviewed is not None)
        assert button(window, "Convert").isEnabled()
        button(window, "Convert").click()
        until(app, entered.is_set)
        until(app, lambda: window.snapshot.busy_operation == "convert_reviewed")
        QTimer.singleShot(0, button(window, "Diagnostic details").click)
        until(app, lambda: window.diagnostics_expanded)
        painted = []
        QTimer.singleShot(
            0, lambda: (window.repaint(), painted.append(not window.grab().isNull()))
        )
        until(app, lambda: bool(painted))
        assert painted == [True] and not release.is_set()
        assert "Converting" in "\n".join(
            label.text() for label in window.findChildren(QLabel)
        )
        clock[0] = 112.0
        until(
            app,
            lambda: any(
                "0:12 elapsed" in label.text() for label in window.findChildren(QLabel)
            ),
        )
        assert not button(window, "Choose source archive").isEnabled()
        assert not button(window, "Choose output parent folder").isEnabled()
        assert not next(
            field
            for field in window.findChildren(QLineEdit)
            if field.accessibleName() == "Vault name"
        ).isEnabled()
        window.close()
        until(app, lambda: window.snapshot.close_pending)
        assert window.isVisible() and not release.is_set()
        release.set()
        until(app, lambda: not window.isVisible())
        assert window.snapshot.result.status == "conversion_created"
        assert window.snapshot.publication.receipt_verified
        assert source.read_bytes() == original
    finally:
        release.set()
        window.close()
        until(app, lambda: not window.isVisible())
        window.shutdown()


@pytest.mark.parametrize(
    "outcome,title,published",
    [
        ("clean", "Vault created", True),
        ("warnings", "Vault created with warnings", True),
        ("refused", "Conversion could not proceed", False),
        ("failed", "Conversion could not complete", False),
        ("late_error", "Vault created; a follow-up error occurred", True),
        ("not_started", "The operation could not start", False),
        ("unknown", "Publication status unknown", False),
    ],
)
def test_conversion_outcomes_render_receipt_path_or_retained_inputs_without_inference(
    tmp_path, outcome, title, published
):
    from brz2obsidian.application.contracts import (
        ConversionResult,
        ConvertCommand,
        Finding,
        Publication,
        SimpleCommand,
        WorkerResponse,
    )
    from brz2obsidian.application.transport import Terminal
    from brz2obsidian.contracts import Counts
    from brz2obsidian_ui.window import MainWindow
    from tests.application.test_conversion_session import ready_session
    from tests.application.test_minimal_workflow import make_archive

    app = QApplication.instance() or QApplication([])
    source = make_archive(tmp_path / "archive.brz")
    session = ready_session(source, tmp_path)
    path = str(tmp_path / "Fresh vault")
    leftover = str(tmp_path / ".brz2obsidian-owned-leftover")
    if outcome not in ("not_started", "unknown"):
        business_outcome = "failed" if outcome == "late_error" else outcome
        status = {
            "clean": "conversion_created",
            "warnings": "conversion_created_with_warnings",
            "refused": "conversion_refused",
            "failed": "conversion_failed",
            "late_error": "conversion_created_with_error",
        }[outcome]
        result = ConversionResult(
            outcome=business_outcome,
            status=status,
            publication=Publication(
                state="published_verified" if published else "not_published",
                destination=path if published else None,
                receipt_verified=published,
            ),
            destination=path,
            counts=Counts(planned_notes=1, actual_notes=1 if published else None),
            findings=(
                Finding(
                    code="cleanup_failure",
                    severity="error",
                    message="Review the reported owned leftover.",
                    path=leftover,
                ),
            )
            if outcome in ("failed", "late_error")
            else (),
            diagnostic_text="Safe complete conversion report.",
        )

    class OutcomeSupervisor:
        def run(self, request):
            if outcome in ("not_started", "unknown"):
                return Terminal(
                    phase="not_started"
                    if outcome == "not_started"
                    else "may_have_executed",
                    code="launch_failure"
                    if outcome == "not_started"
                    else "protocol_failure",
                )
            return Terminal(
                phase="completed",
                process_status=0
                if business_outcome == "clean"
                else 2
                if business_outcome == "warnings"
                else 1,
                response=WorkerResponse(
                    request_id=request.request_id,
                    operation=request.operation,
                    result=result,
                ),
            )

    window = MainWindow(supervisor=OutcomeSupervisor(), session=session)
    window.show()
    try:
        window.submit(SimpleCommand(command="carry_inspection_to_convert"))
        until(app, lambda: window.snapshot.reviewed is not None)
        window.submit(ConvertCommand())
        until(
            app,
            lambda: (
                window.snapshot.result is not None
                and window.snapshot.result.operation == "convert_reviewed"
                or window.snapshot.operational_status is not None
            ),
        )
        text = "\n".join(
            widget.text()
            for widget in window.findChildren(QLabel)
            if widget.isVisible()
        )
        assert title in text
        assert "conversion_created" not in text and "conversion_failed" not in text
        assert not (
            tmp_path / "Fresh vault"
        ).exists()  # Only the injected receipt is authority here.
        name = next(
            field
            for field in window.findChildren(QLineEdit)
            if field.accessibleName() == "Vault name"
        )
        assert name.isVisible() is not published
        if published:
            path_view = next(
                label
                for label in window.findChildren(QTextEdit)
                if label.accessibleName() == "Published vault path"
            )
            assert path_view.isVisible() and path_view.toPlainText() == path
        else:
            assert name.text() == "Fresh vault"
            assert "Actual notes: unavailable" in text or outcome in (
                "not_started",
                "unknown",
            )
        if outcome in ("failed", "late_error"):
            assert leftover in text
        if not published:
            assert not window.findChild(QPushButton, "primary").isEnabled()
    finally:
        window.close()
        until(app, lambda: not window.isVisible())
        window.shutdown()
