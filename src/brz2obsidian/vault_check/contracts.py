"""Separate durable checker envelope; migration schemas remain independent."""

from typing import Literal

from pydantic import Field

from brz2obsidian.contracts import Contract


class VaultCheckIdentity(Contract):
    location: str
    name: str


class VaultCheckCounts(Contract):
    inventory_files: int | None = Field(default=None, ge=0)
    markdown_files: int | None = Field(default=None, ge=0)
    base_files: int | None = Field(default=None, ge=0)
    read_markdown_files: int = Field(default=0, ge=0)
    read_base_files: int = Field(default=0, ge=0)
    category_notes: int | None = Field(default=None, ge=0)
    imported_notes: int | None = Field(default=None, ge=0)


class VaultCheckScope(Contract):
    data_only_yaml: Literal[True] = True
    known_properties: Literal[True] = True
    category_provider_references: Literal[True] = True
    base_image_targets: Literal[True] = True
    imported_identities: Literal[True] = True
    contained_reads: Literal[True] = True


class VaultCheckIssue(Contract):
    code: Literal[
        "invalid_frontmatter",
        "invalid_property",
        "invalid_category",
        "invalid_provider",
        "missing_base",
        "missing_image",
        "ambiguous_reference",
        "duplicate_source_identity",
        "unsafe_reference",
        "read_failure",
        "invalid_base",
    ]
    artifact: str | None = None
    property: str | None = None
    reference: str | None = None
    message: str
    guidance: str
    candidates: tuple[str, ...] = ()


class VaultCheckResult(Contract):
    schema_: Literal["brz2obsidian.vault-check"] = Field(
        default="brz2obsidian.vault-check", alias="schema"
    )
    schema_version: Literal[1] = 1
    operation: Literal["check-vault"] = "check-vault"
    outcome: Literal["clean", "issues", "failed"]
    vault: VaultCheckIdentity
    counts: VaultCheckCounts
    checked_scope: VaultCheckScope = VaultCheckScope()
    issues: tuple[VaultCheckIssue, ...] = ()
