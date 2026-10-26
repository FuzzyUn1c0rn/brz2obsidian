"""Persistent review navigation over bounded, backend-owned presentation facts."""

from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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

    def __init__(self, submit, *, select, pick_source, pick_vault, path_widget):
        super().__init__()
        self._submit = submit
        self._select = select
        self._pick_source, self._pick_vault = pick_source, pick_vault
        self.source, self.vault = None, None
        self._input_revision = 0
        self._preparing = False
        self._state = None
        self._binding_key = None
        self._page = None
        self._offers = ()
        self._requested = set()
        self._last_reply = None
        self._rendered = None
        self._choice_buttons = []
        self._pending_choice = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(26, 18, 26, 20)
        layout.setSpacing(16)
        self.queue = QListWidget(objectName="reviewQueue")
        self.queue.setAccessibleName("Review queue")
        self.queue.addItems(("Archive & vault", "Overview", "Conflicts"))
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
            self._requested.clear()
            self._last_reply = None
        self._state = state
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
        reply = state.reply
        if reply is not None and reply is not self._last_reply:
            self._last_reply = reply
            if reply.binding == binding and binding is not None:
                if reply.page is not None:
                    self._page = reply.page
                if reply.offers or reply.total_choices:
                    self._offers = reply.offers
        if binding is not None and previous_binding is None:
            self.queue.setCurrentRow(1)
        self._render()
        self._refresh_choices()
        if binding is None or state.active_request_id or state.needs_inspection:
            return
        for command in ("page", "choices"):
            if command not in self._requested:
                self._requested.add(command)
                self._submit(
                    {"command": command, "binding": binding, "offset": 0, "limit": 100}
                )
                break

    @property
    def snapshot(self):
        return self._state

    def _refresh_choices(self):
        available = self._state is not None and not (
            self._state.active_request_id
            or self._state.needs_inspection
            or self._state.draft_pending
            or self._pending_choice is not None
        )
        for button in self._choice_buttons:
            button.setEnabled(available)

    def _choose(self, binding, offer, choice):
        state = self._state
        if (
            state is None
            or state.binding != binding
            or state.active_request_id
            or state.needs_inspection
            or state.draft_pending
            or self._pending_choice is not None
            or offer not in self._offers
            or choice not in offer.choices
        ):
            return
        self._pending_choice = state.revision
        self._refresh_choices()
        self._submit(
            {
                "command": "choose",
                "binding": binding,
                "requirement_id": offer.requirement_id,
                "choice": choice,
                "assumptions_digest": offer.assumptions_digest,
            }
        )

    def _render(self, *_):
        key = (self.queue.currentRow(), self._binding_key, self._page, self._offers)
        if key == self._rendered:
            return
        self._rendered = key
        self._choice_buttons = []
        while self._body.count():
            item = self._body.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                if item.widget() is not self._inputs:
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
        else:
            self._body.addWidget(_label("Conflicts", "sectionTitle"))
            rows = () if self._page is None else self._page.items
            offers = {row.change_id: row for row in self._offers}
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
                if offer is not None and offer.domain == "text":
                    for choice, title in (
                        ("current", "Keep vault version"),
                        ("incoming", "Use incoming version"),
                    ):
                        if choice not in offer.choices:
                            continue
                        button = QPushButton(title)
                        button.setAccessibleName(title + " for " + row.current_path)
                        binding = self._state.binding
                        button.clicked.connect(
                            lambda checked=False, b=binding, o=offer, c=choice: (
                                self._choose(b, o, c)
                            )
                        )
                        self._choice_buttons.append(button)
                        self._body.addWidget(button)
        self._body.addStretch()
        self._refresh_choices()

    def _make_inputs(self, path_widget):
        panel = QWidget(self.workspace)
        form = QVBoxLayout(panel)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)
        form.addWidget(_label("Archive & vault", "sectionTitle"))
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
        self._refresh_inputs()
        return panel

    def _refresh_inputs(self):
        busy = self._preparing or bool(self._state and self._state.active_request_id)
        self.source_path.setPlainText(self.source or "No incoming archive selected")
        self.vault_path.setPlainText(self.vault or "No vault selected")
        self.source_choice.setEnabled(not busy)
        self.vault_choice.setEnabled(not busy)
        self.prepare.setEnabled(
            bool(self.source and self.vault)
            and not busy
            and not (
                self._state and (self._state.binding or self._state.needs_inspection)
            )
        )

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
            else:
                self.vault = str(path)
            self._refresh_inputs()

        (self._pick_source if field == "source" else self._pick_vault)(selected)

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
                "kind": "source_update",
                "vault": self.vault,
                "source": self.source,
                "selection_id": selection,
            }
        )
