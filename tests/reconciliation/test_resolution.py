"""Literal current-generation public review transitions."""

from tests.reconciliation.test_proposals import request


def preflight():
    from brz2obsidian.contracts import ReviewPreflight

    return ReviewPreflight(
        schema_id="brz2obsidian.review-preflight",
        schema_version=1,
        operation_status="idle",
        state_status="supported",
        state_schema="import-state",
        state_version=1,
        state_fingerprint="validated:state:1",
        consents=(),
    )


def action(plan, change=None, **updates):
    from brz2obsidian.contracts import ReviewAction

    change = change or plan.proposal.changes[0]
    fields = {
        "schema_id": "brz2obsidian.review-action",
        "schema_version": 1,
        "decision_id": "review:decision:1",
        "proposal_id": plan.proposal.proposal_id,
        "expected_generation": plan.proposal.generation,
        "change_id": change.change_id,
        "reviewed_assumptions": change.assumptions,
        "domain": "text",
        "choice": "approve",
        "candidate": None,
        "attachment_selection": None,
        "attachment_candidate": None,
        "selected_entry_id": None,
        "disassociate_entry_ids": (),
    }
    fields.update(updates)
    return ReviewAction(**fields)


def candidate_link_states(targets):
    """Available target bytes make membership-linked fixtures independently complete."""
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.obsidian import interpret_link_target

    return tuple(
        interpret_link_target(
            ExactContent(data=b"Target body"),
            target_id=t.target_id,
            existence="present",
            memberships=(),
        )
        for t in targets
        if t.kind != "tag"
    )


def test_stale_generation_and_assumptions_never_record_compatible_approval():
    from brz2obsidian.core import prepare_review, resolve_review

    plan = prepare_review(request(), preflight=preflight())
    before = plan.proposal.model_dump_json()
    assert not plan.ready and plan.proposal.changes[0].result.data == b"incoming\n"
    for changed in (
        action(plan, expected_generation=2),
        action(plan, reviewed_assumptions=()),
        action(plan, proposal_id="another"),
    ):
        transition = resolve_review(plan, changed)
        assert transition.status in ("stale", "refused")
        assert transition.plan.approvals == () and not transition.plan.ready
        assert transition.plan.proposal.model_dump_json() == before
    accepted = resolve_review(plan, action(plan))
    assert accepted.status == "accepted" and accepted.plan.ready
    assert accepted.plan.approvals[0].result.data == b"incoming\n"
    assert accepted.plan.proposal.model_dump_json() == before


def test_review_rebuild_refuses_forged_results_and_repeated_decision_identity():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import prepare_review, resolve_review

    plan = prepare_review(request(), preflight=preflight())
    change = plan.proposal.changes[0]
    forged = plan.model_copy(
        update={
            "proposal": plan.proposal.model_copy(
                update={
                    "changes": (
                        change.model_copy(
                            update={"result": ExactContent(data=b"forged authority")}
                        ),
                    )
                }
            )
        }
    )
    refused = resolve_review(forged, action(plan))
    assert refused.status == "refused" and refused.code == "invalid_plan"
    assert refused.plan.approvals == ()
    assert refused.plan.proposal.changes[0].result.data == b"incoming\n"
    approved = resolve_review(plan, action(plan)).plan
    repeated = resolve_review(approved, action(approved))
    assert repeated.status == "refused" and repeated.code == "decision_id_reused"
    assert repeated.plan.approvals == approved.approvals and repeated.plan.ready


def test_text_conflict_choices_keep_exact_distinct_bytes_and_candidate_safety():
    from brz2obsidian.contracts import ExactContent, ImportedItemIdentity
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import inspect_text_candidate, interpret_structure
    from tests.reconciliation.test_structure import structured_request

    original = b'---\nsource_collection_id: "folio:collection"\nsource_item_id: "entry:opening"\nowner: "source"\n---\nOriginal.\n'
    current = original.replace(b"Original.", b"Local prose.")
    incoming = original.replace(b"Original.", b"Incoming prose.")
    edited = b'---\n# authored comment\nsource_collection_id: "folio:collection"\nsource_item_id: "entry:opening"\nowner: "edited" # keep comment\n---\n# My heading\nReviewed prose.\n'
    facts = structured_request(original, current, incoming)
    plan = prepare_review(facts, preflight=preflight())
    assert plan.proposal.changes[0].disposition == "unresolved"
    assert (
        interpret_structure(ExactContent(data=edited), output_format=7).status
        == "unsupported"
    )
    owner = ImportedItemIdentity(
        collection_id="folio:collection",
        module_id="synthetic-folio",
        item_id="entry:opening",
    )
    for choice, data in (
        ("current", current),
        ("incoming", incoming),
        ("edited", edited),
    ):
        candidate = inspect_text_candidate(
            ExactContent(data=data),
            identity=owner,
            target=facts.subjects[0].source_target,
            output_format=7,
            source_path="Notes/Opening.md",
            document_id="review:owner",
            path_mode="vault",
            link_targets=(),
            link_target_facts=(),
            link_inventory="complete",
        )
        assert candidate.document.status == "safe"
        result = resolve_review(plan, action(plan, choice=choice, candidate=candidate))
        assert result.status == "accepted" and result.plan.ready
        approval = result.plan.approvals[0]
        assert approval.result.data == data and approval.source_accepted == (
            choice == "incoming"
        )
        assert approval.target_path == "Notes/Opening.md"
        assert result.plan.proposal.changes[0].result is None
    wrong = inspect_text_candidate(
        ExactContent(data=edited.replace(b"entry:opening", b"entry:other")),
        identity=owner,
        target=facts.subjects[0].source_target,
        output_format=7,
        source_path="Notes/Opening.md",
        document_id="review:owner",
        path_mode="vault",
        link_targets=(),
        link_target_facts=(),
        link_inventory="complete",
    )
    rejected = resolve_review(plan, action(plan, choice="edited", candidate=wrong))
    assert rejected.status == "refused" and rejected.plan.approvals == ()


def mixed_review_facts():
    from brz2obsidian.contracts import CurrentContent, ExactContent
    from tests.reconciliation.test_identity import inventory_item, with_subjects

    facts = request(original=b"old", current=b"old", incoming=b"new one")
    subjects = []
    inventory = []
    for name, current, incoming, role in (
        ("one", b"old", b"new one", "note"),
        ("two", b"old", b"new two", "guide"),
        ("conflict", b"local", b"source", "note"),
        ("config", b"old", b"new config", "configuration"),
    ):
        path = "Notes/" + name + ".md"
        subject = facts.subjects[0].model_copy(
            update={
                "item_id": "entry:" + name,
                "path": path,
                "current": CurrentContent(
                    existence="present", path=path, content=ExactContent(data=current)
                ),
                "incoming": ExactContent(data=incoming),
                "source_target": facts.subjects[0].source_target.model_copy(
                    update={"normalized_path": path.casefold()}
                ),
                "output_role": role,
            }
        )
        subjects.append(subject)
        inventory.append(inventory_item(name, subject.item_id, path, current))
    return with_subjects(facts, tuple(subjects), tuple(inventory))


def test_compatible_group_summary_bulk_leaves_conflict_and_configuration_blocking():
    from brz2obsidian.core import prepare_review, resolve_review

    plan = prepare_review(mixed_review_facts(), preflight=preflight())
    (group,) = plan.groups
    assert group.count == 2 and group.proposed_bytes == 14
    assert [c.path for c in group.comparisons] == ["Notes/one.md", "Notes/two.md"]
    accepted = resolve_review(
        plan,
        action(
            plan,
            change_id=group.group_id,
            reviewed_assumptions=group.assumptions,
            domain="compatible_group",
            choice="approve",
        ),
    )
    assert accepted.status == "accepted" and not accepted.plan.ready
    assert [a.result.data for a in accepted.plan.approvals] == [b"new one", b"new two"]
    assert {r.domain for r in accepted.plan.requirements} == {"text", "configuration"}
    config = next(c for c in plan.proposal.changes if c.item_id == "entry:config")
    refused = resolve_review(
        plan, action(plan, config, domain="text", choice="approve")
    )
    assert refused.status == "refused" and refused.plan.approvals == ()
    stale = resolve_review(
        plan,
        action(
            plan,
            change_id=group.group_id,
            reviewed_assumptions=(),
            domain="compatible_group",
        ),
    )
    assert stale.status == "stale" and stale.plan.approvals == ()


def test_required_storage_and_tracking_consent_gate_all_content_approvals():
    from brz2obsidian.contracts import ReviewConsentRequirement
    from brz2obsidian.core import prepare_review, resolve_review

    consents = tuple(
        ReviewConsentRequirement(
            schema_id="brz2obsidian.review-consent-requirement",
            schema_version=1,
            consent_id=kind,
            kind=kind,
            requirement="required",
            policy="builtin_transform" if kind == "storage" else "ordinary",
            fingerprint="policy:" + kind,
            disclosure="Exact owned preimages and metadata",
            subjects=(),
        )
        for kind in ("storage", "tracking")
    )
    plan = prepare_review(
        request(), preflight=preflight().model_copy(update={"consents": consents})
    )
    approved = resolve_review(plan, action(plan)).plan
    assert not approved.ready and {r.domain for r in approved.requirements} == {
        "storage",
        "tracking",
    }
    storage = next(r for r in approved.requirements if r.domain == "storage")
    declined = resolve_review(
        approved,
        action(
            approved,
            change_id=storage.change_id,
            reviewed_assumptions=storage.assumptions,
            decision_id="storage:decline",
            domain="storage",
            choice="decline",
        ),
    )
    assert declined.status == "accepted" and not declined.plan.ready
    assert declined.plan.approvals == approved.approvals
    state = declined.plan
    for kind in ("storage", "tracking"):
        requirement = next(r for r in state.requirements if r.domain == kind)
        transition = resolve_review(
            state,
            action(
                state,
                change_id=requirement.change_id,
                reviewed_assumptions=requirement.assumptions,
                decision_id=kind + ":accept",
                domain=kind,
                choice="accept",
            ),
        )
        assert transition.status == "accepted"
        state = transition.plan
    assert state.ready and len(state.approvals) == 1 and len(state.consents) == 2


def test_operation_state_and_unsupported_policy_refusal_cannot_be_consented_away():
    from brz2obsidian.contracts import ReviewConsentRequirement
    from brz2obsidian.core import prepare_review, resolve_review

    unsafe = ReviewConsentRequirement(
        schema_id="brz2obsidian.review-consent-requirement",
        schema_version=1,
        consent_id="filter",
        kind="storage",
        requirement="required",
        policy="custom_filter",
        fingerprint="filter:1",
        disclosure="Custom filter",
        subjects=(),
    )
    variants = [
        preflight().model_copy(update={"operation_status": status})
        for status in ("active", "incomplete", "recovery_required", "unknown")
    ]
    variants += [
        preflight().model_copy(update={"state_status": status, "state_version": 999})
        for status in ("unsupported_version", "unsupported_state", "corrupt", "unknown")
    ]
    variants += [preflight().model_copy(update={"consents": (unsafe,)})]
    for facts in variants:
        plan = prepare_review(request(), preflight=facts)
        assert not plan.ready and plan.readiness == "refused" and plan.blockers
        denied = resolve_review(plan, action(plan))
        assert denied.status == "refused" and denied.plan.approvals == ()


def test_current_resolution_records_validated_dependencies_and_preservation_memory():
    from brz2obsidian.contracts import ExactContent, ImportedItemIdentity
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import inspect_text_candidate

    facts = request(original=b"old", current=b"local", incoming=b"incoming")
    plan = prepare_review(facts, preflight=preflight())
    candidate = inspect_text_candidate(
        ExactContent(data=b"local"),
        identity=ImportedItemIdentity(
            collection_id="folio:collection",
            module_id="synthetic-folio",
            item_id="entry:opening",
        ),
        target=facts.subjects[0].source_target,
        output_format=7,
        source_path="Notes/Opening.md",
        document_id="review:owner",
        path_mode="vault",
        link_targets=(),
        link_target_facts=(),
        link_inventory="complete",
    )
    accepted = resolve_review(plan, action(plan, choice="current", candidate=candidate))
    approval = accepted.plan.approvals[0]
    assert (
        accepted.plan.ready
        and approval.result.data == b"local"
        and not approval.source_accepted
    )
    assert approval.source_memory.choice == "keep_vault"
    assert approval.source_memory.reviewed_incoming.data == b"incoming"
    assert (
        approval.source_memory.provenance.reviewed_assumptions
        == plan.proposal.changes[0].assumptions
    )
    assert any(
        a.key.startswith("review-candidate:") and a.kind == "candidate"
        for a in approval.assumptions
    )
    forged = candidate.model_copy(update={"content": ExactContent(data=b"unbound")})
    refused = resolve_review(plan, action(plan, choice="edited", candidate=forged))
    assert refused.status == "refused" and refused.plan.approvals == ()


def test_explicit_configuration_and_opaque_current_preservation_remain_separate():
    from brz2obsidian.core import prepare_review, resolve_review

    facts = request(original=b"old", current=b"authored\xff", incoming=b"new")
    opaque = prepare_review(facts, preflight=preflight())
    kept = resolve_review(opaque, action(opaque, choice="current"))
    assert kept.status == "accepted" and kept.plan.ready
    assert (
        kept.plan.approvals[0].result.data == b"authored\xff"
        and not kept.plan.approvals[0].source_accepted
    )
    config = prepare_review(
        facts.model_copy(
            update={
                "subjects": (
                    facts.subjects[0].model_copy(
                        update={"output_role": "configuration"}
                    ),
                )
            }
        ),
        preflight=preflight(),
    )
    assert {r.domain for r in config.requirements} == {
        "configuration"
    } and config.groups == ()
    wrong = resolve_review(config, action(config, choice="current"))
    assert wrong.status == "refused" and wrong.plan.approvals == ()
    accepted = resolve_review(
        config, action(config, domain="configuration", choice="current")
    )
    assert accepted.status == "accepted" and accepted.plan.ready
    assert (
        accepted.plan.approvals[0].result.data == b"authored\xff"
        and not accepted.plan.approvals[0].source_accepted
    )
    assert accepted.plan.approvals[0].source_memory.review_domain == "configuration"


def test_rename_delegates_exact_offered_path_and_replays_before_content_approval():
    from brz2obsidian.core import prepare_review, resolve_review
    from tests.reconciliation.test_identity import inventory_item

    facts = request()
    moved = inventory_item(
        "moved", "entry:opening", "Authored/Name.md", b"original\r\n"
    )
    facts = facts.model_copy(update={"identity_inventory": (moved,)})
    plan = prepare_review(facts, preflight=preflight())
    assert {r.domain for r in plan.requirements} == {"text"}
    assert plan.groups[0].comparisons[0].target_path == "Authored/Name.md"
    renamed = resolve_review(plan, action(plan, domain="rename", choice="source_path"))
    assert (
        renamed.status == "accepted"
        and not renamed.plan.ready
        and renamed.plan.approvals == ()
    )
    change = renamed.plan.proposal.changes[0]
    assert (
        change.path == "Authored/Name.md" and change.target_path == "Notes/Opening.md"
    )
    assert change.rename_review.status == "accepted"
    approved = resolve_review(
        renamed.plan, action(renamed.plan, decision_id="content:after-rename")
    )
    assert approved.status == "accepted" and approved.plan.ready
    assert approved.plan.approvals[0].target_path == "Notes/Opening.md"
    assert approved.plan.facts == facts and len(approved.plan.actions) == 2


def test_association_records_only_proposed_repair_and_never_completes_identity():
    from brz2obsidian.core import prepare_review, resolve_review
    from tests.reconciliation.test_identity import inventory_item

    facts = request()
    missing = inventory_item(
        "missing", "entry:opening", "Notes/Opening.md", b"original\r\n", state="missing"
    )
    facts = facts.model_copy(update={"identity_inventory": (missing,)})
    plan = prepare_review(facts, preflight=preflight())
    assert {r.domain for r in plan.requirements} == {"identity"} and plan.groups == ()
    selected = resolve_review(
        plan,
        action(
            plan, domain="identity", choice="associate", selected_entry_id="missing"
        ),
    )
    assert (
        selected.status == "accepted"
        and not selected.plan.ready
        and selected.plan.approvals == ()
    )
    review = selected.plan.proposal.changes[0].identity_review
    assert review.status == "association_proposed" and review.repair_required
    assert (
        review.selected_entry_id == "missing" and review.provenance == "explicit_user"
    )
    attempted = resolve_review(
        selected.plan,
        action(selected.plan, decision_id="cannot:approve", choice="approve"),
    )
    assert attempted.status == "refused" and attempted.plan.approvals == ()
    assert selected.plan.facts.identity_inventory[0].identity_state == "missing"
    invalid = resolve_review(
        plan,
        action(
            plan,
            domain="identity",
            choice="associate",
            selected_entry_id="missing",
            disassociate_entry_ids=("missing",),
        ),
    )
    assert (
        invalid.status == "refused"
        and invalid.plan.approvals == ()
        and invalid.plan.actions == ()
    )


def test_restoration_decline_remembers_exact_source_while_restore_needs_valid_candidate():
    from brz2obsidian.contracts import (
        ExactContent,
        ImportedItemIdentity,
    )
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import inspect_text_candidate
    from tests.reconciliation.test_absence import facts_for

    facts = facts_for(existence="absent", incoming=b"incoming\n")
    subject = facts.subjects[0]
    plan = prepare_review(facts, preflight=preflight())
    assert {r.domain for r in plan.requirements} == {
        "restoration"
    } and plan.groups == ()
    declined = resolve_review(
        plan, action(plan, domain="restoration", choice="decline_restoration")
    )
    assert declined.status == "accepted" and declined.plan.ready
    approval = declined.plan.approvals[0]
    assert approval.result is None and not approval.source_accepted
    assert approval.source_memory.choice == "decline_restoration"
    assert approval.source_memory.reviewed_incoming.data == b"incoming\n"
    missing = resolve_review(
        plan, action(plan, domain="restoration", choice="restore_incoming")
    )
    assert missing.status == "refused" and missing.code == "invalid_candidate"
    candidate = inspect_text_candidate(
        ExactContent(data=b"incoming\n"),
        identity=ImportedItemIdentity(
            collection_id="folio:collection",
            module_id="synthetic-folio",
            item_id="entry:opening",
        ),
        target=subject.source_target,
        output_format=7,
        source_path="Notes/Opening.md",
        document_id="review:owner",
        path_mode="vault",
        link_targets=(),
        link_target_facts=(),
        link_inventory="complete",
    )
    restored = resolve_review(
        plan,
        action(
            plan, domain="restoration", choice="restore_incoming", candidate=candidate
        ),
    )
    assert restored.status == "accepted" and restored.plan.ready
    assert (
        restored.plan.approvals[0].result.data == b"incoming\n"
        and restored.plan.approvals[0].source_accepted
    )


def test_mapping_and_format_choices_never_join_compatible_bulk_or_claim_old_bytes_pristine():
    from brz2obsidian.contracts import ClassificationMapping
    from brz2obsidian.core import prepare_review, resolve_review
    from tests.reconciliation.test_formats import operation
    from tests.reconciliation.test_memberships import membership_request, target

    old = b"---\ncategories: []\n---\nText.\n"
    incoming = b'---\ncategories: ["[[B]]"]\n---\nText.\n'
    mapping = ClassificationMapping(
        schema_id="brz2obsidian.classification-mapping",
        schema_version=1,
        classification_id="source:b",
        target_id="b",
        kind="category",
        source_label="B",
    )
    facts = membership_request(
        old,
        old,
        incoming,
        targets=(target("b", "category", "[[B]]"),),
        incoming_mappings=(mapping,),
    )
    plan = prepare_review(facts, preflight=preflight())
    assert {r.domain for r in plan.requirements} == {"mapping"} and plan.groups == ()
    kept = resolve_review(plan, action(plan, domain="mapping", choice="current"))
    assert kept.status == "accepted" and kept.plan.ready
    assert (
        kept.plan.approvals[0].result.data == old
        and not kept.plan.approvals[0].source_accepted
    )
    assert kept.plan.approvals[0].source_memory.choice == "keep_vault"
    # An unavailable historical renderer produces an explicit onboarding choice.
    facts = request(current=b"authored\xff", incoming=b"target format\n")
    older = facts.baseline_identity.model_copy(update={"output_format": 6})
    facts = facts.model_copy(
        update={
            "baseline_identity": older,
            "format_operation": operation(
                "onboarding",
                recorded_generation="unavailable",
                established_baseline=None,
            ),
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    assert {r.domain for r in plan.requirements} == {"format"} and plan.groups == ()
    kept = resolve_review(plan, action(plan, domain="format", choice="current"))
    assert kept.status == "accepted" and kept.plan.ready
    assert (
        kept.plan.approvals[0].result.data == b"authored\xff"
        and not kept.plan.approvals[0].source_accepted
    )
    assert kept.plan.producer_facts.format_operation.established_baseline is None


def test_edited_candidate_rejects_semantic_duplicate_keys_memberships_and_unsafe_targets():
    from brz2obsidian.contracts import ExactContent, ImportedItemIdentity
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import inspect_text_candidate
    from tests.reconciliation.test_memberships import target

    facts = request(original=b"old", current=b"local", incoming=b"source")
    plan = prepare_review(facts, preflight=preflight())
    identity = ImportedItemIdentity(
        collection_id="folio:collection",
        module_id="synthetic-folio",
        item_id="entry:opening",
    )
    a = target("a", "category", "[[A]]")
    candidates = (
        (b"---\nowner: first\nowner: second\n---\nText.", ()),
        (b"---\ntrue: first\nTrue: second\n---\nText.", ()),
        (b'---\ncategories: ["[[A]]", "[[A]]"]\n---\nText.', (a,)),
        (
            b'---\ncategories: ["[[A]]"]\n---\nText.',
            (
                a.model_copy(
                    update={
                        "target": a.target.model_copy(update={"containment": "outside"})
                    }
                ),
            ),
        ),
        (b'---\ncategories: ["[[Unknown]]"]\n---\nText.', ()),
        (b"---\nsource_item_id: 1\n---\nText.", ()),
    )
    for data, targets in candidates:
        candidate = inspect_text_candidate(
            ExactContent(data=data),
            identity=identity,
            target=facts.subjects[0].source_target,
            output_format=7,
            membership_targets=targets,
            source_path="Notes/Opening.md",
            document_id="review:owner",
            path_mode="vault",
            link_targets=targets,
            link_target_facts=candidate_link_states(targets),
            link_inventory="complete",
        )
        refused = resolve_review(
            plan, action(plan, choice="edited", candidate=candidate)
        )
        assert refused.status == "refused" and refused.code == "invalid_candidate"
        assert refused.plan.approvals == () and refused.plan.proposal == plan.proposal
    safe = inspect_text_candidate(
        ExactContent(
            data=b'---\n# caf\xc3\xa9\ncategories: ["[[A]]"]\nappearance_category: ""\n---\nR\xc3\xa9vis\xc3\xa9.\n',
        ),
        identity=identity,
        target=facts.subjects[0].source_target,
        output_format=7,
        membership_targets=(a,),
        source_path="Notes/Opening.md",
        document_id="review:owner",
        path_mode="vault",
        link_targets=(a,),
        link_target_facts=candidate_link_states((a,)),
        link_inventory="complete",
    )
    accepted = resolve_review(plan, action(plan, choice="edited", candidate=safe))
    assert accepted.status == "accepted" and accepted.plan.ready
    assert accepted.plan.approvals[0].result.data.endswith(b"R\xc3\xa9vis\xc3\xa9.\n")
    outside = safe.model_copy(
        update={"target": safe.target.model_copy(update={"containment": "outside"})}
    )
    assert (
        resolve_review(plan, action(plan, choice="edited", candidate=outside)).status
        == "refused"
    )


def test_rename_after_bulk_invalidates_only_affected_content_authority():
    from brz2obsidian.core import prepare_review, resolve_review

    facts = mixed_review_facts()
    entry = facts.identity_inventory[0]
    entry = entry.model_copy(
        update={
            "current": entry.current.model_copy(update={"path": "Authored/One.md"}),
            "target": entry.target.model_copy(
                update={"normalized_path": "authored/one.md"}
            ),
        }
    )
    facts = facts.model_copy(
        update={"identity_inventory": (entry,) + facts.identity_inventory[1:]}
    )
    plan = prepare_review(facts, preflight=preflight())
    group = plan.groups[0]
    approved = resolve_review(
        plan,
        action(
            plan,
            domain="compatible_group",
            change_id=group.group_id,
            reviewed_assumptions=group.assumptions,
        ),
    ).plan
    assert [a.target_path for a in approved.approvals] == [
        "Authored/One.md",
        "Notes/two.md",
    ]
    renamed = resolve_review(
        approved,
        action(
            approved,
            domain="rename",
            choice="source_path",
            decision_id="rename:after-bulk",
        ),
    )
    assert renamed.status == "accepted" and not renamed.plan.ready
    assert [a.target_path for a in renamed.plan.approvals] == ["Notes/two.md"]
    assert renamed.plan.proposal.changes[0].target_path == "Notes/one.md"
    assert renamed.plan.proposal.changes[1] == plan.proposal.changes[1]
    assert any(
        r.change_id == renamed.plan.proposal.changes[0].change_id
        for r in renamed.plan.requirements
    )


def test_preflight_requires_explicit_interpreted_state_and_closed_versioned_actions():
    import pytest
    from pydantic import ValidationError

    from brz2obsidian.contracts import ReviewAction, ReviewPreflight
    from brz2obsidian.core import prepare_review, resolve_review

    plan = prepare_review(request(), preflight=preflight())
    for update in (
        {"schema_version": 2},
        {"schema_version": True},
        {"arbitrary_paths": ("Elsewhere.md",)},
    ):
        with pytest.raises(ValidationError):
            ReviewAction.model_validate(action(plan).model_dump() | update)
    missing = preflight().model_dump()
    del missing["consents"]
    with pytest.raises(ValidationError):
        ReviewPreflight.model_validate(missing)
    for update in (
        {"state_schema": None},
        {"state_version": None},
        {"state_status": "absent", "state_schema": None, "state_version": None},
    ):
        refused = prepare_review(
            request(), preflight=preflight().model_copy(update=update)
        )
        assert refused.readiness == "refused" and not refused.ready
        result = resolve_review(refused, action(refused))
        assert result.status == "refused" and result.plan.approvals == ()


def test_configuration_keep_memory_is_domain_and_context_bound_across_new_proposal():
    from brz2obsidian.contracts import SourceVersionMemory
    from brz2obsidian.core import prepare_review, resolve_review

    facts = request(
        original=b"old config", current=b"authored config", incoming=b"new config"
    )
    subject = facts.subjects[0].model_copy(update={"output_role": "configuration"})
    facts = facts.model_copy(update={"subjects": (subject,)})
    plan = prepare_review(facts, preflight=preflight())
    kept = resolve_review(plan, action(plan, domain="configuration", choice="current"))
    assert kept.status == "accepted" and kept.plan.ready
    memory = kept.plan.approvals[0].source_memory
    assert memory is not None and memory.review_domain == "configuration"
    assert (
        memory.reviewed_incoming.data == b"new config" and memory.choice == "keep_vault"
    )
    restored = SourceVersionMemory.model_validate_json(memory.model_dump_json())
    later = facts.model_copy(
        update={
            "proposal_id": "proposal:later",
            "generation": 2,
            "source_version_memory": (restored,),
        }
    )
    same = prepare_review(later, preflight=preflight())
    assert same.ready and same.approvals == () and same.requirements == ()
    assert same.proposal.changes[0].result.data == b"authored config"
    assert same.proposal.changes[0].provenance.rule == "remembered_keep"
    from tests.reconciliation.test_absence import remembered

    local = subject.current.model_copy(
        update={
            "content": subject.current.content.model_copy(
                update={"data": b"new local config"}
            )
        }
    )
    locally_edited = later.model_copy(
        update={
            "subjects": (subject.model_copy(update={"current": local}),),
            "identity_inventory": (
                later.identity_inventory[0].model_copy(update={"current": local}),
            ),
        }
    )
    retained = prepare_review(locally_edited, preflight=preflight())
    assert (
        retained.ready
        and retained.proposal.changes[0].result.data == b"new local config"
    )
    generic = remembered(
        facts.model_copy(
            update={"subjects": (subject.model_copy(update={"output_role": "note"}),)}
        )
    )
    assert not prepare_review(
        later.model_copy(update={"source_version_memory": (generic,)}),
        preflight=preflight(),
    ).ready
    changed = later.model_copy(
        update={
            "subjects": (
                subject.model_copy(
                    update={
                        "incoming": subject.incoming.model_copy(
                            update={"data": b"newer config"}
                        )
                    }
                ),
            )
        }
    )
    assert not prepare_review(changed, preflight=preflight()).ready
    newer_identity = facts.incoming_identity.model_copy(
        update={"settings_digest": "new settings"}
    )
    changed = later.model_copy(update={"incoming_identity": newer_identity})
    assert not prepare_review(changed, preflight=preflight()).ready
    # A separately established supported context still needs new config consent.
    established = later.format_operation.established_baseline.model_copy(
        update={"identity": newer_identity}
    )
    supported = later.model_copy(
        update={
            "baseline_identity": newer_identity,
            "incoming_identity": newer_identity,
            "format_operation": later.format_operation.model_copy(
                update={"established_baseline": established}
            ),
        }
    )
    reopened = prepare_review(supported, preflight=preflight())
    assert reopened.readiness == "review_required" and {
        r.domain for r in reopened.requirements
    } == {"configuration"}
    released = later.model_copy(
        update={
            "incoming_identity": facts.incoming_identity.model_copy(
                update={"module_version": "new release"}
            )
        }
    )
    assert prepare_review(released, preflight=preflight()).ready
    unsafe = later.model_copy(
        update={
            "identity_inventory": (
                later.identity_inventory[0].model_copy(
                    update={
                        "target": later.identity_inventory[0].target.model_copy(
                            update={"containment": "outside"}
                        )
                    }
                ),
            )
        }
    )
    assert prepare_review(unsafe, preflight=preflight()).readiness == "refused"
    transition = later.model_copy(
        update={
            "format_operation": later.format_operation.model_copy(
                update={
                    "kind": "format_transition",
                    "target_source_version": "source:a",
                }
            )
        }
    )
    assert not prepare_review(transition, preflight=preflight()).ready


def test_configuration_memory_rejects_relabelled_content_history_and_changed_context():
    import pytest
    from pydantic import ValidationError

    from brz2obsidian.contracts import SourceVersionMemory
    from brz2obsidian.core import prepare_review, resolve_review
    from tests.reconciliation.test_absence import remembered

    content = request(original=b"old", current=b"local", incoming=b"new")
    generic = remembered(content)
    facts = content.model_copy(
        update={
            "subjects": (
                content.subjects[0].model_copy(update={"output_role": "configuration"}),
            )
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    kept = resolve_review(plan, action(plan, domain="configuration", choice="current"))
    memory = kept.plan.approvals[0].source_memory
    forged = generic.model_dump() | {
        "review_domain": "configuration",
        "configuration_context": memory.configuration_context,
    }
    with pytest.raises(ValidationError):
        SourceVersionMemory.model_validate(forged)
    changed = memory.model_dump() | {
        "configuration_context": memory.configuration_context.model_copy(
            update={"settings_digest": "unreviewed"}
        )
    }
    with pytest.raises(ValidationError):
        SourceVersionMemory.model_validate(changed)


def test_storage_consent_reopens_when_chosen_exact_bytes_change():
    from brz2obsidian.contracts import (
        ExactContent,
        ImportedItemIdentity,
        ReviewConsentRequirement,
    )
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import inspect_text_candidate

    consent = ReviewConsentRequirement(
        schema_id="brz2obsidian.review-consent-requirement",
        schema_version=1,
        consent_id="owned-preimages",
        kind="storage",
        requirement="required",
        policy="builtin_transform",
        fingerprint="storage:1",
        disclosure="Owned exact originals",
        subjects=(),
    )
    facts = request(original=b"old", current=b"local", incoming=b"source")
    plan = prepare_review(
        facts, preflight=preflight().model_copy(update={"consents": (consent,)})
    )
    requirement = next(r for r in plan.requirements if r.domain == "storage")
    consented = resolve_review(
        plan,
        action(
            plan,
            domain="storage",
            choice="accept",
            change_id=requirement.change_id,
            reviewed_assumptions=requirement.assumptions,
        ),
    ).plan
    assert not consented.ready and {r.domain for r in consented.requirements} == {
        "text"
    }
    candidate = inspect_text_candidate(
        ExactContent(data=b"reviewed text"),
        identity=ImportedItemIdentity(
            collection_id="folio:collection",
            module_id="synthetic-folio",
            item_id="entry:opening",
        ),
        target=facts.subjects[0].source_target,
        output_format=7,
        source_path="Notes/Opening.md",
        document_id="review:owner",
        path_mode="vault",
        link_targets=(),
        link_target_facts=(),
        link_inventory="complete",
    )
    changed = resolve_review(
        consented,
        action(
            consented,
            decision_id="content:edited",
            choice="edited",
            candidate=candidate,
        ),
    )
    assert changed.status == "accepted" and not changed.plan.ready
    assert {r.domain for r in changed.plan.requirements} == {"storage"}
    reopened = changed.plan.requirements[0]
    assert reopened.assumptions != requirement.assumptions
    stale = resolve_review(
        changed.plan,
        action(
            changed.plan,
            decision_id="storage:stale",
            domain="storage",
            choice="accept",
            change_id=reopened.change_id,
            reviewed_assumptions=requirement.assumptions,
        ),
    )
    assert stale.status == "stale" and stale.plan.consents == consented.consents
    accepted = resolve_review(
        changed.plan,
        action(
            changed.plan,
            decision_id="storage:current",
            domain="storage",
            choice="accept",
            change_id=reopened.change_id,
            reviewed_assumptions=reopened.assumptions,
        ),
    )
    assert accepted.status == "accepted" and accepted.plan.ready


def test_public_saved_plan_validation_reconstructs_whole_plan_readiness():
    from brz2obsidian.core import prepare_review, resolve_review, validate_review

    pending = prepare_review(request(), preflight=preflight())
    forged = pending.model_copy(
        update={"ready": True, "readiness": "ready", "requirements": ()}
    )
    refused = validate_review(forged)
    assert refused.status == "refused" and refused.code == "invalid_plan"
    assert refused.plan == pending and not refused.plan.ready
    reviewed = resolve_review(pending, action(pending)).plan
    accepted = validate_review(reviewed)
    assert (
        accepted.status == "accepted"
        and accepted.plan == reviewed
        and accepted.plan.ready
    )


def test_deleted_configuration_has_explicit_restoration_decline_and_scoped_memory():
    from brz2obsidian.contracts import SourceVersionMemory
    from brz2obsidian.core import prepare_review, resolve_review
    from tests.reconciliation.test_absence import facts_for

    facts = facts_for(existence="absent", incoming=b"new configuration")
    facts = facts.model_copy(
        update={
            "subjects": (
                facts.subjects[0].model_copy(update={"output_role": "configuration"}),
            )
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    assert {r.domain for r in plan.requirements} == {
        "restoration"
    } and plan.groups == ()
    assert plan.requirements[0].choices == ("decline_restoration", "restore_incoming")
    declined = resolve_review(
        plan, action(plan, domain="restoration", choice="decline_restoration")
    )
    assert declined.status == "accepted" and declined.plan.ready
    approval = declined.plan.approvals[0]
    assert approval.result is None and not approval.source_accepted
    memory = SourceVersionMemory.model_validate_json(
        approval.source_memory.model_dump_json()
    )
    assert (
        memory.review_domain == "configuration"
        and memory.choice == "decline_restoration"
    )
    later = facts.model_copy(
        update={
            "proposal_id": "review:later-deletion",
            "generation": 2,
            "source_version_memory": (memory,),
        }
    )
    suppressed = prepare_review(later, preflight=preflight())
    assert (
        suppressed.ready
        and suppressed.proposal.changes[0].disposition == "local_deleted"
    )
    assert (
        suppressed.proposal.changes[0].preservation_review.provenance == "source_memory"
    )
    changed = later.model_copy(
        update={
            "subjects": (
                facts.subjects[0].model_copy(
                    update={
                        "incoming": facts.subjects[0].incoming.model_copy(
                            update={"data": b"newer configuration"}
                        )
                    }
                ),
            )
        }
    )
    reopened = prepare_review(changed, preflight=preflight())
    assert not reopened.ready and {r.domain for r in reopened.requirements} == {
        "restoration"
    }


def test_exact_current_choice_cannot_reinterpret_bound_membership_identity():
    from brz2obsidian.contracts import ExactContent, ImportedItemIdentity
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import inspect_text_candidate
    from tests.reconciliation.test_memberships import membership_request, target

    original = (
        b'---\ncategories:\n  - "[[A]]"\nappearance_category: "[[A]]"\n---\nOriginal.'
    )
    current = original.replace(b"Original.", b"Local.")
    incoming = original.replace(b"Original.", b"Incoming.")
    a = target("a", "category", "[[A]]")
    b = target("b", "category", "[[A]]")
    facts = membership_request(original, current, incoming, targets=(a,))
    assert (
        facts.subjects[0].structure.current.memberships[0].entries[0].target_id == "a"
    )
    plan = prepare_review(facts, preflight=preflight())
    for choice, data in (
        ("current", current),
        ("incoming", incoming),
        ("edited", current),
        ("edited", current.replace(b"Local.", b"Reviewed prose.")),
    ):
        candidate = inspect_text_candidate(
            ExactContent(data=data),
            identity=ImportedItemIdentity(
                collection_id="folio:collection",
                module_id="synthetic-folio",
                item_id="entry:opening",
            ),
            target=facts.subjects[0].source_target,
            output_format=7,
            membership_targets=(b,),
            source_path="Notes/Opening.md",
            document_id="review:owner",
            path_mode="vault",
            link_targets=(b,),
            link_target_facts=candidate_link_states((b,)),
            link_inventory="complete",
        )
        refused = resolve_review(plan, action(plan, choice=choice, candidate=candidate))
        assert refused.status == "refused" and refused.code == "invalid_candidate"
        assert refused.plan.approvals == () and refused.plan.proposal == plan.proposal
    honest = inspect_text_candidate(
        ExactContent(data=current),
        identity=ImportedItemIdentity(
            collection_id="folio:collection",
            module_id="synthetic-folio",
            item_id="entry:opening",
        ),
        target=facts.subjects[0].source_target,
        output_format=7,
        membership_targets=(a,),
        source_path="Notes/Opening.md",
        document_id="review:owner",
        path_mode="vault",
        link_targets=(a,),
        link_target_facts=candidate_link_states((a,)),
        link_inventory="complete",
    )
    assert (
        resolve_review(plan, action(plan, choice="current", candidate=honest)).status
        == "accepted"
    )
    inconsistent = honest.model_copy(
        update={"document": honest.document.model_copy(update={"appearance": "[[B]]"})}
    )
    assert (
        resolve_review(
            plan, action(plan, choice="current", candidate=inconsistent)
        ).status
        == "refused"
    )


def test_incoming_and_edited_choices_cannot_waive_unbound_comparison_facts():
    from brz2obsidian.contracts import ExactContent, ImportedItemIdentity
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import inspect_text_candidate
    from tests.reconciliation.test_structure import structured_request

    original = b"---\nowner: source\n---\nOriginal.\n"
    current = original.replace(b"Original.", b"Local.   ")
    incoming = original.replace(b"Original.", b"Incoming.")
    facts = structured_request(original, current, incoming)
    subject = facts.subjects[0]
    unbound = subject.structure.incoming.model_copy(
        update={
            "content": ExactContent(data=incoming.replace(b"Incoming.", b"Unboundx."))
        }
    )
    facts = facts.model_copy(
        update={
            "subjects": (
                subject.model_copy(
                    update={
                        "structure": subject.structure.model_copy(
                            update={"incoming": unbound}
                        )
                    }
                ),
            )
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    assert (
        plan.proposal.changes[0].provenance.rule == "structure_unbound"
        and not plan.ready
    )
    for choice, data in (("incoming", incoming), ("edited", b"Reviewed whole file.")):
        candidate = inspect_text_candidate(
            ExactContent(data=data),
            identity=ImportedItemIdentity(
                collection_id="folio:collection",
                module_id="synthetic-folio",
                item_id="entry:opening",
            ),
            target=subject.source_target,
            output_format=7,
            source_path="Notes/Opening.md",
            document_id="review:owner",
            path_mode="vault",
            link_targets=(),
            link_target_facts=(),
            link_inventory="complete",
        )
        refused = resolve_review(plan, action(plan, choice=choice, candidate=candidate))
        assert (
            refused.status == "refused"
            and refused.plan.approvals == ()
            and refused.plan.actions == ()
        )
        assert refused.plan.proposal == plan.proposal


def test_edited_mapping_choice_is_limited_to_offered_classification_meaning():
    from brz2obsidian.contracts import (
        ClassificationMapping,
        ExactContent,
        ImportedItemIdentity,
    )
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import (
        align_structure,
        inspect_text_candidate,
        interpret_structure,
    )
    from tests.reconciliation.test_memberships import target

    original = b'---\ncategories:\n  - "[[A]]"\n---\nOriginal.'
    current = original.replace(b"Original.", b"Local.")
    incoming = original.replace(b"Original.", b"Incoming.")
    a, b, c = (target(name, "category", "[[A]]") for name in ("a", "b", "c"))
    docs = tuple(
        interpret_structure(
            ExactContent(data=data), output_format=7, membership_targets=(registry,)
        )
        for data, registry in ((original, a), (current, a), (incoming, b))
    )
    mapping = ClassificationMapping(
        schema_id="brz2obsidian.classification-mapping",
        schema_version=1,
        classification_id="source:a",
        target_id="a",
        kind="category",
        source_label="A",
    )
    comparison = align_structure(
        *docs,
        prior_mappings=(mapping,),
        incoming_mappings=(mapping.model_copy(update={"target_id": "b"}),),
    )
    facts = request(original=original, current=current, incoming=incoming)
    facts = facts.model_copy(
        update={
            "subjects": (
                facts.subjects[0].model_copy(update={"structure": comparison}),
            )
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    assert {r.domain for r in plan.requirements} == {"mapping"}
    for registry, expected in ((b, "accepted"), (c, "refused")):
        candidate = inspect_text_candidate(
            ExactContent(data=current.replace(b"Local.", b"Reviewed.")),
            identity=ImportedItemIdentity(
                collection_id="folio:collection",
                module_id="synthetic-folio",
                item_id="entry:opening",
            ),
            target=facts.subjects[0].source_target,
            output_format=7,
            membership_targets=(registry,),
            source_path="Notes/Opening.md",
            document_id="review:owner",
            path_mode="vault",
            link_targets=(registry,),
            link_target_facts=candidate_link_states((registry,)),
            link_inventory="complete",
        )
        result = resolve_review(
            plan, action(plan, domain="mapping", choice="edited", candidate=candidate)
        )
        assert result.status == expected
        assert result.plan.ready == (expected == "accepted")


def test_edited_text_requires_re_resolved_exact_link_meaning():
    from brz2obsidian.contracts import ExactContent, ImportedItemIdentity
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import inspect_text_candidate

    facts = request(original=b"old", current=b"local", incoming=b"incoming")
    plan = prepare_review(facts, preflight=preflight())
    candidate = inspect_text_candidate(
        ExactContent(data=b"Edited [[Missing]]."),
        identity=ImportedItemIdentity(
            collection_id="folio:collection",
            module_id="synthetic-folio",
            item_id="entry:opening",
        ),
        target=facts.subjects[0].source_target,
        output_format=7,
        source_path="Notes/Opening.md",
        document_id="review:owner",
        path_mode="vault",
        link_targets=(),
        link_target_facts=(),
        link_inventory="complete",
    )
    refused = resolve_review(plan, action(plan, choice="edited", candidate=candidate))
    assert refused.status == "refused" and refused.code == "invalid_candidate"
    assert refused.plan.approvals == () and refused.plan.proposal == plan.proposal


def test_binary_choices_use_exact_offered_outputs_and_never_generic_text_approval():
    from brz2obsidian.core import prepare_review, resolve_review
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        attachment_request,
    )

    facts = attachment_request()
    plan = prepare_review(facts, preflight=preflight())
    assert {r.domain for r in plan.requirements} == {"attachment"} and plan.groups == ()
    assert plan.requirements[0].choices == ("current", "incoming", "both")
    for choice, expected in (
        ("current", (b"\x00authored",)),
        ("incoming", (b"abc",)),
        ("both", (b"\x00authored", b"abc")),
    ):
        selection, candidate = attachment_candidate(facts, choice)
        accepted = resolve_review(
            plan,
            action(
                plan,
                domain="attachment",
                choice=choice,
                attachment_selection=selection,
                attachment_candidate=candidate,
            ),
        )
        assert accepted.status == "accepted" and accepted.plan.ready
        approval = accepted.plan.approvals[0]
        assert (
            tuple(o.content.data for o in approval.attachment_candidate.outputs)
            == expected
        )
        assert approval.source_accepted == (choice != "current")
        if choice == "current":
            assert approval.source_memory.choice == "keep_vault"
        if choice == "both":
            assert approval.result is None
            assert [o.path for o in approval.attachment_candidate.outputs] == [
                "Assets/data.bin",
                "Assets/data (incoming-ba7816bf).bin",
            ]
    selection, candidate = attachment_candidate(facts, "current")
    refused = resolve_review(
        plan,
        action(
            plan,
            domain="attachment",
            choice="incoming",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert refused.status == "refused" and refused.plan.approvals == ()


def test_deleted_binary_restoration_uses_incoming_binary_validation_and_decline_memory():
    from brz2obsidian.contracts import CurrentContent
    from brz2obsidian.core import prepare_review, resolve_review
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        attachment_request,
    )

    facts = attachment_request()
    current = CurrentContent(existence="absent", path="Assets/data.bin", content=None)
    subject = facts.subjects[0].model_copy(update={"current": current})
    state = facts.link_context.current_target_facts[0].model_copy(
        update={
            "existence": "missing",
            "content": None,
            "fragments": (),
            "anchors": (),
            "structure": None,
            "interpretation": "unknown",
        }
    )
    facts = facts.model_copy(
        update={
            "subjects": (subject,),
            "identity_inventory": (
                facts.identity_inventory[0].model_copy(update={"current": current}),
            ),
            "link_context": facts.link_context.model_copy(
                update={"current_target_facts": (state,)}
            ),
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    assert {r.domain for r in plan.requirements} == {"restoration"}
    declined = resolve_review(
        plan, action(plan, domain="restoration", choice="decline_restoration")
    )
    assert declined.status == "accepted" and declined.plan.ready
    assert declined.plan.approvals[0].source_memory.choice == "decline_restoration"
    selection, candidate = attachment_candidate(facts, "incoming")
    restored = resolve_review(
        plan,
        action(
            plan,
            domain="restoration",
            choice="restore_incoming",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert restored.status == "accepted" and restored.plan.ready
    assert restored.plan.approvals[0].result.data == b"abc"
    assert restored.plan.approvals[0].attachment_candidate == candidate


def test_nonordinary_format_choice_can_explicitly_preserve_observed_absence():
    from brz2obsidian.contracts import ContentVersion
    from brz2obsidian.core import prepare_review, resolve_review
    from tests.reconciliation.test_absence import facts_for
    from tests.reconciliation.test_formats import operation

    for kind, role in (("format_transition", "note"), ("onboarding", "configuration")):
        facts = facts_for(existence="absent", incoming=b"changed")
        subject = facts.subjects[0].model_copy(update={"output_role": role})
        facts = facts.model_copy(update={"subjects": (subject,)})
        ordinary = prepare_review(facts, preflight=preflight())
        declined = resolve_review(
            ordinary,
            action(ordinary, domain="restoration", choice="decline_restoration"),
        )
        memory = declined.plan.approvals[0].source_memory
        updates = {
            "format_operation": operation(kind),
            "source_version_memory": (memory,),
        }
        if kind == "onboarding":
            subject = subject.model_copy(
                update={
                    "baseline": ContentVersion(
                        status="unknown",
                        content=None,
                        unavailable_digest="old:unavailable",
                    )
                }
            )
            updates |= {
                "subjects": (subject,),
                "baseline_identity": facts.baseline_identity.model_copy(
                    update={"output_format": 6}
                ),
                "format_operation": operation(
                    kind, recorded_generation="unavailable", established_baseline=None
                ),
            }
        facts = facts.model_copy(update=updates)
        plan = prepare_review(facts, preflight=preflight())
        domain = "configuration" if role == "configuration" else "format"
        assert not plan.ready and {r.domain for r in plan.requirements} == {domain}
        assert "current" in plan.requirements[0].choices
        kept = resolve_review(
            plan,
            action(plan, domain=domain, choice="current", decision_id="format:" + kind),
        )
        assert kept.status == "accepted" and kept.plan.ready
        approval = kept.plan.approvals[0]
        assert (
            approval.result is None
            and not approval.source_accepted
            and approval.source_memory is None
        )
        assert kept.plan.proposal.changes[0].disposition == "unresolved"
        assert not prepare_review(facts, preflight=preflight()).ready


def linked_note_request(*, incoming_path="Notes/Opening.md"):
    from brz2obsidian.contracts import ExactContent, LinkContext
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_attachments import target_for_links
    from tests.reconciliation.test_identity import inventory_item

    facts = request(
        original=b"Old [[Guide]].",
        current=b"Old [[Guide]].",
        incoming=b"New [[Guide]].",
    )
    target = target_for_links("guide", "Docs/Guide.md", aliases=("Guide",))
    state = interpret_link_target(
        ExactContent(data=b"Guide body."),
        target_id="guide",
        existence="present",
        memberships=(),
    )

    def document(content, path):
        return interpret_links(
            content,
            document_id="opening",
            source_path=path,
            path_mode="vault",
            targets=(target,),
            target_facts=(state,),
            inventory="complete",
        )

    context = LinkContext(
        schema_id="brz2obsidian.link-context",
        schema_version=1,
        inventory="complete",
        current_targets=(target,),
        incoming_targets=(target,),
        current_target_facts=(state,),
        incoming_target_facts=(state,),
        current_documents=(
            document(facts.subjects[0].current.content, "Notes/Opening.md"),
        ),
        incoming_documents=(document(facts.subjects[0].incoming, incoming_path),),
    )
    return facts.model_copy(
        update={
            "link_context": context,
            "identity_inventory": facts.identity_inventory
            + (inventory_item("guide", "guide", "Docs/Guide.md", b"Guide body."),),
        }
    )


def test_compatible_approval_requires_result_link_facts_at_selected_path():
    from brz2obsidian.core import prepare_review, resolve_review

    facts = linked_note_request(incoming_path="Source/Opening.md")
    plan = prepare_review(facts, preflight=preflight())
    assert plan.proposal.changes[0].result.data == b"New [[Guide]]."
    assert plan.groups == () and "approve" not in plan.requirements[0].choices
    refused = resolve_review(plan, action(plan))
    assert refused.status == "refused" and refused.plan.approvals == ()
    bound = prepare_review(linked_note_request(), preflight=preflight())
    accepted = resolve_review(bound, action(bound))
    assert accepted.status == "accepted" and accepted.plan.ready


def test_note_link_assumptions_bind_lookup_competitors_but_not_unrelated_files():
    from brz2obsidian.core import prepare_review
    from tests.reconciliation.test_attachments import target_for_links

    facts = linked_note_request()
    original = prepare_review(facts, preflight=preflight()).proposal.changes[0]
    for aliases, changed in ((("Other",), False), (("Guide",), True)):
        competitor = target_for_links("competitor", "Other/Second.md", aliases=aliases)
        context = facts.link_context.model_copy(
            update={
                "incoming_targets": facts.link_context.incoming_targets + (competitor,)
            }
        )
        updated = prepare_review(
            facts.model_copy(update={"link_context": context}), preflight=preflight()
        ).proposal.changes[0]
        assert (updated.change_id != original.change_id) == changed
        if changed:
            assert any(a.key.startswith("text-links:") for a in updated.assumptions)


def note_and_attachment_request():
    from brz2obsidian.contracts import IdentityTargetFacts
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_attachments import linked_attachment_request
    from tests.reconciliation.test_identity import with_subjects

    raw = b"Old prose [[Assets/data.bin]]."
    facts = linked_attachment_request(raw=raw)
    note = request(
        original=raw, current=raw, incoming=b"New prose [[Assets/data.bin]]."
    ).subjects[0]
    note = note.model_copy(
        update={
            "path": "Notes/Owner.md",
            "current": note.current.model_copy(update={"path": "Notes/Owner.md"}),
            "source_target": IdentityTargetFacts(
                normalized_path="notes/owner.md", containment="contained", status="safe"
            ),
        }
    )
    facts = with_subjects(facts, (note, facts.subjects[0]), facts.identity_inventory)
    context = facts.link_context
    new_doc = interpret_links(
        note.incoming,
        document_id="owner:note",
        source_path="Notes/Owner.md",
        path_mode="vault",
        targets=context.incoming_targets,
        target_facts=context.incoming_target_facts,
        inventory="complete",
    )
    new_state = interpret_link_target(
        note.incoming, target_id="owner:note", existence="present", memberships=()
    )
    return facts.model_copy(
        update={
            "link_context": context.model_copy(
                update={
                    "incoming_documents": (new_doc,),
                    "incoming_target_facts": tuple(
                        new_state if s.target_id == "owner:note" else s
                        for s in context.incoming_target_facts
                    ),
                }
            )
        }
    )


def test_selected_binary_version_and_text_meaning_must_agree_without_competing_proof_writes():
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import inspect_text_candidate
    from tests.reconciliation.test_attachments import attachment_candidate

    facts = note_and_attachment_request()
    plan = prepare_review(facts, preflight=preflight())
    note, binary = plan.proposal.changes
    selection, binary_candidate = attachment_candidate(facts, "current")
    binary_kept = resolve_review(
        plan,
        action(
            plan,
            binary,
            domain="attachment",
            choice="current",
            decision_id="binary:keep",
            attachment_selection=selection,
            attachment_candidate=binary_candidate,
        ),
    ).plan
    for states, ready in (
        (facts.link_context.incoming_target_facts, False),
        (facts.link_context.current_target_facts, True),
    ):
        candidate = inspect_text_candidate(
            facts.subjects[0].incoming,
            identity=facts.identity_inventory[1].identity,
            target=facts.subjects[0].source_target,
            output_format=7,
            source_path="Notes/Owner.md",
            document_id="owner:note",
            path_mode="vault",
            link_targets=facts.link_context.current_targets,
            link_target_facts=states,
            link_inventory="complete",
        )
        selected = resolve_review(
            binary_kept,
            action(
                binary_kept,
                note,
                choice="incoming",
                decision_id="note:incoming",
                candidate=candidate,
            ),
        )
        assert selected.status == "accepted"
        assert selected.plan.ready == ready
        if not ready:
            assert "selected_link_context_conflict" in selected.plan.blockers
        else:
            assert (
                selected.plan.approvals[-1].result.data
                == b"New prose [[Assets/data.bin]]."
            )
            assert (
                binary_candidate.documents[0].content.data
                == b"Old prose [[Assets/data.bin]]."
            )


def test_old_bulk_token_cannot_authorize_rebound_effective_path_link_context():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    facts = linked_note_request()
    subject = facts.subjects[0]
    facts = facts.model_copy(
        update={
            "subjects": (
                subject.model_copy(
                    update={
                        "path": "Source/Opening.md",
                        "source_target": subject.source_target.model_copy(
                            update={"normalized_path": "source/opening.md"}
                        ),
                    }
                ),
            )
        }
    )
    old = prepare_review(facts, preflight=preflight())
    group = old.groups[0]
    token = action(
        old,
        domain="compatible_group",
        change_id=group.group_id,
        reviewed_assumptions=group.assumptions,
    )
    state = interpret_link_target(
        ExactContent(data=b"Changed incoming guide body."),
        target_id="guide",
        existence="present",
        memberships=(),
    )
    document = interpret_links(
        subject.incoming,
        document_id="opening",
        source_path="Notes/Opening.md",
        path_mode="vault",
        targets=facts.link_context.incoming_targets,
        target_facts=(state,),
        inventory="complete",
    )
    rebound = facts.model_copy(
        update={
            "link_context": facts.link_context.model_copy(
                update={
                    "incoming_target_facts": (state,),
                    "incoming_documents": (document,),
                }
            )
        }
    )
    fresh = prepare_review(rebound, preflight=preflight())
    assert fresh.proposal.changes[0].change_id != old.proposal.changes[0].change_id
    refused = resolve_review(fresh, token)
    assert refused.status in ("stale", "refused") and refused.plan.approvals == ()


def redirected_attachment_choice(facts):
    from brz2obsidian.contracts import ExactContent, LinkOccurrenceChoice
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_attachments import attachment_candidate

    selection, candidate = attachment_candidate(facts, "both")
    old = facts.link_context.current_documents[0]
    replacement = b"[[Assets/data (incoming-ba7816bf).bin]]"
    content = ExactContent(
        data=old.content.data.replace(b"[[Assets/data.bin]]", replacement)
    )
    document = interpret_links(
        content,
        document_id=old.document_id,
        source_path=old.source_path,
        path_mode="vault",
        targets=candidate.targets,
        target_facts=candidate.target_facts,
        inventory="complete",
    )
    choice = LinkOccurrenceChoice(
        document_id=old.document_id,
        occurrence_id=old.occurrences[0].occurrence_id,
        old=old.occurrences[0].meaning,
        replacement=replacement,
        selected=document.occurrences[0].meaning,
        expected_memberships=(),
        provenance="explicit_user",
    )
    state = interpret_link_target(
        content, target_id="owner:note", existence="present", memberships=()
    )
    return selection.model_copy(
        update={"link_choices": (choice,)}
    ), candidate.model_copy(
        update={
            "documents": (document,),
            "target_facts": tuple(
                state if s.target_id == "owner:note" else s
                for s in candidate.target_facts
            ),
        }
    )


def test_storage_consent_binds_both_outputs_and_explicit_link_edits_even_without_single_result():
    from brz2obsidian.contracts import ReviewConsentRequirement
    from brz2obsidian.core import prepare_review, resolve_review
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        linked_attachment_request,
    )

    facts = linked_attachment_request(raw=b"Old prose [[Assets/data.bin]].")
    consent = ReviewConsentRequirement(
        schema_id="brz2obsidian.review-consent-requirement",
        schema_version=1,
        consent_id="storage",
        kind="storage",
        requirement="required",
        policy="ordinary",
        fingerprint="storage:1",
        disclosure="Store exact selected files.",
        subjects=(),
    )
    plan = prepare_review(
        facts, preflight=preflight().model_copy(update={"consents": (consent,)})
    )
    selection, candidate = attachment_candidate(facts, "both")
    chosen = resolve_review(
        plan,
        action(
            plan,
            domain="attachment",
            choice="both",
            decision_id="both:plain",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    ).plan
    requirement = next(r for r in chosen.requirements if r.domain == "storage")
    consented = resolve_review(
        chosen,
        action(
            chosen,
            domain="storage",
            choice="accept",
            decision_id="storage:plain",
            change_id=requirement.change_id,
            reviewed_assumptions=requirement.assumptions,
        ),
    ).plan
    assert consented.ready and consented.approvals[0].result is None
    selection, redirected = redirected_attachment_choice(facts)
    changed = resolve_review(
        consented,
        action(
            consented,
            domain="attachment",
            choice="both",
            decision_id="both:redirect",
            attachment_selection=selection,
            attachment_candidate=redirected,
        ),
    )
    assert changed.status == "accepted" and changed.plan.approvals[0].result is None
    assert not changed.plan.ready and {r.domain for r in changed.plan.requirements} == {
        "storage"
    }
    current = changed.plan.requirements[0]
    assert current.assumptions != requirement.assumptions
    stale = resolve_review(
        changed.plan,
        action(
            changed.plan,
            domain="storage",
            choice="accept",
            decision_id="storage:old-token",
            change_id=requirement.change_id,
            reviewed_assumptions=requirement.assumptions,
        ),
    )
    assert stale.status == "stale"


def test_changed_associated_document_is_a_write_and_cannot_compete_with_text_choice():
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import inspect_text_candidate

    facts = note_and_attachment_request()
    plan = prepare_review(facts, preflight=preflight())
    note, binary = plan.proposal.changes
    selection, candidate = redirected_attachment_choice(facts)
    redirected = resolve_review(
        plan,
        action(
            plan,
            binary,
            domain="attachment",
            choice="both",
            decision_id="binary:redirect",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    ).plan
    text = inspect_text_candidate(
        facts.subjects[0].incoming,
        identity=facts.identity_inventory[1].identity,
        target=facts.subjects[0].source_target,
        output_format=7,
        source_path="Notes/Owner.md",
        document_id="owner:note",
        path_mode="vault",
        link_targets=candidate.targets,
        link_target_facts=candidate.target_facts,
        link_inventory="complete",
    )
    conflict = resolve_review(
        redirected,
        action(
            redirected,
            note,
            choice="incoming",
            decision_id="note:competing",
            candidate=text,
        ),
    )
    assert conflict.status == "accepted" and not conflict.plan.ready
    assert "selected_output_conflict" in conflict.plan.blockers
    assert (
        conflict.plan.approvals[0].attachment_candidate.documents[0].content.data
        == b"Old prose [[Assets/data (incoming-ba7816bf).bin]]."
    )
    assert conflict.plan.approvals[1].result.data == b"New prose [[Assets/data.bin]]."


def test_explicit_note_rename_revalidates_existing_backlinks_against_actual_target_path():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_attachments import target_for_links
    from tests.reconciliation.test_identity import inventory_item

    facts = linked_note_request()
    subject = facts.subjects[0]
    subject = subject.model_copy(
        update={
            "path": "Source/Opening.md",
            "source_target": subject.source_target.model_copy(
                update={"normalized_path": "source/opening.md"}
            ),
        }
    )
    own = target_for_links("opening", "Notes/Opening.md")
    new_own = target_for_links("opening", "Source/Opening.md")
    context = facts.link_context
    old_state = interpret_link_target(
        subject.current.content,
        target_id="opening",
        existence="present",
        memberships=(),
    )
    new_state = interpret_link_target(
        subject.incoming, target_id="opening", existence="present", memberships=()
    )
    old_targets = context.current_targets + (own,)
    new_targets = context.incoming_targets + (new_own,)
    old_states = context.current_target_facts + (old_state,)
    new_states = context.incoming_target_facts + (new_state,)
    backlink = interpret_links(
        ExactContent(data=b"Keep [[Notes/Opening]]."),
        document_id="backlink",
        source_path="Docs/Backlink.md",
        path_mode="vault",
        targets=old_targets,
        target_facts=old_states,
        inventory="complete",
    )
    incoming = interpret_links(
        subject.incoming,
        document_id="opening",
        source_path="Source/Opening.md",
        path_mode="vault",
        targets=new_targets,
        target_facts=new_states,
        inventory="complete",
    )
    facts = facts.model_copy(
        update={
            "subjects": (subject,),
            "link_context": context.model_copy(
                update={
                    "current_targets": old_targets,
                    "incoming_targets": new_targets,
                    "current_target_facts": old_states,
                    "incoming_target_facts": new_states,
                    "current_documents": context.current_documents + (backlink,),
                    "incoming_documents": (incoming,),
                }
            ),
        }
    )
    facts = facts.model_copy(
        update={
            "identity_inventory": facts.identity_inventory
            + (
                inventory_item(
                    "backlink",
                    "backlink",
                    "Docs/Backlink.md",
                    b"Keep [[Notes/Opening]].",
                ),
            )
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    renamed = resolve_review(
        plan,
        action(
            plan, domain="rename", choice="source_path", decision_id="rename:source"
        ),
    ).plan
    selected = resolve_review(renamed, action(renamed, decision_id="content:renamed"))
    assert selected.status == "accepted" and not selected.plan.ready
    assert selected.plan.approvals[0].target_path == "Source/Opening.md"
    assert "selected_link_context_conflict" in selected.plan.blockers
    assert (
        selected.plan.facts.link_context.current_documents[-1].content.data
        == b"Keep [[Notes/Opening]]."
    )

    hidden = interpret_links(
        ExactContent(data=b"Keep authored prose."),
        document_id="backlink",
        source_path="Docs/Backlink.md",
        path_mode="vault",
        targets=old_targets,
        target_facts=old_states,
        inventory="complete",
    )
    hidden_state = interpret_link_target(
        hidden.content, target_id="backlink", existence="present", memberships=()
    )
    actual_entry = next(
        e for e in facts.identity_inventory if e.current.path == "Docs/Backlink.md"
    )
    updated_entry = actual_entry.model_copy(
        update={
            "current": actual_entry.current.model_copy(
                update={"content": hidden.content}
            )
        }
    )
    removed_link = facts.model_copy(
        update={
            "identity_inventory": tuple(
                updated_entry if e.entry_id == actual_entry.entry_id else e
                for e in facts.identity_inventory
            ),
            "link_context": facts.link_context.model_copy(
                update={
                    "current_documents": (
                        facts.link_context.current_documents[0],
                        hidden,
                    )
                }
            ),
        }
    )
    rebound = prepare_review(removed_link, preflight=preflight())
    assert (
        rebound.proposal.changes[0].rename_review.assumptions
        != plan.proposal.changes[0].rename_review.assumptions
    )
    old_token = action(
        plan, domain="rename", choice="source_path", decision_id="rename:old-context"
    )
    assert resolve_review(rebound, old_token).status in ("stale", "refused")
    prose = interpret_links(
        ExactContent(data=b"New authored prose [[Notes/Opening]]."),
        document_id="backlink",
        source_path="Docs/Backlink.md",
        path_mode="vault",
        targets=old_targets,
        target_facts=old_states,
        inventory="complete",
    )
    prose_entry = actual_entry.model_copy(
        update={
            "current": actual_entry.current.model_copy(
                update={"content": prose.content}
            )
        }
    )
    same_meaning = facts.model_copy(
        update={
            "identity_inventory": tuple(
                prose_entry if e.entry_id == actual_entry.entry_id else e
                for e in facts.identity_inventory
            ),
            "link_context": facts.link_context.model_copy(
                update={
                    "current_documents": (
                        facts.link_context.current_documents[0],
                        prose,
                    )
                }
            ),
        }
    )
    unchanged = prepare_review(same_meaning, preflight=preflight())
    assert (
        unchanged.proposal.changes[0].rename_review.assumptions
        == plan.proposal.changes[0].rename_review.assumptions
    )

    forged = facts.model_copy(
        update={
            "link_context": facts.link_context.model_copy(
                update={
                    "current_documents": (
                        facts.link_context.current_documents[0],
                        hidden,
                    ),
                    "current_target_facts": facts.link_context.current_target_facts
                    + (hidden_state,),
                }
            )
        }
    )
    forged_plan = prepare_review(forged, preflight=preflight())
    renamed = resolve_review(
        forged_plan,
        action(
            forged_plan,
            domain="rename",
            choice="source_path",
            decision_id="rename:forged",
        ),
    ).plan
    selected = resolve_review(renamed, action(renamed, decision_id="content:forged"))
    assert not selected.plan.ready
    assert "current_link_context_unbound" in selected.plan.blockers


def test_remembered_text_keep_revalidates_affected_current_link_safety():
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import interpret_links

    facts = linked_note_request()
    plan = prepare_review(facts, preflight=preflight())
    kept = resolve_review(plan, action(plan, choice="current")).plan
    memory = kept.approvals[0].source_memory
    repeated = facts.model_copy(update={"source_version_memory": (memory,)})
    assert prepare_review(repeated, preflight=preflight()).ready
    context = facts.link_context
    unsafe = context.current_targets[0].model_copy(
        update={
            "status": "unsafe",
            "target": context.current_targets[0].target.model_copy(
                update={"containment": "outside"}
            ),
        }
    )
    document = interpret_links(
        facts.subjects[0].current.content,
        document_id="opening",
        source_path="Notes/Opening.md",
        path_mode="vault",
        targets=(unsafe,),
        target_facts=context.current_target_facts,
        inventory="complete",
    )
    changed = repeated.model_copy(
        update={
            "link_context": context.model_copy(
                update={"current_targets": (unsafe,), "current_documents": (document,)}
            )
        }
    )
    refused = prepare_review(changed, preflight=preflight())
    assert not refused.ready and "selected_link_context_conflict" in refused.blockers
    fresh = prepare_review(
        changed.model_copy(update={"source_version_memory": ()}), preflight=preflight()
    )
    unsafe_choice = resolve_review(
        fresh, action(fresh, choice="current", decision_id="current:unsafe")
    )
    assert unsafe_choice.status == "refused" and unsafe_choice.plan.approvals == ()


def test_complete_inventory_proves_gap_or_intentional_absence_without_inventing_intent():
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import interpret_link_target, interpret_links

    facts = linked_note_request()
    context = facts.link_context
    for existence in ("known_source_gap", "intentionally_uncreated"):
        state = interpret_link_target(
            None, target_id="guide", existence=existence, memberships=()
        )
        docs = tuple(
            interpret_links(
                content,
                document_id="opening",
                source_path="Notes/Opening.md",
                path_mode="vault",
                targets=context.current_targets,
                target_facts=(state,),
                inventory="complete",
            )
            for content in (
                facts.subjects[0].current.content,
                facts.subjects[0].incoming,
            )
        )
        missing = facts.model_copy(
            update={
                "identity_inventory": facts.identity_inventory[:1],
                "link_context": context.model_copy(
                    update={
                        "current_target_facts": (state,),
                        "incoming_target_facts": (state,),
                        "current_documents": (docs[0],),
                        "incoming_documents": (docs[1],),
                    }
                ),
            }
        )
        plan = prepare_review(missing, preflight=preflight())
        accepted = resolve_review(plan, action(plan))
        assert accepted.status == "accepted" and accepted.plan.ready
        false_absence = missing.model_copy(
            update={"identity_inventory": facts.identity_inventory}
        )
        refused = prepare_review(false_absence, preflight=preflight())
        assert not refused.ready and "current_link_context_unbound" in refused.blockers
