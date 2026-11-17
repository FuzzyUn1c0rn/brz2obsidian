"""Read-only historical resource associations never create asset write offers."""

from hashlib import sha256

import pytest

from brz2obsidian.contracts import (
    ExactContent,
    ImportedItemIdentity,
    RetainedAttachmentOwnership,
)
from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
from brz2obsidian.obsidian import interpret_link_target
from tests.reconciliation.test_resolution import action, preflight
from tests.reconciliation.test_type_tag_dependencies import (
    BLUE,
    RED,
    conflicted_graph,
    facts_for,
    selected_candidate,
)


def readonly_facts(*, current_image_edit=False):
    baseline, incoming, current = conflicted_graph()
    for payload in (incoming, current):
        payload["Notes/Independent.md"] = baseline["Notes/Independent.md"]
    if current_image_edit:
        current["Attachments/A.svg"] = BLUE
    facts = facts_for(baseline, incoming, current)
    # The outer history reader validates this existing fact. Its source version
    # can precede the newest whole-vault source version; current bytes are separate.
    origin = RetainedAttachmentOwnership(
        schema_id="brz2obsidian.retained-attachment-ownership",
        schema_version=1,
        association_id="a" * 64,
        checkpoint_commit="b" * 40,
        generation=1,
        identity=ImportedItemIdentity(
            collection_id="folio:chain", module_id="synthetic-folio", item_id="image:a"
        ),
        facet="asset",
        source_path="Attachments/A.svg",
        source_version="retained-source-v1",
        mapping_sha256="c" * 64,
        payload_sha256=sha256(RED).hexdigest(),
        payload_size=len(RED),
        payload_mode="100644",
    )
    context = facts.link_context
    states = tuple(
        state.model_copy(update={"resource_origin": origin})
        if state.target_id == "subject:image:a:asset"
        else state
        for state in context.current_target_facts
    )
    return facts.model_copy(
        update={
            "subjects": tuple(s for s in facts.subjects if s.item_id == "category:C"),
            "link_context": context.model_copy(update={"current_target_facts": states}),
        }
    )


@pytest.mark.parametrize("current_image_edit", (False, True))
def test_qualified_readonly_origin_keeps_old_source_version_and_current_resource_bytes(
    current_image_edit,
):
    facts = readonly_facts(current_image_edit=current_image_edit)
    plan = prepare_review(facts, preflight=preflight())
    assert not any(c.item_id == "image:a" for c in plan.proposal.changes)
    change = next(c for c in plan.proposal.changes if c.item_id == "category:C")
    selected = resolve_review(
        plan,
        action(
            plan,
            change,
            choice="incoming",
            candidate=selected_candidate(facts, facts, "category:C"),
        ),
    )
    assert selected.status == "accepted" and selected.plan.ready, selected.plan.blockers
    effects = select_review_effects(selected.plan)
    assert effects.status == "selected"
    assert [(f.path, f.content.data) for f in effects.files] == [
        ("Categories/C.md", change.incoming.data)
    ]
    resource = next(
        state
        for state in selected.plan.facts.link_context.current_target_facts
        if state.resource_origin is not None
    )
    assert resource.content.data == (BLUE if current_image_edit else RED)
    assert resource.resource_origin.source_version == "retained-source-v1"
    assert resource.resource_origin.payload_sha256 == sha256(RED).hexdigest()


@pytest.mark.parametrize(
    "fault",
    (
        "missing_origin",
        "foreign_collection",
        "facet",
        "path",
        "bytes",
        "unsafe",
        "missing",
    ),
)
def test_readonly_origin_requires_exact_association_and_existing_regular_resource_gates(
    fault,
):
    facts = readonly_facts()
    context = facts.link_context
    state = next(
        s for s in context.current_target_facts if s.resource_origin is not None
    )
    origin = state.resource_origin
    if fault == "missing_origin":
        state = state.model_copy(update={"resource_origin": None})
    elif fault == "foreign_collection":
        state = state.model_copy(
            update={
                "resource_origin": origin.model_copy(
                    update={
                        "identity": origin.identity.model_copy(
                            update={"collection_id": "other"}
                        )
                    }
                )
            }
        )
    elif fault in ("facet", "path"):
        state = state.model_copy(
            update={
                "resource_origin": origin.model_copy(
                    update={"facet": "other"}
                    if fault == "facet"
                    else {"source_path": "Attachments/Other.svg"}
                )
            }
        )
    elif fault in ("bytes", "missing"):
        state = interpret_link_target(
            ExactContent(data=BLUE) if fault == "bytes" else None,
            target_id=state.target_id,
            source_path="Attachments/A.svg",
            existence="present" if fault == "bytes" else "missing",
            memberships=(),
            output_format=8,
        ).model_copy(update={"resource_origin": origin})
    targets = context.current_targets
    if fault == "unsafe":
        targets = tuple(
            target.model_copy(update={"status": "unsafe"})
            if target.target_id == state.target_id
            else target
            for target in targets
        )
    facts = facts.model_copy(
        update={
            "link_context": context.model_copy(
                update={
                    "current_targets": targets,
                    "current_target_facts": tuple(
                        state if row.target_id == state.target_id else row
                        for row in context.current_target_facts
                    ),
                }
            )
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    change = next(c for c in plan.proposal.changes if c.item_id == "category:C")
    selected = resolve_review(
        plan,
        action(
            plan,
            change,
            choice="incoming",
            candidate=selected_candidate(facts, facts, "category:C"),
        ),
    )
    if fault in ("bytes", "unsafe", "missing"):
        assert "current_link_context_unbound" in selected.plan.blockers
    else:
        assert selected.status == "accepted" and selected.plan.requirements == ()
        assert "current_link_coverage_unavailable" in selected.plan.blockers
    assert not selected.plan.ready
    assert select_review_effects(selected.plan).status == "refused"
