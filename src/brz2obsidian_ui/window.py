"""C's compact task sheet, rendering only backend-owned safe facts."""

import os
import sys
from functools import partial
from pathlib import Path
from time import monotonic

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QBoxLayout,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from brz2obsidian.application.contracts import (
    ConvertCommand,
    InspectCommand,
    SelectSource,
    SelectVault,
    SessionSnapshot,
    SetDestination,
    SimpleCommand,
)
from brz2obsidian.application.runner import HostRunner
from brz2obsidian.application.transport import Supervisor
from brz2obsidian_ui.platform_actions import DiagnosticActions

EXPLANATIONS = (
    "Convert a BRZ archive into a new Obsidian vault.",
    "Inspect a BRZ archive without creating a vault.",
    "Check an existing vault without changing it.",
)
TITLES = {
    "inspection_clean": "Inspection completed — ready for review",
    "inspection_warnings": "Inspection completed — source warnings",
    "inspection_refused": "Archive cannot be used",
    "inspection_failed": "Inspection could not complete",
    "check_clean": "Check completed — no issues found",
    "check_issues": "Check completed — issues found",
    "check_failed": "Check could not complete",
    "conversion_created": "Vault created",
    "conversion_created_with_warnings": "Vault created with warnings",
    "conversion_refused": "Conversion could not proceed",
    "conversion_failed": "Conversion could not complete",
    "conversion_created_with_error": "Vault created; a follow-up error occurred",
}
CHECK_LABELS = {
    "destination_feasibility": "destination and generated-path feasibility",
    "source_freshness": "source freshness before conversion",
    "publication": "verified vault publication",
    "generated_vault_check": "checking the generated vault",
    "generated_paths": "complete generated-file paths",
    "generated_collisions": "generated-file collisions",
    "manifest_feasibility": "complete manifest feasibility",
    "absolute_path_limit": "final 240 UTF-16-unit absolute paths",
    "write_success": "write success during publication",
}
STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #26302e; background: #ffffff; }
QMainWindow { background: #e9ece9; }
QWidget#surround { background: #e9ece9; }
QFrame#sheet { background: #ffffff; border: 1px solid #cbd4cc; border-radius: 8px; }
QWidget#header, QWidget#footer { background: #f8faf7; }
QLabel#brand { color: #4c6659; font-weight: 600; }
QLabel#heading { font-size: 19pt; font-weight: 600; }
QLabel#sectionTitle { font-weight: 600; }
QLabel#muted, QLabel#sourcePath { color: #63716c; }
QLabel#sourcePath { font-family: Consolas; font-size: 9pt; }
QLabel#findings { background: #f1f6f0; border-left: 3px solid #709580; padding: 12px; }
QLabel#findings[severity='warning'] { background: #fff8e8; border-color: #bc923d; }
QLabel#findings[severity='error'] { background: #fcf1ed; border-color: #b36a5c; }
QPushButton { background: #ffffff; border: 1px solid #cbd3cb; border-radius: 5px; padding: 8px 12px; }
QPushButton:hover { background: #f0f4ef; border-color: #789283; }
QPushButton:focus { border: 2px solid #315b4c; }
QPushButton:disabled { color: #8a938d; background: #f1f3ef; }
QPushButton#primary { background: #315b4c; color: white; font-weight: 600; }
QPushButton#primary:disabled { background: #aebbb2; }
QPushButton#diagnosticDisclosure { border: none; text-align: left; color: #486453; padding-left: 0; }
QPlainTextEdit { background: #f4f6f2; border: 1px solid #e0e5de; font-family: Consolas; font-size: 9pt; }
QLineEdit { background: white; border: 1px solid #cbd3cb; border-radius: 4px; padding: 8px; }
QLineEdit:focus { border: 2px solid #315b4c; }
QLabel#fieldError { color: #984b3e; }
QTabBar::tab { padding: 12px 13px; border-bottom: 3px solid transparent; color: #68776e; }
QTabBar, QTabBar::tab { background: #f8faf7; }
QTabBar::tab:selected { border-bottom: 3px solid #315b4c; color: #254b3d; }
QScrollArea { border: none; background: white; }
"""


def label(text="", name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    widget.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
        | Qt.TextInteractionFlag.TextSelectableByKeyboard
    )
    if name:
        widget.setObjectName(name)
    return widget


class DestinationFields(QWidget):
    """Presentation-only reflow; field policy stays in the application."""

    def resizeEvent(self, event):
        self.layout().setDirection(
            QBoxLayout.Direction.TopToBottom
            if event.size().width() < 570
            else QBoxLayout.Direction.LeftToRight
        )
        super().resizeEvent(event)


class MainWindow(QMainWindow):
    """Public injected UI seam: submit commands and observe presented snapshot."""

    prepared = Signal(object)
    diagnostic_page_ready = Signal(object)
    diagnostic_action_ready = Signal(object)
    carry_ready = Signal(object)

    def __init__(
        self,
        supervisor=None,
        interpreter=None,
        source_root=None,
        dialogs=None,
        session=None,
        diagnostic_actions=None,
    ):
        super().__init__()
        self.setWindowTitle("brz2obsidian")
        self.resize(780, 820)
        self.setMinimumSize(440, 470)
        self.snapshot = SessionSnapshot()
        self.diagnostics_expanded = False
        self._may_close = False
        self._started = None
        self._started_at = {}
        self._result_identity = None
        self._next_offset = None
        self._dialog = None
        self._save_dialog = None
        self._diagnostic_generation = 0
        self._diagnostic_busy = False
        self._pending_form = None
        self.dialogs = dialogs
        self.diagnostic_actions = diagnostic_actions or DiagnosticActions()
        self.prepared.connect(self._present)
        self.carry_ready.connect(self._carried)
        self.diagnostic_page_ready.connect(self._diagnostic_page)
        self.diagnostic_action_ready.connect(self._diagnostic_finished)
        if supervisor is None:
            supervisor = Supervisor(
                Path(interpreter or sys.executable),
                Path(source_root or Path(__file__).parents[1]),
            )
        self.runner = HostRunner(
            supervisor,
            self.prepared.emit,
            self.diagnostic_page_ready.emit,
            session=session,
            on_diagnostic_feedback=self.diagnostic_action_ready.emit,
        )
        self._build()
        self.setStyleSheet(STYLE)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._elapsed)
        self._timer.start()
        self._render()

    def _build(self):
        surround = QWidget(objectName="surround")
        outer = QVBoxLayout(surround)
        outer.setContentsMargins(22, 20, 22, 20)
        sheet = QFrame(objectName="sheet")
        layout = QVBoxLayout(sheet)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QWidget(objectName="header")
        top = QVBoxLayout(header)
        top.setContentsMargins(26, 20, 26, 0)
        top.addWidget(label("brz2obsidian", "brand"))
        self.heading = label("Convert", "heading")
        self.explanation = label(EXPLANATIONS[0], "muted")
        top.addWidget(self.heading)
        top.addWidget(self.explanation)
        self.tabs = QTabBar()
        self.tabs.setAccessibleName("Operation")
        for title in ("Convert", "Inspect", "Check vault"):
            self.tabs.addTab(title)
        self.tabs.currentChanged.connect(self._render)
        top.addWidget(self.tabs)
        layout.addWidget(header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(26, 18, 26, 20)
        body.setSpacing(14)
        self.source_heading = label("Source archive", "sectionTitle")
        body.addWidget(self.source_heading)
        source_row = QHBoxLayout()
        source_icon = QLabel()
        source_icon.setPixmap(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon).pixmap(28, 32)
        )
        source_row.addWidget(source_icon)
        source_text = QVBoxLayout()
        self.source_name = label("Choose a BRZ archive")
        self.source_path = label("No archive selected", "sourcePath")
        self.source_path.setAccessibleName("Selected archive path")
        source_text.addWidget(self.source_name)
        source_text.addWidget(self.source_path)
        source_row.addLayout(source_text, 1)
        self.choose = QPushButton("Choose…")
        self.choose.setAccessibleName("Choose source archive")
        self.choose.clicked.connect(self.choose_source)
        source_row.addWidget(self.choose)
        body.addLayout(source_row)
        self.vault_error = label("", "fieldError")
        self.vault_error.setAccessibleName("Vault folder error")
        body.addWidget(self.vault_error)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        body.addWidget(divider)
        body.addWidget(label("Findings", "sectionTitle"))
        self.findings = label("Your inspection findings will appear here.", "findings")
        self.findings.setAccessibleName("Inspection findings")
        body.addWidget(self.findings)
        self.recovery_status = label("", "muted")
        self.recovery_status.setAccessibleName("Conversion recovery guidance")
        body.addWidget(self.recovery_status)
        self.counts = label("", "muted")
        body.addWidget(self.counts)
        self.pending = label("", "muted")
        body.addWidget(self.pending)
        self.disclosure = QPushButton(
            "▸ Diagnostic details", objectName="diagnosticDisclosure"
        )
        self.disclosure.setCheckable(True)
        self.disclosure.setAccessibleName("Diagnostic details")
        self.disclosure.toggled.connect(self._disclose)
        body.addWidget(self.disclosure)
        self.diagnostic_container = QWidget()
        details = QVBoxLayout(self.diagnostic_container)
        details.setContentsMargins(0, 0, 0, 0)
        self.diagnostic_text = QPlainTextEdit()
        self.diagnostic_text.setReadOnly(True)
        self.diagnostic_text.setAccessibleName("Diagnostic report page")
        self.diagnostic_text.setMinimumHeight(180)
        details.addWidget(self.diagnostic_text)
        self.next_page = QPushButton("Next diagnostic page")
        self.next_page.clicked.connect(
            lambda: self.runner.request_diagnostic_page(
                self._next_offset or 0, self._diagnostic_generation
            )
        )
        details.addWidget(self.next_page)
        actions = QHBoxLayout()
        self.copy = QPushButton("Copy details")
        self.save = QPushButton("Save diagnostic report")
        self.copy.clicked.connect(self.copy_details)
        self.save.clicked.connect(self.save_diagnostic_report)
        for button in (self.copy, self.save):
            button.setEnabled(False)
            button.setAccessibleName(button.text())
            actions.addWidget(button)
        actions.addStretch()
        details.addLayout(actions)
        self.diagnostic_feedback = label("", "muted")
        self.diagnostic_feedback.setAccessibleName("Diagnostic action feedback")
        details.addWidget(self.diagnostic_feedback)
        body.addWidget(self.diagnostic_container)
        self.diagnostic_container.hide()
        self.destination_form = QWidget()
        destination = QVBoxLayout(self.destination_form)
        destination.setContentsMargins(0, 0, 0, 0)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        destination.addWidget(divider)
        destination.addWidget(label("Destination", "sectionTitle"))
        self.destination_fields = DestinationFields()
        self.destination_fields.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        fields = QHBoxLayout(self.destination_fields)
        fields.setContentsMargins(0, 0, 0, 0)
        fields.setSpacing(18)
        parent_column = QWidget()
        parent = QVBoxLayout(parent_column)
        parent.setContentsMargins(0, 0, 0, 0)
        parent.setAlignment(Qt.AlignmentFlag.AlignTop)
        parent_title = label("Output parent folder")
        self.parent_path = QLineEdit()
        self.parent_path.setReadOnly(True)
        self.parent_path.setAccessibleName("Output parent folder")
        self.parent_path.setPlaceholderText("Choose a folder")
        parent_title.setBuddy(self.parent_path)
        parent.addWidget(parent_title)
        parent_row = QHBoxLayout()
        parent_row.addWidget(self.parent_path, 1)
        self.choose_parent_button = QPushButton("Choose…")
        self.choose_parent_button.setAccessibleName("Choose output parent folder")
        self.choose_parent_button.clicked.connect(self.choose_parent)
        parent_row.addWidget(self.choose_parent_button)
        parent.addLayout(parent_row)
        self.parent_error = label("", "fieldError")
        self.parent_error.setAccessibleName("Output parent folder error")
        parent.addWidget(self.parent_error)
        name_column = QWidget()
        name_layout = QVBoxLayout(name_column)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        name_title = label("Vault name")
        self.vault_name = QLineEdit()
        self.vault_name.setAccessibleName("Vault name")
        self.vault_name.textEdited.connect(self._destination_name_edited)
        name_title.setBuddy(self.vault_name)
        name_layout.addWidget(name_title)
        name_layout.addWidget(self.vault_name)
        self.name_error = label("", "fieldError")
        self.name_error.setAccessibleName("Vault name error")
        name_layout.addWidget(self.name_error)
        fields.addWidget(parent_column, 3)
        fields.addWidget(name_column, 2)
        destination.addWidget(self.destination_fields)
        destination.addWidget(label("Complete destination path", "muted"))
        self.destination_path = label("Complete path unavailable", "sourcePath")
        self.destination_path.setAccessibleName("Complete destination path")
        destination.addWidget(self.destination_path)
        self.destination_error = label("", "fieldError")
        self.destination_error.setAccessibleName("Destination error")
        destination.addWidget(self.destination_error)
        self.validation_status = label("Choose an output parent folder.", "muted")
        self.validation_status.setAccessibleName("Destination validation status")
        destination.addWidget(self.validation_status)
        body.addWidget(self.destination_form)
        self.published_panel = QWidget()
        published = QVBoxLayout(self.published_panel)
        published.setContentsMargins(0, 0, 0, 0)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        published.addWidget(divider)
        published.addWidget(label("Published vault", "sectionTitle"))
        self.published_path = label("", "sourcePath")
        self.published_path.setAccessibleName("Published vault path")
        published.addWidget(self.published_path)
        published.addWidget(
            label(
                "Publication was verified. No vault check or external application is started automatically.",
                "muted",
            )
        )
        body.addWidget(self.published_panel)
        body.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        footer = QWidget(objectName="footer")
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(26, 15, 26, 15)
        self.guidance = label("Nothing is written during inspection.", "muted")
        foot.addWidget(self.guidance, 1)
        self.activity = QProgressBar()
        self.activity.setRange(0, 0)
        self.activity.setFixedWidth(60)
        self.activity.setAccessibleName("Operation in progress")
        foot.addWidget(self.activity)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        foot.addWidget(self.close_button)
        self.recovery = QPushButton("Start another conversion")
        self.recovery.setAccessibleName("Start another conversion")
        self.recovery.clicked.connect(self._recovery_action)
        foot.addWidget(self.recovery)
        self.primary = QPushButton("Inspect archive", objectName="primary")
        self.primary.setAccessibleName("Inspect archive")
        self.primary.clicked.connect(self._primary_action)
        foot.addWidget(self.primary)
        layout.addWidget(footer)
        outer.addWidget(sheet)
        self.setCentralWidget(surround)
        QWidget.setTabOrder(self.choose, self.disclosure)
        QWidget.setTabOrder(self.disclosure, self.diagnostic_text)
        QWidget.setTabOrder(self.diagnostic_text, self.next_page)
        QWidget.setTabOrder(self.next_page, self.parent_path)
        QWidget.setTabOrder(self.parent_path, self.choose_parent_button)
        QWidget.setTabOrder(self.choose_parent_button, self.vault_name)
        QWidget.setTabOrder(self.vault_name, self.close_button)
        QWidget.setTabOrder(self.close_button, self.recovery)
        QWidget.setTabOrder(self.recovery, self.primary)

    def submit(self, command):
        self.runner.submit(command)

    def _recovery_action(self):
        if (
            self.tabs.currentIndex() == 0
            and "start_another_conversion" in self.snapshot.allowed_actions
        ):
            self.submit(SimpleCommand(command="start_another_conversion"))
        elif (
            self.tabs.currentIndex() == 0
            and "review_destination" in self.snapshot.allowed_actions
        ):
            self.submit(SimpleCommand(command="acknowledge_destination_review"))
        elif "retry" in self.snapshot.allowed_actions:
            command = {
                "inspect": InspectCommand(),
                "convert_reviewed": ConvertCommand(),
                "check_vault": SimpleCommand(command="check_vault"),
            }.get(self.snapshot.retry_operation)
            if command is not None:
                self.submit(command)

    def _primary_action(self):
        if (
            self.tabs.currentIndex() == 1
            and "convert_this_archive" in self.snapshot.allowed_actions
        ):
            revision = self.snapshot.revision
            self.runner.submit_if_current(
                SimpleCommand(command="carry_inspection_to_convert"),
                revision,
                on_complete=lambda update: self.carry_ready.emit((update, revision)),
            )
            return
        self.submit(
            SimpleCommand(command="check_vault")
            if self.tabs.currentIndex() == 2
            else ConvertCommand(
                proceed_with_warnings="convert_with_warnings"
                in self.snapshot.allowed_actions
            )
            if self.tabs.currentIndex() == 0 and self.snapshot.conversion_primary_action
            else InspectCommand()
        )

    def _carried(self, completion):
        update, revision = completion
        if (
            update.snapshot.revision == revision
            and self.snapshot == update.snapshot
            and "convert_this_archive" in update.snapshot.allowed_actions
        ):
            self.tabs.setCurrentIndex(0)
            self.primary.setFocus()

    def choose_source(self):
        if self.tabs.currentIndex() == 2:
            self.choose_vault()
            return
        if self.dialogs is not None:
            self.dialogs.choose_source(self.source_selected)
            return
        dialog = QFileDialog(self, "Choose BRZ archive")
        initial_directory = (
            str(Path(self.snapshot.source).parent)
            if self.snapshot.source
            else os.environ.get("USERPROFILE")
        )
        if initial_directory:
            dialog.setDirectory(initial_directory)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setNameFilters(
            ["BRZ archives (*.brz *.BRZ *.[bB][rR][zZ])", "All files (*)"]
        )
        dialog.fileSelected.connect(self.source_selected)
        dialog.finished.connect(self._picker_finished)
        self._dialog = dialog
        dialog.open()

    def choose_vault(self):
        if self.dialogs is not None:
            self.dialogs.choose_vault(self.vault_selected)
            return
        dialog = QFileDialog(self, "Choose vault folder")
        initial_directory = self.snapshot.vault or os.environ.get("USERPROFILE")
        if initial_directory:
            dialog.setDirectory(initial_directory)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.fileSelected.connect(self.vault_selected)
        dialog.finished.connect(self._picker_finished)
        self._dialog = dialog
        dialog.open()

    def vault_selected(self, path_or_null):
        """Asynchronous native folder callback; cancellation retains the result."""
        if path_or_null:
            self.submit(SelectVault(path_or_null=str(path_or_null)))

    def source_selected(self, path_or_null):
        """Asynchronous picker callback; cancellation preserves current state."""
        if path_or_null:
            self.submit(SelectSource(path_or_null=str(path_or_null)))

    def _picker_finished(self, _):
        if self._dialog is not None:
            self._dialog.deleteLater()
            self._dialog = None
        self.choose.setFocus()

    def choose_parent(self):
        if self.dialogs is not None:
            self.dialogs.choose_parent(self.parent_selected)
            return
        dialog = QFileDialog(self, "Choose output parent folder")
        initial_directory = self.snapshot.parent or os.environ.get("USERPROFILE")
        if initial_directory:
            dialog.setDirectory(initial_directory)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.fileSelected.connect(self.parent_selected)
        dialog.finished.connect(self._parent_picker_finished)
        self._dialog = dialog
        dialog.open()

    def parent_selected(self, path_or_null):
        if path_or_null:
            self._destination_edited(str(path_or_null), self.vault_name.text())
        self.choose_parent_button.setFocus()

    def _parent_picker_finished(self, _):
        if self._dialog is not None:
            self._dialog.deleteLater()
            self._dialog = None
        self.choose_parent_button.setFocus()

    def _destination_name_edited(self, text):
        parent = self._pending_form[0] if self._pending_form else self.snapshot.parent
        self._destination_edited(parent, text)

    def _destination_edited(self, parent, name):
        self._pending_form = (parent, name)
        self.submit(SetDestination(parent_or_null=parent, vault_name=name))
        self._render()

    def _disclose(self, expanded):
        self.diagnostics_expanded = expanded
        self.disclosure.setText(
            "▾ Diagnostic details" if expanded else "▸ Diagnostic details"
        )
        self.diagnostic_container.setVisible(expanded)

    def copy_details(self):
        self._diagnostic_busy = True
        self.diagnostic_feedback.setText("Copying diagnostic details…")
        # Obtain only a native integer on the Qt thread; the adapter accesses no Qt object.
        perform = partial(
            self.diagnostic_actions.copy_report, owner_window=int(self.winId())
        )
        self.runner.request_diagnostic_export(
            "copy_details", self._diagnostic_generation, perform
        )
        self._render()

    def save_diagnostic_report(self):
        generation = self._diagnostic_generation
        self._diagnostic_busy = True
        self._render()
        callback = partial(self.diagnostic_save_selected, generation)
        if self.dialogs is not None:
            self.dialogs.save_report(callback)
            return
        dialog = QFileDialog(self, "Save diagnostic report")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setNameFilter("Text reports (*.txt)")
        dialog.setDefaultSuffix("txt")
        dialog.selectFile("brz2obsidian-diagnostic-report.txt")
        dialog.fileSelected.connect(callback)
        dialog.finished.connect(partial(self._save_picker_finished, generation, dialog))
        self._save_dialog = dialog
        dialog.open()

    def diagnostic_save_selected(self, generation, path_or_null):
        """Dialog retains only host report identity, never its old safe payload."""
        if generation != self._diagnostic_generation:
            return
        self._diagnostic_busy = False
        if path_or_null:
            self._diagnostic_busy = True
            self.diagnostic_feedback.setText("Saving diagnostic report…")
            perform = partial(
                self.diagnostic_actions.save_report, destination=str(path_or_null)
            )
            self.runner.request_diagnostic_export(
                "save_diagnostic_report", generation, perform
            )
        elif generation == self._diagnostic_generation:
            self.diagnostic_feedback.setText("Diagnostic report save canceled.")
        self._render()
        self.save.setFocus()

    def _save_picker_finished(self, generation, dialog, accepted):
        if not accepted:
            self.diagnostic_save_selected(generation, None)
        dialog.deleteLater()
        if self._save_dialog is dialog:
            self._save_dialog = None
        if generation == self._diagnostic_generation:
            self.save.setFocus()

    def _diagnostic_finished(self, feedback):
        if feedback.generation != self._diagnostic_generation:
            return
        self._diagnostic_busy = False
        self.diagnostic_feedback.setText(feedback.message)
        self._render()

    def _diagnostic_page(self, prepared):
        if prepared.generation == self._diagnostic_generation:
            self._show_page(prepared.page)

    def _present(self, prepared):
        previous = self.snapshot
        self.snapshot = prepared.update.snapshot
        if self._diagnostic_generation != prepared.diagnostic_generation:
            self._diagnostic_generation = prepared.diagnostic_generation
            self._diagnostic_busy = False
            self.diagnostic_feedback.clear()
            self.disclosure.setChecked(False)
            self._show_page(prepared.diagnostics)
        if self.snapshot.source != previous.source or self._pending_form == (
            self.snapshot.parent,
            self.snapshot.vault_name,
        ):
            self._pending_form = None
        active = self.snapshot.active_request_id or self.snapshot.validation_request_id
        active_ids = {
            self.snapshot.active_request_id,
            self.snapshot.validation_request_id,
        } - {None}
        self._started_at = {
            identity: started
            for identity, started in self._started_at.items()
            if identity in active_ids
        }
        for identity in active_ids:
            if identity not in self._started_at:
                self._started_at[identity] = monotonic()
        self._started = self._started_at.get(active)
        if (
            self.snapshot.result is not previous.result
            or self.snapshot.feedback
            and not self.snapshot.active_request_id
        ):
            self._show_page(prepared.diagnostics)
        self._render()
        if any(effect.effect == "close_window" for effect in prepared.update.effects):
            if self._save_dialog is not None:
                self._save_dialog.reject()
            self._may_close = True
            self.close()

    def _show_page(self, page):
        self.diagnostic_text.setPlainText(page.text)
        self._next_offset = page.next_offset
        self.next_page.setVisible(page.next_offset is not None)

    def _render(self, *_):
        mode = self.tabs.currentIndex()
        self.findings.setAccessibleName(
            "Check findings" if mode == 2 else "Inspection findings"
        )
        self.heading.setText(self.tabs.tabText(mode))
        self.explanation.setText(EXPLANATIONS[mode])
        self.source_heading.setText("Vault to check" if mode == 2 else "Source archive")
        selected = self.snapshot.vault if mode == 2 else self.snapshot.source
        self.source_name.setText(
            Path(selected).name
            if selected
            else "Choose a vault folder"
            if mode == 2
            else "Choose a BRZ archive"
        )
        self.source_path.setText(
            selected or ("No vault selected" if mode == 2 else "No archive selected")
        )
        self.source_path.setAccessibleName(
            "Selected vault path" if mode == 2 else "Selected archive path"
        )
        self.choose.setText("Change…" if selected else "Choose…")
        self.choose.setAccessibleName(
            "Choose vault folder" if mode == 2 else "Choose source archive"
        )
        self.choose.setEnabled(
            not self.snapshot.active_request_id and not self.snapshot.close_pending
        )
        self.tabs.setEnabled(not self.snapshot.active_request_id)
        self.activity.setVisible(
            bool(self.snapshot.active_request_id or self.snapshot.validation_request_id)
        )
        primary_action = (
            "check_vault"
            if mode == 2
            else "convert_this_archive"
            if mode == 1 and "convert_this_archive" in self.snapshot.allowed_actions
            else self.snapshot.conversion_primary_action
            if mode == 0 and self.snapshot.conversion_primary_action
            else "inspect"
        )
        self.copy.setEnabled(
            "copy_details" in self.snapshot.allowed_actions
            and not self._diagnostic_busy
        )
        self.save.setEnabled(
            "save_diagnostic_report" in self.snapshot.allowed_actions
            and not self._diagnostic_busy
        )
        self.primary.setEnabled(primary_action in self.snapshot.allowed_actions)
        self.primary.setText(
            {
                "check_vault": "Check vault",
                "convert_this_archive": "Convert this archive",
                "convert_with_warnings": "Convert with warnings",
                "convert": "Convert",
                "inspect": "Inspect archive",
            }[primary_action]
        )
        self.primary.setAccessibleName(self.primary.text())
        publication = self.snapshot.publication
        published = publication is not None and publication.receipt_verified
        locked = publication is not None and (
            publication.receipt_verified
            or publication.state == "unknown"
            and not self.snapshot.destination_review_acknowledged
        )
        retry = "retry" in self.snapshot.allowed_actions and (
            self.snapshot.retry_operation == "check_vault"
            and mode == 2
            or self.snapshot.retry_operation == "inspect"
            and mode != 2
            or self.snapshot.retry_operation == "convert_reviewed"
            and mode == 0
        )
        self.primary.setVisible(not (mode == 0 and published) and not retry)
        self.recovery.setVisible(
            retry
            or mode == 0
            and any(
                action in self.snapshot.allowed_actions
                for action in ("start_another_conversion", "review_destination")
            )
        )
        self.recovery.setText(
            "I reviewed the destination"
            if mode == 0 and "review_destination" in self.snapshot.allowed_actions
            else {
                "inspect": "Inspect again",
                "convert_reviewed": "Retry conversion",
                "check_vault": "Retry check",
            }.get(self.snapshot.retry_operation, "Retry")
            if retry
            else "Start another conversion"
        )
        self.recovery.setAccessibleName(self.recovery.text())
        recovery = []
        if publication is not None and publication.state == "unknown":
            recovery.append(
                "Publication status unknown. Previous destination: "
                + (publication.destination or "unavailable")
                + "\nReview that destination before acknowledging. Acknowledgment does not establish publication. Inspect the current archive and validate a usable destination before another attempt."
            )
        recovery.extend(
            finding.message
            + ("\nReported leftover: " + finding.path if finding.path else "")
            for finding in self.snapshot.recovery_findings
        )
        self.recovery_status.setText("\n".join(recovery))
        self.recovery_status.setVisible(mode == 0 and bool(recovery))
        if mode != 2 and locked:
            self.choose.setEnabled(False)
        if mode == 0 and self.snapshot.conversion_primary_action:
            self.primary.setToolTip(
                "Choose a valid destination before converting."
                if primary_action not in self.snapshot.allowed_actions
                else "Convert the current reviewed archive with the warnings shown above."
                if primary_action == "convert_with_warnings"
                else "Convert the reviewed archive into the displayed fresh vault."
            )
        self.destination_form.setVisible(mode == 0 and not published)
        self.published_panel.setVisible(mode == 0 and published)
        self.published_path.setText(publication.destination if published else "")
        self.choose_parent_button.setEnabled(
            not self.snapshot.active_request_id
            and not self.snapshot.close_pending
            and not locked
        )
        self.vault_name.setEnabled(
            not self.snapshot.active_request_id
            and not self.snapshot.close_pending
            and not locked
        )
        if self._pending_form is None:
            self.vault_name.setText(self.snapshot.vault_name)
            self.parent_path.setText(self.snapshot.parent or "")
        errors = () if self._pending_form else self.snapshot.field_errors
        for widget, field in (
            (self.parent_error, "parent"),
            (self.name_error, "vault_name"),
            (self.destination_error, "destination"),
        ):
            widget.setText(
                "\n".join(error.message for error in errors if error.field == field)
            )
            widget.setVisible(bool(widget.text()))
        validating = self._pending_form is not None or self.snapshot.validation_pending
        self.destination_path.setText(
            self.snapshot.destination
            if self.snapshot.destination and not validating
            else "Complete path unavailable"
            if not validating
            else "Waiting for destination validation…"
        )
        validation = self.snapshot.destination_validation
        self.validation_status.setText(
            "Checking destination…"
            if validating
            else "Preliminary check passed. No folder is reserved. Generated paths, collisions, manifest and final 240 UTF-16-unit paths remain pending; write success is checked during publication."
            if validation and validation.outcome == "valid"
            else "Destination check could not complete. Correct the fields or choose again when ready."
            if validation and validation.outcome == "failed"
            else "Correct the destination fields before conversion."
            if validation
            else "Review the destination and validate a corrected choice before another conversion."
            if publication is not None
            else "Choose an output parent folder."
        )
        result = self.snapshot.result
        self.vault_error.setText(
            "\n".join(
                error.message for error in result.field_errors if error.field == "vault"
            )
            if mode == 2 and result is not None and result.operation == "check_vault"
            else ""
        )
        self.vault_error.setVisible(bool(self.vault_error.text()))
        severity = "info"
        if self.snapshot.active_request_id:
            self.findings.setText(
                (
                    "Checking vault"
                    if self.snapshot.busy_operation == "check_vault"
                    else "Converting archive"
                    if self.snapshot.busy_operation == "convert_reviewed"
                    else "Inspecting archive"
                )
                + "\nWaiting for the worker. The window remains available."
            )
        elif self.snapshot.feedback:
            self.findings.setText(self.snapshot.feedback)
            severity = "error"
        elif result is not None:
            self.findings.setText(
                TITLES.get(result.status, result.status)
                + (
                    "\nThis read-only check covers current vault structure and conventions. It does not repair files or prove preservation of source content."
                    if result.operation == "check_vault"
                    else ""
                )
                + (
                    "\n"
                    + "\n".join(
                        f.message + (f"\nReported leftover: {f.path}" if f.path else "")
                        for f in result.findings[:100]
                    )
                    if result.findings
                    else ""
                    if result.operation == "check_vault"
                    else "\nVerified publication. The generated vault has not been checked."
                    if result.operation == "convert_reviewed"
                    and result.publication.receipt_verified
                    else "\nReview the failure guidance and destination before another attempt."
                    if result.operation == "convert_reviewed"
                    else "\nReview the planned contents and pending checks below."
                )
                + (
                    f"\n{len(result.findings) - 100} further findings are available in Diagnostic details."
                    if len(result.findings) > 100
                    else ""
                )
                + (
                    "\nDiagnostic findings were omitted because the response limit was reached."
                    if result.diagnostic_omission
                    else ""
                )
            )
            severity = (
                "warning"
                if result.outcome in ("warnings", "issues")
                else "error"
                if result.outcome in ("refused", "failed")
                else "info"
            )
        else:
            self.findings.setText(
                "Choose an existing vault folder to check its current structure and conventions. This read-only check does not repair files."
                if mode == 2
                else "Inspect the archive to see its planned contents. Nothing is written during inspection."
            )
        self.findings.setProperty("severity", severity)
        self.findings.style().unpolish(self.findings)
        self.findings.style().polish(self.findings)
        self.counts.setText(
            "    ".join(
                f"{title}: {getattr(result.counts, name) if getattr(result.counts, name) is not None else 'unavailable'}"
                for name, title in (
                    ("inventory_files", "Inventory files"),
                    ("markdown_files", "Markdown files"),
                    ("base_files", "Base files"),
                    ("read_markdown_files", "Markdown files read"),
                    ("read_base_files", "Base files read"),
                    ("category_notes", "Category notes"),
                    ("imported_notes", "Imported notes"),
                )
            )
            if result and result.operation == "check_vault"
            else "\n".join(
                (
                    f"Planned notes: {result.counts.planned_notes if result.counts.planned_notes is not None else 'unavailable'}    Planned resources: {result.counts.planned_assets if result.counts.planned_assets is not None else 'unavailable'}",
                    f"Planned categories: {result.counts.planned_category_notes if result.counts.planned_category_notes is not None else 'unavailable'}    Actual notes: {result.counts.actual_notes if result.counts.actual_notes is not None else 'unavailable'}",
                )
            )
            if result
            else ""
        )
        self.pending.setText(
            "Pending: "
            + "; ".join(
                CHECK_LABELS.get(check, "additional backend check")
                for check in result.pending
            )
            if result and result.pending
            else ""
        )
        self._elapsed()

    def _elapsed(self):
        if self.snapshot.active_request_id or self.snapshot.validation_request_id:
            seconds = (
                int(monotonic() - self._started) if self._started is not None else 0
            )
            self.guidance.setText(
                ("Close requested. " if self.snapshot.close_pending else "")
                + f"{'Checking vault' if self.snapshot.busy_operation == 'check_vault' else 'Converting archive' if self.snapshot.busy_operation == 'convert_reviewed' else 'Inspecting archive' if self.snapshot.active_request_id else 'Validating destination'} · {seconds // 60}:{seconds % 60:02d} elapsed"
            )
        else:
            self.guidance.setText(
                "Checking does not change the selected vault."
                if self.tabs.currentIndex() == 2
                else "Verified vault created. Review the published path and any reported follow-up error."
                if self.snapshot.publication is not None
                and self.snapshot.publication.receipt_verified
                else "Review the destination before another attempt. Publication could not be established."
                if self.snapshot.publication is not None
                and self.snapshot.publication.state == "unknown"
                else "Inspection and preliminary validation are read-only."
            )

    def closeEvent(self, event):
        if self._may_close:
            event.accept()
        else:
            event.ignore()
            self.submit(SimpleCommand(command="request_close"))

    def shutdown(self):
        self._timer.stop()
        self.runner.shutdown()
