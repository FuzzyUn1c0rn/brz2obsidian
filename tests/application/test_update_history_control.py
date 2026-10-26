"""History preparation observes live controls without erasing earlier publication."""

import json
import os
from queue import Queue
from threading import Event, Thread
from uuid import uuid4

import pytest

from brz2obsidian.application.contracts import WorkerRequest
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.protocol import encode_request
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.update_stream import WorkerStreamDecoder
from brz2obsidian.application.update_worker import UpdateWorker
from tests.application.test_history_workflow import absent_history, operation_state, ready_native_recovery


@pytest.mark.parametrize("command", ("prepare_history", "refresh_history"))
def test_worker_history_read_control_retains_native_debt_and_review(tmp_path, command):
    vault = tmp_path / "vault"
    vault.mkdir()
    literal = b"Later authored bytes\r\n"
    (vault / "Personal.md").write_bytes(literal)
    native = ready_native_recovery(direction="finish").native
    observed = operation_state("incomplete")
    entered, release, held = Event(), Event(), Event()
    native_reads = []

    def boundary():
        native_reads.append(True)
        if held.is_set():
            entered.set()
            assert release.wait(5), "History read must retain live control"
        return native

    class NativePorts(Operations):
        def inspect_history(self, path, **kwargs):
            return absent_history()

        def inspect_update_status(self, path):
            return observed

        def prepare_recovery(self, path, *, direction=None):
            assert direction == "finish"
            return boundary()

        def refresh_recovery(self, path, previous):
            assert previous == native
            return boundary()

    context = UpdateContext(operations=NativePorts())
    opened = context.history(str(vault), selection_id=str(uuid4()))
    if command == "refresh_history":
        opened = context.prepare_history(opened.binding, kind="recovery", direction="finish")
    binding = opened.binding
    before_reads = len(native_reads)
    prestart = (
        context.prepare_history(binding, kind="recovery", direction="finish", cancel=lambda: True)
        if command == "prepare_history"
        else context.refresh_history(binding, cancel=lambda: True)
    )
    assert prestart.code == "cancelled_before_history_preparation" and not prestart.ready
    assert prestart.binding == binding and prestart.publication == "partial"
    assert prestart.status == "recovery_required" and prestart.history_retained == opened.history_retained
    assert len(native_reads) == before_reads
    args = {"command": command, "binding": binding}
    if command == "prepare_history":
        args.update(kind="recovery", direction="finish")
    request = WorkerRequest(operation="update", request_id=str(uuid4()), sequence=1, arguments=args)
    cancel = WorkerRequest(operation="update", request_id=str(uuid4()), sequence=2, arguments={
        "command": "cancel", "binding": binding,
        "target_request_id": request.request_id, "target_sequence": 1,
    })
    input_read, input_write = os.pipe()
    output_read, output_write = os.pipe()
    incoming, commands = os.fdopen(input_read, "rb"), os.fdopen(input_write, "wb", buffering=0)
    replies, outgoing = os.fdopen(output_read, "rb"), os.fdopen(output_write, "wb", buffering=0)
    frames = Queue()
    reader = Thread(target=lambda: [frames.put(frame) for frame in iter(replies.readline, b"")], daemon=True)
    worker = UpdateWorker(context=context, output=outgoing)
    server = Thread(target=worker.serve, args=(incoming,), daemon=True)
    decoders = {row.request_id: WorkerStreamDecoder(row) for row in (request, cancel)}
    results, phases = {}, []

    def read_one():
        frame = frames.get(timeout=4)
        decoder = decoders[json.loads(frame)["request_id"]]
        terminal = decoder.feed(frame)
        if decoder.progress is not None:
            phases.append(decoder.progress.value.phase)
        if terminal is not None:
            assert terminal.protocol_error is None
            results[terminal.request_id] = terminal.result

    held.set()
    reader.start()
    server.start()
    try:
        commands.write(encode_request(request))
        assert entered.wait(3)
        commands.write(encode_request(cancel))
        while cancel.request_id not in results:
            read_one()
        assert results[cancel.request_id].code == "cancellation_requested" and not release.is_set()
        while "current_inspection" not in phases:
            read_one()
        release.set()
        while request.request_id not in results:
            read_one()
        result = results[request.request_id]
        assert result.code == "cancelled_after_history_preparation" and not result.ready
        assert result.status == "recovery_required" and result.publication == "partial"
        assert result.history_retained == opened.history_retained
        assert result.binding.operation_id == observed.operation_id
        assert result.binding.operation_generation == 7 and result.binding.review_generation == 3
        assert result.binding != binding
        continued = context.close(result.binding, choice="continue")
        assert not continued.ready and continued.publication == "partial"
        offers = context.history_choices(result.binding)
        assert offers.status == "available"
    finally:
        release.set()
        commands.close()
        server.join(6)
        incoming.close()
        outgoing.close()
        reader.join(3)
        replies.close()
    assert not server.is_alive() and not reader.is_alive()
    assert (vault / "Personal.md").read_bytes() == literal
    assert sorted(path.name for path in vault.iterdir()) == ["Personal.md"]
