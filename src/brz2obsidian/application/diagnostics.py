"""One safe finding projection for GUI operations and diagnostic reports."""

from pathlib import Path

from brz2obsidian.application.contracts import Finding
from brz2obsidian.diagnostics import KNOWN_CODES, explain_issue


def finding_for(issue, operation, *, field=None):
    fallback = {
        "inspect": "inspection_finding",
        "convert": "conversion_finding",
        "list_brains": "api_listing_failed",
    }[operation]
    path = (
        issue.leftover_path
        if issue.code == "cleanup_failure"
        and issue.leftover_path is not None
        and Path(issue.leftover_path).is_absolute()
        else None
    )
    return Finding(
        code=issue.code if issue.code in KNOWN_CODES else fallback,
        severity=issue.severity,
        message=explain_issue(issue, operation),
        field=field,
        path=path,
    )
