"""Outer local actions; invoke on an adapter thread, never the Qt thread."""

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import quote


@dataclass(frozen=True)
class ActionOutcome:
    succeeded: bool
    message: str


@dataclass(frozen=True)
class CompletionOutcome:
    succeeded: bool
    message: str
    path: str | None


class CompletionActions:
    """Open backend-admitted absolute targets without inspecting their content."""

    def __init__(self, launch=None):
        self._launch = launch or open_windows_target

    def open_folder(self, destination: Path | str, *, admit=None) -> CompletionOutcome:
        return self._open(destination, folder=True, admit=admit)

    def open_report(self, report: Path | str, *, admit=None) -> CompletionOutcome:
        return self._open(report, admit=admit)

    def open_in_obsidian(self, report: Path | str, *, admit=None) -> CompletionOutcome:
        report = Path(report)
        path = str(report) if report.is_absolute() else None
        guidance = "If needed, choose Open folder as vault in Obsidian using the published folder path."
        try:
            if path is None or not report.is_file():
                return CompletionOutcome(
                    False, "The migration report is unavailable.", path
                )
            if admit is not None and not admit():
                return CompletionOutcome(
                    False,
                    "The published result changed. Use the current result and try again.",
                    path,
                )
            self._launch("obsidian://open?path=" + quote(path, safe=""))
            return CompletionOutcome(
                True,
                "Opening in Obsidian was requested. This does not confirm the vault opened. "
                + guidance,
                path,
            )
        except Exception:  # noqa: BLE001 -- unavailable URI handlers are nonfatal.
            return CompletionOutcome(
                False,
                "Obsidian could not be opened. Its URI handler may be unavailable. "
                + guidance,
                path,
            )

    def _open(
        self, target: Path | str, *, folder: bool = False, admit=None
    ) -> CompletionOutcome:
        target = Path(target)
        path = str(target) if target.is_absolute() else None
        name = "published folder" if folder else "migration report"
        try:
            if path is None or not (target.is_dir() if folder else target.is_file()):
                return CompletionOutcome(False, f"The {name} is unavailable.", path)
            if admit is not None and not admit():
                return CompletionOutcome(
                    False,
                    "The published result changed. Use the current result and try again.",
                    path,
                )
            self._launch(path)
            return CompletionOutcome(True, f"Opening the {name} was requested.", path)
        except Exception:  # noqa: BLE001 -- native open failures are local feedback.
            return CompletionOutcome(
                False,
                f"The {name} could not be opened. You can use the path below.",
                path,
            )


def open_windows_target(target: str) -> None:
    """Request the registered Windows open action without a shell command."""
    os.startfile(target, "open")


class DiagnosticActions:
    """Perform explicit local exports of backend-admitted safe report text."""

    def __init__(self, clipboard=None):
        self._clipboard = clipboard or copy_windows_text

    def copy_report(self, text: str, owner_window: int) -> ActionOutcome:
        try:
            self._clipboard(text, owner_window)
            return ActionOutcome(True, "Diagnostic details copied.")
        except Exception:  # noqa: BLE001 -- native clipboard contention is nonfatal.
            return ActionOutcome(
                False,
                "Diagnostic details could not be copied. Try again when the clipboard is available.",
            )

    def save_report(self, text: str, destination: Path | str) -> ActionOutcome:
        destination = Path(destination)
        temporary = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                delete=False,
                dir=destination.parent,
                prefix=".brz2obsidian-report-",
                suffix=".tmp",
            ) as stream:
                temporary = Path(stream.name)
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            return ActionOutcome(True, "Diagnostic report saved.")
        except Exception:  # noqa: BLE001 -- an outer export failure must not lose the result.
            return ActionOutcome(
                False,
                "The diagnostic report could not be saved. Choose a writable local file and try again.",
            )
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def copy_windows_text(text: str, owner_window: int) -> None:
    """Copy eager Unicode data using a GUI-captured HWND, without Qt access.

    Microsoft requires a non-NULL owner when EmptyClipboard precedes
    SetClipboardData. Successful SetClipboardData transfers global memory
    ownership to Windows. No retry or delayed rendering is introduced.
    https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setclipboarddata
    """
    if os.name != "nt" or not owner_window:
        raise OSError("A Windows clipboard owner is required")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    # Allocate/encode before opening to keep clipboard ownership brief.
    data = (text + "\0").encode("utf-16-le")
    handle = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    opened = False
    transferred = False
    try:
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            ctypes.memmove(pointer, data, len(data))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.OpenClipboard(owner_window):
            raise ctypes.WinError(ctypes.get_last_error())
        opened = True
        if not user32.EmptyClipboard() or not user32.SetClipboardData(13, handle):
            raise ctypes.WinError(ctypes.get_last_error())
        transferred = True
    finally:
        if opened:
            user32.CloseClipboard()
        if not transferred:
            kernel32.GlobalFree(handle)
