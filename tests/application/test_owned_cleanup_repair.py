"""A ready cleanup remains owned while its complete matching copy repairs one blob."""

import hashlib
import json
import shutil
import stat
import tempfile
from pathlib import Path
from uuid import uuid4

import brz2obsidian.application.update_lifecycle as lifecycle
import brz2obsidian.publication.vault_history as history
import brz2obsidian.publication.vault_native as native
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.publication import checkpoint_payload
from tests.application.test_attachment_cleanup_lifecycle import (
    NEW_ASSET,
    NEW_PATH,
    OLD_ASSET,
    OLD_PATH,
    ORIGINAL,
    user_git,
)
from tests.application.test_owned_cleanup_preparation import _published_source_absence
from tests.application.test_owned_update_preparation import _digest, _tree
from tests.application.test_update_context import worker_context_call
from tests.application.test_vault_checkpoints import git


def test_ready_owned_cleanup_save_and_matching_copy_restore_one_history_blob(
    monkeypatch,
):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-366-cleanup-repair-"))
    marker = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(marker), encoding="utf-8")
    registry = (
        Path(__file__).resolve().parents[2]
        / "tmp/r347-owned-publication-20261110/fixtures"
    )
    registry.mkdir(parents=True, exist_ok=True)
    (registry / (marker["owner"] + ".json")).write_text(
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
    terminal_b = checkpoint_b.locator.commit
    terminal_b_raw = git(vault, "cat-file", "blob", terminal_b + ":manifest.json")
    source_b = json.loads(terminal_b_raw)["source"]
    source_b_version = checkpoint_b.manifest.reviewed_source.target_source_version
    assert source_a_version != source_b_version and all(
        row["path"] != OLD_PATH for row in source_b
    )
    size = 16 * 1024 * 1024
    prefix = b"\xffIndependent ready cleanup retained body\x00"
    raw = prefix + b"r" * (size - len(prefix))
    expected_digest = hashlib.sha256(raw).hexdigest()
    (vault / OLD_PATH).write_bytes(raw)
    del raw
    manual = b"Independent manual ![[Attachments/22222222/Notes.md.original]].\r\n"
    (vault / "Manual.md").write_bytes(manual)
    protected_path = "Protected-history-only.bin"
    protected = b"Independent history-only payload\x00\xff\r\n"
    (vault / protected_path).write_bytes(protected)
    later = b"Independent later writing retained through repair.\r\n"
    (vault / "Later.md").write_bytes(later)
    protected_digest = hashlib.sha256(protected).hexdigest()
    protected_oid = hashlib.sha1(
        f"blob {len(protected)}\0".encode() + protected
    ).hexdigest()
    assert protected_oid.encode() not in git(vault, "ls-files", "--stage")
    assert protected_oid.encode() not in git(vault, "ls-tree", "-r", "HEAD")
    original_user = user_git(vault)
    authored = {
        path.relative_to(vault).as_posix(): _digest(path)
        for path in vault.rglob("*")
        if path.is_file()
        and path.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    }
    source_before = _tree(root / "source")
    archives_before = _digest(archive_a), _digest(archive_b)
    scratch = root / "owned-temporary"
    scratch.mkdir()
    scratch_before = _tree(scratch)
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    observations = []

    def available_memory():
        observations.append(96 * 1024 * 1024)
        return 96 * 1024 * 1024

    for module in (native, history, lifecycle, checkpoint_payload):
        monkeypatch.setattr(module, "available_memory", available_memory)
    warm = UpdateContext()
    opened = worker_context_call(
        warm,
        {
            "command": "prepare",
            "kind": "attachment_cleanup",
            "source": None,
            "vault": str(vault),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    assert opened.status == "prepared_review" and opened.binding is not None, (
        opened.model_dump_json()
    )
    assert (
        opened.kind == "attachment_cleanup"
        and opened.binding.checkpoint_commit == terminal_b
    )
    page = worker_context_call(
        warm, {"command": "page", "binding": opened.binding, "byte_limit": 0}
    )
    assert page.status == "available" and page.page.next_offset is None
    changes = {
        row.item_id: row.change_id for row in page.page.items if row.facet == "asset"
    }
    assert {OLD_ASSET, NEW_ASSET} <= changes.keys()
    state = opened
    decisions = {}
    for item_id in (NEW_ASSET, OLD_ASSET):
        choices = worker_context_call(
            warm, {"command": "choices", "binding": state.binding}
        )
        assert choices.status == "available" and choices.next_choice_offset is None
        (offer,) = [
            offer
            for offer in choices.offers
            if offer.change_id == changes[item_id] and offer.domain == "attachment"
        ]
        assert "current" in offer.choices
        state = worker_context_call(
            warm,
            {
                "command": "choose",
                "binding": state.binding,
                "requirement_id": offer.requirement_id,
                "choice": "current",
                "assumptions_digest": offer.assumptions_digest,
            },
        )
        assert state.code == "accepted" and state.binding is not None, (
            state.model_dump_json()
        )
    assert state.ready and state.unresolved == 0, state.model_dump_json()
    saved = worker_context_call(warm, {"command": "save", "binding": state.binding})
    assert saved.code == "saved" and saved.capture.status == "captured", (
        saved.model_dump_json()
    )
    assert saved.ready and saved.binding is not None and saved.history_retained
    saved_commit = saved.capture.commit
    assert saved.binding.checkpoint_commit == saved_commit
    manifest_raw = git(vault, "cat-file", "blob", saved_commit + ":manifest.json")
    manifest = json.loads(manifest_raw)
    assert manifest["boundary"] == "local" and manifest["previous"] == terminal_b
    assert manifest["source"] == source_b
    assert manifest["reviewed_source"]["target_source_version"] == source_b_version
    assert all(
        row["path"] != OLD_PATH
        for row in manifest["source"] + manifest["reviewed_source"]["files"]
    )
    review_raw = git(vault, "cat-file", "blob", manifest["review_object"])
    plan = json.loads(review_raw)["record"]["plan"]
    assert plan["ready"] is True
    facts = plan["facts"]
    assert facts["format_operation"]["kind"] == "attachment_cleanup"
    assert (
        facts["format_operation"]["baseline_source_version"]
        == facts["format_operation"]["target_source_version"]
        == source_b_version
    )
    assert (
        facts["baseline_identity"] == facts["incoming_identity"] == manifest["identity"]
    )
    for item_id in (OLD_ASSET, NEW_ASSET):
        (approval,) = [
            row
            for row in plan["approvals"]
            if row["change_id"] == changes[item_id] and row["domain"] == "attachment"
        ]
        assert (
            approval["choice"] == "current"
            and approval["provenance"] == "explicit_user"
        )
        decisions[item_id] = approval["decision_id"]
    (subject,) = [
        row
        for row in facts["subjects"]
        if row["item_id"] == OLD_ASSET and row["facet"] == "asset"
    ]
    assert (
        subject["baseline"]["status"] == "unknown"
        and subject["baseline"]["content"] is None
    )
    assert subject["incoming"] is None and subject["current"]["path"] == OLD_PATH
    proof = subject["attachment"]["retained_ownership"]
    assert proof["checkpoint_commit"] == published_a.result_commit
    assert proof["association_id"] == checkpoint_b.locator.association.association_id
    assert (
        proof["source_version"] == source_a_version and proof["source_path"] == OLD_PATH
    )
    assert proof["mapping_sha256"] == hashlib.sha256(source_a_record).hexdigest()
    assert proof["payload_sha256"] == hashlib.sha256(ORIGINAL).hexdigest()
    assert proof["payload_size"] == len(ORIGINAL) and proof["payload_mode"] == "100644"
    (retained_row,) = [row for row in manifest["vault"] if row["path"] == OLD_PATH]
    assert retained_row["size"] == size and retained_row["sha256"] == expected_digest
    retained = git(vault, "cat-file", "blob", saved_commit + ":vault/" + OLD_PATH)
    assert (
        len(retained) == size
        and hashlib.sha256(retained).hexdigest() == expected_digest
        and retained[: len(prefix)] == prefix
    )
    del retained
    # This tiny declared vault payload has no reconciliation subject. Losing it
    # leaves the large canonical review readable while requiring real graph repair.
    (protected_row,) = [
        row for row in manifest["vault"] if row["path"] == protected_path
    ]
    assert (
        protected_row["object_id"] == protected_oid
        and protected_row["sha256"] == protected_digest
    )
    assert protected_row["size"] == len(protected)
    assert protected_digest.encode() not in review_raw
    assert protected_oid != manifest["review_object"]
    assert all(
        row["object_id"] != protected_oid and row["sha256"] != protected_digest
        for row in manifest["review_content"]
    )
    assert git(vault, "cat-file", "blob", protected_oid) == protected
    closed = worker_context_call(
        warm, {"command": "close", "binding": saved.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and _tree(scratch) == scratch_before
    del warm, page, state
    locator = (vault / ".brz2obsidian/locator.json").read_bytes()
    refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    matching = root / "complete-matching-copy"
    shutil.copytree(vault, matching)
    copy_before = _tree(matching)
    object_path = vault / ".git/objects" / protected_oid[:2] / protected_oid[2:]
    assert object_path.resolve().is_relative_to((vault / ".git/objects").resolve())
    assert object_path.is_file()
    # Only the independently identified loose blob in the owned test fixture is removed.
    object_path.chmod(stat.S_IWRITE)
    object_path.unlink()
    assert (vault / "Later.md").read_bytes() == later
    damaged = _tree(vault)
    operations = Operations()
    validation = operations.validate_history_copy(vault, matching)
    assert (
        validation.status == "matching"
        and validation.code == "exact_missing_dependency"
    ), validation.model_dump_json()
    assert validation.target_commit == validation.copy_commit == saved_commit
    assert (
        validation.target_generation
        == validation.copy_generation
        == saved.binding.checkpoint_generation
    )
    assert tuple(row.object_id for row in validation.missing_objects) == (
        protected_oid,
    )
    assert validation.damaged_objects == ()
    preparation = operations.prepare_history_repair(vault, matching, validation)
    assert preparation.status == "prepared", preparation.model_dump_json()
    assert _tree(vault) == damaged and _tree(matching) == copy_before
    repaired = operations.execute_history_repair(vault, matching, preparation)
    assert repaired.status == "repaired" and repaired.history_retained, (
        repaired.model_dump_json()
    )
    assert repaired.object_storage == "verified" and repaired.objects_written == 1
    assert repaired.authored_files_changed is False
    assert git(vault, "cat-file", "blob", protected_oid) == protected
    assert _tree(matching) == copy_before
    restored_relative = object_path.relative_to(vault).as_posix()
    assert tuple(row for row in _tree(vault) if row[0] != restored_relative) == damaged
    assert (
        git(vault, "cat-file", "blob", saved_commit + ":manifest.json") == manifest_raw
    )
    assert git(vault, "cat-file", "blob", manifest["review_object"]) == review_raw
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs
    assert user_git(vault) == original_user and _tree(scratch) == scratch_before
    cold = UpdateContext()
    loaded = worker_context_call(
        cold,
        {
            "command": "load",
            "vault": str(vault),
            "selection_id": "22222222-2222-4222-8222-222222222222",
        },
    )
    assert loaded.code == "revalidation_required" and loaded.next_actions == (
        "resume_update",
    )
    assert loaded.checkpoint_commit == saved_commit and loaded.binding is None
    resumed = worker_context_call(
        cold,
        {
            "command": "resume",
            "vault": str(vault),
            "selection_id": "22222222-2222-4222-8222-222222222222",
        },
    )
    assert resumed.status == "prepared_review" and resumed.code == "unchanged", (
        resumed.model_dump_json()
    )
    assert (
        resumed.kind == "attachment_cleanup"
        and resumed.ready
        and resumed.unresolved == 0
    )
    assert resumed.binding.context_id != saved.binding.context_id
    assert (
        resumed.binding.proposal_id == saved.binding.proposal_id
        and resumed.binding.generation == saved.binding.generation
    )
    assert (
        resumed.binding.checkpoint_commit == saved_commit
        and resumed.binding.checkpoint_generation == saved.binding.checkpoint_generation
    )
    choices = worker_context_call(
        cold, {"command": "choices", "binding": resumed.binding}
    )
    assert choices.status == "available" and choices.next_choice_offset is None
    for item_id in (NEW_ASSET, OLD_ASSET):
        (offer,) = [
            offer
            for offer in choices.offers
            if offer.change_id == changes[item_id] and offer.domain == "attachment"
        ]
        assert offer.selected == "current" and offer.decision_id == decisions[item_id]
    closed = worker_context_call(
        cold, {"command": "close", "binding": resumed.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and _tree(scratch) == scratch_before
    assert observations
    assert user_git(vault) == original_user
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator
    assert (
        git(vault, "cat-file", "blob", terminal_b + ":manifest.json") == terminal_b_raw
    )
    assert git(vault, "cat-file", "blob", manifest["review_object"]) == review_raw
    assert _tree(root / "source") == source_before
    assert (_digest(archive_a), _digest(archive_b)) == archives_before
    assert _tree(matching) == copy_before
    assert {
        path.relative_to(vault).as_posix(): _digest(path)
        for path in vault.rglob("*")
        if path.is_file()
        and path.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    } == authored
    assert (vault / "Manual.md").read_bytes() == manual
    assert (vault / "Later.md").read_bytes() == later and (
        vault / NEW_PATH
    ).read_bytes() == incoming_b
    assert (vault / OLD_PATH).stat().st_size == size and _digest(
        vault / OLD_PATH
    ) == expected_digest
