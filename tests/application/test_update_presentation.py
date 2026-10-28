"""Producer capabilities and bounded safe response facts cross the public codec."""

from hashlib import sha256
from uuid import uuid4

import pytest
from pydantic import ValidationError

from brz2obsidian.application.contracts import WorkerRequest, WorkerResponse
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.protocol import decode_response, encode_response
from brz2obsidian.application.review_offers import choice_offers
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.update_context_contracts import UpdateContextResult
from tests.application.test_update_context import worker_context_call
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_refresh import two_items
from tests.reconciliation.test_resolution import with_review_links


def literal_operation_result(ready=True):
    facts = two_items()
    currents = tuple(
        row.current.model_copy(
            update={
                "content": row.incoming.model_copy(update={"data": b"Local writing"})
            }
        )
        for row in facts.subjects
    )
    facts = facts.model_copy(
        update={
            "subjects": tuple(
                row.model_copy(update={"current": current})
                for row, current in zip(facts.subjects, currents, strict=True)
            ),
            "identity_inventory": tuple(
                row.model_copy(update={"current": current})
                for row, current in zip(facts.identity_inventory, currents, strict=True)
            ),
        }
    )
    prepared = preparation(with_review_links(facts))
    operations = Operations()
    actual = None
    for offer in tuple(row for row in choice_offers(prepared) if row.domain == "text")[
        : 2 if ready else 1
    ]:
        actual = operations.resolve_update_choice(
            prepared,
            requirement_id=offer.requirement_id,
            choice="current",
            assumptions_digest=offer.assumptions_digest,
        )
        prepared = actual.preparation
    return actual


@pytest.mark.parametrize("ready", (False, True))
def test_live_producer_offers_save_refresh_for_actual_operation_readiness_and_retires_them_for_drafts(
    tmp_path, ready
):
    actual = literal_operation_result(ready)
    prepared = actual.preparation
    assert actual.ready is ready
    # These are real public Operations results, not UI-injected capability tuples.
    vault = tmp_path / "Vault"
    vault.mkdir()
    actual = actual.model_copy(
        update={"preparation": prepared.model_copy(update={"vault": str(vault)})}
    )

    class NativeInput(Operations):
        def prepare_update(self, *args, **kwargs):
            return actual

    context = UpdateContext(operations=NativeInput())
    opened = worker_context_call(
        context,
        {
            "command": "prepare",
            "kind": "source_update",
            "vault": str(vault),
            "source": str(tmp_path / "source.brz"),
            "selection_id": str(uuid4()),
        },
    )
    assert {"save_update", "refresh_update"} <= set(opened.next_actions)
    offer = next(row for row in choice_offers(prepared) if row.domain == "text")
    draft = worker_context_call(
        context,
        {
            "command": "begin_edit",
            "binding": opened.binding,
            "requirement_id": offer.requirement_id,
            "size": 0,
            "sha256": sha256(b"").hexdigest(),
        },
    )
    assert draft.draft_pending and not draft.ready
    assert not {"save_update", "refresh_update"} & set(draft.next_actions)
    discarded = worker_context_call(
        context, {"command": "discard_draft", "binding": draft.binding}
    )
    assert not discarded.draft_pending and discarded.ready is ready
    assert {"save_update", "refresh_update"} <= set(discarded.next_actions)


def test_safe_review_projection_defaults_roundtrip_and_rejects_unbounded_or_unknown_fields(
    tmp_path,
):
    fields = {"status": "refused", "code": "literal_refusal", "kind": "source_update"}
    empty = UpdateContextResult(**fields)
    assert (
        empty.summary == ""
        and empty.findings == ()
        and empty.guidance == ""
        and empty.recovery_gap_count == 0
    )
    safe = UpdateContextResult(
        **fields,
        summary="A safe explicit reason.",
        findings=("known_finding",),
        guidance="Inspect current history.",
        diagnostic_omission=False,
        recovery_gap_count=1,
    )
    request = WorkerRequest(
        operation="update",
        request_id=str(uuid4()),
        sequence=7,
        arguments={
            "command": "load",
            "vault": str(tmp_path / "Vault"),
            "selection_id": str(uuid4()),
        },
    )
    response = WorkerResponse(
        operation="update",
        request_id=request.request_id,
        sequence=request.sequence,
        result=safe,
    )
    assert decode_response(encode_response(response), request).result == safe
    for invalid in (
        {"summary": "x" * 2049},
        {"findings": tuple("f" for _ in range(21))},
        {"findings": ("x" * 161,)},
        {"guidance": "x" * 2049},
        {"private_payload": "not permitted"},
    ):
        with pytest.raises(ValidationError):
            UpdateContextResult(**fields, **invalid)
