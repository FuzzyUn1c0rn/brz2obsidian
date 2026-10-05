import shutil
from datetime import date

import pytest
from pydantic import ValidationError

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.contracts import (
    CalendarDates,
    DeclaredAppearance,
    IconSnapshot,
    Item,
    MigrationFailed,
    MigrationRefused,
    RunMetadata,
    RunResult,
    VideoPresentation,
)
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import render
from brz2obsidian.publication import publish
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from tests.application.test_minimal_workflow import PROPERTIES, make_archive

METADATA = RunMetadata(
    converter_version="0.1.0",
    renderer_version="2",
    run_id="test-run",
    run_time="2026-10-03T00:00:00+00:00",
    obsidian_version="1.13.7",
    bookmark_time=1790985600000,
)


def test_public_modules_compose_without_workflow_and_verify_full_manifest(tmp_path):
    source = make_archive(tmp_path / "brain.brz")
    with BrzSourceModule().open(source) as session:
        checked = analyze(session.snapshot, BRZ_POLICY)
        migration_plan = plan(checked)
        artifacts = render(migration_plan, METADATA)
        receipt = publish(artifacts, session, tmp_path / "vault")
    assert receipt.verified and receipt.published
    assert len(receipt.manifest) == 18
    assert receipt.counts.actual_notes == 1
    assert receipt.counts.actual_assets == 1
    assert receipt.manifest[0].length == len(PROPERTIES) + 85


def test_strict_contracts_reject_coercion_mutation_and_unknown_fields(tmp_path):
    source = make_archive(tmp_path / "brain.brz")
    with BrzSourceModule().open(source) as session:
        item = session.snapshot.items[0]
        assert isinstance(session.snapshot.items, tuple)
        with pytest.raises(ValidationError):
            item.title = "changed"
        with pytest.raises(ValidationError):
            Item(**(item.model_dump() | {"key": 42}))
        with pytest.raises(ValidationError):
            Item(**(item.model_dump() | {"new_field": "unknown"}))
        with pytest.raises(ValidationError):
            Item(**(item.model_dump() | {"document_ids": list(item.document_ids)}))
    result = default_workflow().inspect(source)
    assert (
        RunResult.model_validate_json(result.model_dump_json(by_alias=True)) == result
    )


def test_optional_version_two_facts_are_strict_immutable_durable_values():
    appearance = DeclaredAppearance(
        icon_asset_id="image:opaque", foreground_color="#AABBCC"
    )
    dates = CalendarDates(created=date(2026, 10, 4))
    video = VideoPresentation(
        provider="youtube",
        embed_uri="https://www.youtube.com/embed/example",
        start_seconds=18,
    )
    snapshot = IconSnapshot(
        item_key="item:opaque",
        appearance_category_key="category:opaque",
        effective_icon_asset_id="image:opaque",
    )
    for value in (appearance, dates, video, snapshot):
        assert type(value).model_validate_json(value.model_dump_json()) == value
        with pytest.raises(ValidationError):
            type(value)(**(value.model_dump() | {"unknown": "unreviewed"}))
    with pytest.raises(ValidationError):
        dates.created = date(2026, 10, 5)
    with pytest.raises(ValidationError):
        CalendarDates(created="2026-10-04")
    with pytest.raises(ValidationError):
        DeclaredAppearance(foreground_color=-1)
    with pytest.raises(ValidationError):
        VideoPresentation(provider="youtube", embed_uri="url", start_seconds=-1)


def test_public_renderer_requires_explicit_version_two_metadata(tmp_path):
    with BrzSourceModule().open(make_archive(tmp_path / "source.brz")) as session:
        migration = plan(analyze(session.snapshot, BRZ_POLICY))
    with pytest.raises(MigrationRefused) as refused:
        render(migration, METADATA.model_copy(update={"renderer_version": "1"}))
    assert refused.value.issues[0].code == "unsupported_format"


def test_public_publisher_refuses_unaccounted_support_obligations(tmp_path):
    with BrzSourceModule().open(make_archive(tmp_path / "source.brz")) as session:
        artifacts = render(plan(analyze(session.snapshot, BRZ_POLICY)), METADATA)
        support = artifacts.support_artifacts[0].model_copy(
            update={"relative_path": "Missing support.md"}
        )
        artifacts = artifacts.model_copy(
            update={"support_artifacts": (support,) + artifacts.support_artifacts[1:]}
        )
        with pytest.raises(MigrationRefused):
            publish(artifacts, session, tmp_path / "vault")
    assert not (tmp_path / "vault").exists()


def test_bad_copy_digest_prevents_publication_and_cleans_only_owned_staging(tmp_path):
    source = make_archive(tmp_path / "brain.brz")
    caller_file = tmp_path / "caller-owned.txt"
    caller_file.write_text("preserve me")
    with BrzSourceModule().open(source) as session:
        artifacts = render(plan(analyze(session.snapshot, BRZ_POLICY)), METADATA)
        bad_copy = artifacts.copies[0].model_copy(update={"expected_sha256": "0" * 64})
        artifacts = artifacts.model_copy(update={"copies": (bad_copy,)})
        with pytest.raises(MigrationFailed) as error:
            publish(artifacts, session, tmp_path / "vault")
    assert error.value.issues[0].code == "payload_integrity_failure"
    assert not (tmp_path / "vault").exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []
    assert caller_file.read_text() == "preserve me"


def test_cleanup_failure_reports_the_actual_owned_leftover(tmp_path, monkeypatch):
    source = make_archive(tmp_path / "brain.brz")
    original_rmtree = shutil.rmtree

    def cleanup_io_failure(path, *args, **kwargs):
        raise PermissionError("OS denied staging cleanup")

    with BrzSourceModule().open(source) as session:
        artifacts = render(plan(analyze(session.snapshot, BRZ_POLICY)), METADATA)
        bad_copy = artifacts.copies[0].model_copy(update={"expected_sha256": "0" * 64})
        artifacts = artifacts.model_copy(update={"copies": (bad_copy,)})
        monkeypatch.setattr(shutil, "rmtree", cleanup_io_failure)
        with pytest.raises(MigrationFailed) as error:
            publish(artifacts, session, tmp_path / "vault")
    cleanup = error.value.issues[-1]
    assert cleanup.code == "cleanup_failure"
    leftovers = list(tmp_path.glob(".brz2obsidian-*"))
    assert len(leftovers) == 1
    assert str(leftovers[0]) == cleanup.leftover_path
    monkeypatch.setattr(shutil, "rmtree", original_rmtree)
    original_rmtree(leftovers[0])
