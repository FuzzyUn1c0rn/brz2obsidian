"""Keep local editor bytes until an explicit worker commit or discard."""

from hashlib import sha256

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from brz2obsidian.application.update_history_contracts import HistoryContextBinding


def _same_review(left, right):
    return (
        left is not None
        and right is not None
        and left.model_dump(exclude={"revision"})
        == right.model_dump(exclude={"revision"})
    )


class EditedResult(QWidget):
    changed = Signal()

    def __init__(self, submit, state, can_submit):
        super().__init__()
        self._submit, self._state, self._can_submit = submit, state, can_submit
        self.active = False
        self._owner = self._offer = self._handle = None
        self._phase = None
        self._data = b""
        self._sent_revision = 0
        self._sent_reply = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel()
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.text = QPlainTextEdit()
        self.text.setMinimumHeight(180)
        self.use = QPushButton("Use edited result")
        self.use.setAccessibleName("Use edited result")
        self.use.clicked.connect(self._begin)
        self.discard = QPushButton("Discard edited result")
        self.discard.setAccessibleName("Discard edited result")
        self.discard.clicked.connect(self._discard)
        for widget in (self.title, self.notice, self.text, self.use, self.discard):
            layout.addWidget(widget)

    def open(self, binding, offer, path, initial):
        if self.active or not self._can_submit() or binding != self._state().binding:
            return
        self.active = True
        self._owner, self._offer = binding, offer
        self._handle = self._phase = None
        self.title.setText("Edited result: " + path)
        self.text.setAccessibleName("Edited result for " + path)
        if initial is None:
            self.text.setPlainText("")
            self.notice.setText(
                "The comparison is a preview. Enter the complete edited result as UTF-8 text."
            )
        else:
            try:
                self.text.setPlainText(initial.decode("utf-8"))
            except UnicodeDecodeError:
                self.text.setPlainText("")
            self.notice.setText("Enter the complete edited result as UTF-8 text.")
        self._refresh()
        self.changed.emit()
        self.text.setFocus()

    def _refresh(self):
        state = self._state()
        free = state is not None and self._phase is None and self._can_submit()
        self.text.setReadOnly(self._phase is not None)
        self.use.setEnabled(
            free
            and _same_review(self._owner, state.binding)
            and not state.draft_pending
        )
        self.discard.setEnabled(free)

    def _send(self, command, **arguments):
        state = self._state()
        self._phase = command
        self._sent_revision, self._sent_reply = state.revision, state.reply
        self._refresh()
        self.changed.emit()
        self._submit({"command": command, **arguments})

    def _begin(self):
        if not self.use.isEnabled():
            return
        state = self._state()
        self._data = self.text.toPlainText().encode("utf-8")
        self._send(
            "begin_edit",
            binding=state.binding,
            requirement_id=self._offer.requirement_id,
            size=len(self._data),
            sha256=sha256(self._data).hexdigest(),
        )

    def _write(self, received):
        if received < len(self._data):
            data = self._data[received : received + 32768]
            self._expected_received = received + len(data)
            self._send("write_edit", handle=self._handle, offset=received, data=data)
        else:
            self._send("seal_edit", handle=self._handle)

    def present(self, state):
        self._refresh()
        if (
            not self.active
            or self._phase is None
            or state.active_request_id
            or state.revision <= self._sent_revision
            or state.reply is self._sent_reply
        ):
            return
        reply, phase = state.reply, self._phase
        if reply is None:
            self._failed()
            return
        if (
            phase == "begin_edit"
            and reply.code == "edit_started"
            and reply.edit is not None
        ):
            handle = reply.edit.handle
            if (
                handle.binding != state.binding
                or not _same_review(self._owner, handle.binding)
                or handle.requirement_id != self._offer.requirement_id
                or handle.assumptions_digest != self._offer.assumptions_digest
                or handle.size != len(self._data)
                or handle.sha256 != sha256(self._data).hexdigest()
            ):
                self._failed()
                return
            self._handle = handle
            self._write(reply.edit.received_bytes)
        elif (
            phase == "write_edit"
            and reply.code == "edit_chunk_accepted"
            and reply.edit is not None
            and reply.edit.handle == self._handle
            and reply.edit.received_bytes == self._expected_received
        ):
            self._write(reply.edit.received_bytes)
        elif (
            phase == "seal_edit"
            and reply.code == "edit_sealed"
            and reply.edit is not None
            and reply.edit.handle == self._handle
            and reply.edit.sealed
        ):
            self._send(
                "choose_history"
                if isinstance(self._handle.binding, HistoryContextBinding)
                else "choose",
                binding=self._handle.binding,
                requirement_id=self._handle.requirement_id,
                choice="edited",
                assumptions_digest=self._handle.assumptions_digest,
                edit_handle=self._handle,
            )
        elif (
            phase in ("choose", "choose_history")
            and reply.code
            in ("accepted", "recovery_choice_recorded", "undo_choice_recorded")
        ) or (phase == "discard_draft" and reply.code == "draft_discarded"):
            self._clear()
        else:
            self._failed()

    def _failed(self):
        self._phase = None
        self.notice.setText(
            "The edited result was not accepted. Your text is retained; review the current status or discard this draft."
        )
        self._refresh()
        self.changed.emit()

    def _discard(self):
        if not self.discard.isEnabled():
            return
        state = self._state()
        if state.draft_pending and _same_review(self._owner, state.binding):
            self._send("discard_draft", binding=state.binding)
        else:
            self._clear()

    def _clear(self):
        self.active = False
        self._phase = self._handle = self._offer = self._owner = None
        self._data = b""
        self.text.clear()
        self.hide()
        self.changed.emit()
