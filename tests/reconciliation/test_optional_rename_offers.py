"""Optional source paths accompany the primary canonical review decisions."""

import pytest

from brz2obsidian.core import (
    inspect_review_choices,
    prepare_review,
    resolve_review,
    select_review_effects,
)
from tests.reconciliation.test_identity import inventory_item
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links

CURRENT_PATH = "Authored/Opening.md"
SOURCE_PATH = "Notes/Opening.md"
ORIGINAL = b"Original source writing.\r\n"
INCOMING = b"Incoming source writing.\n"
AUTHORED = b"Independent authored writing.\r\n"


def moved_facts(*, conflict=True):
    current = AUTHORED if conflict else ORIGINAL
    facts = request(original=ORIGINAL, current=current, incoming=INCOMING)
    moved = inventory_item("moved", "entry:opening", CURRENT_PATH, current)
    return with_review_links(facts.model_copy(update={"identity_inventory": (moved,)}))


@pytest.mark.parametrize("conflict", (True, False), ids=("conflict", "compatible"))
def test_canonical_optional_rename_accompanies_primary_without_becoming_required(
    conflict,
):
    plan = prepare_review(moved_facts(conflict=conflict), preflight=preflight())
    (change,) = plan.proposal.changes
    assert change.path == change.target_path == "Authored/Opening.md"
    assert change.rename_review.current_path == "Authored/Opening.md"
    assert change.rename_review.source_path == "Notes/Opening.md"
    assert change.rename_review.status == "offered"
    assert not change.rename_review.requires_decision
    before = plan.model_dump_json()
    offers = inspect_review_choices(plan)
    assert plan.model_dump_json() == before
    assert plan.proposal.generation == 1 and not plan.ready
    assert len(plan.requirements) == 1
    assert all(row.domain != "rename" for row in plan.requirements)
    rename = [row for row in offers if row.domain == "rename"]
    assert len(rename) == 1, [(row.domain, row.change_id) for row in offers]
    assert rename[0].change_id == change.change_id
    assert rename[0].enabled_choices == ("keep_path", "source_path")
    assert len({row.requirement_id for row in offers}) == len(offers)
    primary = next(row for row in offers if row.domain == "text")
    assert primary.change_id == change.change_id
    assert primary.requirement_id != rename[0].requirement_id
    if conflict:
        assert plan.groups == ()
        accepted = resolve_review(plan, action(plan, choice="current"))
        expected = AUTHORED
    else:
        (group,) = plan.groups
        assert any(row.domain == "compatible_group" for row in offers)
        accepted = resolve_review(
            plan,
            action(
                plan,
                change_id=group.group_id,
                domain="compatible_group",
                choice="approve",
                reviewed_assumptions=group.assumptions,
            ),
        )
        expected = INCOMING
    assert accepted.status == "accepted" and accepted.plan.ready, accepted.code
    assert accepted.plan.requirements == ()
    assert accepted.plan.proposal.changes[0].target_path == "Authored/Opening.md"
    effects = select_review_effects(accepted.plan)
    assert effects.status == "selected", effects.code
    assert [(row.path, row.content.data) for row in effects.files] == [
        ("Authored/Opening.md", expected)
    ]
    assert effects.remove_paths == ()
