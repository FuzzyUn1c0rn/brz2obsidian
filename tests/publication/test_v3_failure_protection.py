"""Real publication faults reach mixed source-gap notes and image payloads."""

import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest

from brz2obsidian.application import SourceModuleBinding, Workflow
from brz2obsidian.contracts import MigrationFailed, MigrationRefused
from brz2obsidian.obsidian import ObsidianRenderer
from brz2obsidian.publication import FilesystemPublisher, publish
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from tests.application.test_failure_protection import (
    AfterCommitFailurePublisher,
    TeardownFailureSource,
)
from tests.application.test_graph_workflow import identity
from tests.application.test_integrated_v3_workflow import EMPTY
from tests.publication.test_failure_protection import (
    SessionBoundary,
    artifacts_for,
    mutate_complete_staging_on_walk,
)
from tests.publication.test_v2_failure_protection import (
    caller_files,
    failed_safely,
    staged_relative,
)
from tests.support.v2_collection import inventory
from tests.support.v3_collection import mixed_v3_archive

IMAGE_PATH = "Attachments/00000000000000000000000000000003/z-first.png"
TARGETS = (
    EMPTY,
    "Categories/Concept.md",
    IMAGE_PATH,
    "MIGRATION REPORT.md",
    "migration-record.json",
)


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("fault", ["write", "delete", "truncate", "same_length"])
def test_real_v3_write_and_staging_corruption_prevent_partial_acceptance(
    tmp_path, monkeypatch, target, fault
):
    caller, before = caller_files(tmp_path)
    source = mixed_v3_archive(tmp_path / "mixed.brz")
    source_before = source.read_bytes()
    reached = []
    original = Path.open

    def partial_write(path, mode="r", *args, **kwargs):
        if mode == "xb" and staged_relative(path) == target:
            reached.append(path)
            with original(path, mode, *args, **kwargs) as stream:
                stream.write(b"partial")
                stream.flush()
            raise OSError("Controlled mixed artifact partial write")
        return original(path, mode, *args, **kwargs)

    def corrupt(staging):
        path = staging / target
        body = path.read_bytes()
        assert body
        reached.append(path)
        if fault == "delete":
            path.unlink()
            assert not path.exists()
        elif fault == "truncate":
            assert len(body) > 2
            path.write_bytes(body[:2])
            assert path.read_bytes() == body[:2]
        else:
            altered = bytes([body[0] ^ 1]) + body[1:]
            assert len(altered) == len(body) and altered != body
            path.write_bytes(altered)
            assert path.read_bytes() == altered

    with BrzSourceModule().open(source) as session:
        artifacts = artifacts_for(session)
        if fault == "write":
            monkeypatch.setattr(Path, "open", partial_write)
        else:
            staged = mutate_complete_staging_on_walk(
                monkeypatch, tmp_path, artifacts.manifest, corrupt
            )
        with pytest.raises(MigrationFailed) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert len(reached) == 1
    if fault != "write":
        assert len(staged) == 1
    assert source.read_bytes() == source_before
    failed_safely(
        tmp_path,
        caller,
        before,
        error,
        "write_failure" if fault == "write" else "payload_integrity_failure",
    )


@pytest.mark.parametrize("fault", ["open", "read", "short"])
@pytest.mark.parametrize("image", [4010, 4011])
def test_real_owned_fallback_image_stream_failures_preserve_caller(
    tmp_path, image, fault
):
    caller, before = caller_files(tmp_path)
    source = mixed_v3_archive(tmp_path / "mixed.brz")
    source_before = source.read_bytes()
    reached, streams = [], []

    class PartialStream:
        def __init__(self, stream):
            self.stream, self.started = stream, False

        def read(self, size=-1):
            if self.started:
                if fault == "read":
                    raise OSError("Controlled fallback image read failure")
                return b""
            self.started = True
            return self.stream.read(2)

    class SelectedSession(SessionBoundary):
        @contextmanager
        def open_payload(self, key):
            if key != identity(image):
                with self.session.open_payload(key) as stream:
                    yield stream
                return
            reached.append(key)
            if fault == "open":
                raise OSError("Controlled fallback image open failure")
            with self.session.open_payload(key) as stream:
                streams.append(stream)
                yield PartialStream(stream)

    with (
        BrzSourceModule().open(source) as session,
        pytest.raises(MigrationFailed) as error,
    ):
        publish(artifacts_for(session), SelectedSession(session), tmp_path / "vault")
    assert reached == [identity(image)] and all(s.closed for s in streams)
    assert source.read_bytes() == source_before
    failed_safely(
        tmp_path,
        caller,
        before,
        error,
        "payload_integrity_failure" if fault == "short" else "write_failure",
    )


@pytest.mark.parametrize("target", TARGETS)
def test_source_mutation_during_new_artifact_verification_is_rechecked(
    tmp_path, monkeypatch, target
):
    caller, before = caller_files(tmp_path)
    source = mixed_v3_archive(tmp_path / "mixed.brz")
    original = Path.open
    reached = []

    def mutate(path, mode="r", *args, **kwargs):
        if mode == "rb" and staged_relative(path) == target and not reached:
            reached.append(path)
            with original(source, "ab") as stream:
                stream.write(b"controlled source mutation")
        return original(path, mode, *args, **kwargs)

    with BrzSourceModule().open(source) as session:
        artifacts = artifacts_for(session)
        monkeypatch.setattr(Path, "open", mutate)
        with pytest.raises(MigrationRefused) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert len(reached) == 1
    failed_safely(tmp_path, caller, before, error, "source_changed")


@pytest.mark.parametrize("empty", [False, True])
def test_native_commit_races_with_verified_fallback_notes_keep_late_caller_files(
    tmp_path, monkeypatch, empty
):
    destination = tmp_path / "vault"
    if empty:
        destination.mkdir()
    original = Path.rmdir if empty else Path.rename
    reached = []

    def race(path, *args, **kwargs):
        selected = (
            path == destination if empty else path.name.startswith(".brz2obsidian-")
        )
        if selected:
            staging = next(tmp_path.glob(".brz2obsidian-*"))
            assert (staging / IMAGE_PATH).is_file() and (staging / EMPTY).is_file()
            reached.append(path)
            if not empty:
                destination.mkdir()
            (destination / "caller.bin").write_bytes(b"late caller\x00\xff")
        return original(path, *args, **kwargs)

    source = mixed_v3_archive(tmp_path / "mixed.brz")
    source_before = source.read_bytes()
    with BrzSourceModule().open(source) as session:
        artifacts = artifacts_for(session)
        monkeypatch.setattr(Path, "rmdir" if empty else "rename", race)
        with pytest.raises(MigrationRefused) as error:
            publish(artifacts, session, destination)
    assert len(reached) == 1 and error.value.issues[0].code == "destination_not_empty"
    assert list(destination.iterdir()) == [destination / "caller.bin"]
    assert (destination / "caller.bin").read_bytes() == b"late caller\x00\xff"
    assert source.read_bytes() == source_before and not list(
        tmp_path.glob(".brz2obsidian-*")
    )


def test_real_fallback_owner_junction_is_refused_without_touching_caller(
    tmp_path, monkeypatch
):
    caller, before = caller_files(tmp_path)
    owner = "Attachments/00000000000000000000000000000003"
    original = Path.mkdir
    reached = []

    def redirect(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if staged_relative(path) == owner and not reached:
            assert not list(path.iterdir())
            path.rmdir()
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(path), str(caller)],
                check=True,
                capture_output=True,
            )
            reached.append(path)
        return result

    source = mixed_v3_archive(tmp_path / "mixed.brz")
    with BrzSourceModule().open(source) as session:
        artifacts = artifacts_for(session)
        monkeypatch.setattr(Path, "mkdir", redirect)
        with pytest.raises(MigrationRefused) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert len(reached) == 1 and error.value.issues[0].code == "unsafe_target_path"
    assert error.value.issues[-1].code == "cleanup_failure"
    staging = Path(error.value.issues[-1].leftover_path)
    assert staging.parent == tmp_path and staging.name.startswith(".brz2obsidian-")
    assert reached[0].relative_to(staging).as_posix() == owner
    assert inventory(caller) == before and not (tmp_path / "vault").exists()
    reached[0].rmdir()
    shutil.rmtree(staging)
    assert inventory(caller) == before


@pytest.mark.parametrize("later", ["teardown", "post_commit"])
def test_late_workflow_failure_keeps_complete_mixed_verified_receipt(tmp_path, later):
    source = mixed_v3_archive(tmp_path / "mixed.brz")
    before = source.read_bytes()
    source_module = (
        TeardownFailureSource() if later == "teardown" else BrzSourceModule()
    )
    publisher = (
        AfterCommitFailurePublisher()
        if later == "post_commit"
        else FilesystemPublisher()
    )
    workflow = Workflow(
        SourceModuleBinding(source_module, BRZ_POLICY), ObsidianRenderer(), publisher
    )
    result = workflow.convert(source, tmp_path / "vault")
    assert (
        result.outcome == "failed"
        and result.receipt.published
        and result.receipt.verified
    )
    assert result.issues[-1].code == "publication_occurred"
    assert (
        result.counts.actual_generated_embeds == 2 and result.counts.actual_files == 36
    )
    assert result.receipt.counts == result.counts
    assert {
        f.relative_path: (f.length, f.sha256) for f in result.receipt.manifest
    } == inventory(tmp_path / "vault")
    assert source.read_bytes() == before
