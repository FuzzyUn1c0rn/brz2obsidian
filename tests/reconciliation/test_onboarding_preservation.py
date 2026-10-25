"""Unknown links permit exact preservation, never other selected changes."""

from brz2obsidian.contracts import (
    ContentVersion,
    CurrentContent,
    ExactContent,
    IdentityInventoryItem,
    IdentityTargetFacts,
    ReferenceTarget,
)
from brz2obsidian.core import (
    prepare_review,
    resolve_review,
    select_review_effects,
    validate_attachment_candidate,
)
from brz2obsidian.obsidian import interpret_link_target, interpret_links
from tests.reconciliation.test_attachments import (
    attachment_candidate,
    attachment_request,
)
from tests.reconciliation.test_resolution import action, preflight


def test_binary_current_keeps_the_complete_opaque_manual_context():
    facts = attachment_request()
    current = ExactContent(data=b"\xffUninterpreted [[Assets/data.bin]]\r\n")
    target = ReferenceTarget(
        schema_id="brz2obsidian.reference-target",
        schema_version=1,
        target_id="manual-note",
        kind="note",
        canonical_path="Manual.md",
        identity=None,
        target=IdentityTargetFacts(
            normalized_path="manual.md", containment="contained", status="safe"
        ),
        representations=("Manual.md",),
        validation_fingerprint="actual-current-context",
        status="safe",
    )
    entry = IdentityInventoryItem(
        entry_id="manual-note",
        facet="content",
        identity_state="missing",
        identity=None,
        raw_identity=None,
        title="Manual",
        current=CurrentContent(existence="present", path="Manual.md", content=current),
        target=target.target,
    )
    state = interpret_link_target(
        current, target_id="manual-note", existence="present", memberships=()
    )
    context = facts.link_context
    targets = context.current_targets + (target,)
    states = context.current_target_facts + (state,)
    doc = interpret_links(
        current,
        document_id="manual-note",
        source_path="Manual.md",
        path_mode="vault",
        targets=targets,
        target_facts=states,
        inventory="complete",
    )
    assert doc.status != "supported"
    facts = facts.model_copy(
        update={
            "subjects": (
                facts.subjects[0].model_copy(
                    update={
                        "baseline": ContentVersion(
                            status="unknown", content=None, unavailable_digest=None
                        )
                    }
                ),
            ),
            "identity_inventory": facts.identity_inventory + (entry,),
            "format_operation": facts.format_operation.model_copy(
                update={
                    "kind": "onboarding",
                    "recorded_generation": "unknown",
                    "baseline_source_version": None,
                    "established_baseline": None,
                }
            ),
            "link_context": context.model_copy(
                update={
                    "current_targets": targets,
                    "incoming_targets": context.incoming_targets + (target,),
                    "current_target_facts": states,
                    "incoming_target_facts": context.incoming_target_facts + (state,),
                    "current_documents": (doc,),
                    "incoming_documents": (doc,),
                }
            ),
        }
    )
    selection, candidate = attachment_candidate(facts, "current")
    assert len(candidate.outputs) == 1
    assert [(o.path, o.content.data) for o in candidate.outputs] == [
        ("Assets/data.bin", b"\x00authored")
    ]
    checked = validate_attachment_candidate(facts, selection, candidate)
    assert checked.valid, checked.findings
    plan = prepare_review(facts, preflight=preflight())
    chosen = resolve_review(
        plan,
        action(
            plan,
            domain="format",
            choice="current",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert chosen.status == "accepted" and chosen.plan.ready, chosen
    effects = select_review_effects(chosen.plan)
    assert [(r.path, r.content.data) for r in effects.files] == [
        ("Assets/data.bin", b"\x00authored")
    ]
    assert effects.remove_paths == ()


import pytest


@pytest.mark.parametrize("operation_kind", ("onboarding", "format_transition"))
@pytest.mark.parametrize("changed_target", (False, True))
def test_onboarding_current_retains_existing_fragment_warning_without_harming_target(
    tmp_path, changed_target, operation_kind
):
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.update_contracts import UpdatePreparation
    from brz2obsidian.contracts import CurrentContent
    from tests.application.test_update_lifecycle_contracts import preparation
    from tests.reconciliation.test_identity import inventory_item, with_subjects
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import with_review_links

    warning = b"Exact existing [[Second#Missing]] link.\r\n"
    facts = request(original=warning, current=warning, incoming=warning)
    first = facts.subjects[0]
    other = first.model_copy(
        update={
            "item_id": "item:second",
            "title": "Second",
            "path": "Second.md",
            "baseline": ContentVersion(
                status="known",
                content=ExactContent(data=b"# Second\r\n"),
                unavailable_digest=None,
            ),
            "current": CurrentContent(
                existence="present",
                path="Second.md",
                content=ExactContent(data=b"# Second\r\n"),
            ),
            "incoming": ExactContent(data=b"# Second changed\r\n"),
            "source_target": IdentityTargetFacts(
                normalized_path="second.md", containment="contained", status="safe"
            ),
        }
    )
    facts = with_subjects(
        facts,
        (first, other),
        facts.identity_inventory
        + (
            inventory_item(
                "second", "item:second", "Second.md", b"# Second\r\n", title="Second"
            ),
        ),
    )
    operation = facts.format_operation
    facts = with_review_links(
        facts.model_copy(
            update={
                "format_operation": operation.model_copy(
                    update={
                        "kind": operation_kind,
                        "baseline_source_version": operation.target_source_version,
                        "established_baseline": operation.established_baseline.model_copy(
                            update={"source_version": operation.target_source_version}
                        ),
                    }
                ),
            }
        )
    )
    document = next(
        d
        for d in facts.link_context.current_documents
        if d.source_path == "Notes/Opening.md"
    )
    assert document.status == "supported"
    assert document.occurrences[0].meaning.status == "fragment_missing"
    old = preparation()
    prepared = UpdatePreparation.model_validate(
        old.model_dump()
        | {
            "kind": operation_kind,
            "review": prepare_review(facts, preflight=old.review.preflight),
        }
    )
    operations = Operations()
    kept = operations.resolve_update(
        prepared, action(prepared.review, domain="format", choice="current")
    )
    assert kept.code == "accepted", kept
    second = next(
        c
        for c in kept.preparation.review.proposal.changes
        if c.item_id == "item:second"
    )
    assert second.format_review.target_eligible
    chosen = operations.resolve_update(
        kept.preparation,
        action(
            kept.preparation.review,
            second,
            domain="format",
            choice="incoming" if changed_target else "current",
            decision_id="second-choice",
        ),
    )
    assert chosen.code == "accepted", chosen
    (tmp_path / "warning-current-result.json").write_text(
        chosen.model_dump_json(), encoding="utf-8"
    )
    selected = select_review_effects(chosen.preparation.review)
    if changed_target:
        assert not chosen.ready and selected.status == "refused", selected
    else:
        assert chosen.ready and selected.status == "selected", (
            chosen.preparation.review.blockers
        )
        assert [(r.path, r.content.data) for r in selected.files] == [
            ("Notes/Opening.md", warning),
            ("Second.md", b"# Second\r\n"),
        ]
