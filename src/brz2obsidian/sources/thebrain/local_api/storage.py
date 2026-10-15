"""Owned acquisition staging checked at use and teardown."""

import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .errors import failure


def directory_identity(path):
    info = path.lstat()
    if (
        path.is_symlink()
        or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    ):
        raise OSError
    return info.st_dev, info.st_ino


class StagedPayload:
    def __init__(self, storage, name):
        self.storage, self.name = storage, name

    def open(self, mode):
        return self.storage.open(self.name, mode)


class AcquisitionStorage:
    def __init__(self, path):
        self.path = path
        self.identity = directory_identity(path)

    def verify(self):
        try:
            if directory_identity(self.path) != self.identity:
                raise OSError
        except OSError:
            raise failure(
                "api_capture_storage_changed",
                "The owned acquisition staging is no longer available safely",
            ) from None

    def payload(self, name):
        return StagedPayload(self, name)

    def open(self, name, mode):
        self.verify()
        return (self.path / name).open(mode)


@contextmanager
def acquisition_storage():
    path = Path(tempfile.mkdtemp(prefix="brz2obsidian-api-acquire-"))
    storage = AcquisitionStorage(path)
    try:
        yield storage
    finally:
        try:
            if directory_identity(path) != storage.identity:
                raise OSError
            shutil.rmtree(path)
        except OSError:
            raise failure(
                "api_capture_cleanup_failed",
                "The owned acquisition staging could not be cleaned safely",
            ) from None
