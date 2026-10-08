"""C's compact task sheet, rendering only backend-owned safe facts."""

import os
import sys
from pathlib import Path
from time import monotonic

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStyle,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from brz2obsidian.application.contracts import (
    InspectCommand,
    SelectSource,
    SessionSnapshot,
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
}
CHECK_LABELS = {
    "destination_feasibility": "destination and generated-path feasibility",
    "source_freshness": "source freshness before conversion",
    "publication": "verified vault publication",
    "generated_vault_check": "checking the generated vault",
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
QTabBar::tab { padding: 12px 13px; border-bottom: 3px solid transparent; color: #68776e; }
QTabBar, QTabBar::tab { background: #f8faf7; }
QTabBar::tab:selected { border-bottom: 3px solid #315b4c; color: #254b3d; }
QScrollArea { border: none; background: white; }
"""


def label(text="", name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
        | Qt.TextInteractionFlag.TextSelectableByKeyboard
    )
    if name:
        widget.setObjectName(name)
    return widget


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
        self._result_identity = None
        self._next_offset = None
        self._dialog = None
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
        self.convert_note = label(
            "Inspect the archive before choosing a destination. Conversion is not available in this build.",
            "muted",
        )
        body.addWidget(self.convert_note)
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
        self.primary.clicked.connect(lambda: self.submit(InspectCommand()))
        foot.addWidget(self.primary)
        layout.addWidget(footer)
        outer.addWidget(sheet)
        self.setCentralWidget(surround)

    def submit(self, command):
        self.runner.submit(command)

    def choose_source(self):
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

    def source_selected(self, path_or_null):
        """Asynchronous picker callback; cancellation preserves current state."""
        if path_or_null:
            self.submit(SelectSource(path_or_null=str(path_or_null)))

    def _picker_finished(self, _):
        if self._dialog is not None:
            self._dialog.deleteLater()
            self._dialog = None
        self.choose.setFocus()

    def _disclose(self, expanded):
        self.diagnostics_expanded = expanded
        self.disclosure.setText(
            "▾ Diagnostic details" if expanded else "▸ Diagnostic details"
        )
        self.diagnostic_container.setVisible(expanded)

    def _present(self, prepared):
        previous = self.snapshot
        self.snapshot = prepared.update.snapshot
        if self.snapshot.active_request_id != previous.active_request_id:
            self._started = monotonic() if self.snapshot.active_request_id else None
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
        self.heading.setText(self.tabs.tabText(mode))
        self.explanation.setText(EXPLANATIONS[mode])
        self.source_heading.setText("Vault to check" if mode == 2 else "Source archive")
        self.source_name.setText(
            Path(self.snapshot.source).name
            if self.snapshot.source
            else "Choose a BRZ archive"
        )
        self.source_path.setText(self.snapshot.source or "No archive selected")
        self.choose.setText("Change…" if self.snapshot.source else "Choose…")
        self.choose.setEnabled(not self.snapshot.active_request_id and mode != 2)
        self.tabs.setEnabled(not self.snapshot.active_request_id)
        self.activity.setVisible(bool(self.snapshot.active_request_id))
        self.primary.setEnabled(
            "inspect" in self.snapshot.allowed_actions and mode != 2
        )
        self.convert_note.setVisible(mode == 0)
        result = self.snapshot.result
        severity = "info"
        if self.snapshot.active_request_id:
            self.findings.setText(
                "Inspecting archive\nWaiting for the worker. The window remains available."
            )
        elif self.snapshot.feedback:
            self.findings.setText(self.snapshot.feedback)
            severity = "error"
        elif result is not None:
            self.findings.setText(
                TITLES.get(result.status, result.status)
                + (
                    "\n" + "\n".join(f.message for f in result.findings[:100])
                    if result.findings
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
                if result.outcome == "warnings"
                else "error"
                if result.outcome in ("refused", "failed")
                else "info"
            )
        else:
            self.findings.setText(
                "Checking is not available in this build."
                if mode == 2
                else "Inspect the archive to see its planned contents. Nothing is written during inspection."
            )
        self.findings.setProperty("severity", severity)
        self.findings.style().unpolish(self.findings)
        self.findings.style().polish(self.findings)
        self.counts.setText(
            "\n".join(
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
            if result
            else ""
        )
        self._elapsed()

    def _elapsed(self):
        if self.snapshot.active_request_id:
            seconds = (
                int(monotonic() - self._started) if self._started is not None else 0
            )
            self.guidance.setText(
                ("Close requested. " if self.snapshot.close_pending else "")
                + f"Inspecting archive · {seconds // 60}:{seconds % 60:02d} elapsed"
            )
        else:
            self.guidance.setText("Nothing is written during inspection.")

    def closeEvent(self, event):
        if self._may_close:
            event.accept()
        else:
            event.ignore()
            self.submit(SimpleCommand(command="request_close"))

    def shutdown(self):
        self._timer.stop()
        self.runner.shutdown()
