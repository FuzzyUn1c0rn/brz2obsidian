"""Exact saved review values and freshly revalidated public resume authority."""

import pytest

from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links


def test_saved_opaque_review_round_trip_preserves_original_authority_but_load_is_unready():
    from brz2obsidian.core import (
        load_review,
        prepare_review,
        resolve_review,
        save_review,
    )

    facts = with_review_links(
        request(
            original=b"\xffbaseline\r\n",
            current=b"\xfflocal\x00",
            incoming=b"\xffsource\r\n",
        ),
        opaque_link_free=True,
    )
    facts = facts.model_copy(update={"proposal_id": "saved:opaque"})
    initial = prepare_review(facts, preflight=preflight())
    reviewed = resolve_review(initial, action(initial, choice="current")).plan
    assert reviewed.ready
    saved = save_review(reviewed)
    assert saved.status == "saved" and saved.record is not None
    decoded = load_review(saved.record)
    assert decoded.status == "loaded" and decoded.loaded.saved == saved.record
    assert decoded.ready is False and decoded.loaded.ready is False
    loaded = load_review(saved.record.model_dump_json().encode("utf-8"))
    assert loaded.status == "loaded" and not loaded.ready
    value = loaded.loaded
    assert value is not None and not value.ready
    assert value.readiness == "revalidation_required"
    assert value.saved.plan == reviewed
    change = value.saved.plan.proposal.changes[0]
    assert change.original.data == b"\xffbaseline\r\n"
    assert change.current.data == b"\xfflocal\x00" and change.result is None
    assert value.saved.plan.approvals[0].result.data == b"\xfflocal\x00"
    assert change.incoming.data == b"\xffsource\r\n"
    assert value.saved.plan.proposal.proposal_id == "saved:opaque"
    assert value.saved.plan.proposal.generation == 1
    assert value.saved.plan.actions == (action(initial, choice="current"),)
    assert (
        value.saved.plan.approvals[0].source_memory.reviewed_incoming.data
        == b"\xffsource\r\n"
    )


def ready_review():
    from brz2obsidian.core import prepare_review, resolve_review

    facts = with_review_links(request())
    initial = prepare_review(facts, preflight=preflight())
    result = resolve_review(initial, action(initial))
    assert result.status == "accepted" and result.plan.ready
    return result.plan


def test_raw_load_refuses_malformed_duplicate_future_and_inconsistent_records():
    import json

    from brz2obsidian.core import load_review, save_review

    record = save_review(ready_review()).record
    raw = record.model_dump_json()
    fields = json.loads(raw)
    unknown = dict(fields, unknown_interpretation="cannot ignore")
    missing = {key: value for key, value in fields.items() if key != "plan"}
    wrong_bytes = json.loads(raw)
    wrong_bytes["plan"]["facts"]["subjects"][0]["current"]["content"]["data"] = (
        "!not-base64!"
    )
    forged = json.loads(raw)
    forged["plan"]["ready"] = False
    cases = (
        (b"{", "invalid_record"),
        ("[" * 20000 + "0" + "]" * 20000, "invalid_record"),
        (b"\xff", "invalid_record"),
        (
            raw.replace('"brz2obsidian.saved-review"', '"future.saved-review"', 1),
            "unsupported_schema",
        ),
        (json.dumps(dict(fields, schema_version=2)), "unsupported_version"),
        (json.dumps(dict(fields, schema_version=True)), "invalid_record"),
        (json.dumps(dict(fields, schema_version=1.0)), "invalid_record"),
        (json.dumps(unknown), "invalid_record"),
        (json.dumps(missing), "invalid_record"),
        (
            raw.replace('"generation":1', '"generation":1,"generation":9', 1),
            "invalid_record",
        ),
        (
            raw.replace(
                '"schema_id":"brz2obsidian.review-history"',
                '"schema_id":"future.history"',
            ),
            "unsupported_schema",
        ),
        (json.dumps(wrong_bytes), "invalid_record"),
        (json.dumps(forged), "invalid_review"),
    )
    for offered, expected in cases:
        result = load_review(offered)
        assert result.status == "refused" and result.code == expected
        assert result.loaded is None and not result.ready
    assert load_review(raw).loaded.saved == record


def test_unchanged_resume_revalidates_without_new_proposal_generation_or_decisions():
    from brz2obsidian.core import load_review, resume_review, save_review

    original = ready_review()
    loaded = load_review(save_review(original).record.model_dump_json()).loaded
    resumed = resume_review(loaded, original.facts, preflight=preflight())
    assert resumed.status == "resumed" and resumed.code == "unchanged"
    assert resumed.ready and resumed.plan == original
    assert resumed.plan.proposal.generation == 1
    assert resumed.plan.history == original.history
    assert resumed.plan.actions == original.actions
    assert not loaded.ready and loaded.saved.plan == original


def test_changed_resume_delegates_selective_refresh_and_retains_original_epoch_history():
    from brz2obsidian.core import (
        load_review,
        prepare_review,
        resolve_review,
        resume_review,
        save_review,
    )
    from tests.reconciliation.test_refresh import edit_first, two_items

    original = prepare_review(with_review_links(two_items()), preflight=preflight())
    for change in original.proposal.changes:
        original = resolve_review(
            original, action(original, change, decision_id=change.item_id)
        ).plan
    assert original.ready and len(original.approvals) == 2
    unaffected = original.approvals[1]
    old_action = action(original, original.proposal.changes[1], decision_id="old:saved")
    loaded = load_review(save_review(original).record.model_dump_json()).loaded
    current = edit_first(original.facts)
    resumed = resume_review(loaded, current, preflight=preflight())
    assert resumed.status == "resumed" and resumed.code == "refreshed"
    assert not resumed.ready and resumed.plan.proposal.generation == 2
    assert resumed.plan.approvals == (unaffected,)
    assert resumed.plan.actions == original.actions
    assert resumed.plan.history.events[:-1] == original.history.events
    assert resumed.plan.history.events[-1].expected_generation == 1
    assert resumed.plan.history.events[-1].retained[0].origin_generation == 1
    assert resumed.plan.proposal.changes[0].current.data == b"Authored after review"
    assert resumed.plan.approvals[0].result.data == b"incoming\n"
    stale = resolve_review(resumed.plan, old_action)
    assert stale.status == "stale" and stale.code == "generation_changed"
    assert stale.plan.approvals == (unaffected,) and not stale.plan.ready
    again = load_review(save_review(resumed.plan).record.model_dump_json()).loaded
    restored = resume_review(again, current, preflight=preflight())
    assert restored.status == "resumed" and restored.plan == resumed.plan
    assert restored.plan.actions[1].expected_generation == 1
    assert not restored.ready


def test_forged_wrappers_and_invalid_resume_never_return_historically_ready_authority():
    from brz2obsidian.core import load_review, resume_review, save_review

    original = ready_review()
    saved = save_review(original).record
    loaded = load_review(saved.model_dump_json()).loaded
    for ready in (True, 0):
        forged = loaded.model_copy(update={"ready": ready})
        refused = resume_review(forged, original.facts, preflight=preflight())
        assert refused.status == "refused" and refused.code == "invalid_loaded"
        assert refused.plan is None and not refused.ready
    corrupt = original.model_copy(update={"history": None})
    unsaved = save_review(corrupt)
    assert unsaved.status == "refused" and unsaved.record is None
    assert unsaved.code == "invalid_review"
    changed = original.facts.model_copy(update={"proposal_id": "other:proposal"})
    wrong = resume_review(loaded, changed, preflight=preflight())
    assert wrong.status == "refused" and wrong.code == "wrong_proposal"
    assert wrong.plan is None and not wrong.ready
    stale = resume_review(
        loaded,
        original.facts,
        preflight=preflight().model_copy(update={"state_fingerprint": "changed"}),
    )
    assert stale.status == "stale" and stale.code == "generation_changed"
    assert stale.plan is None and not stale.ready
    ill_typed = original.facts.model_copy(update={"generation": True})
    invalid = resume_review(loaded, ill_typed, preflight=preflight())
    assert invalid.status == "refused" and invalid.code == "invalid_current_facts"
    assert invalid.plan is None and not invalid.ready
    # A constructed unready wrapper cannot authorize a forged historical cache.
    altered = loaded.model_copy(
        update={
            "saved": saved.model_copy(
                update={"plan": original.model_copy(update={"approvals": ()})}
            )
        }
    )
    invalid = resume_review(altered, original.facts, preflight=preflight())
    assert invalid.status == "refused" and invalid.code == "invalid_review"
    assert invalid.plan is None and not invalid.ready
    assert loaded.saved.plan.ready and not loaded.ready


@pytest.mark.parametrize("role", ("note", "configuration"))
@pytest.mark.parametrize("existence", ("present", "absent"))
def test_reloaded_keep_and_decline_memory_suppress_same_source_and_reopen_changed_source(
    role, existence
):
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import (
        load_review,
        prepare_review,
        resolve_review,
        resume_review,
        save_review,
    )
    from tests.reconciliation.test_absence import facts_for

    facts = facts_for(
        original=b"source-v1",
        current=b"authored",
        incoming=b"source-v2",
        existence=existence,
    )
    facts = with_review_links(
        facts.model_copy(
            update={
                "subjects": (
                    facts.subjects[0].model_copy(update={"output_role": role}),
                )
            }
        )
    )
    initial = prepare_review(facts, preflight=preflight())
    domain = (
        "restoration"
        if existence == "absent"
        else "configuration"
        if role == "configuration"
        else "text"
    )
    choice = "decline_restoration" if existence == "absent" else "current"
    original = resolve_review(
        initial, action(initial, domain=domain, choice=choice)
    ).plan
    assert original.ready and not original.approvals[0].source_accepted
    loaded = load_review(save_review(original).record.model_dump_json()).loaded
    memory = loaded.saved.plan.approvals[0].source_memory
    assert memory.reviewed_incoming.data == b"source-v2"
    assert memory.review_domain == (
        "configuration" if role == "configuration" else "content"
    )
    assert (memory.configuration_context is not None) == (role == "configuration")
    assert memory.choice == (
        "decline_restoration" if existence == "absent" else "keep_vault"
    )
    same = with_review_links(
        facts.model_copy(
            update={
                "generation": 2,
                "source_version_memory": (memory,),
                "link_context": None,
            }
        )
    )
    repeated = resume_review(loaded, same, preflight=preflight())
    assert repeated.status == "resumed" and repeated.ready
    change = repeated.plan.proposal.changes[0]
    assert change.provenance.rule == (
        "remembered_decline" if existence == "absent" else "remembered_keep"
    )
    if existence == "absent":
        assert change.result is None
    else:
        assert change.result.data == b"authored"
    assert repeated.plan.producer_facts.source_version_memory == (memory,)
    assert repeated.plan.actions == original.actions
    again = load_review(save_review(repeated.plan).record.model_dump_json()).loaded
    changed = with_review_links(
        same.model_copy(
            update={
                "generation": 3,
                "link_context": None,
                "subjects": (
                    same.subjects[0].model_copy(
                        update={"incoming": ExactContent(data=b"source-v3")}
                    ),
                ),
            }
        )
    )
    reopened = resume_review(again, changed, preflight=preflight())
    assert reopened.status == "resumed" and not reopened.ready
    assert reopened.plan.approvals == () and reopened.plan.requirements
    assert reopened.plan.proposal.changes[0].incoming.data == b"source-v3"
    assert reopened.plan.history.initial_facts == original.history.initial_facts
    assert reopened.loaded.saved.plan.producer_facts.source_version_memory == (memory,)


@pytest.mark.parametrize(
    "updates,blocker",
    (
        ({"operation_status": "active"}, "operation:active"),
        ({"operation_status": "incomplete"}, "operation:incomplete"),
        ({"operation_status": "recovery_required"}, "operation:recovery_required"),
        ({"state_status": "unsupported_version"}, "state:unsupported_version"),
    ),
)
def test_current_operation_or_record_gate_blocks_resume_of_historically_ready_review(
    updates, blocker
):
    from brz2obsidian.core import load_review, resume_review, save_review

    original = ready_review()
    loaded = load_review(save_review(original).record.model_dump_json()).loaded
    result = resume_review(
        loaded,
        original.facts.model_copy(update={"generation": 2}),
        preflight=preflight().model_copy(update=updates),
    )
    assert result.status == "resumed" and not result.ready
    assert result.plan.readiness == "refused" and blocker in result.plan.blockers
    assert loaded.saved.plan.ready and not loaded.ready
    assert result.plan.history.initial_preflight.operation_status == "idle"
    assert result.plan.proposal.generation == 2


def test_missing_available_content_cannot_resume_using_only_a_digest_or_locator():
    import json

    from brz2obsidian.core import load_review, resume_review, save_review

    original = ready_review()
    record = save_review(original).record
    fields = json.loads(record.model_dump_json())
    fields["plan"]["facts"]["subjects"][0]["baseline"] = {
        "status": "known",
        "content": None,
        "unavailable_digest": "oid:only",
    }
    refused = load_review(json.dumps(fields))
    assert refused.status == "refused" and refused.code == "invalid_record"
    assert refused.loaded is None and not refused.ready
    loaded = load_review(record.model_dump_json()).loaded
    subject = original.facts.subjects[0]
    missing = subject.baseline.model_copy(
        update={"content": None, "unavailable_digest": "oid:only"}
    )
    result = resume_review(
        loaded,
        original.facts.model_copy(
            update={
                "generation": 2,
                "subjects": (subject.model_copy(update={"baseline": missing}),),
            }
        ),
        preflight=preflight(),
    )
    assert result.status == "refused" and result.code == "invalid_current_facts"
    assert result.plan is None and not result.ready
    assert loaded.saved == record and loaded.saved.plan.ready


def test_record_round_trip_does_not_upgrade_output_format_or_invent_unknown_originals():
    from brz2obsidian.contracts import ContentVersion
    from brz2obsidian.core import (
        load_review,
        prepare_review,
        resume_review,
        save_review,
    )
    from tests.reconciliation.test_formats import operation

    facts = request(current=b"authored\xff", incoming=b"target format 7\n")
    subject = facts.subjects[0].model_copy(
        update={
            "baseline": ContentVersion(
                status="unknown",
                content=None,
                unavailable_digest="older:unavailable",
            )
        }
    )
    facts = with_review_links(
        facts.model_copy(
            update={
                "subjects": (subject,),
                "baseline_identity": facts.baseline_identity.model_copy(
                    update={"output_format": 6}
                ),
                "format_operation": operation(
                    "onboarding",
                    recorded_generation="unavailable",
                    established_baseline=None,
                ),
            }
        ),
        opaque_link_free=True,
    )
    original = prepare_review(facts, preflight=preflight())
    assert not original.ready and {r.domain for r in original.requirements} == {
        "format"
    }
    record = save_review(original).record
    assert record.schema_version == 1
    loaded = load_review(record.model_dump_json()).loaded
    result = resume_review(loaded, facts, preflight=preflight())
    assert result.status == "resumed" and not result.ready
    assert result.plan == original and result.plan.actions == ()
    assert result.plan.proposal.operation == "onboarding"
    assert result.plan.proposal.changes[0].original is None
    assert result.plan.proposal.changes[0].current.data == b"authored\xff"
    assert result.plan.facts.baseline_identity.output_format == 6
    assert result.plan.facts.incoming_identity.output_format == 7
    assert result.plan.facts.format_operation.established_baseline is None
