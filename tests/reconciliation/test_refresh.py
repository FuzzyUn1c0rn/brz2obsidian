"""Literal selective refresh at the public review/history boundary."""

import pytest

from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links


def two_items():
    facts = request()
    first = facts.subjects[0]
    second = first.model_copy(
        update={
            "item_id": "entry:second",
            "path": "Notes/Second.md",
            "title": "Second",
            "current": first.current.model_copy(update={"path": "Notes/Second.md"}),
            "source_target": first.source_target.model_copy(
                update={"normalized_path": "notes/second.md"}
            ),
        }
    )
    entry = facts.identity_inventory[0]
    second_entry = entry.model_copy(
        update={
            "entry_id": "second-entry",
            "identity": entry.identity.model_copy(update={"item_id": second.item_id}),
            "current": second.current,
            "target": second.source_target,
        }
    )
    baseline = facts.format_operation.established_baseline
    outputs = baseline.outputs + (
        baseline.outputs[0].model_copy(update={"item_id": second.item_id}),
    )
    operation = facts.format_operation.model_copy(
        update={
            "established_baseline": baseline.model_copy(update={"outputs": outputs})
        }
    )
    return facts.model_copy(
        update={
            "subjects": (first, second),
            "identity_inventory": (entry, second_entry),
            "format_operation": operation,
        }
    )


def edit_first(facts):
    from brz2obsidian.contracts import ExactContent

    current = facts.subjects[0].current.model_copy(
        update={"content": ExactContent(data=b"Authored after review")}
    )
    return with_review_links(
        facts.model_copy(
            update={
                "generation": facts.generation + 1,
                "link_context": None,
                "subjects": (
                    facts.subjects[0].model_copy(update={"current": current}),
                    facts.subjects[1],
                ),
                "identity_inventory": (
                    facts.identity_inventory[0].model_copy(update={"current": current}),
                    facts.identity_inventory[1],
                ),
            }
        )
    )


def test_refresh_invalidates_only_changed_item_and_preserves_original_consent():
    from brz2obsidian.core import (
        prepare_review,
        refresh_review,
        resolve_review,
        validate_review,
    )

    facts = with_review_links(two_items())
    plan = prepare_review(facts, preflight=preflight())
    for change in plan.proposal.changes:
        plan = resolve_review(
            plan, action(plan, change, decision_id=change.item_id)
        ).plan
    assert plan.ready
    original = plan.approvals[1]
    old_token = action(plan, plan.proposal.changes[1], decision_id="old:token")
    refreshed = refresh_review(plan, edit_first(facts), preflight=preflight())
    assert refreshed.status == "accepted"
    assert refreshed.plan.proposal.generation == 2
    assert [a.decision_id for a in refreshed.plan.approvals] == ["entry:second"]
    assert refreshed.plan.approvals[0] == original
    assert not refreshed.plan.ready
    assert [r.domain for r in refreshed.plan.requirements] == ["text"]
    assert resolve_review(refreshed.plan, old_token).code == "generation_changed"
    assert validate_review(refreshed.plan).status == "accepted"
    again = refresh_review(
        refreshed.plan, edit_first(edit_first(facts)), preflight=preflight()
    )
    assert again.plan.proposal.generation == 3
    assert again.plan.approvals == (original,)
    assert validate_review(again.plan).status == "accepted"
    resolved = resolve_review(
        again.plan,
        action(again.plan, choice="current", decision_id="fresh:third-epoch"),
    )
    assert resolved.status == "accepted" and resolved.plan.ready
    assert resolved.plan.approvals[-1].result.data == b"Authored after review"
    assert resolved.plan.history.events[-1].expected_generation == 3
    assert validate_review(resolved.plan).status == "accepted"


def test_release_metadata_retains_bulk_members_without_changing_original_group_consent():
    from brz2obsidian.core import (
        prepare_review,
        refresh_review,
        resolve_review,
        validate_review,
    )

    facts = with_review_links(two_items())
    plan = prepare_review(facts, preflight=preflight())
    group = plan.groups[0]
    token = action(
        plan,
        change_id=group.group_id,
        domain="compatible_group",
        reviewed_assumptions=group.assumptions,
    )
    approved = resolve_review(plan, token).plan
    assert len(approved.approvals) == 2
    changed = edit_first(facts)
    refreshed = refresh_review(approved, changed, preflight=preflight()).plan
    assert len(refreshed.approvals) == 1
    assert refreshed.approvals[0] == approved.approvals[1]
    assert refreshed.approvals[0].provenance == "compatible_bulk"
    release = facts.model_copy(
        update={
            "generation": 2,
            "incoming_identity": facts.incoming_identity.model_copy(
                update={"module_version": "new-release"}
            ),
            "baseline_identity": facts.baseline_identity.model_copy(
                update={"module_version": "new-release"}
            ),
        }
    )
    equivalent = refresh_review(approved, release, preflight=preflight()).plan
    assert equivalent.ready
    assert equivalent.approvals == approved.approvals
    assert equivalent.proposal.changes[0].format_review is None
    assert validate_review(equivalent).status == "accepted"


def test_history_normalizes_accepted_action_and_rejects_forged_retention():
    from brz2obsidian.contracts import ReviewAction
    from brz2obsidian.core import (
        prepare_review,
        refresh_review,
        resolve_review,
        validate_review,
    )

    facts = with_review_links(request())
    plan = prepare_review(facts, preflight=preflight())
    token = action(plan)
    mapping = token.model_dump()
    accepted = resolve_review(plan, mapping).plan
    mapping["decision_id"] = "mutated-caller"
    assert accepted.history.events[0].decision_id == token.decision_id
    assert isinstance(accepted.history.events[0], ReviewAction)
    assert validate_review(accepted).status == "accepted"
    refreshed = refresh_review(
        accepted, facts.model_copy(update={"generation": 2}), preflight=preflight()
    ).plan
    event = refreshed.history.events[-1]
    forged = event.retained[0].model_copy(update={"origin_generation": 2})
    bad = refreshed.model_copy(
        update={
            "history": refreshed.history.model_copy(
                update={
                    "events": refreshed.history.events[:-1]
                    + (event.model_copy(update={"retained": (forged,)}),)
                }
            )
        }
    )
    assert validate_review(bad).status == "refused"


def test_edited_candidate_and_scoped_storage_consent_retain_their_own_evidence():
    from brz2obsidian.contracts import (
        ExactContent,
        ImportedItemIdentity,
        ReviewConsentRequirement,
    )
    from brz2obsidian.core import (
        prepare_review,
        refresh_review,
        resolve_review,
        validate_review,
    )
    from brz2obsidian.obsidian import inspect_text_candidate

    facts = with_review_links(two_items())
    plan = prepare_review(facts, preflight=preflight())
    subject = plan.proposal.changes[1]
    consent = ReviewConsentRequirement(
        schema_id="brz2obsidian.review-consent-requirement",
        schema_version=1,
        consent_id="second-storage",
        kind="storage",
        requirement="required",
        policy="ordinary",
        fingerprint="storage-policy",
        disclosure="Second only",
        subjects=(subject.subject_id,),
    )
    checks = preflight().model_copy(update={"consents": (consent,)})
    plan = prepare_review(facts, preflight=checks)
    candidate = inspect_text_candidate(
        ExactContent(data=b"Personal synthesis"),
        identity=ImportedItemIdentity(
            collection_id="folio:collection",
            module_id="synthetic-folio",
            item_id="entry:second",
        ),
        target=facts.subjects[1].source_target,
        output_format=7,
        source_path="Notes/Second.md",
        document_id="review:second-entry",
        path_mode="vault",
        link_targets=(),
        link_target_facts=(),
        link_inventory="complete",
    )
    plan = resolve_review(
        plan,
        action(
            plan,
            plan.proposal.changes[1],
            choice="edited",
            candidate=candidate,
            decision_id="edited:second",
        ),
    ).plan
    assert plan.approvals[0].result.data == b"Personal synthesis"
    requirement = next(r for r in plan.requirements if r.domain == "storage")
    plan = resolve_review(
        plan,
        action(
            plan,
            domain="storage",
            choice="accept",
            candidate=None,
            change_id=requirement.change_id,
            reviewed_assumptions=requirement.assumptions,
            decision_id="consent:second",
        ),
    ).plan
    refreshed = refresh_review(plan, edit_first(facts), preflight=checks).plan
    assert refreshed.approvals == plan.approvals
    assert refreshed.consents == plan.consents
    assert {r.domain for r in refreshed.requirements} == {"text"}
    event = refreshed.history.events[-1]
    assert "review-candidate:edited:second" in {n.key for n in event.dependencies}
    assert "consent:second-storage" in {n.key for n in event.dependencies}
    assert validate_review(refreshed).status == "accepted"


def test_unused_mapping_remap_does_not_change_subject_policy_or_approval():
    from brz2obsidian.contracts import ClassificationMapping
    from brz2obsidian.core import prepare_review, refresh_review, resolve_review
    from tests.reconciliation.test_structure import structured_request

    facts = structured_request(b"priority: 1\n", b"priority: 1\n", b"priority: 2\n")
    mapping = ClassificationMapping(
        schema_id="brz2obsidian.classification-mapping",
        schema_version=1,
        classification_id="unrelated-classification",
        target_id="a",
        kind="category",
        source_label="Display",
    )
    subject = facts.subjects[0]
    comparison = subject.structure.model_copy(
        update={"prior_mappings": (mapping,), "incoming_mappings": (mapping,)}
    )
    facts = with_review_links(
        facts.model_copy(
            update={"subjects": (subject.model_copy(update={"structure": comparison}),)}
        )
    )
    plan = prepare_review(facts, preflight=preflight())
    plan = resolve_review(plan, action(plan)).plan
    assert plan.ready
    changed = comparison.model_copy(
        update={"incoming_mappings": (mapping.model_copy(update={"target_id": "b"}),)}
    )
    fresh = facts.model_copy(
        update={
            "generation": 2,
            "subjects": (subject.model_copy(update={"structure": changed}),),
        }
    )
    result = refresh_review(plan, fresh, preflight=preflight())
    assert result.plan.ready
    assert result.plan.approvals == plan.approvals
    assert (
        result.plan.proposal.changes[0].provenance.rule
        == plan.proposal.changes[0].provenance.rule
    )


def test_source_target_link_and_storage_closure_preserves_independent_third_item():
    from brz2obsidian.contracts import ExactContent, ReviewConsentRequirement
    from brz2obsidian.core import prepare_review, refresh_review, resolve_review
    from tests.reconciliation.test_identity import with_subjects

    facts = two_items()
    first, second = facts.subjects
    second = second.model_copy(
        update={"incoming": ExactContent(data=b"[[Notes/Opening.md]]")}
    )
    third = first.model_copy(
        update={
            "item_id": "entry:third",
            "path": "Notes/Third.md",
            "current": first.current.model_copy(update={"path": "Notes/Third.md"}),
            "source_target": first.source_target.model_copy(
                update={"normalized_path": "notes/third.md"}
            ),
        }
    )
    entry = facts.identity_inventory[0]
    extra = entry.model_copy(
        update={
            "entry_id": "third-entry",
            "identity": entry.identity.model_copy(update={"item_id": third.item_id}),
            "current": third.current,
            "target": third.source_target,
        }
    )
    facts = with_review_links(
        with_subjects(
            facts, (first, second, third), facts.identity_inventory + (extra,)
        )
    )
    plan = prepare_review(facts, preflight=preflight())
    ids = {c.item_id: c.subject_id for c in plan.proposal.changes}
    consent = ReviewConsentRequirement(
        schema_id="brz2obsidian.review-consent-requirement",
        schema_version=1,
        consent_id="linked-storage",
        kind="storage",
        requirement="required",
        policy="ordinary",
        fingerprint="policy",
        disclosure="Linked item",
        subjects=(ids[second.item_id],),
    )
    checks = preflight().model_copy(update={"consents": (consent,)})
    plan = prepare_review(facts, preflight=checks)
    for change in plan.proposal.changes:
        transition = resolve_review(
            plan, action(plan, change, decision_id=change.item_id)
        )
        assert transition.status == "accepted"
        plan = transition.plan
    row = next(r for r in plan.requirements if r.domain == "storage")
    plan = resolve_review(
        plan,
        action(
            plan,
            change_id=row.change_id,
            reviewed_assumptions=row.assumptions,
            domain="storage",
            choice="accept",
            decision_id="linked:consent",
        ),
    ).plan
    assert plan.ready
    changed = facts.model_copy(
        update={
            "generation": 2,
            "link_context": None,
            "subjects": (
                first.model_copy(
                    update={"incoming": ExactContent(data=b"Changed target source")}
                ),
                second,
                third,
            ),
        }
    )
    changed = with_review_links(changed)
    transition = refresh_review(plan, changed, preflight=checks)
    assert transition.status == "accepted"
    assert [a.decision_id for a in transition.plan.approvals] == ["entry:third"]
    assert transition.plan.consents == ()
    event = transition.plan.history.events[-1]
    nodes = {n.key: n for n in event.previous_dependencies}
    assert (
        "selected:" + ids[first.item_id]
        in nodes["effect:" + ids[second.item_id]].depends_on
    )
    assert "effect:" + ids[second.item_id] in nodes["consent:linked-storage"].depends_on
    assert {
        "selected:" + ids[first.item_id],
        "effect:" + ids[second.item_id],
        "consent:linked-storage",
    } <= set(event.invalidated_keys)
    assert "effect:" + ids[third.item_id] not in event.invalidated_keys
    assert not transition.plan.ready


def test_used_mapping_and_target_provenance_are_explicit_graph_edges():
    from brz2obsidian.contracts import ClassificationMapping
    from brz2obsidian.core import prepare_review, refresh_review, resolve_review
    from tests.reconciliation.test_memberships import membership_request, target

    original = b"---\ntags:\n  - alpha\npriority: 1\n---\nText.\n"
    incoming = original.replace(b"priority: 1", b"priority: 2")
    mapping = ClassificationMapping(
        schema_id="brz2obsidian.classification-mapping",
        schema_version=1,
        classification_id="source:alpha",
        target_id="alpha",
        kind="tag",
        source_label="Alpha",
    )
    facts = with_review_links(
        membership_request(
            original,
            original,
            incoming,
            targets=(target("alpha", "tag", "alpha"),),
            prior_mappings=(mapping,),
            incoming_mappings=(mapping,),
        )
    )
    plan = prepare_review(facts, preflight=preflight())
    plan = resolve_review(plan, action(plan)).plan
    assert plan.ready
    result = refresh_review(
        plan, facts.model_copy(update={"generation": 2}), preflight=preflight()
    )
    assert result.plan.ready
    nodes = {n.key: n for n in result.plan.history.events[-1].dependencies}
    mappings = {n.key for n in nodes.values() if n.kind == "mapping"}
    assert mappings
    structure = next(n for n in nodes.values() if n.kind == "structure")
    assert mappings <= set(structure.depends_on)
    assert any(
        n.kind == "target" and set(n.depends_on) & mappings for n in nodes.values()
    )


def test_configuration_memory_preserves_origin_and_rejects_missing_or_cyclic_history():
    from brz2obsidian.core import prepare_review, refresh_review, resolve_review

    facts = request(original=b"old", current=b"authored", incoming=b"new")
    facts = with_review_links(
        facts.model_copy(
            update={
                "subjects": (
                    facts.subjects[0].model_copy(
                        update={"output_role": "configuration"}
                    ),
                )
            }
        )
    )
    plan = prepare_review(facts, preflight=preflight())
    plan = resolve_review(
        plan, action(plan, domain="configuration", choice="current")
    ).plan
    memory = plan.approvals[0].source_memory
    assert memory.review_domain == "configuration"
    same = refresh_review(
        plan, facts.model_copy(update={"generation": 2}), preflight=preflight()
    ).plan
    assert same.ready and same.approvals[0].source_memory == memory
    assert same.approvals[0].source_memory.provenance.generation == 1
    reviewed = memory.provenance.reviewed_assumptions
    for dependencies in (("missing-proof",), (reviewed[0].key,)):
        broken = reviewed[0].model_copy(update={"depends_on": dependencies})
        corrupt = memory.model_copy(
            update={
                "provenance": memory.provenance.model_copy(
                    update={"reviewed_assumptions": (broken,) + reviewed[1:]}
                )
            }
        )
        fresh = facts.model_copy(
            update={"generation": 2, "source_version_memory": (corrupt,)}
        )
        result = refresh_review(
            prepare_review(facts, preflight=preflight()), fresh, preflight=preflight()
        ).plan
        assert not result.ready
        assert result.approvals == ()
        assert (
            result.proposal.changes[0].preservation_review.provenance != "source_memory"
        )
    changed = facts.model_copy(
        update={
            "generation": 2,
            "incoming_identity": facts.incoming_identity.model_copy(
                update={"settings_digest": "different-settings"}
            ),
            "source_version_memory": (memory,),
        }
    )
    changed_plan = refresh_review(plan, changed, preflight=preflight()).plan
    assert not changed_plan.ready and changed_plan.approvals == ()
    assert memory in tuple(
        a.source_memory
        for e in changed_plan.history.events
        if hasattr(e, "decision_id")
        for a in plan.approvals
        if a.decision_id == e.decision_id
    )


def test_rename_choice_retains_original_epoch_without_authorizing_stale_public_decision():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import (
        prepare_review,
        reconcile,
        refresh_review,
        resolve_review,
        validate_review,
    )

    facts = two_items()
    first = facts.subjects[0].model_copy(
        update={"incoming": ExactContent(data=b"original\r\n")}
    )
    moved = facts.identity_inventory[0].model_copy(
        update={
            "current": first.current.model_copy(update={"path": "Authored/Opening.md"}),
            "target": first.source_target.model_copy(
                update={"normalized_path": "authored/opening.md"}
            ),
        }
    )
    facts = with_review_links(
        facts.model_copy(
            update={
                "subjects": (first, facts.subjects[1]),
                "identity_inventory": (moved, facts.identity_inventory[1]),
            }
        )
    )
    plan = prepare_review(facts, preflight=preflight())
    plan = resolve_review(
        plan,
        action(plan, domain="rename", choice="keep_path", decision_id="rename:keep"),
    ).plan
    original = plan.producer_facts.rename_decisions[0]
    second = plan.proposal.changes[1]
    plan = resolve_review(plan, action(plan, second, decision_id="second:approve")).plan
    for generation in (2, 3):
        plan = refresh_review(
            plan,
            facts.model_copy(update={"generation": generation}),
            preflight=preflight(),
        ).plan
        assert plan.proposal.changes[0].rename_review.status == "declined"
        assert plan.producer_facts.rename_decisions == (original,)
        assert original.generation == 1
        assert [a.decision_id for a in plan.approvals] == ["second:approve"]
        assert validate_review(plan).status == "accepted"
    arbitrary = facts.model_copy(
        update={"generation": 3, "rename_decisions": (original,)}
    )
    assert reconcile(arbitrary).changes[0].rename_review.status == "stale"
    observed = moved.model_copy(
        update={
            "current": moved.current.model_copy(
                update={"content": ExactContent(data=b"Later local edit")}
            )
        }
    )
    changed = with_review_links(
        facts.model_copy(
            update={
                "generation": 4,
                "link_context": None,
                "subjects": (
                    first.model_copy(update={"current": observed.current}),
                    facts.subjects[1],
                ),
                "identity_inventory": (observed, facts.identity_inventory[1]),
            }
        )
    )
    invalidated = refresh_review(plan, changed, preflight=preflight()).plan
    assert invalidated.proposal.changes[0].rename_review.status == "offered"
    assert invalidated.producer_applicability == ()
    assert [a.decision_id for a in invalidated.approvals] == ["second:approve"]


def test_association_applicability_preserves_origin_without_fabricating_observed_repair():
    from brz2obsidian.core import (
        prepare_review,
        refresh_review,
        resolve_review,
        validate_review,
    )

    facts = two_items()
    opaque = facts.identity_inventory[0].model_copy(
        update={
            "identity_state": "malformed",
            "identity": None,
            "raw_identity": "unreadable",
        }
    )
    facts = with_review_links(
        facts.model_copy(
            update={"identity_inventory": (opaque, facts.identity_inventory[1])}
        )
    )
    plan = prepare_review(facts, preflight=preflight())
    transition = resolve_review(
        plan,
        action(
            plan,
            domain="identity",
            choice="associate",
            selected_entry_id=opaque.entry_id,
        ),
    )
    assert transition.status == "accepted"
    plan = transition.plan
    original = plan.producer_facts.association_decisions[0]
    assert plan.proposal.changes[0].identity_review.repair_required
    for generation in (2, 3):
        transition = refresh_review(
            plan,
            facts.model_copy(update={"generation": generation}),
            preflight=preflight(),
        )
        assert transition.status == "accepted"
        plan = transition.plan
        assert plan.producer_facts.association_decisions == (original,)
        assert plan.proposal.changes[0].identity_review.status == "association_proposed"
        assert plan.proposal.changes[0].identity_review.repair_required
        assert not plan.ready
        assert validate_review(plan).status == "accepted"


def test_binary_retention_rechecks_fresh_safety_and_keeps_original_selection_epoch():
    from brz2obsidian.core import (
        prepare_review,
        refresh_review,
        resolve_review,
        validate_attachment_candidate,
        validate_review,
    )
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        attachment_request,
    )

    facts = attachment_request()
    selection, candidate = attachment_candidate(facts, "both")
    plan = prepare_review(facts, preflight=preflight())
    plan = resolve_review(
        plan,
        action(
            plan,
            domain="attachment",
            choice="both",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    ).plan
    assert plan.ready
    new = facts.model_copy(update={"generation": 2})
    retained = refresh_review(plan, new, preflight=preflight()).plan
    assert retained.ready and retained.approvals == plan.approvals
    assert retained.approvals[0].attachment_selection.generation == 1
    assert not validate_attachment_candidate(new, selection, candidate).valid
    assert validate_review(retained).status == "accepted"
    unsafe = facts.identity_inventory[0].model_copy(
        update={
            "target": facts.identity_inventory[0].target.model_copy(
                update={"containment": "outside"}
            )
        }
    )
    unsafe_facts = facts.model_copy(
        update={
            "generation": 2,
            "identity_inventory": (unsafe,) + facts.identity_inventory[1:],
        }
    )
    refused = refresh_review(plan, unsafe_facts, preflight=preflight()).plan
    assert not refused.ready and refused.approvals == ()
    assert (
        plan.approvals[0].attachment_candidate.outputs[0].content.data
        == b"\x00authored"
    )


def test_refresh_missing_lookup_coverage_and_global_operation_safety_never_retain_readiness():
    from brz2obsidian.core import (
        prepare_review,
        refresh_review,
        resolve_review,
        validate_review,
    )

    facts = with_review_links(two_items())
    plan = prepare_review(facts, preflight=preflight())
    for change in plan.proposal.changes:
        plan = resolve_review(
            plan, action(plan, change, decision_id=change.item_id)
        ).plan
    for context in (
        None,
        facts.link_context.model_copy(
            update={"current_documents": facts.link_context.current_documents[1:]}
        ),
        facts.link_context.model_copy(update={"current_targets": ()}),
    ):
        refreshed = refresh_review(
            plan,
            facts.model_copy(update={"generation": 2, "link_context": context}),
            preflight=preflight(),
        )
        assert refreshed.status == "accepted"
        assert not refreshed.plan.ready and refreshed.plan.approvals == ()
        assert validate_review(refreshed.plan).status == "accepted"
    unsafe = facts.safety_facts[-1].model_copy(update={"status": "active"})
    refused = refresh_review(
        plan,
        facts.model_copy(
            update={
                "generation": 2,
                "safety_facts": facts.safety_facts[:-1] + (unsafe,),
            }
        ),
        preflight=preflight(),
    ).plan
    assert refused.readiness == "refused" and refused.approvals == ()
    assert (
        refresh_review(plan, facts, preflight=preflight()).code == "generation_changed"
    )
    assert (
        refresh_review(
            plan,
            facts.model_copy(update={"proposal_id": "other", "generation": 2}),
            preflight=preflight(),
        ).code
        == "wrong_proposal"
    )
    event_plan = refresh_review(
        plan, facts.model_copy(update={"generation": 2}), preflight=preflight()
    ).plan
    event = event_plan.history.events[-1]
    node = event.dependencies[0]
    cyclic = node.model_copy(update={"depends_on": (node.key,)})
    event = event.model_copy(
        update={"dependencies": (cyclic,) + event.dependencies[1:]}
    )
    forged = event_plan.model_copy(
        update={
            "history": event_plan.history.model_copy(
                update={"events": event_plan.history.events[:-1] + (event,)}
            )
        }
    )
    assert (
        refresh_review(
            forged, facts.model_copy(update={"generation": 3}), preflight=preflight()
        ).code
        == "invalid_plan"
    )


def test_refresh_cannot_resurrect_stale_normalized_producer_records():
    from brz2obsidian.core import prepare_review, refresh_review, resolve_review

    facts = two_items()
    moved = facts.identity_inventory[0].model_copy(
        update={
            "current": facts.subjects[0].current.model_copy(
                update={"path": "Authored/Opening.md"}
            ),
            "target": facts.subjects[0].source_target.model_copy(
                update={"normalized_path": "authored/opening.md"}
            ),
        }
    )
    rename_facts = with_review_links(
        facts.model_copy(
            update={"identity_inventory": (moved, facts.identity_inventory[1])}
        )
    )
    origin = prepare_review(rename_facts, preflight=preflight())
    admitted = resolve_review(
        origin, action(origin, domain="rename", choice="keep_path")
    ).plan
    record = admitted.producer_facts.rename_decisions[0]
    legitimate = prepare_review(
        rename_facts.model_copy(update={"rename_decisions": (record,)}),
        preflight=preflight(),
    )
    assert legitimate.actions == ()
    retained_initial = refresh_review(
        legitimate,
        rename_facts.model_copy(update={"generation": 2}),
        preflight=preflight(),
    ).plan
    assert retained_initial.producer_facts.rename_decisions == (record,)
    assert retained_initial.proposal.changes[0].rename_review.status == "declined"
    unreviewed = record.model_copy(update={"generation": 2})
    refused = refresh_review(
        origin,
        rename_facts.model_copy(
            update={"generation": 2, "rename_decisions": (unreviewed,)}
        ),
        preflight=preflight(),
    )
    assert refused.status == "refused" and refused.code == "choice_not_admitted"
    assert refused.plan == origin
    stale = prepare_review(
        rename_facts.model_copy(
            update={"generation": 2, "rename_decisions": (record,)}
        ),
        preflight=preflight(),
    )
    assert (
        stale.actions == ()
        and stale.proposal.changes[0].rename_review.status == "stale"
    )
    refreshed = refresh_review(
        stale, rename_facts.model_copy(update={"generation": 3}), preflight=preflight()
    ).plan
    assert refreshed.producer_applicability == ()
    assert refreshed.producer_facts.rename_decisions == ()
    assert refreshed.proposal.changes[0].rename_review.status == "offered"
    opaque = facts.identity_inventory[0].model_copy(
        update={
            "identity_state": "malformed",
            "identity": None,
            "raw_identity": "unreadable",
        }
    )
    association_facts = with_review_links(
        facts.model_copy(
            update={"identity_inventory": (opaque, facts.identity_inventory[1])}
        )
    )
    origin = prepare_review(association_facts, preflight=preflight())
    admitted = resolve_review(
        origin,
        action(
            origin,
            domain="identity",
            choice="associate",
            selected_entry_id=opaque.entry_id,
        ),
    ).plan
    record = admitted.producer_facts.association_decisions[0]
    stale = prepare_review(
        association_facts.model_copy(
            update={"generation": 2, "association_decisions": (record,)}
        ),
        preflight=preflight(),
    )
    assert stale.proposal.changes[0].identity_review.status == "stale"
    refreshed = refresh_review(
        stale,
        association_facts.model_copy(update={"generation": 3}),
        preflight=preflight(),
    ).plan
    assert refreshed.producer_applicability == ()
    assert refreshed.producer_facts.association_decisions == ()
    assert (
        refreshed.proposal.changes[0].identity_review.status != "association_proposed"
    )
    assert not refreshed.ready


def add_unrelated_note(facts, payload=b"Unrelated authored prose"):
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_attachments import target_for_links
    from tests.reconciliation.test_identity import inventory_item

    item = inventory_item("unrelated-note", "local", "Other.md", payload).model_copy(
        update={"identity": None, "identity_state": "missing"}
    )
    target = target_for_links("local:other", "Other.md")
    state = interpret_link_target(
        ExactContent(data=payload),
        target_id=target.target_id,
        existence="present",
        memberships=(),
    )
    context = facts.link_context
    updates = {}
    for stage in ("current", "incoming"):
        targets = getattr(context, stage + "_targets") + (target,)
        states = getattr(context, stage + "_target_facts") + (state,)
        document = interpret_links(
            ExactContent(data=payload),
            document_id="local:other",
            source_path="Other.md",
            path_mode="vault",
            targets=targets,
            target_facts=states,
            inventory="complete",
        )
        updates[stage + "_targets"] = targets
        updates[stage + "_target_facts"] = states
        updates[stage + "_documents"] = getattr(context, stage + "_documents") + (
            document,
        )
    context = context.model_copy(update=updates)
    return facts.model_copy(
        update={
            "identity_inventory": facts.identity_inventory + (item,),
            "link_context": context,
        }
    )


def test_binary_original_proof_retains_across_unrelated_complete_context_addition():
    from brz2obsidian.core import (
        prepare_review,
        refresh_review,
        resolve_review,
        validate_review,
    )
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        attachment_request,
    )

    facts = attachment_request()
    selection, candidate = attachment_candidate(facts, "both")
    plan = prepare_review(facts, preflight=preflight())
    plan = resolve_review(
        plan,
        action(
            plan,
            domain="attachment",
            choice="both",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    ).plan
    assert plan.ready
    fresh = add_unrelated_note(facts).model_copy(update={"generation": 2})
    result = refresh_review(plan, fresh, preflight=preflight()).plan
    assert result.ready
    assert result.approvals == plan.approvals
    assert result.approvals[0].attachment_candidate == candidate
    assert result.approvals[0].attachment_selection == selection
    assert validate_review(result).status == "accepted"
    original_facts = add_unrelated_note(facts, b"Old unrelated prose")
    old_selection, old_candidate = attachment_candidate(original_facts, "both")
    original_plan = prepare_review(original_facts, preflight=preflight())
    original_plan = resolve_review(
        original_plan,
        action(
            original_plan,
            domain="attachment",
            choice="both",
            attachment_selection=old_selection,
            attachment_candidate=old_candidate,
        ),
    ).plan
    changed = add_unrelated_note(facts, b"Fresh unrelated authored prose").model_copy(
        update={"generation": 2}
    )
    retained = refresh_review(original_plan, changed, preflight=preflight()).plan
    assert retained.ready and retained.approvals == original_plan.approvals
    assert old_candidate.documents[0].content.data == b"Old unrelated prose"
    assert (
        retained.attachment_applicability[0].candidate.documents[0].content.data
        == b"Fresh unrelated authored prose"
    )
    assert validate_review(retained).status == "accepted"


def test_safety_scope_change_for_other_subject_does_not_revoke_this_admission():
    from brz2obsidian.core import prepare_review, refresh_review, resolve_review

    facts = two_items()
    first, second = facts.subjects
    identity = facts.safety_facts[0].model_copy(
        update={"subjects": (first.item_id, second.item_id)}
    )
    separate = identity.model_copy(
        update={"key": "identity:second", "subjects": (second.item_id,)}
    )
    facts = with_review_links(
        facts.model_copy(
            update={"safety_facts": (identity,) + facts.safety_facts[1:] + (separate,)}
        )
    )
    plan = prepare_review(facts, preflight=preflight())
    plan = resolve_review(plan, action(plan, decision_id="first:approved")).plan
    fresh = facts.model_copy(
        update={
            "generation": 2,
            "safety_facts": (
                identity.model_copy(update={"subjects": (first.item_id,)}),
            )
            + facts.safety_facts[1:],
        }
    )
    result = refresh_review(plan, fresh, preflight=preflight()).plan
    assert [a.decision_id for a in result.approvals] == ["first:approved"]
    assert result.approvals == plan.approvals


def test_changed_required_history_state_invalidates_consent_without_approving_new_facts():
    from brz2obsidian.core import prepare_review, refresh_review, resolve_review

    facts = with_review_links(two_items())
    plan = prepare_review(facts, preflight=preflight())
    for change in plan.proposal.changes:
        plan = resolve_review(
            plan, action(plan, change, decision_id=change.item_id)
        ).plan
    changed = preflight().model_copy(
        update={"state_fingerprint": "new-observed-history-state"}
    )
    result = refresh_review(
        plan, facts.model_copy(update={"generation": 2}), preflight=changed
    ).plan
    assert not result.ready and result.approvals == ()
    assert "review:state" in result.history.events[-1].changed_keys
    assert len(result.requirements) == 2


def test_new_shortened_lookup_competitor_invalidates_linked_choice_only():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import prepare_review, refresh_review, resolve_review
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_attachments import target_for_links
    from tests.reconciliation.test_identity import inventory_item

    facts = two_items()
    second = facts.subjects[1].model_copy(
        update={"incoming": ExactContent(data=b"[[Opening]]")}
    )
    facts = with_review_links(
        facts.model_copy(update={"subjects": (facts.subjects[0], second)})
    )
    context = facts.link_context
    incoming = tuple(
        interpret_links(
            d.content,
            document_id=d.document_id,
            source_path=d.source_path,
            path_mode="shortened",
            targets=context.incoming_targets,
            target_facts=context.incoming_target_facts,
            inventory="complete",
        )
        for d in context.incoming_documents
    )
    current = tuple(
        interpret_links(
            d.content,
            document_id=d.document_id,
            source_path=d.source_path,
            path_mode="shortened",
            targets=context.current_targets,
            target_facts=context.current_target_facts,
            inventory="complete",
        )
        for d in context.current_documents
    )
    context = context.model_copy(
        update={"current_documents": current, "incoming_documents": incoming}
    )
    facts = facts.model_copy(update={"link_context": context})
    plan = prepare_review(facts, preflight=preflight())
    for change in plan.proposal.changes:
        plan = resolve_review(
            plan, action(plan, change, decision_id=change.item_id)
        ).plan
    assert plan.ready
    item = inventory_item(
        "competitor", "local", "Elsewhere/Opening.md", b"Different note"
    ).model_copy(update={"identity": None, "identity_state": "missing"})
    target = target_for_links("local:competitor", "Elsewhere/Opening.md")
    state = interpret_link_target(
        item.current.content,
        target_id=target.target_id,
        existence="present",
        memberships=(),
    )
    current_targets, incoming_targets = (
        context.current_targets + (target,),
        context.incoming_targets + (target,),
    )
    current_states, incoming_states = (
        context.current_target_facts + (state,),
        context.incoming_target_facts + (state,),
    )
    current_docs = tuple(
        interpret_links(
            d.content,
            document_id=d.document_id,
            source_path=d.source_path,
            path_mode=d.path_mode,
            targets=current_targets,
            target_facts=current_states,
            inventory="complete",
        )
        for d in context.current_documents
    )
    incoming_docs = tuple(
        interpret_links(
            d.content,
            document_id=d.document_id,
            source_path=d.source_path,
            path_mode="shortened",
            targets=incoming_targets,
            target_facts=incoming_states,
            inventory="complete",
        )
        for d in incoming
    )
    local_doc = interpret_links(
        item.current.content,
        document_id="local:competitor",
        source_path=item.current.path,
        path_mode="vault",
        targets=current_targets,
        target_facts=current_states,
        inventory="complete",
    )
    fresh = facts.model_copy(
        update={
            "generation": 2,
            "identity_inventory": facts.identity_inventory + (item,),
            "link_context": context.model_copy(
                update={
                    "current_targets": current_targets,
                    "incoming_targets": incoming_targets,
                    "current_target_facts": current_states,
                    "incoming_target_facts": incoming_states,
                    "current_documents": current_docs + (local_doc,),
                    "incoming_documents": incoming_docs + (local_doc,),
                }
            ),
        }
    )
    assert incoming_docs[1].occurrences[0].meaning.status == "ambiguous"
    result = refresh_review(plan, fresh, preflight=preflight()).plan
    assert [a.decision_id for a in result.approvals] == ["entry:opening"]
    assert not result.ready
    assert plan.approvals[1].result.data == b"[[Opening]]"


def test_used_remap_reopens_only_its_subject_with_explicit_mapping_requirement():
    from brz2obsidian.contracts import ClassificationMapping
    from brz2obsidian.core import prepare_review, refresh_review, resolve_review
    from tests.reconciliation.test_identity import with_subjects
    from tests.reconciliation.test_memberships import membership_request, target

    original = b"---\ntags:\n  - alpha\npriority: 1\n---\nText.\n"
    incoming = original.replace(b"priority: 1", b"priority: 2")
    mapping = ClassificationMapping(
        schema_id="brz2obsidian.classification-mapping",
        schema_version=1,
        classification_id="source:tag",
        target_id="alpha",
        kind="tag",
        source_label="Label",
    )
    initial = membership_request(
        original,
        original,
        incoming,
        targets=(target("alpha", "tag", "alpha"),),
        prior_mappings=(mapping,),
        incoming_mappings=(mapping,),
    )
    pair = two_items()
    facts = with_review_links(
        with_subjects(
            initial,
            (initial.subjects[0], pair.subjects[1]),
            (initial.identity_inventory[0], pair.identity_inventory[1]),
        )
    )
    plan = prepare_review(facts, preflight=preflight())
    for change in plan.proposal.changes:
        plan = resolve_review(
            plan, action(plan, change, decision_id=change.item_id)
        ).plan
    assert plan.ready
    remapped = membership_request(
        original,
        original,
        incoming.replace(b"alpha", b"beta"),
        targets=(target("alpha", "tag", "alpha"), target("beta", "tag", "beta")),
        prior_mappings=(mapping,),
        incoming_mappings=(mapping.model_copy(update={"target_id": "beta"}),),
    )
    fresh = with_review_links(
        facts.model_copy(
            update={
                "generation": 2,
                "link_context": None,
                "subjects": (remapped.subjects[0], pair.subjects[1]),
            }
        )
    )
    result = refresh_review(plan, fresh, preflight=preflight()).plan
    assert [a.decision_id for a in result.approvals] == ["entry:second"]
    assert {r.domain for r in result.requirements} == {"mapping"}
    assert not result.ready
    assert any(
        n.kind == "mapping" and n.key in result.history.events[-1].invalidated_keys
        for n in result.history.events[-1].previous_dependencies
    )


def test_cyclic_prospective_producer_relationships_refuse_refresh_authority():
    from brz2obsidian.contracts import RenamePathDecision
    from brz2obsidian.core import prepare_review, refresh_review

    facts = two_items()
    subjects = tuple(
        s.model_copy(
            update={
                "path": "Shared.md",
                "source_target": s.source_target.model_copy(
                    update={"normalized_path": "shared.md"}
                ),
            }
        )
        for s in facts.subjects
    )
    decisions = tuple(
        RenamePathDecision(
            schema_id="brz2obsidian.rename-decision",
            schema_version=1,
            decision_id="conflicting:" + s.item_id,
            proposal_id=facts.proposal_id,
            generation=1,
            collection_id=facts.incoming_identity.collection_id,
            module_id=facts.incoming_identity.module_id,
            item_id=s.item_id,
            facet=s.facet,
            choice="source_path",
            reviewed_assumptions=(),
            provenance="explicit_user",
        )
        for s in subjects
    )
    facts = with_review_links(
        facts.model_copy(update={"subjects": subjects, "rename_decisions": decisions})
    )
    plan = prepare_review(facts, preflight=preflight())
    assert not plan.ready and plan.approvals == ()
    result = refresh_review(
        plan, facts.model_copy(update={"generation": 2}), preflight=preflight()
    )
    assert result.status == "refused" and result.code == "dependency_graph_invalid"
    assert result.plan == plan


def test_refresh_history_records_are_closed_strict_versioned_and_duplicate_safe():
    import json

    import pytest
    from pydantic import ValidationError

    from brz2obsidian.contracts import ReviewHistory
    from brz2obsidian.core import prepare_review

    history = prepare_review(
        with_review_links(request()), preflight=preflight()
    ).history
    data = history.model_dump(mode="json")
    assert ReviewHistory.model_validate_json(history.model_dump_json()) == history
    for bad in (
        data | {"schema_version": True},
        data | {"schema_version": 1.0},
        data | {"unreviewed": True},
        {k: v for k, v in data.items() if k != "events"},
    ):
        with pytest.raises(ValidationError):
            ReviewHistory.model_validate_json(json.dumps(bad))
    duplicate = history.model_dump_json().replace(
        '"events":[]', '"events":[],"events":[]'
    )
    with pytest.raises(ValueError):
        ReviewHistory.model_validate_json(duplicate)


@pytest.mark.parametrize("ordering", ("mapping_rows", "membership_target_spellings"))
def test_mapping_row_order_retains_review_without_reordering_original_facts(ordering):
    from brz2obsidian.contracts import ClassificationMapping
    from brz2obsidian.core import (
        prepare_review,
        refresh_review,
        resolve_review,
        validate_review,
    )
    from tests.reconciliation.test_memberships import membership_request, target

    original = b"---\ntags:\n  - alpha\n  - beta\npriority: 1\n---\nText.\n"
    mappings = tuple(
        ClassificationMapping(
            schema_id="brz2obsidian.classification-mapping",
            schema_version=1,
            classification_id="source:" + name,
            target_id=name,
            kind="tag",
            source_label=name,
        )
        for name in ("alpha", "beta")
    )
    facts = with_review_links(
        membership_request(
            original,
            original,
            original.replace(b"priority: 1", b"priority: 2"),
            targets=(
                target("alpha", "tag", "alpha", "alias-alpha"),
                target("beta", "tag", "beta", "alias-beta"),
            ),
            prior_mappings=mappings,
            incoming_mappings=mappings,
        )
    )
    plan = prepare_review(facts, preflight=preflight())
    approved = resolve_review(plan, action(plan)).plan
    assert approved.ready
    comparison = facts.subjects[0].structure
    if ordering == "mapping_rows":
        structure = comparison.model_copy(
            update={
                "prior_mappings": mappings[::-1],
                "incoming_mappings": mappings[::-1],
            }
        )
    else:
        structure = comparison.model_copy(
            update={
                stage: getattr(comparison, stage).model_copy(
                    update={
                        "memberships": tuple(
                            m.model_copy(
                                update={
                                    "entries": tuple(
                                        e.model_copy(
                                            update={
                                                "target": e.target.model_copy(
                                                    update={
                                                        "representations": e.target.representations[
                                                            ::-1
                                                        ]
                                                    }
                                                )
                                            }
                                        )
                                        for e in m.entries
                                    )
                                }
                            )
                            for m in getattr(comparison, stage).memberships
                        ),
                    }
                )
                for stage in ("original", "current", "incoming")
            }
        )
    fresh = facts.model_copy(
        update={
            "generation": 2,
            "subjects": (
                facts.subjects[0].model_copy(update={"structure": structure}),
            ),
        }
    )
    refreshed = refresh_review(approved, fresh, preflight=preflight()).plan
    assert refreshed.ready
    assert refreshed.approvals == approved.approvals
    assert refreshed.producer_facts.subjects[0].structure == structure
    assert approved.producer_facts.subjects[0].structure.prior_mappings == mappings
    assert validate_review(refreshed).status == "accepted"


@pytest.mark.parametrize(
    "ordering", ("targets", "target_facts", "documents", "representations", "spellings")
)
def test_lookup_set_order_retains_original_binary_review_and_authored_order(ordering):
    from brz2obsidian.core import (
        prepare_review,
        refresh_review,
        resolve_review,
        validate_review,
    )
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        linked_attachment_request,
    )

    facts = add_unrelated_note(linked_attachment_request(), b"Also [[Assets/data.bin]]")
    context = facts.link_context
    updates = {}
    for stage in ("current", "incoming"):
        targets = tuple(
            t.model_copy(
                update={"representations": (t.canonical_path, "alias:" + t.target_id)}
            )
            for t in getattr(context, stage + "_targets")
        )
        docs = tuple(
            d.model_copy(
                update={
                    "occurrences": tuple(
                        o.model_copy(
                            update={
                                "query": o.query.model_copy(
                                    update={
                                        "spellings": (
                                            o.query.value,
                                            "[[" + o.query.value + "]]",
                                        )
                                    }
                                )
                            }
                        )
                        for o in d.occurrences
                    )
                }
            )
            for d in getattr(context, stage + "_documents")
        )
        updates[stage + "_targets"] = targets
        updates[stage + "_documents"] = docs
    context = context.model_copy(update=updates)
    facts = facts.model_copy(update={"link_context": context})
    selection, candidate = attachment_candidate(facts, "both")
    plan = prepare_review(facts, preflight=preflight())
    approved = resolve_review(
        plan,
        action(
            plan,
            domain="attachment",
            choice="both",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    ).plan
    assert approved.ready
    updates = {}
    for stage in ("current", "incoming"):
        if ordering in ("targets", "target_facts", "documents"):
            key = stage + "_" + ordering
            updates[key] = getattr(context, key)[::-1]
        elif ordering == "representations":
            updates[stage + "_targets"] = tuple(
                t.model_copy(update={"representations": t.representations[::-1]})
                for t in getattr(context, stage + "_targets")
            )
        else:
            updates[stage + "_documents"] = tuple(
                d.model_copy(
                    update={
                        "occurrences": tuple(
                            o.model_copy(
                                update={
                                    "query": o.query.model_copy(
                                        update={"spellings": o.query.spellings[::-1]}
                                    )
                                }
                            )
                            for o in d.occurrences
                        )
                    }
                )
                for d in getattr(context, stage + "_documents")
            )
    fresh = facts.model_copy(
        update={"generation": 2, "link_context": context.model_copy(update=updates)}
    )
    result = refresh_review(approved, fresh, preflight=preflight()).plan
    assert result.ready
    assert result.approvals == approved.approvals
    assert result.approvals[0].attachment_candidate == candidate
    assert result.approvals[0].attachment_selection == selection
    assert result.producer_facts.link_context == fresh.link_context
    assert result.history.initial_facts.link_context == context
    assert (
        candidate.documents[0].content.data
        == b"[[Assets/data.bin|Keep first]] and [[Assets/data.bin|Redirect second]]"
    )
    assert len(candidate.documents[0].occurrences) == 2
    assert candidate.documents[1].content.data == b"Also [[Assets/data.bin]]"
    assert validate_review(result).status == "accepted"


def test_changed_used_alias_meaning_reopens_binary_review_with_same_authored_bytes():
    from brz2obsidian.core import prepare_review, refresh_review, resolve_review
    from brz2obsidian.obsidian import interpret_links
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        linked_attachment_request,
    )

    facts = linked_attachment_request(raw=b"[[Payload]]")

    def observed(context, aliases):
        updates = {}
        for stage in ("current", "incoming"):
            targets = tuple(
                t.model_copy(update={"representations": aliases})
                if t.target_id == "resource:payload"
                else t
                for t in getattr(context, stage + "_targets")
            )
            updates[stage + "_targets"] = targets
            updates[stage + "_documents"] = tuple(
                interpret_links(
                    d.content,
                    document_id=d.document_id,
                    source_path=d.source_path,
                    path_mode="vault",
                    targets=targets,
                    target_facts=getattr(context, stage + "_target_facts"),
                    inventory="complete",
                )
                for d in getattr(context, stage + "_documents")
            )
        return context.model_copy(update=updates)

    facts = facts.model_copy(
        update={
            "link_context": observed(facts.link_context, ("Assets/data.bin", "Payload"))
        }
    )
    assert (
        facts.link_context.current_documents[0].occurrences[0].meaning.status
        == "resolved"
    )
    selection, candidate = attachment_candidate(facts, "both")
    # Preserve the existing target's reviewed alias on the current output only.
    candidate = candidate.model_copy(
        update={
            "targets": tuple(
                t.model_copy(update={"representations": ("Assets/data.bin", "Payload")})
                if t.target_id == "resource:payload"
                else t
                for t in candidate.targets
            )
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    approved = resolve_review(
        plan,
        action(
            plan,
            domain="attachment",
            choice="both",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    ).plan
    assert approved.ready
    fresh = facts.model_copy(
        update={
            "generation": 2,
            "link_context": observed(facts.link_context, ("Assets/data.bin",)),
        }
    )
    assert fresh.link_context.current_documents[0].content.data == b"[[Payload]]"
    assert (
        fresh.link_context.current_documents[0].occurrences[0].meaning.status
        == "missing"
    )
    result = refresh_review(approved, fresh, preflight=preflight()).plan
    assert result.approvals == ()
    assert not result.ready
    assert any(
        n.kind == "link" and n.key in result.history.events[-1].invalidated_keys
        for n in result.history.events[-1].previous_dependencies
    )


@pytest.mark.parametrize("ordering", ("consent_subjects", "proposal_subjects"))
def test_consent_scope_set_order_retains_exact_original_consent(ordering):
    from brz2obsidian.contracts import ReviewConsentRequirement
    from brz2obsidian.core import (
        prepare_review,
        refresh_review,
        resolve_review,
        validate_review,
    )

    facts = with_review_links(two_items())
    proposal = prepare_review(facts, preflight=preflight()).proposal
    subjects = tuple(c.subject_id for c in proposal.changes)
    consent = ReviewConsentRequirement(
        schema_id="brz2obsidian.review-consent-requirement",
        schema_version=1,
        consent_id="both-storage",
        kind="storage",
        requirement="required",
        policy="ordinary",
        fingerprint="storage-policy",
        disclosure="Both outputs",
        subjects=subjects,
    )
    checks = preflight().model_copy(update={"consents": (consent,)})
    plan = prepare_review(facts, preflight=checks)
    for change in plan.proposal.changes:
        plan = resolve_review(
            plan, action(plan, change, decision_id=change.item_id)
        ).plan
    requirement = next(r for r in plan.requirements if r.domain == "storage")
    plan = resolve_review(
        plan,
        action(
            plan,
            domain="storage",
            choice="accept",
            change_id=requirement.change_id,
            reviewed_assumptions=requirement.assumptions,
            decision_id="storage:original",
        ),
    ).plan
    assert plan.ready
    fresh = facts.model_copy(update={"generation": 2})
    fresh_checks = checks
    if ordering == "consent_subjects":
        fresh_checks = checks.model_copy(
            update={
                "consents": (consent.model_copy(update={"subjects": subjects[::-1]}),)
            }
        )
    else:
        fresh = fresh.model_copy(update={"subjects": facts.subjects[::-1]})
    result = refresh_review(plan, fresh, preflight=fresh_checks).plan
    assert result.ready
    assert result.approvals == plan.approvals
    assert result.consents == plan.consents
    assert result.history.initial_preflight == checks
    assert result.preflight == fresh_checks
    assert result.producer_facts.subjects == fresh.subjects
    assert validate_review(result).status == "accepted"


@pytest.mark.parametrize(
    "role,domain", (("note", "content"), ("configuration", "configuration"))
)
def test_unchanged_declined_restoration_retains_exact_original_memory_and_absence(
    role, domain
):
    from brz2obsidian.core import (
        prepare_review,
        refresh_review,
        resolve_review,
        validate_review,
    )
    from tests.reconciliation.test_absence import facts_for

    initial = facts_for(existence="absent", incoming=b"incoming\n")
    facts = with_review_links(
        initial.model_copy(
            update={
                "subjects": (
                    initial.subjects[0].model_copy(update={"output_role": role}),
                )
            }
        )
    )
    plan = prepare_review(facts, preflight=preflight())
    token = action(
        plan,
        domain="restoration",
        choice="decline_restoration",
        decision_id="original:decline",
    )
    admitted = resolve_review(plan, token)
    assert admitted.status == "accepted" and admitted.plan.ready
    approved = admitted.plan
    original = approved.approvals[0]
    memory = original.source_memory
    assert original.result is None and not original.source_accepted
    assert memory.choice == "decline_restoration"
    assert memory.review_domain == domain
    assert memory.reviewed_incoming.data == b"incoming\n"
    assert memory.provenance.generation == 1
    for generation in (2, 3):
        fresh = facts.model_copy(update={"generation": generation})
        result = refresh_review(approved, fresh, preflight=preflight()).plan
        assert result.ready
        assert result.approvals == (original,)
        assert result.actions == (token,)
        assert result.approvals[0].source_memory == memory
        assert result.approvals[0].source_memory.provenance.generation == 1
        assert result.producer_facts.source_version_memory == ()
        assert result.producer_facts.subjects[0].current.existence == "absent"
        assert result.producer_facts.identity_inventory[0].current.existence == "absent"
        assert result.history.events[-1].changed_keys == ()
        assert result.history.events[-1].invalidated_keys == ()
        assert resolve_review(result, token).code == "decision_id_reused"
        assert validate_review(result).status == "accepted"
        approved = result
    if role == "note":
        unknown = facts_for(existence="unknown", incoming=b"incoming\n")
        uncertain = refresh_review(
            approved,
            with_review_links(unknown.model_copy(update={"generation": 4})),
            preflight=preflight(),
        ).plan
        assert uncertain.approvals == () and not uncertain.ready
