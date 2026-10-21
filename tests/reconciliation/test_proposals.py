"""Independent exact-byte expectations at the public reconciliation seam."""

import json

import pytest
from pydantic import ValidationError

from brz2obsidian.contracts import (
    ContentVersion,
    CurrentContent,
    ExactContent,
    ImmutableContentReference,
    OutputIdentity,
    ReconciliationInput,
    ReconciliationSubject,
    SafetyFact,
)
from brz2obsidian.core import reconcile


def identity():
    return OutputIdentity(
        collection_id="folio:collection",
        module_id="synthetic-folio",
        module_version="1",
        profile_id="reviewed-folio",
        profile_version="1",
        output_format=7,
        settings_digest="settings:a",
    )


def request(
    original=b"original\r\n", current=b"original\r\n", incoming=b"incoming\n", **changes
):
    subject = ReconciliationSubject(
        item_id="entry:opening",
        facet="content",
        path="Notes/Opening.md",
        baseline=ContentVersion(
            status="known", content=ExactContent(data=original), unavailable_digest=None
        ),
        current=CurrentContent(
            existence="present",
            path="Notes/Opening.md",
            content=ExactContent(data=current),
        ),
        incoming=ExactContent(data=incoming),
        interpretation="supported",
    )
    fields = {
        "schema_id": "brz2obsidian.reconciliation-input",
        "schema_version": 1,
        "proposal_id": "review:one",
        "generation": 1,
        "baseline_identity": identity(),
        "incoming_identity": identity(),
        "subjects": (subject,),
        "inventory": "complete",
        "safety_facts": tuple(
            SafetyFact(
                key=kind,
                kind=kind,
                fingerprint="validated:1",
                status="safe",
                subjects=(),
            )
            for kind in ("identity", "target", "candidate", "operation")
        ),
    }
    fields.update(changes)
    return ReconciliationInput(**fields)


def test_source_only_change_is_exact_unapproved_proposal_with_dependencies():
    result = reconcile(request())
    (change,) = result.changes
    assert change.disposition == "compatible"
    assert change.result.data == b"incoming\n"
    assert change.original.data == b"original\r\n"
    assert change.current.data == b"original\r\n"
    assert change.incoming.data == b"incoming\n"
    assert change.path == "Notes/Opening.md"
    assert change.provenance.rule == "source_only"
    assert {a.kind for a in change.assumptions} >= {
        "baseline",
        "current",
        "incoming",
        "identity",
        "inventory",
    }
    assert change.requires_decision
    assert not result.ready
    assert result.readiness == "review_required"
    assert result.proposal_id == "review:one" and result.generation == 1
    assert (
        result.schema_id == "brz2obsidian.update-proposal"
        and result.schema_version == 1
    )


def test_unchanged_source_preserves_arbitrary_exact_local_bytes_without_interpretation():
    facts = request(
        current=b"\xff\xfe---\r\na: 1\na: 2\n## Unknown\x00", incoming=b"original\r\n"
    )
    subject = facts.subjects[0].model_copy(update={"interpretation": "opaque"})
    result = reconcile(facts.model_copy(update={"subjects": (subject,)}))
    (change,) = result.changes
    assert change.disposition == "preserve_vault"
    assert change.result.data == b"\xff\xfe---\r\na: 1\na: 2\n## Unknown\x00"
    assert change.provenance.rule == "source_unchanged"
    assert not change.requires_decision
    assert result.ready and result.readiness == "ready"
    assert result.local_changes == (change.subject_id,)


def test_identical_three_versions_is_no_change_and_no_local_checkpoint_fact():
    result = reconcile(request(incoming=b"original\r\n"))
    (change,) = result.changes
    assert change.disposition == "no_change"
    assert change.result.data == b"original\r\n"
    assert result.ready and result.local_changes == ()


def test_divergent_changes_and_unknown_originals_offer_exact_unresolved_alternatives():
    facts = request(current=b"local\xff", incoming=b"new source\x00")
    for baseline in (
        facts.subjects[0].baseline,
        ContentVersion(status="unknown", content=None, unavailable_digest="git:012345"),
    ):
        subject = facts.subjects[0].model_copy(update={"baseline": baseline})
        result = reconcile(facts.model_copy(update={"subjects": (subject,)}))
        (change,) = result.changes
        assert change.disposition == "unresolved" and change.result is None
        assert change.current.data == b"local\xff"
        assert change.incoming.data == b"new source\x00"
        assert change.original == baseline.content
        assert change.requires_decision and not result.ready
        assert change.provenance.rule == (
            "divergent" if baseline.status == "known" else "unknown_original"
        )
    # Even a matching current/incoming digest cannot manufacture an original.
    unknown = subject.model_copy(
        update={
            "current": CurrentContent(
                existence="present",
                path="Notes/Opening.md",
                content=ExactContent(data=b"new source\x00"),
            )
        }
    )
    unknown_result = reconcile(facts.model_copy(update={"subjects": (unknown,)}))
    assert unknown_result.changes[0].disposition == "unresolved"
    assert unknown_result.local_changes == ()


def test_changed_opaque_output_remains_unresolved_even_for_pristine_current():
    facts = request()
    for interpretation in ("opaque", "unsupported"):
        subject = facts.subjects[0].model_copy(
            update={"interpretation": interpretation}
        )
        (change,) = reconcile(facts.model_copy(update={"subjects": (subject,)})).changes
        assert change.disposition == "unresolved" and change.result is None
        assert change.provenance.rule == "unsupported_interpretation"


def test_same_changed_bytes_on_both_sides_need_no_overwrite_or_decision():
    result = reconcile(request(current=b"same\r\n", incoming=b"same\r\n"))
    (change,) = result.changes
    assert change.disposition == "no_change"
    assert change.result.data == b"same\r\n"
    assert not change.requires_decision and result.ready
    assert result.local_changes == (change.subject_id,)


def test_inventory_uncertainty_and_missing_current_bytes_are_refusals_never_deletion():
    facts = request()
    for inventory in ("partial", "unreadable"):
        result = reconcile(facts.model_copy(update={"inventory": inventory}))
        (change,) = result.changes
        assert change.disposition == "refused" and change.result is None
        assert result.readiness == "refused" and not result.ready
        assert result.findings[0].code == "inventory_uncertain"
    subject = facts.subjects[0].model_copy(
        update={
            "current": CurrentContent(
                existence="unknown", path="Notes/Opening.md", content=None
            )
        }
    )
    result = reconcile(facts.model_copy(update={"subjects": (subject,)}))
    assert result.findings[0].code == "current_unavailable"
    assert result.changes[0].disposition == "refused"


def test_unsafe_unknown_active_and_recovery_facts_block_dependent_readiness():
    facts = request()
    for status in ("unsafe", "unknown", "active", "recovery_required"):
        fact = SafetyFact(
            key="operation",
            kind="operation",
            fingerprint="operation:changed",
            status=status,
            subjects=(),
        )
        result = reconcile(
            facts.model_copy(update={"safety_facts": facts.safety_facts[:-1] + (fact,)})
        )
        assert result.readiness == "refused" and not result.ready
        assert result.changes[0].disposition == "refused"
        assert result.changes[0].result is None
        assert result.findings[0].code == "unsafe_assumption"
        assert "safety:operation" in result.findings[0].assumption_keys
    absent = reconcile(facts.model_copy(update={"safety_facts": ()}))
    assert absent.findings[0].code == "missing_safety_facts"
    assert absent.changes[0].disposition == "refused"


def test_absent_versions_are_conservative_unresolved_facts_at_this_seam():
    facts = request()
    for update, rule in (
        ({"incoming": None}, "source_absent"),
        (
            {
                "current": CurrentContent(
                    existence="absent", path="Notes/Opening.md", content=None
                )
            },
            "local_absent",
        ),
    ):
        subject = facts.subjects[0].model_copy(update=update)
        result = reconcile(facts.model_copy(update={"subjects": (subject,)}))
        (change,) = result.changes
        assert change.disposition == "unresolved" and change.result is None
        assert change.provenance.rule == rule
        assert not result.ready


def test_closed_frozen_input_rejects_missing_unknown_duplicate_and_ill_typed_facts():
    facts = request()
    fields = facts.model_dump()
    for update in (
        {"schema_version": True},
        {"schema_version": 1.0},
        {"schema_version": 2},
        {"generation": True},
        {"unknown": "changes interpretation"},
        {"subjects": [facts.subjects[0]]},
    ):
        with pytest.raises(ValidationError):
            ReconciliationInput.model_validate(fields | update)
    for field in ("inventory", "incoming_identity", "safety_facts"):
        incomplete = fields.copy()
        del incomplete[field]
        with pytest.raises(ValidationError):
            ReconciliationInput.model_validate(incomplete)
    with pytest.raises(ValidationError):
        facts.subjects[0].current.path = "replacement.md"
    for update in (
        {"subjects": facts.subjects * 2},
        {"safety_facts": facts.safety_facts * 2},
    ):
        with pytest.raises(ValidationError):
            ReconciliationInput.model_validate(fields | update)
    raw = facts.model_dump_json()
    with pytest.raises(ValueError, match="Duplicate"):
        ReconciliationInput.model_validate_json(
            raw.replace('"generation":1', '"generation":1,"generation":2')
        )
    # Nested duplicate keys must be rejected too.
    with pytest.raises(ValueError, match="Duplicate"):
        ReconciliationInput.model_validate_json(
            raw.replace(
                '"existence":"present"', '"existence":"present","existence":"absent"'
            )
        )
    for value in (True, 1.0):
        with pytest.raises(ValidationError):
            ReconciliationInput.model_validate_json(
                json.dumps(json.loads(raw) | {"schema_version": value})
            )


def test_required_available_original_and_current_content_cannot_be_inconsistent():
    for fields in (
        {"status": "known", "content": None, "unavailable_digest": "git:only"},
        {
            "status": "unknown",
            "content": ExactContent(data=b"invented"),
            "unavailable_digest": None,
        },
        {
            "status": "known",
            "content": ExactContent(data=b"original"),
            "unavailable_digest": "git:unused",
        },
    ):
        with pytest.raises(ValidationError):
            ContentVersion(**fields)
    for existence, content in (
        ("present", None),
        ("absent", ExactContent(data=b"bytes")),
        ("unknown", ExactContent(data=b"bytes")),
    ):
        with pytest.raises(ValidationError):
            CurrentContent(
                existence=existence, path="Notes/Opening.md", content=content
            )
    for path in (
        "../outside.md",
        "/absolute.md",
        "C:/outside.md",
        "a\\b.md",
        "a//b.md",
        "a/./b.md",
        "",
        "a\x00b",
    ):
        with pytest.raises(ValidationError):
            CurrentContent(
                existence="present", path=path, content=ExactContent(data=b"bytes")
            )
    fields = request().model_dump()
    for scope in (("item:unavailable",), ("entry:opening", "entry:opening")):
        fact = SafetyFact(
            key="invalid-scope",
            kind="target",
            fingerprint="invalid:1",
            status="safe",
            subjects=scope,
        )
        with pytest.raises(ValidationError):
            ReconciliationInput.model_validate(fields | {"safety_facts": (fact,)})


def test_inconsistent_collection_profile_and_unsupported_format_have_typed_refusals():
    facts = request()
    for update, code in (
        ({"collection_id": "unrelated:collection"}, "identity_mismatch"),
        ({"module_id": "unrelated-module"}, "identity_mismatch"),
        ({"profile_version": "2"}, "profile_transition_required"),
        ({"settings_digest": "settings:b"}, "profile_transition_required"),
        ({"output_format": 8}, "format_transition_required"),
    ):
        incoming = identity().model_copy(update=update)
        result = reconcile(facts.model_copy(update={"incoming_identity": incoming}))
        assert result.findings[0].code == code
        assert result.changes[0].disposition == "refused" and not result.ready
    unsupported = identity().model_copy(update={"output_format": 99})
    result = reconcile(
        facts.model_copy(
            update={"baseline_identity": unsupported, "incoming_identity": unsupported}
        )
    )
    assert result.findings[0].code == "unsupported_format"


def test_available_immutable_references_validate_bytes_and_do_not_change_semantic_identity():
    fields = {
        "content_id": "store:object-a",
        "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        "size": 3,
    }
    reference = ImmutableContentReference(**fields)
    content = ExactContent(data=b"abc", reference=reference)
    assert content.data == b"abc"
    for wrong in (b"abd", b"ab"):
        with pytest.raises(ValidationError):
            ExactContent(data=wrong, reference=reference)
    with pytest.raises(ValidationError):
        ExactContent.model_validate({"reference": reference})
    with pytest.raises(ValidationError):
        ImmutableContentReference(**(fields | {"size": "3"}))
    facts = request(original=b"abc", current=b"abc", incoming=b"xyz")
    inline = reconcile(facts)
    original = ContentVersion(status="known", content=content, unavailable_digest=None)
    subject = facts.subjects[0].model_copy(
        update={
            "baseline": original,
            "current": CurrentContent(
                existence="present",
                path="Notes/Opening.md",
                content=ExactContent(
                    data=b"abc",
                    reference=ImmutableContentReference(
                        **(fields | {"content_id": "store:object-b"})
                    ),
                ),
            ),
        }
    )
    referenced = reconcile(
        facts.model_copy(
            update={
                "subjects": (subject,),
                "proposal_id": "review:two",
                "generation": 2,
                "safety_facts": tuple(reversed(facts.safety_facts)),
            }
        )
    )
    a, b = inline.changes[0], referenced.changes[0]
    assert a.subject_id == b.subject_id and a.change_id == b.change_id
    assert a.source_version == b.source_version
    assert a.assumptions == b.assumptions
    assert (
        inline.proposal_id != referenced.proposal_id
        and inline.generation != referenced.generation
    )
    assert a.result.data == b.result.data == b"xyz"
    # Content changes still create a new change, while the subject is stable.
    edited = reconcile(request(original=b"abc", current=b"abc", incoming=b"new"))
    assert edited.changes[0].subject_id == a.subject_id
    assert edited.changes[0].change_id != a.change_id
    assert edited.changes[0].source_version != a.source_version


def test_plan_gate_retains_unaffected_subject_and_scoped_safety_dependencies():
    facts = request()
    other = facts.subjects[0].model_copy(
        update={
            "item_id": "item:second",
            "current": CurrentContent(
                existence="present",
                path="Notes/Second.md",
                content=ExactContent(data=b"local divergent"),
            ),
        }
    )
    scoped = SafetyFact(
        key="second-target",
        kind="target",
        fingerprint="target:unsafe",
        status="unsafe",
        subjects=("item:second",),
    )
    result = reconcile(
        facts.model_copy(
            update={
                "subjects": (facts.subjects[0], other),
                "safety_facts": facts.safety_facts + (scoped,),
            }
        )
    )
    first, second = result.changes
    assert first.disposition == "compatible" and first.result.data == b"incoming\n"
    assert second.disposition == "refused" and second.result is None
    assert not result.ready and result.readiness == "refused"
    assert "safety:second-target" not in {a.key for a in first.assumptions}
    assert "safety:second-target" in {a.key for a in second.assumptions}
    assert all(f.subject_id == second.subject_id for f in result.findings)


def test_non_utf8_proposal_json_round_trip_is_exact_closed_and_immutable():
    result = reconcile(request(current=b"\xff\x00", incoming=b"original\r\n"))
    restored = type(result).model_validate_json(result.model_dump_json())
    assert restored == result
    assert restored.changes[0].result.data == b"\xff\x00"
    with pytest.raises(ValidationError):
        restored.changes[0].result.data = b"mutated"
    raw = result.model_dump_json().replace(
        '"generation":1', '"generation":1,"generation":9'
    )
    with pytest.raises(ValueError, match="Duplicate"):
        type(result).model_validate_json(raw)


def test_result_contract_cannot_turn_an_unresolved_choice_into_readiness():
    result = reconcile(request(current=b"local"))
    for update in (
        {"readiness": "ready", "ready": True},
        {"changes": result.changes * 2},
        {"generation": 0},
    ):
        with pytest.raises(ValidationError):
            type(result).model_validate(result.model_dump() | update)
    with pytest.raises(ValidationError):
        type(result.changes[0]).model_validate(
            result.changes[0].model_dump()
            | {"result": ExactContent(data=b"silently chosen")}
        )


def test_empty_comparison_set_does_not_hide_globally_active_operations():
    facts = request()
    operation = SafetyFact(
        key="operation",
        kind="operation",
        fingerprint="operation:running",
        status="active",
        subjects=(),
    )
    result = reconcile(
        facts.model_copy(
            update={
                "subjects": (),
                "safety_facts": facts.safety_facts[:-1] + (operation,),
            }
        )
    )
    assert not result.ready and result.readiness == "refused"
    assert result.findings[0].code == "unsafe_assumption"
