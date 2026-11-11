"""A real partial cleanup rebinds its absent removal to the retained origin."""

import hashlib
import json
import tempfile
from pathlib import Path
from uuid import uuid4

import brz2obsidian.application.update_lifecycle as lifecycle
import brz2obsidian.publication.vault_history as history
import brz2obsidian.publication.vault_native as native
import brz2obsidian.publication.vault_recovery as recovery
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.publication import checkpoint_payload
from brz2obsidian.publication.vault_replace import move_file
from tests.application.test_attachment_cleanup_lifecycle import (
    NEW_ASSET,
    NEW_PATH,
    OLD_ASSET,
    OLD_PATH,
    user_git,
)
from tests.application.test_owned_cleanup_preparation import _published_source_absence
from tests.application.test_owned_update_preparation import _digest, _tree
from tests.application.test_update_context import worker_context_call
from tests.application.test_vault_checkpoints import git


def _drop_remove(context, state, offer, *, history=False):
    references = worker_context_call(
        context,
        {
            "command": "references",
            "binding": state.binding,
            "requirement_id": offer.requirement_id,
        },
    )
    assert (
        references.status == "available" and references.next_reference_offset is None
    ), references.model_dump_json()
    assert references.total_references == len(references.references) == 1
    (reference,) = references.references
    assert reference.document_path == "Manual.md" and reference.old.path == OLD_PATH
    assert reference.choices == ("drop",)
    result = worker_context_call(
        context,
        {
            "command": "choose_history" if history else "choose",
            "binding": state.binding,
            "requirement_id": offer.requirement_id,
            "choice": "remove",
            "assumptions_digest": offer.assumptions_digest,
            "references": ({"reference_id": reference.reference_id, "choice": "drop"},),
        },
    )
    assert result.binding is not None, result.model_dump_json()
    assert result.status == "prepared_review" if history else result.code == "accepted"
    return result


def test_owned_cleanup_finish_rebinds_deleted_binary_and_drops_actual_reference(
    monkeypatch,
):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-366-cleanup-finish-"))
    marker = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(marker), encoding="utf-8")
    evidence = (
        Path(__file__).resolve().parents[2]
        / "tmp/r347-owned-publication-20261110/fixtures"
    )
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (marker["owner"] + ".json")).write_text(
        json.dumps(marker), encoding="utf-8"
    )
    (
        vault,
        archive_a,
        archive_b,
        published_a,
        checkpoint_b,
        source_a_record,
        source_a_version,
        incoming_b,
    ) = _published_source_absence(root)
    manifest_b_raw = git(
        vault, "cat-file", "blob", checkpoint_b.locator.commit + ":manifest.json"
    )
    source_b = json.loads(manifest_b_raw)["source"]
    source_b_version = checkpoint_b.manifest.reviewed_source.target_source_version
    assert source_b_version != source_a_version and all(
        row["path"] != OLD_PATH for row in source_b
    )
    size = 16 * 1024 * 1024
    prefix = b"\xffIndependent authored cleanup preimage\x00"
    raw = prefix + b"k" * (size - len(prefix))
    expected_digest = hashlib.sha256(raw).hexdigest()
    (vault / OLD_PATH).write_bytes(raw)
    del raw
    manual = b"Manual [[Attachments/22222222/Notes.md.original|old]]. `[[Attachments/22222222/Notes.md.original]]`\r\n"
    without_reference = b"Manual . `[[Attachments/22222222/Notes.md.original]]`\r\n"
    (vault / "Manual.md").write_bytes(b"Staged user writing before cleanup.\r\n")
    git(vault, "add", "Manual.md")
    (vault / "Manual.md").write_bytes(manual)
    original_user = user_git(vault)
    authored = {
        path.relative_to(vault).as_posix(): _digest(path)
        for path in vault.rglob("*")
        if path.is_file()
        and path.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    }
    archives_before = _digest(archive_a), _digest(archive_b)
    source_before = _tree(root / "source")
    scratch = root / "owned-temporary"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    scratch_before = _tree(scratch)
    capacity = 96 * 1024 * 1024
    assert 9 * size + 64 * 1024 * 1024 > capacity
    observations = []

    def available_memory():
        observations.append(capacity)
        return capacity

    for module in (native, history, lifecycle, checkpoint_payload, recovery):
        monkeypatch.setattr(module, "available_memory", available_memory)
    removed, attempted = [], []

    class StopBeforeReferenceRewrite:
        def remove(self, target, destination):
            assert Path(target).relative_to(vault).as_posix() == OLD_PATH
            assert (
                Path(target).stat().st_size == size
                and _digest(Path(target)) == expected_digest
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            move_file(target, destination, replace=False)
            removed.append(OLD_PATH)

        def move(self, stage, target, *, replace):
            assert Path(target).relative_to(vault).as_posix() == "Manual.md"
            assert removed == [OLD_PATH] and not (vault / OLD_PATH).exists()
            assert (vault / "Manual.md").read_bytes() == manual and replace
            attempted.append("Manual.md")
            raise OSError(
                "Stopped at the real reference rewrite after removing the owned asset"
            )

        def directory(self, stage, target):
            raise AssertionError("This existing-path cleanup creates no directory")

    warm = UpdateContext(
        operations=Operations(vault_executor=StopBeforeReferenceRewrite())
    )
    opened = worker_context_call(
        warm,
        {
            "command": "prepare",
            "kind": "attachment_cleanup",
            "vault": str(vault),
            "source": None,
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    assert opened.status == "prepared_review" and opened.binding is not None, (
        opened.model_dump_json()
    )
    assert opened.kind == "attachment_cleanup" and observations
    page = worker_context_call(
        warm, {"command": "page", "binding": opened.binding, "byte_limit": 0}
    )
    assert page.status == "available" and page.page.next_offset is None
    (old,) = [
        row
        for row in page.page.items
        if row.item_id == OLD_ASSET and row.facet == "asset"
    ]
    (fresh,) = [
        row
        for row in page.page.items
        if row.item_id == NEW_ASSET and row.facet == "asset"
    ]
    assert old.original is None and old.incoming is None
    (keep,) = [
        offer
        for offer in page.offers
        if offer.change_id == fresh.change_id and offer.domain == "attachment"
    ]
    assert "current" in keep.choices
    kept = worker_context_call(
        warm,
        {
            "command": "choose",
            "binding": opened.binding,
            "requirement_id": keep.requirement_id,
            "choice": "current",
            "assumptions_digest": keep.assumptions_digest,
        },
    )
    assert kept.code == "accepted" and kept.binding is not None, kept.model_dump_json()
    choices = worker_context_call(warm, {"command": "choices", "binding": kept.binding})
    assert choices.status == "available" and choices.next_choice_offset is None
    (offer,) = [
        offer
        for offer in choices.offers
        if offer.change_id == old.change_id and offer.domain == "attachment"
    ]
    assert "remove" in offer.choices
    selected = _drop_remove(warm, kept, offer)
    assert selected.ready and selected.unresolved == 0
    # The native executor sorts affected paths; the injected fault also
    # observes the real completed deletion before stopping Manual.md.
    stopped = worker_context_call(
        warm, {"command": "apply", "binding": selected.binding}
    )
    assert stopped.status == "recovery_required" and stopped.operation is not None, (
        stopped.model_dump_json()
    )
    forward = stopped.operation
    assert stopped.binding is None and not stopped.ready
    assert stopped.kind == "attachment_cleanup" and forward.kind == "apply"
    assert forward.recovery_required and forward.publication == "partial"
    assert forward.published_files == 1 and forward.planned_files == 2
    assert forward.intent_commit is not None and forward.checkpoint_commit is not None
    assert forward.result_commit is None and forward.receipt_commit is None
    assert removed == [OLD_PATH] and attempted == ["Manual.md"]
    assert (
        not (vault / OLD_PATH).exists() and (vault / "Manual.md").read_bytes() == manual
    )
    assert (vault / NEW_PATH).read_bytes() == incoming_b and user_git(
        vault
    ) == original_user
    assert _tree(scratch) == scratch_before
    original_manifest = json.loads(
        git(vault, "cat-file", "blob", forward.checkpoint_commit + ":manifest.json")
    )
    original_intent = json.loads(
        git(vault, "cat-file", "blob", forward.intent_commit + ":intent.json")
    )
    original_review_raw = git(
        vault, "cat-file", "blob", original_manifest["review_object"]
    )
    original_plan = json.loads(original_review_raw)["record"]["plan"]
    (original_subject,) = [
        subject
        for subject in original_plan["facts"]["subjects"]
        if subject["item_id"] == OLD_ASSET and subject["facet"] == "asset"
    ]
    proof = original_subject["attachment"]["retained_ownership"]
    assert proof["checkpoint_commit"] == published_a.result_commit
    assert (
        proof["source_version"] == source_a_version and proof["source_path"] == OLD_PATH
    )
    assert proof["mapping_sha256"] == hashlib.sha256(source_a_record).hexdigest()
    assert (
        original_plan["facts"]["format_operation"]["target_source_version"]
        == source_b_version
    )
    (approval,) = [
        approval
        for approval in original_plan["approvals"]
        if approval["change_id"] == old.change_id and approval["domain"] == "attachment"
    ]
    assert approval["choice"] == "remove" and approval["provenance"] == "explicit_user"
    assert approval["attachment_candidate"]["outputs"] == []
    assert (
        original_manifest["source"] == source_b
        and original_manifest["previous"] == checkpoint_b.locator.commit
    )
    assert original_intent["prepared_commit"] == forward.checkpoint_commit
    assert original_intent["affected_paths"] == [OLD_PATH, "Manual.md"]
    assert all(
        row["path"] != OLD_PATH
        for row in original_manifest["source"] + original_manifest["proposed"]
    )
    (before,) = [
        row for row in original_manifest["preimage"] if row["path"] == OLD_PATH
    ]
    assert before["size"] == size and before["sha256"] == expected_digest
    retained = git(
        vault, "cat-file", "blob", forward.checkpoint_commit + ":preimage/" + OLD_PATH
    )
    assert (
        len(retained) == size
        and hashlib.sha256(retained).hexdigest() == expected_digest
    )
    assert retained[: len(prefix)] == prefix
    del retained, warm, page, selected, kept

    later = b"Later independent writing with exact CRLF.\r\n"
    (vault / "Later.md").write_bytes(later)
    refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    locator = (vault / ".brz2obsidian/locator.json").read_bytes()
    cold = UpdateContext()
    inspected = worker_context_call(
        cold,
        {
            "command": "history",
            "vault": str(vault),
            "selection_id": "33333333-3333-4333-8333-333333333333",
        },
    )
    assert inspected.status == "recovery_required" and inspected.binding is not None, (
        inspected.model_dump_json()
    )
    assert inspected.history.operation.origin_role == "attachment_cleanup"
    assert (
        inspected.binding.operation_id == forward.operation_id
        and inspected.binding.intent_commit == forward.intent_commit
    )
    prepared = worker_context_call(
        cold,
        {
            "command": "prepare_history",
            "binding": inspected.binding,
            "kind": "recovery",
            "direction": "finish",
        },
    )
    assert prepared.status == "prepared_review" and prepared.binding is not None, (
        prepared.model_dump_json()
    )
    assert (
        prepared.binding.operation_id == forward.operation_id
        and prepared.binding.intent_commit == forward.intent_commit
    )
    assert prepared.binding.direction == "finish"
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator
    assert (
        user_git(vault) == original_user and (vault / "Later.md").read_bytes() == later
    )
    page = worker_context_call(
        cold, {"command": "page", "binding": prepared.binding, "byte_limit": 0}
    )
    assert page.status == "available" and page.page.next_offset is None
    (absent,) = [
        row
        for row in page.page.items
        if row.item_id == OLD_ASSET and row.facet == "asset"
    ]
    assert absent.current is None and absent.incoming is None
    choices = worker_context_call(
        cold, {"command": "history_choices", "binding": prepared.binding}
    )
    assert choices.status == "available" and choices.next_choice_offset is None
    (offer,) = [
        offer
        for offer in choices.offers
        if offer.change_id == absent.change_id and offer.domain == "attachment"
    ]
    assert "remove" in offer.choices and "current" not in offer.choices
    selected = _drop_remove(cold, prepared, offer, history=True)
    assert not selected.ready and selected.unresolved == 1, selected.model_dump_json()
    index, present = next(
        (index, row)
        for index, row in enumerate(page.page.items)
        if row.item_id == NEW_ASSET and row.facet == "asset"
    )
    shown = worker_context_call(
        cold,
        {
            "command": "page",
            "binding": selected.binding,
            "offset": index,
            "limit": 1,
            "byte_limit": 256,
        },
    )
    assert shown.status == "available", shown.model_dump_json()
    (displayed,) = shown.page.items
    assert displayed.item_id == NEW_ASSET and displayed.current_path == NEW_PATH
    assert displayed.current == incoming_b and not displayed.omitted
    choices = worker_context_call(
        cold, {"command": "history_choices", "binding": selected.binding}
    )
    assert choices.status == "available" and choices.next_choice_offset is None
    (offer,) = [offer for offer in choices.offers if offer.selected is None]
    assert offer.change_id == present.change_id and offer.domain == "attachment"
    assert "current" in offer.choices
    selected = worker_context_call(
        cold,
        {
            "command": "choose_history",
            "binding": selected.binding,
            "requirement_id": offer.requirement_id,
            "choice": "current",
            "assumptions_digest": offer.assumptions_digest,
        },
    )
    assert (
        selected.status == "prepared_review"
        and selected.ready
        and selected.unresolved == 0
    ), selected.model_dump_json()
    finished = worker_context_call(
        cold, {"command": "execute_history", "binding": selected.binding}
    )
    assert (
        finished.status == "applied" and finished.history_action.operation is not None
    ), finished.model_dump_json()
    operation = finished.history_action.operation
    assert operation.operation_id == forward.operation_id and operation.kind == "apply"
    assert (
        operation.direction == "finish"
        and operation.origin_role == "attachment_cleanup"
    )
    assert (
        operation.history == "terminal"
        and operation.phase == "terminal"
        and not operation.recovery_required
    )
    assert (
        operation.publication == "complete"
        and finished.binding is None
        and not finished.ready
    )
    assert (
        not (vault / OLD_PATH).exists()
        and (vault / "Manual.md").read_bytes() == without_reference
    )
    assert (vault / "Later.md").read_bytes() == later and (
        vault / NEW_PATH
    ).read_bytes() == incoming_b
    assert user_git(vault) == original_user and _tree(scratch) == scratch_before
    manifest = json.loads(
        git(vault, "cat-file", "blob", operation.checkpoint_commit + ":manifest.json")
    )
    result = json.loads(
        git(vault, "cat-file", "blob", operation.result_commit + ":manifest.json")
    )
    intent = json.loads(
        git(vault, "cat-file", "blob", operation.intent_commit + ":recovery.json")
    )
    receipt = json.loads(
        git(vault, "cat-file", "blob", operation.receipt_commit + ":receipt.json")
    )
    assert (
        intent["origin_intent_commit"] == forward.intent_commit
        and intent["prepared_commit"] == operation.checkpoint_commit
    )
    assert (
        intent["operation_id"] == forward.operation_id
        and intent["direction"] == "finish"
    )
    assert (
        manifest["recovery_origin_intent_commit"] == forward.intent_commit
        and manifest["recovery_direction"] == "finish"
    )
    assert manifest["source"] == result["source"] == source_b
    assert result["vault"] == manifest["proposed"]
    assert result["operation_intent_commit"] == operation.intent_commit
    assert (
        receipt["intent_commit"] == operation.intent_commit
        and receipt["prepared_commit"] == operation.checkpoint_commit
    )
    assert (
        receipt["result_commit"] == operation.result_commit
        and receipt["status"] == "applied"
    )
    assert receipt["published_paths"] == ["Manual.md"]
    finish_plan = json.loads(git(vault, "cat-file", "blob", manifest["review_object"]))[
        "record"
    ]["plan"]
    (subject,) = [
        subject
        for subject in finish_plan["facts"]["subjects"]
        if subject["item_id"] == OLD_ASSET and subject["facet"] == "asset"
    ]
    assert (
        subject["current"]["existence"] == "absent"
        and subject["current"]["content"] is None
    )
    assert subject["attachment"]["retained_ownership"] == proof
    continuation = subject["attachment"]["removal_continuation"]
    assert (
        continuation["operation_id"] == forward.operation_id
        and continuation["operation_kind"] == "apply"
    )
    assert (
        continuation["direction"] == "finish"
        and continuation["operation_generation"] == forward.generation
    )
    assert (
        continuation["origin_intent_commit"] == forward.intent_commit
        and continuation["prepared_commit"] == forward.checkpoint_commit
    )
    assert (
        continuation["origin_change_id"] == old.change_id
        and continuation["origin_decision_id"] == approval["decision_id"]
    )
    assert (
        continuation["path"] == OLD_PATH
        and continuation["before_size"] == size
        and continuation["before_sha256"] == expected_digest
    )
    assert (
        finish_plan["facts"]["format_operation"]["target_source_version"]
        == source_b_version
    )
    (removed_approval,) = [
        approval
        for approval in finish_plan["approvals"]
        if approval["change_id"] == absent.change_id
        and approval["domain"] == "attachment"
    ]
    assert (
        removed_approval["choice"] == "remove"
        and removed_approval["provenance"] == "explicit_user"
    )
    assert (
        git(vault, "cat-file", "blob", original_manifest["review_object"])
        == original_review_raw
    )
    assert (
        git(vault, "cat-file", "blob", checkpoint_b.locator.commit + ":manifest.json")
        == manifest_b_raw
    )
    assert (_digest(archive_a), _digest(archive_b)) == archives_before and _tree(
        root / "source"
    ) == source_before
    assert {
        path: _digest(vault / path)
        for path in authored
        if path not in (OLD_PATH, "Manual.md")
    } == {
        path: digest
        for path, digest in authored.items()
        if path not in (OLD_PATH, "Manual.md")
    }
    final = UpdateContext()
    observed = worker_context_call(
        final,
        {
            "command": "history",
            "vault": str(vault),
            "selection_id": "44444444-4444-4444-8444-444444444444",
        },
    )
    assert (
        observed.status == "available"
        and "review_recovery" not in observed.next_actions
    ), observed.model_dump_json()
    assert "review_undo" not in observed.next_actions
    assert observed.history.operation.receipt_commit == operation.receipt_commit
    closed = worker_context_call(
        final, {"command": "close", "binding": observed.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and _tree(scratch) == scratch_before
