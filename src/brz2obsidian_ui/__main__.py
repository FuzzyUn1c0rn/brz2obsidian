"""Window entrypoint; build launcher supplies absolute code/interpreter paths."""

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from brz2obsidian_ui.preferences import ParentPreferences, application_data
from brz2obsidian_ui.startup import StartupCoordinator
from brz2obsidian_ui.window import MainWindow


class LocalApplication(QObject):
    """Qt notification boundary; only the owner constructs a migration window."""

    primary_ready = Signal()
    exit_ready = Signal(object)
    activation_feedback = Signal(object)
    preference_feedback = Signal(object)

    def __init__(
        self,
        app,
        interpreter,
        source_root,
        window_factory=MainWindow,
        coordinator_factory=StartupCoordinator,
        preferences=None,
    ):
        super().__init__()
        self.app = app
        self.interpreter, self.source_root = interpreter, source_root
        self.window_factory = window_factory
        self.window = None
        self.notice = None
        self._feedback_revision = None
        directory = application_data()
        self.preferences = (
            preferences if preferences is not None else ParentPreferences(directory)
        )
        self.primary_ready.connect(self._show_primary)
        self.exit_ready.connect(self._exit)
        self.activation_feedback.connect(self._activation_feedback)
        self.preference_feedback.connect(self._preference_feedback)
        self.coordinator = coordinator_factory(
            None,
            self.primary_ready.emit,
            self.exit_ready.emit,
            self.activation_feedback.emit,
        )
        app.aboutToQuit.connect(self.coordinator.shutdown)

    def start(self):
        self.coordinator.begin()

    def _show_primary(self):
        self.window = self.window_factory(
            interpreter=self.interpreter, source_root=self.source_root
        )
        # The window's policy-free runner performs both loads and effect writes
        # off-thread. Keep this injection compatible with the existing UI seam.
        self.window.runner.preferences = self.preferences
        self.window.runner.on_feedback = self.preference_feedback.emit
        self.window.prepared.connect(self._revision_changed)
        self.window.show()
        self.coordinator.window_ready(int(self.window.winId()))
        self.window.runner.restore_preferences()

    def _exit(self, result):
        if result.feedback:
            self.notice = QMessageBox()
            self.notice.setWindowTitle("brz2obsidian")
            self.notice.setText(result.feedback)
            self.notice.finished.connect(lambda status: self.app.exit(1))
            self.notice.open()
        else:
            self.app.quit()

    def _activation_feedback(self, result):
        if self.window is not None:
            self._feedback_revision = None
            self._show_feedback(result.feedback)

    def _preference_feedback(self, feedback):
        if (
            self.window is not None
            and self.window.snapshot.revision == feedback.input_revision
        ):
            self._feedback_revision = feedback.input_revision
            self._show_feedback(feedback.text)

    def _revision_changed(self, prepared):
        if (
            self._feedback_revision is not None
            and prepared.update.snapshot.revision != self._feedback_revision
        ):
            self.window.statusBar().clearMessage()
            self._feedback_revision = None

    def _show_feedback(self, text):
        status = self.window.statusBar()
        status.setAccessibleName("Application feedback")
        status.showMessage(text[:256])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--python", type=Path, default=Path(sys.executable).with_name("python.exe")
    )
    parser.add_argument("--source-root", type=Path, default=Path(__file__).parents[1])
    options = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("brz2obsidian")
    local = LocalApplication(app, options.python, options.source_root)
    local.start()
    status = app.exec()
    if local.window is not None:
        local.window.shutdown()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
