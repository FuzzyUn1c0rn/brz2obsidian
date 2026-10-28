"""Incoming link facts preserve the complete imported owner of every note."""

import json

import pytest

from brz2obsidian.application.update_facts import assemble_facts
from brz2obsidian.core import reconcile


def owned_note(collection, body):
    return (
        '---\ncategories: []\naliases: []\ntags: []\n'
        f'source_collection_id: "{collection}"\n'
        'source_item_id: "entry:opening"\n---\n' + body
    ).encode()


def owner_facts(role, *, duplicate=False):
    path = "Categories/Own.md" if role == "category" else "Notes/Own.md"
    source = {
        "schema": "brz2obsidian.migration", "schema_version": 7,
        "profile_id": "reviewed-folio", "profile_version": "1",
        "source_identity": {
            "source_id": "collection:A", "module_id": "synthetic-folio",
            "module_version": "1", "format_version": "5",
            "source_sha256": "c" * 64, "snapshot_digest": "d" * 64,
        },
        "item_targets": [{
            "original_identity": "entry:opening", "original_title": "Own",
            "relative_path": path, "created": True,
            "creation_reasons": ["definition" if role == "category" else "content"],
        }],
        "asset_targets": [],
    }
    original = owned_note("collection:A", "ORIGINAL own writing.\n")
    incoming = owned_note("collection:A", f"OURS incoming [[{path}|Own target]].\n")
    foreign = owned_note("collection:A" if duplicate else "collection:B", "FOREIGN retained writing.\r\n")
    baseline = {"migration-record.json": json.dumps(source).encode(), path: original}
    received = baseline | {path: incoming}
    current = baseline | {"Foreign/Retained.md": foreign}
    return assemble_facts(baseline, received, current, proposal_id="review:owners", generation=1), path, original, incoming, foreign


@pytest.mark.parametrize("role", ("note", "category"))
def test_foreign_same_item_keeps_its_path_bytes_and_role_in_incoming_context(role):
    facts, path, original, incoming, foreign = owner_facts(role)
    context = facts.link_context
    outsider = next(t for t in context.current_targets if t.canonical_path == "Foreign/Retained.md")
    future = next(t for t in context.incoming_targets if t.identity and t.identity.collection_id == "collection:B")
    assert outsider.identity.item_id == future.identity.item_id == "entry:opening"
    assert outsider.identity.module_id == future.identity.module_id == "synthetic-folio"
    assert future.target_id == outsider.target_id == "file:Foreign/Retained.md"
    assert future.canonical_path == "Foreign/Retained.md" and future.kind == "note"
    foreign_documents = [d for d in context.incoming_documents if d.document_id == future.target_id]
    assert [(d.source_path, d.content.data) for d in foreign_documents] == [("Foreign/Retained.md", foreign)]
    assert next(d for d in context.current_documents if d.document_id == outsider.target_id).content.data == foreign
    own = next(t for t in context.incoming_targets if t.identity and t.identity.collection_id == "collection:A" and t.identity.item_id == "entry:opening")
    assert own.canonical_path == path and own.kind == ("category" if role == "category" else "note")
    document = next(d for d in context.incoming_documents if d.document_id == own.target_id and d.source_path == path)
    assert document.content.data == incoming
    occurrence, = document.occurrences
    assert occurrence.meaning.status == "resolved" and occurrence.meaning.target_id == own.target_id
    change = next(c for c in reconcile(facts).changes if c.item_id == "entry:opening")
    assert change.identity_review.status == "matched"
    assert change.current.data == original


def test_genuine_same_owner_duplicate_remains_ambiguous():
    facts, _, _, _, foreign = owner_facts("note", duplicate=True)
    change = next(c for c in reconcile(facts).changes if c.item_id == "entry:opening")
    assert change.disposition == "identity_resolution"
    assert change.identity_review.reason == "duplicate_identity"
    assert change.identity_review.selected_entry_id is None
    assert foreign in {row.current.content.data for row in change.identity_review.candidates}
    assert not reconcile(facts).ready
