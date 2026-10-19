"""Reviewed conversion composition and safe receipt-based projection."""

from brz2obsidian import __version__
from brz2obsidian.application.contracts import (
    ConversionResult,
    Finding,
    Publication,
    ReviewedInspection,
    same_source_selection,
)
from brz2obsidian.application.diagnostics import finding_for
from brz2obsidian.application.workflow import Workflow
from brz2obsidian.contracts import Counts, Issue, MigrationRefused


class _CapturedRenderer:
    def __init__(self, delegate):
        self.delegate = delegate
        self.plan = self.metadata = None

    def render(self, plan, metadata):
        # Capture actual typed preparation facts at the renderer protocol seam.
        # Do not infer compatibility by parsing generated Markdown or records.
        self.plan, self.metadata = plan, metadata
        return self.delegate.render(plan, metadata)


class _ReviewedPublisher:
    def __init__(self, delegate, reviewed, renderer):
        self.delegate = delegate
        self.reviewed = reviewed
        self.renderer = renderer

    def publish(self, artifacts, session, destination):
        expected = self.reviewed.source_identity
        plan, metadata = self.renderer.plan, self.renderer.metadata
        if any(
            actual != expected
            for actual in (
                artifacts.source_identity,
                session.source_identity,
                session.snapshot.identity,
                plan.source_identity,
                plan.analysis.snapshot.identity,
            )
        ) or (
            self.reviewed.converter_version != __version__
            or metadata.converter_version != self.reviewed.converter_version
            or metadata.renderer_version != artifacts.renderer_version
            or plan.profile_id != self.reviewed.profile_id
            or plan.profile_version != self.reviewed.profile_version
            or plan.analysis.policy.profile_id != self.reviewed.profile_id
            or plan.analysis.policy.profile_version != self.reviewed.profile_version
            or (plan.issues and self.reviewed.outcome != "warnings")
        ):
            raise MigrationRefused(
                (
                    Issue(
                        code="review_changed",
                        phase="publication",
                        message="The current source or conversion compatibility does not match the reviewed inspection.",
                        guidance="Inspect the current source before converting.",
                    ),
                )
            )
        return self.delegate.publish(artifacts, session, destination)


def _refused(
    code,
    message,
    destination,
    *,
    source,
    reviewed,
    review_required=False,
    field_errors=(),
):
    profile = (
        f"{reviewed.profile_id} / {reviewed.profile_version}"
        if isinstance(reviewed, ReviewedInspection)
        else "unavailable"
    )
    return ConversionResult(
        outcome="refused",
        status="conversion_refused",
        publication=Publication(state="not_published"),
        destination=destination,
        findings=(Finding(code=code, severity="error", message=message),),
        field_errors=field_errors,
        review_required=review_required,
        pending=("publication", "generated_vault_check"),
        diagnostic_text=f"brz2obsidian diagnostic report\nOperation: convert_reviewed\nSource: {source}\nConverter: {__version__}\nReviewed profile: {profile}\nOutcome: refused\n{code}: {message}\nDestination: {destination or 'unavailable'}",
    )


def convert(
    workflow, source, validation, reviewed, proceed_with_warnings, *, source_selection
):
    destination = validation.destination
    if not isinstance(reviewed, ReviewedInspection) or not same_source_selection(
        reviewed.source_selection, source_selection
    ):
        return _refused(
            "review_required",
            "Inspect the selected current source before converting.",
            destination,
            source=source,
            reviewed=reviewed,
            review_required=True,
        )
    if reviewed.outcome == "warnings" and proceed_with_warnings is not True:
        return _refused(
            "warning_authorization_required",
            "Review the source warnings and explicitly authorize conversion with warnings.",
            destination,
            source=source,
            reviewed=reviewed,
        )
    if validation.outcome != "valid":
        return _refused(
            "destination_invalid",
            "Choose a valid absent or empty destination before converting.",
            destination,
            source=source,
            reviewed=reviewed,
            field_errors=validation.field_errors,
        )
    renderer = _CapturedRenderer(workflow.renderer)
    current = Workflow(
        workflow.binding,
        renderer,
        _ReviewedPublisher(workflow.publisher, reviewed, renderer),
        workflow.metadata_factory,
    )
    raw = current.convert(source, destination)
    findings = tuple(finding_for(issue, "convert") for issue in raw.issues)
    receipt = raw.receipt
    published = receipt is not None and receipt.published and receipt.verified
    path = receipt.destination if published else str(destination)
    status = (
        "conversion_created_with_error"
        if published and raw.outcome in ("refused", "failed")
        else {
            "clean": "conversion_created",
            "warnings": "conversion_created_with_warnings",
            "refused": "conversion_refused",
            "failed": "conversion_failed",
        }[raw.outcome]
    )
    return ConversionResult(
        outcome=raw.outcome,
        status=status,
        counts=raw.counts or Counts(),
        findings=findings,
        destination=path,
        publication=Publication(
            state="published_verified" if published else "not_published",
            destination=path if published else None,
            receipt_verified=published,
        ),
        checked=("source_consistency", "staged_manifest", "publication")
        if published
        else (),
        pending=("generated_vault_check",),
        review_required=any(
            issue.code
            in (
                "review_changed",
                "source_changed",
                "invalid_source",
                "unsupported_format",
            )
            for issue in raw.issues
        ),
        diagnostic_text="\n".join(
            (
                "brz2obsidian diagnostic report",
                "Operation: convert_reviewed",
                f"Source: {source}",
                f"Destination: {path}",
                f"Converter: {raw.converter_version}",
                f"Profile: {raw.profile_id or 'unavailable'} / {raw.profile_version or 'unavailable'}",
                f"Outcome: {raw.outcome}",
                f"Verified publication: {published}",
                "Planned and actual counts are distinct; unavailable facts are not zero.",
                *(
                    f"{name}: {value if value is not None else 'unavailable'}"
                    for name, value in (raw.counts or Counts()).model_dump().items()
                ),
                *(
                    f"{finding.code}: {finding.message}"
                    + (f"\nReported leftover: {finding.path}" if finding.path else "")
                    for finding in findings
                ),
                "Pending: generated vault check. No check or external application is opened automatically.",
            )
        ),
    )
