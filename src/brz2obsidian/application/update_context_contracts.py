"""Small immutable producer handles; canonical review content stays private."""

from typing import Literal

from pydantic import Field, field_validator, model_validator

from brz2obsidian.contracts import ReconciliationContract, ReviewChoice, ReviewDomain

from .contract_values import absolute, request_identity
from .update_contracts import UpdateReviewPage


class UpdateContextBinding(ReconciliationContract):
    context_id: str
    selection_id: str
    vault: str
    association_id: str | None
    checkpoint_commit: str | None = None
    checkpoint_generation: int | None = Field(default=None, ge=1)
    proposal_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    revision: int = Field(ge=1)
    _identities = field_validator("context_id", "selection_id")(request_identity)
    _absolute = field_validator("vault")(absolute)

    @model_validator(mode="after")
    def native_identity(self):
        if (self.association_id is not None) != (
            self.checkpoint_commit is not None
            and self.checkpoint_generation is not None
        ):
            raise ValueError("Native context requires its complete checkpoint identity")
        if self.association_id is None and (
            self.checkpoint_commit is not None or self.checkpoint_generation is not None
        ):
            raise ValueError("An unassociated review has no native checkpoint")
        return self


class UpdateChoiceOffer(ReconciliationContract):
    requirement_id: str
    change_id: str
    domain: ReviewDomain
    choices: tuple[ReviewChoice, ...]
    assumptions_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class UpdateReferenceChoice(ReconciliationContract):
    reference_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    choice: Literal["drop"]


class UpdateReferenceOffer(ReconciliationContract):
    reference_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_id: str
    occurrence_id: str
    choices: tuple[Literal["drop"], ...] = ("drop",)


class UpdateContextResult(ReconciliationContract):
    schema_id: Literal["brz2obsidian.update-context-result"] = (
        "brz2obsidian.update-context-result"
    )
    schema_version: Literal[1] = 1
    status: Literal[
        "prepared_review",
        "unresolved",
        "stale_review",
        "no_content_change",
        "refused",
        "cancelled_before_publication",
        "recovery_required",
        "publication_unknown",
        "applied",
        "failed",
        "available",
    ]
    code: str
    kind: Literal[
        "source_update", "onboarding", "format_transition", "attachment_cleanup"
    ]
    binding: UpdateContextBinding | None = None
    ready: bool = False
    changes: int = Field(default=0, ge=0)
    unresolved: int = Field(default=0, ge=0)
    stale: int = Field(default=0, ge=0)
    next_actions: tuple[str, ...] = ()
    history_retained: bool = False
    checkpoint_commit: str | None = None
    publication: Literal[
        "not_started", "not_published", "partial", "complete", "unknown"
    ] = "not_started"
    page: UpdateReviewPage | None = None
    offers: tuple[UpdateChoiceOffer, ...] = ()
    references: tuple[UpdateReferenceOffer, ...] = ()
    total_references: int = Field(default=0, ge=0)
    next_reference_offset: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def truthful_context(self):
        if self.ready and (
            self.binding is None
            or self.unresolved
            or self.stale
            or self.status not in ("prepared_review", "unresolved")
        ):
            raise ValueError("Readiness requires a complete bound live review")
        if self.status == "applied" and (
            self.publication != "complete"
            or not self.history_retained
            or self.checkpoint_commit is None
        ):
            raise ValueError("Applied requires retained complete publication")
        if self.status == "available" and self.binding is None:
            raise ValueError("Available review content requires its context")
        if self.page is not None and (
            self.binding is None
            or self.page.status != self.status
            or self.page.proposal_id != self.binding.proposal_id
            or self.page.generation != self.binding.generation
        ):
            raise ValueError("Review page must agree with its live context")
        return self
