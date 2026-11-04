"""Current reobservation scopes onboarding decisions to their real dependencies."""

import json

from tests.application.test_onboarding import legacy_inputs
from tests.reconciliation.test_resolution import action


def two_note_legacy_inputs(tmp_path, monkeypatch):
    operations, vault, source, authored = legacy_inputs(tmp_path, monkeypatch)
    data = json.loads(source.read_text())
    data["entries"].append(
        {
            "key": "entry:second",
            "seed": "00000002000040008000000000000000",
            "title": "Second",
        }
    )
    (tmp_path / "second-source.md").write_bytes(b"Independent source.\n")
    data["assets"].append(
        {
            "key": "asset:second-original",
            "owner": "entry:second",
            "seed": "00000003000040008000000000000000",
            "name": "Notes.md",
            "role": "note_original",
            "file": "second-source.md",
        }
    )
    data["documents"].append(
        {
            "key": "document:second",
            "owner": "entry:second",
            "original": "asset:second-original",
            "text": "Independent source.\n",
        }
    )
    source.write_text(json.dumps(data))
    second = b'---\nsource_collection_id: legacy-collection\nsource_item_id: "entry:second"\n---\nIndependent writing.\n'
    (vault / "Second.md").write_bytes(second)
    return operations, vault, source, authored, second


def test_changed_current_note_keeps_the_independent_onboarding_choice(
    tmp_path, monkeypatch
):
    operations, vault, source, authored, second = two_note_legacy_inputs(
        tmp_path, monkeypatch
    )
    result = operations.prepare_onboarding(vault, source)
    assert result.preparation is not None, result
    for item_id, decision_id in (
        ("entry:opening", "keep-first"),
        ("entry:second", "keep-independent"),
    ):
        prepared = result.preparation
        change = next(
            c for c in prepared.review.proposal.changes if c.item_id == item_id
        )
        result = operations.resolve_update(
            prepared,
            action(
                prepared.review,
                change,
                domain="format",
                choice="current",
                decision_id=decision_id,
            ),
        )
        assert result.code == "accepted", result
    (vault / "Home \u2014 Opening.md").write_bytes(authored + b"Later writing.\r\n")
    refreshed = operations.refresh_update(result.preparation)
    assert refreshed.kind == "onboarding" and refreshed.status == "stale_review", (
        refreshed
    )
    assert refreshed.generation == 2
    assert [a.decision_id for a in refreshed.preparation.review.approvals] == [
        "keep-independent"
    ]
    first = next(
        c
        for c in refreshed.preparation.review.proposal.changes
        if c.item_id == "entry:opening"
    )
    assert any(
        r.change_id == first.change_id
        for r in refreshed.preparation.review.requirements
    )
    assert first.current.data == authored + b"Later writing.\r\n"
    assert (vault / "Second.md").read_bytes() == second
