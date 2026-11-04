"""Exact manual resources support note review without acquiring write ownership."""

import pytest

from brz2obsidian.contracts import ExactContent
from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
from brz2obsidian.obsidian import interpret_link_target, interpret_links
from tests.reconciliation.test_attachments import target_for_links
from tests.reconciliation.test_identity import inventory_item
from tests.reconciliation.test_resolution import action, linked_note_request, preflight


def manual_resource_facts(resource_path="Assets/manual.bin"):
    facts = linked_note_request()
    entries = (
        inventory_item(
            "manual-document",
            None,
            "Docs/Backlink.md",
            b"Keep [[Notes/Opening]]. ![[" + resource_path.encode() + b"]]",
            state="missing",
            facet=None,
        ),
        inventory_item(
            "manual-resource",
            None,
            resource_path,
            b"\x00\xffmanual",
            state="missing",
            facet=None,
        ),
    )
    document, resource = entries
    targets = (
        target_for_links(document.entry_id, document.current.path),
        target_for_links(resource.entry_id, resource.current.path, kind="resource"),
    )
    states = tuple(
        interpret_link_target(
            entry.current.content,
            target_id=target.target_id,
            existence="present",
            memberships=(),
        )
        for entry, target in zip(entries, targets, strict=True)
    )
    context = facts.link_context
    current_targets = context.current_targets + targets
    incoming_targets = context.incoming_targets + targets
    current_states = context.current_target_facts + states
    incoming_states = context.incoming_target_facts + states

    def documents(old, registry, versions):
        return tuple(
            interpret_links(
                content,
                document_id=document_id,
                source_path=path,
                path_mode="vault",
                targets=registry,
                target_facts=versions,
                inventory="complete",
            )
            for content, document_id, path in (
                *((d.content, d.document_id, d.source_path) for d in old),
                (document.current.content, document.entry_id, document.current.path),
            )
        )

    return facts.model_copy(
        update={
            "identity_inventory": facts.identity_inventory + entries,
            "link_context": context.model_copy(
                update={
                    "current_targets": current_targets,
                    "incoming_targets": incoming_targets,
                    "current_target_facts": current_states,
                    "incoming_target_facts": incoming_states,
                    "current_documents": documents(
                        context.current_documents, current_targets, current_states
                    ),
                    "incoming_documents": documents(
                        context.incoming_documents, incoming_targets, incoming_states
                    ),
                }
            ),
        }
    )


@pytest.mark.parametrize(
    ("choice", "expected"),
    (("current", b"Old [[Guide]]."), ("approve", b"New [[Guide]].")),
)
def test_exact_manual_binary_backlink_context_allows_note_choice_without_resource_ownership(
    choice, expected
):
    facts = manual_resource_facts()
    plan = prepare_review(facts, preflight=preflight())
    transition = resolve_review(plan, action(plan, choice=choice))
    assert transition.status == "accepted" and transition.plan.ready
    effects = select_review_effects(transition.plan)
    assert effects.status == "selected"
    assert [(row.path, row.content.data) for row in effects.files] == [
        ("Notes/Opening.md", expected)
    ]
    assert effects.remove_paths == ()
    assert len(transition.plan.proposal.changes) == 1


def reobserve_documents(facts):
    context = facts.link_context
    updates = {}
    for stage in ("current", "incoming"):
        updates[stage + "_documents"] = tuple(
            interpret_links(
                document.content,
                document_id=document.document_id,
                source_path=document.source_path,
                path_mode="vault",
                targets=getattr(context, stage + "_targets"),
                target_facts=getattr(context, stage + "_target_facts"),
                inventory="complete",
            )
            for document in getattr(context, stage + "_documents")
        )
    return facts.model_copy(update={"link_context": context.model_copy(update=updates)})


@pytest.mark.parametrize(
    "contradiction",
    (
        "markdown_path",
        "claimed_identity",
        "malformed_marker",
        "raw_identity",
        "wrong_state",
        "wrong_target",
        "outside",
        "registry_collision",
        "declared_incoming_document",
    ),
)
def test_local_resource_proof_cannot_hide_document_identity_or_physical_contradictions(
    contradiction,
):
    facts = manual_resource_facts(
        "Assets/manual.MD" if contradiction == "markdown_path" else "Assets/manual.bin"
    )
    entry = facts.identity_inventory[-1]
    context = facts.link_context
    resource = context.current_targets[-1]
    state = context.current_target_facts[-1]
    if contradiction == "claimed_identity":
        entry = entry.model_copy(
            update={
                "identity_state": "valid",
                "identity": facts.identity_inventory[0].identity,
            }
        )
    elif contradiction == "malformed_marker":
        entry = entry.model_copy(
            update={"identity_state": "malformed", "raw_identity": "broken marker"}
        )
    elif contradiction == "raw_identity":
        entry = entry.model_copy(update={"raw_identity": "uninterpreted marker"})
    elif contradiction == "wrong_state":
        state = interpret_link_target(
            ExactContent(data=b"different payload"),
            target_id=resource.target_id,
            existence="present",
            memberships=(),
        )
    elif contradiction == "wrong_target":
        entry = entry.model_copy(
            update={"target": entry.target.model_copy(update={"status": "unknown"})}
        )
    elif contradiction == "outside":
        unsafe = entry.target.model_copy(update={"containment": "outside"})
        entry = entry.model_copy(update={"target": unsafe})
        resource = resource.model_copy(update={"target": unsafe})
    elif contradiction == "declared_incoming_document":
        document = interpret_links(
            entry.current.content,
            document_id=resource.target_id,
            source_path=entry.current.path,
            path_mode="vault",
            targets=context.incoming_targets,
            target_facts=context.incoming_target_facts,
            inventory="complete",
        )
        context = context.model_copy(
            update={"incoming_documents": context.incoming_documents + (document,)}
        )
    updates = {
        "current_targets": context.current_targets[:-1] + (resource,),
        "incoming_targets": context.incoming_targets[:-1] + (resource,),
        "current_target_facts": context.current_target_facts[:-1] + (state,),
        "incoming_target_facts": context.incoming_target_facts[:-1] + (state,),
    }
    if contradiction == "registry_collision":
        competitor = target_for_links(
            "physical-competitor", "assets/MANUAL.bin", kind="resource"
        )
        for stage in ("current", "incoming"):
            updates[stage + "_targets"] += (competitor,)
    facts = facts.model_copy(
        update={
            "identity_inventory": facts.identity_inventory[:-1] + (entry,),
            "link_context": context.model_copy(update=updates),
        }
    )
    facts = reobserve_documents(facts)
    plan = prepare_review(facts, preflight=preflight())
    result = resolve_review(plan, action(plan))
    assert not result.plan.ready
    effects = select_review_effects(result.plan)
    assert effects.status == "refused" and effects.files == ()
