"""Identity follows validated inventory facts at the public reconciliation seam."""

import pytest

from brz2obsidian.contracts import (
    IdentityInventoryItem,
    IdentityTargetFacts,
    ImportedItemIdentity,
)
from brz2obsidian.core import reconcile
from tests.reconciliation.test_proposals import request


def inventory_item(
    entry_id,
    item_id,
    path,
    content,
    *,
    collection="folio:collection",
    module="synthetic-folio",
    title="Opening",
    state="valid",
    facet="content",
):
    from brz2obsidian.contracts import CurrentContent, ExactContent

    return IdentityInventoryItem(
        facet=facet,
        entry_id=entry_id,
        identity_state=state,
        identity=ImportedItemIdentity(
            collection_id=collection, module_id=module, item_id=item_id
        )
        if state == "valid"
        else None,
        raw_identity=None
        if state in ("valid", "missing")
        else "invalid imported identity",
        title=title,
        current=CurrentContent(
            existence="present", path=path, content=ExactContent(data=content)
        ),
        target=IdentityTargetFacts(
            normalized_path=path.casefold(), containment="contained", status="safe"
        ),
    )


def with_subjects(facts, subjects, inventory):
    """Bind independently declared originals to the required format evidence."""
    from brz2obsidian.contracts import FormatBaselineOutput

    baseline = facts.format_operation.established_baseline.model_copy(
        update={
            "outputs": tuple(
                FormatBaselineOutput(
                    item_id=subject.item_id,
                    facet=subject.facet,
                    content=subject.baseline.content,
                )
                for subject in subjects
                if subject.baseline.status == "known"
            ),
        }
    )
    return facts.model_copy(
        update={
            "subjects": subjects,
            "identity_inventory": inventory,
            "format_operation": facts.format_operation.model_copy(
                update={"established_baseline": baseline}
            ),
        }
    )


def test_unique_identity_follows_exact_moved_path_and_offers_source_rename_separately():
    facts = request()
    moved = inventory_item(
        "moved-entry", "entry:opening", "My folder/Author Name.md", b"original\r\n"
    )
    result = reconcile(facts.model_copy(update={"identity_inventory": (moved,)}))
    (change,) = result.changes
    assert change.path == "My folder/Author Name.md"
    assert change.target_path == "My folder/Author Name.md"
    assert change.result.data == b"incoming\n"
    assert change.identity_review.status == "matched"
    assert change.identity_review.selected_entry_id == "moved-entry"
    assert change.rename_review.current_path == "My folder/Author Name.md"
    assert change.rename_review.source_path == "Notes/Opening.md"
    assert change.rename_review.status == "offered"
    assert not change.rename_review.requires_decision
    assert not result.ready


def test_equal_title_and_path_from_another_collection_or_module_never_select_identity():
    facts = request()
    for change in (
        {"collection": "other:collection"},
        {"module": "other-module"},
        {"item_id": "other:item"},
    ):
        values = {
            "entry_id": "lookalike",
            "item_id": "entry:opening",
            "path": "Notes/Opening.md",
            "content": b"unrelated exact bytes",
        } | change
        lookalike = inventory_item(**values)
        result = reconcile(
            facts.model_copy(update={"identity_inventory": (lookalike,)})
        )
        (change,) = result.changes
        assert change.disposition == "identity_resolution" and change.result is None
        assert change.identity_review.status == "unresolved"
        assert change.identity_review.selected_entry_id is None
        assert not change.identity_review.candidates[0].eligible
        assert (
            change.identity_review.candidates[0].current.content.data
            == b"unrelated exact bytes"
        )
        assert not result.ready


def test_missing_malformed_inconsistent_and_duplicate_identities_offer_review_without_guessing():
    facts = request()
    for state in ("missing", "malformed", "inconsistent"):
        item = inventory_item(
            "unidentified",
            "entry:opening",
            "Notes/Opening.md",
            b"local\xff",
            state=state,
        )
        result = reconcile(facts.model_copy(update={"identity_inventory": (item,)}))
        (change,) = result.changes
        assert change.disposition == "identity_resolution" and change.result is None
        assert change.identity_review.repair_required
        (candidate,) = change.identity_review.candidates
        assert candidate.entry_id == "unidentified" and candidate.eligible
        assert candidate.current.content.data == b"local\xff"
    duplicates = (
        inventory_item("copy-a", "entry:opening", "A.md", b"copy A"),
        inventory_item("copy-b", "entry:opening", "B.md", b"copy B"),
    )
    result = reconcile(facts.model_copy(update={"identity_inventory": duplicates}))
    review = result.changes[0].identity_review
    assert review.reason == "duplicate_identity" and review.selected_entry_id is None
    assert {c.current.content.data for c in review.candidates} == {b"copy A", b"copy B"}
    assert result.readiness == "review_required"
    for status in ("partial", "unreadable"):
        uncertain = reconcile(
            facts.model_copy(update={"identity_inventory": (), "inventory": status})
        )
        assert uncertain.changes[0].disposition == "refused"
        assert uncertain.findings[0].code == "inventory_uncertain"


def test_identity_blocked_item_leaves_unrelated_valid_item_independently_inspectable():
    from brz2obsidian.contracts import ContentVersion, CurrentContent, ExactContent

    facts = request()
    other = facts.subjects[0].model_copy(
        update={
            "item_id": "item:second",
            "title": "Second",
            "path": "Second.md",
            "baseline": ContentVersion(
                status="known",
                content=ExactContent(data=b"second old"),
                unavailable_digest=None,
            ),
            "current": CurrentContent(
                existence="present",
                path="Second.md",
                content=ExactContent(data=b"second old"),
            ),
            "incoming": ExactContent(data=b"second new"),
            "source_target": IdentityTargetFacts(
                normalized_path="second.md", containment="contained", status="safe"
            ),
        }
    )
    second = inventory_item(
        "second", "item:second", "Second.md", b"second old", title="Second"
    )
    facts = with_subjects(facts, (facts.subjects[0], other), (second,))
    result = reconcile(facts)
    blocked, valid = result.changes
    assert blocked.disposition == "identity_resolution"
    assert valid.disposition == "compatible" and valid.result.data == b"second new"
    assert valid.path == "Second.md" and valid.current.data == b"second old"
    assert valid.identity_review.status == "matched"
    independent = reconcile(
        facts.model_copy(update={"subjects": (other,), "identity_inventory": (second,)})
    ).changes[0]
    assert (
        valid.subject_id == independent.subject_id
        and valid.change_id == independent.change_id
    )
    assert not result.ready


def test_selected_targets_require_safe_containment_exact_normalization_and_no_collisions():
    from brz2obsidian.contracts import ExactContent

    facts = request()
    valid = facts.identity_inventory[0]
    for target in (
        IdentityTargetFacts(
            normalized_path="forged-path.md", containment="contained", status="safe"
        ),
        IdentityTargetFacts(
            normalized_path="notes/opening.md", containment="outside", status="safe"
        ),
        IdentityTargetFacts(
            normalized_path="notes/opening.md", containment="unknown", status="safe"
        ),
        IdentityTargetFacts(
            normalized_path="notes/opening.md",
            containment="contained",
            status="unknown",
        ),
        IdentityTargetFacts(
            normalized_path="notes/opening.md", containment="contained", status="unsafe"
        ),
    ):
        result = reconcile(
            facts.model_copy(
                update={
                    "identity_inventory": (valid.model_copy(update={"target": target}),)
                }
            )
        )
        (change,) = result.changes
        assert change.disposition == "refused" and change.result is None
        assert result.findings[0].code == "unsafe_identity_target"
    for path in ("NOTES/Opening.MD", "Notes", "Notes/Opening.md/child.md"):
        colliding = inventory_item("collision", "other:item", path, b"unrelated")
        result = reconcile(
            facts.model_copy(update={"identity_inventory": (valid, colliding)})
        )
        assert result.changes[0].disposition == "refused" and not result.ready
    for path in ("CON.md", "folder/trailing. ", "bad?.md"):
        unsafe = inventory_item("unsafe", "entry:opening", path, b"original\r\n")
        result = reconcile(facts.model_copy(update={"identity_inventory": (unsafe,)}))
        assert result.changes[0].disposition == "refused"
    # The asserted subject bytes cannot contradict the selected observed file.
    stale = valid.model_copy(
        update={
            "current": valid.current.model_copy(
                update={"content": ExactContent(data=b"changed after scan")}
            )
        }
    )
    result = reconcile(facts.model_copy(update={"identity_inventory": (stale,)}))
    assert result.findings[0].code == "current_inventory_mismatch"


def test_unrelated_inventory_edits_do_not_change_a_uniquely_matched_subject():
    facts = request()
    unrelated = inventory_item(
        "unknown-other",
        "other",
        "Unrelated.md",
        b"authored first",
        state="malformed",
        title="Other",
    )
    before = reconcile(
        facts.model_copy(
            update={"identity_inventory": facts.identity_inventory + (unrelated,)}
        )
    ).changes[0]
    changed = unrelated.model_copy(
        update={
            "current": unrelated.current.model_copy(
                update={
                    "content": unrelated.current.content.model_copy(
                        update={"data": b"authored later"}
                    )
                }
            )
        }
    )
    after = reconcile(
        facts.model_copy(
            update={"identity_inventory": facts.identity_inventory + (changed,)}
        )
    ).changes[0]
    assert before.change_id == after.change_id
    assert before.assumptions == after.assumptions


def association(facts, review, entry_id, disassociate=()):
    from brz2obsidian.contracts import IdentityAssociationDecision

    return IdentityAssociationDecision(
        facet=facts.subjects[0].facet,
        schema_id="brz2obsidian.identity-association-decision",
        schema_version=1,
        decision_id="identity-choice:1",
        proposal_id=facts.proposal_id,
        generation=facts.generation,
        collection_id=facts.incoming_identity.collection_id,
        module_id=facts.incoming_identity.module_id,
        item_id=facts.subjects[0].item_id,
        selected_entry_id=entry_id,
        disassociate_entry_ids=disassociate,
        reviewed_assumptions=review.assumptions
        + tuple(
            a
            for candidate in review.candidates
            if candidate.entry_id in (entry_id,) + disassociate
            for a in candidate.assumptions
        ),
        provenance="explicit_user",
    )


def test_explicit_association_proposes_bound_repairs_without_claiming_duplicate_bytes_were_fixed():
    facts = request()
    duplicates = (
        inventory_item("copy-a", "entry:opening", "A.md", b"copy A"),
        inventory_item("copy-b", "entry:opening", "B.md", b"copy B"),
    )
    facts = facts.model_copy(update={"identity_inventory": duplicates})
    review = reconcile(facts).changes[0].identity_review
    selected = association(facts, review, "copy-b", ("copy-a",))
    result = reconcile(facts.model_copy(update={"association_decisions": (selected,)}))
    (change,) = result.changes
    assert change.disposition == "identity_resolution" and change.result is None
    assert change.current.data == b"copy B" and change.path == "B.md"
    assert change.identity_review.status == "association_proposed"
    assert change.identity_review.selected_entry_id == "copy-b"
    assert change.identity_review.disassociate_entry_ids == ("copy-a",)
    assert change.identity_review.decision_id == "identity-choice:1"
    assert change.identity_review.provenance == "explicit_user"
    assert change.identity_review.repair_required and not result.ready
    assert {c.current.content.data for c in change.identity_review.candidates} == {
        b"copy A",
        b"copy B",
    }
    # Declaring a selection never makes an omitted duplicate repair complete.
    incomplete = association(facts, review, "copy-b")
    incomplete_result = reconcile(
        facts.model_copy(update={"association_decisions": (incomplete,)})
    )
    assert not incomplete_result.ready
    assert incomplete_result.findings[0].code == "identity_repair_incomplete"
    # Independent outer inventory can later establish the actual repaired identities.
    cleared = duplicates[0].model_copy(
        update={"identity_state": "missing", "identity": None}
    )
    repaired = facts.model_copy(
        update={
            "identity_inventory": (cleared, duplicates[1]),
            "subjects": (
                facts.subjects[0].model_copy(update={"current": duplicates[1].current}),
            ),
        }
    )
    repaired_change = reconcile(repaired).changes[0]
    assert repaired_change.identity_review.status == "matched"
    assert not repaired_change.identity_review.repair_required


def test_association_decisions_revalidate_generation_candidate_and_exact_current_assumptions():
    facts = request()
    missing = inventory_item(
        "candidate", "entry:opening", "Moved.md", b"authored\xff", state="missing"
    )
    facts = facts.model_copy(update={"identity_inventory": (missing,)})
    review = reconcile(facts).changes[0].identity_review
    decision = association(facts, review, "candidate")
    for updates in ({"generation": 2}, {"proposal_id": "another-proposal"}):
        changed = reconcile(
            facts.model_copy(update=updates | {"association_decisions": (decision,)})
        )
        assert changed.changes[0].disposition == "stale" and not changed.ready
        assert changed.findings[0].code == "stale_identity_decision"
    edited = missing.model_copy(
        update={
            "current": missing.current.model_copy(
                update={
                    "content": missing.current.content.model_copy(
                        update={"data": b"edited after review"}
                    )
                }
            )
        }
    )
    changed = reconcile(
        facts.model_copy(
            update={
                "identity_inventory": (edited,),
                "association_decisions": (decision,),
            }
        )
    )
    assert changed.changes[0].identity_review.status == "stale"
    assert changed.changes[0].result is None
    for selected in ("unknown-entry", "unrelated-valid"):
        unrelated = inventory_item(
            "unrelated-valid", "other:item", "Other.md", b"protected", title="Other"
        )
        expanded = facts.model_copy(update={"identity_inventory": (missing, unrelated)})
        offered = reconcile(expanded).changes[0].identity_review
        invalid = association(expanded, offered, selected)
        result = reconcile(
            expanded.model_copy(update={"association_decisions": (invalid,)})
        )
        assert result.changes[0].disposition == "refused" and not result.ready
        assert result.findings[0].code == "unsafe_identity_decision"


def test_explicit_association_cannot_bypass_unsafe_candidate_target_facts():
    facts = request()
    item = inventory_item(
        "candidate", "entry:opening", "Candidate.md", b"local", state="missing"
    )
    item = item.model_copy(
        update={"target": item.target.model_copy(update={"containment": "outside"})}
    )
    facts = facts.model_copy(update={"identity_inventory": (item,)})
    decision = association(
        facts, reconcile(facts).changes[0].identity_review, "candidate"
    )
    result = reconcile(facts.model_copy(update={"association_decisions": (decision,)}))
    assert (
        result.changes[0].disposition == "refused" and result.changes[0].result is None
    )
    assert result.findings[0].code == "unsafe_identity_target"


def rename_decision(facts, review, choice):
    from brz2obsidian.contracts import RenamePathDecision

    return RenamePathDecision(
        facet=facts.subjects[0].facet,
        schema_id="brz2obsidian.rename-decision",
        schema_version=1,
        decision_id="rename-choice:1",
        proposal_id=facts.proposal_id,
        generation=facts.generation,
        collection_id=facts.incoming_identity.collection_id,
        module_id=facts.incoming_identity.module_id,
        item_id=facts.subjects[0].item_id,
        choice=choice,
        reviewed_assumptions=review.assumptions,
        provenance="explicit_user",
    )


def test_source_rename_is_a_distinct_current_generation_choice_and_decline_preserves_path():
    facts = request()
    moved = inventory_item(
        "moved", "entry:opening", "Authored/Current.md", b"original\r\n"
    )
    facts = facts.model_copy(update={"identity_inventory": (moved,)})
    offered = reconcile(facts).changes[0].rename_review
    change_ids = []
    for choice, status, expected in (
        ("keep_path", "declined", "Authored/Current.md"),
        ("source_path", "accepted", "Notes/Opening.md"),
    ):
        decision = rename_decision(facts, offered, choice)
        result = reconcile(facts.model_copy(update={"rename_decisions": (decision,)}))
        (change,) = result.changes
        assert change.path == "Authored/Current.md"
        assert change.target_path == expected
        assert (
            change.current.data == b"original\r\n"
            and change.result.data == b"incoming\n"
        )
        assert change.rename_review.status == status
        assert change.rename_review.decision_id == "rename-choice:1"
        assert change.rename_review.provenance == "explicit_user"
        change_ids.append(change.change_id)
    assert change_ids[0] != change_ids[1]
    stale = reconcile(
        facts.model_copy(update={"generation": 2, "rename_decisions": (decision,)})
    )
    assert stale.changes[0].disposition == "stale" and not stale.ready
    assert stale.changes[0].rename_review.status == "stale"
    assert stale.findings[0].code == "stale_rename_decision"


def test_renames_and_selected_associations_cannot_override_collisions_or_normalization():
    facts = request()
    moved = inventory_item("moved", "entry:opening", "Authored.md", b"original\r\n")
    collision = inventory_item(
        "occupied", "other:item", "NOTES/OPENING.MD", b"protected"
    )
    for inventory, target in (
        ((moved, collision), facts.subjects[0].source_target),
        (
            (moved,),
            IdentityTargetFacts(
                normalized_path="forged.md", containment="contained", status="safe"
            ),
        ),
        (
            (moved,),
            IdentityTargetFacts(
                normalized_path="notes/opening.md", containment="outside", status="safe"
            ),
        ),
    ):
        subject = facts.subjects[0].model_copy(update={"source_target": target})
        current = facts.model_copy(
            update={"subjects": (subject,), "identity_inventory": inventory}
        )
        offered = reconcile(current).changes[0].rename_review
        assert offered.status == "blocked"
        accepted = rename_decision(current, offered, "source_path")
        result = reconcile(current.model_copy(update={"rename_decisions": (accepted,)}))
        assert (
            result.changes[0].disposition == "refused"
            and result.changes[0].result is None
        )
        assert result.findings[0].code == "unsafe_rename_target"
        declined = rename_decision(current, offered, "keep_path")
        preserved = reconcile(
            current.model_copy(update={"rename_decisions": (declined,)})
        ).changes[0]
        assert (
            preserved.target_path == "Authored.md"
            and preserved.result.data == b"incoming\n"
        )
    # Windows-equivalent Unicode filenames collide independently of supplied keys.
    named = inventory_item("moved", "entry:opening", "Caf\u00e9.md", b"original\r\n")
    equivalent = inventory_item(
        "duplicate-path", "other:item", "CAFE\u0301.md", b"unrelated"
    )
    assert (
        reconcile(facts.model_copy(update={"identity_inventory": (named, equivalent)}))
        .changes[0]
        .disposition
        == "refused"
    )


def test_identity_decisions_and_inventory_are_closed_immutable_values_with_no_arbitrary_path_patch():
    import pytest
    from pydantic import ValidationError

    from brz2obsidian.contracts import ReconciliationInput

    facts = request()
    fields = facts.model_dump()
    missing = fields.copy()
    del missing["identity_inventory"]
    with pytest.raises(ValidationError):
        ReconciliationInput.model_validate(missing)
    with pytest.raises(ValidationError):
        ReconciliationInput.model_validate(
            fields | {"identity_inventory": facts.identity_inventory * 2}
        )
    for identity_state, identity in (
        ("valid", None),
        ("missing", facts.identity_inventory[0].identity),
    ):
        with pytest.raises(ValidationError):
            IdentityInventoryItem.model_validate(
                facts.identity_inventory[0].model_dump()
                | {"identity_state": identity_state, "identity": identity}
            )
    unresolved = inventory_item(
        "candidate", "entry:opening", "Candidate.md", b"local", state="missing"
    )
    facts = facts.model_copy(update={"identity_inventory": (unresolved,)})
    review = reconcile(facts).changes[0].identity_review
    decision = association(facts, review, "candidate")
    for update in (
        {"path": "Arbitrary.md"},
        {"schema_version": True},
        {"reviewed_assumptions": decision.reviewed_assumptions * 2},
        {"disassociate_entry_ids": ("candidate",)},
    ):
        with pytest.raises(ValidationError):
            type(decision).model_validate(decision.model_dump() | update)
    with pytest.raises(ValidationError):
        ReconciliationInput.model_validate(
            facts.model_dump() | {"association_decisions": (decision, decision)}
        )
    with pytest.raises(ValidationError):
        decision.selected_entry_id = "another"
    # Even a forged internally resolved flag cannot bypass observed repair work.
    result = reconcile(facts.model_copy(update={"association_decisions": (decision,)}))
    with pytest.raises(ValidationError):
        type(result.changes[0]).model_validate(
            result.changes[0].model_dump()
            | {"disposition": "compatible", "result": facts.subjects[0].incoming}
        )
    assert type(result).model_validate_json(result.model_dump_json()) == result


def test_association_provenance_ignores_unrelated_unassociated_file_edits():
    facts = request()
    selected = inventory_item(
        "selected", "entry:opening", "Selected.md", b"local", state="missing"
    )
    unrelated = inventory_item(
        "other",
        "other",
        "Other.md",
        b"unrelated first",
        state="malformed",
        title="Other",
    )
    facts = facts.model_copy(update={"identity_inventory": (selected, unrelated)})
    decision = association(
        facts, reconcile(facts).changes[0].identity_review, "selected"
    )
    reviewed = reconcile(
        facts.model_copy(update={"association_decisions": (decision,)})
    ).changes[0]
    edited = unrelated.model_copy(
        update={
            "current": unrelated.current.model_copy(
                update={
                    "content": unrelated.current.content.model_copy(
                        update={"data": b"unrelated later"}
                    )
                }
            )
        }
    )
    refreshed = reconcile(
        facts.model_copy(
            update={
                "identity_inventory": (selected, edited),
                "association_decisions": (decision,),
            }
        )
    ).changes[0]
    assert refreshed.identity_review.status == "association_proposed"
    assert reviewed.change_id == refreshed.change_id
    assert reviewed.assumptions == refreshed.assumptions


def test_unoffered_rename_and_unsafe_disassociation_are_rejected_without_path_authority():
    facts = request()
    matched = reconcile(facts).changes[0].identity_review
    explicit = association(facts, matched, "opening-entry")
    confirmed = reconcile(
        facts.model_copy(update={"association_decisions": (explicit,)})
    ).changes[0]
    assert confirmed.identity_review.status == "matched"
    assert not confirmed.identity_review.repair_required
    moved = inventory_item("moved", "entry:opening", "Moved.md", b"original\r\n")
    offered = (
        reconcile(facts.model_copy(update={"identity_inventory": (moved,)}))
        .changes[0]
        .rename_review
    )
    unoffered = rename_decision(facts, offered, "source_path")
    result = reconcile(facts.model_copy(update={"rename_decisions": (unoffered,)}))
    assert result.changes[0].disposition == "refused"
    assert result.findings[0].code == "unsafe_rename_decision"
    unsafe = inventory_item(
        "unsafe-duplicate", "entry:opening", "Unsafe.md", b"unsafe exact"
    )
    unsafe = unsafe.model_copy(
        update={"target": unsafe.target.model_copy(update={"containment": "outside"})}
    )
    duplicates = facts.model_copy(
        update={"identity_inventory": facts.identity_inventory + (unsafe,)}
    )
    decision = association(
        duplicates,
        reconcile(duplicates).changes[0].identity_review,
        "opening-entry",
        ("unsafe-duplicate",),
    )
    result = reconcile(
        duplicates.model_copy(update={"association_decisions": (decision,)})
    )
    assert result.changes[0].disposition == "refused" and not result.ready
    assert result.findings[0].code == "unsafe_identity_target"


@pytest.mark.parametrize(
    "first_path,second_path",
    (
        ("Shared.md", "SHARED.MD"),
        ("Shared.md", "SHARED.MD/child.md"),
        ("Shared.md/child.md", "SHARED.MD"),
    ),
)
def test_simultaneous_selected_targets_reject_equality_and_both_ancestor_directions(
    first_path, second_path
):
    from brz2obsidian.contracts import CurrentContent, ExactContent

    facts = request(incoming=b"original\r\n")
    first = facts.subjects[0].model_copy(
        update={
            "path": first_path,
            "source_target": IdentityTargetFacts(
                normalized_path=first_path.casefold(),
                containment="contained",
                status="safe",
            ),
        }
    )
    second = first.model_copy(
        update={
            "item_id": "second:item",
            "title": "Second",
            "path": second_path,
            "source_target": IdentityTargetFacts(
                normalized_path=second_path.casefold(),
                containment="contained",
                status="safe",
            ),
            "current": CurrentContent(
                existence="present",
                path="B.md",
                content=ExactContent(data=b"original\r\n"),
            ),
        }
    )
    entries = (
        inventory_item("a", "entry:opening", "A.md", b"original\r\n"),
        inventory_item("b", "second:item", "B.md", b"original\r\n", title="Second"),
    )
    facts = with_subjects(facts, (first, second), entries)
    offered = reconcile(facts)
    first_decision = rename_decision(
        facts, offered.changes[0].rename_review, "source_path"
    )
    second_decision = rename_decision(
        facts, offered.changes[1].rename_review, "source_path"
    ).model_copy(
        update={"decision_id": "rename-choice:second", "item_id": "second:item"}
    )
    competing = facts.model_copy(
        update={"rename_decisions": (first_decision, second_decision)}
    )
    stale = reconcile(competing)
    assert not stale.ready and all(
        change.disposition == "stale" for change in stale.changes
    )
    # Re-reviewing the exact competing context still cannot approve the collision.
    first_decision = first_decision.model_copy(
        update={"reviewed_assumptions": stale.changes[0].rename_review.assumptions}
    )
    second_decision = second_decision.model_copy(
        update={"reviewed_assumptions": stale.changes[1].rename_review.assumptions}
    )
    result = reconcile(
        facts.model_copy(update={"rename_decisions": (first_decision, second_decision)})
    )
    assert not result.ready and all(
        change.disposition == "refused" for change in result.changes
    )
    assert {finding.code for finding in result.findings} == {"unsafe_rename_target"}
    # Declining one optional rename permits the other after its context is reviewed.
    declined = second_decision.model_copy(update={"choice": "keep_path"})
    refreshed = reconcile(
        facts.model_copy(update={"rename_decisions": (first_decision, declined)})
    )
    assert refreshed.changes[0].disposition == "stale" and not refreshed.ready
    assert refreshed.changes[1].rename_review.status == "declined"
    approved = first_decision.model_copy(
        update={"reviewed_assumptions": refreshed.changes[0].rename_review.assumptions}
    )
    safe = reconcile(
        facts.model_copy(update={"rename_decisions": (approved, declined)})
    )
    assert safe.ready and safe.findings == ()
    assert tuple(change.target_path for change in safe.changes) == (first_path, "B.md")
    assert tuple(change.rename_review.status for change in safe.changes) == (
        "accepted",
        "declined",
    )
    assert all(change.result.data == b"original\r\n" for change in safe.changes)
