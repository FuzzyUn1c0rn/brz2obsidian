"""Validated interrupted-operation discovery and reviewed recovery roles."""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import stat
import sys
import tempfile
import time
import unicodedata
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

from brz2obsidian.application.update_facts import link_state, output_identity, record
from brz2obsidian.application.update_subjects import review_subjects
from brz2obsidian.application.vault_contracts import VaultFile, VaultSubject
from brz2obsidian.application.vault_recovery_contracts import VaultRecoveryPreparation
from brz2obsidian.application.vault_update_contracts import (
    VaultApplyResult,
    VaultOperationIntent,
    VaultOperationLock,
    VaultOperationReceipt,
    VaultOperationStop,
    VaultPathMetadata,
    VaultRecoveryIntent,
)
from brz2obsidian.content_fingerprints import canonical_equal
from brz2obsidian.content_values import content_sha, content_size, same_content
from brz2obsidian.contracts import (
    QUALIFIED_OUTPUT_FORMATS,
    AttachmentFacts,
    ContentValue,
    ContentVersion,
    CurrentContent,
    ExactContent,
    FormatBaselineOutput,
    IdentityInventoryItem,
    IdentityTargetFacts,
    OperationReversalOutput,
    OperationReversalTarget,
    ReconciliationSubject,
    ReferenceTarget,
    ReviewPlan,
    SelectedReviewEffects,
    SelectedReviewFile,
    SupportedFormatBaseline,
    reconciliation_subject_id,
)
from brz2obsidian.core import (
    prepare_review,
    refresh_review,
    resolve_review,
    review_owned_outputs,
    select_review_effects,
)
from brz2obsidian.core.reversals import reversal_document_target, review_owned_documents
from brz2obsidian.obsidian import (
    align_structure,
    interpret_link_target,
    interpret_links,
    interpret_structure,
)
from brz2obsidian.publication.collection_publication import (
    recovery_operation_marker,
    release_native_operation,
)
from brz2obsidian.publication.git_payload import verify_blobs
from brz2obsidian.publication.vault_admission import (
    _inspect_vault_for_recovery,
    _safe_relative,
)
from brz2obsidian.publication.vault_apply import (
    _adopt,
    _ensure_parents,
    _flush_stage,
    _inspect_update_observation,
    _journal,
    _metadata_matches,
    _NativeExecutor,
    _operation_history_fingerprint,
    _OperationObservation,
    _outcome,
    _park,
    _prepare_parents,
    _proposed_directory,
    _review_fact_paths_match,
    _review_subjects,
    _same_file,
    owns_operation,
)
from brz2obsidian.publication.vault_history import (
    _Git,
    _inspect_history,
    _inspect_retained_history,
    capture_checkpoint,
    inspect_history,
)
from brz2obsidian.publication.vault_native import (
    available_memory,
    observe_file,
    verify_directory,
)
from brz2obsidian.publication.vault_replace import (
    copy_stage,
    retained_directory_metadata,
    retained_metadata,
    stage_parent_security,
    supported_durable_volume,
)


def _marker_valid(root, operation_id):
    """An absent copied marker is permissible; a torn one never grants authority."""
    marker = root / ".git" / "brz2obsidian"
    if not os.path.lexists(marker):
        return True
    if not marker.is_dir() or set(os.listdir(marker)) != {"owner.json", "held"}:
        return False
    verify_directory(marker)
    _, raw_hash, raw, _ = observe_file(marker, marker / "owner.json", prefix_limit=4097)
    if len(raw) > 4096 or not raw_hash:
        return False
    owner = VaultOperationLock.model_validate_json(raw)
    held = (marker / "held").lstat()
    return (
        stat.S_ISREG(held.st_mode)
        and held.st_nlink == 1
        and held.st_size == 1
        and owner.operation_id == operation_id
        and owner.vault_anchor == verify_directory(root)
        and owner.git_anchor == verify_directory(root / ".git")
    )


def _lease_free(root, operation_id):
    """Probe only the stopped converter lease; never alter marker bytes."""
    if not _marker_valid(root, operation_id):
        return False
    marker = root / ".git" / "brz2obsidian"
    if not marker.exists():
        return True
    if owns_operation(root, operation_id):
        return False
    with (marker / "held").open("r+b") as stream:
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        except OSError:
            return False
    return True


def _current_record_format(facts, path, content):
    """Use the bound before-image role, otherwise this operation's output role."""
    from brz2obsidian.obsidian_dialect import is_migration_record_path

    if is_migration_record_path(path) and facts.link_context is not None:
        documents = tuple(
            row
            for row in facts.link_context.current_documents
            if row.source_path == path
        )
        subjects = tuple(
            row
            for row in facts.subjects
            if row.item_id == "support:" + path
            and row.facet == "content"
            and row.current.path == path
        )
        if (
            content is not None
            and len(documents) == len(subjects) == 1
            and subjects[0].current.content is not None
            and documents[0].content.data
            == subjects[0].current.content.data
            == content.data
        ):
            return facts.baseline_identity.output_format
    return facts.incoming_identity.output_format


def _admit_recovery_review(root, original, selected, retained, *, _owner):
    query_plan, query_effects = original, selected
    pending = retained.checkpoint
    if (
        retained.unpublished_prepared == pending.locator.commit
        and pending.manifest.undo_of_receipt_commit is not None
        and pending.review is not None
    ):
        # Policy fingerprints include the selected subject/query domain.
        # Reobserve precisely the saved Undo scope, including real Owner
        # document facets that were dependent outputs of the original apply.
        query_plan = pending.review.saved.plan
        query_effects = (
            select_review_effects(query_plan)
            if _owner is None
            else pending.review.historical_effects
        )
    query_subjects = _review_subjects(query_plan, query_effects)
    admission = (
        _inspect_vault_for_recovery(root, retained, subjects=query_subjects)
        if _owner is None
        else _owner._history_scoped(query_subjects)
    )
    if (
        not admission.inventory_complete
        or admission.repository.kind != "root"
        or any(finding.policy != "operation" for finding in admission.findings)
        or admission.preflight.state_status != "supported"
    ):
        raise OSError("Current recovery policy or inventory is unavailable")
    return admission, query_plan, query_subjects


def _require_recovery_tracking_consent(
    original, query_plan, query_subjects, retained, admission, paths, inventory
):
    pending = retained.checkpoint
    granted_plans = [original, query_plan]
    active_prepared = retained.graph.intent.prepared_commit
    if active_prepared in retained.owned:
        loaded = retained.owned[active_prepared][1]
        if loaded is not None:
            granted_plans.append(loaded.saved.plan)
    if (
        retained.unpublished_prepared == pending.locator.commit
        and pending.review is not None
    ):
        granted_plans.append(pending.review.saved.plan)
    for path in paths:
        row = inventory.get(path)
        if row is None or not row.excluded:
            continue
        queried_ids = {
            subject.subject_id for subject in query_subjects if subject.path == path
        }
        if (
            row.exclusion != "git_ignore"
            or row.tracked
            or not queried_ids
            or not any(
                required.kind == "tracking"
                and required.requirement == "required"
                and required.policy == "ordinary"
                and queried_ids <= set(required.subjects)
                and any(
                    required in plan.preflight.consents
                    and any(
                        decision.consent_id == required.consent_id
                        and decision.kind == required.kind
                        and decision.choice == "accept"
                        for decision in plan.consents
                    )
                    for plan in granted_plans
                )
                for required in admission.preflight.consents
            )
        ):
            raise OSError("Excluded recovery bytes lack current scoped consent")


def _observe_recovery_bytes(root, paths, inventory, *, _owner):
    needed = sum(inventory[path].size for path in paths if path in inventory)
    if _owner is None and available_memory() < 9 * needed + 64 * 1024 * 1024:
        raise OSError("Insufficient memory to review exact current recovery bytes")
    current = {}
    owned_current = (
        {}
        if _owner is None
        else _owner._history_current(
            tuple(inventory[path] for path in paths if path in inventory)
        )
    )
    for path in sorted(paths):
        row = inventory.get(path)
        if row is None:
            if os.path.lexists(root / path):
                raise OSError("Current recovery path is outside the inventory")
            current[path] = CurrentContent(existence="absent", path=path, content=None)
            continue
        if _owner is not None:
            current[path] = CurrentContent(
                existence="present", path=path, content=owned_current[path]
            )
            continue
        sink = io.BytesIO()
        info, sha, _, _ = observe_file(root, root / path, prefix_limit=0, sink=sink)
        data = sink.getvalue()
        if (
            info.st_size != row.size
            or sha != row.sha256
            or hashlib.sha256(data).hexdigest() != row.sha256
        ):
            raise OSError("Current recovery bytes changed during review")
        current[path] = CurrentContent(
            existence="present", path=path, content=ExactContent(data=data)
        )
    return current


def _unobserved_recovery_targets(
    original_facts, admission, inventory, identity_inventory, *, operation_paths
):
    context = original_facts.link_context
    from brz2obsidian.core.identity import _paths_collide
    from brz2obsidian.core.reference_targets import validate_targets
    from brz2obsidian.core.review_links import (
        current_lookup_coverage,
        current_observation_problem,
        passive_import_target,
    )

    from .collection_placement import location_conflict

    target_by_id = {target.target_id: target for target in context.current_targets}
    state_by_id = {state.target_id: state for state in context.current_target_facts}
    file_target_ids = {
        target.target_id for target in context.current_targets if target.kind != "tag"
    }
    unobserved = file_target_ids - set(state_by_id)
    if (
        len(target_by_id) != len(context.current_targets)
        or len(state_by_id) != len(context.current_target_facts)
        or set(state_by_id) - file_target_ids
        or unobserved
        and (
            current_observation_problem(original_facts) is not None
            or not current_lookup_coverage(original_facts)
        )
    ):
        raise OSError("Current recovery target lookup is incomplete")
    passive = {}
    retired = set()
    directories = {}
    retained_passive_paths = dict(context.import_passive_targets)
    scoped_import = original_facts.format_operation.kind == "collection_import" or bool(
        retained_passive_paths
    )
    for target_id in unobserved:
        target = target_by_id[target_id]
        path = target.canonical_path
        row = inventory.get(path)
        outside_recovery = (
            scoped_import
            and path is not None
            and target.target_id == f"physical:{path}"
            and target.kind in ("note", "resource")
            and not any(_paths_collide(path, affected) for affected in operation_paths)
        )
        ignored_observation = (
            outside_recovery and row is not None and row.exclusion == "git_ignore"
        )
        absent_observation = outside_recovery and row is None
        preserved = ignored_observation and passive_import_target(context, target)
        if path in retained_passive_paths and not (preserved or absent_observation):
            raise OSError(
                "Passive import link target is no longer outside recovery effects"
            )
        if (
            path is None
            or not (ignored_observation or absent_observation)
            and (target.kind != "resource" or path.casefold().endswith(".md"))
            or target.identity is not None
            or not _safe_relative(path)
            or target.representations != (path,)
            or row is None
            and not absent_observation
            or any(entry.current.path == path for entry in identity_inventory)
            or any(
                d.source_path == path
                for d in context.current_documents + context.incoming_documents
            )
            or any(
                other.path != path and _paths_collide(path, other.path)
                for other in admission.inventory
            )
        ):
            raise OSError(
                "Unobserved recovery resource is not bounded physical metadata"
            )
        validate_targets((target,))
        if absent_observation:
            root = Path(admission.vault)
            if (
                not admission.inventory_complete
                or os.path.lexists(root / path)
                or location_conflict(root, path, directories=directories)
            ):
                raise OSError("Lookup-only recovery target absence is unverified")
            retired.add(target_id)
        elif preserved:
            passive[target_id] = (path, row.sha256)
    return unobserved, state_by_id, passive, retired


def _observed_recovery_target_facts(
    original_facts, current, unobserved, state_by_id, *, _owner
):
    context = original_facts.link_context
    target_facts = []
    for target in context.current_targets:
        if target.kind == "tag" or target.target_id in unobserved:
            continue
        old = state_by_id[target.target_id]
        observed_target = current.get(target.canonical_path)
        retained_absence = old.existence == "missing" or (
            original_facts.incoming_identity.output_format == 9
            and old.existence == "intentionally_uncreated"
        )
        if observed_target is None or (
            observed_target.content == old.content
            and observed_target.existence
            == ("absent" if retained_absence else old.existence)
        ):
            target_facts.append(old)
        else:
            target_facts.append(
                link_state(
                    observed_target.content,
                    target_id=target.target_id,
                    existence="missing"
                    if observed_target.existence == "absent"
                    else "present",
                    membership_targets=context.current_targets,
                    source_path=target.canonical_path,
                    output_format=old.structure.output_format
                    if old.structure is not None
                    else 7
                    if original_facts.baseline_identity.output_format == 6
                    else original_facts.baseline_identity.output_format,
                    qualify_roles=original_facts.incoming_identity.output_format
                    in QUALIFIED_OUTPUT_FORMATS,
                    _owner=None if _owner is None else _owner._session,
                )
            )
    return target_facts


def _observe_operation_owned_note(
    path,
    retained_targets,
    original_facts,
    current,
    selected_files,
    ownership_proposed,
    lookup,
    identity_inventory,
    *,
    path_known,
    direction,
    _owner,
):
    context = original_facts.link_context
    observed_document = current[path]
    current_targets, target_facts, new_documents = lookup
    # The original selected effect can move one real note identity
    # from its old physical path to this approved new path. Reuse
    # that target/document authority for the fresh observation.
    if len(retained_targets) != 1 or path not in selected_files:
        raise OSError("Operation-owned recovery note is ambiguous")
    retained_target = retained_targets[0]
    retained_document = tuple(
        doc
        for doc in context.incoming_documents
        if doc.source_path == path
        and doc.document_id == retained_target.target_id
        and doc.status == "supported"
    )
    original_target = tuple(
        target
        for target in current_targets
        if target.target_id == retained_target.target_id
    )
    owner = tuple(
        item
        for item in identity_inventory
        if item.identity_state == "valid"
        and item.identity == retained_target.identity
        and item.facet == "content"
    )
    row = ownership_proposed.get(path)
    content = selected_files[path]
    if (
        len(retained_document) != 1
        or len(original_target) != 1
        or len(owner) != 1
        or retained_target.identity is None
        or row is None
        or row.size != content_size(content)
        or row.sha256 != content_sha(content)
        or (path_known and owner[0].current.path != path)
    ):
        raise OSError("Operation-owned recovery note lacks retained proof")
    index = next(
        i
        for i, target in enumerate(current_targets)
        if target.target_id == retained_target.target_id
    )
    current_targets[index] = retained_target
    state_index = next(
        i
        for i, state in enumerate(target_facts)
        if state.target_id == retained_target.target_id
    )
    target_facts[state_index] = link_state(
        observed_document.content,
        target_id=retained_target.target_id,
        existence="present",
        membership_targets=tuple(current_targets),
        source_path=path,
        _owner=None if _owner is None else _owner._session,
    )
    parsed = interpret_links(
        observed_document.content,
        document_id=retained_document[0].document_id,
        source_path=path,
        path_mode=retained_document[0].path_mode,
        targets=tuple(current_targets),
        target_facts=tuple(target_facts),
        inventory="complete",
        output_format=original_facts.incoming_identity.output_format,
        record_format=_current_record_format(
            original_facts, path, observed_document.content
        ),
    )
    if parsed.status != "supported":
        raise OSError("Operation-owned recovery note interpretation failed")
    new_documents.append(parsed)
    if owner[0].current.path == path:
        pass
    elif direction == "finish":
        if current[owner[0].current.path].existence != "absent":
            raise OSError("Both renamed recovery endpoints are present")
        # The approved rename has one logical current location.
        # Its old physical path is absent in the actual inventory;
        # finish reviews the exact new-path version under that
        # same retained identity.
        identity_inventory[
            next(
                i
                for i, item in enumerate(identity_inventory)
                if item.entry_id == owner[0].entry_id
            )
        ] = owner[0].model_copy(
            update={
                "current": observed_document,
                "target": retained_target.target,
            }
        )
    else:
        identity_inventory.append(
            owner[0].model_copy(
                update={
                    "entry_id": "recovery-output:"
                    + hashlib.sha256(path.encode()).hexdigest(),
                    "current": observed_document,
                    "target": retained_target.target,
                }
            )
        )


def _observe_authored_recovery_note(
    path,
    observed_document,
    inventory,
    original_facts,
    current_targets,
    incoming_targets,
    target_facts,
    known_identity_paths,
):
    # A new authored note has no imported item identity. Its safe
    # physical path is still a real lookup entry and document owner.
    if path in known_identity_paths or any(
        target.canonical_path == path for target in current_targets + incoming_targets
    ):
        raise OSError("New current recovery document has ambiguous identity")
    target_id = "recovery-note:" + hashlib.sha256(path.encode()).hexdigest()
    target = IdentityTargetFacts(
        normalized_path=unicodedata.normalize(
            "NFC", unicodedata.normalize("NFC", path).casefold()
        ),
        containment="contained",
        status="safe",
    )
    reference = ReferenceTarget(
        schema_id="brz2obsidian.reference-target",
        schema_version=1,
        target_id=target_id,
        kind="note",
        canonical_path=path,
        identity=None,
        target=target,
        representations=(path,),
        validation_fingerprint=hashlib.sha256(
            (path + ":" + inventory[path].sha256).encode()
        ).hexdigest(),
        status="safe",
    )
    state = interpret_link_target(
        observed_document.content,
        target_id=target_id,
        existence="present",
        memberships=(),
        source_path=path,
    )
    parsed = interpret_links(
        observed_document.content,
        document_id=target_id,
        source_path=path,
        path_mode="vault",
        targets=tuple(current_targets) + (reference,),
        target_facts=tuple(target_facts) + (state,),
        inventory="complete",
        output_format=original_facts.incoming_identity.output_format,
        record_format=_current_record_format(
            original_facts, path, observed_document.content
        ),
    )
    # A newly authored note's link mode has no retained S1 proof.
    # Plain notes can join the complete inventory; link-bearing or
    # opaque notes need an explicit qualified observation first.
    if parsed.status != "supported" or parsed.occurrences:
        raise OSError("New current recovery links need qualified review")
    return parsed, reference, state


def _completed_import_outputs(facts, current, selected, proposed, *, direction):
    if direction != "finish" or facts.format_operation.kind != "collection_import":
        return ()
    completed = []
    for path, content in selected.items():
        observed = current.get(path)
        row = proposed.get(path)
        if (
            observed is not None
            and observed.existence == "present"
            and same_content(observed.content, content)
            and row is not None
            and row.size == content_size(content)
            and row.sha256 == content_sha(content)
        ):
            completed.append((path, row.sha256))
    return tuple(sorted(completed))


def _reobserve_retired_link_queries(documents, targets, states, inventory, retired):
    from brz2obsidian.core.link_meanings import resolve_occurrence

    return tuple(
        document.model_copy(
            update={
                "occurrences": tuple(
                    row.model_copy(
                        update={
                            "meaning": resolve_occurrence(
                                row, targets, states, inventory
                            )
                        }
                    )
                    if row.meaning.target_id in retired
                    or retired.intersection(row.meaning.candidates)
                    else row
                    for row in document.occurrences
                )
            }
        )
        for document in documents
    )


def _refresh_recovery_link_context(
    original_facts,
    admission,
    inventory,
    identity_inventory,
    current,
    intent,
    selected_files,
    ownership_proposed,
    *,
    selected_removal,
    direction,
    _owner,
):
    context = original_facts.link_context
    unobserved, state_by_id, passive, retired = _unobserved_recovery_targets(
        original_facts,
        admission,
        inventory,
        identity_inventory,
        operation_paths=set(intent.affected_paths) | set(selected_files),
    )
    target_facts = _observed_recovery_target_facts(
        original_facts, current, unobserved, state_by_id, _owner=_owner
    )
    new_documents = []
    current_targets = [
        target for target in context.current_targets if target.target_id not in retired
    ]
    incoming_targets = [
        target for target in context.incoming_targets if target.target_id not in retired
    ]
    incoming_target_facts = [
        state
        for state in context.incoming_target_facts
        if state.target_id not in retired
    ]
    incoming_documents = list(context.incoming_documents)
    known_document_paths = {
        document.source_path for document in context.current_documents
    }
    known_identity_paths = {item.current.path for item in identity_inventory}
    operation_owned_notes = {
        target.canonical_path
        for target in context.incoming_targets
        if target.kind in ("note", "category", "relationship")
        and target.canonical_path in intent.affected_paths
        and target.canonical_path in selected_files
    }
    from brz2obsidian.obsidian_dialect import is_migration_record_path

    owned_documents = (
        operation_owned_notes
        if original_facts.format_operation.kind == "collection_import"
        else {
            subject.path
            for subject in original_facts.subjects
            if subject.path in operation_owned_notes
            and subject.item_id == "support:" + subject.path
            and is_migration_record_path(subject.path)
        }
    )
    for path in sorted(
        row.path
        for row in admission.inventory
        if (selected_removal or row.path in operation_owned_notes)
        and (row.path.casefold().endswith(".md") or row.path in owned_documents)
        and row.path not in known_document_paths
        and not (
            original_facts.format_operation.kind == "collection_import"
            and row.exclusion == "git_ignore"
            and row.path not in current
        )
    ):
        observed_document = current[path]
        if observed_document.content is None:
            raise OSError("New current recovery document is unavailable")
        retained_targets = tuple(
            target
            for target in context.incoming_targets
            if target.canonical_path == path
            and target.kind in ("note", "category", "relationship")
        )
        if path in operation_owned_notes and retained_targets:
            _observe_operation_owned_note(
                path,
                retained_targets,
                original_facts,
                current,
                selected_files,
                ownership_proposed,
                (current_targets, target_facts, new_documents),
                identity_inventory,
                path_known=path in known_identity_paths,
                direction=direction,
                _owner=_owner,
            )
            known_identity_paths.add(path)
            continue
        parsed, reference, state = _observe_authored_recovery_note(
            path,
            observed_document,
            inventory,
            original_facts,
            current_targets,
            incoming_targets,
            target_facts,
            known_identity_paths,
        )
        current_targets.append(reference)
        incoming_targets.append(reference)
        target_facts.append(state)
        incoming_target_facts.append(state)
        new_documents.append(parsed)
        incoming_documents.append(parsed)
        identity_inventory.append(
            IdentityInventoryItem(
                entry_id=reference.target_id,
                facet=None,
                identity_state="missing",
                identity=None,
                raw_identity=None,
                title=Path(path).stem,
                current=observed_document,
                target=reference.target,
            )
        )
        known_identity_paths.add(path)
    lookup_targets = tuple(current_targets)
    lookup_states = tuple(target_facts)
    lookup_unchanged = (
        lookup_targets == context.current_targets
        and lookup_states == context.current_target_facts
        and context.inventory == "complete"
    )
    documents = []
    for document in context.current_documents:
        observed_document = current[document.source_path]
        if observed_document.content is None:
            continue
        documents.append(
            document
            if (
                lookup_unchanged
                and observed_document.content == document.content
                and observed_document.path == document.source_path
                and document.inventory == "complete"
            )
            else interpret_links(
                observed_document.content,
                document_id=document.document_id,
                source_path=observed_document.path,
                path_mode=document.path_mode,
                targets=lookup_targets,
                target_facts=lookup_states,
                inventory="complete",
                output_format=original_facts.incoming_identity.output_format,
                authored_links=original_facts.format_operation.kind
                == "collection_import",
                record_format=_current_record_format(
                    original_facts,
                    observed_document.path,
                    observed_document.content,
                ),
            )
        )
    documents.extend(
        interpret_links(
            document.content,
            document_id=document.document_id,
            source_path=document.source_path,
            path_mode=document.path_mode,
            targets=lookup_targets,
            target_facts=lookup_states,
            inventory="complete",
            output_format=original_facts.incoming_identity.output_format,
            record_format=_current_record_format(
                original_facts, document.source_path, document.content
            ),
        )
        for document in new_documents
    )
    if retired:
        incoming_documents = _reobserve_retired_link_queries(
            incoming_documents,
            tuple(incoming_targets),
            tuple(incoming_target_facts),
            context.inventory,
            retired,
        )
    context = context.model_copy(
        update={
            "current_targets": lookup_targets,
            "incoming_targets": tuple(incoming_targets),
            "current_target_facts": lookup_states,
            "incoming_target_facts": tuple(incoming_target_facts),
            "current_documents": tuple(documents),
            "import_passive_targets": tuple(sorted(passive.values())),
            "import_finished_outputs": _completed_import_outputs(
                original_facts,
                current,
                selected_files,
                ownership_proposed,
                direction=direction,
            ),
            "incoming_documents": tuple(incoming_documents),
        }
    )
    return context, unobserved - passive.keys() - retired


def _recovery_subject_current(
    subject,
    facts,
    current,
    intent,
    selected,
    selected_files,
    original_before,
    original_proposed,
    *,
    direction,
):
    observed = current[subject.current.path]
    if (
        direction != "finish"
        or observed.existence != "absent"
        or subject.current.path != subject.path
    ):
        return observed
    owners = tuple(
        item
        for item in facts.identity_inventory
        if item.identity_state == "valid"
        and item.identity is not None
        and (
            item.identity.module_id,
            item.identity.collection_id,
        )
        == (
            facts.incoming_identity.module_id,
            facts.incoming_identity.collection_id,
        )
        and (item.identity.item_id, item.facet) == (subject.item_id, subject.facet)
    )
    if len(owners) != 1:
        return observed
    old_path = owners[0].current.path
    old = original_before.get(old_path)
    new = original_proposed.get(subject.path)
    selected_new = selected_files.get(subject.path)
    old_current = current.get(old_path)
    if (
        old_path != subject.path
        and old_path in selected.remove_paths
        and old_path in intent.affected_paths
        and subject.path in intent.affected_paths
        and old is not None
        and owners[0].current.content is not None
        and old.size == content_size(owners[0].current.content)
        and old.sha256 == content_sha(owners[0].current.content)
        and new is not None
        and selected_new is not None
        and new.size == content_size(selected_new)
        and new.sha256 == content_sha(selected_new)
        and old_current is not None
        and old_current.existence == "present"
    ):
        # The approved rename has not made its first physical move. The
        # real retained item still lives at its independently observed
        # old path; the new path is the selected output, currently absent.
        return old_current
    return observed


def _reobserve_recovery_subjects(
    original_facts, current, intent, selected, selected_files, context, *, direction
):
    original_before = {row.path: row for row in intent.before}
    original_proposed = {row.path: row for row in intent.proposed}

    def observed_subject(subject):
        observed = _recovery_subject_current(
            subject,
            original_facts,
            current,
            intent,
            selected,
            selected_files,
            original_before,
            original_proposed,
            direction=direction,
        )
        comparison = subject.structure
        if comparison is not None and observed.content is not None:
            targets = (
                context.current_targets
                if context is not None
                else tuple(
                    entry.target
                    for membership in comparison.current.memberships
                    for entry in membership.entries
                )
                + tuple(
                    target
                    for section in comparison.current.owned_sections
                    for target in section.targets
                )
            )
            current_structure = interpret_structure(
                observed.content,
                output_format=comparison.current.output_format,
                membership_targets=targets,
                section_bases=comparison.section_bases,
                section_targets=targets,
            )
            comparison = align_structure(
                comparison.original,
                current_structure,
                comparison.incoming,
                prior_mappings=comparison.prior_mappings,
                incoming_mappings=comparison.incoming_mappings,
                section_bases=comparison.section_bases,
            )
        return subject.model_copy(update={"current": observed, "structure": comparison})

    return tuple(observed_subject(subject) for subject in original_facts.subjects)


def _require_bound_recovery_links(facts, context, unobserved):
    from brz2obsidian.core.review_links import (
        consumed_context,
        current_lookup_coverage,
        current_observation_problem,
    )

    if current_observation_problem(facts) is not None or not current_lookup_coverage(
        facts
    ):
        raise OSError("Fresh recovery link lookup is unbound")
    for documents, targets, states in (
        (
            context.current_documents,
            context.current_targets,
            context.current_target_facts,
        ),
        (
            context.incoming_documents,
            context.incoming_targets,
            context.incoming_target_facts,
        ),
    ):
        _, _, used, _ = consumed_context(documents, targets, states, context.inventory)
        if unobserved.intersection(target.target_id for target in used):
            raise OSError(
                "Current recovery consumes unobserved physical resource metadata"
            )


def _observed_collection_resources(facts, original):
    if original.facts.format_operation.kind != "collection_import":
        return facts
    from brz2obsidian.core.review_links import collection_asset_effect

    owners = {}
    for change in original.proposal.changes:
        effect = collection_asset_effect(original.producer_facts, change)
        if effect is not None:
            owners[change.item_id, change.facet] = effect[0].target_id
    return facts.model_copy(
        update={
            "subjects": tuple(
                subject.model_copy(
                    update={
                        "attachment": AttachmentFacts(
                            current_target_id=owners[subject.item_id, subject.facet],
                            allocation_candidates=(),
                            affected_documents=(),
                        ),
                    }
                )
                if (subject.item_id, subject.facet) in owners
                else subject
                for subject in facts.subjects
            ),
        }
    )


def _review_observation(
    root,
    observed,
    *,
    direction,
    authority,
    next_generation=None,
    undo_target=None,
    _owner=None,
):
    """Bind original S1 facts to independently observed current vault bytes."""
    git = _Git(root)
    original, intent, origin_commit, retained = authority
    if intent.operation_id != observed.operation_id and not any(
        graph.receipt is not None and graph.origin_intent_commit == origin_commit
        for graph in retained.graphs
    ):
        raise OSError("Validated operation authority changed")
    selected = (
        select_review_effects(original)
        if _owner is None
        else _owner._history_origin.historical_effects
    )
    if selected.status != "selected":
        raise OSError("Original prepared review is not selected")
    selected_files = {row.path: row.content for row in selected.files}
    ownership_proposed = {
        row.path: row
        for row in (
            undo_target.graph.authorities[-1][1].proposed
            if undo_target is not None
            else intent.proposed
        )
    }
    admission, query_plan, query_subjects = _admit_recovery_review(
        root, original, selected, retained, _owner=_owner
    )
    if direction == "finish":
        from .collection_placement import require_collection_finish_links

        prepared = retained.owned[intent.prepared_commit][0]
        require_collection_finish_links(
            admission,
            retained.checkpoint,
            prepared.collection_record_path,
            original,
            selected_files,
            selected.remove_paths,
            origin=intent,
        )
    inventory = {row.path: row for row in admission.inventory}
    paths = (
        {subject.current.path for subject in original.facts.subjects}
        | {item.current.path for item in original.facts.identity_inventory}
        | set(intent.affected_paths)
    )
    target_paths = {
        row.path
        for row in (intent.proposed if direction == "finish" else intent.before)
    }
    selected_removal = bool(selected.remove_paths) or any(
        path in inventory and path not in target_paths for path in intent.affected_paths
    )
    if original.facts.link_context is not None:
        paths.update(
            document.source_path
            for document in original.facts.link_context.current_documents
        )
        if selected_removal:
            # Every present authored note can own an inbound link to a target
            # selected for removal, including notes added after the stop.
            ignored = set()
            if original.facts.format_operation.kind == "collection_import":
                from .collection_placement import prove_ignored_reversal_documents

                ignored = prove_ignored_reversal_documents(
                    admission, intent.affected_paths, selected_files
                )
            paths.update(
                row.path
                for row in admission.inventory
                if row.path.casefold().endswith(".md") and row.path not in ignored
            )
    _require_recovery_tracking_consent(
        original, query_plan, query_subjects, retained, admission, paths, inventory
    )
    current = _observe_recovery_bytes(root, paths, inventory, _owner=_owner)
    original_facts = original.facts
    context = original_facts.link_context
    identity_inventory = list(original_facts.identity_inventory)
    if context is not None:
        context, unobserved = _refresh_recovery_link_context(
            original_facts,
            admission,
            inventory,
            identity_inventory,
            current,
            intent,
            selected_files,
            ownership_proposed,
            selected_removal=selected_removal,
            direction=direction,
            _owner=_owner,
        )
    facts = original_facts.model_copy(
        update={
            "generation": next_generation or original.proposal.generation + 1,
            "subjects": _reobserve_recovery_subjects(
                original_facts,
                current,
                intent,
                selected,
                selected_files,
                context,
                direction=direction,
            ),
            "identity_inventory": tuple(
                item.model_copy(update={"current": current[item.current.path]})
                for item in identity_inventory
            ),
            "link_context": context,
        }
    )
    resource_facts = _observed_collection_resources(facts, original)
    if context is not None and unobserved:
        _require_bound_recovery_links(resource_facts, context, unobserved)
    if direction == "restore":
        facts = resource_facts
    # The checkpoint locator advances during the already-authorized operation.
    # Only that validated movement is neutralized: changed policy, consents,
    # current bytes, or a broken graph still reach the ordinary refresh rules.
    original_prepared = retained.owned[intent.prepared_commit][0]
    preflight = _review_preflight(admission, original_prepared, original, retained)
    return original, intent, origin_commit, git, facts, preflight, current, retained


def _review_preflight(admission, prepared, original, retained):
    same_policy = admission.policy_fingerprint == prepared.policy_fingerprint
    pending = retained.checkpoint
    pending_undo = (
        retained.unpublished_prepared == pending.locator.commit
        and pending.manifest.undo_of_receipt_commit is not None
        and pending.review is not None
        and admission.policy_fingerprint == pending.manifest.policy_fingerprint
    )
    state_fingerprint = (
        pending.review.saved.plan.preflight.state_fingerprint
        if pending_undo
        else original.preflight.state_fingerprint
        if same_policy and retained.graph.receipt is None
        else admission.preflight.state_fingerprint
    )
    return admission.preflight.model_copy(
        update={
            "operation_status": "idle",
            "state_fingerprint": state_fingerprint,
        }
    )


def _current_review_matches(review, admission):
    inventory = {row.path: row for row in admission.inventory}

    def matches(path, content):
        row = inventory.get(path)
        return (
            row is None
            if content is None
            else (
                row is not None
                and row.size == content_size(content)
                and row.sha256 == content_sha(content)
            )
        )

    return _review_fact_paths_match(
        review.producer_facts, matches, lambda path, content: True
    )


def _inactive_attachment_proof(original, intent, subject):
    """Qualify a protected canonical Current, never an affected resource effect."""
    proof = subject.operation_reversal
    operation = original.producer_facts.format_operation
    baseline = operation.established_baseline
    if (
        intent.kind != "undo"
        or proof is None
        or subject.attachment is None
        or subject.baseline.status != "known"
        or subject.incoming is None
        or subject.incoming != subject.baseline.content
        or baseline is None
        or baseline.source_version != operation.baseline_source_version
        or baseline.identity != original.producer_facts.baseline_identity
    ):
        return False
    versions = tuple(
        row
        for row in baseline.outputs
        if (row.item_id, row.facet) == (subject.item_id, subject.facet)
    )
    changes = tuple(
        row
        for row in original.proposal.changes
        if (row.item_id, row.facet) == (subject.item_id, subject.facet)
    )
    if (
        len(versions) != 1
        or versions[0].content != subject.baseline.content
        or len(changes) != 1
        or not any(
            row.change_id == changes[0].change_id
            and row.domain == "reversal"
            and row.choice == "current"
            for row in original.approvals
        )
    ):
        return False
    before = {row.path: row for row in intent.before}
    proposed = {row.path: row for row in intent.proposed}
    paths = {subject.path, subject.current.path} | {row.path for row in proof.outputs}
    return not paths & set(intent.affected_paths) and all(
        path in before and path in proposed and before[path] == proposed[path]
        for path in paths
    )


def _document_preflight(root, retained, original, intent, facts, *, _owner=None):
    """Reinspect the actual derived RESTORE policy/current-claim domain."""
    queries = {(row.path, row.subject_id): row for row in review_subjects(facts)}
    for subject in facts.subjects:
        if subject.operation_reversal is None:
            continue
        owner_id = reconciliation_subject_id(
            facts.incoming_identity.module_id,
            facts.incoming_identity.collection_id,
            subject.item_id,
            subject.facet,
        )
        for output in subject.operation_reversal.outputs:
            queries[output.path, owner_id] = VaultSubject(
                path=output.path, subject_id=owner_id
            )
    subjects = tuple(queries[key] for key in sorted(queries))
    admission = (
        _inspect_vault_for_recovery(root, retained, subjects=subjects)
        if _owner is None
        else _owner._history_scoped(subjects)
    )
    if (
        not admission.inventory_complete
        or admission.repository.kind != "root"
        or any(finding.policy != "operation" for finding in admission.findings)
        or admission.preflight.state_status != "supported"
    ):
        raise OSError("Current recovery policy or inventory is unavailable")
    return _review_preflight(
        admission, retained.owned[intent.prepared_commit][0], original, retained
    )


def _imported_byte_reversal(subject):
    proof = subject.operation_reversal
    return (
        proof is not None
        and len(proof.outputs) == len(proof.owned_targets) == 1
        and proof.owned_targets[0].kind == "note"
        and proof.owned_targets[0].identity is not None
        and proof.outputs[0].produced_existence == "present"
        and proof.outputs[0].target_existence == "present"
    )


def _finish_imported_undo_note(subject, evidence, change, decision, owned, *, _owner):
    path = subject.path
    selected = evidence.selected.get(path)
    retained_target = subject.operation_reversal.owned_targets[0]
    previous = _owned_content(evidence.git, evidence.before.get(path), _owner=_owner)
    proposed = _owned_content(evidence.git, evidence.proposed.get(path), _owner=_owner)
    if (
        path != subject.current.path
        or selected is None
        or selected.subject_id != change.subject_id
        or owned != (retained_target,)
        or previous is None
        or proposed is None
        or not same_content(proposed, selected.content)
    ):
        raise OSError("Imported Undo note lacks exact selected recovery versions")
    intent = evidence.intent
    proof = OperationReversalTarget(
        schema_id="brz2obsidian.operation-reversal-target",
        schema_version=1,
        operation_id=intent.operation_id,
        operation_kind=intent.kind,
        direction="finish",
        operation_generation=intent.generation,
        history_fingerprint=_operation_history_fingerprint(
            evidence.origin_commit, intent
        ),
        origin_change_id=change.change_id,
        origin_decision_id=decision,
        owned_targets=owned,
        outputs=(
            OperationReversalOutput(
                path=path,
                target_id=retained_target.target_id,
                produced_existence="present",
                produced=previous,
                current=subject.current,
                target_existence="present",
                target=proposed,
            ),
        ),
    )
    return subject.model_copy(
        update={"operation_reversal": proof, "incoming": proposed}
    )


@dataclass(frozen=True)
class _UndoFinishEvidence:
    git: _Git
    intent: VaultOperationIntent
    origin_commit: str
    selected: dict
    before: dict
    proposed: dict


def _finish_imported_undo_notes(facts, original, intent, origin_commit, git, *, _owner):
    if intent.kind != "undo" or intent.undo_of_receipt_commit is None:
        return facts
    imported = tuple(
        subject for subject in facts.subjects if _imported_byte_reversal(subject)
    )
    if not imported:
        return facts
    affected = tuple(
        subject for subject in imported if subject.path in intent.affected_paths
    )
    changes = {(row.item_id, row.facet): row for row in original.proposal.changes}
    decisions = {row.change_id: row.decision_id for row in original.approvals}
    queries = tuple(
        (
            changes[subject.item_id, subject.facet].change_id,
            decisions.get(changes[subject.item_id, subject.facet].change_id),
        )
        for subject in affected
    )
    owned = (
        review_owned_outputs(original, queries)
        if _owner is None
        else _owner._history_owned_outputs(original, queries)
    )
    evidence = _UndoFinishEvidence(
        git,
        intent,
        origin_commit,
        {row.path: row for row in owned.effects.files},
        {row.path: row for row in intent.before},
        {row.path: row for row in intent.proposed},
    )
    rebound = tuple(
        _finish_imported_undo_note(
            subject,
            evidence,
            changes[subject.item_id, subject.facet],
            decision,
            targets,
            _owner=_owner,
        )
        for subject, (_, decision), targets in zip(
            affected, queries, owned.target_groups, strict=True
        )
    )
    return facts.model_copy(
        update={
            "subjects": tuple(
                subject for subject in facts.subjects if subject not in imported
            )
            + rebound
        }
    )


def _finish_review(root, observed, *, previous=None, authority=None, _owner=None):
    original, intent, origin_commit, git, facts, preflight, current, retained = (
        _review_observation(
            root,
            observed,
            direction="finish",
            authority=authority,
            next_generation=(previous.proposal.generation + 1 if previous else None),
            _owner=_owner,
        )
    )
    facts = _finish_imported_undo_notes(
        facts, original, intent, origin_commit, git, _owner=_owner
    )
    document_keys = {
        (subject.item_id, subject.facet)
        for subject in original.facts.subjects
        if reversal_document_target(subject) is not None
    }
    if document_keys:
        inactive_keys = {
            (subject.item_id, subject.facet)
            for subject in facts.subjects
            if _inactive_attachment_proof(original, intent, subject)
        }
        facts = facts.model_copy(
            update={
                "subjects": tuple(
                    subject.model_copy(update={"operation_reversal": None})
                    if (subject.item_id, subject.facet) in inactive_keys
                    else subject
                    for subject in facts.subjects
                    if (subject.item_id, subject.facet) not in document_keys
                )
                + _operation_document_subjects(
                    original,
                    intent,
                    origin_commit,
                    git,
                    current,
                    direction="finish",
                    only_documents={item_id for item_id, _ in document_keys},
                    _owner=_owner,
                )
            }
        )
        if inactive_keys:
            preflight = _document_preflight(
                root, retained, original, intent, facts, _owner=_owner
            )
    from .attachment_ownership import compile_removal_continuations

    loaded = retained.owned[intent.prepared_commit][1]
    continuations = compile_removal_continuations(
        original,
        intent,
        origin_commit,
        effects=loaded.historical_effects,
    )
    facts = facts.model_copy(
        update={
            "subjects": tuple(
                subject.model_copy(
                    update={
                        "attachment": subject.attachment.model_copy(
                            update={
                                "removal_continuation": continuations.get(
                                    (subject.item_id, subject.facet)
                                )
                            }
                        )
                    }
                )
                if subject.attachment is not None
                and subject.current.existence == "absent"
                and subject.current.content is None
                else subject
                for subject in facts.subjects
            )
        }
    )
    if _owner is not None:
        return _owner._history_plan(facts, preflight, previous or original)
    refreshed = refresh_review(previous or original, facts, preflight=preflight)
    if refreshed.status != "accepted":
        raise OSError("Current recovery review could not be refreshed")
    return refreshed.plan


def _owned_content(git, row, *, _owner=None):
    if row is None:
        return None
    if _owner is not None:
        return _owner._operation_content(row)
    if available_memory() < 9 * row.size + 64 * 1024 * 1024:
        raise OSError("Insufficient memory to review retained operation payload")
    sink = io.BytesIO()
    verify_blobs(
        [*git.prefix, "cat-file", "--batch"],
        env=git.env,
        objects=((row.object_id, row.size, row.sha256, sink),),
        timeout=max(30, row.size / (8 * 1024 * 1024) + 30),
    )
    return ExactContent(data=sink.getvalue())


@contextmanager
def _retained_source(root, git, rows):
    """Stage truthful generated source rows from validated reachable Git blobs."""
    size = sum(row.size for row in rows)
    if shutil.disk_usage(root.parent).free < size + 64 * 1024 * 1024:
        raise OSError("Insufficient space for retained generated source")
    with tempfile.TemporaryDirectory(
        prefix="brz2obsidian-recovery-source-", dir=root.parent
    ) as name:
        source = Path(name)
        if source.stat().st_dev != root.stat().st_dev:
            raise OSError("Retained source stage is not on the vault volume")
        for start in range(0, len(rows), 128):
            group = rows[start : start + 128]
            streams = []
            try:
                for row in group:
                    target = source / row.path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    streams.append(target.open("wb"))
                verify_blobs(
                    [*git.prefix, "cat-file", "--batch"],
                    env=git.env,
                    objects=tuple(
                        (row.object_id, row.size, row.sha256, stream)
                        for row, stream in zip(group, streams, strict=True)
                    ),
                    timeout=max(
                        30, sum(row.size for row in group) / (8 * 1024 * 1024) + 30
                    ),
                )
                for stream in streams:
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                for stream in streams:
                    stream.close()
        yield source


def _restore_target_states(
    original, context, current_states, before, affected, git, *, _owner
):
    target_states = []
    target_state = (
        interpret_link_target
        if _owner is None
        else _owner._session._assembly_link_state
    )
    for target in context.current_targets:
        if target.kind == "tag":
            continue
        path = target.canonical_path
        if path in affected:
            content = _owned_content(git, before.get(path), _owner=_owner)
            target_states.append(
                target_state(
                    content,
                    target_id=target.target_id,
                    existence="missing" if content is None else "present",
                    memberships=(),
                    source_path=path,
                    output_format=7
                    if original.facts.baseline_identity.output_format == 6
                    else original.facts.baseline_identity.output_format,
                    qualify_roles=original.facts.incoming_identity.output_format
                    in QUALIFIED_OUTPUT_FORMATS,
                )
            )
        elif target.target_id in current_states:
            target_states.append(current_states[target.target_id])
        # The completed recovery observation admits an unaffected ordinary
        # physical resource without content state. Preserve that absence while
        # retaining its exact reference target; affected paths still use BEFORE.
    return target_states


def _restore_link_context(original, facts, before, affected, git, *, _owner=None):
    """Interpret the exact original target inventory with current link owners."""
    context = facts.link_context
    if context is None:
        return None
    original_context = original.facts.link_context
    current_states = {state.target_id: state for state in context.current_target_facts}
    if len(current_states) != len(context.current_target_facts):
        raise OSError("Current recovery lookup is ambiguous")
    target_states = _restore_target_states(
        original, context, current_states, before, affected, git, _owner=_owner
    )
    candidates = {doc.source_path: doc for doc in context.current_documents}
    if original_context is not None:
        for doc in original_context.current_documents:
            candidates.setdefault(doc.source_path, doc)
    documents = []
    for path, document in sorted(candidates.items()):
        content = (
            _owned_content(git, before.get(path), _owner=_owner)
            if path in affected
            else next(
                (
                    entry.current.content
                    for entry in facts.identity_inventory
                    if entry.current.path == path
                ),
                None,
            )
        )
        if content is None:
            continue
        documents.append(
            interpret_links(
                content,
                document_id=document.document_id,
                source_path=path,
                path_mode=document.path_mode,
                targets=context.current_targets,
                target_facts=tuple(target_states),
                inventory="complete",
                output_format=original.facts.incoming_identity.output_format,
                record_format=original.facts.baseline_identity.output_format,
            )
        )
    return context.model_copy(
        update={
            "incoming_targets": context.current_targets,
            "incoming_target_facts": tuple(target_states),
            "incoming_documents": tuple(documents),
        }
    )


def _operation_document_subjects(
    original,
    intent,
    origin_commit,
    git,
    current,
    *,
    direction,
    only_documents=None,
    _owner=None,
):
    """Rebind exact dependent-document versions to this admitted operation."""
    return _operation_document_subjects_from_owned(
        original,
        intent,
        origin_commit,
        git,
        current,
        review_owned_documents(original)
        if _owner is None
        else _owner._history_owned_outputs(original, ()).documents,
        direction=direction,
        only_documents=only_documents,
        _owner=_owner,
    )


def _unaffected_attachment_context(original, intent, subject, change, approval):
    """Retain a selected association, without granting any resource write."""
    if (
        subject.attachment is None
        or subject.incoming is None
        or subject.current.existence != "present"
        or subject.current.content is None
        or subject.path != subject.current.path
        or change.path != subject.path
        or change.target_path != subject.path
        or subject.path in intent.affected_paths
    ):
        return False
    selected = change.result if approval is None else approval.result
    if approval is None:
        kept = not change.requires_decision and change.disposition in (
            "no_change",
            "preserve_vault",
        )
    else:
        kept = approval.domain == "attachment" and approval.choice == "current"
    before = next((row for row in intent.before if row.path == subject.path), None)
    proposed = next((row for row in intent.proposed if row.path == subject.path), None)
    owners = tuple(
        row
        for row in original.producer_facts.identity_inventory
        if row.identity_state == "valid"
        and row.identity is not None
        and (
            row.identity.module_id,
            row.identity.collection_id,
            row.identity.item_id,
            row.facet,
        )
        == (
            original.producer_facts.incoming_identity.module_id,
            original.producer_facts.incoming_identity.collection_id,
            subject.item_id,
            subject.facet,
        )
        and row.current.path == subject.path
        and row.target == subject.source_target
    )
    return (
        kept
        and len(owners) == 1
        and selected is not None
        and before is not None
        and before == proposed
        and before.size == content_size(selected)
        and before.sha256 == content_sha(selected)
    )


def _protected_resource_context(facts, subjects, context, retained, git):
    """Keep exact historical associations for resources outside reversal writes."""
    if (
        context is None
        or facts.incoming_identity.output_format not in QUALIFIED_OUTPUT_FORMATS
    ):
        return context
    included = {(subject.item_id, subject.facet) for subject in subjects}
    protected = {
        subject.current.path: subject
        for subject in facts.subjects
        if subject.attachment is not None
        and (subject.item_id, subject.facet) not in included
        and subject.current.existence == "present"
    }
    if not protected:
        return context
    from .attachment_ownership import read_attachment_ownership

    proofs = read_attachment_ownership(
        git,
        association=retained.checkpoint.locator.association,
        roles=retained.checkpoint_roles,
        paths=set(protected),
        observation=retained,
    )
    roles = {role.commit: role.generation for role in retained.checkpoint_roles}
    bindings = {}
    for proof in proofs:
        subject = protected.get(proof.source_path)
        if (
            subject is None
            or proof.association_id != retained.checkpoint.manifest.association_id
            or roles.get(proof.checkpoint_commit) != proof.generation
            or (
                proof.identity.module_id,
                proof.identity.collection_id,
                proof.identity.item_id,
                proof.facet,
            )
            != (
                facts.incoming_identity.module_id,
                facts.incoming_identity.collection_id,
                subject.item_id,
                subject.facet,
            )
        ):
            raise OSError("Protected resource origin is not the retained association")
        target_id = subject.attachment.current_target_id
        if target_id in bindings:
            raise OSError("Protected resource origin is ambiguous")
        bindings[target_id] = proof
    # The origin's source version can precede the latest whole-vault version.
    # The native reader verifies its historical mapping/checkpoint. Current
    # bytes stay separately bound by each observed state and inventory entry.
    return context.model_copy(
        update={
            "current_target_facts": tuple(
                state.model_copy(update={"resource_origin": bindings[state.target_id]})
                if state.target_id in bindings
                else state
                for state in context.current_target_facts
            )
        }
    )


def _operation_document_subjects_from_owned(
    original,
    intent,
    origin_commit,
    git,
    current,
    owned_documents,
    *,
    direction,
    only_documents=None,
    _owner=None,
):
    before = {row.path: row for row in intent.before}
    produced = {row.path: row for row in intent.proposed}
    approved = {approval.change_id: approval for approval in original.approvals}
    subjects = []
    for change_id, decision_id, reference in owned_documents:
        if only_documents is not None and reference.target_id not in only_documents:
            continue
        approval = approved[change_id]
        if approval.decision_id != decision_id:
            raise OSError("Dependent recovery document decision is ambiguous")
        path = reference.canonical_path
        old = _owned_content(git, before.get(path), _owner=_owner)
        new = _owned_content(git, produced.get(path), _owner=_owner)
        documents = tuple(
            d
            for d in original.facts.link_context.current_documents
            if (d.document_id, d.source_path) == (reference.target_id, path)
        )
        selected_documents = tuple(
            d
            for d in (
                approval.attachment_candidate.documents
                if approval.attachment_candidate is not None
                else original.facts.link_context.incoming_documents
            )
            if (d.document_id, d.source_path) == (reference.target_id, path)
        )
        if (
            path not in intent.affected_paths
            or old is None
            or new is None
            or old == new
            or len(documents) != 1
            or documents[0].content != old
            or len(selected_documents) != 1
            or selected_documents[0].content != new
            or any(s.path == path for s in subjects)
        ):
            raise OSError("Dependent recovery document lacks exact operation versions")
        proof = OperationReversalTarget(
            schema_id="brz2obsidian.operation-reversal-target",
            schema_version=1,
            operation_id=intent.operation_id,
            operation_kind=intent.kind,
            direction=direction,
            operation_generation=intent.generation,
            history_fingerprint=_operation_history_fingerprint(origin_commit, intent),
            origin_change_id=approval.change_id,
            origin_decision_id=approval.decision_id,
            owned_targets=(reference,),
            outputs=(
                OperationReversalOutput(
                    path=path,
                    target_id=reference.target_id,
                    produced_existence="present",
                    produced=old if direction == "finish" else new,
                    current=current[path],
                    target_existence="present",
                    target=new if direction == "finish" else old,
                ),
            ),
        )
        subjects.append(
            ReconciliationSubject(
                item_id=reference.target_id,
                facet="content",
                path=path,
                baseline=ContentVersion(
                    status="unknown", content=None, unavailable_digest=None
                ),
                current=current[path],
                incoming=new if direction == "finish" else old,
                interpretation="supported",
                title=Path(path).stem,
                source_target=reference.target,
                output_role="note",
                structure=None,
                attachment=None,
                operation_reversal=proof,
            )
        )
    return tuple(subjects)


def _restore_subject_queries(original, intent, facts):
    approved = {approval.change_id: approval for approval in original.approvals}
    document_keys = {
        (subject.item_id, subject.facet)
        for subject in original.facts.subjects
        if reversal_document_target(subject) is not None
    }
    ownership_queries = []
    ownership_subjects = []
    for subject in facts.subjects:
        if (subject.item_id, subject.facet) in document_keys:
            continue
        changes = tuple(
            change
            for change in original.proposal.changes
            if (change.item_id, change.facet) == (subject.item_id, subject.facet)
        )
        if not changes and subject.path not in intent.affected_paths:
            continue
        if len(changes) != 1:
            raise OSError("Recovery subject has no unique original change")
        approval = approved.get(changes[0].change_id)
        context_only = _unaffected_attachment_context(
            original, intent, subject, changes[0], approval
        )
        if (
            approval is None
            and subject.path not in intent.affected_paths
            and not context_only
        ):
            continue
        ownership_subjects.append((subject, changes, approval, context_only))
        if not context_only:
            ownership_queries.append(
                (changes[0].change_id, None)
                if approval is None
                else (approval.change_id, approval.decision_id)
            )
    return ownership_subjects, ownership_queries, document_keys


@dataclass(frozen=True)
class _RestoreEvidence:
    original: ReviewPlan
    intent: VaultOperationIntent
    origin_commit: str
    git: _Git
    retained: _OperationObservation
    before: dict[str, object]
    produced: dict[str, object]
    source_prepared: object
    produced_source: dict[str, object]


def _reverse_owned_subjects(
    evidence, ownership_subjects, owned_outputs, current, document_keys, *, _owner
):
    subjects = []
    baseline_outputs = []
    output_references = {}
    owned_groups = iter(owned_outputs.target_groups)
    for subject, changes, approval, context_only in ownership_subjects:
        owned = () if context_only else next(owned_groups)
        rows = []
        for reference in owned:
            path = reference.canonical_path
            if path not in evidence.intent.affected_paths:
                continue
            old = _owned_content(evidence.git, evidence.before.get(path), _owner=_owner)
            new = _owned_content(
                evidence.git, evidence.produced.get(path), _owner=_owner
            )
            if (old is None) == (new is None):
                continue
            rows.append(
                OperationReversalOutput(
                    path=path,
                    target_id=reference.target_id,
                    produced_existence="absent" if new is None else "present",
                    produced=new,
                    current=current[path],
                    target_existence="absent" if old is None else "present",
                    target=old,
                )
            )
            output_references[path] = reference
        protected = (
            context_only
            or bool(document_keys)
            and _inactive_attachment_proof(evidence.original, evidence.intent, subject)
        )
        if (
            subject.path not in evidence.intent.affected_paths
            and not rows
            and not protected
        ):
            continue
        old = _owned_content(
            evidence.git, evidence.before.get(subject.path), _owner=_owner
        )
        if old is None and not rows:
            continue
        proof = (
            OperationReversalTarget(
                schema_id="brz2obsidian.operation-reversal-target",
                schema_version=1,
                operation_id=evidence.intent.operation_id,
                operation_kind=evidence.intent.kind,
                direction="restore",
                operation_generation=evidence.intent.generation,
                history_fingerprint=_operation_history_fingerprint(
                    evidence.origin_commit, evidence.intent
                ),
                origin_change_id=changes[0].change_id,
                origin_decision_id=None if approval is None else approval.decision_id,
                owned_targets=owned,
                outputs=tuple(rows),
            )
            if rows
            else None
        )
        generated = subject.incoming or (
            subject.baseline.content if subject.baseline.status == "known" else None
        )
        if (
            evidence.intent.kind == "undo"
            and evidence.intent.undo_of_receipt_commit is not None
        ):
            generated = _owned_content(
                evidence.git, evidence.produced_source.get(subject.path), _owner=_owner
            )
        subjects.append(
            subject.model_copy(
                update={
                    "baseline": ContentVersion(
                        status="known" if generated is not None else "unknown",
                        content=generated,
                        unavailable_digest=None,
                    ),
                    "incoming": old
                    if subject.path in evidence.intent.affected_paths
                    else subject.incoming,
                    "operation_reversal": proof,
                    "structure": None,
                }
            )
        )
        if generated is not None:
            baseline_outputs.append(
                FormatBaselineOutput(
                    item_id=subject.item_id, facet=subject.facet, content=generated
                )
            )
    return subjects, baseline_outputs, output_references


def _generated_document_paths(git, lineage, source_files, *, scoped_root=False):
    if (
        lineage.collection_record_path is None
        and lineage.collection_baseline_commit is None
        and not scoped_root
    ):
        return None
    record_path = lineage.collection_record_path or "migration-record.json"
    content = _owned_content(git, source_files.get(record_path))
    if content is None:
        raise OSError("Associated recovery document source mapping is unavailable")
    paths = {}
    try:
        mapping = record({record_path: content}, record_path)
        if output_identity(mapping) != lineage.identity:
            raise ValueError("Wrong collection")
        for item in mapping["item_targets"]:
            if not item["created"]:
                continue
            identity, path = item["original_identity"], item["relative_path"]
            if identity in paths or path == record_path or path not in source_files:
                raise ValueError("Ambiguous or unavailable generated document")
            paths[identity] = path
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise OSError("Associated recovery document source mapping is invalid") from exc
    return paths


def _associated_document_reversal(
    evidence, owner, selected_file, owned_groups, target, *, _owner
):
    path = owner.current.path
    change = next(
        (
            change
            for change in evidence.original.proposal.changes
            if (change.item_id, change.facet) == (owner.identity.item_id, owner.facet)
            and change.subject_id == selected_file.subject_id
        ),
        None,
    )
    if change is None:
        raise OSError("Associated recovery document has no selected source change")
    approval = next(
        (
            row
            for row in evidence.original.approvals
            if row.change_id == change.change_id
        ),
        None,
    )
    decision = None if approval is None else approval.decision_id
    query = change.change_id, decision
    owned = owned_groups.get(query)
    if owned is None:
        selection = (
            review_owned_outputs(evidence.original, (query,))
            if _owner is None
            else _owner._history_owned_outputs(evidence.original, (query,))
        )
        owned = selection.target_groups[0]
    matches = tuple(
        reference
        for reference in owned
        if reference.canonical_path == path
        and reference.identity == owner.identity
        and reference.target == owner.target
        and reference.kind == "note"
    )
    published = _owned_content(evidence.git, evidence.produced[path], _owner=_owner)
    if (
        len(matches) != 1
        or published is None
        or not same_content(published, selected_file.content)
    ):
        raise OSError("Associated recovery document has no exact published selection")
    return OperationReversalTarget(
        schema_id="brz2obsidian.operation-reversal-target",
        schema_version=1,
        operation_id=evidence.intent.operation_id,
        operation_kind=evidence.intent.kind,
        direction="restore",
        operation_generation=evidence.intent.generation,
        history_fingerprint=_operation_history_fingerprint(
            evidence.origin_commit, evidence.intent
        ),
        origin_change_id=change.change_id,
        origin_decision_id=decision,
        owned_targets=owned,
        outputs=(
            OperationReversalOutput(
                path=path,
                target_id=matches[0].target_id,
                produced_existence="present",
                produced=published,
                current=owner.current,
                target_existence="present",
                target=target,
            ),
        ),
    )


def _produced_generated_documents(evidence):
    manifest = evidence.source_prepared
    source = {row.path: row for row in manifest.source}
    paths = _generated_document_paths(evidence.git, manifest, source, scoped_root=True)
    return {item: source[path] for item, path in paths.items()}


def _restore_associated_documents(
    evidence,
    owned_outputs,
    facts,
    output_references,
    current,
    subjects,
    baseline_outputs,
    *,
    owned_groups,
    _owner,
):
    covered = {
        path
        for subject in subjects
        for path in (
            (subject.path,) if subject.path in evidence.intent.affected_paths else ()
        )
    } | set(output_references)
    source_lineage = evidence.retained.owned[evidence.source_prepared.previous][0]
    generated_files = {row.path: row for row in source_lineage.source}
    original_files = {row.path: row for row in owned_outputs.effects.files}
    original_documents = (
        set()
        if evidence.original.facts.link_context is None
        else {
            document.source_path
            for document in evidence.original.facts.link_context.current_documents
        }
    )
    associated = sorted(set(evidence.intent.affected_paths) - covered)
    if not associated:
        return
    generated_paths = _generated_document_paths(
        evidence.git, source_lineage, generated_files
    )
    produced_documents = (
        _produced_generated_documents(evidence) if generated_paths is not None else None
    )
    for path in associated:
        owners = tuple(
            item
            for item in facts.identity_inventory
            if item.current.path == path
            and item.identity_state == "valid"
            and item.identity is not None
            and item.facet == "content"
            and (
                item.identity.module_id,
                item.identity.collection_id,
            )
            == (
                evidence.original.facts.incoming_identity.module_id,
                evidence.original.facts.incoming_identity.collection_id,
            )
        )
        if (
            len(owners) != 1
            or path not in original_documents
            or path not in original_files
            or evidence.before.get(path) is None
            or evidence.produced.get(path) is None
            or current[path].content is None
            or facts.link_context is None
            or not any(
                document.source_path == path and document.status == "supported"
                for document in facts.link_context.current_documents
            )
        ):
            raise OSError("Associated recovery document lacks retained authority")
        owner = owners[0]
        generated_path = (
            path
            if generated_paths is None
            else generated_paths.get(owner.identity.item_id)
        )
        generated = _owned_content(
            evidence.git, generated_files.get(generated_path), _owner=_owner
        )
        target = _owned_content(evidence.git, evidence.before[path], _owner=_owner)
        if generated is None or target is None:
            raise OSError("Associated recovery document source is unavailable")
        proof = None
        if produced_documents is not None:
            generated = _owned_content(
                evidence.git,
                produced_documents.get(owner.identity.item_id),
                _owner=_owner,
            )
            if generated is None:
                raise OSError("Associated recovery document lacks generated output")
            proof = _associated_document_reversal(
                evidence,
                owner,
                original_files[path],
                owned_groups,
                target,
                _owner=_owner,
            )
            output_references[path] = next(
                reference
                for reference in proof.owned_targets
                if reference.canonical_path == path
            )
        subjects.append(
            ReconciliationSubject(
                item_id=owner.identity.item_id,
                facet=owner.facet,
                path=path,
                baseline=ContentVersion(
                    status="known", content=generated, unavailable_digest=None
                ),
                current=current[path],
                incoming=target,
                interpretation="supported",
                title=owner.title,
                source_target=owner.target,
                output_role="note",
                structure=None,
                attachment=None,
                operation_reversal=proof,
            )
        )
        baseline_outputs.append(
            FormatBaselineOutput(
                item_id=owner.identity.item_id,
                facet=owner.facet,
                content=generated,
            )
        )


def _restore_review_context(
    evidence, facts, subjects, output_references, current, *, _owner
):
    identity_inventory = list(facts.identity_inventory)
    target_state = (
        interpret_link_target
        if _owner is None
        else _owner._session._assembly_link_state
    )
    known_paths = {item.current.path for item in identity_inventory}
    context = facts.link_context
    for path, reference in sorted(output_references.items()):
        if path not in known_paths:
            identity_inventory.append(
                IdentityInventoryItem(
                    entry_id="recovery-output:"
                    + hashlib.sha256(path.encode()).hexdigest(),
                    facet=None,
                    identity_state="missing",
                    identity=None,
                    raw_identity=None,
                    title=Path(path).stem,
                    current=current[path],
                    target=reference.target,
                )
            )
            known_paths.add(path)
        if context is None:
            continue
        current_refs = list(context.current_targets)
        current_states = list(context.current_target_facts)
        incoming_refs = list(context.incoming_targets)
        incoming_states = list(context.incoming_target_facts)
        if reference.target_id not in {target.target_id for target in current_refs}:
            current_refs.append(reference)
            current_states.append(
                target_state(
                    current[path].content,
                    target_id=reference.target_id,
                    existence="missing" if current[path].content is None else "present",
                    memberships=(),
                    source_path=path,
                    output_format=7
                    if evidence.original.facts.incoming_identity.output_format == 6
                    else evidence.original.facts.incoming_identity.output_format,
                )
            )
        if reference.target_id not in {target.target_id for target in incoming_refs}:
            target = _owned_content(
                evidence.git, evidence.before.get(path), _owner=_owner
            )
            incoming_refs.append(reference)
            incoming_states.append(
                target_state(
                    target,
                    target_id=reference.target_id,
                    existence="missing" if target is None else "present",
                    memberships=(),
                    source_path=path,
                    output_format=7
                    if evidence.original.facts.incoming_identity.output_format == 6
                    else evidence.original.facts.incoming_identity.output_format,
                )
            )
        context = context.model_copy(
            update={
                "current_targets": tuple(current_refs),
                "current_target_facts": tuple(current_states),
                "incoming_targets": tuple(incoming_refs),
                "incoming_target_facts": tuple(incoming_states),
            }
        )
    if context is not None and output_references:
        # Retained selected outputs can qualify an actual current link that
        # the pre-operation lookup could not resolve. Bind its meaning only
        # after all exact owned output references/states have joined lookup.
        context = context.model_copy(
            update={
                "current_documents": tuple(
                    document
                    if document.status != "supported" or not document.occurrences
                    else interpret_links(
                        document.content,
                        document_id=document.document_id,
                        source_path=document.source_path,
                        path_mode=document.path_mode,
                        targets=context.current_targets,
                        target_facts=context.current_target_facts,
                        inventory="complete",
                        output_format=evidence.original.facts.incoming_identity.output_format,
                        record_format=_current_record_format(
                            evidence.original.facts,
                            document.source_path,
                            document.content,
                        ),
                    )
                    for document in context.current_documents
                ),
            }
        )
    context = _protected_resource_context(
        facts, subjects, context, evidence.retained, evidence.git
    )
    facts = facts.model_copy(
        update={
            "identity_inventory": tuple(identity_inventory),
            "link_context": context,
        }
    )
    return facts


def _restore_review(
    root, observed, *, previous=None, authority=None, undo_target=None, _owner=None
):
    original, intent, origin_commit, git, facts, preflight, current, retained = (
        _review_observation(
            root,
            observed,
            direction="restore",
            authority=authority,
            next_generation=(previous.proposal.generation + 1 if previous else None),
            undo_target=undo_target,
            _owner=_owner,
        )
    )
    before = {row.path: row for row in intent.before}
    produced = {row.path: row for row in intent.proposed}
    source_prepared = retained.owned[intent.prepared_commit][0]
    produced_source = {row.path: row for row in source_prepared.source}
    evidence = _RestoreEvidence(
        original,
        intent,
        origin_commit,
        git,
        retained,
        before,
        produced,
        source_prepared,
        produced_source,
    )
    ownership_subjects, ownership_queries, document_keys = _restore_subject_queries(
        original, intent, facts
    )
    owned_outputs = (
        review_owned_outputs(original, tuple(ownership_queries))
        if _owner is None
        else _owner._history_owned_outputs(original, tuple(ownership_queries))
    )
    subjects, baseline_outputs, output_references = _reverse_owned_subjects(
        evidence,
        ownership_subjects,
        owned_outputs,
        current,
        document_keys,
        _owner=_owner,
    )
    for subject in _operation_document_subjects_from_owned(
        original,
        intent,
        origin_commit,
        git,
        current,
        owned_outputs.documents,
        direction="restore",
        _owner=_owner,
    ):
        if subject.path in output_references or any(
            row.path == subject.path for row in subjects
        ):
            raise OSError("Dependent recovery document has multiple owners")
        subjects.append(subject)
        output_references[subject.path] = subject.operation_reversal.owned_targets[0]
    _restore_associated_documents(
        evidence,
        owned_outputs,
        facts,
        output_references,
        current,
        subjects,
        baseline_outputs,
        owned_groups=dict(
            zip(ownership_queries, owned_outputs.target_groups, strict=True)
        ),
        _owner=_owner,
    )
    if not subjects:
        raise OSError("Retained operation has no reviewed recovery subjects")
    facts = _restore_review_context(
        evidence,
        facts,
        subjects,
        output_references,
        current,
        _owner=_owner,
    )
    format_operation = facts.format_operation.model_copy(
        update={
            "kind": "source_update"
            if facts.baseline_identity == facts.incoming_identity
            else "format_transition",
            "recorded_generation": "supported",
            "baseline_source_version": facts.format_operation.target_source_version,
            "target_source_version": facts.format_operation.baseline_source_version,
            "established_baseline": (
                SupportedFormatBaseline(
                    schema_id="brz2obsidian.supported-format-baseline",
                    schema_version=1,
                    identity=facts.incoming_identity,
                    source_version=facts.format_operation.target_source_version,
                    outputs=tuple(baseline_outputs),
                )
                if facts.format_operation.target_source_version is not None
                and baseline_outputs
                else None
            ),
        }
    )
    reverse_facts = facts.model_copy(
        update={
            "proposal_id": "recovery:" + intent.operation_id + ":restore",
            "generation": previous.proposal.generation + 1 if previous else 1,
            "baseline_identity": facts.incoming_identity,
            "incoming_identity": facts.baseline_identity,
            "subjects": tuple(subjects),
            "identity_inventory": facts.identity_inventory,
            "format_operation": format_operation,
            "link_context": _restore_link_context(
                original, facts, before, set(intent.affected_paths), git, _owner=_owner
            ),
            "source_version_memory": (),
            "association_decisions": (),
            "rename_decisions": (),
            "preservation_decisions": (),
        }
    )
    preflight = _document_preflight(
        root, retained, original, intent, reverse_facts, _owner=_owner
    )
    if _owner is not None:
        return _owner._history_plan(reverse_facts, preflight, previous)
    if previous is None:
        return prepare_review(reverse_facts, preflight=preflight)
    refreshed = refresh_review(previous, reverse_facts, preflight=preflight)
    if refreshed.status != "accepted":
        raise OSError("Current recovery review could not be refreshed")
    return refreshed.plan


def _recovery_preparation(
    status, code, *, observed=None, directions=(), direction=None, review=None
):
    return VaultRecoveryPreparation(
        schema_id="brz2obsidian.vault-recovery-preparation",
        schema_version=1,
        status=status,
        code=code,
        operation_id=observed.operation_id if observed is not None else None,
        kind=observed.kind if observed is not None else None,
        generation=observed.generation if observed is not None else None,
        intent_commit=observed.intent_commit if observed is not None else None,
        available_directions=directions,
        direction=direction,
        review=review,
    )


def _prepare_terminal_cleanup(root, observed, direction):
    if direction is not None:
        return _recovery_preparation("refused", "terminal_direction_unavailable")
    if observed.code == "terminal_cleanup_required" and observed.recovery_required:
        try:
            if not _marker_valid(root, observed.operation_id):
                raise OSError("Terminal owner marker changed")
        except OSError, ValueError, TypeError, UnicodeError:
            return _recovery_preparation("unavailable", "operation_marker_invalid")
        return _recovery_preparation(
            "cleanup", "terminal_cleanup_required", observed=observed
        )
    return _recovery_preparation("refused", observed.code)


def _build_recovery_review(
    root, observed, authority, directions, *, direction, previous, _owner
):
    from .collection_placement import ImportRecoveryLinkChange

    origin_commit, origin = authority.graph.authorities[-1]
    loaded = authority.owned[origin.prepared_commit][1]
    if loaded is None:
        return _recovery_preparation("unavailable", "original_review_unavailable")
    original = (
        loaded.saved.plan
        if _owner is None
        else _owner._operation_origin(authority).saved.plan
    )
    selected_authority = (original, origin, origin_commit, authority)
    try:
        if _owner is not None and direction in ("finish", "restore"):
            with _owner._session._operation():
                builder = _finish_review if direction == "finish" else _restore_review
                review = builder(
                    root,
                    observed,
                    previous=previous,
                    authority=selected_authority,
                    _owner=_owner,
                )
            return _recovery_preparation(
                "offered",
                "recovery_review_required",
                observed=observed,
                directions=directions,
                direction=direction,
                review=review,
            )
        review = (
            _finish_review(
                root, observed, previous=previous, authority=selected_authority
            )
            if direction == "finish"
            else _restore_review(
                root, observed, previous=previous, authority=selected_authority
            )
            if direction == "restore"
            else None
        )
    except ImportRecoveryLinkChange as error:
        return _recovery_preparation("refused", str(error))
    except OSError, ValueError, TypeError, UnicodeError:
        return _recovery_preparation("unavailable", "recovery_review_unavailable")
    return _recovery_preparation(
        "offered",
        "recovery_review_required" if review is not None else "initial_recovery_choice",
        observed=observed,
        directions=directions,
        direction=direction,
        review=review,
    )


def _prepare_recovery_observed(
    root, observed, authority, *, direction=None, previous=None, _owner=None
):
    """Use one fully validated operation walk and a fresh current observation."""
    if direction not in (None, "finish", "restore"):
        return _recovery_preparation("refused", "unsupported_recovery_direction")
    if authority is not None and authority.graph.receipt is not None:
        return _prepare_terminal_cleanup(root, observed, direction)
    if authority is None or not (
        (
            observed.status in ("cancelled", "incomplete", "content_complete")
            or observed.code == "unknown_current_bytes"
        )
        and observed.recovery_required
        and observed.intent_commit is not None
        and observed.operation_id is not None
        and observed.generation is not None
    ):
        return _recovery_preparation(
            "unavailable" if observed.recovery_required else "refused", observed.code
        )
    try:
        if not recovery_operation_marker(root, authority):
            raise ValueError("Operation marker is torn or belongs to another owner")
    except OSError, ValueError, TypeError, UnicodeError:
        return _recovery_preparation("unavailable", "operation_marker_invalid")
    active = authority.graph.intent
    directions = (
        (active.direction,)
        if isinstance(active, VaultRecoveryIntent)
        else ("finish", "restore")
    )
    if direction is not None and direction not in directions:
        return _recovery_preparation("refused", "saved_recovery_direction_required")
    return _build_recovery_review(
        root,
        observed,
        authority,
        directions,
        direction=direction,
        previous=previous,
        _owner=_owner,
    )


def prepare_recovery(vault, *, direction=None, _owner=None):
    """Offer a reviewed direction after one validated operation observation."""
    root = Path(vault).absolute()
    if _owner is not None:
        try:
            _owner._observe(vault, _recovery=True)
            _owner._start_session()
            return _prepare_recovery_observed(
                root,
                _owner.observed._recovery_status,
                _owner.observed._terminal,
                direction=direction,
                _owner=_owner,
            )
        except OSError, ValueError, TypeError, UnicodeError:
            return _recovery_preparation("unavailable", "recovery_review_unavailable")
    observed, authority = _inspect_update_observation(root)
    from .collection_publication import LOCAL_LOCATOR_PENDING
    from .collection_result_locator import RESULT_LOCATOR_PENDING
    from .collection_undo_publication import pending_scoped_undo
    from .unpublished_collection import UNPUBLISHED_RECOVERY_CODES

    if direction in (None, "finish", "restore"):
        pending = pending_scoped_undo(root, authority)
        if pending is not None:
            return pending
    if observed.code == RESULT_LOCATOR_PENDING and direction in (
        None,
        "finish",
        "restore",
    ):
        offered = _recovery_preparation("cleanup", observed.code, observed=observed)
        return VaultRecoveryPreparation.model_validate(
            offered.model_dump() | {"result_locator_checkpoint": observed.result_commit}
        )
    if (
        observed.code == LOCAL_LOCATOR_PENDING
        and direction in (None, "finish", "restore")
        or observed.code in UNPUBLISHED_RECOVERY_CODES
        and direction in (None, "restore")
    ):
        return VaultRecoveryPreparation(
            schema_id="brz2obsidian.vault-recovery-preparation",
            schema_version=1,
            status="cleanup",
            code=observed.code,
            operation_id=observed.operation_id,
            kind="apply",
            generation=observed.generation,
            intent_commit=None,
            unpublished_checkpoint=observed.checkpoint_commit,
            available_directions=(),
            review=None,
        )
    return _prepare_recovery_observed(root, observed, authority, direction=direction)


def _refused_recovery(code):
    return _recovery_preparation("refused", code)


def refresh_recovery(vault, preparation, *, _owner=None):
    """Refresh one selected recovery review from actual current bytes."""
    try:
        previous = VaultRecoveryPreparation.model_validate(preparation)
        if (
            previous.status != "offered"
            or previous.direction is None
            or previous.review is None
        ):
            return _refused_recovery("recovery_review_required")
        root = Path(vault).absolute()
        if _owner is None:
            observed, authority = _inspect_update_observation(root)
        else:
            _owner._observe(vault, _recovery=True)
            observed, authority = (
                _owner.observed._recovery_status,
                _owner.observed._terminal,
            )
        current = _prepare_recovery_observed(
            root,
            observed,
            authority,
            direction=previous.direction,
            previous=previous.review,
            _owner=_owner,
        )
        if (
            current.status != "offered"
            or current.operation_id != previous.operation_id
            or current.intent_commit != previous.intent_commit
            or _owner is not None
            and (current.kind, current.generation)
            != (previous.kind, previous.generation)
            or previous.direction not in current.available_directions
        ):
            return _refused_recovery("recovery_authority_changed")
        return VaultRecoveryPreparation.model_validate(
            current.model_copy(
                update={
                    "code": "recovery_review_refreshed",
                }
            )
        )
    except OSError, ValueError, TypeError, UnicodeError:
        return _refused_recovery("recovery_refresh_unavailable")


def resolve_recovery(vault, preparation, action):
    """Record an explicit S1 choice only for the same current recovery facts."""
    try:
        previous = VaultRecoveryPreparation.model_validate(preparation)
        if (
            previous.status != "offered"
            or previous.direction is None
            or previous.review is None
        ):
            return _refused_recovery("recovery_review_required")
        root = Path(vault).absolute()
        observed, authority = _inspect_update_observation(root)
        current = _prepare_recovery_observed(
            root, observed, authority, direction=previous.direction
        )
        if (
            current.status != "offered"
            or current.operation_id != previous.operation_id
            or current.intent_commit != previous.intent_commit
            or current.review is None
        ):
            return _refused_recovery("recovery_authority_changed")
        observed_facts = current.review.facts.model_copy(
            update={"generation": previous.review.facts.generation}
        )
        if (
            observed_facts != previous.review.facts
            or current.review.preflight != previous.review.preflight
        ):
            return _refused_recovery("recovery_review_stale")
        transition = resolve_review(previous.review, action)
        if transition.status != "accepted":
            return _refused_recovery("recovery_" + transition.code)
        return VaultRecoveryPreparation.model_validate(
            previous.model_copy(
                update={"code": "recovery_choice_recorded", "review": transition.plan}
            )
        )
    except OSError, ValueError, TypeError, UnicodeError:
        return _refused_recovery("recovery_resolution_unavailable")


def _same_recovery_review(offered, saved):
    """A saved choice may advance readiness, never change observed facts."""
    if offered.review is None or saved.review is None:
        return False
    current_facts = offered.review.facts.model_copy(
        update={"generation": saved.review.facts.generation}
    )
    return (
        offered.operation_id == saved.operation_id
        and offered.intent_commit == saved.intent_commit
        and offered.kind == saved.kind
        and offered.direction == saved.direction
        and canonical_equal(current_facts, saved.review.facts)
        and offered.review.preflight == saved.review.preflight
    )


def _recovery_result_status(kind, direction, original_effect):
    if direction == "restore":
        return "restored"
    if kind == "undo":
        return "undone"
    return "applied" if original_effect else "no_content_change"


def _refuse_known_recovery(observed, code, *, start):
    """A refused new action does not erase the validated stopped operation."""
    return _outcome(
        "refused",
        code,
        start=start,
        operation_id=observed.operation_id,
        kind=observed.kind,
        direction=observed.direction,
        review_generation=observed.review_generation,
        generation=observed.generation,
        phase=observed.phase,
        publication=observed.publication,
        history=observed.history,
        planned=observed.planned_files,
        published=observed.published_files,
        changed=observed.authored_files_changed,
        checkpoint=observed.checkpoint_commit,
        intent=observed.intent_commit,
        result=observed.result_commit,
        receipt=observed.receipt_commit,
        stop=observed.stop_commit,
        recovery=observed.recovery_required,
    )


def _stopped_before_recovery_intent(
    observed, status, code, *, start, direction, review_generation, prepared=None
):
    """A failed preparation leaves the earlier stopped operation authoritative."""
    retained_prepared = prepared is not None
    return _outcome(
        status,
        code,
        start=start,
        operation_id=observed.operation_id,
        kind=observed.kind,
        direction=direction,
        review_generation=review_generation,
        generation=observed.generation,
        phase="prepared",
        publication=observed.publication,
        history="prepared" if retained_prepared else observed.history,
        planned=observed.planned_files,
        published=observed.published_files,
        changed=observed.authored_files_changed,
        checkpoint=prepared if retained_prepared else observed.checkpoint_commit,
        intent=observed.intent_commit,
        result=observed.result_commit,
        receipt=observed.receipt_commit,
        stop=observed.stop_commit,
        recovery=True,
    )


class _OwnedRecoveryCleanupFailure(Exception):
    def __init__(self, result):
        self.result = result


def _cleanup_verified_terminal(root, saved, *, start, _owners=None):
    observed, authority = _inspect_update_observation(root, _owners=_owners)
    if (
        authority is None
        or authority.graph.receipt is None
        or observed.code != "terminal_cleanup_required"
        or observed.operation_id != saved.operation_id
        or observed.intent_commit != saved.intent_commit
        or observed.generation != saved.generation
        or not _marker_valid(root, saved.operation_id)
    ):
        return _outcome("refused", "terminal_cleanup_stale", start=start)
    from .collection_publication import read_native_marker, scoped_operation_marker

    try:
        _adopt(root, saved.operation_id)
        held, held_authority = _inspect_update_observation(root, _owners=_owners)
        if (
            held_authority is None
            or held_authority.graph.commit != authority.graph.commit
            or held.code != "terminal_cleanup_required"
        ):
            _park(root, saved.operation_id)
            return _outcome("refused", "terminal_cleanup_changed", start=start)
        marker = read_native_marker(root)
        scoped = (
            marker is not None
            and marker.collection_saved_checkpoint is not None
            and scoped_operation_marker(_Git(root), held_authority.graph, marker)
        )
        release_native_operation(root, saved.operation_id)
        final = _inspect_update_observation(root, _owners=_owners)[0]
        if final.status not in ("applied", "no_content_change", "undone", "restored"):
            raise OSError("Verified terminal status was not rediscovered")
        if scoped:
            return final.model_copy(
                update={"published_files": 0, "authored_files_changed": False}
            )
        return final
    except OSError, ValueError, TypeError:
        _park(root, saved.operation_id)
        return _outcome(
            "content_complete",
            "terminal_cleanup_required",
            start=start,
            operation_id=saved.operation_id,
            kind=saved.kind,
            generation=saved.generation,
            phase="terminal",
            publication="complete",
            history="terminal",
            intent=saved.intent_commit,
            recovery=True,
        )


@dataclass(frozen=True)
class _RecoveryPublication:
    root: Path
    saved: VaultRecoveryPreparation
    observed: VaultApplyResult
    authority: _OperationObservation
    subjects: tuple[VaultSubject, ...]
    selected: SelectedReviewEffects
    export: object
    owners: ExitStack | None
    start: float
    progress: object


@dataclass(frozen=True)
class _RecoveryLineage:
    history: object
    association: object
    origin_commit: str
    origin: VaultOperationIntent
    source_manifest: object


@dataclass(frozen=True)
class _RecoveryPaths:
    before: dict[str, VaultFile]
    selected_rows: dict[str, SelectedReviewFile]
    selected_files: dict[str, ContentValue]
    removals: set[str]
    changed: set[str]


@dataclass(frozen=True)
class _RecoveryStage:
    proposed_root: Path
    before_metadata: dict
    result_metadata: dict
    prepared_parents: dict
    parent_metadata: dict


@dataclass(frozen=True)
class _RecoveryJournal:
    git: _Git
    manifest: object
    intent: VaultRecoveryIntent
    ref: str


@dataclass
class _RecoveryProgress:
    acquired: bool = False
    phase: str = "admission"
    prepared_commit: str | None = None
    recovery_commit: str | None = None
    result_commit: str | None = None
    receipt_commit: str | None = None
    published: int = 0
    planned: int = 0
    failure_code: str = "recovery_unavailable"
    generation: int | None = None


def _read_recovery_operation(root, owners):
    return (
        _inspect_update_observation(root)
        if owners is None
        else _inspect_update_observation(root, _owners=owners)
    )


def _recovery_prelease_refusal(known, code, start, owner):
    outcome = (
        _outcome(
            "refused",
            code,
            start=start,
            publication="unknown",
            history="unknown",
            recovery=True,
        )
        if known is None
        else _refuse_known_recovery(known, code, start=start)
    )
    if owner is not None and owner._cancel.is_set():
        return outcome.model_copy(
            update={
                "status": "cancelled",
                "code": "cancelled_before_recovery_lease",
            }
        )
    return outcome


def _revalidate_recovery_review(root, observed, authority, saved, *, start, owner):
    fresh = _prepare_recovery_observed(
        root, observed, authority, direction=saved.direction, _owner=owner
    )
    if (
        fresh.status != "offered"
        or not _same_recovery_review(fresh, saved)
        or (owner is not None and fresh.generation != saved.generation)
    ):
        if authority is not None and observed.operation_id == saved.operation_id:
            return _refuse_known_recovery(
                observed, "recovery_review_stale", start=start
            )
        return _outcome("refused", "recovery_review_stale", start=start)


def _export_recovery_authority_matches(observed, authority, saved):
    return not (
        authority is None
        or not observed.recovery_required
        or (
            observed.operation_id,
            observed.kind,
            observed.generation,
            observed.intent_commit,
        )
        != (
            saved.operation_id,
            saved.kind,
            saved.generation,
            saved.intent_commit,
        )
        or observed.review_generation is not None
        and observed.direction != saved.direction
    )


def _observe_recovery_for_execute(vault, root, owner, owners):
    if owner is None:
        return _read_recovery_operation(root, owners)
    owner._observe(vault, _recovery=True)
    return owner.observed._recovery_status, owner.observed._terminal


def _select_recovery_publication(
    vault, root, saved, *, start, progress, _owner, _owners
):
    known = (
        None
        if _owner is None or _owner.observed is None
        else _owner.observed._recovery_status
    )

    try:
        selected = (
            select_review_effects(saved.review)
            if _owner is None
            else _owner._session.select_review_effects(saved.review)
        )
        if selected.status != "selected":
            if _owner is not None and known is not None:
                return _recovery_prelease_refusal(known, selected.code, start, _owner)
            return _outcome("refused", selected.code, start=start)
        if not supported_durable_volume(root):
            return _outcome("refused", "unsupported_durable_volume", start=start)

        observed, authority = _observe_recovery_for_execute(
            vault, root, _owner, _owners
        )
        known = observed
        refusal = _revalidate_recovery_review(
            root, observed, authority, saved, start=start, owner=_owner
        )
        if refusal is not None:
            return refusal
        try:
            subjects = _review_subjects(saved.review, selected)
        except OSError, ValueError, TypeError:
            return _refuse_known_recovery(
                observed, "invalid_recovery_scope", start=start
            )
        export = None if _owner is None else _owner._publication_export(saved.review)
        if export is not None:
            selected = export.effects
            observed, authority = _read_recovery_operation(root, _owners)
            known = observed
            if not _export_recovery_authority_matches(observed, authority, saved):
                return _refuse_known_recovery(
                    observed, "recovery_review_stale", start=start
                )
    except OSError, ValueError, TypeError, UnicodeError:
        if _owner is None:
            raise
        return _recovery_prelease_refusal(
            known, "recovery_review_unavailable", start, _owner
        )
    return _RecoveryPublication(
        root,
        saved,
        observed,
        authority,
        subjects,
        selected,
        export,
        _owners,
        start,
        progress,
    )


def _recheck_held_recovery_marker(publication, state):
    root = publication.root
    operation = publication.saved.operation_id
    try:
        if owns_operation(root, operation) and recovery_operation_marker(
            root, publication.authority
        ):
            return True
    except OSError, ValueError, TypeError, UnicodeError:
        pass
    _park(root, operation)
    state.acquired = False
    return False


def _adopt_recovery(publication, state):
    before_lease = _inspect_vault_for_recovery(
        publication.root, publication.authority, subjects=publication.subjects
    )
    origin = publication.authority.graph.authorities[-1][1]
    original_prepared, original_saved = publication.authority.owned[
        origin.prepared_commit
    ]
    if (
        before_lease.status != "supported"
        or not _current_review_matches(publication.saved.review, before_lease)
        or _review_preflight(
            before_lease,
            original_prepared,
            original_saved.saved.plan,
            publication.authority,
        )
        != publication.saved.review.preflight
    ):
        return _refuse_known_recovery(
            publication.observed, "recovery_review_stale", start=publication.start
        )
    _adopt(publication.root, publication.saved.operation_id)
    state.acquired = True
    if not _recheck_held_recovery_marker(publication, state):
        return _refuse_known_recovery(
            publication.observed, "operation_marker_invalid", start=publication.start
        )
    return before_lease


def _observe_recovery_lineage(publication, before_lease):
    history = _inspect_retained_history(
        publication.root,
        publication.authority,
        subjects=publication.subjects,
        active_operation=publication.saved.operation_id,
    )
    if (
        history.status != "intact"
        or history.admission.status != "supported"
        or history.admission.inventory != before_lease.inventory
        or history.admission.policy_fingerprint != before_lease.policy_fingerprint
    ):
        return _refuse_known_recovery(
            publication.observed, "recovery_admission_required", start=publication.start
        )
    association = history.checkpoint.locator.association
    origin_commit, origin = publication.authority.graph.authorities[-1]
    original_prepared = publication.authority.owned[origin.prepared_commit][0]
    source_manifest = (
        original_prepared
        if publication.saved.direction == "finish"
        else publication.authority.owned[original_prepared.previous][0]
    )
    if (
        publication.observed.operation_id != publication.saved.operation_id
        or publication.observed.intent_commit != publication.saved.intent_commit
        or (
            isinstance(publication.authority.graph.intent, VaultRecoveryIntent)
            and publication.observed.direction != publication.saved.direction
        )
        or association.association_id != origin.association_id
        or publication.saved.review.facts.incoming_identity != source_manifest.identity
        or _operation_history_fingerprint(origin_commit, origin)
        != _operation_history_fingerprint(
            publication.authority.graph.origin_intent_commit, origin
        )
    ):
        return _refuse_known_recovery(
            publication.observed,
            "recovery_source_lineage_changed",
            start=publication.start,
        )
    return _RecoveryLineage(
        history, association, origin_commit, origin, source_manifest
    )


def _held_collection_finish_refusal(publication, lineage, selected_files, removals):
    if publication.saved.direction != "finish":
        return None
    from .collection_placement import (
        ImportRecoveryLinkChange,
        require_collection_finish_links,
    )

    prepared, loaded = publication.authority.owned[lineage.origin.prepared_commit]
    try:
        require_collection_finish_links(
            lineage.history.admission,
            lineage.history.checkpoint,
            prepared.collection_record_path,
            loaded.saved.plan,
            selected_files,
            removals,
            produced={row.path: row.content for row in loaded.historical_effects.files},
            origin=lineage.origin,
        )
    except ImportRecoveryLinkChange as error:
        return _refuse_known_recovery(
            publication.observed,
            str(error),
            start=publication.start,
        )
    return None


def _plan_recovery_paths(publication, lineage, state):
    selected = publication.selected
    accepted_tracking = {
        subject_id
        for requirement in lineage.history.admission.preflight.consents
        if requirement.kind == "tracking"
        and any(
            decision.consent_id == requirement.consent_id
            and decision.kind == requirement.kind
            and decision.choice == "accept"
            for decision in publication.saved.review.consents
        )
        for subject_id in requirement.subjects
    }
    included_paths = {
        subject.path
        for subject in publication.subjects
        if subject.subject_id in accepted_tracking
    }
    before = {
        row.path: row
        for row in lineage.history.admission.inventory
        if not row.excluded or row.path in included_paths
    }
    selected_rows = {row.path: row for row in selected.files}
    selected_files = {path: row.content for path, row in selected_rows.items()}
    removals = set(selected.remove_paths)
    from .attachment_ownership import (
        review_ownership_claims,
        validate_removal_continuations,
    )

    satisfied = validate_removal_continuations(
        review_ownership_claims(publication.saved.review, selected)[0],
        origin=lineage.origin,
        original=publication.authority.owned[lineage.origin.prepared_commit][
            1
        ].saved.plan,
        origin_commit=lineage.origin_commit,
        before=tuple(before.values()),
        direction=publication.saved.direction,
        effects=publication.authority.owned[lineage.origin.prepared_commit][
            1
        ].historical_effects,
    )
    removals -= satisfied
    if any(not _safe_relative(path) for path in (*selected_files, *removals)):
        return _refuse_known_recovery(
            publication.observed, "unsafe_recovery_path", start=publication.start
        )
    if any(path not in before for path in removals):
        return _refuse_known_recovery(
            publication.observed, "recovery_removal_missing", start=publication.start
        )
    changed = {
        path
        for path, data in selected_files.items()
        if path not in before
        or before[path].size != content_size(data)
        or before[path].sha256 != content_sha(data)
    } | removals
    if not changed.issubset(lineage.origin.affected_paths):
        return _refuse_known_recovery(
            publication.observed, "recovery_scope_changed", start=publication.start
        )
    refusal = _held_collection_finish_refusal(
        publication, lineage, selected_files, removals
    )
    if refusal is not None:
        return refusal
    state.planned = len(changed)
    stage_need = (
        sum(row.size for path, row in before.items() if path not in removals)
        + sum(content_size(data) for data in selected_files.values())
        + sum(row.size for row in lineage.source_manifest.source)
        + 128 * 1024 * 1024
        + 4096
        * (len(before) + len(selected_files) + len(lineage.source_manifest.source))
    )
    if shutil.disk_usage(publication.root.parent).free < stage_need:
        return _refuse_known_recovery(
            publication.observed,
            "insufficient_recovery_stage_resources",
            start=publication.start,
        )
    return _RecoveryPaths(before, selected_rows, selected_files, removals, changed)


def _write_recovery_stage(publication, paths, proposed_root, result_metadata):
    for path, data in paths.selected_files.items():
        target = proposed_root / path
        stage_parent_security(publication.root, proposed_root, Path(path).parent)
        with target.open("wb") as stream:
            if publication.export is None:
                stream.write(data.data)
            else:
                publication.export.stage(paths.selected_rows[path], stream)
            stream.flush()
            os.fsync(stream.fileno())
        if publication.export is not None:
            info, sha, _, _ = observe_file(proposed_root, target, prefix_limit=0)
            if (info.st_size, sha) != (
                content_size(data),
                content_sha(data),
            ):
                raise OSError(
                    "Recovery stage differs from the canonical selected content"
                )
        if path in paths.before:
            shutil.copymode(publication.root / path, target)
        if path in paths.changed:
            if path in paths.before:
                retained_metadata(publication.root / path, copy_to=target)
            result_metadata[path] = retained_metadata(target)
            _flush_stage(target)


def _stage_recovery(publication, paths, proposed_root):
    if proposed_root.stat().st_dev != publication.root.stat().st_dev:
        return _refuse_known_recovery(
            publication.observed, "same_volume_stage_required", start=publication.start
        )
    stage_parent_security(publication.root, proposed_root, Path("."))
    before_metadata = {}
    result_metadata = {}
    for path, row in paths.before.items():
        if path in paths.removals:
            continue
        target = proposed_root / path
        stage_parent_security(publication.root, proposed_root, Path(path).parent)
        if not _same_file(publication.root, row):
            return _refuse_known_recovery(
                publication.observed, "current_bytes_changed", start=publication.start
            )
        if path in paths.changed:
            before_metadata[path] = retained_metadata(publication.root / path)
            copy_stage(publication.root / path, target)
        else:
            shutil.copy2(publication.root / path, target)
    _write_recovery_stage(publication, paths, proposed_root, result_metadata)
    for path in paths.removals:
        before_metadata[path] = retained_metadata(publication.root / path)
    prepared_parents = _prepare_parents(
        publication.root,
        proposed_root,
        (path for path in paths.changed if path in paths.selected_files),
    )
    parent_metadata = {
        path: retained_directory_metadata(stage)
        for path, stage in prepared_parents.items()
    }
    return _RecoveryStage(
        proposed_root,
        before_metadata,
        result_metadata,
        prepared_parents,
        parent_metadata,
    )


def _retain_recovery_preparation(
    publication, lineage, stage, state, source, cancel_requested
):
    state.phase = "prepared"
    prepared = capture_checkpoint(
        publication.root,
        source,
        vault_id=lineage.association.vault_id,
        import_id=lineage.association.import_id,
        identity=lineage.source_manifest.identity,
        admission=lineage.history.admission,
        subjects=publication.subjects,
        review=publication.saved.review,
        boundary="prepared",
        proposed=stage.proposed_root,
        active_operation=publication.saved.operation_id,
        recovery_direction=publication.saved.direction,
        _observation=(publication.observed, publication.authority),
        **(
            {}
            if publication.export is None
            else {"_owned_export": publication.export, "_owners": publication.owners}
        ),
        progress=publication.progress,
    )
    reused_preparation = (
        prepared.status == "unchanged"
        and prepared.code == "already_retained"
        and prepared.history_retained
        and prepared.commit == publication.authority.unpublished_prepared
    )
    if prepared.status != "captured" and not reused_preparation:
        return _stopped_before_recovery_intent(
            publication.observed,
            "refused" if prepared.status == "refused" else "failed",
            "recovery_prepare_" + prepared.code,
            start=publication.start,
            direction=publication.saved.direction,
            review_generation=publication.saved.review.proposal.generation,
            prepared=prepared.commit if prepared.history_retained else None,
        )
    state.prepared_commit = prepared.commit
    if cancel_requested():
        return _stopped_before_recovery_intent(
            publication.observed,
            "cancelled",
            "cancelled_before_recovery_intent",
            start=publication.start,
            direction=publication.saved.direction,
            review_generation=publication.saved.review.proposal.generation,
            prepared=state.prepared_commit,
        )


def _rediscover_recovery_preparation(publication):
    tip = (
        inspect_history(
            publication.root,
            subjects=publication.subjects,
            active_operation=publication.saved.operation_id,
        )
        if publication.export is None
        else _inspect_history(
            publication.root,
            subjects=publication.subjects,
            active_operation=publication.saved.operation_id,
            _metadata_only=True,
            _owners=publication.owners,
        )
    )
    if (
        tip.status != "intact"
        or tip.checkpoint is None
        or tip.checkpoint.manifest is None
        or tip.checkpoint.manifest.boundary != "prepared"
    ):
        raise OSError("Recovery preparation could not be rediscovered")
    manifest = tip.checkpoint.manifest
    return manifest


def _record_recovery_intent(publication, lineage, paths, stage, state, git, manifest):
    state.generation = manifest.generation
    intent = VaultRecoveryIntent(
        schema_id="brz2obsidian.vault-recovery-intent",
        schema_version=1,
        operation_id=publication.saved.operation_id,
        kind=lineage.origin.kind,
        generation=state.generation,
        direction=publication.saved.direction,
        association_id=manifest.association_id,
        prepared_commit=state.prepared_commit,
        before=manifest.preimage,
        proposed=manifest.proposed,
        affected_paths=tuple(sorted(paths.changed)),
        protected_paths=tuple(sorted(set(paths.before) - paths.changed)),
        before_metadata=tuple(
            VaultPathMetadata(
                path=path,
                mode=value[0],
                attributes=value[1],
                security=value[2],
            )
            for path, value in sorted(stage.before_metadata.items())
        ),
        result_metadata=tuple(
            VaultPathMetadata(
                path=path,
                mode=value[0],
                attributes=value[1],
                security=value[2],
            )
            for path, value in sorted(stage.result_metadata.items())
        ),
        created_directories=tuple(
            VaultPathMetadata(
                path=path.as_posix(),
                mode=value[0],
                attributes=value[1],
                security=value[2],
            )
            for path, value in sorted(
                stage.parent_metadata.items(), key=lambda item: item[0].as_posix()
            )
        ),
        origin_intent_commit=lineage.origin_commit,
        previous_operation_commit=publication.authority.graph.commit,
        review_generation=publication.saved.review.proposal.generation,
    )
    op_ref = (
        "refs/brz2obsidian/imports/"
        + manifest.association_id
        + "/operations/"
        + publication.saved.operation_id
    )
    state.phase = "intent"
    state.recovery_commit = _journal(
        git,
        "recovery.json",
        intent,
        parents=(publication.authority.graph.commit, state.prepared_commit),
        previous=publication.authority.graph.commit,
        ref=op_ref,
    )
    return _RecoveryJournal(git, manifest, intent, op_ref)


def _publish_recovery_path(path, root, stage, executor, old, new, expected_metadata):
    target = root / path
    if old is None:
        if os.path.lexists(target):
            raise OSError("Recovery creation path became occupied")
    elif not _same_file(root, old):
        raise OSError("Recovery current bytes changed before transition")
    if new is None:
        destination = stage.proposed_root / (
            "removed-" + hashlib.sha256(path.encode()).hexdigest()
        )
        executor.remove(target, destination)
    else:
        staged_file = stage.proposed_root / path
        if not _same_file(stage.proposed_root, new):
            raise OSError("Prepared recovery bytes changed")
        _ensure_parents(
            root, target, stage.prepared_parents, stage.parent_metadata, executor
        )
        executor.move(staged_file, target, replace=old is not None)
        if not _same_file(root, new) or not _metadata_matches(
            root, path, expected_metadata[path]
        ):
            raise OSError("Published recovery result changed")


def _publish_recovery_paths(
    publication, lineage, paths, stage, state, journal, executor, cancel_requested
):
    from brz2obsidian.application.vault_progress_contracts import report_progress

    state.phase = "publication"
    report_progress(
        publication.progress,
        "publication",
        operation_id=publication.saved.operation_id,
        operation_generation=state.generation,
        intent_commit=state.recovery_commit,
        completed_units=state.published,
        total_units=state.planned,
        unit="files",
    )
    proposed = {row.path: row for row in journal.manifest.proposed}
    prior = {row.path: row for row in journal.manifest.preimage}
    expected_metadata = {row.path: row for row in journal.intent.result_metadata}
    for path in sorted(paths.changed):
        if cancel_requested():
            stopped = VaultOperationStop(
                schema_id="brz2obsidian.vault-operation-stop",
                schema_version=1,
                operation_id=publication.saved.operation_id,
                kind=lineage.origin.kind,
                generation=state.generation,
                direction=publication.saved.direction,
                status="cancelled",
                intent_commit=state.recovery_commit,
                acknowledged_after_files=state.published,
            )
            stop_commit = _journal(
                journal.git,
                "stop.json",
                stopped,
                parents=(state.recovery_commit,),
                previous=state.recovery_commit,
                ref=journal.ref,
            )
            return _outcome(
                "cancelled",
                "cancelled_after_recovery_intent",
                start=publication.start,
                operation_id=publication.saved.operation_id,
                kind=lineage.origin.kind,
                direction=publication.saved.direction,
                review_generation=publication.saved.review.proposal.generation,
                generation=state.generation,
                phase=state.phase,
                publication="partial" if state.published else "not_published",
                history="intent",
                planned=state.planned,
                published=state.published,
                changed=bool(state.published),
                checkpoint=state.prepared_commit,
                intent=state.recovery_commit,
                stop=stop_commit,
                recovery=True,
            )
        _publish_recovery_path(
            path,
            publication.root,
            stage,
            executor,
            prior.get(path),
            proposed.get(path),
            expected_metadata,
        )
        state.published += 1
        report_progress(
            publication.progress,
            "publication",
            operation_id=publication.saved.operation_id,
            operation_generation=state.generation,
            intent_commit=state.recovery_commit,
            completed_units=state.published,
            total_units=state.planned,
            unit="files",
        )
    report_progress(
        publication.progress,
        "final_verification",
        operation_id=publication.saved.operation_id,
        operation_generation=state.generation,
        intent_commit=state.recovery_commit,
    )
    if any(not _same_file(publication.root, row) for row in journal.manifest.proposed):
        raise OSError("Complete recovery inventory changed")
    if any(
        os.path.lexists(publication.root / path) for path in set(prior) - set(proposed)
    ):
        raise OSError("Removed recovery path remains visible")


def _retain_recovery_result(publication, lineage, paths, state, source, journal):
    from brz2obsidian.application.vault_progress_contracts import report_progress

    state.phase = "result"
    report_progress(
        publication.progress,
        "final_reporting",
        operation_id=publication.saved.operation_id,
        operation_generation=state.generation,
        intent_commit=state.recovery_commit,
    )
    result_observation = _read_recovery_operation(publication.root, publication.owners)
    current = _inspect_retained_history(
        publication.root,
        result_observation[1],
        subjects=publication.subjects,
        active_operation=publication.saved.operation_id,
    )
    result_checkpoint = capture_checkpoint(
        publication.root,
        source,
        vault_id=lineage.association.vault_id,
        import_id=lineage.association.import_id,
        identity=lineage.source_manifest.identity,
        admission=current.admission,
        subjects=publication.subjects,
        boundary="result",
        expected_prepared=state.prepared_commit,
        active_operation=publication.saved.operation_id,
        operation_intent_commit=state.recovery_commit,
        _observation=result_observation,
        **(
            {}
            if publication.export is None
            else {
                "review": publication.export.saved.plan,
                "_owned_export": publication.export,
                "_owners": publication.owners,
            }
        ),
        progress=publication.progress,
    )
    if result_checkpoint.status != "captured":
        state.failure_code = "result_" + result_checkpoint.code
        raise OSError("Recovery result checkpoint was not retained")
    state.result_commit = result_checkpoint.commit
    terminal = _recovery_result_status(
        lineage.origin.kind,
        publication.saved.direction,
        bool(lineage.origin.affected_paths),
    )
    receipt = VaultOperationReceipt(
        schema_id="brz2obsidian.vault-operation-receipt",
        schema_version=1,
        operation_id=publication.saved.operation_id,
        kind=lineage.origin.kind,
        generation=state.generation,
        status=terminal,
        direction=publication.saved.direction,
        intent_commit=state.recovery_commit,
        prepared_commit=state.prepared_commit,
        result_commit=state.result_commit,
        published_paths=tuple(sorted(paths.changed)),
    )
    state.phase = "terminal"
    state.receipt_commit = _journal(
        journal.git,
        "receipt.json",
        receipt,
        parents=(state.recovery_commit, state.result_commit),
        previous=state.recovery_commit,
        ref=journal.ref,
    )
    return terminal


def _report_recovery_failure(publication, state):
    failure = (
        _read_recovery_operation(publication.root, publication.owners)[0]
        if state.phase in ("intent", "publication", "result", "terminal")
        else None
    )
    if (
        failure is not None
        and failure.operation_id == publication.saved.operation_id
        and failure.intent_commit is not None
    ):
        return _outcome(
            "content_complete"
            if failure.status in ("applied", "undone", "restored", "no_content_change")
            else failure.status,
            state.failure_code + "_" + failure.code,
            start=publication.start,
            operation_id=publication.saved.operation_id,
            kind=failure.kind,
            direction=failure.direction,
            review_generation=failure.review_generation,
            generation=failure.generation,
            phase=state.phase,
            publication=failure.publication,
            history=failure.history,
            planned=state.planned,
            published=failure.published_files,
            changed=failure.authored_files_changed,
            checkpoint=state.prepared_commit,
            intent=failure.intent_commit,
            result=failure.result_commit or state.result_commit,
            receipt=failure.receipt_commit,
            stop=failure.stop_commit,
            recovery=True,
        )
    return _outcome(
        "content_complete" if state.result_commit is not None else "unknown",
        state.failure_code,
        start=publication.start,
        operation_id=publication.saved.operation_id,
        kind=publication.saved.kind,
        direction=publication.saved.direction,
        review_generation=publication.saved.review.proposal.generation,
        generation=state.generation,
        phase=state.phase,
        publication="complete" if state.result_commit is not None else "unknown",
        history="result"
        if state.result_commit is not None
        else "unknown"
        if state.phase == "intent"
        else "intent"
        if state.recovery_commit is not None
        else "prepared"
        if state.prepared_commit is not None
        else "none",
        planned=state.planned,
        published=state.published,
        changed=True if state.result_commit is not None and state.planned else None,
        checkpoint=state.prepared_commit,
        intent=state.recovery_commit,
        result=state.result_commit,
        receipt=state.receipt_commit,
        recovery=True,
    )


def _release_recovery_lease(publication, state):
    if state.acquired and state.recovery_commit is not None:
        _park(publication.root, publication.saved.operation_id)
    elif state.acquired:
        pending_exception = sys.exc_info()[0]
        try:
            release_native_operation(publication.root, publication.saved.operation_id)
        except OSError, ValueError, TypeError:
            if pending_exception is None or issubclass(
                pending_exception, (OSError, ValueError, TypeError)
            ):
                try:
                    stopped = _read_recovery_operation(
                        publication.root, publication.owners
                    )[0]
                except OSError, ValueError, TypeError, UnicodeError:
                    stopped = None
                if (
                    stopped is None
                    or stopped.operation_id != publication.saved.operation_id
                ):
                    raise _OwnedRecoveryCleanupFailure(
                        _outcome(
                            "unknown",
                            "recovery_cleanup_failed",
                            start=publication.start,
                            operation_id=publication.saved.operation_id,
                            kind=publication.saved.kind,
                            direction=publication.saved.direction,
                            review_generation=publication.saved.review.proposal.generation,
                            generation=publication.observed.generation,
                            phase="prepared" if state.prepared_commit else "admission",
                            publication="unknown",
                            history=(
                                "prepared"
                                if state.prepared_commit
                                else publication.observed.history
                            ),
                            planned=max(
                                state.planned, publication.observed.planned_files
                            ),
                            published=publication.observed.published_files,
                            checkpoint=(
                                state.prepared_commit
                                or publication.observed.checkpoint_commit
                            ),
                            intent=publication.observed.intent_commit,
                            stop=publication.observed.stop_commit,
                            changed=None,
                            recovery=True,
                        )
                    )
                raise _OwnedRecoveryCleanupFailure(
                    _refuse_known_recovery(
                        stopped, "recovery_cleanup_failed", start=publication.start
                    )
                )


def _completed_recovery(publication, lineage, paths, state, terminal):
    release_native_operation(publication.root, publication.saved.operation_id)
    state.acquired = False
    return _outcome(
        terminal,
        terminal,
        start=publication.start,
        operation_id=publication.saved.operation_id,
        kind=lineage.origin.kind,
        direction=publication.saved.direction,
        review_generation=publication.saved.review.proposal.generation,
        generation=state.generation,
        phase="terminal",
        publication="complete",
        history="terminal",
        planned=state.planned,
        published=state.published,
        changed=bool(paths.changed),
        checkpoint=state.prepared_commit,
        intent=state.recovery_commit,
        result=state.result_commit,
        receipt=state.receipt_commit,
        recovery=False,
        message="Reviewed recovery result and terminal receipt retained.",
    )


def _publish_staged_recovery(
    publication, lineage, paths, state, executor, cancel_requested
):
    root = publication.root
    git = _Git(root)
    with _retained_source(root, git, lineage.source_manifest.source) as source:  # noqa: SIM117
        with _proposed_directory(root.parent) as proposed_root:
            stage = _stage_recovery(publication, paths, proposed_root)
            if isinstance(stage, VaultApplyResult):
                return stage
            if not _recheck_held_recovery_marker(publication, state):
                return _refuse_known_recovery(
                    publication.observed,
                    "operation_marker_invalid",
                    start=publication.start,
                )
            stopped = _retain_recovery_preparation(
                publication, lineage, stage, state, source, cancel_requested
            )
            if stopped is not None:
                return stopped
            manifest = _rediscover_recovery_preparation(publication)
            journal = _record_recovery_intent(
                publication, lineage, paths, stage, state, git, manifest
            )
            stopped = _publish_recovery_paths(
                publication,
                lineage,
                paths,
                stage,
                state,
                journal,
                executor,
                cancel_requested,
            )
            if stopped is not None:
                return stopped
            terminal = _retain_recovery_result(
                publication, lineage, paths, state, source, journal
            )
    return _completed_recovery(publication, lineage, paths, state, terminal)


def _execute_recovery_cleanup(root, saved, *, cancel, start, owners):
    from .collection_publication import LOCAL_LOCATOR_PENDING, recover_local_publication
    from .collection_undo_publication import (
        SCOPED_UNDO_PENDING,
        recover_scoped_undo_metadata,
    )

    if saved.code == SCOPED_UNDO_PENDING and saved.unpublished_checkpoint is not None:
        return recover_scoped_undo_metadata(root, saved, cancel=cancel)
    if saved.code == LOCAL_LOCATOR_PENDING and saved.unpublished_checkpoint is not None:
        return recover_local_publication(root, saved, cancel=cancel)
    if saved.unpublished_checkpoint is not None:
        from .unpublished_collection import restore_unpublished_collection

        return restore_unpublished_collection(root, saved, cancel=cancel)
    if saved.result_locator_checkpoint is not None:
        from .collection_result_locator import reseal_scoped_result

        return reseal_scoped_result(root, saved, cancel=cancel)
    return _cleanup_verified_terminal(root, saved, start=start, _owners=owners)


def _execute_recovery(
    vault,
    preparation,
    *,
    cancel=None,
    progress=None,
    executor=None,
    _owner=None,
    _owners=None,
):
    """Retain selected direction before ordinary per-file publication."""
    from brz2obsidian.application.vault_progress_contracts import report_progress

    report_progress(progress, "review_validation")
    start = time.monotonic()
    try:
        saved = VaultRecoveryPreparation.model_validate(preparation)
    except OSError, ValueError, TypeError, UnicodeError:
        return _outcome("refused", "invalid_recovery_preparation", start=start)
    root = Path(vault).absolute()
    if saved.status == "cleanup":
        return _execute_recovery_cleanup(
            root, saved, cancel=cancel, start=start, owners=_owners
        )
    if saved.status != "offered" or saved.direction is None or saved.review is None:
        return _outcome("refused", "recovery_review_required", start=start)
    publication = _select_recovery_publication(
        vault,
        root,
        saved,
        start=start,
        progress=progress,
        _owner=_owner,
        _owners=_owners,
    )
    if isinstance(publication, VaultApplyResult):
        return publication
    state = _RecoveryProgress()
    cancel_requested = cancel if cancel is not None else lambda: False
    executor = executor if executor is not None else _NativeExecutor()
    try:
        before_lease = _adopt_recovery(publication, state)
        if isinstance(before_lease, VaultApplyResult):
            return before_lease
        lineage = _observe_recovery_lineage(publication, before_lease)
        if isinstance(lineage, VaultApplyResult):
            return lineage
        paths = _plan_recovery_paths(publication, lineage, state)
        if isinstance(paths, VaultApplyResult):
            return paths
        return _publish_staged_recovery(
            publication, lineage, paths, state, executor, cancel_requested
        )
    except OSError, ValueError, TypeError:
        return _report_recovery_failure(publication, state)
    finally:
        _release_recovery_lease(publication, state)


def execute_recovery(
    vault, preparation, *, cancel=None, progress=None, executor=None, _owner=None
):
    """Apply a selected recovery direction through the shared Operations seam."""
    try:
        with ExitStack() as owners:
            return _execute_recovery(
                vault,
                preparation,
                cancel=cancel,
                progress=progress,
                executor=executor,
                _owner=_owner,
                _owners=owners if _owner is not None else None,
            )
    except _OwnedRecoveryCleanupFailure as failure:
        return failure.result
