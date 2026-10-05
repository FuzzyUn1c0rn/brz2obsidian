"""Durable integrated receipts and opaque source/session failures."""

import json
from contextlib import contextmanager

import pytest

from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.publication import FilesystemPublisher
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from tests.application.test_alternate_source import workflow
from tests.application.test_failure_protection import (
    AfterCommitFailurePublisher,
    FailingPublisher,
    TeardownFailureSource,
)
from tests.support.folio_source import FOLIO_POLICY, FolioSourceModule
from tests.support.paired_v2_sources import TYPE_IMAGE, paired_v2_sources
from tests.support.v2_collection import SUPPORT_PATHS, inventory, mixed_archive


@pytest.mark.parametrize("post_commit", [False, True])
def test_integrated_failure_retains_verified_receipt_for_every_actual_file(
    tmp_path, post_commit
):
    from brz2obsidian.application import SourceModuleBinding, Workflow
    from brz2obsidian.obsidian import ObsidianRenderer

    source = mixed_archive(tmp_path / "source.brz")
    operation = Workflow(
        SourceModuleBinding(
            BrzSourceModule() if post_commit else TeardownFailureSource(), BRZ_POLICY
        ),
        ObsidianRenderer(),
        AfterCommitFailurePublisher() if post_commit else FilesystemPublisher(),
    )
    result = operation.convert(source, tmp_path / "vault")
    assert (
        result.outcome == "failed"
        and result.receipt.verified
        and result.receipt.published
    )
    assert [i.code for i in result.issues] == [
        "approved_source_gap",
        "after_commit_failure" if post_commit else "session_teardown_failure",
        "publication_occurred",
    ]
    assert (
        result.counts.actual_notes,
        result.counts.actual_assets,
        result.counts.actual_files,
        result.counts.actual_category_notes,
        result.counts.actual_support_files,
    ) == (7, 8, 34, 1, 19)
    actual = inventory(tmp_path / "vault")
    assert {
        f.relative_path: (f.length, f.sha256) for f in result.receipt.manifest
    } == actual
    assert SUPPORT_PATHS <= actual.keys()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


def test_integrated_material_error_and_teardown_failure_leave_actual_counts_unavailable(
    tmp_path,
):
    from brz2obsidian.application import SourceModuleBinding, Workflow
    from brz2obsidian.obsidian import ObsidianRenderer

    operation = Workflow(
        SourceModuleBinding(TeardownFailureSource(), BRZ_POLICY),
        ObsidianRenderer(),
        FailingPublisher(),
    )
    result = operation.convert(
        mixed_archive(tmp_path / "source.brz"), tmp_path / "vault"
    )
    assert result.outcome == "failed" and result.receipt is None
    assert [i.code for i in result.issues] == [
        "approved_source_gap",
        "material_failure",
        "session_teardown_failure",
    ]
    assert (
        result.counts.planned_notes == 7 and result.counts.planned_support_files == 19
    )
    assert (
        result.counts.actual_files
        is result.counts.actual_support_files
        is result.counts.actual_category_notes
        is None
    )
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize(
    "fault,code,outcome",
    [
        ("open", "write_failure", "failed"),
        ("read", "write_failure", "failed"),
        ("short", "payload_integrity_failure", "failed"),
        ("mutate", "source_changed", "refused"),
    ],
)
def test_opaque_rich_source_faults_reach_category_icon_and_preserve_caller(
    tmp_path, fault, code, outcome
):
    _, source = paired_v2_sources(tmp_path)
    caller = tmp_path / "caller.bin"
    caller.write_bytes(b"caller\x00\xff")
    attempts, streams = [], []

    class StreamControl:
        def __init__(self, stream):
            self.stream, self.started = stream, False

        def read(self, size=-1):
            if self.started:
                if fault == "read":
                    raise OSError("Opaque category icon became unreadable")
                return b""
            self.started = True
            return self.stream.read(2)

    class SelectedSource(FolioSourceModule):
        @contextmanager
        def open(self, path):
            with super().open(path) as session:
                original = session.open_payload

                @contextmanager
                def selected(key):
                    if key != "asset:107:category-image":
                        with original(key) as stream:
                            yield stream
                        return
                    attempts.append(key)
                    if fault == "open":
                        raise OSError("Opaque category icon open failed")
                    with original(key) as stream:
                        streams.append(stream)
                        if fault == "mutate":
                            source.write_bytes(source.read_bytes() + b"\n")
                        yield (
                            StreamControl(stream)
                            if fault in {"read", "short"}
                            else stream
                        )

                session.open_payload = selected
                yield session

    result = workflow(SelectedSource(), FOLIO_POLICY).convert(
        source, tmp_path / "vault"
    )
    assert attempts == ["asset:107:category-image"] and all(s.closed for s in streams)
    assert result.outcome == outcome and result.issues[0].code == code
    assert (
        result.counts.planned_notes == 5 and result.counts.planned_support_files == 19
    )
    assert result.counts.actual_notes is result.counts.actual_support_files is None
    assert result.receipt is None and not (tmp_path / "vault").exists()
    assert (source.parent / "payload-107").read_bytes() == TYPE_IMAGE
    assert (
        caller.read_bytes() == b"caller\x00\xff"
        and list(tmp_path.glob(".brz2obsidian-*")) == []
    )


def test_opaque_rich_teardown_failure_retains_entire_actual_inventory(tmp_path):
    _, source = paired_v2_sources(tmp_path)
    result = workflow(FolioSourceModule(teardown_failure=True), FOLIO_POLICY).convert(
        source, tmp_path / "vault"
    )
    assert (
        result.outcome == "failed"
        and result.receipt.verified
        and result.receipt.published
    )
    assert [i.code for i in result.issues] == [
        "session_teardown_failure",
        "publication_occurred",
    ]
    assert (
        result.counts.actual_notes,
        result.counts.actual_assets,
        result.counts.actual_support_files,
        result.counts.actual_category_notes,
    ) == (5, 7, 19, 1)
    actual = inventory(tmp_path / "vault")
    assert {
        f.relative_path: (f.length, f.sha256) for f in result.receipt.manifest
    } == actual
    assert SUPPORT_PATHS <= actual.keys()


@pytest.mark.parametrize("mutation", ["classification", "calendar", "icon"])
def test_opaque_v2_session_revokes_icon_stream_and_detects_changed_own_facts(
    tmp_path, mutation
):
    _, source = paired_v2_sources(tmp_path)
    module = FolioSourceModule()
    with module.open(source) as session:
        durable = session.snapshot
        manager = session.open_payload("asset:107:category-image")
        stream = manager.__enter__()
        assert stream.read(2) == TYPE_IMAGE[:2]
    assert stream.closed
    with pytest.raises(ValueError):
        stream.read()
    with pytest.raises(OSError, match="closed"):
        session.verify_consistency()
    with pytest.raises(OSError, match="closed"):
        manager.__exit__(None, None, None)
    assert len(durable.classification_assignments) == 2
    with module.open(source) as current:
        if mutation == "icon":
            (source.parent / "payload-107").write_bytes(b"changed icon")
        else:
            data = json.loads(source.read_bytes())
            if mutation == "classification":
                data["assignments"][0]["item_key"] = "orphan:alone"
            else:
                data["entries"][3]["calendar"]["created"] = [2030, 1, 2]
            source.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(MigrationRefused) as changed:
            current.verify_consistency()
        assert changed.value.issues[0].code == "source_changed"
