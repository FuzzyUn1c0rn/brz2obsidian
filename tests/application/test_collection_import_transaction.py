"""Native transaction scenarios for unrelated collection review."""

import json

import pytest

from brz2obsidian.application.checkpoint_payload_contracts import (
    CheckpointPayloadRequest,
)
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_facts import output_identity
from tests.application.test_collection_import_facts import _incoming_brain
from tests.application.test_vault_checkpoints import fixture_case, git, user_state
from tests.reconciliation.test_resolution import action


def _payload(directory, collection, *, scoped, body):
    path_b, record_b, sample = _incoming_brain()
    path = path_b if scoped else "Opening.md"
    record_path = record_b if scoped else "migration-record.json"
    record = json.loads(sample[record_b])
    record["source_identity"]["source_id"] = collection
    record["source_identity"]["snapshot_digest"] = body.decode().strip()
    record["item_targets"][0]["relative_path"] = path
    note = (
        sample[path_b].split(b"New B text.")[0].replace(b"brain-b", collection.encode())
        + body
    )
    for relative, raw in ((path, note), (record_path, json.dumps(record).encode())):
        (directory / relative).parent.mkdir(parents=True, exist_ok=True)
        (directory / relative).write_bytes(raw)
    return path, record_path, note, record


def _vault(*, established):
    vault, source_a = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Manual.md").write_bytes(b"Independent authored bytes.\r\n")
    (vault / ".obsidian").mkdir()
    (vault / ".obsidian/app.json").write_bytes(b'{"alwaysUpdateLinks":true}\r\n')
    if established:
        path, record_path, note, record = _payload(
            source_a, "brain-a", scoped=False, body=b"Original A.\r\n"
        )
        (vault / path).write_bytes(note)
        (vault / record_path).write_bytes((source_a / record_path).read_bytes())
        operations = Operations()
        captured = operations.capture_checkpoint(
            vault,
            source_a,
            vault_id="test-vault",
            import_id="stage-one",
            identity=output_identity(record),
            admission=operations.inspect_history(vault).admission,
        )
        assert captured.status == "captured", captured.code
    git(vault, "add", "Manual.md")
    git(vault, "commit", "-qm", "Authored history")
    git(vault, "branch", "independent")
    (vault / "Manual.md").write_bytes(b"Staged authored bytes.\n")
    git(vault, "add", "Manual.md")
    (vault / "Manual.md").write_bytes(b"Unstaged authored bytes.\r\n")
    return vault


def _user_git(vault):
    observed = user_state(vault)
    return (
        observed["index"],
        observed["head"],
        observed["config"],
        observed["stages"],
        tuple(row for row in observed["refs"] if row.startswith(b"refs/heads/")),
    )


def _source_note(vault, collection, path):
    operations = Operations()
    locator = operations.read_checkpoint(vault).locator
    return operations.read_checkpoint_payload(
        vault,
        locator=locator,
        collection=("thebrain-brz", collection),
        requests=(CheckpointPayloadRequest(path=path, limit=4096),),
        byte_limit=4096,
    )


def _choose_undo(operations, vault, undo, keep_path):
    while undo.review.requirements:
        requirement = undo.review.requirements[0]
        change = next(
            row
            for row in undo.review.proposal.changes
            if row.change_id == requirement.change_id
        )
        undo = operations.resolve_undo(
            vault,
            undo,
            action(
                undo.review,
                change,
                domain="reversal",
                choice="current" if change.path == keep_path else "reverse",
                decision_id="undo:" + change.change_id,
            ),
        )
        assert undo.status == "offered", undo.code
    return undo


def test_first_import_undo_keeps_later_bytes_and_blocks_duplicate_identity():
    vault = _vault(established=False)
    before = _user_git(vault)
    source = vault.parent / "brain-b"
    path, record_path, note, _ = _payload(
        source, "brain-b", scoped=True, body=b"Original B.\r\n"
    )
    operations = Operations()
    offered = operations.prepare_collection_import(
        vault, source, record_path=record_path
    )
    assert offered.ready, offered
    cancelled = operations.apply_update(offered.preparation, cancel=lambda: True)
    assert cancelled.status == "cancelled_before_publication", cancelled
    assert operations.read_checkpoint(vault).status == "absent"
    applied = operations.apply_update(offered.preparation)
    assert applied.status == "applied", applied
    assert (vault / path).read_bytes() == note
    assert _source_note(vault, "brain-b", path).chunks[0].data == note
    edited = note + b"Later authored words.\r\n"
    (vault / path).write_bytes(edited)
    operations = Operations()
    undo = operations.prepare_undo(vault)
    assert undo.status == "offered", undo
    assert undo.target_receipt_commit == applied.application.receipt_commit
    undo = _choose_undo(operations, vault, undo, path)
    result = operations.execute_undo(vault, undo)
    assert result.status == "undone", result
    assert (vault / path).read_bytes() == edited
    assert not (vault / record_path).exists()
    assert _source_note(vault, "brain-b", path).code == "collection_not_active"
    duplicate = operations.prepare_collection_import(
        vault, source, record_path=record_path
    )
    assert duplicate.code == "retained_source_identity_conflict"
    assert _user_git(vault) == before


@pytest.mark.parametrize("direction", ["finish", "restore"])
def test_interrupted_second_import_resolves_without_changing_first_collection(
    direction,
):
    vault = _vault(established=True)
    before = _user_git(vault)
    source = vault.parent / "brain-b"
    path, record_path, note, _ = _payload(
        source, "brain-b", scoped=True, body=b"Original B.\r\n"
    )
    note_a = (vault / "Opening.md").read_bytes()
    settings = (vault / ".obsidian/app.json").read_bytes()
    operations = Operations()
    offered = operations.prepare_collection_import(
        vault, source, record_path=record_path
    )
    assert offered.ready, offered
    stopped = False

    def progress(value):
        nonlocal stopped
        if value.phase == "publication" and value.completed_units == 1:
            stopped = True

    pending = operations.apply_update(
        offered.preparation, cancel=lambda: stopped, progress=progress
    )
    assert pending.status == "recovery_required", pending
    assert pending.application.intent_commit
    assert pending.application.published_files == 1
    operations = Operations()
    offered_recovery = operations.prepare_recovery(vault, direction=direction)
    assert offered_recovery.status == "offered", offered_recovery
    while offered_recovery.review.requirements:
        review = offered_recovery.review
        requirement = review.requirements[0]
        change = next(
            row
            for row in review.proposal.changes
            if row.change_id == requirement.change_id
        )
        offered_recovery = operations.resolve_recovery(
            vault,
            offered_recovery,
            action(
                review,
                change,
                domain=requirement.domain,
                choice="reverse" if requirement.domain == "reversal" else "approve",
                decision_id="recover:" + change.change_id,
            ),
        )
        assert offered_recovery.status == "offered", offered_recovery
    recovered = operations.execute_recovery(vault, offered_recovery)
    if direction == "finish":
        assert recovered.status == "applied", recovered
        assert (vault / path).read_bytes() == note
        assert _source_note(vault, "brain-b", path).chunks[0].data == note
    else:
        assert recovered.status == "restored", recovered
        assert not (vault / path).exists()
        assert not (vault / record_path).exists()
        assert _source_note(vault, "brain-b", path).code == "collection_not_active"
    assert (vault / "Opening.md").read_bytes() == note_a
    assert _source_note(vault, "brain-a", "Opening.md").chunks[0].data == note_a
    assert (vault / ".obsidian/app.json").read_bytes() == settings
    assert _user_git(vault) == before
