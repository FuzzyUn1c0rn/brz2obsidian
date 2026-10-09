"""Serialized session host and outer worker execution, with no Qt imports."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Event

from brz2obsidian.application.contracts import (
    ApplyResult,
    ApplyTransportFailure,
    DiagnosticPage,
    SessionUpdate,
    SetDestination,
)
from brz2obsidian.application.operations import ApplicationSession

_UNGUARDED = object()


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
    path: str | None = None


@dataclass(frozen=True)
class CompletionFeedback:
    generation: int
    message: str
    succeeded: bool = False
    path: str | None = None


@dataclass(frozen=True)
class PreferenceFeedback:
    text: str
    input_revision: int


class HostRunner:
    """Callbacks deliver immutable prepared facts; GUI adapters marshal them.

    Session reduction, process launch/wait, parsing and report preparation all
    run on outer threads. The serialized command executor remains available
    while an independent primary-operation executor waits for its child.
    """

    def __init__(
        self,
        supervisor,
        on_update,
        on_page,
        session=None,
        on_diagnostic_feedback=None,
        preferences=None,
        on_feedback=None,
        on_completion_feedback=None,
    ):
        self.session = session if session is not None else ApplicationSession()
        self.supervisor, self.on_update, self.on_page = supervisor, on_update, on_page
        self.preferences = preferences
        self.on_feedback = on_feedback or (lambda feedback: None)
        self._stopped = Event()
        self.on_diagnostic_feedback = on_diagnostic_feedback or (lambda feedback: None)
        self.on_completion_feedback = on_completion_feedback or (lambda feedback: None)
        self._commands = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="application-session"
        )
        self._operations = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="operation-supervisor"
        )
        self._validation = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="destination-supervisor"
        )
        self._preferences = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="output-parent-preference"
        )
        self._exports = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="diagnostic-export"
        )
        self._completion = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="completion-action"
        )

    def submit(self, command):
        self._commands.submit(self._dispatch, command)

    def submit_if_current(self, command, expected_revision, on_complete=None):
        self._commands.submit(self._dispatch, command, expected_revision, on_complete)

    def _dispatch(self, command, expected_revision=_UNGUARDED, on_complete=None):
        update = (
            self.session.dispatch(command)
            if expected_revision is _UNGUARDED
            else self.session.dispatch_if_current(command, expected_revision)
        )
        self._deliver(update)
        if on_complete is not None:
            on_complete(update)

    def _deliver(self, update):
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
            elif effect.effect == "persist_output_parent" and self.preferences:
                self._preferences.submit(
                    self._save_parent, effect.path, update.snapshot.revision
                )

    def restore_preferences(self):
        if self.preferences is not None:
            self._commands.submit(self._begin_restore)

    def _begin_restore(self):
        revision = self.session.snapshot.revision
        self._preferences.submit(self._load_parent, revision)

    def _load_parent(self, revision):
        try:
            result = self.preferences.load()
        except Exception:  # noqa: BLE001 -- safe outer I/O failure feedback.
            self._queue_feedback(
                "The saved output folder could not be read. Choose a folder.", revision
            )
            return
        if not self._stopped.is_set():
            self._commands.submit(self._restore_parent, result, revision)

    def _restore_parent(self, result, revision):
        if result.parent is not None:
            command = SetDestination(
                parent_or_null=result.parent,
                vault_name=self.session.snapshot.vault_name,
            )
            self._deliver(self.session.dispatch_if_current(command, revision))
        if result.feedback:
            self._feedback(result.feedback, revision)

    def _save_parent(self, parent, revision):
        try:
            result = self.preferences.save(parent)
            text = result.feedback
        except Exception:  # noqa: BLE001 -- safe outer I/O failure feedback.
            text = "The output folder could not be remembered for the next launch."
        if text:
            self._queue_feedback(text, revision)

    def _queue_feedback(self, text, revision):
        if not self._stopped.is_set():
            self._commands.submit(self._feedback, text, revision)

    def _feedback(self, text, revision):
        if self.session.snapshot.revision == revision:
            self.on_feedback(PreferenceFeedback(text=text, input_revision=revision))

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

    def request_published_check(self, expected_generation):
        self._commands.submit(self._check_published, expected_generation)

    def _check_published(self, generation):
        self._deliver(self.session.check_published_vault(generation))

    def request_completion_action(self, action, expected_generation, perform):
        """Queue intent only; platform work receives re-admission after its stat."""
        self._completion.submit(
            self._complete_action, action, expected_generation, perform
        )

    def _complete_action(self, action, generation, perform):
        target = self.session.admit_completion_action(action, generation)
        if target is None or self._stopped.is_set():
            self.on_completion_feedback(
                CompletionFeedback(
                    generation,
                    "The published result changed. Use the current result and try again.",
                )
            )
            return

        def readmit():
            return (
                not self._stopped.is_set()
                and self.session.admit_completion_action(action, generation) == target
            )

        try:
            outcome = perform(target, readmit)
            feedback = CompletionFeedback(
                generation, outcome.message, outcome.succeeded, target.path
            )
        except Exception:  # noqa: BLE001 -- local platform failures retain the operation result.
            feedback = CompletionFeedback(
                generation,
                "The open action could not complete. Your operation result is retained.",
                path=target.path,
            )
        self.on_completion_feedback(feedback)

    def _prepare_page(self, offset, generation):
        page = self.session.diagnostics_page_if_current(generation, offset)
        if page is not None:
            self.on_page(DiagnosticPresentation(generation, page))

    def request_diagnostic_export(
        self, action, expected_generation, perform, *, failure_path=None
    ):
        """Queue intent only; no old result/report is retained before admission."""
        self._exports.submit(
            self._export, action, expected_generation, perform, failure_path
        )

    def _export(self, action, generation, perform, failure_path):
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
                generation,
                outcome.message,
                outcome.succeeded,
                (failure_path or getattr(outcome, "path", None))
                if not outcome.succeeded
                else None,
            )
        except Exception:  # noqa: BLE001 -- outer platform action failures are nonfatal.
            feedback = DiagnosticFeedback(
                generation,
                "The diagnostic action could not complete. Your operation result is retained.",
                path=failure_path,
            )
        self.on_diagnostic_feedback(feedback)

    def shutdown(self):
        # A normal close is admitted only after the primary terminal result.
        # No GUI-thread join, timeout policy or child termination is introduced.
        self._stopped.set()
        self._operations.shutdown(wait=False)
        self._validation.shutdown(wait=False)
        self._preferences.shutdown(wait=False)
        self._exports.shutdown(wait=False, cancel_futures=True)
        self._completion.shutdown(wait=False, cancel_futures=True)
        self._commands.shutdown(wait=False)
