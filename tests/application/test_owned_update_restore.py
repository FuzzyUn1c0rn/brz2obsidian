"""Draft owning RESTORE journey; promote only after the current Undo loop passes."""

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
from brz2obsidian.contracts import OutputIdentity
from brz2obsidian.publication import checkpoint_payload
from brz2obsidian.publication.vault_replace import move_file
from tests.application.test_owned_update_preparation import _digest, _tree
from tests.application.test_owned_update_undo import (
    _choose_incoming_attachment,
    _choose_offered_record,
)
from tests.application.test_update_context import worker_context_call
from tests.application.test_vault_checkpoints import git, user_state
from tests.application.test_verified_coverage import (
    add_attachment,
    change_record,
    source_parts,
    write_source,
)
from tests.support.recorded_format8 import format8_workflow


def test_fresh_history_context_restores_large_preimage_after_stopped_apply(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-366-restore-"))
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
    original = b"\xffIndependent generated original.\r\n"
    incoming = b"\xfdTiny applied replacement.\r\n"
    size = 16 * 1024 * 1024
    prefix = b"\xfcRetained RESTORE target\x00"
    authored = prefix + b"r" * (size - len(prefix))
    authored_digest = hashlib.sha256(authored).hexdigest()
    parts = source_parts(initial_directory)
    add_attachment(parts, item_id, 1, "large.bin", original)
    initial_archive = write_source(initial_directory, parts)
    workflow = format8_workflow()
    metadata = workflow.metadata_factory()
    workflow.metadata_factory = lambda: metadata
    vault = root / "vault"
    converted = workflow.convert(initial_archive, vault)
    assert converted.receipt is not None and converted.receipt.verified, (
        converted.model_dump_json()
    )
    assert (vault / asset_path).read_bytes() == original
    baseline = root / "baseline"
    shutil.copytree(vault, baseline)
    (vault / asset_path).write_bytes(authored)
    assert _digest(vault / asset_path) == authored_digest
    parts["22222222-2222-4222-8222-222222222222/large.bin"] = incoming
    change_record(parts, item_id, DataLength=len(incoming))
    incoming_archive = write_source(incoming_directory, parts)
    del parts, authored, converted
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

    moved = []

    class StopAfterActualAssetMove:
        def move(self, stage, target, *, replace):
            move_file(stage, target, replace=replace)
            moved.append(Path(target).relative_to(vault).as_posix())
            if moved[-1] == asset_path:
                raise OSError("Stopped after the actual selected binary replacement")

        def remove(self, target, destination):
            raise AssertionError("This offered incoming selection removes no path")

    operations = Operations(
        workflow=workflow, vault_executor=StopAfterActualAssetMove()
    )
    seed = operations.capture_checkpoint(
        vault,
        baseline,
        vault_id="owned-restore-vault",
        import_id="owned-restore-import",
        identity=OutputIdentity(
            collection_id="11111111-1111-4111-8111-111111111111",
            module_id="thebrain-brz",
            module_version="11",
            profile_id="thebrain-format5-reviewed",
            profile_version="11",
            output_format=8,
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
        row
        for row in page.offers
        if row.change_id == asset.change_id and row.domain == "attachment"
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
    stopped = worker_context_call(warm, {"command": "apply", "binding": chosen.binding})
    assert stopped.status == "recovery_required" and stopped.operation is not None, (
        stopped.model_dump_json()
    )
    forward = stopped.operation
    assert forward.kind == "apply" and forward.recovery_required
    assert forward.intent_commit is not None and forward.checkpoint_commit is not None
    assert forward.receipt_commit is None and forward.result_commit is None
    assert asset_path in moved
    assert (vault / asset_path).read_bytes() == incoming
    assert stopped.binding is None and not stopped.ready
    forward_manifest = json.loads(
        git(vault, "cat-file", "blob", forward.checkpoint_commit + ":manifest.json")
    )
    (before_row,) = [
        row for row in forward_manifest["preimage"] if row["path"] == asset_path
    ]
    assert (before_row["size"], before_row["sha256"]) == (size, authored_digest)
    retained = git(
        vault, "cat-file", "blob", forward.checkpoint_commit + ":preimage/" + asset_path
    )
    assert (
        len(retained) == size
        and hashlib.sha256(retained).hexdigest() == authored_digest
    )
    assert retained[:32] == prefix + b"r" * (32 - len(prefix))
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
    del warm, operations, chosen, opened, page, before_setup, after_setup

    later = b"Writing added after the stopped Apply.\r\n"
    personal.write_bytes(later)
    before = user_state(vault, owned_ref=seed.ref)
    refs_before = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    locator_before = (vault / ".brz2obsidian/locator.json").read_bytes()
    operation_ref = (
        seed.ref.removesuffix("/checkpoints") + "/operations/" + forward.operation_id
    )
    pending_commit = git(vault, "rev-parse", operation_ref).decode().strip()
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
        inspected.status == "recovery_required"
        and "review_recovery" in inspected.next_actions
    ), inspected.model_dump_json()
    assert inspected.binding is not None
    assert inspected.binding.operation_id == forward.operation_id
    assert inspected.binding.intent_commit == forward.intent_commit
    assert inspected.history.operation.recovery_required
    prepared = worker_context_call(
        cold,
        {
            "command": "prepare_history",
            "binding": inspected.binding,
            "kind": "recovery",
            "direction": "restore",
        },
    )
    assert prepared.status == "prepared_review" and prepared.binding is not None, (
        prepared.model_dump_json()
    )
    assert prepared.binding.operation_id == forward.operation_id
    assert prepared.binding.intent_commit == forward.intent_commit
    assert prepared.binding.direction == "restore"
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
    assert displayed.incoming == prefix + b"r" * (len(displayed.incoming) - len(prefix))
    assert len(prefix) < len(displayed.incoming) <= 256 and displayed.omitted
    choices = worker_context_call(
        cold, {"command": "history_choices", "binding": prepared.binding}
    )
    assert choices.status == "available" and choices.binding == prepared.binding, (
        choices.model_dump_json()
    )
    assert choices.next_choice_offset is None
    (offer,) = [
        row
        for row in choices.offers
        if row.change_id == asset.change_id and row.domain == "attachment"
    ]
    chosen = _choose_incoming_attachment(
        cold,
        prepared,
        offer,
        path=asset_path,
        size=size,
        digest=authored_digest,
        history=True,
    )
    chosen = _choose_offered_record(cold, chosen, page, history=True)
    selected = worker_context_call(
        cold, {"command": "history_choices", "binding": chosen.binding}
    )
    assert selected.status == "available" and selected.binding == chosen.binding, (
        selected.model_dump_json()
    )
    (attachment,) = [
        row
        for row in selected.offers
        if row.change_id == asset.change_id and row.domain == "attachment"
    ]
    assert attachment.selected == "incoming" and attachment.decision_id is not None
    assert cold.execute_history(prepared.binding).code == "context_changed"
    assert user_state(vault, owned_ref=seed.ref) == before
    restored = worker_context_call(
        cold, {"command": "execute_history", "binding": chosen.binding}
    )
    assert (
        restored.status == "restored" and restored.history_action.operation is not None
    ), restored.model_dump_json()
    operation = restored.history_action.operation
    assert operation.operation_id == forward.operation_id and operation.kind == "apply"
    assert operation.direction == "restore" and operation.publication == "complete"
    assert (
        operation.history == "terminal"
        and operation.phase == "terminal"
        and not operation.recovery_required
    )
    assert operation.intent_commit != forward.intent_commit
    assert operation.published_files == operation.planned_files > 0
    assert restored.binding is None and not restored.ready
    assert (vault / asset_path).stat().st_size == size
    assert _digest(vault / asset_path) == authored_digest
    with (vault / asset_path).open("rb") as stream:
        assert stream.read(32) == prefix + b"r" * (32 - len(prefix))
    assert personal.read_bytes() == later
    assert _tree(scratch) == scratch_before
    closed = worker_context_call(cold, {"command": "close", "choice": "discard"})
    assert closed.code == "context_closed" and closed.binding is None, (
        closed.model_dump_json()
    )
    assert _tree(scratch) == scratch_before
    intent = json.loads(
        git(vault, "cat-file", "blob", operation.intent_commit + ":recovery.json")
    )
    receipt = json.loads(
        git(vault, "cat-file", "blob", operation.receipt_commit + ":receipt.json")
    )
    manifest = json.loads(
        git(vault, "cat-file", "blob", operation.checkpoint_commit + ":manifest.json")
    )
    result_manifest = json.loads(
        git(vault, "cat-file", "blob", operation.result_commit + ":manifest.json")
    )
    assert intent["schema_id"] == "brz2obsidian.vault-recovery-intent"
    assert intent["kind"] == "apply" and intent["direction"] == "restore"
    assert intent["origin_intent_commit"] == forward.intent_commit
    assert intent["previous_operation_commit"] == pending_commit
    assert intent["prepared_commit"] == operation.checkpoint_commit
    assert (
        receipt["kind"] == "apply"
        and receipt["status"] == "restored"
        and receipt["direction"] == "restore"
    )
    assert receipt["intent_commit"] == operation.intent_commit
    assert receipt["result_commit"] == operation.result_commit
    assert receipt["prepared_commit"] == operation.checkpoint_commit
    assert asset_path in receipt["published_paths"]
    assert manifest["recovery_direction"] == "restore"
    assert "recovery_direction" not in result_manifest
    assert result_manifest["operation_intent_commit"] == operation.intent_commit
    assert result_manifest["previous"] == operation.checkpoint_commit
    assert manifest["recovery_origin_intent_commit"] == forward.intent_commit
    for role, expected_size, expected_digest in (
        ("source", len(original), hashlib.sha256(original).hexdigest()),
        ("preimage", len(incoming), hashlib.sha256(incoming).hexdigest()),
        ("proposed", size, authored_digest),
    ):
        (row,) = [row for row in manifest[role] if row["path"] == asset_path]
        assert (row["size"], row["sha256"]) == (expected_size, expected_digest)
    (result_row,) = [
        row for row in result_manifest["vault"] if row["path"] == asset_path
    ]
    assert (result_row["size"], result_row["sha256"]) == (size, authored_digest)
    retained = git(
        vault,
        "cat-file",
        "blob",
        operation.checkpoint_commit + ":proposed/" + asset_path,
    )
    assert (
        len(retained) == size
        and hashlib.sha256(retained).hexdigest() == authored_digest
    )
    del retained
    saved = json.loads(git(vault, "cat-file", "blob", manifest["review_object"]))[
        "record"
    ]["plan"]
    (decision,) = [
        row
        for row in saved["approvals"]
        if row["decision_id"] == attachment.decision_id
    ]
    assert decision["domain"] == "attachment" and decision["choice"] == "incoming"
    assert decision["provenance"] == "explicit_user"
    after = user_state(vault, owned_ref=seed.ref)
    for key in ("head", "index", "config", "stages"):
        assert after[key] == before[key]
    assert set(after["refs"]) == (
        set(before["refs"]) - {(operation_ref + " " + pending_commit).encode()}
    ) | {(operation_ref + " " + operation.receipt_commit).encode()}
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
    assert (
        final.status == "available" and "review_recovery" not in final.next_actions
    ), final.model_dump_json()
    assert (
        final.history.operation.status == "restored"
        and not final.history.operation.recovery_required
    )
    assert final.history.operation.receipt_commit == operation.receipt_commit
    closed = worker_context_call(
        fresh, {"command": "close", "binding": final.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed", closed.model_dump_json()
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs_after
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator_after
    assert user_state(vault, owned_ref=seed.ref) == after
    assert _tree(scratch) == scratch_before
