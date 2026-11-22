import hashlib
import json

import pytest

from brz2obsidian.application.checkpoint_payload_contracts import (
    CheckpointPayloadRequest,
)
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_facts import assemble_facts
from brz2obsidian.core import prepare_review
from tests.application.test_vault_checkpoints import fixture_case, git
from tests.reconciliation.test_resolution import preflight


def _incoming_brain():
    path = "Imports/Brain B/Opening.md"
    record_path = "Imports/Brain B/migration-record.json"
    record = {
        "schema": "brz2obsidian.migration",
        "schema_version": 9,
        "profile_id": "fixture",
        "profile_version": "1",
        "source_identity": {
            "source_id": "brain-b",
            "module_id": "thebrain-brz",
            "module_version": "9",
            "snapshot_digest": "incoming-b",
            "format_version": "fixture/1",
            "source_sha256": "a" * 64,
        },
        "source_gaps": [],
        "item_targets": [
            {
                "original_identity": "opening",
                "item_key": "opening",
                "original_title": "Opening",
                "relative_path": path,
                "created": True,
            }
        ],
        "asset_targets": [],
    }
    note = b"---\nsource_collection_id: brain-b\nsource_item_id: opening\n---\nNew B text.\n"
    return (
        path,
        record_path,
        {path: note, record_path: json.dumps(record).encode("utf-8")},
    )


def test_first_import_distinguishes_unrelated_and_retained_source_identity():
    path, record_path, incoming = _incoming_brain()
    note = incoming[path]
    record = json.loads(incoming[record_path])
    record["original_excerpt"] = "[[Literal source evidence]]"
    incoming[record_path] = json.dumps(record).encode()

    def first_import(current):
        return assemble_facts(
            None,
            incoming,
            current,
            proposal_id="first-b",
            generation=1,
            record_path=record_path,
        )

    other = note.replace(b"brain-b", b"brain-a").replace(b"New B", b"Existing A")
    facts = first_import({"Opening.md": other})
    assert facts.format_operation.kind == "collection_import"
    assert facts.format_operation.established_baseline is None
    assert facts.format_operation.baseline_source_version is None
    planned = prepare_review(facts, preflight=preflight())
    opening = next(row for row in planned.proposal.changes if row.item_id == "opening")
    assert opening.path == path
    assert opening.disposition == "compatible"
    assert opening.result.data == note
    record_document = next(
        document
        for document in facts.link_context.incoming_documents
        if document.source_path == record_path
    )
    assert record_document.status == "supported"
    assert record_document.occurrences == ()
    assert planned.ready

    retained = note.replace(b"New B text.", b"Later authored text.")
    with pytest.raises(ValueError, match="^retained_source_identity_conflict$"):
        first_import({"Moved/Opening.md": retained})


def test_first_import_review_inspection_and_refresh_reobserve_current_inputs():
    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    path, record_path, incoming = _incoming_brain()
    for relative, raw in incoming.items():
        (source / relative).parent.mkdir(parents=True, exist_ok=True)
        (source / relative).write_bytes(raw)
    manual = vault / "Manual.md"
    manual.write_bytes(b"Original writing.\n")
    operations = Operations()
    offered = operations.prepare_collection_import(
        vault, source, record_path=record_path
    )
    assert offered.preparation is not None, offered.code
    assert offered.ready, offered.preparation.review.blockers
    prepared = offered.preparation
    assert prepared.locator is None

    def inspect(value):
        return operations.inspect_update_review(
            value,
            proposal_id=offered.operation_id,
            generation=value.review.proposal.generation,
        )

    page = inspect(prepared)
    assert page.status == "available", page.code
    refreshed = operations.refresh_update(prepared)
    assert refreshed.preparation is not None, refreshed.code
    assert refreshed.generation == offered.generation

    manual.write_bytes(b"Later writing.\r\n")
    assert inspect(prepared).status == "refused"
    changed = operations.refresh_update(prepared)
    assert changed.generation == offered.generation + 1, changed.code
    assert inspect(changed.preparation).status == "available"

    (source / path).write_bytes(incoming[path] + b"Changed source.\n")
    assert inspect(changed.preparation).code == "source_payload_changed"
    assert (
        operations.refresh_update(changed.preparation).code == "source_payload_changed"
    )
    assert operations.read_checkpoint(vault).status == "absent"


def test_scoped_update_binds_incoming_bytes_to_the_moved_note():
    path, record_path, original = _incoming_brain()
    record = json.loads(original[record_path])
    record["source_identity"]["snapshot_digest"] = "next-b"
    updated = original | {
        path: original[path].replace(b"New B text.", b"Latest B text."),
        record_path: json.dumps(record).encode(),
    }
    moved = "Moved/Opening.md"
    current = {moved: original[path], record_path: original[record_path]}
    facts = assemble_facts(
        original,
        updated,
        current,
        record_path=record_path,
        proposal_id="update-b",
        generation=1,
    )
    review = prepare_review(facts, preflight=preflight())
    assert review.ready, review.blockers
    from brz2obsidian.core import select_review_effects

    selected = select_review_effects(review)
    assert {row.path: row.content.data for row in selected.files} == {
        moved: updated[path],
        record_path: updated[record_path],
    }


def test_prepared_collection_without_intent_exposes_exact_recovery_authority():
    from brz2obsidian.publication.vault_apply import _acquire, _release

    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    path, record_path, incoming = _incoming_brain()
    for relative, raw in incoming.items():
        (source / relative).parent.mkdir(parents=True, exist_ok=True)
        (source / relative).write_bytes(raw)
    operations = Operations()
    prepared = operations.prepare_collection_import(
        vault, source, record_path=record_path
    )
    saved = operations.save_update(prepared.preparation)
    assert saved.code == "saved", saved
    association = saved.checkpoint.association
    plan = saved.preparation.review
    operation_id = "b" * 32
    _acquire(vault, operation_id)
    try:
        snapshot = operations.capture_checkpoint(
            vault,
            source,
            vault_id=association.vault_id,
            import_id=association.import_id,
            identity=plan.facts.incoming_identity,
            admission=operations.inspect_history(
                vault, active_operation=operation_id
            ).admission,
            review=plan,
            boundary="prepared",
            proposed=source,
            active_operation=operation_id,
            source_binding=saved.preparation.source_binding,
            observed_source=saved.preparation.observed_source,
        )
        assert snapshot.status == "captured", snapshot.code
    finally:
        _release(vault, operation_id)
    offered = Operations().prepare_recovery(vault, direction="restore")
    assert (offered.status, offered.code) == (
        "cleanup",
        "unpublished_collection_prepared",
    )
    assert offered.operation_id == operation_id
    assert offered.unpublished_checkpoint == snapshot.commit
    assert offered.intent_commit is None
    assert Operations().inspect_history(vault).admission.status == "recovery_first"
    assert not (vault / path).exists()
    restored = Operations().execute_recovery(vault, offered)
    assert restored.code == "saved_collection_review_restored", restored
    assert not restored.authored_files_changed
    resumed = Operations().resume_update(vault)
    assert resumed.code == "resumed", resumed
    assert resumed.operation_id == plan.proposal.proposal_id
    assert not (vault / record_path).exists()


def test_saved_unrelated_review_keeps_the_established_source_available():
    vault, source_a = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    authored = b"Existing A.\r\n"
    original = b"Original A.\n"
    (vault / "Opening.md").write_bytes(authored)
    (source_a / "Opening.md").write_bytes(original)
    path_b, record_path, incoming = _incoming_brain()
    record_a = json.loads(incoming[record_path])
    record_a["source_identity"]["source_id"] = "brain-a"
    record_a["source_identity"]["snapshot_digest"] = "original-a"
    record_a["item_targets"][0]["relative_path"] = "Opening.md"
    asset_a = "Assets/shared.bin"
    asset_b = "Imports/Brain B/Assets/shared.bin"
    record_a["asset_targets"] = [{"asset_id": "shared", "relative_path": asset_a}]
    (source_a / "migration-record.json").write_bytes(json.dumps(record_a).encode())
    (vault / "migration-record.json").write_bytes(json.dumps(record_a).encode())
    for directory in (vault, source_a):
        (directory / asset_a).parent.mkdir()
        (directory / asset_a).write_bytes(b"Historical A resource\x00")
    record_b = json.loads(incoming[record_path])
    record_b["asset_targets"] = [{"asset_id": "shared", "relative_path": asset_b}]
    incoming[record_path] = json.dumps(record_b).encode()
    incoming[asset_b] = b"Distinct B resource\xff"
    operations = Operations()
    first = operations.capture_checkpoint(
        vault,
        source_a,
        vault_id="vault",
        import_id="stage-one",
        identity={
            "collection_id": "brain-a",
            "module_id": "thebrain-brz",
            "module_version": "9",
            "profile_id": "fixture",
            "profile_version": "1",
            "output_format": 9,
            "settings_digest": hashlib.sha256(b"{}").hexdigest(),
        },
        admission=operations.inspect_history(vault).admission,
    )
    assert first.status == "captured", first.code
    source_b = source_a.parent / "brain-b"
    for path, raw in incoming.items():
        (source_b / path).parent.mkdir(parents=True, exist_ok=True)
        (source_b / path).write_bytes(raw)
    offered = operations.prepare_collection_import(
        vault, source_b, record_path=record_path
    )
    assert offered.ready, offered
    saved = operations.save_update(offered.preparation.model_dump())
    assert saved.code == "saved", saved
    reopened = operations.read_checkpoint(vault)
    assert reopened.status == "valid"
    assert reopened.review.saved.plan.proposal.proposal_id == offered.operation_id
    assert reopened.manifest.source == ()
    assert reopened.locator.association == first.locator.association
    assert (
        operations.inspect_history(vault).admission.preflight
        == saved.preparation.review.preflight
    )
    source = operations.read_checkpoint_payload(
        vault,
        locator=reopened.locator,
        collection=("thebrain-brz", "brain-a"),
        requests=(CheckpointPayloadRequest(path="Opening.md", limit=64),),
        byte_limit=64,
    )
    assert source.status == "available", source.code
    assert source.chunks[0].data == original
    absent = operations.read_checkpoint_payload(
        vault,
        locator=reopened.locator,
        collection=("thebrain-brz", "brain-b"),
        requests=(CheckpointPayloadRequest(path="Opening.md", limit=64),),
        byte_limit=64,
    )
    assert absent.code == "collection_not_active", absent
    with operations.inspect_update_inputs(vault) as observed:
        (owner,) = observed.read_attachment_ownership(
            locator=reopened.locator, paths=(asset_a,)
        )
    assert owner.checkpoint_commit == first.commit
    assert owner.identity.collection_id == "brain-a"
    assert owner.source_path == asset_a
    resumed = Operations().resume_update(vault)
    assert resumed.code == "resumed", resumed
    assert resumed.operation_id == offered.operation_id
    assert (vault / "Opening.md").read_bytes() == authored
    assert not (vault / record_path).exists()
    discarded = operations.discard_saved_review(
        vault, expected_commit=reopened.locator.commit
    )
    assert discarded.code == "saved_review_discarded", discarded

    source_a_next = source_a.parent / "brain-a-next"
    source_a_next.mkdir()
    record_a["source_identity"]["snapshot_digest"] = "next-a"
    (source_a_next / "migration-record.json").write_text(
        json.dumps(record_a), encoding="utf-8"
    )
    (source_a_next / "Opening.md").write_bytes(b"Next A.\n")
    (source_a_next / asset_a).parent.mkdir()
    (source_a_next / asset_a).write_bytes(b"Historical A resource\x00")
    next_a = operations.prepare_collection_update(
        vault, source_a_next, record_path="migration-record.json"
    )
    assert next_a.preparation is not None, next_a
    refreshed = operations.refresh_update(next_a.preparation)
    assert refreshed.preparation is not None, refreshed.code
    note = next(
        subject
        for subject in refreshed.preparation.review.facts.subjects
        if subject.item_id == "opening"
    )
    assert note.baseline.content.data == original
    assert note.current.content.data == authored
    assert operations.save_update(next_a.preparation).code == "saved"
    assert not (vault / path_b).exists()
