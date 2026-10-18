"""Safe failures: external exception/body text never crosses the source seam."""

from brz2obsidian.contracts import (
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
