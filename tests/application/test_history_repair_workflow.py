"""Bound metadata and matching local-copy repair through shared public roles."""

import hashlib
import shutil
import stat

from brz2obsidian.application.operations import Operations
from brz2obsidian.contracts import ReviewPlan
from tests.application.test_history_actions import authored, remember_owner
from tests.application.test_vault_checkpoints import git, user_state
from tests.application.test_vault_recovery_process import _two_note_case


def all_bytes(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_terminal_matching_copy_repairs_history_without_restoring_files_and_binds_details():
    vault, source, review_path, _, _ = _two_note_case()
    evidence = remember_owner(vault)
    operations = Operations()
    plan = ReviewPlan.model_validate_json(review_path.read_bytes())
    source_bytes = authored(source)
    older = vault.parent / "older-complete-copy"
    shutil.copytree(vault, older)
    older_bytes = all_bytes(older)
    applied = operations.apply_reviewed_update(
        vault,
        source,
        review=plan,
        source_binding=operations.observe_reviewed_source(source, plan),
        vault_id="vault-one",
        import_id="import-one",
    )
    assert applied.status == "applied", applied.code
    expected = operations.inspect_update_status(vault)
    assert expected.operation_id == applied.operation_id
    assert expected.intent_commit == applied.intent_commit
    assert expected.generation == applied.generation
    page = operations.read_history_details(vault, expected=expected, offset=0, limit=1)
    assert page.status == "available" and len(page.items) == 1, page.code
    assert page.operation_id == applied.operation_id
    assert page.intent_commit == applied.intent_commit
    assert page.generation == applied.generation
    assert page.kind == "apply" and page.direction == "finish"
    assert page.review_generation == expected.review_generation
    assert page.content_omitted is True
    assert page.offset == 0 and page.total == 3 and page.next_offset == 1
    detail = page.items[0]
    assert detail.path == "Notes/Closing.md"
    assert detail.before_size == len(b"closing authored\r\n")
    assert detail.before_sha256 == hashlib.sha256(b"closing authored\r\n").hexdigest()
    assert detail.after_size == len(b"closing incoming\n")
    assert detail.after_sha256 == hashlib.sha256(b"closing incoming\n").hexdigest()
    assert b"closing incoming" not in page.model_dump_json().encode()
    stale = operations.read_history_details(
        vault,
        expected=expected.model_copy(update={"generation": expected.generation + 1}),
        offset=0,
        limit=1,
    )
    assert stale.status == "unavailable" and stale.code == "operation_authority_changed"
    assert stale.items == () and stale.total == 0
    checkpoint = operations.read_checkpoint(vault)
    assert checkpoint.status == "valid"
    source_blob = next(
        row.object_id
        for row in checkpoint.manifest.source
        if row.path == "Notes/Closing.md"
    )
    assert git(vault, "cat-file", "blob", source_blob) == b"closing incoming\n"
    assert source_blob.encode() not in git(vault, "ls-files", "--stage")
    before_old = all_bytes(vault)
    old = operations.prepare_history_workflow(vault, kind="repair", copy=older)
    assert old.status == "refused" and old.code == "newer_intact_history", old.code
    assert old.copy_validation.target_generation > old.copy_validation.copy_generation
    assert all_bytes(vault) == before_old and all_bytes(older) == older_bytes
    matching = vault.parent / "matching-complete-copy"
    shutil.copytree(vault, matching)
    copy_bytes = all_bytes(matching)
    unanchored = vault.parent / "unanchored-vault"
    unanchored.mkdir()
    git(unanchored, "init", "-q")
    no_anchor_bytes = all_bytes(unanchored)
    no_anchor = operations.prepare_history_workflow(
        unanchored, kind="repair", copy=matching
    )
    assert (
        no_anchor.status == "refused" and no_anchor.code == "no_independent_anchor"
    ), no_anchor.code
    assert all_bytes(unanchored) == no_anchor_bytes
    assert all_bytes(matching) == copy_bytes

    object_path = vault / ".git/objects" / source_blob[:2] / source_blob[2:]
    assert object_path.resolve().is_relative_to(vault.resolve())
    assert object_path.is_file()
    object_path.chmod(stat.S_IWRITE)
    object_path.unlink()  # Damage only this fresh owned fixture's declared blob.
    later = b"opening incoming\nlater working bytes after complete copy\n"
    (vault / "Notes/Opening.md").write_bytes(later)
    damaged_bytes = all_bytes(vault)
    damaged_user = user_state(vault)
    route = operations.inspect_history_workflow(vault)
    assert route.status == "recovery_required", route.code
    assert "review_history_repair" in route.next_actions
    assert "review_update" not in route.next_actions
    assert "review_onboarding" not in route.next_actions
    prepared = operations.prepare_history_workflow(vault, kind="repair", copy=matching)
    (evidence / "repair-prepared.json").write_text(
        prepared.model_dump_json(), encoding="utf-8"
    )
    assert prepared.status == "ready", prepared.code
    assert prepared.copy_validation.status == "matching"
    assert tuple(row.object_id for row in prepared.copy_validation.missing_objects) == (
        source_blob,
    )
    assert all_bytes(vault) == damaged_bytes and all_bytes(matching) == copy_bytes
    assert user_state(vault) == damaged_user
    later += b"another stopped edit\n"
    (vault / "Notes/Opening.md").write_bytes(later)
    stopped_bytes = all_bytes(vault)
    stopped_user = user_state(vault)
    stale_repair = operations.execute_history_workflow(
        prepared.preparation, cancel=lambda: False
    )
    assert stale_repair.status == "refused" and stale_repair.code == "stale_repair", (
        stale_repair.code
    )
    assert not object_path.exists()
    assert all_bytes(vault) == stopped_bytes and all_bytes(matching) == copy_bytes
    refreshed = operations.refresh_history_workflow(prepared.preparation)
    assert refreshed.status == "ready", refreshed.code
    assert all_bytes(vault) == stopped_bytes and all_bytes(matching) == copy_bytes
    repaired = operations.execute_history_workflow(
        refreshed.preparation, cancel=lambda: False
    )
    (evidence / "repaired.json").write_text(
        repaired.model_dump_json(), encoding="utf-8"
    )
    assert repaired.status == "repaired" and repaired.kind == "repair", repaired.code
    assert repaired.publication is None and repaired.operation is None
    assert repaired.history_retained and repaired.repair.authored_files_changed is False
    assert (
        repaired.repair.object_storage == "verified"
        and repaired.repair.objects_written == 1
    )
    assert operations.read_checkpoint(vault).locator == checkpoint.locator
    assert git(vault, "cat-file", "blob", source_blob) == b"closing incoming\n"
    assert authored(vault) == {
        "Notes/Closing.md": b"closing incoming\n",
        "Notes/Opening.md": b"opening incoming\nlater working bytes after complete copy\nanother stopped edit\n",
        "Unrelated.bin": b"protected\x00\xff",
    }
    assert user_state(vault) == stopped_user
    assert all_bytes(matching) == copy_bytes and all_bytes(older) == older_bytes
    assert authored(source) == source_bytes
    after = all_bytes(vault)
    after.pop(object_path.relative_to(vault).as_posix())
    assert after == stopped_bytes
