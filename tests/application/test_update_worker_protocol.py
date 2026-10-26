"""Versioned worker envelopes retain existing migration output contracts."""

import json

import pytest


def test_progress_is_a_bounded_observation_until_one_matching_terminal_seal(tmp_path):
    from brz2obsidian.application.update_context_contracts import (
        UpdateContextBinding,
        UpdateContextResult,
    )
    from brz2obsidian.application.update_stream import (
        WorkerProgress,
        WorkerStreamDecoder,
        encode_end,
        encode_progress,
    )
    from brz2obsidian.application.vault_progress_contracts import VaultProgress

    identity = "11111111-1111-4111-8111-111111111111"
    binding = UpdateContextBinding(
        context_id=identity,
        selection_id=identity,
        vault=str(tmp_path),
        association_id="a" * 64,
        checkpoint_commit="4" * 40,
        checkpoint_generation=4,
        proposal_id="closed-proposal",
        generation=2,
        revision=1,
    )
    request = WorkerRequest(
        operation="update",
        request_id=identity,
        sequence=7,
        arguments={"command": "apply", "binding": binding},
    )
    observed = VaultProgress(
        phase="publication",
        operation_id="1" * 32,
        operation_generation=5,
        intent_commit="6" * 40,
        completed_units=1,
        total_units=2,
        unit="files",
    )
    progress = WorkerProgress(
        request_id=identity, sequence=7, ordinal=1, value=observed
    )
    wire = encode_progress(progress)
    assert len(wire) < 2048 and json.loads(wire)["schema_version"] == 4
    decoder = WorkerStreamDecoder(request)
    assert decoder.feed(wire) is None and not decoder.sealed
    assert decoder.progress == progress
    for ordinal in range(2, 1002):
        latest = progress.model_copy(update={"ordinal": ordinal})
        assert decoder.feed(encode_progress(latest)) is None
    assert decoder.progress.ordinal == 1001 and decoder.progress.value == observed
    result = WorkerResponse(
        operation="update",
        request_id=identity,
        sequence=7,
        result=UpdateContextResult(
            status="recovery_required",
            kind="attachment_cleanup",
            code="cancelled_after_intent",
            publication="partial",
            history_retained=True,
            checkpoint_commit="5" * 40,
            next_actions=("inspect_history",),
        ),
    )
    terminal = encode_response(result)
    assert decoder.feed(terminal) is None and decoder.progress is None
    assert decoder.feed(encode_end(result)) == result and decoder.sealed
    with pytest.raises(ProtocolFailure):
        decoder.feed(wire)
    assert decoder.poisoned and not decoder.sealed and decoder.progress is None
    for corrupt in (
        progress.model_copy(
            update={"request_id": "22222222-2222-4222-8222-222222222222"}
        ),
        progress.model_copy(update={"sequence": 8}),
        progress.model_copy(update={"ordinal": 0}),
    ):
        with pytest.raises(ProtocolFailure):
            WorkerStreamDecoder(request).feed(encode_progress(corrupt))
    repeated = WorkerStreamDecoder(request)
    repeated.feed(wire)
    with pytest.raises(ProtocolFailure):
        repeated.feed(wire)
    assert repeated.progress is None
    missing = json.loads(wire)
    del missing["value"]["completed_units"]
    with pytest.raises(ProtocolFailure):
        WorkerStreamDecoder(request).feed(json.dumps(missing).encode() + b"\n")
    abandoned = WorkerStreamDecoder(request)
    abandoned.feed(wire)
    with pytest.raises(ProtocolFailure):
        abandoned.eof()
    assert abandoned.progress is None


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


def test_sealed_history_reply_requires_consistent_readiness_and_native_outcome(
    tmp_path,
):
    from brz2obsidian.application.update_context_contracts import UpdateContextResult
    from brz2obsidian.application.update_history_contracts import (
        HistoryContextBinding,
        UpdateHistoryActionState,
    )
    from brz2obsidian.application.update_stream import WorkerStreamDecoder, encode_end
    from brz2obsidian.application.vault_update_contracts import VaultApplyResult
    from tests.application.test_history_workflow import operation_state

    identity = "11111111-1111-4111-8111-111111111111"
    request = WorkerRequest(
        operation="update",
        request_id=identity,
        sequence=1,
        arguments={
            "command": "history",
            "vault": str(tmp_path),
            "selection_id": identity,
        },
    )
    binding = HistoryContextBinding(
        context_id=identity,
        selection_id=identity,
        vault=str(tmp_path),
        revision=1,
        fingerprint="a" * 64,
        operation_id="1" * 32,
        operation_generation=7,
        intent_commit="2" * 40,
    )
    directions = UpdateContextResult(
        status="direction_required",
        kind="history",
        code="direction_required",
        binding=binding,
        history_action=UpdateHistoryActionState(
            kind="recovery",
            status="direction_required",
            ready=False,
            available_directions=("finish", "restore"),
            operation=None,
            summary="Choose a direction.",
        ),
    )
    response = WorkerResponse(
        operation="update", request_id=identity, sequence=1, result=directions
    )

    def sealed(result):
        value = WorkerResponse(
            operation="update", request_id=identity, sequence=1, result=result
        )
        decoder = WorkerStreamDecoder(request)
        assert decoder.feed(encode_response(value)) is None
        return decoder.feed(encode_end(value)).result

    assert not sealed(directions).ready
    for kind in ("recovery", "repair"):
        # Cleanup-only recovery and repair legitimately have no S1 direction/review.
        ready = directions.model_copy(
            update={
                "status": "prepared_review",
                "ready": True,
                "history_action": UpdateHistoryActionState(
                    kind=kind,
                    status="ready",
                    ready=True,
                    available_directions=(),
                    operation=None,
                    summary="Ready native preparation.",
                ),
            }
        )
        assert sealed(ready).ready
    native = VaultApplyResult.model_validate(
        operation_state("incomplete").model_dump()
        | {
            "status": "restored",
            "direction": "restore",
            "phase": "terminal",
            "publication": "complete",
            "history": "terminal",
            "checkpoint_commit": "3" * 40,
            "result_commit": "4" * 40,
            "receipt_commit": "5" * 40,
            "published_files": 2,
            "recovery_required": False,
        }
    )
    restored = directions.model_copy(
        update={
            "status": "restored",
            "binding": None,
            "publication": "complete",
            "history_retained": True,
            "checkpoint_commit": "3" * 40,
            "history_action": UpdateHistoryActionState(
                kind="recovery",
                status="restored",
                ready=False,
                available_directions=(),
                operation=native,
                summary="Restored.",
            ),
        }
    )
    assert sealed(restored).status == "restored"
    contradictions = [
        {"status": "prepared_review", "ready": True},
        {"status": "prepared_review", "ready": True, "history_action": None},
        {
            "status": "prepared_review",
            "ready": True,
            "history_action": directions.history_action.model_dump()
            | {"status": "ready", "ready": True},
        },
    ]
    for status in ("restored", "undone"):
        contradictions.append(
            {
                "status": status,
                "binding": None,
                "history_action": directions.history_action.model_dump()
                | {"status": status, "available_directions": []},
            }
        )
    for contradiction in contradictions:
        unsafe = json.loads(encode_response(response))
        unsafe["result"].update(contradiction)
        with pytest.raises(ProtocolFailure):
            WorkerStreamDecoder(request).feed(json.dumps(unsafe).encode() + b"\n")
    mismatched = json.loads(
        encode_response(
            WorkerResponse(
                operation="update", request_id=identity, sequence=1, result=restored
            )
        )
    )
    mismatched["result"]["status"] = mismatched["result"]["history_action"][
        "status"
    ] = "undone"
    with pytest.raises(ProtocolFailure):
        WorkerStreamDecoder(request).feed(json.dumps(mismatched).encode() + b"\n")


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
