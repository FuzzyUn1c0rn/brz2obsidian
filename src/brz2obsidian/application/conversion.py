"""Reviewed conversion composition and safe receipt-based projection."""

from pathlib import Path

from brz2obsidian import __version__
from brz2obsidian.application.contracts import (
    ConversionResult,
    Finding,
    Publication,
    ReviewedInspection,
    same_source_selection,
)
from brz2obsidian.application.workflow import Workflow
from brz2obsidian.contracts import Counts, Issue, MigrationRefused

# Never forward source/publisher exception text, evidence or authored guidance.
# These messages cover safe actions while retaining only explicit path facts.
_SAFE_FINDINGS = {
    "formatting_loss": "Included note formatting needs review: table layout may become responsive, custom icons use visible title fallbacks, or an insert remains unsupported. Review affected notes and declarations in the Migration report and edit the converted Markdown if needed.",
    "review_changed": "The current source or conversion compatibility changed. Inspect the current archive before converting.",
    "source_changed": "The source changed during conversion. Inspect a stable export before converting again.",
    "invalid_source": "The source or prepared output is inconsistent. Review the export and inspect again.",
    "invalid_entry": "The export needs a valid live Home thought. Set Home and re-export.",
    "invalid_reference": "Source references could not be interpreted safely. Review the export and inspect again.",
    "unsupported_feature": "The source contains an unsupported feature. Review the export before continuing.",
    "unsupported_format": "The source format and conversion profile are incompatible. Review the export and inspect again.",
    "approved_source_gap": "Source note, icon or resource bytes are unavailable. Conversion discloses these source limitations; review the migration report.",
    "approved_metadata_discrepancy": "Source metadata differs from verified available bytes. Review the migration report for the disclosed discrepancy.",
    "target_path_too_long": "A generated path exceeds the final supported Windows limit. Choose a shorter output parent or vault name.",
    "unsafe_target_path": "Generated paths are unsafe or collide. Review the source and choose a valid destination.",
    "destination_not_empty": "The destination is populated or unavailable. Review it and choose another absent or empty destination.",
    "unsafe_destination": "The destination has an unsafe path or reparse ancestor. Choose another output parent.",
    "write_failure": "Conversion could not write or publish the vault. Review filesystem access, free space and the destination before another attempt.",
    "payload_integrity_failure": "Staged output failed verification. Review the export and filesystem before another attempt.",
    "cleanup_failure": "Owned staging cleanup did not complete. Review the exact reported leftover path; the app will not delete it or retry automatically. Use an absent or empty destination with a shorter path and check filesystem access.",
    "session_teardown_failure": "The source could not be closed normally. Review source access and the reported publication status.",
    "operation_failure": "Conversion did not complete normally. Review source access and the destination before another attempt.",
    "publication_occurred": "A verified vault was published before a later handled error. Review the published vault; choose another destination for another conversion.",
}


def _safe_finding(issue):
    known = issue.code in _SAFE_FINDINGS
    path = (
        issue.leftover_path
        if issue.code == "cleanup_failure"
        and issue.leftover_path is not None
        and Path(issue.leftover_path).is_absolute()
        else None
    )
    return Finding(
        code=issue.code if known else "conversion_finding",
        severity=issue.severity,
        message=_SAFE_FINDINGS.get(
            issue.code,
            "Conversion reported a source or filesystem limitation. Review the export, destination and publication status before continuing.",
        ),
        path=path,
    )


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
                        guidance="Inspect the current archive before converting.",
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
            "Inspect the selected current archive before converting.",
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
    findings = tuple(_safe_finding(issue) for issue in raw.issues)
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
