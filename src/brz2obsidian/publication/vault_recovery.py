"""Validated interrupted-operation discovery and reviewed recovery roles."""

import hashlib
import io
import os
import shutil
import stat
import sys
import tempfile
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path

from brz2obsidian.application.vault_recovery_contracts import VaultRecoveryPreparation
from brz2obsidian.application.vault_update_contracts import (
    VaultOperationLock,
    VaultOperationReceipt,
    VaultOperationStop,
    VaultPathMetadata,
    VaultRecoveryIntent,
)
from brz2obsidian.contracts import (
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
    SupportedFormatBaseline,
)
from brz2obsidian.core import (
    prepare_review,
    refresh_review,
    resolve_review,
    review_owned_targets,
    select_review_effects,
)
from brz2obsidian.obsidian import interpret_link_target, interpret_links
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
    _outcome,
    _park,
    _prepare_parents,
    _proposed_directory,
    _release,
    _review_subjects,
    _same_file,
    owns_operation,
)
from brz2obsidian.publication.vault_history import (
    _Git,
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


def _review_observation(root, observed, *, direction, authority, next_generation=None):
    """Bind original S1 facts to independently observed current vault bytes."""
    git = _Git(root)
    original, intent, origin_commit, retained = authority
    if intent.operation_id != observed.operation_id:
        raise OSError("Validated operation authority changed")
    selected = select_review_effects(original)
    if selected.status != "selected":
        raise OSError("Original prepared review is not selected")
    selected_files = {row.path: row.content for row in selected.files}
    produced = {row.path: row for row in intent.proposed}
    admission = _inspect_vault_for_recovery(
        root, retained, subjects=_review_subjects(original, selected)
    )
    if (
        not admission.inventory_complete
        or admission.repository.kind != "root"
        or any(finding.policy != "operation" for finding in admission.findings)
        or admission.preflight.state_status != "supported"
    ):
        raise OSError("Current recovery policy or inventory is unavailable")
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
    selected_removal = any(
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
            paths.update(
                row.path for row in admission.inventory if row.path.endswith(".md")
            )
    needed = sum(inventory[path].size for path in paths if path in inventory)
    if available_memory() < 9 * needed + 64 * 1024 * 1024:
        raise OSError("Insufficient memory to review exact current recovery bytes")
    current = {}
    for path in sorted(paths):
        row = inventory.get(path)
        if row is None:
            if os.path.lexists(root / path):
                raise OSError("Current recovery path is outside the inventory")
            current[path] = CurrentContent(existence="absent", path=path, content=None)
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
    original_facts = original.facts
    context = original_facts.link_context
    identity_inventory = list(original_facts.identity_inventory)
    if context is not None:
        target_by_id = {target.target_id: target for target in context.current_targets}
        state_by_id = {state.target_id: state for state in context.current_target_facts}
        if (
            len(target_by_id) != len(context.current_targets)
            or len(state_by_id) != len(context.current_target_facts)
            or set(target_by_id) != set(state_by_id)
        ):
            raise OSError("Current recovery target lookup is incomplete")
        target_facts = []
        for target in context.current_targets:
            old = state_by_id[target.target_id]
            observed_target = current.get(target.canonical_path)
            if observed_target is None or (
                observed_target.content == old.content
                and observed_target.existence
                == ("absent" if old.existence == "missing" else old.existence)
            ):
                target_facts.append(old)
            else:
                target_facts.append(
                    interpret_link_target(
                        observed_target.content,
                        target_id=target.target_id,
                        existence="missing"
                        if observed_target.existence == "absent"
                        else "present",
                        memberships=(),
                    )
                )
        documents = []
        for document in context.current_documents:
            observed_document = current[document.source_path]
            if observed_document.content is None:
                continue
            documents.append(
                document
                if observed_document.content == document.content
                else interpret_links(
                    observed_document.content,
                    document_id=document.document_id,
                    source_path=document.source_path,
                    path_mode=document.path_mode,
                    targets=context.current_targets,
                    target_facts=tuple(target_facts),
                    inventory="complete",
                )
            )
        current_targets = list(context.current_targets)
        incoming_targets = list(context.incoming_targets)
        incoming_target_facts = list(context.incoming_target_facts)
        incoming_documents = list(context.incoming_documents)
        known_document_paths = {
            document.source_path for document in context.current_documents
        }
        known_identity_paths = {item.current.path for item in identity_inventory}
        operation_owned_notes = {
            target.canonical_path
            for target in context.incoming_targets
            if target.kind == "note"
            and target.canonical_path in intent.affected_paths
            and target.canonical_path in selected_files
        }
        for path in sorted(
            row.path
            for row in admission.inventory
            if (selected_removal or row.path in operation_owned_notes)
            and row.path.endswith(".md")
            and row.path not in known_document_paths
        ):
            observed_document = current[path]
            if observed_document.content is None:
                raise OSError("New current recovery document is unavailable")
            retained_targets = tuple(
                target
                for target in context.incoming_targets
                if target.canonical_path == path and target.kind == "note"
            )
            if path in operation_owned_notes and retained_targets:
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
                row = produced.get(path)
                content = selected_files[path]
                if (
                    len(retained_document) != 1
                    or len(original_target) != 1
                    or len(owner) != 1
                    or retained_target.identity is None
                    or row is None
                    or row.size != len(content.data)
                    or row.sha256 != hashlib.sha256(content.data).hexdigest()
                    or (path in known_identity_paths and owner[0].current.path != path)
                ):
                    raise OSError("Operation-owned recovery note lacks retained proof")
                index = next(
                    i
                    for i, target in enumerate(current_targets)
                    if target.target_id == retained_target.target_id
                )
                current_targets[index] = retained_target
                target_facts[index] = interpret_link_target(
                    observed_document.content,
                    target_id=retained_target.target_id,
                    existence="present",
                    memberships=(),
                )
                parsed = interpret_links(
                    observed_document.content,
                    document_id=retained_document[0].document_id,
                    source_path=path,
                    path_mode=retained_document[0].path_mode,
                    targets=tuple(current_targets),
                    target_facts=tuple(target_facts),
                    inventory="complete",
                )
                if parsed.status != "supported":
                    raise OSError("Operation-owned recovery note interpretation failed")
                documents.append(parsed)
                if owner[0].current.path == path:
                    # A created note already has the sole retained item at
                    # this physical path. Its ordinary inventory row below
                    # receives the observed bytes; no second identity exists.
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
                    # Restore reviews both physical endpoints under the
                    # operation-bound reversal proof.
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
                known_identity_paths.add(path)
                continue
            # A new authored note has no imported item identity. Its safe
            # physical path is still a real lookup entry and document owner.
            if path in known_identity_paths or any(
                target.canonical_path == path
                for target in current_targets + incoming_targets
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
            )
            parsed = interpret_links(
                observed_document.content,
                document_id=target_id,
                source_path=path,
                path_mode="vault",
                targets=tuple(current_targets) + (reference,),
                target_facts=tuple(target_facts) + (state,),
                inventory="complete",
            )
            # A newly authored note's link mode has no retained S1 proof.
            # Plain notes can join the complete inventory; link-bearing or
            # opaque notes need an explicit qualified observation first.
            if parsed.status != "supported" or parsed.occurrences:
                raise OSError("New current recovery links need qualified review")
            current_targets.append(reference)
            incoming_targets.append(reference)
            target_facts.append(state)
            incoming_target_facts.append(state)
            documents.append(parsed)
            incoming_documents.append(parsed)
            identity_inventory.append(
                IdentityInventoryItem(
                    entry_id=target_id,
                    facet=None,
                    identity_state="missing",
                    identity=None,
                    raw_identity=None,
                    title=Path(path).stem,
                    current=observed_document,
                    target=target,
                )
            )
            known_identity_paths.add(path)
        context = context.model_copy(
            update={
                "current_targets": tuple(current_targets),
                "incoming_targets": tuple(incoming_targets),
                "current_target_facts": tuple(target_facts),
                "incoming_target_facts": tuple(incoming_target_facts),
                "current_documents": tuple(documents),
                "incoming_documents": tuple(incoming_documents),
            }
        )
    original_before = {row.path: row for row in intent.before}
    original_proposed = {row.path: row for row in intent.proposed}

    def observed_subject_current(subject):
        observed = current[subject.current.path]
        if (
            direction != "finish"
            or observed.existence != "absent"
            or subject.current.path != subject.path
        ):
            return observed
        owners = tuple(
            item
            for item in original_facts.identity_inventory
            if item.identity_state == "valid"
            and item.identity is not None
            and (
                item.identity.module_id,
                item.identity.collection_id,
            )
            == (
                original_facts.incoming_identity.module_id,
                original_facts.incoming_identity.collection_id,
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
            and old.size == len(owners[0].current.content.data)
            and old.sha256 == hashlib.sha256(owners[0].current.content.data).hexdigest()
            and new is not None
            and selected_new is not None
            and new.size == len(selected_new.data)
            and new.sha256 == hashlib.sha256(selected_new.data).hexdigest()
            and old_current is not None
            and old_current.existence == "present"
        ):
            # The approved rename has not made its first physical move. The
            # real retained item still lives at its independently observed
            # old path; the new path is the selected output, currently absent.
            return old_current
        return observed

    facts = original_facts.model_copy(
        update={
            "generation": next_generation or original.proposal.generation + 1,
            "subjects": tuple(
                subject.model_copy(
                    update={"current": observed_subject_current(subject)}
                )
                for subject in original_facts.subjects
            ),
            "identity_inventory": tuple(
                item.model_copy(update={"current": current[item.current.path]})
                for item in identity_inventory
            ),
            "link_context": context,
        }
    )
    # The checkpoint locator advances during the already-authorized operation.
    # Only that validated movement is neutralized: changed policy, consents,
    # current bytes, or a broken graph still reach the ordinary refresh rules.
    original_prepared = retained.owned[intent.prepared_commit][0]
    same_policy = admission.policy_fingerprint == original_prepared.policy_fingerprint
    preflight = admission.preflight.model_copy(
        update={
            "operation_status": "idle",
            "state_fingerprint": original.preflight.state_fingerprint
            if same_policy
            else admission.preflight.state_fingerprint,
        }
    )
    return original, intent, origin_commit, git, facts, preflight, current, retained


def _finish_review(root, observed, *, previous=None, authority=None):
    original, _, _, _, facts, preflight, _, _ = _review_observation(
        root,
        observed,
        direction="finish",
        authority=authority,
        next_generation=(previous.proposal.generation + 1 if previous else None),
    )
    refreshed = refresh_review(previous or original, facts, preflight=preflight)
    if refreshed.status != "accepted":
        raise OSError("Current recovery review could not be refreshed")
    return refreshed.plan


def _owned_content(git, row):
    if row is None:
        return None
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


def _restore_link_context(original, facts, before, affected, git):
    """Interpret the exact original target inventory with current link owners."""
    context = facts.link_context
    if context is None:
        return None
    original_context = original.facts.link_context
    current_states = {state.target_id: state for state in context.current_target_facts}
    if len(current_states) != len(context.current_target_facts):
        raise OSError("Current recovery lookup is ambiguous")
    target_states = []
    for target in context.current_targets:
        path = target.canonical_path
        if path in affected:
            content = _owned_content(git, before.get(path))
            target_states.append(
                interpret_link_target(
                    content,
                    target_id=target.target_id,
                    existence="missing" if content is None else "present",
                    memberships=(),
                )
            )
        else:
            target_states.append(current_states[target.target_id])
    candidates = {doc.source_path: doc for doc in context.current_documents}
    if original_context is not None:
        for doc in original_context.current_documents:
            candidates.setdefault(doc.source_path, doc)
    documents = []
    for path, document in sorted(candidates.items()):
        content = (
            _owned_content(git, before.get(path))
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
            )
        )
    return context.model_copy(
        update={
            "incoming_targets": context.current_targets,
            "incoming_target_facts": tuple(target_states),
            "incoming_documents": tuple(documents),
        }
    )


def _restore_review(root, observed, *, previous=None, authority=None):
    original, intent, origin_commit, git, facts, preflight, current, retained = (
        _review_observation(
            root,
            observed,
            direction="restore",
            authority=authority,
            next_generation=(previous.proposal.generation + 1 if previous else None),
        )
    )
    before = {row.path: row for row in intent.before}
    produced = {row.path: row for row in intent.proposed}
    subjects = []
    baseline_outputs = []
    output_references = {}
    approved = {approval.change_id: approval for approval in original.approvals}
    for subject in facts.subjects:
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
        if approval is None:
            if subject.path not in intent.affected_paths:
                # An automatic, unchanged producer has no decision to reverse.
                # Affected outputs still require retained selected ownership.
                continue
            raise OSError("Recovery subject lacks original selected approval")
        owned = review_owned_targets(original, approval.change_id, approval.decision_id)
        rows = []
        for reference in owned:
            path = reference.canonical_path
            if path not in intent.affected_paths:
                continue
            old = _owned_content(git, before.get(path))
            new = _owned_content(git, produced.get(path))
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
        if subject.path not in intent.affected_paths and not rows:
            continue
        old = _owned_content(git, before.get(subject.path))
        if old is None and not rows:
            continue
        proof = (
            OperationReversalTarget(
                schema_id="brz2obsidian.operation-reversal-target",
                schema_version=1,
                operation_id=intent.operation_id,
                operation_kind=intent.kind,
                direction="restore",
                operation_generation=intent.generation,
                history_fingerprint=_operation_history_fingerprint(
                    origin_commit, intent
                ),
                origin_change_id=approval.change_id,
                origin_decision_id=approval.decision_id,
                owned_targets=owned,
                outputs=tuple(rows),
            )
            if rows
            else None
        )
        generated = subject.incoming or (
            subject.baseline.content if subject.baseline.status == "known" else None
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
                    if subject.path in intent.affected_paths
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
    covered = {
        path
        for subject in subjects
        for path in ((subject.path,) if subject.path in intent.affected_paths else ())
    } | set(output_references)
    source_prepared = retained.owned[intent.prepared_commit][0]
    source_lineage = retained.owned[source_prepared.previous][0]
    generated_files = {row.path: row for row in source_lineage.source}
    original_files = {
        row.path: row.content for row in select_review_effects(original).files
    }
    original_documents = (
        set()
        if original.facts.link_context is None
        else {
            document.source_path
            for document in original.facts.link_context.current_documents
        }
    )
    for path in sorted(set(intent.affected_paths) - covered):
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
                original.facts.incoming_identity.module_id,
                original.facts.incoming_identity.collection_id,
            )
        )
        if (
            len(owners) != 1
            or path not in original_documents
            or path not in original_files
            or before.get(path) is None
            or produced.get(path) is None
            or current[path].content is None
            or facts.link_context is None
            or not any(
                document.source_path == path and document.status == "supported"
                for document in facts.link_context.current_documents
            )
        ):
            raise OSError("Associated recovery document lacks retained authority")
        owner = owners[0]
        generated = _owned_content(git, generated_files.get(path))
        target = _owned_content(git, before[path])
        if generated is None or target is None:
            raise OSError("Associated recovery document source is unavailable")
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
            )
        )
        baseline_outputs.append(
            FormatBaselineOutput(
                item_id=owner.identity.item_id,
                facet=owner.facet,
                content=generated,
            )
        )
    if not subjects:
        raise OSError("Retained operation has no reviewed recovery subjects")
    identity_inventory = list(facts.identity_inventory)
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
                interpret_link_target(
                    current[path].content,
                    target_id=reference.target_id,
                    existence="missing" if current[path].content is None else "present",
                    memberships=(),
                )
            )
        if reference.target_id not in {target.target_id for target in incoming_refs}:
            target = _owned_content(git, before.get(path))
            incoming_refs.append(reference)
            incoming_states.append(
                interpret_link_target(
                    target,
                    target_id=reference.target_id,
                    existence="missing" if target is None else "present",
                    memberships=(),
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
    facts = facts.model_copy(
        update={
            "identity_inventory": tuple(identity_inventory),
            "link_context": context,
        }
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
            "identity_inventory": tuple(identity_inventory),
            "format_operation": format_operation,
            "link_context": _restore_link_context(
                original, facts, before, set(intent.affected_paths), git
            ),
            "source_version_memory": (),
            "association_decisions": (),
            "rename_decisions": (),
            "preservation_decisions": (),
        }
    )
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


def _prepare_recovery_observed(
    root, observed, authority, *, direction=None, previous=None
):
    """Use one fully validated operation walk and a fresh current observation."""
    if direction not in (None, "finish", "restore"):
        return _recovery_preparation("refused", "unsupported_recovery_direction")
    if authority is not None and authority.graph.receipt is not None:
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
        if not _marker_valid(root, observed.operation_id):
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
    origin_commit, origin = authority.graph.authorities[-1]
    loaded = authority.owned[origin.prepared_commit][1]
    if loaded is None:
        return _recovery_preparation("unavailable", "original_review_unavailable")
    original = loaded.saved.plan
    selected_authority = (original, origin, origin_commit, authority)
    try:
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


def prepare_recovery(vault, *, direction=None):
    """Offer a reviewed direction after one validated operation observation."""
    root = Path(vault).absolute()
    observed, authority = _inspect_update_observation(root)
    return _prepare_recovery_observed(root, observed, authority, direction=direction)


def _refused_recovery(code):
    return _recovery_preparation("refused", code)


def refresh_recovery(vault, preparation):
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
        observed, authority = _inspect_update_observation(root)
        current = _prepare_recovery_observed(
            root,
            observed,
            authority,
            direction=previous.direction,
            previous=previous.review,
        )
        if (
            current.status != "offered"
            or current.operation_id != previous.operation_id
            or current.intent_commit != previous.intent_commit
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
        and current_facts == saved.review.facts
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


def _cleanup_verified_terminal(root, saved, *, start):
    observed, authority = _inspect_update_observation(root)
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
    try:
        _adopt(root, saved.operation_id)
        held, held_authority = _inspect_update_observation(root)
        if (
            held_authority is None
            or held_authority.graph.commit != authority.graph.commit
            or held.code != "terminal_cleanup_required"
        ):
            _park(root, saved.operation_id)
            return _outcome("refused", "terminal_cleanup_changed", start=start)
        _release(root, saved.operation_id)
        final = _inspect_update_observation(root)[0]
        if final.status not in ("applied", "no_content_change", "undone", "restored"):
            raise OSError("Verified terminal status was not rediscovered")
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


def _execute_recovery(vault, preparation, *, cancel=None, executor=None):
    """Retain selected direction before ordinary per-file publication."""
    start = time.monotonic()
    try:
        saved = VaultRecoveryPreparation.model_validate(preparation)
    except OSError, ValueError, TypeError, UnicodeError:
        return _outcome("refused", "invalid_recovery_preparation", start=start)
    root = Path(vault).absolute()
    if saved.status == "cleanup":
        return _cleanup_verified_terminal(root, saved, start=start)
    if saved.status != "offered" or saved.direction is None or saved.review is None:
        return _outcome("refused", "recovery_review_required", start=start)
    selected = select_review_effects(saved.review)
    if selected.status != "selected":
        return _outcome("refused", selected.code, start=start)
    if not supported_durable_volume(root):
        return _outcome("refused", "unsupported_durable_volume", start=start)
    observed, authority = _inspect_update_observation(root)
    fresh = _prepare_recovery_observed(
        root, observed, authority, direction=saved.direction
    )
    if fresh.status != "offered" or not _same_recovery_review(fresh, saved):
        if authority is not None and observed.operation_id == saved.operation_id:
            return _refuse_known_recovery(
                observed, "recovery_review_stale", start=start
            )
        return _outcome("refused", "recovery_review_stale", start=start)
    try:
        subjects = _review_subjects(saved.review, selected)
    except OSError, ValueError, TypeError:
        return _refuse_known_recovery(observed, "invalid_recovery_scope", start=start)
    operation_id = saved.operation_id
    acquired = False
    phase = "admission"
    prepared_commit = recovery_commit = result_commit = receipt_commit = None
    published = planned = 0
    failure_code = "recovery_unavailable"
    generation = None
    cancel_requested = cancel if cancel is not None else lambda: False
    executor = executor if executor is not None else _NativeExecutor()
    current_status = observed
    try:
        _adopt(root, operation_id)
        acquired = True
        if not owns_operation(root, operation_id):
            raise OSError("Recovery operation lease is unavailable")
        current_status, current_authority = _inspect_update_observation(root)
        if (
            current_authority is None
            or current_authority.graph.commit != authority.graph.commit
            or current_status.operation_id != operation_id
            or current_status.intent_commit != saved.intent_commit
            or (
                isinstance(current_authority.graph.intent, VaultRecoveryIntent)
                and current_status.direction != saved.direction
            )
        ):
            return _refuse_known_recovery(
                current_status, "recovery_authority_changed", start=start
            )
        history = inspect_history(
            root, subjects=subjects, active_operation=operation_id
        )
        if history.status != "intact" or history.admission.status != "supported":
            return _refuse_known_recovery(
                current_status, "recovery_admission_required", start=start
            )
        association = history.checkpoint.locator.association
        origin_commit, origin = current_authority.graph.authorities[-1]
        original_prepared = current_authority.owned[origin.prepared_commit][0]
        source_manifest = (
            original_prepared
            if saved.direction == "finish"
            else current_authority.owned[original_prepared.previous][0]
        )
        if (
            current_status.operation_id != operation_id
            or current_status.intent_commit != saved.intent_commit
            or (
                isinstance(current_authority.graph.intent, VaultRecoveryIntent)
                and current_status.direction != saved.direction
            )
            or association.association_id != origin.association_id
            or saved.review.facts.incoming_identity != source_manifest.identity
            or _operation_history_fingerprint(origin_commit, origin)
            != _operation_history_fingerprint(
                current_authority.graph.origin_intent_commit, origin
            )
        ):
            return _refuse_known_recovery(
                current_status, "recovery_source_lineage_changed", start=start
            )
        accepted_tracking = {
            subject_id
            for requirement in history.admission.preflight.consents
            if requirement.kind == "tracking"
            and any(
                decision.consent_id == requirement.consent_id
                and decision.kind == requirement.kind
                and decision.choice == "accept"
                for decision in saved.review.consents
            )
            for subject_id in requirement.subjects
        }
        included_paths = {
            subject.path
            for subject in subjects
            if subject.subject_id in accepted_tracking
        }
        before = {
            row.path: row
            for row in history.admission.inventory
            if not row.excluded or row.path in included_paths
        }
        selected_files = {row.path: row.content.data for row in selected.files}
        removals = set(selected.remove_paths)
        if any(not _safe_relative(path) for path in (*selected_files, *removals)):
            return _refuse_known_recovery(
                current_status, "unsafe_recovery_path", start=start
            )
        if any(path not in before for path in removals):
            return _refuse_known_recovery(
                current_status, "recovery_removal_missing", start=start
            )
        changed = {
            path
            for path, data in selected_files.items()
            if path not in before
            or before[path].size != len(data)
            or before[path].sha256 != hashlib.sha256(data).hexdigest()
        } | removals
        if not changed.issubset(origin.affected_paths):
            return _refuse_known_recovery(
                current_status, "recovery_scope_changed", start=start
            )
        planned = len(changed)
        stage_need = (
            sum(row.size for path, row in before.items() if path not in removals)
            + sum(len(data) for data in selected_files.values())
            + sum(row.size for row in source_manifest.source)
            + 128 * 1024 * 1024
            + 4096 * (len(before) + len(selected_files) + len(source_manifest.source))
        )
        if shutil.disk_usage(root.parent).free < stage_need:
            return _refuse_known_recovery(
                current_status, "insufficient_recovery_stage_resources", start=start
            )
        git = _Git(root)
        with _retained_source(root, git, source_manifest.source) as source:  # noqa: SIM117
            with _proposed_directory(root.parent) as proposed_root:
                if proposed_root.stat().st_dev != root.stat().st_dev:
                    return _refuse_known_recovery(
                        current_status, "same_volume_stage_required", start=start
                    )
                stage_parent_security(root, proposed_root, Path("."))
                before_metadata = {}
                result_metadata = {}
                for path, row in before.items():
                    if path in removals:
                        continue
                    target = proposed_root / path
                    stage_parent_security(root, proposed_root, Path(path).parent)
                    if not _same_file(root, row):
                        return _refuse_known_recovery(
                            current_status, "current_bytes_changed", start=start
                        )
                    if path in changed:
                        before_metadata[path] = retained_metadata(root / path)
                        copy_stage(root / path, target)
                    else:
                        shutil.copy2(root / path, target)
                for path, data in selected_files.items():
                    target = proposed_root / path
                    stage_parent_security(root, proposed_root, Path(path).parent)
                    with target.open("wb") as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    if path in before:
                        shutil.copymode(root / path, target)
                    if path in changed:
                        if path in before:
                            retained_metadata(root / path, copy_to=target)
                        result_metadata[path] = retained_metadata(target)
                        _flush_stage(target)
                for path in removals:
                    before_metadata[path] = retained_metadata(root / path)
                prepared_parents = _prepare_parents(
                    root,
                    proposed_root,
                    (path for path in changed if path in selected_files),
                )
                parent_metadata = {
                    path: retained_directory_metadata(stage)
                    for path, stage in prepared_parents.items()
                }
                phase = "prepared"
                prepared = capture_checkpoint(
                    root,
                    source,
                    vault_id=association.vault_id,
                    import_id=association.import_id,
                    identity=source_manifest.identity,
                    admission=history.admission,
                    subjects=subjects,
                    review=saved.review,
                    boundary="prepared",
                    proposed=proposed_root,
                    active_operation=operation_id,
                    recovery_direction=saved.direction,
                )
                reused_preparation = (
                    prepared.status == "unchanged"
                    and prepared.code == "already_retained"
                    and prepared.history_retained
                    and prepared.commit == current_authority.unpublished_prepared
                )
                if prepared.status != "captured" and not reused_preparation:
                    return _stopped_before_recovery_intent(
                        current_status,
                        "refused" if prepared.status == "refused" else "failed",
                        "recovery_prepare_" + prepared.code,
                        start=start,
                        direction=saved.direction,
                        review_generation=saved.review.proposal.generation,
                        prepared=prepared.commit if prepared.history_retained else None,
                    )
                prepared_commit = prepared.commit
                if cancel_requested():
                    return _stopped_before_recovery_intent(
                        current_status,
                        "cancelled",
                        "cancelled_before_recovery_intent",
                        start=start,
                        direction=saved.direction,
                        review_generation=saved.review.proposal.generation,
                        prepared=prepared_commit,
                    )
                tip = inspect_history(
                    root, subjects=subjects, active_operation=operation_id
                )
                manifest = tip.checkpoint.manifest
                if tip.status != "intact" or manifest.boundary != "prepared":
                    raise OSError("Recovery preparation could not be rediscovered")
                generation = manifest.generation
                intent = VaultRecoveryIntent(
                    schema_id="brz2obsidian.vault-recovery-intent",
                    schema_version=1,
                    operation_id=operation_id,
                    kind=origin.kind,
                    generation=generation,
                    direction=saved.direction,
                    association_id=manifest.association_id,
                    prepared_commit=prepared_commit,
                    before=manifest.preimage,
                    proposed=manifest.proposed,
                    affected_paths=tuple(sorted(changed)),
                    protected_paths=tuple(sorted(set(before) - changed)),
                    before_metadata=tuple(
                        VaultPathMetadata(
                            path=path,
                            mode=value[0],
                            attributes=value[1],
                            security=value[2],
                        )
                        for path, value in sorted(before_metadata.items())
                    ),
                    result_metadata=tuple(
                        VaultPathMetadata(
                            path=path,
                            mode=value[0],
                            attributes=value[1],
                            security=value[2],
                        )
                        for path, value in sorted(result_metadata.items())
                    ),
                    created_directories=tuple(
                        VaultPathMetadata(
                            path=path.as_posix(),
                            mode=value[0],
                            attributes=value[1],
                            security=value[2],
                        )
                        for path, value in sorted(
                            parent_metadata.items(), key=lambda item: item[0].as_posix()
                        )
                    ),
                    origin_intent_commit=origin_commit,
                    previous_operation_commit=current_authority.graph.commit,
                    review_generation=saved.review.proposal.generation,
                )
                op_ref = (
                    "refs/brz2obsidian/imports/"
                    + manifest.association_id
                    + "/operations/"
                    + operation_id
                )
                phase = "intent"
                recovery_commit = _journal(
                    git,
                    "recovery.json",
                    intent,
                    parents=(current_authority.graph.commit, prepared_commit),
                    previous=current_authority.graph.commit,
                    ref=op_ref,
                )
                phase = "publication"
                proposed = {row.path: row for row in manifest.proposed}
                prior = {row.path: row for row in manifest.preimage}
                expected_metadata = {row.path: row for row in intent.result_metadata}
                for path in sorted(changed):
                    if cancel_requested():
                        stopped = VaultOperationStop(
                            schema_id="brz2obsidian.vault-operation-stop",
                            schema_version=1,
                            operation_id=operation_id,
                            kind=origin.kind,
                            generation=generation,
                            direction=saved.direction,
                            status="cancelled",
                            intent_commit=recovery_commit,
                            acknowledged_after_files=published,
                        )
                        stop_commit = _journal(
                            git,
                            "stop.json",
                            stopped,
                            parents=(recovery_commit,),
                            previous=recovery_commit,
                            ref=op_ref,
                        )
                        return _outcome(
                            "cancelled",
                            "cancelled_after_recovery_intent",
                            start=start,
                            operation_id=operation_id,
                            kind=origin.kind,
                            direction=saved.direction,
                            review_generation=saved.review.proposal.generation,
                            generation=generation,
                            phase=phase,
                            publication="partial" if published else "not_published",
                            history="intent",
                            planned=planned,
                            published=published,
                            changed=bool(published),
                            checkpoint=prepared_commit,
                            intent=recovery_commit,
                            stop=stop_commit,
                            recovery=True,
                        )
                    target = root / path
                    old, new = prior.get(path), proposed.get(path)
                    if old is None:
                        if os.path.lexists(target):
                            raise OSError("Recovery creation path became occupied")
                    elif not _same_file(root, old):
                        raise OSError(
                            "Recovery current bytes changed before transition"
                        )
                    if new is None:
                        destination = proposed_root / (
                            "removed-" + hashlib.sha256(path.encode()).hexdigest()
                        )
                        executor.remove(target, destination)
                    else:
                        stage = proposed_root / path
                        if not _same_file(proposed_root, new):
                            raise OSError("Prepared recovery bytes changed")
                        _ensure_parents(
                            root, target, prepared_parents, parent_metadata, executor
                        )
                        executor.move(stage, target, replace=old is not None)
                        if not _same_file(root, new) or not _metadata_matches(
                            root, path, expected_metadata[path]
                        ):
                            raise OSError("Published recovery result changed")
                    published += 1
                if any(not _same_file(root, row) for row in manifest.proposed):
                    raise OSError("Complete recovery inventory changed")
                if any(
                    os.path.lexists(root / path) for path in set(prior) - set(proposed)
                ):
                    raise OSError("Removed recovery path remains visible")
                phase = "result"
                current = inspect_history(
                    root, subjects=subjects, active_operation=operation_id
                )
                result_checkpoint = capture_checkpoint(
                    root,
                    source,
                    vault_id=association.vault_id,
                    import_id=association.import_id,
                    identity=source_manifest.identity,
                    admission=current.admission,
                    subjects=subjects,
                    boundary="result",
                    expected_prepared=prepared_commit,
                    active_operation=operation_id,
                    operation_intent_commit=recovery_commit,
                )
                if result_checkpoint.status != "captured":
                    failure_code = "result_" + result_checkpoint.code
                    raise OSError("Recovery result checkpoint was not retained")
                result_commit = result_checkpoint.commit
                terminal = _recovery_result_status(
                    origin.kind, saved.direction, bool(origin.affected_paths)
                )
                receipt = VaultOperationReceipt(
                    schema_id="brz2obsidian.vault-operation-receipt",
                    schema_version=1,
                    operation_id=operation_id,
                    kind=origin.kind,
                    generation=generation,
                    status=terminal,
                    direction=saved.direction,
                    intent_commit=recovery_commit,
                    prepared_commit=prepared_commit,
                    result_commit=result_commit,
                    published_paths=tuple(sorted(changed)),
                )
                phase = "terminal"
                receipt_commit = _journal(
                    git,
                    "receipt.json",
                    receipt,
                    parents=(recovery_commit, result_commit),
                    previous=recovery_commit,
                    ref=op_ref,
                )
        _release(root, operation_id)
        acquired = False
        return _outcome(
            terminal,
            terminal,
            start=start,
            operation_id=operation_id,
            kind=origin.kind,
            direction=saved.direction,
            review_generation=saved.review.proposal.generation,
            generation=generation,
            phase="terminal",
            publication="complete",
            history="terminal",
            planned=planned,
            published=published,
            changed=bool(changed),
            checkpoint=prepared_commit,
            intent=recovery_commit,
            result=result_commit,
            receipt=receipt_commit,
            recovery=False,
            message="Reviewed recovery result and terminal receipt retained.",
        )
    except OSError, ValueError, TypeError:
        failure = (
            _inspect_update_observation(root)[0]
            if phase in ("intent", "publication", "result", "terminal")
            else None
        )
        if (
            failure is not None
            and failure.operation_id == operation_id
            and failure.intent_commit is not None
        ):
            return _outcome(
                "content_complete"
                if failure.status
                in ("applied", "undone", "restored", "no_content_change")
                else failure.status,
                failure_code + "_" + failure.code,
                start=start,
                operation_id=operation_id,
                kind=failure.kind,
                direction=failure.direction,
                review_generation=failure.review_generation,
                generation=failure.generation,
                phase=phase,
                publication=failure.publication,
                history=failure.history,
                planned=planned,
                published=failure.published_files,
                changed=failure.authored_files_changed,
                checkpoint=prepared_commit,
                intent=failure.intent_commit,
                result=failure.result_commit or result_commit,
                receipt=failure.receipt_commit,
                stop=failure.stop_commit,
                recovery=True,
            )
        return _outcome(
            "content_complete" if result_commit is not None else "unknown",
            failure_code,
            start=start,
            operation_id=operation_id,
            kind=saved.kind,
            direction=saved.direction,
            review_generation=saved.review.proposal.generation,
            generation=generation,
            phase=phase,
            publication="complete" if result_commit is not None else "unknown",
            history="result"
            if result_commit is not None
            else "unknown"
            if phase == "intent"
            else "intent"
            if recovery_commit is not None
            else "prepared"
            if prepared_commit is not None
            else "none",
            planned=planned,
            published=published,
            changed=True if result_commit is not None and planned else None,
            checkpoint=prepared_commit,
            intent=recovery_commit,
            result=result_commit,
            receipt=receipt_commit,
            recovery=True,
        )
    finally:
        if acquired and recovery_commit is not None:
            _park(root, operation_id)
        elif acquired:
            pending_exception = sys.exc_info()[0]
            try:
                _release(root, operation_id)
            except OSError, ValueError, TypeError:
                if pending_exception is None or issubclass(
                    pending_exception, (OSError, ValueError, TypeError)
                ):
                    try:
                        stopped = _inspect_update_observation(root)[0]
                    except OSError, ValueError, TypeError, UnicodeError:
                        stopped = None
                    if stopped is None or stopped.operation_id != operation_id:
                        raise _OwnedRecoveryCleanupFailure(
                            _outcome(
                                "unknown",
                                "recovery_cleanup_failed",
                                start=start,
                                operation_id=operation_id,
                                kind=saved.kind,
                                direction=saved.direction,
                                review_generation=saved.review.proposal.generation,
                                generation=current_status.generation,
                                phase="prepared" if prepared_commit else "admission",
                                publication="unknown",
                                history=(
                                    "prepared"
                                    if prepared_commit
                                    else current_status.history
                                ),
                                planned=max(planned, current_status.planned_files),
                                published=current_status.published_files,
                                checkpoint=(
                                    prepared_commit or current_status.checkpoint_commit
                                ),
                                intent=current_status.intent_commit,
                                stop=current_status.stop_commit,
                                changed=None,
                                recovery=True,
                            )
                        )
                    raise _OwnedRecoveryCleanupFailure(
                        _refuse_known_recovery(
                            stopped, "recovery_cleanup_failed", start=start
                        )
                    )


def execute_recovery(vault, preparation, *, cancel=None, executor=None):
    """Apply a selected recovery direction through the shared Operations seam."""
    try:
        return _execute_recovery(vault, preparation, cancel=cancel, executor=executor)
    except _OwnedRecoveryCleanupFailure as failure:
        return failure.result
