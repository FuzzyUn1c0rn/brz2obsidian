"""Serialize and recover scoped, metadata-only checkpoint publication."""

import os
import stat
import tempfile
import time
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field

from brz2obsidian.application.checkpoint_contracts import CheckpointLocator
from brz2obsidian.application.vault_recovery_contracts import VaultRecoveryPreparation
from brz2obsidian.application.vault_update_contracts import VaultOperationLock
from brz2obsidian.contracts import ReconciliationContract

from .vault_native import _physical, observe_file, verify_directory
from .vault_replace import move_file

LOCAL_LOCATOR_PENDING = "collection_local_locator_pending"
_JOURNAL = "brz2obsidian-collection-publication.json"
_GUARD = "brz2obsidian-collection-publication.lock"


class _LocalPublication(ReconciliationContract):
    schema_version: Literal[1]
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    previous: str | None = Field(pattern=r"^[0-9a-f]{40}$")
    locator: CheckpointLocator


def local_publication_pending(gitdir):
    return os.path.lexists(gitdir / _JOURNAL)


def _check_guard(path, stream):
    current = path.lstat()
    opened = os.fstat(stream.fileno())
    if (
        not _physical(current)
        or not stat.S_ISREG(current.st_mode)
        or current.st_nlink != 1
        or current.st_size != 0
        or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
    ):
        raise OSError("Scoped checkpoint publication guard changed")


@contextmanager
def collection_publication_guard(root):
    gitdir = root / ".git"
    anchor = verify_directory(gitdir)
    path = gitdir / _GUARD
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "r+b") as stream:
        _check_guard(path, stream)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _check_guard(path, stream)
        if verify_directory(gitdir) != anchor:
            raise OSError("Scoped checkpoint publication repository changed")
        yield


def read_native_marker(root):
    marker = root / ".git" / "brz2obsidian"
    if not os.path.lexists(marker):
        return None
    verify_directory(marker)
    if set(os.listdir(marker)) != {"owner.json", "held"}:
        raise OSError("Native operation marker is incomplete")
    info, _, raw, _ = observe_file(marker, marker / "owner.json", prefix_limit=4097)
    owner = VaultOperationLock.model_validate_json(raw)
    held = (marker / "held").lstat()
    if (
        len(raw) > 4096
        or len(raw) != info.st_size
        or not _physical(held)
        or not stat.S_ISREG(held.st_mode)
        or held.st_nlink != 1
        or held.st_size != 1
        or owner.vault_anchor != verify_directory(root)
        or owner.git_anchor != verify_directory(root / ".git")
    ):
        raise OSError("Native operation marker is outside its exact ownership context")
    return owner


def _scoped_apply_preparation(prepared, operation_id):
    return prepared.boundary == "prepared" and (
        prepared.collection_preparation_owner == operation_id
        or prepared.collection_preparation_owner is None
        and prepared.collection_record_path is not None
    )


def scoped_undo_target(target):
    origin = target.intent
    prepared, _ = target.observation.owned[origin.prepared_commit]
    return _scoped_apply_preparation(prepared, origin.operation_id)


def scoped_undo_receipt(git, receipt_commit, association_id):
    from .vault_apply import _operation_graph
    from .vault_history import _checkpoint_graph

    graph = _operation_graph(git, receipt_commit)
    origin = graph.authorities[-1][1]
    if (
        graph.receipt is None
        or graph.receipt.status != "applied"
        or origin.kind != "apply"
        or origin.association_id != association_id
    ):
        return False
    ref = f"refs/brz2obsidian/imports/{association_id}/operations/{origin.operation_id}"
    if git.call("rev-parse", "--verify", ref).decode().strip() != receipt_commit:
        return False
    _, _, manifest, _ = _checkpoint_graph(git, origin.prepared_commit, {}, None)
    return _scoped_apply_preparation(manifest, origin.operation_id)


def _scoped_operation_origin(git, graph, *, owned=None):
    from .vault_history import _checkpoint_graph

    origin = graph.authorities[-1][1]
    if owned is None:
        _, _, manifest, _ = _checkpoint_graph(git, origin.prepared_commit, {}, None)
    else:
        manifest = owned[origin.prepared_commit][0]
    if origin.kind == "apply":
        if _scoped_apply_preparation(manifest, origin.operation_id):
            return (manifest.previous,), None
        return None
    receipt = origin.undo_of_receipt_commit
    if receipt is None or not scoped_undo_receipt(git, receipt, origin.association_id):
        return None
    if manifest.undo_of_receipt_commit != receipt:
        raise OSError("Scoped Undo preparation does not match its retained receipt")
    return (manifest.previous, origin.prepared_commit), receipt


def _matches_scoped_origin(owner, operation_id, scope):
    checkpoints, receipt = scope
    return (
        owner is not None
        and owner.operation_id == operation_id
        and owner.collection_saved_checkpoint is not None
        and owner.collection_saved_checkpoint in checkpoints
        and owner.collection_undo_receipt == receipt
    )


def scoped_operation_marker(git, graph, owner):
    scope = _scoped_operation_origin(git, graph)
    return scope is not None and _matches_scoped_origin(
        owner, graph.intent.operation_id, scope
    )


def recovery_operation_marker(root, authority):
    from .vault_history import _Git

    owner = read_native_marker(root)
    graph = authority.graph
    scope = _scoped_operation_origin(_Git(root), graph, owned=authority.owned)
    operation_id = graph.intent.operation_id
    if scope is not None:
        return _matches_scoped_origin(owner, operation_id, scope)
    return owner is None or (
        owner.operation_id == operation_id
        and owner.collection_saved_checkpoint is None
        and owner.collection_undo_receipt is None
    )


def scoped_terminal_marker(root, git, receipt_commit, operation_id):
    from .vault_apply import _operation_graph

    owner = read_native_marker(root)
    graph = _operation_graph(git, receipt_commit)
    scope = _scoped_operation_origin(git, graph)
    if scope is not None:
        return _matches_scoped_origin(owner, operation_id, scope)
    if owner is not None and owner.collection_saved_checkpoint is not None:
        return False
    return None


def acquire_collection_apply(root, operation, locator, *, undo_receipt=None):
    from .vault_apply import _adopt, _lock_path
    from .vault_history import _Git, _validate_locator_association

    gitdir = root / ".git"
    with collection_publication_guard(root):
        _require_no_native_marker(root)
        _validate_locator_association(root, locator.association)
        if (
            local_publication_pending(gitdir)
            or _current_locator(root, advanced=False) != locator
            or _Git(root)
            .call("rev-parse", "--verify", locator.association.ref)
            .decode()
            .strip()
            != locator.commit
        ):
            raise OSError("Scoped Apply is no longer based on its saved review")
        staged = Path(tempfile.mkdtemp(dir=gitdir, prefix="brz2obsidian-start-"))
        try:
            owner = VaultOperationLock(
                schema_id="brz2obsidian.vault-operation-lock",
                schema_version=1,
                operation_id=operation,
                vault_anchor=locator.association.vault_anchor,
                git_anchor=locator.association.git_anchor,
                collection_saved_checkpoint=locator.commit,
                collection_undo_receipt=undo_receipt,
            )
            with (staged / "owner.json").open("xb") as stream:
                stream.write(owner.model_dump_json().encode())
                stream.flush()
                os.fsync(stream.fileno())
            with (staged / "held").open("xb") as stream:
                stream.write(b"1")
                stream.flush()
                os.fsync(stream.fileno())
            move_file(staged, _lock_path(root), replace=False)
            _adopt(root, operation)
        finally:
            with suppress(OSError):
                (staged / "owner.json").unlink(missing_ok=True)
                (staged / "held").unlink(missing_ok=True)
                staged.rmdir()


def release_native_operation(root, operation):
    from .vault_apply import _release

    owner = read_native_marker(root)
    if owner is None or owner.operation_id != operation:
        raise OSError("Native operation marker owner changed")
    if owner.collection_saved_checkpoint is None:
        _release(root, operation)
    else:
        with collection_publication_guard(root):
            _retire_collection_marker(root, operation)


def _retire_collection_marker(root, operation):
    """Detach the complete lease after closing its handle under the scoped guard."""
    from .vault_apply import _ACTIVE, _lock_path, _park, owns_operation

    marker = _lock_path(root)
    if not owns_operation(root, operation):
        raise OSError("Scoped restoration no longer owns the converter lease")
    anchor = verify_directory(marker)
    held = (marker / "held").lstat()
    live = os.fstat(_ACTIVE[str(root), operation][1].fileno())
    if (
        not _physical(held)
        or not stat.S_ISREG(held.st_mode)
        or held.st_nlink != 1
        or held.st_size != 1
        or (held.st_dev, held.st_ino) != (live.st_dev, live.st_ino)
    ):
        raise OSError("Scoped restoration lease file changed")
    scratch = Path(tempfile.mkdtemp(dir=marker.parent, prefix="brz2obsidian-retired-"))
    retired = scratch / "lease"
    try:
        _park(root, operation)
        if verify_directory(marker) != anchor:
            raise OSError("Collection restoration lease changed before retirement")
        move_file(marker, retired, replace=False)
        with suppress(OSError):
            if verify_directory(retired) == anchor:
                (retired / "owner.json").unlink()
                (retired / "held").unlink()
                retired.rmdir()
    finally:
        with suppress(OSError):
            scratch.rmdir()


def _require_no_native_marker(root):
    if os.path.lexists(root / ".git" / "brz2obsidian"):
        raise OSError("A native converter operation holds the vault")


def _journal_local_publication(root, journal):
    gitdir = root / ".git"
    with tempfile.NamedTemporaryFile(
        dir=gitdir, prefix="brz2obsidian-publication-", delete=False
    ) as output:
        stage = Path(output.name)
        output.write(journal.model_dump_json().encode())
        output.flush()
        os.fsync(output.fileno())
    try:
        move_file(stage, gitdir / _JOURNAL, replace=False)
    finally:
        stage.unlink(missing_ok=True)


def publish_local_capture(root, git, association, manifest, writes, *, scoped):
    if scoped:
        return _publish_collection_local(root, git, association, manifest, writes)
    from .vault_history import _publish_locator

    with collection_publication_guard(root):
        if local_publication_pending(root / ".git"):
            raise OSError("A scoped checkpoint publication is already pending")
        if (
            owner := read_native_marker(root)
        ) is not None and owner.collection_saved_checkpoint is not None:
            raise OSError("A scoped Apply already owns the converter lease")
        return _publish_locator(root, git, association, manifest, writes)


def _publish_collection_local(root, git, association, manifest, writes):
    from .vault_history import _publish_locator

    locator = CheckpointLocator(
        schema_id="brz2obsidian.checkpoint-locator",
        schema_version=1,
        association=association,
        generation=manifest.generation,
        commit=writes.commit,
    )
    journal = _LocalPublication(
        schema_version=1,
        operation_id=uuid4().hex,
        previous=manifest.previous,
        locator=locator,
    )
    with collection_publication_guard(root):
        _require_no_native_marker(root)
        if local_publication_pending(root / ".git"):
            raise OSError("A scoped checkpoint publication is already pending")
        if _local_publication_advanced(root, git, journal):
            raise OSError("The proposed scoped checkpoint is already current")
        _journal_local_publication(root, journal)
        _require_no_native_marker(root)
        published = _publish_locator(root, git, association, manifest, writes)
        (root / ".git" / _JOURNAL).unlink()
        return published


def _read_journal(root):
    gitdir = root / ".git"
    path = gitdir / _JOURNAL
    info, _, raw, _ = observe_file(gitdir, path, prefix_limit=65537)
    if info.st_size != len(raw) or len(raw) > 65536:
        raise OSError("Scoped checkpoint publication record exceeds its size bound")
    return _LocalPublication.model_validate_json(raw)


def _current_locator(root, *, advanced):
    directory = root / ".brz2obsidian"
    if not os.path.lexists(directory):
        return None
    verify_directory(directory)
    names = set(os.listdir(directory))
    permitted = {"locator.json", "locator.pending"} if advanced else {"locator.json"}
    if not names <= permitted or not advanced and names != permitted:
        raise OSError("Scoped checkpoint metadata directory changed")
    if "locator.pending" in names:
        observe_file(root, directory / "locator.pending", prefix_limit=0)
    if "locator.json" not in names:
        return None
    _, _, raw, _ = observe_file(root, directory / "locator.json", prefix_limit=65537)
    return CheckpointLocator.model_validate_json(raw)


def _local_publication_advanced(root, git, journal):
    from .vault_history import _validate_locator_association

    locator = journal.locator
    _validate_locator_association(root, locator.association)
    refs = (
        git.call(
            "for-each-ref",
            "--format=%(refname) %(objectname)",
            locator.association.ref
            if journal.previous
            else "refs/brz2obsidian/imports",
        )
        .decode()
        .splitlines()
    )
    new = f"{locator.association.ref} {locator.commit}"
    old = (
        []
        if journal.previous is None
        else [f"{locator.association.ref} {journal.previous}"]
    )
    advanced = refs == [new]
    if not advanced and refs != old:
        raise OSError("Scoped checkpoint publication has an unexpected owned ref")
    previous = (
        locator.model_copy(
            update={"commit": journal.previous, "generation": locator.generation - 1}
        )
        if journal.previous is not None
        else None
    )
    current = _current_locator(root, advanced=advanced)
    if current != previous and (not advanced or current != locator):
        raise OSError(
            "Scoped checkpoint publication has an unexpected physical locator"
        )
    return advanced


def _validate_local_checkpoint(git, journal):
    from .vault_history import _checkpoint_graph

    locator = journal.locator
    parents, _, manifest, association = _checkpoint_graph(git, locator.commit, {}, None)
    if (
        locator.association != association
        or manifest.association_id != association.association_id
        or manifest.boundary != "local"
        or manifest.generation != locator.generation
        or manifest.previous != journal.previous
        or parents != ([] if journal.previous is None else [journal.previous])
        or manifest.abandoned_collection_preparation is not None
        or manifest.operation_intent_commit is not None
    ):
        raise OSError("Scoped local checkpoint does not match retained publication")
    if manifest.discarded_review is not None:
        _, _, saved, saved_association = _checkpoint_graph(
            git, journal.previous, {}, None
        )
        qualified = (
            saved_association == association
            and saved.boundary == "local"
            and saved.reviewed_source is not None
            and saved.generation + 1 == locator.generation
            and (saved.collection_record_path or saved.collection_baseline_commit)
            and manifest.discarded_review == journal.previous
            and manifest.collection_record_path == saved.collection_record_path
            and manifest.identity == saved.identity
            and manifest.source == saved.source
            and manifest.vault == manifest.preimage == saved.vault
        )
    else:
        qualified = (
            (manifest.collection_record_path or manifest.collection_baseline_commit)
            and manifest.reviewed_source is not None
            and manifest.review_object is not None
            and (
                journal.previous is not None
                or not manifest.source
                and locator.generation == 1
            )
        )
    if not qualified:
        raise OSError("Checkpoint is not a scoped saved review or discard")


def _verify_advanced_checkpoint(root, locator):
    from .vault_history import _Git, _read_checkpoint_chain, _verify_checkpoint_payloads

    git = _Git(root)
    chain = _read_checkpoint_chain(git, locator, None, None, None, False, None)
    absent, damaged = _verify_checkpoint_payloads(root, git, chain.pending, None, None)
    if absent or damaged:
        raise OSError("Scoped checkpoint publication has invalid retained payloads")


def _observe_local_publication(root):
    from .vault_history import _Git

    _require_no_native_marker(root)
    journal = _read_journal(root)
    git = _Git(root)
    advanced = _local_publication_advanced(root, git, journal)
    _validate_local_checkpoint(git, journal)
    return journal, advanced


def _local_offer(journal):
    return VaultRecoveryPreparation(
        schema_id="brz2obsidian.vault-recovery-preparation",
        schema_version=1,
        status="cleanup",
        code=LOCAL_LOCATOR_PENDING,
        operation_id=journal.operation_id,
        kind="apply",
        generation=journal.locator.generation,
        intent_commit=None,
        unpublished_checkpoint=journal.locator.commit,
        available_directions=(),
        review=None,
    )


def prepare_local_publication(root):
    if not local_publication_pending(root / ".git"):
        return None
    return _local_offer(_observe_local_publication(root)[0])


def local_publication_status(root):
    from .vault_apply import _outcome

    start = time.monotonic()
    try:
        pending = prepare_local_publication(root)
        if pending is None:
            return None
        return _outcome(
            "incomplete",
            pending.code,
            start=start,
            operation_id=pending.operation_id,
            generation=pending.generation,
            checkpoint=pending.unpublished_checkpoint,
            recovery=True,
        )
    except OSError, ValueError, TypeError:
        return _outcome(
            "unknown",
            "collection_local_publication_invalid",
            start=start,
            recovery=True,
        )


def recover_local_publication(root, offer, *, cancel):
    from .vault_apply import _outcome
    from .vault_history import _persist_checkpoint_locator

    start = time.monotonic()
    try:
        with collection_publication_guard(root):
            journal, advanced = _observe_local_publication(root)
            if _local_offer(journal) != offer:
                return _outcome("refused", "recovery_preparation_changed", start=start)
            if cancel is not None and cancel():
                return _outcome(
                    "cancelled", "recovery_cancelled", start=start, recovery=True
                )
            if advanced:
                _verify_advanced_checkpoint(root, journal.locator)
                _persist_checkpoint_locator(root, journal.locator, replace_pending=True)
            (root / ".git" / _JOURNAL).unlink()
            return _outcome(
                "cancelled",
                "collection_local_locator_resealed"
                if advanced
                else "collection_local_publication_abandoned",
                start=start,
                operation_id=journal.operation_id,
                generation=journal.locator.generation,
                checkpoint=journal.locator.commit if advanced else journal.previous,
            )
    except OSError, ValueError, TypeError:
        return _outcome(
            "incomplete",
            "collection_local_publication_unavailable",
            start=start,
            recovery=True,
        )
