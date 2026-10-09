"""Closed, immutable application and transport values; no GUI dependencies."""

from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter, field_validator, model_validator

from brz2obsidian.contracts import Contract, Counts, SourceIdentity
from brz2obsidian.vault_check.contracts import VaultCheckCounts

Operation = Literal[
    "inspect", "validate_destination", "convert_reviewed", "check_vault"
]
Action = Literal[
    "inspect",
    "convert",
    "convert_with_warnings",
    "convert_this_archive",
    "check_vault",
    "open_folder",
    "open_migration_report",
    "open_in_obsidian",
    "retry",
    "start_another_conversion",
    "review_destination",
    "copy_details",
    "save_diagnostic_report",
    "close",
]
FieldId = Literal["source", "parent", "vault_name", "destination", "vault"]


def absolute(value: str) -> str:
    if not Path(value).is_absolute():
        raise ValueError("An absolute path is required")
    return value


def request_identity(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError("A canonical UUID is required")
    return value


class Versioned(Contract):
    schema_version: Literal[1] = 1

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("An integer schema version is required")
        return value


class ReviewedInspection(Versioned):
    schema_: Literal["brz2obsidian.review"] = Field(
        default="brz2obsidian.review", alias="schema"
    )
    source: str
    source_identity: SourceIdentity
    converter_version: str
    profile_id: str
    profile_version: str
    outcome: Literal["clean", "warnings"]
    _absolute = field_validator("source")(absolute)


class Finding(Contract):
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    field: FieldId | None = None
    path: str | None = None


class Publication(Contract):
    state: Literal["not_published", "published_verified", "unknown"]
    destination: str | None = None
    receipt_verified: bool = False

    @model_validator(mode="after")
    def consistent(self):
        if self.receipt_verified != (self.state == "published_verified"):
            raise ValueError("Publication and receipt disagree")
        if self.state == "published_verified" and self.destination is None:
            raise ValueError("Verified publication requires a destination")
        if self.destination is not None:
            absolute(self.destination)
        return self


class DiagnosticOmission(Contract):
    findings_count: int = Field(ge=0)
    reason: Literal["response_limit"] = "response_limit"


class Result(Versioned):
    schema_: Literal["brz2obsidian.operation-result"] = Field(
        default="brz2obsidian.operation-result", alias="schema"
    )
    counts: Counts = Counts()
    findings: tuple[Finding, ...] = ()
    field_errors: tuple[Finding, ...] = ()
    reviewed: ReviewedInspection | None = None
    publication: Publication | None = None
    destination: str | None = None
    checked: tuple[str, ...] = ()
    pending: tuple[str, ...] = ()
    review_required: bool = False
    diagnostic_text: str = ""
    diagnostic_omission: DiagnosticOmission | None = None

    @model_validator(mode="after")
    def aggregate_counts(self):
        if any(v is not None and v < 0 for v in self.counts.model_dump().values()):
            raise ValueError("Aggregate counts cannot be negative")
        if self.destination is not None:
            absolute(self.destination)
        if self.diagnostic_omission and "omitted" not in self.diagnostic_text.lower():
            raise ValueError("Diagnostic omission must be disclosed")
        return self


class InspectionResult(Result):
    operation: Literal["inspect"] = "inspect"
    outcome: Literal["clean", "warnings", "refused", "failed"]
    status: Literal[
        "inspection_clean",
        "inspection_warnings",
        "inspection_refused",
        "inspection_failed",
    ]

    @model_validator(mode="after")
    def consistent(self):
        if self.status != "inspection_" + self.outcome:
            raise ValueError("Inspection status disagrees with outcome")
        if (self.reviewed is not None) != (self.outcome in ("clean", "warnings")):
            raise ValueError("Only usable inspections carry a review")
        if self.reviewed and self.reviewed.outcome != self.outcome:
            raise ValueError("Review outcome disagrees with inspection")
        if self.publication is not None:
            raise ValueError("Inspection cannot publish")
        return self


class DestinationValidation(Result):
    operation: Literal["validate_destination"] = "validate_destination"
    outcome: Literal["valid", "invalid", "failed"]
    status: Literal["destination_valid", "destination_invalid", "destination_failed"]

    @model_validator(mode="after")
    def consistent(self):
        if (
            self.status != "destination_" + self.outcome
            or self.reviewed
            or self.publication
        ):
            raise ValueError("Inconsistent destination validation")
        if self.outcome == "valid" and (self.destination is None or self.field_errors):
            raise ValueError(
                "Valid destination requires a constructed path without field errors"
            )
        return self


class ConversionResult(Result):
    operation: Literal["convert_reviewed"] = "convert_reviewed"
    outcome: Literal["clean", "warnings", "refused", "failed"]
    status: Literal[
        "conversion_created",
        "conversion_created_with_warnings",
        "conversion_refused",
        "conversion_failed",
        "conversion_created_with_error",
    ]
    publication: Publication

    @model_validator(mode="after")
    def consistent(self):
        if self.reviewed is not None:
            raise ValueError("Only usable inspection results can carry a review")
        expected = {
            "clean": "conversion_created",
            "warnings": "conversion_created_with_warnings",
            "refused": "conversion_refused",
            "failed": "conversion_failed",
        }[self.outcome]
        if self.publication.receipt_verified and self.outcome in ("refused", "failed"):
            expected = "conversion_created_with_error"
        if self.status != expected:
            raise ValueError("Conversion status disagrees with outcome/receipt")
        if (
            self.status.startswith("conversion_created")
            and not self.publication.receipt_verified
        ):
            raise ValueError("Created requires a verified receipt")
        return self


class CheckResult(Result):
    counts: VaultCheckCounts = VaultCheckCounts()
    operation: Literal["check_vault"] = "check_vault"
    outcome: Literal["clean", "issues", "failed"]
    status: Literal["check_clean", "check_issues", "check_failed"]

    @model_validator(mode="after")
    def consistent(self):
        if self.status != "check_" + self.outcome or self.reviewed or self.publication:
            raise ValueError("Inconsistent check result")
        return self


OperationResult = Annotated[
    InspectionResult | DestinationValidation | ConversionResult | CheckResult,
    Field(discriminator="operation"),
]
RESULT = TypeAdapter(OperationResult)


class InspectArguments(Contract):
    source: str
    _absolute = field_validator("source")(absolute)


class DestinationArguments(Contract):
    parent: str
    vault_name: str
    _absolute = field_validator("parent")(absolute)


class ConvertArguments(DestinationArguments):
    source: str
    reviewed: ReviewedInspection
    proceed_with_warnings: bool
    _source = field_validator("source")(absolute)


class CheckArguments(Contract):
    vault: str
    _absolute = field_validator("vault")(absolute)


class WorkerRequest(Versioned):
    schema_: Literal["brz2obsidian.worker-request"] = Field(
        default="brz2obsidian.worker-request", alias="schema"
    )
    request_id: str
    operation: Operation
    arguments: (
        InspectArguments | DestinationArguments | ConvertArguments | CheckArguments
    )
    _identity = field_validator("request_id")(request_identity)

    @model_validator(mode="after")
    def argument_shape(self):
        expected = {
            "inspect": InspectArguments,
            "validate_destination": DestinationArguments,
            "convert_reviewed": ConvertArguments,
            "check_vault": CheckArguments,
        }[self.operation]
        if type(self.arguments) is not expected:
            raise ValueError("Arguments disagree with operation")
        return self


class ProtocolError(Contract):
    code: Literal["invalid_request", "operation_unavailable", "internal_error"]
    message: Literal[
        "The worker request is invalid.",
        "This operation is not available in this build.",
        "The operation could not complete.",
    ]


class WorkerResponse(Versioned):
    schema_: Literal["brz2obsidian.worker-response"] = Field(
        default="brz2obsidian.worker-response", alias="schema"
    )
    request_id: str
    operation: Operation
    result: OperationResult | None = None
    protocol_error: ProtocolError | None = None
    _identity = field_validator("request_id")(request_identity)

    @model_validator(mode="after")
    def one_terminal(self):
        if (self.result is None) == (self.protocol_error is None):
            raise ValueError("Exactly one terminal result is required")
        if self.result is not None and self.result.operation != self.operation:
            raise ValueError("Result operation disagrees with response")
        return self


class SelectSource(Contract):
    command: Literal["select_source"] = "select_source"
    path_or_null: str | None


class SetDestination(Contract):
    command: Literal["set_destination"] = "set_destination"
    parent_or_null: str | None
    vault_name: str

    @field_validator("parent_or_null")
    @classmethod
    def absolute_parent(cls, value):
        return absolute(value) if value is not None else None


class SelectVault(Contract):
    command: Literal["select_vault"] = "select_vault"
    path_or_null: str | None

    @field_validator("path_or_null")
    @classmethod
    def absolute_vault(cls, value):
        return absolute(value) if value is not None else None


class InspectCommand(Contract):
    command: Literal["inspect"] = "inspect"


class ConvertCommand(Contract):
    command: Literal["convert"] = "convert"
    proceed_with_warnings: bool = False


class SimpleCommand(Contract):
    command: Literal[
        "check_vault",
        "carry_inspection_to_convert",
        "start_another_conversion",
        "acknowledge_destination_review",
        "request_close",
    ]


class ApplyResult(Contract):
    command: Literal["apply_result"] = "apply_result"
    request_id: str
    input_revision: int = Field(ge=0)
    result: OperationResult
    process_status: int


class ApplyTransportFailure(Contract):
    command: Literal["apply_transport_failure"] = "apply_transport_failure"
    request_id: str
    phase: Literal["not_started", "may_have_executed"]
    code: Literal[
        "launch_failure", "protocol_failure", "worker_failure", "operation_unavailable"
    ]


SessionCommand = Annotated[
    SelectSource
    | SetDestination
    | SelectVault
    | InspectCommand
    | ConvertCommand
    | SimpleCommand
    | ApplyResult
    | ApplyTransportFailure,
    Field(discriminator="command"),
]
COMMAND = TypeAdapter(SessionCommand)


class SessionSnapshot(Contract):
    revision: int = 0
    source: str | None = None
    parent: str | None = None
    vault_name: str = ""
    vault: str | None = None
    result: OperationResult | None = None
    reviewed: ReviewedInspection | None = None
    conversion_primary_action: Literal["convert", "convert_with_warnings"] | None = None
    active_request_id: str | None = None
    busy_operation: Operation | None = None
    close_pending: bool = False
    field_errors: tuple[Finding, ...] = ()
    destination: str | None = None
    destination_validation: DestinationValidation | None = None
    destination_revision: int | None = None
    validation_request_id: str | None = None
    validation_pending: bool = False
    publication: Publication | None = None
    review_required: bool = False
    retry_operation: Literal["inspect", "convert_reviewed", "check_vault"] | None = None
    destination_review_acknowledged: bool = False
    recovery_findings: tuple[Finding, ...] = ()
    operational_status: (
        Literal["operation_not_started", "publication_unknown"] | None
    ) = None
    feedback: str = ""
    allowed_actions: tuple[Action, ...] = ("close",)
    can_check_selected_vault: bool = False


class RunOperation(Contract):
    effect: Literal["run_operation"] = "run_operation"
    request: WorkerRequest
    input_revision: int


class PersistOutputParent(Contract):
    effect: Literal["persist_output_parent"] = "persist_output_parent"
    path: str


class CloseWindow(Contract):
    effect: Literal["close_window"] = "close_window"


class SessionUpdate(Contract):
    snapshot: SessionSnapshot
    effects: tuple[RunOperation | PersistOutputParent | CloseWindow, ...] = ()


class DiagnosticPage(Contract):
    offset: int = Field(ge=0)
    text: str
    lines: tuple[str, ...]
    next_offset: int | None
