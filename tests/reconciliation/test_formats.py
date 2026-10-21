"""Format-operation review at the public pure reconciliation seam."""

from brz2obsidian.contracts import FormatOperation
from brz2obsidian.core import reconcile
from tests.reconciliation.test_proposals import request


def operation(kind="source_update", **changes):
    fields = {
        "schema_id": "brz2obsidian.format-operation",
        "schema_version": 1,
        "kind": kind,
        "recorded_generation": "supported",
        "established_baseline": request().format_operation.established_baseline,
        "baseline_source_version": "source:a",
        "target_source_version": "source:b" if kind == "source_update" else "source:a",
    }
    return FormatOperation(**(fields | changes))


def test_new_converter_retains_recorded_supported_format_and_profile():
    facts = request()
    facts = facts.model_copy(update={"format_operation": operation()})
    result = reconcile(facts)
    assert result.operation == "source_update"
    assert result.changes[0].result.data == b"incoming\n"
    assert result.changes[0].format_review is None
    assert result.changes[0].provenance.rule == "source_only"
    assert "format" in {a.kind for a in result.changes[0].assumptions}


def test_unavailable_old_generation_requires_separate_preservation_first_review():
    facts = request(current=b"authored\xff", incoming=b"target format 7\n")
    old = facts.baseline_identity.model_copy(update={"output_format": 6})
    result = reconcile(
        facts.model_copy(
            update={
                "baseline_identity": old,
                "incoming_identity": old,
                "format_operation": operation(
                    recorded_generation="unavailable", established_baseline=None
                ),
            }
        )
    )
    change = result.changes[0]
    assert change.disposition == "unresolved"
    assert change.provenance.rule == "onboarding_required"
    assert change.current.data == b"authored\xff"
    assert change.result is None and not result.ready
    assert result.readiness == "review_required"
    assert change.format_review.choices == ("keep_current", "use_target", "edit_result")


def test_old_known_and_unknown_originals_expose_separate_role_choices_without_promoting_current():
    from brz2obsidian.contracts import ContentVersion, CurrentContent, ExactContent

    facts = request()
    old = facts.baseline_identity.model_copy(update={"output_format": 6})
    roles = ("note", "dashboard", "template", "guide", "configuration")
    for known in (True, False):
        subjects = tuple(
            facts.subjects[0].model_copy(
                update={
                    "item_id": role,
                    "output_role": role,
                    "path": f"{role}.md",
                    "baseline": ContentVersion(
                        status="known" if known else "unknown",
                        content=ExactContent(data=b"old generated\r\n")
                        if known
                        else None,
                        unavailable_digest=None if known else "record:oid-only",
                    ),
                    "current": CurrentContent(
                        existence="present",
                        path=f"{role}.md",
                        content=ExactContent(data=b"authored\xff\r\n"),
                    ),
                    "incoming": ExactContent(data=b"target generated\n"),
                }
            )
            for role in roles
        )
        result = reconcile(
            facts.model_copy(
                update={
                    "baseline_identity": old,
                    "subjects": subjects,
                    "format_operation": operation(
                        "format_transition",
                        recorded_generation="unavailable",
                        established_baseline=None,
                    ),
                }
            )
        )
        assert result.operation == "format_transition" and not result.ready
        for change, role in zip(result.changes, roles, strict=True):
            assert change.disposition == "unresolved" and change.result is None
            assert change.current.data == b"authored\xff\r\n"
            assert (
                change.original.data == b"old generated\r\n"
                if known
                else change.original is None
            )
            assert change.incoming.data == b"target generated\n"
            assert change.format_review.target_generated.data == b"target generated\n"
            assert change.format_review.original_known == known
            assert change.format_review.old_identity.output_format == 6
            assert change.format_review.target_identity.output_format == 7
            assert change.format_review.configuration_choice == (
                role == "configuration"
            )
            assert change.format_review.target_eligible
            assert change.provenance.producer == "format-review/v1"
            assert change.provenance.rule == "format_review"


def test_converter_release_change_alone_does_not_require_format_upgrade():
    facts = request()
    result = reconcile(
        facts.model_copy(
            update={
                "incoming_identity": facts.incoming_identity.model_copy(
                    update={"module_version": "2"}
                )
            }
        )
    )
    assert result.changes[0].result.data == b"incoming\n"
    assert result.changes[0].format_review is None
    assert result.findings == ()


def test_transition_cannot_hide_changed_or_unknown_source_versions():
    facts = request()
    for source, rule, readiness, code in (
        ("source:b", "unsafe_input", "refused", "format_source_changed"),
        (None, "format_source_uncertain", "review_required", None),
    ):
        result = reconcile(
            facts.model_copy(
                update={
                    "format_operation": operation(
                        "format_transition", target_source_version=source
                    )
                }
            )
        )
        change = result.changes[0]
        assert change.provenance.rule == rule and result.readiness == readiness
        assert not result.ready and not change.format_review.target_eligible
        assert change.result is None
        assert [f.code for f in result.findings] == ([code] if code else [])


def test_followup_source_update_requires_bound_generated_baseline_and_new_review():
    from brz2obsidian.contracts import (
        ContentVersion,
        ExactContent,
        FormatBaselineOutput,
    )

    transition_facts = request(current=b"authored", incoming=b"format target")
    transition = reconcile(
        transition_facts.model_copy(
            update={
                "format_operation": operation("onboarding", established_baseline=None)
            }
        )
    )
    assert transition.changes[0].result is None
    # The outer consumer explicitly establishes validated generated output, retaining
    # authored current separately. This models facts, not persistence/application.
    original = ContentVersion(
        status="known",
        content=ExactContent(data=b"format target"),
        unavailable_digest=None,
    )
    subject = transition_facts.subjects[0].model_copy(
        update={"baseline": original, "incoming": ExactContent(data=b"later source")}
    )
    baseline = transition_facts.format_operation.established_baseline.model_copy(
        update={
            "outputs": (
                FormatBaselineOutput(
                    item_id=subject.item_id,
                    facet=subject.facet,
                    content=ExactContent(data=b"format target"),
                ),
            )
        }
    )
    facts = transition_facts.model_copy(
        update={
            "subjects": (subject,),
            "proposal_id": "separate:source-update",
            "format_operation": operation(established_baseline=baseline),
        }
    )
    update = reconcile(facts)
    change = update.changes[0]
    assert (
        update.operation == "source_update"
        and update.proposal_id != transition.proposal_id
    )
    assert change.provenance.rule == "divergent" and change.requires_decision
    assert (
        change.original.data == b"format target" and change.current.data == b"authored"
    )
    assert change.change_id != transition.changes[0].change_id
    assert not update.ready
    unchanged = subject.model_copy(
        update={"incoming": ExactContent(data=b"format target")}
    )
    preserved = reconcile(facts.model_copy(update={"subjects": (unchanged,)}))
    assert preserved.ready
    assert preserved.changes[0].result.data == b"authored"
    assert preserved.changes[0].original.data == b"format target"
    for corrupt in (
        None,
        baseline.model_copy(update={"source_version": "source:unrelated"}),
        baseline.model_copy(
            update={
                "identity": baseline.identity.model_copy(
                    update={"settings_digest": "other"}
                )
            }
        ),
        baseline.model_copy(update={"outputs": ()}),
        baseline.model_copy(
            update={
                "outputs": (
                    FormatBaselineOutput(
                        item_id=subject.item_id,
                        facet=subject.facet,
                        content=ExactContent(data=b"authored"),
                    ),
                )
            }
        ),
    ):
        blocked = reconcile(
            facts.model_copy(
                update={"format_operation": operation(established_baseline=corrupt)}
            )
        )
        assert blocked.changes[0].provenance.rule == "onboarding_required"
        assert blocked.changes[0].result is None and not blocked.ready


def test_configuration_update_remains_distinct_explicit_choice_from_compatible_note():
    facts = request()
    config = facts.subjects[0].model_copy(update={"output_role": "configuration"})
    result = reconcile(facts.model_copy(update={"subjects": (config,)}))
    change = result.changes[0]
    assert change.disposition == "unresolved" and change.result is None
    assert change.format_review.configuration_choice
    assert change.format_review.target_eligible
    assert change.format_review.choices == ("keep_current", "use_target", "edit_result")
    assert change.current.data == b"original\r\n"
    assert not result.ready


def test_transition_without_output_facts_cannot_be_ready():
    facts = request()
    result = reconcile(
        facts.model_copy(
            update={
                "subjects": (),
                "format_operation": operation("format_transition"),
            }
        )
    )
    assert not result.ready and result.readiness == "refused"
    assert result.findings[0].code == "format_outputs_unavailable"


def test_unsupported_target_and_duplicate_establishment_records_are_rejected():
    import pytest
    from pydantic import ValidationError

    facts = request()
    unsupported = facts.incoming_identity.model_copy(update={"output_format": 8})
    result = reconcile(
        facts.model_copy(
            update={
                "incoming_identity": unsupported,
                "format_operation": operation("format_transition"),
            }
        )
    )
    assert result.findings[0].code == "format_target_unsupported"
    assert result.changes[0].disposition == "refused"
    assert not result.changes[0].format_review.target_eligible
    baseline = facts.format_operation.established_baseline
    with pytest.raises(ValidationError, match="distinct"):
        type(baseline).model_validate(
            baseline.model_dump() | {"outputs": baseline.outputs * 2}
        )
    for update in (
        {"schema_version": True},
        {"kind": "automatic_upgrade"},
        {"target_source_version": ""},
    ):
        with pytest.raises(ValidationError):
            FormatOperation.model_validate(facts.format_operation.model_dump() | update)
    missing = facts.model_dump()
    del missing["format_operation"]
    with pytest.raises(ValidationError):
        type(facts).model_validate(missing)


def test_unrelated_established_output_and_whole_source_churn_leave_facet_dependencies_stable():
    from brz2obsidian.contracts import ExactContent, FormatBaselineOutput

    facts = request()
    first = reconcile(facts).changes[0]
    baseline = facts.format_operation.established_baseline
    unrelated = FormatBaselineOutput(
        item_id="unrelated:item",
        facet="content",
        content=ExactContent(data=b"unrelated generated bytes"),
    )
    revised = operation(
        target_source_version="source:changed-elsewhere",
        established_baseline=baseline.model_copy(
            update={"outputs": baseline.outputs + (unrelated,)}
        ),
    )
    later = reconcile(facts.model_copy(update={"format_operation": revised})).changes[0]
    assert first.change_id == later.change_id
    assert first.assumptions == later.assumptions


def test_unchanged_source_preserves_opaque_local_configuration_without_new_choice():
    facts = request(current=b"local config\xff\x00", incoming=b"original\r\n")
    config = facts.subjects[0].model_copy(
        update={"output_role": "configuration", "interpretation": "opaque"}
    )
    result = reconcile(facts.model_copy(update={"subjects": (config,)}))
    (change,) = result.changes
    assert change.disposition == "preserve_vault"
    assert change.result.data == b"local config\xff\x00"
    assert change.original.data == change.incoming.data == b"original\r\n"
    assert change.format_review is None
    assert not change.requires_decision
    assert change.provenance.rule == "source_unchanged"
    assert result.local_changes == (change.subject_id,)
    assert result.ready and result.readiness == "ready"
