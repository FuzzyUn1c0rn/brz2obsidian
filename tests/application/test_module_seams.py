import shutil

import pytest
from pydantic import ValidationError

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.contracts import Item, MigrationFailed, RunMetadata, RunResult
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import render
from brz2obsidian.publication import publish
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from tests.application.test_minimal_workflow import make_archive

METADATA = RunMetadata(
    converter_version="0.1.0",
    renderer_version="1",
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
    assert len(receipt.manifest) == 6
    assert receipt.counts.actual_notes == 1
    assert receipt.counts.actual_assets == 1
    assert receipt.manifest[0].length == 33


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
