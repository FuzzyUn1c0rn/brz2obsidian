"""Versioned exact-byte checkpoint values; physical trust remains outer."""

from typing import Literal

from pydantic import Field, model_validator

from brz2obsidian.application.vault_contracts import VaultAdmission
from brz2obsidian.contracts import LoadedReview, OutputIdentity, ReconciliationContract


class VaultInitializationDecision(ReconciliationContract):
    schema_id: Literal["brz2obsidian.vault-initialization-decision"]
    schema_version: Literal[1]
    observation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    choice: Literal["initialize", "decline"]


class VaultInitializationResult(ReconciliationContract):
    schema_id: Literal["brz2obsidian.vault-initialization-result"]
    schema_version: Literal[1]
    status: Literal["initialized_review_required", "declined", "refused", "failed"]
    repository_created: bool
    history_retained: Literal[False]
    admission: VaultAdmission
    message: str


class CheckpointFile(ReconciliationContract):
    path: str
    mode: Literal["100644", "100755"]
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    object_id: str = Field(pattern=r"^[0-9a-f]{40}$")


class VaultAssociation(ReconciliationContract):
    schema_id: Literal["brz2obsidian.vault-association"]
    schema_version: Literal[1]
    association_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    vault_id: str = Field(min_length=1)
    import_id: str = Field(min_length=1)
    collection_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    vault_anchor: str
    git_anchor: str
    ref: str


class CheckpointManifest(ReconciliationContract):
    schema_id: Literal["brz2obsidian.checkpoint-manifest"]
    schema_version: Literal[1]
    association_id: str
    generation: int = Field(ge=1)
    boundary: Literal["local", "prepared", "result"]
    identity: OutputIdentity
    source: tuple[CheckpointFile, ...]
    vault: tuple[CheckpointFile, ...]
    preimage: tuple[CheckpointFile, ...]
    proposed: tuple[CheckpointFile, ...]
    review_content: tuple[CheckpointFile, ...]
    recovery_gaps: tuple[str, ...]
    semantic_fingerprint: str
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_continuity_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    previous: str | None
    operation_intent_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    recovery_origin_intent_commit: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{40}$",
        exclude_if=lambda value: value is None,
    )
    recovery_previous_operation_commit: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{40}$",
        exclude_if=lambda value: value is None,
    )
    recovery_direction: Literal["finish", "restore"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    review_object: str | None
    review_size: int | None = Field(ge=0)
    review_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def inventories(self):
        if self.operation_intent_commit is not None and self.boundary != "result":
            raise ValueError("Only an actual result may bind an application intent")
        if len(
            {
                self.recovery_origin_intent_commit is None,
                self.recovery_previous_operation_commit is None,
                self.recovery_direction is None,
            }
        ) != 1 or self.recovery_direction is not None and self.boundary != "prepared":
            raise ValueError("Only a recovery preparation may bind its origin and direction")
        if (self.review_object is None) != (self.review_size is None) or (
            self.review_object is None
        ) != (self.review_sha256 is None):
            raise ValueError("Saved review requires exact payload size and digest")
        for inventory in (
            self.source,
            self.vault,
            self.preimage,
            self.proposed,
            self.review_content,
        ):
            paths = [entry.path for entry in inventory]
            if paths != sorted(set(paths)):
                raise ValueError("Checkpoint inventories must be unique and sorted")
        if self.review_object is None and self.review_content:
            raise ValueError("Review content requires a saved review")
        if any(
            entry.path != entry.sha256 or entry.mode != "100644"
            for entry in self.review_content
        ):
            raise ValueError("Review content paths must name exact byte digests")
        return self


class CheckpointLocator(ReconciliationContract):
    schema_id: Literal["brz2obsidian.checkpoint-locator"]
    schema_version: Literal[1]
    association: VaultAssociation
    generation: int = Field(ge=1)
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")


class CheckpointResult(ReconciliationContract):
    schema_id: Literal["brz2obsidian.checkpoint-result"]
    schema_version: Literal[1]
    status: Literal["captured", "unchanged", "refused", "failed"]
    code: str
    commit: str | None
    ref: str | None
    history_retained: bool
    objects_written: bool
    object_storage: Literal["not_started", "possible", "verified"]
    authored_files_changed: Literal[False]
    message: str


class CheckpointRead(ReconciliationContract):
    schema_id: Literal["brz2obsidian.checkpoint-read"]
    schema_version: Literal[1]
    status: Literal["valid", "absent", "refused"]
    code: str
    locator: CheckpointLocator | None
    manifest: CheckpointManifest | None
    review: LoadedReview | None
    message: str


class VaultHistoryInspection(ReconciliationContract):
    schema_id: Literal["brz2obsidian.vault-history-inspection"]
    schema_version: Literal[1]
    status: Literal["intact", "absent", "unavailable"]
    admission: VaultAdmission
    checkpoint: CheckpointRead | None
