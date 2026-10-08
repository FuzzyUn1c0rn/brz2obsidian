import os
from time import monotonic

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QPushButton, QTabBar

pytestmark = pytest.mark.gui


def until(app, condition):
    deadline = monotonic() + 15
    while not condition():
        app.processEvents()
        if monotonic() > deadline:
            pytest.fail("GUI condition did not complete")


def action(window, name):
    return next(
        button
        for button in window.findChildren(QPushButton)
        if button.accessibleName() == name
    )


def test_standalone_clean_inspection_carries_through_host_without_conversion(tmp_path):
    from brz2obsidian.application.contracts import InspectCommand, SelectSource
    from brz2obsidian_ui.window import MainWindow
    from tests.application.test_minimal_workflow import make_archive

    app = QApplication.instance() or QApplication([])
    source = make_archive(tmp_path / "Clean archive.brz")
    original = source.read_bytes()
    window = MainWindow()
    window.show()
    tabs = window.findChild(QTabBar)
    tabs.setCurrentIndex(1)
    try:
        window.submit(SelectSource(path_or_null=source.as_posix()))
        until(app, lambda: window.snapshot.source is not None)
        window.submit(InspectCommand())
        until(app, lambda: window.snapshot.result is not None)
        reviewed, result = window.snapshot.reviewed, window.snapshot.result
        assert action(window, "Convert this archive").isEnabled()
        action(window, "Convert this archive").click()
        until(app, lambda: tabs.currentIndex() == 0)
        assert window.snapshot.reviewed == reviewed
        assert window.snapshot.result == result
        assert window.snapshot.source == str(source)
        assert window.snapshot.publication is None
        assert not action(window, "Convert").isEnabled()
        assert source.read_bytes() == original
        assert not (tmp_path / "Clean archive").exists()
    finally:
        window.close()
        until(app, lambda: not window.isVisible())
        window.shutdown()


def test_real_standalone_warning_carry_requires_explicit_warning_action(tmp_path):
    import sys
    from pathlib import Path

    from PySide6.QtWidgets import QCheckBox, QLabel

    from brz2obsidian.application.contracts import InspectCommand, SelectSource
    from brz2obsidian.application.transport import Supervisor
    from brz2obsidian_ui.window import MainWindow
    from tests.support.v3_collection import mixed_v3_archive

    app = QApplication.instance() or QApplication([])
    source = mixed_v3_archive(tmp_path / "Warning archive.BRZ")
    original = source.read_bytes()
    parent = tmp_path / "Warning Café"
    parent.mkdir()
    requests, terminals = [], []
    delegate = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src")

    class RecordingSupervisor:
        def run(self, request):
            requests.append(request)
            terminal = delegate.run(request)
            terminals.append(terminal)
            return terminal

    window = MainWindow(supervisor=RecordingSupervisor())
    window.show()
    tabs = window.findChild(QTabBar)
    tabs.setCurrentIndex(1)
    try:
        window.submit(SelectSource(path_or_null=source.as_posix()))
        until(app, lambda: window.snapshot.source is not None)
        window.submit(InspectCommand())
        until(app, lambda: window.snapshot.result is not None)
        reviewed, result = window.snapshot.reviewed, window.snapshot.result
        assert reviewed.outcome == "warnings" and result.findings
        tabs.setCurrentIndex(0)
        assert not action(window, "Convert with warnings").isEnabled()
        tabs.setCurrentIndex(1)
        assert window.snapshot.reviewed == reviewed and len(requests) == 1
        action(window, "Convert this archive").click()
        until(app, lambda: tabs.currentIndex() == 0)
        assert window.snapshot.reviewed == reviewed and window.snapshot.result == result
        panel = window.findChild(QLabel, "findings").text()
        assert "Inspection completed — source warnings" in panel
        assert all(finding.message in panel for finding in result.findings)
        assert window.snapshot.publication is None
        window.parent_selected(parent.as_posix())
        until(app, lambda: window.snapshot.destination_validation is not None)
        assert action(window, "Convert with warnings").isEnabled()
        assert not window.findChildren(QCheckBox)
        assert [request.operation for request in requests] == [
            "inspect",
            "validate_destination",
        ]
        action(window, "Convert with warnings").click()
        until(app, lambda: window.snapshot.publication is not None)
        assert requests[-1].arguments.proceed_with_warnings is True
        assert terminals[-1].process_status == 2
        assert window.snapshot.result.status == "conversion_created_with_warnings"
        assert window.snapshot.publication.receipt_verified
        assert any(
            "Vault created with warnings" in label.text()
            for label in window.findChildren(QLabel)
        )
        assert all(
            finding.message in window.findChild(QLabel, "findings").text()
            for finding in window.snapshot.result.findings
        )
        assert next(
            label
            for label in window.findChildren(QLabel)
            if label.accessibleName() == "Published vault path"
        ).text() == str(parent / "Warning archive")
        assert source.read_bytes() == original
    finally:
        window.close()
        until(app, lambda: not window.isVisible())
        window.shutdown()


@pytest.mark.parametrize("outcome", ["clean", "warnings", "refused", "failed"])
def test_injected_inspection_outcome_carry_tabs_and_source_invalidation(
    tmp_path, outcome
):
    from brz2obsidian.application.contracts import (
        InspectCommand,
        InspectionResult,
        SelectSource,
        WorkerResponse,
    )
    from brz2obsidian.application.operations import inspect
    from brz2obsidian.application.transport import Terminal
    from brz2obsidian_ui.window import MainWindow
    from tests.application.test_minimal_workflow import make_archive
    from tests.support.v3_collection import mixed_v3_archive

    app = QApplication.instance() or QApplication([])
    source = (
        mixed_v3_archive(tmp_path / "Warning.brz")
        if outcome == "warnings"
        else make_archive(tmp_path / "Source.brz")
    )
    result = (
        inspect(source)
        if outcome in ("clean", "warnings")
        else InspectionResult(
            outcome=outcome, status="inspection_" + outcome, review_required=True
        )
    )
    requests = []

    class PreparedSupervisor:
        def run(self, request):
            requests.append(request)
            return Terminal(
                phase="completed",
                process_status=0
                if outcome == "clean"
                else 2
                if outcome == "warnings"
                else 1,
                response=WorkerResponse(
                    request_id=request.request_id, operation="inspect", result=result
                ),
            )

    window = MainWindow(supervisor=PreparedSupervisor())
    window.show()
    tabs = window.findChild(QTabBar)
    tabs.setCurrentIndex(1)
    try:
        window.submit(SelectSource(path_or_null=str(source)))
        until(app, lambda: window.snapshot.source is not None)
        window.submit(InspectCommand())
        until(app, lambda: window.snapshot.result is not None)
        before = window.snapshot
        tabs.setCurrentIndex(0)
        tabs.setCurrentIndex(1)
        assert window.snapshot == before and len(requests) == 1
        if outcome in ("clean", "warnings"):
            action(window, "Convert this archive").click()
            until(app, lambda: tabs.currentIndex() == 0)
            name = "Convert with warnings" if outcome == "warnings" else "Convert"
            assert not action(window, name).isEnabled()
            assert window.snapshot.reviewed == result.reviewed
        else:
            assert not any(
                button.accessibleName() == "Convert this archive"
                for button in window.findChildren(QPushButton)
            )
            assert window.snapshot.reviewed is None
            tabs.setCurrentIndex(0)
            assert action(window, "Inspect archive").isEnabled()
        window.submit(SelectSource(path_or_null=str(tmp_path / "Different.brz")))
        until(app, lambda: window.snapshot.source != str(source))
        assert window.snapshot.reviewed is None and window.snapshot.review_required
        assert action(window, "Inspect archive").isEnabled()
        assert len(requests) == 1
    finally:
        window.close()
        until(app, lambda: not window.isVisible())
        window.shutdown()
