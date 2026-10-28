"""Persistent review navigation over bounded, backend-owned presentation facts."""

from uuid import uuid4
from time import monotonic

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from brz2obsidian.application.update_context_contracts import UpdateContextBinding
from brz2obsidian.application.update_history_contracts import HistoryContextBinding

from .edited_result import EditedResult


def _label(text, name=None):
    result = QLabel(text, objectName=name or "")
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setWordWrap(True)
    result.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
        | Qt.TextInteractionFlag.TextSelectableByKeyboard
    )
    result.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return result


class UpdateWorkbench(QWidget):
    """A view cache and navigation; the shared session owns review authority."""

    availability_changed = Signal()
    close_choice = Signal(str, int)

    def __init__(self, submit, *, select, pick_source, pick_vault, path_widget):
        super().__init__()
        self._submit = submit
        self._select = select
        self._pick_source, self._pick_vault = pick_source, pick_vault
        self.source, self.vault, self.original_source = None, None, None
        self._input_revision = 0
        self._source_selection_id = None
        self._saved_selection_id = None
        self._preparing = False
        self._state = None
        self._binding_key = None
        self._page = None
        self._offers = ()
        self._row_offers = ()
        self._offer_page = (0, 0, None)
        self._details = self._references = None
        self._read_request = None
        self._read_buttons = []
        self._cursors = {}
        self._reference_owner = None
        self._reference_pending = None
        self._reference_selections = {}
        self._reference_dirty = False
        self._reference_controls = {}
        self._draft_buttons = []
        self._chosen_owner = None
        self._draft_message = ""
        self._configuration = None
        self._identity_selection = {}
        self.history_copy = None
        self._history = self._history_action = None
        self._after_close = None
        self._internal_close = None
        self._transition = None
        self._details_expanded = False
        self._history_scope = None
        self._closing = False
        self._active_id = self._active_started = None
        self._requested = set()
        self._last_reply = None
        self._rendered = None
        self._choice_buttons = []
        self._pending_choice = None
        self._pending_read = None
        self._editor = EditedResult(
            self._submit, lambda: self._state,
            lambda: not self._external_busy() and not self._reference_dirty,
        )
        self._editor.changed.connect(self._draft_changed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(26, 18, 26, 20)
        layout.setSpacing(16)
        self.queue = QListWidget(objectName="reviewQueue")
        self.queue.setAccessibleName("Review queue")
        self.queue.addItems(("Archive & vault", "Overview", "Conflicts", "Other choices", "History & recovery", "Compatible changes", "All changes"))
        self.queue.setFixedWidth(160)
        self.queue.setWordWrap(True)
        self.queue.setCurrentRow(0)
        layout.addWidget(self.queue)
        scroll = self.scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.workspace = QWidget()
        self.workspace.setAccessibleName("Decision workspace")
        self._body = QVBoxLayout(self.workspace)
        self._body.setContentsMargins(4, 0, 4, 0)
        self._body.setSpacing(12)
        self._inputs = self._make_inputs(path_widget)
        scroll.setWidget(self.workspace)
        layout.addWidget(scroll, 1)
        self.queue.currentRowChanged.connect(self._render)
        self._render()

    def present(self, state):
        if self._state is not None and state.revision < self._state.revision:
            return
        previous_binding = self._state.binding if self._state is not None else None
        binding = state.binding
        key = (state.selection_id, binding.model_dump_json() if binding else None)
        if key != self._binding_key:
            self._binding_key = key
            self._page, self._offers = None, ()
            self._row_offers = ()
            self._offer_page = (0, 0, None)
            self._details = self._references = None
            self._read_request = None
            self._cursors.clear()
            self._requested.clear()
            self._last_reply = None
            self._pending_read = None
            self._configuration = None
            self._identity_selection.clear()
        self._state = state
        scope = (state.selection_id, state.vault)
        if (scope != self._history_scope
                or state.reply is not None and state.reply.kind != "history"
                or state.reply is None and state.publication == "unknown"):
            self._history = self._history_action = None
        self._history_scope = scope
        if state.active_request_id != self._active_id:
            self._active_id = state.active_request_id
            self._active_started = monotonic() if self._active_id else None
        if state.reply is not None:
            if state.reply.history is not None:
                self._history = state.reply.history
            if state.reply.history_action is not None:
                self._history_action = state.reply.history_action
            pending = self._internal_close
            if pending is not None and not state.active_request_id and state.revision > pending[0] and state.reply is not pending[1]:
                self._internal_close = None
                action, self._after_close = self._after_close, None
                if state.reply.code == "context_closed" and action is not None:
                    self._transition = None
                    self._closing = False
                    action()
                elif self._transition is not None:
                    self._closing = True
        if (
            self._pending_read is not None
            and state.revision > self._pending_read
            and not state.active_request_id
            and state.transport_phase is not None
        ):
            self._pending_read = None
        if (
            self._pending_choice is not None
            and state.revision > self._pending_choice
            and not state.active_request_id
        ):
            self._pending_choice = None
        if (
            self._preparing
            and not state.active_request_id
            and state.transport_phase is not None
        ):
            self._preparing = False
        self._refresh_inputs()
        self._editor.present(state)
        self._complete_reference_action(state)
        reply = state.reply
        if reply is not None and reply is not self._last_reply:
            self._last_reply = reply
            if reply.binding == binding and binding is not None:
                if reply.page is not None:
                    self._page = reply.page
                    self._row_offers = reply.offers
                if reply.configuration is not None:
                    self._configuration = reply.configuration
                if reply.page is None and (reply.offers or reply.total_choices):
                    self._offers = reply.offers
                    offset = (self._read_request or {}).get("offset", 0)
                    self._offer_page = (offset, reply.total_choices, reply.next_choice_offset)
                request = self._read_request or {}
                requirement = request.get("requirement_id")
                if request.get("command") == "choice_details" and reply.status == "available":
                    self._details = (requirement, request.get("offset", 0), reply)
                if request.get("command") == "references" and reply.status == "available":
                    self._references = (requirement, request.get("offset", 0), reply)
                if request and reply.status == "available":
                    cursor_key = (request["command"], requirement)
                    cursor = (request.get("offset", 0), request.get("byte_offset", 0))
                    trail = self._cursors.setdefault(cursor_key, [])
                    if cursor in trail:
                        del trail[trail.index(cursor) + 1:]
                    else:
                        trail.append(cursor)
        if self._pending_read is None:
            self._read_request = None
        if binding is not None and previous_binding is None and self.queue.currentRow() == 0:
            self.queue.setCurrentRow(1)
        self._render()
        self._refresh_choices()
        if binding is None or self.busy or state.needs_inspection:
            return
        if isinstance(binding, HistoryContextBinding) and binding.proposal_id is None:
            return
        reads = [("page", {"offset": 0, "limit": 100}),
                 ("choices", {"offset": self._reference_owner["offer_offset"] if self._reference_owner else 0, "limit": 100})]
        if self._reference_owner is not None:
            reads.append(("references", {"requirement_id": self._reference_owner["requirement_id"],
                                         "offset": self._reference_owner["offset"], "limit": 100}))
        for command, arguments in reads:
            if command not in self._requested:
                self._requested.add(command)
                self._read(command, binding=binding, **arguments)
                break

    @property
    def snapshot(self):
        return self._state

    @property
    def has_review(self):
        state = self._state
        return self.local_draft or bool(state and (state.binding or state.active_request_id or state.draft_pending))

    @property
    def local_draft(self):
        return self._editor.active or self._reference_dirty

    @property
    def status_text(self):
        state = self._state
        if state is None:
            return "Choose a vault to review."
        if state.active_request_id:
            progress = state.progress
            phases = {"current_inspection": "Inspecting current vault", "reference_preparation": "Preparing reference output",
                      "review_validation": "Validating review", "snapshot_preparation": "Snapshot preparation",
                      "publication": "Publishing reviewed files", "final_verification": "Verifying published files", "final_reporting": "Recording final result"}
            text = phases.get(progress.value.phase, progress.value.phase) if progress else "Running " + state.active_command.replace("_", " ")
            elapsed = progress.elapsed_ms // 1000 if progress else int(monotonic() - self._active_started) if self._active_started is not None else 0
            text += f" · {elapsed // 60}:{elapsed % 60:02d} elapsed"
            if progress and progress.value.completed_units is not None:
                value = progress.value
                text += f" · {value.completed_units}" + (f" of {value.total_units}" if value.total_units is not None else "") + " " + value.unit.replace("_", " ")
            if state.control_code in ("cancellation_queued", "cancellation_requested"):
                text = "Cancellation requested. Waiting for the operation's safe stop. " + text
            return text
        if state.needs_inspection or state.publication in ("partial", "unknown"):
            return "Publication is unknown; inspect history before continuing." if state.publication == "unknown" else "Recovery is required; inspect current history before continuing."
        if state.transport_phase == "not_started":
            return "The review worker could not start. Check the Python environment and try again."
        reply = state.reply
        if reply is not None and reply.operation is not None:
            return reply.operation.message
        if reply is not None and reply.history_action is not None:
            return reply.history_action.summary
        if reply is not None and reply.status == "cancelled_before_publication":
            return "Stopped before file publication. Retained history and saved review remain available."
        if reply is not None and reply.code == "saved":
            return "Review saved. Reopening rechecks current source and vault inputs."
        return "Review the whole proposal before applying. Keep the target vault idle while an operation runs."

    def open_close_choices(self):
        self._transition = None
        self._closing = True
        self._rendered = None
        self._render()
        self.scroll.ensureWidgetVisible(self._close_panel)

    def finish_close_choice(self):
        self._closing = False
        self._rendered = None
        self._render()

    def discard_local(self):
        self._editor._clear()
        self._reference_selections.clear()
        self._reference_dirty = False

    @property
    def busy(self):
        return self._external_busy() or self._editor.active or self._reference_dirty

    def _external_busy(self):
        return (
            self._pending_read is not None
            or self._pending_choice is not None
            or bool(self._state and self._state.active_request_id)
        )

    def _refresh_choices(self):
        available = self._state is not None and not self.busy
        for button in self._choice_buttons:
            owner = self._reference_owner
            pending_allowed = owner is not None and button.property("draftRequirement") == owner["requirement_id"]
            inspected = self._state is not None and (not self._state.needs_inspection or button.property("inspectionAllowed"))
            button.setEnabled(bool(available and inspected and (not self._state.draft_pending or pending_allowed)))
        for button in self._read_buttons:
            button.setEnabled(self._state is not None and not self.busy and not self._state.needs_inspection)
        for button, allowed in self._draft_buttons:
            button.setEnabled(bool(allowed()))

    def _draft_changed(self):
        self._render()
        self._refresh_choices()
        self._refresh_inputs()
        self.availability_changed.emit()

    def _complete_reference_action(self, state):
        pending = self._reference_pending
        if pending and not state.active_request_id and state.revision > pending["revision"] and state.reply is not pending["reply"]:
            reply = state.reply
            if reply is not None and reply.code == "reference_choices_staged":
                self._reference_owner = {**pending["owner"], "binding": state.binding}
                for choice in pending["choices"]:
                    self._reference_selections.pop(choice["reference_id"], None)
                self._reference_dirty = bool(self._reference_selections)
                self._draft_message = "Reference choices staged. Review remaining occurrences before choosing a version."
            elif reply is not None and reply.code == "draft_discarded":
                self._reference_owner = None
                self._reference_selections.clear()
                self._reference_dirty = False
                self._draft_message = "Reference draft discarded."
            else:
                self._draft_message = "The reference choices were not accepted. Your selections are retained."
            self._reference_pending = None
        chosen = self._chosen_owner
        if chosen and not state.active_request_id and state.revision > chosen["revision"] and state.reply is not chosen["reply"]:
            if state.reply is not None and state.reply.code in ("accepted", "recovery_choice_recorded", "undo_choice_recorded") and self._reference_owner is not None and chosen["requirement_id"] == self._reference_owner["requirement_id"]:
                self._reference_owner = None
                self._reference_selections.clear()
                self._reference_dirty = False
                self._draft_message = ""
            self._chosen_owner = None

    def _stage_references(self, binding, offer, offset, reply):
        state = self._state
        if state is None or binding != state.binding or self._external_busy() or self._editor.active or state.needs_inspection:
            return
        choices = []
        for row in reply.references:
            choice = self._reference_selections.get(row.reference_id, row.selected)
            if choice not in row.choices:
                return
            choices.append({"reference_id": row.reference_id, "choice": choice})
        if not choices:
            return
        self._reference_pending = {
            "revision": state.revision, "reply": state.reply, "choices": choices,
            "owner": {"requirement_id": offer.requirement_id, "offer_offset": self._offer_page[0], "offset": offset},
        }
        self._pending_choice = state.revision
        self._refresh_choices()
        self.availability_changed.emit()
        self._submit({"command": "stage_references", "binding": binding,
                      "requirement_id": offer.requirement_id, "choices": tuple(choices)})

    def _discard_references(self):
        state = self._state
        if state is None or self._external_busy() or self._editor.active:
            return
        if state.draft_pending and self._reference_owner is not None:
            self._reference_pending = {"revision": state.revision, "reply": state.reply, "choices": (), "owner": self._reference_owner}
            self._pending_choice = state.revision
            self._refresh_choices()
            self.availability_changed.emit()
            self._submit({"command": "discard_draft", "binding": state.binding})
        else:
            self._reference_selections.clear()
            self._reference_dirty = False
            self._rendered = None
            self._draft_changed()

    def _read(self, command, *, binding=None, **arguments):
        state = self._state
        if state is None or state.binding is None or self.busy or state.needs_inspection:
            return
        if binding is not None and binding != state.binding:
            return
        self._pending_read = state.revision
        self._read_request = {"command": command, **arguments}
        if command == "choices":
            self._details = self._references = None
        self._refresh_choices()
        self._refresh_inputs()
        self.availability_changed.emit()
        wire_command = "history_choices" if command == "choices" and isinstance(state.binding, HistoryContextBinding) else command
        self._submit({"command": wire_command, "binding": state.binding, **arguments})

    def _read_button(self, title, command, *, name=None, **arguments):
        button = QPushButton(title)
        button.setAccessibleName(name or title)
        binding = self._state.binding if self._state else None
        button.clicked.connect(lambda checked=False, b=binding, c=command, a=arguments: self._read(c, binding=b, **a))
        self._read_buttons.append(button)
        self._body.addWidget(button)

    def _previous_button(self, title, command, *, requirement_id=None):
        trail = self._cursors.get((command, requirement_id), ())
        if len(trail) > 1:
            offset, byte_offset = trail[-2]
            arguments = {"offset": offset, "limit": 100}
            if command == "page":
                arguments["byte_offset"] = byte_offset
            if requirement_id is not None:
                arguments["requirement_id"] = requirement_id
            self._read_button(title, command, **arguments)

    def _choose(self, binding, offer, choice):
        state = self._state
        if (
            state is None
            or state.binding != binding
            or self.busy
            or state.needs_inspection
            or state.draft_pending and (self._reference_owner is None or self._reference_owner["requirement_id"] != offer.requirement_id)
            or offer not in (*self._offers, *self._row_offers)
            or choice not in offer.choices
        ):
            return
        self._pending_choice = state.revision
        self._chosen_owner = {"revision": state.revision, "reply": state.reply, "requirement_id": offer.requirement_id}
        self._refresh_choices()
        self.availability_changed.emit()
        self._submit(
            {
                "command": "choose_history" if isinstance(binding, HistoryContextBinding) else "choose",
                "binding": binding,
                "requirement_id": offer.requirement_id,
                "choice": choice,
                "assumptions_digest": offer.assumptions_digest,
            }
        )

    def _action(self, command, **arguments):
        if self._state is None or self.busy or self._state.draft_pending:
            return
        self._pending_choice = self._state.revision
        self._refresh_choices()
        self._refresh_inputs()
        self.availability_changed.emit()
        self._submit({"command": command, **arguments})

    def _action_button(self, title, command, **arguments):
        button = QPushButton(title)
        button.setAccessibleName(title)
        button.setProperty("inspectionAllowed", command in ("prepare_history", "initialize_vault", "close", "refresh_history"))
        button.clicked.connect(lambda checked=False, c=command, a=arguments: self._action(c, **a))
        self._choice_buttons.append(button)
        self._body.addWidget(button)

    def _render_lifecycle(self):
        state = self._state
        if state is None:
            return
        if state.reply is not None and state.reply.code == "revalidation_required" and state.binding is None:
            self._body.addWidget(_label("Saved decisions are loaded. Recheck the source and vault before continuing.", "muted"))
            self._action_button("Resume saved review", "resume", vault=state.vault, selection_id=state.selection_id)
        if isinstance(state.binding, UpdateContextBinding):
            self._body.addWidget(_label("Reviewed vault: " + state.binding.vault, "muted"))
            incoming = self.source if state.selection_id == self._source_selection_id else None
            origin = "saved review" if state.selection_id == self._saved_selection_id else "current review"
            self._body.addWidget(_label("Incoming source: " + incoming if incoming else "Incoming source: retained from the " + origin + "; no new archive selected.", "muted"))
            if "save_update" in state.next_actions:
                self._action_button("Save review", "save", binding=state.binding)
            if "refresh_update" in state.next_actions or state.stale:
                self._action_button("Refresh review", "refresh", binding=state.binding, source=incoming)
        if self.queue.currentRow() != 0 and (state.needs_inspection or "inspect_history" in state.next_actions or "inspect_update_status" in state.next_actions):
            self._action_button_callback("Inspect history and recovery", self._inspect_history)

    def _action_button_callback(self, title, callback):
        button = QPushButton(title)
        button.setAccessibleName(title)
        button.setProperty("inspectionAllowed", True)
        button.clicked.connect(callback)
        self._choice_buttons.append(button)
        self._body.addWidget(button)

    def _start_history(self):
        self._history = self._history_action = None
        self._preparing = True
        selection = str(uuid4())
        self._select(self.vault or self._state.vault, selection_id=selection)
        self._submit({"command": "history", "vault": self.vault or self._state.vault, "selection_id": selection})
        self.queue.setCurrentRow(4)
        self._refresh_inputs()

    def _inspect_history(self):
        if self.busy or self._state and self._state.draft_pending:
            return
        if self._state and self._state.binding is not None:
            if isinstance(self._state.binding, UpdateContextBinding) or self._state.binding.proposal_id is not None:
                self._transition = ("inspect history", self._start_history)
                self._closing = True
                self._rendered = None
                self._render()
                self.scroll.ensureWidgetVisible(self._close_panel)
            else:
                self._close_internal(self._start_history, "discard")
        elif self.vault or self._state and self._state.vault:
            self._start_history()

    def _history_source(self, kind, command=None):
        def selected_role():
            self.operation.setCurrentIndex(self.operation.findData(kind))
            self.queue.setCurrentRow(0)
            self._refresh_inputs()
            if command:
                selection = str(uuid4())
                self._saved_selection_id = selection
                self._select(self.vault or self._state.vault, selection_id=selection)
                self._submit({"command": command, "vault": self.vault or self._state.vault, "selection_id": selection})
        if self._state.binding:
            self._close_internal(selected_role, "discard")
        else:
            selected_role()

    def _close_internal(self, callback, choice):
        self._after_close = callback
        self._internal_close = (self._state.revision, self._state.reply)
        self._action("close", binding=self._state.binding, choice=choice)

    def _transition_choice(self, choice, revision):
        if self._state.revision != revision or self._transition is None:
            self._rendered = None
            self._render()
            return
        if choice == "continue":
            self._transition = None
            self.finish_close_choice()
        elif choice in ("save", "discard") and not (choice == "save" and self.local_draft):
            self._close_internal(self._transition[1], choice)

    def _render_feedback(self):
        state = self._state
        if state is None or state.active_request_id:
            return
        reply = state.reply
        not_started = state.transport_phase == "not_started"
        uncertain = state.publication == "unknown" or state.transport_phase == "may_have_executed"
        failed = reply is not None and reply.status in ("refused", "failed", "stale_review", "recovery_required", "publication_unknown", "unknown", "incomplete", "content_complete")
        if not (not_started or uncertain or failed or reply and (reply.findings or reply.guidance or reply.recovery_gap_count)):
            return
        if not_started:
            self._body.addWidget(_label("Review could not start", "sectionTitle"))
            self._body.addWidget(_label("Check the application's Python environment and worker setup, then try again. This request was not dispatched.", "fieldError"))
        elif uncertain:
            self._body.addWidget(_label("Connection lost", "sectionTitle"))
            self._body.addWidget(_label("Publication is unknown. Inspect current history before continuing.", "fieldError"))
        elif failed:
            self._body.addWidget(_label("Review could not continue", "sectionTitle"))
            known = {"context_changed": "The review changed. Reopen or refresh the current review before choosing.",
                     "offer_changed": "This choice changed. Refresh the current review before choosing again.",
                     "uncommitted_draft": "Accept or explicitly discard your draft before continuing.",
                     "source_payload_changed": "The source changed. Refresh and review the affected choices before applying."}
            summary = known.get(reply.code, reply.summary or "Check the selected source and vault, then inspect current history before another attempt.")
            self._body.addWidget(_label(summary[:240] + (" See review details." if len(summary) > 240 else ""), "fieldError"))
        if not_started or uncertain or failed:
            self._body.addWidget(_label("File publication: " + state.publication.replace("_", " "), "muted"))
            retained = "unknown" if uncertain or state.history_retained is None else "retained" if state.history_retained else "not established"
            self._body.addWidget(_label("Saved converter history: " + retained, "muted"))
        toggle = QPushButton("Hide review details" if self._details_expanded else "Show review details")
        toggle.setAccessibleName(toggle.text())
        def expand():
            self._details_expanded = not self._details_expanded
            self._rendered = None
            self._render()
        toggle.clicked.connect(expand)
        self._body.addWidget(toggle)
        if self._details_expanded:
            if not_started:
                self._body.addWidget(_label("Worker launch detail: " + (state.transport_code or "not started"), "muted"))
            elif reply is not None:
                summary = _label(reply.summary)
                summary.setAccessibleName("Review diagnostic summary")
                self._body.addWidget(summary)
                self._body.addWidget(_label("Status: " + reply.status + "; detail: " + reply.code, "muted"))
                for finding in reply.findings:
                    self._body.addWidget(_label(finding, "muted"))
                if reply.recovery_gap_count:
                    self._body.addWidget(_label(f"Recovery gaps: {reply.recovery_gap_count}", "muted"))
                if reply.diagnostic_omission:
                    self._body.addWidget(_label("Some review diagnostics were omitted from this bounded view.", "muted"))
                if reply.guidance:
                    self._body.addWidget(_label(reply.guidance, "muted"))
            elif state.transport_code:
                self._body.addWidget(_label("Worker contact detail: " + state.transport_code, "muted"))

    def _pick_history_copy(self):
        binding = self._state.binding
        def selected(path):
            if path and self._state.binding == binding and not self.busy:
                self.history_copy = str(path)
                self._rendered = None
                self._render()
        self._pick_vault(selected, field="history_copy")

    def _render_history(self):
        state = self._state
        self._body.addWidget(_label("History & recovery", "sectionTitle"))
        self._body.addWidget(_label("All saved converter history is retained locally. Disk use grows as further versions are saved.", "muted"))
        if state is None:
            self._body.addWidget(_label("Select a vault, then inspect its current history and recovery state.", "muted"))
            return
        actions, binding = state.next_actions, state.binding
        if binding is None and self._history_action is not None:
            self._body.addWidget(_label(self._history_action.summary))
            if self._history_action.repair is not None:
                self._body.addWidget(_label(self._history_action.repair.message))
            return
        if self._history is not None:
            self._body.addWidget(_label(self._history.summary))
            self._body.addWidget(_label(self._history.operation.message, "muted"))
            for finding in self._history.findings:
                self._body.addWidget(_label(finding.replace("_", " "), "muted"))
            if self._history.recovery_gap_count:
                self._body.addWidget(_label(f"Recovery gaps: {self._history.recovery_gap_count}. Excluded content is outside retained recovery coverage.", "muted"))
            if self._history.diagnostic_omission:
                self._body.addWidget(_label("Some history diagnostics were omitted from this bounded view.", "muted"))
        if "setup_git" in actions:
            self._body.addWidget(_label("Install Git with the required local storage commands, make it available to the application, then restart the converter and inspect this vault again. No Git account or command-line experience is required."))
        if "initialize_vault" in actions and isinstance(binding, HistoryContextBinding):
            self._body.addWidget(_label("This vault has no local repository. Explicitly initialize converter history before preservation-first onboarding."))
            self._action_button("Initialize local history", "initialize_vault", binding=binding, choice="initialize")
            self._action_button("Decline initialization", "initialize_vault", binding=binding, choice="decline")
        if "review_onboarding" in actions:
            self._body.addWidget(_label("Earlier recovery and Undo are unavailable without validated matching history. Current notes do not prove pristine original output."))
            self._action_button_callback("Review preservation-first onboarding", lambda: self._history_source("onboarding"))
        if "review_update" in actions:
            self._action_button_callback("Choose incoming source update", lambda: self._history_source("source_update"))
        if "resume_update" in actions:
            self._action_button_callback("Resume saved review", lambda: self._history_source("source_update", "resume"))
        if not isinstance(binding, HistoryContextBinding):
            return
        if "review_recovery" in actions and (self._history_action is None or self._history_action.status != "direction_required"):
            self._action_button("Review interrupted update", "prepare_history", binding=binding, kind="recovery")
        if "review_undo" in actions:
            self._body.addWidget(_label("Undo reviews the latest eligible completed import or update. Keeping current content can retain later writing and imported changes while reversing eligible other changes."))
            self._action_button("Review latest Undo", "prepare_history", binding=binding, kind="undo")
        if "review_history_repair" in actions:
            self._body.addWidget(_label("Supply a complete local matching vault copy, including hidden history. Repair restores verified converter history, not authored files; notes-only sync or a normal clone may omit this history."))
            self._body.addWidget(_label(self.history_copy or "No complete history copy selected", "muted"))
            self._action_button_callback("Choose complete history copy", self._pick_history_copy)
            if self.history_copy:
                self._action_button("Review matching-history repair", "prepare_history", binding=binding, kind="repair", copy_path=self.history_copy)
        action = self._history_action
        if action is not None:
            self._body.addWidget(_label(action.summary))
            if action.status == "direction_required":
                for direction in action.available_directions:
                    self._action_button("Review " + direction + " direction", "prepare_history", binding=binding, kind="recovery", direction=direction)
            if action.copy_validation is not None:
                copy = action.copy_validation
                self._body.addWidget(_label(f"History copy: {copy.status}; missing objects: {copy.missing_objects}; damaged objects: {copy.damaged_objects}.", "muted"))
            if action.repair is not None:
                self._body.addWidget(_label(action.repair.message))
            if "execute_history" in actions and state.ready and action.ready:
                self._action_button("Execute reviewed " + action.kind, "execute_history", binding=binding)
            if "refresh_history" in actions:
                self._action_button("Refresh history review", "refresh_history", binding=binding)

    def _render_close(self):
        panel = self._close_panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(_label("Close review", "sectionTitle"))
        state = self._state
        options = state.close_options if state is not None else ("close",)
        if self.local_draft:
            layout.addWidget(_label("Your draft is uncommitted. Continue to accept or discard it; saving the review would not save this draft."))
        names = {"continue": "Continue operation" if state and state.active_request_id else "Continue review",
                 "background": "Keep running in background", "wait": "Wait for operation", "safe_stop": "Request safe stop",
                 "save": "Save review and close", "discard": "Discard review and close", "close": "Close window"}
        if self._transition is not None:
            names.update(save="Save review and " + self._transition[0], discard="Discard review and " + self._transition[0])
        if self.local_draft and not (state and state.active_request_id):
            options = ("continue", "discard")
        for option in options:
            if option == "save" and self.local_draft:
                continue
            button = QPushButton(names[option])
            button.setAccessibleName(names[option])
            if self._transition is not None:
                button.clicked.connect(lambda checked=False, choice=option, revision=state.revision: self._transition_choice(choice, revision))
            else:
                button.clicked.connect(lambda checked=False, choice=option, revision=state.revision if state else 0: self.close_choice.emit(choice, revision))
            layout.addWidget(button)
        self._body.addWidget(panel)

    def _render_configuration(self):
        offer = self._configuration
        if offer is None:
            return
        self._body.addWidget(_label("Vault configuration", "sectionTitle"))
        self._body.addWidget(_label(f"Review {offer.member_count} configuration files separately; these settings affect the whole vault."))
        if offer.selected:
            self._body.addWidget(_label("Configuration chosen: " + offer.selected, "muted"))
        for choice, title in (("current", "Keep current configuration"), ("incoming", "Use reviewed incoming configuration")):
            if choice in offer.choices:
                self._action_button(title, "choose_configuration", binding=self._state.binding, group_id=offer.group_id, choice=choice)

    def _render_identity(self, offer, title, rows):
        state = self._identity_selection.setdefault(offer.requirement_id, {"selected": None, "disassociate": set()})
        combo = QComboBox()
        combo.setAccessibleName("Selected identity for " + title)
        combo.addItem("Choose an identity candidate", None)
        for row in rows:
            if row.eligible and row.target_safe and row.existence == "present":
                combo.addItem(row.path, row.entry_id)
        combo.setCurrentIndex(max(0, combo.findData(state["selected"])))
        boxes = {}
        def selection_changed(index):
            state["selected"] = combo.itemData(index)
            if state["selected"] in boxes:
                boxes[state["selected"]].setChecked(False)
            self._refresh_choices()
        combo.currentIndexChanged.connect(selection_changed)
        self._body.addWidget(combo)
        self._body.addWidget(_label("Choose any other identities to disassociate explicitly. The vault still needs the reviewed identity repair before update.", "muted"))
        for row in rows:
            checkbox = QCheckBox("Disassociate identity from " + row.path)
            checkbox.setAccessibleName("Disassociate identity from " + row.path)
            checkbox.setChecked(row.entry_id in state["disassociate"])
            def checked(value, token=row.entry_id):
                if value:
                    state["disassociate"].add(token)
                else:
                    state["disassociate"].discard(token)
                self._refresh_choices()
            checkbox.toggled.connect(checked)
            boxes[row.entry_id] = checkbox
            self._body.addWidget(checkbox)
        button = QPushButton("Associate selected identity")
        button.setAccessibleName("Associate selected identity for " + title)
        binding = self._state.binding
        def associate():
            if self._state.binding != binding or self.busy or self._state.draft_pending or state["selected"] is None:
                return
            self._action("choose", binding=binding, requirement_id=offer.requirement_id, choice="associate",
                         assumptions_digest=offer.assumptions_digest, selected_entry_id=state["selected"],
                         disassociate_entry_ids=tuple(sorted(state["disassociate"])))
        button.clicked.connect(associate)
        self._body.addWidget(button)
        self._draft_buttons.append((button, lambda: not self.busy and not self._state.draft_pending
                                    and state["selected"] is not None and state["selected"] not in state["disassociate"]))

    def _render(self, *_):
        key = (self.queue.currentRow(), self._binding_key, self._page, self._offers,
               self._offer_page, self._details, self._references, self._editor.active, self._reference_owner, self._draft_message,
               self._configuration, self._state.next_actions if self._state else None,
               self._state.reply.code if self._state and self._state.reply else None,
               self._history, self._history_action, self.history_copy, self._closing,
               self._state.close_options if self._state else None,
               self._state.revision if self._closing and self._state else None,
               self._transition[0] if self._transition else None, self._details_expanded,
               self._state.reply if self._state else None, self._state.transport_phase if self._state else None)
        if key == self._rendered:
            return
        self._rendered = key
        self._choice_buttons = []
        self._read_buttons = []
        self._draft_buttons = []
        while self._body.count():
            item = self._body.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                if item.widget() not in (self._inputs, self._editor):
                    item.widget().deleteLater()
        if self.queue.currentRow() == 0:
            self._body.addWidget(self._inputs)
            self._inputs.show()
        elif self.queue.currentRow() == 1:
            self._body.addWidget(_label("Review the whole update", "sectionTitle"))
            if self._state is None or self._state.binding is None:
                self._body.addWidget(
                    _label(
                        "Choose an incoming BRZ archive and an existing vault.", "muted"
                    )
                )
            else:
                self._body.addWidget(
                    _label(
                        f"Changes: {self._state.changes}    Unresolved choices: {self._state.unresolved}"
                    )
                )
                self._body.addWidget(
                    _label(
                        "Your decisions are retained as you move through the review.",
                        "muted",
                    )
                )
        elif self.queue.currentRow() == 3:
            self._render_offers()
        elif self.queue.currentRow() == 4:
            self._render_history()
        else:
            compatible = self.queue.currentRow() == 5
            catalogue = self.queue.currentRow() == 6
            self._body.addWidget(_label("All changes" if catalogue else "Compatible changes" if compatible else "Conflicts", "sectionTitle"))
            rows = () if self._page is None else self._page.items
            offers = {row.change_id: row for row in (*self._offers, *self._row_offers)}
            positions = {row.change_id: self._page.offset + index for index, row in enumerate(rows)}
            rows = sorted(
                (row for row in rows if catalogue or row.disposition == ("compatible" if compatible else "unresolved")),
                key=lambda row: (
                    offers.get(row.change_id) is not None
                    and offers[row.change_id].selected is not None
                ),
            )
            if not rows:
                self._body.addWidget(
                    _label("No matching comparisons in the current page.", "muted")
                )
            for row in rows:
                self._body.addWidget(_label(row.current_path, "sectionTitle"))
                self._body.addWidget(_label(row.disposition.replace("_", " ").capitalize(), "muted"))
                if row.incoming_path != row.current_path:
                    self._body.addWidget(_label("Incoming path: " + row.incoming_path, "muted"))
                offer = offers.get(row.change_id)
                if offer is not None and offer.selected is not None:
                    self._body.addWidget(_label("Chosen: " + offer.selected, "muted"))
                for title, raw in (
                    ("Original", row.original),
                    ("Current", row.current),
                    ("Incoming", row.incoming),
                    ("Result", row.result),
                ):
                    self._body.addWidget(_label(title, "sectionTitle"))
                    if raw is None:
                        self._body.addWidget(_label("Not available", "muted"))
                        continue
                    try:
                        text = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        self._body.addWidget(
                            _label(
                                f"{len(raw)} bytes; content cannot be displayed as text.",
                                "muted",
                            )
                        )
                        continue
                    view = QPlainTextEdit()
                    view.setAccessibleName(title + " version")
                    view.setReadOnly(True)
                    view.setPlainText(text)
                    view.setMinimumHeight(90)
                    self._body.addWidget(view)
                if row.omitted:
                    self._body.addWidget(
                        _label(
                            "This comparison is paged; more bytes are available.",
                            "muted",
                        )
                    )
                if row.next_byte_offset is not None:
                    self._read_button(
                        "More comparison bytes", "page",
                        name="More comparison bytes for " + row.current_path,
                        offset=positions[row.change_id], limit=1, byte_offset=row.next_byte_offset,
                    )
                if offer is not None and offer.domain in ("text", "reversal"):
                    for choice, title in (
                        ("current", "Keep vault version"),
                        ("incoming", "Use incoming version"),
                        ("reverse", "Reverse reviewed change"),
                    ):
                        if choice not in offer.choices:
                            continue
                        button = QPushButton(title)
                        button.setAccessibleName(title + " for " + row.current_path)
                        button.setProperty("draftRequirement", offer.requirement_id)
                        binding = self._state.binding
                        button.clicked.connect(
                            lambda checked=False, b=binding, o=offer, c=choice: (
                                self._choose(b, o, c)
                            )
                        )
                        self._choice_buttons.append(button)
                        self._body.addWidget(button)
                    if "edited" in offer.choices:
                        button = QPushButton("Edit result")
                        button.setAccessibleName("Edit result for " + row.current_path)
                        initial = row.current if not row.omitted and row.offset == 0 else None
                        binding = self._state.binding
                        button.clicked.connect(lambda checked=False, b=binding, o=offer, p=row.current_path, raw=initial: self._editor.open(b, o, p, raw))
                        self._choice_buttons.append(button)
                        self._body.addWidget(button)
            if self._page is not None:
                self._previous_button("Previous comparison page", "page")
                if self._page.next_offset is not None:
                    self._read_button("Next comparison items", "page", offset=self._page.next_offset, limit=100, byte_offset=0)
        if self._draft_message:
            self._body.addWidget(_label(self._draft_message, "muted"))
        if self.queue.currentRow() == 1:
            self._render_configuration()
        self._render_lifecycle()
        self._render_feedback()
        if self._editor.active:
            self._body.addWidget(self._editor)
            self._editor.show()
        if self._closing:
            self._render_close()
        self._body.addStretch()
        self._refresh_choices()

    def _render_offers(self):
        self._body.addWidget(_label("Review choices", "sectionTitle"))
        offset, total, following = self._offer_page
        self._body.addWidget(_label(f"Showing {len(self._offers)} of {total} choices; page starts at {offset + 1}.", "muted"))
        names = {"compatible_group": "compatible group", "storage": "storage policy", "tracking": "tracking policy",
                 "attachment": "attachment", "text": "text", "identity": "identity", "rename": "rename",
                 "restoration": "restoration", "configuration": "configuration", "mapping": "mapping",
                 "format": "format", "reversal": "reversal"}
        labels = {"approve": "Approve", "current": "Keep vault version", "incoming": "Use incoming version",
                  "both": "Keep both versions", "accept": "Accept", "decline": "Decline",
                  "reverse": "Reverse reviewed change", "remove": "Remove", "keep_path": "Keep current path",
                  "source_path": "Use incoming path", "restore_incoming": "Restore incoming version",
                  "decline_restoration": "Keep deletion", "associate": "Associate selected identity", "edited": "Use edited result"}
        for index, offer in enumerate(self._offers, offset + 1):
            domain = names[offer.domain]
            title = f"{domain} choice {index}"
            self._body.addWidget(_label(title.capitalize(), "sectionTitle"))
            if offer.disclosure:
                self._body.addWidget(_label(offer.disclosure))
            if offer.detail_omitted:
                self._body.addWidget(_label("Some disclosure was omitted; review the bounded details.", "muted"))
            if offer.selected is not None:
                self._body.addWidget(_label("Chosen: " + offer.selected, "muted"))
            scoped_configuration = offer.domain == "configuration" and self._configuration is not None
            if scoped_configuration:
                button = QPushButton("Review vault configuration")
                button.setAccessibleName("Review vault configuration")
                button.clicked.connect(lambda checked=False: self.queue.setCurrentRow(1))
                self._body.addWidget(button)
            for choice in (() if scoped_configuration else offer.choices):
                if choice in ("edited", "associate"):
                    continue
                text = labels[choice]
                action_name = text + " " + domain if choice in ("approve", "accept", "decline") else text + " for " + title
                button = QPushButton(text)
                button.setAccessibleName(action_name)
                button.setProperty("draftRequirement", offer.requirement_id)
                binding = self._state.binding
                button.clicked.connect(lambda checked=False, b=binding, o=offer, c=choice: self._choose(b, o, c))
                self._choice_buttons.append(button)
                self._body.addWidget(button)
            for unavailable in (() if scoped_configuration else offer.unavailable_choices):
                self._body.addWidget(_label("Unavailable: " + labels[unavailable.choice] + " — " + ", ".join(r.replace("_", " ") for r in unavailable.reasons), "muted"))
                button = QPushButton(labels[unavailable.choice])
                button.setAccessibleName(labels[unavailable.choice] + " for " + title)
                button.setEnabled(False)
                self._body.addWidget(button)
            self._read_button("Review details", "choice_details", name="Review details for " + title,
                              requirement_id=offer.requirement_id, offset=0, limit=100)
            if offer.reference_review or offer.domain == "attachment":
                self._read_button("Review references", "references", name="Review references for " + title,
                                  requirement_id=offer.requirement_id, offset=0, limit=100)
            if self._details is not None and self._details[0] == offer.requirement_id:
                _, _, reply = self._details
                if not reply.choice_details:
                    self._body.addWidget(_label("No additional details for this choice.", "muted"))
                for row in reply.choice_details:
                    if row.choice is not None:
                        wording = {"current": "Vault version", "incoming": "Incoming version", "both": "Both versions"}
                        self._body.addWidget(_label("Output for: " + wording.get(row.choice, row.choice.replace("_", " ")), "sectionTitle"))
                    fields = [row.path, row.entry_id, row.target_id,
                              None if row.size is None else f"{row.size} bytes", row.sha256,
                              row.identity_state, row.existence]
                    self._body.addWidget(_label("\n".join(str(v) for v in fields if v is not None)))
                if offer.domain == "identity" and "associate" in offer.choices:
                    self._render_identity(offer, title, reply.choice_details)
                self._previous_button("Previous choice details", "choice_details", requirement_id=offer.requirement_id)
                if reply.next_choice_detail_offset is not None:
                    self._read_button("Next choice details", "choice_details", requirement_id=offer.requirement_id,
                                      offset=reply.next_choice_detail_offset, limit=100)
            if self._references is not None and self._references[0] == offer.requirement_id:
                _, reference_offset, reply = self._references
                if not reply.references:
                    self._body.addWidget(_label("No reference occurrences for this choice.", "muted"))
                for row in reply.references:
                    self._body.addWidget(_label(row.document_path, "sectionTitle"))
                    self._body.addWidget(_label("Reference text: " + (row.old.display_text or "No display text")))
                    self._body.addWidget(_label(row.snippet.decode("utf-8", errors="replace")))
                    combo = QComboBox()
                    combo.setAccessibleName("Reference target for " + (row.old.display_text or row.document_path))
                    combo.addItem("Choose a reference result", None)
                    wordings = {"drop": "Remove reference", "keep_current": "Keep current target", "use_incoming": "Use incoming target", "use_secondary": "Use secondary target"}
                    for choice in row.choices:
                        destination = next((d.meaning for d in row.destinations if d.choice == choice), None)
                        text = wordings[choice] + (": " + destination.path if destination is not None and destination.path is not None else "")
                        combo.addItem(text, choice)
                    chosen = self._reference_selections.get(row.reference_id, row.selected)
                    combo.setCurrentIndex(max(0, combo.findData(chosen)))
                    def changed(index, control=combo, token=row.reference_id, previous=row.selected):
                        value = control.itemData(index)
                        if value is None or value == previous:
                            self._reference_selections.pop(token, None)
                        else:
                            self._reference_selections[token] = value
                        self._reference_dirty = bool(self._reference_selections)
                        self._refresh_choices()
                        self.availability_changed.emit()
                    combo.currentIndexChanged.connect(changed)
                    self._body.addWidget(combo)
                if reply.references:
                    stage = QPushButton("Stage reference choices")
                    stage.setAccessibleName("Stage reference choices")
                    binding = self._state.binding
                    stage.clicked.connect(lambda checked=False, b=binding, o=offer, offset=reference_offset, r=reply: self._stage_references(b, o, offset, r))
                    self._body.addWidget(stage)
                    def may_stage(r=reply):
                        return (not self._external_busy() and not self._editor.active
                                and self._state.binding == r.binding and not self._state.needs_inspection
                                and all(self._reference_selections.get(row.reference_id, row.selected) in row.choices for row in r.references))
                    self._draft_buttons.append((stage, may_stage))
                    discard = QPushButton("Discard reference draft")
                    discard.setAccessibleName("Discard reference draft")
                    discard.clicked.connect(self._discard_references)
                    self._body.addWidget(discard)
                    self._draft_buttons.append((discard, lambda: not self._external_busy() and not self._editor.active))
                self._previous_button("Previous reference page", "references", requirement_id=offer.requirement_id)
                if reply.next_reference_offset is not None:
                    self._read_button("Next reference page", "references", requirement_id=offer.requirement_id,
                                      offset=reply.next_reference_offset, limit=100)
        self._previous_button("Previous review choices", "choices")
        if following is not None:
            self._read_button("Next review choices", "choices", offset=following, limit=100)

    def _make_inputs(self, path_widget):
        panel = QWidget(self.workspace)
        form = QVBoxLayout(panel)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)
        form.addWidget(_label("Archive & vault", "sectionTitle"))
        self.operation = QComboBox()
        self.operation.setAccessibleName("Review operation")
        for title, kind in (("Update from a source export", "source_update"), ("Onboard a vault without update history", "onboarding"),
                            ("Review an output-format transition", "format_transition"), ("Review attachment-file cleanup", "attachment_cleanup")):
            self.operation.addItem(title, kind)
        form.addWidget(self.operation)
        form.addWidget(
            _label(
                "Review an export from the same Brain, including an older or scoped export.",
                "muted",
            )
        )
        form.addWidget(_label("Incoming BRZ", "sectionTitle"))
        self.source_path = path_widget()
        self.source_path.setAccessibleName("Selected incoming BRZ")
        form.addWidget(self.source_path)
        self.source_choice = QPushButton("Choose incoming BRZ")
        self.source_choice.setAccessibleName("Choose incoming BRZ")
        self.source_choice.clicked.connect(lambda: self._pick_input("source"))
        form.addWidget(self.source_choice)
        self.original_heading = _label("Original generated BRZ evidence (optional)", "sectionTitle")
        self.original_path = path_widget()
        self.original_path.setAccessibleName("Selected original BRZ evidence")
        self.original_choice = QPushButton("Choose original BRZ evidence")
        self.original_choice.setAccessibleName("Choose original BRZ evidence")
        self.original_choice.clicked.connect(lambda: self._pick_input("original_source"))
        self.original_clear = QPushButton("Review without original evidence")
        self.original_clear.setAccessibleName("Review without original evidence")
        self.original_clear.clicked.connect(self._clear_original)
        for widget in (self.original_heading, self.original_path, self.original_choice, self.original_clear):
            form.addWidget(widget)
        form.addWidget(_label("Vault", "sectionTitle"))
        self.vault_path = path_widget()
        self.vault_path.setAccessibleName("Selected update vault")
        form.addWidget(self.vault_path)
        self.vault_choice = QPushButton("Choose update vault")
        self.vault_choice.setAccessibleName("Choose update vault")
        self.vault_choice.clicked.connect(lambda: self._pick_input("vault"))
        form.addWidget(self.vault_choice)
        self.prepare = QPushButton("Prepare update review", objectName="primary")
        self.prepare.setAccessibleName("Prepare update review")
        self.prepare.clicked.connect(self._prepare)
        form.addWidget(self.prepare)
        self.reopen = QPushButton("Reopen saved review")
        self.reopen.setAccessibleName("Reopen saved review")
        self.reopen.clicked.connect(self._reopen)
        form.addWidget(self.reopen)
        self.inspect_history = QPushButton("Inspect history and recovery")
        self.inspect_history.setAccessibleName("Inspect history and recovery")
        self.inspect_history.clicked.connect(self._inspect_history)
        form.addWidget(self.inspect_history)
        form.addWidget(_label("Keep the target vault idle while any conversion, recovery, Undo, repair or cleanup operation runs. Saved converter history is retained and grows with further versions.", "muted"))
        self.operation.currentIndexChanged.connect(self._refresh_inputs)
        self._refresh_inputs()
        return panel

    def _refresh_inputs(self):
        busy = self._preparing or self.busy
        bound = self._state.binding if self._state else None
        locked = bool(bound or self._state and self._state.needs_inspection)
        own_source = not bound or self._state.selection_id == self._source_selection_id
        if isinstance(bound, UpdateContextBinding) and self._state.reply is not None:
            self.operation.blockSignals(True)
            self.operation.setCurrentIndex(self.operation.findData(self._state.reply.kind))
            self.operation.blockSignals(False)
        self.source_path.setPlainText((self.source or "No incoming archive selected") if own_source else "Retained incoming source from the current review; no new archive selected.")
        self.vault_path.setPlainText(bound.vault if bound else self._state.vault if locked else self.vault or "No vault selected")
        self.original_path.setPlainText((self.original_source or "Original output is unknown; current vault content is preserved for review.") if own_source else "Original evidence belongs to the saved review; no new evidence selected.")
        kind = self.operation.currentData()
        self.source_path.setVisible(kind != "attachment_cleanup")
        self.source_choice.setVisible(kind != "attachment_cleanup")
        for widget in (self.original_heading, self.original_path, self.original_choice, self.original_clear):
            widget.setVisible(kind == "onboarding")
        self.operation.setEnabled(not busy and not locked)
        self.original_choice.setEnabled(not busy and not locked)
        self.original_clear.setEnabled(not busy and not locked and self.original_source is not None)
        self.source_choice.setEnabled(not busy and not locked)
        self.vault_choice.setEnabled(not busy and not locked)
        self.prepare.setEnabled(
            bool(self.vault and (self.source or kind == "attachment_cleanup"))
            and not busy
            and not (
                self._state and (self._state.binding or self._state.needs_inspection)
            )
        )
        self.reopen.setEnabled(bool(self.vault) and not busy and not locked)
        self.inspect_history.setEnabled(bool(self.vault or self._state and self._state.vault) and not busy)

    def _clear_original(self):
        if self.original_clear.isEnabled():
            self.original_source = None
            self._refresh_inputs()

    def _reopen(self):
        if not self.reopen.isEnabled():
            return
        self._preparing = True
        self._input_revision += 1
        self._refresh_inputs()
        selection = str(uuid4())
        self._saved_selection_id = selection
        self._select(self.vault, selection_id=selection)
        self._submit({"command": "load", "vault": self.vault, "selection_id": selection})

    def _pick_input(self, field):
        revision = self._input_revision

        def selected(path):
            if (
                not path
                or revision != self._input_revision
                or self._preparing
                or (self._state is not None and self._state.binding is not None)
                or (self._state is not None and self._state.needs_inspection)
                or (self._state is not None and self._state.active_request_id)
            ):
                return
            self._input_revision += 1
            if field == "source":
                self.source = str(path)
            elif field == "vault":
                self.vault = str(path)
            else:
                self.original_source = str(path)
            self._refresh_inputs()

        (self._pick_vault if field == "vault" else lambda callback: self._pick_source(callback, field=field))(selected)

    def _prepare(self):
        if not self.prepare.isEnabled():
            return
        self._preparing = True
        self._input_revision += 1
        self._refresh_inputs()
        selection = str(uuid4())
        self._source_selection_id = selection
        self._select(self.vault, selection_id=selection)
        self._submit(
            {
                "command": "prepare",
                "kind": self.operation.currentData(),
                "vault": self.vault,
                "source": None if self.operation.currentData() == "attachment_cleanup" else self.source,
                "original_source": self.original_source if self.operation.currentData() == "onboarding" else None,
                "selection_id": selection,
            }
        )
