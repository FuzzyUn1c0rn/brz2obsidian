"""Synchronous public application operations and host-lifetime state.

The Qt adapter consumes these facts; it does not interpret Workflow trees.
"""

from pathlib import Path
from threading import RLock
from uuid import uuid4

from brz2obsidian import __version__
from brz2obsidian.application.contracts import (
    ApplyResult,
    ApplyTransportFailure,
    CheckArguments,
    CheckResult,
    CloseWindow,
    ConversionResult,
    DestinationArguments,
    DestinationValidation,
    DiagnosticPage,
    Finding,
    InspectArguments,
    InspectionResult,
    ReviewedInspection,
    RunOperation,
    SessionCommand,
    SessionSnapshot,
    SessionUpdate,
    WorkerRequest,
)
from brz2obsidian.contracts import Counts
from brz2obsidian.publication.filesystem import preflight_destination

# Deliberately static messages: backend Issue.message/evidence can contain authored
# text, filenames or exception strings. Never project them across this boundary.
SAFE_ISSUES = {
    "invalid_source": "The archive does not contain a supported, consistent source. Re-export it from TheBrain.",
    "invalid_entry": "The source needs a valid live Home thought. Set Home and re-export.",
    "invalid_reference": "Source references could not be interpreted safely. Review the export and re-export.",
    "unsupported_feature": "The source contains an unsupported feature. Review the export before continuing.",
    "source_changed": "The source changed while it was being read. Inspect a stable export again.",
    "payload_read_failure": "An archived resource could not be read. Check the export and source access.",
    "operation_failure": "Inspection could not complete. Check source access and inspect again.",
    "session_teardown_failure": "The source could not be closed normally. Check source access and inspect again.",
    "target_path_too_long": "A planned path exceeds the supported Windows path limit.",
    "absent_payload": "An archived resource is unavailable. Review source warnings before conversion.",
    "source_gap": "Source content is unavailable. Review source warnings before conversion.",
    "approved_source_gap": "Source note, icon or resource bytes are unavailable. Their absence will be disclosed during conversion. Review these source limitations before continuing.",
    "approved_metadata_discrepancy": "Source resource metadata differs from the available bytes. Conversion preserves verified actual bytes and reports the discrepancy.",
}


class Operations:
    """Explicitly injected migration and checker composition for headless callers."""

    def __init__(self, workflow=None, *, checker=None):
        self.workflow = workflow
        self.checker = checker

    def inspect(self, source: Path) -> InspectionResult:
        if self.workflow is None:
            from brz2obsidian.application.wiring import default_workflow

            self.workflow = default_workflow()
        source = source.absolute()
        raw = self.workflow.inspect(source)
        usable = (
            raw.outcome in ("clean", "warnings")
            and raw.inspection is not None
            and raw.source_identity is not None
            and raw.profile_id is not None
            and raw.profile_version is not None
        )
        outcome = (
            raw.outcome if usable or raw.outcome in ("refused", "failed") else "failed"
        )
        reviewed = (
            ReviewedInspection(
                source=str(source),
                source_identity=raw.source_identity,
                converter_version=raw.converter_version,
                profile_id=raw.profile_id,
                profile_version=raw.profile_version,
                outcome=outcome,
            )
            if usable
            else None
        )
        findings = tuple(
            Finding(
                code=issue.code if issue.code in SAFE_ISSUES else "inspection_finding",
                severity=issue.severity,
                message=SAFE_ISSUES.get(
                    issue.code,
                    "Inspection found a source limitation. Review the export and its supported content before conversion.",
                ),
                field="source",
            )
            for issue in raw.issues
        )
        counts = raw.counts or Counts()
        checked = (
            (
                "source_structure",
                "source_identity",
                "planned_content",
                "source_consistency",
            )
            if usable
            else ("source_inspection",)
        )
        pending = (
            "destination_feasibility",
            "source_freshness",
            "publication",
            "generated_vault_check",
        )
        text = "\n".join(
            (
                "brz2obsidian diagnostic report",
                "Operation: inspect",
                f"Source: {source}",
                f"Converter: {__version__}",
                f"Profile: {raw.profile_id or 'unavailable'} / {raw.profile_version or 'unavailable'}",
                f"Outcome: {outcome}",
                "Counts are planned; actual publication counts are unavailable.",
                *(
                    f"{name}: {value if value is not None else 'unavailable'}"
                    for name, value in counts.model_dump().items()
                ),
                *(f"{finding.code}: {finding.message}" for finding in findings),
                "Pending: " + ", ".join(pending),
            )
        )
        return InspectionResult(
            outcome=outcome,
            status="inspection_" + outcome,
            counts=counts,
            findings=findings,
            reviewed=reviewed,
            checked=checked,
            pending=pending,
            review_required=not usable,
            diagnostic_text=text,
        )

    def check_vault(self, vault: Path) -> CheckResult:
        from brz2obsidian.application.checking import check_vault as check_current_vault

        return check_current_vault(vault, checker=self.checker)


def inspect(source: Path) -> InspectionResult:
    return Operations().inspect(source)


def validate_destination(parent: Path, vault_name: str) -> DestinationValidation:
    preliminary = preflight_destination(parent, vault_name)
    outcome = (
        "failed" if preliminary.failed else "invalid" if preliminary.errors else "valid"
    )
    errors = tuple(
        Finding(
            code=error.code, severity="error", message=error.message, field=error.field
        )
        for error in preliminary.errors
    )
    destination = (
        str(preliminary.destination) if preliminary.destination is not None else None
    )
    pending = (
        "generated_paths",
        "generated_collisions",
        "manifest_feasibility",
        "absolute_path_limit",
        "write_success",
    )
    text = "\n".join(
        (
            "brz2obsidian diagnostic report",
            "Operation: validate_destination",
            f"Parent: {parent}",
            f"Destination: {destination or 'unavailable'}",
            f"Outcome: {outcome}",
            *(f"{error.code}: {error.message}" for error in errors),
            "Preliminary check only. No reservation or writeability promise.",
            "Generated paths, collisions, manifest and final 240 UTF-16-unit absolute-path limit remain pending. Writes are checked during publication.",
        )
    )
    return DestinationValidation(
        outcome=outcome,
        status="destination_" + outcome,
        destination=destination,
        field_errors=errors,
        checked=preliminary.checked,
        pending=pending,
        diagnostic_text=text,
    )


def convert_reviewed(
    source: Path,
    parent: Path,
    vault_name: str,
    reviewed: ReviewedInspection,
    proceed_with_warnings: bool = False,
) -> ConversionResult:
    raise NotImplementedError("Reviewed conversion is not available in this build")


def check_vault(vault: Path) -> CheckResult:
    return Operations().check_vault(vault)


class ApplicationSession:
    """Admission and reduction for one launch; use from a serialized outer runner.

    Primary operation workers may exit without losing the safe diagnostic report.
    No filesystem access, Qt types or transport implementation is needed here.
    """

    def __init__(self):
        self._snapshot = SessionSnapshot()
        self._active_revision = None
        self._validation_revision = None
        self._diagnostic_text = ""
        self._lock = RLock()

    @property
    def snapshot(self) -> SessionSnapshot:
        return self._snapshot

    def dispatch(self, command: SessionCommand) -> SessionUpdate:
        with self._lock:
            return self._dispatch(command)

    def _dispatch(self, command):
        state = self._snapshot
        effects = ()
        name = command.command
        if name == "request_close":
            if state.active_request_id or state.validation_request_id:
                state = state.model_copy(
                    update={
                        "close_pending": True,
                        "feedback": "Close requested. Waiting for the operation to finish.",
                    }
                )
            else:
                effects = (CloseWindow(),)
        elif (
            isinstance(command, (ApplyResult, ApplyTransportFailure))
            and command.request_id == state.validation_request_id
        ):
            state = self._validation_terminal(state, command)
        elif isinstance(command, (ApplyResult, ApplyTransportFailure)):
            if command.request_id != state.active_request_id:
                return SessionUpdate(snapshot=state)
            if isinstance(command, ApplyResult):
                expected_exit = {
                    "clean": 0,
                    "warnings": 2,
                    "refused": 1,
                    "failed": 1,
                    "valid": 0,
                    "invalid": 1,
                    "issues": 2,
                }[command.result.outcome]
                trusted = (
                    command.result.operation == state.busy_operation
                    and command.process_status == expected_exit
                )
                if trusted:
                    self._diagnostic_text = command.result.diagnostic_text
                    eligible = (
                        command.input_revision
                        == self._active_revision
                        == state.revision
                    )
                    reviewed = (
                        command.result.reviewed
                        if eligible
                        and command.result.reviewed is not None
                        and command.result.reviewed.source == state.source
                        else None
                    )
                    if command.result.operation == "check_vault":
                        reviewed = state.reviewed
                    state = state.model_copy(
                        update={
                            "result": command.result,
                            "reviewed": reviewed,
                            "review_required": state.review_required
                            if command.result.operation == "check_vault"
                            else command.result.review_required or not eligible,
                            "feedback": "",
                            "operational_status": None,
                        }
                    )
                else:
                    state = self._failure(
                        state, "may_have_executed", "protocol_failure"
                    )
            else:
                state = self._failure(state, command.phase, command.code)
            state = state.model_copy(
                update={"active_request_id": None, "busy_operation": None}
            )
            self._active_revision = None
            if state.close_pending and not state.validation_request_id:
                effects = (CloseWindow(),)
        elif state.active_request_id or state.close_pending:
            # UI disabling is only presentation; bypassed calls cannot mutate the
            # active source/review or start overlapping primary operations.
            return SessionUpdate(snapshot=state)
        elif name == "select_source":
            if (
                command.path_or_null is not None
                and command.path_or_null != state.source
            ):
                from brz2obsidian.application.contracts import absolute

                absolute(command.path_or_null)
                self._diagnostic_text = ""
                state = state.model_copy(
                    update={
                        "source": command.path_or_null,
                        "revision": state.revision + 1,
                        "result": None,
                        "reviewed": None,
                        "review_required": True,
                        "operational_status": None,
                        "feedback": "",
                        "vault_name": Path(command.path_or_null).stem,
                    }
                )
                state = self._destination_edited(state)
        elif name == "set_destination":
            if (command.parent_or_null, command.vault_name) != (
                state.parent,
                state.vault_name,
            ) or (
                state.destination_validation is not None
                and state.destination_validation.outcome == "failed"
            ):
                state = self._destination_edited(
                    state.model_copy(
                        update={
                            "parent": command.parent_or_null,
                            "vault_name": command.vault_name,
                            "revision": state.revision + 1,
                        }
                    )
                )
        elif name == "select_vault":
            if command.path_or_null is not None and command.path_or_null != state.vault:
                self._diagnostic_text = ""
                state = state.model_copy(
                    update={
                        "vault": command.path_or_null,
                        "revision": state.revision + 1,
                        "result": None,
                        "operational_status": None,
                        "feedback": "",
                    }
                )
        elif name == "check_vault" and "check_vault" in state.allowed_actions:
            request = WorkerRequest(
                request_id=str(uuid4()),
                operation="check_vault",
                arguments=CheckArguments(vault=state.vault),
            )
            self._active_revision = state.revision
            state = state.model_copy(
                update={
                    "active_request_id": request.request_id,
                    "busy_operation": "check_vault",
                    "feedback": "",
                    "operational_status": None,
                }
            )
            effects = (RunOperation(request=request, input_revision=state.revision),)
        elif name == "inspect" and "inspect" in state.allowed_actions:
            request = WorkerRequest(
                request_id=str(uuid4()),
                operation="inspect",
                arguments=InspectArguments(source=state.source),
            )
            self._active_revision = state.revision
            state = state.model_copy(
                update={
                    "active_request_id": request.request_id,
                    "busy_operation": "inspect",
                    "reviewed": None,
                    "feedback": "",
                    "operational_status": None,
                }
            )
            effects = (RunOperation(request=request, input_revision=state.revision),)
        elif name == "carry_inspection_to_convert" and state.reviewed:
            state = state.model_copy(
                update={"feedback": "Reviewed archive retained for Convert."}
            )
        elif name in (
            "convert",
            "start_another_conversion",
            "acknowledge_destination_review",
        ):
            state = state.model_copy(
                update={"feedback": "This operation is not available in this build."}
            )
        if state.close_pending and not (
            state.active_request_id or state.validation_request_id
        ):
            effects = (CloseWindow(),)
            state = state.model_copy(update={"close_pending": False})
        elif (
            state.validation_pending
            and not state.validation_request_id
            and not state.close_pending
        ):
            request = WorkerRequest(
                request_id=str(uuid4()),
                operation="validate_destination",
                arguments=DestinationArguments(
                    parent=state.parent, vault_name=state.vault_name
                ),
            )
            self._validation_revision = state.revision
            state = state.model_copy(
                update={"validation_request_id": request.request_id}
            )
            effects += (RunOperation(request=request, input_revision=state.revision),)
        actions = []
        if not state.active_request_id and not state.close_pending:
            if state.source:
                actions.append("inspect")
            if state.reviewed:
                actions.append("convert_this_archive")
            if state.vault:
                actions.append("check_vault")
                if (
                    state.result is not None
                    and state.result.operation == "check_vault"
                    and state.result.outcome in ("issues", "failed")
                ) or (state.feedback and state.result is None):
                    actions.append("retry")
            if self._diagnostic_text:
                actions.extend(("copy_details", "save_diagnostic_report"))
        actions.append("close")
        self._snapshot = state.model_copy(update={"allowed_actions": tuple(actions)})
        return SessionUpdate(snapshot=self._snapshot, effects=effects)

    def _destination_edited(self, state):
        return state.model_copy(
            update={
                "destination": None,
                "destination_validation": None,
                "destination_revision": None,
                "validation_pending": state.parent is not None,
                "field_errors": ()
                if state.parent is not None
                else (
                    Finding(
                        code="parent_required",
                        severity="error",
                        message="Choose an output parent folder.",
                        field="parent",
                    ),
                ),
            }
        )

    def _validation_terminal(self, state, command):
        current = (
            isinstance(command, ApplyResult)
            and command.input_revision == self._validation_revision == state.revision
        )
        trusted = (
            isinstance(command, ApplyResult)
            and isinstance(command.result, DestinationValidation)
            and command.process_status
            == (0 if command.result.outcome == "valid" else 1)
        )
        if self._validation_revision == state.revision:
            result = (
                command.result
                if current and trusted
                else DestinationValidation(
                    outcome="failed",
                    status="destination_failed",
                    field_errors=(
                        Finding(
                            code="destination_validation_failure",
                            severity="error",
                            field="destination",
                            message="The destination check did not complete reliably. Edit or choose the destination again when ready.",
                        ),
                    ),
                    pending=("destination_feasibility", "write_success"),
                    diagnostic_text="Destination validation did not return a trustworthy result. No write or reservation was performed by this preliminary check.",
                )
            )
            state = state.model_copy(
                update={
                    "destination_validation": result,
                    "destination_revision": state.revision,
                    "destination": result.destination,
                    "field_errors": result.field_errors,
                    "validation_pending": False,
                }
            )
        self._validation_revision = None
        return state.model_copy(update={"validation_request_id": None})

    def _failure(self, state, phase, code):
        checking = state.busy_operation == "check_vault"
        status = (
            "operation_not_started"
            if phase == "not_started"
            else "publication_unknown"
            if state.busy_operation == "convert_reviewed"
            else None
        )
        feedback = (
            "Check could not complete. The operation could not start. Check the local Python environment."
            if checking and phase == "not_started"
            else "Check could not complete. The worker did not return a trustworthy result. Check vault access and try again when ready."
            if checking
            else "The operation could not start. Check the local Python environment."
            if phase == "not_started"
            else "Publication status unknown. Review the destination before another attempt."
            if state.busy_operation == "convert_reviewed"
            else "The operation did not return a trustworthy result. Check the source and try again when ready."
        )
        selected = (
            f"Vault: {state.vault or 'unavailable'}"
            if checking
            else f"Source: {state.source or 'unavailable'}"
        )
        self._diagnostic_text = f"brz2obsidian diagnostic report\nOperation: {state.busy_operation}\n{selected}\nOutcome: operational error\nCode: {code}\n{feedback}"
        return state.model_copy(
            update={
                "result": None,
                "reviewed": state.reviewed if checking else None,
                "review_required": state.review_required if checking else True,
                "feedback": feedback,
                "operational_status": status,
            }
        )

    def diagnostics_text(self) -> str:
        """Current safe text for an explicitly requested background export."""
        with self._lock:
            return self._diagnostic_text

    def diagnostics_page(self, offset: int = 0, limit: int = 100) -> DiagnosticPage:
        """Character offsets allow oversized individual lines to be paged safely."""
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise ValueError("A nonnegative offset and 1–100 lines are required")
        with self._lock:
            text = self._diagnostic_text
            if offset > len(text):
                raise ValueError("Diagnostic offset is outside the current report")
            # At most 32 Ki characters are examined/encoded, even for a single
            # enormous line. UTF-8 decoding drops only a partial final character.
            candidate = (
                text[offset : offset + 32768]
                .encode("utf-8")[:32768]
                .decode("utf-8", errors="ignore")
            )
            lines = candidate.splitlines(keepends=True)[:limit]
            returned = "".join(lines)
            next_offset = offset + len(returned)
            return DiagnosticPage(
                offset=offset,
                text=returned,
                lines=tuple(lines),
                next_offset=next_offset if next_offset < len(text) else None,
            )
