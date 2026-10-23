"""Operation-bound absence is an explicit whole-review selection."""

import pytest

from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links


def reversal_facts(*, current=b"created\r\n", produced=b"created\r\n"):
    from brz2obsidian.contracts import ExactContent, OperationReversalAbsence

    facts = request(original=produced, current=current, incoming=produced)
    subject = facts.subjects[0]
    proof = OperationReversalAbsence(
        schema_id="brz2obsidian.operation-reversal-absence",
        schema_version=1,
        operation_id="operation:created",
        operation_kind="apply",
        direction="restore",
        operation_generation=1,
        history_fingerprint="validated:before-absent/proposed-created",
        path=subject.path,
        produced=ExactContent(data=produced),
        target_existence="absent",
    )
    facts = facts.model_copy(
        update={
            "subjects": (
                subject.model_copy(
                    update={"incoming": None, "reversal_absence": proof}
                ),
            )
        }
    )
    return with_review_links(facts)


def test_created_path_removal_requires_explicit_canonical_absence_choice():
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects

    plan = prepare_review(reversal_facts(), preflight=preflight())
    assert not plan.ready and not plan.blockers
    assert [(r.domain, r.choices) for r in plan.requirements] == [
        ("reversal", ("current", "reverse_absence", "edited"))
    ]
    assert select_review_effects(plan).code == "review_not_ready"
    result = resolve_review(
        plan, action(plan, domain="reversal", choice="reverse_absence")
    )
    assert result.status == "accepted" and result.plan.ready
    effects = select_review_effects(result.plan)
    assert effects.status == "selected"
    assert effects.files == () and effects.remove_paths == ("Notes/Opening.md",)


def test_selected_absence_invalidates_a_retained_inbound_link_in_whole_plan():
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
    from tests.reconciliation.test_identity import inventory_item

    facts = reversal_facts()
    owner = inventory_item(
        "owner", "entry:owner", "Notes/Owner.md", b"Keep [[Notes/Opening]]"
    )
    facts = with_review_links(
        facts.model_copy(
            update={
                "identity_inventory": facts.identity_inventory + (owner,),
                "link_context": None,
            }
        )
    )
    plan = prepare_review(facts, preflight=preflight())
    result = resolve_review(
        plan, action(plan, domain="reversal", choice="reverse_absence")
    )
    assert result.status == "accepted"
    assert not result.plan.ready
    assert "selected_link_context_conflict" in result.plan.blockers
    assert select_review_effects(result.plan).code == "review_not_ready"


@pytest.mark.parametrize("current", [b"created\r\n", b"created\r\nlater writing", b""])
def test_current_choice_keeps_exact_present_bytes_without_source_deletion_memory(
    current,
):
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects

    plan = prepare_review(reversal_facts(current=current), preflight=preflight())
    chosen = resolve_review(plan, action(plan, domain="reversal", choice="current"))
    assert chosen.status == "accepted" and chosen.plan.ready
    assert chosen.plan.approvals[0].source_memory is None
    effects = select_review_effects(chosen.plan)
    assert [(f.path, f.content.data) for f in effects.files] == [
        ("Notes/Opening.md", current)
    ]
    assert effects.remove_paths == ()


def test_binary_reversal_keeps_third_bytes_or_explicitly_removes_created_path():
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
    from tests.reconciliation.test_attachments import attachment_request

    facts = attachment_request()
    subject = facts.subjects[0]
    proof = (
        reversal_facts()
        .subjects[0]
        .reversal_absence.model_copy(
            update={"path": subject.path, "produced": subject.baseline.content}
        )
    )
    facts = with_review_links(
        facts.model_copy(
            update={
                "subjects": (
                    subject.model_copy(
                        update={"incoming": None, "reversal_absence": proof}
                    ),
                )
            }
        ),
        opaque_link_free=True,
    )
    offered = prepare_review(facts, preflight=preflight())
    assert offered.requirements[0].choices == ("current", "reverse_absence")
    kept = resolve_review(offered, action(offered, domain="reversal", choice="current"))
    assert kept.status == "accepted" and kept.plan.ready
    effects = select_review_effects(kept.plan)
    assert [(f.path, f.content.data) for f in effects.files] == [
        ("Assets/data.bin", b"\x00authored")
    ]
    removed = resolve_review(
        offered, action(offered, domain="reversal", choice="reverse_absence")
    )
    effects = select_review_effects(removed.plan)
    assert effects.status == "selected" and effects.files == ()
    assert effects.remove_paths == ("Assets/data.bin",)


def test_already_absent_reversal_is_ready_without_a_file_effect():
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
    from tests.reconciliation.test_absence import facts_for

    facts = facts_for(original=b"created\r\n", existence="absent", incoming=None)
    proof = reversal_facts().subjects[0].reversal_absence
    subject = facts.subjects[0].model_copy(update={"reversal_absence": proof})
    facts = with_review_links(facts.model_copy(update={"subjects": (subject,)}))
    plan = prepare_review(facts, preflight=preflight())
    assert plan.ready and plan.requirements == ()
    effects = select_review_effects(plan)
    assert effects.status == "selected" and effects.files == effects.remove_paths == ()
    redundant = resolve_review(
        plan, action(plan, domain="reversal", choice="reverse_absence")
    )
    assert redundant.status == "refused" and redundant.code == "choice_not_admitted"


def test_saved_ordinary_review_retains_pre_extension_identity_and_wire_fields():
    from brz2obsidian.core import (
        load_review,
        prepare_review,
        resolve_review,
        save_review,
        validate_review,
    )

    facts = with_review_links(
        request(original=b"base\r\n", current=b"base\r\n", incoming=b"future\r\n")
    )
    plan = prepare_review(facts, preflight=preflight())
    plan = resolve_review(plan, action(plan)).plan
    assert plan.proposal.changes[0].change_id == (
        "1ce2d1e2791c1230d9f6fdaa10f12919f3fbda85e5c5d64cb6a85f4f54ec9da0"
    )
    raw = save_review(plan).record.model_dump_json()
    assert "reversal_absence" not in raw
    loaded = load_review(raw)
    assert loaded.status == "loaded" and not loaded.ready
    assert loaded.loaded.saved.plan == plan
    assert validate_review(loaded.loaded.saved.plan).status == "accepted"


def test_reversal_refresh_preserves_unaffected_approval_and_requires_new_current_choice():
    from brz2obsidian.core import (
        load_review,
        prepare_review,
        refresh_review,
        resolve_review,
        resume_review,
        save_review,
        select_review_effects,
        validate_review,
    )
    from tests.reconciliation.test_refresh import edit_first, two_items

    facts = two_items()
    first = facts.subjects[0]
    proof = (
        reversal_facts()
        .subjects[0]
        .reversal_absence.model_copy(update={"produced": first.baseline.content})
    )
    facts = with_review_links(
        facts.model_copy(
            update={
                "subjects": (
                    first.model_copy(
                        update={"incoming": None, "reversal_absence": proof}
                    ),
                    facts.subjects[1],
                )
            }
        )
    )
    plan = prepare_review(facts, preflight=preflight())
    plan = resolve_review(
        plan, action(plan, domain="reversal", choice="reverse_absence")
    ).plan
    plan = resolve_review(
        plan, action(plan, plan.proposal.changes[1], decision_id="unaffected:decision")
    ).plan
    assert plan.ready
    unaffected = plan.approvals[1]
    loaded = load_review(save_review(plan).record.model_dump_json())
    assert loaded.status == "loaded" and not loaded.ready
    refreshed = resume_review(loaded.loaded, edit_first(facts), preflight=preflight())
    assert refreshed.status == "resumed" and not refreshed.plan.ready
    assert refreshed.plan.proposal.generation == 2
    assert refreshed.plan.approvals == (unaffected,)
    stale = action(
        plan, domain="reversal", choice="reverse_absence", decision_id="stale"
    )
    assert resolve_review(refreshed.plan, stale).code == "generation_changed"
    selected = resolve_review(
        refreshed.plan,
        action(
            refreshed.plan,
            domain="reversal",
            choice="current",
            decision_id="later:keep",
        ),
    )
    assert selected.status == "accepted" and selected.plan.ready
    assert validate_review(selected.plan).status == "accepted"
    effects = select_review_effects(selected.plan)
    assert [(f.path, f.content.data) for f in effects.files] == [
        ("Notes/Opening.md", b"Authored after review"),
        ("Notes/Second.md", b"incoming\n"),
    ]
    assert effects.remove_paths == ()
    # Changing only the retained operation proof must also invalidate removal.
    same = facts.model_copy(update={"generation": 2})
    retained = refresh_review(plan, same, preflight=preflight())
    assert retained.status == "accepted" and retained.plan.ready
    assert retained.plan.approvals == plan.approvals
    changed_proof = proof.model_copy(
        update={"history_fingerprint": "different:history"}
    )
    changed = same.model_copy(
        update={
            "subjects": (
                same.subjects[0].model_copy(update={"reversal_absence": changed_proof}),
                same.subjects[1],
            )
        }
    )
    invalidated = refresh_review(plan, changed, preflight=preflight())
    assert invalidated.status == "accepted" and not invalidated.plan.ready
    assert invalidated.plan.approvals == (unaffected,)


def test_reversal_accepts_validated_edited_note_as_present_exact_bytes():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
    from brz2obsidian.obsidian import inspect_text_candidate, interpret_link_target

    facts = reversal_facts(current=b"created\r\nlater writing")
    context = facts.link_context
    edited = b"Preserved later writing; reviewed new introduction.\r\n"
    target = context.current_targets[0]
    states = (
        interpret_link_target(
            ExactContent(data=edited),
            target_id=target.target_id,
            existence="present",
            memberships=(),
        ),
    )
    candidate = inspect_text_candidate(
        ExactContent(data=edited),
        identity=facts.identity_inventory[0].identity,
        target=facts.subjects[0].source_target,
        output_format=7,
        source_path="Notes/Opening.md",
        document_id=context.current_documents[0].document_id,
        path_mode="vault",
        link_targets=context.current_targets,
        link_target_facts=states,
        link_inventory="complete",
    )
    plan = prepare_review(facts, preflight=preflight())
    missing = resolve_review(plan, action(plan, domain="reversal", choice="edited"))
    assert missing.status == "refused" and missing.code == "invalid_candidate"
    result = resolve_review(
        plan, action(plan, domain="reversal", choice="edited", candidate=candidate)
    )
    assert result.status == "accepted" and result.plan.ready
    selected = select_review_effects(result.plan)
    assert [(f.path, f.content.data) for f in selected.files] == [
        ("Notes/Opening.md", edited)
    ]
    assert selected.remove_paths == ()


@pytest.mark.parametrize(
    "change", ["incoming", "unknown_original", "different_produced", "other_path"]
)
def test_operation_absence_refuses_unbound_subject_facts(change):
    from pydantic import ValidationError

    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import prepare_review

    facts = reversal_facts()
    subject = facts.subjects[0]
    updates = {
        "incoming": {"incoming": ExactContent(data=b"source")},
        "unknown_original": {
            "baseline": subject.baseline.model_copy(
                update={"status": "unknown", "content": None}
            )
        },
        "different_produced": {
            "reversal_absence": subject.reversal_absence.model_copy(
                update={"produced": ExactContent(data=b"different")}
            )
        },
        "other_path": {"path": "Notes/Other.md"},
    }[change]
    with pytest.raises(ValidationError, match="Reversal absence requires"):
        prepare_review(
            facts.model_copy(
                update={"subjects": (subject.model_copy(update=updates),)}
            ),
            preflight=preflight(),
        )


def test_created_zero_byte_file_is_present_and_requires_explicit_removal():
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects

    plan = prepare_review(
        reversal_facts(current=b"", produced=b""), preflight=preflight()
    )
    assert not plan.ready and plan.proposal.changes[0].current.data == b""
    result = resolve_review(
        plan, action(plan, domain="reversal", choice="reverse_absence")
    )
    assert result.status == "accepted" and result.plan.ready
    effects = select_review_effects(result.plan)
    assert effects.files == () and effects.remove_paths == ("Notes/Opening.md",)


def test_identity_rebinding_cannot_move_operation_absence_authority_to_another_path():
    from brz2obsidian.core import prepare_review, select_review_effects
    from tests.reconciliation.test_identity import inventory_item

    facts = reversal_facts()
    moved = inventory_item(
        "moved", "entry:opening", "Authored/Moved.md", b"created\r\n"
    )
    facts = with_review_links(
        facts.model_copy(
            update={
                "identity_inventory": (moved,),
                "link_context": None,
            }
        )
    )
    plan = prepare_review(facts, preflight=preflight())
    assert plan.blockers
    assert select_review_effects(plan).code == "review_not_ready"


def test_whole_review_can_remove_created_target_with_exact_reviewed_owner_reversal():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
    from tests.reconciliation.test_identity import with_subjects
    from tests.reconciliation.test_refresh import two_items

    facts = two_items()
    first, second = facts.subjects
    proof = (
        reversal_facts()
        .subjects[0]
        .reversal_absence.model_copy(update={"produced": first.baseline.content})
    )
    first = first.model_copy(update={"incoming": None, "reversal_absence": proof})
    owner_before = ExactContent(data=b"Imported [[Notes/Opening]]\r\n")
    second = second.model_copy(
        update={
            "baseline": second.baseline.model_copy(update={"content": owner_before}),
            "current": second.current.model_copy(update={"content": owner_before}),
            "incoming": ExactContent(data=b"Restored owner\r\n"),
        }
    )
    facts = with_review_links(
        with_subjects(
            facts,
            (first, second),
            (
                facts.identity_inventory[0],
                facts.identity_inventory[1].model_copy(
                    update={"current": second.current}
                ),
            ),
        )
    )
    plan = prepare_review(facts, preflight=preflight())
    plan = resolve_review(
        plan, action(plan, domain="reversal", choice="reverse_absence")
    ).plan
    assert not plan.ready
    plan = resolve_review(
        plan, action(plan, plan.proposal.changes[1], decision_id="owner:reversal")
    ).plan
    assert plan.ready
    effects = select_review_effects(plan)
    assert effects.status == "selected"
    assert [(f.path, f.content.data) for f in effects.files] == [
        ("Notes/Second.md", b"Restored owner\r\n")
    ]
    assert effects.remove_paths == ("Notes/Opening.md",)
