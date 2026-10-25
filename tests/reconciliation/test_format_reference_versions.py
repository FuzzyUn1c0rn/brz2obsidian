"""A retained format-review reference distinguishes prose from a changed fragment."""

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_contracts import UpdatePreparation
from brz2obsidian.contracts import (
    ContentVersion,
    CurrentContent,
    ExactContent,
    IdentityTargetFacts,
)
from brz2obsidian.core import prepare_review, select_review_effects
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_identity import inventory_item, with_subjects
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, with_review_links


@pytest.mark.parametrize("changed_fragment", (False, True))
def test_format_current_reference_allows_only_a_prose_version_change(changed_fragment):
    report = (
        b"Keep [[Second#Section]].\r\n" if changed_fragment else b"Keep [[Second]].\r\n"
    ) + b"Existing [[Untouched#Missing]] warning.\r\n"
    facts = request(original=report, current=report, incoming=report)
    old = b"# Section\nOld guide prose.\r\n"
    incoming = (
        b"# Renamed\nNew guide prose.\r\n"
        if changed_fragment
        else b"# Section\nNew guide prose.\r\n"
    )
    guide = facts.subjects[0].model_copy(
        update={
            "item_id": "item:second",
            "title": "Second",
            "path": "Second.md",
            "output_role": "guide",
            "baseline": ContentVersion(
                status="known", content=ExactContent(data=old), unavailable_digest=None
            ),
            "current": CurrentContent(
                existence="present", path="Second.md", content=ExactContent(data=old)
            ),
            "incoming": ExactContent(data=incoming),
            "source_target": IdentityTargetFacts(
                normalized_path="second.md", containment="contained", status="safe"
            ),
        }
    )
    untouched = guide.model_copy(
        update={
            "item_id": "item:untouched",
            "title": "Untouched",
            "path": "Untouched.md",
            "current": guide.current.model_copy(update={"path": "Untouched.md"}),
            "incoming": ExactContent(data=old),
            "source_target": IdentityTargetFacts(
                normalized_path="untouched.md", containment="contained", status="safe"
            ),
        }
    )
    facts = with_subjects(
        facts,
        (facts.subjects[0], guide, untouched),
        facts.identity_inventory
        + (
            inventory_item("second", "item:second", "Second.md", old, title="Second"),
            inventory_item(
                "untouched", "item:untouched", "Untouched.md", old, title="Untouched"
            ),
        ),
    )
    operation = facts.format_operation
    facts = with_review_links(
        facts.model_copy(
            update={
                "format_operation": operation.model_copy(
                    update={
                        "kind": "format_transition",
                        "baseline_source_version": operation.target_source_version,
                        "established_baseline": operation.established_baseline.model_copy(
                            update={"source_version": operation.target_source_version}
                        ),
                    }
                )
            }
        )
    )
    original = preparation()
    prepared = UpdatePreparation.model_validate(
        original.model_dump()
        | {
            "kind": "format_transition",
            "review": prepare_review(facts, preflight=original.review.preflight),
        }
    )
    operations = Operations()
    kept = operations.resolve_update(
        prepared,
        action(
            prepared.review,
            domain="format",
            choice="current",
            decision_id="keep-report",
        ),
    )
    assert kept.code == "accepted", kept
    second = next(
        c
        for c in kept.preparation.review.proposal.changes
        if c.item_id == "item:second"
    )
    assert second.format_review.target_eligible
    changed = operations.resolve_update(
        kept.preparation,
        action(
            kept.preparation.review,
            second,
            domain="format",
            choice="incoming",
            decision_id="new-guide",
        ),
    )
    assert changed.code == "accepted", changed
    third = next(
        c
        for c in changed.preparation.review.proposal.changes
        if c.item_id == "item:untouched"
    )
    changed = operations.resolve_update(
        changed.preparation,
        action(
            changed.preparation.review,
            third,
            domain="format",
            choice="current",
            decision_id="untouched-reference-target",
        ),
    )
    assert changed.code == "accepted", changed
    selected = select_review_effects(changed.preparation.review)
    if changed_fragment:
        assert not changed.ready and selected.status == "refused"
    else:
        assert changed.ready and selected.status == "selected", (
            changed.preparation.review.blockers
        )
        assert [(row.path, row.content.data) for row in selected.files] == [
            ("Notes/Opening.md", report),
            ("Second.md", incoming),
            ("Untouched.md", old),
        ]
