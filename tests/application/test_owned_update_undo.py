"""Fresh history review restores a large target held only in retained Git."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import brz2obsidian.application.update_lifecycle as lifecycle
import brz2obsidian.publication.vault_history as history
import brz2obsidian.publication.vault_native as native
import brz2obsidian.publication.vault_recovery as recovery
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.contracts import OutputIdentity
from brz2obsidian.publication import checkpoint_payload
from tests.application.test_owned_update_preparation import _digest, _tree
from tests.application.test_update_context import worker_context_call
from tests.application.test_vault_checkpoints import git, user_state
from tests.application.test_verified_coverage import (
    add_attachment,
    change_record,
    source_parts,
    write_source,
)


def _choose_incoming_attachment(
    context, state, offer, *, path, size, digest, history=False
):
    details = worker_context_call(
        context,
        {
            "command": "choice_details",
            "binding": state.binding,
            "requirement_id": offer.requirement_id,
        },
    )
    assert (
        details.status == "available" and details.next_choice_detail_offset is None
    ), details.model_dump_json()
    (output,) = [row for row in details.choice_details if row.choice == "incoming"]
    assert (output.path, output.size, output.sha256) == (path, size, digest)
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
    assert references.total_references == len(references.references)
    if not history:
        assert references.references
    selected = []
    for reference in references.references:
        (destination,) = [
            row
            for row in reference.destinations
            if row.choice == "use_incoming"
            and row.meaning.status == "resolved"
            and row.meaning.target_id == output.target_id
            and row.meaning.path == path
            and row.meaning.target_version == digest
        ]
        assert destination.choice in reference.choices
        selected.append(
            {"reference_id": reference.reference_id, "choice": destination.choice}
        )
    result = worker_context_call(
        context,
        {
            "command": "choose_history" if history else "choose",
            "binding": state.binding,
            "requirement_id": offer.requirement_id,
            "choice": "incoming",
            "assumptions_digest": offer.assumptions_digest,
            "references": tuple(selected),
        },
    )
    if history:
        assert result.status == "prepared_review" and result.binding is not None, (
            result.model_dump_json()
        )
    else:
        assert result.code == "accepted" and result.binding is not None, (
            result.model_dump_json()
        )
    return result


def _choose_offered_record(context, state, page, *, history=False):
    choices = worker_context_call(
        context,
        {
            "command": "history_choices" if history else "choices",
            "binding": state.binding,
        },
    )
    assert choices.status == "available" and choices.next_choice_offset is None, (
        choices.model_dump_json()
    )
    remaining = [offer for offer in choices.offers if offer.selected is None]
    assert all(offer.domain in ("text", "compatible_group") for offer in remaining), (
        choices.model_dump_json()
    )
    groups = [offer for offer in remaining if offer.domain == "compatible_group"]
    assert len(groups) <= 1, choices.model_dump_json()
    if groups:
        (group,) = groups
        assert group.choices == ("approve",) and group.detail_count == 1
        details = worker_context_call(
            context,
            {
                "command": "choice_details",
                "binding": state.binding,
                "requirement_id": group.requirement_id,
            },
        )
        assert (
            details.status == "available" and details.next_choice_detail_offset is None
        ), details.model_dump_json()
        assert details.total_choice_details == group.detail_count
        (detail,) = details.choice_details
        assert detail.kind == "compatible_group"
        index, record = next(
            (index, row)
            for index, row in enumerate(page.page.items)
            if row.change_id == detail.change_id
        )
        assert detail.path == record.current_path
        assert detail.path in {
            "migration-record.json",
            "MIGRATION REPORT.md",
            "Attachments/22222222/large.bin",
        }
        assert detail.size is not None and detail.size > 0
        shown = worker_context_call(
            context,
            {
                "command": "page",
                "binding": state.binding,
                "offset": index,
                "limit": 1,
                "byte_offset": max(0, detail.size - 128),
                "byte_limit": 65536,
            },
        )
        assert shown.status == "available", shown.model_dump_json()
        (member,) = shown.page.items
        assert member.change_id == detail.change_id
        assert member.incoming is not None and member.result == member.incoming
        assert len(member.result) == min(detail.size, 128)
        state = worker_context_call(
            context,
            {
                "command": "choose_history" if history else "choose",
                "binding": state.binding,
                "requirement_id": group.requirement_id,
                "choice": "approve",
                "assumptions_digest": group.assumptions_digest,
            },
        )
        assert state.binding is not None, state.model_dump_json()
        assert (
            state.status == "prepared_review" if history else state.code == "accepted"
        ), state.model_dump_json()
        choices = worker_context_call(
            context,
            {
                "command": "history_choices" if history else "choices",
                "binding": state.binding,
            },
        )
        assert choices.status == "available" and choices.next_choice_offset is None, (
            choices.model_dump_json()
        )
    records = [offer for offer in choices.offers if offer.domain == "text"]
    assert len(records) <= 1, choices.model_dump_json()
    if records:
        (offer,) = records
        (record,) = [
            row
            for row in page.page.items
            if row.item_id == "support:migration-record.json" and row.facet == "content"
        ]
        assert offer.change_id == record.change_id
        assert offer.domain == "text" and "incoming" in offer.choices
        assert offer.disclosure == "Current file: migration-record.json"
        if offer.selected != "incoming":
            state = worker_context_call(
                context,
                {
                    "command": "choose_history" if history else "choose",
                    "binding": state.binding,
                    "requirement_id": offer.requirement_id,
                    "choice": "incoming",
                    "assumptions_digest": offer.assumptions_digest,
                },
            )
    assert (
        state.status == "prepared_review" and state.ready and state.unresolved == 0
    ), state.model_dump_json()
    return state


def test_fresh_history_context_undo_restores_large_retained_preimage(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-366-undo-"))
    owner = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(owner), encoding="utf-8")
    evidence = (
        Path(__file__).resolve().parents[2]
        / "tmp/r347-owned-publication-20261110/fixtures"
    )
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (owner["owner"] + ".json")).write_text(
        json.dumps(owner), encoding="utf-8"
    )
    initial_directory, incoming_directory = root / "initial", root / "incoming"
    initial_directory.mkdir()
    incoming_directory.mkdir()
    item_id = "66666666-6666-4666-8666-666666666666"
    asset_path = "Attachments/22222222/large.bin"
    size = 16 * 1024 * 1024
    prefix = b"\xfcRetained Undo target\x00"
    original = prefix + b"z" * (size - len(prefix))
    original_digest = hashlib.sha256(original).hexdigest()
    incoming = b"\xfdTiny applied replacement.\r\n"
    parts = source_parts(initial_directory)
    add_attachment(parts, item_id, 1, "large.bin", original)
    initial_archive = write_source(initial_directory, parts)
    workflow = default_workflow()
    metadata = workflow.metadata_factory()
    workflow.metadata_factory = lambda: metadata
    vault = root / "vault"
    converted = workflow.convert(initial_archive, vault)
    assert converted.receipt is not None and converted.receipt.verified, (
        converted.model_dump_json()
    )
    assert (vault / asset_path).stat().st_size == size
    assert _digest(vault / asset_path) == original_digest
    baseline = root / "baseline"
    shutil.copytree(vault, baseline)
    parts["22222222-2222-4222-8222-222222222222/large.bin"] = incoming
    change_record(parts, item_id, DataLength=len(incoming))
    incoming_archive = write_source(incoming_directory, parts)
    del parts, original, converted
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    personal = vault / "Personal.md"
    personal.write_bytes(b"Committed independent writing.\r\n")
    git(vault, "add", "Personal.md")
    git(vault, "commit", "-qm", "Independent user history")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    personal.write_bytes(b"Staged independent writing.\r\n")
    git(vault, "add", "Personal.md")
    personal.write_bytes(b"Unstaged independent writing.\r\n")
    scratch = root / "owned-temporary"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    operations = Operations(workflow=workflow)
    seed = operations.capture_checkpoint(
        vault,
        baseline,
        vault_id="owned-undo-vault",
        import_id="owned-undo-import",
        identity=OutputIdentity(
            collection_id="11111111-1111-4111-8111-111111111111",
            module_id="thebrain-brz",
            module_version="11",
            profile_id="thebrain-format5-reviewed",
            profile_version="11",
            output_format=9,
            settings_digest=hashlib.sha256(b"{}").hexdigest(),
        ),
        admission=operations.inspect_history(vault).admission,
    )
    assert seed.status == "captured" and seed.locator.generation == 1, (
        seed.model_dump_json()
    )
    seed_manifest = git(vault, "cat-file", "blob", seed.commit + ":manifest.json")
    assert json.loads(seed_manifest)["review_object"] is None
    before_setup = user_state(vault, owned_ref=seed.ref)
    baseline_before, scratch_before = _tree(baseline), _tree(scratch)
    archives_before = _digest(initial_archive), _digest(incoming_archive)
    warm = UpdateContext(operations=operations)
    opened = worker_context_call(
        warm,
        {
            "command": "prepare",
            "vault": str(vault),
            "source": str(incoming_archive),
            "selection_id": "11111111-1111-4111-8111-111111111111",
            "kind": "source_update",
        },
    )
    assert opened.status == "prepared_review" and opened.binding is not None, (
        opened.model_dump_json()
    )
    page = worker_context_call(
        warm, {"command": "page", "binding": opened.binding, "byte_limit": 0}
    )
    assert page.status == "available" and page.page.next_offset is None, (
        page.model_dump_json()
    )
    (asset,) = [
        row
        for row in page.page.items
        if row.item_id == item_id and row.facet == "asset"
    ]
    (offer,) = [
        offer
        for offer in page.offers
        if offer.change_id == asset.change_id and offer.domain == "attachment"
    ]
    chosen = _choose_incoming_attachment(
        warm,
        opened,
        offer,
        path=asset_path,
        size=len(incoming),
        digest=hashlib.sha256(incoming).hexdigest(),
    )
    chosen = _choose_offered_record(warm, chosen, page)
    applied = worker_context_call(warm, {"command": "apply", "binding": chosen.binding})
    assert applied.status == "applied" and applied.operation is not None, (
        applied.model_dump_json()
    )
    forward = applied.operation
    assert (
        forward.kind == "apply"
        and forward.history == "terminal"
        and forward.publication == "complete"
    )
    assert (vault / asset_path).read_bytes() == incoming
    forward_manifest = json.loads(
        git(vault, "cat-file", "blob", forward.checkpoint_commit + ":manifest.json")
    )
    (retained_row,) = [
        row for row in forward_manifest["preimage"] if row["path"] == asset_path
    ]
    assert (retained_row["size"], retained_row["sha256"]) == (size, original_digest)
    retained = git(
        vault, "cat-file", "blob", forward.checkpoint_commit + ":preimage/" + asset_path
    )
    assert (
        len(retained) == size
        and hashlib.sha256(retained).hexdigest() == original_digest
    )
    assert retained[:32] == prefix + b"z" * (32 - len(prefix))
    del retained
    closed = worker_context_call(warm, {"command": "close", "choice": "discard"})
    assert closed.code == "context_closed" and closed.binding is None, (
        closed.model_dump_json()
    )
    assert _tree(scratch) == scratch_before
    after_setup = user_state(vault, owned_ref=seed.ref)
    for key in ("head", "index", "config", "stages"):
        assert after_setup[key] == before_setup[key]
    for path, data in before_setup["authored"].items():
        if path not in (asset_path, "migration-record.json", "MIGRATION REPORT.md"):
            assert after_setup["authored"][path] == data
    del warm, operations, opened, chosen, page, after_setup, before_setup

    later = b"Writing added after completed Apply.\r\n"
    personal.write_bytes(later)
    before = user_state(vault, owned_ref=seed.ref)
    refs_before = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    locator_before = (vault / ".brz2obsidian/locator.json").read_bytes()
    capacity = 96 * 1024 * 1024
    assert 9 * size + 64 * 1024 * 1024 > capacity
    observed_capacity = []

    def available_memory():
        observed_capacity.append(capacity)
        return capacity

    for module in (native, history, lifecycle, checkpoint_payload, recovery):
        monkeypatch.setattr(module, "available_memory", available_memory)
    cold = UpdateContext()
    inspected = worker_context_call(
        cold,
        {
            "command": "history",
            "vault": str(vault),
            "selection_id": "22222222-2222-4222-8222-222222222222",
        },
    )
    assert (
        inspected.status == "available" and "review_undo" in inspected.next_actions
    ), inspected.model_dump_json()
    assert (
        inspected.binding is not None
        and inspected.binding.checkpoint_commit == forward.result_commit
    )
    prepared = worker_context_call(
        cold,
        {"command": "prepare_history", "binding": inspected.binding, "kind": "undo"},
    )
    assert prepared.status == "prepared_review" and prepared.binding is not None, (
        prepared.model_dump_json()
    )
    assert prepared.binding.target_receipt_commit == forward.receipt_commit
    assert prepared.binding.checkpoint_commit == inspected.binding.checkpoint_commit
    assert (
        prepared.binding.checkpoint_generation
        == inspected.binding.checkpoint_generation
    )
    assert (
        prepared.binding.proposal_id is not None
        and prepared.binding.review_generation is not None
    )
    assert observed_capacity
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs_before
    )
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator_before
    assert user_state(vault, owned_ref=seed.ref) == before
    page = worker_context_call(
        cold, {"command": "page", "binding": prepared.binding, "byte_limit": 0}
    )
    assert page.status == "available" and page.page.next_offset is None, (
        page.model_dump_json()
    )
    index, asset = next(
        (index, row)
        for index, row in enumerate(page.page.items)
        if row.item_id == item_id and row.facet == "asset"
    )
    shown = worker_context_call(
        cold,
        {
            "command": "page",
            "binding": prepared.binding,
            "offset": index,
            "limit": 1,
            "byte_limit": 256,
        },
    )
    assert shown.status == "available", shown.model_dump_json()
    (displayed,) = shown.page.items
    assert displayed.original == incoming and displayed.current == incoming
    assert displayed.incoming == prefix + b"z" * (len(displayed.incoming) - len(prefix))
    assert len(prefix) < len(displayed.incoming) <= 256 and displayed.omitted
    choices = worker_context_call(
        cold, {"command": "history_choices", "binding": prepared.binding}
    )
    assert choices.binding == prepared.binding, choices.model_dump_json()
    assert choices.status == "available" and choices.next_choice_offset is None, (
        choices.model_dump_json()
    )
    (offer,) = [
        offer
        for offer in choices.offers
        if offer.change_id == asset.change_id and offer.domain == "attachment"
    ]
    chosen = _choose_incoming_attachment(
        cold,
        prepared,
        offer,
        path=asset_path,
        size=size,
        digest=original_digest,
        history=True,
    )
    chosen = _choose_offered_record(cold, chosen, page, history=True)
    assert cold.execute_history(prepared.binding).code == "context_changed"
    assert user_state(vault, owned_ref=seed.ref) == before
    undone = worker_context_call(
        cold, {"command": "execute_history", "binding": chosen.binding}
    )
    assert undone.status == "undone" and undone.history_action.operation is not None, (
        undone.model_dump_json()
    )
    operation = undone.history_action.operation
    assert (
        operation.kind == "undo"
        and operation.history == "terminal"
        and operation.publication == "complete"
    )
    assert operation.phase == "terminal" and not operation.recovery_required
    assert operation.operation_id != forward.operation_id
    assert operation.published_files == operation.planned_files > 0
    assert undone.binding is None and not undone.ready
    assert (vault / asset_path).stat().st_size == size
    assert _digest(vault / asset_path) == original_digest
    with (vault / asset_path).open("rb") as stream:
        assert stream.read(32) == prefix + b"z" * (32 - len(prefix))
    assert personal.read_bytes() == later
    assert _tree(scratch) == scratch_before
    closed = worker_context_call(cold, {"command": "close", "choice": "discard"})
    assert closed.code == "context_closed" and closed.binding is None, (
        closed.model_dump_json()
    )
    assert _tree(scratch) == scratch_before
    intent = json.loads(
        git(vault, "cat-file", "blob", operation.intent_commit + ":intent.json")
    )
    receipt = json.loads(
        git(vault, "cat-file", "blob", operation.receipt_commit + ":receipt.json")
    )
    manifest = json.loads(
        git(vault, "cat-file", "blob", operation.checkpoint_commit + ":manifest.json")
    )
    assert intent["kind"] == "undo" and intent["direction"] == "finish"
    assert intent["undo_of_receipt_commit"] == forward.receipt_commit
    assert intent["prepared_commit"] == operation.checkpoint_commit
    assert manifest["undo_of_receipt_commit"] == forward.receipt_commit
    assert receipt["kind"] == "undo" and receipt["status"] == "undone"
    assert receipt["intent_commit"] == operation.intent_commit
    assert receipt["result_commit"] == operation.result_commit
    assert receipt["prepared_commit"] == operation.checkpoint_commit
    assert asset_path in receipt["published_paths"]
    (restored_row,) = [row for row in manifest["proposed"] if row["path"] == asset_path]
    assert (restored_row["size"], restored_row["sha256"]) == (size, original_digest)
    retained = git(
        vault,
        "cat-file",
        "blob",
        operation.checkpoint_commit + ":proposed/" + asset_path,
    )
    assert (
        len(retained) == size
        and hashlib.sha256(retained).hexdigest() == original_digest
    )
    del retained
    after = user_state(vault, owned_ref=seed.ref)
    for key in ("head", "index", "config", "stages"):
        assert after[key] == before[key]
    operation_ref = (
        seed.ref.removesuffix("/checkpoints") + "/operations/" + operation.operation_id
    )
    assert set(after["refs"]) == set(before["refs"]) | {
        (operation_ref + " " + operation.receipt_commit).encode()
    }
    assert after["authored"].keys() == before["authored"].keys()
    for path, data in before["authored"].items():
        if path not in (asset_path, "migration-record.json", "MIGRATION REPORT.md"):
            assert after["authored"][path] == data
    assert _tree(baseline) == baseline_before
    assert (_digest(initial_archive), _digest(incoming_archive)) == archives_before
    assert (
        git(vault, "cat-file", "blob", seed.commit + ":manifest.json") == seed_manifest
    )
    refs_after = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    locator_after = (vault / ".brz2obsidian/locator.json").read_bytes()
    fresh = UpdateContext()
    final = worker_context_call(
        fresh,
        {
            "command": "history",
            "vault": str(vault),
            "selection_id": "33333333-3333-4333-8333-333333333333",
        },
    )
    assert final.status == "available" and "review_undo" not in final.next_actions, (
        final.model_dump_json()
    )
    assert final.history.operation.status == "undone"
    assert final.history.operation.receipt_commit == operation.receipt_commit
    closed = worker_context_call(
        fresh, {"command": "close", "binding": final.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed", closed.model_dump_json()
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs_after
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator_after
    assert user_state(vault, owned_ref=seed.ref) == after
    assert _tree(scratch) == scratch_before
