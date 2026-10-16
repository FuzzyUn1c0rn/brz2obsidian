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
    ConvertCommand,
    InspectArguments,
    InspectCommand,
    ListBrainsArguments,
    ListBrainsCommand,
    LocalApiSourceSelection,
    SelectSource,
    SetDestination,
    SimpleCommand,
    WorkerRequest,
    WorkerResponse,
)
from brz2obsidian.application.operations import (
    ApplicationSession,
    Operations,
    validate_destination,
)
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
        assert inspected.reviewed.profile_version == "3"
        previous_profile = inspected.reviewed.model_copy(
            update={"profile_version": "2"}
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


def test_api_capture_teardown_after_reviewed_publication_keeps_receipt_and_safe_guidance(
    tmp_path, monkeypatch
):
    import shutil

    from tests.support.local_api_payloads import (
        RichPayloadApi,
        assert_published_payloads,
    )

    captures = tmp_path / "captures"
    captures.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(captures))
    remove = shutil.rmtree

    def deny_frozen_capture(path, *args, **kwargs):
        if (path / "manifest.json").is_file():
            raise PermissionError("TEARDOWN_SECRET_CANARY SERVICE_TOKEN_CANARY")
        return remove(path, *args, **kwargs)

    with api_server(RichPayloadApi(jpeg=True)) as (_, address):
        selection = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        operations = Operations(credentials=lambda: KEY)
        inspected = operations.inspect(selection)
        assert inspected.reviewed is not None and not list(captures.iterdir())
        session = ApplicationSession()
        session.dispatch(SelectSource(source_selection=selection))
        effect = session.dispatch(InspectCommand()).effects[0]
        session.dispatch(
            ApplyResult(
                request_id=effect.request.request_id,
                input_revision=effect.input_revision,
                result=inspected,
                process_status=0,
            )
        )
        effect = next(
            effect
            for effect in session.dispatch(
                SetDestination(
                    parent_or_null=str(tmp_path), vault_name="Published before teardown"
                )
            ).effects
            if effect.effect == "run_operation"
        )
        validation = validate_destination(tmp_path, "Published before teardown")
        assert validation.outcome == "valid"
        session.dispatch(
            ApplyResult(
                request_id=effect.request.request_id,
                input_revision=effect.input_revision,
                result=validation,
                process_status=0,
            )
        )
        conversion_effect = session.dispatch(ConvertCommand()).effects[0]
        with monkeypatch.context() as boundary:
            boundary.setattr(shutil, "rmtree", deny_frozen_capture)
            result = operations.convert_reviewed(
                selection, tmp_path, "Published before teardown", inspected.reviewed
            )
        try:
            assert result.status == "conversion_created_with_error"
            assert result.publication.receipt_verified
            assert_published_payloads(tmp_path / "Published before teardown", jpeg=True)
            finding = next(
                f for f in result.findings if f.code == "api_capture_cleanup_failed"
            )
            assert "capture" in finding.message.lower()
            assert "publication status" in finding.message.lower()
            assert "CANARY" not in result.model_dump_json()
            done = session.dispatch(
                ApplyResult(
                    request_id=conversion_effect.request.request_id,
                    input_revision=conversion_effect.input_revision,
                    result=result,
                    process_status=1,
                )
            ).snapshot
            assert done.publication.receipt_verified
            assert "start_another_conversion" in done.allowed_actions
            assert "open_folder" in done.allowed_actions
            assert (
                "convert" not in done.allowed_actions
                and "retry" not in done.allowed_actions
            )
            restarted = session.dispatch(
                SimpleCommand(command="start_another_conversion")
            ).snapshot
            assert restarted.reviewed is None and restarted.review_required
            assert restarted.source_selection == selection
            assert_published_payloads(tmp_path / "Published before teardown", jpeg=True)
        finally:
            for capture in captures.iterdir():
                remove(capture)


def test_inspection_capture_teardown_failure_is_unusable_and_secret_safe(
    tmp_path, monkeypatch
):
    import shutil

    from tests.support.local_api_payloads import RichPayloadApi

    captures = tmp_path / "captures"
    captures.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(captures))
    remove = shutil.rmtree

    def deny_frozen_capture(path, *args, **kwargs):
        if (path / "manifest.json").is_file():
            raise PermissionError("TEARDOWN_SECRET_CANARY SERVICE_TOKEN_CANARY")
        return remove(path, *args, **kwargs)

    with api_server(RichPayloadApi(jpeg=True)) as (_, address):
        selection = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        try:
            with monkeypatch.context() as boundary:
                boundary.setattr(shutil, "rmtree", deny_frozen_capture)
                inspected = Operations(credentials=lambda: KEY).inspect(selection)
            assert inspected.outcome == "failed" and inspected.reviewed is None
            finding = next(
                f for f in inspected.findings if f.code == "api_capture_cleanup_failed"
            )
            assert "inspection capture" in finding.message.lower()
            assert "temporary storage access" in finding.message.lower()
            assert "CANARY" not in inspected.model_dump_json()
        finally:
            for capture in captures.iterdir():
                remove(capture)


def test_changed_included_scope_requires_review_before_any_publication(tmp_path):
    from tests.support.local_api import thought

    extra = "99999999-9999-4999-8999-999999999999"
    with api_server() as (api, address):
        api.thoughts[extra] = thought(extra, "Disconnected active source control")
        api.search.append(
            {
                "brainId": BRAIN,
                "isFromOtherBrain": False,
                "sourceThought": {"id": extra, "brainId": BRAIN, "kind": 0},
                "sourceLink": None,
            }
        )
        selection = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        operations = Operations(credentials=lambda: KEY)
        reviewed = operations.inspect(selection).reviewed
        assert reviewed is not None
        api.thoughts[extra]["forgottenDateTime"] = "2026-10-15T12:00:00Z"
        changed = operations.convert_reviewed(
            selection, tmp_path, "Changed scope", reviewed
        )
        assert changed.status == "conversion_refused"
        assert changed.findings[0].code == "review_changed"
        assert changed.review_required and changed.publication.state == "not_published"
        assert not (tmp_path / "Changed scope").exists()
        refreshed = operations.inspect(selection).reviewed
        assert (
            refreshed is not None
            and refreshed.source_identity != reviewed.source_identity
        )


def test_after_capture_live_payload_change_publishes_verified_captured_bytes_only(
    tmp_path, monkeypatch
):
    from tests.support.local_api_payloads import (
        NOTE,
        RICH_NOTE,
        RichPayloadApi,
        assert_published_payloads,
    )

    with api_server(RichPayloadApi(jpeg=True)) as (api, address):
        selection = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        operations = Operations(credentials=lambda: KEY)
        reviewed = operations.inspect(selection).reviewed
        assert reviewed is not None
        make_directory = tempfile.mkdtemp

        def change_live_source_at_output_directory(*args, **kwargs):
            if kwargs.get("dir") == tmp_path:
                api.payloads[NOTE] = (
                    RICH_NOTE + b"Changed after capture and review comparison"
                )
            return make_directory(*args, **kwargs)

        with monkeypatch.context() as boundary:
            boundary.setattr(
                tempfile, "mkdtemp", change_live_source_at_output_directory
            )
            result = operations.convert_reviewed(
                selection, tmp_path, "captured", reviewed
            )
        assert result.publication.receipt_verified
        assert api.payloads[NOTE] != RICH_NOTE
        assert_published_payloads(tmp_path / "captured", jpeg=True)
        record = json.loads((tmp_path / "captured/migration-record.json").read_bytes())
        assert record["source_identity"] == reviewed.source_identity.model_dump()
        assert record["run_metadata"]["source_acquisition"]["audit"]["atomic"] is False
        next_review = operations.inspect(selection).reviewed
        assert next_review.source_identity != reviewed.source_identity


def test_rich_review_identity_survives_reordered_http_ports_and_audit_only_changes(
    tmp_path,
):
    from tests.support.local_api_payloads import (
        RichPayloadApi,
        assert_published_payloads,
    )
    from tests.support.reviewed_api import ReorderedReviewApi

    operations = Operations(credentials=lambda: KEY)
    with api_server(RichPayloadApi(jpeg=True)) as (_, address):
        first = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        reviewed = operations.inspect(first).reviewed
        assert reviewed is not None
    with api_server(ReorderedReviewApi(jpeg=True)) as (_, address):
        second = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        reordered = operations.inspect(second).reviewed
        assert reordered is not None
        assert first.config.api_url != second.config.api_url
        assert reordered.source_identity == reviewed.source_identity
        old_configuration = operations.convert_reviewed(
            second, tmp_path, "unreviewed-port", reviewed
        )
        assert old_configuration.findings[0].code == "review_required"
        assert not (tmp_path / "unreviewed-port").exists()
        result = operations.convert_reviewed(
            second, tmp_path, "reviewed-order", reordered
        )
        assert result.publication.receipt_verified
        assert_published_payloads(tmp_path / "reviewed-order", jpeg=True)


@pytest.mark.parametrize(
    "field",
    [
        "converter_version",
        "profile_id",
        "profile_version",
        "source_sha256",
        "snapshot_digest",
    ],
)
def test_real_worker_rich_review_compatibility_never_publishes_a_mismatched_review(
    tmp_path, monkeypatch, field
):
    from tests.support.local_api_payloads import RichPayloadApi

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    worker = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src")
    with api_server(RichPayloadApi(jpeg=True)) as (_, address):
        selection = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        inspected = worker.run(
            WorkerRequest(
                request_id=str(uuid4()),
                operation="inspect",
                arguments=InspectArguments(source_selection=selection),
            )
        ).response.result
        review = inspected.reviewed
        assert review is not None
        if field in {"source_sha256", "snapshot_digest"}:
            review = review.model_copy(
                update={
                    "source_identity": review.source_identity.model_copy(
                        update={field: "0" * 64}
                    )
                }
            )
        else:
            review = review.model_copy(update={field: "previous-review"})
        result = worker.run(
            WorkerRequest(
                request_id=str(uuid4()),
                operation="convert_reviewed",
                arguments=ConvertArguments(
                    source_selection=selection,
                    parent=str(tmp_path),
                    vault_name=field,
                    reviewed=review,
                    proceed_with_warnings=False,
                ),
            )
        ).response.result
    assert result.status == "conversion_refused" and result.review_required
    assert result.findings[0].code == "review_changed"
    assert result.publication.state == "not_published"
    assert not (tmp_path / field).exists()


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


def test_real_worker_requires_gap_warning_authorization_and_fresh_pdf_review(
    tmp_path, monkeypatch
):
    from tests.support.local_api_payloads import (
        PDF,
        PDF_BYTES,
        MissingTxtPdfApi,
        assert_published_txt_pdf_gap,
    )

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    with api_server(MissingTxtPdfApi()) as (api, address):
        selection = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        worker = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src")

        def inspect():
            return worker.run(
                WorkerRequest(
                    request_id=str(uuid4()),
                    operation="inspect",
                    arguments=InspectArguments(source_selection=selection),
                )
            ).response.result

        def convert(name, reviewed, authorized):
            return worker.run(
                WorkerRequest(
                    request_id=str(uuid4()),
                    operation="convert_reviewed",
                    arguments=ConvertArguments(
                        source_selection=selection,
                        parent=str(tmp_path),
                        vault_name=name,
                        reviewed=reviewed,
                        proceed_with_warnings=authorized,
                    ),
                )
            ).response.result

        inspected = inspect()
        assert inspected.reviewed.outcome == "warnings"
        refused = convert("unauthorized", inspected.reviewed, False)
        assert refused.status == "conversion_refused"
        assert refused.findings[0].code == "warning_authorization_required"
        assert not (tmp_path / "unauthorized").exists()
        api.payloads[PDF] += b"Changed PDF bytes"
        changed = convert("changed", inspected.reviewed, True)
        assert changed.status == "conversion_refused"
        assert "review_changed" in {finding.code for finding in changed.findings}
        assert not (tmp_path / "changed").exists()
        api.payloads[PDF] = PDF_BYTES
        from tests.support.local_api_payloads import TXT

        path = f"/api/attachments/{BRAIN}/{TXT}/file-content"
        unavailable = api.overrides[path]
        api.overrides[path] = 200, b"Now available source TXT"
        available = convert("availability-changed", inspected.reviewed, True)
        assert available.status == "conversion_refused"
        assert "review_changed" in {finding.code for finding in available.findings}
        assert not (tmp_path / "availability-changed").exists()
        api.overrides[path] = unavailable
        fresh = inspect()
        converted = convert("authorized", fresh.reviewed, True)
        assert converted.status == "conversion_created_with_warnings"
        assert converted.publication.receipt_verified
        assert_published_txt_pdf_gap(tmp_path / "authorized")


@pytest.mark.parametrize("stage", ["search", "relationship", "resource"])
def test_profile3_fixed_stage_messages_survive_real_worker_and_reviewed_conversion(
    tmp_path, monkeypatch, stage
):
    from tests.support.local_api import MetadataApi
    from tests.support.local_api_graph import HIERARCHY
    from tests.support.local_api_payloads import (
        FILE,
        SHAPE_MESSAGES,
        unsupported_shape_api,
    )

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    api = unsupported_shape_api(stage)
    if stage == "search":
        fault = api.search
        api.search = MetadataApi().search
    elif stage == "relationship":
        fault = api.links[HIERARCHY]["relation"]
        api.links[HIERARCHY]["relation"] = 1
    else:
        fault = api.attachments.pop(FILE)
    worker = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src")
    with api_server(api) as (_, address):
        selection = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        operations = Operations()
        review = operations.inspect(selection).reviewed
        assert review is not None
        if stage == "search":
            api.search = fault
        elif stage == "relationship":
            api.links[HIERARCHY]["relation"] = fault
        else:
            api.attachments[FILE] = fault
        results = [
            operations.inspect(selection),
            operations.convert_reviewed(selection, tmp_path, "refused", review),
        ]
        for operation, arguments in (
            ("inspect", InspectArguments(source_selection=selection)),
            (
                "convert_reviewed",
                ConvertArguments(
                    source_selection=selection,
                    parent=str(tmp_path),
                    vault_name="worker-refused",
                    reviewed=review,
                    proceed_with_warnings=False,
                ),
            ),
        ):
            terminal = worker.run(
                WorkerRequest(
                    request_id=str(uuid4()), operation=operation, arguments=arguments
                )
            )
            assert terminal.phase == "completed"
            results.append(terminal.response.result)
        for result in results:
            assert result.outcome == "refused"
            assert result.findings[0].code == f"api_{stage}_shape_unsupported"
            assert result.findings[0].message == SHAPE_MESSAGES[stage]
            assert SHAPE_MESSAGES[stage] in result.diagnostic_text
            assert "CANARY" not in result.model_dump_json()
        assert not (tmp_path / "refused").exists()
        assert not (tmp_path / "worker-refused").exists()


def test_valid_replacement_image_has_new_identity_and_needs_new_review(tmp_path):
    from io import BytesIO

    from PIL import Image

    from tests.support.local_api_payloads import IMAGE, RichPayloadApi

    stream = BytesIO()
    Image.new("RGB", (2, 1), "blue").save(stream, format="PNG")
    replacement = stream.getvalue()
    with api_server(RichPayloadApi()) as (api, address):
        selection = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        operations = Operations(credentials=lambda: KEY)
        original = operations.inspect(selection)
        assert original.reviewed is not None
        api.payloads[IMAGE] = replacement
        current = operations.inspect(selection)
        assert current.reviewed is not None
        assert current.reviewed.source_identity != original.reviewed.source_identity
        assert (
            current.reviewed.source_identity.source_sha256
            != original.reviewed.source_identity.source_sha256
        )
        refused = operations.convert_reviewed(
            selection, tmp_path, "old-review", original.reviewed
        )
        assert refused.findings[0].code == "review_changed"
        assert not (tmp_path / "old-review").exists()
        accepted = operations.convert_reviewed(
            selection, tmp_path, "new-review", current.reviewed
        )
        assert accepted.publication.receipt_verified
        assert (
            tmp_path / f"new-review/Attachments/22222222/{IMAGE}.png"
        ).read_bytes() == replacement


def test_valid_reverse_arrow_change_requires_a_fresh_review(tmp_path):
    from tests.sources.test_local_api_relationship_candidates import (
        LINK,
        LinkCandidateApi,
    )

    api = LinkCandidateApi()
    with api_server(api) as (_, address):
        selection = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        operations = Operations(credentials=lambda: KEY)
        original = operations.inspect(selection)
        assert original.reviewed is not None
        api.links[LINK]["direction"] = 3
        current = operations.inspect(selection)
        assert current.reviewed is not None
        assert (
            current.reviewed.source_identity.source_sha256
            != original.reviewed.source_identity.source_sha256
        )
        assert (
            current.reviewed.source_identity.snapshot_digest
            != original.reviewed.source_identity.snapshot_digest
        )
        refused = operations.convert_reviewed(
            selection, tmp_path, "old-review", original.reviewed
        )
        assert refused.findings[0].code == "review_changed"
        assert not (tmp_path / "old-review").exists()
        accepted = operations.convert_reviewed(
            selection, tmp_path, "new-review", current.reviewed
        )
        assert accepted.publication.receipt_verified
