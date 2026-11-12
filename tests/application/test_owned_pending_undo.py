"""A fresh owned Undo retry reobserves its real ignored binary tracking scope."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from queue import Queue
from threading import Event, Thread
from uuid import uuid4

import brz2obsidian.publication.vault_apply as native_apply
from brz2obsidian.application.contracts import WorkerRequest
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.protocol import encode_request
from brz2obsidian.application.review_choices import (
    requirement_digest,
    review_plan_choice_action,
)
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.update_stream import WorkerStreamDecoder
from brz2obsidian.application.update_worker import UpdateWorker
from brz2obsidian.application.vault_contracts import VaultSubject
from brz2obsidian.contracts import reconciliation_subject_id
from brz2obsidian.core import inspect_review_choices, prepare_review, resolve_review
from tests.application.test_attachment_cleanup_lifecycle import user_git
from tests.application.test_owned_update_preparation import _digest, _tree
from tests.application.test_owned_update_undo import _choose_incoming_attachment
from tests.application.test_update_context import worker_context_call
from tests.application.test_vault_apply import _apply
from tests.application.test_vault_checkpoints import fixture_case, git
from tests.reconciliation.test_attachments import attachment_request


def _select_exact_binary_undo(context, state, *, path, before):
    """Reconfirm only the actual binary Incoming and ordinary tracking grant."""
    for _ in range(3):
        if state.ready:
            break
        choices = worker_context_call(
            context, {"command": "history_choices", "binding": state.binding}
        )
        assert choices.status == "available" and choices.next_choice_offset is None
        remaining = [offer for offer in choices.offers if offer.selected is None]
        assert remaining and all(
            offer.domain in ("attachment", "tracking") for offer in remaining
        )
        offer = remaining[0]
        if offer.domain == "attachment":
            state = _choose_incoming_attachment(
                context,
                state,
                offer,
                path=path,
                size=len(before),
                digest=hashlib.sha256(before).hexdigest(),
                history=True,
            )
        else:
            assert offer.choices == ("accept", "decline")
            state = worker_context_call(
                context,
                {
                    "command": "choose_history",
                    "binding": state.binding,
                    "requirement_id": offer.requirement_id,
                    "choice": "accept",
                    "assumptions_digest": offer.assumptions_digest,
                },
            )
            assert state.status == "prepared_review" and state.binding is not None, (
                state.model_dump_json()
            )
    assert state.ready and state.unresolved == 0, state.model_dump_json()
    return state


def test_fresh_owned_undo_retry_reobserves_pending_ignored_binary_grant(monkeypatch):
    vault, source = fixture_case()
    root = vault.parent
    marker = json.loads((root / ".fixture-owner.json").read_bytes())
    registry = (
        Path(__file__).resolve().parents[2]
        / "tmp/r347-owned-publication-20261110/fixtures"
    )
    registry.mkdir(parents=True, exist_ok=True)
    (registry / (marker["owner"] + ".json")).write_text(
        json.dumps(marker), encoding="utf-8"
    )
    asset_path = "Assets/data.bin"
    original = b"\x00original"
    authored = b"\x00authored"
    incoming = b"abc"
    (vault / "Assets").mkdir()
    (source / "Assets").mkdir()
    (vault / asset_path).write_bytes(authored)
    (source / asset_path).write_bytes(original)
    personal = b"Independent committed writing.\r\n"
    (vault / "Personal.md").write_bytes(personal)
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    git(vault, "add", "Personal.md")
    git(vault, "commit", "-qm", "Independent user history")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    operations = Operations()
    facts = attachment_request()
    assert facts.subjects[0].current.content.data == authored
    seeded = operations.capture_checkpoint(
        vault,
        source,
        vault_id="pending-undo-vault",
        import_id="pending-undo-import",
        identity=facts.incoming_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert seeded.status == "captured", seeded.model_dump_json()
    ignore = b"Assets/data.bin\nPrivate.bin\n"
    private = b"Independent ignored private bytes\x00\xff\r\n"
    (vault / ".gitignore").write_bytes(ignore)
    (vault / "Private.bin").write_bytes(private)
    git(vault, "add", ".gitignore")
    assert git(vault, "check-ignore", "--", asset_path).strip() == asset_path.encode()
    assert not git(vault, "ls-files", "--", asset_path)
    subject_id = reconciliation_subject_id(
        facts.incoming_identity.module_id,
        facts.incoming_identity.collection_id,
        facts.subjects[0].item_id,
        facts.subjects[0].facet,
    )
    admission = operations.inspect_history(
        vault,
        subjects=(VaultSubject(path=asset_path, subject_id=subject_id),),
    ).admission
    (tracking,) = admission.preflight.consents
    assert tracking.kind == "tracking" and tracking.requirement == "required"
    assert tracking.policy == "ordinary" and tracking.subjects == (subject_id,)
    plan = prepare_review(facts, preflight=admission.preflight)
    for domain, choice in (("attachment", "incoming"), ("tracking", "accept")):
        (offer,) = [
            offer for offer in inspect_review_choices(plan) if offer.domain == domain
        ]
        action = review_plan_choice_action(
            plan,
            requirement_id=offer.requirement_id,
            choice=choice,
            assumptions_digest=requirement_digest(offer),
        )
        chosen = resolve_review(plan, action)
        assert chosen.status == "accepted", chosen.code
        plan = chosen.plan
    assert plan.ready
    (source / asset_path).write_bytes(incoming)
    applied = _apply(
        operations,
        vault,
        source,
        review=plan,
        vault_id="pending-undo-vault",
        import_id="pending-undo-import",
    )
    assert applied.status == "applied" and applied.history == "terminal", (
        applied.model_dump_json()
    )
    assert (vault / asset_path).read_bytes() == incoming
    user_before = user_git(vault)
    source_before = _tree(source)
    authored_before = {
        path.relative_to(vault).as_posix(): _digest(path)
        for path in vault.rglob("*")
        if path.is_file()
        and path.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    }
    original_refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    scratch = root / "owned-temporary"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    warm = UpdateContext()
    inspected = worker_context_call(
        warm, {"command": "history", "vault": str(vault), "selection_id": str(uuid4())}
    )
    assert (
        inspected.status == "available" and "review_undo" in inspected.next_actions
    ), inspected.model_dump_json()
    prepared = worker_context_call(
        warm,
        {"command": "prepare_history", "binding": inspected.binding, "kind": "undo"},
    )
    assert prepared.status == "prepared_review" and prepared.binding is not None, (
        prepared.model_dump_json()
    )
    assert prepared.binding.target_receipt_commit == applied.receipt_commit
    selected = _select_exact_binary_undo(
        warm, prepared, path=asset_path, before=authored
    )

    # Stop only after the real capture has published its exact Undo PREPARED.
    # The existing worker control channel supplies the actual cancellation.
    entered, release = Event(), Event()
    captures = []
    actual_capture = native_apply.capture_checkpoint

    def hold_actual_prepared(*args, **kwargs):
        captured = actual_capture(*args, **kwargs)
        if (
            kwargs.get("undo_of_receipt_commit") == applied.receipt_commit
            and kwargs.get("boundary") == "prepared"
        ):
            assert captured.status == "captured", captured.model_dump_json()
            captures.append(captured.commit)
            retained = json.loads(
                git(vault, "cat-file", "blob", captured.commit + ":manifest.json")
            )
            assert (
                retained["boundary"] == "prepared"
                and retained["undo_of_receipt_commit"] == applied.receipt_commit
            )
            assert retained["operation_intent_commit"] is None
            entered.set()
            assert release.wait(600), (
                "Actual PREPARED must retain cooperative cancellation"
            )
        return captured

    request = WorkerRequest(
        operation="update",
        request_id=str(uuid4()),
        sequence=1,
        arguments={"command": "execute_history", "binding": selected.binding},
    )
    cancel = WorkerRequest(
        operation="update",
        request_id=str(uuid4()),
        sequence=2,
        arguments={
            "command": "cancel",
            "binding": selected.binding,
            "target_request_id": request.request_id,
            "target_sequence": 1,
        },
    )
    input_read, input_write = os.pipe()
    output_read, output_write = os.pipe()
    incoming_pipe, commands = (
        os.fdopen(input_read, "rb"),
        os.fdopen(input_write, "wb", buffering=0),
    )
    replies, outgoing = (
        os.fdopen(output_read, "rb"),
        os.fdopen(output_write, "wb", buffering=0),
    )
    frames = Queue()
    reader = Thread(
        target=lambda: [frames.put(frame) for frame in iter(replies.readline, b"")],
        daemon=True,
    )
    worker = UpdateWorker(context=warm, output=outgoing)
    decoders = {row.request_id: WorkerStreamDecoder(row) for row in (request, cancel)}
    results = {}

    def read_one():
        frame = frames.get(timeout=600)
        terminal = decoders[json.loads(frame)["request_id"]].feed(frame)
        if terminal is not None:
            assert terminal.protocol_error is None
            results[terminal.request_id] = terminal.result

    failures = []

    def control_client():
        try:
            commands.write(encode_request(request))
            assert entered.wait(600), "The real Undo PREPARED was not reached"
            commands.write(encode_request(cancel))
            while cancel.request_id not in results:
                read_one()
            assert (
                results[cancel.request_id].code == "cancellation_requested"
                and not release.is_set()
            )
            release.set()
            while request.request_id not in results:
                read_one()
            stopped = results[request.request_id]
            assert (
                stopped.status == "cancelled"
                and stopped.history_action.operation is not None
            ), stopped.model_dump_json()
            operation = stopped.history_action.operation
            assert (
                operation.code == "cancelled_before_intent"
                and operation.phase == "prepared"
            )
            assert (
                operation.publication == "not_started"
                and operation.intent_commit is None
            )
            assert (
                operation.checkpoint_commit == captures[0]
                and not operation.authored_files_changed
            )
            close = WorkerRequest(
                operation="update",
                request_id=str(uuid4()),
                sequence=3,
                arguments={
                    "command": "close",
                    "binding": stopped.binding,
                    "choice": "discard",
                },
            )
            decoders[close.request_id] = WorkerStreamDecoder(close)
            commands.write(encode_request(close))
            while close.request_id not in results:
                read_one()
            assert results[close.request_id].code == "context_closed"
        except BaseException as error:  # noqa: BLE001 -- rethrow the control-thread failure on the test thread.
            failures.append(error)
        finally:
            release.set()
            commands.close()

    client = Thread(target=control_client, daemon=True)
    with monkeypatch.context() as boundary:
        boundary.setattr(native_apply, "capture_checkpoint", hold_actual_prepared)
        reader.start()
        client.start()
        try:
            # The same MainThread that prepared the owned review performs it.
            code = worker.serve(incoming_pipe)
        finally:
            release.set()
            client.join(600)
            incoming_pipe.close()
            outgoing.close()
            reader.join(600)
            replies.close()
    assert not client.is_alive() and not reader.is_alive()
    if failures:
        raise failures[0]
    assert code == 0
    assert len(captures) == 1 and _tree(scratch) == ()
    pending_commit = captures[0]
    assert (vault / asset_path).read_bytes() == incoming and user_git(
        vault
    ) == user_before
    pending_raw = git(vault, "cat-file", "blob", pending_commit + ":manifest.json")
    pending = json.loads(pending_raw)
    assert (
        pending["previous"] == applied.result_commit
        and pending["undo_of_receipt_commit"] == applied.receipt_commit
    )
    pending_review_raw = git(vault, "cat-file", "blob", pending["review_object"])
    pending_plan = json.loads(pending_review_raw)["record"]["plan"]
    assert pending_plan["ready"] is True
    (binary_subject,) = [
        row
        for row in pending_plan["producer_facts"]["subjects"]
        if row["current"]["path"] == asset_path
    ]
    assert binary_subject["current"]["content"]["data"] == {
        "__brz2obsidian_review_blob__": hashlib.sha256(incoming).hexdigest()
    }
    (required,) = [
        row
        for row in pending_plan["preflight"]["consents"]
        if row["kind"] == "tracking"
    ]
    assert (
        required["requirement"] == "required"
        and required["policy"] == "ordinary"
        and subject_id in required["subjects"]
    )
    assert any(
        row["consent_id"] == required["consent_id"] and row["choice"] == "accept"
        for row in pending_plan["consents"]
    )
    assert (
        git(vault, "cat-file", "blob", pending_commit + ":preimage/" + asset_path)
        == incoming
    )
    assert (
        git(vault, "cat-file", "blob", pending_commit + ":proposed/" + asset_path)
        == authored
    )
    pending_refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    assert [row for row in original_refs.splitlines() if b"/operations/" in row] == [
        row for row in pending_refs.splitlines() if b"/operations/" in row
    ]
    locator = (vault / ".brz2obsidian/locator.json").read_bytes()
    assert not (vault / ".git/brz2obsidian").exists()
    cold = UpdateContext()
    inspected = worker_context_call(
        cold, {"command": "history", "vault": str(vault), "selection_id": str(uuid4())}
    )
    assert "review_undo" in inspected.next_actions and inspected.binding is not None, (
        inspected.model_dump_json()
    )
    retry = worker_context_call(
        cold,
        {"command": "prepare_history", "binding": inspected.binding, "kind": "undo"},
    )
    assert retry.status == "prepared_review" and retry.binding is not None, (
        retry.model_dump_json()
    )
    assert (
        retry.binding.checkpoint_commit == pending_commit
        and retry.binding.target_receipt_commit == applied.receipt_commit
    )
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == pending_refs
    )
    ready = _select_exact_binary_undo(cold, retry, path=asset_path, before=authored)
    refreshed = worker_context_call(
        cold, {"command": "refresh_history", "binding": ready.binding}
    )
    assert refreshed.status == "prepared_review" and refreshed.ready, (
        refreshed.model_dump_json()
    )
    assert refreshed.unresolved == 0 and refreshed.binding is not None
    assert refreshed.binding.checkpoint_commit == pending_commit
    assert refreshed.binding.target_receipt_commit == applied.receipt_commit
    assert refreshed.binding.proposal_id == ready.binding.proposal_id
    assert refreshed.binding.review_generation == ready.binding.review_generation
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == pending_refs
    )
    ready = refreshed
    finished = worker_context_call(
        cold, {"command": "execute_history", "binding": ready.binding}
    )
    assert (
        finished.status == "undone" and finished.history_action.operation is not None
    ), finished.model_dump_json()
    undone = finished.history_action.operation
    assert (
        undone.kind == "undo"
        and undone.direction == "finish"
        and undone.history == "terminal"
    )
    assert undone.publication == "complete" and not undone.recovery_required
    assert undone.planned_files == undone.published_files == 1
    final_prepared = json.loads(
        git(vault, "cat-file", "blob", undone.checkpoint_commit + ":manifest.json")
    )
    assert final_prepared["undo_of_receipt_commit"] == applied.receipt_commit
    assert undone.generation == final_prepared["generation"]
    if undone.checkpoint_commit == pending_commit:
        assert final_prepared["previous"] == applied.result_commit
        assert undone.generation == pending["generation"]
    else:
        assert final_prepared["previous"] == pending_commit
        assert undone.generation == pending["generation"] + 1
    assert (
        git(
            vault,
            "cat-file",
            "blob",
            undone.checkpoint_commit + ":preimage/" + asset_path,
        )
        == incoming
    )
    assert (
        git(
            vault,
            "cat-file",
            "blob",
            undone.checkpoint_commit + ":proposed/" + asset_path,
        )
        == authored
    )
    result = json.loads(
        git(vault, "cat-file", "blob", undone.result_commit + ":manifest.json")
    )
    intent = json.loads(
        git(vault, "cat-file", "blob", undone.intent_commit + ":intent.json")
    )
    receipt = json.loads(
        git(vault, "cat-file", "blob", undone.receipt_commit + ":receipt.json")
    )
    assert (
        result["previous"] == undone.checkpoint_commit
        and result["vault"] == final_prepared["proposed"]
    )
    assert result["generation"] == undone.generation + 1
    final_locator = json.loads((vault / ".brz2obsidian/locator.json").read_bytes())
    assert (
        final_locator["commit"] == undone.result_commit
        and final_locator["generation"] == result["generation"]
    )
    assert (
        intent["prepared_commit"] == undone.checkpoint_commit
        and intent["undo_of_receipt_commit"] == applied.receipt_commit
    )
    assert (
        receipt["intent_commit"] == undone.intent_commit
        and receipt["prepared_commit"] == undone.checkpoint_commit
    )
    assert (
        receipt["result_commit"] == undone.result_commit
        and receipt["status"] == "undone"
    )
    assert receipt["published_paths"] == [asset_path]
    assert (
        git(vault, "cat-file", "blob", undone.result_commit + ":source/" + asset_path)
        == original
    )
    assert (
        git(vault, "cat-file", "blob", pending_commit + ":manifest.json") == pending_raw
    )
    assert (
        git(vault, "cat-file", "blob", pending["review_object"]) == pending_review_raw
    )
    assert (vault / asset_path).read_bytes() == authored
    authored_before[asset_path] = hashlib.sha256(authored).hexdigest()
    assert {
        path.relative_to(vault).as_posix(): _digest(path)
        for path in vault.rglob("*")
        if path.is_file()
        and path.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    } == authored_before
    assert user_git(vault) == user_before and _tree(source) == source_before
    assert (vault / "Private.bin").read_bytes() == private and (
        vault / "Personal.md"
    ).read_bytes() == personal
    assert not git(vault, "ls-files", "--", asset_path)
    assert _tree(scratch) == ()
