"""Owned staging, byte verification and fresh-destination publication."""

import hashlib
import os
import shutil
import stat
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath

from brz2obsidian.contracts import (
    Issue,
    MigrationFailed,
    MigrationRefused,
    Receipt,
    RenderedVault,
    SourceSession,
    VerifiedFile,
)


def _issue(code, message, leftover=None):
    return Issue(
        code=code,
        phase="publication",
        message=message,
        guidance="Use an absent or empty destination with a shorter path and check filesystem access.",
        leftover_path=leftover,
    )


def _fresh(destination):
    _safe_ancestors(destination)
    if destination.exists() and (
        not destination.is_dir() or any(destination.iterdir())
    ):
        raise MigrationRefused(
            (_issue("destination_not_empty", "Destination must be absent or empty"),)
        )


def _reparse(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _safe_ancestors(path):
    for ancestor in (path, *path.parents):
        if os.path.lexists(ancestor) and _reparse(ancestor):
            raise MigrationRefused(
                (_issue("unsafe_target_path", f"Reparse path is unsafe: {ancestor}"),)
            )


def _staged_files(staging):
    files = set()
    for root, directories, names in os.walk(staging, followlinks=False):
        for name in (*directories, *names):
            path = Path(root) / name
            if _reparse(path):
                raise MigrationRefused(
                    (
                        _issue(
                            "unsafe_target_path",
                            f"Staging contains a reparse path: {path}",
                        ),
                    )
                )
            if name in names:
                if not path.is_file():
                    raise MigrationFailed(
                        (
                            _issue(
                                "payload_integrity_failure",
                                "Staging contains an unexpected file type",
                            ),
                        )
                    )
                files.add(path.relative_to(staging).as_posix())
    return files


def publish(
    artifacts: RenderedVault, payloads: SourceSession, destination: object
) -> Receipt:
    destination = Path(destination).absolute()
    staging = None
    try:
        _fresh(destination)
        if (
            artifacts.source_identity != payloads.source_identity
            or payloads.source_identity != payloads.snapshot.identity
        ):
            raise MigrationRefused(
                (
                    _issue(
                        "source_changed",
                        "Artifacts are bound to a different source session",
                    ),
                )
            )
        payloads.verify_consistency()
        manifest = artifacts.manifest
        actual_paths = tuple(
            file.relative_path for file in artifacts.generated_files
        ) + tuple(copy.relative_path for copy in artifacts.copies)
        assigned_paths = manifest + artifacts.reserved_paths
        normalized = {
            unicodedata.normalize("NFC", path).casefold() for path in assigned_paths
        }
        if manifest != actual_paths or len(normalized) != len(assigned_paths):
            raise MigrationRefused(
                (_issue("unsafe_target_path", "Manifest paths are missing or collide"),)
            )
        for path in assigned_paths:
            parts = PurePosixPath(path)
            if (
                parts.is_absolute()
                or not parts.parts
                or ".." in parts.parts
                or "\\" in path
                or ":" in path
                or parts.as_posix() != path
                or any(
                    part.endswith((".", " "))
                    or any(ord(char) < 32 or char in '<>"|?*' for char in part)
                    or part.split(".")[0].upper()
                    in {
                        "CON",
                        "PRN",
                        "AUX",
                        "NUL",
                        *(f"COM{i}" for i in range(1, 10)),
                        *(f"LPT{i}" for i in range(1, 10)),
                    }
                    for part in parts.parts
                )
                or any(
                    "/".join(
                        unicodedata.normalize("NFC", part).casefold()
                        for part in parts.parts[:i]
                    )
                    in normalized
                    for i in range(1, len(parts.parts))
                )
            ):
                raise MigrationRefused(
                    (_issue("unsafe_target_path", "Target path is unsafe"),)
                )
            if len(str(destination / path).encode("utf-16-le")) // 2 > 240:
                raise MigrationRefused(
                    (
                        _issue(
                            "target_path_too_long",
                            "Target exceeds the 240-unit absolute-path limit",
                        ),
                    )
                )
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix=".brz2obsidian-", dir=destination.parent)
        ).absolute()
        _safe_ancestors(staging)
        owned_identity = (staging.stat().st_dev, staging.stat().st_ino)
        expected = {}
        for artifact in artifacts.generated_files:
            path = staging / artifact.relative_path
            _safe_ancestors(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            _safe_ancestors(path)
            with path.open("xb") as target:
                target.write(artifact.content)
            expected[artifact.relative_path] = (len(artifact.content), artifact.sha256)
        for copy in artifacts.copies:
            path = staging / copy.relative_path
            _safe_ancestors(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with payloads.open_payload(copy.asset_id) as source:
                _safe_ancestors(path)
                with path.open("xb") as target:
                    shutil.copyfileobj(source, target, 1024 * 1024)
            expected[copy.relative_path] = (copy.expected_length, copy.expected_sha256)
        payloads.verify_consistency()
        _safe_ancestors(staging)
        actual = _staged_files(staging)
        if actual != set(manifest):
            raise MigrationFailed(
                (
                    _issue(
                        "payload_integrity_failure",
                        "Staged files differ from the complete manifest",
                    ),
                )
            )
        verified = []
        for relative_path in manifest:
            path = staging / relative_path
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            length = path.stat().st_size
            if (length, digest) != expected[relative_path]:
                raise MigrationFailed(
                    (
                        _issue(
                            "payload_integrity_failure",
                            "Staged content failed length/hash verification",
                        ),
                    )
                )
            verified.append(
                VerifiedFile(relative_path=relative_path, length=length, sha256=digest)
            )
        counts = artifacts.counts.model_copy(
            update={
                "actual_notes": artifacts.counts.planned_notes,
                "actual_assets": len(artifacts.copies),
                "actual_files": len(manifest),
            }
        )
        receipt = Receipt(
            destination=str(destination),
            source_identity=artifacts.source_identity,
            manifest=tuple(verified),
            counts=counts,
        )
        payloads.verify_consistency()
        if _staged_files(staging) != set(manifest):
            raise MigrationFailed(
                (
                    _issue(
                        "payload_integrity_failure",
                        "Staged files changed before commit",
                    ),
                )
            )
        _fresh(destination)
        try:
            if destination.exists():
                destination.rmdir()
            # Native Windows rename refuses any existing destination. Removing
            # an empty directory cannot remove a late file (rmdir then fails).
            staging.rename(destination)
        except OSError:
            _fresh(destination)
            raise
        staging = None
        return receipt
    except (MigrationFailed, MigrationRefused) as error:
        issues = error.issues
        error_type = type(error)
    except OSError as error:
        issues = (_issue("write_failure", str(error)),)
        error_type = MigrationFailed
    except BaseException as error:  # noqa: BLE001 - cleanup, then re-raise unchanged
        unexpected = error
        issues = ()
        error_type = None
    if staging is not None:
        try:
            # Only this freshly created sibling staging directory is owned.
            if (
                staging.parent != destination.parent.resolve()
                or not staging.name.startswith(".brz2obsidian-")
                or staging.resolve() != staging
                or (staging.stat().st_dev, staging.stat().st_ino) != owned_identity
            ):
                raise OSError("Cannot establish owned staging containment")
            _safe_ancestors(staging)
            _staged_files(staging)
            shutil.rmtree(staging)
        except (OSError, MigrationRefused, MigrationFailed) as error:
            issues += (_issue("cleanup_failure", str(error), str(staging)),)
    if error_type is None:
        for issue in issues:
            unexpected.add_note(
                f"{issue.code}: {issue.message}; owned leftover: {issue.leftover_path}"
            )
        raise unexpected
    raise error_type(issues)


class FilesystemPublisher:
    publish = staticmethod(publish)
