"""Exact admitted content through the public observation/session interface."""

import os
import shutil
from pathlib import Path
from threading import Event

import pytest

from brz2obsidian.contracts import ImmutableContentReference
from brz2obsidian.publication.content_session import ContentSession
from brz2obsidian.publication.vault_history import inspect_update_inputs
from tests.application.test_checkpoint_payload import git, retained

__all__ = ["retained"]


def test_current_literal_snapshot_page_stage_and_close(retained, tmp_path):
    vault, _ = retained
    original = (vault / "note.md").read_bytes()
    (vault / "note.md").write_bytes(b"A\r\nB\x00\xffZ")
    index = (vault / ".git/index").read_bytes()
    refs = git(vault, "show-ref")
    head = (vault / ".git/HEAD").read_bytes()
    try:
        with inspect_update_inputs(vault) as observed:
            with observed.content_session(scratch_parent=tmp_path) as session:
                reference = session.acquire("note.md", byte_limit=7)
                assert reference.size == 7
                assert reference.sha256 == (
                    "12a79bc9e4a98a1c672d9be2118a83017128bf98b4bbe36037bc25e93c2c7245"
                )
                assert session.page(reference, offset=2, limit=3) == b"\nB\x00"
                staged = session.stage(reference, byte_limit=7)
                assert staged.path.read_bytes() == b"A\r\nB\x00\xffZ"
                assert staged.reference == reference
            assert not staged.path.exists()
            with pytest.raises(OSError, match="closed"):
                session.page(reference, offset=0, limit=1)
        assert (vault / "note.md").read_bytes() == b"A\r\nB\x00\xffZ"
        assert (vault / ".git/index").read_bytes() == index
        assert git(vault, "show-ref") == refs
        assert (vault / ".git/HEAD").read_bytes() == head
    finally:
        (vault / "note.md").write_bytes(original)


def test_retained_origin_is_closed_over_current_locator_role_and_path(
    retained, tmp_path
):
    vault, locator = retained
    with (
        inspect_update_inputs(vault) as observed,
        observed.content_session(scratch_parent=tmp_path) as session,
    ):
        retained_value = session.acquire(
            "note.md", role="source", locator=locator, byte_limit=7
        )
        current = session.acquire("note.md", byte_limit=6)
        assert session.page(retained_value, offset=0, limit=7) == b"A\r\nB\x00\xffZ"
        assert session.page(current, offset=0, limit=6) == b"later\xff"
        assert session.stage(retained_value, byte_limit=7).path.read_bytes() == (
            b"A\r\nB\x00\xffZ"
        )
        for changes in (
            {"locator": locator.model_copy(update={"generation": 2})},
            {"locator": locator.model_copy(update={"generation": True})},
            {"role": "unsupported"},
            {"role": "review_content"},
            {"path": "absent.bin"},
        ):
            request = {"path": "note.md", "role": "source", "locator": locator}
            with pytest.raises(OSError):
                session.acquire(**(request | changes), byte_limit=7)


def test_finite_budgets_and_cancellation_refuse_transport(retained, tmp_path):
    vault, _ = retained
    cancelled = Event()
    cancelled.set()
    with (
        inspect_update_inputs(vault) as observed,
        observed.content_session(scratch_parent=tmp_path) as session,
    ):
        with pytest.raises(OSError, match="cancel"):
            session.acquire("note.md", byte_limit=6, cancel=cancelled)
        with pytest.raises(OSError, match="time"):
            session.acquire("note.md", byte_limit=6, timeout=1e-9)
        with pytest.raises(OSError, match="budget"):
            session.acquire("note.md", byte_limit=5)
        value = session.acquire("note.md", byte_limit=6)
        with pytest.raises(OSError, match="cancel"):
            session.page(value, offset=0, limit=1, cancel=cancelled)
        with pytest.raises(OSError, match="budget"):
            session.stage(value, byte_limit=5)
        with pytest.raises(OSError, match="cancel"):
            session.stage(value, byte_limit=6, cancel=cancelled)
        with pytest.raises(OSError, match="time"):
            session.stage(value, byte_limit=6, timeout=float("inf"))


def test_registered_values_reconstruct_but_altered_and_foreign_values_refuse(
    retained, tmp_path
):
    vault, locator = retained
    with (
        inspect_update_inputs(vault) as observed,
        observed.content_session(scratch_parent=tmp_path) as session,
        observed.content_session(scratch_parent=tmp_path) as other,
    ):
        value = session.acquire("note.md", byte_limit=6)
        copy = ImmutableContentReference.model_validate(value.model_dump())
        assert copy is not value
        assert session.page(copy, offset=0, limit=6) == b"later\xff"
        for altered in (
            value.model_copy(update={"content_id": "unknown"}),
            value.model_copy(update={"size": 5}),
            value.model_copy(update={"sha256": "0" * 64}),
            value.model_copy(update={"content_id": []}),
            value.model_dump(),
        ):
            with pytest.raises(OSError):
                session.page(altered, offset=0, limit=1)
        with pytest.raises(OSError):
            other.stage(value, byte_limit=6)
        with pytest.raises(OSError):
            session.acquire("note.md", byte_limit=6, locator=locator)
        for offset, limit in ((-1, 1), (7, 1), (0, 65537), (0, 0), (True, 1)):
            with pytest.raises(OSError, match="range"):
                session.page(value, offset=offset, limit=limit)


@pytest.mark.parametrize(
    ("fault", "message"),
    (
        ("corrupt", "integrity"),
        ("partial", "Incomplete content sink write"),
        ("flush", "Synthetic flush failure"),
        ("cancel", "cancel"),
    ),
)
def test_written_stage_must_match_the_verified_input(
    retained, tmp_path, monkeypatch, fault, message
):
    vault, _ = retained
    source = (vault / "note.md").read_bytes()
    index = (vault / ".git/index").read_bytes()
    refs = git(vault, "show-ref")
    head = (vault / ".git/HEAD").read_bytes()
    sentinel = tmp_path / "unrelated"
    sentinel.write_bytes(b"keep")
    cancelled = Event()
    with (
        inspect_update_inputs(vault) as observed,
        observed.content_session(scratch_parent=tmp_path) as session,
    ):
        value = session.acquire("note.md", byte_limit=6)
        real_open = Path.open

        class FaultyWriter:
            def __init__(self, stream):
                self.stream = stream

            def __getattr__(self, name):
                return getattr(self.stream, name)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.stream.close()

            def write(self, block):
                if fault == "corrupt":
                    return self.stream.write(block[:-1] + b"?")
                if fault == "partial":
                    return self.stream.write(block[:-1])
                result = self.stream.write(block)
                if fault == "cancel":
                    cancelled.set()
                return result

            def flush(self):
                if fault == "flush":
                    raise OSError("Synthetic flush failure")
                self.stream.flush()

        def faulty_open(path, mode="r", *args, **kwargs):
            output = real_open(path, mode, *args, **kwargs)
            return FaultyWriter(output) if mode == "xb" else output

        with monkeypatch.context() as patch:
            patch.setattr(Path, "open", faulty_open)
            with pytest.raises(OSError, match=message):
                session.stage(value, byte_limit=6, cancel=cancelled)
            if fault == "corrupt":
                with pytest.raises(OSError, match="integrity"):
                    session.acquire("note.md", byte_limit=6)
        assert session.page(value, offset=0, limit=6) == b"later\xff"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["unrelated"]
    assert sentinel.read_bytes() == b"keep"
    assert (vault / "note.md").read_bytes() == source
    assert (vault / ".git/index").read_bytes() == index
    assert git(vault, "show-ref") == refs
    assert (vault / ".git/HEAD").read_bytes() == head


def test_equal_digest_registration_compares_complete_owned_bytes(retained, tmp_path):
    vault, _ = retained
    with (
        inspect_update_inputs(vault) as observed,
        observed.content_session(scratch_parent=tmp_path) as session,
    ):
        first = session.acquire("note.md", byte_limit=6)
        again = session.acquire("note.md", byte_limit=6)
        assert session.page(first, offset=0, limit=6) == b"later\xff"
        assert session.page(again, offset=0, limit=6) == b"later\xff"
        # Damage test-owned scratch through the filesystem, not an internal
        # equality mock. A later valid source cannot bless an earlier value.
        for path in tmp_path.glob("content-*/*"):
            path.write_bytes(b"later?")
        with pytest.raises(OSError):
            session.acquire("note.md", byte_limit=6)


def test_complete_integrity_precedes_even_a_prefix_page(retained, tmp_path):
    vault, locator = retained
    with (
        inspect_update_inputs(vault) as observed,
        observed.content_session(scratch_parent=tmp_path) as session,
    ):
        original = (vault / "note.md").read_bytes()
        try:
            (vault / "note.md").write_bytes(b"other!")
            with pytest.raises(OSError, match="changed"):
                session.acquire("note.md", byte_limit=6)
        finally:
            (vault / "note.md").write_bytes(original)
        value = session.acquire("note.md", byte_limit=6)
        for damage in (b"later?", b"late"):
            for path in tmp_path.glob("content-*/*"):
                path.write_bytes(damage)
            with pytest.raises(OSError, match="integrity"):
                session.page(value, offset=0, limit=1)
        for path in tmp_path.glob("content-*/*"):
            path.unlink()
        with pytest.raises(OSError):
            session.stage(value, byte_limit=6)
        row = next(
            row
            for row in observed.history.checkpoint.manifest.source
            if row.path == "note.md"
        )
        blob = vault / ".git/objects" / row.object_id[:2] / row.object_id[2:]
        original_blob = blob.read_bytes()
        original_mode = blob.stat().st_mode
        blob.chmod(0o600)
        try:
            blob.write_bytes(b"broken loose blob")
            with pytest.raises(OSError):
                session.acquire("note.md", role="source", locator=locator, byte_limit=7)
        finally:
            blob.write_bytes(original_blob)
            blob.chmod(original_mode)


def test_empty_and_chunk_boundary_values_keep_exact_bytes(retained, tmp_path):
    vault, locator = retained
    large = vault / "boundary.bin"
    large.write_bytes(b"A" * (1024 * 1024) + b"\x00\xffZ")
    try:
        with (
            inspect_update_inputs(vault) as observed,
            observed.content_session(scratch_parent=tmp_path) as session,
        ):
            empty = session.acquire(
                "empty.bin", role="source", locator=locator, byte_limit=0
            )
            assert session.page(empty, offset=0, limit=0) == b""
            assert session.stage(empty, byte_limit=0).path.read_bytes() == b""
            value = session.acquire("boundary.bin", byte_limit=1024 * 1024 + 3)
            assert session.page(value, offset=1024 * 1024 - 1, limit=4) == b"A\x00\xffZ"
            staged = session.stage(value, byte_limit=1024 * 1024 + 3)
            with staged.path.open("rb") as stream:
                assert stream.read(1024 * 1024) == b"A" * (1024 * 1024)
                assert stream.read(4) == b"\x00\xffZ"
                assert stream.read(1) == b""
    finally:
        large.unlink()


def test_observation_lifetime_and_refs_guard_every_session_use(retained, tmp_path):
    vault, _ = retained
    with inspect_update_inputs(vault) as observed:
        with pytest.raises(OSError):
            ContentSession(observed.history, scratch_parent=tmp_path)
        with pytest.raises(OSError, match="outside"):
            observed.content_session(scratch_parent=vault)
        session = observed.content_session(scratch_parent=tmp_path)
        value = session.acquire("note.md", byte_limit=6)
        ref = "refs/heads/content-session-change"
        git(vault, "update-ref", ref, "HEAD")
        try:
            with pytest.raises(OSError):
                session.page(value, offset=0, limit=1)
            with pytest.raises(OSError):
                session.acquire("note.md", byte_limit=6)
        finally:
            git(vault, "update-ref", "-d", ref)
    try:
        with pytest.raises(OSError):
            session.stage(value, byte_limit=6)
        with pytest.raises(OSError):
            observed.content_session(scratch_parent=tmp_path)
    finally:
        session.close()


def test_cleanup_retains_unknown_files_and_refuses_replaced_owned_file(
    retained, tmp_path
):
    vault, _ = retained
    unrelated = tmp_path / "unrelated.bin"
    unrelated.write_bytes(b"retain me")
    with inspect_update_inputs(vault) as observed:
        session = observed.content_session(scratch_parent=tmp_path)
        value = session.acquire("note.md", byte_limit=6)
        stage = session.stage(value, byte_limit=6)
        unknown = stage.path.parent / "not-session-owned"
        unknown.write_bytes(b"unknown owner")
        with pytest.raises(OSError, match="scratch retained"):
            session.close()
        assert unknown.read_bytes() == b"unknown owner"
        assert unrelated.read_bytes() == b"retain me"
        with pytest.raises(OSError, match="closed"):
            session.page(value, offset=0, limit=1)
        unknown.unlink()
        session.close()
        session.close()

        session = observed.content_session(scratch_parent=tmp_path)
        value = session.acquire("note.md", byte_limit=6)
        stage = session.stage(value, byte_limit=6)
        stage.path.unlink()
        os.link(unrelated, stage.path)
        with pytest.raises(OSError, match="scratch retained"):
            session.close()
        assert unrelated.read_bytes() == b"retain me"
        assert stage.path.read_bytes() == b"retain me"
        stage.path.unlink()
        session.close()


def test_disk_admission_refuses_before_owning_another_payload(
    retained, tmp_path, monkeypatch
):
    vault, _ = retained
    with (
        inspect_update_inputs(vault) as observed,
        observed.content_session(scratch_parent=tmp_path) as session,
    ):
        value = session.acquire("note.md", byte_limit=6)
        usage = shutil.disk_usage(tmp_path)
        with monkeypatch.context() as patch:
            patch.setattr(shutil, "disk_usage", lambda _: usage._replace(free=0))
            with pytest.raises(OSError, match="disk budget"):
                session.acquire("note.md", byte_limit=6)
            with pytest.raises(OSError, match="disk budget"):
                session.stage(value, byte_limit=6)
        assert session.page(value, offset=0, limit=6) == b"later\xff"


def test_replaced_scratch_directory_is_never_read_or_cleaned(retained, tmp_path):
    vault, _ = retained
    with inspect_update_inputs(vault) as observed:
        session = observed.content_session(scratch_parent=tmp_path)
        value = session.acquire("note.md", byte_limit=6)
        directory = session.stage(value, byte_limit=6).path.parent
        moved = tmp_path / "retained-original"
        directory.rename(moved)
        directory.mkdir()
        foreign = directory / "unrelated"
        foreign.write_bytes(b"preserve replacement")
        try:
            with pytest.raises(OSError, match="identity"):
                session.page(value, offset=0, limit=1)
            with pytest.raises(OSError, match="scratch retained"):
                session.close()
            assert foreign.read_bytes() == b"preserve replacement"
        finally:
            foreign.unlink()
            directory.rmdir()
            moved.rename(directory)
            session.close()


def test_replaced_backing_with_equal_bytes_is_not_owned_content(retained, tmp_path):
    vault, _ = retained
    with inspect_update_inputs(vault) as observed:
        session = observed.content_session(scratch_parent=tmp_path)
        value = session.acquire("note.md", byte_limit=6)
        replacement = tmp_path / "replacement"
        replacement.write_bytes(b"later\xff")
        backing = next(tmp_path.glob("content-*/*"))
        backing.unlink()
        replacement.rename(backing)
        try:
            with pytest.raises(OSError, match="identity"):
                session.page(value, offset=0, limit=1)
        finally:
            backing.unlink()
            session.close()
