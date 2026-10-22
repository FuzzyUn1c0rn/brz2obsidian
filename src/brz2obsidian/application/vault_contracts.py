"""Immutable observations for existing-vault preparation; never write authority."""

from typing import Literal

from pydantic import Field, model_validator

from brz2obsidian.contracts import ReconciliationContract, ReviewPreflight


class VaultSubject(ReconciliationContract):
    path: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)


class VaultFile(ReconciliationContract):
    path: str
    mode: Literal["100644", "100755"]
    size: int = Field(ge=0)
    sha256: str
    identity: str
    tracked: bool
    excluded: bool
    exclusion: Literal["git_ignore", "cache", "temporary"] | None


class VaultFinding(ReconciliationContract):
    code: str
    policy: Literal["layout", "storage", "execution", "operation", "inventory", "git"]
    message: str
    paths: tuple[str, ...]


class VaultRepository(ReconciliationContract):
    kind: Literal["none", "root", "unsupported", "unknown"]
    root: str | None
    git_directory: str | None
    common_directory: str | None
    object_directory: str | None
    head: str | None
    object_format: str | None
    ref_format: str | None


class VaultAdmission(ReconciliationContract):
    schema_id: Literal["brz2obsidian.vault-admission"]
    schema_version: Literal[1]
    vault: str
    status: Literal["supported", "refused", "recovery_first", "unknown"]
    repository: VaultRepository
    git_executable: str | None
    git_version: str | None
    capabilities: tuple[str, ...]
    policy_scope: Literal["current_repository", "before_initialization", "unknown"]
    policy_fingerprint: str
    observation_fingerprint: str
    inventory: tuple[VaultFile, ...]
    inventory_complete: bool
    exclusions: tuple[str, ...]
    recovery_gaps: tuple[str, ...]
    findings: tuple[VaultFinding, ...]
    admitted_actions: tuple[
        Literal["review_history", "review_initialization", "resolve_operation"], ...
    ]
    preflight: ReviewPreflight

    @model_validator(mode="after")
    def consistent_observation(self):
        paths = [f.path for f in self.inventory]
        if paths != sorted(set(paths)):
            raise ValueError("Inventory paths must be unique and sorted")
        if self.status == "supported" and (
            self.findings or not self.inventory_complete
        ):
            raise ValueError(
                "Supported admission requires complete unblocked observations"
            )
        if self.status in ("refused", "unknown") and self.admitted_actions:
            raise ValueError(
                "Refused/unknown observations admit no dependent preparation"
            )
        return self
