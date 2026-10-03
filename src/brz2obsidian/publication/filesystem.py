"""Owned staging, byte verification and fresh-destination publication."""

import hashlib
import shutil
import tempfile
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
    if destination.exists() and (
        not destination.is_dir() or any(destination.iterdir())
    ):
        raise MigrationRefused(
            (_issue("destination_not_empty", "Destination must be absent or empty"),)
        )


def publish(
    artifacts: RenderedVault, payloads: SourceSession, destination: object
) -> Receipt:
    destination = Path(destination).absolute()
    staging = None
    try:
        _fresh(destination)
        if artifacts.source_identity != payloads.source_identity:
            raise MigrationRefused(
                (
                    _issue(
                        "source_changed",
                        "Artifacts are bound to a different source session",
                    ),
                )
            )
        manifest = artifacts.manifest
        actual_paths = tuple(
            file.relative_path for file in artifacts.generated_files
        ) + tuple(copy.relative_path for copy in artifacts.copies)
        if manifest != actual_paths or len(
            {path.casefold() for path in manifest}
        ) != len(manifest):
            raise MigrationRefused(
                (_issue("unsafe_target_path", "Manifest paths are missing or collide"),)
            )
        for path in manifest:
            parts = PurePosixPath(path)
            if (
                parts.is_absolute()
                or not parts.parts
                or ".." in parts.parts
                or "\\" in path
                or ":" in path
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
        ).resolve()
        expected = {}
        for artifact in artifacts.generated_files:
            path = staging / artifact.relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(artifact.content)
            expected[artifact.relative_path] = (len(artifact.content), artifact.sha256)
        for copy in artifacts.copies:
            path = staging / copy.relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            with (
                payloads.open_payload(copy.asset_id) as source,
                path.open("wb") as target,
            ):
                shutil.copyfileobj(source, target, 1024 * 1024)
            expected[copy.relative_path] = (copy.expected_length, copy.expected_sha256)
        actual = {
            path.relative_to(staging).as_posix()
            for path in staging.rglob("*")
            if path.is_file()
        }
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
        payloads.verify_consistency()
        _fresh(destination)
        if destination.exists():
            destination.rmdir()
        staging.rename(destination)
        staging = None
        counts = artifacts.counts.model_copy(
            update={
                "actual_notes": artifacts.counts.planned_notes,
                "actual_assets": len(artifacts.copies),
                "actual_files": len(manifest),
            }
        )
        return Receipt(
            destination=str(destination),
            source_identity=artifacts.source_identity,
            manifest=tuple(verified),
            counts=counts,
        )
    except (MigrationFailed, MigrationRefused) as error:
        issues = error.issues
        error_type = type(error)
    except OSError as error:
        issues = (_issue("write_failure", str(error)),)
        error_type = MigrationFailed
    if staging is not None:
        try:
            # Only this freshly created sibling staging directory is owned.
            if (
                staging.parent != destination.parent.resolve()
                or not staging.name.startswith(".brz2obsidian-")
            ):
                raise OSError("Cannot establish owned staging containment")
            shutil.rmtree(staging)
        except OSError as error:
            issues += (_issue("cleanup_failure", str(error), str(staging)),)
    raise error_type(issues)


class FilesystemPublisher:
    publish = staticmethod(publish)
