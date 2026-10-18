"""Safe failures: external exception/body text never crosses the source seam."""

import unicodedata

from brz2obsidian.contracts import (
    DiagnosticSubject,
    Issue,
    MigrationFailed,
    MigrationRefused,
)
from brz2obsidian.diagnostics import diagnosed_issue


def refuse(message, code="invalid_source"):
    raise MigrationRefused(
        (
            diagnosed_issue(
                Issue(
                    code=code,
                    phase="source",
                    message=message,
                    guidance="Correct the source or acquisition configuration and inspect again.",
                )
            ),
        )
    )


def with_subject(error, kind, name):
    """Attach only validated display metadata; omit URI-like and secret labels."""
    if not isinstance(name, str) or any(
        token in name.casefold()
        for token in ("://", "token=", "key=", "password=", "authorization:")
    ):
        return error
    name = "".join(
        char for char in name if not unicodedata.category(char).startswith("C")
    ).strip()[:120]
    if not name:
        return error
    subject = DiagnosticSubject(kind=kind, name=name)
    return type(error)(
        tuple(
            issue.model_copy(update={"subject": subject})
            if issue.subject is None
            else issue
            for issue in error.issues
        ),
        receipt=error.receipt,
    )


def failure(code, message):
    return MigrationFailed(
        (
            diagnosed_issue(
                Issue(
                    code=code,
                    phase="source",
                    message=message,
                    guidance="Check local API and private capture access, then inspect again.",
                )
            ),
        )
    )


SHAPE_MESSAGES = {
    "search": "The local API returned an unsupported search result. This source shape needs review.",
    "relationship": "The local API returned an unsupported relationship. Its source form needs review.",
    "resource": "The local API returned an unsupported resource declaration. Its source form needs review.",
}


def unsupported_shape(profile_version, stage, legacy_message):
    if profile_version == "3":
        refuse(SHAPE_MESSAGES[stage], f"api_{stage}_shape_unsupported")
    refuse(legacy_message)
