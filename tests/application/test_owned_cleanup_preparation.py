"""Owned cleanup keeps actual source-A ownership distinct from retained source B."""

import hashlib
import json
import tempfile
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

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
)
from tests.application.test_onboarding_completion import keep_current
from tests.application.test_owned_update_preparation import _digest, _tree
from tests.application.test_type_tag_updates import use_incoming
from tests.application.test_update_context import worker_context_call
from tests.application.test_update_lifecycle import _seed
from tests.application.test_vault_checkpoints import git, user_state


def _published_source_absence(root):
    """Publish both small native operations before adding any large current value."""
    vault, archive_a = _seed(root, capture_history=False)
    assert (vault / OLD_PATH).read_bytes() == ORIGINAL == b"Authored body.\r\n"
    (vault / "Manual.md").write_bytes(b"Independent user history.\r\n")
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "Independent history before converter operations")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    operations = Operations()
    onboarding = operations.prepare_onboarding(vault, archive_a)
    assert onboarding.preparation is not None, onboarding.model_dump_json()
    initial = keep_current(operations, onboarding.preparation)
    saved = operations.save_update(initial)
    assert saved.code == "saved", saved.model_dump_json()
    published_a = operations.apply_update(saved.preparation)
    assert published_a.status == "no_content_change", published_a.model_dump_json()
    assert published_a.application.history == "terminal"
    assert published_a.application.result_commit is not None
    source_a_record = (root / "source/migration-record.json").read_bytes()
    source_a_version = json.loads(source_a_record)["source_identity"]["snapshot_digest"]
    incoming_b = b"Independent source B attachment.\r\n"
    archive_b = root / "source-B.brz"
    with ZipFile(archive_a) as old, ZipFile(archive_b, "w") as new:
        for name in old.namelist():
            raw = old.read(name)
            if name == "attachments.json":
                record = json.loads(raw)
                record.update(
                    Id=NEW_ASSET, Location="Fresh.md", DataLength=len(incoming_b)
                )
                raw = json.dumps(record).encode()
            elif name == "meta.json":
                record = json.loads(raw)
                record["AttachmentFileStates"] = {NEW_ASSET: 1}
                raw = json.dumps(record).encode()
            elif name == "22222222-2222-4222-8222-222222222222/Notes.md":
                name = "22222222-2222-4222-8222-222222222222/Fresh.md"
                raw = incoming_b
            new.writestr(name, raw)
    offered = operations.prepare_update(vault, archive_b)
    assert offered.preparation is not None, offered.model_dump_json()
    prepared = use_incoming(operations, offered.preparation)
    published_b = operations.apply_update(prepared)
    assert published_b.status == "applied", published_b.model_dump_json()
    assert published_b.application.history == "terminal"
    assert (vault / OLD_PATH).read_bytes() == ORIGINAL
    assert (vault / NEW_PATH).read_bytes() == incoming_b
    checkpoint = operations.read_checkpoint(vault)
    assert checkpoint.status == "valid", checkpoint.code
    assert checkpoint.locator.commit == published_b.application.result_commit
    assert all(row.path != OLD_PATH for row in checkpoint.manifest.source)
    return (
        vault,
        archive_a,
        archive_b,
        published_a.application,
        checkpoint,
        source_a_record,
        source_a_version,
        incoming_b,
    )


def test_default_context_saves_and_cold_resumes_historically_owned_cleanup(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-366-cleanup-"))
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
    before_manifest = git(
        vault, "cat-file", "blob", checkpoint_b.locator.commit + ":manifest.json"
    )
    source_b_version = checkpoint_b.manifest.reviewed_source.target_source_version
    assert source_b_version != source_a_version
    size = 16 * 1024 * 1024
    prefix = b"\xffIndependent retained authored attachment\x00"
    raw = prefix + b"q" * (size - len(prefix))
    expected_digest = hashlib.sha256(raw).hexdigest()
    (vault / OLD_PATH).write_bytes(raw)
    del raw
    staged = b"Staged later user writing.\r\n"
    manual = b"Later independent ![[Attachments/22222222/Notes.md.original]].\r\n"
    (vault / "Manual.md").write_bytes(staged)
    git(vault, "add", "Manual.md")
    (vault / "Manual.md").write_bytes(manual)
    user_before = user_state(vault, owned_ref=checkpoint_b.locator.association.ref)
    user_before.pop("authored")
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
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    scratch_before = _tree(scratch)
    capacity = 96 * 1024 * 1024
    assert 9 * size + 64 * 1024 * 1024 > capacity
    observations = []

    def available_memory():
        observations.append(capacity)
        return capacity

    for module in (native, history, lifecycle, checkpoint_payload):
        monkeypatch.setattr(module, "available_memory", available_memory)
    warm = UpdateContext()
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
    assert opened.status == "prepared_review" and opened.kind == "attachment_cleanup", (
        opened.model_dump_json()
    )
    assert opened.binding is not None
    assert opened.binding.checkpoint_commit == checkpoint_b.locator.commit
    assert observations
    page = worker_context_call(
        warm, {"command": "page", "binding": opened.binding, "byte_limit": 0}
    )
    assert page.status == "available" and page.page.next_offset is None, (
        page.model_dump_json()
    )
    index, row = next(
        (index, row)
        for index, row in enumerate(page.page.items)
        if row.item_id == OLD_ASSET and row.facet == "asset"
    )
    shown = worker_context_call(
        warm,
        {
            "command": "page",
            "binding": opened.binding,
            "offset": index,
            "limit": 1,
            "byte_limit": 256,
        },
    )
    assert shown.status == "available", shown.model_dump_json()
    (displayed,) = shown.page.items
    assert displayed.original is None and displayed.incoming is None
    assert displayed.current_path == displayed.incoming_path == OLD_PATH
    assert len(prefix) <= len(displayed.current) <= 256 and displayed.omitted
    assert displayed.current == prefix + b"q" * (len(displayed.current) - len(prefix))
    assert (
        sum(
            len(value)
            for value in (
                displayed.original,
                displayed.current,
                displayed.incoming,
                displayed.result,
            )
            if value is not None
        )
        <= 256
    )
    (offer,) = [
        offer
        for offer in shown.offers
        if offer.change_id == row.change_id and offer.domain == "attachment"
    ]
    assert "current" in offer.choices and "remove" in offer.choices
    references = worker_context_call(
        warm,
        {
            "command": "references",
            "binding": opened.binding,
            "requirement_id": offer.requirement_id,
        },
    )
    assert references.status == "available" and references.next_reference_offset is None
    (reference,) = [
        reference
        for reference in references.references
        if reference.document_path == "Manual.md"
    ]
    assert (
        reference.old.path == OLD_PATH
        and reference.old.target_version == expected_digest
    )
    assert reference.old.status == "resolved" and reference.choices == ("drop",)
    chosen = worker_context_call(
        warm,
        {
            "command": "choose",
            "binding": opened.binding,
            "requirement_id": offer.requirement_id,
            "choice": "current",
            "assumptions_digest": offer.assumptions_digest,
        },
    )
    assert chosen.code == "accepted" and chosen.binding is not None, (
        chosen.model_dump_json()
    )
    saved = worker_context_call(warm, {"command": "save", "binding": chosen.binding})
    assert saved.code == "saved" and saved.capture is not None, saved.model_dump_json()
    assert saved.capture.status == "captured" and saved.history_retained
    assert saved.ready == chosen.ready
    assert saved.binding.checkpoint_generation == checkpoint_b.locator.generation + 1
    assert saved.binding.checkpoint_commit == saved.capture.commit
    manifest = json.loads(
        git(vault, "cat-file", "blob", saved.capture.commit + ":manifest.json")
    )
    assert (
        manifest["boundary"] == "local"
        and manifest["previous"] == checkpoint_b.locator.commit
    )
    assert manifest["source"] == json.loads(before_manifest)["source"]
    assert all(row["path"] != OLD_PATH for row in manifest["source"])
    assert all(row["path"] != OLD_PATH for row in manifest["reviewed_source"]["files"])
    assert manifest["reviewed_source"]["target_source_version"] == source_b_version
    assert manifest["identity"] == manifest["reviewed_source"]["incoming_identity"]
    assert (
        git(vault, "cat-file", "blob", saved.capture.commit + ":source/" + NEW_PATH)
        == incoming_b
    )
    plan = json.loads(
        git(vault, "cat-file", "blob", saved.capture.commit + ":review.json")
    )["record"]["plan"]
    assert plan["ready"] == saved.ready
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
    (subject,) = [
        subject
        for subject in facts["subjects"]
        if subject["item_id"] == OLD_ASSET and subject["facet"] == "asset"
    ]
    assert (
        subject["baseline"]["status"] == "unknown"
        and subject["baseline"]["content"] is None
    )
    assert subject["incoming"] is None and subject["current"]["path"] == OLD_PATH
    proof = subject["attachment"]["retained_ownership"]
    assert proof["association_id"] == checkpoint_b.locator.association.association_id
    assert proof["checkpoint_commit"] == published_a.result_commit
    assert proof["identity"] == {
        "collection_id": "11111111-1111-4111-8111-111111111111",
        "module_id": "thebrain-brz",
        "item_id": OLD_ASSET,
    }
    assert proof["facet"] == "asset" and proof["source_path"] == OLD_PATH
    assert proof["source_version"] == source_a_version
    assert proof["mapping_sha256"] == hashlib.sha256(source_a_record).hexdigest()
    assert proof["payload_sha256"] == hashlib.sha256(ORIGINAL).hexdigest()
    assert proof["payload_size"] == len(ORIGINAL) and proof["payload_mode"] == "100644"
    (approval,) = [
        approval
        for approval in plan["approvals"]
        if approval["change_id"] == row.change_id and approval["domain"] == "attachment"
    ]
    assert approval["choice"] == "current" and approval["provenance"] == "explicit_user"
    retained = git(
        vault, "cat-file", "blob", saved.capture.commit + ":vault/" + OLD_PATH
    )
    assert (
        len(retained) == size
        and hashlib.sha256(retained).hexdigest() == expected_digest
    )
    assert retained[: len(prefix)] == prefix
    del retained
    closed = worker_context_call(
        warm, {"command": "close", "binding": saved.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and closed.binding is None, (
        closed.model_dump_json()
    )
    assert _tree(scratch) == scratch_before
    del warm, page, shown
    refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    locator = (vault / ".brz2obsidian/locator.json").read_bytes()
    cold = UpdateContext()
    loaded = worker_context_call(
        cold,
        {
            "command": "load",
            "vault": str(vault),
            "selection_id": "22222222-2222-4222-8222-222222222222",
        },
    )
    assert loaded.status == "unresolved" and loaded.code == "revalidation_required", (
        loaded.model_dump_json()
    )
    assert (
        loaded.kind == "attachment_cleanup"
        and loaded.binding is None
        and not loaded.ready
    )
    assert loaded.checkpoint_commit == saved.capture.commit and loaded.next_actions == (
        "resume_update",
    )
    assert _tree(scratch) == scratch_before
    resumed = worker_context_call(
        cold,
        {
            "command": "resume",
            "vault": str(vault),
            "selection_id": "22222222-2222-4222-8222-222222222222",
        },
    )
    assert resumed.status == "prepared_review" and resumed.binding is not None, (
        resumed.model_dump_json()
    )
    assert resumed.kind == "attachment_cleanup" and resumed.code == "unchanged"
    assert resumed.ready == saved.ready
    assert resumed.binding.context_id != saved.binding.context_id
    assert resumed.binding.proposal_id == saved.binding.proposal_id
    assert resumed.binding.generation == saved.binding.generation
    assert resumed.binding.checkpoint_generation == saved.binding.checkpoint_generation
    assert resumed.binding.checkpoint_commit == saved.capture.commit
    assert cold.page(saved.binding).code == "context_changed"
    shown = worker_context_call(
        cold,
        {
            "command": "page",
            "binding": resumed.binding,
            "offset": index,
            "limit": 1,
            "byte_limit": 256,
        },
    )
    assert shown.status == "available", shown.model_dump_json()
    (displayed,) = shown.page.items
    assert (
        displayed.item_id == OLD_ASSET
        and displayed.original is None
        and displayed.incoming is None
    )
    assert displayed.current == prefix + b"q" * (len(displayed.current) - len(prefix))
    assert len(prefix) <= len(displayed.current) <= 256 and displayed.omitted
    selected = next(
        offer
        for offer in shown.offers
        if offer.change_id == displayed.change_id and offer.domain == "attachment"
    )
    assert (
        selected.selected == "current"
        and selected.decision_id == approval["decision_id"]
    )
    closed = worker_context_call(
        cold, {"command": "close", "binding": resumed.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and closed.binding is None, (
        closed.model_dump_json()
    )
    assert _tree(scratch) == scratch_before
    after = user_state(vault, owned_ref=saved.capture.ref)
    after.pop("authored")
    assert after == user_before
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator
    assert (
        git(vault, "cat-file", "blob", checkpoint_b.locator.commit + ":manifest.json")
        == before_manifest
    )
    assert _tree(root / "source") == source_before
    assert (_digest(archive_a), _digest(archive_b)) == archives_before
    assert {
        path.relative_to(vault).as_posix(): _digest(path)
        for path in vault.rglob("*")
        if path.is_file()
        and path.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    } == authored
    assert (vault / "Manual.md").read_bytes() == manual
    assert (vault / OLD_PATH).stat().st_size == size and _digest(
        vault / OLD_PATH
    ) == expected_digest

    # Cleanup requires the complete Markdown reference inventory, including a
    # genuinely ignored file with independent writing and no source references.
    ignore_path = vault / ".gitignore"
    previous_ignore = ignore_path.read_bytes() if ignore_path.exists() else b""
    expected_ignore = previous_ignore + b"\nPrivate-cleanup.md\n"
    ignore_path.write_bytes(expected_ignore)
    private = b"Independent private writing.\r\n"
    (vault / "Private-cleanup.md").write_bytes(private)
    assert (
        git(vault, "check-ignore", "--", "Private-cleanup.md").strip()
        == b"Private-cleanup.md"
    )
    refusal_before = user_state(vault, owned_ref=saved.capture.ref)
    refusal_before.pop("authored")
    refusal_authored = {
        path.relative_to(vault).as_posix(): _digest(path)
        for path in vault.rglob("*")
        if path.is_file()
        and path.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    }
    refused_context = UpdateContext()
    rejected = worker_context_call(
        refused_context,
        {
            "command": "prepare",
            "kind": "attachment_cleanup",
            "vault": str(vault),
            "source": None,
            "selection_id": "33333333-3333-4333-8333-333333333333",
        },
    )
    assert rejected.status == "refused" and rejected.kind == "attachment_cleanup", (
        rejected.model_dump_json()
    )
    assert (
        rejected.code == "excluded_dependency_requires_tracking"
        and rejected.next_actions == ("review_tracking",)
    )
    assert rejected.binding is None and not rejected.ready
    assert (
        rejected.publication == "not_started"
        and rejected.capture is None
        and rejected.operation is None
    )
    assert _tree(scratch) == scratch_before
    refusal_after = user_state(vault, owned_ref=saved.capture.ref)
    refusal_after.pop("authored")
    assert refusal_after == refusal_before
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator
    assert (vault / "Private-cleanup.md").read_bytes() == private
    assert ignore_path.read_bytes() == expected_ignore
    assert {
        path.relative_to(vault).as_posix(): _digest(path)
        for path in vault.rglob("*")
        if path.is_file()
        and path.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    } == refusal_authored
