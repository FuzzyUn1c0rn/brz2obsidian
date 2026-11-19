"""Native read observations: no creation, replacement, truncation or ACL changes."""

import ctypes
import hashlib
import os
import stat
from contextlib import closing, contextmanager
from pathlib import Path


def _windows_bindings():
    """Initialize shared API prototypes before concurrent native observations."""
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetFinalPathNameByHandleW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    kernel.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.DuplicateHandle.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    security.GetSecurityInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    security.GetSecurityInfo.restype = wintypes.DWORD
    security.IsValidSid.argtypes = [ctypes.c_void_p]
    security.GetLengthSid.argtypes = [ctypes.c_void_p]
    security.GetLengthSid.restype = wintypes.DWORD
    return kernel, security


# Only API bindings are shared. Handles, buffers, security descriptors and every
# filesystem/permission observation remain local to their individual calls.
_WINDOWS_BINDINGS = _windows_bindings() if os.name == "nt" else None


def available_memory():
    """Current available commit capacity, without reserving future capacity."""
    if os.name == "nt":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong)
                for name in (
                    "total_physical",
                    "available_physical",
                    "total_page",
                    "available_page",
                    "total_virtual",
                    "available_virtual",
                    "extended",
                )
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
        kernel.GlobalMemoryStatusEx.restype = ctypes.c_int
        if not kernel.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ctypes.WinError(ctypes.get_last_error())
        return status.available_page
    try:
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, AttributeError) as error:
        raise OSError("Available review memory cannot be established") from error


def _physical(info):
    return not stat.S_ISLNK(info.st_mode) and not (
        getattr(info, "st_file_attributes", 0) & 0x400
    )


@contextmanager
def _handle(path, *, directory=False, write=False):
    """Open the named object itself, with maximal compatible sharing."""
    kernel, security = _WINDOWS_BINDINGS
    rights = 0x80 | 0x20000 | (1 if directory else 0)  # list, metadata and security
    rights |= (0x2 | 0x4 | 0x40) if directory and write else 0
    if not directory:
        rights |= 0x80000000 | (0x40000000 if write else 0)
    handle = kernel.CreateFileW(
        str(path),
        rights,
        7,
        None,
        3,
        0x00200000 | (0x02000000 if directory else 0),
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        output = ctypes.create_unicode_buffer(32768)
        count = kernel.GetFinalPathNameByHandleW(handle, output, len(output), 0)
        if not count or count >= len(output):
            raise OSError("Resolved handle path unavailable")
        actual = output.value
        if actual.startswith("\\\\?\\UNC\\"):
            actual = "\\\\" + actual[8:]
        elif actual.startswith("\\\\?\\"):
            actual = actual[4:]
        if os.path.normcase(os.path.abspath(actual)) != os.path.normcase(
            os.path.abspath(path)
        ):
            raise OSError("Physical handle path does not match the observed name")
        # Native security descriptor availability establishes owner facts. Access
        # itself is decided by Windows for the actual process token; ownership
        # need not equal the current user (groups/system owners are legitimate).
        descriptor = ctypes.c_void_p()
        owner = ctypes.c_void_p()
        code = security.GetSecurityInfo(
            handle,
            1,
            1,
            ctypes.byref(owner),
            None,
            None,
            None,
            ctypes.byref(descriptor),
        )
        if code:
            raise OSError("Owner/security descriptor observation unavailable")
        try:
            if not owner.value or not security.IsValidSid(owner):
                raise OSError("Owner identity unavailable")
            owner_digest = hashlib.sha256(
                ctypes.string_at(owner, security.GetLengthSid(owner))
            ).hexdigest()
        finally:
            kernel.LocalFree(descriptor)
        yield handle, owner_digest
    finally:
        kernel.CloseHandle(handle)


def verify_directory(path, *, writable=False):
    """Observe physical directory identity, access and owner without creating files."""
    path = Path(path).absolute()
    before = path.lstat()
    if not _physical(before) or not stat.S_ISDIR(before.st_mode):
        raise OSError("Directory is not physical")
    if os.name == "nt":
        with _handle(path, directory=True, write=writable) as (_, owner):
            after = path.lstat()
    else:
        if not os.access(path, os.R_OK | os.X_OK | (os.W_OK if writable else 0)):
            raise PermissionError("Directory access unavailable")
        owner = str(before.st_uid)
        after = path.lstat()
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise OSError("Directory identity changed")
    return f"{before.st_dev}:{before.st_ino}:{owner}"


def _observed_chunks(
    root,
    path,
    *,
    writable=False,
    expected_size=None,
    read_chunk_limit=1024 * 1024,
    owned_identity=None,
):
    """Internal traversal; its return value exists only after verified EOF."""
    if (
        expected_size is not None
        and (type(expected_size) is not int or not 0 <= expected_size < 1 << 63)
        or type(read_chunk_limit) is not int
        or not 1 <= read_chunk_limit <= 1024 * 1024
    ):
        raise OSError("Invalid bounded native read")

    def blocks(stream):
        if expected_size is None:
            while block := stream.read(read_chunk_limit):
                yield block
        else:
            remaining = expected_size
            while remaining:
                request = min(read_chunk_limit, remaining)
                block = stream.read(request)
                if len(block) != request:
                    raise OSError("Short bounded native read")
                remaining -= request
                yield block
            if stream.read(1):
                raise OSError("Expected content has trailing bytes")

    root, path = Path(root).absolute(), Path(path).absolute()
    path.relative_to(root)
    if owned_identity is not None and path.parent != root:
        raise OSError("Owned backing is outside its scratch directory")
    ancestors = []
    parent = path.parent
    while True:
        identity = verify_directory(parent)
        ancestors.append((parent, identity))
        if parent == root:
            if owned_identity is not None and identity != owned_identity[0]:
                raise OSError("Content scratch identity changed")
            break
        parent = parent.parent
    before = path.lstat()
    if (
        owned_identity is not None
        and (before.st_dev, before.st_ino) != owned_identity[1]
    ):
        raise OSError("Owned backing identity changed")
    values = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)

    def check_opened(opened):
        if expected_size is not None and values(opened) != values(before):
            raise OSError("Opened file identity/size differs before reading")

    if (
        not _physical(before)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
    ):
        raise OSError("File is not an independent physical file")
    if expected_size is not None and before.st_size != expected_size:
        raise OSError("File size differs from expected content before reading")
    content = hashlib.sha256()
    buffering = -1 if expected_size is None else 0
    if os.name == "nt":
        import msvcrt

        with _handle(path, write=writable) as (handle, owner):
            # Duplicate the verified handle before transferring it to Python.
            from ctypes import wintypes

            kernel, _ = _WINDOWS_BINDINGS
            duplicate = wintypes.HANDLE()
            process = kernel.GetCurrentProcess()
            if not kernel.DuplicateHandle(
                process, handle, process, ctypes.byref(duplicate), 0, False, 2
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            fd = msvcrt.open_osfhandle(duplicate.value, os.O_RDONLY | os.O_BINARY)
            with os.fdopen(fd, "rb", buffering=buffering) as stream:
                opened = os.fstat(stream.fileno())
                check_opened(opened)
                for block in blocks(stream):
                    content.update(block)
                    yield block
                finished = os.fstat(stream.fileno())
    else:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb", buffering=buffering) as stream:
            opened = os.fstat(stream.fileno())
            check_opened(opened)
            for block in blocks(stream):
                content.update(block)
                yield block
            finished = os.fstat(stream.fileno())
        owner = str(opened.st_uid)
    after = path.lstat()
    if any(values(s) != values(before) for s in (opened, finished, after)):
        raise OSError("File identity/content changed during observation")
    if any(verify_directory(parent) != identity for parent, identity in ancestors):
        raise OSError("Ancestor identity changed during observation")
    return after, content.hexdigest(), f"{after.st_dev}:{after.st_ino}:{owner}"


def observe_file(
    root,
    path,
    *,
    writable=False,
    prefix_limit=1024,
    sink=None,
    expected_size=None,
    read_chunk_limit=1024 * 1024,
):
    """Hash verified file bytes; optional bounded reads use unbuffered OS IO."""
    prefix = b""
    with closing(
        _observed_chunks(
            root,
            path,
            writable=writable,
            expected_size=expected_size,
            read_chunk_limit=read_chunk_limit,
        )
    ) as chunks:
        while True:
            try:
                block = next(chunks)
            except StopIteration as complete:
                info, digest, identity = complete.value
                return info, digest, prefix, identity
            if sink is not None and sink.write(block) != len(block):
                raise OSError("Incomplete captured file bytes")
            if len(prefix) < prefix_limit:
                prefix += block[: prefix_limit - len(prefix)]
