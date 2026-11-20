"""Keep Windows pipe waits outside native reads during extension loading."""

import io
import os
import stat
import time


class _PollingPipe(io.RawIOBase):
    def __init__(self, descriptor):
        self._descriptor = descriptor

    def readable(self):
        return True

    def readinto(self, buffer):
        while True:
            try:
                data = os.read(self._descriptor, len(buffer))
            except BlockingIOError:
                time.sleep(0.01)
                continue
            buffer[: len(data)] = data
            return len(data)


def worker_input(stream):
    """Select input before any buffered read, preserving normal frame handling."""
    if os.name != "nt":
        return stream
    try:
        descriptor = stream.fileno()
    except AttributeError, io.UnsupportedOperation:
        return stream
    if not stat.S_ISFIFO(os.fstat(descriptor).st_mode):
        return stream
    os.set_blocking(descriptor, False)
    return io.BufferedReader(_PollingPipe(descriptor))
