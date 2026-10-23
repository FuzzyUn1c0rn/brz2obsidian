"""Validate a supplied local history copy against target-owned evidence."""

import os
import shutil
import tempfile
import zlib
from pathlib import Path

from brz2obsidian.application.vault_repair_contracts import (
    DamagedHistoryObject,
    HistoryCopyValidation,
    HistoryRepairPreparation,
    HistoryRepairResult,
    MissingHistoryObject,
)
from brz2obsidian.publication.git_payload import verify_blobs
from brz2obsidian.publication.vault_admission import (
    _existing_git_operation_blockers,
    _exists,
    _Inspection,
    _safe_relative,
    _walk,
)
from brz2obsidian.publication.vault_apply import (
    _inspect_update_status,
    _operation_graph,
)
from brz2obsidian.publication.vault_history import (
    _damaged_loose_payload,
    _Git,
    _LooseBlobCheck,
    _quoted_paths,
    _read,
    _spool_oid,
    digest,
)
from brz2obsidian.publication.vault_native import observe_file, verify_directory
from brz2obsidian.publication.vault_replace import (
    copy_stage,
    move_file,
    retained_metadata,
)


def _snapshot(root):
    """Bind exact current vault/copy bytes and metadata between public calls."""
    rows = []
    known = set()
    for directory, names, files in _walk(root):
        base = Path(directory)
        relative_directory = base.relative_to(root).as_posix()
        rows.append(("directory", relative_directory, verify_directory(base)))
        for name in sorted((*names, *files)):
            path = base / name
            relative = path.relative_to(root).as_posix()
            folded = relative.casefold()
            safe = (
                relative == ".git"
                or relative.startswith(".git/")
                and _safe_relative(relative[len(".git/") :])
                or _safe_relative(relative)
            )
            if not safe or folded in known:
                raise OSError("Snapshot has an unsafe or repeated path")
            known.add(folded)
        for name in sorted(files):
            path = base / name
            info, sha, _, identity = observe_file(root, path, prefix_limit=0)
            rows.append(
                ("file", path.relative_to(root).as_posix(), info.st_size, sha, identity)
            )
    return digest(rows)


def _validation(
    status, code, *, target=None, copied=None, missing=(), damaged=(), message
):
    return HistoryCopyValidation(
        schema_id="brz2obsidian.history-copy-validation",
        schema_version=1,
        status=status,
        code=code,
        target_generation=target.locator.generation if target is not None else None,
        copy_generation=copied.locator.generation if copied is not None else None,
        target_commit=target.locator.commit if target is not None else None,
        copy_commit=copied.locator.commit if copied is not None else None,
        association_id=(
            target.locator.association.association_id if target is not None else None
        ),
        missing_objects=tuple(
            MissingHistoryObject(object_id=oid, size=size, sha256=sha)
            for oid, size, sha, _ in sorted(missing)
        ),
        damaged_objects=tuple(
            DamagedHistoryObject(object_id=oid, size=size, sha256=sha)
            for oid, size, sha, _ in sorted(damaged)
        ),
        message=message,
    )


def _supported_layout(root):
    """Reuse the ordinary local layout and Git policy gates before raw reads."""
    inspection = _Inspection(root, (), None)
    if not inspection.layout() or inspection.repo.kind != "root":
        return False
    locations = inspection.locations()
    if (
        locations is None
        or tuple(Path(path) for path in locations[:4])
        != (
            root,
            root / ".git",
            root / ".git",
            root / ".git/objects",
        )
        or locations[4:] != ["sha1", "files"]
    ):
        return False
    return inspection.configuration()


def _operation_blocker(root):
    """Use ordinary pre-existing owner and Git-operation blockers."""
    if _exists(root / ".git/brz2obsidian"):
        return "recovery_first"
    git_operation, foreign_lock = _existing_git_operation_blockers(root / ".git")
    if git_operation or foreign_lock:
        return "git_operation_busy"
    return None


def validate_history_copy(vault, copy):
    """Assess a complete supplied graph only under a local physical association."""
    root, supplied = Path(vault).absolute(), Path(copy).absolute()
    if (root / ".git").exists():
        try:
            if not _supported_layout(root):
                raise OSError("Unsupported target Git layout or policy")
        except OSError, ValueError, TypeError, UnicodeError:
            return _validation(
                "refused",
                "target_unsupported",
                message="Target Git layout or policy is unsupported for repair.",
            )
        try:
            blocker = _operation_blocker(root)
        except OSError, ValueError, TypeError, UnicodeError:
            return _validation(
                "unavailable",
                "operation_state_unavailable",
                message="Target operation and lock state could not be inspected.",
            )
        if blocker is not None:
            return _validation(
                "refused",
                blocker,
                message=(
                    "Resolve the converter operation before repairing history."
                    if blocker == "recovery_first"
                    else "Resolve the existing Git operation or lock before repair."
                ),
            )
    missing = []
    damaged = []
    linked_intents = []
    target_git = None
    try:
        target_git = _Git(root)
        target = _read(
            root,
            target_git,
            missing_payloads=missing,
            damaged_payloads=damaged,
            linked_intents=linked_intents,
        )
    except OSError, ValueError, TypeError, UnicodeError:
        target = None
    if (
        target is None
        or target.status not in ("valid", "refused")
        or (
            target.status == "refused"
            and target.code not in ("payloads_missing", "payloads_unavailable")
        )
    ):
        # A damaged local declaration is still evidence that a target history
        # was attempted.  It cannot authorize adopting the supplied copy, but
        # must not be reported as a pristine target with no anchor either.
        try:
            declared = (root / ".brz2obsidian").exists() or bool(
                target_git is not None
                and target_git.call(
                    "for-each-ref",
                    "--format=%(refname)",
                    "refs/brz2obsidian/imports/",
                ).strip()
            )
        except OSError, ValueError, TypeError, UnicodeError:
            declared = (root / ".brz2obsidian").exists()
        return _validation(
            "unavailable",
            "history_invalid" if declared else "no_independent_anchor",
            message=(
                "Target history is unreadable; the copy cannot supply its authority."
                if declared
                else "No validated target-owned history anchors this copy."
            ),
        )
    association = target.locator.association
    operation_prefix = (
        "refs/brz2obsidian/imports/" + association.association_id + "/operations/"
    )
    operation_refs = ()
    try:
        operation_refs = tuple(
            line
            for line in target_git.call(
                "for-each-ref",
                "--format=%(refname) %(objectname)",
                operation_prefix,
            )
            .decode("ascii")
            .splitlines()
            if line.startswith(operation_prefix)
        )
        if operation_refs and target.status == "valid":
            operation = _inspect_update_status(root, observations=[])
            if (
                operation.status
                not in ("applied", "no_content_change", "restored", "undone")
                or operation.recovery_required
            ):
                return _validation(
                    "refused",
                    "recovery_first",
                    target=target,
                    message="Retained operation history needs recovery first.",
                )
        elif operation_refs:
            for row in operation_refs:
                ref, oid = row.split(" ", 1)
                graph = _operation_graph(target_git, oid)
                if (
                    not ref.endswith("/" + graph.intent.operation_id)
                    or graph.intent.association_id != association.association_id
                    or graph.receipt is None
                ):
                    return _validation(
                        "refused",
                        "recovery_first",
                        target=target,
                        message="Retained operation history needs recovery first.",
                    )
        elif not operation_refs and linked_intents:
            return _validation(
                "unavailable",
                "operation_record_missing",
                target=target,
                message="Target operation authority is missing.",
            )
    except OSError, ValueError, TypeError, UnicodeError:
        return _validation(
            "unavailable",
            "operation_history_invalid",
            target=target,
            message="Target operation authority is unavailable.",
        )
    try:
        if association.vault_anchor != verify_directory(root) or (
            association.git_anchor != verify_directory(root / ".git")
        ):
            raise OSError("Target physical association changed")
        verify_directory(supplied)
        verify_directory(supplied / ".git")
        if not _supported_layout(supplied) or _operation_blocker(supplied):
            raise OSError("Supplied Git store is not self-contained")
        supplied_git = _Git(supplied)
        copied = _read(supplied, supplied_git, trusted_association=association)
        if copied.status == "valid":
            operation = _inspect_update_status(
                supplied, observations=[], trusted_association=association
            )
            if operation.code != "operation_absent" and (
                operation.status
                not in ("applied", "no_content_change", "restored", "undone")
                or operation.recovery_required
            ):
                raise OSError("Supplied copy has incomplete operation authority")
            copied_refs = tuple(
                line
                for line in supplied_git.call(
                    "for-each-ref",
                    "--format=%(refname) %(objectname)",
                    operation_prefix,
                )
                .decode("ascii")
                .splitlines()
                if line.startswith(operation_prefix)
            )
            if copied_refs != operation_refs or (
                operation_refs and operation.code == "operation_absent"
            ):
                return _validation(
                    "refused",
                    "copy_invalid",
                    target=target,
                    message="Supplied operation authority differs from the target.",
                )
            supplied_git.call("fsck", "--full", "--no-reflogs", "--no-progress")
    except OSError, ValueError, TypeError, UnicodeError:
        return _validation(
            "refused",
            "copy_invalid",
            target=target,
            message="Supplied copy is not a complete matching owned graph.",
        )
    if copied.status != "valid":
        return _validation(
            "refused",
            "copy_invalid",
            target=target,
            message="Supplied copy has no complete owned graph.",
        )
    if copied.locator.generation < target.locator.generation:
        return _validation(
            "refused",
            "newer_intact_history",
            target=target,
            copied=copied,
            message="Intact newer target history cannot be replaced by an older copy.",
        )
    if copied.locator.commit != target.locator.commit:
        return _validation(
            "refused",
            "different_intact_history",
            target=target,
            copied=copied,
            message="Intact target history differs from the supplied copy.",
        )
    return _validation(
        "matching",
        (
            "exact_unavailable_dependency"
            if missing and damaged
            else "exact_damaged_dependency"
            if damaged
            else "exact_missing_dependency"
            if missing
            else "same_intact_history"
        ),
        target=target,
        copied=copied,
        missing=missing,
        damaged=damaged,
        message="Supplied copy and intact target own the same complete history.",
    )


def prepare_history_repair(vault, copy, validation):
    """Bind a matching copy and the current target bytes before repair."""
    current = validate_history_copy(vault, copy)
    if current != validation:
        return HistoryRepairPreparation(
            schema_id="brz2obsidian.history-repair-preparation",
            schema_version=1,
            status="refused",
            code="stale_validation",
            validation=current,
            message="Target or copy validation changed; inspect again.",
        )
    if current.code not in (
        "exact_missing_dependency",
        "exact_damaged_dependency",
        "exact_unavailable_dependency",
    ):
        return HistoryRepairPreparation(
            schema_id="brz2obsidian.history-repair-preparation",
            schema_version=1,
            status="refused",
            code=current.code if current.status != "matching" else "no_repair_needed",
            validation=current,
            message="The target history has no unavailable repairable payload.",
        )
    root, supplied = Path(vault).absolute(), Path(copy).absolute()
    try:
        target_anchor = verify_directory(root)
        target_git_anchor = verify_directory(root / ".git")
        copy_anchor = verify_directory(supplied)
        copy_git_anchor = verify_directory(supplied / ".git")
        target_snapshot = _snapshot(root)
        copy_snapshot = _snapshot(supplied)
    except OSError, ValueError, TypeError, UnicodeError:
        return HistoryRepairPreparation(
            schema_id="brz2obsidian.history-repair-preparation",
            schema_version=1,
            status="unavailable",
            code="repair_context_unavailable",
            validation=current,
            message="Target or copy bytes could not be observed for repair.",
        )
    return HistoryRepairPreparation(
        schema_id="brz2obsidian.history-repair-preparation",
        schema_version=1,
        status="prepared",
        code=current.code,
        validation=current,
        target_anchor=target_anchor,
        target_git_anchor=target_git_anchor,
        copy_anchor=copy_anchor,
        copy_git_anchor=copy_git_anchor,
        target_snapshot=target_snapshot,
        copy_snapshot=copy_snapshot,
        message=current.message,
    )


def _stage_loose_blob(spool, staged, size):
    """Write the verified payload as a flushed ordinary loose Git blob."""
    compressor = zlib.compressobj()
    with spool.open("rb") as source, staged.open("wb") as sink:
        sink.write(compressor.compress(f"blob {size}\0".encode("ascii")))
        while block := source.read(1024 * 1024):
            sink.write(compressor.compress(block))
        sink.write(compressor.flush())
        sink.flush()
        os.fsync(sink.fileno())


def _discard_temporary(path, parent):
    """Remove only this call's contained diagnostic staging directory."""
    base = parent.resolve(strict=True)
    actual = path.resolve(strict=True)
    if actual.parent != base or not actual.name.startswith("brz2obsidian-repair-"):
        raise OSError("Repair temporary directory escaped its owned parent")
    shutil.rmtree(actual)


def execute_history_repair(vault, copy, preparation):
    """Retain exact unavailable payloads proven by the target's own root."""
    root, supplied = Path(vault).absolute(), Path(copy).absolute()

    def outcome(
        status,
        code,
        *,
        retained=False,
        storage="not_started",
        written=0,
        diagnostic=None,
        message,
    ):
        return HistoryRepairResult(
            schema_id="brz2obsidian.history-repair-result",
            schema_version=1,
            status=status,
            code=code,
            history_retained=retained,
            object_storage=storage,
            objects_written=written,
            authored_files_changed=False,
            diagnostic_path=diagnostic,
            message=message,
        )

    if not isinstance(preparation, HistoryRepairPreparation) or (
        preparation.status != "prepared"
    ):
        return outcome("refused", "not_prepared", message="No repair is prepared.")
    try:
        current = validate_history_copy(root, supplied)
        stale = current != preparation.validation or any(
            actual != expected
            for actual, expected in (
                (verify_directory(root), preparation.target_anchor),
                (verify_directory(root / ".git"), preparation.target_git_anchor),
                (verify_directory(supplied), preparation.copy_anchor),
                (verify_directory(supplied / ".git"), preparation.copy_git_anchor),
                (_snapshot(root), preparation.target_snapshot),
                (_snapshot(supplied), preparation.copy_snapshot),
            )
        )
    except OSError, ValueError, TypeError, UnicodeError:
        return outcome(
            "refused",
            "repair_context_unavailable",
            message="Target or copy proof could not be inspected.",
        )
    if stale:
        return outcome(
            "refused", "stale_repair", message="Target or copy proof changed."
        )
    rows = tuple(
        (row.object_id, row.size, row.sha256, False) for row in current.missing_objects
    ) + tuple(
        (row.object_id, row.size, row.sha256, True) for row in current.damaged_objects
    )
    total = sum(row[1] for row in rows)
    try:
        object_directory = root / ".git/objects"
        same_volume = os.stat(root.parent).st_dev == os.stat(object_directory).st_dev
        damaged_bytes = sum(
            (object_directory / oid[:2] / oid[2:]).lstat().st_size
            for oid, _, _, damaged in rows
            if damaged
        )
        margin = 64 * 1024 * 1024
        enough = (
            shutil.disk_usage(root.parent).free
            >= (2 * total + damaged_bytes if same_volume else total) + margin
            and shutil.disk_usage(object_directory).free >= total + margin
            and (same_volume or not current.damaged_objects)
        )
    except OSError:
        enough = False
    if not rows or not enough:
        return outcome(
            "refused",
            "repair_resources_unavailable",
            message="Repair space is unavailable.",
        )

    def complete():
        for oid, metadata in original_metadata.items():
            path = object_directory / oid[:2] / oid[2:]
            if retained_metadata(path) != metadata:
                return False
        after = _read(root, _Git(root))
        if after.status != "valid" or after.locator.commit != current.target_commit:
            return False
        operation = _inspect_update_status(root, observations=[])
        return operation.code == "operation_absent" or (
            operation.status in ("applied", "no_content_change", "restored", "undone")
            and not operation.recovery_required
        )

    attempted = False
    written = 0
    temporary = None
    keep_diagnostic = False
    original_metadata = {}
    try:
        target_git = _Git(root)
        supplied_git = _Git(supplied)
        temporary = Path(
            tempfile.mkdtemp(prefix="brz2obsidian-repair-", dir=root.parent)
        )
        for oid, size, sha, damaged in rows:
            spool = temporary / oid
            with spool.open("w+b") as sink:
                verify_blobs(
                    [*supplied_git.prefix, "cat-file", "--batch"],
                    env=supplied_git.env,
                    objects=((oid, size, sha, sink),),
                    timeout=120,
                )
                sink.flush()
            if _spool_oid(temporary, spool, size, sha) != oid:
                raise OSError("Copied history payload changed during repair")
            if damaged:
                destination = object_directory / oid[:2] / oid[2:]
                original_metadata[oid] = retained_metadata(destination)
                diagnostic = temporary / (oid + ".damaged")
                with diagnostic.open("xb") as sink:
                    observe_file(
                        object_directory, destination, sink=sink, prefix_limit=0
                    )
                    sink.flush()
                    os.fsync(sink.fileno())
                staged = temporary / (oid + ".staged")
                copy_stage(destination, staged)
                staged.chmod(original_metadata[oid][0] | 0o200)
                _stage_loose_blob(spool, staged, size)
                staged.chmod(original_metadata[oid][0])
                retained_metadata(destination, copy_to=staged)
                with staged.open("r+b") as sink:
                    os.fsync(sink.fileno())
                staged_proof = _LooseBlobCheck(oid, size, sha)
                observe_file(temporary, staged, sink=staged_proof, prefix_limit=0)
                if not staged_proof.valid():
                    raise OSError("Staged Git blob does not match the copy")
                if not _damaged_loose_payload(root, (oid, size, sha, None)):
                    raise OSError("Damaged loose object changed before replacement")
                attempted = True
                move_file(staged, destination, replace=True)
                actual = oid
            else:
                attempted = True
                actual = (
                    target_git.call(
                        "hash-object",
                        "-w",
                        "--no-filters",
                        "--stdin-paths",
                        input=_quoted_paths((spool,)),
                    )
                    .decode()
                    .strip()
                )
            written += 1
            if actual != oid:
                raise OSError("Retained target object differs from the copy")
            verify_blobs(
                [*target_git.prefix, "cat-file", "--batch"],
                env=target_git.env,
                objects=((oid, size, sha, None),),
            )
            if damaged and retained_metadata(destination) != original_metadata[oid]:
                raise OSError("Replaced Git object metadata changed")
        if not complete():
            raise OSError("Repaired target history did not verify")
        return outcome(
            "repaired",
            "exact_dependency_restored",
            retained=True,
            storage="verified",
            written=len(rows),
            message="Exact history payloads verified under the target root.",
        )
    except OSError, ValueError, TypeError, UnicodeError:
        if attempted:
            try:
                if complete():
                    return outcome(
                        "repaired",
                        "verified_after_write_fault",
                        retained=True,
                        storage="verified",
                        written=len(rows),
                        message="Exact target history verified after an uncertain Git response.",
                    )
            except OSError, ValueError, TypeError, UnicodeError:
                pass
            confirmed = 0
            try:
                target_git = _Git(root)
                for row in rows:
                    try:
                        verify_blobs(
                            [*target_git.prefix, "cat-file", "--batch"],
                            env=target_git.env,
                            objects=((row[0], row[1], row[2], None),),
                        )
                    except OSError, ValueError, TypeError, UnicodeError:
                        continue
                    confirmed += 1
            except OSError, ValueError, TypeError, UnicodeError:
                pass
            keep_diagnostic = bool(current.damaged_objects)
            return outcome(
                "unknown",
                "repair_unverified",
                storage="verified" if confirmed == len(rows) else "possible",
                written=confirmed,
                diagnostic=str(temporary) if keep_diagnostic else None,
                message=(
                    "Object writes may have occurred; inspect target history. "
                    f"Damaged bytes retained at {temporary}."
                    if current.damaged_objects
                    else "Some object writes may have occurred; inspect target history."
                ),
            )
        return outcome(
            "failed",
            "repair_not_started",
            message="Repair stopped before any target object write.",
        )
    finally:
        if temporary is not None and not keep_diagnostic:
            try:
                _discard_temporary(temporary, root.parent)
            except OSError:
                pass
