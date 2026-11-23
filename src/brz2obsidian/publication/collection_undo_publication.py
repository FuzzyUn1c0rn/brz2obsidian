"""Validate scoped Undo ownership before its native intent exists."""

import os
import time

from brz2obsidian.application.vault_recovery_contracts import VaultRecoveryPreparation

from .collection_publication import (
    _retire_collection_marker,
    collection_publication_guard,
    read_native_marker,
    scoped_undo_receipt,
)

SCOPED_UNDO_PENDING = "scoped_undo_metadata_pending"


def locator_after_scoped_undo_preparation(root, git, physical, tip, names):
    from .vault_history import _checkpoint_graph

    if names not in ({"locator.json"}, {"locator.json", "locator.pending"}):
        return None
    _, _, prepared, association = _checkpoint_graph(git, tip, {}, None)
    if (
        prepared.boundary != "prepared"
        or prepared.undo_of_receipt_commit is None
        or prepared.recovery_origin_intent_commit is not None
        or prepared.previous != physical.commit
        or prepared.generation != physical.generation + 1
        or association != physical.association
    ):
        return None
    owner = read_native_marker(root)
    if (
        owner is None
        or owner.collection_saved_checkpoint != physical.commit
        or owner.collection_undo_receipt != prepared.undo_of_receipt_commit
        or not scoped_undo_receipt(
            git, owner.collection_undo_receipt, association.association_id
        )
    ):
        return None
    return physical.model_copy(
        update={"commit": tip, "generation": prepared.generation}
    )


def _pending_target(observation, owner):
    from .vault_undo import _qualify_undo_target, _terminal_target_graph

    graph = _terminal_target_graph(observation)
    if (
        graph is None
        or graph.commit != owner.collection_undo_receipt
        or observation.graph.intent.operation_id == owner.operation_id
        or observation.graph.receipt is None
    ):
        return None
    return _qualify_undo_target(graph, observation)[2]


def _marker_matches_checkpoint(observation, owner):
    checkpoint = observation.checkpoint
    locator = checkpoint.locator
    manifest = checkpoint.manifest
    if manifest.boundary != "prepared":
        return owner.collection_saved_checkpoint == locator.commit
    return (
        observation.unpublished_prepared == locator.commit
        and manifest.undo_of_receipt_commit == owner.collection_undo_receipt
        and owner.collection_saved_checkpoint in (locator.commit, manifest.previous)
    )


def pending_scoped_undo(root, observation):
    from .collection_publication import scoped_undo_target

    if observation is None or not os.path.lexists(root / ".git" / "brz2obsidian"):
        return None
    try:
        owner = read_native_marker(root)
        if owner is None or owner.collection_undo_receipt is None:
            return None
        target = _pending_target(observation, owner)
        if (
            not _marker_matches_checkpoint(observation, owner)
            or target is None
            or not scoped_undo_target(target)
        ):
            return None
        locator = observation.checkpoint.locator
        return VaultRecoveryPreparation(
            schema_id="brz2obsidian.vault-recovery-preparation",
            schema_version=1,
            status="cleanup",
            code=SCOPED_UNDO_PENDING,
            operation_id=owner.operation_id,
            kind="undo",
            generation=locator.generation,
            intent_commit=None,
            unpublished_checkpoint=locator.commit,
            available_directions=(),
            review=None,
        )
    except OSError, ValueError, TypeError:
        return None


def recover_scoped_undo_metadata(root, offer, *, cancel):
    from .vault_apply import _adopt, _inspect_update_observation, _outcome, _park
    from .vault_history import _persist_checkpoint_locator

    start = time.monotonic()
    operation = offer.operation_id
    try:
        with collection_publication_guard(root):
            _, observed = _inspect_update_observation(root)
            if pending_scoped_undo(root, observed) != offer:
                return _outcome("refused", "recovery_preparation_changed", start=start)
            if cancel is not None and cancel():
                return _outcome(
                    "cancelled", "recovery_cancelled", start=start, recovery=True
                )
            _adopt(root, operation)
            try:
                _, held = _inspect_update_observation(root)
                if pending_scoped_undo(root, held) != offer:
                    raise OSError("Scoped Undo ownership changed during recovery")
                locator = held.checkpoint.locator
                if held.unpublished_prepared == locator.commit:
                    _persist_checkpoint_locator(root, locator, replace_pending=True)
                _retire_collection_marker(root, operation)
            finally:
                _park(root, operation)
        return _outcome(
            "cancelled",
            "scoped_undo_metadata_recovered",
            start=start,
            operation_id=operation,
            kind="undo",
            generation=offer.generation,
            checkpoint=offer.unpublished_checkpoint,
        )
    except OSError, ValueError, TypeError:
        return _outcome(
            "incomplete", "scoped_undo_metadata_unavailable", start=start, recovery=True
        )
