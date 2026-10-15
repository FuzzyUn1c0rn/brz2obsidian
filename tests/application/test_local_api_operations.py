"""API GUI operations use the real adapter and HTTP-boundary source fixtures."""

import json
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from brz2obsidian.application.contracts import (
    ApiAcquisitionConfig,
    ApplyResult,
    BrainListResult,
    ConfigureApi,
    ConvertArguments,
    InspectArguments,
    InspectCommand,
    ListBrainsArguments,
    ListBrainsCommand,
    LocalApiSourceSelection,
    SelectSource,
    WorkerRequest,
    WorkerResponse,
)
from brz2obsidian.application.operations import ApplicationSession, Operations
from brz2obsidian.application.protocol import (
    ProtocolFailure,
    decode_request,
    decode_response,
    encode_request,
    encode_response,
)
from brz2obsidian.application.transport import Supervisor
from tests.support.local_api import BRAIN, HOME, KEY, api_server


def test_resource_review_rejects_cross_profile_compatibility_and_changed_payload(
    tmp_path, monkeypatch
):
    from tests.support.local_api_payloads import (
        NOTE,
        RichPayloadApi,
        assert_published_payloads,
    )

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    with api_server(RichPayloadApi(jpeg=True)) as (api, address):
        selection = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        operations = Operations()
        inspected = operations.inspect(selection)
        assert inspected.reviewed is not None
        assert inspected.reviewed.profile_version == "2"
        previous_profile = inspected.reviewed.model_copy(
            update={"profile_version": "1"}
        )
        refused = operations.convert_reviewed(
            selection, tmp_path, "old-profile", previous_profile
        )
        assert refused.status == "conversion_refused"
        assert not (tmp_path / "old-profile").exists()
        api.payloads[NOTE] += b"Changed source bytes"
        changed = operations.convert_reviewed(
            selection, tmp_path, "changed", inspected.reviewed
        )
        assert changed.status == "conversion_refused"
        assert not (tmp_path / "changed").exists()
        inspected = operations.inspect(selection)
        assert inspected.reviewed is not None
        api.payloads[NOTE] = api.payloads[NOTE].removesuffix(b"Changed source bytes")
        inspected = operations.inspect(selection)
        result = operations.convert_reviewed(
            selection, tmp_path, "reviewed", inspected.reviewed
        )
        assert result.publication.receipt_verified
        assert_published_payloads(tmp_path / "reviewed", jpeg=True)


def test_every_effective_config_change_invalidates_review_and_blocks_old_publication(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    changes = {
        "api_url": "http://127.0.0.1:11523/api",
        "search_initial_results": 5001,
        "search_timeout": 301,
        "search_max_response_bytes": 128000001,
        "search_max_results": 6000,
        "request_timeout": 31,
        "max_response_bytes": 16000001,
        "max_requests": 100001,
        "max_traversal_items": 100001,
        "max_total_capture_bytes": 1000000001,
        "max_payload_bytes": 256000001,
        "include_pins": True,
    }
    with api_server() as (api, address):
        original = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        operations = Operations()
        inspected = operations.inspect(original)
        assert inspected.reviewed is not None
        before = len(api.requests)
        for field, changed in changes.items():
            values = original.config.model_dump()
            values[field] = changed
            config = ApiAcquisitionConfig(**values)
            session = ApplicationSession()
            session.dispatch(SelectSource(source_selection=original))
            effect = session.dispatch(InspectCommand()).effects[0]
            session.dispatch(
                ApplyResult(
                    request_id=effect.request.request_id,
                    input_revision=effect.input_revision,
                    result=inspected,
                    process_status=0,
                )
            )
            assert session.snapshot.reviewed is not None
            state = session.dispatch(ConfigureApi(config=config)).snapshot
            assert state.reviewed is None and state.source_selection is None
            assert state.review_required
            result = operations.convert_reviewed(
                LocalApiSourceSelection(brain_id=BRAIN, config=config),
                tmp_path,
                field,
                inspected.reviewed,
            )
            assert result.findings[0].code == "review_required"
            assert not (tmp_path / field).exists()
        assert len(api.requests) == before


def test_accessible_brains_keep_duplicate_names_and_exact_stable_ids(monkeypatch):
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    other = "44444444-4444-4444-8444-444444444444"
    with api_server() as (api, address):
        api.overrides["/api/brains"] = (
            200,
            [
                {"id": BRAIN, "name": "Duplicate", "homeThoughtId": HOME},
                {"id": other, "name": "Duplicate", "homeThoughtId": HOME},
            ],
        )
        result = Operations().list_brains(ApiAcquisitionConfig(api_url=address))
    assert result.status == "brains_listed"
    assert [(b.name, b.brain_id) for b in result.brains] == [
        ("Duplicate", BRAIN),
        ("Duplicate", other),
    ]
    assert KEY not in result.model_dump_json()


def test_brain_refresh_runs_real_worker_and_never_substitutes_another_brain(
    monkeypatch,
):
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    with api_server() as (api, address):
        config = ApiAcquisitionConfig(api_url=address)
        session = ApplicationSession()
        session.dispatch(ConfigureApi(config=config))
        effect = session.dispatch(ListBrainsCommand()).effects[0]
        assert session.snapshot.busy_operation == "list_brains"
        terminal = Supervisor(
            Path(sys.executable), Path(__file__).parents[2] / "src"
        ).run(effect.request)
        assert terminal.phase == "completed"
        session.dispatch(
            ApplyResult(
                request_id=effect.request.request_id,
                input_revision=effect.input_revision,
                result=terminal.response.result,
                process_status=terminal.process_status,
            )
        )
        assert session.snapshot.brains[0].brain_id == BRAIN
        assert session.snapshot.source_selection is None
        selected = LocalApiSourceSelection(brain_id=BRAIN, config=config)
        session.dispatch(SelectSource(source_selection=selected))
        api.overrides["/api/brains"] = (200, [])
        effect = session.dispatch(ListBrainsCommand()).effects[0]
        terminal = Supervisor(
            Path(sys.executable), Path(__file__).parents[2] / "src"
        ).run(effect.request)
        session.dispatch(
            ApplyResult(
                request_id=effect.request.request_id,
                input_revision=effect.input_revision,
                result=terminal.response.result,
                process_status=terminal.process_status,
            )
        )
    assert session.snapshot.brains == ()
    assert session.snapshot.source_selection is None
    assert "inspect" not in session.snapshot.allowed_actions


@pytest.mark.parametrize(
    "reply",
    [
        (401, b"SERVICE_TOKEN_CANARY"),
        (200, {"token": "SERVICE_TOKEN_CANARY"}),
        (200, [{"id": BRAIN, "name": KEY}]),
    ],
)
def test_listing_failures_never_forward_authored_or_transport_secret_text(
    monkeypatch, reply
):
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    with api_server() as (api, address):
        api.overrides["/api/brains"] = reply
        result = Operations().list_brains(ApiAcquisitionConfig(api_url=address))
    assert result.outcome in {"refused", "failed"}
    assert result.brains == ()
    assert "CANARY" not in result.model_dump_json()


def test_missing_credentials_have_actionable_safe_guidance(monkeypatch):
    monkeypatch.delenv("THE_BRAIN_LOCAL_API_KEY", raising=False)
    result = Operations().list_brains(ApiAcquisitionConfig())
    assert result.findings[0].code == "api_credentials_missing"
    assert "THE_BRAIN_LOCAL_API_KEY" in result.findings[0].message


def test_failed_refresh_preserves_brain_identity_until_successful_retry(monkeypatch):
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    with api_server() as (api, address):
        config = ApiAcquisitionConfig(api_url=address)
        operations, session = Operations(), ApplicationSession()
        session.dispatch(ConfigureApi(config=config))

        def refresh():
            effect = session.dispatch(ListBrainsCommand()).effects[0]
            result = operations.list_brains(config)
            return session.dispatch(
                ApplyResult(
                    request_id=effect.request.request_id,
                    input_revision=effect.input_revision,
                    result=result,
                    process_status=0 if result.outcome == "clean" else 1,
                )
            ).snapshot

        refresh()
        selection = LocalApiSourceSelection(brain_id=BRAIN, config=config)
        session.dispatch(SelectSource(source_selection=selection))
        api.overrides["/api/brains"] = (401, b"SERVICE_TOKEN_CANARY")
        failed = refresh()
        assert failed.source_selection == selection
        assert failed.brain_list_status == "failed"
        assert "inspect" not in failed.allowed_actions
        del api.overrides["/api/brains"]
        ready = refresh()
        assert ready.source_selection == selection
        assert ready.brain_list_status == "ready"
        assert "inspect" in ready.allowed_actions


def test_real_worker_api_review_rejects_changed_content_before_publication(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    worker = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src")
    with api_server() as (api, address):
        selection = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        request = WorkerRequest(
            request_id=str(uuid4()),
            operation="inspect",
            arguments=InspectArguments(source_selection=selection),
        )
        assert KEY.encode() not in encode_request(request)
        inspected = worker.run(request).response.result
        assert inspected.status == "inspection_clean"
        api.thoughts[HOME]["name"] = "Changed entry"
        converted = worker.run(
            WorkerRequest(
                request_id=str(uuid4()),
                operation="convert_reviewed",
                arguments=ConvertArguments(
                    source_selection=selection,
                    parent=str(tmp_path),
                    vault_name="Changed",
                    reviewed=inspected.reviewed,
                    proceed_with_warnings=False,
                ),
            )
        ).response.result
    assert converted.review_required
    assert converted.findings[0].code == "review_changed"
    assert converted.publication.state == "not_published"
    assert not (tmp_path / "Changed").exists()


def test_api_inspection_refusal_and_provider_failure_keep_secrets_out_of_results(
    monkeypatch,
):
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    with api_server() as (api, address):
        selection = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        api.thoughts[HOME]["name"] = KEY
        refused = Operations().inspect(selection)
        assert refused.status == "inspection_refused"
        assert "CANARY" not in refused.model_dump_json()

        def broken_provider():
            raise RuntimeError("PROVIDER_SECRET_CANARY")

        failed = Operations(credentials=broken_provider).inspect(selection)
        assert failed.status == "inspection_failed"
        assert "CANARY" not in failed.model_dump_json()


def test_old_configuration_free_wire_and_partial_effective_config_are_rejected():
    selection = LocalApiSourceSelection(brain_id=BRAIN)
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="inspect",
        arguments=InspectArguments(source_selection=selection),
    )
    wire = json.loads(encode_request(request))
    wire["schema_version"] = 2
    with pytest.raises(ProtocolFailure):
        decode_request(json.dumps(wire).encode() + b"\n")
    wire["schema_version"] = 3
    del wire["arguments"]["source_selection"]["config"]["max_requests"]
    with pytest.raises(ProtocolFailure):
        decode_request(json.dumps(wire).encode() + b"\n")


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_inventory",
        "null_inventory",
        "missing_id",
        "bad_id",
        "empty_name",
        "duplicate_id",
    ],
)
def test_successful_listing_wire_requires_explicit_complete_inventory(mutation):
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="list_brains",
        arguments=ListBrainsArguments(config=ApiAcquisitionConfig()),
    )
    response = WorkerResponse(
        request_id=request.request_id,
        operation="list_brains",
        result=BrainListResult(outcome="clean", status="brains_listed", brains=()),
    )
    assert decode_response(encode_response(response), request).result.brains == ()
    wire = json.loads(encode_response(response))
    if mutation == "missing_inventory":
        del wire["result"]["brains"]
    elif mutation == "null_inventory":
        wire["result"]["brains"] = None
    else:
        row = {"brain_id": BRAIN, "name": "Name"}
        if mutation == "missing_id":
            del row["brain_id"]
        elif mutation == "bad_id":
            row["brain_id"] = "00000000-0000-0000-0000-000000000000"
        elif mutation == "empty_name":
            row["name"] = ""
        wire["result"]["brains"] = [row, row] if mutation == "duplicate_id" else [row]
    with pytest.raises(ProtocolFailure):
        decode_response(json.dumps(wire).encode() + b"\n", request)


def test_api_inspection_releases_capture_and_reviewed_conversion_acquires_again(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    capture_parent = tmp_path / "captures"
    capture_parent.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(capture_parent))
    with api_server() as (api, address):
        selection = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        operations = Operations()
        inspected = operations.inspect(selection)
        assert inspected.status == "inspection_clean", inspected.diagnostic_text
        assert inspected.reviewed.source_selection == selection
        assert not list(capture_parent.iterdir())
        first_searches = sum(
            path.startswith("/api/search/") for path, _, _ in api.requests
        )
        converted = operations.convert_reviewed(
            selection, tmp_path, "API vault", inspected.reviewed
        )
        assert converted.status == "conversion_created", converted.diagnostic_text
        assert converted.publication.receipt_verified
        assert (
            sum(path.startswith("/api/search/") for path, _, _ in api.requests)
            > first_searches
        )
    record = json.loads((tmp_path / "API vault/migration-record.json").read_bytes())
    assert record["source_identity"]["source_id"] == BRAIN
    assert record["run_metadata"]["source_acquisition"]["audit"]["atomic"] is False
    assert "# Entry\n" in (tmp_path / "API vault/Home — Entry.md").read_text(
        encoding="utf-8"
    )
    assert KEY not in inspected.model_dump_json() + converted.model_dump_json()
    assert record["item_targets"][0]["item_key"] in {
        HOME,
        "33333333-3333-4333-8333-333333333333",
    }
