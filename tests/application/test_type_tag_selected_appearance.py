"""Public choices requalify the actual selected appearance file versions."""

import json

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_choices import (
    attachment_reference_page,
    requirement_digest,
)
from brz2obsidian.core import inspect_review_choices, select_review_effects
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_resolution import action
from tests.reconciliation.test_type_tag_dependencies import (
    BLUE,
    conflicted_graph,
    facts_for,
)


def incoming_image_choice(
    *, qualified=True, output_format=8, explicit_owner=False, recorded_roles=False
):
    baseline, incoming, current = conflicted_graph()
    for payload in (baseline, incoming, current):
        record = json.loads(payload["migration-record.json"])
        record["schema_version"] = output_format
        payload["migration-record.json"] = json.dumps(record).encode()
        if qualified:
            payload["Categories/A.md"] = payload["Categories/A.md"].replace(
                b"[[A.svg]]", b"[[Attachments/A.svg]]"
            )
    incoming["Attachments/A.svg"] = BLUE
    facts = facts_for(baseline, incoming, current)
    if recorded_roles:
        facts = facts.model_copy(
            update={
                "link_context": facts.link_context.model_copy(
                    update={
                        stage + "_target_facts": tuple(
                            state.model_copy(update={"file_roles": None})
                            for state in getattr(
                                facts.link_context, stage + "_target_facts"
                            )
                        )
                        for stage in ("current", "incoming")
                    }
                )
            }
        )
    prepared = preparation(facts)
    operations = Operations()
    for item in ("support:migration-record.json", "category:C", "entry:I") + (
        ("category:A",) if explicit_owner else ()
    ):
        plan = prepared.review
        change = next(row for row in plan.proposal.changes if row.item_id == item)
        chosen = operations.resolve_update(
            prepared, action(plan, change, choice="current", decision_id="keep:" + item)
        )
        assert chosen.code == "accepted", chosen.code
        prepared = chosen.preparation
    offered = next(
        row
        for row in inspect_review_choices(prepared.review)
        if row.domain == "attachment"
    )
    references, total, following = attachment_reference_page(
        prepared, offered.requirement_id
    )
    assert total == 1 and following is None
    result = operations.resolve_update_choice(
        prepared,
        requirement_id=offered.requirement_id,
        choice="incoming",
        assumptions_digest=requirement_digest(offered),
        references=tuple(
            {"reference_id": row.reference_id, "choice": "use_incoming"}
            for row in references
        ),
    )
    assert result.code == "accepted", result.code
    return result, current


@pytest.mark.parametrize("qualified", (False, True), ids=("short", "qualified"))
@pytest.mark.parametrize("output_format", (7, 8), ids=("format7", "format8"))
def test_selected_incoming_owned_image_requalifies_exact_path_and_bytes(
    qualified, output_format
):
    result, current = incoming_image_choice(
        qualified=qualified, output_format=output_format
    )
    if output_format == 7:
        assert not result.ready
        assert "selected_link_context_conflict" in result.preparation.review.blockers
        assert select_review_effects(result.preparation.review).status == "refused"
        return
    assert result.ready, result.preparation.review.blockers
    selected = select_review_effects(result.preparation.review)
    assert selected.status == "selected"
    files = {row.path: row.content.data for row in selected.files}
    assert files["Attachments/A.svg"] == BLUE
    assert files["Categories/A.md"] == current["Categories/A.md"]
    assert files["Categories/C.md"] == current["Categories/C.md"]
    assert files["Notes/Independent.md"] == current["Notes/Independent.md"]


def test_explicit_whole_current_owner_keeps_its_reference_authority_guard():
    result, current = incoming_image_choice(explicit_owner=True)
    assert not result.ready
    assert "selected_link_context_conflict" in result.preparation.review.blockers
    owner = next(
        row
        for row in result.preparation.review.approvals
        if row.decision_id == "keep:category:A"
    )
    assert owner.choice == "current" and owner.provenance == "explicit_user"
    assert owner.result.data == current["Categories/A.md"]
    assert select_review_effects(result.preparation.review).status == "refused"


def test_recorded8_facts_without_role_evidence_keep_their_original_reference_refusal():
    result, _ = incoming_image_choice(recorded_roles=True)
    assert not result.ready
    assert "selected_link_context_conflict" in result.preparation.review.blockers
    assert select_review_effects(result.preparation.review).status == "refused"


def test_current_bytes_at_explicit_source_path_requalify_the_selected_file():
    baseline, incoming, current = conflicted_graph()
    authored = current.pop("Notes/Independent.md")
    current["Manual/Independent.md"] = authored
    prepared = preparation(facts_for(baseline, incoming, current))
    operations = Operations()
    for item in ("support:migration-record.json", "category:C"):
        plan = prepared.review
        change = next(row for row in plan.proposal.changes if row.item_id == item)
        result = operations.resolve_update(
            prepared, action(plan, change, choice="current", decision_id="keep:" + item)
        )
        assert result.code == "accepted", result.code
        prepared = result.preparation
    plan = prepared.review
    change = next(row for row in plan.proposal.changes if row.item_id == "entry:I")
    renamed = operations.resolve_update(
        prepared,
        action(
            plan, change, domain="rename", choice="source_path", decision_id="rename:I"
        ),
    )
    assert renamed.code == "accepted", renamed.code
    plan = renamed.preparation.review
    change = next(row for row in plan.proposal.changes if row.item_id == "entry:I")
    kept = operations.resolve_update(
        renamed.preparation,
        action(plan, change, choice="current", decision_id="keep:I"),
    )
    assert kept.code == "accepted", kept.code
    assert kept.ready, kept.preparation.review.blockers
    effects = select_review_effects(kept.preparation.review)
    assert effects.status == "selected"
    assert (
        next(
            row.content.data
            for row in effects.files
            if row.path == "Notes/Independent.md"
        )
        == authored
    )
    assert effects.remove_paths == ("Manual/Independent.md",)
