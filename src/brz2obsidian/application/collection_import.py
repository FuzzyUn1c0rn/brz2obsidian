"""Application review of a rendered collection within an existing vault."""

import hashlib
import tempfile
from pathlib import Path
from uuid import uuid4

from brz2obsidian.application.checkpoint_payload_contracts import (
    CheckpointPayloadRequest,
)
from brz2obsidian.contracts import SourceIdentity
from brz2obsidian.core import prepare_review, refresh_review, validate_review
from brz2obsidian.publication.vault_admission import _safe_relative, _walk
from brz2obsidian.publication.vault_history import _Git, _read, collection_baselines
from brz2obsidian.publication.vault_native import available_memory, observe_file

from .update_contracts import UpdatePreparation, UpdateResult, update_application_status
from .update_facts import CollectionImportConflict, output_identity, record
from .update_lifecycle import (
    _materialize,
    _memory,
    _observed_facts,
    _prepared,
    _scope_review,
    _scoped,
    _stale_slots,
    _subjects,
)


def _refused(code, *, history=None, action="inspect_history", kind="collection_import"):
    return UpdateResult(
        kind=kind,
        status="refused",
        code=code,
        next_actions=(action,),
        history_retained=history is not None and history.status == "intact",
    )


def _read_rendered(root, record_path):
    directory, _, name = record_path.rpartition("/")
    if name != "migration-record.json" or not _safe_relative(record_path):
        raise ValueError("Invalid collection record path")
    available = available_memory() // 4
    payload = {}
    for parent, _, filenames in _walk(root):
        for name in filenames:
            path = Path(parent) / name
            relative = path.relative_to(root).as_posix()
            if (
                not _safe_relative(relative)
                or directory
                and not relative.startswith(directory + "/")
            ):
                raise ValueError("Rendered output is outside the import scope")
            info, _, raw, _ = observe_file(root, path, prefix_limit=available + 1)
            if info.st_size > available or info.st_size != len(raw):
                raise OSError("Rendered collection exceeds the review resources")
            payload[relative] = raw
            available -= len(raw)
    return payload


def _baseline(operations, history, observed, record_path):
    checkpoint = history.checkpoint
    if checkpoint is None or checkpoint.status != "valid":
        raise CollectionImportConflict("collection_not_active")
    key = observed.module_id, observed.source_id
    selected = collection_baselines(checkpoint).get(key)
    if selected is None:
        raise CollectionImportConflict("collection_not_active")
    commit, manifest = selected
    if (manifest.collection_record_path or "migration-record.json") != record_path:
        raise CollectionImportConflict("collection_scope_changed")
    size = sum(row.size for row in manifest.source)
    retained = operations.read_checkpoint_payload(
        history.admission.vault,
        locator=checkpoint.locator,
        collection=key,
        requests=tuple(
            CheckpointPayloadRequest(path=row.path, limit=row.size)
            for row in manifest.source
        ),
        byte_limit=size,
    )
    if retained.status != "available":
        raise OSError(retained.code)
    payload = {row.path: row.data for row in retained.chunks}
    if output_identity(record(payload, record_path)) != manifest.identity:
        raise OSError("Collection baseline does not match retained identity")
    return payload, manifest, commit


def _baseline_review(history, baseline):
    if baseline is None:
        return None
    _, manifest, commit = baseline
    checkpoint = history.checkpoint
    if commit == checkpoint.locator.commit and manifest.discarded_review is None:
        return checkpoint.review
    target = manifest.discarded_review or commit
    root = Path(history.admission.vault)
    current, retained = _read(root, _Git(root), targets={target})
    if current.locator != checkpoint.locator:
        raise OSError("Collection baseline changed during review")
    return retained[target][1]


def _collection_facts(
    history, baseline, incoming, record_path, proposal_id, generation
):
    retained = _baseline_review(history, baseline)
    memory = (
        ()
        if retained is None
        else retained.saved.plan.producer_facts.source_version_memory
        if baseline[1].discarded_review is not None
        or baseline[1].boundary == "local"
        and baseline[1].reviewed_source is not None
        else _memory(retained.saved.plan)
    )
    return _observed_facts(
        history,
        baseline[0] if baseline is not None else None,
        incoming,
        proposal_id=proposal_id,
        generation=generation,
        record_path=record_path,
        source_memory=memory,
        retained_review=retained,
    )


def prepare_collection_import(operations, vault, source, *, record_path, update=False):
    root, source = Path(vault).absolute(), Path(source).absolute()
    kind = "source_update" if update else "collection_import"
    try:
        if source == root or root in source.parents or source in root.parents:
            return _refused("distinct_source_required")
        history = operations.inspect_history(root)
        if history.admission.repository.kind == "none":
            return _refused(
                "git_initialization_required", action="review_initialization"
            )
        if history.admission.status != "supported" or history.status == "unavailable":
            return _refused(
                "recovery_first"
                if history.admission.status == "recovery_first"
                else "current_history_unavailable",
                history=history,
            )
        if not update and "/" not in record_path:
            return _refused("collection_scope_required", history=history)
        incoming = _read_rendered(source, record_path)
        observed = SourceIdentity.model_validate(
            record(incoming, record_path)["source_identity"]
        )
        checkpoint = history.checkpoint
        if checkpoint is not None and checkpoint.status == "valid":
            if not update and collection_baselines(checkpoint).get(
                (observed.module_id, observed.source_id)
            ):
                return _refused("collection_already_active", history=history)
            if (
                checkpoint.manifest.boundary == "local"
                and checkpoint.manifest.reviewed_source
            ):
                return _refused(
                    "saved_review_pending",
                    history=history,
                    action="resume_update",
                    kind=kind,
                )
        baseline = (
            _baseline(operations, history, observed, record_path) if update else None
        )
        facts = _collection_facts(
            history, baseline, incoming, record_path, uuid4().hex, 1
        )
        history = _scoped(operations, history, facts)
        review = prepare_review(facts, preflight=history.admission.preflight)
        binding = _bind_payload(operations, source, review, incoming)
        return _prepared(
            history,
            source,
            binding,
            review,
            observed,
            collection_record_path=record_path,
        )
    except CollectionImportConflict as error:
        return _refused(str(error), action="resolve_import_conflict", kind=kind)
    except OSError, ValueError, TypeError, AttributeError, KeyError, StopIteration:
        return _refused("collection_review_unavailable", kind=kind)


def _bind_payload(operations, source, plan, incoming):
    binding = operations.observe_reviewed_source(source, plan)
    expected = tuple(
        (path, len(raw), hashlib.sha256(raw).hexdigest())
        for path, raw in sorted(incoming.items())
    )
    if tuple((row.path, row.size, row.sha256) for row in binding.files) != expected:
        raise CollectionImportConflict("source_payload_changed")
    return binding


def _review_source_inputs(operations, prepared, replacement):
    source = Path(
        prepared.payload_directory if replacement is None else replacement
    ).absolute()
    root = Path(prepared.vault).absolute()
    if source == root or root in source.parents or source in root.parents:
        raise CollectionImportConflict("distinct_source_required")
    if (
        replacement is None
        and operations.observe_reviewed_source(source, prepared.review)
        != prepared.source_binding
    ):
        raise CollectionImportConflict("source_payload_changed")
    incoming = _read_rendered(source, prepared.collection_record_path)
    observed = SourceIdentity.model_validate(
        record(incoming, prepared.collection_record_path)["source_identity"]
    )
    if (observed.module_id, observed.source_id) != (
        prepared.observed_source.module_id,
        prepared.observed_source.source_id,
    ):
        raise CollectionImportConflict("association_mismatch")
    if replacement is None and observed != prepared.observed_source:
        raise CollectionImportConflict("source_observation_mismatch")
    return source, incoming, observed


def _observe_review(operations, preparation, *, replacement=None):
    prepared = UpdatePreparation.model_validate(preparation)
    plan = prepared.review
    history = operations.inspect_history(prepared.vault)
    checkpoint = history.checkpoint
    locator = checkpoint.locator if checkpoint is not None else None
    if history.admission.status != "supported" or history.status == "unavailable":
        return history, _refused("current_history_unavailable", history=history)
    if prepared.locator != locator:
        return history, _refused("current_history_changed", history=history)
    if validate_review(plan).status != "accepted":
        return history, _refused("invalid_review", history=history)
    source, incoming, observed = _review_source_inputs(
        operations, prepared, replacement
    )
    baseline = (
        None
        if prepared.kind == "collection_import"
        else _baseline(operations, history, observed, prepared.collection_record_path)
    )
    facts = _collection_facts(
        history,
        baseline,
        incoming,
        prepared.collection_record_path,
        plan.proposal.proposal_id,
        plan.proposal.generation,
    )
    history = _scope_review(operations, history, facts, plan)
    changed = (
        facts != plan.producer_facts or history.admission.preflight != plan.preflight
    )
    stale = 0
    if changed:
        transition = refresh_review(
            plan,
            facts.model_copy(update={"generation": facts.generation + 1}),
            preflight=history.admission.preflight,
        )
        if transition.status != "accepted":
            return history, _refused(transition.code, history=history)
        stale = _stale_slots(plan, transition.plan)
        plan = transition.plan
    actual = _bind_payload(operations, source, plan, incoming)
    if replacement is None and actual != prepared.source_binding.model_copy(
        update={"generation": plan.proposal.generation}
    ):
        return history, _refused("source_payload_changed", history=history)
    return history, _prepared(
        history,
        source,
        actual,
        plan,
        observed,
        collection_record_path=prepared.collection_record_path,
        status="stale_review" if changed else "prepared_review",
        code="current_facts_changed" if changed else "current",
        stale=stale,
    )


def refresh_collection_review(operations, preparation, *, source=None):
    try:
        _, result = _observe_review(operations, preparation, replacement=source)
        if result.status == "stale_review" and result.ready and not result.stale:
            return result.model_copy(update={"status": "prepared_review"})
        return result.model_copy(update={"kind": preparation.kind})
    except CollectionImportConflict as error:
        return _refused(str(error), kind=preparation.kind)
    except OSError, ValueError, TypeError, AttributeError, KeyError, StopIteration:
        return _refused("current_inputs_unavailable", kind=preparation.kind)


def inspect_collection_authority(operations, preparation):
    try:
        history, current = _observe_review(operations, preparation)
    except CollectionImportConflict as error:
        return str(error)
    if current.code != "current":
        return current.code
    if (
        not history.admission.inventory_complete
        or history.admission.inventory != preparation.current_inventory
    ):
        return "current_inventory_changed"
    return None


def _capture_review(operations, history, current, *, progress):
    prepared = current.preparation
    plan = prepared.review
    association = prepared.locator.association if prepared.locator else None
    with tempfile.TemporaryDirectory(
        prefix="brz2obsidian-collection-baseline-"
    ) as empty:
        baseline = (
            Path(empty)
            if prepared.kind == "collection_import"
            else _materialized_baseline(operations, history, prepared, Path(empty))
        )
        captured = operations.capture_checkpoint(
            prepared.vault,
            baseline,
            vault_id=association.vault_id
            if association
            else "vault-" + plan.proposal.proposal_id,
            import_id=association.import_id
            if association
            else "import-" + plan.proposal.proposal_id,
            identity=plan.facts.baseline_identity,
            admission=history.admission,
            subjects=_subjects(plan.producer_facts, plan)
            if history.admission.preflight.consents
            else (),
            review=plan,
            source_binding=prepared.source_binding,
            review_source=prepared.payload_directory,
            observed_source=prepared.observed_source,
            collection_record_path=prepared.collection_record_path,
            progress=progress,
        )
    if captured.locator is None:
        return _refused(captured.code, history=history).model_copy(
            update={"capture": captured, "history_retained": captured.history_retained}
        )
    return current.model_copy(
        update={
            "code": "saved",
            "capture": captured,
            "history_retained": True,
            "checkpoint": captured.locator,
            "checkpoint_commit": captured.commit,
            "preparation": prepared.model_copy(update={"locator": captured.locator}),
        }
    )


def _materialized_baseline(operations, history, prepared, directory):
    payload, manifest, _ = _baseline(
        operations, history, prepared.observed_source, prepared.collection_record_path
    )
    return _materialize(
        payload,
        {row.path: row.mode for row in manifest.source},
        directory=directory / "baseline",
    )


def save_collection_review(
    operations, preparation, *, cancel=None, progress=None, apply=False
):
    try:
        history, current = _observe_review(operations, preparation)
        if current.code != "current":
            return current
        if apply and not current.ready:
            return current.model_copy(
                update={"status": "unresolved", "code": "review_not_ready"}
            )
        if cancel is not None and cancel():
            return current.model_copy(
                update={
                    "status": "cancelled_before_publication",
                    "code": "cancelled_before_publication",
                    "ready": False,
                    "publication": "not_published",
                }
            )
        saved = _capture_review(operations, history, current, progress=progress)
        if not apply or saved.code != "saved":
            return saved
        return _apply_saved(operations, saved, cancel=cancel, progress=progress)
    except CollectionImportConflict as error:
        return _refused(str(error), action="resolve_import_conflict")
    except OSError, ValueError, TypeError, AttributeError, KeyError, StopIteration:
        return _refused("collection_review_unavailable")


def _apply_saved(operations, saved, *, cancel, progress):
    prepared = saved.preparation
    association = prepared.locator.association
    applied = operations.apply_reviewed_update(
        prepared.vault,
        prepared.payload_directory,
        review=prepared.review,
        vault_id=association.vault_id,
        import_id=association.import_id,
        source_binding=prepared.source_binding,
        observed_source=prepared.observed_source,
        cancel=cancel,
        progress=progress,
    )
    return saved.model_copy(
        update={
            "status": update_application_status(applied),
            "code": applied.code,
            "summary": applied.message,
            "application": applied,
            "publication": applied.publication,
            "checkpoint": None,
            "checkpoint_commit": applied.result_commit
            or applied.checkpoint_commit
            or saved.checkpoint_commit,
            "preparation": None,
            "ready": False,
            "next_actions": ("review_recovery",) if applied.recovery_required else (),
        }
    )


def resume_collection_review(operations, history):
    checkpoint = history.checkpoint
    manifest = checkpoint.manifest
    plan = checkpoint.review.saved.plan
    kind = plan.facts.format_operation.kind
    try:
        incoming = {
            subject.path: subject.incoming.data
            for subject in plan.producer_facts.subjects
            if subject.incoming is not None
        }
        binding = manifest.reviewed_source
        if set(incoming) != {row.path for row in binding.files}:
            return _refused("saved_payload_mismatch", history=history, kind=kind)
        directory = _materialize(
            incoming, {row.path: row.mode for row in binding.files}
        )
        actual = operations.observe_reviewed_source(directory, plan)
        if actual.files != binding.files:
            return _refused("saved_payload_mismatch", history=history, kind=kind)
        prepared = _prepared(
            history,
            directory,
            actual,
            plan,
            manifest.observed_source,
            collection_record_path=manifest.collection_record_path
            or "migration-record.json",
        )
        _, current = _observe_review(operations, prepared.preparation)
        return (
            current.model_copy(update={"code": "resumed"})
            if current.code == "current"
            else current
        )
    except CollectionImportConflict as error:
        return _refused(str(error), history=history, kind=kind)
    except OSError, ValueError, TypeError, KeyError, AttributeError, StopIteration:
        return _refused("saved_update_unavailable", history=history, kind=kind)
