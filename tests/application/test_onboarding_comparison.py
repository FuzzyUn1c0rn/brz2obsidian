"""Bounded first-review comparisons precede any history adoption."""

from types import SimpleNamespace

import pytest

from tests.application.test_onboarding import legacy_inputs


@pytest.mark.parametrize("generation", (1, 2))
def test_first_onboarding_comparison_is_bounded_before_a_checkpoint(
    tmp_path, monkeypatch, generation
):
    operations, vault, source, authored = legacy_inputs(tmp_path, monkeypatch)
    offered = operations.prepare_onboarding(vault, source)
    prepared = offered.preparation
    assert prepared is not None, offered
    monkeypatch.setattr(
        operations,
        "read_checkpoint",
        lambda *args, **kwargs: SimpleNamespace(status="absent", locator=None),
    )
    page = operations.inspect_update_review(
        prepared,
        proposal_id=prepared.review.proposal.proposal_id,
        generation=generation,
        offset=0,
        limit=1,
        byte_limit=32,
    )
    if generation != prepared.review.proposal.generation:
        assert page.status == "refused" and page.items == ()
        return
    assert page.status == "available", page
    assert len(page.items) == 1 and page.omitted
    row = page.items[0]
    assert (
        row.item_id == "entry:opening" and row.current_path == "Home \u2014 Opening.md"
    )
    assert row.original is None and row.current and authored.startswith(row.current)
    assert (
        sum(
            len(raw)
            for raw in (row.original, row.current, row.incoming, row.result)
            if raw is not None
        )
        <= 32
    )
    assert not (vault / ".brz2obsidian").exists()
