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
