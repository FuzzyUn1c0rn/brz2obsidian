"""Explicit attachment cleanup through the public whole-review seam."""

import hashlib

import pytest

from brz2obsidian.contracts import (
    AttachmentCandidate,
    AttachmentSelection,
    ExactContent,
    FormatOperation,
    LinkOccurrenceChoice,
)
from brz2obsidian.core import (
    prepare_review,
    refresh_review,
    resolve_review,
    select_review_effects,
)
from brz2obsidian.obsidian import interpret_link_target, interpret_links
from tests.reconciliation.test_attachments import attachment_request, binary_context
from tests.reconciliation.test_identity import inventory_item, with_subjects
from tests.reconciliation.test_resolution import action, preflight


def cleanup_request():
    facts = attachment_request()
    first = facts.subjects[0].model_copy(
        update={"incoming": facts.subjects[0].baseline.content}
    )
    keep = first.model_copy(
        update={
            "facet": "attachment:keep",
            "path": "Assets/keep.bin",
            "baseline": first.baseline.model_copy(
                update={"content": ExactContent(data=b"\x00keep")}
            ),
            "current": first.current.model_copy(
                update={
                    "path": "Assets/keep.bin",
                    "content": ExactContent(data=b"\x00keep"),
                }
            ),
            "incoming": ExactContent(data=b"\x00keep"),
            "source_target": first.source_target.model_copy(
                update={"normalized_path": "assets/keep.bin"}
            ),
            "attachment": first.attachment.model_copy(
                update={
                    "current_target_id": "resource:keep",
                    "allocation_candidates": (),
                }
            ),
        }
    )
    facts = with_subjects(
        facts,
        (first, keep),
        facts.identity_inventory
        + (
            inventory_item(
                "keep",
                first.item_id,
                "Assets/keep.bin",
                b"\x00keep",
                facet="attachment:keep",
            ),
            inventory_item(
                "owner",
                first.item_id,
                "Notes/Owner.md",
                b"Import ![[Assets/data.bin]].",
                facet="content",
            ),
            inventory_item(
                "manual",
                "manual",
                "Manual.md",
                b"Manual [[Assets/data.bin|old]]. `[[Assets/data.bin]]`",
                state="missing",
                facet=None,
            ),
        ),
    )
    operation = FormatOperation.model_validate(
        facts.format_operation.model_dump()
        | {
            "kind": "attachment_cleanup",
            "target_source_version": facts.format_operation.baseline_source_version,
        }
    )
    return facts.model_copy(
        update={"format_operation": operation, "link_context": binary_context(facts)}
    )


def test_historical_ownership_keeps_absent_original_and_current_source_distinct():
    from brz2obsidian.contracts import ImportedItemIdentity, RetainedAttachmentOwnership

    facts = cleanup_request()
    subject = facts.subjects[0]
    assert "retained_ownership" not in subject.attachment.model_dump()
    proof = RetainedAttachmentOwnership(
        schema_id="brz2obsidian.retained-attachment-ownership", schema_version=1,
        association_id="a" * 64, checkpoint_commit="1" * 40, generation=1,
        identity=ImportedItemIdentity(collection_id=facts.incoming_identity.collection_id,
                                     module_id=facts.incoming_identity.module_id,
                                     item_id=subject.item_id),
        facet=subject.facet, source_path="Assets/data.bin", source_version="source:A",
        mapping_sha256=hashlib.sha256(b"independent historical mapping").hexdigest(),
        payload_sha256=hashlib.sha256(b"\x00original").hexdigest(),
        payload_size=len(b"\x00original"), payload_mode="100644",
    )
    absent = subject.model_copy(update={
        "baseline": subject.baseline.model_copy(update={"status": "unknown", "content": None}),
        "incoming": None,
        "attachment": subject.attachment.model_copy(update={"retained_ownership": proof}),
    })
    facts = with_subjects(facts, (absent, *facts.subjects[1:]), facts.identity_inventory)
    facts = facts.model_copy(update={"format_operation": facts.format_operation.model_copy(update={
        "baseline_source_version": "source:B", "target_source_version": "source:B",
        "established_baseline": facts.format_operation.established_baseline.model_copy(update={"source_version": "source:B"}),
    })})
    plan = prepare_review(facts, preflight=preflight())
    current = plan.producer_facts.subjects[0]
    assert current.baseline.status == "unknown" and current.baseline.content is None
    assert current.incoming is None and current.current.content.data == b"\x00authored"
    assert current.attachment.retained_ownership.source_version == "source:A"
    assert plan.facts.format_operation.target_source_version == "source:B"
    change = next(c for c in plan.proposal.changes if c.facet == subject.facet)
    remove = next(a for a in change.attachment_review.alternatives if a.choice == "remove")
    assert remove.eligible and remove.outputs == ()


def attachment_action(plan, facet, choice):
    change = next(c for c in plan.proposal.changes if c.facet == facet)
    alternative = next(
        a for a in change.attachment_review.alternatives if a.choice == choice
    )
    context = plan.producer_facts.link_context
    states = context.current_target_facts
    documents = context.current_documents
    links = ()
    if choice == "remove":
        states = tuple(
            interpret_link_target(
                None, target_id=s.target_id, existence="missing", memberships=()
            )
            if s.target_id == "resource:payload"
            else s
            for s in states
        )
        edited = {
            "Notes/Owner.md": b"Import .",
            "Manual.md": b"Manual . `[[Assets/data.bin]]`",
        }
        documents = tuple(
            interpret_links(
                ExactContent(data=edited[d.source_path]),
                document_id=d.document_id,
                source_path=d.source_path,
                path_mode=d.path_mode,
                targets=context.current_targets,
                target_facts=states,
                inventory="complete",
            )
            for d in documents
        )
        states = tuple(
            interpret_link_target(
                d.content, target_id=s.target_id, existence="present", memberships=()
            )
            if (d := next((d for d in documents if d.document_id == s.target_id), None))
            is not None
            else s
            for s in states
        )
        links = tuple(
            LinkOccurrenceChoice(
                document_id=d.document_id,
                occurrence_id=o.occurrence_id,
                old=o.meaning,
                replacement=b"",
                selected=None,
                expected_memberships=(),
                provenance="explicit_user",
            )
            for d in context.current_documents
            for o in d.occurrences
        )
    selection = AttachmentSelection(
        schema_id="brz2obsidian.attachment-selection",
        schema_version=1,
        proposal_id=plan.proposal.proposal_id,
        generation=plan.proposal.generation,
        item_id=change.item_id,
        facet=change.facet,
        reviewed_change_id=change.change_id,
        reviewed_assumptions=change.assumptions,
        choice=choice,
        link_choices=links,
        provenance="explicit_user",
    )
    candidate = AttachmentCandidate(
        schema_id="brz2obsidian.attachment-candidate",
        schema_version=1,
        outputs=alternative.outputs,
        documents=documents,
        targets=context.current_targets,
        target_facts=states,
    )
    return action(
        plan,
        change,
        decision_id="cleanup:" + facet,
        domain="attachment",
        choice=choice,
        attachment_selection=selection,
        attachment_candidate=candidate,
    )


def select_attachment(plan, facet, choice):
    return resolve_review(plan, attachment_action(plan, facet, choice))


def test_explicit_cleanup_removes_only_selected_attachment_and_literal_references():
    facts = cleanup_request()
    plan = prepare_review(facts, preflight=preflight())
    assert not plan.ready and len(plan.requirements) == 2
    assert all(
        tuple(a.choice for a in c.attachment_review.alternatives if a.eligible)
        == ("current", "remove")
        for c in plan.proposal.changes
    )
    kept = select_attachment(plan, "attachment:keep", "current")
    assert kept.status == "accepted" and not kept.plan.ready
    removed = select_attachment(kept.plan, "attachment:payload", "remove")
    assert removed.status == "accepted" and removed.plan.ready, removed
    assert len(removed.plan.approvals) == 2
    effects = select_review_effects(removed.plan)
    assert effects.status == "selected"
    assert effects.remove_paths == ("Assets/data.bin",)
    assert {f.path: f.content.data for f in effects.files} == {
        "Assets/keep.bin": b"\x00keep",
        "Notes/Owner.md": b"Import .",
        "Manual.md": b"Manual . `[[Assets/data.bin]]`",
    }


def test_ordinary_source_absence_preserves_bytes_and_never_admits_remove():
    facts = cleanup_request()
    facts = facts.model_copy(
        update={
            "format_operation": facts.format_operation.model_copy(
                update={"kind": "source_update"}
            ),
            "subjects": (
                facts.subjects[0].model_copy(update={"incoming": None}),
                facts.subjects[1],
            ),
        }
    )
    context = facts.link_context
    incoming_states = tuple(
        interpret_link_target(
            None, target_id=s.target_id, existence="missing", memberships=()
        )
        if s.target_id == "resource:payload"
        else s
        for s in context.incoming_target_facts
    )
    facts = facts.model_copy(
        update={
            "link_context": context.model_copy(
                update={
                    "incoming_target_facts": incoming_states,
                    "incoming_documents": tuple(
                        interpret_links(
                            d.content,
                            document_id=d.document_id,
                            source_path=d.source_path,
                            path_mode=d.path_mode,
                            targets=context.incoming_targets,
                            target_facts=incoming_states,
                            inventory="complete",
                        )
                        for d in context.incoming_documents
                    ),
                }
            )
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    first = plan.proposal.changes[0]
    assert plan.ready and first.disposition == "source_absent"
    assert first.result.data == b"\x00authored"
    assert "remove" not in {a.choice for a in first.attachment_review.alternatives}
    refused = resolve_review(
        plan, action(plan, first, domain="attachment", choice="remove")
    )
    assert refused.status == "refused" and refused.plan.approvals == ()
    effects = select_review_effects(plan)
    assert effects.status == "selected" and effects.remove_paths == ()
    assert {f.path: f.content.data for f in effects.files}[
        "Assets/data.bin"
    ] == b"\x00authored"
    assert (
        facts.link_context.current_documents[1].content.data
        == b"Manual [[Assets/data.bin|old]]. `[[Assets/data.bin]]`"
    )


@pytest.mark.parametrize(
    "uncertainty",
    ("ownership", "omitted_manual", "unreadable_inventory", "unsupported_manual"),
)
def test_cleanup_does_not_treat_missing_ownership_or_reference_coverage_as_zero(
    uncertainty,
):
    facts = cleanup_request()
    context = facts.link_context
    if uncertainty == "ownership":
        facts = facts.model_copy(
            update={
                "format_operation": facts.format_operation.model_copy(
                    update={"established_baseline": None}
                )
            }
        )
    elif uncertainty == "omitted_manual":
        facts = facts.model_copy(
            update={
                "link_context": context.model_copy(
                    update={"current_documents": context.current_documents[:1]}
                )
            }
        )
    elif uncertainty == "unreadable_inventory":
        facts = facts.model_copy(
            update={
                "link_context": context.model_copy(update={"inventory": "unreadable"})
            }
        )
    else:
        facts = facts.model_copy(
            update={
                "link_context": context.model_copy(
                    update={
                        "current_documents": (
                            context.current_documents[0],
                            context.current_documents[1].model_copy(
                                update={"status": "unsupported"}
                            ),
                        )
                    }
                )
            }
        )
    plan = prepare_review(facts, preflight=preflight())
    offered = next(
        a
        for a in plan.proposal.changes[0].attachment_review.alternatives
        if a.choice == "remove"
    )
    assert not offered.eligible and offered.outputs == ()
    refused = resolve_review(plan, action(plan, domain="attachment", choice="remove"))
    assert refused.status == "refused" and refused.plan.approvals == ()
    assert select_review_effects(plan).remove_paths == ()


@pytest.mark.parametrize(
    "tamper", ("missing_choice", "extra_prose", "unselected_asset")
)
def test_cleanup_requires_each_reference_choice_and_exact_unselected_bytes(tamper):
    facts = cleanup_request()
    plan = prepare_review(facts, preflight=preflight())
    selected = attachment_action(plan, "attachment:payload", "remove")
    if tamper == "missing_choice":
        selected = selected.model_copy(
            update={
                "attachment_selection": selected.attachment_selection.model_copy(
                    update={
                        "link_choices": selected.attachment_selection.link_choices[:1]
                    }
                )
            }
        )
    elif tamper == "extra_prose":
        candidate = selected.attachment_candidate
        selected = selected.model_copy(
            update={
                "attachment_candidate": candidate.model_copy(
                    update={
                        "documents": (
                            candidate.documents[0].model_copy(
                                update={
                                    "content": ExactContent(data=b"Import . Extra.")
                                }
                            ),
                            candidate.documents[1],
                        )
                    }
                )
            }
        )
    else:
        candidate = selected.attachment_candidate
        selected = selected.model_copy(
            update={
                "attachment_candidate": candidate.model_copy(
                    update={
                        "target_facts": tuple(
                            interpret_link_target(
                                ExactContent(data=b"injected"),
                                target_id=s.target_id,
                                existence="present",
                                memberships=(),
                            )
                            if s.target_id == "resource:keep"
                            else s
                            for s in candidate.target_facts
                        )
                    }
                )
            }
        )
    refused = resolve_review(plan, selected)
    assert refused.status == "refused" and refused.plan.approvals == ()
    assert select_review_effects(refused.plan).remove_paths == ()


@pytest.mark.parametrize("changed", ("unrelated_asset", "new_reference"))
def test_cleanup_refresh_reopens_only_the_affected_explicit_choice(changed):
    facts = cleanup_request()
    plan = prepare_review(facts, preflight=preflight())
    plan = select_attachment(plan, "attachment:keep", "current").plan
    old_remove = attachment_action(plan, "attachment:payload", "remove")
    plan = resolve_review(plan, old_remove).plan
    assert plan.ready
    if changed == "unrelated_asset":
        current = facts.subjects[1].current.model_copy(
            update={"content": ExactContent(data=b"\x00later keep")}
        )
        facts = facts.model_copy(
            update={
                "subjects": (
                    facts.subjects[0],
                    facts.subjects[1].model_copy(update={"current": current}),
                ),
                "identity_inventory": tuple(
                    e.model_copy(update={"current": current})
                    if e.entry_id == "keep"
                    else e
                    for e in facts.identity_inventory
                ),
            }
        )
        retained = "cleanup:attachment:payload"
        affected = "attachment:keep"
    else:
        facts = facts.model_copy(
            update={
                "identity_inventory": tuple(
                    e.model_copy(
                        update={
                            "current": e.current.model_copy(
                                update={
                                    "content": ExactContent(
                                        data=b"New ![[Assets/data.bin]]."
                                    )
                                }
                            )
                        }
                    )
                    if e.entry_id == "manual"
                    else e
                    for e in facts.identity_inventory
                )
            }
        )
        retained = "cleanup:attachment:keep"
        affected = "attachment:payload"
    facts = facts.model_copy(
        update={"generation": 2, "link_context": binary_context(facts)}
    )
    refreshed = refresh_review(plan, facts, preflight=preflight())
    assert refreshed.status == "accepted", refreshed
    assert [a.decision_id for a in refreshed.plan.approvals] == [retained]
    pending = {r.change_id for r in refreshed.plan.requirements}
    assert pending == {
        c.change_id for c in refreshed.plan.proposal.changes if c.facet == affected
    }
    assert not refreshed.plan.ready
    assert select_review_effects(refreshed.plan).status == "refused"
    stale = resolve_review(
        refreshed.plan,
        old_remove.model_copy(update={"decision_id": "cleanup:stale-token"}),
    )
    assert stale.status == "stale" and not stale.plan.ready
