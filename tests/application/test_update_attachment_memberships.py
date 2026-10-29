"""Attachment compilation retains independently known note memberships and edits."""

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_choices import (
    attachment_reference_page,
    requirement_digest,
)
from brz2obsidian.application.update_contracts import UpdatePreparation
from brz2obsidian.contracts import ExactContent, LinkContext
from brz2obsidian.core import (
    inspect_review_choices,
    prepare_review,
    select_review_effects,
)
from brz2obsidian.obsidian import interpret_link_target, interpret_links
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_attachments import (
    linked_attachment_request,
    target_for_links,
)
from tests.reconciliation.test_identity import inventory_item, with_subjects
from tests.reconciliation.test_memberships import target
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import preflight

SUPPORT = "Templates/Category starter.md"
SUPPORT_BYTES = b"---\ntags:\n  - categories\n---\nUnrelated template stays exact.\r\n"
EDIT_PATH = "Notes/Independent.md"
EDIT_PREFIX = b'---\nsource_collection_id: "folio:collection"\nsource_item_id: "entry:independent"\n---\n'
EDITED = EDIT_PREFIX + b"Independently accepted Edited writing.\r\n"


def membership_preparation(choice):
    owner = (
        b"Owner without resource references.\r\n"
        if choice == "incoming"
        else b"Keep [[Assets/data.bin|First]] and ![[Assets/data.bin|Second]].\r\n"
    )
    if choice == "remove":
        owner = b"Owner [[Assets/data.bin|Remove]] retained.\r\n"
    facts = linked_attachment_request(raw=owner)
    context = facts.link_context
    registry = target("format:7:categories", "tag", "categories")
    support = target_for_links("support:category-template", SUPPORT)
    support_state = interpret_link_target(
        ExactContent(data=SUPPORT_BYTES),
        target_id=support.target_id,
        existence="present",
        memberships=(registry.target_id,),
        membership_targets=(registry,),
    )
    support_document = interpret_links(
        ExactContent(data=SUPPORT_BYTES),
        document_id=support.target_id,
        source_path=SUPPORT,
        path_mode="vault",
        targets=(support, registry),
        target_facts=(support_state,),
        inventory="complete",
    )
    targets = context.current_targets + (support, registry)
    states = context.current_target_facts + (support_state,)
    incoming_states = context.incoming_target_facts + (support_state,)
    documents = context.current_documents + (support_document,)
    incoming_documents = context.incoming_documents + (support_document,)
    subjects = facts.subjects
    inventory = facts.identity_inventory + (
        inventory_item(
            "support-template", "unused", SUPPORT, SUPPORT_BYTES, state="missing"
        ),
    )
    if choice != "remove":
        independent = request(
            original=EDIT_PREFIX + b"Original writing.\n",
            current=EDIT_PREFIX + b"Authored writing.\n",
            incoming=EDIT_PREFIX + b"Incoming writing.\n",
        ).subjects[0]
        entry = inventory_item(
            "independent-note",
            "entry:independent",
            EDIT_PATH,
            independent.current.content.data,
        )
        independent = independent.model_copy(
            update={
                "item_id": "entry:independent",
                "path": EDIT_PATH,
                "current": entry.current,
                "source_target": entry.target,
                "title": "Independent",
            }
        )
        reference = target_for_links("independent-note", EDIT_PATH).model_copy(
            update={"identity": entry.identity}
        )
        old = interpret_link_target(
            entry.current.content,
            target_id=reference.target_id,
            existence="present",
            memberships=(),
        )
        new = interpret_link_target(
            independent.incoming,
            target_id=reference.target_id,
            existence="present",
            memberships=(),
        )
        targets += (reference,)
        states += (old,)
        incoming_states += (new,)

        def document(content, state):
            return interpret_links(
                content,
                document_id=reference.target_id,
                source_path=EDIT_PATH,
                path_mode="vault",
                targets=targets,
                target_facts=(state,),
                inventory="complete",
            )

        documents += (document(entry.current.content, old),)
        incoming_documents += (document(independent.incoming, new),)
        subjects += (independent,)
        inventory += (entry,)
    facts = with_subjects(facts, subjects, inventory)
    if choice == "remove":
        resource = subjects[0]
        resource = resource.model_copy(update={"incoming": resource.baseline.content})
        facts = facts.model_copy(
            update={
                "subjects": (resource,),
                "format_operation": facts.format_operation.model_copy(
                    update={
                        "kind": "attachment_cleanup",
                        "target_source_version": facts.format_operation.baseline_source_version,
                    }
                ),
            }
        )
        incoming_states = (
            interpret_link_target(
                resource.incoming,
                target_id="resource:payload",
                existence="present",
                memberships=(),
            ),
        ) + incoming_states[1:]
        incoming_documents = tuple(
            interpret_links(
                row.content,
                document_id=row.document_id,
                source_path=row.source_path,
                path_mode=row.path_mode,
                targets=targets,
                target_facts=incoming_states,
                inventory="complete",
            )
            for row in incoming_documents
        )
    facts = facts.model_copy(
        update={
            "link_context": LinkContext(
                schema_id="brz2obsidian.link-context",
                schema_version=1,
                inventory="complete",
                current_targets=targets,
                incoming_targets=targets,
                current_target_facts=states,
                incoming_target_facts=incoming_states,
                current_documents=documents,
                incoming_documents=incoming_documents,
            )
        }
    )
    if choice == "remove":
        base = preparation()
        plan = prepare_review(facts, preflight=preflight())
        prepared = UpdatePreparation.model_validate(
            base.model_dump()
            | {
                "kind": "attachment_cleanup",
                "review": plan,
                "source_binding": base.source_binding.model_copy(
                    update={
                        "proposal_id": plan.proposal.proposal_id,
                        "generation": plan.proposal.generation,
                        "target_source_version": facts.format_operation.target_source_version,
                    }
                ),
            }
        )
    else:
        prepared = preparation(facts)
        offer = next(
            row
            for row in inspect_review_choices(prepared.review)
            if next(
                change
                for change in prepared.review.proposal.changes
                if change.change_id == row.change_id
            ).item_id
            == "entry:independent"
        )
        accepted = Operations().resolve_update_choice(
            prepared,
            requirement_id=offer.requirement_id,
            choice="edited",
            assumptions_digest=requirement_digest(offer),
            edited=EDITED,
        )
        assert accepted.code == "accepted", accepted.code
        prepared = accepted.preparation
        assert prepared.review.approvals[0].result.data == EDITED
    return prepared, owner


@pytest.mark.parametrize("choice", ("incoming", "both", "remove"))
def test_public_attachment_choice_preserves_memberships_and_independent_edited_result(
    choice,
):
    prepared, owner = membership_preparation(choice)
    before = prepared.review
    offer = next(
        row for row in inspect_review_choices(before) if row.domain == "attachment"
    )
    assert choice in offer.enabled_choices
    references, total, following = attachment_reference_page(
        prepared, offer.requirement_id
    )
    assert total == (0 if choice == "incoming" else 1 if choice == "remove" else 2)
    assert following is None
    supplied = tuple(
        {
            "reference_id": row.reference_id,
            "choice": "drop"
            if choice == "remove"
            else "keep_current"
            if index == 0
            else "use_secondary",
        }
        for index, row in enumerate(references)
    )
    result = Operations().resolve_update_choice(
        prepared,
        requirement_id=offer.requirement_id,
        choice=choice,
        assumptions_digest=requirement_digest(offer),
        references=supplied,
    )
    assert result.code == "accepted" and result.ready, result.code
    assert result.publication == "not_started" and result.application is None
    plan = result.preparation.review
    approval = next(row for row in plan.approvals if row.domain == "attachment")
    candidate = approval.attachment_candidate
    support = next(row for row in candidate.documents if row.source_path == SUPPORT)
    assert support.content.data == SUPPORT_BYTES
    state = next(
        row for row in candidate.target_facts if row.target_id == support.document_id
    )
    assert state.content.data == SUPPORT_BYTES and state.memberships == (
        "format:7:categories",
    )
    assert next(
        row for row in candidate.targets if row.target_id == "format:7:categories"
    ).representations == ("categories",)
    effects = select_review_effects(plan)
    assert effects.status == "selected", effects.code
    files = {row.path: row.content.data for row in effects.files}
    assert SUPPORT not in files
    assert (
        next(
            row
            for row in before.facts.link_context.current_documents
            if row.source_path == SUPPORT
        ).content.data
        == SUPPORT_BYTES
    )
    if choice == "remove":
        assert effects.remove_paths == ("Assets/data.bin",)
        assert "Assets/data.bin" not in files
        assert files["Notes/Owner.md"] == b"Owner  retained.\r\n"
        assert approval.attachment_selection.link_choices[0].selected is None
    else:
        assert (
            next(
                row
                for row in plan.approvals
                if row.result is not None and row.result.data == EDITED
            )
            == before.approvals[0]
        )
        assert files[EDIT_PATH] == EDITED
        assert files["Assets/data.bin"] == (
            b"abc" if choice == "incoming" else b"\x00authored"
        )
        assert effects.remove_paths == ()
        if choice == "both":
            assert files["Assets/data (incoming-ba7816bf).bin"] == b"abc"
            assert (
                files["Notes/Owner.md"]
                == b"Keep [[Assets/data.bin|First]] and ![[Assets/data (incoming-ba7816bf).bin|Second]].\r\n"
            )
            assert tuple(
                row.selected.path for row in approval.attachment_selection.link_choices
            ) == ("Assets/data.bin", "Assets/data (incoming-ba7816bf).bin")
        else:
            assert "Assets/data (incoming-ba7816bf).bin" not in files
            assert (
                next(
                    row
                    for row in candidate.documents
                    if row.source_path == "Notes/Owner.md"
                ).content.data
                == owner
            )


def test_inconsistent_membership_registry_is_rejected_before_attachment_admission():
    wrong = target("format:7:categories", "tag", "another-tag")
    with pytest.raises(ValueError, match="membership facts must bind"):
        interpret_link_target(
            ExactContent(data=SUPPORT_BYTES),
            target_id="support:category-template",
            existence="present",
            memberships=("format:7:categories",),
            membership_targets=(wrong,),
        )
