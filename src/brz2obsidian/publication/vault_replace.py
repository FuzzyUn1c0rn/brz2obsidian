"""Ordinary same-volume Windows file transition with retained ACL facts."""

import ctypes
import os
import shutil
import stat
from ctypes import wintypes
from pathlib import Path

from brz2obsidian.publication.vault_native import verify_directory


def supported_durable_volume(path):
    """The qualified ordinary publication profile is local fixed Windows NTFS."""
    if os.name != "nt":
        return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    volume_path = ctypes.create_unicode_buffer(32768)
    get_path = kernel.GetVolumePathNameW
    get_path.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    get_path.restype = wintypes.BOOL
    if not get_path(str(Path(path).absolute()), volume_path, len(volume_path)):
        return False
    drive_type = kernel.GetDriveTypeW
    drive_type.argtypes = [wintypes.LPCWSTR]
    drive_type.restype = wintypes.UINT
    if drive_type(volume_path.value) != 3:  # DRIVE_FIXED
        return False
    filesystem = ctypes.create_unicode_buffer(256)
    get_volume = kernel.GetVolumeInformationW
    get_volume.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR,
        wintypes.DWORD,
    ]
    get_volume.restype = wintypes.BOOL
    return bool(
        get_volume(
            volume_path.value,
            None,
            0,
            None,
            None,
            None,
            filesystem,
            len(filesystem),
        )
        and filesystem.value.upper() == "NTFS"
    )


def _ordinary_streams(path):
    class StreamData(ctypes.Structure):
        _fields_ = [("size", ctypes.c_longlong), ("name", ctypes.c_wchar * 296)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    first = kernel.FindFirstStreamW
    first.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_int,
        ctypes.POINTER(StreamData),
        wintypes.DWORD,
    ]
    first.restype = wintypes.HANDLE
    following = kernel.FindNextStreamW
    following.argtypes = [wintypes.HANDLE, ctypes.POINTER(StreamData)]
    following.restype = wintypes.BOOL
    kernel.FindClose.argtypes = [wintypes.HANDLE]
    data = StreamData()
    handle = first(str(path), 0, ctypes.byref(data), 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if data.name != "::$DATA" or following(handle, ctypes.byref(data)):
            raise OSError("Alternate file streams need separate qualification")
        if ctypes.get_last_error() != 38:  # ERROR_HANDLE_EOF
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.FindClose(handle)


def _windows_security(path, *, copy_to=None):
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    get = advapi.GetNamedSecurityInfoW
    get.argtypes = [wintypes.LPCWSTR, ctypes.c_int, wintypes.DWORD] + [
        ctypes.POINTER(ctypes.c_void_p)
    ] * 5
    get.restype = wintypes.DWORD
    set_info = advapi.SetNamedSecurityInfoW
    set_info.argtypes = [wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD] + [
        ctypes.c_void_p
    ] * 4
    set_info.restype = wintypes.DWORD
    to_sddl = advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
    to_sddl.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD),
    ]
    to_sddl.restype = wintypes.BOOL
    get_control = advapi.GetSecurityDescriptorControl
    get_control.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.WORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    get_control.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    owner, group, dacl, sacl, descriptor = (ctypes.c_void_p() for _ in range(5))
    code = get(
        str(path),
        1,
        7,
        ctypes.byref(owner),
        ctypes.byref(group),
        ctypes.byref(dacl),
        ctypes.byref(sacl),
        ctypes.byref(descriptor),
    )
    if code:
        raise OSError(code, "File security observation unavailable")
    text = ctypes.c_void_p()
    try:
        if not to_sddl(descriptor, 1, 7, ctypes.byref(text), None):
            raise ctypes.WinError(ctypes.get_last_error())
        control, revision = wintypes.WORD(), wintypes.DWORD()
        if not get_control(descriptor, ctypes.byref(control), ctypes.byref(revision)):
            raise ctypes.WinError(ctypes.get_last_error())
        observed = ctypes.wstring_at(text)
        if copy_to is not None:
            if _windows_security(copy_to) == observed:
                return observed
            protection = 0x80000000 if control.value & 0x1000 else 0x20000000
            code = set_info(str(copy_to), 1, 4 | protection, None, None, dacl, None)
            if code:
                raise OSError(code, "File DACL could not be retained")
            if _windows_security(copy_to) != observed:
                raise OSError("Replacement owner, group or DACL changed")
        return observed
    finally:
        if text:
            kernel.LocalFree(text)
        if descriptor:
            kernel.LocalFree(descriptor)


def stage_parent_security(root, stage_root, relative):
    """Give staged children the actual destination parent's ordinary DACL."""
    if os.name != "nt":
        raise OSError("Durable staged publication requires qualified Windows NTFS")
    verify_directory(root)
    verify_directory(stage_root)
    _windows_security(root, copy_to=stage_root)
    actual, staged = Path(root), Path(stage_root)
    for part in Path(relative).parts:
        if part == ".":
            continue
        actual, staged = actual / part, staged / part
        if not staged.exists():
            staged.mkdir()
        verify_directory(staged)
        if actual.exists():
            verify_directory(actual)
            _windows_security(actual, copy_to=staged)


def stage_directory_security(reference, staged):
    """Copy verified inherited security to the empty movable directory."""
    if os.name != "nt":
        raise OSError("Durable staged publication requires qualified Windows NTFS")
    verify_directory(reference)
    verify_directory(staged)
    _windows_security(reference, copy_to=staged)


def retained_metadata(path, *, copy_to=None):
    """Reject unsupported special attributes and preserve ordinary target security."""
    info = path.stat()
    mode = stat.S_IMODE(info.st_mode)
    attributes = getattr(info, "st_file_attributes", 0)
    if os.name == "nt":
        # Archive and normal attributes are the qualified ordinary file class.
        if attributes & ~(0x20 | 0x80):
            raise OSError("Special file attributes need separate qualification")
        _ordinary_streams(path)
        security = _windows_security(path, copy_to=copy_to)
    else:
        security = str(info.st_uid) + ":" + str(info.st_gid)
    if copy_to is not None:
        after = copy_to.stat()
        if (
            stat.S_IMODE(after.st_mode) != mode
            or getattr(after, "st_file_attributes", 0) != attributes
        ):
            raise OSError("Replacement mode or ordinary attributes changed")
    return mode, attributes, security


def retained_directory_metadata(path):
    """Observe the qualified ordinary directory attributes and ACL."""
    verify_directory(path)
    info = Path(path).stat()
    attributes = getattr(info, "st_file_attributes", 0)
    if os.name != "nt" or not attributes & 0x10 or attributes & ~(0x10 | 0x20 | 0x80):
        raise OSError("Directory metadata needs separate qualification")
    return stat.S_IMODE(info.st_mode), attributes, _windows_security(path)


def copy_stage(source, destination):
    """Copy a reviewed existing file to a separate same-volume stage."""
    if os.name == "nt":
        copy = ctypes.WinDLL("kernel32", use_last_error=True).CopyFileW
        copy.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.BOOL]
        copy.restype = wintypes.BOOL
        if not copy(str(source), str(destination), True):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        shutil.copy2(source, destination)
    retained_metadata(source, copy_to=destination)


def move_file(source, destination, *, replace):
    """Publish one staged file with Windows write-through namespace semantics."""
    if os.name == "nt":
        move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        move.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        move.restype = wintypes.BOOL
        if not move(str(source), str(destination), 8 | (1 if replace else 0)):
            raise ctypes.WinError(ctypes.get_last_error())
    elif replace:
        os.replace(source, destination)
    else:
        os.rename(source, destination)
