"""Live controls reach blocked native I/O without changing publication truth."""

import io
import json
import os
from threading import Event, Thread
from uuid import uuid4

import pytest

from brz2obsidian.application.contracts import WorkerRequest
from brz2obsidian.application.protocol import (
    ProtocolFailure,
    encode_request,
    encode_response,
)
from brz2obsidian.application.update_stream import WorkerStreamDecoder, encode_end
from brz2obsidian.application.update_worker import UpdateWorker
from brz2obsidian.application.vault_update_contracts import VaultApplyResult
from tests.application.test_history_workflow import operation_state
from tests.application.test_update_context import context_case


def test_live_cancel_reaches_blocked_native_io_and_retains_after_intent_truth(
    tmp_path, monkeypatch
):
    context, case = context_case(tmp_path)
    opened = context.prepare(
        case.vault, selection_id=str(uuid4()), kind="attachment_cleanup"
    )
    binding = opened.binding
    page = context.page(binding, byte_limit=0)
    for item, choice in (("keep-asset", "current"), ("remove-asset", "remove")):
        change = next(row for row in page.page.items if row.item_id == item)
        offer = next(row for row in page.offers if row.change_id == change.change_id)
        refs = (
            context.reference_page(
                binding, requirement_id=offer.requirement_id
            ).references
            if choice == "remove"
            else ()
        )
        selected = context.choose(
            binding,
            requirement_id=offer.requirement_id,
            choice=choice,
            assumptions_digest=offer.assumptions_digest,
            references=tuple(
                {"reference_id": row.reference_id, "choice": "drop"} for row in refs
            ),
        )
        assert selected.code == "accepted"
        binding = selected.binding
    assert selected.ready
    case.history.checkpoint.manifest.vault = case.history.admission.inventory
    entered, release = Event(), Event()
    observed_cancel = []
    native = VaultApplyResult.model_validate(
        operation_state("incomplete").model_dump()
        | {
            "status": "cancelled",
            "code": "cancelled_after_intent",
            "phase": "publication",
            "publication": "partial",
            "history": "intent",
            "published_files": 1,
            "authored_files_changed": True,
            "intent_commit": "2" * 40,
            "generation": 3,
            "review_generation": binding.generation,
            "direction": None,
            "origin_role": "attachment_cleanup",
            "recovery_required": True,
        }
    )

    def native_io(self, *args, cancel=None, **kwargs):
        entered.set()
        assert release.wait(5), (
            "The control reply must arrive before blocked I/O is released"
        )
        observed_cancel.append(cancel())
        return native

    monkeypatch.setattr(type(case.operations), "apply_reviewed_update", native_io)
    read_fd, write_fd = os.pipe()
    input_pipe, commands = (
        os.fdopen(read_fd, "rb"),
        os.fdopen(write_fd, "wb", buffering=0),
    )
    output_read, output_write = os.pipe()
    replies, output_pipe = (
        os.fdopen(output_read, "rb"),
        os.fdopen(output_write, "wb", buffering=0),
    )
    worker = UpdateWorker(context=context, output=output_pipe)
    server = Thread(target=worker.serve, args=(input_pipe,), daemon=True)
    apply = WorkerRequest(
        request_id=str(uuid4()),
        operation="update",
        sequence=1,
        arguments={"command": "apply", "binding": binding},
    )
    wrong = WorkerRequest(
        request_id=str(uuid4()),
        operation="update",
        sequence=2,
        arguments={
            "command": "cancel",
            "binding": binding,
            "target_request_id": apply.request_id,
            "target_sequence": 999,
        },
    )
    cancel = WorkerRequest(
        request_id=str(uuid4()),
        operation="update",
        sequence=3,
        arguments={
            "command": "cancel",
            "binding": binding,
            "target_request_id": apply.request_id,
            "target_sequence": 1,
        },
    )
    server.start()
    try:
        commands.write(encode_request(apply))
        assert entered.wait(5)
        commands.write(encode_request(wrong))
        decoder = WorkerStreamDecoder(wrong)
        assert decoder.feed(replies.readline()) is None
        assert decoder.feed(replies.readline()).result.code == "context_changed"
        commands.write(encode_request(cancel))
        decoder = WorkerStreamDecoder(cancel)
        assert decoder.feed(replies.readline()) is None
        ack = decoder.feed(replies.readline())
        assert ack.result.code == "cancellation_requested" and not release.is_set()
        release.set()
        decoder = WorkerStreamDecoder(apply)
        assert decoder.feed(replies.readline()) is None
        terminal = decoder.feed(replies.readline())
        assert terminal.result.status == "recovery_required"
        assert (
            terminal.result.publication == "partial"
            and terminal.result.history_retained
        )
        assert terminal.result.operation == native
        assert (
            terminal.result.operation.generation == 3
            and binding.checkpoint_generation == 2
        )
        assert terminal.result.operation.review_generation == binding.generation == 1
        assert terminal.result.operation.origin_role == "attachment_cleanup"
        assert terminal.result.operation.intent_commit == "2" * 40
        assert terminal.result.binding is None
        baseline = WorkerStreamDecoder(apply)
        assert baseline.feed(encode_response(terminal)) is None
        assert baseline.feed(encode_end(terminal)) == terminal
        for contradiction in (
            {"publication": "not_published"},
            {"history_retained": False},
            {"status": "cancelled_before_publication"},
        ):
            raw = json.loads(encode_response(terminal))
            raw["result"].update(contradiction)
            rejected = WorkerStreamDecoder(apply)
            with pytest.raises(ProtocolFailure):
                rejected.feed(json.dumps(raw).encode("utf-8") + b"\n")
            assert rejected.poisoned and not rejected.sealed
        continued = context.close(None, choice="continue")
        assert (
            continued.operation == native
            and continued.publication == "partial"
            and continued.history_retained
        )
        assert continued.status == "recovery_required" and not continued.ready
        closed = context.close(None, choice="discard")
        assert (
            closed.operation == native
            and closed.publication == "partial"
            and closed.history_retained
        )
        other = context.prepare(
            str(tmp_path / "other-vault"),
            selection_id=str(uuid4()),
            kind="onboarding",
            cancel=lambda: True,
        )
        assert (
            other.status == "cancelled_before_publication" and other.operation is None
        )
        assert (
            other.history_retained is False
            and other.checkpoint_commit is None
            and other.binding is None
        )
        assert observed_cancel == [True]
    finally:
        release.set()
        commands.close()
        server.join(5)
        input_pipe.close()
        output_pipe.close()
        replies.close()
    assert not server.is_alive()
    assert {
        path: (case.vault / path).read_bytes() for path in case.current
    } == case.current


@pytest.mark.parametrize("sequence", (1, 3))
def test_stream_replay_or_sequence_gap_poisons_before_producer_dispatch(
    tmp_path, sequence
):
    context, case = context_case(tmp_path)
    output = io.BytesIO()
    worker = UpdateWorker(context=context, output=output)
    first = WorkerRequest(
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
    worker.handle(first)
    before = output.getvalue()
    replay = first.model_copy(update={"request_id": str(uuid4()), "sequence": sequence})
    with pytest.raises(ProtocolFailure):
        worker.handle(replay)
    assert worker.closed and output.getvalue() == before


def test_poisoned_hidden_child_is_drained_through_eof_without_admitting_result(
    tmp_path,
):
    import sys
    from pathlib import Path

    from brz2obsidian.application.transport import Supervisor

    source = tmp_path / "child-source"
    package = source / "brz2obsidian"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    marker = tmp_path / "writer-completed"
    (package / "worker.py").write_text(
        "import os,sys,time\nfrom threading import Thread\nfrom pathlib import Path\n"
        "def watchdog():\n time.sleep(4)\n os._exit(4)\n"
        "Thread(target=watchdog,daemon=True).start()\n"
        "sys.stdin.buffer.readline()\n"
        "sys.stdout.buffer.write(b'invalid-frame\\n');sys.stdout.buffer.flush()\n"
        "sys.stdout.buffer.write(b'x'*(2*1024*1024));sys.stdout.buffer.flush()\n"
        + "Path("
        + repr(str(marker))
        + ").write_text('drained')\n",
        encoding="utf-8",
    )
    uncertain = Event()
    observations = []

    def on_uncertain():
        observations.append(channel.diagnostics)
        uncertain.set()

    channel = Supervisor(Path(sys.executable), source).open_update(
        on_uncertain=on_uncertain
    )
    try:
        terminal = channel.run(
            WorkerRequest(
                request_id=str(uuid4()),
                operation="update",
                sequence=1,
                arguments={
                    "command": "prepare",
                    "vault": str(tmp_path / "vault"),
                    "selection_id": str(uuid4()),
                    "kind": "onboarding",
                    "source": None,
                },
            )
        )
        assert terminal.phase == "may_have_executed" and terminal.response is None
        assert channel.poisoned and uncertain.wait(1)
        assert observations[0].first_failure == "invalid_outer_frame"
        assert channel.diagnostics.first_failure == "invalid_outer_frame"
    finally:
        channel.close()
    assert marker.read_text(encoding="utf-8") == "drained"
    snapshot = channel.diagnostics
    assert snapshot.first_failure == "invalid_outer_frame"
    assert snapshot.stdout_bytes == 14 + 2 * 1024 * 1024
    assert snapshot.stdout_frames == 1 and snapshot.largest_frame_bytes == 14
    assert snapshot.stderr_drain_finished and not snapshot.stderr_drain_error
    assert channel.process_status == 0


def test_hidden_child_diagnostics_are_immutable_and_drain_private_stderr(tmp_path):
    from dataclasses import FrozenInstanceError, asdict

    from brz2obsidian.application.contracts import WorkerResponse
    from brz2obsidian.application.update_context_contracts import UpdateContextResult

    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="update",
        sequence=1,
        arguments={"command": "close", "binding": None, "choice": "discard"},
    )
    response = WorkerResponse(
        request_id=request.request_id,
        operation="update",
        sequence=1,
        result=UpdateContextResult(
            status="declined", code="context_closed", kind="onboarding"
        ),
    )
    frames = (encode_response(response), encode_end(response))
    private_stderr = b"PRIVATE-SOURCE-CANARY\n" * 8192
    uncertain = Event()
    channel = controlled_update_channel(
        tmp_path,
        f"sys.stderr.buffer.write({private_stderr!r});sys.stderr.buffer.flush()\n"
        f"sys.stdout.buffer.write({b''.join(frames)!r});sys.stdout.buffer.flush()\n",
        on_uncertain=uncertain.set,
    )
    try:
        initial = channel.diagnostics
        assert initial.first_failure is None and initial.stdout_bytes == 0
        terminal = channel.run(request)
        assert terminal.phase == "completed" and terminal.response == response
    finally:
        channel.close()
    snapshot = channel.diagnostics
    assert channel.process_status == 0 and not uncertain.is_set()
    assert asdict(snapshot) == {
        "first_failure": None,
        "stdout_bytes": sum(map(len, frames)),
        "stdout_frames": 2,
        "largest_frame_bytes": max(map(len, frames)),
        "stderr_bytes": len(private_stderr),
        "stderr_drain_finished": True,
        "stderr_drain_error": False,
        "worker_protocol_error": None,
    }
    assert "PRIVATE-SOURCE-CANARY" not in repr(snapshot)
    assert initial.stdout_bytes == 0 and channel.diagnostics == snapshot
    with pytest.raises(FrozenInstanceError):
        snapshot.first_failure = "caller_close"


def controlled_update_channel(tmp_path, body, *, on_uncertain):
    import sys
    from pathlib import Path

    from brz2obsidian.application.transport import Supervisor

    source = tmp_path / "child-source"
    package = source / "brz2obsidian"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "worker.py").write_text(
        "import os,sys,time\nfrom threading import Thread\n"
        "def watchdog():\n time.sleep(4)\n os._exit(4)\n"
        "Thread(target=watchdog,daemon=True).start()\n"
        "request = sys.stdin.buffer.readline()\n" + body,
        encoding="utf-8",
    )
    return Supervisor(Path(sys.executable), source).open_update(
        on_uncertain=on_uncertain
    )


def test_hidden_child_observes_oversized_frame_without_admitting_it(tmp_path):
    uncertain = Event()
    channel = controlled_update_channel(
        tmp_path,
        "sys.stdout.buffer.write(b'x'*(16*1024*1024+1));sys.stdout.buffer.flush()\n"
        "sys.stdin.buffer.read()\n",
        on_uncertain=uncertain.set,
    )
    try:
        terminal = channel.run(
            WorkerRequest(
                request_id=str(uuid4()),
                operation="update",
                sequence=1,
                arguments={"command": "close", "binding": None, "choice": "discard"},
            )
        )
        assert terminal.phase == "may_have_executed" and terminal.response is None
        assert channel.poisoned and uncertain.wait(1)
        assert channel.diagnostics.first_failure == "oversized_frame"
    finally:
        channel.close()
    snapshot = channel.diagnostics
    assert snapshot.first_failure == "oversized_frame"
    assert snapshot.stdout_bytes == snapshot.largest_frame_bytes == 16 * 1024 * 1024 + 1
    assert snapshot.stdout_frames == 1 and channel.process_status == 0


def test_hidden_child_rejects_uncorrelated_output_without_restoring_authority(tmp_path):
    frame = b'{"request_id":"11111111-1111-4111-8111-111111111111"}\n'
    uncertain = Event()
    channel = controlled_update_channel(
        tmp_path,
        f"sys.stdout.buffer.write({frame!r});sys.stdout.buffer.flush()\n"
        "remaining = sys.stdin.buffer.read()\n"
        "sys.exit(8 if remaining else 0)\n",
        on_uncertain=uncertain.set,
    )
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="update",
        sequence=1,
        arguments={"command": "close", "binding": None, "choice": "discard"},
    )
    try:
        terminal = channel.run(request)
        assert (
            terminal.phase == "may_have_executed"
            and terminal.code == "protocol_failure"
        )
        assert terminal.response is None and uncertain.wait(1)
        snapshot = channel.diagnostics
        assert snapshot.first_failure == "unexpected_request"
        assert channel.diagnostics == snapshot
        refused = channel.run(request)
        assert refused.phase == "may_have_executed" and refused.response is None
    finally:
        channel.close()
    assert channel.diagnostics.first_failure == "unexpected_request"
    assert channel.diagnostics.stdout_bytes == len(frame)
    assert channel.process_status == 0


def test_hidden_child_observes_coarse_decoder_rejection(tmp_path):
    uncertain = Event()
    channel = controlled_update_channel(
        tmp_path,
        "import json\n"
        "value = {'request_id':json.loads(request)['request_id'],"
        "'schema':'PRIVATE-DECODER-REJECTION-CANARY'}\n"
        "sys.stdout.buffer.write(json.dumps(value).encode()+b'\\n');sys.stdout.buffer.flush()\n"
        "sys.stdin.buffer.read()\n",
        on_uncertain=uncertain.set,
    )
    try:
        terminal = channel.run(
            WorkerRequest(
                request_id=str(uuid4()),
                operation="update",
                sequence=1,
                arguments={"command": "close", "binding": None, "choice": "discard"},
            )
        )
        assert terminal.phase == "may_have_executed" and terminal.response is None
        assert uncertain.wait(1)
        assert channel.diagnostics.first_failure == "decoder_rejected"
        assert "PRIVATE-DECODER-REJECTION-CANARY" not in repr(channel.diagnostics)
    finally:
        channel.close()
    assert channel.diagnostics.first_failure == "decoder_rejected"
    assert channel.diagnostics.stdout_frames == 1 and channel.process_status == 0


def test_hidden_child_reports_unsealed_eof_and_actual_exit(tmp_path):
    from brz2obsidian.application.contracts import ProtocolError, WorkerResponse

    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="update",
        sequence=1,
        arguments={"command": "close", "binding": None, "choice": "discard"},
    )
    response = WorkerResponse(
        request_id=request.request_id,
        operation="update",
        sequence=1,
        protocol_error=ProtocolError(
            code="internal_error", message="The operation could not complete."
        ),
    )
    frame = encode_response(response)
    uncertain = Event()
    channel = controlled_update_channel(
        tmp_path,
        f"sys.stdout.buffer.write({frame!r});sys.stdout.buffer.flush()\nsys.exit(7)\n",
        on_uncertain=uncertain.set,
    )
    try:
        terminal = channel.run(request)
        assert terminal.phase == "may_have_executed" and terminal.response is None
        assert uncertain.wait(1)
        assert channel.diagnostics.first_failure == "unexpected_eof"
        assert channel.diagnostics.worker_protocol_error is None
    finally:
        channel.close()
    assert channel.diagnostics.first_failure == "unexpected_eof"
    assert channel.diagnostics.stdout_bytes == len(frame)
    assert channel.process_status == 7


def test_hidden_child_retains_only_sealed_safe_protocol_error(tmp_path):
    from dataclasses import asdict

    from brz2obsidian.application.contracts import ProtocolError, WorkerResponse

    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="update",
        sequence=1,
        arguments={"command": "close", "binding": None, "choice": "discard"},
    )
    response = WorkerResponse(
        request_id=request.request_id,
        operation="update",
        sequence=1,
        protocol_error=ProtocolError(
            code="internal_error", message="The operation could not complete."
        ),
    )
    frames = encode_response(response) + encode_end(response)
    uncertain = Event()
    observations = []

    def on_uncertain():
        observations.append(channel.diagnostics)
        uncertain.set()

    channel = controlled_update_channel(
        tmp_path,
        f"sys.stdout.buffer.write({frames!r});sys.stdout.buffer.flush()\n"
        "sys.stdin.buffer.read()\n",
        on_uncertain=on_uncertain,
    )
    try:
        terminal = channel.run(request)
        assert (
            terminal.phase == "may_have_executed" and terminal.code == "worker_failure"
        )
        assert terminal.response is None and uncertain.wait(1)
        snapshot = channel.diagnostics
        assert snapshot.first_failure == "worker_protocol_error"
        assert snapshot.worker_protocol_error == "internal_error"
        assert observations[0] == snapshot
        assert "The operation could not complete." not in repr(asdict(snapshot))
        assert "MemoryError" not in repr(snapshot)
    finally:
        channel.close()
    assert channel.diagnostics.first_failure == "worker_protocol_error"
    assert channel.diagnostics.worker_protocol_error == "internal_error"
    assert channel.process_status == 0


def test_hidden_child_observes_caller_close_without_prior_fault(tmp_path):
    uncertain = Event()
    observations = []

    def on_uncertain():
        observations.append(channel.diagnostics)
        uncertain.set()

    channel = controlled_update_channel(
        tmp_path, "sys.exit(0)\n", on_uncertain=on_uncertain
    )
    try:
        initial = channel.diagnostics
        assert initial.first_failure is None and channel.diagnostics == initial
        assert not channel.poisoned and not channel.closed and not uncertain.is_set()
        with pytest.raises(AttributeError):
            channel.diagnostics = initial
        assert channel.diagnostics == initial
        assert not channel.poisoned and not channel.closed and not uncertain.is_set()
    finally:
        channel.close()
    assert uncertain.is_set() and observations[0].first_failure == "caller_close"
    snapshot = channel.diagnostics
    assert snapshot.first_failure == "caller_close" and snapshot.stdout_bytes == 0
    assert snapshot.stderr_drain_finished and not snapshot.stderr_drain_error
    assert initial.first_failure is None and channel.process_status == 0


def test_hidden_child_progress_observer_failure_cannot_admit_result(tmp_path):
    from brz2obsidian.application.update_stream import WorkerProgress, encode_progress
    from brz2obsidian.application.vault_progress_contracts import VaultProgress

    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="update",
        sequence=1,
        arguments={
            "command": "prepare",
            "vault": str(tmp_path / "vault"),
            "selection_id": str(uuid4()),
            "kind": "onboarding",
            "source": None,
        },
    )
    progress = WorkerProgress(
        request_id=request.request_id,
        sequence=1,
        ordinal=1,
        value=VaultProgress(phase="current_inspection"),
    )
    frame = encode_progress(progress)
    uncertain = Event()
    delivered = []
    channel = controlled_update_channel(
        tmp_path,
        f"sys.stdout.buffer.write({frame!r});sys.stdout.buffer.flush()\n"
        "sys.stdin.buffer.read()\n",
        on_uncertain=uncertain.set,
    )

    def on_progress(actual, observed):
        delivered.append((actual, observed, channel.diagnostics))
        raise RuntimeError("PRIVATE-PROGRESS-OBSERVER-CANARY")

    try:
        terminal = channel.run(request, on_progress=on_progress)
        assert terminal.phase == "may_have_executed" and terminal.response is None
        assert uncertain.wait(1)
        assert len(delivered) == 1
        actual, observed, before_failure = delivered[0]
        assert actual == request and observed == progress
        assert before_failure.first_failure is None
        assert channel.diagnostics.first_failure == "observer_failure"
        assert "PRIVATE-PROGRESS-OBSERVER-CANARY" not in repr(channel.diagnostics)
    finally:
        channel.close()
    assert channel.diagnostics.first_failure == "observer_failure"
    assert channel.process_status == 0


def test_hidden_child_dispatch_observer_failure_cannot_admit_result(tmp_path):
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="update",
        sequence=1,
        arguments={"command": "close", "binding": None, "choice": "discard"},
    )
    uncertain = Event()
    dispatched = []
    channel = controlled_update_channel(
        tmp_path, "sys.stdin.buffer.read()\n", on_uncertain=uncertain.set
    )

    def on_dispatched(actual):
        dispatched.append((actual, channel.diagnostics))
        raise ValueError("PRIVATE-DISPATCH-OBSERVER-CANARY")

    try:
        terminal = channel.run(request, on_dispatched=on_dispatched)
        assert terminal.phase == "may_have_executed" and terminal.response is None
        assert uncertain.wait(1)
        assert len(dispatched) == 1 and dispatched[0][0] == request
        assert dispatched[0][1].first_failure is None
        assert channel.diagnostics.first_failure == "observer_failure"
        assert "PRIVATE-DISPATCH-OBSERVER-CANARY" not in repr(channel.diagnostics)
    finally:
        channel.close()
    assert channel.diagnostics.first_failure == "observer_failure"
    assert channel.process_status == 0


def test_update_channel_refuses_other_operation_with_safe_dispatch_failure(tmp_path):
    from brz2obsidian.application.contracts import InspectArguments

    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="inspect",
        arguments=InspectArguments(source=str(tmp_path / "unopened.brz")),
    )
    uncertain = Event()
    dispatched = []
    channel = controlled_update_channel(
        tmp_path, "sys.exit(8 if request else 0)\n", on_uncertain=uncertain.set
    )
    try:
        terminal = channel.run(request, on_dispatched=dispatched.append)
        assert (
            terminal.phase == "may_have_executed"
            and terminal.code == "protocol_failure"
        )
        assert terminal.response is None and uncertain.wait(1)
        assert channel.diagnostics.first_failure == "dispatch_failure"
        assert not dispatched and channel.diagnostics.stdout_bytes == 0
    finally:
        channel.close()
    assert channel.diagnostics.first_failure == "dispatch_failure"
    assert channel.process_status == 0


def test_prestart_prepare_cancel_is_bound_before_any_producer_io(tmp_path, monkeypatch):
    import json

    context, case = context_case(tmp_path)
    accessed = []
    acknowledged = Event()
    original_inputs = type(case.operations).inspect_update_inputs

    def forbid_io(self, *args, **kwargs):
        accessed.append(acknowledged.is_set())
        return original_inputs(self, *args, **kwargs)

    monkeypatch.setattr(type(case.operations), "inspect_update_inputs", forbid_io)

    class ObservedOutput(io.BytesIO):
        def write(self, raw):
            value = json.loads(raw)
            if value.get("result", {}).get("code") == "cancellation_requested":
                acknowledged.set()
            return super().write(raw)

    output = ObservedOutput()
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
    cancel = WorkerRequest(
        request_id=str(uuid4()),
        operation="update",
        sequence=2,
        arguments={
            "command": "cancel",
            "binding": None,
            "vault": str(case.vault),
            "selection_id": prepare.arguments.selection_id,
            "target_request_id": prepare.request_id,
            "target_sequence": 1,
        },
    )
    worker.serve(io.BytesIO(encode_request(cancel)), first=prepare)
    decoders = {row.request_id: WorkerStreamDecoder(row) for row in (prepare, cancel)}
    results = {}
    for frame in output.getvalue().splitlines(keepends=True):
        identity = json.loads(frame)["request_id"]
        result = decoders[identity].feed(frame)
        if result is not None:
            results[identity] = result.result
    if results[cancel.request_id].code == "cancellation_requested":
        assert results[prepare.request_id].status == "cancelled_before_publication"
        assert results[prepare.request_id].publication == "not_published"
    else:
        # A completed preparation may win scheduling; a late control cannot
        # retroactively cancel it. No artificial wait is added to production.
        assert results[cancel.request_id].code == "context_changed"
        assert results[prepare.request_id].status == "prepared_review"
    assert not any(accessed), (
        "No native inspection may start after cancellation was accepted"
    )


def test_cancel_cannot_match_another_sequence_reusing_request_identity(tmp_path):
    from pydantic import ValidationError

    # The wire must carry the actual targeted stream generation as well as UUID.
    with pytest.raises(ValidationError):
        WorkerRequest(
            request_id=str(uuid4()),
            operation="update",
            sequence=2,
            arguments={
                "command": "cancel",
                "binding": None,
                "vault": str(tmp_path),
                "selection_id": str(uuid4()),
                "target_request_id": str(uuid4()),
            },
        )
