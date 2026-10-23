"""Public matching-history repair over real local Git stores and exact bytes."""

import json
import shutil
import stat
from pathlib import Path
from types import SimpleNamespace

from brz2obsidian.application.operations import Operations
from brz2obsidian.publication import vault_repair
from tests.application.test_vault_apply import _apply, _ready_case
from tests.application.test_vault_checkpoints import fixture_case, git, user_state
from tests.reconciliation.test_proposals import request


def _all_file_bytes(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_older_copy_refusal_then_exact_missing_history_dependency_repair(monkeypatch):
    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Notes").mkdir()
    (vault / "Notes/Opening.md").write_bytes(b"first authored\r\n")
    git(vault, "add", "Notes/Opening.md")
    git(vault, "commit", "-qm", "user baseline")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    git(vault, "update-ref", "refs/brz2obsidian/user-independent", "HEAD")
    (source / "Notes").mkdir()
    (source / "Notes/Opening.md").write_bytes(b"first generated\n")
    operations = Operations()
    first = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=request().incoming_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert first.status == "captured" and first.commit
    old_authored_blob = Operations().read_checkpoint(vault).manifest.vault[0].object_id
    older = vault.parent / "complete-older-copy"
    shutil.copytree(vault, older)
    older_bytes = _all_file_bytes(older)

    (vault / "Notes/Opening.md").write_bytes(b"newer authored\r\n")
    (source / "Notes/Opening.md").write_bytes(b"newer generated\n")
    second = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=request().incoming_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert second.status == "captured" and second.commit != first.commit
    (vault / "Notes/Opening.md").write_bytes(b"newer authored\r\nlater writing\n")
    git(vault, "add", "Notes/Opening.md")
    (vault / "Notes/Opening.md").write_bytes(
        b"newer authored\r\nlater writing\nunstaged\n"
    )
    (vault / "Unrelated.bin").write_bytes(b"user \xff\x00\n")
    target_bytes = _all_file_bytes(vault)
    target_git = user_state(vault)

    validated = Operations().validate_history_copy(vault, older)
    assert validated.status == "refused" and validated.code == "newer_intact_history"
    assert validated.copy_generation == 1 and validated.target_generation == 2
    refused = Operations().prepare_history_repair(vault, older, validated)
    assert refused.status == "refused" and refused.code == "newer_intact_history"
    assert _all_file_bytes(vault) == target_bytes
    assert _all_file_bytes(older) == older_bytes
    assert user_state(vault) == target_git
    assert Operations().read_checkpoint(vault).manifest.generation == 2

    matching = vault.parent / "complete-current-copy"
    shutil.copytree(vault, matching)
    matching_bytes = _all_file_bytes(matching)
    blob_path = vault / ".git/objects" / old_authored_blob[:2] / old_authored_blob[2:]
    assert blob_path.is_file()
    blob_path.chmod(stat.S_IWRITE)
    blob_path.unlink()
    assert Operations().read_checkpoint(vault).status == "refused"
    damaged_bytes = _all_file_bytes(vault)
    damaged_git = user_state(vault)

    candidate = Operations().validate_history_copy(vault, matching)
    assert (
        candidate.status == "matching" and candidate.code == "exact_missing_dependency"
    )
    assert candidate.copy_generation == 2 and candidate.target_generation == 2
    with monkeypatch.context() as patch:

        def inaccessible_snapshot(root):
            raise OSError("sampled read access failure")

        patch.setattr(vault_repair, "_snapshot", inaccessible_snapshot)
        unavailable_preparation = Operations().prepare_history_repair(
            vault, matching, candidate
        )
    assert unavailable_preparation.status == "unavailable"
    assert unavailable_preparation.code == "repair_context_unavailable"
    assert _all_file_bytes(vault) == damaged_bytes
    assert _all_file_bytes(matching) == matching_bytes
    prepared = Operations().prepare_history_repair(vault, matching, candidate)
    assert prepared.status == "prepared"
    assert _all_file_bytes(vault) == damaged_bytes
    assert _all_file_bytes(matching) == matching_bytes
    (matching / "later-copy-note.txt").write_bytes(b"later copy content\n")
    stale = Operations().execute_history_repair(vault, matching, prepared)
    assert stale.status == "refused" and stale.code == "stale_repair"
    assert _all_file_bytes(vault) == damaged_bytes
    (matching / "later-copy-note.txt").unlink()
    restored = Operations().execute_history_repair(vault, matching, prepared)
    assert restored.status == "repaired"
    assert Operations().read_checkpoint(vault).manifest.generation == 2
    assert user_state(vault) == damaged_git
    assert _all_file_bytes(matching) == matching_bytes
    assert (vault / "Notes/Opening.md").read_bytes() == (
        b"newer authored\r\nlater writing\nunstaged\n"
    )
    assert (vault / "Unrelated.bin").read_bytes() == b"user \xff\x00\n"
    blob_path.chmod(stat.S_IWRITE)
    blob_path.write_bytes(b"damaged same-OID loose object")
    damaged_mode = stat.S_IMODE(blob_path.stat().st_mode)
    damaged_attributes = getattr(blob_path.stat(), "st_file_attributes", 0)
    damaged_loose = _all_file_bytes(vault)
    assert Operations().read_checkpoint(vault).status == "refused"
    damaged_candidate = Operations().validate_history_copy(vault, matching)
    assert damaged_candidate.status == "matching"
    assert damaged_candidate.code == "exact_damaged_dependency"
    assert tuple(row.object_id for row in damaged_candidate.damaged_objects) == (
        old_authored_blob,
    )
    assert _all_file_bytes(vault) == damaged_loose
    assert _all_file_bytes(matching) == matching_bytes
    damaged_preparation = Operations().prepare_history_repair(
        vault, matching, damaged_candidate
    )
    assert damaged_preparation.status == "prepared"
    with monkeypatch.context() as patch:
        patch.setattr(
            vault_repair.shutil,
            "disk_usage",
            lambda path: SimpleNamespace(free=0),
        )
        insufficient = Operations().execute_history_repair(
            vault, matching, damaged_preparation
        )
    assert insufficient.status == "refused"
    assert insufficient.code == "repair_resources_unavailable"
    assert insufficient.object_storage == "not_started"
    assert _all_file_bytes(vault) == damaged_loose
    assert _all_file_bytes(matching) == matching_bytes
    with monkeypatch.context() as patch:

        def failed_native_move(*args, **kwargs):
            raise OSError("sampled namespace move failure")

        patch.setattr(vault_repair, "move_file", failed_native_move)
        uncertain = Operations().execute_history_repair(
            vault, matching, damaged_preparation
        )
    assert uncertain.status == "unknown"
    assert uncertain.object_storage == "possible"
    assert uncertain.objects_written == 0
    assert uncertain.diagnostic_path is not None
    diagnostic = Path(uncertain.diagnostic_path)
    assert diagnostic.parent == vault.parent
    assert (diagnostic / (old_authored_blob + ".damaged")).read_bytes() == (
        b"damaged same-OID loose object"
    )
    assert _all_file_bytes(vault) == damaged_loose
    assert _all_file_bytes(matching) == matching_bytes
    assert user_state(vault) == damaged_git
    assert diagnostic.resolve().parent == vault.parent.resolve()
    assert diagnostic.name.startswith("brz2obsidian-repair-")
    shutil.rmtree(diagnostic)
    repaired_damage = Operations().execute_history_repair(
        vault, matching, damaged_preparation
    )
    assert repaired_damage.status == "repaired"
    assert repaired_damage.object_storage == "verified"
    assert stat.S_IMODE(blob_path.stat().st_mode) == damaged_mode
    assert getattr(blob_path.stat(), "st_file_attributes", 0) == damaged_attributes
    assert _all_file_bytes(matching) == matching_bytes
    assert Operations().read_checkpoint(vault).manifest.generation == 2
    assert user_state(vault) == damaged_git

    git(vault, "repack", "-a", "-d")
    git(vault, "prune-packed")
    assert not blob_path.exists()
    assert git(vault, "cat-file", "blob", old_authored_blob) == b"first authored\r\n"
    packed_target = _all_file_bytes(vault)
    packed_git = user_state(vault)
    original_call = vault_repair._Git.call
    failed_queries = []

    def unavailable_packed_query(self, *args, **kwargs):
        query = kwargs.get("input", b"")
        if (
            self.root == vault
            and args[:2]
            == ("cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)")
            and old_authored_blob.encode("ascii") in query.splitlines()
        ):
            failed_queries.append(query)
            raise OSError("sampled Git query access failure for a readable packed blob")
        return original_call(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(vault_repair._Git, "call", unavailable_packed_query)
        inaccessible = Operations().validate_history_copy(vault, matching)
    assert failed_queries
    assert inaccessible.status == "unavailable"
    assert inaccessible.code == "history_invalid"
    assert _all_file_bytes(vault) == packed_target
    assert _all_file_bytes(matching) == matching_bytes
    assert user_state(vault) == packed_git
    assert Operations().read_checkpoint(vault).status == "valid"
    repaired_bytes = packed_target

    transferred = vault.parent / "notes-only-transfer"
    transferred.mkdir()
    git(transferred, "init", "-q")
    (transferred / "Notes").mkdir()
    (transferred / "Notes/Opening.md").write_bytes(
        b"newer authored\r\nlater writing\nunstaged\n"
    )
    (transferred / "Unrelated.bin").write_bytes(b"user \xff\x00\n")
    (transferred / "migration.json").write_bytes(
        b'{"vault_id":"vault-one","import_id":"import-one"}\n'
    )
    transferred_bytes = _all_file_bytes(transferred)
    no_anchor = Operations().validate_history_copy(transferred, matching)
    assert (
        no_anchor.status == "unavailable" and no_anchor.code == "no_independent_anchor"
    )
    assert Operations().read_checkpoint(transferred).status == "absent"
    assert _all_file_bytes(transferred) == transferred_bytes
    assert _all_file_bytes(matching) == matching_bytes

    incomplete = vault.parent / "incomplete-copy"
    shutil.copytree(matching, incomplete)
    missing_in_copy = (
        incomplete / ".git/objects" / old_authored_blob[:2] / old_authored_blob[2:]
    )
    missing_in_copy.chmod(stat.S_IWRITE)
    missing_in_copy.unlink()
    incomplete_bytes = _all_file_bytes(incomplete)
    rejected = Operations().validate_history_copy(vault, incomplete)
    assert rejected.status == "refused" and rejected.code == "copy_invalid"
    assert _all_file_bytes(incomplete) == incomplete_bytes
    assert _all_file_bytes(vault) == repaired_bytes

    shutil.copy2(
        matching / ".git/objects" / old_authored_blob[:2] / old_authored_blob[2:],
        missing_in_copy,
    )
    locator = incomplete / ".brz2obsidian/locator.json"
    future = json.loads(locator.read_bytes())
    future["schema_version"] = 99
    locator.write_text(json.dumps(future, separators=(",", ":")), encoding="utf-8")
    future_bytes = _all_file_bytes(incomplete)
    unsupported = Operations().validate_history_copy(vault, incomplete)
    assert unsupported.status == "refused" and unsupported.code == "copy_invalid"
    assert _all_file_bytes(incomplete) == future_bytes
    assert _all_file_bytes(vault) == repaired_bytes
    assert _all_file_bytes(matching) == matching_bytes

    target_locator = vault / ".brz2obsidian/locator.json"
    target_locator.write_bytes(b'{"schema_id":"brz2obsidian.checkpoint-locator"')
    torn_target = _all_file_bytes(vault)
    unavailable = Operations().validate_history_copy(vault, matching)
    assert unavailable.status == "unavailable" and unavailable.code == "history_invalid"
    assert _all_file_bytes(vault) == torn_target
    assert _all_file_bytes(matching) == matching_bytes


def test_copy_requires_complete_terminal_operation_root_and_local_object_store(
    monkeypatch,
):
    vault, source, operations, review, _ = _ready_case()
    applied = _apply(
        operations,
        vault,
        source,
        review=review,
        vault_id="vault-one",
        import_id="import-one",
    )
    assert applied.status == "applied" and applied.receipt_commit
    supplied = vault.parent / "copy-of-completed-apply"
    shutil.copytree(vault, supplied)
    assert Operations().validate_history_copy(vault, supplied).status == "matching"
    operation_ref = (
        "refs/brz2obsidian/imports/"
        + operations.read_checkpoint(vault).locator.association.association_id
        + "/operations/"
        + applied.operation_id
    )
    git(supplied, "update-ref", "-d", operation_ref, applied.receipt_commit)
    copy_without_root = _all_file_bytes(supplied)
    target = _all_file_bytes(vault)
    missing = Operations().validate_history_copy(vault, supplied)
    assert missing.status == "refused" and missing.code == "copy_invalid"
    assert _all_file_bytes(vault) == target
    assert _all_file_bytes(supplied) == copy_without_root

    git(supplied, "update-ref", operation_ref, applied.receipt_commit)
    alternates = supplied / ".git/objects/info/alternates"
    alternates.write_text(str(vault / ".git/objects") + "\n", encoding="utf-8")
    copy_with_external_store = _all_file_bytes(supplied)
    external = Operations().validate_history_copy(vault, supplied)
    assert external.status == "refused" and external.code == "copy_invalid"
    assert _all_file_bytes(vault) == target
    assert _all_file_bytes(supplied) == copy_with_external_store

    alternates.unlink()
    complete_copy = _all_file_bytes(supplied)
    git(
        vault,
        "update-ref",
        operation_ref,
        applied.intent_commit,
        applied.receipt_commit,
    )
    interrupted_target = _all_file_bytes(vault)
    assert Operations().inspect_update_status(vault).recovery_required
    incomplete = Operations().validate_history_copy(vault, supplied)
    assert incomplete.status == "refused" and incomplete.code == "recovery_first"
    assert _all_file_bytes(vault) == interrupted_target
    assert _all_file_bytes(supplied) == complete_copy

    git(
        vault,
        "update-ref",
        operation_ref,
        applied.receipt_commit,
        applied.intent_commit,
    )
    retained_authored = next(
        row
        for row in Operations().read_checkpoint(vault).manifest.vault
        if row.path == "Notes/Local.md"
    )
    missing_blob = (
        vault
        / ".git/objects"
        / retained_authored.object_id[:2]
        / retained_authored.object_id[2:]
    )
    assert missing_blob.is_file()
    missing_blob.chmod(stat.S_IWRITE)
    missing_blob.unlink()
    damaged_terminal = _all_file_bytes(vault)
    assert Operations().read_checkpoint(vault).status == "refused"
    target_alternates = vault / ".git/objects/info/alternates"
    target_alternates.write_text(
        str(supplied / ".git/objects") + "\n", encoding="utf-8"
    )
    unsupported_target = _all_file_bytes(vault)
    unsupported = Operations().validate_history_copy(vault, supplied)
    assert unsupported.status == "refused" and unsupported.code == "target_unsupported"
    assert _all_file_bytes(vault) == unsupported_target
    assert _all_file_bytes(supplied) == complete_copy
    target_alternates.unlink()
    assert _all_file_bytes(vault) == damaged_terminal
    owner_marker = vault / ".git/brz2obsidian"
    owner_marker.mkdir()
    (owner_marker / "owner.json").write_bytes(b"{torn owner marker")
    owned_target = _all_file_bytes(vault)
    torn_owner = Operations().validate_history_copy(vault, supplied)
    assert torn_owner.status == "refused" and torn_owner.code == "recovery_first"
    assert _all_file_bytes(vault) == owned_target
    assert _all_file_bytes(supplied) == complete_copy
    (owner_marker / "owner.json").unlink()
    owner_marker.rmdir()
    index_lock = vault / ".git/index.lock"
    index_lock.write_bytes(b"held by another Git operation")
    locked_target = _all_file_bytes(vault)
    locked = Operations().validate_history_copy(vault, supplied)
    assert locked.status == "refused" and locked.code == "git_operation_busy"
    assert _all_file_bytes(vault) == locked_target
    assert _all_file_bytes(supplied) == complete_copy
    index_lock.unlink()
    assert _all_file_bytes(vault) == damaged_terminal
    receipt_object = (
        vault / ".git/objects" / applied.receipt_commit[:2] / applied.receipt_commit[2:]
    )
    assert receipt_object.is_file()
    receipt_object.chmod(stat.S_IWRITE)
    receipt_object.unlink()
    missing_control = _all_file_bytes(vault)
    unavailable_control = Operations().validate_history_copy(vault, supplied)
    assert unavailable_control.status == "unavailable"
    assert unavailable_control.code == "operation_history_invalid"
    assert _all_file_bytes(vault) == missing_control
    assert _all_file_bytes(supplied) == complete_copy
    shutil.copy2(
        supplied
        / ".git/objects"
        / applied.receipt_commit[:2]
        / applied.receipt_commit[2:],
        receipt_object,
    )
    assert _all_file_bytes(vault) == damaged_terminal
    terminal_copy = Operations().validate_history_copy(vault, supplied)
    assert terminal_copy.status == "matching"
    assert terminal_copy.code == "exact_missing_dependency"
    assert tuple(row.object_id for row in terminal_copy.missing_objects) == (
        retained_authored.object_id,
    )
    assert _all_file_bytes(vault) == damaged_terminal
    assert _all_file_bytes(supplied) == complete_copy
    ready = Operations().prepare_history_repair(vault, supplied, terminal_copy)
    assert ready.status == "prepared"
    original_call = vault_repair._Git.call
    wrote = []

    def lost_write_acknowledgement(self, *args, **kwargs):
        if self.root == vault and args[:2] == ("hash-object", "-w"):
            oid = original_call(self, *args, **kwargs).decode().strip()
            wrote.append(oid)
            raise OSError("Fixture lost the Git response after a real object write")
        return original_call(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(vault_repair._Git, "call", lost_write_acknowledgement)
        repaired = Operations().execute_history_repair(vault, supplied, ready)
    assert wrote == [retained_authored.object_id]
    assert repaired.status == "repaired" and repaired.objects_written == 1
    assert Operations().inspect_update_status(vault).status == "applied"
    assert Operations().read_checkpoint(vault).status == "valid"
    assert _all_file_bytes(supplied) == complete_copy
