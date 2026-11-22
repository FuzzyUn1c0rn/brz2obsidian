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

from brz2obsidian.content_fingerprints import canonical_equal
from brz2obsidian.content_values import same_content
from brz2obsidian.contracts import (
    QUALIFIED_OUTPUT_FORMATS,
    ExactContent,
    ImportedItemIdentity,
    RunMetadata,
    SourceGapDiagnostic,
    SourceIdentity,
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
from brz2obsidian.core.formats import obsolete_support_listing
from brz2obsidian.core.selected_effects import SelectedEffectsWork
from brz2obsidian.obsidian import inspect_text_candidate
from brz2obsidian.publication.vault_native import available_memory, observe_file

from .update_contracts import (
    UpdateComparison,
    UpdatePreparation,
    UpdateResult,
    UpdateReviewPage,
    update_application_status,
)
from .update_facts import assemble_facts, link_state, output_identity, record, target
from .update_subjects import review_subjects as _subjects
from .workflow import Workflow


def _new_payload_directory():
    return Path(tempfile.mkdtemp(prefix="brz2obsidian-update-")) / "incoming"


def _refused(code, history=None, *, action="inspect_history", preparation=None):
    findings = history.admission.findings if history is not None else ()
    if any(row.policy == "git" for row in findings):
        action = "setup_git"
    return UpdateResult(
        kind=preparation.kind
        if isinstance(preparation, UpdatePreparation)
        else "source_update",
        status="refused",
        code=code,
        summary=findings[0].message
        if findings
        else "Review the current source and vault history before continuing.",
        next_actions=(action,),
        history_retained=history is not None and history.status == "intact",
        findings=tuple(row.code for row in findings),
    )


def _retained_update_refusal(
    operations, history, *, onboarding, recorded_output_format
):
    from brz2obsidian.publication.vault_history import _MetadataCheckpoint

    checkpoint = history.checkpoint
    review_kind = (
        checkpoint.review.saved.plan.facts.format_operation.kind
        if checkpoint.review is not None
        else checkpoint.metadata[10]
        if type(checkpoint) is _MetadataCheckpoint and checkpoint.metadata is not None
        else None
    )
    if (
        history.checkpoint.manifest.boundary != "result"
        and review_kind == "format_transition"
    ):
        return _refused(
            "format_transition_review_required", history, action="resume_update"
        )
    onboarding_pending = (
        history.checkpoint.manifest.boundary != "result" and review_kind == "onboarding"
    )
    if onboarding and onboarding_pending:
        return None
    identity = history.checkpoint.manifest.identity
    workflow = operations._configured_workflow()
    target_format = (
        int(workflow.metadata_factory().renderer_version)
        if recorded_output_format not in QUALIFIED_OUTPUT_FORMATS
        else recorded_output_format
    )
    if identity.output_format != target_format:
        return _refused(
            "format_transition_required", history, action="review_format_transition"
        )
    policy = workflow.binding.policy
    if (
        identity.module_id,
        identity.profile_id,
        identity.profile_version,
    ) != (
        policy.module_id,
        policy.profile_id,
        policy.profile_version,
    ):
        return _refused(
            "source_profile_unavailable", history, action="review_format_transition"
        )
    if identity.settings_digest != hashlib.sha256(b"{}").hexdigest():
        return _refused(
            "configuration_transition_required", history, action="review_configuration"
        )
    if onboarding_pending:
        return _refused("onboarding_review_required", history, action="resume_update")
    return None


def _history(
    operations,
    vault,
    observed=None,
    *,
    onboarding=False,
    maintenance=False,
    new_operation=None,
    recorded_output_format=None,
):
    purpose = {"new_operation": new_operation} if new_operation is not None else {}
    history = (
        operations.inspect_history(vault, **purpose)
        if observed is None
        else observed.inspect(subjects=(), **purpose)
        if purpose
        else observed.history
    )
    if history.admission.status == "recovery_first":
        checkpoint = history.checkpoint
        locator = (
            checkpoint.locator
            if checkpoint is not None and checkpoint.status == "valid"
            else None
        )
        return history, UpdateResult(
            status="recovery_required",
            code="recovery_first",
            next_actions=("review_recovery",),
            history_retained=True,
            recovery_gaps=history.admission.recovery_gaps,
            vault=history.admission.vault,
            checkpoint=locator,
            checkpoint_commit=locator.commit if locator is not None else None,
        )
    if history.status == "absent" or history.admission.repository.kind == "none":
        return history, _refused(
            "onboarding_required", history, action="review_onboarding"
        )
    if history.status != "intact" or history.admission.status != "supported":
        return history, _refused("history_unavailable", history)
    # Maintenance deliberately replaces an unavailable generation; native history
    # and current admission above still have to be fully valid.
    if maintenance:
        return history, None
    return history, _retained_update_refusal(
        operations,
        history,
        onboarding=onboarding,
        recorded_output_format=recorded_output_format,
    )


def _read_physical(root, rows, *, _owner=None):
    rows = tuple(
        row
        for row in rows
        if getattr(row, "exclusion", None) not in ("cache", "temporary")
    )
    if _owner is not None:
        return _owner._physical_payload(root, rows)
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


def _read_source(operations, vault, checkpoint, observed=None, *, _owner=None):
    from .checkpoint_payload_contracts import CheckpointPayloadRequest

    rows = checkpoint.manifest.source
    if _owner is not None:
        return _owner._source_payload(checkpoint)
    budget = sum(row.size for row in rows)
    if budget > available_memory() // 4:
        raise ValueError("comparison_resources_unavailable")
    arguments = {
        "locator": checkpoint.locator,
        "role": "source",
        "requests": tuple(
            CheckpointPayloadRequest(path=row.path, offset=0, limit=row.size)
            for row in rows
        ),
        "byte_limit": budget,
    }
    result = (
        operations.read_checkpoint_payload(vault, **arguments)
        if observed is None
        else observed.read_payload(**arguments)
    )
    if result.status != "available":
        raise ValueError(result.code)
    return {row.path: row.data for row in result.chunks}


class _ExcludedDependency(ValueError):
    """Excluded authored bytes require current tracking review before storage."""


def _managed_observation_paths(baseline, incoming, retained_ownership, inventory):
    managed = set(baseline or ()) | set(incoming)
    if retained_ownership is not None:
        owned = {proof.source_path for proof in retained_ownership}
        assets = {
            row["relative_path"]
            for value in (baseline, incoming)
            for row in record(value)["asset_targets"]
            if row["relative_path"] is not None
        }
        managed.difference_update(assets - owned)
        managed.update(owned)
        if any(row.excluded and row.path in owned for row in inventory):
            raise _ExcludedDependency
    return managed


def _observation_link_graph(context):
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
    return graph


def _authored_observation_targets(context, inventory):
    excluded = {row.path for row in inventory if row.excluded}
    return {
        target_id
        for document in context.current_documents
        if document.source_path not in excluded
        for occurrence in document.occurrences
        for target_id in (occurrence.meaning.target_id, *occurrence.meaning.candidates)
        if target_id is not None
    }


def _required_observation_paths(facts, inventory, managed, *, _owner):
    context = facts.link_context
    targets = {row.target_id: row for row in context.current_targets}
    graph = _observation_link_graph(context)
    related = {key for key in targets if key.startswith("subject:")}
    by_path = {row.canonical_path: row.target_id for row in targets.values()}
    # Identity suggestions remain suggestions, but their exact candidate files
    # are consumed evidence and cannot be discarded as unrelated context.
    if any(
        row.excluded and row.path not in managed and row.path.lower().endswith(".md")
        for row in inventory
    ):
        reconciled = reconcile(facts) if _owner is None else _owner._reconcile(facts)
        for change in reconciled.changes:
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
    if facts.format_operation.kind == "collection_import":
        related.update(_authored_observation_targets(context, inventory))
    needed = {targets[key].canonical_path for key in related if key in targets}
    return needed


def _observed_facts(
    history,
    baseline,
    incoming,
    *,
    retained_ownership=None,
    retained_review=None,
    _owner=None,
    **identity,
):
    if retained_review is None and "record_path" not in identity:
        retained_review = (
            getattr(_owner, "_tip", None)
            if _owner is not None
            else getattr(getattr(history, "checkpoint", None), "review", None)
        )
    retired_note_ids = (
        retained_review.saved.plan.producer_facts.retired_note_ids
        if retained_review is not None and baseline is not None
        else ()
    )
    inventory = history.admission.inventory
    managed = _managed_observation_paths(
        baseline, incoming, retained_ownership, inventory
    )
    current = _read_physical(
        history.admission.vault,
        tuple(
            row
            for row in inventory
            if row.path in managed or row.path.lower().endswith(".md")
        ),
        _owner=_owner,
    )

    def assembled():
        return assemble_facts(
            baseline,
            incoming,
            current,
            current_inventory=inventory,
            retained_ownership=retained_ownership,
            retired_note_ids=retired_note_ids,
            _owner=_owner._session if _owner is not None else None,
            **identity,
        )

    facts = assembled()
    context = facts.link_context
    needed = _required_observation_paths(facts, inventory, managed, _owner=_owner)
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
                or facts.format_operation.kind != "collection_import"
                and document is not None
                and document.status != "supported"
            ):
                raise _ExcludedDependency
            removed |= current.pop(row.path, None) is not None
        elif row.path in needed and row.path not in current:
            additional.append(row)
    if additional:
        current.update(
            _read_physical(history.admission.vault, additional, _owner=_owner)
        )
    return assembled() if removed or additional else facts


def _baseline(checkpoint, source, *, _owner=None):
    review = _owner._tip if _owner is not None else checkpoint.review
    if review is None:
        return source
    facts = review.saved.plan.producer_facts
    manifest = checkpoint.manifest
    if (
        manifest.boundary == "prepared"
        and facts.format_operation.kind == "format_transition"
    ):
        if manifest.identity != facts.incoming_identity:
            raise ValueError("prepared_source_identity_mismatch")
        if facts.format_operation.established_baseline is None:
            return source
    elif manifest.boundary != "local" or manifest.reviewed_source is not None:
        return source
    # The prepared source role holds Incoming. The authenticated review
    # separately retains the exact old Original for an unpublished transition.
    rows = {(s.item_id, s.facet): s for s in facts.subjects}
    original_record = rows[
        ("support:migration-record.json", "content")
    ].baseline.content
    if original_record is None:
        raise ValueError("onboarding_required")
    old_record = json.loads(
        _owner._session._text(original_record).data
        if _owner is not None
        else original_record.data
    )
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
        result[path] = (
            _owner._session._text(subject.baseline.content)
            if _owner is not None and path == "migration-record.json"
            else subject.baseline.content
            if _owner is not None
            else subject.baseline.content.data
        )
    return result


class _UpdateRenderer:
    """Retain the creation time of the same established Home bookmark."""

    def __init__(self, delegate, baseline, *, _owner=None):
        self.delegate = delegate
        self.baseline = baseline
        self._owner = _owner

    def render(self, plan, metadata):
        if ".obsidian/bookmarks.json" not in self.baseline:
            return self.delegate.render(plan, metadata)
        home = next(
            (
                row.relative_path
                for row in plan.item_targets
                if row.item_key == plan.analysis.entry_key
            ),
            None,
        )
        bookmarks_raw = self.baseline[".obsidian/bookmarks.json"]
        if self._owner is not None:
            bookmarks_raw = self._owner._session._text(bookmarks_raw).data
        bookmarks = json.loads(bookmarks_raw)
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


def _render(
    operations,
    source,
    baseline,
    *,
    metadata=None,
    output_format=None,
    directory=None,
    _owner=None,
):
    from .contracts import BrzSourceSelection

    workflow, reference = operations._selected_workflow(
        BrzSourceSelection(path=str(Path(source).absolute()))
    )
    if metadata is None:
        metadata = workflow.metadata_factory()
    if output_format is not None:
        metadata = metadata.model_copy(update={"renderer_version": str(output_format)})
    renderer = Workflow(
        workflow.binding,
        _UpdateRenderer(workflow.renderer, baseline, _owner=_owner),
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
        _owner=_owner,
    )
    if _owner is not None:
        _owner._session._coadmit()
    equivalent = _equivalent_payload(baseline, payload, _owner=_owner)
    if equivalent:
        for path, raw in baseline.items():
            if _owner is None:
                (directory / path).write_bytes(raw)
            else:
                _owner._write_content(raw, directory / path)
        payload = baseline
    return directory, payload, result.source_identity, equivalent


def _equivalent_payload(baseline, incoming, *, _owner=None):
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
            report = (
                _owner._session._text(raw).data
                if _owner is not None
                else raw.data
                if hasattr(raw, "identity")
                else raw
            )
            raw = report.replace(
                ("Source fingerprint: " + new_sha + suffix).encode(),
                ("Source fingerprint: " + old_sha + suffix).encode(),
                1,
            )
        old_raw = baseline[path]
        if hasattr(old_raw, "identity") and type(raw) is bytes:
            old_raw = (
                _owner._session._text(old_raw).data
                if _owner is not None
                else old_raw.data
            )
        if (
            not canonical_equal(raw, old_raw)
            if hasattr(raw, "identity") and hasattr(old_raw, "identity")
            else raw != old_raw
        ):
            return False
    return True


def _stale_slots(before, after):
    """Count retired accepted slots that the current Core plan requires again."""

    def slots(plan):
        changes = {change.change_id: change for change in plan.proposal.changes}

        def slot(change_id, domain):
            change = changes.get(change_id)
            return (domain, change.subject_id) if change else (domain, change_id)

        accepted = {slot(row.change_id, row.domain) for row in plan.approvals}
        accepted.update(
            (row.kind, "consent:" + row.consent_id) for row in plan.consents
        )
        by_item = {
            (change.item_id, change.facet): change for change in changes.values()
        }
        for domain, decisions in (
            ("identity", plan.producer_facts.association_decisions),
            ("rename", plan.producer_facts.rename_decisions),
        ):
            for decision in decisions:
                change = by_item.get((decision.item_id, decision.facet))
                review = None if change is None else getattr(change, domain + "_review")
                if (
                    review is not None
                    and review.decision_id == decision.decision_id
                    and review.provenance == "explicit_user"
                    and review.status
                    in ("matched", "association_proposed", "accepted", "declined")
                ):
                    accepted.add((domain, change.subject_id))
        required = {slot(row.change_id, row.domain) for row in plan.requirements}
        return accepted, required

    prior, _ = slots(before)
    current, required = slots(after)
    return len((prior - current) & required)


def _review_explanation(result, *, review=None):
    """Expose approved guidance without copying authored names or references."""
    messages = (
        (
            "current_link_coverage_unavailable",
            "Some links in the current vault could not be verified.",
            "Review the current notes and attachment targets in All changes. Restore complete supported link evidence before applying.",
        ),
        (
            "selected_link_context_conflict",
            "The selected file versions have incompatible or unavailable reference evidence.",
            "Review the selected notes, attachment versions and reference choices in All changes. Choose compatible targets or repair the affected references, then refresh before applying.",
        ),
        (
            "selected_provider_cycle",
            "The selected appearance-category chains contain a cycle.",
            "Review the selected appearance-category chains and remove the repeated provider before applying. A nearer owned icon does not repair the independent cycle.",
        ),
        (
            "selected_provider_invalid",
            "A selected appearance-category chain reaches an invalid declaration.",
            "Follow the selected appearance-category chain to the note with the invalid declaration. Choose a valid category membership there or leave its appearance category blank. Repair or clear any invalid icon declaration, including a missing or unsuitable image target, then refresh the review. A nearer owned icon does not repair the independent declaration.",
        ),
    )
    if review is None and result.preparation is not None:
        review = result.preparation.review
    selected = tuple(
        row for row in messages if review is not None and row[0] in review.blockers
    )
    guidance = tuple(row[2] for row in selected)
    if review is not None:
        pending = {row.change_id for row in review.requirements}
        if any(
            change.change_id in pending and change.provenance.rule == "moved_navigation"
            for change in review.proposal.changes
        ):
            guidance += (
                (
                    "Edit the generated relationship to point to the reviewed note's "
                    "actual path. Keep authored links at their original destinations. "
                    "If an authored section repeats the generated heading and link, "
                    "give your section a distinct heading and keep its link unchanged. "
                    "If the generated row is missing, add it in the generated section."
                ),
            )
    if guidance:
        updates = {
            "summary": " ".join(row[1] for row in selected)
            if selected
            else result.summary,
            "guidance": (*guidance, *result.guidance)
            if isinstance(result.guidance, tuple)
            else " ".join((*guidance, result.guidance)),
        }
        if hasattr(result, "findings"):
            updates["findings"] = tuple(
                dict.fromkeys((*result.findings, *(row[0] for row in selected)))
            )
        return result.model_copy(update=updates)
    return result


def _prepared(
    history,
    directory,
    binding,
    review,
    observed_source,
    retained_provenance=False,
    *,
    source_ref=None,
    original_source_ref=None,
    collection_record_path=None,
    import_link_connections=(),
    status="prepared_review",
    code="prepared",
    stale=0,
    _owner=None,
):
    source_record = json.loads(
        next(
            subject.incoming.data
            for subject in review.facts.subjects
            if subject.item_id
            == "support:" + (collection_record_path or "migration-record.json")
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
    retained_notes = sum(
        s.source_still_reserved and s.current.existence == "present"
        for s in review.facts.subjects
    )
    retained_listings = tuple(
        s.path
        for s in review.facts.subjects
        if s.current.existence == "present"
        and obsolete_support_listing(review.facts, s)
    )
    preparation = UpdatePreparation(
        schema_id="brz2obsidian.update-preparation",
        schema_version=1,
        kind=review.facts.format_operation.kind,
        vault=history.admission.vault,
        locator=history.checkpoint.locator if history.checkpoint is not None else None,
        payload_directory=str(directory),
        source_ref=source_ref,
        original_source_ref=original_source_ref,
        collection_record_path=collection_record_path,
        import_link_connections=import_link_connections,
        source_binding=binding,
        observed_source=observed_source,
        retained_source_provenance=retained_provenance,
        source_gaps=gaps,
        intentional_targets=intentional,
        current_inventory=history.admission.inventory,
        review=review,
    )
    result = UpdateResult(
        kind=preparation.kind,
        status=status,
        code=code,
        operation_id=review.proposal.proposal_id,
        generation=review.proposal.generation,
        preparation=preparation,
        ready=review.ready,
        changes=len(review.proposal.changes),
        unresolved=len(review.requirements),
        stale=stale,
        summary=(
            f"{len(review.proposal.changes)} comparisons; "
            f"{len(review.requirements)} choices remain."
            + (
                f" {retained_notes} vault notes are retained for source items "
                "that still exist but no longer qualify for generated notes."
                if retained_notes
                else ""
            )
            + (
                " Retained vault listings omitted from the new generated output: "
                + ", ".join(retained_listings)
                + "."
                if retained_listings
                else ""
            )
        ),
        next_actions=("save_update",)
        if review.ready
        and preparation.kind == "onboarding"
        and preparation.locator is None
        and not review.facts.format_operation.automatic_merge
        else ("apply_update",)
        if review.ready
        else ("resolve_update", "save_update"),
        recovery_gaps=history.admission.recovery_gaps,
        history_retained=history.status == "intact",
        checkpoint_commit=preparation.locator.commit if preparation.locator else None,
        findings=("older_checkpoints_unavailable", "older_undo_unavailable")
        if preparation.kind == "onboarding"
        else (),
    )
    return _review_explanation(_configuration_route(result, _owner=_owner))


def _scoped(operations, history, facts, review=None, observed=None):
    subjects = _subjects(facts, review)
    purpose = (
        {"new_operation": "format_transition"}
        if facts.format_operation.kind == "format_transition"
        else {}
    )
    scoped = (
        operations.inspect_history(
            history.admission.vault, subjects=subjects, **purpose
        )
        if observed is None
        else observed.inspect(subjects=subjects, **purpose)
    )
    if (
        scoped.status != history.status
        or scoped.admission.status != "supported"
        or (scoped.checkpoint.locator if scoped.checkpoint else None)
        != (history.checkpoint.locator if history.checkpoint else None)
        or scoped.admission.inventory != history.admission.inventory
    ):
        raise ValueError("current_scoped_admission_required")
    return scoped if scoped.admission.preflight.consents else history


def _scope_review(operations, history, facts, plan, observed=None):
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
    return _scoped(operations, history, facts, current, observed)


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


def _producer_memory(checkpoint, proposal_id=None, *, _owner=None):
    if checkpoint.manifest.discarded_review is not None:
        discarded = (
            _owner._load_discarded_review(checkpoint)
            if _owner is not None
            else checkpoint._discarded_review
        )
        return discarded.saved.plan.producer_facts.source_version_memory
    retained = _owner._tip if _owner is not None else checkpoint.review
    if retained is None:
        return ()
    saved = retained.saved.plan
    if (
        checkpoint.manifest.boundary == "local"
        and checkpoint.manifest.reviewed_source is not None
        and saved.proposal.proposal_id == proposal_id
    ):
        return saved.facts.source_version_memory
    return _memory(saved)


def _configuration_route(result, *, _owner=None):
    if result.kind == "onboarding":
        from .onboarding import route_onboarding

        result = route_onboarding(result)
    prepared = result.preparation
    if (
        prepared is None
        or not prepared.review.ready
        or result.status in ("refused", "stale_review", "failed")
    ):
        return result
    selected = (
        select_review_effects(prepared.review)
        if _owner is None
        else _owner._session._drive(SelectedEffectsWork(prepared.review))
    )
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
            or not same_content(matching[0].current.content, row.content)
        )
    if not changed:
        return result
    if prepared.kind == "format_transition":
        from .format_configuration import configuration_effects_authorized

        if configuration_effects_authorized(prepared, selected):
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


def _canonical_text_lookup(plan, context, targets, states, *, _owner):
    if _owner is None:
        validated = validate_review(plan)
        canonical = validated.plan if validated.status == "accepted" else None
    else:
        canonical = _owner._session._replay(plan)
    if canonical is None:
        raise ValueError("The review plan is not canonical")
    selected = []
    versions = {
        row.change_id: (row, row.target_path, row.result)
        for row in canonical.proposal.changes
        if not row.requires_decision
    }
    for approval in canonical.approvals:
        if approval.domain not in ("text", "format", "mapping"):
            continue
        comparison = next(
            row
            for row in canonical.proposal.changes
            if row.change_id == approval.change_id
        )
        versions[comparison.change_id] = (
            comparison,
            approval.target_path,
            approval.result,
        )
    for comparison, selected_path, chosen in versions.values():
        matches = tuple(
            row
            for row in targets
            if row.identity is not None
            and row.identity.item_id == comparison.item_id
            and row.identity.collection_id == plan.facts.incoming_identity.collection_id
            and row.identity.module_id == plan.facts.incoming_identity.module_id
        )
        if comparison.facet != "content" or len(matches) != 1:
            continue
        owner = next(
            (
                row
                for row in (*context.current_targets, *targets)
                if row.target_id == matches[0].target_id
                and row.canonical_path == selected_path
            ),
            None,
        )
        if owner is None:
            continue
        targets = tuple(
            owner if row.target_id == owner.target_id else row for row in targets
        )
        selected.append((owner, chosen))
    for owner, chosen in selected:
        observed = link_state(
            chosen,
            target_id=owner.target_id,
            existence="present" if chosen is not None else "missing",
            membership_targets=targets,
            source_path=owner.canonical_path,
            output_format=plan.facts.incoming_identity.output_format,
            _owner=_owner._session if _owner is not None else None,
        )
        states = tuple(s for s in states if s.target_id != owner.target_id) + (
            observed,
        )
    return targets, states


def _text_choice(plan, change, choice, edited, *, _owner=None):
    if choice == "edited":
        if edited is None:
            raise ValueError("Edited bytes are required")
        content = ExactContent(data=edited)
    else:
        content = change.incoming
    if content is None:
        return None
    if _owner is not None:
        content = _owner._session._assembly_content(content, semantic=True)
    context = plan.producer_facts.link_context
    document_id = next(
        (
            row.document_id
            for row in (*context.current_documents, *context.incoming_documents)
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
    if plan.facts.incoming_identity.output_format in QUALIFIED_OUTPUT_FORMATS:
        targets, states = _canonical_text_lookup(
            plan, context, targets, states, _owner=_owner
        )
    if own is not None:
        observed = link_state(
            content,
            target_id=own.target_id,
            existence="present",
            membership_targets=targets,
            source_path=change.target_path,
            output_format=plan.facts.incoming_identity.output_format,
            _owner=_owner._session if _owner is not None else None,
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
        output_format=plan.facts.incoming_identity.output_format,
        source_path=change.target_path,
        document_id=document_id,
        path_mode="vault",
        link_targets=targets,
        link_target_facts=states,
        link_inventory=context.inventory,
        membership_targets=targets,
    )


def _current_path_choice(plan, change):
    """Interpret observed Current bytes at the explicitly selected prospective path."""
    facts = plan.producer_facts
    subject = next(
        row
        for row in facts.subjects
        if (row.item_id, row.facet) == (change.item_id, change.facet)
    )
    context = facts.link_context
    documents = tuple(
        row
        for row in context.current_documents
        if row.source_path == change.rename_review.current_path
        and row.content == change.current
    )
    owners = tuple(
        row
        for row in context.current_targets
        if row.canonical_path == change.rename_review.current_path
    )
    if len(documents) != 1 or len(owners) != 1:
        raise ValueError("Current path interpretation is unavailable")
    document, owner = documents[0], owners[0]
    prospective = owner.model_copy(
        update={
            "canonical_path": change.target_path,
            "target": subject.source_target,
            "representations": (change.target_path,),
        }
    )
    targets = tuple(
        prospective if row.target_id == owner.target_id else row
        for row in context.current_targets
    )
    observed = link_state(
        change.current,
        target_id=owner.target_id,
        existence="present",
        membership_targets=targets,
        source_path=change.target_path,
        output_format=facts.baseline_identity.output_format,
        qualify_roles=facts.incoming_identity.output_format in QUALIFIED_OUTPUT_FORMATS,
    )
    states = tuple(
        observed if row.target_id == owner.target_id else row
        for row in context.current_target_facts
    )
    return inspect_text_candidate(
        change.current,
        identity=ImportedItemIdentity(
            collection_id=facts.incoming_identity.collection_id,
            module_id=facts.incoming_identity.module_id,
            item_id=change.item_id,
        ),
        target=subject.source_target,
        output_format=facts.baseline_identity.output_format,
        source_path=change.target_path,
        document_id=document.document_id,
        path_mode=document.path_mode,
        link_targets=targets,
        link_target_facts=states,
        link_inventory=context.inventory,
        membership_targets=targets,
    )


def text_choice_action(plan, action, *, edited=None, _owner=None):
    if (
        action.domain == "text"
        and action.choice == "current"
        and action.candidate is None
    ):
        change = next(
            row for row in plan.proposal.changes if row.change_id == action.change_id
        )
        if (
            change.rename_review is not None
            and change.rename_review.status == "accepted"
        ):
            return action.model_copy(
                update={"candidate": _current_path_choice(plan, change)}
            )
    if (
        action.candidate is None
        and action.domain
        in ("text", "configuration", "format", "mapping", "restoration", "reversal")
        and action.choice in ("incoming", "edited", "restore_incoming", "reverse")
    ):
        change = next(
            row for row in plan.proposal.changes if row.change_id == action.change_id
        )
        if change.attachment_review is None:
            if action.domain == "reversal":
                from brz2obsidian.core.reversals import (
                    reversal_document_entry,
                    reversal_subject,
                    reversal_text_comparison,
                )

                subject = reversal_subject(plan.producer_facts, change)
                if action.choice == "reverse" and (
                    subject.attachment is not None
                    or reversal_document_entry(plan.producer_facts, subject) is not None
                ):
                    return action
                change = reversal_text_comparison(plan.producer_facts, change)
            action = action.model_copy(
                update={
                    "candidate": _text_choice(
                        plan,
                        change,
                        "incoming" if action.choice == "reverse" else action.choice,
                        edited,
                        _owner=_owner,
                    )
                }
            )
    return action


def resolve_update(operations, preparation, action, *, edited=None):
    try:
        preparation = UpdatePreparation.model_validate(preparation)
        plan = preparation.review
        from brz2obsidian.contracts import ReviewKeepCurrentGroup

        if not isinstance(action, ReviewKeepCurrentGroup):
            action = text_choice_action(plan, action, edited=edited)
        transition = resolve_review(plan, action)
        result_plan = transition.plan
        binding = preparation.source_binding.model_copy(
            update={"generation": result_plan.proposal.generation}
        )
        prepared = preparation.model_copy(
            update={"review": result_plan, "source_binding": binding}
        )
        result = UpdateResult(
            kind=preparation.kind,
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
            history_retained=preparation.locator is not None,
            checkpoint_commit=preparation.locator.commit
            if preparation.locator
            else None,
            next_actions=("save_update",)
            if result_plan.ready
            and prepared.kind == "onboarding"
            and prepared.locator is None
            and not result_plan.facts.format_operation.automatic_merge
            else ("apply_update",)
            if result_plan.ready
            else ("resolve_update", "save_update"),
        )
        return _review_explanation(_configuration_route(result))
    except OSError, ValueError, KeyError, TypeError, StopIteration, AttributeError:
        return _refused("invalid_review_action", preparation=preparation)


def refresh_update(operations, preparation, *, source=None):
    try:
        preparation = UpdatePreparation.model_validate(preparation)
        if preparation.collection_record_path is not None:
            from .collection_import import refresh_collection_review

            return refresh_collection_review(operations, preparation, source=source)
        if source is None:
            result = _reobserve(operations, preparation)[1]
            # Explicit Refresh may expose a newly complete review. Internal
            # Save/Apply reobservation still stops at its stale_review boundary.
            if result.status == "stale_review" and result.ready and not result.stale:
                result = result.model_copy(update={"status": "prepared_review"})
            return result
        with operations.inspect_update_inputs(preparation.vault) as observed:
            result = _refresh_source_update(
                operations, preparation, observed, source=source
            )
            return (
                result.model_copy(update={"kind": preparation.kind})
                if result.preparation is None
                else result
            )
    except OSError, ValueError, TypeError, AttributeError:
        return _refused(
            "current_inputs_unavailable",
            action="refresh_update",
            preparation=preparation,
        )


def _refresh_source_update(operations, preparation, observed, *, source):
    try:
        maintenance = preparation.kind == "format_transition"
        output_format = preparation.source_binding.incoming_identity.output_format
        history, stopped = _history(
            operations,
            preparation.vault,
            observed,
            maintenance=maintenance,
            new_operation="format_transition" if maintenance else None,
            recorded_output_format=output_format,
        )
        if stopped is not None:
            return stopped
        if history.checkpoint.locator.association != preparation.locator.association:
            return _refused("association_mismatch", history)
        retained = _read_source(
            operations, preparation.vault, history.checkpoint, observed
        )
        baseline = _baseline(history.checkpoint, retained)
        directory, incoming, observed_source, reused = _render(
            operations, source, baseline, output_format=output_format
        )
        if maintenance:
            from .format_transition import transition_facts

            facts = transition_facts(
                history,
                baseline,
                incoming,
                proposal_id=preparation.review.proposal.proposal_id,
                generation=preparation.review.proposal.generation + 1,
            )
        else:
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
        history = _scope_review(
            operations, history, facts, preparation.review, observed
        )
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
            observed_source,
            reused,
            source_ref=str(Path(source).absolute()),
            stale=_stale_slots(preparation.review, transition.plan),
        )
    except _ExcludedDependency:
        return _refused(
            "excluded_dependency_requires_tracking", action="review_tracking"
        )
    except ValueError as error:
        if preparation.kind == "format_transition" and error.args == (
            "format_source_changed",
        ):
            return _refused("format_source_changed", action="choose_source_reference")
        return _refused("refresh_unavailable")
    except OSError, KeyError, TypeError, AttributeError:
        return _refused("refresh_unavailable")


def save_update(operations, preparation, *, cancel=None, progress=None):
    try:
        from .vault_progress_contracts import report_progress

        report_progress(progress, "current_inspection")
        history, current, snapshot = _reobserve(operations, preparation, for_save=True)
        if history is None or current.status == "stale_review":
            return current
        prepared = current.preparation
        if prepared is not None and cancel is not None and cancel():
            return current.model_copy(
                update={
                    "status": "cancelled_before_publication",
                    "code": "cancelled_before_snapshot",
                    "ready": False,
                    "publication": "not_published",
                    "next_actions": ("continue_review", "save_update"),
                }
            )
        if prepared.kind == "onboarding":
            from .onboarding import save_onboarding

            return save_onboarding(operations, history, current, progress=progress)
        association = prepared.locator.association
        baseline, source_files = snapshot
        with tempfile.TemporaryDirectory(prefix="brz2obsidian-baseline-") as owned:
            source = _materialize(
                baseline,
                {r.path: r.mode for r in source_files},
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
                **({"progress": progress} if progress is not None else {}),
            )
        if captured.status not in ("captured", "unchanged"):
            return _refused(captured.code, history, preparation=prepared).model_copy(
                update={
                    "capture": captured,
                    "history_retained": captured.history_retained
                    or current.history_retained,
                    "checkpoint_commit": captured.commit,
                }
            )
        if captured.locator is None:
            return _refused(
                "saved_history_unavailable", history, preparation=prepared
            ).model_copy(update={"capture": captured})
        locator = captured.locator
        return current.model_copy(
            update={
                "code": "saved",
                "capture": captured,
                "preparation": prepared.model_copy(update={"locator": locator}),
                "checkpoint_commit": captured.commit,
                "checkpoint": locator,
            }
        )
    except OSError, ValueError, KeyError, TypeError, AttributeError:
        return _refused("save_unavailable", preparation=preparation)


def load_update(operations, vault):
    history, stopped = _history(operations, vault, onboarding=True, maintenance=True)
    if stopped is not None:
        return stopped
    checkpoint = history.checkpoint
    if not _saved_review_available(checkpoint):
        return _refused("saved_update_unavailable", history)
    plan = checkpoint.review.saved.plan
    return UpdateResult(
        kind=plan.facts.format_operation.kind,
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
        with operations.inspect_update_inputs(vault) as observed:
            return _resume_update(operations, vault, observed)
    except OSError, ValueError, TypeError, AttributeError:
        return _refused("current_inputs_unavailable", action="refresh_update")


def _saved_review_available(checkpoint):
    return (
        checkpoint.manifest.boundary != "result"
        and checkpoint.review is not None
        and checkpoint.manifest.reviewed_source is not None
    )


def _resume_input_facts(operations, history, vault, observed, plan, incoming):
    checkpoint = history.checkpoint
    baseline = (
        incoming
        if plan.facts.format_operation.kind == "attachment_cleanup"
        else _read_source(operations, vault, checkpoint, observed)
    )
    if plan.facts.format_operation.kind == "attachment_cleanup":
        from .attachment_cleanup import cleanup_facts

        facts = cleanup_facts(
            history,
            baseline,
            observed=observed,
            proposal_id=plan.proposal.proposal_id,
            generation=plan.proposal.generation,
            source_memory=plan.facts.source_version_memory,
        )
    elif plan.facts.format_operation.kind == "format_transition":
        from .format_transition import transition_facts

        facts = transition_facts(
            history,
            _baseline(checkpoint, baseline),
            incoming,
            proposal_id=plan.proposal.proposal_id,
            generation=plan.proposal.generation,
        )
    else:
        facts = _observed_facts(
            history,
            baseline,
            incoming,
            proposal_id=plan.proposal.proposal_id,
            generation=plan.proposal.generation,
            source_memory=plan.facts.source_version_memory,
        )
    return facts


def _resume_update(operations, vault, observed):
    try:
        history, stopped = _history(
            operations, vault, observed, onboarding=True, maintenance=True
        )
        if stopped is not None:
            return stopped
        checkpoint = history.checkpoint
        if not _saved_review_available(checkpoint):
            return _refused("saved_update_unavailable", history)
        loaded = checkpoint.review
        binding = checkpoint.manifest.reviewed_source
        plan = loaded.saved.plan
        if (
            plan.facts.format_operation.kind == "collection_import"
            or checkpoint.manifest.collection_baseline_commit is not None
        ):
            from .collection_import import resume_collection_review

            return resume_collection_review(operations, history)
        if plan.facts.format_operation.kind == "onboarding":
            from .onboarding import resume_onboarding

            return resume_onboarding(operations, history, observed)
        incoming = (
            _read_source(operations, vault, checkpoint, observed)
            if plan.facts.format_operation.kind == "attachment_cleanup"
            else {
                s.path: s.incoming.data
                for s in plan.facts.subjects
                if s.incoming is not None
            }
        )
        if tuple(
            sorted(
                (path, len(raw), hashlib.sha256(raw).hexdigest())
                for path, raw in incoming.items()
            )
        ) != tuple((r.path, r.size, r.sha256) for r in binding.files):
            return _refused("saved_payload_mismatch", history)
        directory = _materialize(incoming, {r.path: r.mode for r in binding.files})
        facts = _resume_input_facts(
            operations, history, vault, observed, plan, incoming
        )
        history = _scope_review(operations, history, facts, plan, observed)
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
            plan.facts.format_operation.kind == "attachment_cleanup"
            or observed.source_sha256
            != record(incoming)["source_identity"]["source_sha256"],
            code=resumed.code,
            stale=_stale_slots(plan, resumed.plan),
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
    queue="all",
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
        if preparation.collection_record_path is not None:
            from .collection_import import inspect_collection_authority

            code = inspect_collection_authority(operations, preparation)
            if code is not None:
                return refused(code)
        else:
            code = _legacy_review_authority(operations, preparation)
            if code is not None:
                return refused(code)
        return review_plan_page(
            plan,
            proposal_id=proposal_id,
            generation=generation,
            offset=offset,
            limit=limit,
            byte_offset=byte_offset,
            byte_limit=byte_limit,
            queue=queue,
        )
    except OSError, ValueError, TypeError, AttributeError, KeyError, StopIteration:
        return refused("invalid_review")


def _legacy_review_authority(operations, preparation):
    checkpoint = operations.read_checkpoint(preparation.vault)
    if preparation.kind == "onboarding" and preparation.locator is None:
        history = operations.inspect_history(preparation.vault)
        if (
            checkpoint.status != "absent"
            or checkpoint.locator is not None
            or history.status != "absent"
            or history.admission.status != "supported"
            or not history.admission.inventory_complete
            or history.admission.inventory != preparation.current_inventory
        ):
            return "association_or_history_changed"
        directory = Path(preparation.payload_directory).absolute()
        if (
            directory.name != "incoming"
            or directory.parent.parent != Path(tempfile.gettempdir())
            or not directory.parent.name.startswith("brz2obsidian-update-")
            or operations.observe_reviewed_source(directory, preparation.review)
            != preparation.source_binding
        ):
            return "source_payload_changed"
    elif checkpoint.status != "valid" or checkpoint.locator != preparation.locator:
        return "association_or_history_changed"
    return None


def _slice_comparison_versions(versions, byte_offset, remaining, unread, *, _owner):
    parts, omitted = [], False
    quota = remaining // unread if unread else 0
    for content in versions:
        if content is None:
            parts.append(None)
            continue
        raw = (
            content.data[byte_offset : byte_offset + quota]
            if _owner is None
            else _owner._byteslice(content, byte_offset, quota)
        )
        remaining -= len(raw)
        omitted |= byte_offset != 0 or len(raw) != content.identity.size
        parts.append(raw)
    return parts, remaining, omitted


def review_plan_page(
    plan,
    *,
    proposal_id,
    generation,
    offset=0,
    limit=100,
    byte_offset=0,
    byte_limit=65536,
    _owner=None,
    _canonical_plan=None,
    queue="all",
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
        if (
            proposal_id != plan.proposal.proposal_id
            or generation != plan.proposal.generation
        ):
            return refused("review_identity_changed")
        if (
            any(
                type(v) is not int or v < 0
                for v in (offset, limit, byte_offset, byte_limit)
            )
            or not 1 <= limit <= 100
            or byte_limit > available_memory() // 16
            or (
                validate_review(plan).status != "accepted"
                if _owner is None
                else (
                    _owner._session._replay(plan)
                    if _canonical_plan is not plan
                    else _canonical_plan
                )
                is None
            )
        ):
            return refused("invalid_page")
        if queue not in ("all", "unresolved"):
            return refused("invalid_page")
        unresolved_ids = {r.change_id for r in plan.requirements}
        changes = tuple(
            c
            for c in plan.proposal.changes
            if queue == "all" or c.change_id in unresolved_ids
        )
        items = []
        remaining = byte_limit
        approvals = {approval.change_id: approval for approval in plan.approvals}
        for change in changes[offset : offset + limit]:
            UpdatePreparation.relative_vault_path(change.path)
            UpdatePreparation.relative_vault_path(change.target_path)
            approval = approvals.get(change.change_id)
            reviewed_result = (
                approval.result
                if approval is not None
                and approval.attachment_candidate is None
                and approval.result is not None
                else change.result
            )
            versions = change.original, change.current, change.incoming, reviewed_result
            unread = sum(
                content is not None and content.identity.size > byte_offset
                for content in versions
            )
            if byte_limit and unread > remaining:
                if not items:
                    return refused("insufficient_page_budget")
                break
            parts, remaining, omitted = _slice_comparison_versions(
                versions, byte_offset, remaining, unread, _owner=_owner
            )
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
                        content is not None and content.identity.size > following_byte
                        for content in versions
                    )
                    else None,
                    omitted=omitted,
                )
            )
        following = offset + len(items)
        total = len(changes)
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
    except OSError, ValueError, TypeError, AttributeError:
        return refused("invalid_review")


def prepare_update(operations, vault, source):
    try:
        with operations.inspect_update_inputs(vault) as observed:
            return _prepare_update(operations, vault, source, observed)
    except OSError, ValueError, TypeError, AttributeError:
        return _refused("current_inputs_unavailable", action="refresh_update")


def _prepare_update(operations, vault, source, observed):
    history, stopped = _history(operations, vault, observed)
    if stopped is not None:
        return stopped
    try:
        retained = _read_source(operations, vault, history.checkpoint, observed)
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
        history = _scoped(operations, history, facts, observed=observed)
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


def _reobserve(operations, preparation, *, for_save=False):
    try:
        preparation = UpdatePreparation.model_validate(preparation)
        if preparation.kind == "onboarding":
            from .onboarding import reobserve_onboarding

            return reobserve_onboarding(operations, preparation)
        with operations.inspect_update_inputs(preparation.vault) as observed:
            history, result, baseline = _reobserve_inputs(
                operations, preparation, observed
            )
            if result.status == "refused" and result.preparation is None:
                result = result.model_copy(update={"kind": preparation.kind})
            if for_save and history is not None:
                checkpoint = history.checkpoint
                if (
                    preparation.kind == "format_transition"
                    and checkpoint.manifest.boundary == "prepared"
                ):
                    baseline = (
                        _baseline(checkpoint, baseline),
                        observed.format_baseline_files(),
                    )
                else:
                    baseline = (baseline, checkpoint.manifest.source)
            return history, result, baseline
    except OSError, ValueError, TypeError, AttributeError:
        return (
            None,
            _refused(
                "current_inputs_unavailable",
                action="refresh_update",
                preparation=preparation,
            ),
            None,
        )


def _source_reobservation_refusal(
    operations, preparation, history, retained, baseline, actual
):
    if preparation.kind == "attachment_cleanup":
        expected = tuple(
            (row.path, row.mode, row.size, row.sha256)
            for row in history.checkpoint.manifest.source
        )
        if (
            preparation.source_ref is not None
            or actual.incoming_identity != history.checkpoint.manifest.identity
            or actual.target_source_version
            != record(retained)["source_identity"]["snapshot_digest"]
            or tuple((row.path, row.mode, row.size, row.sha256) for row in actual.files)
            != expected
            or preparation.observed_source
            != SourceIdentity.model_validate(record(retained)["source_identity"])
        ):
            return _refused(
                "retained_source_authority_required", history, preparation=preparation
            )
    elif preparation.source_ref is not None:
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
            return _refused("incoming_source_changed", history, action="refresh_update")
    else:
        saved_binding = history.checkpoint.manifest.reviewed_source
        if (
            saved_binding is None
            or saved_binding.proposal_id != preparation.review.proposal.proposal_id
            or saved_binding.files != actual.files
            or history.checkpoint.manifest.observed_source
            != preparation.observed_source
        ):
            return _refused("persisted_source_authority_required", history)


def _rebuild_update_facts(history, preparation, observed, retained, baseline, incoming):
    memory = _producer_memory(
        history.checkpoint, preparation.review.proposal.proposal_id
    )
    if preparation.kind == "attachment_cleanup":
        from .attachment_cleanup import cleanup_facts

        facts = cleanup_facts(
            history,
            retained,
            observed=observed,
            proposal_id=preparation.review.proposal.proposal_id,
            generation=preparation.review.proposal.generation,
            source_memory=memory,
        )
    elif preparation.kind == "format_transition":
        from .format_transition import transition_facts

        facts = transition_facts(
            history,
            baseline,
            incoming,
            proposal_id=preparation.review.proposal.proposal_id,
            generation=preparation.review.proposal.generation,
        )
    else:
        facts = _observed_facts(
            history,
            baseline,
            incoming,
            proposal_id=preparation.review.proposal.proposal_id,
            generation=preparation.review.proposal.generation,
            source_memory=memory,
        )
    return facts


def _reobserve_inputs(operations, preparation, observed):
    history, stopped = _history(
        operations,
        preparation.vault,
        observed,
        maintenance=preparation.kind == "format_transition",
        new_operation="format_transition"
        if preparation.kind == "format_transition"
        else None,
        recorded_output_format=preparation.source_binding.incoming_identity.output_format,
    )
    if stopped is not None:
        return (None, stopped.model_copy(update={"kind": preparation.kind}), None)
    if history.checkpoint.locator.association != preparation.locator.association:
        return (None, _refused("association_mismatch", history), None)
    directory = Path(preparation.payload_directory).absolute()
    if (
        directory.name != "incoming"
        or directory.parent.parent != Path(tempfile.gettempdir())
        or not directory.parent.name.startswith("brz2obsidian-update-")
    ):
        return (None, _refused("owned_payload_required", history), None)
    if validate_review(preparation.review).status != "accepted":
        return (None, _refused("invalid_review", history), None)
    actual = operations.observe_reviewed_source(directory, preparation.review)
    if actual != preparation.source_binding:
        return (None, _refused("source_payload_changed", history), None)
    retained = _read_source(operations, preparation.vault, history.checkpoint, observed)
    baseline = _baseline(history.checkpoint, retained)
    refusal = _source_reobservation_refusal(
        operations, preparation, history, retained, baseline, actual
    )
    if refusal is not None:
        return None, refusal, None
    incoming = _read_physical(directory, actual.files)
    try:
        facts = _rebuild_update_facts(
            history, preparation, observed, retained, baseline, incoming
        )
    except _ExcludedDependency:
        return (
            None,
            _refused(
                "excluded_dependency_requires_tracking",
                history,
                action="review_tracking",
            ),
            None,
        )
    history = _scope_review(operations, history, facts, preparation.review, observed)
    review = preparation.review
    changed = facts != review.facts or history.admission.preflight != review.preflight
    if changed:
        facts = facts.model_copy(update={"generation": facts.generation + 1})
        transition = refresh_review(
            review, facts, preflight=history.admission.preflight
        )
        if transition.status != "accepted":
            return (None, _refused(transition.code, history), None)
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
        stale=_stale_slots(preparation.review, review) if changed else 0,
    )
    return (history, result, retained)


def _apply_after_first_snapshot(
    operations, prepared, current, *, cancel, progress, _owner
):
    if not prepared.review.facts.format_operation.automatic_merge:
        return current.model_copy(
            update={
                "status": "unresolved",
                "code": "first_checkpoint_required",
                "ready": False,
                "next_actions": ("save_update",),
            }
        )
    captured = (
        save_update(operations, prepared, cancel=cancel, progress=progress)
        if _owner is None
        else _owner._save(prepared, cancel=cancel, progress=progress)
    )
    if captured.code != "saved" or captured.preparation is None:
        return captured
    if cancel is not None and cancel():
        return captured.model_copy(
            update={
                "status": "cancelled_before_publication",
                "code": "cancelled_before_publication",
                "ready": False,
                "publication": "not_published",
                "next_actions": ("continue_review", "refresh_update"),
            }
        )
    applied = apply_update(
        operations,
        captured.preparation,
        cancel=cancel,
        progress=progress,
        _owner=_owner,
    )
    retained = {
        "capture": applied.capture or captured.capture,
        "history_retained": applied.history_retained or captured.history_retained,
        "checkpoint_commit": applied.checkpoint_commit or captured.checkpoint_commit,
    }
    if (
        applied.preparation is None
        and applied.application is None
        and applied.status not in ("publication_unknown", "recovery_required", "failed")
    ):
        retained["preparation"] = captured.preparation
    return applied.model_copy(update=retained)


def _unchanged_source_update(prepared, current, history, *, _owner):
    selected = (
        select_review_effects(prepared.review)
        if _owner is None
        else _owner._session.select_review_effects(prepared.review)
    )
    source_rows = tuple(
        (r.path, r.mode, r.size, r.sha256) for r in prepared.source_binding.files
    )
    retained_source = tuple(
        (r.path, r.mode, r.size, r.sha256) for r in history.checkpoint.manifest.source
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
        (r.path, r.mode, r.size, r.sha256) for r in history.checkpoint.manifest.vault
    )
    if _owner is not None:
        if _owner._tip_commit != history.checkpoint.locator.commit:
            _owner._tip = _owner._load_tip(history.checkpoint)
        retained = _owner._tip
    else:
        retained = history.checkpoint.review
    retained_memory = _memory(retained.saved.plan) if retained is not None else ()
    same_memory = canonical_equal(
        tuple(
            sorted(_memory(prepared.review), key=lambda row: row.provenance.decision_id)
        ),
        tuple(sorted(retained_memory, key=lambda row: row.provenance.decision_id)),
    )
    same_selected = all(
        row.path in current_files
        and row.content.identity.size == current_files[row.path].size
        and row.content.identity.sha256 == current_files[row.path].sha256
        for row in selected.files
    )
    if (
        prepared.kind == "source_update"
        and selected.status == "selected"
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


def apply_update(operations, preparation, *, cancel=None, progress=None, _owner=None):
    native_contact = False
    try:
        history, current, _ = (
            _reobserve(operations, preparation)
            if _owner is None
            else _owner._reobserve(preparation, for_apply=True)
        )
        if (
            history is None
            or current.status == "stale_review"
            or current.code == "separate_configuration_operation_required"
        ):
            return current
        if current.kind == "onboarding" and current.preparation is not None:
            from .onboarding import transition_required

            if transition_required(current.preparation.review.facts):
                return current.model_copy(
                    update={
                        "status": "unresolved",
                        "code": "format_transition_required",
                        "ready": False,
                        "next_actions": ("save_update", "review_format_transition"),
                    }
                )
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
        if prepared.kind == "onboarding" and prepared.locator is None:
            return _apply_after_first_snapshot(
                operations,
                prepared,
                current,
                cancel=cancel,
                progress=progress,
                _owner=_owner,
            )
        association = prepared.locator.association
        unchanged = _unchanged_source_update(prepared, current, history, _owner=_owner)
        if unchanged is not None:
            return unchanged
        export = (
            _owner._publication_export(prepared.review) if _owner is not None else None
        )
        native_contact = True
        applied = operations.apply_reviewed_update(
            prepared.vault,
            prepared.payload_directory,
            review=prepared.review,
            source_binding=prepared.source_binding,
            observed_source=prepared.observed_source,
            vault_id=association.vault_id,
            import_id=association.import_id,
            cancel=cancel,
            **({"_owned_export": export} if export is not None else {}),
            **({"progress": progress} if progress is not None else {}),
        )
        status = update_application_status(applied)
        stopped_intent = applied.status == "cancelled" and status == "recovery_required"
        save_review_again = applied.code == "prepare_prepared_review_changed"
        return UpdateResult(
            kind=prepared.kind,
            status=status,
            code=applied.code,
            operation_id=applied.operation_id,
            generation=prepared.review.proposal.generation,
            changes=current.changes,
            vault=prepared.vault,
            summary=applied.message,
            next_actions=("review_recovery",)
            if applied.recovery_required or stopped_intent
            else ("resume_update",)
            if applied.code == "intent_ref_unavailable"
            else ("save_update",)
            if save_review_again
            else (),
            preparation=prepared if save_review_again else None,
            history_retained=current.history_retained or applied.history != "none",
            checkpoint_commit=applied.result_commit or applied.checkpoint_commit,
            publication=applied.publication,
            application=applied,
            recovery_gaps=history.admission.recovery_gaps,
        )
    except OSError, ValueError, KeyError, TypeError:
        if native_contact:
            return UpdateResult(
                kind=prepared.kind,
                status="publication_unknown",
                code="native_reply_unavailable",
                vault=prepared.vault,
                changes=current.changes,
                next_actions=("inspect_update_status",),
                history_retained=current.history_retained,
                publication="unknown",
                recovery_gaps=history.admission.recovery_gaps,
            )
        return _refused("current_review_unavailable", preparation=preparation)
