"""Explicit shared refresh rebinds a current producer without saving it."""

import faulthandler
import io
import json
import tempfile
from hashlib import sha256
from pathlib import Path
from time import monotonic
from uuid import uuid4

from brz2obsidian.application.checkpoint_contracts import CheckpointRead
from brz2obsidian.application.operations import ApplicationSession
from brz2obsidian.application.protocol import decode_request, encode_request
from brz2obsidian.application.transport import Terminal
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.update_stream import WorkerStreamDecoder
from brz2obsidian.application.update_worker import UpdateWorker
from tests.application.test_onboarding_refresh import two_note_legacy_inputs
from tests.application.test_update_context import (
    worker_context_call as stale_worker_call,
)


def test_worker_refresh_reobserves_current_and_keeps_the_independent_decision(
    tmp_path, monkeypatch, request
):
    operations, vault, source, authored, second = two_note_legacy_inputs(
        tmp_path, monkeypatch
    )
    # Make Current an actual offer for the legacy note-original attachment.
    original_asset = vault / "Attachments/00000002/Notes.md.original"
    original_asset.parent.mkdir(parents=True)
    original_asset.write_bytes(b"Independent authored original asset.\r\n")
    absent = CheckpointRead(
        schema_id="brz2obsidian.checkpoint-read",
        schema_version=1,
        status="absent",
        code="no_owned_checkpoint",
        locator=None,
        manifest=None,
        review=None,
        message="Controlled native absence.",
    )
    monkeypatch.setattr(operations, "read_checkpoint", lambda *args, **kwargs: absent)
    observed_directories = []
    observe = operations.observe_reviewed_source

    def observed_payload(directory, review):
        observed_directories.append(Path(directory))
        return observe(directory, review)

    monkeypatch.setattr(operations, "observe_reviewed_source", observed_payload)
    # Preserve a bounded diagnostic if a real canonical replay exceeds allocation.
    trace = (tmp_path / "068-stack.txt").open("w")
    faulthandler.dump_traceback_later(15, file=trace)

    def stop_trace():
        faulthandler.cancel_dump_traceback_later()
        trace.close()

    request.addfinalizer(stop_trace)
    started_at = monotonic()
    context = UpdateContext(operations=operations)
    session = ApplicationSession()
    selection_id = str(uuid4())
    session.select_update(str(vault), selection_id=selection_id)

    def worker_context_call(producer, arguments):
        phase_log = tmp_path / "068-wire-phases.jsonl"
        with phase_log.open("a") as log:
            log.write(
                json.dumps(
                    {
                        "command": arguments["command"],
                        "phase": "start",
                        "elapsed": monotonic() - started_at,
                    }
                )
                + "\n"
            )
        output = io.BytesIO()
        request = session.start_update(arguments)
        assert request is not None
        UpdateWorker(context=producer, output=output).handle(
            decode_request(encode_request(request))
        )
        decoder = WorkerStreamDecoder(request)
        terminal = None
        for frame in output.getvalue().splitlines(keepends=True):
            terminal = decoder.feed(frame)
        assert terminal is not None and terminal.protocol_error is None
        session.complete_update(
            request.request_id, Terminal(phase="completed", response=terminal)
        )
        with phase_log.open("a") as log:
            log.write(
                json.dumps(
                    {
                        "command": arguments["command"],
                        "phase": "complete",
                        "code": terminal.result.code,
                        "elapsed": monotonic() - started_at,
                    }
                )
                + "\n"
            )
        return terminal.result

    opened = worker_context_call(
        context,
        {
            "command": "prepare",
            "kind": "onboarding",
            "vault": str(vault),
            "source": str(source),
            "selection_id": selection_id,
        },
    )
    assert opened.kind == "onboarding" and opened.binding is not None
    binding = opened.binding
    decisions = {}
    for item in ("entry:opening", "entry:second"):
        page = worker_context_call(
            context, {"command": "page", "binding": binding, "byte_limit": 0}
        )
        change = next(row for row in page.page.items if row.item_id == item)
        offers = worker_context_call(
            context, {"command": "choices", "binding": binding}
        )
        offer = next(row for row in offers.offers if row.change_id == change.change_id)
        selected = worker_context_call(
            context,
            {
                "command": "choose",
                "binding": binding,
                "requirement_id": offer.requirement_id,
                "choice": "current",
                "assumptions_digest": offer.assumptions_digest,
            },
        )
        assert selected.code == "accepted"
        binding = selected.binding
        offers = worker_context_call(
            context, {"command": "choices", "binding": binding}
        )
        decisions[item] = next(
            row.decision_id
            for row in offers.offers
            if row.change_id == change.change_id
        )
        assert decisions[item] is not None
    # The legacy support rows also require explicit preservation choices.
    remaining = worker_context_call(context, {"command": "choices", "binding": binding})
    for offer in remaining.offers:
        if offer.selected is not None:
            continue
        assert "current" in offer.choices
        selected = worker_context_call(
            context,
            {
                "command": "choose",
                "binding": binding,
                "requirement_id": offer.requirement_id,
                "choice": "current",
                "assumptions_digest": offer.assumptions_digest,
            },
        )
        assert selected.code == "accepted"
        binding = selected.binding
    assert selected.ready
    payload_file = observed_directories[-1] / "Home \u2014 Opening.md"
    original_payload = payload_file.read_bytes()
    payload_file.write_bytes(b"Changed retained incoming payload.\r\n")
    stale_source = worker_context_call(context, {"command": "page", "binding": binding})
    assert stale_source.code == "source_payload_changed" and not stale_source.ready
    assert stale_source.binding == binding and stale_source.publication != "unknown"
    assert not stale_source.history_retained and stale_source.checkpoint_commit is None
    assert stale_source.next_actions == ("refresh_update",)
    source_offer = next(
        row
        for row in worker_context_call(
            context,
            {
                "command": "choices",
                "binding": binding,
            },
        ).offers
        if row.decision_id == decisions["entry:second"]
    )
    reconsidered = worker_context_call(
        context,
        {
            "command": "choose",
            "binding": binding,
            "requirement_id": source_offer.requirement_id,
            "choice": "current",
            "assumptions_digest": source_offer.assumptions_digest,
        },
    )
    assert reconsidered.code == "accepted" and not reconsidered.ready
    binding = reconsidered.binding
    offers = worker_context_call(context, {"command": "choices", "binding": binding})
    decisions["entry:second"] = next(
        row.decision_id
        for row in offers.offers
        if row.requirement_id == source_offer.requirement_id
    )
    continued = worker_context_call(
        context, {"command": "close", "binding": binding, "choice": "continue"}
    )
    assert not continued.ready and continued.next_actions == ("refresh_update",)
    refused_apply = worker_context_call(
        context, {"command": "apply", "binding": binding}
    )
    assert not refused_apply.ready and refused_apply.binding == binding
    assert (
        refused_apply.next_actions == ("refresh_update",)
        and refused_apply.publication != "unknown"
    )
    failed_refresh = worker_context_call(
        context, {"command": "refresh", "binding": binding}
    )
    assert not failed_refresh.ready and failed_refresh.binding is not None
    assert failed_refresh.next_actions == ("refresh_update",)
    binding = failed_refresh.binding
    payload_file.write_bytes(original_payload)
    continued = worker_context_call(
        context, {"command": "close", "binding": binding, "choice": "continue"}
    )
    assert not continued.ready and continued.next_actions == ("refresh_update",)
    source_refreshed = worker_context_call(
        context, {"command": "refresh", "binding": binding}
    )
    assert (
        source_refreshed.ready and source_refreshed.binding.revision > binding.revision
    )
    assert source_refreshed.binding.context_id == binding.context_id
    assert source_refreshed.binding.proposal_id == binding.proposal_id
    binding = source_refreshed.binding
    offers = worker_context_call(context, {"command": "choices", "binding": binding})
    assert set(decisions.values()) <= {
        row.decision_id for row in offers.offers if row.selected == "current"
    }
    later = authored + b"Later writing.\r\n"
    (vault / "Home \u2014 Opening.md").write_bytes(later)
    before = {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }
    refreshed = worker_context_call(
        context, {"command": "refresh", "binding": binding, "source": None}
    )
    assert (
        refreshed.kind == "onboarding"
        and refreshed.status == "stale_review"
        and not refreshed.ready
    )
    assert (
        refreshed.binding.proposal_id == binding.proposal_id
        and refreshed.binding.generation == binding.generation + 1
    )
    assert refreshed.binding.revision > binding.revision
    assert (
        stale_worker_call(context, {"command": "choices", "binding": binding}).code
        == "context_changed"
    )
    page = worker_context_call(
        context, {"command": "page", "binding": refreshed.binding}
    )
    offers = worker_context_call(
        context, {"command": "choices", "binding": refreshed.binding}
    )
    for item in ("entry:opening", "entry:second"):
        change = next(row for row in page.page.items if row.item_id == item)
        offer = next(row for row in offers.offers if row.change_id == change.change_id)
        if item == "entry:opening":
            assert (
                change.current == later
                and offer.selected is None
                and offer.decision_id is None
            )
        else:
            assert (
                change.current == second
                and offer.selected == "current"
                and offer.decision_id == decisions[item]
            )
    assert not refreshed.history_retained and refreshed.checkpoint_commit is None
    assert {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    } == before

    # Reobserve a genuine supported source record before requesting Edited.
    # Notes-only legacy onboarding deliberately offers preservation, not Edited.
    (vault / "migration-record.json").write_bytes(
        (payload_file.parent / "migration-record.json").read_bytes()
    )
    supported = worker_context_call(
        context,
        {
            "command": "refresh",
            "binding": refreshed.binding,
        },
    )
    assert supported.binding is not None
    supported_page = worker_context_call(
        context, {"command": "page", "binding": supported.binding}
    )
    supported_offers = worker_context_call(
        context, {"command": "choices", "binding": supported.binding}
    )
    opening = next(
        row for row in supported_page.page.items if row.item_id == "entry:opening"
    )
    offer = next(
        row for row in supported_offers.offers if row.change_id == opening.change_id
    )
    assert "edited" in offer.choices
    # Retiring native authority must preserve an owned volatile edit until discard.
    allocated = []
    allocate = tempfile.TemporaryFile

    def owned_file(*args, **kwargs):
        descriptor = allocate(*args, **kwargs)
        allocated.append(descriptor)
        return descriptor

    monkeypatch.setattr(tempfile, "TemporaryFile", owned_file)
    draft = worker_context_call(
        context,
        {
            "command": "begin_edit",
            "binding": supported.binding,
            "requirement_id": offer.requirement_id,
            "size": 0,
            "sha256": sha256(b"").hexdigest(),
        },
    )
    assert draft.draft_pending and len(allocated) == 1 and not allocated[0].closed
    changed = absent.model_copy(
        update={"status": "refused", "code": "changed_native_history"}
    )
    monkeypatch.setattr(operations, "read_checkpoint", lambda *args, **kwargs: changed)
    retired = worker_context_call(
        context, {"command": "page", "binding": draft.binding}
    )
    assert retired.code == "association_or_history_changed"
    assert retired.binding is None and not retired.ready and retired.draft_pending
    assert retired.publication == "unknown" and not allocated[0].closed
    assert retired.next_actions == ("continue_review", "discard")
    replacement = worker_context_call(
        context,
        {
            "command": "prepare",
            "kind": "onboarding",
            "vault": str(vault),
            "source": str(source),
            "selection_id": selection_id,
        },
    )
    assert replacement.code == "close_decision_required" and replacement.binding is None
    assert replacement.draft_pending and not replacement.ready
    assert replacement.publication == "unknown" and replacement.next_actions == (
        "continue_review",
        "discard",
    )
    assert not allocated[0].closed
    continued = worker_context_call(
        context, {"command": "close", "binding": None, "choice": "continue"}
    )
    assert continued.binding is None and not continued.ready and continued.draft_pending
    assert continued.publication == "unknown" and continued.next_actions == (
        "continue_review",
        "discard",
    )
    assert not allocated[0].closed
    assert (
        session.update_snapshot.needs_inspection
        and session.update_snapshot.draft_pending
    )
    assert session.update_snapshot.close_options == ("continue", "discard")
    discarded = worker_context_call(
        context, {"command": "close", "binding": None, "choice": "discard"}
    )
    assert discarded.code == "context_closed" and not discarded.draft_pending
    assert discarded.binding is None and discarded.publication == "unknown"
    assert discarded.next_actions == ("inspect_history",) and allocated[0].closed
