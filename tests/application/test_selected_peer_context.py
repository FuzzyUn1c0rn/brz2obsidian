"""Explicit text choices observe canonical automatically preserved peer bytes."""

import json

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_choices import requirement_digest
from brz2obsidian.application.update_facts import assemble_facts
from brz2obsidian.core import inspect_review_choices, select_review_effects
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_resolution import action
from tests.reconciliation.test_type_tag_dependencies import graph_payload, note


@pytest.mark.parametrize(
    ("output_format", "peer_mode"),
    [
        (8, "preserved"),
        (7, "preserved"),
        (8, "unresolved"),
        (8, "explicit"),
        (8, "incoming"),
        (8, "deleted"),
    ],
)
def test_edited_renamed_note_observes_selected_mutual_reference(
    output_format, peer_mode
):
    record = json.loads(graph_payload()["migration-record.json"])
    record["item_targets"] = [
        row
        for row in record["item_targets"]
        if row["original_identity"] in ("category:B", "entry:I")
    ]
    record["asset_targets"] = []
    record["schema_version"] = output_format
    baseline = {
        "migration-record.json": json.dumps(record).encode(),
        "Categories/B.md": note(
            "category:B", body="Kept B prose.\n[[Notes/Independent.md|I]]"
        ),
        "Notes/Independent.md": note(
            "entry:I", category=False, body="[[Categories/B.md|B]]"
        ),
    }
    current, incoming = dict(baseline), dict(baseline)
    current["Categories/B local.md"] = current.pop("Categories/B.md")
    current["Notes/Independent.md"] = current["Notes/Independent.md"].replace(
        b"Categories/B.md", b"Categories/B local.md"
    )
    incoming["Categories/B.md"] = incoming["Categories/B.md"].replace(
        b"Kept B prose.", b"New source B prose."
    )
    if peer_mode in ("unresolved", "explicit", "incoming"):
        incoming["Notes/Independent.md"] += b"New peer source writing.\n"
        if peer_mode == "incoming":
            incoming["Notes/Independent.md"] = note(
                "entry:I", category=False, body="Incoming peer writing."
            )
    elif peer_mode == "deleted":
        del current["Notes/Independent.md"]
    record["source_identity"].update(source_sha256="e" * 64, snapshot_digest="f" * 64)
    incoming["migration-record.json"] = json.dumps(record).encode()
    facts = assemble_facts(
        baseline, incoming, current, proposal_id="mutual-peer", generation=1
    )
    p = preparation(facts)
    operations = Operations()
    rename = next(
        row for row in inspect_review_choices(p.review) if row.domain == "rename"
    )
    kept = operations.resolve_update_choice(
        p,
        requirement_id=rename.requirement_id,
        choice="keep_path",
        assumptions_digest=requirement_digest(rename),
    )
    assert kept.code == "accepted", kept.code
    p = kept.preparation
    peer = next(c for c in p.review.proposal.changes if c.item_id == "entry:I")
    if peer_mode == "preserved":
        assert not peer.requires_decision
        assert peer.result.data == current["Notes/Independent.md"]
        assert peer.disposition == "preserve_vault"
    elif peer_mode == "deleted":
        assert not peer.requires_decision and peer.result is None
        assert peer.disposition == "local_deleted"
    else:
        assert peer.requires_decision and peer.result is None
        if peer_mode in ("explicit", "incoming"):
            peer_bytes = note("entry:I", category=False, body="Explicit peer writing.")
            if peer_mode == "incoming":
                peer_bytes = incoming["Notes/Independent.md"]
            resolved = operations.resolve_update(
                p,
                action(
                    p.review,
                    peer,
                    choice="incoming" if peer_mode == "incoming" else "edited",
                    decision_id="explicit-peer",
                ),
                **({"edited": peer_bytes} if peer_mode == "explicit" else {}),
            )
            assert resolved.code == "accepted", resolved.code
            p = resolved.preparation
    b = next(c for c in p.review.proposal.changes if c.item_id == "category:B")
    chosen = operations.resolve_update(
        p,
        action(p.review, b, choice="edited", decision_id="keep-local-B"),
        edited=current["Categories/B local.md"],
    )
    assert chosen.code == "accepted", chosen.code
    p = chosen.preparation
    metadata = next(
        c
        for c in p.review.proposal.changes
        if c.item_id == "support:migration-record.json"
    )
    chosen = operations.resolve_update(
        p, action(p.review, metadata, choice="incoming", decision_id="record-incoming")
    )
    if peer_mode == "deleted":
        assert chosen.code == "accepted" and not chosen.ready
        assert "selected_link_context_conflict" in chosen.preparation.review.blockers
        return
    if peer_mode == "unresolved":
        assert chosen.code == "accepted" and not chosen.ready
        assert any(
            row.change_id == peer.change_id
            for row in chosen.preparation.review.requirements
        )
        return
    if output_format == 7:
        assert chosen.code == "accepted" and not chosen.ready
        assert "selected_link_context_conflict" in chosen.preparation.review.blockers
        return
    assert chosen.code == "accepted" and chosen.ready, (
        chosen.code,
        chosen.preparation.review.blockers,
    )
    assert any(
        a.change_id == peer.change_id for a in chosen.preparation.review.approvals
    ) == (peer_mode in ("explicit", "incoming"))
    effects = select_review_effects(chosen.preparation.review)
    assert effects.status == "selected"
    files = {row.path: row.content.data for row in effects.files}
    assert files.get("Notes/Independent.md", current["Notes/Independent.md"]) == (
        peer_bytes
        if peer_mode in ("explicit", "incoming")
        else current["Notes/Independent.md"]
    )
    assert files["Categories/B local.md"] == current["Categories/B local.md"]
    assert "Categories/B.md" not in files
