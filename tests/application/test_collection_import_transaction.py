"""Native transaction scenarios for unrelated collection review."""

import json
import subprocess
import sys

import pytest

from brz2obsidian.application.checkpoint_payload_contracts import (
    CheckpointPayloadRequest,
)
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_facts import output_identity
from tests.application.test_collection_import_facts import _incoming_brain
from tests.application.test_vault_checkpoints import fixture_case, git, user_state
from tests.reconciliation.test_resolution import action


def _payload(directory, collection, *, scoped, body, asset=False):
    path_b, record_b, sample = _incoming_brain()
    path = path_b if scoped else "Opening.md"
    record_path = record_b if scoped else "migration-record.json"
    if collection == "brain-c":
        path = path.replace("Brain B", "Brain C")
        record_path = record_path.replace("Brain B", "Brain C")
    record = json.loads(sample[record_b])
    record["source_identity"]["source_id"] = collection
    record["source_identity"]["snapshot_digest"] = body.decode().strip()
    record["item_targets"][0]["relative_path"] = path
    if asset:
        asset_path = (
            record_path.removesuffix("migration-record.json") + "Assets/protected.bin"
        )
        record["asset_targets"] = [
            {"asset_id": "protected", "relative_path": asset_path}
        ]
        (directory / asset_path).parent.mkdir(parents=True, exist_ok=True)
        (directory / asset_path).write_bytes(
            b"Protected " + collection.encode() + b"\x00\xff"
        )
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
            source_a,
            "brain-a",
            scoped=False,
            body=b"Original A.\r\n",
            asset=True,
        )
        (vault / path).write_bytes(note)
        (vault / record_path).write_bytes((source_a / record_path).read_bytes())
        protected = "Assets/protected.bin"
        (vault / protected).parent.mkdir()
        (vault / protected).write_bytes((source_a / protected).read_bytes())
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


def _protected_owners(vault, *paths):
    with Operations().inspect_update_inputs(vault) as observed:
        locator = observed.history.checkpoint.locator
        return {
            proof.source_path: proof.identity.collection_id
            for proof in observed.read_attachment_ownership(
                locator=locator, paths=paths
            )
        }


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
    saved = operations.save_update(offered.preparation)
    assert saved.code == "saved", saved
    operations = Operations()
    resumed = operations.resume_update(vault)
    assert resumed.code == "resumed", resumed
    applied = operations.apply_update(resumed.preparation.model_dump())
    assert applied.status == "applied", applied
    assert (vault / path).read_bytes() == note
    assert _source_note(vault, "brain-b", path).chunks[0].data == note
    assert operations.load_update(vault).code == "saved_update_unavailable"
    assert operations.resume_update(vault).code == "saved_update_unavailable"
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
                choice="reverse" if requirement.domain == "reversal" else "current",
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


def test_alternating_updates_use_each_exact_baseline_and_keep_the_moved_location():
    vault = _vault(established=True)
    before = _user_git(vault)
    original_a = (vault / "Opening.md").read_bytes()
    source_b = vault.parent / "brain-b"
    path_b, record_b, original_b, _ = _payload(
        source_b, "brain-b", scoped=True, body=b"Original B.\r\n", asset=True
    )
    operations = Operations()
    imported = operations.prepare_collection_import(
        vault, source_b, record_path=record_b
    )
    assert operations.apply_update(imported.preparation).status == "applied"
    moved_path = "Moved/Loose note.md"
    (vault / moved_path).parent.mkdir()
    (vault / path_b).rename(vault / moved_path)

    for collection, scoped, expected_prior, observed_path, body in (
        ("brain-a", False, original_a, "Opening.md", b"Second A.\r\n"),
        ("brain-b", True, original_b, moved_path, b"Second B.\r\n"),
    ):
        source = vault.parent / (collection + "-next")
        source_path, record_path, incoming, _ = _payload(
            source, collection, scoped=scoped, body=body, asset=True
        )
        current = operations.prepare_collection_update(
            vault, source, record_path=record_path
        )
        assert current.ready, current.preparation.review.blockers
        note = next(
            row
            for row in current.preparation.review.facts.subjects
            if row.item_id == "opening"
        )
        assert (
            note.baseline.content.data,
            note.current.path,
            note.current.content.data,
            note.incoming.data,
        ) == (expected_prior, observed_path, expected_prior, incoming)
        applied = operations.apply_update(current.preparation)
        assert applied.status == "applied", applied
        assert (vault / observed_path).read_bytes() == incoming
        assert _source_note(vault, collection, source_path).chunks[0].data == incoming
        if collection == "brain-a":
            expected_a = incoming
            assert (vault / moved_path).read_bytes() == original_b
            assert _source_note(vault, "brain-b", path_b).chunks[0].data == original_b
    assert (vault / "Opening.md").read_bytes() == expected_a
    assert _source_note(vault, "brain-a", "Opening.md").chunks[0].data == expected_a
    assert not (vault / path_b).exists()
    assert _protected_owners(
        vault, "Assets/protected.bin", "Imports/Brain B/Assets/protected.bin"
    ) == {
        "Assets/protected.bin": "brain-a",
        "Imports/Brain B/Assets/protected.bin": "brain-b",
    }
    assert Operations().prepare_undo(vault).status == "offered"
    assert _user_git(vault) == before


_PREPARED_REF_EXIT = """
import os
import sys
from pathlib import Path
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_contracts import UpdatePreparation
from brz2obsidian.publication import vault_history

publish = vault_history._publish_locator
def stop_after_ref(root, git, association, manifest, writes):
    if manifest.collection_preparation_owner is not None:
        git.call('update-ref', writes.ref, writes.commit, manifest.previous)
        os._exit(81)
    return publish(root, git, association, manifest, writes)

vault_history._publish_locator = stop_after_ref
plan = UpdatePreparation.model_validate_json(Path(sys.argv[1]).read_bytes())
result = Operations().apply_update(plan)
print(result.model_dump_json(), flush=True)
"""


@pytest.mark.parametrize("boundary", ["prepared", "ref_before_locator"])
def test_unpublished_preparation_restores_saved_review_and_keeps_latest_undo(
    monkeypatch, boundary
):
    from brz2obsidian.publication import vault_apply

    vault = _vault(established=True)
    before = _user_git(vault)
    source_b = vault.parent / "brain-b"
    path_b, record_b, bytes_b, _ = _payload(
        source_b, "brain-b", scoped=True, body=b"Completed B.\r\n"
    )
    operations = Operations()
    initial = operations.prepare_collection_import(
        vault, source_b, record_path=record_b
    )
    completed = operations.apply_update(initial.preparation)
    assert completed.status == "applied", completed
    source_c = vault.parent / "brain-c"
    path_c, record_c, _, _ = _payload(
        source_c, "brain-c", scoped=True, body=b"Unpublished C.\r\n"
    )
    review = operations.prepare_collection_import(vault, source_c, record_path=record_c)
    assert review.ready, review
    if boundary == "ref_before_locator":
        plan = vault.parent / "collection-preparation.json"
        plan.write_text(review.preparation.model_dump_json(), encoding="utf-8")
        process = subprocess.run(
            [sys.executable, "-c", _PREPARED_REF_EXIT, str(plan)],
            capture_output=True,
            check=False,
            timeout=120,
        )
        assert process.returncode == 81, (process.stdout, process.stderr)
    else:
        stopped = False
        retain = vault_apply._retain_apply_preparation

        def cancel_after_prepared(*args, **kwargs):
            result = retain(*args, **kwargs)
            nonlocal stopped
            stopped = result is None
            return result

        with monkeypatch.context() as injection:
            injection.setattr(
                vault_apply, "_retain_apply_preparation", cancel_after_prepared
            )
            outcome = operations.apply_update(
                review.preparation, cancel=lambda: stopped
            )
        assert outcome.status == "recovery_required", outcome
        assert outcome.application.intent_commit is None
        assert outcome.application.published_files == 0
    fresh = Operations()
    offered = fresh.prepare_recovery(vault, direction="restore")
    assert offered.status == "cleanup", offered
    assert offered.unpublished_checkpoint and offered.intent_commit is None
    recovered = fresh.execute_recovery(vault, offered)
    assert recovered.code == "saved_collection_review_restored", recovered
    assert not recovered.authored_files_changed and not recovered.recovery_required
    resumed = fresh.resume_update(vault)
    assert resumed.code == "resumed", resumed
    assert resumed.operation_id == review.operation_id
    assert not (vault / path_c).exists()
    assert not (vault / record_c).exists()
    assert (vault / path_b).read_bytes() == bytes_b
    assert _source_note(vault, "brain-b", path_b).chunks[0].data == bytes_b
    discarded = fresh.discard_saved_review(
        vault, expected_commit=resumed.checkpoint_commit
    )
    assert discarded.code == "saved_review_discarded", discarded
    undo = fresh.prepare_undo(vault)
    assert undo.target_receipt_commit == completed.application.receipt_commit
    assert _user_git(vault) == before
