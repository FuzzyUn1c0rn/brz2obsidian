"""Persistent review navigation over bounded, backend-owned presentation facts."""

from uuid import uuid4

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

    def __init__(self, submit, *, select, pick_source, pick_vault, path_widget):
        super().__init__()
        self._submit = submit
        self._select = select
        self._pick_source, self._pick_vault = pick_source, pick_vault
        self.source, self.vault, self.original_source = None, None, None
        self._input_revision = 0
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
        self.queue.addItems(("Archive & vault", "Overview", "Conflicts", "Other choices"))
        self.queue.setFixedWidth(160)
        self.queue.setWordWrap(True)
        self.queue.setCurrentRow(0)
        layout.addWidget(self.queue)
        scroll = QScrollArea()
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
            and state.transport_phase == "completed"
            and state.reply is not None
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
    def busy(self):
        return self._external_busy() or self._editor.active or self._reference_dirty

    def _external_busy(self):
        return (
            self._pending_read is not None
            or self._pending_choice is not None
            or bool(self._state and self._state.active_request_id)
        )

    def _refresh_choices(self):
        available = self._state is not None and not (
            self.busy or self._state.needs_inspection
        )
        for button in self._choice_buttons:
            owner = self._reference_owner
            pending_allowed = owner is not None and button.property("draftRequirement") == owner["requirement_id"]
            button.setEnabled(available and (not self._state.draft_pending or pending_allowed))
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
            if state.reply is not None and state.reply.code == "accepted" and self._reference_owner is not None and chosen["requirement_id"] == self._reference_owner["requirement_id"]:
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
        self._submit({"command": command, "binding": state.binding, **arguments})

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
                "command": "choose",
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
            if "save_update" in state.next_actions:
                self._action_button("Save review", "save", binding=state.binding)
            if "refresh_update" in state.next_actions or state.stale:
                self._action_button("Refresh review", "refresh", binding=state.binding, source=self.source)

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
               self._state.reply.code if self._state and self._state.reply else None)
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
        else:
            self._body.addWidget(_label("Conflicts", "sectionTitle"))
            rows = () if self._page is None else self._page.items
            offers = {row.change_id: row for row in (*self._offers, *self._row_offers)}
            positions = {row.change_id: self._page.offset + index for index, row in enumerate(rows)}
            rows = sorted(
                (row for row in rows if row.disposition == "unresolved"),
                key=lambda row: (
                    offers.get(row.change_id) is not None
                    and offers[row.change_id].selected is not None
                ),
            )
            if not rows:
                self._body.addWidget(
                    _label("No conflict comparisons in the current page.", "muted")
                )
            for row in rows:
                self._body.addWidget(_label(row.current_path, "sectionTitle"))
                offer = offers.get(row.change_id)
                if offer is not None and offer.selected is not None:
                    self._body.addWidget(_label("Chosen: " + offer.selected, "muted"))
                for title, raw in (
                    ("Original", row.original),
                    ("Current", row.current),
                    ("Incoming", row.incoming),
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
                if offer is not None and offer.domain == "text":
                    for choice, title in (
                        ("current", "Keep vault version"),
                        ("incoming", "Use incoming version"),
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
        if self._editor.active:
            self._body.addWidget(self._editor)
            self._editor.show()
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
            for choice in offer.choices:
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
            for unavailable in offer.unavailable_choices:
                self._body.addWidget(_label("Unavailable: " + labels[unavailable.choice] + " — " + ", ".join(r.replace("_", " ") for r in unavailable.reasons), "muted"))
                button = QPushButton(labels[unavailable.choice])
                button.setAccessibleName(labels[unavailable.choice] + " for " + title)
                button.setEnabled(False)
                self._body.addWidget(button)
            self._read_button("Review details", "choice_details", name="Review details for " + title,
                              requirement_id=offer.requirement_id, offset=0, limit=100)
            if offer.domain == "attachment":
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
        self.operation.currentIndexChanged.connect(self._refresh_inputs)
        self._refresh_inputs()
        return panel

    def _refresh_inputs(self):
        busy = self._preparing or self.busy
        self.source_path.setPlainText(self.source or "No incoming archive selected")
        self.vault_path.setPlainText(self.vault or "No vault selected")
        self.original_path.setPlainText(self.original_source or "Original output is unknown; current vault content is preserved for review.")
        kind = self.operation.currentData()
        self.source_path.setVisible(kind != "attachment_cleanup")
        self.source_choice.setVisible(kind != "attachment_cleanup")
        for widget in (self.original_heading, self.original_path, self.original_choice, self.original_clear):
            widget.setVisible(kind == "onboarding")
        self.operation.setEnabled(not busy and not (self._state and self._state.binding))
        self.original_choice.setEnabled(not busy)
        self.original_clear.setEnabled(not busy and self.original_source is not None)
        self.source_choice.setEnabled(not busy)
        self.vault_choice.setEnabled(not busy)
        self.prepare.setEnabled(
            bool(self.vault and (self.source or kind == "attachment_cleanup"))
            and not busy
            and not (
                self._state and (self._state.binding or self._state.needs_inspection)
            )
        )
        self.reopen.setEnabled(bool(self.vault) and not busy and not (self._state and self._state.binding))

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
        self._select(self.vault, selection_id=selection)
        self._submit({"command": "load", "vault": self.vault, "selection_id": selection})

    def _pick_input(self, field):
        revision = self._input_revision

        def selected(path):
            if (
                not path
                or revision != self._input_revision
                or self._preparing
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
