"""Resolve a scoped Apply stopped before it retained a native intent."""

import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

from brz2obsidian.application.checkpoint_contracts import CheckpointManifest
from brz2obsidian.application.vault_update_contracts import VaultOperationLock

from .vault_history import (
    _binding_signature,
    _CaptureWrites,
    _checkpoint_graph,
    _commit_checkpoint_tree,
    _Git,
    _persist_checkpoint_locator,
    _publish_locator,
    _read,
    _review_meaning,
    _semantic_meaning,
    _write_capture_metadata,
    inspect_history,
)
from .vault_native import observe_file, verify_directory

_PREPARED = "unpublished_collection_prepared"
_RESEAL = "restored_collection_locator_pending"
UNPUBLISHED_RECOVERY_CODES = (_PREPARED, _RESEAL)


class _UnpublishedLineage(NamedTuple):
    preparing: CheckpointManifest
    prepared_commit: str
    saved: CheckpointManifest
    saved_commit: str


def _owned_marker_matches(root, operation):
    marker = root / ".git" / "brz2obsidian"
    if not os.path.lexists(marker):
        return False
    verify_directory(marker)
    if set(os.listdir(marker)) != {"owner.json", "held"}:
        return False
    _, _, raw, _ = observe_file(marker, marker / "owner.json", prefix_limit=4097)
    if len(raw) > 4096:
        return False
    owner = VaultOperationLock.model_validate_json(raw)
    return (
        owner.operation_id == operation
        and owner.vault_anchor == verify_directory(root)
        and owner.git_anchor == verify_directory(root / ".git")
    )


def _unpublished_lineage(git, commit, manifest, association):
    if manifest.collection_preparation_owner is not None:
        prepared, prepared_commit = manifest, commit
    elif manifest.abandoned_collection_preparation is not None:
        prepared_commit = manifest.abandoned_collection_preparation
        _, _, prepared, actual = _checkpoint_graph(git, prepared_commit, {}, None)
        if (
            actual != association
            or prepared.collection_preparation_owner is None
            or prepared.generation + 1 != manifest.generation
        ):
            return None
    else:
        return None
    saved_commit = prepared.previous
    _, _, saved, actual = _checkpoint_graph(git, saved_commit, {}, None)
    if (
        saved.boundary != "local"
        or saved.generation + 1 != prepared.generation
        or saved.reviewed_source is None
        or saved.preimage != prepared.preimage
        or actual != association
        or not (saved.collection_record_path or saved.collection_baseline_commit)
        or _binding_signature(saved.reviewed_source)
        != _binding_signature(prepared.reviewed_source)
        or manifest.abandoned_collection_preparation is not None
        and not restored_roles_match(manifest, saved, saved_commit)
    ):
        return None
    return _UnpublishedLineage(prepared, prepared_commit, saved, saved_commit)


def locator_after_unpublished_preparation(root, git, saved_locator, tip, names):
    if names not in ({"locator.json"}, {"locator.json", "locator.pending"}):
        return None
    _, _, manifest, association = _checkpoint_graph(git, tip, {}, None)
    if association != saved_locator.association:
        return None
    lineage = _unpublished_lineage(git, tip, manifest, association)
    if lineage is None:
        return None
    owner = lineage.preparing.collection_preparation_owner
    if not _owned_marker_matches(root, owner):
        return None
    permitted = {(lineage.saved_commit, lineage.saved.generation)}
    if manifest.abandoned_collection_preparation is not None:
        permitted.update(
            (
                (lineage.prepared_commit, lineage.preparing.generation),
                (tip, manifest.generation),
            )
        )
    if (saved_locator.commit, saved_locator.generation) not in permitted:
        return None
    return saved_locator.model_copy(
        update={"commit": tip, "generation": manifest.generation}
    )


def _restored_fields(saved, commit):
    return {
        "collection_baseline_commit": commit
        if saved.collection_baseline_commit
        else None,
    }


def restored_roles_match(restored, saved, commit):
    structural = {
        "generation",
        "previous",
        "semantic_fingerprint",
        "abandoned_collection_preparation",
    }
    expected = saved.model_copy(update=_restored_fields(saved, commit))
    return restored.model_dump(exclude=structural) == expected.model_dump(
        exclude=structural
    )


def unpublished_outcome(git, checkpoint, start, *, previous=None):
    from .vault_apply import _outcome, _terminal_result_in_history

    if checkpoint.status != "valid":
        return None
    manifest = checkpoint.manifest
    locator = checkpoint.locator
    reseal = manifest.abandoned_collection_preparation is not None
    marker_present = os.path.lexists(git.root / ".git" / "brz2obsidian")
    if reseal and not marker_present:
        return None
    lineage = _unpublished_lineage(git, locator.commit, manifest, locator.association)
    if lineage is None:
        return None
    owner = lineage.preparing.collection_preparation_owner
    if marker_present and not _owned_marker_matches(git.root, owner):
        return None
    if previous is not None:
        if (
            previous.receipt is None
            or previous.intent.generation >= lineage.preparing.generation
            or previous.intent.operation_id == owner
        ):
            return None
        parent = SimpleNamespace(
            locator=locator.model_copy(
                update={
                    "commit": lineage.saved_commit,
                    "generation": lineage.saved.generation,
                }
            ),
            manifest=lineage.saved,
        )
        if not _terminal_result_in_history(
            git, parent, previous.intent, previous.receipt
        ):
            return None
    return _outcome(
        "incomplete",
        _RESEAL if reseal else _PREPARED,
        start=start,
        operation_id=owner,
        phase="prepared",
        generation=manifest.generation,
        checkpoint=checkpoint.locator.commit,
        history="prepared",
        recovery=True,
        message=(
            "Finish publishing the restored review locator and release its lease."
            if reseal
            else "Restore the saved review from its unpublished preparation."
        ),
    )


def restore_unpublished_collection(vault, prepared, *, cancel):
    from .vault_apply import _adopt, _outcome, _park, _release, inspect_update_status

    start = time.monotonic()
    root = Path(vault).absolute()
    operation = prepared.operation_id
    acquired = False
    try:
        if not _matches_offer(inspect_update_status(root), prepared):
            return _outcome("refused", "recovery_preparation_changed", start=start)
        if cancel is not None and cancel():
            return _outcome(
                "cancelled", "recovery_cancelled", start=start, recovery=True
            )
        _adopt(root, operation)
        acquired = True
        if not _matches_offer(inspect_update_status(root), prepared):
            raise OSError("Unpublished preparation changed under its converter lease")
        history = inspect_history(root, active_operation=operation)
        if history.status != "intact" or history.admission.status != "supported":
            raise OSError("Current repository admission is unavailable")
        locator = (
            _reseal_restored_checkpoint(root, history.checkpoint, prepared)
            if prepared.code == _RESEAL
            else _restore_saved_checkpoint(root, history.checkpoint, prepared)
        )
        _release(root, operation)
        acquired = False
        return _outcome(
            "cancelled",
            "saved_collection_review_restored",
            start=start,
            operation_id=operation,
            generation=locator.generation,
            phase="prepared",
            checkpoint=locator.commit,
            message="Publication was cancelled and the saved review was restored.",
        )
    except OSError, ValueError, TypeError, AttributeError:
        return _outcome(
            "incomplete",
            "unpublished_collection_restore_unavailable",
            start=start,
            operation_id=operation,
            checkpoint=prepared.unpublished_checkpoint,
            phase="prepared",
            history="prepared",
            recovery=True,
        )
    finally:
        if acquired:
            _park(root, operation)


def _matches_offer(observed, offer):
    return (
        observed.code == offer.code
        and offer.code in UNPUBLISHED_RECOVERY_CODES
        and observed.operation_id == offer.operation_id
        and observed.generation == offer.generation
        and observed.checkpoint_commit == offer.unpublished_checkpoint
    )


def _reseal_restored_checkpoint(root, checkpoint, offer):
    locator = checkpoint.locator
    if (
        locator.commit != offer.unpublished_checkpoint
        or checkpoint.manifest.abandoned_collection_preparation is None
    ):
        raise OSError("Current restored review changed")
    _persist_checkpoint_locator(root, locator, replace_pending=True)
    return locator


def _restore_saved_checkpoint(root, checkpoint, prepared):
    git = _Git(root)
    prior_commit = checkpoint.manifest.previous
    tip, records = _read(root, git, targets={prior_commit})
    if (
        tip.locator != checkpoint.locator
        or tip.locator.commit != prepared.unpublished_checkpoint
    ):
        raise OSError("Current unpublished preparation changed")
    saved, review = records[prior_commit]
    if review is None:
        raise OSError("Unpublished preparation lacks its saved review")
    association = tip.locator.association
    restored_fields = _restored_fields(saved, prior_commit)
    semantic = _semantic_meaning(
        association,
        saved.identity,
        saved.source,
        saved.vault,
        saved.preimage,
        saved.proposed,
        saved.recovery_gaps,
        saved.boundary,
        saved.policy_fingerprint,
        _review_meaning(review.saved),
        observed_source=saved.observed_source,
        reviewed_source=saved.reviewed_source,
        collection_record_path=saved.collection_record_path,
        collection_baseline_commit=restored_fields["collection_baseline_commit"],
        abandoned_collection_preparation=tip.locator.commit,
    )
    restored = CheckpointManifest.model_validate(
        saved.model_dump()
        | {
            **restored_fields,
            "generation": tip.locator.generation + 1,
            "previous": tip.locator.commit,
            "abandoned_collection_preparation": tip.locator.commit,
            "semantic_fingerprint": semantic,
        }
    )
    _, entries, _, _ = _checkpoint_graph(git, prior_commit, {}, None)
    roots = [
        (path, mode, oid)
        for path, (mode, kind, oid) in entries.items()
        if "/" not in path and kind == "tree"
    ]
    writes = _CaptureWrites()
    writes.git, writes.ref = git, association.ref
    with tempfile.TemporaryDirectory(prefix="brz2obsidian-restore-review-") as scratch:
        git.suppress_hooks(Path(scratch))
        metadata = _write_capture_metadata(
            git, association, restored, saved.review_object, writes
        )
        _commit_checkpoint_tree(git, restored, [*metadata, *roots], writes)
        pending = root / ".brz2obsidian" / "locator.pending"
        if pending.exists():
            observe_file(root, pending, prefix_limit=0)
            pending.unlink()
        return _publish_locator(root, git, association, restored, writes)
