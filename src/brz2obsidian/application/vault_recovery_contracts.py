"""Bounded public preparation facts for one retained interrupted operation."""

from typing import Literal

from pydantic import Field, model_validator

from brz2obsidian.contracts import ReconciliationContract, ReviewPlan


class VaultRecoveryPreparation(ReconciliationContract):
    schema_id: Literal["brz2obsidian.vault-recovery-preparation"]
    schema_version: Literal[1]
    status: Literal["offered", "cleanup", "refused", "unavailable"]
    code: str
    operation_id: str | None = Field(pattern=r"^[0-9a-f]{32}$")
    kind: Literal["apply", "undo"] | None
    generation: int | None = Field(ge=1)
    intent_commit: str | None = Field(pattern=r"^[0-9a-f]{40}$")
    available_directions: tuple[Literal["finish", "restore"], ...]
    direction: Literal["finish", "restore"] | None = None
    review: ReviewPlan | None

    @model_validator(mode="after")
    def bounded_authority(self):
        identified = self.status in ("offered", "cleanup")
        if identified != all(
            value is not None
            for value in (
                self.operation_id,
                self.kind,
                self.generation,
                self.intent_commit,
            )
        ):
            raise ValueError(
                "Recovery offer requires exact retained operation identity"
            )
        if (self.status == "offered") != bool(
            self.available_directions
        ) or self.available_directions not in (
            (),
            ("finish",),
            ("restore",),
            ("finish", "restore"),
        ):
            raise ValueError("Recovery directions must describe one supported choice")
        if self.status != "offered" and self.review is not None:
            raise ValueError("Unavailable recovery cannot carry a review")
        if self.review is not None and (
            self.status != "offered" or self.direction is None
        ):
            raise ValueError("Recovery review needs a selected offered direction")
        if (self.direction is None) != (self.review is None):
            raise ValueError("Selected recovery direction requires its reviewed facts")
        if (
            self.direction is not None
            and self.direction not in self.available_directions
        ):
            raise ValueError("Selected recovery direction is not offered")
        return self
