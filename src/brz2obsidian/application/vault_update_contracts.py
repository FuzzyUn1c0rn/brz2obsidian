"""Bounded public facts for one existing-vault application attempt."""

from typing import Literal

from pydantic import Field, model_validator

from brz2obsidian.application.checkpoint_contracts import CheckpointFile
from brz2obsidian.contracts import ReconciliationContract


class VaultOperationLock(ReconciliationContract):
    schema_id: Literal["brz2obsidian.vault-operation-lock"]
    schema_version: Literal[1]
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    vault_anchor: str
    git_anchor: str


class VaultPathMetadata(ReconciliationContract):
    path: str
    mode: int = Field(ge=0)
    attributes: int = Field(ge=0)
    security: str = Field(min_length=1)


class VaultOperationIntent(ReconciliationContract):
    schema_id: Literal["brz2obsidian.vault-operation-intent"]
    schema_version: Literal[1]
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    kind: Literal["apply", "undo"]
    generation: int = Field(ge=1)
    direction: Literal["finish", "restore"]
    association_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    prepared_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    before: tuple[CheckpointFile, ...]
    proposed: tuple[CheckpointFile, ...]
    affected_paths: tuple[str, ...]
    protected_paths: tuple[str, ...]
    before_metadata: tuple[VaultPathMetadata, ...]
    result_metadata: tuple[VaultPathMetadata, ...]
    created_directories: tuple[VaultPathMetadata, ...]

    @model_validator(mode="after")
    def complete_transition(self):
        for rows in (self.before, self.proposed):
            paths = [row.path for row in rows]
            if paths != sorted(set(paths)):
                raise ValueError("Operation inventory paths must be unique and sorted")
        if self.affected_paths != tuple(sorted(set(self.affected_paths))):
            raise ValueError("Affected paths must be unique and sorted")
        if self.protected_paths != tuple(sorted(set(self.protected_paths))):
            raise ValueError("Protected paths must be unique and sorted")
        for path in (*self.affected_paths, *self.protected_paths):
            self.relative_vault_path(path)
        before = {row.path: row for row in self.before}
        proposed = {row.path: row for row in self.proposed}
        changes = {
            path
            for path in before.keys() | proposed.keys()
            if before.get(path) != proposed.get(path)
        }
        if (
            set(self.affected_paths) != changes
            or set(self.protected_paths) != set(before) - changes
        ):
            raise ValueError("Intent path roles must match exact inventories")
        for rows, inventory in (
            (self.before_metadata, before),
            (self.result_metadata, proposed),
        ):
            paths = [row.path for row in rows]
            if paths != sorted(set(paths)) or set(paths) != changes & set(inventory):
                raise ValueError("Affected metadata must cover exact file roles")
            for row in rows:
                self.relative_vault_path(row.path)
        directories = [row.path for row in self.created_directories]
        if directories != sorted(set(directories)):
            raise ValueError("Created directory paths must be unique and sorted")
        for path in directories:
            self.relative_vault_path(path)
            if (
                path in before
                or path in proposed
                or not any(
                    changed_path in proposed and changed_path.startswith(path + "/")
                    for changed_path in changes
                )
            ):
                raise ValueError("Created directory must parent a changed result file")
        return self


class VaultRecoveryIntent(VaultOperationIntent):
    """A selected recovery transition rooted in one original operation."""

    schema_id: Literal["brz2obsidian.vault-recovery-intent"]
    origin_intent_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    previous_operation_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    review_generation: int = Field(ge=1)


class VaultOperationReceipt(ReconciliationContract):
    schema_id: Literal["brz2obsidian.vault-operation-receipt"]
    schema_version: Literal[1]
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    kind: Literal["apply", "undo"]
    generation: int = Field(ge=1)
    status: Literal["applied", "no_content_change", "undone", "restored"]
    direction: Literal["finish", "restore"]
    intent_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    prepared_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    result_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    published_paths: tuple[str, ...]

    @model_validator(mode="after")
    def ordered_publication(self):
        if self.published_paths != tuple(sorted(set(self.published_paths))):
            raise ValueError("Published paths must be unique and sorted")
        for path in self.published_paths:
            self.relative_vault_path(path)
        if self.direction == "restore":
            expected = ("restored",)
        elif self.kind == "undo":
            expected = ("undone",)
        else:
            expected = (
                ("applied",)
                if self.published_paths
                else ("applied", "no_content_change")
            )
        if self.status not in expected:
            raise ValueError("Receipt status must reflect actual file publication")
        return self


class VaultOperationStop(ReconciliationContract):
    schema_id: Literal["brz2obsidian.vault-operation-stop"]
    schema_version: Literal[1]
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    kind: Literal["apply", "undo"]
    generation: int = Field(ge=1)
    direction: Literal["finish", "restore"]
    status: Literal["cancelled"]
    intent_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    acknowledged_after_files: int = Field(ge=0)


class VaultApplyResult(ReconciliationContract):
    schema_id: Literal["brz2obsidian.vault-apply-result"]
    schema_version: Literal[1]
    status: Literal[
        "refused",
        "failed",
        "cancelled",
        "incomplete",
        "content_complete",
        "applied",
        "no_content_change",
        "undone",
        "restored",
        "unknown",
    ]
    code: str
    operation_id: str | None
    kind: Literal["apply", "undo"]
    direction: Literal["finish", "restore"] | None = None
    review_generation: int | None = Field(default=None, ge=1)
    generation: int | None = Field(ge=1)
    phase: Literal[
        "admission", "prepared", "intent", "publication", "result", "terminal"
    ]
    publication: Literal[
        "not_started", "not_published", "partial", "complete", "unknown"
    ]
    history: Literal["none", "prepared", "intent", "result", "terminal", "unknown"]
    planned_files: int = Field(ge=0)
    published_files: int = Field(ge=0)
    authored_files_changed: bool | None
    checkpoint_commit: str | None = Field(pattern=r"^[0-9a-f]{40}$")
    intent_commit: str | None = Field(pattern=r"^[0-9a-f]{40}$")
    result_commit: str | None = Field(pattern=r"^[0-9a-f]{40}$")
    receipt_commit: str | None = Field(pattern=r"^[0-9a-f]{40}$")
    stop_commit: str | None = Field(pattern=r"^[0-9a-f]{40}$", default=None)
    recovery_required: bool
    elapsed_ms: int = Field(ge=0)
    message: str

    @model_validator(mode="after")
    def truthful_terminal(self):
        if self.status in ("applied", "no_content_change", "undone", "restored") and (
            self.phase != "terminal"
            or self.publication != "complete"
            or self.history != "terminal"
            or self.receipt_commit is None
            or self.result_commit is None
            or self.recovery_required
        ):
            raise ValueError("Applied requires complete files, result and receipt")
        if self.status == "restored" and self.direction != "restore":
            raise ValueError("Restored requires saved restoration direction")
        if self.status == "undone" and (
            self.kind != "undo" or self.direction != "finish"
        ):
            raise ValueError("Undone requires a finished undo")
        if self.status in ("applied", "no_content_change") and (
            self.kind != "apply" or self.direction == "restore"
        ):
            raise ValueError("Applied requires a finished apply")
        if self.status == "no_content_change" and (
            self.planned_files or self.published_files or self.authored_files_changed
        ):
            raise ValueError("No-content outcome cannot claim authored publication")
        if self.published_files > self.planned_files:
            raise ValueError("Published count cannot exceed planned count")
        return self


class VaultComparisonDetail(ReconciliationContract):
    path: str
    before_size: int | None = Field(ge=0)
    before_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    after_size: int | None = Field(ge=0)
    after_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")


class VaultUpdateDetailPage(ReconciliationContract):
    schema_id: Literal["brz2obsidian.vault-update-detail-page"]
    schema_version: Literal[1]
    status: Literal["available", "unavailable"]
    code: str
    operation_id: str | None
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    items: tuple[VaultComparisonDetail, ...]
    next_offset: int | None = Field(ge=0)

    @model_validator(mode="after")
    def bounded_page(self):
        if len(self.items) > self.limit or (
            self.items and self.offset + len(self.items) > self.total
        ):
            raise ValueError("Detail page exceeds declared bounds")
        expected_next = (
            self.offset + len(self.items)
            if self.offset + len(self.items) < self.total
            else None
        )
        if self.next_offset != expected_next:
            raise ValueError("Detail page continuation disagrees")
        if self.status == "available" and self.operation_id is None:
            raise ValueError("Available detail page needs operation authority")
        return self
