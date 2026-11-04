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
OWNER_PREFIX = b'---\nsource_collection_id: "folio:collection"\nsource_item_id: "entry:owner"\n---\n'
OWNER_EDITED = OWNER_PREFIX + b"Edited approved owner [[Assets/data.bin|Map]].\r\n"
MANUAL = b"Manual link [[Assets/data.bin|Current]] and embed ![[Assets/data.bin|Incoming]].\r\n"


def membership_preparation(choice, *, include_base=False):
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
    if include_base:
        path = "Templates/Bases/Members.base"
        raw = b"views:\n  - type: table\n    name: Members\n"
        entry = inventory_item("members-base", "support:members-base", path, raw)
        base = target_for_links("support:members-base", path).model_copy(
            update={"identity": entry.identity}
        )
        state = interpret_link_target(
            ExactContent(data=raw),
            target_id=base.target_id,
            existence="present",
            memberships=(),
            source_path=path,
        )
        document = interpret_links(
            ExactContent(data=raw),
            document_id=base.target_id,
            source_path=path,
            path_mode="vault",
            targets=(base,),
            target_facts=(state,),
            inventory="complete",
        )
        targets += (base,)
        states += (state,)
        incoming_states += (state,)
        documents += (document,)
        incoming_documents += (document,)
        inventory += (entry,)
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


def test_public_binary_choice_retains_exact_base_named_view_facts():
    prepared, _ = membership_preparation("incoming", include_base=True)
    offer = next(
        row
        for row in inspect_review_choices(prepared.review)
        if row.domain == "attachment"
    )
    result = Operations().resolve_update_choice(
        prepared,
        requirement_id=offer.requirement_id,
        choice="incoming",
        assumptions_digest=requirement_digest(offer),
    )
    assert result.code == "accepted" and result.ready, result.code
    attachment = next(
        row for row in result.preparation.review.approvals if row.domain == "attachment"
    )
    state = next(
        row
        for row in attachment.attachment_candidate.target_facts
        if row.target_id == "support:members-base"
    )
    assert state.content.data == b"views:\n  - type: table\n    name: Members\n"
    assert [(a.fragment.value, a.raw_parts) for a in state.anchors] == [
        ("Members", (b"Members",)),
    ]
    assert state.interpretation == "supported"
    assert result.publication == "not_started" and result.application is None


def overlapping_preparation():
    """Real public producers see an edited owner and a separate split-reference note."""
    prepared, _ = membership_preparation("both")
    facts = prepared.review.facts
    context = facts.link_context
    original = OWNER_PREFIX + b"Original owner [[Assets/data.bin|Map]].\r\n"
    current = OWNER_PREFIX + b"Current owner [[Assets/data.bin|Map]].\r\n"
    incoming = OWNER_PREFIX + b"Incoming owner [[Assets/data.bin|Map]].\r\n"
    entry = inventory_item("owner-note", "entry:owner", "Notes/Owner.md", current)
    owner = request(original=original, current=current, incoming=incoming).subjects[0]
    owner = owner.model_copy(
        update={
            "item_id": "entry:owner",
            "path": "Notes/Owner.md",
            "current": entry.current,
            "source_target": entry.target,
            "title": "Owner",
        }
    )
    owner_target = target_for_links("owner:note", "Notes/Owner.md").model_copy(
        update={"identity": entry.identity}
    )
    manual_target = target_for_links("manual:note", "Notes/Manual.md")
    targets = tuple(t for t in context.current_targets if t.target_id != "owner:note")
    targets += (owner_target, manual_target)

    def states(rows, raw):
        return tuple(s for s in rows if s.target_id != "owner:note") + tuple(
            interpret_link_target(
                ExactContent(data=content),
                target_id=target_id,
                existence="present",
                memberships=(),
            )
            for target_id, content in (("owner:note", raw), ("manual:note", MANUAL))
        )

    old_states = states(context.current_target_facts, current)
    new_states = states(context.incoming_target_facts, incoming)

    def documents(rows, raw, target_states):
        return tuple(d for d in rows if d.document_id != "owner:note") + tuple(
            interpret_links(
                ExactContent(data=content),
                document_id=target_id,
                source_path=path,
                path_mode="vault",
                targets=targets,
                target_facts=target_states,
                inventory="complete",
            )
            for target_id, content, path in (
                ("owner:note", raw, "Notes/Owner.md"),
                ("manual:note", MANUAL, "Notes/Manual.md"),
            )
        )

    resource = facts.subjects[0].model_copy(
        update={
            "attachment": facts.subjects[0].attachment.model_copy(
                update={"affected_documents": ("owner:note", "manual:note")}
            )
        }
    )
    inventory = tuple(i for i in facts.identity_inventory if i.entry_id != "owner-note")
    inventory += (
        entry,
        inventory_item(
            "manual-note", "unused", "Notes/Manual.md", MANUAL, state="missing"
        ),
    )
    facts = with_subjects(facts, (resource,) + facts.subjects[1:] + (owner,), inventory)
    facts = facts.model_copy(
        update={
            "link_context": LinkContext(
                schema_id="brz2obsidian.link-context",
                schema_version=1,
                inventory="complete",
                current_targets=targets,
                incoming_targets=targets,
                current_target_facts=old_states,
                incoming_target_facts=new_states,
                current_documents=documents(
                    context.current_documents, current, old_states
                ),
                incoming_documents=documents(
                    context.incoming_documents, incoming, new_states
                ),
            )
        }
    )
    prepared = preparation(type(facts).model_validate(facts.model_dump()))
    return choose_text(prepared, "entry:independent", EDITED).preparation


def choose_text(prepared, item_id, raw):
    offer = next(
        row
        for row in inspect_review_choices(prepared.review)
        if next(
            change
            for change in prepared.review.proposal.changes
            if change.change_id == row.change_id
        ).item_id
        == item_id
    )
    result = Operations().resolve_update_choice(
        prepared,
        requirement_id=offer.requirement_id,
        choice="edited",
        assumptions_digest=requirement_digest(offer),
        edited=raw,
    )
    assert result.code == "accepted", result.code
    return result


def choose_overlapping_binary(prepared, *, owner_choice="keep_current"):
    offer = next(
        row
        for row in inspect_review_choices(prepared.review)
        if row.domain == "attachment"
    )
    refs, total, following = attachment_reference_page(prepared, offer.requirement_id)
    assert total == 3 and following is None
    result = Operations().resolve_update_choice(
        prepared,
        requirement_id=offer.requirement_id,
        choice="both",
        assumptions_digest=requirement_digest(offer),
        references=tuple(
            {
                "reference_id": row.reference_id,
                "choice": owner_choice
                if row.document_path == "Notes/Owner.md"
                else "use_secondary"
                if row.old.display_text == "Incoming"
                else "keep_current",
            }
            for row in refs
        ),
    )
    assert result.code == "accepted", result.code
    return result


@pytest.mark.parametrize("owner_choice", ("keep_current", "use_secondary"))
def test_edited_owner_composes_with_later_explicit_attachment_reference(owner_choice):
    """#298 A1: the later link decision preserves already approved prose exactly."""
    prepared = overlapping_preparation()
    prepared = choose_text(prepared, "entry:owner", OWNER_EDITED).preparation
    prior_approvals = prepared.review.approvals
    result = choose_overlapping_binary(prepared, owner_choice=owner_choice)
    assert result.ready and not result.preparation.review.requirements
    assert not result.preparation.review.blockers
    assert all(row in result.preparation.review.approvals for row in prior_approvals)
    selected = select_review_effects(result.preparation.review)
    assert selected.status == "selected", selected.code
    assert {row.path: row.content.data for row in selected.files} == {
        "Assets/data.bin": b"\x00authored",
        "Assets/data (incoming-ba7816bf).bin": b"abc",
        "Notes/Owner.md": OWNER_EDITED
        if owner_choice == "keep_current"
        else OWNER_PREFIX
        + b"Edited approved owner [[Assets/data (incoming-ba7816bf).bin|Map]].\r\n",
        "Notes/Independent.md": EDITED,
        "Notes/Manual.md": b"Manual link [[Assets/data.bin|Current]] and embed ![[Assets/data (incoming-ba7816bf).bin|Incoming]].\r\n",
    }
    assert selected.remove_paths == ()
    assert result.publication == "not_started" and result.application is None


@pytest.mark.parametrize(
    "raw",
    (
        OWNER_PREFIX + b"Edited owner removes the map.\r\n",
        OWNER_PREFIX + b"Edited owner [[Assets/data.bin|Changed alias]].\r\n",
        OWNER_PREFIX
        + b"Edited owner [[Assets/data.bin|Map]] [[Assets/data.bin|Map]].\r\n",
        OWNER_PREFIX
        + b"Edited owner [[Assets/data.bin|Map]] [[Assets/data.bin|New]].\r\n",
    ),
    ids=("removed", "changed", "duplicate", "unreviewed-new-reference"),
)
def test_attachment_reference_does_not_claim_changed_edited_occurrences(raw):
    prepared = choose_text(overlapping_preparation(), "entry:owner", raw).preparation
    result = choose_overlapping_binary(prepared)
    assert not result.ready
    assert "selected_link_context_conflict" in result.preparation.review.blockers
    assert (
        next(
            row.result.data
            for row in result.preparation.review.approvals
            if row.domain == "text" and row.result.data != EDITED
        )
        == raw
    )
    assert select_review_effects(result.preparation.review).status == "refused"


def test_later_edited_owner_preserves_previously_reviewed_secondary_reference():
    binary = choose_overlapping_binary(
        overlapping_preparation(), owner_choice="use_secondary"
    )
    raw = (
        OWNER_PREFIX
        + b"Edited approved owner [[Assets/data (incoming-ba7816bf).bin|Map]].\r\n"
    )
    result = choose_text(binary.preparation, "entry:owner", raw)
    assert result.ready
    selected = select_review_effects(result.preparation.review)
    assert selected.status == "selected", selected.code
    files = {row.path: row.content.data for row in selected.files}
    assert files["Notes/Owner.md"] == raw
    assert files["Assets/data.bin"] == b"\x00authored"
    assert files["Assets/data (incoming-ba7816bf).bin"] == b"abc"
    assert files[EDIT_PATH] == EDITED
    assert selected.remove_paths == ()


def test_later_edited_owner_cannot_silently_undo_reviewed_secondary_destination():
    binary = choose_overlapping_binary(
        overlapping_preparation(), owner_choice="use_secondary"
    )
    result = choose_text(binary.preparation, "entry:owner", OWNER_EDITED)
    assert not result.ready
    assert "selected_link_context_conflict" in result.preparation.review.blockers
    assert select_review_effects(result.preparation.review).status == "refused"


def test_owner_reference_rewrite_preserves_other_occurrences_and_anchor_evidence():
    raw = (
        OWNER_PREFIX
        + b"Edited [[Assets/data.bin|Map]] then [Reference](https://example.test).\r\n"
        + b"# Heading\r\nTail ^stable\r\n"
    )
    prepared = choose_text(overlapping_preparation(), "entry:owner", raw).preparation
    result = choose_overlapping_binary(prepared, owner_choice="use_secondary")
    assert result.ready
    selected = select_review_effects(result.preparation.review)
    assert selected.status == "selected", selected.code
    files = {row.path: row.content.data for row in selected.files}
    assert files["Notes/Owner.md"] == (
        OWNER_PREFIX
        + b"Edited [[Assets/data (incoming-ba7816bf).bin|Map]] then [Reference](https://example.test).\r\n"
        + b"# Heading\r\nTail ^stable\r\n"
    )
    assert files[EDIT_PATH] == EDITED
    assert selected.remove_paths == ()


def test_reference_rewrite_refuses_unsupported_edited_owner_anchor_interpretation():
    raw = OWNER_PREFIX + b"# Edited [[Assets/data.bin|Map]]\r\n"
    prepared = choose_text(overlapping_preparation(), "entry:owner", raw).preparation
    result = choose_overlapping_binary(prepared, owner_choice="use_secondary")
    assert not result.ready
    assert "selected_link_context_conflict" in result.preparation.review.blockers
    assert select_review_effects(result.preparation.review).status == "refused"
