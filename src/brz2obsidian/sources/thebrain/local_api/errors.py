"""Safe failures: external exception/body text never crosses the source seam."""

from brz2obsidian.contracts import Issue, MigrationFailed, MigrationRefused


def refuse(message, code="invalid_source"):
    raise MigrationRefused(
        (
            Issue(
                code=code,
                phase="source",
                message=message,
                guidance="Correct the source or acquisition configuration and inspect again.",
            ),
        )
    )


def failure(code, message):
    return MigrationFailed(
        (
            Issue(
                code=code,
                phase="source",
                message=message,
                guidance="Check local API and private capture access, then inspect again.",
            ),
        )
    )
