"""Stdio-only synthetic allocation controls; never read source or vault content."""

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes

MIB = 1024 * 1024


def emit(phase, **facts):
    print(json.dumps({"phase": phase, "pid": os.getpid(), **facts}), flush=True)


def barrier():
    if sys.stdin.readline() != "continue\n":
        raise RuntimeError("Observer did not release the allocation barrier")


class Allocation:
    """Explicit Windows committed pages, independent of Python's allocator."""

    def __init__(self, size):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.VirtualAlloc.argtypes = (
            ctypes.c_void_p,
            ctypes.c_size_t,
            wintypes.DWORD,
            wintypes.DWORD,
        )
        self.kernel.VirtualAlloc.restype = ctypes.c_void_p
        self.kernel.VirtualFree.argtypes = (
            ctypes.c_void_p,
            ctypes.c_size_t,
            wintypes.DWORD,
        )
        self.address = self.kernel.VirtualAlloc(None, size, 0x3000, 4)
        if not self.address:
            raise ctypes.WinError(ctypes.get_last_error())
        ctypes.memset(self.address, 0x5A, size)

    def release(self):
        if not self.kernel.VirtualFree(self.address, 0, 0x8000):
            raise ctypes.WinError(ctypes.get_last_error())
        self.address = None


def main(mode):
    if mode == "malformed":
        print("malformed calibration", flush=True)
        return
    if mode == "incomplete":
        return
    if mode == "overflow":
        sys.stdout.write("x" * 65536)
        sys.stdout.flush()
        return
    fake = mode in ("false-allocation", "false-descendant")
    if mode in ("descendant", "false-descendant"):
        emit("descendant-ready")
        barrier()
        held = None if fake else Allocation(16 * MIB)
        emit("descendant-held", requested_bytes=16 * MIB)
        barrier()
        if not fake:
            held.release()
            transient = Allocation(32 * MIB)
            transient.release()
        emit("descendant-released", short_allocation_released=True)
        return
    with subprocess.Popen(
        [sys.executable, __file__, "false-descendant" if fake else "descendant"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ) as child:
        ready = json.loads(child.stdout.readline())
        emit(
            "baseline",
            descendant_pid=-1 if mode == "missing-attribution" else ready["pid"],
        )
        barrier()
        held = None if fake else Allocation(8 * MIB)
        child.stdin.write("continue\n")
        child.stdin.flush()
        entered = json.loads(child.stdout.readline())
        emit("held", descendant_pid=entered["pid"], requested_bytes=24 * MIB)
        barrier()
        if mode == "timeout":
            time.sleep(60)
        child.stdin.write("continue\n")
        child.stdin.flush()
        released = json.loads(child.stdout.readline())
        if child.wait(timeout=5) != 0:
            raise RuntimeError("Calibration descendant failed")
    if not fake:
        held.release()
    extras = {}
    if mode == "nested-done":
        nested = []
        for _ in range(400):
            nested = [nested]
        extras["extra"] = nested
    emit(
        "done",
        requested_bytes=0 if mode == "invalid-done" else 56 * MIB,
        short_allocation_released=released["short_allocation_released"],
        **extras,
    )
    barrier()


if __name__ == "__main__":
    main(sys.argv[1])
