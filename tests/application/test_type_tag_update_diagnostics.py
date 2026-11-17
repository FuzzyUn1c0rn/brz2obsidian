"""Safe public explanations for combined selected provider graphs."""

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context import UpdateContext
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_resolution import action
from tests.reconciliation.test_type_tag_dependencies import (
    facts_for,
    invalid_provider_graph,
    note,
    provider_cycle_graph,
    selected_candidate,
)


def test_selected_provider_cycle_explains_the_chain_without_copying_authored_text():
    baseline, incoming, current = provider_cycle_graph(own_icon=True)
    secret = b"Bearer private-cycle-fixture"
    current["Categories/B.md"] = current["Categories/B.md"].replace(b"Local B.", secret)
    facts = facts_for(baseline, incoming, current)
    selected = current | {"Categories/E.md": incoming["Categories/E.md"]}
    selected_facts = facts_for(baseline, selected, current)
    prepared = preparation(facts)
    operations = Operations()
    for item, choice in (
        ("support:migration-record.json", "current"),
        ("category:B", "current"),
        ("category:E", "incoming"),
    ):
        plan = prepared.review
        change = next(c for c in plan.proposal.changes if c.item_id == item)
        candidate = (
            None
            if item.startswith("support:")
            else selected_candidate(facts, selected_facts, item)
        )
        result = operations.resolve_update(
            prepared,
            action(plan, change, choice=choice, candidate=candidate, decision_id=item),
        )
        assert result.code == "accepted", result.code
        prepared = result.preparation
    assert not result.ready and result.status == "unresolved"
    assert result.summary == "The selected appearance-category chains contain a cycle."
    assert result.findings == ("selected_provider_cycle",)
    assert "remove the repeated provider" in result.guidance
    assert "owned icon" in result.guidance
    assert "this note" not in result.guidance.lower()
    assert secret.decode() not in result.summary + result.guidance

    # Only native I/O preparation is supplied here; actual public Operations
    # resolution above produced the blocked plan and the safe diagnostic.
    class ObservedPreparation(Operations):
        def prepare_update(self, vault, source):
            return result

    context = UpdateContext(operations=ObservedPreparation())
    opened = context.prepare(
        "unused",
        source="unused.brz",
        selection_id="11111111-1111-4111-8111-111111111111",
    )
    assert not opened.ready and opened.summary == result.summary
    assert opened.findings == result.findings and opened.guidance == result.guidance
    assert secret.decode() not in opened.model_dump_json()


def test_selected_invalid_upstream_provider_guides_repair_to_the_chain():
    baseline, incoming, current = invalid_provider_graph()
    facts = facts_for(baseline, incoming, current)
    selected = current | {"Categories/C.md": incoming["Categories/C.md"]}
    prospective = facts_for(baseline, selected, current)
    prepared = preparation(facts)
    plan = prepared.review
    change = next(c for c in plan.proposal.changes if c.item_id == "category:C")
    operations = Operations()
    kept = operations.resolve_update(prepared, action(plan, change, choice="current"))
    assert kept.ready and not kept.findings
    blocked = operations.resolve_update(
        prepared,
        action(
            plan,
            change,
            choice="incoming",
            candidate=selected_candidate(facts, prospective, "category:C"),
        ),
    )
    assert not blocked.ready and blocked.status == "unresolved"
    assert blocked.findings == ("selected_provider_invalid",)
    assert (
        blocked.summary
        == "A selected appearance-category chain reaches an invalid declaration."
    )
    assert "note with the invalid declaration" in blocked.guidance
    assert "this note" not in blocked.guidance.lower()
    assert "[[Missing]]" not in blocked.summary + blocked.guidance


def test_invalid_upstream_icon_guidance_covers_the_actual_declaration_and_repair():
    secret = "Bearer private-icon-fixture"
    for repaired in (False, True):
        baseline, incoming, current = invalid_provider_graph()
        current["Categories/A.md"] = note(
            "category:A", icon=None if repaired else secret
        )
        # Provider and memberships are already valid and blank. The independent
        # invalid icon remains visible beyond B's nearer valid owned icon.
        assert (
            b"categories: []\nappearance_category: null" in current["Categories/A.md"]
        )
        facts = facts_for(baseline, incoming, current)
        prospective = facts_for(
            baseline,
            current | {"Categories/C.md": incoming["Categories/C.md"]},
            current,
        )
        prepared = preparation(facts)
        change = next(
            c for c in prepared.review.proposal.changes if c.item_id == "category:C"
        )
        result = Operations().resolve_update(
            prepared,
            action(
                prepared.review,
                change,
                choice="incoming",
                candidate=selected_candidate(facts, prospective, "category:C"),
            ),
        )
        assert result.code == "accepted" and result.ready is repaired
        if repaired:
            assert not result.findings
        else:
            assert result.findings == ("selected_provider_invalid",)
            assert "invalid icon declaration" in result.guidance
            assert "image target" in result.guidance
            assert "note with the invalid declaration" in result.guidance
            assert "category membership" in result.guidance
        assert secret not in result.summary + result.guidance
