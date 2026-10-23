"""One real subject reverses its proven selected physical output set."""

import pytest

from tests.reconciliation.test_resolution import action, preflight


def both_reversal_facts(*, with_origin=False):
    from brz2obsidian.contracts import (
        CurrentContent,
        IdentityInventoryItem,
        OperationReversalOutput,
        OperationReversalTarget,
    )
    from brz2obsidian.core import prepare_review, resolve_review
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        linked_attachment_request,
    )

    original = linked_attachment_request()
    offered = prepare_review(original, preflight=preflight())
    selection, candidate = attachment_candidate(original, "both")
    approved = resolve_review(
        offered,
        action(
            offered,
            domain="attachment",
            choice="both",
            decision_id="original:both",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    ).plan
    assert approved.ready
    extra = candidate.outputs[1]
    observed = CurrentContent(
        existence="present", path=extra.path, content=extra.content
    )
    target = next(t for t in candidate.targets if t.target_id == extra.target_id)
    entry = IdentityInventoryItem(
        entry_id="observed:generated-version",
        facet=None,
        identity_state="missing",
        identity=None,
        raw_identity=None,
        title="Generated version",
        current=observed,
        target=target.target,
    )
    proof = OperationReversalTarget(
        schema_id="brz2obsidian.operation-reversal-target",
        schema_version=1,
        operation_id="operation:both",
        operation_kind="apply",
        direction="restore",
        operation_generation=1,
        history_fingerprint="validated:original-both/prepared",
        origin_change_id=offered.proposal.changes[0].change_id,
        origin_decision_id="original:both",
        owned_targets=tuple(
            t
            for t in candidate.targets
            if t.target_id in {o.target_id for o in candidate.outputs}
        ),
        outputs=(
            OperationReversalOutput(
                path=extra.path,
                target_id=extra.target_id,
                produced_existence="present",
                produced=extra.content,
                current=observed,
                target_existence="absent",
                target=None,
            ),
        ),
    )
    subject = original.subjects[0].model_copy(update={"operation_reversal": proof})
    context = original.link_context.model_copy(
        update={
            "current_targets": candidate.targets,
            "incoming_targets": candidate.targets,
            "current_target_facts": candidate.target_facts,
            "incoming_target_facts": candidate.target_facts,
        }
    )
    facts = original.model_copy(
        update={
            "subjects": (subject,),
            "identity_inventory": original.identity_inventory + (entry,),
            "link_context": context,
        }
    )
    return (facts, approved) if with_origin else facts


def test_reverse_removes_only_owned_generated_version_and_preserves_primary_asset():
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects

    facts = both_reversal_facts()
    plan = prepare_review(facts, preflight=preflight())
    assert not plan.ready and not plan.blockers
    assert plan.producer_facts.subjects[0].current.path == "Assets/data.bin"
    chosen = resolve_review(plan, action(plan, domain="reversal", choice="reverse"))
    assert chosen.status == "accepted" and chosen.plan.ready
    selected = select_review_effects(chosen.plan)
    assert selected.status == "selected"
    assert [(f.path, f.content.data) for f in selected.files] == [
        ("Assets/data.bin", b"\x00authored")
    ]
    assert selected.remove_paths == ("Assets/data (incoming-ba7816bf).bin",)


def test_current_keeps_the_complete_owned_output_set_without_source_memory():
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects

    plan = prepare_review(both_reversal_facts(), preflight=preflight())
    kept = resolve_review(plan, action(plan, domain="reversal", choice="current"))
    assert kept.status == "accepted" and kept.plan.ready
    assert kept.plan.approvals[0].source_memory is None
    selected = select_review_effects(kept.plan)
    assert [(f.path, f.content.data) for f in selected.files] == [
        ("Assets/data (incoming-ba7816bf).bin", b"abc"),
        ("Assets/data.bin", b"\x00authored"),
    ]
    assert selected.remove_paths == ()


def test_output_set_approval_survives_only_unchanged_observed_versions():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import (
        load_review,
        prepare_review,
        refresh_review,
        resolve_review,
        resume_review,
        save_review,
        select_review_effects,
    )
    from brz2obsidian.obsidian import interpret_link_target

    facts = both_reversal_facts()
    plan = prepare_review(facts, preflight=preflight())
    approved = resolve_review(
        plan, action(plan, domain="reversal", choice="reverse")
    ).plan
    same = facts.model_copy(update={"generation": 2})
    saved = save_review(approved)
    assert saved.status == "saved"
    loaded = load_review(saved.record.model_dump_json())
    assert loaded.status == "loaded" and not loaded.ready
    unchanged = resume_review(loaded.loaded, same, preflight=preflight())
    assert unchanged.status == "resumed" and unchanged.plan.ready
    assert unchanged.plan.approvals == approved.approvals
    subject = facts.subjects[0]
    proof = subject.operation_reversal
    row = proof.outputs[0]
    observed = row.current.model_copy(
        update={"content": ExactContent(data=b"abc plus later writing")}
    )
    row = row.model_copy(update={"current": observed})
    states = tuple(
        interpret_link_target(
            observed.content,
            target_id=row.target_id,
            existence="present",
            memberships=(),
        )
        if s.target_id == row.target_id
        else s
        for s in facts.link_context.current_target_facts
    )
    changed = same.model_copy(
        update={
            "subjects": (
                subject.model_copy(
                    update={
                        "operation_reversal": proof.model_copy(
                            update={"outputs": (row,)}
                        )
                    }
                ),
            ),
            "identity_inventory": tuple(
                e.model_copy(update={"current": observed})
                if e.current.path == row.path
                else e
                for e in facts.identity_inventory
            ),
            "link_context": facts.link_context.model_copy(
                update={"current_target_facts": states}
            ),
        }
    )
    fresh = refresh_review(approved, changed, preflight=preflight())
    assert fresh.status == "accepted" and not fresh.plan.ready
    assert fresh.plan.approvals == ()
    kept = resolve_review(
        fresh.plan,
        action(
            fresh.plan, domain="reversal", choice="current", decision_id="later:keep"
        ),
    )
    assert kept.status == "accepted" and kept.plan.ready
    selected = select_review_effects(kept.plan)
    assert [(f.path, f.content.data) for f in selected.files] == [
        ("Assets/data (incoming-ba7816bf).bin", b"abc plus later writing"),
        ("Assets/data.bin", b"\x00authored"),
    ]


def test_ownership_projection_retains_only_canonical_subject_outputs():
    import pytest

    from brz2obsidian.core import review_owned_targets

    facts, origin = both_reversal_facts(with_origin=True)
    proof = facts.subjects[0].operation_reversal
    owned = review_owned_targets(
        origin, proof.origin_change_id, proof.origin_decision_id
    )
    assert [(t.target_id, t.canonical_path) for t in owned] == [
        ("resource:payload", "Assets/data.bin"),
        (
            "resource:payload:incoming:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            "Assets/data (incoming-ba7816bf).bin",
        ),
    ]
    assert all(t.identity is None for t in owned)
    with pytest.raises(ValueError, match="Origin decision"):
        review_owned_targets(origin, proof.origin_change_id, "foreign:decision")


def test_foreign_physical_path_cannot_be_added_to_retained_owned_outputs():
    import pytest
    from pydantic import ValidationError

    from brz2obsidian.contracts import OperationReversalTarget

    facts = both_reversal_facts()
    proof = facts.subjects[0].operation_reversal
    row = proof.outputs[0]
    foreign = row.model_copy(
        update={
            "path": "Assets/foreign.bin",
            "current": row.current.model_copy(update={"path": "Assets/foreign.bin"}),
        }
    )
    with pytest.raises(ValidationError, match="retained owned output"):
        OperationReversalTarget.model_validate(
            proof.model_copy(update={"outputs": (foreign,)})
        )


def present_extra_facts():
    from brz2obsidian.obsidian import interpret_link_target

    facts = both_reversal_facts()
    subject = facts.subjects[0]
    proof = subject.operation_reversal
    old = proof.outputs[0]
    current = old.current.model_copy(update={"existence": "absent", "content": None})
    row = old.model_copy(
        update={
            "produced_existence": "absent",
            "produced": None,
            "current": current,
            "target_existence": "present",
            "target": old.produced,
        }
    )
    proof = proof.model_copy(update={"operation_kind": "undo", "outputs": (row,)})
    current_states = tuple(
        interpret_link_target(
            None, target_id=row.target_id, existence="missing", memberships=()
        )
        if s.target_id == row.target_id
        else s
        for s in facts.link_context.current_target_facts
    )
    facts = facts.model_copy(
        update={
            "subjects": (subject.model_copy(update={"operation_reversal": proof}),),
            "identity_inventory": tuple(
                e.model_copy(update={"current": current})
                if e.current.path == row.path
                else e
                for e in facts.identity_inventory
            ),
            "link_context": facts.link_context.model_copy(
                update={"current_target_facts": current_states}
            ),
        }
    )
    selection, candidate = qualified_output_candidate(facts)
    return facts, selection, candidate


def qualified_output_candidate(facts):
    from brz2obsidian.contracts import AttachmentCandidate, AttachmentSelection
    from brz2obsidian.core import reconcile

    subject = facts.subjects[0]
    change = reconcile(facts).changes[0]
    outputs = next(
        a.outputs
        for a in change.attachment_review.alternatives
        if a.choice == "incoming"
    )
    selection = AttachmentSelection(
        schema_id="brz2obsidian.attachment-selection",
        schema_version=1,
        proposal_id=facts.proposal_id,
        generation=facts.generation,
        item_id=subject.item_id,
        facet=subject.facet,
        reviewed_change_id=change.change_id,
        reviewed_assumptions=change.assumptions,
        choice="incoming",
        link_choices=(),
        provenance="explicit_user",
    )
    candidate = AttachmentCandidate(
        schema_id="brz2obsidian.attachment-candidate",
        schema_version=1,
        outputs=outputs,
        documents=facts.link_context.current_documents,
        targets=facts.link_context.current_targets,
        target_facts=tuple(
            next(
                s
                for s in facts.link_context.incoming_target_facts
                if s.target_id == current.target_id
            )
            if current.target_id in {o.target_id for o in outputs}
            else current
            for current in facts.link_context.current_target_facts
        ),
    )
    return selection, candidate


def test_reverse_restores_removed_extra_through_existing_attachment_qualification():
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects

    facts, selection, candidate = present_extra_facts()
    plan = prepare_review(facts, preflight=preflight())
    result = resolve_review(
        plan,
        action(
            plan,
            domain="reversal",
            choice="reverse",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert result.status == "accepted" and result.plan.ready
    selected = select_review_effects(result.plan)
    assert [(f.path, f.content.data) for f in selected.files] == [
        ("Assets/data (incoming-ba7816bf).bin", b"abc"),
        ("Assets/data.bin", b"\x00authored"),
    ]
    assert selected.remove_paths == ()


def test_restored_extra_and_real_owner_note_require_coherent_whole_review():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_identity import with_subjects
    from tests.reconciliation.test_proposals import request

    facts, _, _ = present_extra_facts()
    owner = facts.identity_inventory[1]
    changed = b"[[Assets/data.bin|Keep first]] and [[Assets/data (incoming-ba7816bf).bin|Restored second]]"
    note = request(
        original=owner.current.content.data,
        current=owner.current.content.data,
        incoming=changed,
    ).subjects[0]
    note = note.model_copy(
        update={
            "path": owner.current.path,
            "current": owner.current,
            "source_target": owner.target,
        }
    )
    facts = with_subjects(facts, (facts.subjects[0], note), facts.identity_inventory)
    context = facts.link_context
    incoming_states = tuple(
        interpret_link_target(
            ExactContent(data=changed),
            target_id="owner:note",
            existence="present",
            memberships=(),
        )
        if s.target_id == "owner:note"
        else s
        for s in context.incoming_target_facts
    )
    incoming_doc = interpret_links(
        ExactContent(data=changed),
        document_id="owner:note",
        source_path=owner.current.path,
        path_mode="vault",
        targets=context.incoming_targets,
        target_facts=incoming_states,
        inventory="complete",
    )
    facts = facts.model_copy(
        update={
            "link_context": context.model_copy(
                update={
                    "incoming_target_facts": incoming_states,
                    "incoming_documents": (incoming_doc,),
                }
            )
        }
    )
    selection, candidate = qualified_output_candidate(facts)
    plan = prepare_review(facts, preflight=preflight())
    restored = resolve_review(
        plan,
        action(
            plan,
            domain="reversal",
            choice="reverse",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert restored.status == "accepted" and not restored.plan.ready
    complete = resolve_review(
        restored.plan,
        action(
            restored.plan,
            restored.plan.proposal.changes[1],
            decision_id="owner:restore",
        ),
    )
    assert complete.status == "accepted" and complete.plan.ready
    selected = select_review_effects(complete.plan)
    assert [(f.path, f.content.data) for f in selected.files] == [
        ("Assets/data (incoming-ba7816bf).bin", b"abc"),
        ("Assets/data.bin", b"\x00authored"),
        ("Notes/Owner.md", changed),
    ]


def test_unaffected_primary_later_writing_is_preserved_during_extra_removal():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    facts = both_reversal_facts()
    subject = facts.subjects[0]
    current = subject.current.model_copy(
        update={
            "content": ExactContent(data=b"\x00authored plus later primary writing")
        }
    )
    context = facts.link_context
    states = tuple(
        interpret_link_target(
            current.content,
            target_id="resource:payload",
            existence="present",
            memberships=(),
        )
        if s.target_id == "resource:payload"
        else s
        for s in context.current_target_facts
    )
    documents = tuple(
        interpret_links(
            d.content,
            document_id=d.document_id,
            source_path=d.source_path,
            path_mode=d.path_mode,
            targets=context.current_targets,
            target_facts=states,
            inventory="complete",
        )
        for d in context.current_documents
    )
    facts = facts.model_copy(
        update={
            "subjects": (subject.model_copy(update={"current": current}),),
            "identity_inventory": tuple(
                e.model_copy(update={"current": current})
                if e.current.path == current.path
                else e
                for e in facts.identity_inventory
            ),
            "link_context": context.model_copy(
                update={"current_target_facts": states, "current_documents": documents}
            ),
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    chosen = resolve_review(plan, action(plan, domain="reversal", choice="reverse"))
    assert chosen.status == "accepted" and chosen.plan.ready
    selected = select_review_effects(chosen.plan)
    assert [(f.path, f.content.data) for f in selected.files] == [
        ("Assets/data.bin", b"\x00authored plus later primary writing")
    ]
    assert selected.remove_paths == ("Assets/data (incoming-ba7816bf).bin",)


def test_storage_consent_reopens_when_only_extra_output_selection_changes():
    from brz2obsidian.contracts import ReviewConsentRequirement
    from brz2obsidian.core import prepare_review, resolve_review

    consent = ReviewConsentRequirement(
        schema_id="brz2obsidian.review-consent-requirement",
        schema_version=1,
        consent_id="output-preimages",
        kind="storage",
        requirement="required",
        policy="builtin_transform",
        fingerprint="storage:outputs",
        disclosure="Exact output preimages",
        subjects=(),
    )
    plan = prepare_review(
        both_reversal_facts(),
        preflight=preflight().model_copy(update={"consents": (consent,)}),
    )
    kept = resolve_review(plan, action(plan, domain="reversal", choice="current")).plan
    requirement = next(r for r in kept.requirements if r.domain == "storage")
    consented = resolve_review(
        kept,
        action(
            kept,
            domain="storage",
            choice="accept",
            change_id=requirement.change_id,
            reviewed_assumptions=requirement.assumptions,
            decision_id="storage:keep",
        ),
    ).plan
    assert consented.ready
    reversed_plan = resolve_review(
        consented,
        action(
            consented, domain="reversal", choice="reverse", decision_id="output:remove"
        ),
    ).plan
    assert not reversed_plan.ready
    reopened = next(r for r in reversed_plan.requirements if r.domain == "storage")
    assert reopened.assumptions != requirement.assumptions


@pytest.mark.parametrize("current_state", ["normal", "both_absent", "both_present"])
def test_ownership_projection_uses_retained_note_and_rename_target_paths(current_state):
    from brz2obsidian.core import prepare_review, resolve_review, review_owned_targets
    from tests.reconciliation.test_identity import inventory_item
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import with_review_links

    facts = request(original=b"base\r\n", current=b"base\r\n", incoming=b"new\r\n")
    offered = prepare_review(with_review_links(facts), preflight=preflight())
    approved = resolve_review(offered, action(offered)).plan
    target = review_owned_targets(
        approved, approved.approvals[0].change_id, approved.approvals[0].decision_id
    )
    assert [(t.target_id, t.canonical_path) for t in target] == [
        ("review:opening-entry", "Notes/Opening.md")
    ]
    moved = inventory_item("moved", "entry:opening", "Authored/Name.md", b"base\r\n")
    offered = prepare_review(
        with_review_links(facts.model_copy(update={"identity_inventory": (moved,)})),
        preflight=preflight(),
    )
    renamed = resolve_review(
        offered, action(offered, domain="rename", choice="source_path")
    ).plan
    approved = resolve_review(
        renamed, action(renamed, decision_id="content:renamed")
    ).plan
    assert approved.ready
    targets = review_owned_targets(
        approved, approved.approvals[0].change_id, approved.approvals[0].decision_id
    )
    assert [(t.target_id, t.canonical_path) for t in targets] == [
        ("review:moved", "Authored/Name.md"),
        ("review:moved", "Notes/Opening.md"),
    ]
    from brz2obsidian.contracts import (
        CurrentContent,
        OperationReversalOutput,
        OperationReversalTarget,
    )
    from brz2obsidian.core import select_review_effects
    from brz2obsidian.obsidian import (
        inspect_text_candidate,
        interpret_link_target,
        interpret_links,
    )

    # Actual post-rename observation: one source item, two owned physical paths.
    current_facts = with_review_links(
        request(original=b"base\r\n", current=b"new\r\n", incoming=b"base\r\n")
    )
    subject = current_facts.subjects[0]
    if current_state == "both_absent":
        subject = subject.model_copy(
            update={
                "current": subject.current.model_copy(
                    update={"existence": "absent", "content": None}
                )
            }
        )
    old, new = targets
    observed_old = CurrentContent(
        existence="absent", path=old.canonical_path, content=None
    )
    if current_state == "both_present":
        observed_old = moved.current.model_copy(
            update={
                "content": moved.current.content.model_copy(
                    update={"data": b"base plus later writing\r\n"}
                )
            }
        )
    proof = OperationReversalTarget(
        schema_id="brz2obsidian.operation-reversal-target",
        schema_version=1,
        operation_id="operation:rename",
        operation_kind="apply",
        direction="restore",
        operation_generation=1,
        history_fingerprint="validated:rename",
        origin_change_id=approved.approvals[0].change_id,
        origin_decision_id=approved.approvals[0].decision_id,
        owned_targets=targets,
        outputs=(
            OperationReversalOutput(
                path=new.canonical_path,
                target_id=new.target_id,
                produced_existence="present",
                produced=approved.approvals[0].result,
                current=subject.current,
                target_existence="absent",
                target=None,
            ),
            OperationReversalOutput(
                path=old.canonical_path,
                target_id=old.target_id,
                produced_existence="absent",
                produced=None,
                current=observed_old,
                target_existence="present",
                target=subject.incoming,
            ),
        ),
    )
    state = interpret_link_target(
        subject.current.content,
        target_id=new.target_id,
        existence="missing" if subject.current.content is None else "present",
        memberships=(),
    )
    incoming_state = interpret_link_target(
        subject.incoming, target_id=old.target_id, existence="present", memberships=()
    )
    documents = (
        ()
        if subject.current.content is None
        else (
            interpret_links(
                subject.current.content,
                document_id=new.target_id,
                source_path=new.canonical_path,
                path_mode="vault",
                targets=(new,),
                target_facts=(state,),
                inventory="complete",
            ),
        )
    )
    if observed_old.content is not None:
        documents += (
            interpret_links(
                observed_old.content,
                document_id="physical:old",
                source_path=old.canonical_path,
                path_mode="vault",
                targets=(new,),
                target_facts=(state,),
                inventory="complete",
            ),
        )
    incoming_doc = interpret_links(
        subject.incoming,
        document_id=old.target_id,
        source_path=old.canonical_path,
        path_mode="vault",
        targets=(old,),
        target_facts=(incoming_state,),
        inventory="complete",
    )
    context = current_facts.link_context.model_copy(
        update={
            "current_targets": (new,),
            "incoming_targets": (old,),
            "current_target_facts": (state,),
            "incoming_target_facts": (incoming_state,),
            "current_documents": documents,
            "incoming_documents": (incoming_doc,),
        }
    )
    entries = (
        current_facts.identity_inventory[0].model_copy(
            update={"current": subject.current}
        ),
    )
    if observed_old.content is not None:
        entries += (moved.model_copy(update={"current": observed_old}),)
    current_facts = current_facts.model_copy(
        update={
            "subjects": (subject.model_copy(update={"operation_reversal": proof}),),
            "identity_inventory": entries,
            "link_context": context,
        }
    )
    plan = prepare_review(current_facts, preflight=preflight())
    assert not plan.blockers
    if observed_old.content is not None:
        ordinary = current_facts.model_copy(update={"subjects": (subject,)})
        assert (
            prepare_review(ordinary, preflight=preflight())
            .proposal.changes[0]
            .identity_review.status
            == "unresolved"
        )
        foreign = moved.model_copy(
            update={
                "entry_id": "foreign:duplicate",
                "current": moved.current.model_copy(update={"path": "Foreign/Copy.md"}),
            }
        )
        unrelated = current_facts.model_copy(
            update={"identity_inventory": entries + (foreign,)}
        )
        assert (
            prepare_review(unrelated, preflight=preflight())
            .proposal.changes[0]
            .identity_review.status
            == "unresolved"
        )
        kept = resolve_review(
            plan,
            action(
                plan,
                domain="reversal",
                choice="current",
                decision_id="rename:keep-both",
            ),
        )
        assert (
            not kept.plan.ready
            and "selected_link_context_conflict" in kept.plan.blockers
        )
        assert select_review_effects(kept.plan).status == "refused"
    candidate = inspect_text_candidate(
        subject.incoming,
        identity=current_facts.identity_inventory[0].identity,
        target=old.target,
        output_format=7,
        source_path=old.canonical_path,
        document_id=old.target_id,
        path_mode="vault",
        link_targets=(old,),
        link_target_facts=(incoming_state,),
        link_inventory="complete",
    )
    reversed_plan = resolve_review(
        plan, action(plan, domain="reversal", choice="reverse", candidate=candidate)
    )
    assert reversed_plan.status == "accepted" and reversed_plan.plan.ready
    effects = select_review_effects(reversed_plan.plan)
    assert [(f.path, f.content.data) for f in effects.files] == [
        ("Authored/Name.md", b"base\r\n")
    ]
    assert effects.remove_paths == (
        () if current_state == "both_absent" else ("Notes/Opening.md",)
    )


def test_present_reversal_candidate_cannot_replace_proven_output_payload():
    from hashlib import sha256

    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import prepare_review, resolve_review

    facts, selection, candidate = present_extra_facts()
    outputs = tuple(
        o.model_copy(
            update={
                "content": ExactContent(data=b"foreign payload"),
                "content_version": sha256(b"foreign payload").hexdigest(),
            }
        )
        if o.path != "Assets/data.bin"
        else o
        for o in candidate.outputs
    )
    forged = candidate.model_copy(update={"outputs": outputs})
    plan = prepare_review(facts, preflight=preflight())
    refused = resolve_review(
        plan,
        action(
            plan,
            domain="reversal",
            choice="reverse",
            attachment_selection=selection,
            attachment_candidate=forged,
        ),
    )
    assert refused.status == "refused" and refused.plan == plan


def test_ordinary_review_cannot_inject_operation_alternative_or_foreign_ownership():
    import pytest

    from brz2obsidian.core import review_owned_targets, validate_review

    _, origin = both_reversal_facts(with_origin=True)
    change = origin.proposal.changes[0]
    review = change.attachment_review
    both = next(a for a in review.alternatives if a.choice == "both")
    alternatives = tuple(
        a.model_copy(update={"operation_bound": True, "outputs": both.outputs})
        if a.choice == "incoming"
        else a
        for a in review.alternatives
    )
    forged = origin.model_copy(
        update={
            "proposal": origin.proposal.model_copy(
                update={
                    "changes": (
                        change.model_copy(
                            update={
                                "attachment_review": review.model_copy(
                                    update={"alternatives": alternatives}
                                )
                            }
                        ),
                    )
                }
            )
        }
    )
    assert validate_review(forged).status == "refused"
    approval = origin.approvals[0]
    candidate = approval.attachment_candidate
    extra = candidate.outputs[1]
    foreign = extra.model_copy(update={"path": "Assets/foreign.bin"})
    forged = origin.model_copy(
        update={
            "approvals": (
                approval.model_copy(
                    update={
                        "attachment_candidate": candidate.model_copy(
                            update={"outputs": candidate.outputs + (foreign,)}
                        ),
                    }
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="canonical ready"):
        review_owned_targets(forged, approval.change_id, approval.decision_id)
