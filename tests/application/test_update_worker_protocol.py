"""Versioned worker envelopes retain existing migration output contracts."""

import json

import pytest

from brz2obsidian.application.contracts import (
    ConvertArguments,
    InspectArguments,
    InspectionResult,
    ReviewedInspection,
    WorkerRequest,
    WorkerResponse,
)
from brz2obsidian.application.protocol import (
    ProtocolFailure,
    decode_request,
    decode_response,
    encode_request,
    encode_response,
)
from brz2obsidian.contracts import SourceIdentity


def test_worker_envelope4_preserves_nested_migration3_and_refuses_old_envelope(
    tmp_path,
):
    identity = "11111111-1111-4111-8111-111111111111"
    source = str(tmp_path / "independent.brz")
    review = ReviewedInspection(
        source=source,
        source_identity=SourceIdentity(
            source_id="independent-source",
            module_id="thebrain-brz",
            module_version="1",
            format_version="5",
            source_sha256="a" * 64,
            snapshot_digest="b" * 64,
        ),
        converter_version="independent-version",
        profile_id="independent-profile",
        profile_version="1",
        outcome="clean",
    )
    request = WorkerRequest(
        request_id=identity,
        operation="inspect",
        arguments=InspectArguments(source=source),
    )
    response = WorkerResponse(
        request_id=identity,
        operation="inspect",
        result=InspectionResult(
            outcome="clean", status="inspection_clean", reviewed=review
        ),
    )
    request_wire = json.loads(encode_request(request))
    response_wire = json.loads(encode_response(response))
    assert request_wire["schema_version"] == 4
    assert response_wire["schema_version"] == 4
    assert response_wire["result"]["schema_version"] == 3
    assert response_wire["result"]["reviewed"]["schema_version"] == 3
    assert decode_response(encode_response(response), request).result.status == (
        "inspection_clean"
    )

    conversion = WorkerRequest(
        request_id=identity,
        operation="convert_reviewed",
        arguments=ConvertArguments(
            source=source,
            parent=str(tmp_path),
            vault_name="Reviewed vault",
            reviewed=review,
            proceed_with_warnings=False,
        ),
    )
    converted_wire = json.loads(encode_request(conversion))
    assert converted_wire["schema_version"] == 4
    assert converted_wire["arguments"]["reviewed"]["schema_version"] == 3
    assert decode_request(encode_request(conversion)).arguments.reviewed == review
    for wire, decoder in (
        (request_wire, decode_request),
        (response_wire, lambda raw: decode_response(raw, request)),
    ):
        wire["schema_version"] = 3
        with pytest.raises(ProtocolFailure):
            decoder(json.dumps(wire).encode("utf-8") + b"\n")


def test_update_commands_roundtrip_without_canonical_preparation(tmp_path):
    import pytest
    from pydantic import ValidationError

    from brz2obsidian.application.contracts import WorkerRequest
    from brz2obsidian.application.protocol import decode_request, encode_request

    request = WorkerRequest(
        request_id="11111111-1111-4111-8111-111111111111",
        operation="update",
        sequence=1,
        arguments={
            "command": "prepare",
            "vault": str(tmp_path),
            "selection_id": "22222222-2222-4222-8222-222222222222",
            "kind": "onboarding",
            "source": None,
        },
    )
    assert decode_request(encode_request(request)) == request
    assert request.schema_version == 4 and request.arguments.command == "prepare"
    with pytest.raises(ValidationError):
        WorkerRequest(
            request_id=request.request_id,
            operation="update",
            sequence=1,
            arguments={
                **request.arguments.model_dump(),
                "preparation": {"ready": True},
            },
        )


def test_stream_terminal_is_provisional_until_matching_end_and_poisoned_by_late_fault():
    import pytest

    from brz2obsidian.application.contracts import WorkerRequest, WorkerResponse
    from brz2obsidian.application.protocol import ProtocolFailure, encode_response
    from brz2obsidian.application.update_context_contracts import UpdateContextResult
    from brz2obsidian.application.update_stream import WorkerStreamDecoder, encode_end

    request = WorkerRequest(
        request_id="11111111-1111-4111-8111-111111111111",
        operation="update",
        sequence=1,
        arguments={
            "command": "prepare",
            "vault": "C:/vault",
            "selection_id": "22222222-2222-4222-8222-222222222222",
            "kind": "onboarding",
            "source": None,
        },
    )
    response = WorkerResponse(
        request_id=request.request_id,
        operation="update",
        sequence=1,
        result=UpdateContextResult(
            status="refused", kind="onboarding", code="evidence_required"
        ),
    )
    terminal = encode_response(response)
    seal = encode_end(response)
    for contradiction in (
        {
            "status": "applied",
            "ready": True,
            "publication": "not_started",
            "history_retained": False,
            "binding": None,
        },
        {"ready": True, "binding": None},
        {"status": "available", "page": None, "binding": None},
    ):
        unsafe = json.loads(terminal)
        unsafe["result"].update(contradiction)
        with pytest.raises(ProtocolFailure):
            WorkerStreamDecoder(request).feed(json.dumps(unsafe).encode() + b"\n")
    for field in ("publication", "history_retained", "binding"):
        incomplete = json.loads(terminal)
        del incomplete["result"][field]
        with pytest.raises(ProtocolFailure):
            WorkerStreamDecoder(request).feed(json.dumps(incomplete).encode() + b"\n")
    abandoned = WorkerStreamDecoder(request)
    abandoned.feed(terminal)
    with pytest.raises(ProtocolFailure):
        abandoned.eof()
    assert abandoned.poisoned
    decoder = WorkerStreamDecoder(request)
    assert decoder.feed(terminal) is None and not decoder.sealed
    assert decoder.feed(seal) == response and decoder.sealed
    with pytest.raises(ProtocolFailure):
        decoder.feed(terminal)
    assert decoder.poisoned and not decoder.sealed
    for frames in (
        (seal,),
        (terminal, terminal),
        (
            terminal,
            seal.replace(
                request.request_id.encode(), b"33333333-3333-4333-8333-333333333333"
            ),
        ),
        (terminal, b'{"schema_version":4,"schema_version":4}\n'),
    ):
        broken = WorkerStreamDecoder(request)
        with pytest.raises(ProtocolFailure):
            for frame in frames:
                broken.feed(frame)
        assert broken.poisoned and not broken.sealed


def test_hidden_update_worker_reuses_process_until_explicit_close(tmp_path):
    import sys
    from pathlib import Path
    from uuid import uuid4

    from brz2obsidian.application.transport import Supervisor

    supervisor = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src")
    channel = supervisor.open_update()
    try:
        pid = channel.pid
        for _ in range(2):
            request = WorkerRequest(
                request_id=str(uuid4()),
                operation="update",
                sequence=1,
                arguments={
                    "command": "prepare",
                    "vault": str(tmp_path / "Missing vault"),
                    "selection_id": str(uuid4()),
                    "kind": "onboarding",
                    "source": None,
                },
            )
            terminal = channel.run(request)
            assert terminal.phase == "completed"
            assert terminal.response.result.kind == "onboarding"
            assert terminal.response.result.status == "refused"
            assert channel.pid == pid and not channel.poisoned
        closed = channel.run(
            WorkerRequest(
                request_id=str(uuid4()),
                operation="update",
                sequence=1,
                arguments={"command": "close", "choice": "discard"},
            )
        )
        assert (
            closed.phase == "completed"
            and closed.response.result.code == "context_closed"
        )
    finally:
        channel.close()
    assert channel.closed
    assert channel.process_status == 0


def test_worker_stream_keeps_unsaved_producer_between_commands(tmp_path):
    import io
    from uuid import uuid4

    from brz2obsidian.application.update_stream import WorkerStreamDecoder
    from brz2obsidian.application.update_worker import UpdateWorker
    from tests.application.test_update_context import context_case

    context, case = context_case(tmp_path)
    output = io.BytesIO()
    worker = UpdateWorker(context=context, output=output)
    prepare = WorkerRequest(
        request_id=str(uuid4()),
        operation="update",
        sequence=1,
        arguments={
            "command": "prepare",
            "vault": str(case.vault),
            "selection_id": str(uuid4()),
            "kind": "attachment_cleanup",
            "source": None,
        },
    )
    worker.handle(prepare)
    frames = output.getvalue().splitlines(keepends=True)
    first = WorkerStreamDecoder(prepare)
    assert first.feed(frames[0]) is None
    result = first.feed(frames[1]).result
    assert result.binding is not None and result.unresolved == 2
    output.seek(0)
    output.truncate()
    page = WorkerRequest(
        request_id=str(uuid4()),
        operation="update",
        sequence=2,
        arguments={
            "command": "page",
            "binding": result.binding,
            "limit": 1,
            "byte_limit": 16,
        },
    )
    worker.handle(page)
    decoder = WorkerStreamDecoder(page)
    answer = None
    for frame in output.getvalue().splitlines(keepends=True):
        answer = decoder.feed(frame)
    assert answer.result.page.proposal_id == result.binding.proposal_id
    assert len(answer.result.page.items) == 1
    assert not (case.vault / ".brz2obsidian").exists()


def test_reference_draft_commands_page_choices_without_a_total_reference_cap(tmp_path):
    from uuid import uuid4

    from pydantic import ValidationError

    from tests.application.test_update_context import context_case

    context, case = context_case(tmp_path)
    opened = context.prepare(
        case.vault, selection_id=str(uuid4()), kind="attachment_cleanup"
    )
    args = {
        "command": "stage_references",
        "binding": opened.binding,
        "requirement_id": "canonical-offer",
        "choices": tuple(
            {"reference_id": f"{n:064x}", "choice": "drop"} for n in range(100)
        ),
    }
    request = WorkerRequest(
        request_id=str(uuid4()), operation="update", sequence=1, arguments=args
    )
    assert len(encode_request(request)) < 256 * 1024
    assert len(decode_request(encode_request(request)).arguments.choices) == 100
    with pytest.raises(ValidationError):
        WorkerRequest(
            request_id=request.request_id,
            operation="update",
            sequence=1,
            arguments=args | {"choices": args["choices"] + (args["choices"][0],)},
        )
