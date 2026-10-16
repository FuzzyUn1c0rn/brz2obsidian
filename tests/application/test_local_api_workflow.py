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


@pytest.mark.parametrize("case", ["tags", "zero-tags"])
def test_standard_workflow_preserves_mixed_scope_baseline(tmp_path, case):
    from tests.local_acceptance.api_checker import audit_baseline, check_api_vault
    from tests.local_acceptance.api_scope_inputs import (
        mixed_expectations,
        mixed_source_packet,
    )
    from tests.local_acceptance.test_api_scope_v3 import scope_baseline
    from tests.support.local_api_packet import RawPacketApi

    baseline = scope_baseline(tmp_path / "independent-source", case)
    audited = audit_baseline(baseline, profile_version="3")
    literal = mixed_expectations()
    packet = mixed_source_packet(case)
    api = RawPacketApi.from_source_packet(packet)
    reference = LocalApiSourceRef(baseline.json(baseline.data["brain"])["id"])
    destination = tmp_path / "actual-vault"
    with api_server(api) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address, include_pins=False), credentials=lambda: KEY
        )
        inspected = workflow.inspect(reference)
        assert inspected.outcome == "warnings", inspected.issues
        converted = workflow.convert(reference, destination)
    assert converted.outcome == "warnings", converted.issues
    assert converted.receipt.published and converted.receipt.verified
    baseline.verify()
    check_api_vault(baseline, destination, profile_version="3")
    record = json.loads((destination / "migration-record.json").read_bytes())
    targets = {row["item_key"]: row for row in record["item_targets"]}
    assert set(targets) == set(baseline.data["scope"]["thought_ids"])
    for key, row in targets.items():
        assert row["created"] is literal["created"][key]
    documents = {
        doc["key"]: (row, doc)
        for row in record["item_targets"]
        for doc in row["documents"]
    }
    assert "documents" not in record
    for key in audited["retention"]["omitted_original_ids"]:
        row, document = documents[key]
        assert document["original_copy_omitted"] is True
        assert document["original_asset_id"] is None
        assert document["owner_target"] == row["relative_path"]
        if not row["created"]:
            assert not (destination / row["relative_path"]).exists()
    for path in destination.rglob("*"):
        if path.is_file():
            assert all(c.encode() not in path.read_bytes() for c in literal["canaries"])
    ledger = json.loads(packet["files"]["endpoints.json"])
    assert not api.unexpected_requests
    assert {row["path"] for row in api.served}.isdisjoint(ledger["forbidden_routes"])


@pytest.mark.parametrize("excluded", [True, False], ids=["scoped", "identity"])
@pytest.mark.parametrize(
    "profile,image_format", [("1", "webp"), ("2", "png"), ("3", "png")]
)
def test_qualified_raster_workflow_preserves_scope_and_document_obligations(
    tmp_path, monkeypatch, excluded, profile, image_format
):
    import tempfile

    from brz2obsidian.application.workflow import SourceModuleBinding, Workflow
    from brz2obsidian.obsidian import ObsidianRenderer
    from brz2obsidian.publication import FilesystemPublisher
    from brz2obsidian.sources.thebrain.local_api import (
        LOCAL_API_POLICY,
        LOCAL_API_POLICY_V2,
        LocalApiSourceModule,
    )
    from tests.local_acceptance.api_checker import audit_baseline, check_api_vault
    from tests.local_acceptance.api_scope_inputs import (
        identity,
        mixed_expectations,
        raster_scope_packet,
    )
    from tests.local_acceptance.test_api_scope_v3 import raster_scope_baseline
    from tests.support.local_api_packet import RawPacketApi

    baseline = raster_scope_baseline(
        tmp_path / "independent-source",
        excluded=excluded,
        profile_version=profile,
        image_format=image_format,
    )
    audited = audit_baseline(baseline, profile_version=profile)
    packet = raster_scope_packet(
        excluded=excluded, profile_version=profile, image_format=image_format
    )
    api = RawPacketApi.from_source_packet(packet)
    reference = LocalApiSourceRef(baseline.json(baseline.data["brain"])["id"])
    captures = tmp_path / "product-captures"
    captures.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(captures))
    destination = tmp_path / "actual-vault"
    with api_server(api) as (_, address):
        config = LocalApiConfig(api_url=address, include_pins=False)
        if profile == "3":
            workflow = local_api_workflow(config, credentials=lambda: KEY)
        else:
            module = LocalApiSourceModule(
                config, credentials=lambda: KEY, profile_version=profile
            )
            policy = {"1": LOCAL_API_POLICY, "2": LOCAL_API_POLICY_V2}[profile]
            workflow = Workflow(
                SourceModuleBinding(module, policy),
                ObsidianRenderer(),
                FilesystemPublisher(),
            )
            metadata_factory = workflow.metadata_factory
            workflow.metadata_factory = lambda: module.run_metadata(metadata_factory())
        inspected = workflow.inspect(reference)
        assert inspected.outcome == "clean", inspected.issues
        assert inspected.profile_version == profile
        assert inspected.receipt is None
        assert not tuple(captures.iterdir())
        assert not destination.exists()
        converted = workflow.convert(reference, destination)
    assert converted.outcome == "clean", converted.issues
    assert converted.profile_version == profile
    assert converted.receipt.published and converted.receipt.verified
    assert not tuple(captures.iterdir())
    baseline.verify()
    check_api_vault(baseline, destination, profile_version=profile)
    record = json.loads((destination / "migration-record.json").read_bytes())
    assert "documents" not in record
    targets = {row["item_key"]: row for row in record["item_targets"]}
    home = baseline.json(baseline.data["brain"])["homeThoughtId"]
    assert set(targets) == set(baseline.data["scope"]["thought_ids"])
    for key, row in targets.items():
        assert row["created"] is (key == home)
        if not row["created"]:
            assert not (destination / row["relative_path"]).exists()
    documents = {
        document["key"]: document
        for row in targets.values()
        for document in row["documents"]
    }
    assert set(documents) == {identity(201)}
    assert targets[identity(3)]["documents"] == []
    original = documents[identity(201)]
    assert original["original_copy_omitted"] is excluded
    assert original["original_asset_id"] == (None if excluded else identity(201))
    assert (
        original["text_digest"]
        == {
            "png": "e1b8fdf01bd2fa1e0f4f9335360c0c824fdc583f11c2abd6e296035d8bd68522",
            "webp": "5a79c03399a9275e91909e1d510691b25733f23467eababff24ded5dec529772",
        }[image_format]
    )
    assert (
        sorted(row["asset_id"] for row in record["asset_targets"])
        == audited["retention"]["retained_asset_ids"]
    )
    diagnostics = inspected.model_dump_json() + converted.model_dump_json()
    canaries = [*mixed_expectations()["canaries"], KEY]
    assert all(c not in diagnostics for c in canaries)
    for path in destination.rglob("*"):
        if path.is_file():
            assert all(c.encode("utf-8") not in path.read_bytes() for c in canaries)
    assert set(tmp_path.iterdir()) == {
        baseline.manifest_path.parent,
        captures,
        destination,
    }
    ledger = json.loads(packet["files"]["endpoints.json"])
    assert not api.unexpected_requests
    requested = {row["path"] for row in api.served}
    assert requested.isdisjoint(ledger["forbidden_routes"])
    assert not any(
        row["optional"] and row["route"] in requested for row in ledger["routes"]
    )


@pytest.mark.parametrize(
    "case,expected_code",
    [
        ("forgotten-invalid-calendar", None),
        ("relationship-contradictory-repeat", None),
        ("resource-unsupported-type", "api_resource_shape_unsupported"),
        ("external-traversal", "api_resource_shape_unsupported"),
        ("note-unresolved-thought", None),
        ("jpeg-premature-entropy", None),
    ],
)
def test_independent_negative_workflow_refuses_without_publication(
    tmp_path, monkeypatch, case, expected_code
):
    import tempfile

    from tests.local_acceptance.api_scope_inputs import (
        mixed_expectations,
        negative_mixed_source_packet,
    )
    from tests.support.local_api_packet import RawPacketApi

    packet = negative_mixed_source_packet(case)
    ledger = json.loads(packet["files"]["endpoints.json"])
    brain = json.loads(packet["files"][packet["baseline_inputs"]["brain"]])["id"]
    api = RawPacketApi.from_source_packet(packet)
    destination = tmp_path / "actual-vault"
    captures = tmp_path / "product-captures"
    captures.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(captures))
    with api_server(api) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address, include_pins=False), credentials=lambda: KEY
        )
        reference = LocalApiSourceRef(brain)
        inspected = workflow.inspect(reference)
        assert inspected.outcome == "refused", inspected.issues
        assert inspected.receipt is None
        assert not tuple(captures.iterdir())
        assert not destination.exists()
        assert set(tmp_path.iterdir()) == {captures}
        converted = workflow.convert(reference, destination)
    assert converted.outcome == "refused", converted.issues
    assert converted.receipt is None
    assert not destination.exists()
    assert not tuple(captures.iterdir())
    assert set(tmp_path.iterdir()) == {captures}
    if expected_code is not None:
        for result in (inspected, converted):
            assert expected_code in {issue.code for issue in result.issues}
    diagnostic = inspected.model_dump_json() + converted.model_dump_json()
    assert all(c not in diagnostic for c in [*mixed_expectations()["canaries"], KEY])
    assert not api.unexpected_requests
    requested = {row["path"] for row in api.served}
    assert requested.isdisjoint(ledger["forbidden_routes"])
    assert not any(
        row["optional"] and row["route"] in requested for row in ledger["routes"]
    )
