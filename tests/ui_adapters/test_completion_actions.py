"""Completion adapters at the filesystem and OS dispatch boundaries."""

import pytest

CompletionActions = pytest.importorskip(
    "brz2obsidian_ui.platform_actions"
).CompletionActions


def test_explicit_folder_and_report_opens_dispatch_existing_absolute_paths(tmp_path):
    vault = tmp_path / "Vault café 雪"
    vault.mkdir()
    report = vault / "MIGRATION REPORT.md"
    report.write_text("generated report", encoding="utf-8")
    received = []
    actions = CompletionActions(launch=received.append)

    folder = actions.open_folder(vault)
    migration_report = actions.open_report(report)

    assert folder.succeeded and migration_report.succeeded
    assert received == [str(vault), str(report)]
    assert folder.path == str(vault)
    assert migration_report.path == str(report)
    assert "requested" in folder.message and "requested" in migration_report.message
    assert report.read_text(encoding="utf-8") == "generated report"
    assert list(vault.iterdir()) == [report]


def test_obsidian_requests_vault_manager_without_private_path_and_explains_first_use(
    tmp_path,
):
    vault = tmp_path / "Vault café 雪 #% & Leadership"
    vault.mkdir()
    report = vault / "MIGRATION REPORT.md"
    report.write_text("existing generated report", encoding="utf-8")
    received = []

    outcome = CompletionActions(launch=received.append).open_in_obsidian(report)

    assert outcome.succeeded
    assert received == ["obsidian://choose-vault"]
    assert outcome.path == str(vault)
    assert "requested" in outcome.message
    assert "does not confirm" in outcome.message
    assert "Open folder as vault" in outcome.message
    assert "published vault folder" in outcome.message
    assert report.read_text(encoding="utf-8") == "existing generated report"
    assert list(vault.iterdir()) == [report]


@pytest.mark.parametrize("method", ["open_folder", "open_report", "open_in_obsidian"])
def test_missing_target_does_not_dispatch_and_returns_copyable_path(tmp_path, method):
    missing = tmp_path / "missing"
    received = []

    outcome = getattr(CompletionActions(launch=received.append), method)(missing)

    assert not outcome.succeeded
    assert "unavailable" in outcome.message
    assert outcome.path == str(
        missing.parent if method == "open_in_obsidian" else missing
    )
    assert received == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("method", ["open_folder", "open_report", "open_in_obsidian"])
def test_relative_target_never_reaches_os_dispatch(method):
    received = []

    outcome = getattr(CompletionActions(launch=received.append), method)("relative")

    assert not outcome.succeeded
    assert outcome.path is None
    assert received == []


@pytest.mark.parametrize("method", ["open_folder", "open_report", "open_in_obsidian"])
def test_failed_native_dispatch_is_safe_and_keeps_target_available(tmp_path, method):
    vault = tmp_path / "published"
    vault.mkdir()
    report = vault / "MIGRATION REPORT.md"
    report.write_bytes(b"generated report")
    target = vault if method == "open_folder" else report
    received = []

    def unavailable(value):
        received.append(value)
        raise OSError("PRIVATE native handler canary")

    outcome = getattr(CompletionActions(launch=unavailable), method)(target)

    assert not outcome.succeeded
    assert "could not be opened" in outcome.message
    assert "PRIVATE" not in outcome.message
    assert outcome.path == str(vault if method == "open_in_obsidian" else target)
    assert len(received) == 1
    if method == "open_in_obsidian":
        assert "URI handler may be unavailable" in outcome.message
        assert "Open folder as vault" in outcome.message
        assert "published vault folder" in outcome.message
    assert report.read_bytes() == b"generated report"
    assert list(vault.iterdir()) == [report]


def test_report_folder_mismatch_never_dispatches(tmp_path):
    report = tmp_path / "MIGRATION REPORT.md"
    report.write_text("generated report", encoding="utf-8")
    received = []
    actions = CompletionActions(launch=received.append)

    assert not actions.open_folder(report).succeeded
    assert not actions.open_report(tmp_path).succeeded
    assert not actions.open_in_obsidian(tmp_path).succeeded
    assert received == []


@pytest.mark.parametrize("method", ["open_folder", "open_report", "open_in_obsidian"])
def test_permission_is_readmitted_after_target_check_and_before_dispatch(
    tmp_path, method
):
    vault = tmp_path / "published"
    vault.mkdir()
    report = vault / "MIGRATION REPORT.md"
    report.write_text("generated report", encoding="utf-8")
    target = vault if method == "open_folder" else report
    received = []
    checks = []

    def deny_current():
        checks.append("readmitted")
        return False

    outcome = getattr(CompletionActions(launch=received.append), method)(
        target, admit=deny_current
    )

    assert checks == ["readmitted"]
    assert received == []
    assert not outcome.succeeded
    assert "changed" in outcome.message
    assert report.read_text(encoding="utf-8") == "generated report"


def test_default_adapter_requests_registered_windows_open_action(tmp_path, monkeypatch):
    received = []
    monkeypatch.setattr(
        "os.startfile", lambda *args: received.append(args), raising=False
    )

    outcome = CompletionActions().open_folder(tmp_path)

    assert outcome.succeeded
    assert received == [(str(tmp_path), "open")]


def test_blocked_filesystem_check_readmits_before_any_native_launch(
    tmp_path, monkeypatch
):
    import os
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from threading import Event, get_ident

    report = tmp_path / "MIGRATION REPORT.md"
    report.write_bytes(b"generated report")
    started, release = Event(), Event()
    original_isfile = os.path.isfile
    threads, received = [], []
    allowed = True

    def blocked_isfile(path):
        if not isinstance(path, int) and Path(path) == report:
            threads.append(get_ident())
            started.set()
            assert release.wait(5)
        return original_isfile(path)

    monkeypatch.setattr(os.path, "isfile", blocked_isfile)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            CompletionActions(launch=received.append).open_report,
            report,
            admit=lambda: allowed,
        )
        try:
            assert started.wait(5)
            assert not future.done()
            allowed = False
        finally:
            release.set()
        outcome = future.result(timeout=5)

    assert threads and all(thread != get_ident() for thread in threads)
    assert received == []
    assert not outcome.succeeded and "changed" in outcome.message
    assert report.read_bytes() == b"generated report"
