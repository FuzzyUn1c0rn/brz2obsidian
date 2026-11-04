"""A saved complete real BRZ review applies and restarts with exact user state."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_contracts import UpdatePreparation
from tests.application.test_update_lifecycle import (
    _changed_archive,
    _finish_incoming,
    _seed,
    _user_state,
    case_path,
    git,
)
from tests.reconciliation.test_resolution import action

__all__ = ["case_path"]


def test_saved_complete_brz_review_applies_and_restarts_without_volatile_history(
    case_path,
):
    vault, initial = _seed(case_path, two_notes=True)
    note = vault / "Home — Entry thought.md"
    original_note = note.read_bytes()
    assert b"Authored body." in original_note
    note.write_bytes(original_note.replace(b"Authored body.", b"Local writing."))
    assert b"Local writing." in note.read_bytes()
    user_before = _user_state(vault)
    second_before = (vault / "Notes/Second thought.md").read_bytes()
    assert b"Second source.\r\n" in second_before
    incoming = _changed_archive(initial, case_path / "incoming.brz")
    offered = Operations().prepare_update(vault, incoming)
    assert offered.status == "prepared_review" and not offered.ready, offered
    prepared = offered.preparation
    first = next(
        c
        for c in prepared.review.proposal.changes
        if c.item_id == "22222222-2222-4222-8222-222222222222"
    )
    second = next(
        c
        for c in prepared.review.proposal.changes
        if c.item_id == "44444444-4444-4444-8444-444444444444"
    )
    kept = Operations().resolve_update(
        prepared,
        action(
            prepared.review, second, choice="current", decision_id="independent-second"
        ),
    )
    assert kept.code == "accepted", kept
    later = note.read_bytes() + b"\nLater independent writing.\r\n"
    note.write_bytes(later)
    refreshed = Operations().refresh_update(kept.preparation)
    assert refreshed.preparation is not None, refreshed
    current = refreshed.preparation
    assert current.review.proposal.generation == 2
    assert [a.decision_id for a in current.review.approvals] == ["independent-second"]
    event = current.review.history.events[-1]
    assert first.subject_id + ":current" in event.changed_keys
    assert "effect:" + second.subject_id not in event.invalidated_keys
    change = next(
        c for c in current.review.proposal.changes if c.item_id == first.item_id
    )
    edited_bytes = later.replace(b"Local writing.", b"Reviewed writing.")
    assert edited_bytes != later and b"Reviewed writing." in edited_bytes
    edited = Operations().resolve_update(
        current,
        action(
            current.review, change, choice="edited", decision_id="edited-after-refresh"
        ),
        edited=edited_bytes,
    )
    assert edited.code == "accepted", edited
    resolved = _finish_incoming(edited.preparation)
    assert resolved.review.ready and resolved.review.proposal.generation == 2
    expected = [a.decision_id for a in resolved.review.approvals]
    saved = Operations().save_update(resolved)
    assert saved.code == "saved", saved
    checkpoint = Operations().read_checkpoint(vault)
    assert saved.checkpoint == checkpoint.locator
    assert checkpoint.manifest.boundary == "local"
    assert checkpoint.manifest.identity == resolved.review.facts.baseline_identity
    assert checkpoint.manifest.reviewed_source.files == resolved.source_binding.files
    assert (
        checkpoint.manifest.observed_source.source_sha256
        == hashlib.sha256(incoming.read_bytes()).hexdigest()
    )
    original = next(
        r
        for r in checkpoint.manifest.source
        if r.path == "Attachments/22222222/Notes.md.original"
    )
    assert (
        original.sha256
        == "5ffa7716ee53174debb9b0ddfec17efa574c4e494b4bd1a321a0378c29016229"
    )
    persisted = case_path / "ready.json"
    script = (
        "import json, pathlib, sys\n"
        "from brz2obsidian.application.operations import Operations\n"
        "result = Operations().resume_update(sys.argv[1])\n"
        "if result.preparation is not None:\n"
        " pathlib.Path(sys.argv[2]).write_text(result.preparation.model_dump_json())\n"
        "print(json.dumps({'status':result.status,'code':result.code,'ready':result.ready,'decisions':[] if result.preparation is None else [a.decision_id for a in result.preparation.review.approvals]}))\n"
    )
    process = subprocess.run(
        [sys.executable, "-c", script, str(vault), str(persisted)],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    reopened = json.loads(process.stdout)
    assert reopened["ready"] and reopened["decisions"] == expected, reopened
    final = UpdatePreparation.model_validate_json(persisted.read_bytes())
    assert final.review.proposal.generation == 2 and final.review.ready
    assert final.source_binding.files == resolved.source_binding.files
    edited_approval = next(
        a for a in final.review.approvals if a.decision_id == "edited-after-refresh"
    )
    assert edited_approval.result.data == edited_bytes
    edited_action = next(
        a for a in final.review.actions if a.decision_id == "edited-after-refresh"
    )
    assert edited_action.candidate.content.data == edited_bytes
    assert (vault / "Home — Entry thought.md").read_bytes() == later
    ready = final
    payload = Path(ready.payload_directory) / "Attachments/22222222/Notes.md.original"
    bound_bytes = payload.read_bytes()
    assert bound_bytes == b"Incoming body.\r\n"
    locator_bytes = (vault / ".brz2obsidian/locator.json").read_bytes()
    refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    payload.write_bytes(b"Tampered owned B")
    denied = Operations().apply_update(ready)
    assert denied.status == "refused" and denied.code == "source_payload_changed", (
        denied
    )
    assert _user_state(vault) == user_before
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator_bytes
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs
    payload.write_bytes(bound_bytes)
    applied = Operations().apply_update(ready)
    assert applied.status == "applied", (applied.code, applied.application)
    assert (
        applied.publication == "complete" and applied.application.history == "terminal"
    )
    assert applied.vault == str(vault) and applied.changes == len(
        ready.review.proposal.changes
    )
    assert (vault / "Home — Entry thought.md").read_bytes() == edited_bytes
    assert (vault / "Notes/Second thought.md").read_bytes() == second_before
    assert (
        vault / "Attachments/22222222/Notes.md.original"
    ).read_bytes() == b"Incoming body.\r\n"
    assert (
        vault / "Attachments/44444444/Notes.md.original"
    ).read_bytes() == b"Incoming body.\r\n"
    assert _user_state(vault) == user_before
    receipt_id = applied.application.receipt_commit
    assert receipt_id is not None
    operation_ref = (
        ready.locator.association.ref.removesuffix("/checkpoints")
        + "/operations/"
        + applied.application.operation_id
    )
    assert git(vault, "rev-parse", operation_ref).decode().strip() == receipt_id
    again = Operations().prepare_update(vault, incoming)
    assert again.ready, again
    assert not again.preparation.review.requirements
    assert {
        m.provenance.decision_id
        for m in again.preparation.review.facts.source_version_memory
    } >= {"independent-second"}
    second_again = next(
        c
        for c in again.preparation.review.proposal.changes
        if c.item_id == "44444444-4444-4444-8444-444444444444"
    )
    assert second_again.result.data == second_before
    assert again.preparation.source_binding.files == ready.source_binding.files
    current_locator = (vault / ".brz2obsidian/locator.json").read_bytes()
    current_refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    duplicate = Operations().apply_update(again.preparation)
    assert duplicate.status == "no_content_change", duplicate
    assert duplicate.publication == "not_published" and duplicate.application is None
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == current_locator
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == current_refs
    )
    absent = Operations().prepare_update(vault, case_path / "initial.brz")
    assert absent.preparation is not None, absent
    second_absent = next(
        c
        for c in absent.preparation.review.proposal.changes
        if c.item_id == "44444444-4444-4444-8444-444444444444"
    )
    assert second_absent.incoming is None
    assert second_absent.result.data == second_before
    assert second_absent.preservation_review.kind == "source_absent"
    assert (vault / "Notes/Second thought.md").read_bytes() == second_before
    assert _user_state(vault) == user_before
