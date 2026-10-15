"""Owned acquisition staging with identity-checked teardown."""

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


@contextmanager
def acquisition_storage():
    path = Path(tempfile.mkdtemp(prefix="brz2obsidian-api-acquire-"))
    identity = directory_identity(path)
    try:
        yield path
    finally:
        try:
            if directory_identity(path) != identity:
                raise OSError
            shutil.rmtree(path)
        except OSError:
            raise failure(
                "api_capture_cleanup_failed",
                "The owned acquisition staging could not be cleaned safely",
            ) from None
