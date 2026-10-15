"""Public source-selection controls derived from #181's accepted contracts."""

import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from brz2obsidian.application.contracts import (
    ApplyResult,
    BrzSourceSelection,
    ConvertArguments,
    InspectArguments,
    InspectCommand,
    LocalApiSourceSelection,
    ReviewedInspection,
    SelectSource,
    SourceSelection,
    WorkerRequest,
    WorkerResponse,
)
from brz2obsidian.application.operations import ApplicationSession, Operations, inspect
from brz2obsidian.application.protocol import (
    ProtocolFailure,
    decode_request,
    decode_response,
    encode_request,
    encode_response,
)
from brz2obsidian.application.transport import Supervisor


def test_typed_archive_request_roundtrips_without_a_legacy_source_field(tmp_path):
    selection = BrzSourceSelection(path=str(tmp_path / "Été.brz"))
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="inspect",
        arguments=InspectArguments(source_selection=selection),
    )
    wire = encode_request(request)
    assert json.loads(wire)["arguments"] == {
        "source_selection": {"kind": "brz", "path": str(tmp_path / "Été.brz")}
    }
    assert json.loads(wire)["schema_version"] == 3
    assert decode_request(wire).arguments.source_selection == selection


def test_session_selects_a_brain_without_inventing_an_archive_or_vault_name():
    selection = LocalApiSourceSelection(brain_id="1fa60175-c910-4a09-b072-a1d5155c8314")
    session = ApplicationSession()
    selected = session.dispatch(SelectSource(source_selection=selection)).snapshot
    assert selected.source_selection == selection
    assert selected.source is None
    assert selected.vault_name == ""
    assert selected.allowed_actions == ("list_brains", "inspect", "close")
    request = session.dispatch(InspectCommand()).effects[0].request
    assert (
        decode_request(encode_request(request)).arguments.source_selection == selection
    )


def test_public_operations_keep_typed_brz_inspection_and_reviewed_publication(tmp_path):
    source = Path(__file__).parents[1] / "fixtures/minimal.brz"
    selection = BrzSourceSelection(path=str(source.absolute()))
    operations = Operations()
    result = operations.inspect(selection)
    assert result.status == "inspection_clean"
    assert result.reviewed.source_selection == selection
    assert result.reviewed.schema_version == 3
    converted = operations.convert_reviewed(
        selection, tmp_path, "Typed vault", result.reviewed
    )
    assert converted.status == "conversion_created"
    assert converted.publication.receipt_verified is True


def test_local_api_operations_and_real_worker_report_missing_credentials_without_archive_access(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("THE_BRAIN_LOCAL_API_KEY", raising=False)
    selection = LocalApiSourceSelection(brain_id="1fa60175-c910-4a09-b072-a1d5155c8314")
    operations = Operations()
    result = operations.inspect(selection)
    assert result.status == "inspection_failed"
    assert result.findings[0].code == "api_credentials_missing"
    assert result.reviewed is None
    assert operations.workflow is None
    conversion = operations.convert_reviewed(
        selection, tmp_path, "No publication", None
    )
    assert conversion.publication.state == "not_published"
    assert conversion.findings[0].code == "review_required"
    assert not (tmp_path / "No publication").exists()
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="inspect",
        arguments=InspectArguments(source_selection=selection),
    )
    terminal = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src").run(
        request
    )
    assert terminal.phase == "completed"
    assert terminal.response.result.findings[0].code == "api_credentials_missing"
    assert terminal.response.result.reviewed is None

    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    conversion_request = WorkerRequest(
        request_id=str(uuid4()),
        operation="convert_reviewed",
        arguments=ConvertArguments(
            source_selection=selection,
            parent=str(tmp_path),
            vault_name="No worker publication",
            reviewed=inspect(source).reviewed,
            proceed_with_warnings=False,
        ),
    )
    terminal = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src").run(
        conversion_request
    )
    assert terminal.phase == "completed"
    assert terminal.response.result.findings[0].code == "review_required"
    assert terminal.response.result.publication.state == "not_published"
    assert not (tmp_path / "No worker publication").exists()


def test_wire_rejects_legacy_archive_shapes_even_under_the_current_version():
    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="inspect",
        arguments=InspectArguments(source=str(source)),
    )
    payload = json.loads(encode_request(request))
    payload["arguments"] = {"source": str(source)}
    with pytest.raises(ProtocolFailure):
        decode_request(json.dumps(payload).encode() + b"\n")
    response = WorkerResponse(
        request_id=request.request_id, operation="inspect", result=inspect(source)
    )
    payload = json.loads(encode_response(response))
    review = payload["result"]["reviewed"]
    review.pop("source_selection")
    review["source"] = str(source)
    with pytest.raises(ProtocolFailure):
        decode_response(json.dumps(payload).encode() + b"\n", request)


def test_serialized_review_requires_an_explicit_current_version():
    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    payload = json.loads(inspect(source).reviewed.model_dump_json(by_alias=True))
    payload.pop("schema_version")
    with pytest.raises(ValidationError):
        ReviewedInspection.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "selection",
    [
        {"kind": "brz", "path": "relative.brz"},
        {"kind": "brz", "path": "1fa60175-c910-4a09-b072-a1d5155c8314"},
        {"kind": "local-api", "brain_id": "1FA60175-C910-4A09-B072-A1D5155C8314"},
        {"kind": "local-api", "brain_id": "{1fa60175-c910-4a09-b072-a1d5155c8314}"},
        {"kind": "local-api", "brain_id": "1fa60175c9104a09b072a1d5155c8314"},
        {"kind": "local-api", "brain_id": "not-a-brain"},
        {"kind": "local-api", "path": "C:/archive.brz"},
        {"kind": "brz", "brain_id": "1fa60175-c910-4a09-b072-a1d5155c8314"},
        {
            "kind": "local-api",
            "brain_id": "1fa60175-c910-4a09-b072-a1d5155c8314",
            "api_key": "INPUT_CREDENTIAL_CANARY",
        },
        {"kind": "other", "brain_id": "1fa60175-c910-4a09-b072-a1d5155c8314"},
    ],
)
def test_public_source_contract_rejects_malformed_or_credential_bearing_references(
    selection,
):
    with pytest.raises(ValidationError):
        TypeAdapter(SourceSelection).validate_python(selection)


@pytest.mark.parametrize("target", ["request", "response", "result", "review"])
def test_protocol_rejects_every_old_envelope_or_review_version(target):
    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="inspect",
        arguments=InspectArguments(source=str(source)),
    )
    if target == "request":
        payload = json.loads(encode_request(request))
        payload["schema_version"] = 1
        with pytest.raises(ProtocolFailure):
            decode_request(json.dumps(payload).encode() + b"\n")
        return
    payload = json.loads(
        encode_response(
            WorkerResponse(
                request_id=request.request_id,
                operation="inspect",
                result=inspect(source),
            )
        )
    )
    envelope = (
        payload
        if target == "response"
        else payload["result"]
        if target == "result"
        else payload["result"]["reviewed"]
    )
    envelope["schema_version"] = 1
    with pytest.raises(ProtocolFailure):
        decode_response(json.dumps(payload).encode() + b"\n", request)


@pytest.mark.parametrize("legacy", [str, Path])
def test_public_operation_requires_a_source_kind_for_a_bare_brain_uuid(legacy):
    operations = Operations()
    with pytest.raises(ValueError, match="local-api source selection"):
        operations.inspect(legacy("1fa60175-c910-4a09-b072-a1d5155c8314"))
    assert operations.workflow is None


def test_changing_source_kind_discards_an_archive_review_before_another_inspection():
    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=str(source)))
    started = session.dispatch(InspectCommand()).effects[0]
    session.dispatch(
        ApplyResult(
            request_id=started.request.request_id,
            input_revision=started.input_revision,
            result=inspect(source),
            process_status=0,
        )
    )
    assert session.snapshot.reviewed is not None
    selected = session.dispatch(
        SelectSource(
            source_selection=LocalApiSourceSelection(
                brain_id="1fa60175-c910-4a09-b072-a1d5155c8314"
            )
        )
    ).snapshot
    assert selected.reviewed is None
    assert selected.review_required is True
    assert selected.source is None
    assert selected.result is None
    assert selected.allowed_actions == ("list_brains", "inspect", "close")
