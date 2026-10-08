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


class HostRunner:
    """Callbacks deliver immutable prepared facts; GUI adapters marshal them.

    Session reduction, process launch/wait, parsing and report preparation all
    run on outer threads. The serialized command executor remains available
    while an independent primary-operation executor waits for its child.
    """

    def __init__(self, supervisor, on_update, on_page, session=None):
        self.session = session if session is not None else ApplicationSession()
        self.supervisor, self.on_update, self.on_page = supervisor, on_update, on_page
        self._commands = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="application-session"
        )
        self._operations = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="operation-supervisor"
        )

    def submit(self, command):
        self._commands.submit(self._dispatch, command)

    def _dispatch(self, command):
        update = self.session.dispatch(command)
        self.on_update(PresentationUpdate(update, self.session.diagnostics_page()))
        for effect in update.effects:
            if effect.effect == "run_operation":
                self._operations.submit(self._run, effect)

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

    def request_diagnostic_page(self, offset=0):
        self._commands.submit(
            lambda: self.on_page(self.session.diagnostics_page(offset))
        )

    def shutdown(self):
        # A normal close is admitted only after the primary terminal result.
        # No GUI-thread join, timeout policy or child termination is introduced.
        self._operations.shutdown(wait=False)
        self._commands.shutdown(wait=False)
