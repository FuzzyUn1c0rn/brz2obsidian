"""Actual output details travel through the bound worker stream without payloads."""

import io
from hashlib import sha256
from itertools import count
from uuid import uuid4

from brz2obsidian.application.contracts import WorkerRequest
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.protocol import decode_request, encode_request
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.update_contracts import UpdateResult
from brz2obsidian.application.update_stream import WorkerStreamDecoder
from brz2obsidian.application.update_worker import UpdateWorker
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_attachments import attachment_request


def test_bound_worker_pages_binary_output_metadata_and_refuses_retired_bindings(
    tmp_path,
):
    vault = tmp_path / "vault"
    vault.mkdir()
    prepared = preparation(attachment_request()).model_copy(
        update={"vault": str(vault)}
    )

    class NativePreparation(Operations):
        # Controlled outer preparation port, returning a real canonical Core
        # review. This owns wire/context delivery, not physical Native admission.
        def prepare_update(self, path, source, **kwargs):
            assert path == str(vault)
            return UpdateResult(
                status="prepared_review",
                code="prepared",
                kind="source_update",
                preparation=prepared,
                changes=1,
                unresolved=1,
                history_retained=True,
                checkpoint_commit=prepared.locator.commit,
            )

    output = io.BytesIO()
    worker = UpdateWorker(
        context=UpdateContext(operations=NativePreparation()), output=output
    )
    sequence = count(1)

    def call(arguments):
        request = WorkerRequest(
            request_id=str(uuid4()),
            sequence=next(sequence),
            operation="update",
            arguments=arguments,
        )
        worker.handle(decode_request(encode_request(request)))
        wire = output.getvalue()
        output.seek(0)
        output.truncate()
        decoder = WorkerStreamDecoder(request)
        terminal = None
        for frame in wire.splitlines(keepends=True):
            received = decoder.feed(frame)
            if received is not None:
                terminal = received
        decoder.eof()
        assert decoder.sealed and not decoder.poisoned and terminal is not None
        assert terminal.protocol_error is None
        assert b"attachment_candidate" not in wire
        return terminal.result, wire

    opened, _ = call(
        {
            "command": "prepare",
            "kind": "source_update",
            "vault": str(vault),
            "source": str(tmp_path / "incoming.brz"),
            "selection_id": str(uuid4()),
        }
    )
    binding = opened.binding
    assert binding is not None and not opened.ready
    try:
        choices, _ = call({"command": "choices", "binding": binding})
        (offer,) = choices.offers
        assert offer.detail_count == 4
        foreign = binding.model_copy(update={"selection_id": str(uuid4())})
        rejected, _ = call(
            {
                "command": "choice_details",
                "binding": foreign,
                "requirement_id": offer.requirement_id,
            }
        )
        assert rejected.code == "context_changed"
        rows = []
        for offset in (0, 2):
            page, wire = call(
                {
                    "command": "choice_details",
                    "binding": binding,
                    "requirement_id": offer.requirement_id,
                    "offset": offset,
                    "limit": 2,
                }
            )
            assert page.binding == binding and page.total_choice_details == 4
            assert page.next_choice_detail_offset == (2 if offset == 0 else None)
            assert len(page.choice_details) == 2
            assert b"AGF1dGhvcmVk" not in wire and b"YWJj" not in wire
            rows.extend(page.choice_details)
        incoming_hash = (
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )
        current_hash = sha256(b"\x00authored").hexdigest()
        assert [(row.choice, row.path, row.size, row.sha256) for row in rows] == [
            ("current", "Assets/data.bin", 9, current_hash),
            ("incoming", "Assets/data.bin", 3, incoming_hash),
            ("both", "Assets/data.bin", 9, current_hash),
            ("both", "Assets/data (incoming-ba7816bf).bin", 3, incoming_hash),
        ]
        assert all(row.kind == "attachment_output" for row in rows)
        assert [row.target_id for row in rows] == [
            "resource:payload",
            "resource:payload",
            "resource:payload",
            "resource:payload:incoming:" + incoming_hash,
        ]
        chosen, _ = call(
            {
                "command": "choose",
                "binding": binding,
                "requirement_id": offer.requirement_id,
                "choice": "both",
                "assumptions_digest": offer.assumptions_digest,
            }
        )
        old_binding, binding = binding, chosen.binding
        assert chosen.ready and binding is not None and binding != old_binding
        stale, _ = call(
            {
                "command": "choice_details",
                "binding": old_binding,
                "requirement_id": offer.requirement_id,
            }
        )
        assert stale.code == "context_changed"
        current, _ = call(
            {
                "command": "choice_details",
                "binding": binding,
                "requirement_id": offer.requirement_id,
                "limit": 2,
            }
        )
        assert current.binding == binding and not current.ready
        assert current.total_choice_details == 4 and len(current.choice_details) == 2
        continued, _ = call(
            {"command": "close", "binding": binding, "choice": "continue"}
        )
        assert continued.code == "continue_review" and continued.ready
        assert continued.binding == binding
        assert list(vault.iterdir()) == []
    finally:
        call({"command": "close", "binding": binding, "choice": "discard"})
