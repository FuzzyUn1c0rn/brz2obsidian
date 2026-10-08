"""Serialized session host and outer worker execution, with no Qt imports."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from brz2obsidian.application.contracts import (
    ApplyResult,
    ApplyTransportFailure,
    DiagnosticPage,
    SessionUpdate,
)
from brz2obsidian.application.operations import ApplicationSession


@dataclass(frozen=True)
class PresentationUpdate:
    update: SessionUpdate
    diagnostics: DiagnosticPage
    diagnostic_generation: int = 0


@dataclass(frozen=True)
class DiagnosticPresentation:
    generation: int
    page: DiagnosticPage


@dataclass(frozen=True)
class DiagnosticFeedback:
    generation: int
    message: str
    succeeded: bool = False


class HostRunner:
    """Callbacks deliver immutable prepared facts; GUI adapters marshal them.

    Session reduction, process launch/wait, parsing and report preparation all
    run on outer threads. The serialized command executor remains available
    while an independent primary-operation executor waits for its child.
    """

    def __init__(
        self, supervisor, on_update, on_page, session=None, on_diagnostic_feedback=None
    ):
        self.session = session if session is not None else ApplicationSession()
        self.supervisor, self.on_update, self.on_page = supervisor, on_update, on_page
        self.on_diagnostic_feedback = on_diagnostic_feedback or (lambda feedback: None)
        self._commands = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="application-session"
        )
        self._operations = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="operation-supervisor"
        )
        self._validation = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="destination-supervisor"
        )
        self._exports = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="diagnostic-export"
        )

    def submit(self, command):
        self._commands.submit(self._dispatch, command)

    def _dispatch(self, command):
        update = self.session.dispatch(command)
        self.on_update(
            PresentationUpdate(
                update,
                self.session.diagnostics_page(),
                self.session.diagnostic_generation,
            )
        )
        for effect in update.effects:
            if effect.effect == "run_operation":
                executor = (
                    self._validation
                    if effect.request.operation == "validate_destination"
                    else self._operations
                )
                executor.submit(self._run, effect)

    def _run(self, effect):
        try:
            terminal = self.supervisor.run(effect.request)
            if terminal.phase == "completed":
                command = ApplyResult(
                    request_id=effect.request.request_id,
                    input_revision=effect.input_revision,
                    result=terminal.response.result,
                    process_status=terminal.process_status,
                )
            else:
                command = ApplyTransportFailure(
                    request_id=effect.request.request_id,
                    phase=terminal.phase,
                    code=terminal.code,
                )
        except Exception:  # noqa: BLE001 -- outer adapter boundary preserves safe failure semantics.
            command = ApplyTransportFailure(
                request_id=effect.request.request_id,
                phase="may_have_executed",
                code="worker_failure",
            )
        self.submit(command)

    def request_diagnostic_page(self, offset=0, expected_generation=None):
        generation = (
            self.session.diagnostic_generation
            if expected_generation is None
            else expected_generation
        )
        self._exports.submit(self._prepare_page, offset, generation)

    def _prepare_page(self, offset, generation):
        page = self.session.diagnostics_page_if_current(generation, offset)
        if page is not None:
            self.on_page(DiagnosticPresentation(generation, page))

    def request_diagnostic_export(self, action, expected_generation, perform):
        """Queue intent only; no old result/report is retained before admission."""
        self._exports.submit(self._export, action, expected_generation, perform)

    def _export(self, action, generation, perform):
        text = self.session.admit_diagnostic_report(action, generation)
        if text is None:
            self.on_diagnostic_feedback(
                DiagnosticFeedback(
                    generation,
                    "The diagnostic report changed. Use the current report and try again.",
                )
            )
            return
        try:
            outcome = perform(text)
            feedback = DiagnosticFeedback(
                generation, outcome.message, outcome.succeeded
            )
        except Exception:  # noqa: BLE001 -- outer platform action failures are nonfatal.
            feedback = DiagnosticFeedback(
                generation,
                "The diagnostic action could not complete. Your operation result is retained.",
            )
        self.on_diagnostic_feedback(feedback)

    def shutdown(self):
        # A normal close is admitted only after the primary terminal result.
        # No GUI-thread join, timeout policy or child termination is introduced.
        self._operations.shutdown(wait=False)
        self._validation.shutdown(wait=False)
        self._exports.shutdown(wait=False, cancel_futures=True)
        self._commands.shutdown(wait=False)
