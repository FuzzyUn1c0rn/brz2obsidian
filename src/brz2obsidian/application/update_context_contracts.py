"""Small immutable producer handles; canonical review content stays private."""

from typing import Literal

from pydantic import Field, field_validator, model_validator

from brz2obsidian.contracts import (
    LinkMeaning,
    ReconciliationContract,
    ReviewChoice,
    ReviewChoiceAvailability,
    ReviewDomain,
)

from .contract_values import absolute, request_identity
from .update_contracts import UpdateReviewPage
from .update_history_contracts import (
    HistoryContextBinding,
    UpdateHistoryActionState,
    UpdateHistoryState,
)


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
    selected: ReviewChoice | None = None
    decision_id: str | None = None
    unavailable_choices: tuple[ReviewChoiceAvailability, ...] = ()
    disclosure: str = Field(default="", max_length=2048)
    policy: str | None = None
    detail_count: int = Field(default=0, ge=0)
    detail_omitted: bool = False


class UpdateChoiceDetail(ReconciliationContract):
    kind: Literal["identity", "compatible_group", "consent_scope"]
    entry_id: str | None = None
    change_id: str | None = None
    subject_id: str | None = None
    path: str | None = None
    identity_state: str | None = None
    eligible: bool | None = None
    target_safe: bool | None = None
    existence: str | None = None
    size: int | None = Field(default=None, ge=0)
    sha256: str | None = None


class UpdateConfigurationOffer(ReconciliationContract):
    group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_count: int = Field(ge=1)
    choices: tuple[Literal["current", "incoming"], ...]
    selected: Literal["current", "incoming"] | None


class UpdateEditHandle(ReconciliationContract):
    edit_id: str
    binding: UpdateContextBinding
    requirement_id: str
    assumptions_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    _identity = field_validator("edit_id")(request_identity)


class UpdateEditState(ReconciliationContract):
    handle: UpdateEditHandle
    received_bytes: int = Field(ge=0)
    sealed: bool

    @model_validator(mode="after")
    def complete(self):
        if (
            self.received_bytes > self.handle.size
            or self.sealed
            and self.received_bytes != self.handle.size
        ):
            raise ValueError("Edit state must agree with its declared byte count")
        return self


class UpdateReferenceChoice(ReconciliationContract):
    reference_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    choice: Literal["drop", "keep_current", "use_incoming", "use_secondary"]


class UpdateReferenceDestination(ReconciliationContract):
    choice: Literal["keep_current", "use_incoming", "use_secondary"]
    meaning: LinkMeaning


class UpdateReferenceOffer(ReconciliationContract):
    reference_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_id: str
    occurrence_id: str
    document_path: str
    snippet: bytes = Field(max_length=512)
    old: LinkMeaning
    choices: tuple[
        Literal["drop", "keep_current", "use_incoming", "use_secondary"], ...
    ] = ("drop",)
    destinations: tuple[UpdateReferenceDestination, ...] = ()
    selected: (
        Literal["drop", "keep_current", "use_incoming", "use_secondary"] | None
    ) = None


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
        "initialization_required",
        "initialized_review_required",
        "declined",
        "onboarding_required",
        "unavailable",
        "setup_required",
        "direction_required",
        "undone",
        "restored",
        "repaired",
        "cancelled",
        "incomplete",
        "content_complete",
        "unknown",
    ]
    code: str
    kind: Literal[
        "source_update",
        "onboarding",
        "format_transition",
        "attachment_cleanup",
        "history",
    ]
    binding: UpdateContextBinding | HistoryContextBinding | None = None
    ready: bool = False
    draft_pending: bool = False
    changes: int = Field(default=0, ge=0)
    unresolved: int = Field(default=0, ge=0)
    stale: int = Field(default=0, ge=0)
    next_actions: tuple[str, ...] = ()
    history_retained: bool | None = False
    checkpoint_commit: str | None = None
    publication: Literal[
        "not_started", "not_published", "partial", "complete", "unknown"
    ] = "not_started"
    page: UpdateReviewPage | None = None
    offers: tuple[UpdateChoiceOffer, ...] = ()
    total_choices: int = Field(default=0, ge=0)
    next_choice_offset: int | None = Field(default=None, ge=0)
    choice_details: tuple[UpdateChoiceDetail, ...] = ()
    total_choice_details: int = Field(default=0, ge=0)
    next_choice_detail_offset: int | None = Field(default=None, ge=0)
    references: tuple[UpdateReferenceOffer, ...] = ()
    total_references: int = Field(default=0, ge=0)
    next_reference_offset: int | None = Field(default=None, ge=0)
    edit: UpdateEditState | None = None
    configuration: UpdateConfigurationOffer | None = None
    history: UpdateHistoryState | None = None
    history_action: UpdateHistoryActionState | None = None
    repository_created: bool | None = None

    @model_validator(mode="after")
    def truthful_context(self):
        action = self.history_action
        if self.kind == "history" and self.ready and action is None:
            raise ValueError("Ready history requires its native action facts")
        if self.status == "repaired" and (
            self.kind != "history"
            or action is None
            or action.repair is None
            or action.repair.status != "repaired"
        ):
            raise ValueError(
                "Repaired requires its actual verified native repair result"
            )
        if action is not None:
            if self.kind != "history":
                raise ValueError("History action facts require their actual role")
            if self.ready and (not action.ready or action.status != "ready"):
                raise ValueError("Ready history requires a ready native preparation")
            if (
                action.ready
                and action.available_directions
                and (
                    not isinstance(self.binding, HistoryContextBinding)
                    or self.binding.direction not in action.available_directions
                )
            ):
                raise ValueError(
                    "A ready recovery review requires its chosen direction"
                )
            if action.operation is not None:
                native = action.operation
                if (
                    action.status not in ("refused", "recovery_required")
                    and action.status != native.status
                ):
                    raise ValueError(
                        "History outcome differs from its native operation"
                    )
                if (
                    self.publication != native.publication
                    or self.history_retained
                    is not (
                        None
                        if native.history == "unknown"
                        else native.history != "none"
                    )
                ):
                    raise ValueError(
                        "Native history/publication facts must be retained"
                    )
            if (
                action.repair is not None
                and self.history_retained is not action.repair.history_retained
            ):
                raise ValueError("Repair must preserve actual history retention")
        if (
            self.kind == "history"
            and self.status
            in ("applied", "undone", "restored", "incomplete", "content_complete")
            and (
                action is None
                or action.operation is None
                or action.operation.status != self.status
            )
        ):
            raise ValueError("History file outcomes require their exact native result")
        if self.ready and (
            self.binding is None
            or self.draft_pending
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
