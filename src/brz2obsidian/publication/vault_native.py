"""Native read observations: no creation, replacement, truncation or ACL changes."""

import ctypes
import hashlib
import io
import os
import stat
from contextlib import closing, contextmanager
from pathlib import Path

FILE_LIST_DIRECTORY = 0x0001
FILE_ADD_FILE = 0x0002
FILE_ADD_SUBDIRECTORY = 0x0004
FILE_DELETE_CHILD = 0x0040
FILE_READ_ATTRIBUTES = 0x0080
READ_CONTROL = 0x00020000
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000

FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_NAME_NORMALIZED = 0x0
VOLUME_NAME_DOS = 0x0
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

SE_FILE_OBJECT = 1
OWNER_SECURITY_INFORMATION = 0x00000001
DUPLICATE_SAME_ACCESS = 0x00000002


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
    kernel.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
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
_FILE_ID_INFO_CLASS = 18


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
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


@contextmanager
def _handle(path, *, directory=False, write=False):
    """Open the named object itself, with maximal compatible sharing."""
    kernel, security = _WINDOWS_BINDINGS
    rights = (
        FILE_READ_ATTRIBUTES | READ_CONTROL | (FILE_LIST_DIRECTORY if directory else 0)
    )
    rights |= (
        (FILE_ADD_FILE | FILE_ADD_SUBDIRECTORY | FILE_DELETE_CHILD)
        if directory and write
        else 0
    )
    if not directory:
        rights |= GENERIC_READ | (GENERIC_WRITE if write else 0)
    handle = kernel.CreateFileW(
        str(path),
        rights,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None,
        OPEN_EXISTING,
        FILE_FLAG_OPEN_REPARSE_POINT | (FILE_FLAG_BACKUP_SEMANTICS if directory else 0),
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        output = ctypes.create_unicode_buffer(32768)
        count = kernel.GetFinalPathNameByHandleW(
            handle, output, len(output), FILE_NAME_NORMALIZED | VOLUME_NAME_DOS
        )
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
            SE_FILE_OBJECT,
            OWNER_SECURITY_INFORMATION,
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


class _FileIdInfo(ctypes.Structure):
    _fields_ = [
        ("volume_serial", ctypes.c_uint64),
        ("file_id", ctypes.c_ubyte * 16),
    ]


def _check_owned_directory(path, anchor):
    """Recheck a scratch anchor using the opened directory's own identity."""
    if os.name == "nt":
        kernel, _ = _WINDOWS_BINDINGS
        with _handle(path, directory=True) as (handle, owner):
            identity = _FileIdInfo()
            if kernel.GetFileInformationByHandleEx(
                handle,
                _FILE_ID_INFO_CLASS,
                ctypes.byref(identity),
                ctypes.sizeof(identity),
            ):
                file_id = int.from_bytes(identity.file_id, "little")
                if file_id:
                    current = path.lstat()
                    if (
                        not _physical(current)
                        or not stat.S_ISDIR(current.st_mode)
                        or (current.st_dev, current.st_ino)
                        != (identity.volume_serial, file_id)
                        or f"{identity.volume_serial}:{file_id}:{owner}" != anchor
                    ):
                        raise OSError("Content scratch identity changed")
                    return
    if verify_directory(path) != anchor:
        raise OSError("Content scratch identity changed")


def _read_observation_blocks(stream, expected_size, read_chunk_limit):
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


def _observation_ancestors(root, path, owned_identity):
    ancestors = []
    if owned_identity is None:
        parent = path.parent
        while True:
            ancestors.append((parent, verify_directory(parent)))
            if parent == root:
                break
            parent = parent.parent
    else:
        if path.parent != root:
            raise OSError("Owned backing is outside its scratch directory")
        _check_owned_directory(root, owned_identity[0])
    return ancestors


@contextmanager
def _observation_stream(path, writable, buffering):
    if os.name == "nt":
        import msvcrt

        with _handle(path, write=writable) as (handle, owner):
            from ctypes import wintypes

            kernel, _ = _WINDOWS_BINDINGS
            duplicate = wintypes.HANDLE()
            process = kernel.GetCurrentProcess()
            if not kernel.DuplicateHandle(
                process,
                handle,
                process,
                ctypes.byref(duplicate),
                0,
                False,
                DUPLICATE_SAME_ACCESS,
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            fd = msvcrt.open_osfhandle(duplicate.value, os.O_RDONLY | os.O_BINARY)
            with os.fdopen(fd, "rb", buffering=buffering) as stream:
                yield stream, owner
    else:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb", buffering=buffering) as stream:
            yield stream, None


def _observation_file_stat(path, owned_identity, expected_size):
    before = path.lstat()
    if (
        owned_identity is not None
        and (before.st_dev, before.st_ino) != owned_identity[1]
    ):
        raise OSError("Owned backing identity changed")
    if (
        not _physical(before)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
    ):
        raise OSError("File is not an independent physical file")
    if expected_size is not None and before.st_size != expected_size:
        raise OSError("File size differs from expected content before reading")
    return before


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

    root, path = Path(root).absolute(), Path(path).absolute()
    path.relative_to(root)
    ancestors = _observation_ancestors(root, path, owned_identity)
    before = _observation_file_stat(path, owned_identity, expected_size)
    values = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)

    def check_opened(opened):
        if expected_size is not None and values(opened) != values(before):
            raise OSError("Opened file identity/size differs before reading")

    content = hashlib.sha256()
    buffering = -1 if expected_size is None else 0
    with _observation_stream(path, writable, buffering) as (stream, owner):
        opened = os.fstat(stream.fileno())
        check_opened(opened)
        for block in _read_observation_blocks(stream, expected_size, read_chunk_limit):
            content.update(block)
            yield block
        finished = os.fstat(stream.fileno())
    if owner is None:
        owner = str(opened.st_uid)
    after = path.lstat()
    if any(values(s) != values(before) for s in (opened, finished, after)):
        raise OSError("File identity/content changed during observation")
    if any(verify_directory(parent) != identity for parent, identity in ancestors):
        raise OSError("Ancestor identity changed during observation")
    if owned_identity is not None:
        _check_owned_directory(root, owned_identity[0])
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


def read_observed_payload(root, rows):
    if sum(row.size for row in rows) > available_memory() // 4:
        raise ValueError("comparison_resources_unavailable")
    result = {}
    for row in rows:
        sink = io.BytesIO()
        info, digest, _, physical_identity = observe_file(
            root, Path(root) / row.path, prefix_limit=0, sink=sink
        )
        if (info.st_size, digest) != (row.size, row.sha256):
            raise ValueError("observed_payload_changed")
        mode = "100755" if os.name != "nt" and info.st_mode & stat.S_IXUSR else "100644"
        if (
            getattr(row, "mode", mode) != mode
            or getattr(row, "identity", physical_identity) != physical_identity
        ):
            raise ValueError("observed_identity_changed")
        result[row.path] = sink.getvalue()
    return result
