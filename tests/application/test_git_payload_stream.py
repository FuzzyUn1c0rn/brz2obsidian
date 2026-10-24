"""Raw Git payload protocol and owned process-lifetime boundaries."""

import ctypes
import hashlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

from brz2obsidian.publication.git_payload import verify_blobs

_PAYLOAD = b"\x00\xffliteral\r\n"
_OID = hashlib.sha1(
    b"blob " + str(len(_PAYLOAD)).encode() + b"\0" + _PAYLOAD, usedforsecurity=False
).hexdigest()
_SHA = hashlib.sha256(_PAYLOAD).hexdigest()


@pytest.mark.parametrize("fault", ("wrong_type", "extra_tail"))
def test_raw_batch_refuses_malformed_actual_process_stream(fault):
    with tempfile.TemporaryDirectory(prefix="brz2obsidian-272-raw-") as name:
        script = Path(name) / "git-stream.py"
        header = (
            f"{_OID} commit {len(_PAYLOAD)}\n"
            if fault == "wrong_type"
            else f"{_OID} blob {len(_PAYLOAD)}\n"
        ).encode()
        output = (
            header + _PAYLOAD + b"\n" + (b"extra" if fault == "extra_tail" else b"")
        )
        script.write_text(
            "import sys\n"
            + "assert sys.stdin.buffer.read() == "
            + repr((_OID + "\n").encode())
            + "\n"
            + "sys.stdout.buffer.write("
            + repr(output)
            + ")\n"
            + "sys.stdout.buffer.flush()\n",
            encoding="utf-8",
        )
        with pytest.raises(OSError):
            verify_blobs(
                [sys.executable, str(script)],
                env=os.environ.copy(),
                objects=((_OID, len(_PAYLOAD), _SHA, None),),
                timeout=3,
            )


@pytest.mark.skipif(os.name != "nt", reason="Windows job-child ownership")
def test_raw_batch_timeout_terminates_owned_descendant_process():
    with tempfile.TemporaryDirectory(prefix="brz2obsidian-272-raw-") as name:
        marker = Path(name) / "child.pid"
        script = Path(name) / "git-stall.py"
        script.write_text(
            "import pathlib, subprocess, sys, time\n"
            + "assert sys.stdin.buffer.read() == "
            + repr((_OID + "\n").encode())
            + "\n"
            + "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], creationflags=subprocess.CREATE_NO_WINDOW)\n"
            + "pathlib.Path("
            + repr(str(marker))
            + ").write_text(str(child.pid), encoding='ascii')\n"
            + "time.sleep(120)\n",
            encoding="utf-8",
        )
        with pytest.raises(OSError):
            verify_blobs(
                [sys.executable, str(script)],
                env=os.environ.copy(),
                objects=((_OID, len(_PAYLOAD), _SHA, None),),
                timeout=3,
            )
        assert marker.exists(), (
            "The owned descendant must have started before the timeout."
        )
        pid = int(marker.read_text(encoding="ascii"))
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
        kernel.WaitForSingleObject.restype = ctypes.c_ulong
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel.OpenProcess(0x00100000, 0, pid)
        if handle:
            try:
                assert kernel.WaitForSingleObject(handle, 2000) == 0
            finally:
                kernel.CloseHandle(handle)
