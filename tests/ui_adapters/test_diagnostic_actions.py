"""Diagnostic file adapters at the real filesystem boundary."""

import pytest

DiagnosticActions = pytest.importorskip(
    "brz2obsidian_ui.platform_actions"
).DiagnosticActions


def test_save_complete_unicode_report_without_requiring_rendered_pages(tmp_path):
    report = "brz2obsidian diagnostic report\nOperation: inspect\n" + (
        "Safe finding: café 雪 🦄\n" * 450
    )
    destination = tmp_path / "rapport 雪.txt"

    outcome = DiagnosticActions().save_report(report, destination)

    assert outcome.succeeded
    assert outcome.path is None
    assert destination.read_bytes() == report.encode("utf-8")
    assert list(tmp_path.iterdir()) == [destination]


def test_failed_replace_preserves_existing_report_and_hides_exception(
    tmp_path, monkeypatch
):
    destination = tmp_path / "Selected report with spaces Café 雪.txt"
    destination.write_bytes(b"previous report")

    def denied(source, target):
        raise PermissionError("PRIVATE exception canary")

    monkeypatch.setattr("os.replace", denied)
    outcome = DiagnosticActions().save_report("new safe report", destination)

    assert not outcome.succeeded
    assert "could not be saved" in outcome.message
    assert "PRIVATE" not in outcome.message
    assert outcome.path == str(destination)
    assert destination.read_bytes() == b"previous report"
    assert list(tmp_path.iterdir()) == [destination]


def test_copy_delivers_complete_safe_text_to_clipboard_boundary():
    received = []
    report = "Safe Unicode 雪\n" * 450
    actions = DiagnosticActions(
        clipboard=lambda text, owner: received.append((text, owner))
    )

    outcome = actions.copy_report(report, 123)

    assert outcome.succeeded
    assert outcome.path is None
    assert received == [(report, 123)]


def test_clipboard_failure_is_nonfatal_and_does_not_expose_native_error():
    def busy(text, owner):
        raise OSError("PRIVATE native error canary")

    outcome = DiagnosticActions(clipboard=busy).copy_report("safe report", 123)

    assert not outcome.succeeded
    assert "could not be copied" in outcome.message
    assert outcome.path is None
    assert "PRIVATE" not in outcome.message


def test_missing_destination_parent_reports_nonfatal_save_failure(tmp_path):
    destination = tmp_path / "absent Café" / "Selected report 雪.txt"
    outcome = DiagnosticActions().save_report("safe report", destination)

    assert not outcome.succeeded
    assert outcome.path == str(destination)
    assert not list(tmp_path.iterdir())
