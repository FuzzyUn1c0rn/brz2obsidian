"""External output pressure cannot block native cooperative control."""

import json
import os
import time
from itertools import pairwise
from threading import Event, Thread
from uuid import uuid4

import pytest

from brz2obsidian.application.contracts import WorkerRequest
from brz2obsidian.application.protocol import ProtocolFailure, encode_request
from brz2obsidian.application.update_stream import WorkerStreamDecoder
from brz2obsidian.application.update_worker import UpdateWorker
from brz2obsidian.application.vault_progress_contracts import VaultProgress
from brz2obsidian.application.vault_update_contracts import VaultApplyResult
from tests.application.test_history_workflow import operation_state
from tests.application.test_update_context import context_case


def ready_cleanup(tmp_path):
    context, case = context_case(tmp_path)
    opened = context.prepare(
        case.vault, selection_id=str(uuid4()), kind="attachment_cleanup"
    )
    binding = opened.binding
    for item, choice in (("keep-asset", "current"), ("remove-asset", "remove")):
        page = context.page(binding, byte_limit=0)
        change = next(row for row in page.page.items if row.item_id == item)
        offer = next(row for row in page.offers if row.change_id == change.change_id)
        references = (
            context.reference_page(
                binding, requirement_id=offer.requirement_id
            ).references
            if choice == "remove"
            else ()
        )
        chosen = context.choose(
            binding,
            requirement_id=offer.requirement_id,
            choice=choice,
            assumptions_digest=offer.assumptions_digest,
            references=tuple(
                {"reference_id": row.reference_id, "choice": "drop"}
                for row in references
            ),
        )
        assert chosen.code == "accepted"
        binding = chosen.binding
    assert chosen.ready
    case.history.checkpoint.manifest.vault = case.history.admission.inventory
    return context, case, binding


def test_worker_observer_keeps_native_control_live_while_stdout_is_blocked(
    tmp_path, monkeypatch
):
    context, case, binding = ready_cleanup(tmp_path)
    output_entered, release_output, native_reached_end, native_saw_stop = (
        Event(),
        Event(),
        Event(),
        Event(),
    )
    native = VaultApplyResult.model_validate(
        operation_state("incomplete").model_dump()
        | {
            "status": "cancelled",
            "code": "cancelled_after_intent",
            "publication": "partial",
            "history": "intent",
            "review_generation": None,
            "recovery_required": True,
        }
    )

    def external_native(self, *args, cancel=None, progress=None, **kwargs):
        assert progress is not None
        # This external native port models rapid object-verification reports;
        # physical file-transition correctness is owned by test_native_progress.
        for count in range(20000):
            progress(
                VaultProgress(
                    phase="review_validation",
                    completed_units=count,
                    total_units=20000,
                    unit="history_objects",
                )
            )
        native_reached_end.set()
        deadline = time.monotonic() + 5
        while not cancel():
            assert time.monotonic() < deadline, "Output pressure blocked native control"
            time.sleep(0.001)
        native_saw_stop.set()
        return native

    monkeypatch.setattr(type(case.operations), "apply_reviewed_update", external_native)
    input_read, input_write = os.pipe()
    output_read, output_write = os.pipe()
    incoming, commands = (
        os.fdopen(input_read, "rb"),
        os.fdopen(input_write, "wb", buffering=0),
    )
    replies, actual_output = (
        os.fdopen(output_read, "rb"),
        os.fdopen(output_write, "wb", buffering=0),
    )

    class SlowOutput:
        def write(self, raw):
            if (
                json.loads(raw).get("schema") == "brz2obsidian.worker-progress"
                and not release_output.is_set()
            ):
                output_entered.set()
                assert release_output.wait(8), "Owned stdout barrier exhausted"
            return actual_output.write(raw)

        def flush(self):
            return actual_output.flush()

    work = WorkerRequest(
        operation="update",
        request_id=str(uuid4()),
        sequence=1,
        arguments={"command": "apply", "binding": binding},
    )
    cancel = WorkerRequest(
        operation="update",
        request_id=str(uuid4()),
        sequence=2,
        arguments={
            "command": "cancel",
            "binding": binding,
            "target_request_id": work.request_id,
            "target_sequence": 1,
        },
    )
    worker = UpdateWorker(context=context, output=SlowOutput())
    server = Thread(target=worker.serve, args=(incoming,), daemon=True)
    server.start()
    try:
        commands.write(encode_request(work))
        assert native_reached_end.wait(5), "The observer blocked actual native work"
        assert output_entered.wait(1) and not release_output.is_set()
        commands.write(encode_request(cancel))
        assert native_saw_stop.wait(2), "A blocked progress write held the control path"
        release_output.set()
        decoders = {row.request_id: WorkerStreamDecoder(row) for row in (work, cancel)}
        results, frames, elapsed = {}, 0, []
        while len(results) < 2:
            raw = replies.readline()
            frames += 1
            assert frames < 64, "Intermediate observations were retained without bounds"
            value = json.loads(raw)
            decoder = decoders[value["request_id"]]
            result = decoder.feed(raw)
            if decoder.progress is not None:
                elapsed.append(decoder.progress.elapsed_ms)
            if result is not None:
                results[value["request_id"]] = result.result
        assert elapsed and elapsed == sorted(elapsed) and min(elapsed) >= 0
        assert results[cancel.request_id].code == "cancellation_requested"
        assert (
            results[work.request_id].status == "recovery_required"
            and results[work.request_id].publication == "partial"
        )
        assert not results[work.request_id].ready
    finally:
        release_output.set()
        commands.close()
        server.join(10)
        incoming.close()
        actual_output.close()
        replies.close()
    assert not server.is_alive()
    assert {
        path: (case.vault / path).read_bytes() for path in case.current
    } == case.current


@pytest.mark.parametrize("failure", ("write", "flush"))
def test_broken_progress_output_requests_safe_stop_without_authoritative_terminal(
    tmp_path, monkeypatch, failure
):
    context, case, binding = ready_cleanup(tmp_path)
    callback_completed, stopped = Event(), Event()
    captured = bytearray()
    native = VaultApplyResult.model_validate(
        operation_state("incomplete").model_dump()
        | {
            "status": "cancelled",
            "code": "cancelled_after_intent",
            "publication": "partial",
            "history": "intent",
            "review_generation": None,
            "recovery_required": True,
        }
    )

    def external_native(self, *args, cancel=None, progress=None, **kwargs):
        assert progress is not None
        progress(
            VaultProgress(
                phase="publication", completed_units=1, total_units=2, unit="files"
            )
        )
        deadline = time.monotonic() + 3
        while not cancel():
            assert time.monotonic() < deadline, (
                "Broken output did not request a native safe stop"
            )
            time.sleep(0.001)
        stopped.set()
        # Observations after the I/O fault must remain nonthrowing. The native
        # port returns its actual stopped state; transport cannot seal it.
        progress(VaultProgress(phase="final_reporting"))
        callback_completed.set()
        return native

    monkeypatch.setattr(type(case.operations), "apply_reviewed_update", external_native)

    class BrokenOutput:
        def write(self, raw):
            if failure == "write":
                raise OSError("external private output path")
            captured.extend(raw)
            return len(raw)

        def flush(self):
            raise OSError("external private output path")

    request = WorkerRequest(
        operation="update",
        request_id=str(uuid4()),
        sequence=1,
        arguments={"command": "apply", "binding": binding},
    )
    worker = UpdateWorker(context=context, output=BrokenOutput())
    worker.handle(request)
    assert stopped.is_set() and callback_completed.is_set() and worker.closed
    decoder = WorkerStreamDecoder(request)
    for frame in bytes(captured).splitlines(keepends=True):
        assert decoder.feed(frame) is None
    with pytest.raises(ProtocolFailure):
        decoder.eof()
    assert decoder.poisoned and not decoder.sealed
    assert not context.page(binding, byte_limit=0).ready
    assert context.page(binding, byte_limit=0).code == "context_changed"
    assert {
        path: (case.vault / path).read_bytes() for path in case.current
    } == case.current


def test_unblocked_progress_has_a_finite_rate_without_delaying_terminal(
    tmp_path, monkeypatch
):
    context, case, binding = ready_cleanup(tmp_path)
    captured = bytearray()
    written = []
    sent = 0
    native = VaultApplyResult.model_validate(
        operation_state("incomplete").model_dump()
        | {
            "status": "cancelled",
            "code": "cancelled_after_intent",
            "publication": "partial",
            "history": "intent",
            "review_generation": None,
            "recovery_required": True,
        }
    )

    def external_native(self, *args, progress=None, **kwargs):
        nonlocal sent
        assert progress is not None
        deadline = time.monotonic() + 0.35
        while time.monotonic() < deadline:
            progress(
                VaultProgress(
                    phase="review_validation",
                    completed_units=sent,
                    unit="history_objects",
                )
            )
            sent += 1
            time.sleep(0.001)
        return native

    monkeypatch.setattr(type(case.operations), "apply_reviewed_update", external_native)

    class UnblockedOutput:
        def write(self, raw):
            if json.loads(raw).get("schema") == "brz2obsidian.worker-progress":
                written.append(time.monotonic())
            captured.extend(raw)
            return len(raw)

        def flush(self):
            pass

    request = WorkerRequest(
        operation="update",
        request_id=str(uuid4()),
        sequence=1,
        arguments={"command": "apply", "binding": binding},
    )
    UpdateWorker(context=context, output=UnblockedOutput()).handle(request)
    decoder = WorkerStreamDecoder(request)
    observations, result = [], None
    for frame in bytes(captured).splitlines(keepends=True):
        result = decoder.feed(frame)
        if decoder.progress is not None:
            observations.append(decoder.progress)
    assert sent >= 20, "The external producer must actually exceed the delivery rate"
    assert 1 <= len(observations) <= 4, (
        "Progress must be limited to at most ten observations per second"
    )
    assert all(right - left >= 0.1 for left, right in pairwise(written))
    assert (
        result is not None and decoder.sealed and result.result.publication == "partial"
    )
    assert result.result.status == "recovery_required" and not result.result.ready
