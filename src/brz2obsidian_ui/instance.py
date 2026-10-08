"""User-local activation only. All lifecycle methods run outside the Qt thread.

An OS-held lock decides ownership; the JSON endpoint never decides whether a
process is alive. A crashed owner releases its lock automatically, allowing a
new owner to replace its transient registration. No converter lock is involved.
"""

import ctypes
import json
import msvcrt
import os
import secrets
import socket
import tempfile
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread


@dataclass(frozen=True)
class InstanceResult:
    status: str
    feedback: str | None = None


def coordination_directory() -> Path | None:
    """Resolve separate user-profile-local coordination storage off-thread."""
    profile = os.environ.get("USERPROFILE")
    if not profile or not Path(profile).is_absolute():
        return None
    return Path(profile) / "AppData" / "Local" / "Temp" / "brz2obsidian"


class WindowActivator:
    """Restore/request foreground, respecting denial with taskbar attention.

    The handle is captured on the Qt thread; these native calls run outside it.
    ``windows`` is the outer OS boundary for deterministic foreground controls.
    """

    def __init__(self, windows=None):
        self.windows = windows if windows is not None else _WindowsActivation()

    def activate(self, hwnd: int) -> InstanceResult:
        try:
            self.windows.restore(hwnd)
            if self.windows.foreground(hwnd):
                return InstanceResult("activated")
            self.windows.attention(hwnd)
        except OSError:
            pass
        return InstanceResult(
            "attention_requested",
            "The app is already open. Select it from the taskbar.",
        )


class _WindowsActivation:
    def __init__(self):
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        self.api.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
        self.api.ShowWindowAsync.restype = wintypes.BOOL
        self.api.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.api.SetForegroundWindow.restype = wintypes.BOOL

    def restore(self, hwnd):
        self.api.ShowWindowAsync(hwnd, 9)  # SW_RESTORE; posts without waiting.

    def foreground(self, hwnd):
        return bool(self.api.SetForegroundWindow(hwnd))

    def attention(self, hwnd):
        class FlashInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("hwnd", wintypes.HWND),
                ("dwFlags", wintypes.DWORD),
                ("uCount", wintypes.UINT),
                ("dwTimeout", wintypes.DWORD),
            ]

        self.api.FlashWindowEx.argtypes = [ctypes.POINTER(FlashInfo)]
        self.api.FlashWindowEx.restype = wintypes.BOOL
        # FLASHW_ALL: flash both taskbar and caption, without forcing focus.
        details = FlashInfo(ctypes.sizeof(FlashInfo), hwnd, 3, 3, 0)
        self.api.FlashWindowEx(ctypes.byref(details))


class LocalInstance:
    """Claim one local UI, or request activation of the existing owner.

    ``on_activate`` runs on an outer thread and must marshal any Qt interaction.
    An unavailable endpoint never authorizes another window while its lock is
    held. Tests use a separate root, never the real user's application directory.
    """

    def __init__(self, directory: Path | None, on_activate):
        self.directory = directory
        self.on_activate = on_activate
        self.owns_endpoint = False
        self._lock = None
        self._socket = None
        self._stop = Event()
        self._token = secrets.token_hex(32)

    def claim(self) -> InstanceResult:
        try:
            if self.directory is None:
                raise OSError("User-local coordination unavailable")
            self.directory.mkdir(parents=True, exist_ok=True)
            self._lock = (self.directory / "instance.lock").open("a+b")
            if os.fstat(self._lock.fileno()).st_size == 0:
                self._lock.write(b"\0")
                self._lock.flush()
            self._lock.seek(0)
            try:
                msvcrt.locking(self._lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self._lock.close()
                self._lock = None
                return self._request_activation()
            self.owns_endpoint = True
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.bind(("127.0.0.1", 0))
            self._socket.listen(8)
            self._socket.settimeout(0.2)
            Thread(target=self._serve, name="ui-activation", daemon=True).start()
            registration = {
                "port": self._socket.getsockname()[1],
                "token": self._token,
            }
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=self.directory, delete=False
                ) as stream:
                    temporary = Path(stream.name)
                    json.dump(registration, stream)
                os.replace(temporary, self.directory / "instance.json")
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return InstanceResult("primary")
        except OSError:
            self.close()
            return InstanceResult(
                "unavailable",
                "The app could not coordinate this launch. Close other app windows and try again.",
            )

    def _request_activation(self):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                with (self.directory / "instance.json").open("rb") as stream:
                    registration = json.loads(stream.read(513))
                if (
                    set(registration) != {"port", "token"}
                    or type(registration["port"]) is not int
                    or not 1 <= registration["port"] <= 65535
                    or not isinstance(registration["token"], str)
                    or len(registration["token"]) != 64
                ):
                    raise ValueError("Invalid endpoint")
                with socket.create_connection(
                    ("127.0.0.1", registration["port"]), timeout=0.3
                ) as connection:
                    connection.sendall(
                        f"activate {registration['token']}\n".encode("ascii")
                    )
                    if connection.recv(32) == b"activation requested\n":
                        return InstanceResult("activation_requested")
            except OSError, ValueError, TypeError, UnicodeError:
                pass
            time.sleep(0.05)
        return InstanceResult(
            "unavailable",
            "Another app instance is starting or unavailable. Try opening it from the taskbar.",
        )

    def _serve(self):
        listener = self._socket
        while not self._stop.is_set():
            try:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(0.3)
                    message = bytearray()
                    while len(message) <= 128 and not message.endswith(b"\n"):
                        chunk = connection.recv(129 - len(message))
                        if not chunk:
                            break
                        message.extend(chunk)
                    if message == f"activate {self._token}\n".encode("ascii"):
                        self.on_activate()
                        connection.sendall(b"activation requested\n")
            except OSError:
                continue

    def close(self):
        """Release transient coordination; never terminate an operation/process."""
        self._stop.set()
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self.owns_endpoint:
            try:
                (self.directory / "instance.json").unlink(missing_ok=True)
            except OSError:
                pass
        if self._lock is not None:
            if self.owns_endpoint:
                self._lock.seek(0)
                msvcrt.locking(self._lock.fileno(), msvcrt.LK_UNLCK, 1)
            self._lock.close()
            self._lock = None
        self.owns_endpoint = False
