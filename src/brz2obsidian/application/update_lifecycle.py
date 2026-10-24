"""Physical source/current/baseline composition behind Operations."""

import hashlib
import io
import json
import os
import stat
import tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from brz2obsidian.contracts import (
    ExactContent,
    ImportedItemIdentity,
    RunMetadata,
    SourceGapDiagnostic,
    SourceIdentity,
    reconciliation_subject_id,
)
from brz2obsidian.core import (
    prepare_review,
    reconcile,
    refresh_review,
    resolve_review,
    resume_review,
    select_review_effects,
    validate_review,
)
from brz2obsidian.obsidian import inspect_text_candidate
from brz2obsidian.publication.vault_native import available_memory, observe_file

from .update_contracts import (
    UpdateComparison,
    UpdatePreparation,
    UpdateResult,
    UpdateReviewPage,
)
from .update_facts import assemble_facts, link_state, output_identity, record, target
from .vault_contracts import VaultSubject
from .workflow import Workflow


def _new_payload_directory():
    return Path(tempfile.mkdtemp(prefix="brz2obsidian-update-")) / "incoming"


def _refused(code, history=None, *, action="inspect_history"):
    findings = history.admission.findings if history is not None else ()
    if any(row.policy == "git" for row in findings):
        action = "setup_git"
    return UpdateResult(
        status="refused",
        code=code,
        summary=findings[0].message
        if findings
        else "Review the current source and vault history before continuing.",
        next_actions=(action,),
        history_retained=history is not None and history.status == "intact",
        findings=tuple(row.code for row in findings),
    )


def _history(operations, vault):
    history = operations.inspect_history(vault)
    if history.admission.status == "recovery_first":
        return history, UpdateResult(
            status="recovery_required",
            code="recovery_first",
            next_actions=("review_recovery",),
            history_retained=True,
        )
    if history.status == "absent" or history.admission.repository.kind == "none":
        return history, _refused(
            "onboarding_required", history, action="review_onboarding"
        )
    if history.status != "intact" or history.admission.status != "supported":
        return history, _refused("history_unavailable", history)
    identity = history.checkpoint.manifest.identity
    if identity.output_format != 7:
        return history, _refused(
            "format_transition_required", history, action="review_format_transition"
        )
    policy = operations._configured_workflow().binding.policy
    if (
        identity.module_id,
        identity.profile_id,
        identity.profile_version,
    ) != (
        policy.module_id,
        policy.profile_id,
        policy.profile_version,
    ):
        return history, _refused(
            "source_profile_unavailable", history, action="review_format_transition"
        )
    if identity.settings_digest != hashlib.sha256(b"{}").hexdigest():
        return history, _refused(
            "configuration_transition_required", history, action="review_configuration"
        )
    return history, None


def _read_physical(root, rows):
    rows = tuple(
        row
        for row in rows
        if getattr(row, "exclusion", None) not in ("cache", "temporary")
    )
    if sum(row.size for row in rows) > available_memory() // 4:
        raise ValueError("comparison_resources_unavailable")
    result = {}
    for row in rows:
        sink = io.BytesIO()
        info, digest, _, physical_identity = observe_file(
            root, Path(root) / row.path, prefix_limit=0, sink=sink
        )
        if (info.st_size, digest) != (row.size, row.sha256):
            raise ValueError("observed_payload_changed")
        mode = "100755" if os.name != "nt" and info.st_mode & stat.S_IXUSR else "100644"
        if (
            getattr(row, "mode", mode) != mode
            or getattr(row, "identity", physical_identity) != physical_identity
        ):
            raise ValueError("observed_identity_changed")
        result[row.path] = sink.getvalue()
    return result


def _read_source(operations, vault, checkpoint):
    # One finite request verifies the current complete owned manifest once.
    from .checkpoint_payload_contracts import CheckpointPayloadRequest

    rows = checkpoint.manifest.source
    budget = sum(row.size for row in rows)
    if budget > available_memory() // 4:
        raise ValueError("comparison_resources_unavailable")
    result = operations.read_checkpoint_payload(
        vault,
        locator=checkpoint.locator,
        role="source",
        requests=tuple(
            CheckpointPayloadRequest(path=row.path, offset=0, limit=row.size)
            for row in rows
        ),
        byte_limit=budget,
    )
    if result.status != "available":
        raise ValueError(result.code)
    return {row.path: row.data for row in result.chunks}


class _ExcludedDependency(ValueError):
    """Excluded authored bytes require current tracking review before storage."""


def _observed_facts(history, baseline, incoming, **identity):
    inventory = history.admission.inventory
    managed = set(baseline) | set(incoming)
    current = _read_physical(
        history.admission.vault,
        tuple(
            row
            for row in inventory
            if row.path in managed or row.path.lower().endswith(".md")
        ),
    )

    def assembled():
        return assemble_facts(
            baseline, incoming, current, current_inventory=inventory, **identity
        )

    facts = assembled()
    context = facts.link_context
    targets = {row.target_id: row for row in context.current_targets}
    graph = {}
    for document in context.current_documents + context.incoming_documents:
        for occurrence in document.occurrences:
            for target_id in (
                occurrence.meaning.target_id,
                *occurrence.meaning.candidates,
            ):
                if target_id is not None:
                    graph.setdefault(document.document_id, set()).add(target_id)
                    graph.setdefault(target_id, set()).add(document.document_id)
    related = {key for key in targets if key.startswith("subject:")}
    by_path = {row.canonical_path: row.target_id for row in targets.values()}
    # Identity suggestions remain suggestions, but their exact candidate files
    # are consumed evidence and cannot be discarded as unrelated context.
    if any(
        row.excluded and row.path not in managed and row.path.lower().endswith(".md")
        for row in inventory
    ):
        for change in reconcile(facts).changes:
            related.update(
                by_path[candidate.current.path]
                for candidate in change.identity_review.candidates
                if candidate.current.path in by_path
            )
    prospective = tuple(
        path
        for subject in facts.subjects
        for path in (subject.path, subject.current.path)
    )
    for path, target_id in by_path.items():
        if path is None:
            continue
        normalized = target(path).normalized_path
        if any(
            normalized == target(other).normalized_path
            or normalized.startswith(target(other).normalized_path + "/")
            or target(other).normalized_path.startswith(normalized + "/")
            for other in prospective
        ):
            related.add(target_id)
    while True:
        expanded = related | {other for key in related for other in graph.get(key, ())}
        if expanded == related:
            break
        related = expanded
    needed = {targets[key].canonical_path for key in related if key in targets}
    additional = []
    removed = False
    documents = {row.source_path: row for row in context.current_documents}
    for row in inventory:
        if row.path in managed:
            continue
        if row.excluded:
            document = documents.get(row.path)
            if (
                row.path in needed
                or document is not None
                and document.status != "supported"
            ):
                raise _ExcludedDependency
            removed |= current.pop(row.path, None) is not None
        elif row.path in needed and row.path not in current:
            additional.append(row)
    if additional:
        current.update(_read_physical(history.admission.vault, additional))
    return assembled() if removed or additional else facts


def _baseline(checkpoint, source):
    if (
        checkpoint.manifest.boundary != "local"
        or checkpoint.review is None
        or checkpoint.manifest.reviewed_source is not None
    ):
        return source
    facts = checkpoint.review.saved.plan.producer_facts
    # Saved unresolved reviews retain complete exact originals in schema-1
    # review_content; the source role retains the complete incoming payload.
    rows = {(s.item_id, s.facet): s for s in facts.subjects}
    original_record = rows[
        ("support:migration-record.json", "content")
    ].baseline.content
    if original_record is None:
        raise ValueError("onboarding_required")
    old_record = json.loads(original_record.data)
    paths = {
        (row["original_identity"], "content"): row["relative_path"]
        for row in old_record["item_targets"]
        if row["created"]
    }
    paths.update(
        {
            (row["asset_id"], "asset"): row["relative_path"]
            for row in old_record["asset_targets"]
            if row["relative_path"] is not None
        }
    )
    result = {}
    for key, subject in rows.items():
        if subject.baseline.content is None:
            continue
        path = paths.get(
            key,
            subject.item_id.removeprefix("support:")
            if subject.item_id.startswith("support:")
            else None,
        )
        if path is None:
            raise ValueError("baseline_payload_unavailable")
        result[path] = subject.baseline.content.data
    return result


class _UpdateRenderer:
    """Retain the creation time of the same established Home bookmark."""

    def __init__(self, delegate, baseline):
        self.delegate = delegate
        self.baseline = baseline

    def render(self, plan, metadata):
        home = next(
            (
                row.relative_path
                for row in plan.item_targets
                if row.item_key == plan.analysis.entry_key
            ),
            None,
        )
        bookmarks = json.loads(self.baseline[".obsidian/bookmarks.json"])
        items = bookmarks.get("items", ())
        if len(items) == 1 and set(items[0]) == {"type", "ctime", "path", "title"}:
            old = items[0]
            if (
                old["type"] == "file"
                and old["path"] == home
                and old["title"] == "Home"
                and type(old["ctime"]) is int
                and old["ctime"] >= 0
                and old["ctime"]
                == record(self.baseline)["run_metadata"]["bookmark_time"]
            ):
                metadata = metadata.model_copy(update={"bookmark_time": old["ctime"]})
        return self.delegate.render(plan, metadata)


def _render(operations, source, baseline, *, metadata=None, directory=None):
    from .contracts import BrzSourceSelection

    workflow, reference = operations._selected_workflow(
        BrzSourceSelection(path=str(Path(source).absolute()))
    )
    metadata = workflow.metadata_factory() if metadata is None else metadata
    renderer = Workflow(
        workflow.binding,
        _UpdateRenderer(workflow.renderer, baseline),
        workflow.publisher,
        metadata_factory=lambda: metadata,
    )
    directory = _new_payload_directory() if directory is None else directory
    result = renderer.convert(reference, directory)
    if result.receipt is None or result.outcome in ("failed", "refused"):
        raise ValueError("incoming_source_refused")
    payload = _read_physical(
        directory,
        tuple(
            SimpleNamespace(path=row.relative_path, size=row.length, sha256=row.sha256)
            for row in result.receipt.manifest
        ),
    )
    equivalent = _equivalent_payload(baseline, payload)
    if equivalent:
        for path, raw in baseline.items():
            (directory / path).write_bytes(raw)
        payload = baseline
    return directory, payload, result.source_identity, equivalent


def _equivalent_payload(baseline, incoming):
    if set(baseline) != set(incoming):
        return False
    old, new = record(baseline), record(incoming)
    if (
        output_identity(old) != output_identity(new)
        or old["source_identity"]["snapshot_digest"]
        != new["source_identity"]["snapshot_digest"]
    ):
        return False
    old_sha = old["source_identity"]["source_sha256"]
    new_sha = new["source_identity"]["source_sha256"]
    # Physical ZIP hashes are provenance, not scoped source-content versions.
    # Only the physical ZIP observation and these three volatile run facts may
    # vary. Other metadata and authored text are compared without normalization.
    new["source_identity"]["source_sha256"] = old_sha
    for key in ("run_id", "run_time", "bookmark_time"):
        new["run_metadata"][key] = old["run_metadata"][key]
    if old != new:
        return False
    for path, raw in incoming.items():
        if path == "migration-record.json":
            continue
        if path == "MIGRATION REPORT.md":
            suffix = (
                "; scoped digest: "
                + new["source_identity"]["snapshot_digest"]
                + "; collection: "
            )
            raw = raw.replace(
                ("Source fingerprint: " + new_sha + suffix).encode(),
                ("Source fingerprint: " + old_sha + suffix).encode(),
                1,
            )
        if raw != baseline[path]:
            return False
    return True


def _prepared(
    history,
    directory,
    binding,
    review,
    observed_source,
    retained_provenance=False,
    *,
    source_ref=None,
    status="prepared_review",
    code="prepared",
):
    source_record = json.loads(
        next(
            subject.incoming.data
            for subject in review.facts.subjects
            if subject.item_id == "support:migration-record.json"
        )
    )
    gaps = tuple(
        SourceGapDiagnostic.model_validate_json(json.dumps(row))
        for row in source_record["source_gaps"]
    )
    intentional = tuple(
        row["relative_path"]
        for row in source_record["item_targets"]
        if not row["created"]
    )
    preparation = UpdatePreparation(
        schema_id="brz2obsidian.update-preparation",
        schema_version=1,
        vault=history.admission.vault,
        locator=history.checkpoint.locator,
        payload_directory=str(directory),
        source_ref=source_ref,
        source_binding=binding,
        observed_source=observed_source,
        retained_source_provenance=retained_provenance,
        source_gaps=gaps,
        intentional_targets=intentional,
        current_inventory=history.admission.inventory,
        review=review,
    )
    result = UpdateResult(
        status=status,
        code=code,
        operation_id=review.proposal.proposal_id,
        generation=review.proposal.generation,
        preparation=preparation,
        ready=review.ready,
        changes=len(review.proposal.changes),
        unresolved=len(review.requirements),
        summary=(
            f"{len(review.proposal.changes)} comparisons; "
            f"{len(review.requirements)} choices remain."
        ),
        next_actions=("apply_update",)
        if review.ready
        else ("resolve_update", "save_update"),
        recovery_gaps=history.admission.recovery_gaps,
        history_retained=True,
        checkpoint_commit=history.checkpoint.locator.commit,
    )
    return _configuration_route(result)


def _subjects(facts, review=None):
    paths = {}

    def add(path, subject_id):
        paths[path, subject_id] = VaultSubject(path=path, subject_id=subject_id)

    observed = (facts,) if review is None else (facts, review.facts)
    for current in observed:
        for subject in current.subjects:
            subject_id = reconciliation_subject_id(
                current.incoming_identity.module_id,
                current.incoming_identity.collection_id,
                subject.item_id,
                subject.facet,
            )
            for path in (subject.path, subject.current.path):
                add(path, subject_id)
    if review is not None:
        approvals = {a.change_id: a for a in review.approvals}
        views = {a.decision_id: a.candidate for a in review.attachment_applicability}
        context = review.producer_facts.link_context
        documents = (
            {}
            if context is None
            else {d.document_id: d for d in context.current_documents}
        )
        for change in review.proposal.changes:
            approval = approvals.get(change.change_id)
            candidate = (
                None
                if approval is None
                else views.get(approval.decision_id, approval.attachment_candidate)
            )
            if candidate is not None:
                for output in candidate.outputs:
                    add(output.path, change.subject_id)
                for document in candidate.documents:
                    prior = documents.get(document.document_id)
                    if prior is None or (prior.source_path, prior.content) != (
                        document.source_path,
                        document.content,
                    ):
                        add(document.source_path, change.subject_id)
            elif (change.result if approval is None else approval.result) is not None:
                add(
                    change.target_path if approval is None else approval.target_path,
                    change.subject_id,
                )
    return tuple(paths[key] for key in sorted(paths))


def _scoped(operations, history, facts, review=None):
    scoped = operations.inspect_history(
        history.admission.vault, subjects=_subjects(facts, review)
    )
    if (
        scoped.status != "intact"
        or scoped.admission.status != "supported"
        or scoped.checkpoint.locator != history.checkpoint.locator
        or scoped.admission.inventory != history.admission.inventory
    ):
        raise ValueError("current_scoped_admission_required")
    return scoped if scoped.admission.preflight.consents else history


def _scope_review(operations, history, facts, plan):
    current = plan
    if facts != plan.facts:
        provisional = refresh_review(
            plan,
            facts.model_copy(update={"generation": plan.proposal.generation + 1}),
            preflight=plan.preflight,
        )
        if provisional.status != "accepted":
            raise ValueError("current_selected_scope_unavailable")
        current = provisional.plan
    return _scoped(operations, history, facts, current)


def _materialize(payload, modes=None, *, directory=None):
    directory = _new_payload_directory() if directory is None else directory
    directory.mkdir(parents=True)
    for path, content in payload.items():
        UpdatePreparation.relative_vault_path(path)
        destination = directory / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        if modes is not None:
            destination.chmod(0o755 if modes[path] == "100755" else 0o644)
    return directory


def _memory(plan):
    records = {
        row.provenance.decision_id: row for row in plan.facts.source_version_memory
    }
    for approval in plan.approvals:
        if approval.source_memory is not None:
            row = approval.source_memory
            records[row.provenance.decision_id] = row
    return tuple(records.values())


def _producer_memory(checkpoint, proposal_id=None):
    if checkpoint.review is None:
        return ()
    saved = checkpoint.review.saved.plan
    if (
        checkpoint.manifest.boundary == "local"
        and checkpoint.manifest.reviewed_source is not None
        and saved.proposal.proposal_id == proposal_id
    ):
        return saved.facts.source_version_memory
    return _memory(saved)


def _configuration_route(result):
    prepared = result.preparation
    if (
        prepared is None
        or not prepared.review.ready
        or result.status in ("refused", "stale_review", "failed")
    ):
        return result
    selected = select_review_effects(prepared.review)
    if selected.status != "selected":
        return result
    current = prepared.review.producer_facts.identity_inventory
    changed = any(path.startswith(".obsidian/") for path in selected.remove_paths)
    for row in selected.files:
        if not row.path.startswith(".obsidian/"):
            continue
        matching = tuple(entry for entry in current if entry.current.path == row.path)
        changed |= (
            len(matching) != 1
            or matching[0].current.content is None
            or matching[0].current.content.data != row.content.data
        )
    if not changed:
        return result
    return result.model_copy(
        update={
            "status": "unresolved",
            "code": "separate_configuration_operation_required",
            "ready": False,
            "summary": "Obsidian configuration changes require the separate reviewed configuration operation.",
            "next_actions": ("review_configuration",),
        }
    )


def _text_choice(plan, change, choice, edited):
    if choice == "edited":
        if edited is None:
            raise ValueError("Edited bytes are required")
        content = ExactContent(data=edited)
    else:
        content = change.incoming
    if content is None:
        return None
    context = plan.producer_facts.link_context
    document_id = next(
        (
            row.document_id
            for row in context.current_documents
            if row.source_path == change.target_path
        ),
        "subject:" + change.item_id + ":" + change.facet,
    )
    own = next(
        (t for t in context.current_targets if t.canonical_path == change.target_path),
        None,
    )
    states = context.incoming_target_facts
    targets = context.incoming_targets
    for approval in plan.approvals:
        candidate = approval.attachment_candidate
        if candidate is None:
            continue
        selected_ids = {output.target_id for output in candidate.outputs}
        targets = tuple(t for t in targets if t.target_id not in selected_ids) + tuple(
            t for t in candidate.targets if t.target_id in selected_ids
        )
        states = tuple(s for s in states if s.target_id not in selected_ids) + tuple(
            s for s in candidate.target_facts if s.target_id in selected_ids
        )
    if own is not None:
        observed = link_state(
            content,
            target_id=own.target_id,
            existence="present",
            membership_targets=targets,
        )
        states = tuple(s for s in states if s.target_id != own.target_id) + (observed,)
    return inspect_text_candidate(
        content,
        identity=ImportedItemIdentity(
            collection_id=plan.facts.incoming_identity.collection_id,
            module_id=plan.facts.incoming_identity.module_id,
            item_id=change.item_id,
        ),
        target=target(change.target_path),
        output_format=7,
        source_path=change.target_path,
        document_id=document_id,
        path_mode="vault",
        link_targets=targets,
        link_target_facts=states,
        link_inventory=context.inventory,
        membership_targets=targets,
    )


def resolve_update(operations, preparation, action, *, edited=None):
    try:
        preparation = UpdatePreparation.model_validate(preparation)
        plan = preparation.review
        if (
            action.candidate is None
            and action.domain
            in ("text", "configuration", "format", "mapping", "restoration")
            and action.choice in ("incoming", "edited", "restore_incoming")
        ):
            change = next(
                row
                for row in plan.proposal.changes
                if row.change_id == action.change_id
            )
            action = action.model_copy(
                update={"candidate": _text_choice(plan, change, action.choice, edited)}
            )
        transition = resolve_review(plan, action)
        result_plan = transition.plan
        binding = preparation.source_binding.model_copy(
            update={"generation": result_plan.proposal.generation}
        )
        prepared = preparation.model_copy(
            update={"review": result_plan, "source_binding": binding}
        )
        result = UpdateResult(
            status="stale_review"
            if transition.status == "stale"
            else "refused"
            if transition.status == "refused"
            else "prepared_review"
            if result_plan.ready
            else "unresolved",
            code=transition.code,
            operation_id=result_plan.proposal.proposal_id,
            generation=result_plan.proposal.generation,
            preparation=prepared,
            ready=transition.status == "accepted" and result_plan.ready,
            changes=len(result_plan.proposal.changes),
            unresolved=len(result_plan.requirements),
            history_retained=True,
            checkpoint_commit=preparation.locator.commit,
            next_actions=("apply_update",)
            if result_plan.ready
            else ("resolve_update", "save_update"),
        )
        return _configuration_route(result)
    except OSError, ValueError, KeyError, TypeError, StopIteration, AttributeError:
        return _refused("invalid_review_action")


def refresh_update(operations, preparation, *, source=None):
    try:
        preparation = UpdatePreparation.model_validate(preparation)
        if source is None:
            return _reobserve(operations, preparation)[1]
        history, stopped = _history(operations, preparation.vault)
        if stopped is not None:
            return stopped
        if history.checkpoint.locator.association != preparation.locator.association:
            return _refused("association_mismatch", history)
        retained = _read_source(operations, preparation.vault, history.checkpoint)
        baseline = _baseline(history.checkpoint, retained)
        directory, incoming, observed, reused = _render(operations, source, baseline)
        facts = _observed_facts(
            history,
            baseline,
            incoming,
            proposal_id=preparation.review.proposal.proposal_id,
            generation=preparation.review.proposal.generation + 1,
            source_memory=_producer_memory(
                history.checkpoint, preparation.review.proposal.proposal_id
            ),
        )
        history = _scope_review(operations, history, facts, preparation.review)
        transition = refresh_review(
            preparation.review, facts, preflight=history.admission.preflight
        )
        if transition.status != "accepted":
            return _refused(transition.code, history)
        binding = operations.observe_reviewed_source(directory, transition.plan)
        return _prepared(
            history,
            directory,
            binding,
            transition.plan,
            observed,
            reused,
            source_ref=str(Path(source).absolute()),
        )
    except _ExcludedDependency:
        return _refused(
            "excluded_dependency_requires_tracking", action="review_tracking"
        )
    except OSError, ValueError, KeyError, TypeError, AttributeError:
        return _refused("refresh_unavailable")


def save_update(operations, preparation):
    try:
        history, current = _reobserve(operations, preparation)
        if history is None or current.status == "stale_review":
            return current
        prepared = current.preparation
        baseline = _read_source(operations, prepared.vault, history.checkpoint)
        association = prepared.locator.association
        with tempfile.TemporaryDirectory(prefix="brz2obsidian-baseline-") as owned:
            source = _materialize(
                baseline,
                {r.path: r.mode for r in history.checkpoint.manifest.source},
                directory=Path(owned) / "incoming",
            )
            captured = operations.capture_checkpoint(
                prepared.vault,
                source,
                vault_id=association.vault_id,
                import_id=association.import_id,
                identity=prepared.review.facts.baseline_identity,
                admission=history.admission,
                subjects=_subjects(prepared.review.producer_facts, prepared.review)
                if history.admission.preflight.consents
                else (),
                review=prepared.review,
                source_binding=prepared.source_binding,
                review_source=prepared.payload_directory,
                observed_source=prepared.observed_source,
            )
        if captured.status not in ("captured", "unchanged"):
            return _refused(captured.code, history).model_copy(
                update={
                    "history_retained": captured.history_retained
                    or current.history_retained,
                    "checkpoint_commit": captured.commit,
                }
            )
        if captured.locator is None:
            return _refused("saved_history_unavailable", history)
        locator = captured.locator
        return current.model_copy(
            update={
                "code": "saved",
                "preparation": prepared.model_copy(update={"locator": locator}),
                "checkpoint_commit": captured.commit,
                "checkpoint": locator,
            }
        )
    except OSError, ValueError, KeyError, TypeError, AttributeError:
        return _refused("save_unavailable")


def load_update(operations, vault):
    history, stopped = _history(operations, vault)
    if stopped is not None:
        return stopped
    checkpoint = history.checkpoint
    if checkpoint.review is None or checkpoint.manifest.reviewed_source is None:
        return _refused("saved_update_unavailable", history)
    plan = checkpoint.review.saved.plan
    return UpdateResult(
        status="unresolved",
        code="revalidation_required",
        operation_id=plan.proposal.proposal_id,
        generation=plan.proposal.generation,
        loaded=checkpoint.review,
        changes=len(plan.proposal.changes),
        unresolved=len(plan.requirements),
        next_actions=("resume_update",),
        history_retained=True,
        checkpoint_commit=checkpoint.locator.commit,
        checkpoint=checkpoint.locator,
        vault=history.admission.vault,
    )


def resume_update(operations, vault):
    try:
        history, stopped = _history(operations, vault)
        if stopped is not None:
            return stopped
        checkpoint = history.checkpoint
        if checkpoint.review is None or checkpoint.manifest.reviewed_source is None:
            return _refused("saved_update_unavailable", history)
        loaded = checkpoint.review
        binding = checkpoint.manifest.reviewed_source
        plan = loaded.saved.plan
        incoming = {
            s.path: s.incoming.data
            for s in plan.facts.subjects
            if s.incoming is not None
        }
        if tuple(
            sorted(
                (path, len(raw), hashlib.sha256(raw).hexdigest())
                for path, raw in incoming.items()
            )
        ) != tuple((r.path, r.size, r.sha256) for r in binding.files):
            return _refused("saved_payload_mismatch", history)
        directory = _materialize(incoming, {r.path: r.mode for r in binding.files})
        baseline = _read_source(operations, vault, checkpoint)
        facts = _observed_facts(
            history,
            baseline,
            incoming,
            proposal_id=plan.proposal.proposal_id,
            generation=plan.proposal.generation,
            source_memory=plan.facts.source_version_memory,
        )
        history = _scope_review(operations, history, facts, plan)
        if facts != plan.facts or history.admission.preflight != plan.preflight:
            facts = facts.model_copy(update={"generation": facts.generation + 1})
        resumed = resume_review(loaded, facts, preflight=history.admission.preflight)
        if resumed.status != "resumed":
            return _refused(resumed.code, history)
        fresh_binding = operations.observe_reviewed_source(directory, resumed.plan)
        observed = (
            checkpoint.manifest.observed_source
            or SourceIdentity.model_validate_json(
                json.dumps(record(incoming)["source_identity"])
            )
        )
        return _prepared(
            history,
            directory,
            fresh_binding,
            resumed.plan,
            observed,
            observed.source_sha256
            != record(incoming)["source_identity"]["source_sha256"],
            code=resumed.code,
        )
    except _ExcludedDependency:
        return _refused(
            "excluded_dependency_requires_tracking", action="review_tracking"
        )
    except OSError, ValueError, KeyError, TypeError, AttributeError:
        return _refused("resume_unavailable")


def inspect_update_review(
    operations,
    preparation,
    *,
    proposal_id,
    generation,
    offset=0,
    limit=100,
    byte_offset=0,
    byte_limit=65536,
):
    def refused(code):
        return UpdateReviewPage(
            status="refused",
            code=code,
            proposal_id=proposal_id if type(proposal_id) is str else "",
            generation=generation if type(generation) is int and generation > 0 else 1,
            total=0,
            offset=max(offset, 0) if type(offset) is int else 0,
            next_offset=None,
            items=(),
            omitted=True,
        )

    try:
        preparation = UpdatePreparation.model_validate(preparation)
        plan = preparation.review
        if (
            proposal_id != plan.proposal.proposal_id
            or generation != plan.proposal.generation
        ):
            return refused("review_identity_changed")
        checkpoint = operations.read_checkpoint(preparation.vault)
        if checkpoint.status != "valid" or checkpoint.locator != preparation.locator:
            return refused("association_or_history_changed")
        if (
            any(
                type(v) is not int or v < 0
                for v in (offset, limit, byte_offset, byte_limit)
            )
            or not 1 <= limit <= 100
            or byte_limit > available_memory() // 16
            or validate_review(plan).status != "accepted"
        ):
            return refused("invalid_page")
        items = []
        remaining = byte_limit
        for change in plan.proposal.changes[offset : offset + limit]:
            UpdatePreparation.relative_vault_path(change.path)
            UpdatePreparation.relative_vault_path(change.target_path)
            versions = change.original, change.current, change.incoming, change.result
            unread = sum(
                content is not None and len(content.data) > byte_offset
                for content in versions
            )
            if byte_limit and unread > remaining:
                if not items:
                    return refused("insufficient_page_budget")
                break
            parts, omitted = [], False
            quota = remaining // unread if unread else 0
            for content in versions:
                if content is None:
                    parts.append(None)
                    continue
                raw = content.data[byte_offset : byte_offset + quota]
                remaining -= len(raw)
                omitted |= byte_offset != 0 or len(raw) != len(content.data)
                parts.append(raw)
            following_byte = byte_offset + max(
                (len(raw) for raw in parts if raw is not None), default=0
            )
            items.append(
                UpdateComparison(
                    change_id=change.change_id,
                    item_id=change.item_id,
                    facet=change.facet,
                    current_path=change.target_path,
                    incoming_path=change.path,
                    disposition=change.disposition,
                    original=parts[0],
                    current=parts[1],
                    incoming=parts[2],
                    result=parts[3],
                    offset=byte_offset,
                    next_byte_offset=following_byte
                    if any(
                        content is not None and len(content.data) > following_byte
                        for content in versions
                    )
                    else None,
                    omitted=omitted,
                )
            )
        following = offset + len(items)
        total = len(plan.proposal.changes)
        return UpdateReviewPage(
            status="available",
            code="available",
            proposal_id=proposal_id,
            generation=generation,
            total=total,
            offset=offset,
            next_offset=following if following < total else None,
            items=tuple(items),
            omitted=any(row.omitted for row in items) or following < total,
        )
    except ValueError, TypeError, AttributeError:
        return refused("invalid_review")


def prepare_update(operations, vault, source):
    history, stopped = _history(operations, vault)
    if stopped is not None:
        return stopped
    try:
        retained = _read_source(operations, vault, history.checkpoint)
        baseline = _baseline(history.checkpoint, retained)
        directory, incoming, observed_source, retained_provenance = _render(
            operations, source, baseline
        )
        association = history.checkpoint.locator.association
        if (
            record(incoming)["source_identity"]["source_id"],
            record(incoming)["source_identity"]["module_id"],
        ) != (association.collection_id, association.module_id):
            return _refused(
                "association_mismatch", history, action="choose_matching_source"
            )
        if output_identity(record(baseline)) != history.checkpoint.manifest.identity:
            return _refused("baseline_identity_mismatch", history)
        memory = _producer_memory(history.checkpoint)
        facts = _observed_facts(
            history,
            baseline,
            incoming,
            proposal_id=uuid4().hex,
            generation=1,
            source_memory=memory,
        )
        history = _scoped(operations, history, facts)
        review = prepare_review(facts, preflight=history.admission.preflight)
        binding = operations.observe_reviewed_source(directory, review)
        return _prepared(
            history,
            directory,
            binding,
            review,
            observed_source,
            retained_provenance,
            source_ref=str(Path(source).absolute()),
        )
    except _ExcludedDependency:
        return _refused(
            "excluded_dependency_requires_tracking", history, action="review_tracking"
        )
    except OSError, ValueError, KeyError, TypeError:
        return _refused(
            "preparation_unavailable", history, action="inspect_source_and_history"
        )


def _reobserve(operations, preparation):
    preparation = UpdatePreparation.model_validate(preparation)
    history, stopped = _history(operations, preparation.vault)
    if stopped is not None:
        return None, stopped
    if history.checkpoint.locator.association != preparation.locator.association:
        return None, _refused("association_mismatch", history)
    directory = Path(preparation.payload_directory).absolute()
    if (
        directory.name != "incoming"
        or directory.parent.parent != Path(tempfile.gettempdir())
        or not directory.parent.name.startswith("brz2obsidian-update-")
    ):
        return None, _refused("owned_payload_required", history)
    if validate_review(preparation.review).status != "accepted":
        return None, _refused("invalid_review", history)
    actual = operations.observe_reviewed_source(directory, preparation.review)
    if actual != preparation.source_binding:
        return None, _refused("source_payload_changed", history)
    retained = _read_source(operations, preparation.vault, history.checkpoint)
    baseline = _baseline(history.checkpoint, retained)
    if preparation.source_ref is not None:
        incoming_record = json.loads(
            next(
                s.incoming.data
                for s in preparation.review.facts.subjects
                if s.item_id == "support:migration-record.json"
            )
        )
        metadata = RunMetadata.model_validate_json(
            json.dumps(incoming_record["run_metadata"])
        )
        with tempfile.TemporaryDirectory(prefix="brz2obsidian-update-check-") as owned:
            fresh_directory, _, fresh_source, _ = _render(
                operations,
                preparation.source_ref,
                baseline,
                metadata=metadata,
                directory=Path(owned) / "incoming",
            )
            fresh_binding = operations.observe_reviewed_source(
                fresh_directory, preparation.review
            )
        if (
            fresh_source != preparation.observed_source
            or fresh_binding.files != actual.files
        ):
            return None, _refused(
                "incoming_source_changed", history, action="refresh_update"
            )
    else:
        saved_binding = history.checkpoint.manifest.reviewed_source
        if (
            saved_binding is None
            or saved_binding.proposal_id != preparation.review.proposal.proposal_id
            or saved_binding.files != actual.files
            or history.checkpoint.manifest.observed_source
            != preparation.observed_source
        ):
            return None, _refused("persisted_source_authority_required", history)
    incoming = _read_physical(directory, actual.files)
    try:
        facts = _observed_facts(
            history,
            baseline,
            incoming,
            proposal_id=preparation.review.proposal.proposal_id,
            generation=preparation.review.proposal.generation,
            source_memory=_producer_memory(
                history.checkpoint, preparation.review.proposal.proposal_id
            ),
        )
    except _ExcludedDependency:
        return None, _refused(
            "excluded_dependency_requires_tracking", history, action="review_tracking"
        )
    history = _scope_review(operations, history, facts, preparation.review)
    review = preparation.review
    changed = facts != review.facts or history.admission.preflight != review.preflight
    if changed:
        facts = facts.model_copy(update={"generation": facts.generation + 1})
        transition = refresh_review(
            review, facts, preflight=history.admission.preflight
        )
        if transition.status != "accepted":
            return None, _refused(transition.code, history)
        review = transition.plan
        actual = operations.observe_reviewed_source(directory, review)
    result = _prepared(
        history,
        directory,
        actual,
        review,
        preparation.observed_source,
        preparation.retained_source_provenance,
        source_ref=preparation.source_ref,
        status="stale_review" if changed else "prepared_review",
        code="current_facts_changed" if changed else "current",
    )
    return history, result


def apply_update(operations, preparation, *, cancel=None):
    try:
        history, current = _reobserve(operations, preparation)
        if history is None or current.status == "stale_review":
            return current
        if current.code == "separate_configuration_operation_required":
            return current
        if not current.ready:
            return current.model_copy(
                update={"status": "unresolved", "code": "review_not_ready"}
            )
        prepared = current.preparation
        if cancel is not None and cancel():
            return current.model_copy(
                update={
                    "status": "cancelled_before_publication",
                    "code": "cancelled_before_publication",
                    "ready": False,
                    "publication": "not_published",
                }
            )
        association = prepared.locator.association
        selected = select_review_effects(prepared.review)
        source_rows = tuple(
            (r.path, r.mode, r.size, r.sha256) for r in prepared.source_binding.files
        )
        retained_source = tuple(
            (r.path, r.mode, r.size, r.sha256)
            for r in history.checkpoint.manifest.source
        )
        accepted_tracking = {
            subject_id
            for requirement in prepared.review.preflight.consents
            if requirement.kind == "tracking"
            and any(
                decision.consent_id == requirement.consent_id
                and decision.kind == requirement.kind
                and decision.choice == "accept"
                for decision in prepared.review.consents
            )
            for subject_id in requirement.subjects
        }
        included_paths = {
            row.path for row in selected.files if row.subject_id in accepted_tracking
        }
        current_files = {
            row.path: row
            for row in history.admission.inventory
            if not row.excluded or row.path in included_paths
        }
        vault_rows = tuple(
            (r.path, r.mode, r.size, r.sha256) for r in current_files.values()
        )
        retained_vault = tuple(
            (r.path, r.mode, r.size, r.sha256)
            for r in history.checkpoint.manifest.vault
        )
        retained_memory = (
            _memory(history.checkpoint.review.saved.plan)
            if history.checkpoint.review is not None
            else ()
        )
        same_memory = sorted(
            _memory(prepared.review), key=lambda row: row.provenance.decision_id
        ) == sorted(retained_memory, key=lambda row: row.provenance.decision_id)
        same_selected = all(
            row.path in current_files
            and len(row.content.data) == current_files[row.path].size
            and hashlib.sha256(row.content.data).hexdigest()
            == current_files[row.path].sha256
            for row in selected.files
        )
        if (
            selected.status == "selected"
            and not selected.remove_paths
            and source_rows == retained_source
            and vault_rows == retained_vault
            and same_memory
            and same_selected
        ):
            return UpdateResult(
                status="no_content_change",
                code="already_current",
                operation_id=prepared.review.proposal.proposal_id,
                generation=prepared.review.proposal.generation,
                changes=current.changes,
                recovery_gaps=current.recovery_gaps,
                history_retained=True,
                checkpoint_commit=history.checkpoint.locator.commit,
                checkpoint=history.checkpoint.locator,
                vault=prepared.vault,
                publication="not_published",
                summary="The source and vault are unchanged; no additional checkpoint was needed.",
            )
        applied = operations.apply_reviewed_update(
            prepared.vault,
            prepared.payload_directory,
            review=prepared.review,
            source_binding=prepared.source_binding,
            observed_source=prepared.observed_source,
            vault_id=association.vault_id,
            import_id=association.import_id,
            cancel=cancel,
        )
        status = {
            "cancelled": "cancelled_before_publication",
            "incomplete": "recovery_required",
            "content_complete": "recovery_required",
            "unknown": "publication_unknown",
        }.get(applied.status, applied.status)
        return UpdateResult(
            status=status,
            code=applied.code,
            operation_id=applied.operation_id,
            generation=prepared.review.proposal.generation,
            changes=current.changes,
            vault=prepared.vault,
            summary=applied.message,
            next_actions=("review_recovery",) if applied.recovery_required else (),
            history_retained=applied.history != "none",
            checkpoint_commit=applied.result_commit or applied.checkpoint_commit,
            publication=applied.publication,
            application=applied,
            recovery_gaps=history.admission.recovery_gaps,
        )
    except OSError, ValueError, KeyError, TypeError:
        return _refused("current_review_unavailable")
