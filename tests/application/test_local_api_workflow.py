import json

import pytest

from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.sources.thebrain.local_api import LocalApiConfig, LocalApiSourceRef
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, api_server


def test_complete_graph_is_published_as_navigation_classification_and_declared_metadata(
    tmp_path,
):
    from tests.support.local_api_graph import (
        DEFINITION,
        EXPECTED_RELATIONSHIPS,
        TAG,
        TYPE_LINK,
        CompleteGraphApi,
    )

    with api_server(CompleteGraphApi()) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "clean", inspected.issues
        assert inspected.counts.source_items == 9
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "clean", result.issues
    assert result.receipt.verified
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert {
        (r["key"], r["kind"], r["item_a"], r["item_b"]) for r in record["relationships"]
    } == EXPECTED_RELATIONSHIPS
    assert [
        (a["relationship_key"], a["definition_key"], a["item_key"])
        for a in record["classification_assignments"]
    ] == [(TYPE_LINK, DEFINITION, HOME)]
    targets = {t["item_key"]: t for t in record["item_targets"]}
    assert targets[HOME]["declared_appearance"] == {
        "foreground_color": "#123AbC",
        "background_color": None,
        "icon_asset_id": None,
    }
    assert targets[DEFINITION]["declared_appearance"] == {
        "foreground_color": "#6070ff",
        "background_color": "#ffe050",
        "icon_asset_id": None,
    }
    assert targets[HOME]["calendar_dates"] == {
        "created": "2026-01-01",
        "updated": "2026-12-31",
    }
    assert targets[HOME]["icon_snapshot"]["appearance_category_key"] == DEFINITION
    assert targets[HOME]["icon_snapshot"]["effective_icon_asset_id"] is None
    note = (tmp_path / "vault/Home — Entry.md").read_text(encoding="utf-8")
    for expected in (
        "Categories/Definition",
        "created: 2026-01-01",
        "updated: 2026-12-31",
        "Source-tag",
        "Alone",
        "Arrow child",
        "Forward one way",
        "Reverse one way",
        "Plain reverse arrow",
        "Peer",
    ):
        assert expected in note
    assert any(
        t["tag_key"] == TAG and t["item_key"] == HOME for t in record["tag_memberships"]
    )
    assert "CANARY" not in json.dumps(record)


def test_metadata_only_home_and_disconnected_item_use_real_workflow(tmp_path):
    with api_server() as (api, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        reference = LocalApiSourceRef(BRAIN)
        inspected = workflow.inspect(reference)
        assert inspected.outcome == "clean", inspected.issues
        assert inspected.counts.source_items == 2
        assert inspected.counts.planned_notes == 1
        converted = workflow.convert(reference, tmp_path / "vault")
    assert converted.outcome == "clean", converted.issues
    assert converted.receipt.verified and converted.counts.actual_notes == 1
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert record["source_identity"]["source_id"] == BRAIN
    assert {t["item_key"]: t["created"] for t in record["item_targets"]} == {
        HOME: True,
        ALONE: False,
    }
    assert "# Entry\n" in (tmp_path / "vault/Home — Entry.md").read_text(
        encoding="utf-8"
    )
    assert KEY not in json.dumps(record)
    acquisition = record["run_metadata"]["source_acquisition"]
    assert acquisition["audit"]["atomic"] is False
    assert acquisition["audit"]["started_at"] <= acquisition["audit"]["finished_at"]
    assert len(acquisition["integrity_sha256"]) == 64
    assert acquisition["audit"]["requests"][0]["operation"] == "brain"
    assert acquisition["audit"]["requests"][1]["operation"] == "brain"
    assert acquisition["audit"]["requests"][1]["subject_id"] is None
    assert acquisition["audit"]["requests"][-1]["operation"] == "statistics"
    assert all(
        set(request)
        == {
            "sequence",
            "operation",
            "brain_id",
            "subject_id",
            "status",
            "outcome",
            "started_at",
            "finished_at",
            "actual_length",
        }
        for request in acquisition["audit"]["requests"]
    )
    from brz2obsidian.contracts import MigrationFailed

    with pytest.raises(MigrationFailed):
        workflow.metadata_factory()
    searches = [
        query for path, query, _ in api.requests if path.startswith("/api/search/")
    ]
    assert all(
        q["queryText"] == ["*"] and q["onlySearchThoughtNames"] == ["false"]
        for q in searches
    )


@pytest.mark.parametrize("with_payload", [False, True])
def test_published_receipt_survives_safe_capture_cleanup_failure(
    tmp_path, monkeypatch, with_payload
):
    import shutil
    import tempfile

    captures = tmp_path / "captures"
    captures.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(captures))
    original = shutil.rmtree

    def cannot_remove_capture(path, *args, **kwargs):
        # Fail the frozen capture teardown after publication; acquisition
        # staging is a separate earlier lifetime and has no manifest.
        if (path / "manifest.json").is_file():
            raise OSError("HEADER_CANARY SERVICE_TOKEN_CANARY")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", cannot_remove_capture)
    from tests.support.local_api import MetadataApi
    from tests.support.local_api_payloads import RAW_NOTE, PayloadApi

    with api_server(PayloadApi() if with_payload else MetadataApi()) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    if with_payload:
        assert (
            tmp_path / "vault/Attachments/22222222/Notes.md.original"
        ).read_bytes() == RAW_NOTE
    assert result.outcome == "failed"
    assert result.receipt.published and result.receipt.verified
    assert (tmp_path / "vault/migration-record.json").is_file()
    assert {issue.code for issue in result.issues} >= {
        "api_capture_cleanup_failed",
        "publication_occurred",
    }
    assert "CANARY" not in result.model_dump_json()
    from brz2obsidian.contracts import MigrationFailed

    with pytest.raises(MigrationFailed):
        workflow.metadata_factory()
    # This injected filesystem failure leaves only test-owned captures; release
    # them through the external filesystem seam after the failure observation.
    leftovers = list(captures.iterdir())
    assert len(leftovers) == 1
    original(leftovers[0])


def test_metadata_context_is_nested_and_concurrent_and_never_crosses_closed_sessions(
    tmp_path,
):
    from concurrent.futures import ThreadPoolExecutor

    from brz2obsidian.contracts import MigrationFailed

    with api_server() as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        module = workflow.binding.source
        with module.open(LocalApiSourceRef(BRAIN)) as first:
            initial = workflow.metadata_factory().source_acquisition
            assert initial == first.acquisition
            with module.open(LocalApiSourceRef(BRAIN)) as second:
                assert (
                    workflow.metadata_factory().source_acquisition == second.acquisition
                )
                assert second.acquisition != initial
            assert workflow.metadata_factory().source_acquisition == initial
        with pytest.raises(MigrationFailed):
            workflow.metadata_factory()
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(
                workers.map(
                    lambda index: workflow.convert(
                        LocalApiSourceRef(BRAIN), tmp_path / str(index)
                    ),
                    range(2),
                )
            )
        assert all(result.outcome == "clean" for result in results)
        records = [
            json.loads((tmp_path / str(index) / "migration-record.json").read_bytes())
            for index in range(2)
        ]
        assert records[0]["source_identity"] == records[1]["source_identity"]
        assert (
            records[0]["run_metadata"]["source_acquisition"]
            != records[1]["run_metadata"]["source_acquisition"]
        )
        with pytest.raises(MigrationFailed):
            workflow.metadata_factory()


@pytest.mark.parametrize("failure", ["provider", "capture_write"])
def test_external_provider_and_filesystem_errors_are_typed_before_workflow(
    tmp_path, monkeypatch, failure
):
    import tempfile
    from pathlib import Path

    captures = tmp_path / "captures"
    captures.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(captures))

    def broken_provider():
        raise RuntimeError("KEY_CANARY SERVICE_TOKEN_CANARY")

    if failure == "capture_write":
        original = Path.write_bytes

        def broken_write(path, value):
            if path.name == "metadata.json":
                raise OSError("KEY_CANARY SERVICE_TOKEN_CANARY")
            return original(path, value)

        monkeypatch.setattr(Path, "write_bytes", broken_write)
    with api_server() as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address),
            credentials=broken_provider if failure == "provider" else lambda: KEY,
        )
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "failed"
    assert result.receipt is None
    assert "CANARY" not in result.model_dump_json()
    assert list(captures.iterdir()) == []


def test_public_definition_and_tag_metadata_use_the_real_planner_and_publisher(
    tmp_path,
):
    from tests.support.local_api import MetadataApi, thought

    api = MetadataApi()
    definition, tag = (
        "44444444-4444-4444-8444-444444444444",
        "55555555-5555-4555-8555-555555555555",
    )
    api.thoughts[definition] = thought(definition, "Definition") | {"kind": 2}
    api.thoughts[tag] = thought(tag, "Tag") | {"kind": 4}
    api.types = [api.thoughts[definition]]
    api.tags = [api.thoughts[tag]]
    with api_server(api) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "clean", inspected.issues
        assert inspected.counts.source_items == 4
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "clean", result.issues
    assert result.receipt.verified
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert {target["item_key"] for target in record["item_targets"]} == {
        HOME,
        ALONE,
        definition,
        tag,
    }


def test_missing_api_txt_warns_and_publishes_preserved_pdf_with_neutral_notice(
    tmp_path,
):
    from tests.support.local_api_payloads import PDF, PDF_BYTES, TXT, MissingTxtPdfApi

    with api_server(MissingTxtPdfApi()) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "warnings", inspected.issues
        (issue,) = inspected.issues
        assert (issue.code, issue.rule_id, issue.affected) == (
            "approved_source_gap",
            "local-api.missing-txt-pdf.v1",
            (TXT,),
        )
        destination = tmp_path / "gap-vault"
        result = workflow.convert(LocalApiSourceRef(BRAIN), destination)
        assert result.outcome == "warnings", result.issues
        assert result.receipt.published and result.receipt.verified
        assert (
            destination / "Attachments/22222222/different-purpose.pdf"
        ).read_bytes() == PDF_BYTES
        assert not list(destination.rglob("*.txt"))
        note = (destination / "Home — Entry.md").read_text(encoding="utf-8")
        assert "Absent source file: authored.txt" in note
        report = (destination / "Migration report.md").read_text(encoding="utf-8")
        assert "Conversion used captured source material only." in report
        assert "convert the updated source into a fresh vault" in report
        assert "archived material" not in report
        assert "Declaration and unavailable bytes:" in report
        assert "physical absence" not in report
        assert TXT in report and PDF in report
        assert "CANARY" not in result.model_dump_json() + report + note
