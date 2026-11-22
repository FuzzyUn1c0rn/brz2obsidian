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
    assert planned.ready

    retained = note.replace(b"New B text.", b"Later authored text.")
    with pytest.raises(ValueError, match="^retained_source_identity_conflict$"):
        first_import({"Moved/Opening.md": retained})


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
    (source_a / "migration-record.json").write_text(
        json.dumps(record_a), encoding="utf-8"
    )
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
    saved = operations.save_update(offered.preparation)
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
    next_a = operations.prepare_collection_update(
        vault, source_a_next, record_path="migration-record.json"
    )
    assert next_a.preparation is not None, next_a
    note = next(
        subject
        for subject in next_a.preparation.review.facts.subjects
        if subject.item_id == "opening"
    )
    assert note.baseline.content.data == original
    assert note.current.content.data == authored
    assert operations.save_update(next_a.preparation).code == "saved"
    assert not (vault / path_b).exists()
