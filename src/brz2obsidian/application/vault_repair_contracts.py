"""Read-only matching-history judgments and bounded repair preparations."""

from typing import Literal

from pydantic import Field, model_validator

from brz2obsidian.contracts import ReconciliationContract


class MissingHistoryObject(ReconciliationContract):
    object_id: str = Field(pattern=r"^[0-9a-f]{40}$")
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DamagedHistoryObject(MissingHistoryObject):
    """A declared payload with a physically present, invalid loose Git object."""


class HistoryCopyValidation(ReconciliationContract):
    schema_id: Literal["brz2obsidian.history-copy-validation"]
    schema_version: Literal[1]
    status: Literal["matching", "refused", "unavailable"]
    code: str
    target_generation: int | None = Field(default=None, ge=1)
    copy_generation: int | None = Field(default=None, ge=1)
    target_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    copy_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    association_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    missing_objects: tuple[MissingHistoryObject, ...] = ()
    damaged_objects: tuple[DamagedHistoryObject, ...] = ()
    message: str

    @model_validator(mode="after")
    def exact_missing_inventory(self):
        if tuple(row.object_id for row in self.missing_objects) != tuple(
            sorted({row.object_id for row in self.missing_objects})
        ):
            raise ValueError("Missing history objects must be unique and sorted")
        if self.missing_objects and (
            self.status != "matching"
            or self.code
            not in ("exact_missing_dependency", "exact_unavailable_dependency")
        ):
            raise ValueError("Only a matching repair may name missing objects")
        if tuple(row.object_id for row in self.damaged_objects) != tuple(
            sorted({row.object_id for row in self.damaged_objects})
        ):
            raise ValueError("Damaged history objects must be unique and sorted")
        if self.damaged_objects and (
            self.status != "matching"
            or self.code
            not in ("exact_damaged_dependency", "exact_unavailable_dependency")
        ):
            raise ValueError("Only a matching repair may name damaged objects")
        if {row.object_id for row in self.missing_objects} & {
            row.object_id for row in self.damaged_objects
        }:
            raise ValueError("A history object cannot be missing and damaged")
        return self


class HistoryRepairPreparation(ReconciliationContract):
    schema_id: Literal["brz2obsidian.history-repair-preparation"]
    schema_version: Literal[1]
    status: Literal["prepared", "refused", "unavailable"]
    code: str
    validation: HistoryCopyValidation
    target_anchor: str | None = None
    target_git_anchor: str | None = None
    copy_anchor: str | None = None
    copy_git_anchor: str | None = None
    target_snapshot: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    copy_snapshot: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    message: str


class HistoryRepairResult(ReconciliationContract):
    schema_id: Literal["brz2obsidian.history-repair-result"]
    schema_version: Literal[1]
    status: Literal["repaired", "refused", "failed", "unknown"]
    code: str
    history_retained: bool
    object_storage: Literal["not_started", "possible", "verified"]
    objects_written: int = Field(ge=0)
    authored_files_changed: Literal[False]
    diagnostic_path: str | None = None
    message: str

    @model_validator(mode="after")
    def verified_result(self):
        if self.status == "repaired" and (
            not self.history_retained or self.object_storage != "verified"
        ):
            raise ValueError("A repaired result requires verified retained history")
        if self.object_storage == "not_started" and self.objects_written:
            raise ValueError("No object count can be confirmed before storage starts")
        if self.diagnostic_path is not None and self.status != "unknown":
            raise ValueError("Only uncertain repair may retain diagnostic bytes")
        return self
