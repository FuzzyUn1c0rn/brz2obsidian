"""Snapshot control reports actual native storage facts after an atomic step."""

import os
from threading import Event, Thread
from uuid import uuid4

import pytest

from brz2obsidian.application.checkpoint_contracts import CheckpointResult
from brz2obsidian.application.contracts import WorkerRequest, WorkerResponse
from brz2obsidian.application.protocol import (
    ProtocolFailure,
    encode_request,
    encode_response,
)
from brz2obsidian.application.update_stream import WorkerStreamDecoder, encode_end
from brz2obsidian.application.update_worker import UpdateWorker
from brz2obsidian.application.vault_progress_contracts import VaultProgress
from brz2obsidian.core import load_review, save_review
from tests.application.test_update_context import context_case


@pytest.mark.parametrize("outcome", ("captured", "possible_objects"))
def test_save_control_waits_for_atomic_capture_and_retains_actual_storage_facts(
    tmp_path, monkeypatch, outcome
):
    context, case = context_case(tmp_path)
    opened = context.prepare(
        case.vault, selection_id=str(uuid4()), kind="attachment_cleanup"
    )
    assert opened.binding.checkpoint_generation == 2 and not opened.ready
    entered, release, observer_entered = Event(), Event(), Event()
    captured = []

    def native_snapshot(
        self,
        vault,
        source,
        *,
        review,
        source_binding,
        observed_source,
        progress=None,
        **kwargs,
    ):
        entered.set()
        assert progress is not None, "The actual snapshot boundary needs its observer"
        progress(VaultProgress(phase="snapshot_preparation"))
        observer_entered.set()
        assert release.wait(5), (
            "Control must be acknowledged during the indivisible capture"
        )
        checkpoint = case.history.checkpoint
        if outcome == "captured":
            saved = save_review(review)
            assert saved.status == "saved"
            loaded = load_review(saved.record.model_dump_json())
            assert loaded.status == "loaded" and not loaded.loaded.saved.plan.ready
            checkpoint.review = loaded.loaded
            checkpoint.locator = checkpoint.locator.model_copy(
                update={"commit": "c" * 40, "generation": 3}
            )
            checkpoint.manifest.boundary = "local"
            checkpoint.manifest.reviewed_source = source_binding
            checkpoint.manifest.observed_source = observed_source
        result = CheckpointResult(
            schema_id="brz2obsidian.checkpoint-result",
            schema_version=1,
            status="captured" if outcome == "captured" else "failed",
            code="captured" if outcome == "captured" else "snapshot_failed",
            commit=checkpoint.locator.commit if outcome == "captured" else None,
            ref=checkpoint.locator.association.ref,
            history_retained=outcome == "captured",
            objects_written=True,
            object_storage="verified" if outcome == "captured" else "possible",
            authored_files_changed=False,
            message="External indivisible native snapshot outcome.",
            locator=checkpoint.locator if outcome == "captured" else None,
        )
        captured.append(result)
        return result

    monkeypatch.setattr(type(case.operations), "capture_checkpoint", native_snapshot)
    input_read, input_write = os.pipe()
    output_read, output_write = os.pipe()
    incoming, commands = (
        os.fdopen(input_read, "rb"),
        os.fdopen(input_write, "wb", buffering=0),
    )
    replies, outgoing = (
        os.fdopen(output_read, "rb"),
        os.fdopen(output_write, "wb", buffering=0),
    )
    request = WorkerRequest(
        operation="update",
        request_id=str(uuid4()),
        sequence=1,
        arguments={"command": "save", "binding": opened.binding},
    )
    cancel = WorkerRequest(
        operation="update",
        request_id=str(uuid4()),
        sequence=2,
        arguments={
            "command": "cancel",
            "binding": opened.binding,
            "target_request_id": request.request_id,
            "target_sequence": 1,
        },
    )
    worker = UpdateWorker(context=context, output=outgoing)
    server = Thread(target=worker.serve, args=(incoming,), daemon=True)
    server.start()
    decoders = {row.request_id: WorkerStreamDecoder(row) for row in (request, cancel)}
    results, observed = {}, []

    def read_one():
        import json

        frame = replies.readline()
        identity = json.loads(frame)["request_id"]
        decoder = decoders[identity]
        terminal = decoder.feed(frame)
        if decoder.progress is not None:
            observed.append(decoder.progress.value.phase)
        if terminal is not None:
            assert terminal.protocol_error is None
            results[identity] = terminal.result

    try:
        commands.write(encode_request(request))
        assert entered.wait(4)
        assert observer_entered.wait(3), (
            "Snapshot observer was not forwarded to native I/O"
        )
        commands.write(encode_request(cancel))
        while (
            cancel.request_id not in results or "snapshot_preparation" not in observed
        ):
            read_one()
        assert (
            results[cancel.request_id].code == "cancellation_requested" and not captured
        )
        release.set()
        while request.request_id not in results:
            read_one()
        result = results[request.request_id]
        assert "snapshot_preparation" in observed
        assert result.capture == captured[0]
        assert (
            result.capture.objects_written and not result.capture.authored_files_changed
        )
        assert result.publication in ("not_started", "not_published")
        if outcome == "captured":
            assert result.code == "saved" and result.history_retained
            assert result.capture.object_storage == "verified"
            assert (
                result.binding.checkpoint_generation == 3
                and result.binding.generation == opened.binding.generation
            )
            assert context.page(opened.binding).code == "context_changed"
            import json

            valid = WorkerResponse(
                operation="update",
                request_id=request.request_id,
                sequence=request.sequence,
                result=result,
            )
            baseline = WorkerStreamDecoder(request)
            assert baseline.feed(encode_response(valid)) is None
            assert baseline.feed(encode_end(valid)) == valid
            for contradiction in (
                "history",
                "commit",
                "binding_commit",
                "binding_generation",
                "capture_locator",
            ):
                raw = json.loads(encode_response(valid))
                if contradiction == "history":
                    raw["result"]["history_retained"] = False
                elif contradiction == "commit":
                    raw["result"]["checkpoint_commit"] = "d" * 40
                elif contradiction == "capture_locator":
                    raw["result"]["capture"]["commit"] = "d" * 40
                    raw["result"]["checkpoint_commit"] = "d" * 40
                elif contradiction == "binding_commit":
                    raw["result"]["binding"]["checkpoint_commit"] = "d" * 40
                else:
                    raw["result"]["binding"]["checkpoint_generation"] = 4
                decoder = WorkerStreamDecoder(request)
                with pytest.raises(ProtocolFailure):
                    decoder.feed(json.dumps(raw).encode("utf-8") + b"\n")
                assert decoder.poisoned and not decoder.sealed
        else:
            assert (
                result.code == "snapshot_failed"
                and result.capture.object_storage == "possible"
            )
            assert not result.capture.history_retained and not result.ready
        close = WorkerRequest(
            operation="update",
            request_id=str(uuid4()),
            sequence=3,
            arguments={
                "command": "close",
                "binding": result.binding,
                "choice": "discard",
            },
        )
        decoders[close.request_id] = WorkerStreamDecoder(close)
        commands.write(encode_request(close))
        while close.request_id not in results:
            read_one()
        assert results[close.request_id].code == "context_closed"
        assert results[close.request_id].capture == captured[0]
        if outcome == "captured":
            valid = WorkerResponse(
                operation="update",
                request_id=close.request_id,
                sequence=3,
                result=results[close.request_id],
            )
            baseline = WorkerStreamDecoder(close)
            assert baseline.feed(encode_response(valid)) is None
            assert baseline.feed(encode_end(valid)) == valid
            raw = json.loads(encode_response(valid))
            raw["result"]["capture"]["commit"] = "d" * 40
            raw["result"]["checkpoint_commit"] = "d" * 40
            rejected = WorkerStreamDecoder(close)
            with pytest.raises(ProtocolFailure):
                rejected.feed(json.dumps(raw).encode("utf-8") + b"\n")
            assert rejected.poisoned and not rejected.sealed
    finally:
        release.set()
        commands.close()
        server.join(10)
        incoming.close()
        outgoing.close()
        replies.close()
    assert not server.is_alive()
    assert {
        path: (case.vault / path).read_bytes() for path in case.current
    } == case.current


@pytest.mark.parametrize("boundary", ("prestart", "reobserving"))
def test_save_cancellation_before_capture_preserves_review_without_native_writes(
    tmp_path, monkeypatch, boundary
):
    from contextlib import contextmanager

    context, case = context_case(tmp_path)
    opened = context.prepare(
        case.vault, selection_id=str(uuid4()), kind="attachment_cleanup"
    )
    entered, release, stop = Event(), Event(), Event()
    reads, captures, results, failures = [], [], [], []
    actual_read = type(case.operations).inspect_update_inputs

    @contextmanager
    def native_read(self, *args, **kwargs):
        reads.append(True)
        assert boundary != "prestart", (
            "Prestart cancellation cannot inspect native inputs"
        )
        with actual_read(self, *args, **kwargs) as observation:
            entered.set()
            assert release.wait(4)
            yield observation

    def capture(self, *args, **kwargs):
        captures.append(True)
        raise AssertionError(
            "Cancellation before atomic capture must not start native writes"
        )

    monkeypatch.setattr(type(case.operations), "inspect_update_inputs", native_read)
    monkeypatch.setattr(type(case.operations), "capture_checkpoint", capture)
    if boundary == "prestart":
        stop.set()
        try:
            results.append(context.save(opened.binding, cancel=stop.is_set))
        except Exception as error:  # noqa: BLE001 -- preserve public boundary failure as the assertion.
            failures.append(error)
    else:
        import json

        input_read, input_write = os.pipe()
        output_read, output_write = os.pipe()
        incoming, commands = (
            os.fdopen(input_read, "rb"),
            os.fdopen(input_write, "wb", buffering=0),
        )
        replies, outgoing = (
            os.fdopen(output_read, "rb"),
            os.fdopen(output_write, "wb", buffering=0),
        )
        request = WorkerRequest(
            operation="update",
            request_id=str(uuid4()),
            sequence=1,
            arguments={"command": "save", "binding": opened.binding},
        )
        cancel = WorkerRequest(
            operation="update",
            request_id=str(uuid4()),
            sequence=2,
            arguments={
                "command": "cancel",
                "binding": opened.binding,
                "target_request_id": request.request_id,
                "target_sequence": 1,
            },
        )
        decoders = {
            row.request_id: WorkerStreamDecoder(row) for row in (request, cancel)
        }
        replies_by_id = {}

        def read_one():
            frame = replies.readline()
            identity = json.loads(frame)["request_id"]
            reply = decoders[identity].feed(frame)
            if reply is not None:
                assert reply.protocol_error is None
                replies_by_id[identity] = reply.result

        worker = UpdateWorker(context=context, output=outgoing)
        thread = Thread(target=worker.serve, args=(incoming,), daemon=True)
        thread.start()
        try:
            commands.write(encode_request(request))
            assert entered.wait(3), "The actual native input read was not reached"
            commands.write(encode_request(cancel))
            while cancel.request_id not in replies_by_id:
                read_one()
            assert (
                replies_by_id[cancel.request_id].code == "cancellation_requested"
                and not captures
            )
            release.set()
            while request.request_id not in replies_by_id:
                read_one()
            results.append(replies_by_id[request.request_id])
        finally:
            release.set()
            commands.close()
            thread.join(10)
            incoming.close()
            outgoing.close()
            replies.close()
        assert not thread.is_alive()
    assert not failures and len(results) == 1
    result = results[0]
    assert (
        result.status == "cancelled_before_publication"
        and result.code == "cancelled_before_snapshot"
    )
    assert not result.ready and result.binding is not None
    assert (
        result.binding.proposal_id == opened.binding.proposal_id
        and result.binding.generation == opened.binding.generation
    )
    assert (
        result.history_retained
        and result.checkpoint_commit == opened.binding.checkpoint_commit
    )
    assert result.publication == "not_published" and not captures
    assert reads == ([] if boundary == "prestart" else [True])
    assert {
        path: (case.vault / path).read_bytes() for path in case.current
    } == case.current
