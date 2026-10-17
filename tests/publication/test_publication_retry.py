import hashlib
import time
from pathlib import Path

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_minimal_workflow import PROPERTIES, make_archive


def access_denied():
    error = PermissionError("Controlled final rename denial")
    error.winerror = 5
    return error


@pytest.mark.parametrize("empty", [False, True])
def test_transient_windows_rename_denial_publishes_complete_verified_vault(
    tmp_path, monkeypatch, empty
):
    source = make_archive(tmp_path / "source.brz")
    before = source.read_bytes()
    sentinel = tmp_path / "caller.bin"
    sentinel.write_bytes(b"caller owned\x00\xff")
    destination = tmp_path / "vault"
    if empty:
        destination.mkdir()
    original = Path.rename
    attempts = []
    delays = []

    def rename(path, target):
        if path.name.startswith(".brz2obsidian-"):
            attempts.append((path, target))
            if len(attempts) == 1:
                raise access_denied()
        return original(path, target)

    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(time, "sleep", delays.append)
    result = default_workflow().convert(source, destination)
    assert result.outcome == "clean", result.model_dump(mode="json")
    assert len(attempts) == 2 and delays == [0.01]
    assert result.receipt is not None
    files = {
        p.relative_to(destination).as_posix(): p.read_bytes()
        for p in destination.rglob("*")
        if p.is_file()
    }
    assert {f.relative_path for f in result.receipt.manifest} == set(files)
    for verified in result.receipt.manifest:
        data = files[verified.relative_path]
        assert verified.length == len(data)
        assert verified.sha256 == hashlib.sha256(data).hexdigest()
    assert files["Attachments/22222222/Notes.md.original"] == b"Authored body.\r\n"
    assert files["Home — Entry thought.md"] == PROPERTIES + (
        b"# Entry thought\n\nAuthored body.\r\n\n"
        b"## Categories\n\n[[Categories.md|Browse categories]]\n"
    )
    assert source.read_bytes() == before
    assert sentinel.read_bytes() == b"caller owned\x00\xff"
    assert not list(tmp_path.glob(".brz2obsidian-*"))


@pytest.mark.parametrize(
    ("error_type", "winerror", "attempt_count", "expected_delays"),
    [
        (PermissionError, 5, 6, [0.01, 0.02, 0.04, 0.08, 0.16]),
        (PermissionError, 32, 1, []),
        (OSError, 5, 1, []),
        (FileExistsError, 183, 1, []),
    ],
)
def test_permanent_or_unselected_rename_errors_fail_safely(
    tmp_path, monkeypatch, error_type, winerror, attempt_count, expected_delays
):
    source = make_archive(tmp_path / "source.brz")
    before = source.read_bytes()
    destination = tmp_path / "vault"
    original = Path.rename
    attempts = []
    delays = []

    def rename(path, target):
        if path.name.startswith(".brz2obsidian-"):
            attempts.append(path)
            error = error_type("Controlled persistent rename error")
            error.winerror = winerror
            raise error
        return original(path, target)

    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(time, "sleep", delays.append)
    result = default_workflow().convert(source, destination)
    assert result.outcome == "failed", result.model_dump(mode="json")
    assert result.receipt is None
    assert [i.code for i in result.issues] == ["write_failure"]
    assert len(attempts) == attempt_count and delays == expected_delays
    assert source.read_bytes() == before
    assert not destination.exists() and not list(tmp_path.glob(".brz2obsidian-*"))


def test_empty_destination_removal_denial_is_not_retried(tmp_path, monkeypatch):
    source = make_archive(tmp_path / "source.brz")
    destination = tmp_path / "vault"
    destination.mkdir()
    original = Path.rmdir
    removals = []
    delays = []

    def rmdir(path, *args, **kwargs):
        if path == destination:
            removals.append(path)
            raise access_denied()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "rmdir", rmdir)
    monkeypatch.setattr(time, "sleep", delays.append)
    result = default_workflow().convert(source, destination)
    assert result.outcome == "failed" and result.receipt is None
    assert [i.code for i in result.issues] == ["write_failure"]
    assert removals == [destination] and delays == []
    assert destination.is_dir() and list(destination.iterdir()) == []
    assert not list(tmp_path.glob(".brz2obsidian-*"))


@pytest.mark.parametrize("initially_empty", [False, True])
@pytest.mark.parametrize("populated", [False, True])
def test_late_caller_destination_survives_denied_rename_interval(
    tmp_path, monkeypatch, initially_empty, populated
):
    source = make_archive(tmp_path / "source.brz")
    before = source.read_bytes()
    destination = tmp_path / "vault"
    if initially_empty:
        destination.mkdir()
    original_rename = Path.rename
    original_rmdir = Path.rmdir
    attempts = []
    removals = []
    delays = []

    def rename(path, target):
        if path.name.startswith(".brz2obsidian-"):
            attempts.append(path)
            if len(attempts) == 1:
                raise access_denied()
        return original_rename(path, target)

    def rmdir(path, *args, **kwargs):
        if path == destination:
            removals.append(path)
        return original_rmdir(path, *args, **kwargs)

    def sleep(delay):
        delays.append(delay)
        destination.mkdir()
        if populated:
            (destination / "caller.bin").write_bytes(b"late caller\x00\xff")

    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(Path, "rmdir", rmdir)
    monkeypatch.setattr(time, "sleep", sleep)
    result = default_workflow().convert(source, destination)
    assert result.outcome == ("refused" if populated else "failed"), result.issues
    assert result.receipt is None
    assert [i.code for i in result.issues] == [
        "destination_not_empty" if populated else "write_failure"
    ]
    assert len(attempts) == (1 if populated else 2) and delays == [0.01]
    assert removals == ([destination] if initially_empty else [])
    if populated:
        assert (destination / "caller.bin").read_bytes() == b"late caller\x00\xff"
        assert list(destination.iterdir()) == [destination / "caller.bin"]
    else:
        assert destination.is_dir() and list(destination.iterdir()) == []
    assert source.read_bytes() == before
    assert not list(tmp_path.glob(".brz2obsidian-*"))


def test_non_windows_denial_is_not_retried(tmp_path, monkeypatch):
    import sys

    source = make_archive(tmp_path / "source.brz")
    destination = tmp_path / "vault"
    original = Path.rename
    attempts = []
    delays = []

    def rename(path, target):
        if path.name.startswith(".brz2obsidian-"):
            attempts.append(path)
            raise access_denied()
        return original(path, target)

    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(time, "sleep", delays.append)
    monkeypatch.setattr(sys, "platform", "linux")
    result = default_workflow().convert(source, destination)
    assert result.outcome == "failed" and result.receipt is None
    assert [i.code for i in result.issues] == ["write_failure"]
    assert len(attempts) == 1 and delays == []
    assert not destination.exists() and not list(tmp_path.glob(".brz2obsidian-*"))


@pytest.mark.parametrize("mutation", ["source", "corrupt", "extra", "missing"])
def test_changed_source_or_staging_cannot_be_published_after_denial(
    tmp_path, monkeypatch, mutation
):
    source = make_archive(tmp_path / "source.brz")
    before = source.read_bytes()
    destination = tmp_path / "vault"
    original = Path.rename
    attempts = []
    delays = []

    def rename(path, target):
        if path.name.startswith(".brz2obsidian-"):
            attempts.append(path)
            raise access_denied()
        return original(path, target)

    def sleep(delay):
        delays.append(delay)
        staging = attempts[0]
        payload = staging / "Attachments/22222222/Notes.md.original"
        assert payload.read_bytes() == b"Authored body.\r\n"
        if mutation == "source":
            source.write_bytes(before + b"changed during delay")
        elif mutation == "corrupt":
            payload.write_bytes(b"Corrupt! body.\r\n")
        elif mutation == "extra":
            (staging / "unexpected.bin").write_bytes(b"unplanned")
        else:
            payload.unlink()

    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(time, "sleep", sleep)
    result = default_workflow().convert(source, destination)
    assert result.outcome == ("refused" if mutation == "source" else "failed")
    assert result.receipt is None
    assert [i.code for i in result.issues] == [
        "source_changed" if mutation == "source" else "payload_integrity_failure"
    ]
    assert len(attempts) == 1 and delays == [0.01]
    assert source.read_bytes() == (
        before + b"changed during delay" if mutation == "source" else before
    )
    assert not destination.exists() and not list(tmp_path.glob(".brz2obsidian-*"))


def test_source_change_during_retry_hashing_refuses_publication(tmp_path, monkeypatch):
    source = make_archive(tmp_path / "source.brz")
    before = source.read_bytes()
    destination = tmp_path / "vault"
    original_rename = Path.rename
    original_open = Path.open
    attempts = []
    reads = []

    def rename(path, target):
        if path.name.startswith(".brz2obsidian-"):
            attempts.append(path)
            raise access_denied()
        return original_rename(path, target)

    def open_file(path, mode="r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        if attempts and not reads and mode == "rb" and path.is_relative_to(attempts[0]):
            reads.append(path)
            assert source.read_bytes() == before
            source.write_bytes(before + b"changed during renewed hash")
        return stream

    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(Path, "open", open_file)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    result = default_workflow().convert(source, destination)
    assert result.outcome == "refused", result.model_dump(mode="json")
    assert result.receipt is None
    assert [i.code for i in result.issues] == ["source_changed"]
    assert len(attempts) == len(reads) == 1
    assert source.read_bytes() == before + b"changed during renewed hash"
    assert not destination.exists() and not list(tmp_path.glob(".brz2obsidian-*"))


@pytest.mark.parametrize(
    "replacement", ["directory", "junction", "descendant_junction"]
)
def test_replaced_or_reparse_staging_never_claims_foreign_ownership(
    tmp_path, monkeypatch, replacement
):
    import subprocess

    source = make_archive(tmp_path / "source.brz")
    before = source.read_bytes()
    destination = tmp_path / "vault"
    caller = tmp_path / "caller"
    caller.mkdir()
    (caller / "sentinel.bin").write_bytes(b"caller owned\x00\xff")
    parked = tmp_path / "original-owned"
    original = Path.rename
    attempts = []
    junctions = []

    def rename(path, target):
        if path.name.startswith(".brz2obsidian-"):
            attempts.append(path)
            raise access_denied()
        return original(path, target)

    def sleep(_delay):
        staging = attempts[0]
        if replacement != "descendant_junction":
            original(staging, parked)
        if replacement == "directory":
            staging.mkdir()
            (staging / "foreign.bin").write_bytes(b"replacement owned by caller")
        else:
            junction = (
                staging / "foreign" if replacement == "descendant_junction" else staging
            )
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(caller)],
                check=True,
                capture_output=True,
            )
            junctions.append(junction)

    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(time, "sleep", sleep)
    result = default_workflow().convert(source, destination)
    assert result.outcome == ("failed" if replacement == "directory" else "refused")
    assert result.receipt is None
    assert [i.code for i in result.issues] == [
        "write_failure" if replacement == "directory" else "unsafe_target_path",
        "cleanup_failure",
    ]
    assert len(attempts) == 1
    assert result.issues[-1].leftover_path == str(attempts[0])
    assert not destination.exists() and source.read_bytes() == before
    assert (caller / "sentinel.bin").read_bytes() == b"caller owned\x00\xff"
    assert list(caller.iterdir()) == [caller / "sentinel.bin"]
    if replacement == "directory":
        assert (attempts[0] / "foreign.bin").read_bytes() == (
            b"replacement owned by caller"
        )
        assert list(attempts[0].iterdir()) == [attempts[0] / "foreign.bin"]
    if replacement != "descendant_junction":
        assert (parked / "Attachments/22222222/Notes.md.original").read_bytes() == (
            b"Authored body.\r\n"
        )
    # Remove only the test-created junction itself, retaining both owned data
    # and caller data; do not leave a traversable link in retained test evidence.
    for junction in junctions:
        junction.rmdir()


def test_exhausted_rename_and_cleanup_denial_report_owned_leftover(
    tmp_path, monkeypatch
):
    import os

    source = make_archive(tmp_path / "source.brz")
    before = source.read_bytes()
    destination = tmp_path / "vault"
    original_rename = Path.rename
    original_rmdir = os.rmdir
    attempts = []
    removals = []

    def rename(path, target):
        if path.name.startswith(".brz2obsidian-"):
            attempts.append(path)
            raise access_denied()
        return original_rename(path, target)

    def rmdir(path, *args, **kwargs):
        if Path(path).name.startswith(".brz2obsidian-"):
            removals.append(Path(path))
            raise PermissionError("Controlled owned cleanup denial")
        return original_rmdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(os, "rmdir", rmdir)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    result = default_workflow().convert(source, destination)
    assert result.outcome == "failed" and result.receipt is None
    assert [i.code for i in result.issues] == ["write_failure", "cleanup_failure"]
    assert len(attempts) == 6 and removals == [attempts[0]]
    assert result.issues[-1].leftover_path == str(attempts[0])
    assert attempts[0].is_dir()
    assert not destination.exists() and source.read_bytes() == before


@pytest.mark.parametrize("failure_boundary", ["ancestry", "identity_stat"])
def test_failure_before_staging_identity_returns_issue_and_preserves_unknown_path(
    tmp_path, monkeypatch, failure_boundary
):
    import tempfile

    source = make_archive(tmp_path / "source.brz")
    before = source.read_bytes()
    destination = tmp_path / "vault"
    original_create = tempfile.mkdtemp
    original_read = Path.lstat if failure_boundary == "ancestry" else Path.stat
    created = []
    failures = []

    def create(*args, **kwargs):
        name = original_create(*args, **kwargs)
        staging = Path(name)
        (staging / "caller.bin").write_bytes(b"unknown identity caller bytes\x00\xff")
        created.append(staging)
        return name

    def read_identity(path, *args, **kwargs):
        if created and path == created[0]:
            failures.append(path)
            raise PermissionError("Controlled failure before staging identity capture")
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(tempfile, "mkdtemp", create)
    monkeypatch.setattr(
        Path, "lstat" if failure_boundary == "ancestry" else "stat", read_identity
    )
    result = default_workflow().convert(source, destination)
    assert result.outcome == "failed", result.model_dump(mode="json")
    assert result.receipt is None
    assert [i.code for i in result.issues] == ["write_failure", "cleanup_failure"]
    assert (
        "Controlled failure before staging identity capture" in result.issues[0].message
    )
    assert result.issues[-1].leftover_path == str(created[0])
    assert failures == created
    assert not destination.exists() and source.read_bytes() == before
    assert (
        created[0] / "caller.bin"
    ).read_bytes() == b"unknown identity caller bytes\x00\xff"
