"""Qualified document reversal composes with independently retained note versions."""

import pytest

from brz2obsidian.application.review_choices import (
    requirement_digest,
    review_plan_choice_action,
)
from brz2obsidian.application.update_lifecycle import text_choice_action
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


def operation_document_facts(*, changed="none"):
    """Outer facts bind the exact identityless document and operation preimage."""
    current_home = HOME_LATER
    if changed == "heading":
        current_home = current_home.replace(b"## Shared", b"## Changed")
    elif changed == "block":
        current_home = current_home.replace(b"^kept", b"^changed")
    manual_before = MANUAL_BEFORE
    if changed == "resource":
        manual_before += b"[[Assets/data.bin|Resource]]\n"
    manual_produced = manual_before.replace(b"|Home]]", b"|Recorded home]]")
    facts = request(original=HOME_APPLIED, current=current_home, incoming=HOME_OLD)
    home = target_for_links("review:opening-entry", "Notes/Opening.md").model_copy(
        update={
            "identity": facts.identity_inventory[0].identity,
            "target": facts.subjects[0].source_target,
        }
    )
    manual = target_for_links("file:Manual.md", "Manual.md")
    observed = CurrentContent(
        existence="present",
        path="Manual.md",
        content=ExactContent(data=manual_produced),
    )
    # This Core input declares verified outer history authority, as the existing
    # reversal-output fixtures do. No retained fixture or plan is loaded.
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
                produced=ExactContent(data=manual_produced),
                current=observed,
                target_existence="present",
                target=ExactContent(data=manual_before),
            ),
        ),
    )
    subject = ReconciliationSubject(
        item_id="file:Manual.md",
        facet="content",
        path="Manual.md",
        baseline=ContentVersion(
            status="unknown", content=None, unavailable_digest=None
        ),
        current=observed,
        incoming=ExactContent(data=manual_before),
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
    extra = None
    extra_content = None
    if changed == "resource":
        extra = target_for_links(
            "resource:retained", "Assets/data.bin", kind="resource"
        )
        extra_content = ExactContent(data=b"\x00current resource")
    elif changed == "ambiguous":
        extra = target_for_links(
            "file:Other.md", "Other.md", aliases=("Other.md", "Notes/Opening.md")
        )
        extra_content = ExactContent(data=b"An independent authored note.\n")
    entries = (entry,)
    if extra is not None:
        entries += (
            IdentityInventoryItem(
                entry_id="observed:extra",
                facet=None,
                identity_state="missing",
                identity=None,
                raw_identity=None,
                title="Other authored target",
                current=CurrentContent(
                    existence="present",
                    path=extra.canonical_path,
                    content=extra_content,
                ),
                target=extra.target,
            ),
        )
    contexts = {}
    for stage, home_bytes, manual_bytes in (
        ("current", current_home, manual_produced),
        ("incoming", HOME_OLD, manual_before),
    ):
        targets = (home, manual)
        content = (ExactContent(data=home_bytes), ExactContent(data=manual_bytes))
        if extra is not None and (stage == "current" or changed == "resource"):
            targets += (extra,)
            content += (
                ExactContent(data=b"\x00old resource")
                if stage == "incoming" and changed == "resource"
                else extra_content,
            )
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
            if target.kind != "resource"
        )
        assert all(d.status == "supported" for d in documents)
        contexts[stage + "_targets"] = targets
        contexts[stage + "_target_facts"] = states
        contexts[stage + "_documents"] = documents
    return facts.model_copy(
        update={
            "subjects": facts.subjects + (subject,),
            "identity_inventory": facts.identity_inventory + entries,
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


@pytest.mark.parametrize("changed", ["heading", "block", "ambiguous", "resource"])
def test_operation_document_reverse_still_blocks_changed_reference_semantics(changed):
    facts = operation_document_facts(changed=changed)
    plan = prepare_review(facts, preflight=preflight())
    plan = choose(plan, "Notes/Opening.md", "current")
    assert not plan.blockers
    plan = choose(plan, "Manual.md", "reverse")
    assert not plan.requirements
    assert "selected_link_context_conflict" in plan.blockers
    assert not plan.ready
    selected = select_review_effects(plan)
    assert selected.status == "refused"
    assert selected.files == () and selected.remove_paths == ()
