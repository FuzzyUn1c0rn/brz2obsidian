"""Safe failures: external exception/body text never crosses the source seam."""

from brz2obsidian.contracts import (
    Issue,
    MigrationFailed,
    MigrationRefused,
)
from brz2obsidian.diagnostics import diagnosed_issue, with_subject


def refuse(message, code="invalid_source", *, subject=None):
    error = MigrationRefused(
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

    raise with_subject(error, *subject) if subject is not None else error


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


def check_cancel(cancel):
    """Observe trusted operational control without retaining provider details."""
    if cancel is None:
        return
    try:
        if not callable(cancel):
            raise TypeError
        requested = cancel()
        if type(requested) is not bool:
            raise TypeError
    except Exception:  # noqa: BLE001 -- control providers must not expose exception details.
        raise failure(
            "api_acquisition_cancelled",
            "The acquisition control could not be checked safely",
        ) from None
    if requested:
        raise failure(
            "api_acquisition_cancelled", "Local API acquisition was cancelled"
        )


SHAPE_MESSAGES = {
    "search": "The local API returned an unsupported search result. This source shape needs review.",
    "relationship": "The local API returned an unsupported relationship. Its source form needs review.",
    "resource": "The local API returned an unsupported resource declaration. Its source form needs review.",
}


def unsupported_shape(profile_version, stage, legacy_message):
    if profile_version in {"3", "4", "5"}:
        refuse(SHAPE_MESSAGES[stage], f"api_{stage}_shape_unsupported")
    refuse(legacy_message)
