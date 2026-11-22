"""Latest completed-operation eligibility and shared reviewed reversal."""

import time
from contextlib import ExitStack
from pathlib import Path
from typing import NamedTuple

from brz2obsidian.application.vault_undo_contracts import VaultUndoPreparation
from brz2obsidian.content_fingerprints import canonical_equal
from brz2obsidian.core import resolve_review, select_review_effects
from brz2obsidian.publication.vault_apply import (
    _apply_reviewed_update,
    _inspect_update_observation,
    _outcome,
    _OwnedCleanupFailure,
)
from brz2obsidian.publication.vault_history import _Git
from brz2obsidian.publication.vault_recovery import _restore_review, _retained_source


class _UndoTarget(NamedTuple):
    """Same-call validated target; never an additional stored operation."""

    receipt_commit: str
    graph: object
    intent: object
    plan: object
    lineage: object
    observation: object
    status: object = None


class _ReversalTarget(NamedTuple):
    """Derived physical endpoints, distinct from an admitted operation record."""

    operation_id: str
    kind: str
    generation: int
    association_id: str
    prepared_commit: str
    before: tuple
    proposed: tuple
    affected_paths: tuple
    undo_of_receipt_commit: None = None


def _target_from_graph(graph, observation):
    if (
        graph.receipt is None
        or graph.receipt.status != "applied"
        or graph.intent.kind != "apply"
    ):
        raise OSError("Undo target is not a completed apply")
    origin = graph.authorities[-1][1]
    prepared, loaded = observation.owned[origin.prepared_commit]
    if loaded is None or prepared.previous is None:
        raise OSError("Undo target lacks canonical review or previous source")
    before = {row.path: row for row in origin.before}
    proposed = {row.path: row for row in graph.intent.proposed}
    # A terminal recovery inventory also retains later protected writing.
    # Its difference from the original preimage grants no write ownership.
    owned_paths = {
        path for _, authority in graph.authorities for path in authority.affected_paths
    }
    affected = tuple(
        sorted(
            path
            for path in before.keys() | proposed.keys()
            if path in owned_paths and before.get(path) != proposed.get(path)
        )
    )
    target = _ReversalTarget(
        origin.operation_id,
        origin.kind,
        origin.generation,
        origin.association_id,
        origin.prepared_commit,
        origin.before,
        graph.intent.proposed,
        affected,
    )
    return _UndoTarget(
        graph.commit,
        graph,
        target,
        loaded.saved.plan,
        observation.owned[prepared.previous][0],
        observation,
    )


def _unused_preparations(current, completed, target, roles):
    """Allow only discarded reviews and unused preparations for this Undo."""
    by_commit = {row.commit: row for row in roles}
    discarded = _discarded_memos(roles)
    while current != completed:
        row = by_commit.get(current)
        if (
            row is None
            or current not in discarded
            and not (
                row.boundary == "prepared"
                and row.undo_of_receipt_commit == target
                and row.operation_intent_commit is None
                and row.recovery_origin_intent_commit is None
            )
        ):
            return False
        current = row.previous
    return True


def _target_history_known(graph, observation):
    """No unknown maintenance boundary can be hidden behind a later role."""
    target = graph.commit
    allowed = _discarded_memos(observation.checkpoint_roles)
    recovery_origins = set()
    for operation in observation.graphs:
        if operation.authorities[-1][1].undo_of_receipt_commit != target:
            continue
        allowed.update(
            authority.prepared_commit for _, authority in operation.authorities
        )
        recovery_origins.add(operation.origin_intent_commit)
        if operation.receipt is not None:
            allowed.add(operation.receipt.result_commit)
    current = observation.checkpoint.locator.commit
    for row in observation.checkpoint_roles:
        if row.commit != current:
            return False
        if current == graph.receipt.result_commit:
            return True
        if current not in allowed and not (
            row.boundary == "prepared"
            and row.operation_intent_commit is None
            and (
                row.undo_of_receipt_commit == target
                or row.recovery_origin_intent_commit in recovery_origins
            )
        ):
            return False
        current = row.previous
    return False


def _discarded_memos(roles):
    allowed = set()
    expected = proposal = None
    for row in roles:
        if row.discarded_review is not None:
            expected = row.discarded_review
            allowed.add(row.commit)
        elif row.commit == expected:
            expected = None
            proposal = row.saved_proposal_id
            allowed.add(row.commit)
        elif proposal is not None and row.saved_proposal_id == proposal:
            allowed.add(row.commit)
        else:
            proposal = None
    return allowed


def _terminal_target_graph(observation):
    graph = observation.graph
    if graph.receipt is None:
        return None
    if graph.intent.kind == "undo":
        if graph.receipt.status != "restored":
            return None
        target = graph.authorities[-1][1].undo_of_receipt_commit
        graph = next((row for row in observation.graphs if row.commit == target), None)
    return graph if graph is not None and graph.receipt.status == "applied" else None


def _unpublished_undo_matches(observation):
    """Bind the selected pending transition without manufacturing an intent."""
    from brz2obsidian.publication.vault_apply import (
        _prepared_for_intent,
        _recovery_prepared_matches,
        _UnpublishedUndo,
    )

    graph = _terminal_target_graph(observation)
    manifest = observation.checkpoint.manifest
    loaded = observation.checkpoint.review
    if (
        graph is None
        or manifest.undo_of_receipt_commit != graph.commit
        or loaded is None
        or not _target_history_known(graph, observation)
        or not _unused_preparations(
            manifest.previous,
            observation.graph.receipt.result_commit,
            graph.commit,
            observation.checkpoint_roles,
        )
    ):
        return False
    target = _target_from_graph(graph, observation)
    before = {row.path: row for row in manifest.preimage}
    proposed = {row.path: row for row in manifest.proposed}
    transition = _UnpublishedUndo(
        manifest.generation,
        manifest.association_id,
        manifest.preimage,
        manifest.proposed,
        observation.checkpoint.locator.commit,
        tuple(
            sorted(
                path
                for path in before.keys() | proposed.keys()
                if before.get(path) != proposed.get(path)
            )
        ),
        graph.commit,
    )
    return _prepared_for_intent(
        transition,
        manifest,
        loaded,
        origin=target.intent,
        origin_commit=target.graph.origin_intent_commit,
        origin_plan=target.plan,
        undo_target=target,
        origin_effects=target.observation.owned[target.intent.prepared_commit][
            1
        ].historical_effects,
    ) and _recovery_prepared_matches(
        transition,
        target.intent,
        target.graph.origin_intent_commit,
        manifest,
        loaded,
        target.lineage,
        target.plan,
        direction="restore",
        undo_target=target,
        origin_loaded=target.observation.owned[target.intent.prepared_commit][1],
    )


def _qualify_undo_target(graph, observation):
    if graph.receipt.status == "no_content_change":
        return "none", "latest_update_had_no_effect", None
    if graph.receipt.status != "applied":
        return "none", "latest_update_not_applied", None
    if not _target_history_known(graph, observation):
        return "unsupported", "maintenance_eligibility_unavailable", None
    target = _target_from_graph(graph, observation)
    if target.plan.facts.format_operation.kind not in (
        "source_update",
        "onboarding",
        "collection_import",
    ):
        return "none", "latest_operation_is_maintenance", None
    return (
        "offered",
        "latest_undo_review_required",
        target,
    )


def _eligible_target(observed, observation, *, active_operation=None):
    if observation is None:
        return (
            ("recovery_required", observed.code, None)
            if observed.recovery_required
            else ("none", "no_completed_update", None)
        )
    if (
        observed.recovery_required
        and not (
            observed.code == "undo_prepared"
            and observation.unpublished_prepared is not None
        )
        and not (
            active_operation is not None
            and observed.history == "terminal"
            and observed.code
            in ("terminal_cleanup_required", "terminal_requires_recovery")
        )
    ):
        return "recovery_required", observed.code, None
    graph = observation.graph
    if graph.receipt is None:
        return "recovery_required", "incomplete_operation", None
    if graph.intent.kind == "undo":
        target_commit = graph.authorities[-1][1].undo_of_receipt_commit
        if target_commit is None:
            return "unsupported", "legacy_undo_eligibility_unknown", None
        if graph.receipt.status == "undone":
            return "already_undone", "latest_update_already_undone", None
        if graph.receipt.status != "restored":
            return "unsupported", "undo_terminal_unsupported", None
        graph = next(
            (item for item in observation.graphs if item.commit == target_commit), None
        )
        if graph is None:
            return "unavailable", "undo_target_missing", None
    return _qualify_undo_target(graph, observation)


def _capture_target(
    root, *, receipt_commit, active_operation, prior, boundary, retained=None
):
    """Revalidate actual admitted ownership and the exact Undo target at capture."""
    from brz2obsidian.publication.vault_apply import owns_operation

    if not owns_operation(root, active_operation):
        raise OSError("Undo capture lacks its owned operation lease")
    status, observation = (
        _inspect_update_observation(root) if retained is None else retained
    )
    if observation is None:
        raise OSError("Undo capture history is unavailable")
    if boundary == "prepared":
        _, _, target = _eligible_target(
            status, observation, active_operation=active_operation
        )
        if target is None or target.receipt_commit != receipt_commit:
            raise OSError("Latest Undo target changed")
    else:
        intent = observation.graph.intent
        if (
            intent.operation_id != active_operation
            or intent.kind != "undo"
            or intent.undo_of_receipt_commit != receipt_commit
            or intent.prepared_commit != prior.locator.commit
            or prior.manifest.undo_of_receipt_commit != receipt_commit
        ):
            raise OSError("Undo result lacks its exact admitted target")
        graph = next(
            (item for item in observation.graphs if item.commit == receipt_commit), None
        )
        if graph is None:
            raise OSError("Undo completed target is unavailable")
        target = _target_from_graph(graph, observation)
    return target


def _preparation(status, code, *, target=None, review=None):
    return VaultUndoPreparation(
        schema_id="brz2obsidian.vault-undo-preparation",
        schema_version=1,
        status=status,
        code=code,
        checkpoint_commit=(
            target.observation.checkpoint.locator.commit if target else None
        ),
        generation=(
            target.observation.checkpoint.manifest.generation if target else None
        ),
        target_receipt_commit=target.receipt_commit if target else None,
        review=review,
    )


def _prepare_observed(root, observed, observation, *, previous=None, _owner=None):
    status, code, target = _eligible_target(observed, observation)
    if target is None:
        return _preparation(status, code), None
    target = target._replace(status=observed)
    if previous is not None and previous.target_receipt_commit != target.receipt_commit:
        return _preparation("refused", "undo_target_changed"), None
    if _owner is not None:
        target = _owner._operation_target(target)
        pending_review = None
        checkpoint = observation.checkpoint
        if (
            observation.unpublished_prepared == checkpoint.locator.commit
            and checkpoint.manifest.boundary == "prepared"
            and checkpoint.manifest.undo_of_receipt_commit == target.receipt_commit
            and checkpoint.manifest.operation_intent_commit is None
            and checkpoint.manifest.recovery_origin_intent_commit is None
            and checkpoint.review is not None
        ):
            pending = _owner._load_tip(checkpoint)
            if pending is None:
                raise OSError("Pending Undo lacks its canonical retained review")
            if previous is None or canonical_equal(previous.review, pending.saved.plan):
                pending_review = pending.saved.plan
        with _owner._session._operation():
            review = _restore_review(
                root,
                observed,
                previous=previous.review if previous else pending_review,
                authority=(
                    target.plan,
                    target.intent,
                    target.graph.origin_intent_commit,
                    observation,
                ),
                undo_target=target,
                _owner=_owner,
            )
        prepared = _preparation("offered", code, target=target, review=review)
        if pending_review is not None:
            retained = _preparation(
                "offered", code, target=target, review=pending_review
            )
            if _same_review(prepared, retained):
                prepared = retained
        return prepared, target
    review = _restore_review(
        root,
        observed,
        previous=previous.review if previous else None,
        authority=(
            target.plan,
            target.intent,
            target.graph.origin_intent_commit,
            observation,
        ),
        undo_target=target,
    )
    return _preparation("offered", code, target=target, review=review), target


def prepare_undo(vault, *, previous=None, _owner=None):
    """Observe latest eligibility and prepare/refresh one canonical S1 reversal."""
    try:
        if previous is not None:
            previous = VaultUndoPreparation.model_validate(previous)
            if previous.status != "offered":
                return _preparation("refused", "undo_review_required")
        root = Path(vault).absolute()
        if _owner is not None:
            history = _owner._observe(vault, _recovery=True)
            if (
                history.status != "intact"
                or history.admission.status != "supported"
                or _owner.observed._terminal is None
            ):
                return _preparation("unavailable", "undo_history_or_review_unavailable")
            _owner._start_session()
        observed, observation = (
            _inspect_update_observation(root)
            if _owner is None
            else (_owner.observed._recovery_status, _owner.observed._terminal)
        )
        return _prepare_observed(
            root, observed, observation, previous=previous, _owner=_owner
        )[0]
    except OSError, ValueError, TypeError, UnicodeError:
        return _preparation("unavailable", "undo_history_or_review_unavailable")


def _same_review(fresh, saved):
    return (
        fresh.status == saved.status == "offered"
        and fresh.checkpoint_commit == saved.checkpoint_commit
        and fresh.target_receipt_commit == saved.target_receipt_commit
        and canonical_equal(
            fresh.review.facts.model_copy(
                update={"generation": saved.review.facts.generation}
            ),
            saved.review.facts,
        )
        and fresh.review.preflight == saved.review.preflight
    )


def resolve_undo(vault, preparation, action):
    """Resolve only a still-current exact target and S1 generation."""
    try:
        saved = VaultUndoPreparation.model_validate(preparation)
        if saved.status != "offered":
            return _preparation("refused", "undo_review_required")
        fresh = prepare_undo(vault)
        if not _same_review(fresh, saved):
            return _preparation("refused", "undo_review_stale")
        transition = resolve_review(saved.review, action)
        if transition.status != "accepted":
            return _preparation("refused", "undo_" + transition.code)
        return saved.model_copy(
            update={"review": transition.plan, "code": "undo_choice_recorded"}
        )
    except OSError, ValueError, TypeError, UnicodeError:
        return _preparation("unavailable", "undo_resolution_unavailable")


def execute_undo(
    vault, preparation, *, cancel=None, progress=None, executor=None, _owner=None
):
    """Start one new Undo operation through the existing staged apply executor."""
    start = time.monotonic()
    result = None
    try:
        saved = VaultUndoPreparation.model_validate(preparation)
        if (
            saved.status != "offered"
            or (
                select_review_effects(saved.review)
                if _owner is None
                else _owner._session.select_review_effects(saved.review)
            ).status
            != "selected"
        ):
            return _outcome("refused", "undo_review_required", start=start, kind="undo")
        root = Path(vault).absolute()
        if _owner is not None:
            history = _owner._observe(vault, _recovery=True)
            if (
                history.status != "intact"
                or history.admission.status != "supported"
                or _owner.observed._terminal is None
            ):
                return _outcome(
                    "refused", "undo_review_stale", start=start, kind="undo"
                )
        observed, observation = (
            _inspect_update_observation(root)
            if _owner is None
            else (_owner.observed._recovery_status, _owner.observed._terminal)
        )
        fresh, target = _prepare_observed(root, observed, observation, _owner=_owner)
        if target is None or not _same_review(fresh, saved):
            return _outcome("refused", "undo_review_stale", start=start, kind="undo")
        association = observation.checkpoint.locator.association
        export = None if _owner is None else _owner._publication_export(saved.review)
        with (
            ExitStack() as owners,
            _retained_source(root, _Git(root), target.lineage.source) as source,
        ):
            try:
                result = _apply_reviewed_update(
                    root,
                    source,
                    review=saved.review,
                    vault_id=association.vault_id,
                    import_id=association.import_id,
                    cancel=cancel,
                    progress=progress,
                    executor=executor,
                    undo_target=target,
                    **(
                        {}
                        if export is None
                        else {"_owned_export": export, "_owners": owners}
                    ),
                )
            except _OwnedCleanupFailure as failure:
                result = failure.result
    except OSError, ValueError, TypeError, UnicodeError:
        if result is None:
            return _outcome("refused", "undo_unavailable", start=start, kind="undo")
        result = result.model_copy(
            update={
                "message": result.message
                + " Retained source cleanup reported an error.",
            }
        )
    message = result.message
    if result.status == "undone":
        kept = sorted(
            {
                approval.target_path
                for approval in saved.review.approvals
                if approval.choice == "current"
            }
        )
        if kept:
            message += " Kept reviewed current content at " + ", ".join(kept) + "."
    return result.model_copy(
        update={
            "message": message,
            "elapsed_ms": max(0, int((time.monotonic() - start) * 1000)),
        }
    )
