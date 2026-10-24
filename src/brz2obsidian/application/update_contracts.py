"""Closed application facts for the shared source-update review lifecycle."""

from typing import Literal

from pydantic import Field, model_validator

from brz2obsidian.application.checkpoint_contracts import CheckpointLocator
from brz2obsidian.application.source_payload_contracts import ReviewedSourceBinding
from brz2obsidian.application.vault_contracts import VaultFile
from brz2obsidian.application.vault_update_contracts import VaultApplyResult
from brz2obsidian.contracts import (
    LoadedReview,
    ReconciliationContract,
    ReviewPlan,
    SourceGapDiagnostic,
    SourceIdentity,
)


class UpdatePreparation(ReconciliationContract):
    schema_id: Literal["brz2obsidian.update-preparation"]
    schema_version: Literal[1]
    vault: str
    locator: CheckpointLocator
    payload_directory: str
    source_ref: str | None = None
    source_binding: ReviewedSourceBinding
    observed_source: SourceIdentity
    retained_source_provenance: bool
    source_gaps: tuple[SourceGapDiagnostic, ...] = ()
    intentional_targets: tuple[str, ...] = ()
    current_inventory: tuple[VaultFile, ...] = ()
    review: ReviewPlan

    @model_validator(mode="after")
    def same_review_association(self):
        association = self.locator.association
        scope = association.collection_id, association.module_id
        for facts in (self.review.facts, self.review.producer_facts):
            if any(
                (identity.collection_id, identity.module_id) != scope
                for identity in (facts.baseline_identity, facts.incoming_identity)
            ):
                raise ValueError("Review identities belong to another association")
        binding = self.source_binding
        identity = self.review.facts.incoming_identity
        if (
            binding.proposal_id != self.review.proposal.proposal_id
            or binding.generation != self.review.proposal.generation
            or binding.incoming_identity != identity
            or (
                self.observed_source.source_id,
                self.observed_source.module_id,
                self.observed_source.module_version,
            )
            != (identity.collection_id, identity.module_id, identity.module_version)
        ):
            raise ValueError("Incoming source binding differs from the reviewed source")
        return self


class UpdateResult(ReconciliationContract):
    schema_id: Literal["brz2obsidian.update-result"] = "brz2obsidian.update-result"
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
    ]
    code: str
    operation_id: str | None = None
    kind: Literal["source_update"] = "source_update"
    generation: int | None = Field(default=None, ge=1)
    preparation: UpdatePreparation | None = None
    loaded: LoadedReview | None = None
    ready: bool = False
    changes: int = Field(default=0, ge=0)
    unresolved: int = Field(default=0, ge=0)
    stale: int = Field(default=0, ge=0)
    summary: str = ""
    next_actions: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()
    diagnostic_omission: bool = True
    recovery_gaps: tuple[str, ...] = ()
    history_retained: bool = False
    checkpoint_commit: str | None = None
    checkpoint: CheckpointLocator | None = None
    vault: str | None = None
    publication: Literal[
        "not_started", "not_published", "partial", "complete", "unknown"
    ] = "not_started"
    application: VaultApplyResult | None = None
    guidance: str = (
        "Keep the target vault idle while an operation runs. Saved converter "
        "history is retained; disk use grows with further versions."
    )

    @model_validator(mode="after")
    def current_readiness(self):
        if self.ready and (
            self.preparation is None
            or not self.preparation.review.ready
            or self.loaded is not None
        ):
            raise ValueError("Readiness requires a current complete review")
        return self


class UpdateComparison(ReconciliationContract):
    change_id: str
    item_id: str
    facet: str
    current_path: str
    incoming_path: str
    disposition: str
    original: bytes | None
    current: bytes | None
    incoming: bytes | None
    result: bytes | None
    offset: int = Field(ge=0)
    next_byte_offset: int | None = Field(default=None, ge=0)
    omitted: bool


class UpdateReviewPage(ReconciliationContract):
    schema_id: Literal["brz2obsidian.update-review-page"] = (
        "brz2obsidian.update-review-page"
    )
    schema_version: Literal[1] = 1
    status: Literal["available", "refused"]
    code: str
    proposal_id: str
    generation: int
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    next_offset: int | None
    items: tuple[UpdateComparison, ...]
    omitted: bool
