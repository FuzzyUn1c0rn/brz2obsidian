"""Private contained read inventory, refusing links and Windows reparse points."""

import os
import stat
from pathlib import Path

from .contracts import VaultCheckIssue


class UnsafePath(ValueError):
    pass


def reparse(info):
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def guard(path, root=None):
    if root is not None and not path.absolute().is_relative_to(root):
        raise UnsafePath("Path escapes the vault")
    # Check ancestors from the filesystem root before asking resolve to follow them.
    for component in (*reversed(path.parents), path):
        try:
            info = component.lstat()
        except FileNotFoundError:
            break
        if reparse(info):
            raise UnsafePath("Reparse paths cannot be read")
    if root is not None and not path.resolve().is_relative_to(root):
        raise UnsafePath("Physical path escapes the vault")


def read_failure(artifact=None):
    return VaultCheckIssue(
        code="read_failure",
        artifact=artifact,
        message="Vault directory or file could not be read completely.",
        guidance="Check the path, permissions and file encoding, then run the check again.",
    )


def unsafe_issue(artifact=None):
    return VaultCheckIssue(
        code="unsafe_reference",
        artifact=artifact,
        message="Vault contains a symbolic link, reparse point or unsafe file kind.",
        guidance="Use regular files and directories contained in the vault.",
    )


def inventory(root):
    files = []
    names = []
    issues = []
    complete = True

    def visit(directory):
        nonlocal complete
        try:
            guard(directory, root)
            with os.scandir(directory) as entries:
                paths = sorted(
                    (Path(entry.path) for entry in entries), key=lambda p: p.name
                )
        except UnsafePath:
            complete = False
            issues.append(unsafe_issue(directory.relative_to(root).as_posix()))
            return
        except OSError:
            complete = False
            issues.append(read_failure(directory.relative_to(root).as_posix()))
            return
        for path in paths:
            artifact = path.relative_to(root).as_posix()
            try:
                info = path.lstat()
                if reparse(info) or not (
                    stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)
                ):
                    names.append(artifact)
                    complete = False
                    issues.append(unsafe_issue(artifact))
                elif stat.S_ISDIR(info.st_mode):
                    visit(path)
                else:
                    files.append(path)
                    names.append(artifact)
            except OSError:
                complete = False
                issues.append(read_failure(artifact))

    visit(root)
    return sorted(files), tuple(sorted(names)), issues, complete


def read_text(path, root):
    guard(path, root)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise UnsafePath("Required read target is not a regular file")
    return path.read_text(encoding="utf-8-sig")
