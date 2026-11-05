"""Source-independent checker facts projected for local application clients."""

from collections.abc import Callable
from pathlib import Path

from brz2obsidian import __version__
from brz2obsidian.application.contracts import CheckResult, Finding
from brz2obsidian.vault_check import check_vault as check_current_vault
from brz2obsidian.vault_check.contracts import VaultCheckResult

# Raw messages, references and candidate lists can contain authored content.
# Only known codes, static guidance and the affected artifact path are admitted.
DETAILED_FINDINGS = {
    "provider_cycle": "The full appearance-category chain contains a repeated provider. Review the affected note and selected categories and remove the cycle. An owned icon may still display; it does not repair the independent chain problem.",
    "icon_lookup_depth": "Icon lookup exceeds 8 links. Native dashboards show no inherited icon for this lookup; migration-time body snapshots use the full finite chain. Assign a nearer valid icon or change a selected appearance category, then close and reopen affected category dashboards and Categories overview. Depth alone does not prevent import, update or checking.",
    "invalid_frontmatter": "Vault check found invalid frontmatter, the properties at the start of a note. These properties must use YAML (a text data format) with one value per key and no executable tags. Correct the properties in the affected note, then check again.",
    "invalid_property": "Vault check found a note property with an invalid value. Review that property's type and supported format in the affected note, then check again.",
    "invalid_category": "Vault check found an invalid category membership. Link it to a note in Categories with the categories tag, then check again.",
    "invalid_provider": "Follow the affected note’s selected appearance-category chain and locate the invalid declaration. In the note with the invalid declaration, choose one of its category memberships or leave its appearance category blank, then check again.",
    "missing_base": "Vault check could not verify a required Base file. Check the Base link and that its target is a nonempty Base file, then check again.",
    "missing_image": "Vault check could not verify a required image. Review the image link and check that its target is a nonempty image file, then check again.",
    "ambiguous_reference": "Vault check found a link with multiple possible targets. Give the link a complete, unambiguous path within the vault, then check again.",
    "duplicate_source_identity": "Vault check found multiple notes with the same imported Brain and thought identifiers. Review those copies before making changes, then check again.",
    "unsafe_reference": "Vault check could not read a path or link safely. Use regular files and directories contained in the vault, then check again.",
    "read_failure": "Vault check could not read the vault folder or one of its files completely. Check the path, permissions and text encoding, then check again.",
    "invalid_base": "Vault check found invalid Base data. A Base must use YAML (a text data format), with one value per key and no executable tags. Correct the affected Base file, then check again.",
}
SAFE_FINDINGS = {
    "provider_cycle": "Appearance-category chain contains a cycle. Review the selected providers.",
    "icon_lookup_depth": "Icon lookup exceeds 8 links. Choose a nearer icon or change the selected appearance category.",
    "invalid_frontmatter": "Invalid note properties. Check their format.",
    "invalid_property": "Invalid property value. Check its type and format.",
    "invalid_category": "Link to a category note in Categories with the categories tag.",
    "invalid_provider": "Invalid appearance-category chain. Review the selected providers.",
    "missing_base": "Couldn’t verify the Base file. Check its link and contents.",
    "missing_image": "Couldn’t verify the image. Check its link and file.",
    "ambiguous_reference": "Several files match this link. Use its full vault path.",
    "duplicate_source_identity": "Multiple notes identify the same imported item. Review the copies.",
    "unsafe_reference": "Use a regular file or folder inside the vault.",
    "read_failure": "Couldn’t read this file. Check access and text encoding.",
    "invalid_base": "Invalid Base file. Check its format.",
}


def finding_for_check(issue, outcome):
    path = None if issue.artifact == "." else issue.artifact
    message = SAFE_FINDINGS[issue.code]
    if issue.code == "read_failure" and path is None:
        message = "Couldn’t read the vault. Check folder access."
    return Finding(
        code=issue.code,
        severity="error" if outcome == "failed" else "warning",
        message=message,
        field="vault",
        path=path,
    )


def check_vault(
    vault: Path, *, checker: Callable[[Path], VaultCheckResult] | None = None
) -> CheckResult:
    root = vault.absolute()
    raw = (checker if checker is not None else check_current_vault)(root)
    findings = tuple(finding_for_check(issue, raw.outcome) for issue in raw.issues)
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
                    line
                    for issue, finding in zip(raw.issues, findings, strict=True)
                    for line in (
                        f"{finding.code} ({finding.path or 'vault'}): {finding.message}",
                        f"  Details: {DETAILED_FINDINGS[issue.code]}",
                    )
                ),
            )
        ),
    )
