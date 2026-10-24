"""Source-neutral current eligibility and canonical latest-operation review."""

from typing import Literal

from pydantic import Field, model_validator

from brz2obsidian.contracts import ReconciliationContract, ReviewPlan


class VaultUndoPreparation(ReconciliationContract):
    schema_id: Literal["brz2obsidian.vault-undo-preparation"]
    schema_version: Literal[1]
    status: Literal[
        "offered",
        "none",
        "already_undone",
        "recovery_required",
        "unavailable",
        "unsupported",
        "refused",
    ]
    code: str
    checkpoint_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    generation: int | None = Field(default=None, ge=1)
    target_receipt_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    review: ReviewPlan | None = None

    @model_validator(mode="after")
    def exact_offer(self):
        if self.status == "offered":
            if any(
                value is None
                for value in (
                    self.checkpoint_commit,
                    self.generation,
                    self.target_receipt_commit,
                    self.review,
                )
            ):
                raise ValueError(
                    "Undo offer requires current history and reviewed target"
                )
        elif self.review is not None:
            raise ValueError("Unavailable Undo cannot carry a review")
        return self
