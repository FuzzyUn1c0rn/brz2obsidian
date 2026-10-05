"""Actual OS/staging/stream controls reach new v2 artifact families."""

import hashlib
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest

from brz2obsidian.contracts import GeneratedFile, MigrationFailed, MigrationRefused
from brz2obsidian.publication import publish
from brz2obsidian.sources.thebrain import BrzSourceModule
from tests.application.test_graph_workflow import identity
from tests.publication.test_failure_protection import SessionBoundary, artifacts_for
from tests.support.v2_collection import CATEGORY_ICON, inventory, mixed_archive

SUPPORT_TARGETS = (
    "Templates/New note.md",
    "Templates/Concept.md",
    "Templates/Bases/Members.base",
    ".obsidian/templates.json",
    ".obsidian/types.json",
    "Vault guide.md",
)


def staged_relative(path):
    for parent in path.parents:
        if parent.name.startswith(".brz2obsidian-"):
            return path.relative_to(parent).as_posix()
    return None


def caller_files(tmp_path):
    caller = tmp_path / "caller"
    (caller / "nested").mkdir(parents=True)
    (caller / "sentinel.bin").write_bytes(b"caller owned\x00\xff")
    (caller / "nested/keep.md").write_bytes(b"caller Markdown\r\n")
    return caller, inventory(caller)


def failed_safely(tmp_path, caller, before, error, code):
    assert error.value.issues[0].code == code
    assert not (tmp_path / "vault").exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []
    assert inventory(caller) == before


@pytest.mark.parametrize("target", SUPPORT_TARGETS)
def test_partial_real_support_write_reaches_selected_family_and_cleans_owned_staging(
    tmp_path, monkeypatch, target
):
    caller, before = caller_files(tmp_path)
    original = Path.open
    reached, streams = [], []

    class PartialWrite:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def write(self, data):
            self.stream.write(data[:2])
            self.stream.flush()
            raise OSError("Controlled selected support write failure")

    def fail_selected(path, mode="r", *args, **kwargs):
        stream = original(path, mode, *args, **kwargs)
        if mode == "xb" and staged_relative(path) == target:
            reached.append(target)
            streams.append(stream)
            return PartialWrite(stream)
        return stream

    with BrzSourceModule().open(mixed_archive(tmp_path / "source.brz")) as session:
        artifacts = artifacts_for(session)
        monkeypatch.setattr(Path, "open", fail_selected)
        with pytest.raises(MigrationFailed) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert reached == [target] and all(s.closed for s in streams)
    failed_safely(tmp_path, caller, before, error, "write_failure")


@pytest.mark.parametrize("target", SUPPORT_TARGETS)
@pytest.mark.parametrize("corruption", ["delete", "truncate", "same_length"])
def test_selected_staged_support_corruption_cannot_publish(
    tmp_path, target, corruption
):
    caller, before = caller_files(tmp_path)
    reached = []
    with BrzSourceModule().open(mixed_archive(tmp_path / "source.brz")) as session:
        artifacts = artifacts_for(session)

        def corrupt():
            path = next(tmp_path.glob(".brz2obsidian-*")) / target
            original = path.read_bytes()
            assert original
            reached.append(target)
            if corruption == "delete":
                path.unlink()
            elif corruption == "truncate":
                path.write_bytes(original[:2])
            else:
                altered = bytes([original[0] ^ 1]) + original[1:]
                assert len(altered) == len(original) and altered != original
                path.write_bytes(altered)

        with pytest.raises(MigrationFailed) as error:
            publish(
                artifacts,
                SessionBoundary(session, before_commit=corrupt),
                tmp_path / "vault",
            )
    assert reached == [target]
    failed_safely(tmp_path, caller, before, error, "payload_integrity_failure")


@pytest.mark.parametrize("target", SUPPORT_TARGETS)
def test_source_change_while_validating_selected_nested_support_is_rechecked(
    tmp_path, monkeypatch, target
):
    caller, before = caller_files(tmp_path)
    source = mixed_archive(tmp_path / "source.brz")
    original = Path.open
    reached = []

    def change_source(path, mode="r", *args, **kwargs):
        if mode == "rb" and staged_relative(path) == target and not reached:
            reached.append(target)
            with original(source, "ab") as stream:
                stream.write(b"source changed during support validation")
        return original(path, mode, *args, **kwargs)

    with BrzSourceModule().open(source) as session:
        artifacts = artifacts_for(session)
        monkeypatch.setattr(Path, "open", change_source)
        with pytest.raises(MigrationRefused) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert reached == [target]
    failed_safely(tmp_path, caller, before, error, "source_changed")


@pytest.mark.parametrize("field", ["source_sha256", "snapshot_digest"])
def test_support_rich_plan_remains_bound_to_source_identity(tmp_path, field):
    caller, before = caller_files(tmp_path)
    with BrzSourceModule().open(mixed_archive(tmp_path / "source.brz")) as session:
        artifacts = artifacts_for(session)
        bound = artifacts.source_identity.model_copy(update={field: "0" * 64})
        with pytest.raises(MigrationRefused) as error:
            publish(
                artifacts.model_copy(update={"source_identity": bound}),
                session,
                tmp_path / "vault",
            )
    failed_safely(tmp_path, caller, before, error, "source_changed")


@pytest.mark.parametrize("when", ["before_staging", "after_staging"])
def test_support_rich_source_truncation_refuses_commit(tmp_path, when):
    caller, before = caller_files(tmp_path)
    source = mixed_archive(tmp_path / "source.brz")
    with BrzSourceModule().open(source) as session:
        artifacts = artifacts_for(session)
        if when == "before_staging":
            source.write_bytes(b"truncated")
        boundary = (
            SessionBoundary(
                session, before_commit=lambda: source.write_bytes(b"truncated")
            )
            if when == "after_staging"
            else session
        )
        with pytest.raises(MigrationRefused) as error:
            publish(artifacts, boundary, tmp_path / "vault")
    failed_safely(tmp_path, caller, before, error, "source_changed")


@pytest.mark.parametrize(
    "collision",
    [
        "reserved_template",
        "case_base",
        "nfc_base",
        "file_parent",
        "long_support",
        "long_reserved",
    ],
)
def test_support_manifest_and_reserved_path_collisions_refuse_before_staging(
    tmp_path, collision
):
    caller, before = caller_files(tmp_path)
    with BrzSourceModule().open(mixed_archive(tmp_path / "source.brz")) as session:
        artifacts = artifacts_for(session)
        generated = list(artifacts.generated_files)
        reserved = artifacts.reserved_paths
        if collision == "reserved_template":
            reserved += ("Templates/New note.md",)
        elif collision == "long_reserved":
            reserved += ("Notes/" + "\U0001f600" * 100 + ".md",)
        else:
            additions = {
                "case_base": ("templates/bases/members.BASE",),
                "nfc_base": (
                    "Templates/Bases/Café.base",
                    "Templates/Bases/Cafe\u0301.base",
                ),
                "file_parent": ("Templates",),
                "long_support": ("Templates/" + "x" * 220 + ".md",),
            }[collision]
            generated.extend(
                GeneratedFile(
                    relative_path=p,
                    content=b"control",
                    sha256=hashlib.sha256(b"control").hexdigest(),
                )
                for p in additions
            )
        manifest = tuple(g.relative_path for g in generated) + tuple(
            c.relative_path for c in artifacts.copies
        )
        # Keep manifest aligned so collision/path validation is the selected control.
        altered = artifacts.model_copy(
            update={
                "generated_files": tuple(generated),
                "manifest": manifest,
                "reserved_paths": reserved,
            }
        )
        with pytest.raises(MigrationRefused) as error:
            publish(altered, session, tmp_path / "vault")
    failed_safely(
        tmp_path,
        caller,
        before,
        error,
        "target_path_too_long"
        if collision.startswith("long")
        else "unsafe_target_path",
    )


@pytest.mark.parametrize("target", ["Templates", ".obsidian"])
def test_real_support_namespace_junction_never_writes_or_cleans_caller_directory(
    tmp_path, monkeypatch, target
):
    caller, before = caller_files(tmp_path)
    original = Path.mkdir
    reached = []

    def redirect_parent(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if staged_relative(path) == target and not reached:
            assert list(path.iterdir()) == []
            path.rmdir()
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(path), str(caller)],
                check=True,
                capture_output=True,
            )
            reached.append(path)
        return result

    with BrzSourceModule().open(mixed_archive(tmp_path / "source.brz")) as session:
        artifacts = artifacts_for(session)
        monkeypatch.setattr(Path, "mkdir", redirect_parent)
        with pytest.raises(MigrationRefused) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert len(reached) == 1
    assert error.value.issues[0].code == "unsafe_target_path"
    cleanup = error.value.issues[-1]
    assert cleanup.code == "cleanup_failure"
    owned = Path(cleanup.leftover_path)
    assert owned.parent == tmp_path and owned.name.startswith(".brz2obsidian-")
    assert reached[0].parent == owned
    assert not (tmp_path / "vault").exists() and inventory(caller) == before
    reached[
        0
    ].rmdir()  # Remove only our exact junction, then the checked owned staging.
    shutil.rmtree(owned)
    assert list(tmp_path.glob(".brz2obsidian-*")) == [] and inventory(caller) == before


@pytest.mark.parametrize("empty", [False, True])
def test_native_support_rich_commit_races_preserve_late_caller_bytes(
    tmp_path, monkeypatch, empty
):
    destination = tmp_path / "vault"
    if empty:
        destination.mkdir()
    reached = []
    original = Path.rmdir if empty else Path.rename

    def race(path, *args, **kwargs):
        if path == destination if empty else path.name.startswith(".brz2obsidian-"):
            staging = next(tmp_path.glob(".brz2obsidian-*"))
            assert (staging / "Templates/Concept.md").is_file()
            assert (staging / ".obsidian/types.json").is_file()
            reached.append(path)
            if not empty:
                destination.mkdir()
            (destination / "caller.bin").write_bytes(b"late caller\x00\xff")
        return original(path, *args, **kwargs)

    with BrzSourceModule().open(mixed_archive(tmp_path / "source.brz")) as session:
        artifacts = artifacts_for(session)
        monkeypatch.setattr(Path, "rmdir" if empty else "rename", race)
        with pytest.raises(MigrationRefused) as error:
            publish(artifacts, session, destination)
    assert len(reached) == 1 and error.value.issues[0].code == "destination_not_empty"
    assert list(destination.iterdir()) == [destination / "caller.bin"]
    assert (destination / "caller.bin").read_bytes() == b"late caller\x00\xff"
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


@pytest.mark.parametrize("fault", ["short", "read", "open"])
@pytest.mark.parametrize("icon", [3001, 3002])
def test_selected_category_and_override_stream_faults_never_publish(
    tmp_path, fault, icon
):
    caller, before = caller_files(tmp_path)
    reached, streams = [], []

    class StreamControl:
        def __init__(self, stream):
            self.stream, self.started = stream, False

        def read(self, size=-1):
            if self.started:
                if fault == "read":
                    raise OSError("Selected image read failed")
                return b""
            self.started = True
            return self.stream.read(2)

    class SelectedSession(SessionBoundary):
        @contextmanager
        def open_payload(self, key):
            if key != identity(icon):
                with self.session.open_payload(key) as stream:
                    yield stream
                return
            reached.append(key)
            if fault == "open":
                raise OSError("Selected image open failed")
            with self.session.open_payload(key) as stream:
                streams.append(stream)
                yield StreamControl(stream)

    source = mixed_archive(tmp_path / "source.brz")
    original_source = source.read_bytes()
    with (
        BrzSourceModule().open(source) as session,
        pytest.raises(MigrationFailed) as error,
    ):
        publish(artifacts_for(session), SelectedSession(session), tmp_path / "vault")
    assert reached == [identity(icon)] and all(s.closed for s in streams)
    assert source.read_bytes() == original_source
    failed_safely(
        tmp_path,
        caller,
        before,
        error,
        "payload_integrity_failure" if fault == "short" else "write_failure",
    )


def test_new_icon_stream_revocation_and_teardown_close_failures_are_distinct(
    tmp_path, monkeypatch
):
    import zipfile

    source = mixed_archive(tmp_path / "source.brz")
    contexts, streams = [], []
    original = zipfile.ZipExtFile.close
    reached = []

    def close_failure(stream):
        original(stream)
        if stream.name in {s.name for s in streams} and not reached:
            reached.append(stream)
            raise OSError("Selected icon close failed")

    with (
        pytest.raises(MigrationFailed) as error,
        BrzSourceModule().open(source) as session,
    ):
        durable = session.snapshot
        for icon in (3001, 3002):
            manager = session.open_payload(identity(icon))
            contexts.append(manager)
            streams.append(manager.__enter__())
        assert streams[0].read(2) == CATEGORY_ICON[:2]
        monkeypatch.setattr(zipfile.ZipExtFile, "close", close_failure)
    assert len(reached) == 1 and all(s.closed for s in streams)
    assert error.value.issues[0].code == "session_teardown_failure"
    assert len(durable.classification_assignments) == 3
    with pytest.raises(ValueError):
        streams[0].read()
    monkeypatch.setattr(zipfile.ZipExtFile, "close", original)
    for manager in contexts:
        manager.__exit__(None, None, None)


@pytest.mark.parametrize(
    "target",
    [
        "Templates/Concept.md",
        "Templates/Bases/Members.base",
        ".obsidian/templates.json",
    ],
)
@pytest.mark.parametrize("fault", ["omit", "missing", "duplicate", "count"])
def test_support_obligations_are_checked_before_staging(tmp_path, target, fault):
    caller, before = caller_files(tmp_path)
    with BrzSourceModule().open(mixed_archive(tmp_path / "source.brz")) as session:
        artifacts = artifacts_for(session)
        supports = artifacts.support_artifacts
        selected = next(a for a in supports if a.relative_path == target)
        if fault == "omit":
            supports = tuple(a for a in supports if a != selected)
        elif fault == "missing":
            supports = tuple(
                a.model_copy(update={"relative_path": "Templates/absent.md"})
                if a == selected
                else a
                for a in supports
            )
        elif fault == "duplicate":
            supports += (selected,)
        counts = (
            artifacts.counts.model_copy(update={"planned_support_files": 999})
            if fault == "count"
            else artifacts.counts
        )
        with pytest.raises(MigrationRefused) as error:
            publish(
                artifacts.model_copy(
                    update={"support_artifacts": supports, "counts": counts}
                ),
                session,
                tmp_path / "vault",
            )
    failed_safely(tmp_path, caller, before, error, "invalid_source")


@pytest.mark.parametrize("target", SUPPORT_TARGETS)
def test_bad_generated_support_digest_is_verified_against_actual_bytes(
    tmp_path, target
):
    caller, before = caller_files(tmp_path)
    with BrzSourceModule().open(mixed_archive(tmp_path / "source.brz")) as session:
        artifacts = artifacts_for(session)
        generated = tuple(
            g.model_copy(update={"sha256": "0" * 64})
            if g.relative_path == target
            else g
            for g in artifacts.generated_files
        )
        assert any(
            g.relative_path == target and g.sha256 == "0" * 64 for g in generated
        )
        with pytest.raises(MigrationFailed) as error:
            publish(
                artifacts.model_copy(update={"generated_files": generated}),
                session,
                tmp_path / "vault",
            )
    failed_safely(tmp_path, caller, before, error, "payload_integrity_failure")


@pytest.mark.parametrize("icon", [3001, 3002])
def test_bad_category_or_override_copy_digest_preserves_source_and_caller(
    tmp_path, icon
):
    caller, before = caller_files(tmp_path)
    source = mixed_archive(tmp_path / "source.brz")
    source_before = source.read_bytes()
    with BrzSourceModule().open(source) as session:
        artifacts = artifacts_for(session)
        copies = tuple(
            c.model_copy(update={"expected_sha256": "0" * 64})
            if c.asset_id == identity(icon)
            else c
            for c in artifacts.copies
        )
        assert any(
            c.asset_id == identity(icon) and c.expected_sha256 == "0" * 64
            for c in copies
        )
        with pytest.raises(MigrationFailed) as error:
            publish(
                artifacts.model_copy(update={"copies": copies}),
                session,
                tmp_path / "vault",
            )
    assert source.read_bytes() == source_before
    failed_safely(tmp_path, caller, before, error, "payload_integrity_failure")


def test_selected_support_failure_and_cleanup_denial_report_exact_owned_leftover(
    tmp_path, monkeypatch
):
    caller, before = caller_files(tmp_path)
    original_open, original_remove = Path.open, shutil.rmtree
    reached = []

    def write_failure(path, mode="r", *args, **kwargs):
        if mode == "xb" and staged_relative(path) == "Templates/Concept.md":
            reached.append(path)
            with original_open(path, mode, *args, **kwargs) as stream:
                stream.write(b"partial")
            raise OSError("Selected full-template write denied")
        return original_open(path, mode, *args, **kwargs)

    def cleanup_failure(path, *args, **kwargs):
        raise PermissionError("Owned staging cleanup denied")

    with BrzSourceModule().open(mixed_archive(tmp_path / "source.brz")) as session:
        artifacts = artifacts_for(session)
        monkeypatch.setattr(Path, "open", write_failure)
        monkeypatch.setattr(shutil, "rmtree", cleanup_failure)
        with pytest.raises(MigrationFailed) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert len(reached) == 1
    assert [i.code for i in error.value.issues] == ["write_failure", "cleanup_failure"]
    owned = Path(error.value.issues[-1].leftover_path)
    assert owned.parent == tmp_path and owned.name.startswith(".brz2obsidian-")
    assert reached[0].relative_to(owned).as_posix() == "Templates/Concept.md"
    assert reached[0].read_bytes() == b"partial"
    assert list(tmp_path.glob(".brz2obsidian-*")) == [owned]
    assert not (tmp_path / "vault").exists() and inventory(caller) == before
    monkeypatch.setattr(shutil, "rmtree", original_remove)
    original_remove(owned)
    assert inventory(caller) == before
