"""Owned staging, byte verification and fresh-destination publication."""

import hashlib
import ntpath
import os
import shutil
import stat
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass
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


def _windows_component(part):
    """Shared Windows component predicate for generated paths and form names."""
    # ntpath also covers DOS devices with extensions/superscript digits and the
    # console device names, per the supported CPython Windows naming rules.
    return bool(part) and not (
        any(char in part for char in "/\\:")
        or part.endswith((".", " "))
        or ntpath.isreserved(part)
    )


def vault_name_error(vault_name: str) -> str | None:
    """Return concise feedback for an invalid single Windows folder name."""
    if not vault_name.strip():
        return "Enter a vault name."
    if vault_name.endswith("."):
        return "Remove the final dot."
    if vault_name.endswith(" "):
        return "Remove the space at the end."
    if any(ord(char) < 32 for char in vault_name):
        return "Remove hidden control characters."
    invalid_character = next(
        (char for char in vault_name if char in '<>:"/\\|?*'), None
    )
    if invalid_character is not None:
        return f"Remove “{invalid_character}” from the vault name."
    if ntpath.isreserved(vault_name):
        return f"“{vault_name}” is reserved. Choose another name."
    return None


@dataclass(frozen=True)
class DestinationError:
    code: str
    field: str
    message: str


@dataclass(frozen=True)
class DestinationPreflight:
    destination: Path | None
    errors: tuple[DestinationError, ...]
    checked: tuple[str, ...]
    failed: bool = False


def preflight_destination(parent: Path, vault_name: str) -> DestinationPreflight:
    """Read-only preliminary form check; does not reserve or promise writes.

    Existing-parent policy belongs only to this entry point. Publication keeps
    its established ability to create missing parents and validates final paths.
    """
    errors = []
    checked = ["vault_name_component", "parent_directory"]
    name_error = vault_name_error(vault_name)
    if name_error is not None or not _windows_component(vault_name):
        errors.append(
            DestinationError(
                "invalid_vault_name",
                "vault_name",
                name_error or "Enter a valid vault name.",
            )
        )
    if not parent.is_absolute():
        errors.append(
            DestinationError(
                "invalid_parent",
                "parent",
                "Choose a parent folder using its full path.",
            )
        )
    destination = parent / vault_name if not errors else None
    field = "parent"
    try:
        _safe_ancestors(parent)
        if not parent.is_dir():
            errors.append(
                DestinationError(
                    "parent_unavailable",
                    "parent",
                    "Choose an existing, readable parent folder.",
                )
            )
        if destination is not None:
            field = "destination"
            _fresh(destination)
            checked.extend(("reparse_ancestry", "destination_absent_or_empty"))
    except MigrationRefused as error:
        code = error.issues[0].code
        errors.append(
            DestinationError(
                code,
                field,
                "Choose a new or empty vault folder."
                if code == "destination_not_empty"
                else "Choose a folder without redirects.",
            )
        )
    except OSError:
        errors.append(
            DestinationError(
                "destination_read_failure",
                field,
                "Couldn’t check the destination. Choose it again.",
            )
        )
        return DestinationPreflight(destination, tuple(errors), tuple(checked), True)
    return DestinationPreflight(destination, tuple(errors), tuple(checked))


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


def _owned_staging(staging, destination, identity):
    if identity is None:
        raise OSError("Cannot establish owned staging identity")
    # Reject reparse ancestry before stat, inventory, reads or cleanup can follow it.
    _safe_ancestors(staging)
    info = staging.stat()
    if (
        staging.parent != destination.parent.resolve()
        or not staging.name.startswith(".brz2obsidian-")
        or staging.resolve() != staging
        or (info.st_dev, info.st_ino) != identity
    ):
        raise OSError("Cannot establish owned staging containment")


def _verify_retry_staging(staging, destination, identity, expected, payloads):
    _owned_staging(staging, destination, identity)
    payloads.verify_consistency()
    if _staged_files(staging) != set(expected):
        raise MigrationFailed(
            (_issue("payload_integrity_failure", "Staged files changed before retry"),)
        )
    for relative_path, expected_facts in expected.items():
        path = staging / relative_path
        _safe_ancestors(path)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if (path.stat().st_size, digest) != expected_facts:
            raise MigrationFailed(
                (
                    _issue(
                        "payload_integrity_failure",
                        "Staged content changed before retry",
                    ),
                )
            )
    _owned_staging(staging, destination, identity)
    if _staged_files(staging) != set(expected):
        raise MigrationFailed(
            (
                _issue(
                    "payload_integrity_failure",
                    "Staged files changed during retry verification",
                ),
            )
        )
    payloads.verify_consistency()
    _fresh(destination)


def publish(
    artifacts: RenderedVault, payloads: SourceSession, destination: object
) -> Receipt:
    destination = Path(destination).absolute()
    staging = None
    owned_identity = None
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
                or any(not _windows_component(part) for part in parts.parts)
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
        support_paths = tuple(a.relative_path for a in artifacts.support_artifacts)
        if (
            len(set(support_paths)) != len(support_paths)
            or not set(support_paths)
            <= {f.relative_path for f in artifacts.generated_files}
            or artifacts.counts.planned_support_files != len(support_paths)
        ):
            raise MigrationRefused(
                (
                    _issue(
                        "invalid_source",
                        "Support artifact obligations are inconsistent",
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
                "actual_category_notes": artifacts.counts.planned_category_notes,
                "actual_support_files": len(artifacts.support_artifacts),
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
        except OSError:
            _fresh(destination)
            raise
        # Remove an initially empty destination once only. A caller-created
        # destination during a delay must remain protected by native rename.
        delays = (0.01, 0.02, 0.04, 0.08, 0.16)
        for attempt in range(len(delays) + 1):
            try:
                # Native Windows rename refuses any existing destination.
                staging.rename(destination)
                break
            except OSError as error:
                _fresh(destination)
                if not (
                    sys.platform == "win32"
                    and isinstance(error, PermissionError)
                    and getattr(error, "winerror", None) == 5
                    and attempt < len(delays)
                ):
                    raise
                time.sleep(delays[attempt])
                _verify_retry_staging(
                    staging, destination, owned_identity, expected, payloads
                )
        staging = None
        return receipt
    except (MigrationFailed, MigrationRefused) as error:
        issues = error.issues
        error_type = type(error)
    except OSError:
        issues = (
            _issue("write_failure", "The vault could not be written or published."),
        )
        error_type = MigrationFailed
    except BaseException as error:  # noqa: BLE001 - cleanup, then re-raise unchanged
        unexpected = error
        issues = ()
        error_type = None
    if staging is not None:
        try:
            # Only this freshly created sibling staging directory is owned.
            _owned_staging(staging, destination, owned_identity)
            _staged_files(staging)
            shutil.rmtree(staging)
        except OSError, MigrationRefused, MigrationFailed:
            issues += (
                _issue(
                    "cleanup_failure",
                    "The temporary folder used to prepare the vault could not be removed.",
                    str(staging),
                ),
            )
    if error_type is None:
        for issue in issues:
            unexpected.add_note(
                f"{issue.code}: {issue.message}; owned leftover: {issue.leftover_path}"
            )
        raise unexpected
    raise error_type(issues)


class FilesystemPublisher:
    publish = staticmethod(publish)
