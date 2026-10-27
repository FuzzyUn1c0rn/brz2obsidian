"""Public typed producer projections for thin Qt adapter state coverage."""

from itertools import count

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QPushButton, QTabBar

from brz2obsidian.application.contracts import WorkerResponse
from brz2obsidian.application.transport import Terminal
from tests.gui.test_conversion_window import until


class ProjectedReviewTransport:
    """Controlled outer transport; shared HostRunner/session admission remains real."""

    def __init__(self, projection):
        self.projection = projection
        self.commands = []
        self.closed = self.poisoned = False
        self.sequence = count(1)

    def open_update(self, **kwargs):
        self.closed = False
        return self

    def run(self, request, **callbacks):
        actual = request.model_copy(update={"sequence": next(self.sequence)})
        if callbacks.get("on_dispatched"):
            callbacks["on_dispatched"](actual)
        self.commands.append(actual.arguments)
        result = self.projection(actual, callbacks)
        return Terminal(phase="completed", response=WorkerResponse(
            operation="update", request_id=actual.request_id,
            sequence=actual.sequence, result=result,
        ))

    def close(self):
        self.closed = True


class ReviewControls:
    def __init__(self, window, app):
        self.window, self.app = window, app
        tabs = window.findChild(QTabBar)
        tabs.setCurrentIndex(next(i for i in range(tabs.count()) if tabs.tabText(i) == "Update vault"))

    def button(self, name):
        return next((w for w in self.window.findChildren(QPushButton)
                     if w.isVisible() and w.accessibleName() == name), None)

    def click(self, name):
        until(self.app, lambda: self.button(name) is not None and self.button(name).isEnabled())
        self.button(name).click()

    def select(self, name):
        queue = next(w for w in self.window.findChildren(QAbstractItemView)
                     if w.accessibleName() == "Review queue")
        index = next(queue.model().index(i, 0) for i in range(queue.model().rowCount())
                     if queue.model().index(i, 0).data() == name)
        QTest.mouseClick(queue.viewport(), Qt.MouseButton.LeftButton, pos=queue.visualRect(index).center())
        self.app.processEvents()


class ReviewDialogs:
    def __init__(self, source, vault):
        self.source, self.vault = str(source), str(vault)

    def choose_source(self, callback):
        callback(self.source)

    def choose_vault(self, callback):
        callback(self.vault)
