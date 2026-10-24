"""Exact preservation and source-facet memory through public reconciliation."""

import pytest

from brz2obsidian.contracts import CurrentContent, ExactContent
from brz2obsidian.core import reconcile
from tests.reconciliation.test_identity import with_subjects
from tests.reconciliation.test_proposals import request


def facts_for(
    *,
    original=b"original",
    current=b"original",
    incoming=b"changed",
    existence="present",
    facet="content",
):
    facts = request(original=original, current=current, incoming=incoming or b"")
    subject = facts.subjects[0].model_copy(
        update={
            "facet": facet,
            "current": CurrentContent(
                existence=existence,
                path="Notes/Opening.md",
                content=ExactContent(data=current) if existence == "present" else None,
            ),
            "incoming": None if incoming is None else ExactContent(data=incoming),
        }
    )
    entry = facts.identity_inventory[0].model_copy(
        update={"current": subject.current, "facet": subject.facet}
    )
    return with_subjects(facts, (subject,), (entry,))


@pytest.mark.parametrize(
    "facet,original,current",
    (
        ("content", b"source note", b"authored\xff\r\n"),
        ("attachment:payload", b"\x00original\xff", b"\x00local\xfe"),
    ),
)
def test_source_absent_notes_and_attachments_retain_exact_current_bytes(
    facet, original, current
):
    facts = facts_for(original=original, current=current, incoming=None, facet=facet)
    proposal = reconcile(facts)
    (change,) = proposal.changes
    assert change.disposition == "source_absent"
    assert change.current.data == change.result.data == current
    assert change.path == change.target_path == "Notes/Opening.md"
    assert change.incoming is None
    assert not change.requires_decision and proposal.ready
    assert change.preservation_review.kind == "source_absent"
    assert change.preservation_review.choices == ()
    assert proposal.source_version_memory == ()


def test_deliberate_deletion_suppresses_unchanged_source_and_changed_source_only_offers_restore():
    facts = facts_for(existence="absent", incoming=b"original")
    unchanged = reconcile(facts)
    (change,) = unchanged.changes
    assert change.disposition == "local_deleted" and change.result is None
    assert unchanged.ready and not change.requires_decision
    changed = reconcile(facts_for(existence="absent", incoming=b"changed"))
    (change,) = changed.changes
    assert change.disposition == "restoration" and change.result is None
    assert change.current is None and change.incoming.data == b"changed"
    assert change.preservation_review.default_choice == "decline_restoration"
    assert change.preservation_review.choices == (
        "decline_restoration",
        "restore_incoming",
    )
    assert change.requires_decision and not changed.ready
    for status in ("partial", "unreadable"):
        uncertain = reconcile(facts.model_copy(update={"inventory": status}))
        assert uncertain.changes[0].disposition == "refused" and not uncertain.ready
    missing = reconcile(facts.model_copy(update={"identity_inventory": ()}))
    assert missing.changes[0].disposition == "identity_resolution"


def choose(facts, proposal, choice, decision_id="preserve:1"):
    from brz2obsidian.contracts import PreservationDecision

    (change,) = proposal.changes
    return PreservationDecision(
        schema_id="brz2obsidian.preservation-decision",
        schema_version=1,
        decision_id=decision_id,
        proposal_id=facts.proposal_id,
        generation=facts.generation,
        collection_id=facts.incoming_identity.collection_id,
        module_id=facts.incoming_identity.module_id,
        item_id=change.item_id,
        facet=change.facet,
        choice=choice,
        review_domain="content",
        reviewed_source_version=change.source_version,
        reviewed_change_id=change.change_id,
        reviewed_assumptions=change.assumptions,
        provenance="explicit_user",
    )


def test_changed_declined_and_reconstructed_restoration_memory_sequence():
    from brz2obsidian.contracts import SourceVersionMemory

    facts = facts_for(existence="absent", incoming=b"abc")
    offered = reconcile(facts)
    declined = choose(facts, offered, "decline_restoration")
    reviewed = reconcile(
        facts.model_copy(update={"preservation_decisions": (declined,)})
    )
    assert reviewed.ready and reviewed.changes[0].disposition == "local_deleted"
    assert reviewed.changes[0].result is None
    (memory,) = reviewed.source_version_memory
    assert memory.reviewed_incoming.data == b"abc"
    assert (
        memory.source_version
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert memory.choice == "decline_restoration"
    assert memory.provenance.decision_id == "preserve:1"
    reconstructed = SourceVersionMemory.model_validate_json(memory.model_dump_json())
    again = facts.model_copy(
        update={
            "source_version_memory": (reconstructed,),
            "proposal_id": "review:later",
            "generation": 2,
        }
    )
    suppressed = reconcile(again)
    assert suppressed.ready and suppressed.changes[0].preservation_review.choices == ()
    assert suppressed.changes[0].preservation_review.matched_memory_ids == (
        "preserve:1",
    )
    assert suppressed.source_version_memory == (reconstructed,)
    newer = again.model_copy(
        update={
            "subjects": (
                again.subjects[0].model_copy(
                    update={"incoming": ExactContent(data=b"def")}
                ),
            )
        }
    )
    reopened = reconcile(newer)
    assert reopened.changes[0].disposition == "restoration" and not reopened.ready
    assert reopened.changes[0].result is None
    assert reopened.source_version_memory == (reconstructed,)
    repeated = reconcile(again)
    assert repeated == suppressed


def test_explicit_keep_vault_memory_survives_new_local_writing_but_reopens_relevant_source():
    from brz2obsidian.contracts import SourceVersionMemory

    facts = facts_for(current=b"authored\xff", incoming=b"abc")
    offered = reconcile(facts)
    assert offered.changes[0].disposition == "unresolved"
    kept = reconcile(
        facts.model_copy(
            update={"preservation_decisions": (choose(facts, offered, "keep_vault"),)}
        )
    )
    assert kept.ready and kept.changes[0].result.data == b"authored\xff"
    memory = SourceVersionMemory.model_validate(
        kept.source_version_memory[0].model_dump()
    )
    later = facts_for(current=b"more authored\xfe", incoming=b"abc").model_copy(
        update={"source_version_memory": (memory,)}
    )
    preserved = reconcile(later)
    assert preserved.ready and preserved.changes[0].result.data == b"more authored\xfe"
    assert preserved.changes[0].original.data == b"original"
    assert preserved.changes[0].preservation_review.provenance == "source_memory"
    changed = facts_for(current=b"more authored\xfe", incoming=b"def").model_copy(
        update={"source_version_memory": (memory,)}
    )
    assert reconcile(changed).changes[0].disposition == "unresolved"
    assert not reconcile(changed).ready


def test_already_current_bytes_do_not_offer_a_volatile_keep_choice():
    facts = facts_for(current=b"abc", incoming=b"abc")
    proposal = reconcile(facts)
    assert proposal.ready and proposal.changes[0].disposition == "no_change"
    assert proposal.changes[0].preservation_review.choices == ()


def test_memory_and_new_choices_have_distinct_provenance_and_known_decision_scopes():
    from pydantic import ValidationError

    from brz2obsidian.contracts import ReconciliationInput, SourceVersionMemory

    facts = facts_for(existence="absent", incoming=b"abc")
    decision = choose(facts, reconcile(facts), "decline_restoration")
    reviewed = reconcile(
        facts.model_copy(update={"preservation_decisions": (decision,)})
    )
    (memory,) = reviewed.source_version_memory
    for updates in (
        {"source_version_memory": (memory, memory)},
        {"preservation_decisions": (decision, decision)},
        {"source_version_memory": (memory,), "preservation_decisions": (decision,)},
        {
            "preservation_decisions": (
                decision.model_copy(update={"facet": "not-offered"}),
            )
        },
    ):
        with pytest.raises(ValidationError):
            ReconciliationInput.model_validate(facts.model_dump() | updates)
    raw = memory.model_dump()
    for updates in (
        {"schema_version": True},
        {"schema_version": 1.0},
        {"source_version": "0" * 64},
        {"reviewed_incoming": None},
        {"path": "arbitrary.md"},
        {"archive_version": "newer"},
        {"provenance": None},
    ):
        with pytest.raises(ValidationError):
            SourceVersionMemory.model_validate(raw | updates)
    with pytest.raises(ValueError, match="Duplicate field"):
        SourceVersionMemory.model_validate_json(
            memory.model_dump_json().replace(
                '"schema_version":1', '"schema_version":1,"schema_version":1'
            )
        )


def remembered(facts, choice="keep_vault", decision_id="keep:abc"):
    proposal = reconcile(facts)
    decision = choose(facts, proposal, choice, decision_id)
    return reconcile(
        facts.model_copy(update={"preservation_decisions": (decision,)})
    ).source_version_memory[0]


def test_memory_history_is_scoped_to_source_facet_and_relevant_version_without_chronology():
    from brz2obsidian.contracts import SourceVersionMemory

    base = facts_for(current=b"authored", incoming=b"abc")
    first = remembered(base)
    other_facet = remembered(
        facts_for(current=b"authored", incoming=b"abc", facet="attachment:payload"),
        decision_id="attachment:abc",
    )

    def review_in_context(decision_id, **scope):
        identity = base.baseline_identity.model_copy(update=scope)
        inventory = base.identity_inventory[0]
        context = base.model_copy(
            update={
                "baseline_identity": identity,
                "incoming_identity": identity,
                "identity_inventory": (
                    inventory.model_copy(
                        update={"identity": inventory.identity.model_copy(update=scope)}
                    ),
                ),
                "format_operation": base.format_operation.model_copy(
                    update={
                        "established_baseline": base.format_operation.established_baseline.model_copy(
                            update={"identity": identity}
                        )
                    }
                ),
            }
        )
        return remembered(context, decision_id=decision_id)

    other_module = review_in_context("other-module:abc", module_id="other-module")
    other_collection = review_in_context(
        "other-collection:abc", collection_id="other-collection"
    )
    unrelated = (other_facet, other_module, other_collection)
    independent = reconcile(
        base.model_copy(update={"source_version_memory": unrelated})
    )
    assert independent.changes[0].disposition == "unresolved"
    assert independent.changes[0].change_id == reconcile(base).changes[0].change_id
    assert independent.source_version_memory == unrelated
    newer = facts_for(current=b"authored", incoming=b"def").model_copy(
        update={"source_version_memory": (first,) + unrelated}
    )
    offered = reconcile(newer)
    assert offered.changes[0].preservation_review.choices == ("keep_vault",)
    decision = choose(newer, offered, "keep_vault", "keep:def")
    reviewed = reconcile(
        newer.model_copy(update={"preservation_decisions": (decision,)})
    )
    assert len(reviewed.source_version_memory) == 5
    assert reviewed.source_version_memory[:4] == (first,) + unrelated
    history = tuple(
        SourceVersionMemory.model_validate_json(m.model_dump_json())
        for m in reviewed.source_version_memory
    )
    older = base.model_copy(
        update={
            "proposal_id": "scoped:older",
            "generation": 9,
            "source_version_memory": history,
            "format_operation": base.format_operation.model_copy(
                update={"target_source_version": "archive:older-scoped"}
            ),
        }
    )
    retained = reconcile(older)
    assert retained.ready and retained.changes[0].result.data == b"authored"
    equivalent = reconcile(
        base.model_copy(update={"source_version_memory": tuple(reversed(history))})
    )
    assert retained.changes[0].change_id == equivalent.changes[0].change_id
    assert retained.changes[0].preservation_review.matched_memory_ids == ("keep:abc",)
    assert retained.source_version_memory == history
    assert retained.local_changes == (retained.changes[0].subject_id,)
    absent = older.model_copy(
        update={"subjects": (older.subjects[0].model_copy(update={"incoming": None}),)}
    )
    assert reconcile(absent).changes[0].disposition == "source_absent"
    assert reconcile(absent).source_version_memory == history


def test_source_absence_and_reference_change_are_independent_exact_comparisons():
    from brz2obsidian.contracts import IdentityTargetFacts
    from tests.reconciliation.test_identity import inventory_item

    facts = facts_for(
        original=b"\x00source",
        current=b"\x00local",
        incoming=None,
        facet="attachment:payload",
    )
    reference = facts.subjects[0].model_copy(
        update={
            "item_id": "reference-note",
            "facet": "imported-references",
            "path": "Reference.md",
            "baseline": facts.subjects[0].baseline.model_copy(
                update={"content": ExactContent(data=b"old reference")}
            ),
            "current": CurrentContent(
                existence="present",
                path="Reference.md",
                content=ExactContent(data=b"old reference"),
            ),
            "incoming": ExactContent(data=b"new reference"),
            "source_target": IdentityTargetFacts(
                normalized_path="reference.md", containment="contained", status="safe"
            ),
        }
    )
    facts = with_subjects(
        facts,
        (facts.subjects[0], reference),
        facts.identity_inventory
        + (
            inventory_item(
                "ref",
                "reference-note",
                "Reference.md",
                b"old reference",
                facet="imported-references",
            ),
        ),
    )
    result = reconcile(facts)
    retained, changed = result.changes
    assert (
        retained.disposition == "source_absent" and retained.result.data == b"\x00local"
    )
    assert retained.preservation_review.choices == ()
    assert (
        changed.disposition == "compatible" and changed.result.data == b"new reference"
    )
    assert changed.requires_decision and not result.ready
    assert result.source_version_memory == ()


def test_remembered_content_never_approves_independent_identity_format_or_safety_gates():
    from brz2obsidian.contracts import ContentVersion, IdentityTargetFacts

    base = facts_for(current=b"authored", incoming=b"abc")
    memory = remembered(base)
    facts = base.model_copy(update={"source_version_memory": (memory,)})
    (subject,) = facts.subjects
    for updates, disposition, finding in (
        ({"identity_inventory": ()}, "identity_resolution", None),
        ({"inventory": "partial"}, "refused", "inventory_uncertain"),
        (
            {
                "safety_facts": tuple(
                    f.model_copy(update={"status": "recovery_required"})
                    if f.kind == "operation"
                    else f
                    for f in facts.safety_facts
                )
            },
            "refused",
            "unsafe_assumption",
        ),
        (
            {
                "identity_inventory": (
                    facts.identity_inventory[0].model_copy(
                        update={
                            "target": IdentityTargetFacts(
                                normalized_path="notes/opening.md",
                                containment="outside",
                                status="safe",
                            )
                        }
                    ),
                )
            },
            "refused",
            "unsafe_identity_target",
        ),
        (
            {
                "incoming_identity": facts.incoming_identity.model_copy(
                    update={"settings_digest": "new-settings"}
                )
            },
            "refused",
            "profile_transition_required",
        ),
        (
            {
                "format_operation": facts.format_operation.model_copy(
                    update={"kind": "onboarding", "target_source_version": "source:a"}
                )
            },
            "unresolved",
            None,
        ),
        (
            {
                "subjects": (
                    subject.model_copy(update={"output_role": "configuration"}),
                )
            },
            "unresolved",
            None,
        ),
        (
            {
                "subjects": (
                    subject.model_copy(
                        update={
                            "baseline": ContentVersion(
                                status="unknown",
                                content=None,
                                unavailable_digest="history:missing",
                            )
                        }
                    ),
                )
            },
            "unresolved",
            None,
        ),
        (
            {
                "subjects": (
                    subject.model_copy(
                        update={
                            "current": CurrentContent(
                                existence="unknown",
                                path="Notes/Opening.md",
                                content=None,
                            )
                        }
                    ),
                ),
                "identity_inventory": (
                    facts.identity_inventory[0].model_copy(
                        update={
                            "current": CurrentContent(
                                existence="unknown",
                                path="Notes/Opening.md",
                                content=None,
                            )
                        }
                    ),
                ),
            },
            "refused",
            "current_unavailable",
        ),
    ):
        proposal = reconcile(facts.model_copy(update=updates))
        (change,) = proposal.changes
        assert change.disposition == disposition and not proposal.ready, updates
        assert change.result is None and proposal.source_version_memory == (memory,)
        if change.format_review is not None:
            assert (
                change.preservation_review is None
                or change.preservation_review.choices == ()
            )
        if finding:
            assert finding in {f.code for f in proposal.findings}
        if (
            "subjects" in updates
            and updates["subjects"][0].baseline.status == "unknown"
        ):
            assert change.original is None and not change.format_review.original_known


def test_preservation_choice_is_current_generation_and_cannot_change_its_offered_kind():
    facts = facts_for(existence="absent", incoming=b"abc")
    offered = reconcile(facts)
    decision = choose(facts, offered, "decline_restoration")
    for updates in (
        {"generation": 2},
        {"proposal_id": "another-review"},
        {
            "subjects": (
                facts.subjects[0].model_copy(
                    update={"incoming": ExactContent(data=b"def")}
                ),
            )
        },
    ):
        stale = reconcile(
            facts.model_copy(update=updates | {"preservation_decisions": (decision,)})
        )
        assert stale.changes[0].disposition == "stale" and not stale.ready
        assert stale.changes[0].result is None and stale.source_version_memory == ()
        assert "stale_preservation_decision" in {f.code for f in stale.findings}
    unsafe = choose(facts, offered, "keep_vault")
    refused = reconcile(facts.model_copy(update={"preservation_decisions": (unsafe,)}))
    assert refused.changes[0].disposition == "refused" and not refused.ready
    assert refused.source_version_memory == ()
    assert "unsafe_preservation_decision" in {f.code for f in refused.findings}


def test_unsafe_optional_rename_cannot_borrow_remembered_content_approval():
    from tests.reconciliation.test_identity import inventory_item, rename_decision

    facts = facts_for(current=b"authored", incoming=b"abc")
    memory = remembered(facts)
    facts = facts.model_copy(
        update={
            "source_version_memory": (memory,),
            "identity_inventory": (
                inventory_item("moved", "entry:opening", "My.md", b"authored"),
                inventory_item(
                    "other", "other:item", "Notes/Opening.md/child.md", b"unrelated"
                ),
            ),
        }
    )
    kept = reconcile(facts)
    assert kept.ready and kept.changes[0].target_path == "My.md"
    assert kept.changes[0].rename_review.status == "blocked"
    decision = rename_decision(facts, kept.changes[0].rename_review, "source_path")
    unsafe = reconcile(facts.model_copy(update={"rename_decisions": (decision,)}))
    assert unsafe.changes[0].disposition == "refused" and not unsafe.ready
    assert unsafe.changes[0].result is None
    assert unsafe.source_version_memory == (memory,)


def test_historical_deletion_policy_does_not_invalidate_an_existing_file_choice():
    facts = facts_for(current=b"authored", incoming=b"abc")
    deleted = facts_for(existence="absent", incoming=b"abc")
    memory = remembered(deleted, "decline_restoration", "decline:abc")
    before = reconcile(facts)
    after = reconcile(facts.model_copy(update={"source_version_memory": (memory,)}))
    assert before.changes[0].change_id == after.changes[0].change_id
    assert after.changes[0].disposition == "unresolved" and not after.ready
    assert after.changes[0].preservation_review.matched_memory_ids == ()
    assert after.source_version_memory == (memory,)


def test_whole_file_keep_clears_a_different_structured_candidate():
    from tests.reconciliation.test_structure import structured_request

    original = b'---\npriority: 1\nowner: "source"\n---\nBody.\n'
    current = b'---\npriority: 1\nowner: "local"\n---\nBody.\n'
    incoming = b'---\npriority: 2\nowner: "source"\n---\nBody.\n'
    facts = structured_request(original, current, incoming)
    offered = reconcile(facts)
    assert (
        offered.changes[0].result.data
        == b'---\npriority: 2\nowner: "local"\n---\nBody.\n'
    )
    assert offered.changes[0].structure_result is not None
    decision = choose(facts, offered, "keep_vault")
    kept = reconcile(facts.model_copy(update={"preservation_decisions": (decision,)}))
    assert kept.ready and kept.changes[0].result.data == current
    assert kept.changes[0].structure_result is None
    assert len(kept.source_version_memory) == 1


def test_memory_keeps_opaque_or_overlapping_bytes_but_never_trusts_contradictory_structure():
    from tests.reconciliation.test_structure import structured_request

    original = b'---\nsource_item_id: "entry:opening"\npriority: 1\n---\nBody.\n'
    current = b'---\nsource_item_id: "entry:opening"\npriority: 2\n---\nBody.\n'
    incoming = b'---\nsource_item_id: "entry:opening"\npriority: 3\n---\nBody.\n'
    base = structured_request(original, current, incoming)
    memory = remembered(base)
    for local in (
        current,
        b"---\npriority: 2\npriority: 4\n---\nAuthored.\n",
        b"\xff\x00Opaque local bytes",
    ):
        facts = structured_request(original, local, incoming).model_copy(
            update={"source_version_memory": (memory,)}
        )
        preserved = reconcile(facts)
        assert preserved.ready and preserved.changes[0].result.data == local
        assert preserved.changes[0].structure_result is None
    changed_identity = structured_request(
        original, current.replace(b"entry:opening", b"other:item"), incoming
    )
    missing_identity = structured_request(
        original, b"---\npriority: 2\n---\nBody.\n", incoming
    )
    wrong_binding = base.model_copy(
        update={
            "subjects": (
                base.subjects[0].model_copy(
                    update={
                        "structure": base.subjects[0].structure.model_copy(
                            update={"current": base.subjects[0].structure.incoming}
                        )
                    }
                ),
            )
        }
    )
    for unsafe, rule in (
        (changed_identity, "structure_identity_conflict"),
        (missing_identity, "structure_identity_conflict"),
        (wrong_binding, "structure_unbound"),
    ):
        refused = reconcile(
            unsafe.model_copy(update={"source_version_memory": (memory,)})
        )
        assert not refused.ready and refused.changes[0].result is None
        assert refused.changes[0].provenance.rule == rule
        assert refused.source_version_memory == (memory,)


def test_reconstructed_memory_requires_sufficient_subject_scoped_review_provenance():
    import json

    from pydantic import ValidationError

    from brz2obsidian.contracts import SourceVersionMemory

    facts = facts_for(current=b"authored\xff", incoming=b"abc")
    valid = remembered(facts)
    raw = json.loads(valid.model_dump_json())
    assumptions = raw["provenance"]["reviewed_assumptions"]
    malformed = (
        [],
        [
            {
                "key": "unrelated",
                "kind": "history",
                "fingerprint": "0" * 64,
                "depends_on": [],
            }
        ],
        [a for a in assumptions if not a["key"].endswith(":incoming")],
        [
            a | {"kind": "current"} if a["key"].endswith(":incoming") else a
            for a in assumptions
        ],
        [
            a | {"fingerprint": "unknown"} if a["key"].endswith(":current") else a
            for a in assumptions
        ],
        [
            a
            for a in assumptions
            if not (a["key"].startswith("safety:") and a["kind"] == "operation")
        ],
        [a for a in assumptions if not a["key"].startswith("identity-candidate:")],
    )
    for history in malformed:
        candidate = raw | {
            "provenance": raw["provenance"] | {"reviewed_assumptions": history}
        }
        with pytest.raises(ValidationError):
            SourceVersionMemory.model_validate_json(json.dumps(candidate))
    for changed_scope in (
        {"item_id": "another-item"},
        {"facet": "attachment:payload"},
        {"module_id": "another-module"},
        {"collection_id": "another-collection"},
    ):
        with pytest.raises(ValidationError):
            SourceVersionMemory.model_validate_json(json.dumps(raw | changed_scope))
    historical = assumptions + [
        {
            "key": "legacy:context",
            "kind": "history",
            "fingerprint": "1" * 64,
            "depends_on": [],
        }
    ]
    reconstructed = SourceVersionMemory.model_validate_json(
        json.dumps(
            raw
            | {"provenance": raw["provenance"] | {"reviewed_assumptions": historical}}
        )
    )
    later = facts_for(current=b"more writing\xfe", incoming=b"abc").model_copy(
        update={"source_version_memory": (reconstructed,)}
    )
    result = reconcile(later)
    assert result.ready and result.changes[0].result.data == b"more writing\xfe"
    assert result.changes[0].original.data == b"original"
    assert result.source_version_memory == (reconstructed,)
    assert (
        result.source_version_memory[0].provenance.reviewed_assumptions[-1].key
        == "legacy:context"
    )
