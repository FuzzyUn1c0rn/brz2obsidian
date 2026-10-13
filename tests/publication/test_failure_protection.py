import os
from pathlib import Path

import pytest

from brz2obsidian.contracts import GeneratedFile, MigrationRefused
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import render
from brz2obsidian.publication import publish
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from tests.application.test_minimal_workflow import make_archive
from tests.application.test_module_seams import METADATA


def artifacts_for(session):
    return render(plan(analyze(session.snapshot, BRZ_POLICY)), METADATA)


@pytest.mark.parametrize(
    "paths",
    [
        ("Café.md", "Cafe\u0301.md"),
        ("folder", "folder/note.md"),
        ("notes/A.md", "NOTES/a.md"),
        ("./note.md",),
        ("folder//note.md",),
        ("NUL.md",),
        ("COM¹.md",),
        ("CONIN$",),
        ("con .txt",),
        ("note.md ",),
    ],
)
def test_unsafe_or_ambiguous_manifest_is_refused_before_staging(tmp_path, paths):
    with BrzSourceModule().open(make_archive(tmp_path / "source.brz")) as session:
        artifacts = artifacts_for(session)
        generated = tuple(
            GeneratedFile(
                relative_path=p,
                content=b"",
                sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            )
            for p in paths
        )
        artifacts = artifacts.model_copy(
            update={"generated_files": generated, "copies": (), "manifest": paths}
        )
        with pytest.raises(MigrationRefused) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert error.value.issues[0].code == "unsafe_target_path"
    assert not (tmp_path / "vault").exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


def test_session_closure_revokes_an_already_open_payload_stream(tmp_path):
    with BrzSourceModule().open(make_archive(tmp_path / "source.brz")) as session:
        durable = session.snapshot
        payload_context = session.open_payload(session.snapshot.assets[0].asset_id)
        stream = payload_context.__enter__()
        assert stream.read(1) == b"A"
    assert stream.closed
    assert durable.documents[0].text == "Authored body.\r\n"
    with pytest.raises(ValueError):
        stream.read()
    payload_context.__exit__(None, None, None)


def test_source_truncation_refuses_commit_and_cleans_staging(tmp_path):
    source = make_archive(tmp_path / "source.brz")
    with BrzSourceModule().open(source) as session:
        artifacts = artifacts_for(session)
        source.write_bytes(b"truncated")
        with pytest.raises((MigrationRefused, Exception)) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert not (tmp_path / "vault").exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []
    assert getattr(error.value, "issues", None)


class SessionBoundary:
    def __init__(self, session, before_copy=None):
        self.snapshot = session.snapshot
        self.source_identity = session.source_identity
        self.session = session
        self.before_copy = before_copy

    def open_payload(self, asset_id):
        if self.before_copy:
            self.before_copy()
        return self.session.open_payload(asset_id)

    def verify_consistency(self):
        self.session.verify_consistency()


def mutate_complete_staging_on_walk(monkeypatch, parent, manifest, mutate):
    """Inject once when the filesystem inventories fully written staging.

    Check the actual files before mutation; consistency verification remains real
    and may run any number of times. Delegate all walks, including cleanup.
    """
    original = os.walk
    reached = []

    def walk(root, *args, **kwargs):
        staging = Path(root)
        if (
            staging.parent == parent
            and staging.name.startswith(".brz2obsidian-")
            and not reached
        ):
            assert all((staging / path).is_file() for path in manifest)
            mutate(staging)
            reached.append(staging)
        return original(root, *args, **kwargs)

    monkeypatch.setattr(os, "walk", walk)
    return reached


def test_staged_extra_file_is_refused_when_added_before_staged_inventory(
    tmp_path, monkeypatch
):
    with BrzSourceModule().open(make_archive(tmp_path / "source.brz")) as session:
        artifacts = artifacts_for(session)

        def add_extra(staging):
            (staging / "unplanned.txt").write_bytes(b"unplanned")
            assert (staging / "unplanned.txt").read_bytes() == b"unplanned"

        reached = mutate_complete_staging_on_walk(
            monkeypatch, tmp_path, artifacts.manifest, add_extra
        )
        with pytest.raises(Exception) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert len(reached) == 1
    assert error.value.issues[0].code == "payload_integrity_failure"
    assert not (tmp_path / "vault").exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


def test_native_commit_never_replaces_late_caller_destination(tmp_path, monkeypatch):
    destination = tmp_path / "vault"
    original = Path.rename

    def racing_rename(path, target):
        destination.mkdir()
        (destination / "caller.txt").write_bytes(b"late caller content")
        return original(path, target)

    monkeypatch.setattr(Path, "rename", racing_rename)
    with (
        BrzSourceModule().open(make_archive(tmp_path / "source.brz")) as session,
        pytest.raises(MigrationRefused) as error,
    ):
        publish(artifacts_for(session), session, destination)
    assert error.value.issues[0].code == "destination_not_empty"
    assert (destination / "caller.txt").read_bytes() == b"late caller content"
    assert list(destination.iterdir()) == [destination / "caller.txt"]
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


def test_staging_junction_cannot_redirect_payload_writes_or_recursive_cleanup(tmp_path):
    import shutil
    import subprocess

    caller = tmp_path / "caller"
    caller.mkdir()
    (caller / "sentinel.txt").write_bytes(b"caller owned")
    junction = None
    with BrzSourceModule().open(make_archive(tmp_path / "source.brz")) as session:

        def redirect_copy():
            nonlocal junction
            staging = next(tmp_path.glob(".brz2obsidian-*"))
            junction = staging / "Attachments"
            (junction / "22222222").rmdir()
            junction.rmdir()
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(caller)],
                check=True,
                capture_output=True,
            )

        with pytest.raises(Exception) as error:
            publish(
                artifacts_for(session),
                SessionBoundary(session, before_copy=redirect_copy),
                tmp_path / "vault",
            )
    assert (caller / "sentinel.txt").read_bytes() == b"caller owned"
    assert list(caller.iterdir()) == [caller / "sentinel.txt"]
    assert not (tmp_path / "vault").exists()
    assert error.value.issues[0].code == "unsafe_target_path"
    leftover = error.value.issues[-1]
    assert leftover.code == "cleanup_failure"
    owned = Path(leftover.leftover_path)
    assert owned.parent == tmp_path and owned.name.startswith(".brz2obsidian-")
    junction.rmdir()
    shutil.rmtree(owned)


@pytest.mark.parametrize("field", ["source_sha256", "snapshot_digest"])
def test_matching_asset_identity_cannot_bypass_source_binding(tmp_path, field):
    with BrzSourceModule().open(make_archive(tmp_path / "source.brz")) as session:
        artifacts = artifacts_for(session)
        identity = artifacts.source_identity.model_copy(update={field: "0" * 64})
        artifacts = artifacts.model_copy(update={"source_identity": identity})
        with pytest.raises(MigrationRefused) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert error.value.issues[0].code == "source_changed"
    assert not (tmp_path / "vault").exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


def test_late_caller_file_in_empty_destination_survives_rmdir_race(
    tmp_path, monkeypatch
):
    destination = tmp_path / "vault"
    destination.mkdir()
    original = Path.rmdir

    def racing_rmdir(path):
        if path == destination:
            (destination / "caller.txt").write_bytes(b"keep this")
        return original(path)

    monkeypatch.setattr(Path, "rmdir", racing_rmdir)
    with (
        BrzSourceModule().open(make_archive(tmp_path / "source.brz")) as session,
        pytest.raises(MigrationRefused) as error,
    ):
        publish(artifacts_for(session), session, destination)
    assert error.value.issues[0].code == "destination_not_empty"
    assert (destination / "caller.txt").read_bytes() == b"keep this"
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


def test_changed_source_between_fingerprint_and_zip_open_is_refused(
    tmp_path, monkeypatch
):
    import zipfile

    source = make_archive(tmp_path / "source.brz")
    original = zipfile.ZipFile.__init__

    def changed_open(archive, stream, *args, **kwargs):
        with source.open("ab") as output:
            output.write(b"changed after fingerprint")
        original(archive, stream, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "__init__", changed_open)
    with pytest.raises(MigrationRefused) as error, BrzSourceModule().open(source):
        pass
    assert error.value.issues[0].code == "source_changed"


@pytest.mark.parametrize("fault", ["short", "read"])
def test_partial_or_failing_real_payload_stream_never_publishes(tmp_path, fault):
    from contextlib import contextmanager

    from brz2obsidian.contracts import MigrationFailed

    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"Authored" if fault == "short" else b"Authored body.\r\n")
    streams = []

    class ReadFailure:
        def __init__(self, stream):
            self.stream = stream
            self.read_once = False

        def read(self, length):
            if self.read_once:
                raise OSError("Controlled payload read failure")
            self.read_once = True
            return self.stream.read(length)

    class FaultSession(SessionBoundary):
        @contextmanager
        def open_payload(self, asset_id):
            with payload.open("rb") as stream:
                streams.append(stream)
                yield ReadFailure(stream) if fault == "read" else stream

    with (
        BrzSourceModule().open(make_archive(tmp_path / "source.brz")) as session,
        pytest.raises(MigrationFailed) as error,
    ):
        publish(artifacts_for(session), FaultSession(session), tmp_path / "vault")
    assert error.value.issues[0].code == (
        "payload_integrity_failure" if fault == "short" else "write_failure"
    )
    assert all(stream.closed for stream in streams)
    assert payload.read_bytes().startswith(b"Authored")
    assert not (tmp_path / "vault").exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


def test_partial_real_write_failure_cleans_staging_and_preserves_caller_files(
    tmp_path, monkeypatch
):
    from brz2obsidian.contracts import MigrationFailed

    original = Path.open
    caller = tmp_path / "caller.txt"
    caller.write_bytes(b"caller owned")

    class WriteFailure:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def write(self, content):
            self.stream.write(content[:2])
            self.stream.flush()
            raise OSError("Controlled partial write failure")

    def fail_write(path, mode="r", *args, **kwargs):
        stream = original(path, mode, *args, **kwargs)
        return WriteFailure(stream) if mode == "xb" else stream

    with BrzSourceModule().open(make_archive(tmp_path / "source.brz")) as session:
        artifacts = artifacts_for(session)
        monkeypatch.setattr(Path, "open", fail_write)
        with pytest.raises(MigrationFailed) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert error.value.issues[0].code == "write_failure"
    assert caller.read_bytes() == b"caller owned"
    assert not (tmp_path / "vault").exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


def test_source_mutation_during_staging_is_detected_before_commit(
    tmp_path, monkeypatch
):
    source = make_archive(tmp_path / "source.brz")
    with BrzSourceModule().open(source) as session:
        artifacts = artifacts_for(session)

        def change_source(staging):
            source.write_bytes(b"changed")
            assert source.read_bytes() == b"changed"

        reached = mutate_complete_staging_on_walk(
            monkeypatch, tmp_path, artifacts.manifest, change_source
        )
        with pytest.raises(MigrationRefused) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert len(reached) == 1
    assert error.value.issues[0].code == "source_changed"
    assert not (tmp_path / "vault").exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


def test_source_crc_failure_during_payload_access_is_structured(tmp_path):
    import zipfile

    from brz2obsidian.contracts import MigrationFailed

    source = make_archive(tmp_path / "source.brz")
    with BrzSourceModule().open(source) as session:
        with zipfile.ZipFile(source) as archive:
            info = archive.getinfo("22222222-2222-4222-8222-222222222222/Notes.md")
        with source.open("r+b") as changed:
            changed.seek(
                info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
            )
            changed.write(b"X")
        with (
            pytest.raises(MigrationFailed) as error,
            session.open_payload(session.snapshot.assets[0].asset_id) as stream,
        ):
            stream.read()
    assert error.value.issues[0].code == "payload_read_failure"


def test_session_teardown_closes_all_payloads_even_when_one_close_reports_io_failure(
    tmp_path, monkeypatch
):
    import zipfile

    from brz2obsidian.contracts import MigrationFailed

    source = make_archive(tmp_path / "source.brz")
    contexts = []
    streams = []
    original = zipfile.ZipExtFile.close
    first_close = True

    def failing_close(stream):
        nonlocal first_close
        original(stream)
        if first_close:
            first_close = False
            raise OSError("Controlled payload close failure")

    with (
        pytest.raises(MigrationFailed) as error,
        BrzSourceModule().open(source) as session,
    ):
        for _ in range(2):
            context = session.open_payload(session.snapshot.assets[0].asset_id)
            contexts.append(context)
            streams.append(context.__enter__())
        monkeypatch.setattr(zipfile.ZipExtFile, "close", failing_close)
    assert error.value.issues[0].code == "session_teardown_failure"
    assert all(stream.closed for stream in streams)
    monkeypatch.setattr(zipfile.ZipExtFile, "close", original)
    for context in contexts:
        context.__exit__(None, None, None)


def test_source_change_during_staged_validation_is_rechecked_before_commit(
    tmp_path, monkeypatch
):
    source = make_archive(tmp_path / "source.brz")
    original = Path.open
    changed = False

    def change_during_validation(path, mode="r", *args, **kwargs):
        nonlocal changed
        if (
            mode == "rb"
            and path.parent.name.startswith(".brz2obsidian-")
            and not changed
        ):
            changed = True
            with original(source, "ab") as stream:
                stream.write(b"changed during validation")
        return original(path, mode, *args, **kwargs)

    with BrzSourceModule().open(source) as session:
        artifacts = artifacts_for(session)
        monkeypatch.setattr(Path, "open", change_during_validation)
        with pytest.raises(MigrationRefused) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert error.value.issues[0].code == "source_changed"
    assert not (tmp_path / "vault").exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


@pytest.mark.parametrize(
    "reserved",
    [("migration-record.json",), ("folder", "folder/child.md"), ("../escape.md",)],
)
def test_uncreated_target_paths_are_reserved_and_validated_with_emitted_files(
    tmp_path, reserved
):
    with BrzSourceModule().open(make_archive(tmp_path / "source.brz")) as session:
        artifacts = artifacts_for(session).model_copy(
            update={"reserved_paths": reserved}
        )
        with pytest.raises(MigrationRefused) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert error.value.issues[0].code == "unsafe_target_path"
    assert not (tmp_path / "vault").exists()


def test_uncreated_target_final_path_uses_240_utf16_unit_limit(tmp_path):
    with BrzSourceModule().open(make_archive(tmp_path / "source.brz")) as session:
        artifacts = artifacts_for(session).model_copy(
            update={"reserved_paths": ("Notes/" + "\U0001f600" * 100 + ".md",)}
        )
        with pytest.raises(MigrationRefused) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert error.value.issues[0].code == "target_path_too_long"
    assert not (tmp_path / "vault").exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


def test_public_source_context_preserves_material_diagnostics_when_teardown_fails(
    tmp_path, monkeypatch
):
    import zipfile

    from brz2obsidian.contracts import Issue, MigrationFailed

    original = zipfile.ZipFile.close

    def failing_close(archive):
        original(archive)
        raise OSError("Controlled archive close failure")

    source = make_archive(tmp_path / "source.brz")
    with pytest.raises(MigrationFailed) as error, BrzSourceModule().open(source):
        monkeypatch.setattr(zipfile.ZipFile, "close", failing_close)
        raise MigrationRefused(
            (
                Issue(
                    code="material_refusal",
                    phase="publication",
                    message="Caller content exists",
                    guidance="Use fresh vault",
                ),
            )
        )
    assert [issue.code for issue in error.value.issues] == [
        "material_refusal",
        "session_teardown_failure",
    ]
    monkeypatch.setattr(zipfile.ZipFile, "close", original)
