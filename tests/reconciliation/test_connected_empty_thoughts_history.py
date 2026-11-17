"""Cold, format-specific reconciliation controls produced at 1c2c0f00."""

from pathlib import Path

import pytest

from brz2obsidian.contracts import ContentVersion
from brz2obsidian.core import (
    load_review,
    reconcile,
    resume_review,
    select_review_effects,
)
from tests.reconciliation.test_identity import inventory_item, with_subjects
from tests.reconciliation.test_proposals import request

FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "fixtures/saved_reviews/connected-empty-thoughts"
)


@pytest.mark.parametrize(
    ("fixture_name", "kind", "old_format", "old_profile", "source_version", "incoming"),
    (
        (
            "source-update-8.json",
            "source_update",
            8,
            "11",
            "source:b",
            b"# Opening\n\nSource edit.\n",
        ),
        (
            "transition-7-to-8.json",
            "format_transition",
            7,
            "10",
            "source:a",
            b"# Opening\n\nFormat eight.\n",
        ),
    ),
)
def test_cold_review_keeps_recorded_format_roles_and_authored_choice(
    fixture_name, kind, old_format, old_profile, source_version, incoming
):
    result = load_review((FIXTURES / fixture_name).read_bytes())
    assert result.status == "loaded" and not result.ready
    loaded = result.loaded
    historical = loaded.saved.plan
    facts = historical.facts
    assert (
        facts.baseline_identity.profile_version,
        facts.baseline_identity.output_format,
    ) == (old_profile, old_format)
    assert (
        facts.incoming_identity.profile_version,
        facts.incoming_identity.output_format,
    ) == ("11", 8)
    operation = facts.format_operation
    assert (
        operation.kind,
        operation.baseline_source_version,
        operation.target_source_version,
    ) == (kind, "source:a", source_version)
    (change,) = historical.proposal.changes
    assert change.original.data == b"# Opening\r\n\r\nOriginal generated prose.\r\n"
    assert change.current.data == b"# Opening\r\n\r\nLocal prose.\r\n"
    assert change.incoming.data == incoming

    resumed = resume_review(loaded, facts, preflight=historical.preflight)
    assert (resumed.status, resumed.code, resumed.ready) == (
        "resumed",
        "unchanged",
        True,
    )
    assert [approval.decision_id for approval in resumed.plan.approvals] == [
        "keep-authored-opening"
    ]
    effects = select_review_effects(resumed.plan)
    assert effects.status == "selected" and effects.remove_paths == ()
    assert [(row.path, row.content.data) for row in effects.files] == [
        ("Notes/Opening.md", b"# Opening\r\n\r\nLocal prose.\r\n")
    ]


@pytest.mark.parametrize(
    ("occupant_identity", "current", "eligible"),
    (
        (None, b"", True),
        (None, b"# Opening\r\n\r\nLocal prose.\r\n", True),
        ("entry:different", b"# Opening\r\n\r\nDifferent thought.\r\n", False),
    ),
)
def test_occupied_reserved_note_path_does_not_establish_a_generated_original(
    occupant_identity, current, eligible
):
    incoming = b"# Opening\n\n## Parents\n\n- [[Home.md|Home]]\n"
    facts = request(current=current, incoming=incoming)
    subject = facts.subjects[0].model_copy(
        update={
            "baseline": ContentVersion(
                status="unknown", content=None, unavailable_digest=None
            )
        }
    )
    occupant = inventory_item(
        "reserved-path-occupant",
        occupant_identity or subject.item_id,
        "Notes/Opening.md",
        current,
        state="valid" if occupant_identity else "missing",
    )
    result = reconcile(with_subjects(facts, (subject,), (occupant,)))
    (change,) = result.changes
    assert not result.ready
    assert change.original is None and change.result is None
    assert change.incoming.data == incoming
    assert change.identity_review.selected_entry_id is None
    (candidate,) = change.identity_review.candidates
    assert candidate.current.content.data == current
    assert candidate.eligible is eligible
