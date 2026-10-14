"""Synchronous public application operations and host-lifetime state.

The Qt adapter consumes these facts; it does not interpret Workflow trees.
"""

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from uuid import uuid4

from brz2obsidian import __version__
from brz2obsidian.application.contracts import (
    ApplyResult,
    ApplyTransportFailure,
    BrzSourceSelection,
    CheckArguments,
    CheckResult,
    CloseWindow,
    ConversionResult,
    ConvertArguments,
    DestinationArguments,
    DestinationValidation,
    DiagnosticPage,
    Finding,
    InspectArguments,
    InspectionResult,
    LocalApiSourceSelection,
    PersistOutputParent,
    Publication,
    ReviewedInspection,
    RunOperation,
    SelectVault,
    SessionCommand,
    SessionSnapshot,
    SessionUpdate,
    SimpleCommand,
    SourceSelection,
    WorkerRequest,
    same_source_selection,
    source_selection,
)
from brz2obsidian.application.conversion import convert
from brz2obsidian.contracts import Counts
from brz2obsidian.publication.filesystem import preflight_destination

# Deliberately static messages: backend Issue.message/evidence can contain authored
# text, filenames or exception strings. Never project them across this boundary.
SAFE_ISSUES = {
    "formatting_loss": "Included note formatting needs review: table layout may become responsive, custom icons use visible title fallbacks, or an insert remains unsupported. Review affected notes and declarations in the Migration report and edit the converted Markdown if needed.",
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


def _source_unavailable(operation):
    """The selection contract precedes local API acquisition/composition."""
    message = "The selected source kind is not available in this build."
    facts = {
        "outcome": "failed",
        "status": "inspection_failed"
        if operation == "inspect"
        else "conversion_failed",
        "findings": (
            Finding(code="operation_unavailable", severity="error", message=message),
        ),
        "review_required": True,
        "diagnostic_text": f"brz2obsidian diagnostic report\nOperation: {operation}\nOutcome: failed\noperation_unavailable: {message}",
    }
    if operation == "inspect":
        return InspectionResult(**facts)
    return ConversionResult(**facts, publication=Publication(state="not_published"))


class Operations:
    """Explicitly injected migration and checker composition for headless callers."""

    def __init__(self, workflow=None, *, checker=None):
        self.workflow = workflow
        self.checker = checker

    def convert_reviewed(
        self,
        source: Path | str | SourceSelection,
        parent: Path,
        vault_name: str,
        reviewed: ReviewedInspection,
        proceed_with_warnings: bool = False,
    ) -> ConversionResult:
        selection = source_selection(source)
        if isinstance(selection, LocalApiSourceSelection):
            return _source_unavailable("convert_reviewed")
        source = Path(selection.path)
        if self.workflow is None:
            from brz2obsidian.application.wiring import default_workflow

            self.workflow = default_workflow()
        return convert(
            self.workflow,
            source.absolute(),
            validate_destination(parent, vault_name),
            reviewed,
            proceed_with_warnings,
            source_selection=selection,
        )

    def inspect(self, source: Path | str | SourceSelection) -> InspectionResult:
        selection = source_selection(source)
        if isinstance(selection, LocalApiSourceSelection):
            return _source_unavailable("inspect")
        source = Path(selection.path)
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
                source_selection=selection,
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
                "Guidance: Review the planned contents and pending checks before conversion.",
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


def inspect(source: Path | str | SourceSelection) -> InspectionResult:
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
    source: Path | str | SourceSelection,
    parent: Path,
    vault_name: str,
    reviewed: ReviewedInspection,
    proceed_with_warnings: bool = False,
) -> ConversionResult:
    return Operations().convert_reviewed(
        source, parent, vault_name, reviewed, proceed_with_warnings
    )


def check_vault(vault: Path) -> CheckResult:
    return Operations().check_vault(vault)


@dataclass(frozen=True)
class CompletionTarget:
    """A current host-admitted target, never a worker request or filesystem proof."""

    action: str
    path: str


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
        self._diagnostic_generation = 0
        self._closed = False
        self._lock = RLock()

    @property
    def snapshot(self) -> SessionSnapshot:
        return self._snapshot

    def dispatch(self, command: SessionCommand) -> SessionUpdate:
        with self._lock:
            return self._dispatch(command)

    def dispatch_if_current(
        self, command: SessionCommand, expected_revision: int
    ) -> SessionUpdate:
        """Apply an asynchronous input only while its captured revision is current."""
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Expected revision must be a nonnegative integer")
        with self._lock:
            if self._snapshot.revision != expected_revision:
                return SessionUpdate(snapshot=self._snapshot)
            return self._dispatch(command)

    def _dispatch(self, command):
        state = self._snapshot
        if self._closed:
            return SessionUpdate(snapshot=state)
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
                    self._diagnostic_generation += 1
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
                        and same_source_selection(
                            command.result.reviewed.source_selection,
                            state.source_selection,
                        )
                        else None
                    )
                    if command.result.operation == "check_vault" or (
                        command.result.operation == "convert_reviewed"
                        and eligible
                        and not command.result.review_required
                        and command.result.publication.state == "not_published"
                    ):
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
                            "retry_operation": (
                                "inspect"
                                if command.result.operation == "convert_reviewed"
                                and command.result.review_required
                                else command.result.operation
                            )
                            if command.result.outcome in ("refused", "failed", "issues")
                            else None,
                        }
                    )
                    if command.result.operation == "convert_reviewed":
                        state = state.model_copy(
                            update={
                                "publication": state.publication
                                if state.publication is not None
                                and state.publication.state == "unknown"
                                and not command.result.publication.receipt_verified
                                else command.result.publication,
                                "destination": command.result.destination,
                                "field_errors": command.result.field_errors,
                                "destination_validation": None,
                                "destination_revision": None,
                                "validation_pending": False,
                                "recovery_findings": tuple(
                                    finding
                                    for finding in command.result.findings
                                    if finding.code == "cleanup_failure"
                                ),
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
        elif (
            name == "start_another_conversion"
            and "start_another_conversion" in state.allowed_actions
        ):
            self._diagnostic_generation += 1
            self._diagnostic_text = ""
            state = state.model_copy(
                update={
                    "revision": state.revision + 1,
                    "result": None,
                    "publication": None,
                    "reviewed": None,
                    "review_required": True,
                    "retry_operation": None,
                    "destination_review_acknowledged": False,
                    "recovery_findings": (),
                    "vault_name": "",
                    "destination": None,
                    "destination_validation": None,
                    "destination_revision": None,
                    "validation_pending": False,
                    "field_errors": (),
                    "operational_status": None,
                    "feedback": "Inspect the current archive and choose another usable destination for a new conversion.",
                }
            )
        elif (
            name == "acknowledge_destination_review"
            and "review_destination" in state.allowed_actions
        ):
            state = self._destination_edited(
                state.model_copy(
                    update={
                        "revision": state.revision + 1,
                        "destination_review_acknowledged": True,
                        "reviewed": None,
                        "review_required": True,
                        "feedback": "Destination review acknowledged. Publication remains unknown. Inspect the current archive and validate a usable destination before another attempt.",
                    }
                )
            )
        elif (
            state.publication is not None
            and (
                state.publication.receipt_verified
                or state.publication.state == "unknown"
                and not state.destination_review_acknowledged
            )
            and name
            in (
                "select_source",
                "set_destination",
                "convert",
                "inspect",
                "start_another_conversion",
                "acknowledge_destination_review",
            )
        ):
            # Neither a bypassed form command nor a retry establishes what an
            # unknown attempt published or discards a verified receipt.
            return SessionUpdate(snapshot=state)
        elif name == "select_source":
            selected = command.source_selection
            if selected is not None and not same_source_selection(
                selected, state.source_selection
            ):
                self._diagnostic_generation += 1
                self._diagnostic_text = ""
                state = state.model_copy(
                    update={
                        "source_selection": selected,
                        "revision": state.revision + 1,
                        "result": None,
                        "reviewed": None,
                        "review_required": True,
                        "retry_operation": None,
                        "operational_status": None,
                        "feedback": "",
                        "vault_name": Path(selected.path).stem
                        if isinstance(selected, BrzSourceSelection)
                        else "",
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
                if command.parent_or_null is not None and (
                    command.parent_or_null != state.parent
                ):
                    effects = (PersistOutputParent(path=command.parent_or_null),)
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
                self._diagnostic_generation += 1
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
        elif (
            name == "check_vault"
            and "check_vault" in state.allowed_actions
            and state.vault is not None
        ):
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
                arguments=InspectArguments(source_selection=state.source_selection),
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
        elif (
            name == "convert"
            and "retry" in state.allowed_actions
            and state.retry_operation == "convert_reviewed"
        ):
            state = self._destination_edited(state)
        elif name == "convert" and (
            "convert" in state.allowed_actions
            or command.proceed_with_warnings
            and "convert_with_warnings" in state.allowed_actions
        ):
            request = WorkerRequest(
                request_id=str(uuid4()),
                operation="convert_reviewed",
                arguments=ConvertArguments(
                    source_selection=state.source_selection,
                    parent=state.parent,
                    vault_name=state.vault_name,
                    reviewed=state.reviewed,
                    proceed_with_warnings=command.proceed_with_warnings,
                ),
            )
            self._active_revision = state.revision
            state = state.model_copy(
                update={
                    "active_request_id": request.request_id,
                    "busy_operation": "convert_reviewed",
                    "recovery_findings": (),
                    "feedback": "",
                    "operational_status": None,
                }
            )
            effects = (RunOperation(request=request, input_revision=state.revision),)
        elif (
            name == "carry_inspection_to_convert"
            and "convert_this_archive" in state.allowed_actions
        ):
            state = state.model_copy(update={"feedback": ""})
        elif name in (
            "convert",
            "start_another_conversion",
            "acknowledge_destination_review",
        ):
            return SessionUpdate(snapshot=state)
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
        if any(
            effect.effect == "run_operation"
            and effect.request.operation != "validate_destination"
            for effect in effects
        ):
            # Applies equally to future primary operations using this contract.
            self._diagnostic_generation += 1
            self._diagnostic_text = ""
            state = state.model_copy(update={"retry_operation": None})
        if any(effect.effect == "close_window" for effect in effects):
            self._closed = True
            self._diagnostic_generation += 1
            self._diagnostic_text = ""
            # Retain summary facts in the final update, but release its report.
            if state.result is not None:
                state = state.model_copy(
                    update={
                        "result": state.result.model_copy(
                            update={"diagnostic_text": "", "diagnostic_omission": None}
                        )
                    }
                )
        actions = []
        if not self._closed and not state.active_request_id and not state.close_pending:
            if state.publication is not None and state.publication.receipt_verified:
                actions.append("start_another_conversion")
            if (
                state.publication is not None
                and state.publication.state == "unknown"
                and not state.destination_review_acknowledged
            ):
                actions.append("review_destination")
            if state.source_selection and (
                state.publication is None
                or state.publication.state == "not_published"
                or state.destination_review_acknowledged
            ):
                actions.append("inspect")
            if state.reviewed:
                actions.append("convert_this_archive")
            if (
                state.reviewed is not None
                and same_source_selection(
                    state.reviewed.source_selection, state.source_selection
                )
                and not state.review_required
                and state.destination_validation is not None
                and state.destination_validation.outcome == "valid"
                and state.destination == state.destination_validation.destination
                and not state.validation_pending
                and not state.validation_request_id
                and (
                    state.publication is None
                    or state.publication.state == "not_published"
                    or state.publication.state == "unknown"
                    and state.destination_review_acknowledged
                )
            ):
                actions.append(
                    "convert"
                    if state.reviewed.outcome == "clean"
                    else "convert_with_warnings"
                )
            if state.publication is not None and state.publication.receipt_verified:
                actions.extend(
                    ("open_folder", "open_migration_report", "open_in_obsidian")
                )
            if state.vault or (
                state.publication is not None and state.publication.receipt_verified
            ):
                actions.append("check_vault")
            if (
                state.retry_operation is not None
                and (
                    state.retry_operation == "check_vault"
                    or state.publication is None
                    or state.publication.state == "not_published"
                    or state.publication.state == "unknown"
                    and state.destination_review_acknowledged
                )
                and not state.validation_pending
                and not state.validation_request_id
                and (
                    state.retry_operation != "convert_reviewed"
                    or state.destination_validation is None
                    or state.destination_validation.outcome != "valid"
                )
            ):
                actions.append("retry")
            if self._diagnostic_text:
                actions.extend(("copy_details", "save_diagnostic_report"))
        actions.append("close")
        # Presentation intent is independent of destination readiness. The UI
        # must not inspect the opaque review to label its disabled primary.
        conversion_primary_action = None
        if (
            state.reviewed is not None
            and same_source_selection(
                state.reviewed.source_selection, state.source_selection
            )
            and not state.review_required
        ):
            conversion_primary_action = (
                "convert"
                if state.reviewed.outcome == "clean"
                else "convert_with_warnings"
            )
        self._snapshot = state.model_copy(
            update={
                "allowed_actions": tuple(actions),
                "conversion_primary_action": conversion_primary_action,
                "can_check_selected_vault": state.vault is not None
                and "check_vault" in actions,
            }
        )
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
        self._diagnostic_generation += 1
        converting = state.busy_operation == "convert_reviewed"
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
        self._diagnostic_text = "\n".join(
            (
                "brz2obsidian diagnostic report",
                f"Operation: {state.busy_operation}",
                selected,
                *(
                    (f"Destination: {state.destination or 'unavailable'}",)
                    if state.busy_operation == "convert_reviewed"
                    else ()
                ),
                f"Converter: {__version__}",
                "Counts: unavailable",
                "Outcome: operational error",
                f"Code: {code}",
                feedback,
            )
        )
        updates = {
            "result": None,
            "reviewed": state.reviewed
            if checking or converting and phase == "not_started"
            else None,
            "review_required": state.review_required
            if checking or converting and phase == "not_started"
            else True,
            "feedback": feedback,
            "operational_status": status,
            "retry_operation": "inspect"
            if converting and phase != "not_started"
            else state.busy_operation,
        }
        if converting:
            updates.update(
                publication=state.publication
                if state.publication is not None
                and state.publication.state == "unknown"
                else Publication(
                    state="not_published" if phase == "not_started" else "unknown",
                    destination=state.destination if phase != "not_started" else None,
                ),
                destination_validation=None,
                destination_revision=None,
                validation_pending=False,
                destination_review_acknowledged=state.destination_review_acknowledged
                if phase == "not_started"
                else False,
            )
        return state.model_copy(update=updates)

    def diagnostics_text(self) -> str:
        """Current safe text for an explicitly requested background export."""
        with self._lock:
            return self._diagnostic_text

    def admit_completion_action(
        self, action: str, expected_generation: int
    ) -> CompletionTarget | None:
        """Derive an optional-open target from current verified host facts only."""
        if action not in ("open_folder", "open_migration_report", "open_in_obsidian"):
            raise ValueError("Unknown completion action")
        self._completion_generation(expected_generation)
        with self._lock:
            destination = self._current_published_destination(expected_generation)
            if destination is None or action not in self._snapshot.allowed_actions:
                return None
            path = (
                destination
                if action == "open_folder"
                else destination / "MIGRATION REPORT.md"
            )
            return CompletionTarget(action, str(path))

    def check_published_vault(self, expected_generation: int) -> SessionUpdate:
        """Atomically select the current published vault and admit an explicit check."""
        self._completion_generation(expected_generation)
        with self._lock:
            destination = self._current_published_destination(expected_generation)
            if (
                destination is None
                or "check_vault" not in self._snapshot.allowed_actions
            ):
                return SessionUpdate(snapshot=self._snapshot)
            self._dispatch(SelectVault(path_or_null=str(destination)))
            return self._dispatch(SimpleCommand(command="check_vault"))

    @staticmethod
    def _completion_generation(generation):
        if type(generation) is not int or generation < 0:
            raise ValueError("Expected generation must be a nonnegative integer")

    def _current_published_destination(self, generation):
        state = self._snapshot
        publication = state.publication
        if (
            self._closed
            or generation != self._diagnostic_generation
            or state.active_request_id
            or state.close_pending
            or publication is None
            or not publication.receipt_verified
        ):
            return None
        return Path(publication.destination)

    @property
    def diagnostic_generation(self) -> int:
        """Opaque host-only identity; input revisions do not identify reports."""
        with self._lock:
            return self._diagnostic_generation

    @staticmethod
    def _validate_generation(expected_generation):
        if type(expected_generation) is not int or expected_generation < 0:
            raise ValueError("A nonnegative diagnostic generation is required")

    def admit_diagnostic_report(
        self, action: str, expected_generation: int
    ) -> str | None:
        """Capture only the currently permitted report for an explicit export.

        This bounded admission does not encode/write text or invoke adapters.
        The caller starts its background side effect immediately after admission.
        """
        self._validate_generation(expected_generation)
        if action not in ("copy_details", "save_diagnostic_report"):
            raise ValueError("A diagnostic export action is required")
        with self._lock:
            if (
                self._closed
                or expected_generation != self._diagnostic_generation
                or action not in self._snapshot.allowed_actions
            ):
                return None
            return self._diagnostic_text or None

    def diagnostics_page_if_current(
        self, expected_generation: int, offset: int = 0, limit: int = 100
    ) -> DiagnosticPage | None:
        """Prepare a bounded page only while its host report identity is current."""
        self._validate_generation(expected_generation)
        with self._lock:
            if self._closed or expected_generation != self._diagnostic_generation:
                return None
            return self.diagnostics_page(offset, limit)

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
