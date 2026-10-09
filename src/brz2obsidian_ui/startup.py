"""Off-thread local-launch lifecycle; callbacks marshal bounded Qt notifications."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

from brz2obsidian_ui.instance import (
    LocalInstance,
    WindowActivator,
    coordination_directory,
)


class StartupCoordinator:
    def __init__(
        self,
        directory,
        on_primary,
        on_exit,
        on_feedback,
        instance_factory=LocalInstance,
        activator_factory=WindowActivator,
    ):
        self.on_primary, self.on_exit, self.on_feedback = (
            on_primary,
            on_exit,
            on_feedback,
        )
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ui-startup"
        )
        self._stopped = Event()
        self._instance_factory = instance_factory
        self._activator_factory = activator_factory
        self._directory = directory
        self._instance = None
        self._hwnd = None
        self._pending_activation = False

    def begin(self):
        self._executor.submit(self._claim)

    def _claim(self):
        directory = (
            self._directory if self._directory is not None else coordination_directory()
        )
        self._instance = self._instance_factory(directory, self._requested)
        result = self._instance.claim()
        if self._stopped.is_set():
            self._instance.close()
        elif result.status == "primary":
            self.on_primary()
        else:
            self.on_exit(result)

    def _requested(self):
        if not self._stopped.is_set():
            self._executor.submit(self._activate)

    def window_ready(self, hwnd: int):
        # Capture winId on the Qt thread, pass only the integer to this executor.
        self._executor.submit(self._window_ready, hwnd)

    def _window_ready(self, hwnd):
        self._hwnd = hwnd
        if self._pending_activation:
            self._activate()

    def _activate(self):
        if self._hwnd is None:
            self._pending_activation = True
            return
        self._pending_activation = False
        result = self._activator_factory().activate(self._hwnd)
        if result.feedback and not self._stopped.is_set():
            self.on_feedback(result)

    def shutdown(self):
        self._stopped.set()
        self._executor.submit(self._close)
        self._executor.shutdown(wait=False)

    def _close(self):
        if self._instance is not None:
            self._instance.close()
