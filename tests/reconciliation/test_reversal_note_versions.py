"""Qualified document reversal composes with independently retained note versions."""

from brz2obsidian.contracts import (
    ContentVersion,
    CurrentContent,
    ExactContent,
    IdentityInventoryItem,
    LinkContext,
    OperationReversalOutput,
    OperationReversalTarget,
    ReconciliationSubject,
)
from brz2obsidian.application.review_choices import (
    requirement_digest,
    review_plan_choice_action,
)
from brz2obsidian.application.update_lifecycle import text_choice_action
from brz2obsidian.core import (
    inspect_review_choices,
    prepare_review,
    resolve_review,
    select_review_effects,
)
from brz2obsidian.obsidian import interpret_link_target, interpret_links
from tests.reconciliation.test_attachments import target_for_links
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import preflight

HOME_OLD = b"# Home\n\n## Shared\nA paragraph ^kept\n"
HOME_APPLIED = HOME_OLD + b"Generated note prose.\n"
HOME_LATER = HOME_APPLIED + b"Independent later writing.\n"
MANUAL_BEFORE = (
    b"[[Notes/Opening.md|Home]]\n"
    b"[[Notes/Opening.md#Shared|Heading]]\n"
    b"[[Notes/Opening.md#^kept|Block]]\n"
    b"[Relative](Notes/Opening.md)\n"
)
MANUAL_PRODUCED = MANUAL_BEFORE.replace(b"|Home]]", b"|Recorded home]]")


def operation_document_facts():
    """Public outer-fact contract: exact preimage/current/owned row, no imported Manual."""
    facts = request(
        original=HOME_APPLIED, current=HOME_LATER, incoming=HOME_OLD
    )
    home = target_for_links("review:opening-entry", "Notes/Opening.md").model_copy(
        update={
            "identity": facts.identity_inventory[0].identity,
            "target": facts.subjects[0].source_target,
        }
    )
    manual = target_for_links("file:Manual.md", "Manual.md")
    observed = CurrentContent(
        existence="present", path="Manual.md", content=ExactContent(data=MANUAL_PRODUCED)
    )
    #This Core input declares previously verified outer history authority, just as
    #the existing reversal-output fixtures do. No retained fixture/plan is loaded.
    proof = OperationReversalTarget(
        schema_id="brz2obsidian.operation-reversal-target",
        schema_version=1,
        operation_id="operation:reference-edit",
        operation_kind="apply",
        direction="restore",
        operation_generation=3,
        history_fingerprint="validated:reference-edit/prepared",
        origin_change_id="origin:dependent-document",
        origin_decision_id="origin:selected-reference-edit",
        owned_targets=(manual,),
        outputs=(
            OperationReversalOutput(
                path="Manual.md",
                target_id="file:Manual.md",
                produced_existence="present",
                produced=ExactContent(data=MANUAL_PRODUCED),
                current=observed,
                target_existence="present",
                target=ExactContent(data=MANUAL_BEFORE),
            ),
        ),
    )
    subject = ReconciliationSubject(
        item_id="file:Manual.md",
        facet="content",
        path="Manual.md",
        baseline=ContentVersion(status="unknown", content=None, unavailable_digest=None),
        current=observed,
        incoming=ExactContent(data=MANUAL_BEFORE),
        interpretation="supported",
        title="Manual",
        source_target=manual.target,
        output_role="note",
        structure=None,
        attachment=None,
        operation_reversal=proof,
    )
    entry = IdentityInventoryItem(
        entry_id="observed:manual",
        facet="content",
        identity_state="missing",
        identity=None,
        raw_identity=None,
        title="Manual",
        current=observed,
        target=manual.target,
    )
    targets = (home, manual)
    contexts = {}
    for stage, home_bytes, manual_bytes in (
        ("current", HOME_LATER, MANUAL_PRODUCED),
        ("incoming", HOME_OLD, MANUAL_BEFORE),
    ):
        content = (ExactContent(data=home_bytes), ExactContent(data=manual_bytes))
        states = tuple(
            interpret_link_target(
                raw,
                target_id=target.target_id,
                existence="present",
                memberships=(),
                source_path=target.canonical_path,
            )
            for target, raw in zip(targets, content, strict=True)
        )
        documents = tuple(
            interpret_links(
                raw,
                document_id=target.target_id,
                source_path=target.canonical_path,
                path_mode="vault",
                targets=targets,
                target_facts=states,
                inventory="complete",
            )
            for target, raw in zip(targets, content, strict=True)
        )
        assert all(d.status == "supported" for d in documents)
        contexts[stage + "_targets"] = targets
        contexts[stage + "_target_facts"] = states
        contexts[stage + "_documents"] = documents
    return facts.model_copy(
        update={
            "subjects": facts.subjects + (subject,),
            "identity_inventory": facts.identity_inventory + (entry,),
            "link_context": LinkContext(
                schema_id="brz2obsidian.link-context",
                schema_version=1,
                inventory="complete",
                **contexts,
            ),
        }
    )


def choose(plan, path, choice):
    changes = {c.change_id: c for c in plan.proposal.changes}
    offered = [
        r
        for r in inspect_review_choices(plan)
        if changes[r.change_id].path == path and choice in r.enabled_choices
    ]
    assert len(offered) == 1
    action = review_plan_choice_action(
        plan,
        requirement_id=offered[0].requirement_id,
        choice=choice,
        assumptions_digest=requirement_digest(offered[0]),
    )
    transition = resolve_review(plan, text_choice_action(plan, action))
    assert transition.status == "accepted", transition.code
    return transition.plan


def test_operation_document_reverse_keeps_later_referenced_note():
    facts = operation_document_facts()
    manual = facts.subjects[1]
    assert manual.baseline.status == "unknown"
    assert facts.identity_inventory[1].identity is None
    plan = prepare_review(facts, preflight=preflight())
    plan = choose(plan, "Notes/Opening.md", "current")
    assert not plan.blockers
    plan = choose(plan, "Manual.md", "reverse")
    assert not plan.requirements
    assert plan.ready, plan.blockers
    selected = select_review_effects(plan)
    assert selected.status == "selected"
    assert {row.path: row.content.data for row in selected.files} == {
        "Notes/Opening.md": HOME_LATER,
        "Manual.md": MANUAL_BEFORE,
    }
    assert selected.remove_paths == ()
