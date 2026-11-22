"""Resolve a scoped Apply stopped before it retained a native intent."""

import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from brz2obsidian.application.vault_update_contracts import VaultOperationLock

from .vault_history import (
    _binding_signature,
    _CaptureWrites,
    _checkpoint_graph,
    _commit_checkpoint_tree,
    _Git,
    _publish_locator,
    _read,
    _review_meaning,
    _semantic_meaning,
    _write_capture_metadata,
    inspect_history,
)
from .vault_native import observe_file, verify_directory

_CODE = "unpublished_collection_prepared"


def locator_after_unpublished_preparation(root, git, saved_locator, tip, names):
    if tip == saved_locator.commit or names not in (
        {"locator.json"},
        {"locator.json", "locator.pending"},
    ):
        return None
    _, _, manifest, association = _checkpoint_graph(git, tip, {}, None)
    if (
        manifest.collection_preparation_owner is None
        or manifest.previous != saved_locator.commit
        or manifest.generation != saved_locator.generation + 1
        or association != saved_locator.association
    ):
        return None
    marker = root / ".git" / "brz2obsidian"
    _, _, raw, _ = observe_file(marker, marker / "owner.json", prefix_limit=4097)
    if len(raw) > 4096:
        return None
    owner = VaultOperationLock.model_validate_json(raw)
    if (
        owner.operation_id != manifest.collection_preparation_owner
        or owner.vault_anchor != verify_directory(root)
        or owner.git_anchor != verify_directory(root / ".git")
    ):
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
    owner = manifest.collection_preparation_owner
    if owner is None:
        return None
    if previous is not None and (
        previous.receipt is None or previous.intent.generation >= manifest.generation
    ):
        return None
    saved_commit = manifest.previous
    _, _, saved, association = _checkpoint_graph(git, saved_commit, {}, None)
    if (
        saved.boundary != "local"
        or saved.reviewed_source is None
        or saved.preimage != manifest.preimage
        or association != checkpoint.locator.association
        or not (saved.collection_record_path or saved.collection_baseline_commit)
        or _binding_signature(saved.reviewed_source)
        != _binding_signature(manifest.reviewed_source)
    ):
        return None
    if previous is not None:
        parent = SimpleNamespace(
            locator=checkpoint.locator.model_copy(
                update={"commit": saved_commit, "generation": saved.generation}
            ),
            manifest=saved,
        )
        if not _terminal_result_in_history(
            git, parent, previous.intent, previous.receipt
        ):
            return None
    return _outcome(
        "incomplete",
        _CODE,
        start=start,
        operation_id=owner,
        phase="prepared",
        generation=manifest.generation,
        checkpoint=checkpoint.locator.commit,
        history="prepared",
        recovery=True,
        message="Restore the saved review from its unpublished preparation.",
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
        locator = _restore_saved_checkpoint(root, history.checkpoint, prepared)
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
        observed.code == _CODE
        and observed.operation_id == offer.operation_id
        and observed.generation == offer.generation
        and observed.checkpoint_commit == offer.unpublished_checkpoint
    )


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
    restored = saved.model_copy(
        update={
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
