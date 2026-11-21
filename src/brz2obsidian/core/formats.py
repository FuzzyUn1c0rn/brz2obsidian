"""Pure normalized format/onboarding policy; no parsing or output generation."""

from brz2obsidian.content_values import content_key, content_sha, same_content
from brz2obsidian.contracts import REVIEWABLE_OUTPUT_FORMATS, FormatReview


def output_semantics(identity):
    """Compatibility meaning excludes informational source-module release metadata."""
    return identity.model_dump(mode="json", exclude={"module_version"})


def _cleanup_format_findings(operation, baseline, target):
    if (
        operation.recorded_generation != "supported"
        or operation.baseline_source_version is None
        or operation.baseline_source_version != operation.target_source_version
    ):
        return ("format_source_changed",)
    if output_semantics(baseline) != output_semantics(target):
        return ("profile_transition_required",)
    return (
        ()
        if baseline.output_format in REVIEWABLE_OUTPUT_FORMATS
        else ("unsupported_format",)
    )


def _transition_format_findings(facts, operation, baseline, target):
    if not facts.subjects:
        return ("format_outputs_unavailable",)
    if target.output_format not in REVIEWABLE_OUTPUT_FORMATS:
        return ("format_target_unsupported",)
    if (
        operation.baseline_source_version is not None
        and operation.target_source_version is not None
        and operation.baseline_source_version != operation.target_source_version
        and not (
            operation.kind == "onboarding"
            and operation.automatic_merge
            and output_semantics(baseline) == output_semantics(target)
        )
    ):
        return ("format_source_changed",)
    return ()


def format_findings(facts):
    """Return typed operation-level problems; unavailable old paths allow onboarding."""
    operation = facts.format_operation
    baseline, target = facts.baseline_identity, facts.incoming_identity
    if operation.kind == "attachment_cleanup":
        return _cleanup_format_findings(operation, baseline, target)
    if operation.kind != "source_update":
        return _transition_format_findings(facts, operation, baseline, target)
    if operation.recorded_generation != "supported":
        return ()
    if baseline.output_format != target.output_format:
        return ("format_transition_required",)
    if baseline.output_format not in REVIEWABLE_OUTPUT_FORMATS:
        return ("unsupported_format",)
    if (baseline.profile_id, baseline.profile_version, baseline.settings_digest) != (
        target.profile_id,
        target.profile_version,
        target.settings_digest,
    ):
        return ("profile_transition_required",)
    return ()


def established_original(facts, subject):
    """Validate establishment association and exact generated baseline bytes."""
    operation = facts.format_operation
    baseline = operation.established_baseline
    if (
        baseline is None
        or output_semantics(baseline.identity)
        != output_semantics(facts.baseline_identity)
        or baseline.identity.output_format not in REVIEWABLE_OUTPUT_FORMATS
        or baseline.source_version != operation.baseline_source_version
        or subject.baseline.content is None
    ):
        return False
    return any(
        (output.item_id, output.facet) == (subject.item_id, subject.facet)
        and content_key(output.content) == content_key(subject.baseline.content)
        for output in baseline.outputs
    )


def needs_onboarding(facts, subject):
    return (
        facts.format_operation.recorded_generation != "supported"
        or not established_original(facts, subject)
    )


def configuration_change(subject):
    return (
        subject.output_role == "configuration"
        and subject.incoming is not None
        and (
            subject.baseline.content is None
            or content_key(subject.baseline.content) != content_key(subject.incoming)
        )
        and (
            subject.current.content is None
            or content_key(subject.current.content) != content_key(subject.incoming)
        )
    )


def automatic_onboarding(facts, subject):
    """Known generated originals permit normal three-way setup reconciliation."""
    return (
        facts.format_operation.automatic_merge
        and facts.format_operation.kind == "onboarding"
        and not needs_onboarding(facts, subject)
        and output_semantics(facts.baseline_identity)
        == output_semantics(facts.incoming_identity)
    )


def automatic_configuration(facts, subject):
    return (
        facts.format_operation.automatic_merge
        and facts.format_operation.kind == "source_update"
        and not needs_onboarding(facts, subject)
        and subject.baseline.status == "known"
    )


def automatic_transition(facts, subject):
    """Assess proven interpretable files inside an explicit source-stable operation."""
    operation = facts.format_operation
    comparison = subject.structure
    return (
        operation.automatic_merge
        and operation.kind == "format_transition"
        and operation.recorded_generation == "supported"
        and operation.baseline_source_version is not None
        and operation.baseline_source_version == operation.target_source_version
        and subject.baseline.status == "known"
        and not needs_onboarding(facts, subject)
        and (
            (
                subject.attachment is not None
                and subject.interpretation in ("opaque", "supported")
            )
            or (
                subject.interpretation == "supported"
                and comparison is not None
                and (
                    comparison.alignment == "supported"
                    or same_content(subject.current.content, subject.baseline.content)
                )
                and all(
                    document.status == "supported"
                    for document in (
                        comparison.original,
                        comparison.current,
                        comparison.incoming,
                    )
                )
            )
        )
    )


def obsolete_support_listing(facts, subject):
    return (
        facts.incoming_identity.output_format == 9
        and facts.format_operation.kind == "format_transition"
        and subject.baseline.status == "known"
        and subject.incoming is None
        and subject.item_id
        in ("support:Uncreated targets.md", "support:Tag memberships.md")
    )


def format_proposal(facts, subject):
    """Retain explicit choices where the selected operation lacks safe evidence."""
    operation = facts.format_operation
    if (
        operation.kind == "attachment_cleanup"
        or automatic_onboarding(facts, subject)
        or automatic_transition(facts, subject)
        or obsolete_support_listing(facts, subject)
        or (operation.automatic_merge and _new_source_output(facts, subject))
    ):
        return None
    if operation.kind == "source_update":
        if configuration_change(subject) and not automatic_configuration(
            facts, subject
        ):
            return "unresolved", None, "format_review", True
        if subject.baseline.status == "known" and needs_onboarding(facts, subject):
            return "unresolved", None, "onboarding_required", True
        return None
    rule = (
        "format_source_uncertain"
        if operation.baseline_source_version is None
        or operation.target_source_version is None
        else "format_review"
    )
    return "unresolved", None, rule, True


def _new_source_output(facts, subject):
    """An absent new output needs byte approval, not an invented old original."""
    operation = facts.format_operation
    baseline = operation.established_baseline
    return (
        operation.kind in ("source_update", "onboarding")
        and operation.recorded_generation == "supported"
        and baseline is not None
        and baseline.identity.output_format in REVIEWABLE_OUTPUT_FORMATS
        and output_semantics(baseline.identity)
        == output_semantics(facts.baseline_identity)
        and output_semantics(facts.baseline_identity)
        == output_semantics(facts.incoming_identity)
        and baseline.source_version == operation.baseline_source_version
        and operation.target_source_version is not None
        and facts.inventory == "complete"
        and (subject.output_role != "configuration" or operation.automatic_merge)
        and subject.baseline.status == "unknown"
        and not subject.previously_generated
        and subject.baseline.content is None
        and subject.baseline.unavailable_digest is None
        and subject.current.existence == "absent"
        and subject.incoming is not None
        and all(
            (output.item_id, output.facet) != (subject.item_id, subject.facet)
            for output in baseline.outputs
        )
    )


def review_facts(facts, subject):
    if (
        facts.format_operation.kind == "attachment_cleanup"
        or automatic_onboarding(facts, subject)
        or automatic_transition(facts, subject)
        or automatic_configuration(facts, subject)
        or obsolete_support_listing(facts, subject)
        or (
            subject.previously_generated
            and facts.format_operation.kind == "source_update"
            and facts.format_operation.recorded_generation == "supported"
            and facts.incoming_identity.output_format == 9
        )
        or (
            facts.format_operation.automatic_merge
            and _new_source_output(facts, subject)
        )
    ):
        return None
    if (
        facts.format_operation.kind == "source_update"
        and (not needs_onboarding(facts, subject) or _new_source_output(facts, subject))
        and not configuration_change(subject)
    ):
        return None
    return FormatReview(
        old_identity=facts.baseline_identity,
        target_identity=facts.incoming_identity,
        original_known=subject.baseline.status == "known",
        baseline_source_version=facts.format_operation.baseline_source_version,
        target_source_version=facts.format_operation.target_source_version,
        output_role=subject.output_role,
        choices=("keep_current", "use_target", "edit_result"),
        configuration_choice=subject.output_role == "configuration",
        target_generated=subject.incoming,
        target_eligible=(
            subject.incoming is not None
            and facts.incoming_identity.output_format in REVIEWABLE_OUTPUT_FORMATS
            and (
                (
                    facts.format_operation.kind == "source_update"
                    and configuration_change(subject)
                    and not needs_onboarding(facts, subject)
                )
                or (
                    facts.format_operation.kind != "source_update"
                    and facts.format_operation.baseline_source_version is not None
                    and facts.format_operation.baseline_source_version
                    == facts.format_operation.target_source_version
                )
            )
        ),
    )


def format_assumption(facts, subject):
    """Scope output evidence to this facet, without unrelated output/ref churn."""
    operation = facts.format_operation
    baseline = operation.established_baseline
    return (
        operation.kind,
        operation.recorded_generation,
        operation.baseline_source_version,
        operation.target_source_version if operation.kind != "source_update" else None,
        None
        if baseline is None
        else (
            output_semantics(baseline.identity),
            baseline.source_version,
            tuple(
                content_sha(o.content)
                for o in baseline.outputs
                if (o.item_id, o.facet) == (subject.item_id, subject.facet)
            ),
        ),
        subject.output_role,
    ) + (
        (
            subject.prior_reservation,
            subject.previously_generated,
            subject.source_still_reserved,
        )
        if facts.incoming_identity.output_format == 9
        else ()
    )


def configuration_memory_allowed(facts, subject):
    """Only an ordinary established configuration update admits scoped keep memory."""
    return (
        subject.output_role == "configuration"
        and facts.format_operation.kind == "source_update"
        and facts.format_operation.recorded_generation == "supported"
        and not needs_onboarding(facts, subject)
        and not format_findings(facts)
    )
