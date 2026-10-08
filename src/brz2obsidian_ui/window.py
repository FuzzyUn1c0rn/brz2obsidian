"""C's compact task sheet, rendering only backend-owned safe facts."""

import os
import sys
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
    InspectCommand,
    SelectSource,
    SelectVault,
    SessionSnapshot,
    SetDestination,
    SimpleCommand,
)
from brz2obsidian.application.runner import HostRunner
from brz2obsidian.application.transport import Supervisor

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

    def __init__(
        self,
        supervisor=None,
        interpreter=None,
        source_root=None,
        dialogs=None,
        session=None,
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
        self._pending_form = None
        self.dialogs = dialogs
        self.prepared.connect(self._present)
        self.diagnostic_page_ready.connect(self._show_page)
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
            lambda: self.runner.request_diagnostic_page(self._next_offset or 0)
        )
        details.addWidget(self.next_page)
        actions = QHBoxLayout()
        self.copy = QPushButton("Copy details")
        self.save = QPushButton("Save diagnostic report")
        for button in (self.copy, self.save):
            button.setEnabled(False)
            button.setToolTip("Diagnostic export is not available in this build.")
            button.setAccessibleName(button.text())
            actions.addWidget(button)
        actions.addStretch()
        details.addLayout(actions)
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
        QWidget.setTabOrder(self.close_button, self.primary)

    def submit(self, command):
        self.runner.submit(command)

    def _primary_action(self):
        self.submit(
            SimpleCommand(command="check_vault")
            if self.tabs.currentIndex() == 2
            else InspectCommand()
        )

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

    def _present(self, prepared):
        previous = self.snapshot
        self.snapshot = prepared.update.snapshot
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
        self.primary.setEnabled(
            ("check_vault" if mode == 2 else "inspect") in self.snapshot.allowed_actions
        )
        self.primary.setText(
            "Check vault"
            if mode == 2
            else "Convert"
            if mode == 0 and self.snapshot.reviewed
            else "Inspect archive"
        )
        self.primary.setAccessibleName(self.primary.text())
        if mode == 0 and self.snapshot.reviewed:
            self.primary.setEnabled(False)
            self.primary.setToolTip("Conversion is not available in this build.")
        self.destination_form.setVisible(mode == 0)
        self.choose_parent_button.setEnabled(
            not self.snapshot.active_request_id and not self.snapshot.close_pending
        )
        self.vault_name.setEnabled(
            not self.snapshot.active_request_id and not self.snapshot.close_pending
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
            else "Preliminary check passed. No folder is reserved. Generated paths, collisions, manifest and final 240 UTF-16-unit paths remain pending; write success is checked during publication. Conversion is not available in this build."
            if validation and validation.outcome == "valid"
            else "Destination check could not complete. Correct the fields or choose again when ready."
            if validation and validation.outcome == "failed"
            else "Correct the destination fields before conversion."
            if validation
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
                    "\n" + "\n".join(f.message for f in result.findings[:100])
                    if result.findings
                    else ""
                    if result.operation == "check_vault"
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
                + f"{'Checking vault' if self.snapshot.busy_operation == 'check_vault' else 'Inspecting archive' if self.snapshot.active_request_id else 'Validating destination'} · {seconds // 60}:{seconds % 60:02d} elapsed"
            )
        else:
            self.guidance.setText(
                "Checking does not change the selected vault."
                if self.tabs.currentIndex() == 2
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
