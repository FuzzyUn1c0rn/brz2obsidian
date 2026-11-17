"""Cold source-update resume keeps baseline and incoming role meanings distinct."""

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
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from brz2obsidian.cli_review import CliReviewResult
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


def test_fresh_context_resumes_saved_binary_original_source_update(monkeypatch, capsys):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-364-update-"))
    owner = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(owner), encoding="utf-8")
    evidence = (
        Path(__file__).resolve().parents[2] / "tmp/r347-owned-resume-20261110/fixtures"
    )
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (owner["owner"] + ".json")).write_text(
        json.dumps(owner), encoding="utf-8"
    )
    initial_directory, incoming_directory = root / "initial", root / "incoming"
    initial_directory.mkdir()
    incoming_directory.mkdir()
    parts = source_parts(initial_directory)
    item_id = "66666666-6666-4666-8666-666666666666"
    asset_path = "Attachments/22222222/large.bin"
    size = 16 * 1024 * 1024
    raw = b"\xffOriginal binary\x00" + b"x" * (size - 17)
    assert len(raw) == size
    original_digest = hashlib.sha256(raw).hexdigest()
    add_attachment(parts, item_id, 1, "large.bin", raw)
    initial_archive = write_source(initial_directory, parts)
    del raw
    workflow = default_workflow()
    metadata = workflow.metadata_factory()
    workflow.metadata_factory = lambda: metadata
    vault = root / "vault"
    converted = workflow.convert(initial_archive, vault)
    assert converted.receipt is not None and converted.receipt.verified, converted
    assert (vault / asset_path).stat().st_size == size
    assert _digest(vault / asset_path) == original_digest
    baseline = root / "baseline"
    shutil.copytree(vault, baseline)
    current = b"\xfeIndependent authored binary.\r\n"
    incoming = b"\xfdIndependent incoming binary.\r\n"
    (vault / asset_path).write_bytes(current)
    parts["22222222-2222-4222-8222-222222222222/large.bin"] = incoming
    change_record(parts, item_id, DataLength=len(incoming))
    incoming_archive = write_source(incoming_directory, parts)
    del parts
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Personal.md").write_bytes(b"Committed independent writing.\r\n")
    git(vault, "add", "Personal.md")
    git(vault, "commit", "-qm", "Independent user history")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    (vault / "Personal.md").write_bytes(b"Staged independent writing.\r\n")
    git(vault, "add", "Personal.md")
    (vault / "Personal.md").write_bytes(b"Unstaged independent writing.\r\n")
    scratch = root / "owned-temporary"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    operations = Operations(workflow=workflow)
    seed = operations.capture_checkpoint(
        vault,
        baseline,
        vault_id="owned-resume-vault",
        import_id="owned-resume-import",
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
    assert seed.status == "captured" and seed.locator.generation == 1, seed
    seed_manifest_raw = git(vault, "cat-file", "blob", seed.commit + ":manifest.json")
    seed_manifest = json.loads(seed_manifest_raw)
    assert seed_manifest["review_object"] is None
    source_row = next(
        row for row in seed_manifest["source"] if row["path"] == asset_path
    )
    assert source_row["size"] == size and source_row["sha256"] == original_digest
    before = user_state(vault, owned_ref=seed.ref)
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
    offer = next(
        offer
        for offer in page.offers
        if offer.change_id == row.change_id and offer.domain == "attachment"
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
    assert saved.binding.checkpoint_commit == saved.capture.commit != seed.commit
    assert saved.binding.checkpoint_generation == 2
    manifest = json.loads(
        git(vault, "cat-file", "blob", saved.capture.commit + ":manifest.json")
    )
    assert manifest["previous"] == seed.commit and manifest["boundary"] == "local"
    assert manifest["source"] == seed_manifest["source"]
    incoming_row = next(
        row for row in manifest["reviewed_source"]["files"] if row["path"] == asset_path
    )
    assert incoming_row["size"] == len(incoming)
    assert incoming_row["sha256"] == hashlib.sha256(incoming).hexdigest()
    envelope = json.loads(
        git(vault, "cat-file", "blob", saved.capture.commit + ":review.json")
    )
    plan = envelope["record"]["plan"]
    approval = next(
        approval
        for approval in plan["approvals"]
        if approval["change_id"] == row.change_id and approval["domain"] == "attachment"
    )
    assert approval["choice"] == "current" and approval["provenance"] == "explicit_user"
    assert not approval["source_accepted"]
    assert approval["attachment_selection"]["provenance"] == "explicit_user"
    memory = approval["source_memory"]
    assert memory["choice"] == "keep_vault" and memory["item_id"] == item_id
    assert memory["provenance"]["decision_id"] == approval["decision_id"]
    assert memory["reviewed_incoming"]["data"] == {
        "__brz2obsidian_review_blob__": hashlib.sha256(incoming).hexdigest()
    }
    retained = git(
        vault, "cat-file", "blob", saved.capture.commit + ":source/" + asset_path
    )
    assert len(retained) == size
    assert hashlib.sha256(retained).hexdigest() == original_digest
    del retained
    assert (
        git(vault, "cat-file", "blob", saved.capture.commit + ":vault/" + asset_path)
        == current
    )
    closed = worker_context_call(
        warm, {"command": "close", "binding": saved.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and closed.binding is None, closed
    assert _tree(scratch) == scratch_before
    assert user_state(vault, owned_ref=seed.ref) == before
    del warm, opened, chosen, page, converted

    # This new context cannot obtain the 16MiB ORIGINAL through eager tip load.
    capacity = 96 * 1024 * 1024
    assert 9 * size + 64 * 1024 * 1024 > capacity
    capacity_observed = []

    def available_memory():
        capacity_observed.append(capacity)
        return capacity

    for module in (native, history, lifecycle, checkpoint_payload):
        monkeypatch.setattr(module, "available_memory", available_memory)
    refs_before = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    locator_before = (vault / ".brz2obsidian/locator.json").read_bytes()
    cold = UpdateContext(operations=Operations(workflow=workflow))
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
    assert capacity_observed
    assert (
        loaded.kind == "source_update" and not loaded.ready and loaded.binding is None
    )
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
    assert resumed.status == "prepared_review" and resumed.code == "unchanged", resumed
    assert resumed.kind == "source_update" and resumed.binding is not None
    assert resumed.binding.context_id != saved.binding.context_id
    assert resumed.binding.proposal_id == saved.binding.proposal_id
    assert resumed.binding.generation == saved.binding.generation
    assert resumed.binding.checkpoint_generation == 2 and resumed.history_retained
    assert resumed.binding.checkpoint_commit == saved.capture.commit
    assert cold.page(saved.binding).code == "context_changed"
    foreign = resumed.binding.model_copy(
        update={"context_id": "33333333-3333-4333-8333-333333333333"}
    )
    assert cold.page(foreign).code == "context_changed"
    page = worker_context_call(
        cold, {"command": "page", "binding": resumed.binding, "byte_limit": 0}
    )
    assert page.status == "available", page
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
    assert displayed.item_id == item_id
    assert displayed.current_path == displayed.incoming_path == asset_path
    assert 64 <= len(displayed.original) <= 256
    assert displayed.original == b"\xffOriginal binary\x00" + b"x" * (
        len(displayed.original) - 17
    )
    assert displayed.current == current and displayed.incoming == incoming
    assert displayed.omitted and displayed.next_byte_offset == len(displayed.original)
    selected = next(offer for offer in shown.offers if offer.domain == "attachment")
    assert selected.selected == "current"
    assert selected.decision_id == approval["decision_id"]
    assert len(shown.model_dump_json().encode()) < 16384
    closed = worker_context_call(
        cold, {"command": "close", "binding": resumed.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and closed.binding is None, closed
    assert cold.page(resumed.binding).code == "context_changed"
    assert _tree(scratch) == scratch_before
    capsys.readouterr()
    exit_code = main(
        [
            "review",
            "inspect",
            str(vault),
            "--proposal-id",
            saved.binding.proposal_id,
            "--generation",
            str(saved.binding.generation),
            "--checkpoint",
            saved.capture.commit,
            "--offset",
            "0",
            "--limit",
            "100",
            "--byte-limit",
            "65536",
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0, captured.out
    assert captured.err == ""
    inspected = CliReviewResult.model_validate_json(captured.out)
    assert inspected.schema_ == "brz2obsidian.cli-review-result"
    assert inspected.schema_version == 1 and inspected.command == "inspect"
    assert inspected.kind == "source_update"
    assert inspected.status == "prepared_review" and inspected.code == "unchanged"
    assert inspected.proposal_id == saved.binding.proposal_id
    assert inspected.generation == saved.binding.generation
    assert (
        inspected.checkpoint_commit
        == inspected.checkpoint.commit
        == saved.capture.commit
    )
    assert inspected.checkpoint.generation == 2 and inspected.history_retained
    assert inspected.page.status == "available"
    displayed = next(row for row in inspected.page.items if row.item_id == item_id)
    assert displayed.current_path == displayed.incoming_path == asset_path
    assert 64 <= len(displayed.original) <= 65536
    assert displayed.original == b"\xffOriginal binary\x00" + b"x" * (
        len(displayed.original) - 17
    )
    assert displayed.current == current and displayed.incoming == incoming
    assert displayed.omitted and displayed.next_byte_offset == len(displayed.original)
    assert (
        sum(
            len(raw)
            for row in inspected.page.items
            for raw in (row.original, row.current, row.incoming, row.result)
            if raw is not None
        )
        <= 65536
    )
    selected = next(
        choice
        for choice in inspected.choices
        if choice.change_id == displayed.change_id and choice.domain == "attachment"
    )
    assert selected.selected == "current"
    assert selected.decision_id == approval["decision_id"]
    assert _tree(scratch) == scratch_before
    assert user_state(vault, owned_ref=seed.ref) == before
    assert _tree(baseline) == baseline_before
    assert (_digest(initial_archive), _digest(incoming_archive)) == archives_before
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs_before
    )
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator_before
    assert (
        git(vault, "cat-file", "blob", seed.commit + ":manifest.json")
        == seed_manifest_raw
    )
