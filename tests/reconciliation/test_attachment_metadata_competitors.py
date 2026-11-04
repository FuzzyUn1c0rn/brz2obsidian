"""Unconsumed physical competitors need no private content in binary review."""

import pytest

from brz2obsidian.contracts import IdentityTargetFacts, ReferenceTarget
from brz2obsidian.core import (
    prepare_review,
    resolve_review,
    validate_attachment_candidate,
)
from tests.reconciliation.test_attachments import (
    attachment_candidate,
    attachment_request,
)
from tests.reconciliation.test_resolution import action, preflight


def metadata_competitor(facts, *, path="Ignored/private.bin", identity=None):
    target = ReferenceTarget(
        schema_id="brz2obsidian.reference-target",
        schema_version=1,
        target_id="metadata:private",
        kind="resource",
        canonical_path=path,
        identity=identity,
        target=IdentityTargetFacts(
            normalized_path=path.casefold(), containment="contained", status="safe"
        ),
        representations=(path,),
        validation_fingerprint="observed-private-metadata",
        status="safe",
    )
    context = facts.link_context
    return facts.model_copy(
        update={
            "link_context": context.model_copy(
                update={
                    "current_targets": context.current_targets + (target,),
                    "incoming_targets": context.incoming_targets + (target,),
                }
            )
        }
    )


def test_unconsumed_identity_free_resource_keeps_metadata_without_private_state():
    facts = metadata_competitor(attachment_request())
    selection, candidate = attachment_candidate(facts, "current")
    assert "metadata:private" in {t.target_id for t in candidate.targets}
    assert "metadata:private" not in {s.target_id for s in candidate.target_facts}
    checked = validate_attachment_candidate(facts, selection, candidate)
    assert checked.valid, checked.findings
    plan = prepare_review(facts, preflight=preflight())
    chosen = resolve_review(
        plan,
        action(
            plan,
            domain="attachment",
            choice="current",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert chosen.status == "accepted" and chosen.plan.ready
    assert chosen.plan.approvals[0].result.data == b"\x00authored"


@pytest.mark.parametrize("difference", ("identity", "selected_collision"))
def test_missing_private_state_never_proves_identity_or_a_free_selected_path(
    difference,
):
    facts = attachment_request()
    facts = metadata_competitor(
        facts,
        path="Assets/data (incoming-ba7816bf).bin"
        if difference == "selected_collision"
        else "Ignored/private.bin",
        identity=facts.identity_inventory[0].identity
        if difference == "identity"
        else None,
    )
    choice = "both" if difference == "selected_collision" else "current"
    selection, candidate = attachment_candidate(facts, choice)
    checked = validate_attachment_candidate(facts, selection, candidate)
    assert not checked.valid
    plan = prepare_review(facts, preflight=preflight())
    chosen = resolve_review(
        plan,
        action(
            plan,
            domain="attachment",
            choice=choice,
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert chosen.status == "refused" and not chosen.plan.approvals


@pytest.mark.parametrize("view", ("current", "incoming"))
def test_actual_reference_to_private_resource_remains_unbound(view):
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.obsidian import interpret_links
    from tests.reconciliation.test_attachments import binary_context
    from tests.reconciliation.test_resolution import note_and_attachment_request

    facts = note_and_attachment_request()
    subject = next(s for s in facts.subjects if s.facet == "content")
    if view == "current":
        current = subject.current.model_copy(
            update={
                "content": ExactContent(
                    data=subject.current.content.data + b" [[Ignored/private.bin]]"
                )
            }
        )
        changed = subject.model_copy(update={"current": current})
    else:
        current = subject.current
        changed = subject.model_copy(
            update={
                "incoming": ExactContent(
                    data=subject.incoming.data + b" [[Ignored/private.bin]]"
                )
            }
        )
    facts = facts.model_copy(
        update={
            "subjects": tuple(changed if s is subject else s for s in facts.subjects),
            "identity_inventory": tuple(
                e.model_copy(update={"current": current})
                if e.current.path == current.path
                else e
                for e in facts.identity_inventory
            ),
        }
    )
    facts = facts.model_copy(update={"link_context": binary_context(facts)})
    facts = metadata_competitor(facts)
    context = facts.link_context
    original_documents = (
        context.current_documents if view == "current" else context.incoming_documents
    )
    registry = (
        context.current_targets if view == "current" else context.incoming_targets
    )
    states = (
        context.current_target_facts
        if view == "current"
        else context.incoming_target_facts
    )
    documents = tuple(
        interpret_links(
            d.content,
            document_id=d.document_id,
            source_path=d.source_path,
            path_mode=d.path_mode,
            targets=registry,
            target_facts=states,
            inventory="complete",
        )
        for d in original_documents
    )
    assert any(
        occurrence.raw == b"[[Ignored/private.bin]]"
        for document in documents
        for occurrence in document.occurrences
    )
    facts = facts.model_copy(
        update={
            "link_context": context.model_copy(update={view + "_documents": documents})
        }
    )
    selection, candidate = attachment_candidate(facts, "current")
    checked = validate_attachment_candidate(facts, selection, candidate)
    assert not checked.valid
    plan = prepare_review(facts, preflight=preflight())
    assert not plan.ready
    binary = next(c for c in plan.proposal.changes if c.attachment_review is not None)
    chosen = resolve_review(
        plan,
        action(
            plan,
            binary,
            domain="attachment",
            choice="current",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert chosen.status == "refused" and not chosen.plan.approvals
