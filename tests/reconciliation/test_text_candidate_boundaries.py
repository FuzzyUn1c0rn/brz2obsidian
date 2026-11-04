"""Explicit candidate decisions retain exact independently supplied meanings."""

import json

import pytest

from brz2obsidian.contracts import (
    ExactContent,
    ImportedItemIdentity,
    ReviewedTextCandidate,
)
from brz2obsidian.core import prepare_review, resolve_review
from brz2obsidian.obsidian import inspect_text_candidate
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links
from tests.reconciliation.test_structure import structured_request

IDENTITY = ImportedItemIdentity(
    collection_id="folio:collection",
    module_id="synthetic-folio",
    item_id="entry:opening",
)


def example(*, structured=True):
    original = b'---\nsource_collection_id: "folio:collection"\nsource_item_id: "entry:opening"\npriority: 1\n---\nOriginal.\n'
    current = original.replace(b"Original.", b"Local.")
    incoming = original.replace(b"Original.", b"Incoming.")
    facts = (
        structured_request(original, current, incoming)
        if structured
        else request(original=original, current=current, incoming=incoming)
    )
    plan = prepare_review(with_review_links(facts), preflight=preflight())
    return facts, plan, current, incoming


def candidate(facts, data):
    return inspect_text_candidate(
        ExactContent(data=data),
        identity=IDENTITY,
        target=facts.subjects[0].source_target,
        output_format=7,
        source_path="Notes/Opening.md",
        document_id="review:owner",
        path_mode="vault",
        link_targets=(),
        link_target_facts=(),
        link_inventory="complete",
    )


def assert_refused_without_grant(plan, offered, *, choice="edited"):
    before = plan.model_dump(mode="json", by_alias=True)
    result = resolve_review(plan, action(plan, choice=choice, candidate=offered))
    assert (result.status, result.code) == ("refused", "invalid_candidate")
    assert result.plan.approvals == () and result.plan.actions == ()
    assert result.plan.proposal == plan.proposal
    assert plan.model_dump(mode="json", by_alias=True) == before


def test_incoming_choice_binds_actual_incoming_bytes():
    facts, plan, current, incoming = example()
    honest = candidate(facts, incoming)
    accepted = resolve_review(plan, action(plan, choice="incoming", candidate=honest))
    assert (
        accepted.status == "accepted"
        and accepted.plan.approvals[0].result.data == incoming
    )
    assert_refused_without_grant(plan, candidate(facts, current), choice="incoming")


@pytest.mark.parametrize(
    "defect",
    ["duplicate_key", "duplicate_identity", "raw", "overlap", "missing_identity"],
)
def test_untrusted_candidate_properties_cannot_contradict_exact_text(defect):
    facts, plan, current, _ = example()
    edited = current.replace(b"Local.", b"Reviewed exact prose.")
    honest = candidate(facts, edited)
    accepted = resolve_review(plan, action(plan, choice="edited", candidate=honest))
    assert (
        accepted.status == "accepted"
        and accepted.plan.approvals[0].result.data == edited
    )
    wire = json.loads(honest.model_dump_json(by_alias=True))
    props = wire["document"]["properties"]
    if defect == "duplicate_key":
        props[1]["key"] = props[0]["key"]
    elif defect == "duplicate_identity":
        props[1]["identity_component"] = props[0]["identity_component"]
    elif defect == "raw":
        props[0]["raw"] = "bm90IHRoZSBvcmlnaW5hbCBieXRlcw=="
    elif defect == "overlap":
        props[1]["span"]["start"] = props[0]["span"]["start"]
    else:
        props.pop(0)
    forged = ReviewedTextCandidate.model_validate_json(json.dumps(wire))
    assert_refused_without_grant(plan, forged)


def test_edited_local_unresolved_appearance_may_only_preserve_its_value():
    original = b"---\ncategories: []\nappearance_category: local-unresolved-provider\n---\nOriginal.\n"
    current = original.replace(b"Original.", b"Local.")
    incoming = original.replace(b"Original.", b"Incoming.")
    facts = structured_request(original, current, incoming)
    plan = prepare_review(with_review_links(facts), preflight=preflight())
    edited = current.replace(b"Local.", b"Reviewed.")
    accepted = resolve_review(
        plan, action(plan, choice="edited", candidate=candidate(facts, edited))
    )
    assert (
        accepted.status == "accepted"
        and accepted.plan.approvals[0].result.data == edited
    )
    other = edited.replace(b"local-unresolved-provider", b"other-unresolved-provider")
    assert_refused_without_grant(plan, candidate(facts, other))

    unstructured = request(original=b"old", current=b"local", incoming=b"incoming")
    unstructured_plan = prepare_review(
        with_review_links(unstructured), preflight=preflight()
    )
    unbound = b"---\nappearance_category: unknown-provider\n---\nReviewed.\n"
    assert_refused_without_grant(unstructured_plan, candidate(unstructured, unbound))


def test_edited_membership_preserves_bound_target_representation():
    from tests.reconciliation.test_memberships import membership_request, target
    from tests.reconciliation.test_resolution import candidate_link_states

    original = b'---\ncategories:\n  - "[[A]]"\n---\nOriginal.'
    current = original.replace(b"Original.", b"Local.")
    incoming = original.replace(b"Original.", b"Incoming.")
    category = target("a", "category", "[[A]]")
    facts = membership_request(original, current, incoming, targets=(category,))
    plan = prepare_review(with_review_links(facts), preflight=preflight())
    edited = current.replace(b"Local.", b"Reviewed.")
    honest = inspect_text_candidate(
        ExactContent(data=edited),
        identity=IDENTITY,
        target=facts.subjects[0].source_target,
        output_format=7,
        membership_targets=(category,),
        source_path="Notes/Opening.md",
        document_id="review:owner",
        path_mode="vault",
        link_targets=(category,),
        link_target_facts=candidate_link_states((category,)),
        link_inventory="complete",
    )
    accepted = resolve_review(plan, action(plan, choice="edited", candidate=honest))
    assert (
        accepted.status == "accepted"
        and accepted.plan.approvals[0].result.data == edited
    )
    wire = json.loads(honest.model_dump_json(by_alias=True))
    prop = next(p for p in wire["document"]["properties"] if p["key"] == "categories")
    prop["representations"] = ["[[Unbound]]"]
    assert_refused_without_grant(
        plan, ReviewedTextCandidate.model_validate_json(json.dumps(wire))
    )
