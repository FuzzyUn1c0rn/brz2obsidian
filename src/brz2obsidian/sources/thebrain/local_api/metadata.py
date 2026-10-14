"""Closed safe acquisition evidence in the outer API composition."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from brz2obsidian.contracts import Contract, RunMetadata

Positive = Annotated[int, Field(gt=0)]
Nonnegative = Annotated[int, Field(ge=0)]
Timestamp = Annotated[str, Field(pattern=r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
CONSISTENCY_LIMITS = (
    "non-atomic-multi-request",
    "captured-copy-integrity-only",
    "empirical-discovery-no-completeness-guarantee",
)


def canonical_uuid(value):
    return isinstance(value, str) and str(UUID(value)) == value and UUID(value).int != 0


class AcquisitionLimits(Contract):
    initial_search_results: Annotated[int, Field(gt=0, le=2147483647)]
    search_budget_ms: Positive
    search_max_response_bytes: Positive
    max_search_results: Annotated[int, Field(gt=0, le=2147483647)] | None
    request_timeout_ms: Positive
    max_response_bytes: Positive
    max_total_capture_bytes: Positive
    max_requests: Positive
    max_traversal_items: Positive
    max_payload_bytes: Positive


class AcquisitionRequest(Contract):
    sequence: Positive
    operation: Literal[
        "brain",
        "statistics",
        "search",
        "types",
        "tags",
        "thought",
        "graph",
        "link",
        "attachments",
        "note",
        "attachment-content",
    ]
    brain_id: str
    subject_id: str | None
    status: int
    outcome: Literal["success", "tag_inventory_zero_exception", "missing_txt_404"]
    started_at: Timestamp
    finished_at: Timestamp
    actual_length: Nonnegative

    @model_validator(mode="after")
    def qualified(self):
        if (
            not canonical_uuid(self.brain_id)
            or self.subject_id is not None
            and not canonical_uuid(self.subject_id)
        ):
            raise ValueError("Invalid request identity")
        expected = {
            "success": (200, None),
            "tag_inventory_zero_exception": (400, "tags"),
            "missing_txt_404": (404, "attachment-content"),
        }
        status, operation = expected[self.outcome]
        if (
            self.status != status
            or operation is not None
            and self.operation != operation
        ):
            raise ValueError("Unqualified acquisition outcome")
        return self


class AcquisitionAudit(Contract):
    atomic: Literal[False]
    method: Literal["bounded-read-only-local-api"]
    started_at: Timestamp
    finished_at: Timestamp
    limits: AcquisitionLimits
    requests: tuple[AcquisitionRequest, ...]
    consistency_limits: tuple[str, ...]

    @field_validator("atomic", mode="before")
    @classmethod
    def actual_false(cls, value):
        if value is not False:
            raise ValueError("Atomic acquisition requires the boolean false")
        return value

    @model_validator(mode="after")
    def ordered(self):
        previous = datetime.fromisoformat(self.started_at)
        finish = datetime.fromisoformat(self.finished_at)
        brain = None
        if (
            previous > finish
            or self.consistency_limits != CONSISTENCY_LIMITS
            or not self.requests
        ):
            raise ValueError("Invalid acquisition interval")
        for index, request in enumerate(self.requests, 1):
            start, end = (
                datetime.fromisoformat(request.started_at),
                datetime.fromisoformat(request.finished_at),
            )
            if request.sequence != index or not previous <= start <= end <= finish:
                raise ValueError("Invalid acquisition chronology")
            if brain is not None and request.brain_id != brain:
                raise ValueError("Foreign acquisition request")
            brain, previous = request.brain_id, end
        if len(self.requests) > self.limits.max_requests:
            raise ValueError("Acquisition request limit exceeded")
        return self


class SourceAcquisition(Contract):
    audit: AcquisitionAudit
    integrity_sha256: Digest


class LocalApiRunMetadata(RunMetadata):
    source_acquisition: SourceAcquisition
