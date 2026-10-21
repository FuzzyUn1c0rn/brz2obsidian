"""Pure normalized format/onboarding policy; no parsing or output generation."""

from hashlib import sha256

from brz2obsidian.contracts import FormatReview


def format_findings(facts):
    """Return typed operation-level problems; unavailable old paths allow onboarding."""
    operation = facts.format_operation
    baseline, target = facts.baseline_identity, facts.incoming_identity
    if operation.kind != "source_update":
        if not facts.subjects:
            return ("format_outputs_unavailable",)
        if target.output_format != 7:
            return ("format_target_unsupported",)
        if (
            operation.baseline_source_version is not None
            and operation.target_source_version is not None
            and operation.baseline_source_version != operation.target_source_version
        ):
            return ("format_source_changed",)
        return ()
    if operation.recorded_generation != "supported":
        return ()
    if baseline.output_format != target.output_format:
        return ("format_transition_required",)
    if baseline.output_format != 7:
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
        or baseline.identity != facts.baseline_identity
        or baseline.identity.output_format != 7
        or baseline.source_version != operation.baseline_source_version
        or subject.baseline.content is None
    ):
        return False
    return any(
        (output.item_id, output.facet) == (subject.item_id, subject.facet)
        and output.content.data == subject.baseline.content.data
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
            subject.current.content is None
            or subject.current.content.data != subject.incoming.data
        )
    )


def format_proposal(facts, subject):
    """A format operation always needs an explicit current-generation choice."""
    operation = facts.format_operation
    if operation.kind == "source_update":
        if configuration_change(subject):
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


def review_facts(facts, subject):
    if (
        facts.format_operation.kind == "source_update"
        and not needs_onboarding(facts, subject)
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
            and facts.incoming_identity.output_format == 7
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
            baseline.identity.model_dump(mode="json"),
            baseline.source_version,
            tuple(
                sha256(o.content.data).hexdigest()
                for o in baseline.outputs
                if (o.item_id, o.facet) == (subject.item_id, subject.facet)
            ),
        ),
        subject.output_role,
    )
