"""Explicit historical evidence alone qualifies owned onboarding originals."""

import hashlib
import json
import tempfile
from pathlib import Path
from uuid import uuid4

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context import UpdateContext
from tests.application.test_owned_update_preparation import _digest, _tree
from tests.application.test_update_context import worker_context_call
from tests.application.test_vault_checkpoints import git, user_state
from tests.application.test_verified_coverage import (
    add_attachment,
    change_record,
    source_parts,
    write_source,
)
from tests.support.recorded_format8 import format8_workflow


def test_explicit_original_evidence_qualifies_owned_onboarding_bytes(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-363-originals-"))
    marker = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(marker), encoding="utf-8")
    evidence = (
        Path(__file__).resolve().parents[2]
        / "tmp/r347-owned-onboarding-20261109/fixtures"
    )
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (marker["owner"] + ".json")).write_text(
        json.dumps(marker), encoding="utf-8"
    )
    original_directory, mismatched_directory = root / "original", root / "mismatched"
    original_directory.mkdir()
    mismatched_directory.mkdir()
    asset_id = "66666666-6666-4666-8666-666666666666"
    asset_path = "Attachments/22222222/payload.bin"
    original = b"\xffExact historical binary.\r\n"
    current = b"\xfeIndependently authored binary.\r\n"
    unrelated = b"\xffDifferent source evidence.\r\n"
    parts = source_parts(original_directory)
    add_attachment(parts, asset_id, 1, "payload.bin", original)
    archive = write_source(original_directory, parts)
    parts["22222222-2222-4222-8222-222222222222/payload.bin"] = unrelated
    change_record(parts, asset_id, DataLength=len(unrelated))
    mismatched = write_source(mismatched_directory, parts)
    workflow = format8_workflow()
    metadata = workflow.metadata_factory()
    workflow.metadata_factory = lambda: metadata
    vault = root / "vault"
    converted = workflow.convert(archive, vault)
    assert converted.receipt is not None and converted.receipt.verified, converted
    assert (vault / asset_path).read_bytes() == original
    record_raw = (vault / "migration-record.json").read_bytes()
    recorded = json.loads(record_raw)
    assert recorded["schema_version"] == 8
    assert recorded["run_metadata"]["renderer_version"] == "8"
    (vault / asset_path).write_bytes(current)
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Personal.md").write_bytes(b"Committed independent writing.\r\n")
    git(vault, "add", "Personal.md")
    git(vault, "commit", "-qm", "Independent original-evidence fixture")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    (vault / "Personal.md").write_bytes(b"Staged independent writing.\r\n")
    git(vault, "add", "Personal.md")
    (vault / "Personal.md").write_bytes(b"Unstaged independent writing.\r\n")
    scratch = root / "owned-temporary"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    operations = Operations(workflow=workflow)
    absent = operations.inspect_history(vault)
    assert absent.status == "absent" and absent.admission.status == "supported", absent
    assert (
        absent.admission.inventory_complete
        and absent.admission.repository.kind == "root"
    )
    before, scratch_before = user_state(vault), _tree(scratch)
    archives_before = _digest(archive), _digest(mismatched)
    refs_before = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    context = UpdateContext(operations=operations)
    rejected_original = worker_context_call(
        context,
        {
            "command": "prepare",
            "kind": "onboarding",
            "vault": str(vault),
            "source": str(archive),
            "original_source": str(mismatched),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    assert rejected_original.status == "prepared_review", rejected_original
    assert (
        rejected_original.binding is not None and not rejected_original.history_retained
    )
    assert rejected_original.binding.checkpoint_commit is None
    unknown_rows = []
    offset = 0
    while True:
        unknown = worker_context_call(
            context,
            {
                "command": "page",
                "binding": rejected_original.binding,
                "offset": offset,
                "byte_limit": 0,
            },
        )
        assert unknown.status == "available", unknown
        unknown_rows.extend(
            (offset + index, row) for index, row in enumerate(unknown.page.items)
        )
        if unknown.page.next_offset is None:
            break
        assert unknown.page.next_offset > offset
        offset = unknown.page.next_offset
    # The qualifier rejected the explicitly mismatched snapshot. The correct
    # incoming archive cannot fill any unknown original or establish a baseline.
    assert len(unknown_rows) == unknown.page.total > 0
    assert all(row.original is None for _, row in unknown_rows)
    unknown_index = next(
        index for index, row in unknown_rows if row.item_id == asset_id
    )
    unknown_bytes = worker_context_call(
        context,
        {
            "command": "page",
            "binding": rejected_original.binding,
            "offset": unknown_index,
            "limit": 1,
            "byte_limit": 256,
        },
    )
    assert unknown_bytes.status == "available", unknown_bytes
    unknown_asset = unknown_bytes.page.items[0]
    assert unknown_asset.item_id == asset_id and unknown_asset.original is None
    assert unknown_asset.current == current and unknown_asset.incoming == original
    assert not unknown_asset.omitted
    discarded = worker_context_call(
        context,
        {"command": "close", "binding": rejected_original.binding, "choice": "discard"},
    )
    assert discarded.code == "context_closed" and discarded.binding is None, discarded
    assert not discarded.history_retained
    assert operations.inspect_history(vault).status == "absent"
    assert not (vault / ".brz2obsidian").exists()
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs_before
    )
    assert user_state(vault) == before and _tree(scratch) == scratch_before

    matched = worker_context_call(
        context,
        {
            "command": "prepare",
            "kind": "onboarding",
            "vault": str(vault),
            "source": str(archive),
            "original_source": str(archive),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    assert matched.status == "prepared_review" and matched.binding is not None, matched
    matched_rows = []
    offset = 0
    while True:
        metadata_page = worker_context_call(
            context,
            {
                "command": "page",
                "binding": matched.binding,
                "offset": offset,
                "byte_limit": 0,
            },
        )
        assert metadata_page.status == "available", metadata_page
        matched_rows.extend(
            (offset + index, row) for index, row in enumerate(metadata_page.page.items)
        )
        if metadata_page.page.next_offset is None:
            break
        assert metadata_page.page.next_offset > offset
        offset = metadata_page.page.next_offset
    assert len(matched_rows) == metadata_page.page.total
    index = next(index for index, row in matched_rows if row.item_id == asset_id)
    page = worker_context_call(
        context,
        {
            "command": "page",
            "binding": matched.binding,
            "offset": index,
            "limit": 1,
            "byte_limit": 256,
        },
    )
    assert page.status == "available", page
    asset = page.page.items[0]
    assert asset.item_id == asset_id
    assert asset.original == asset.incoming == original and asset.current == current
    assert not asset.omitted and asset.current_path == asset.incoming_path == asset_path
    offer = next(
        offer
        for offer in page.offers
        if offer.change_id == asset.change_id and "current" in offer.choices
    )
    kept = worker_context_call(
        context,
        {
            "command": "choose",
            "binding": matched.binding,
            "requirement_id": offer.requirement_id,
            "choice": "current",
            "assumptions_digest": offer.assumptions_digest,
        },
    )
    assert kept.code == "accepted" and kept.binding is not None, kept
    saved = worker_context_call(context, {"command": "save", "binding": kept.binding})
    assert saved.code == "saved" and saved.capture is not None, saved
    assert saved.capture.status == "captured" and saved.history_retained
    assert saved.binding.checkpoint_generation == 1
    assert saved.binding.checkpoint_commit == saved.capture.commit
    assert saved.binding.revision > kept.binding.revision
    shown = worker_context_call(
        context,
        {
            "command": "page",
            "binding": saved.binding,
            "offset": index,
            "limit": 1,
            "byte_limit": 256,
        },
    )
    assert shown.status == "available", shown
    persisted = shown.page.items[0]
    assert persisted.item_id == asset_id and not persisted.omitted
    assert (
        persisted.original == persisted.incoming == original
        and persisted.current == current
    )
    selected = next(
        offer for offer in shown.offers if offer.change_id == persisted.change_id
    )
    assert selected.selected == "current" and selected.decision_id is not None
    assert len(shown.model_dump_json().encode()) < 16384
    assert context.page(matched.binding).code == "context_changed"
    assert context.page(kept.binding).code == "context_changed"
    foreign = saved.binding.model_copy(update={"context_id": str(uuid4())})
    assert context.page(foreign).code == "context_changed"
    manifest = json.loads(
        git(vault, "cat-file", "blob", saved.capture.commit + ":manifest.json")
    )
    envelope = json.loads(
        git(vault, "cat-file", "blob", saved.capture.commit + ":review.json")
    )
    assert manifest["previous"] is None and manifest["boundary"] == "local"
    assert git(
        vault, "rev-list", "--parents", "-n", "1", saved.capture.commit
    ).split() == [saved.capture.commit.encode()]
    facts = envelope["record"]["plan"]["facts"]
    operation = facts["format_operation"]
    assert operation["recorded_generation"] == "supported"
    assert (
        operation["baseline_source_version"]
        == recorded["source_identity"]["snapshot_digest"]
    )
    assert operation["established_baseline"] is not None
    subject = next(row for row in facts["subjects"] if row["item_id"] == asset_id)
    original_blob = {
        "__brz2obsidian_review_blob__": hashlib.sha256(original).hexdigest()
    }
    assert subject["baseline"]["status"] == "known"
    assert subject["baseline"]["content"]["data"] == original_blob
    assert subject["incoming"]["data"] == original_blob
    assert subject["current"]["content"]["data"] == {
        "__brz2obsidian_review_blob__": hashlib.sha256(current).hexdigest()
    }
    approval = next(
        row
        for row in envelope["record"]["plan"]["approvals"]
        if row["decision_id"] == selected.decision_id
    )
    assert approval["choice"] == "current" and approval["provenance"] == "explicit_user"
    assert not approval["source_accepted"]
    assert (
        git(vault, "cat-file", "blob", saved.capture.commit + ":source/" + asset_path)
        == original
    )
    assert (
        git(vault, "cat-file", "blob", saved.capture.commit + ":vault/" + asset_path)
        == current
    )
    assert not saved.capture.authored_files_changed
    closed = worker_context_call(
        context, {"command": "close", "binding": saved.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and closed.history_retained, closed
    assert user_state(vault, owned_ref=saved.capture.ref) == before
    assert (vault / "migration-record.json").read_bytes() == record_raw
    assert _tree(scratch) == scratch_before
    assert (_digest(archive), _digest(mismatched)) == archives_before
    assert (
        git(vault, "rev-parse", saved.capture.ref).decode().strip()
        == saved.capture.commit
    )
