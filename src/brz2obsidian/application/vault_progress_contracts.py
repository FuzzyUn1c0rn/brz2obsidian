"""Closed observations of work; these values carry no writer authority."""

from typing import Literal

from pydantic import Field, model_validator

from brz2obsidian.contracts import ReconciliationContract


class VaultProgress(ReconciliationContract):
    schema_id: Literal["brz2obsidian.vault-progress"] = "brz2obsidian.vault-progress"
    schema_version: Literal[1] = 1
    phase: Literal[
        "current_inspection",
        "reference_preparation",
        "review_validation",
        "snapshot_preparation",
        "publication",
        "final_verification",
        "final_reporting",
    ]
    operation_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    operation_generation: int | None = Field(default=None, ge=1)
    intent_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    completed_units: int | None = Field(default=None, ge=0)
    total_units: int | None = Field(default=None, ge=0)
    unit: Literal["files", "history_objects"] | None = None

    @model_validator(mode="after")
    def known_units(self):
        if (
            self.completed_units is not None or self.total_units is not None
        ) and self.unit is None:
            raise ValueError("Known progress counts require their unit")
        if (
            self.completed_units is not None
            and self.total_units is not None
            and self.completed_units > self.total_units
        ):
            raise ValueError("Observed completed count exceeds the known total")
        return self


def report_progress(observer, phase, **known):
    """Synchronously report actual work; callers retain cancellation/result truth.

    The worker's observer catches transport failure, marks contact uncertain and
    sets its existing cooperative stop Event. No native poll is added here.
    """
    if observer is not None:
        observer(VaultProgress(phase=phase, **known))
