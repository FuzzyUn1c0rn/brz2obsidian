"""Source-independent checker facts projected for local application clients."""

from pathlib import Path

from brz2obsidian import __version__
from brz2obsidian.application.contracts import CheckResult, Finding
from brz2obsidian.vault_check import check_vault as check_current_vault

# Raw messages, references and candidate lists can contain authored content.
# Only known codes, static guidance and the affected artifact path are admitted.
SAFE_FINDINGS = {
    "invalid_frontmatter": "Frontmatter is not valid data-only YAML. Correct its mapping, duplicate keys or unsupported tags.",
    "invalid_property": "A known property has an invalid value. Review its type and supported format.",
    "invalid_category": "A category membership is invalid. Link to a Categories note with the categories tag.",
    "invalid_provider": "An appearance provider is invalid. Choose a valid category membership or leave it blank.",
    "missing_base": "A required Base is unavailable. Review the Base link and its target file.",
    "missing_image": "A required image is unavailable. Review the image link and its target file.",
    "ambiguous_reference": "A required reference has multiple possible targets. Use an unambiguous vault path.",
    "duplicate_source_identity": "Multiple notes share an imported source identity pair. Review those copies before making changes.",
    "unsafe_reference": "A path or reference cannot be read safely. Use regular files and directories contained in the vault.",
    "read_failure": "The vault directory or a file could not be read completely. Check the path, permissions and encoding, then check again.",
    "invalid_base": "A Base is not valid data-only YAML. Correct its mapping, duplicate keys or unsupported tags.",
}


def check_vault(vault: Path) -> CheckResult:
    root = vault.absolute()
    raw = check_current_vault(root)
    findings = tuple(
        Finding(
            code=issue.code,
            severity="error" if raw.outcome == "failed" else "warning",
            message=SAFE_FINDINGS[issue.code],
            field="vault",
            path=issue.artifact,
        )
        for issue in raw.issues
    )
    return CheckResult(
        outcome=raw.outcome,
        status="check_" + raw.outcome,
        counts=raw.counts,
        findings=findings,
        field_errors=findings[:1] if raw.outcome == "failed" else (),
        checked=tuple(raw.checked_scope.model_dump()),
        diagnostic_text="\n".join(
            (
                "brz2obsidian diagnostic report",
                "Operation: check_vault",
                f"Vault: {root}",
                f"Converter: {__version__}",
                f"Outcome: {raw.outcome}",
                "This read-only check covers current vault structure and conventions.",
                "It does not repair files or prove preservation of source content.",
                *(
                    f"{name}: {value if value is not None else 'unavailable'}"
                    for name, value in raw.counts.model_dump().items()
                ),
                *(
                    f"{finding.code} ({finding.path or 'vault'}): {finding.message}"
                    for finding in findings
                ),
            )
        ),
    )
