"""Live controls reach blocked native I/O without changing publication truth."""

import io
import os
from threading import Event, Thread
from uuid import uuid4

import pytest

from brz2obsidian.application.contracts import WorkerRequest
from brz2obsidian.application.protocol import ProtocolFailure, encode_request
from brz2obsidian.application.update_stream import WorkerStreamDecoder
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
            "review_generation": None,
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
    channel = Supervisor(Path(sys.executable), source).open_update(
        on_uncertain=uncertain.set
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
    finally:
        channel.close()
    assert marker.read_text(encoding="utf-8") == "drained"


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
