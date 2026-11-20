"""A fresh default context restores saved unknown originals from owned history."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import brz2obsidian.application.update_lifecycle as lifecycle
import brz2obsidian.publication.vault_history as history
import brz2obsidian.publication.vault_native as native
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.publication import checkpoint_payload
from tests.application.test_owned_update_preparation import _digest, _tree
from tests.application.test_update_context import worker_context_call
from tests.application.test_vault_checkpoints import git, user_state
from tests.application.test_verified_coverage import (
    add_attachment,
    source_parts,
    write_source,
)
from tests.support.recorded_format8 import format8_workflow


def test_fresh_context_resumes_saved_unknown_binary_onboarding(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-364-"))
    owner = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(owner), encoding="utf-8")
    evidence = (
        Path(__file__).resolve().parents[2] / "tmp/r347-owned-resume-20261110/fixtures"
    )
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (owner["owner"] + ".json")).write_text(
        json.dumps(owner), encoding="utf-8"
    )
    source_directory = root / "source"
    source_directory.mkdir()
    parts = source_parts(source_directory)
    item_id = "66666666-6666-4666-8666-666666666666"
    asset_path = "Attachments/22222222/large.bin"
    size = 16 * 1024 * 1024
    raw = b"\xffIncoming binary\x00" + b"x" * (size - 17)
    assert len(raw) == size
    incoming_digest = hashlib.sha256(raw).hexdigest()
    add_attachment(parts, item_id, 1, "large.bin", raw)
    archive = write_source(source_directory, parts)
    del parts, raw
    workflow = format8_workflow()
    metadata = workflow.metadata_factory()
    workflow.metadata_factory = lambda: metadata
    rendered = root / "rendered"
    converted = workflow.convert(archive, rendered)
    assert converted.receipt is not None and converted.receipt.verified, converted
    assert (rendered / asset_path).stat().st_size == size
    assert _digest(rendered / asset_path) == incoming_digest

    vault = root / "vault"
    vault.mkdir()
    for path in rendered.iterdir():
        if path.name == "migration-record.json":
            continue
        if path.is_dir():
            shutil.copytree(path, vault / path.name)
        else:
            shutil.copy2(path, vault / path.name)
    current = b"\xfeIndependent authored binary.\r\n"
    (vault / asset_path).write_bytes(current)
    assert not (vault / "migration-record.json").exists()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Personal.md").write_bytes(b"Committed independent writing.\r\n")
    git(vault, "add", "Personal.md")
    git(vault, "commit", "-qm", "Independent legacy history")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    (vault / "Personal.md").write_bytes(b"Staged independent writing.\r\n")
    git(vault, "add", "Personal.md")
    (vault / "Personal.md").write_bytes(b"Unstaged independent writing.\r\n")
    scratch = root / "owned-temporary"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    before = user_state(vault)
    scratch_before, rendered_before = _tree(scratch), _tree(rendered)
    archive_before = _digest(archive)
    warm = UpdateContext(operations=Operations(workflow=workflow))
    opened = worker_context_call(
        warm,
        {
            "command": "prepare",
            "vault": str(vault),
            "source": str(archive),
            "selection_id": "11111111-1111-4111-8111-111111111111",
            "kind": "onboarding",
        },
    )
    assert opened.status == "prepared_review" and opened.binding is not None, opened
    page = worker_context_call(
        warm, {"command": "page", "binding": opened.binding, "byte_limit": 0}
    )
    assert page.status == "available", page
    row = next(
        row
        for row in page.page.items
        if row.item_id == item_id and row.facet == "asset"
    )
    assert row.original is None
    offer = next(
        offer
        for offer in page.offers
        if offer.change_id == row.change_id and offer.domain == "format"
    )
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
    assert chosen.code == "accepted" and chosen.binding is not None, chosen
    saved = worker_context_call(warm, {"command": "save", "binding": chosen.binding})
    assert saved.code == "saved" and saved.capture is not None, saved
    assert saved.capture.status == "captured" and saved.history_retained
    assert saved.binding.checkpoint_commit == saved.capture.commit
    assert saved.binding.checkpoint_generation == saved.binding.generation == 1
    envelope = json.loads(
        git(vault, "cat-file", "blob", saved.capture.commit + ":review.json")
    )
    plan = envelope["record"]["plan"]
    approval = next(
        approval
        for approval in plan["approvals"]
        if approval["change_id"] == row.change_id and approval["domain"] == "format"
    )
    assert approval["choice"] == "current" and approval["provenance"] == "explicit_user"
    assert not approval["source_accepted"]
    assert approval["attachment_selection"]["provenance"] == "explicit_user"
    assert all(
        subject["baseline"]["status"] == "unknown"
        and subject["baseline"]["content"] is None
        for subject in plan["facts"]["subjects"]
    )
    retained = git(
        vault, "cat-file", "blob", saved.capture.commit + ":source/" + asset_path
    )
    assert len(retained) == size
    assert hashlib.sha256(retained).hexdigest() == incoming_digest
    del retained
    assert (
        git(vault, "cat-file", "blob", saved.capture.commit + ":vault/" + asset_path)
        == current
    )
    assert user_state(vault, owned_ref=saved.capture.ref) == before
    closed = worker_context_call(
        warm, {"command": "close", "binding": saved.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and closed.binding is None, closed
    assert warm.page(saved.binding).code == "context_changed"
    assert _tree(scratch) == scratch_before
    del warm, opened, chosen, page, converted

    capacity = 96 * 1024 * 1024
    assert 9 * size + 64 * 1024 * 1024 > capacity
    capacity_observed = []

    def available_memory():
        capacity_observed.append(capacity)
        return capacity

    for module in (native, history, lifecycle, checkpoint_payload):
        monkeypatch.setattr(module, "available_memory", available_memory)
    operations = Operations(workflow=workflow)
    inline = operations.load_update(vault)
    # Eager tip loading exceeds 9U+64MiB. Native history discovery maps that
    # unavailable checkpoint to recovery_first before lifecycle history checks.
    assert inline.status == "recovery_required" and inline.code == "recovery_first", (
        inline
    )
    assert inline.next_actions == ("review_recovery",) and not inline.ready
    assert inline.loaded is None and inline.preparation is None
    assert capacity_observed
    refs_before = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    locator_before = (vault / ".brz2obsidian/locator.json").read_bytes()
    cold = UpdateContext(operations=operations)
    loaded = worker_context_call(
        cold,
        {
            "command": "load",
            "vault": str(vault),
            "selection_id": "22222222-2222-4222-8222-222222222222",
        },
    )
    assert loaded.status == "unresolved" and loaded.code == "revalidation_required", (
        loaded
    )
    assert loaded.kind == "onboarding" and not loaded.ready and loaded.binding is None
    assert loaded.history_retained and loaded.checkpoint_commit == saved.capture.commit
    assert loaded.changes == saved.changes and loaded.unresolved == saved.unresolved
    assert loaded.next_actions == ("resume_update",)
    assert _tree(scratch) == scratch_before
    resumed = worker_context_call(
        cold,
        {
            "command": "resume",
            "vault": str(vault),
            "selection_id": "22222222-2222-4222-8222-222222222222",
        },
    )
    assert resumed.status == "prepared_review" and resumed.code == "current", resumed
    assert resumed.kind == "onboarding" and resumed.binding is not None
    assert resumed.binding.context_id != saved.binding.context_id
    assert resumed.binding.proposal_id == saved.binding.proposal_id
    assert resumed.binding.generation == 1
    assert resumed.binding.checkpoint_commit == saved.capture.commit
    assert resumed.binding.checkpoint_generation == 1 and resumed.history_retained
    assert cold.page(saved.binding).code == "context_changed"
    foreign = resumed.binding.model_copy(
        update={"context_id": "33333333-3333-4333-8333-333333333333"}
    )
    assert cold.page(foreign).code == "context_changed"
    page = worker_context_call(
        cold, {"command": "page", "binding": resumed.binding, "byte_limit": 0}
    )
    index = next(
        index
        for index, row in enumerate(page.page.items)
        if row.item_id == item_id and row.facet == "asset"
    )
    shown = worker_context_call(
        cold,
        {
            "command": "page",
            "binding": resumed.binding,
            "offset": index,
            "limit": 1,
            "byte_offset": 0,
            "byte_limit": 256,
        },
    )
    assert shown.status == "available" and shown.page.status == "available", shown
    displayed = shown.page.items[0]
    assert displayed.item_id == item_id and displayed.original is None
    assert displayed.current_path == displayed.incoming_path == asset_path
    assert displayed.current == current
    assert 64 <= len(displayed.incoming) <= 256
    assert displayed.incoming == b"\xffIncoming binary\x00" + b"x" * (
        len(displayed.incoming) - 17
    )
    assert displayed.omitted and displayed.next_byte_offset == len(displayed.incoming)
    selected = next(offer for offer in shown.offers if offer.domain == "format")
    assert selected.selected == "current"
    assert selected.decision_id == approval["decision_id"]
    assert len(shown.model_dump_json().encode()) < 16384
    closed = worker_context_call(
        cold, {"command": "close", "binding": resumed.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and closed.binding is None, closed
    assert cold.page(resumed.binding).code == "context_changed"
    assert _tree(scratch) == scratch_before
    assert user_state(vault, owned_ref=saved.capture.ref) == before
    assert not (vault / "migration-record.json").exists()
    assert _tree(rendered) == rendered_before and _digest(archive) == archive_before
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs_before
    )
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator_before
