"""Reseal a scoped Result locator using its retained native intent."""

import time
from pathlib import Path

from brz2obsidian.application.checkpoint_contracts import CheckpointLocator

from .unpublished_collection import _owned_marker_matches
from .vault_history import (
    _checkpoint_graph,
    _persist_checkpoint_locator,
    inspect_history,
)
from .vault_native import observe_file

RESULT_LOCATOR_PENDING = "scoped_result_locator_pending"


def _result_locator_matches(manifest, prepared, intent):
    return (
        (
            prepared.collection_record_path is not None
            or prepared.collection_preparation_owner is not None
        )
        and manifest.collection_record_path == prepared.collection_record_path
        and manifest.identity == prepared.identity
        and manifest.source == prepared.source
        and manifest.association_id == intent.association_id
        and manifest.previous == intent.prepared_commit
        and manifest.generation == intent.generation + 1
        and manifest.vault == manifest.proposed == intent.proposed
        and manifest.preimage == intent.before
        and (
            prepared.collection_preparation_owner is None
            or prepared.collection_preparation_owner == intent.operation_id
        )
    )


def locator_after_scoped_result(root, git, saved_locator, tip, names):
    from .vault_apply import _operation_graph

    if names not in ({"locator.json"}, {"locator.json", "locator.pending"}):
        return None
    _, _, manifest, association = _checkpoint_graph(git, tip, {}, None)
    if (
        manifest.boundary != "result"
        or manifest.operation_intent_commit is None
        or association != saved_locator.association
        or manifest.previous != saved_locator.commit
        or manifest.generation != saved_locator.generation + 1
    ):
        return None
    _, _, prepared, parent_association = _checkpoint_graph(
        git, saved_locator.commit, {}, None
    )
    graph = _operation_graph(git, manifest.operation_intent_commit)
    intent = graph.intent
    ref = f"refs/brz2obsidian/imports/{intent.association_id}/operations/{intent.operation_id}"
    if (
        parent_association != association
        or prepared.boundary != "prepared"
        or prepared.generation != saved_locator.generation
        or graph.intent_commit != manifest.operation_intent_commit
        or graph.receipt is not None
        or git.call("rev-parse", "--verify", ref).decode().strip()
        != graph.intent_commit
        or not _result_locator_matches(manifest, prepared, intent)
        or not _owned_marker_matches(
            root,
            intent.operation_id,
            saved_checkpoint=prepared.previous
            if prepared.collection_preparation_owner
            else None,
        )
    ):
        return None
    return saved_locator.model_copy(
        update={"commit": tip, "generation": manifest.generation}
    )


def with_result_locator_status(root, checkpoint, outcome, retained_result):
    if retained_result is None:
        return outcome
    _, _, raw, _ = observe_file(
        root, root / ".brz2obsidian/locator.json", prefix_limit=65537
    )
    if CheckpointLocator.model_validate_json(raw) == checkpoint.locator:
        return outcome
    return outcome.model_copy(
        update={
            "code": RESULT_LOCATOR_PENDING,
            "message": "Finish publishing the retained Result locator before recovery.",
        }
    )


def _matches(outcome, offer):
    return (
        outcome.code == RESULT_LOCATOR_PENDING
        and outcome.operation_id == offer.operation_id
        and outcome.kind == offer.kind
        and outcome.generation == offer.generation
        and outcome.intent_commit == offer.intent_commit
        and outcome.result_commit == offer.result_locator_checkpoint
    )


def reseal_scoped_result(vault, offer, *, cancel):
    from .vault_apply import _adopt, _outcome, _park, inspect_update_status

    root = Path(vault).absolute()
    start = time.monotonic()
    operation = offer.operation_id
    acquired = False
    try:
        observed = inspect_update_status(root)
        if not _matches(observed, offer):
            return _outcome("refused", "recovery_preparation_changed", start=start)
        if cancel is not None and cancel():
            return _outcome(
                "cancelled", "recovery_cancelled", start=start, recovery=True
            )
        _adopt(root, operation)
        acquired = True
        if not _matches(inspect_update_status(root), offer):
            raise OSError("Result locator authority changed under its lease")
        history = inspect_history(root, active_operation=operation)
        if (
            history.status != "intact"
            or history.admission.status != "supported"
            or history.checkpoint.locator.commit != offer.result_locator_checkpoint
        ):
            raise OSError("Current Result locator is not admitted")
        _persist_checkpoint_locator(
            root, history.checkpoint.locator, replace_pending=True
        )
        return observed.model_copy(
            update={
                "code": "scoped_result_locator_resealed",
                "authored_files_changed": False,
                "published_files": 0,
                "message": "The retained Result locator is current. Continue the existing recovery.",
            }
        )
    except OSError, ValueError, TypeError, AttributeError:
        return _outcome(
            "incomplete",
            "scoped_result_locator_unavailable",
            start=start,
            operation_id=operation,
            intent=offer.intent_commit,
            result=offer.result_locator_checkpoint,
            phase="result",
            history="result",
            recovery=True,
        )
    finally:
        if acquired:
            _park(root, operation)
