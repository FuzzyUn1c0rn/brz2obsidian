"""Durable existing-vault publication of one whole reviewed S1 result."""

import hashlib
import os
import shutil
import sys
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

from brz2obsidian.application.checkpoint_contracts import CheckpointManifest
from brz2obsidian.application.vault_contracts import VaultSubject
from brz2obsidian.application.vault_update_contracts import (
    VaultApplyResult,
    VaultComparisonDetail,
    VaultOperationIntent,
    VaultOperationLock,
    VaultOperationReceipt,
    VaultOperationStop,
    VaultPathMetadata,
    VaultRecoveryIntent,
    VaultUpdateDetailPage,
)
from brz2obsidian.content_values import content_sha, content_size
from brz2obsidian.contracts import ReviewPlan
from brz2obsidian.core import review_owned_targets, select_review_effects
from brz2obsidian.core.reversals import (
    _owned_documents,
    _owned_targets,
    reversal_document_target,
    review_owned_documents,
)
from brz2obsidian.publication.git_payload import verify_blobs
from brz2obsidian.publication.vault_admission import _safe_relative
from brz2obsidian.publication.vault_history import (
    _ApplyReviewOwners,
    _control_objects,
    _Git,
    _inspect_history,
    _inspect_retained_history,
    _MetadataCheckpoint,
    _MetadataHistory,
    _read,
    capture_checkpoint,
    inspect_history,
)
from brz2obsidian.publication.vault_native import observe_file, verify_directory
from brz2obsidian.publication.vault_replace import (
    copy_stage,
    move_file,
    retained_directory_metadata,
    retained_metadata,
    stage_directory_security,
    stage_parent_security,
    supported_durable_volume,
)

_ACTIVE = {}


def _lock_path(root):
    return root / ".git" / "brz2obsidian"


def _review_subjects(review, selected):
    paths = {row.path: row.subject_id for row in selected.files}
    if len(selected.remove_paths) != len(set(selected.remove_paths)):
        raise ValueError("Selected removal paths are duplicated")
    claimed_removals = set()
    for change in review.proposal.changes:
        owned = {change.path} & set(selected.remove_paths)
        subject = next(
            row
            for row in review.producer_facts.subjects
            if (row.item_id, row.facet) == (change.item_id, change.facet)
        )
        if subject.operation_reversal is not None:
            owned.update(
                row.path
                for row in subject.operation_reversal.outputs
                if row.target_existence == "absent"
                and row.path in selected.remove_paths
            )
        for path in owned:
            existing = paths.get(path)
            if existing is not None and existing != change.subject_id:
                raise ValueError("Selected removal has conflicting owner")
            if path in claimed_removals:
                raise ValueError("Selected removal has multiple reviewed owners")
            claimed_removals.add(path)
            paths[path] = change.subject_id
    if set(selected.remove_paths) - set(paths):
        raise ValueError("Selected removal has no reviewed owner")
    return tuple(
        VaultSubject(path=path, subject_id=owner)
        for path, owner in sorted(paths.items())
    )


def owns_operation(root, operation_id):
    """Same-owner admission requires the exact physical marker and anchors."""
    root = Path(root).absolute()
    if (str(root), operation_id) not in _ACTIVE:
        return False
    if _ACTIVE[str(root), operation_id][0] != os.getpid():
        return False
    directory = _lock_path(root)
    if not directory.is_dir() or set(os.listdir(directory)) != {"owner.json", "held"}:
        return False
    verify_directory(directory)
    _, _, raw, _ = observe_file(directory, directory / "owner.json", prefix_limit=4097)
    if len(raw) > 4096:
        return False
    owner = VaultOperationLock.model_validate_json(raw)
    return (
        owner.operation_id == operation_id
        and owner.vault_anchor == verify_directory(root)
        and owner.git_anchor == verify_directory(root / ".git")
    )


def _acquire(root, operation_id):
    directory = _lock_path(root)
    directory.mkdir()
    stream = None
    try:
        owner = VaultOperationLock(
            schema_id="brz2obsidian.vault-operation-lock",
            schema_version=1,
            operation_id=operation_id,
            vault_anchor=verify_directory(root),
            git_anchor=verify_directory(root / ".git"),
        )
        with (directory / "owner.json").open("xb") as stream:
            stream.write(owner.model_dump_json().encode())
            stream.flush()
            os.fsync(stream.fileno())
        with (directory / "held").open("xb") as held:
            held.write(b"1")
            held.flush()
            os.fsync(held.fileno())
        stream = (directory / "held").open("r+b")
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _ACTIVE[str(root), operation_id] = (os.getpid(), stream)
        if not owns_operation(root, operation_id):
            raise OSError("Owned operation marker could not be verified")
    except OSError, ValueError, TypeError:
        active = _ACTIVE.pop((str(root), operation_id), None)
        if active is not None:
            active[1].close()
        elif stream is not None:
            stream.close()
        if (directory / "owner.json").exists():
            (directory / "owner.json").unlink()
        if (directory / "held").exists():
            (directory / "held").unlink()
        directory.rmdir()
        raise


def _release(root, operation_id):
    if not owns_operation(root, operation_id):
        raise OSError("Owned operation marker changed")
    directory = _lock_path(root)
    _ACTIVE.pop((str(root), operation_id))[1].close()
    (directory / "owner.json").unlink()
    (directory / "held").unlink()
    directory.rmdir()


def _park(root, operation_id):
    """Drop this process's lock after a stop; retain the recovery marker."""
    active = _ACTIVE.pop((str(root), operation_id), None)
    if active is not None:
        active[1].close()


def _adopt(root, operation_id):
    """Claim only the validated stopped converter lease in this process."""
    root = Path(root).absolute()
    directory = _lock_path(root)
    if not os.path.lexists(directory):
        _acquire(root, operation_id)
        return
    if (str(root), operation_id) in _ACTIVE:
        raise OSError("Operation still holds an in-process lease")
    if not directory.is_dir() or set(os.listdir(directory)) != {"owner.json", "held"}:
        raise OSError("Stopped operation marker is torn")
    verify_directory(directory)
    _, _, raw, _ = observe_file(directory, directory / "owner.json", prefix_limit=4097)
    owner = VaultOperationLock.model_validate_json(raw)
    if (
        len(raw) > 4096
        or owner.operation_id != operation_id
        or owner.vault_anchor != verify_directory(root)
        or owner.git_anchor != verify_directory(root / ".git")
    ):
        raise OSError("Stopped operation owner is inconsistent")
    stream = (directory / "held").open("r+b")
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _ACTIVE[str(root), operation_id] = (os.getpid(), stream)
        if not owns_operation(root, operation_id):
            raise OSError("Stopped operation lease changed during adoption")
    except OSError, ValueError, TypeError:
        _ACTIVE.pop((str(root), operation_id), None)
        stream.close()
        raise


def _journal(git, name, record, *, parents=(), previous=None, ref=None):
    payload = record.model_dump_json().encode()
    sha = hashlib.sha256(payload).hexdigest()
    oid = git.call("hash-object", "-w", "--stdin", input=payload).decode().strip()
    verify_blobs(
        [*git.prefix, "cat-file", "--batch"],
        env=git.env,
        objects=((oid, len(payload), sha, None),),
    )
    tree = git.tree([(name, "100644", oid)])
    _control_objects(git, {tree: "tree"}, {})
    commit = (
        git.call(
            "commit-tree",
            tree,
            *(arg for parent in parents for arg in ("-p", parent)),
            input=b"brz2obsidian operation\n",
        )
        .decode()
        .strip()
    )
    _control_objects(git, {commit: "commit"}, {})
    git.call("update-ref", ref, commit, previous or "0" * 40)
    if git.call("rev-parse", "--verify", ref).decode().strip() != commit:
        raise OSError("Owned operation ref did not retain its commit")
    return commit


def _read_record(git, commit, name, contract):
    raw = _control_objects(git, {commit: "commit"}, {})[commit]
    headers, separator, _ = raw.partition(b"\n\n")
    parents = tuple(
        line[7:].decode("ascii")
        for line in headers.splitlines()
        if line.startswith(b"parent ")
    )
    trees = tuple(
        line[5:].decode("ascii")
        for line in headers.splitlines()
        if line.startswith(b"tree ")
    )
    if not separator or len(trees) != 1:
        raise OSError("Operation commit is incomplete")
    tree = trees[0]
    _control_objects(git, {tree: "tree"}, {})
    entry = git.call("ls-tree", "-z", commit).split(b"\0")
    if len(entry) != 2 or not entry[0].startswith(b"100644 blob "):
        raise OSError("Operation record graph has unknown edges")
    declaration, path = entry[0].split(b"\t", 1)
    if path != name.encode():
        raise OSError("Operation record path changed")
    oid = declaration.split()[2].decode("ascii")
    content = _control_objects(git, {oid: "blob"}, {})[oid]
    return contract.model_validate_json(content), parents


def _terminal_result_in_history(git, checkpoint, intent, receipt):
    """A completed result remains authoritative through later local checkpoints."""
    current = checkpoint.locator.commit
    generation = checkpoint.manifest.generation
    while current != receipt.result_commit:
        manifest = CheckpointManifest.model_validate_json(
            git.call("show", f"{current}:manifest.json")
        )
        if manifest.generation != generation or manifest.boundary != "local":
            return False
        current = manifest.previous
        generation -= 1
        if manifest.abandoned_collection_preparation is not None:
            prepared = CheckpointManifest.model_validate_json(
                git.call("show", f"{current}:manifest.json")
            )
            if prepared.collection_preparation_owner is None:
                return False
            current = prepared.previous
            generation -= 1
        if current is None or generation <= receipt.generation:
            return False
    result = CheckpointManifest.model_validate_json(
        git.call("show", f"{current}:manifest.json")
    )
    return (
        result.generation == receipt.generation + 1
        and result.boundary == "result"
        and result.association_id == intent.association_id
        and result.previous == intent.prepared_commit
        and result.preimage == intent.before
        and result.proposed == intent.proposed
        and result.vault == intent.proposed
    )


class _OperationGraph(NamedTuple):
    intent: VaultOperationIntent | VaultRecoveryIntent
    intent_commit: str
    origin_intent_commit: str
    authorities: tuple
    receipt: VaultOperationReceipt | None
    stopped: VaultOperationStop | None
    commit: str


def _validate_operation_ancestry(authorities, stops, commit, origin):
    by_commit = dict(authorities)
    for stopped in stops:
        authority = by_commit[stopped.intent_commit]
        if (
            stopped.operation_id != authority.operation_id
            or stopped.kind != authority.kind
            or stopped.generation != authority.generation
            or stopped.direction != authority.direction
            or stopped.acknowledged_after_files > len(authority.affected_paths)
        ):
            raise OSError("Stop identity disagrees with its authority")
    for index, (_, authority) in enumerate(authorities[:-1]):
        previous = authorities[index + 1][1]
        if (
            authority.origin_intent_commit != commit
            or authority.operation_id != origin.operation_id
            or authority.kind != origin.kind
            or authority.association_id != origin.association_id
            or authority.generation <= previous.generation
            or isinstance(previous, VaultRecoveryIntent)
            and authority.direction != previous.direction
        ):
            raise OSError(
                "Recovery ancestry identity, generation or direction disagrees"
            )


def _operation_receipt(git, commit, active_commit):
    receipt, parents = _read_record(git, commit, "receipt.json", VaultOperationReceipt)
    if active_commit is not None or parents != (
        receipt.intent_commit,
        receipt.result_commit,
    ):
        raise OSError("Receipt has invalid real edges or is being replayed")
    return receipt


def _operation_stop(git, commit):
    stopped, parents = _read_record(git, commit, "stop.json", VaultOperationStop)
    if parents != (stopped.intent_commit,):
        raise OSError("Stop has invalid real parent")
    return stopped


def _operation_recovery(git, commit):
    intent, parents = _read_record(git, commit, "recovery.json", VaultRecoveryIntent)
    if parents != (intent.previous_operation_commit, intent.prepared_commit):
        raise OSError("Recovery has invalid real parents")
    return intent


def _operation_origin(git, commit):
    origin, parents = _read_record(git, commit, "intent.json", VaultOperationIntent)
    if parents != (origin.prepared_commit,) or origin.direction != "finish":
        raise OSError("Original operation lacks its prepared finish authority")
    return origin


def _validate_terminal_receipt(top_receipt, authorities, origin):
    intent = authorities[0][1]
    expected_status = (
        "restored"
        if intent.direction == "restore"
        else "undone"
        if intent.kind == "undo"
        else "applied"
        if origin.affected_paths
        else "no_content_change"
    )
    if top_receipt is not None and (
        top_receipt.operation_id != intent.operation_id
        or top_receipt.kind != intent.kind
        or top_receipt.generation != intent.generation
        or top_receipt.direction != intent.direction
        or top_receipt.prepared_commit != intent.prepared_commit
        or top_receipt.published_paths != intent.affected_paths
        or top_receipt.status != expected_status
    ):
        raise OSError("Terminal receipt identity disagrees with active authority")
    return intent


def _operation_graph(git, commit):
    """Read one operation's exact retained authority chain, including stops."""
    tip = commit
    authorities = []
    stops = []
    expected_authority = None
    top_receipt = top_stop = None
    active_commit = None
    while True:
        entry = git.call("ls-tree", "--name-only", commit).decode().splitlines()
        if expected_authority is not None and entry not in (
            ["intent.json"],
            ["recovery.json"],
        ):
            raise OSError("Stop does not directly retain an authority")
        expected_authority = None
        if entry == ["receipt.json"]:
            receipt = _operation_receipt(git, commit, active_commit)
            top_receipt = receipt
            commit = receipt.intent_commit
            active_commit = commit
            expected_authority = commit
            continue
        if entry == ["stop.json"]:
            stopped = _operation_stop(git, commit)
            stops.append(stopped)
            expected_authority = stopped.intent_commit
            if active_commit is None:
                top_stop = stopped
                active_commit = stopped.intent_commit
            commit = stopped.intent_commit
            continue
        if entry == ["recovery.json"]:
            intent = _operation_recovery(git, commit)
            authorities.append((commit, intent))
            if active_commit is None:
                active_commit = commit
            commit = intent.previous_operation_commit
            continue
        if entry != ["intent.json"]:
            raise OSError("Unknown operation record graph")
        origin = _operation_origin(git, commit)
        authorities.append((commit, origin))
        if active_commit is None:
            active_commit = commit
        break
    _validate_operation_ancestry(authorities, stops, commit, origin)
    intent = _validate_terminal_receipt(top_receipt, authorities, origin)
    return _OperationGraph(
        intent, active_commit, commit, tuple(authorities), top_receipt, top_stop, tip
    )


def _read_operation_intent(git, commit):
    """Read an original/recovery authority after validating its complete ancestry."""
    graph = _operation_graph(git, commit)
    if graph.intent_commit != commit:
        raise OSError("Expected an operation authority commit")
    return graph.intent


class _UnpublishedRecovery(NamedTuple):
    """Validated checkpoint transition facts, with no published operation root."""

    generation: int
    association_id: str
    before: tuple
    proposed: tuple
    prepared_commit: str
    direction: str
    review_generation: int
    previous_operation_commit: str
    affected_paths: tuple


class _UnpublishedUndo(NamedTuple):
    """Prepared transition proof without a new operation or consumption."""

    generation: int
    association_id: str
    before: tuple
    proposed: tuple
    prepared_commit: str
    affected_paths: tuple
    undo_of_receipt_commit: str


def _prepared_recovery_lineage(
    intent, manifest, plan, origin, origin_commit, origin_plan, undo_target
):
    if undo_target is not None:
        if manifest.undo_of_receipt_commit != intent.undo_of_receipt_commit:
            return False
    elif (
        plan.proposal.generation != intent.review_generation
        or manifest.recovery_origin_intent_commit != origin_commit
        or manifest.recovery_previous_operation_commit
        != intent.previous_operation_commit
        or manifest.recovery_direction != intent.direction
    ):
        return False
    return origin is not None and origin_plan is not None


def _retained_prepared_incoming(
    plan, origin, origin_plan, direction, finish_incoming_rows
):
    retained_incoming = {}
    original_subjects = {
        (subject.item_id, subject.facet): subject
        for subject in origin_plan.producer_facts.subjects
    }
    for subject in plan.producer_facts.subjects:
        retained_source_incoming = (
            direction == "finish" and subject.operation_reversal is None
        )
        if subject.path not in origin.affected_paths or retained_source_incoming:
            original_subject = original_subjects.get((subject.item_id, subject.facet))
            if original_subject is None or subject.path != original_subject.path:
                return None
            expected = original_subject.incoming
            if retained_source_incoming and subject.path in origin.affected_paths:
                source_row = next(
                    (row for row in finish_incoming_rows if row.path == subject.path),
                    None,
                )
                if (
                    (expected is None) != (source_row is None)
                    or expected is not None
                    and (
                        content_size(expected) != source_row.size
                        or content_sha(expected) != source_row.sha256
                    )
                ):
                    return None
            retained_incoming[subject.path] = expected
    return retained_incoming


def _prepared_incoming_facts(
    intent,
    manifest,
    plan,
    origin,
    origin_commit,
    origin_plan,
    undo_target,
    origin_undo_target,
):
    source = {row.path: row for row in manifest.source}
    retained_incoming = {}
    if undo_target is not None or isinstance(
        intent, (VaultRecoveryIntent, _UnpublishedRecovery)
    ):
        if not _prepared_recovery_lineage(
            intent, manifest, plan, origin, origin_commit, origin_plan, undo_target
        ):
            return None
        direction = "restore" if undo_target is not None else intent.direction
        finish_incoming_rows = manifest.source
        if direction == "finish" and origin.kind == "undo":
            if (
                origin.undo_of_receipt_commit is None
                or origin_undo_target is None
                or origin_undo_target.receipt_commit != origin.undo_of_receipt_commit
                or origin_undo_target.intent.association_id != origin.association_id
            ):
                return None
            finish_incoming_rows = origin_undo_target.intent.before
        source = {
            row.path: row
            for row in (origin.proposed if direction == "finish" else origin.before)
        }
        retained_incoming = _retained_prepared_incoming(
            plan, origin, origin_plan, direction, finish_incoming_rows
        )
        if retained_incoming is None:
            return None
    elif (
        manifest.recovery_direction is not None
        or manifest.undo_of_receipt_commit is not None
    ):
        return None

    return source, retained_incoming


def _prepared_file_matches(row, content):
    return (
        row is not None
        and row.size == content_size(content)
        and row.sha256 == content_sha(content)
    )


def _prepared_fact_paths_match(plan, before, source, retained_incoming):
    def saved_current(path, expected):
        if not _safe_relative(path):
            return False
        row = before.get(path)
        return (
            row is None if expected is None else _prepared_file_matches(row, expected)
        )

    def saved_incoming(path, expected):
        if not _safe_relative(path):
            return False
        if path in retained_incoming:
            return expected == retained_incoming[path]
        row = source.get(path)
        return (
            row is None if expected is None else _prepared_file_matches(row, expected)
        )

    return _review_fact_paths_match(plan.producer_facts, saved_current, saved_incoming)


def _prepared_overlay_matches(before, proposed, selected, continued_removals):
    selected_files = {row.path: row.content for row in selected.files}
    removals = set(selected.remove_paths)
    if any(
        path not in before and path not in continued_removals or path in proposed
        for path in removals
    ):
        return False
    for path, content in selected_files.items():
        row = proposed.get(path)
        if not _prepared_file_matches(row, content):
            return False
        if path in before and before[path].mode != row.mode:
            return False
    return all(
        before.get(path) == proposed.get(path)
        for path in (before.keys() | proposed.keys()) - selected_files.keys() - removals
    )


def _prepared_for_intent(
    intent,
    manifest,
    loaded,
    *,
    origin=None,
    origin_commit=None,
    origin_plan=None,
    undo_target=None,
    origin_undo_target=None,
    origin_effects=None,
):
    """A retained prepared review authorizes exactly its selected transition."""
    if loaded is None:
        return False
    plan = loaded.saved.plan
    selected = loaded.historical_effects
    if selected is None:
        selected = select_review_effects(plan)
    if selected.status != "selected":
        return False
    if not (
        manifest.boundary == "prepared"
        and manifest.generation == intent.generation
        and manifest.association_id == intent.association_id
        and manifest.identity == plan.facts.incoming_identity
        and manifest.vault == intent.before
        and manifest.preimage == intent.before
        and manifest.proposed == intent.proposed
        and manifest.review_object is not None
    ):
        return False

    before = {row.path: row for row in intent.before}
    proposed = {row.path: row for row in intent.proposed}
    incoming = _prepared_incoming_facts(
        intent,
        manifest,
        plan,
        origin,
        origin_commit,
        origin_plan,
        undo_target,
        origin_undo_target,
    )
    if incoming is None:
        return False
    source, retained_incoming = incoming

    if not _prepared_fact_paths_match(plan, before, source, retained_incoming):
        return False
    from .attachment_ownership import (
        review_ownership_claims,
        validate_removal_continuations,
    )

    try:
        continued_removals = validate_removal_continuations(
            review_ownership_claims(plan, selected)[0],
            origin=origin,
            original=origin_plan,
            origin_commit=origin_commit,
            before=intent.before,
            direction=(
                intent.direction
                if isinstance(intent, (VaultRecoveryIntent, _UnpublishedRecovery))
                else None
            ),
            effects=origin_effects,
        )
    except OSError, ValueError, KeyError:
        return False
    return _prepared_overlay_matches(before, proposed, selected, continued_removals)


def _operation_history_fingerprint(origin_commit, origin):
    return hashlib.sha256((origin_commit + origin.association_id).encode()).hexdigest()


def _recovery_file_matches(row, content):
    if row is None:
        return content is None
    return (
        content is not None
        and row.size == content_size(content)
        and row.sha256 == content_sha(content)
    )


class _RecoveryFiles(NamedTuple):
    target: dict
    produced: dict
    current: dict
    original_proposed: dict


class _OriginReviewFiles(NamedTuple):
    subjects: dict
    files: dict
    removals: set
    documents: set


def _cover_original_creation_or_rename(
    origin_item, origin_subject, subject, origin, direction, files, original, covered
):
    old_path = origin_item.current.path
    new_path = subject.path
    if (
        direction == "finish"
        and old_path == new_path
        and subject.current.path == new_path
        and origin_subject.current.existence == "absent"
        and subject.path == origin_subject.path
        and subject.source_target == origin_subject.source_target
        and new_path in origin.affected_paths
        and new_path not in files.produced
        and new_path in original.files
        and _recovery_file_matches(files.target.get(new_path), original.files[new_path])
    ):
        # A selected original creation has one real identity
        # at the same path after publication. Its absence in
        # the original before inventory is the reviewed
        # physical effect, not an arbitrary source version.
        covered.add(new_path)
        return True
    if (
        direction == "finish"
        and old_path != new_path
        and subject.path == origin_subject.path
        and subject.source_target == origin_subject.source_target
        and subject.current.path
        == (old_path if old_path in files.current else new_path)
        and {old_path, new_path}.issubset(origin.affected_paths)
        and old_path in original.removals
        and new_path in original.files
        and _recovery_file_matches(
            files.produced.get(old_path), origin_item.current.content
        )
        and old_path not in files.target
        and not (old_path in files.current and new_path in files.current)
        and new_path not in files.produced
        and _recovery_file_matches(files.target.get(new_path), original.files[new_path])
    ):
        # The original reviewed rename authorizes both its
        # displaced old path and selected new output. The
        # recovery review separately binds the later current
        # new-path bytes and exact selected overlay.
        covered.update((old_path, new_path))
        return True
    return False


def _cover_unproved_recovery_subject(
    subject, direction, origin, origin_plan, loaded, covered, files, original
):
    if (subject.item_id, subject.facet) in original.subjects:
        origin_subject = original.subjects[(subject.item_id, subject.facet)]
        origin_items = tuple(
            item
            for item in origin_plan.producer_facts.identity_inventory
            if item.identity_state == "valid"
            and item.identity is not None
            and (
                item.identity.module_id,
                item.identity.collection_id,
            )
            == (
                origin_plan.producer_facts.incoming_identity.module_id,
                origin_plan.producer_facts.incoming_identity.collection_id,
            )
            and (item.identity.item_id, item.facet) == (subject.item_id, subject.facet)
        )
        if len(origin_items) == 1 and _cover_original_creation_or_rename(
            origin_items[0],
            origin_subject,
            subject,
            origin,
            direction,
            files,
            original,
            covered,
        ):
            return True
        paths = {subject.path, subject.current.path}
        paths.update(
            item.current.path
            for item in loaded.saved.plan.producer_facts.identity_inventory
            if item.identity is not None
            and (item.identity.item_id, item.facet) == (subject.item_id, subject.facet)
        )
        for path in paths & set(origin.affected_paths):
            if (path in files.target) != (path in files.produced):
                return False
            covered.add(path)
    elif subject.path in origin.affected_paths:
        owners = tuple(
            item
            for item in origin_plan.producer_facts.identity_inventory
            if item.identity_state == "valid"
            and item.identity is not None
            and (
                item.identity.module_id,
                item.identity.collection_id,
            )
            == (
                origin_plan.producer_facts.incoming_identity.module_id,
                origin_plan.producer_facts.incoming_identity.collection_id,
            )
            and (item.identity.item_id, item.facet) == (subject.item_id, subject.facet)
            and item.current.path == subject.path
            and item.target == subject.source_target
        )
        if (
            len(owners) != 1
            or subject.current.path != subject.path
            or subject.path not in original.documents
            or not _recovery_file_matches(
                files.original_proposed.get(subject.path),
                original.files.get(subject.path),
            )
            or (subject.path in files.target) != (subject.path in files.produced)
        ):
            return False
        covered.add(subject.path)
    return True


def _cover_proved_recovery_subject(
    subject,
    proof,
    origin,
    origin_commit,
    origin_plan,
    direction,
    files,
    origin_loaded,
    origin_effects,
    covered,
    owned_documents,
    owned_targets,
):
    change = next(
        (
            change
            for change in origin_plan.proposal.changes
            if change.change_id == proof.origin_change_id
        ),
        None,
    )
    document = reversal_document_target(subject)
    if (
        change is None
        or (
            document is None
            and (change.item_id, change.facet) != (subject.item_id, subject.facet)
        )
        or proof.operation_id != origin.operation_id
        or proof.operation_kind != origin.kind
        or proof.direction != direction
        or proof.operation_generation != origin.generation
        or proof.history_fingerprint
        != _operation_history_fingerprint(origin_commit, origin)
    ):
        return False, owned_documents
    if document is not None and owned_documents is None:
        owned_documents = (
            review_owned_documents(origin_plan)
            if origin_loaded is None
            else _owned_documents(origin_plan, lambda: origin_effects)
        )
    owned = (
        tuple(
            t
            for change_id, decision_id, t in owned_documents
            if (change_id, decision_id)
            == (proof.origin_change_id, proof.origin_decision_id)
            and t == document
        )
        if document is not None
        else owned_targets(proof.origin_change_id, proof.origin_decision_id)
    )
    if proof.owned_targets != owned:
        return False, owned_documents
    for row in proof.outputs:
        if (
            row.path not in origin.affected_paths
            or not _recovery_file_matches(files.produced.get(row.path), row.produced)
            or not _recovery_file_matches(
                files.current.get(row.path), row.current.content
            )
            or not _recovery_file_matches(files.target.get(row.path), row.target)
            or row.path in covered
        ):
            return False, owned_documents
        covered.add(row.path)
    return True, owned_documents


def _qualified_manual_recovery_reference(
    subject,
    path,
    origin_plan,
    approval,
    continued_removals,
    original_file,
    document,
    files,
):
    manual_reference = False
    continuation = (
        subject.attachment.removal_continuation
        if subject.attachment is not None
        else None
    )
    if (
        continuation is not None
        and continuation.path in continued_removals
        and continuation.origin_change_id == approval.change_id
        and continuation.origin_decision_id == approval.decision_id
        and approval.choice == "remove"
        and approval.provenance == "explicit_user"
        and approval.attachment_selection is not None
        and approval.attachment_candidate is not None
    ):
        context = origin_plan.producer_facts.link_context
        original_documents = tuple(
            d for d in context.current_documents if d.source_path == path
        )
        declared = tuple(
            e
            for e in origin_plan.producer_facts.identity_inventory
            if e.current.path == path
        )
        records = tuple(t for t in context.current_targets if t.canonical_path == path)
        produced_documents = tuple(
            d for d in approval.attachment_candidate.documents if d.source_path == path
        )
        manual_reference = (
            len(original_documents)
            == len(declared)
            == len(records)
            == len(produced_documents)
            == 1
            and declared[0].identity_state == "missing"
            and declared[0].identity is None
            and declared[0].raw_identity is None
            and declared[0].facet == "content"
            and records[0].kind == "note"
            and records[0].identity is None
            and records[0].target_id
            == original_documents[0].document_id
            == produced_documents[0].document_id
            and produced_documents[0].content == original_file.content
            and document is not None
            and document.document_id == original_documents[0].document_id
            and _recovery_file_matches(
                files.produced.get(path), original_documents[0].content
            )
            and any(
                choice.document_id == original_documents[0].document_id
                and choice.old.target_id == continuation.target_id
                and choice.provenance == "explicit_user"
                for choice in approval.attachment_selection.link_choices
            )
        )
    return manual_reference


def _cover_finish_attachment_path(
    path,
    intent,
    origin_plan,
    origin_effects,
    approval,
    change,
    loaded,
    subject,
    owned,
    selected_files,
    proposed,
    observed_documents,
    files,
    original,
    continued_removals,
    covered,
):
    original_file = next(
        (
            row
            for row in origin_effects.files
            if row.path == path and row.subject_id == change.subject_id
        ),
        None,
    )
    chosen = selected_files.get(path)
    current_change = next(
        (
            row
            for row in loaded.saved.plan.proposal.changes
            if (row.item_id, row.facet) == (change.item_id, change.facet)
        ),
        None,
    )
    current_approval = next(
        (
            row
            for row in loaded.saved.plan.approvals
            if current_change is not None
            and row.change_id == current_change.change_id
            and row.domain == "attachment"
            and row.choice == "current"
            and row.provenance == "explicit_user"
            and row.attachment_candidate is not None
        ),
        None,
    )
    output = tuple(row for row in owned if row.canonical_path == path)
    if (
        original_file is not None
        and chosen is None
        and current_approval is not None
        and path not in intent.affected_paths
        and _recovery_file_matches(
            files.original_proposed.get(path), original_file.content
        )
        and files.current.get(path) == proposed.get(path)
    ):
        if (
            len(output) == 1
            and output[0].kind == "resource"
            and path not in files.produced
            and files.current.get(path) == files.target.get(path)
        ):
            covered.add(path)
            return
        document = observed_documents.get(path)
        approved_documents = tuple(
            row
            for row in current_approval.attachment_candidate.documents
            if row.source_path == path
        )
        owners = tuple(
            row
            for row in origin_plan.producer_facts.identity_inventory
            if row.identity_state == "valid"
            and row.identity is not None
            and row.facet == "content"
            and row.current.path == path
            and (row.identity.module_id, row.identity.collection_id)
            == (
                origin_plan.producer_facts.incoming_identity.module_id,
                origin_plan.producer_facts.incoming_identity.collection_id,
            )
        )
        if (
            len(owners) == 1
            and path in original.documents
            and path in files.target
            and path in files.produced
            and document is not None
            and document.status == "supported"
            and approved_documents == (document,)
            and _recovery_file_matches(files.current.get(path), document.content)
        ):
            covered.add(path)
            return
    if (
        original_file is None
        or chosen is None
        or chosen.subject_id != change.subject_id
        or not _recovery_file_matches(
            files.original_proposed.get(path), original_file.content
        )
        or not _recovery_file_matches(proposed.get(path), chosen.content)
    ):
        return
    if len(output) == 1 and output[0].kind == "resource":
        # Finish may reuse an already exact selected output, or
        # create the original absent endpoint. A later different
        # current binary needs its own actual S1 current fact.
        if (
            path not in files.produced
            and _recovery_file_matches(files.target.get(path), original_file.content)
            and (path not in files.current or files.current[path] == files.target[path])
            and chosen.content == original_file.content
        ):
            covered.add(path)
        return
    owners = tuple(
        row
        for row in origin_plan.producer_facts.identity_inventory
        if row.identity_state == "valid"
        and row.identity is not None
        and row.facet == "content"
        and row.current.path == path
        and (row.identity.module_id, row.identity.collection_id)
        == (
            origin_plan.producer_facts.incoming_identity.module_id,
            origin_plan.producer_facts.incoming_identity.collection_id,
        )
    )
    document = observed_documents.get(path)
    manual_reference = _qualified_manual_recovery_reference(
        subject,
        path,
        origin_plan,
        approval,
        continued_removals,
        original_file,
        document,
        files,
    )
    if (
        (len(owners) == 1 or manual_reference)
        and path in original.documents
        and document is not None
        and document.status == "supported"
        and path in files.target
        and path in files.produced
        and _recovery_file_matches(files.current.get(path), document.content)
    ):
        covered.add(path)


def _cover_finish_attachment_paths(
    intent,
    origin,
    origin_plan,
    loaded,
    origin_effects,
    owned_targets,
    continued_removals,
    files,
    original,
    covered,
):
    selected = loaded.historical_effects
    if selected is None:
        selected = select_review_effects(loaded.saved.plan)
    if selected.status != "selected":
        return False
    selected_files = {row.path: row for row in selected.files}
    proposed = {row.path: row for row in intent.proposed}
    observed_documents = {
        row.source_path: row
        for row in (
            ()
            if loaded.saved.plan.producer_facts.link_context is None
            else loaded.saved.plan.producer_facts.link_context.current_documents
        )
    }
    for approval in origin_plan.approvals:
        if approval.domain != "attachment":
            continue
        change = next(
            row
            for row in origin_plan.proposal.changes
            if row.change_id == approval.change_id
        )
        subject = next(
            (
                row
                for row in loaded.saved.plan.producer_facts.subjects
                if (row.item_id, row.facet) == (change.item_id, change.facet)
            ),
            None,
        )
        if subject is None or subject.operation_reversal is not None:
            continue
        owned = owned_targets(approval.change_id, approval.decision_id)
        for path in set(origin.affected_paths) - covered:
            _cover_finish_attachment_path(
                path,
                intent,
                origin_plan,
                origin_effects,
                approval,
                change,
                loaded,
                subject,
                owned,
                selected_files,
                proposed,
                observed_documents,
                files,
                original,
                continued_removals,
                covered,
            )
    return True


def _cover_recovery_subjects(
    loaded,
    continued_removals,
    origin,
    origin_commit,
    origin_plan,
    direction,
    files,
    original,
    origin_loaded,
    origin_effects,
    covered,
    owned_targets,
):
    owned_documents = None
    for subject in loaded.saved.plan.producer_facts.subjects:
        if (
            subject.attachment is not None
            and subject.attachment.removal_continuation is not None
        ):
            if (
                subject.current.path not in continued_removals
                or subject.current.path in covered
            ):
                return False
            covered.add(subject.current.path)
            continue
        proof = subject.operation_reversal
        if proof is None:
            if not _cover_unproved_recovery_subject(
                subject,
                direction,
                origin,
                origin_plan,
                loaded,
                covered,
                files,
                original,
            ):
                return False
            continue
        proved, owned_documents = _cover_proved_recovery_subject(
            subject,
            proof,
            origin,
            origin_commit,
            origin_plan,
            direction,
            files,
            origin_loaded,
            origin_effects,
            covered,
            owned_documents,
            owned_targets,
        )
        if not proved:
            return False
    return True


def _recovery_prepared_matches(
    intent,
    origin,
    origin_commit,
    manifest,
    loaded,
    lineage,
    origin_plan,
    *,
    direction=None,
    undo_target=None,
    origin_loaded=None,
):
    """Bind reviewed operation targets separately from truthful source lineage."""
    direction = direction or intent.direction
    if manifest.source != lineage.source or manifest.identity != lineage.identity:
        return False
    if not set(intent.affected_paths).issubset(origin.affected_paths):
        return False
    target = {
        row.path: row
        for row in (origin.proposed if direction == "finish" else origin.before)
    }
    produced = {
        row.path: row
        for row in (origin.before if direction == "finish" else origin.proposed)
    }
    current = {row.path: row for row in intent.before}
    ownership_proposed = (
        undo_target.graph.authorities[-1][1].proposed
        if undo_target is not None
        else origin.proposed
    )
    original_proposed = {row.path: row for row in ownership_proposed}
    origin_subjects = {
        (subject.item_id, subject.facet): subject
        for subject in origin_plan.producer_facts.subjects
    }
    if origin_loaded is not None:
        origin_effects = (
            origin_loaded.historical_effects
            if origin_loaded.saved.plan is origin_plan
            else None
        )
    else:
        origin_effects = select_review_effects(origin_plan)
    if origin_effects is None or origin_effects.status != "selected":
        return False
    origin_files = {row.path: row.content for row in origin_effects.files}
    origin_removals = set(origin_effects.remove_paths)
    from .attachment_ownership import (
        review_ownership_claims,
        validate_removal_continuations,
    )

    try:
        continued_removals = validate_removal_continuations(
            review_ownership_claims(loaded.saved.plan, loaded.historical_effects)[0],
            origin=origin,
            original=origin_plan,
            origin_commit=origin_commit,
            before=intent.before,
            direction=direction,
            effects=origin_effects,
        )
    except OSError, ValueError, KeyError:
        return False
    origin_documents = {
        row.source_path
        for row in (
            ()
            if origin_plan.producer_facts.link_context is None
            else origin_plan.producer_facts.link_context.current_documents
        )
    }
    files = _RecoveryFiles(target, produced, current, original_proposed)
    original = _OriginReviewFiles(
        origin_subjects, origin_files, origin_removals, origin_documents
    )
    covered = set()

    def owned_targets(change_id, decision_id):
        return (
            review_owned_targets(origin_plan, change_id, decision_id)
            if origin_loaded is None
            else _owned_targets(
                origin_plan, change_id, decision_id, lambda: origin_effects
            )
        )

    if not _cover_recovery_subjects(
        loaded,
        continued_removals,
        origin,
        origin_commit,
        origin_plan,
        direction,
        files,
        original,
        origin_loaded,
        origin_effects,
        covered,
        owned_targets,
    ):
        return False
    if direction == "finish" and not _cover_finish_attachment_paths(
        intent,
        origin,
        origin_plan,
        loaded,
        origin_effects,
        owned_targets,
        continued_removals,
        files,
        original,
        covered,
    ):
        return False
    return covered == set(origin.affected_paths)


def _unpublished_recovery_matches(
    graph, checkpoint, owned, origins, *, origin_undo_target=None
):
    """An exact retained preparation does not advance operation authority."""
    manifest, loaded = checkpoint.manifest, checkpoint.review
    if (
        loaded is None
        or manifest.recovery_direction is None
        or manifest.generation <= graph.intent.generation
        or isinstance(graph.intent, VaultRecoveryIntent)
        and manifest.recovery_direction != graph.intent.direction
    ):
        return False
    origin = graph.authorities[-1][1]
    before = {row.path: row for row in manifest.vault}
    proposed = {row.path: row for row in manifest.proposed}
    transition = _UnpublishedRecovery(
        manifest.generation,
        origin.association_id,
        manifest.vault,
        manifest.proposed,
        checkpoint.locator.commit,
        manifest.recovery_direction,
        loaded.saved.plan.proposal.generation,
        graph.commit,
        tuple(
            sorted(
                path
                for path in before.keys() | proposed.keys()
                if before.get(path) != proposed.get(path)
            )
        ),
    )
    original_loaded = owned[origin.prepared_commit][1]
    original_plan = original_loaded.saved.plan
    lineage_commit = (
        origin.prepared_commit
        if transition.direction == "finish"
        else origins[graph.origin_intent_commit]
    )
    return _prepared_for_intent(
        transition,
        manifest,
        loaded,
        origin=origin,
        origin_commit=graph.origin_intent_commit,
        origin_plan=original_plan,
        origin_undo_target=origin_undo_target,
        origin_effects=original_loaded.historical_effects,
    ) and _recovery_prepared_matches(
        transition,
        origin,
        graph.origin_intent_commit,
        manifest,
        loaded,
        owned[lineage_commit][0],
        original_plan,
        origin_loaded=original_loaded,
    )


def _terminal_files_match(root, intent):
    proposed = {row.path: row for row in intent.proposed}
    metadata = {row.path: row for row in intent.result_metadata}
    return all(state == "after" for state in _directory_states(root, intent)) and all(
        _metadata_matches(root, path, metadata.get(path))
        and (proposed.get(path) is None or _same_file(root, proposed[path]))
        for path in intent.affected_paths
    )


class _OperationObservation(NamedTuple):
    graph: _OperationGraph
    checkpoint: object
    owned: dict
    unpublished_prepared: str | None = None
    graphs: tuple = ()
    checkpoint_roles: tuple = ()
    origin_undo_target: object = None


def _inspect_update_observation(vault, *, _owners=None):
    """Return fresh status and validated graph facts for this one public call."""
    from .collection_publication import local_publication_status

    pending = local_publication_status(Path(vault).absolute())
    if pending is not None:
        return pending, None
    observations = []
    status = _inspect_update_status(vault, observations=observations, _owners=_owners)
    observation = observations[0] if observations else None
    if observation is not None and (
        status.operation_id,
        status.kind,
        status.generation,
        status.intent_commit,
    ) == (
        observation.graph.intent.operation_id,
        observation.graph.intent.kind,
        observation.graph.intent.generation,
        observation.graph.intent_commit,
    ):
        original = observation.graph.authorities[-1][1]
        loaded = observation.owned[original.prepared_commit][1]
        if loaded is not None:
            status = status.model_copy(
                update={"origin_role": loaded.saved.plan.facts.format_operation.kind}
            )
    return status, observation


def inspect_update_status(vault):
    with ExitStack() as owners:
        return _inspect_update_observation(vault, _owners=owners)[0]


def _operation_refs(git):
    raw = git.call(
        "for-each-ref",
        "--format=%(refname) %(objectname)",
        "refs/brz2obsidian/imports",
    )
    operations = []
    for line in raw.splitlines():
        ref, oid = line.split(b" ")
        parts = ref.split(b"/")
        if (
            len(parts) == 6
            and parts[:3] == [b"refs", b"brz2obsidian", b"imports"]
            and parts[4] == b"operations"
        ):
            operations.append(
                tuple(value.decode("ascii") for value in (parts[3], parts[5], oid))
            )
    return operations


def _ordered_operation_graphs(git, operations):
    records = []
    graphs = []
    for association, operation_id, commit in operations:
        graph = _operation_graph(git, commit)
        intent, receipt, stopped = graph.intent, graph.receipt, graph.stopped
        if intent.operation_id != operation_id or intent.association_id != association:
            raise OSError("Operation ref identity changed")
        graphs.append(graph)
        records.append((intent.generation, intent, receipt, stopped, commit))
    records.sort(key=lambda row: row[0])
    if len({row[0] for row in records}) != len(records):
        raise OSError("Multiple operation intents claim one generation")
    graphs.sort(key=lambda graph: graph.intent.generation)
    return records, graphs


def _operation_checkpoints(git, graphs, records):
    targets = {
        authority.prepared_commit
        for graph in graphs
        for _, authority in graph.authorities
    }
    targets.update(row[2].result_commit for row in records if row[2] is not None)
    origins = {}
    for graph in graphs:
        origin = graph.authorities[-1][1]
        declared = CheckpointManifest.model_validate_json(
            git.call("show", f"{origin.prepared_commit}:manifest.json")
        )
        if declared.previous is None:
            raise OSError("Operation origin lacks prior source lineage")
        origins[graph.origin_intent_commit] = declared.previous
        targets.add(declared.previous)
    return targets, origins


def _retained_operation_undo_target(
    origin, graph, graphs, owned, checkpoint, checkpoint_roles
):
    undo_target = None
    if origin.undo_of_receipt_commit is not None:
        from brz2obsidian.publication.vault_undo import _target_from_graph

        preceding = sorted(
            (item for item in graphs if item.intent.generation < origin.generation),
            key=lambda item: item.intent.generation,
        )
        target_graph = next(
            (
                item
                for item in preceding
                if item.commit == origin.undo_of_receipt_commit
            ),
            None,
        )
        if target_graph is None or not preceding:
            raise OSError("Undo target is not a retained preceding operation")
        previous = preceding[-1]
        if previous.commit != target_graph.commit and not (
            previous.intent.kind == "undo"
            and previous.receipt is not None
            and previous.receipt.status == "restored"
            and previous.authorities[-1][1].undo_of_receipt_commit
            == target_graph.commit
        ):
            raise OSError("Undo target has been superseded or consumed")
        from brz2obsidian.publication.vault_undo import _unused_preparations

        if (
            previous.receipt is None
            or not _unused_preparations(
                owned[origin.prepared_commit][0].previous,
                previous.receipt.result_commit,
                target_graph.commit,
                checkpoint_roles,
            )
            or target_graph.intent.association_id != origin.association_id
        ):
            raise OSError("Undo lacks exact current completed history")
        undo_target = _target_from_graph(
            target_graph,
            _OperationObservation(graph, checkpoint, owned, graphs=tuple(graphs)),
        )
    return undo_target


def _validate_operation_preparations(
    graph, origin, origin_saved, origin_plan, undo_target, owned, origins
):
    for _, authority in reversed(graph.authorities):
        prepared, saved = owned[authority.prepared_commit]
        initial_undo = undo_target if authority is origin else None
        validation_origin = (
            initial_undo.observation.owned[initial_undo.intent.prepared_commit][1]
            if initial_undo is not None
            else origin_saved
        )
        if not _prepared_for_intent(
            authority,
            prepared,
            saved,
            origin=initial_undo.intent if initial_undo else origin,
            origin_commit=(
                initial_undo.graph.origin_intent_commit
                if initial_undo
                else graph.origin_intent_commit
            ),
            origin_plan=initial_undo.plan if initial_undo else origin_plan,
            undo_target=initial_undo,
            origin_undo_target=undo_target,
            origin_effects=validation_origin.historical_effects,
        ):
            raise OSError("Operation intent lacks a selected prepared review")
        if initial_undo is not None and not _recovery_prepared_matches(
            authority,
            undo_target.intent,
            undo_target.graph.origin_intent_commit,
            prepared,
            saved,
            undo_target.lineage,
            undo_target.plan,
            direction="restore",
            undo_target=undo_target,
            origin_loaded=undo_target.observation.owned[
                undo_target.intent.prepared_commit
            ][1],
        ):
            raise OSError("Undo target or source lineage changed")
        if isinstance(authority, VaultRecoveryIntent):
            if authority.undo_of_receipt_commit not in (
                None,
                origin.undo_of_receipt_commit,
            ):
                raise OSError("Recovery changed the original Undo target")
            lineage_commit = (
                origin.prepared_commit
                if authority.direction == "finish"
                else origins[graph.origin_intent_commit]
            )
            if not _recovery_prepared_matches(
                authority,
                origin,
                graph.origin_intent_commit,
                prepared,
                saved,
                owned[lineage_commit][0],
                origin_plan,
                origin_loaded=origin_saved,
            ):
                raise OSError("Recovery target or source lineage changed")


def _validate_operation_result(graph, owned):
    candidate, terminal = graph.intent, graph.receipt
    prepared, _saved = owned[candidate.prepared_commit]
    if terminal is not None:
        result, _ = owned[terminal.result_commit]
        if not (
            result.boundary == "result"
            and result.generation == candidate.generation + 1
            and result.association_id == candidate.association_id
            and result.operation_intent_commit == terminal.intent_commit
            and result.previous == candidate.prepared_commit
            and result.preimage == candidate.before
            and result.proposed == candidate.proposed
            and result.vault == candidate.proposed
            and (
                result.collection_record_path is None
                and prepared.collection_record_path is None
                or result.collection_record_path == prepared.collection_record_path
                and result.identity == prepared.identity
                and result.source == prepared.source
            )
        ):
            raise OSError("Terminal receipt lacks its exact result checkpoint")


def _validate_retained_operations(graphs, checkpoint, owned, checkpoint_roles, origins):
    active_undo_target = None
    for graph in graphs:
        origin = graph.authorities[-1][1]
        origin_saved = owned[origin.prepared_commit][1]
        if origin_saved is None:
            raise OSError("Operation origin lacks its retained review")
        origin_plan = origin_saved.saved.plan
        undo_target = _retained_operation_undo_target(
            origin, graph, graphs, owned, checkpoint, checkpoint_roles
        )
        if graph is graphs[-1]:
            active_undo_target = undo_target
        _validate_operation_preparations(
            graph, origin, origin_saved, origin_plan, undo_target, owned, origins
        )
        _validate_operation_result(graph, owned)
    return active_undo_target


def _observe_operation_checkpoint(
    observation, unpublished_prepared, observations, start, review_generation
):
    active_graph, checkpoint = observation.graph, observation.checkpoint
    intent, receipt, stopped, commit = (
        active_graph.intent,
        active_graph.receipt,
        active_graph.stopped,
        active_graph.commit,
    )
    try:
        manifest = checkpoint.manifest
        unpublished_undo = False
        if (
            receipt is not None
            and manifest.boundary == "prepared"
            and manifest.undo_of_receipt_commit is not None
        ):
            from brz2obsidian.publication.vault_undo import (
                _unpublished_undo_matches,
            )

            unpublished_undo = _unpublished_undo_matches(observation)
        if (
            checkpoint.status != "valid"
            or manifest.association_id != intent.association_id
            or manifest.generation < intent.generation
            or (
                manifest.boundary == "prepared"
                and not unpublished_prepared
                and not unpublished_undo
                and (
                    checkpoint.locator.commit != intent.prepared_commit
                    or manifest.preimage != intent.before
                    or manifest.proposed != intent.proposed
                )
            )
            or (
                manifest.boundary == "result"
                and (
                    manifest.previous != intent.prepared_commit
                    or manifest.preimage != intent.before
                    or manifest.proposed != intent.proposed
                )
            )
            or manifest.boundary
            not in (
                ("result", "local", "prepared")
                if unpublished_undo
                else ("result", "local")
                if receipt is not None
                else ("prepared", "result")
            )
        ):
            raise OSError("Operation intent and owned checkpoint disagree")
        if unpublished_prepared:
            observations[-1] = observation._replace(
                unpublished_prepared=checkpoint.locator.commit,
            )
        if unpublished_undo:
            observations[-1] = observation._replace(
                unpublished_prepared=checkpoint.locator.commit,
            )
            return _outcome(
                "content_complete",
                "undo_prepared",
                start=start,
                operation_id=intent.operation_id,
                kind=intent.kind,
                direction=intent.direction,
                generation=intent.generation,
                phase="prepared",
                publication="complete",
                history="terminal",
                planned=len(intent.affected_paths),
                published=len(receipt.published_paths),
                changed=bool(receipt.published_paths),
                checkpoint=intent.prepared_commit,
                intent=receipt.intent_commit,
                result=receipt.result_commit,
                receipt=commit,
                recovery=True,
                message="Undo preparation retained; no new operation has started.",
            )
    except OSError, ValueError, TypeError, UnicodeError:
        return _outcome(
            "unknown",
            "operation_checkpoint_invalid",
            start=start,
            operation_id=intent.operation_id,
            kind=intent.kind,
            direction=intent.direction,
            review_generation=review_generation,
            generation=intent.generation,
            phase="intent",
            publication="unknown",
            history="unknown",
            planned=len(intent.affected_paths),
            changed=None,
            checkpoint=intent.prepared_commit,
            intent=active_graph.intent_commit,
            receipt=commit if receipt is not None else None,
            stop=commit if stopped is not None else None,
            recovery=True,
        )
    return None


def _terminal_cleanup_matches(root, git, commit, intent):
    from .collection_publication import scoped_terminal_marker

    scoped = scoped_terminal_marker(root, git, commit, intent.operation_id)
    return _terminal_files_match(root, intent) if scoped is None else scoped


def _terminal_operation_status(
    root, git, checkpoint, intent, receipt, commit, start, review_generation
):
    complete_history = checkpoint.status == "valid" and _terminal_result_in_history(
        git, checkpoint, intent, receipt
    )
    if complete_history and not _lock_path(root).exists():
        return _outcome(
            receipt.status,
            receipt.status,
            start=start,
            operation_id=intent.operation_id,
            kind=intent.kind,
            direction=intent.direction,
            review_generation=review_generation,
            generation=intent.generation,
            phase="terminal",
            publication="complete",
            history="terminal",
            planned=len(intent.affected_paths),
            published=len(receipt.published_paths),
            changed=bool(receipt.published_paths),
            checkpoint=intent.prepared_commit,
            intent=receipt.intent_commit,
            result=receipt.result_commit,
            receipt=commit,
            message="Validated terminal operation record.",
        )
    if (
        complete_history
        and _lock_path(root).exists()
        and _terminal_cleanup_matches(root, git, commit, intent)
    ):
        return _outcome(
            "content_complete",
            "terminal_cleanup_required",
            start=start,
            operation_id=intent.operation_id,
            kind=intent.kind,
            direction=intent.direction,
            review_generation=review_generation,
            generation=intent.generation,
            phase="terminal",
            publication="complete",
            history="terminal",
            planned=len(intent.affected_paths),
            published=len(receipt.published_paths),
            changed=bool(receipt.published_paths),
            checkpoint=intent.prepared_commit,
            intent=receipt.intent_commit,
            result=receipt.result_commit,
            receipt=commit,
            recovery=True,
            message="Exact result and receipt retained; owned marker needs cleanup.",
        )
    return _outcome(
        "unknown",
        "terminal_requires_recovery",
        start=start,
        operation_id=intent.operation_id,
        kind=intent.kind,
        direction=intent.direction,
        review_generation=review_generation,
        generation=intent.generation,
        phase="terminal",
        publication="unknown",
        history="terminal",
        planned=len(intent.affected_paths),
        checkpoint=intent.prepared_commit,
        intent=receipt.intent_commit,
        result=receipt.result_commit,
        receipt=commit,
        changed=None,
        recovery=True,
    )


def _observed_publication_states(root, intent):
    prior = {row.path: row for row in intent.before}
    proposed = {row.path: row for row in intent.proposed}
    prior_metadata = {row.path: row for row in intent.before_metadata}
    result_metadata = {row.path: row for row in intent.result_metadata}
    states = []
    for path in intent.affected_paths:
        before = prior.get(path)
        after = proposed.get(path)
        before_match = (
            _same_file(root, before)
            and _metadata_matches(root, path, prior_metadata[path])
            if before is not None
            else not os.path.lexists(root / path)
        )
        after_match = (
            _same_file(root, after)
            and _metadata_matches(root, path, result_metadata[path])
            if after is not None
            else not os.path.lexists(root / path)
        )
        states.append(
            "before"
            if before_match and not after_match
            else "after"
            if after_match and not before_match
            else "unknown"
        )
    directory_states = _directory_states(root, intent)
    protected_states = [
        "before" if _same_file(root, prior[path]) else "unknown"
        for path in intent.protected_paths
    ]
    all_states = states + directory_states
    if "unknown" in protected_states:
        all_states.append("unknown")
    return states, all_states


def _unfinished_operation_status(
    root,
    intent,
    intent_commit,
    commit,
    stopped,
    retained_result,
    start,
    review_generation,
):
    states, all_states = _observed_publication_states(root, intent)
    if "unknown" in all_states:
        status, publication, code = "unknown", "unknown", "unknown_current_bytes"
    elif not all_states:
        status, publication, code = (
            "content_complete",
            "complete",
            "no_content_change",
        )
    elif all(state == "before" for state in all_states):
        status, publication, code = (
            "incomplete",
            "not_published",
            "intent_not_published",
        )
    elif all(state == "after" for state in all_states):
        status, publication, code = (
            "content_complete",
            "complete",
            "content_without_receipt",
        )
    else:
        status, publication, code = "incomplete", "partial", "partial_publication"
    return _outcome(
        "cancelled" if stopped is not None and status != "unknown" else status,
        "cancelled_after_intent"
        if stopped is not None and status != "unknown"
        else code,
        start=start,
        operation_id=intent.operation_id,
        kind=intent.kind,
        direction=intent.direction,
        review_generation=review_generation,
        generation=intent.generation,
        phase="publication",
        publication=publication,
        history="result" if retained_result is not None else "intent",
        planned=len(intent.affected_paths),
        published=states.count("after"),
        changed=None if "unknown" in all_states else "after" in all_states,
        checkpoint=intent.prepared_commit,
        intent=intent_commit,
        result=retained_result,
        stop=commit if stopped is not None else None,
        recovery=True,
    )


def _inspect_without_operations(root, git, *, trusted_association, owners, start):
    from .unpublished_collection import unpublished_outcome

    linked_intents = []
    checkpoint = _read(
        root,
        git,
        linked_intents=linked_intents,
        trusted_association=trusted_association,
        ownership_demands_out=[],
        _owners=owners,
    )
    if linked_intents:
        return _outcome(
            "unknown",
            "operation_record_missing",
            start=start,
            publication="unknown",
            history="unknown",
            changed=None,
            recovery=True,
        )
    return unpublished_outcome(git, checkpoint, start) or _outcome(
        "refused", "operation_absent", start=start
    )


def _inspect_update_status(
    vault, *, observations, trusted_association=None, _owners=None
):
    """Discover the latest owned intent independently of the current locator."""
    start = time.monotonic()
    root = Path(vault).absolute()
    from .unpublished_collection import unpublished_outcome

    try:
        git = _Git(root)
        operations = _operation_refs(git)
        if not operations:
            return _inspect_without_operations(
                root,
                git,
                trusted_association=trusted_association,
                owners=_owners,
                start=start,
            )
        records, graphs = _ordered_operation_graphs(git, operations)
        targets, origins = _operation_checkpoints(git, graphs, records)
        linked_intents = []
        checkpoint_roles = []
        ownership_demands = []
        checkpoint, owned = _read(
            root,
            git,
            targets=targets,
            linked_intents=linked_intents,
            checkpoint_roles=checkpoint_roles,
            trusted_association=trusted_association,
            ownership_demands_out=ownership_demands,
            _owners=_owners,
        )
        rooted_intents = {commit for graph in graphs for commit, _ in graph.authorities}
        if len(linked_intents) != len(set(linked_intents)) or not set(
            linked_intents
        ).issubset(rooted_intents):
            raise OSError(
                "Application result has a missing or duplicate operation root"
            )
        active_undo_target = _validate_retained_operations(
            graphs, checkpoint, owned, checkpoint_roles, origins
        )
        _, intent, receipt, stopped, commit = records[-1]
        active_graph = next(graph for graph in graphs if graph.commit == commit)
        observation = _OperationObservation(
            active_graph,
            checkpoint,
            owned,
            graphs=tuple(graphs),
            checkpoint_roles=tuple(checkpoint_roles),
            origin_undo_target=active_undo_target,
        )
        unpublished_prepared = (
            receipt is None
            and checkpoint.status == "valid"
            and checkpoint.manifest.boundary == "prepared"
            and checkpoint.locator.commit != intent.prepared_commit
            and _unpublished_recovery_matches(
                active_graph,
                checkpoint,
                owned,
                origins,
                origin_undo_target=observation.origin_undo_target,
            )
        )
        if unpublished_prepared:
            observation = observation._replace(
                unpublished_prepared=checkpoint.locator.commit
            )
        if ownership_demands:
            from .attachment_ownership import validate_history_claims

            for association, roles, demands in ownership_demands:
                validate_history_claims(
                    git,
                    association=association,
                    roles=roles,
                    demands=demands,
                    observation=observation,
                )
        orphan = unpublished_outcome(git, checkpoint, start, previous=active_graph)
        if orphan is not None:
            return orphan
        observations.append(observation)
        review_generation = (
            intent.review_generation
            if isinstance(intent, VaultRecoveryIntent)
            else None
        )
        checkpoint_outcome = _observe_operation_checkpoint(
            observation, unpublished_prepared, observations, start, review_generation
        )
        if checkpoint_outcome is not None:
            return checkpoint_outcome
        manifest = checkpoint.manifest
        retained_result = (
            checkpoint.locator.commit
            if receipt is None
            and manifest.boundary == "result"
            and manifest.association_id == intent.association_id
            and manifest.generation == intent.generation + 1
            and manifest.previous == intent.prepared_commit
            and manifest.preimage == intent.before
            and manifest.proposed == intent.proposed
            and manifest.vault == intent.proposed
            and manifest.operation_intent_commit == active_graph.intent_commit
            else None
        )
        if receipt is not None:
            return _terminal_operation_status(
                root, git, checkpoint, intent, receipt, commit, start, review_generation
            )
        observed = _unfinished_operation_status(
            root,
            intent,
            active_graph.intent_commit,
            commit,
            stopped,
            retained_result,
            start,
            review_generation,
        )
        from .collection_result_locator import with_result_locator_status

        return with_result_locator_status(root, checkpoint, observed, retained_result)
    except OSError, ValueError, TypeError, UnicodeError, IndexError:
        return _outcome(
            "unknown",
            "operation_history_invalid",
            start=start,
            publication="unknown",
            history="unknown",
            changed=None,
            recovery=True,
        )


def read_update_details(vault, *, offset=0, limit=100, expected=None):
    """Page only validated owned before/result comparison facts, never bytes."""
    with ExitStack() as owners:
        return _read_update_details(
            vault, offset=offset, limit=limit, expected=expected, _owners=owners
        )


def _detail_authority_changed(expected, observed):
    fields = (
        "operation_id",
        "intent_commit",
        "generation",
        "kind",
        "direction",
        "review_generation",
        "checkpoint_commit",
    )
    return any(
        getattr(expected, field) != getattr(observed, field) for field in fields
    ) or any(
        getattr(expected, field) is None
        for field in fields
        if field != "review_generation"
    )


def _update_detail_page(
    offset, limit, status, code, operation_id=None, total=0, items=(), *, binding=None
):
    next_offset = offset + len(items) if offset + len(items) < total else None
    return VaultUpdateDetailPage(
        schema_id="brz2obsidian.vault-update-detail-page",
        schema_version=1,
        status=status,
        code=code,
        operation_id=operation_id,
        intent_commit=None if binding is None else binding.intent_commit,
        generation=None if binding is None else binding.generation,
        kind=None if binding is None else binding.kind,
        direction=None if binding is None else binding.direction,
        review_generation=None if binding is None else binding.review_generation,
        offset=offset,
        limit=limit,
        total=total,
        items=tuple(items),
        next_offset=next_offset,
    )


def _read_update_details(vault, *, offset, limit, expected, _owners):
    if (
        type(offset) is not int
        or offset < 0
        or type(limit) is not int
        or not 1 <= limit <= 100
    ):
        raise ValueError("Detail offset or limit is outside the bounded page")

    page = partial(_update_detail_page, offset, limit)

    observed, observation = _inspect_update_observation(vault, _owners=_owners)
    if observed.status in ("unknown", "refused") or observed.intent_commit is None:
        return page("unavailable", "operation_authority_unavailable")
    if expected is not None:
        try:
            expected = VaultApplyResult.model_validate(expected)
        except ValueError, TypeError:
            return page("unavailable", "operation_authority_unavailable")
        if _detail_authority_changed(expected, observed):
            return page("unavailable", "operation_authority_changed")
    try:
        if observation is None:
            return page("unavailable", "operation_authority_unavailable")
        intent = observation.graph.intent
        if (
            intent.operation_id != observed.operation_id
            or intent.generation != observed.generation
            or intent.prepared_commit != observed.checkpoint_commit
            or intent.kind != observed.kind
            or intent.direction != observed.direction
        ):
            return page("unavailable", "operation_authority_changed")
        before = {row.path: row for row in intent.before}
        after = {row.path: row for row in intent.proposed}
        paths = sorted(before.keys() | after.keys())
        items = []
        for path in paths[offset : offset + limit]:
            old, new = before.get(path), after.get(path)
            items.append(
                VaultComparisonDetail(
                    path=path,
                    before_size=old.size if old is not None else None,
                    before_sha256=old.sha256 if old is not None else None,
                    after_size=new.size if new is not None else None,
                    after_sha256=new.sha256 if new is not None else None,
                )
            )
        return page(
            "available",
            "validated",
            intent.operation_id,
            len(paths),
            items,
            binding=observed,
        )
    except OSError, ValueError, TypeError, UnicodeError, IndexError:
        return page("unavailable", "operation_authority_unavailable")


def _same_file(root, row):
    path = root / row.path
    if not os.path.lexists(path):
        return False
    info, digest, _, _ = observe_file(root, path)
    mode = "100755" if info.st_mode & 0o111 else "100644"
    return (mode, info.st_size, digest) == (row.mode, row.size, row.sha256)


def _review_fact_paths_match(facts, current, incoming):
    """Use the same exact S1 fact locators for live and retained inventories."""
    identified = {
        (item.identity.item_id, item.facet)
        for item in facts.identity_inventory
        if item.identity_state == "valid" and item.identity is not None
    }
    for subject in facts.subjects:
        if not incoming(subject.path, subject.incoming):
            return False
        # S1's valid imported identity inventory supplies the actual authored
        # locator. During a reviewed rename the subject still names its source
        # target, which may no longer be present in the vault.
        if (subject.item_id, subject.facet) in identified:
            continue
        if subject.current.existence == "unknown" or not current(
            subject.current.path, subject.current.content
        ):
            return False
    for item in facts.identity_inventory:
        if item.current.existence == "unknown" or not current(
            item.current.path, item.current.content
        ):
            return False
    if facts.link_context is not None:
        for document in facts.link_context.current_documents:
            if not current(document.source_path, document.content):
                return False
    return True


def _review_inputs_match(review, admission, source):
    """Bind reviewed current and incoming bytes to observed outer files."""
    inventory = {row.path: row for row in admission.inventory}

    def current(path, expected):
        if not _safe_relative(path):
            return False
        row = inventory.get(path)
        if expected is None:
            return row is None
        return (
            row is not None
            and row.size == content_size(expected)
            and row.sha256 == content_sha(expected)
        )

    def incoming(path, expected):
        if not _safe_relative(path):
            return False
        target = source / path
        if expected is None:
            return not os.path.lexists(target)
        if not os.path.lexists(target):
            return False
        info, sha, _, _ = observe_file(source, target, prefix_limit=0)
        return info.st_size == content_size(expected) and sha == content_sha(expected)

    return _review_fact_paths_match(review.producer_facts, current, incoming)


class _NativeExecutor:
    def move(self, stage, target, *, replace):
        move_file(stage, target, replace=replace)

    def remove(self, target, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        move_file(target, destination, replace=False)

    def directory(self, stage, target):
        move_file(stage, target, replace=False)


def _prepare_parents(root, stage_root, paths):
    prepared = {}
    for path in sorted(paths):
        destination = (root / path).parent
        while destination != root:
            if os.path.lexists(destination):
                verify_directory(destination)
            else:
                relative = destination.relative_to(root)
                if relative not in prepared:
                    staged = stage_root / relative.parent / ("parent-" + uuid4().hex)
                    staged.mkdir()
                    stage_directory_security(stage_root / relative, staged)
                    prepared[relative] = staged
            destination = destination.parent
    return prepared


def _ensure_parents(root, target, prepared, expected, executor):
    missing = []
    parent = target.parent
    while parent != root and not os.path.lexists(parent):
        missing.append(parent.relative_to(root))
        parent = parent.parent
    verify_directory(parent)
    for relative in reversed(missing):
        destination = root / relative
        if os.path.lexists(destination):
            raise OSError("New authored parent became occupied")
        staged = prepared[relative]
        executor.directory(staged, destination)
        if retained_directory_metadata(destination) != expected[relative]:
            raise OSError("Published parent metadata changed")


def _flush_stage(path):
    with path.open("r+b") as stream:
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def _proposed_directory(parent):
    """Create a naturally inheriting same-volume stage beside the vault."""
    parent = Path(parent).resolve(strict=True)
    path = parent / ("brz2obsidian-proposed-" + uuid4().hex)
    path.mkdir()
    try:
        yield path
    finally:
        if path.is_symlink() or path.resolve(strict=True).parent != parent:
            raise OSError("Staging cleanup target changed")
        shutil.rmtree(path)


def _metadata_matches(root, path, expected):
    if expected is None:
        return not os.path.lexists(root / path)
    return retained_metadata(root / path) == (
        expected.mode,
        expected.attributes,
        expected.security,
    )


def _directory_states(root, intent):
    states = []
    for expected in intent.created_directories:
        path = root / expected.path
        if not os.path.lexists(path):
            states.append("before")
        elif path.is_dir() and retained_directory_metadata(path) == (
            expected.mode,
            expected.attributes,
            expected.security,
        ):
            states.append("after")
        else:
            states.append("unknown")
    return states


def _outcome(
    status,
    code,
    *,
    start,
    operation_id=None,
    kind="apply",
    direction=None,
    review_generation=None,
    generation=None,
    phase="admission",
    publication="not_started",
    history="none",
    planned=0,
    published=0,
    changed=False,
    checkpoint=None,
    intent=None,
    result=None,
    receipt=None,
    stop=None,
    recovery=False,
    message="Existing-vault operation requires inspection.",
):
    return VaultApplyResult(
        schema_id="brz2obsidian.vault-apply-result",
        schema_version=1,
        status=status,
        code=code,
        operation_id=operation_id,
        kind=kind,
        direction=direction,
        review_generation=review_generation,
        generation=generation,
        phase=phase,
        publication=publication,
        history=history,
        planned_files=planned,
        published_files=published,
        authored_files_changed=changed,
        checkpoint_commit=checkpoint,
        intent_commit=intent,
        result_commit=result,
        receipt_commit=receipt,
        stop_commit=stop,
        recovery_required=recovery,
        elapsed_ms=max(0, int((time.monotonic() - start) * 1000)),
        message=message,
    )


class _OwnedCleanupFailure(Exception):
    def __init__(self, result):
        self.result = result


@dataclass
class _ApplyProgress:
    scoped: bool = False
    """Track transitions that determine failure reporting and lease cleanup."""

    phase: str = "admission"
    prepared_commit: str | None = None
    intent_commit: str | None = None
    result_commit: str | None = None
    receipt_commit: str | None = None
    published: int = 0
    planned: int = 0
    operation_generation: int | None = None
    acquired: bool = False
    failure_code: str = "apply_unavailable"


def _apply_source_binding(source, source_binding, review, undo_target, outcome, start):
    from brz2obsidian.application.source_payload_contracts import ReviewedSourceBinding
    from brz2obsidian.publication.source_payload import observe_reviewed_source

    try:
        if undo_target is not None:
            binding = None
        elif source_binding is None:
            return outcome("refused", "source_binding_required", start=start)
        else:
            binding = ReviewedSourceBinding.model_validate(source_binding)
        if binding is not None and (
            binding.proposal_id != review.proposal.proposal_id
            or binding.generation != review.proposal.generation
            or binding.incoming_identity != review.facts.incoming_identity
            or binding.target_source_version
            != review.facts.format_operation.target_source_version
        ):
            return outcome("refused", "source_binding_mismatch", start=start)
        if binding is not None and observe_reviewed_source(source, review) != binding:
            return outcome("refused", "source_payload_changed", start=start)
    except OSError, ValueError, TypeError, UnicodeError:
        return outcome("refused", "source_payload_unavailable", start=start)
    return binding


def _observe_apply_inputs(
    root, subjects, purpose, undo_target, retained_history, _owned_export, _owners
):
    format_parent = None
    if undo_target is None:
        inspections = []
        reviewed_observation = _inspect_history(
            root,
            **purpose,
            _capture=lambda inspection, admission: inspections.append(inspection),
            _metadata_only=_owned_export is not None,
            _owners=_owners,
        )
        inspected = inspections[0] if inspections else None
        if (
            inspected is not None
            and inspected.recovery_status is not None
            and inspected.recovery_observation is not None
        ):
            retained_history = (
                inspected.recovery_status,
                inspected.recovery_observation,
            )
        first = _inspect_history(
            root,
            subjects=subjects,
            **purpose,
            recovery_observation=retained_history[1] if retained_history else None,
            _metadata_only=_owned_export is not None,
            _owners=_owners,
        )
        if (
            purpose
            and inspected is not None
            and reviewed_observation.status == "intact"
        ):
            format_parent = inspected._format_prepared_parent()
    else:
        from brz2obsidian.application.checkpoint_contracts import (
            VaultHistoryInspection,
        )
        from brz2obsidian.publication.vault_admission import (
            _inspect_vault_for_recovery,
        )

        checkpoint = undo_target.observation.checkpoint
        admission = _inspect_vault_for_recovery(
            root, undo_target.observation, subjects=subjects
        )
        first = (
            _MetadataHistory(admission, checkpoint)
            if type(checkpoint) is _MetadataCheckpoint
            else VaultHistoryInspection(
                schema_id="brz2obsidian.vault-history-inspection",
                schema_version=1,
                status="intact",
                checkpoint=checkpoint,
                admission=admission,
            )
        )
        reviewed_observation = first
    return first, reviewed_observation, format_parent, retained_history


def _apply_admission_refusal(
    source,
    review,
    first,
    reviewed_observation,
    undo_target,
    format_parent,
    vault_id,
    import_id,
):
    scoped_preflight = first.admission.preflight
    if undo_target is not None:
        from brz2obsidian.publication.vault_recovery import _review_preflight

        scoped_preflight = _review_preflight(
            first.admission,
            undo_target.observation.owned[undo_target.intent.prepared_commit][0],
            undo_target.plan,
            undo_target.observation,
        )
    matched_review_query = (
        review.preflight == scoped_preflight
        if scoped_preflight.consents
        else review.preflight
        in (
            reviewed_observation.admission.preflight,
            scoped_preflight,
        )
    )
    if reviewed_observation.status != "intact" or not matched_review_query:
        return "current_review_required"
    if first.status != "intact" or first.admission.status != "supported":
        return "scoped_admission_required"
    pending = first.checkpoint.manifest
    if (
        pending.boundary == "local"
        and pending.reviewed_source is not None
        and pending.reviewed_source.proposal_id != review.proposal.proposal_id
        and (
            pending.collection_record_path is not None
            or pending.collection_baseline_commit is not None
        )
    ):
        return "saved_review_pending"
    baseline_identity = (
        format_parent.identity
        if format_parent is not None
        else first.checkpoint.manifest.identity
    )
    if (
        first.checkpoint.locator.commit
        != reviewed_observation.checkpoint.locator.commit
        or first.checkpoint.locator.association.vault_id != vault_id
        or first.checkpoint.locator.association.import_id != import_id
        or baseline_identity != review.facts.baseline_identity
        and undo_target is None
    ):
        return "current_review_required"
    if undo_target is not None:
        if (
            first.checkpoint.locator.commit
            != undo_target.observation.checkpoint.locator.commit
        ):
            return "undo_review_stale"
    elif not _review_inputs_match(review, first.admission, source):
        return "review_inputs_changed"
    return None


def _observe_apply_under_lease(
    root,
    subjects,
    retained_history,
    operation_id,
    purpose,
    _owned_export,
    _owners,
):
    observed = (
        (
            inspect_history(
                root, subjects=subjects, active_operation=operation_id, **purpose
            )
            if _owned_export is None
            else _inspect_history(
                root,
                subjects=subjects,
                active_operation=operation_id,
                **purpose,
                _metadata_only=True,
                _owners=_owners,
            )
        )
        if retained_history is None
        else _inspect_retained_history(
            root,
            retained_history[1],
            subjects=subjects,
            active_operation=operation_id,
        )
    )
    return observed


def _apply_path_plan(observed, review, selected, subjects, undo_target, outcome, start):
    accepted_tracking = {
        subject_id
        for requirement in observed.admission.preflight.consents
        if requirement.kind == "tracking"
        and any(
            decision.consent_id == requirement.consent_id
            and decision.kind == requirement.kind
            and decision.choice == "accept"
            for decision in review.consents
        )
        for subject_id in requirement.subjects
    }
    included_paths = {
        subject.path for subject in subjects if subject.subject_id in accepted_tracking
    }
    before = {
        row.path: row
        for row in observed.admission.inventory
        if not row.excluded or row.path in included_paths
    }
    selected_files = {row.path: row.content for row in selected.files}
    selected_rows = {row.path: row for row in selected.files}
    removals = set(selected.remove_paths)
    if any(not _safe_relative(path) for path in (*selected_files, *removals)):
        return outcome("refused", "unsafe_selected_path", start=start)
    if any(path not in before for path in removals):
        return outcome("refused", "selected_removal_missing", start=start)
    changed = {
        path
        for path, data in selected_files.items()
        if path not in before
        or before[path].size != content_size(data)
        or before[path].sha256 != content_sha(data)
    } | removals
    if undo_target is not None and not changed.issubset(
        undo_target.intent.affected_paths
    ):
        return outcome("refused", "undo_effect_outside_origin", start=start)
    return before, selected_files, selected_rows, removals, changed


def _stage_apply_selected(
    root, proposed_root, before, selected_files, selected_rows, changed, _owned_export
):
    result_metadata = {}
    for path, data in selected_files.items():
        target = proposed_root / path
        stage_parent_security(root, proposed_root, Path(path).parent)
        with target.open("wb") as stream:
            if _owned_export is None:
                stream.write(data.data)
            else:
                _owned_export.stage(selected_rows[path], stream)
            stream.flush()
            os.fsync(stream.fileno())
        if _owned_export is not None:
            info, digest, _, _ = observe_file(proposed_root, target, prefix_limit=0)
            if info.st_size != content_size(data) or digest != content_sha(data):
                raise OSError("Selected staged bytes changed")
        if path in before:
            shutil.copymode(root / path, target)
        if path in changed:
            if path in before:
                retained_metadata(root / path, copy_to=target)
            result_metadata[path] = retained_metadata(target)
            _flush_stage(target)
    return result_metadata


def _stage_apply_files(
    root,
    proposed_root,
    before,
    selected_files,
    selected_rows,
    removals,
    changed,
    _owned_export,
):
    before_metadata = {}
    for path, row in before.items():
        if path in removals:
            continue
        target = proposed_root / path
        stage_parent_security(root, proposed_root, Path(path).parent)
        if not _same_file(root, row):
            return None
        if path in changed:
            before_metadata[path] = retained_metadata(root / path)
        if path in changed:
            copy_stage(root / path, target)
        else:
            shutil.copy2(root / path, target)
    result_metadata = _stage_apply_selected(
        root,
        proposed_root,
        before,
        selected_files,
        selected_rows,
        changed,
        _owned_export,
    )
    for path in removals:
        before_metadata[path] = retained_metadata(root / path)
    prepared_parents = _prepare_parents(
        root,
        proposed_root,
        (path for path in changed if path in selected_files),
    )
    prepared_parent_metadata = {
        path: retained_directory_metadata(stage)
        for path, stage in prepared_parents.items()
    }
    return before_metadata, result_metadata, prepared_parents, prepared_parent_metadata


def _retain_apply_preparation(publication, observed, proposed_root, state):
    state.phase = "prepared"
    prepared = capture_checkpoint(
        publication.root,
        publication.source,
        vault_id=publication.vault_id,
        import_id=publication.import_id,
        identity=publication.review.facts.incoming_identity,
        admission=observed.admission,
        review=publication.review,
        boundary="prepared",
        proposed=proposed_root,
        active_operation=publication.operation_id,
        subjects=publication.subjects,
        source_binding=publication.binding,
        observed_source=publication.observed_source,
        undo_of_receipt_commit=(
            publication.undo_target.receipt_commit if publication.undo_target else None
        ),
        _observation=publication.retained_history,
        _owned_export=publication.owned_export,
        _owners=publication.owners,
        progress=publication.progress,
    )
    reused_undo_prepared = (
        publication.undo_target is not None
        and prepared.status == "unchanged"
        and prepared.code == "already_retained"
        and prepared.history_retained
        and prepared.commit == publication.undo_target.observation.unpublished_prepared
    )
    reused_format_prepared = (
        publication.format_parent is not None
        and prepared.status == "unchanged"
        and prepared.code == "already_retained"
        and prepared.history_retained
        and prepared.locator == observed.checkpoint.locator
    )
    if prepared.status != "captured" and not (
        reused_undo_prepared or reused_format_prepared
    ):
        if state.scoped and prepared.history_retained:
            state.prepared_commit = prepared.commit
        return publication.outcome(
            "refused" if prepared.status == "refused" else "failed",
            "prepare_" + prepared.code,
            start=publication.start,
            operation_id=publication.operation_id,
            generation=state.operation_generation,
            phase=state.phase,
            history="prepared" if prepared.history_retained else "none",
            checkpoint=prepared.commit,
            recovery=state.scoped and prepared.history_retained,
        )
    state.prepared_commit = prepared.commit
    if reused_undo_prepared or reused_format_prepared:
        state.operation_generation = prepared.locator.generation
    return None


def _rediscover_prepared_apply(
    root, subjects, operation_id, cancel_requested, _owned_export, _owners
):
    cancelled = cancel_requested()
    if not cancelled:
        if type(_owners) is _ApplyReviewOwners:
            _owners._read_cancelled = False
        tip = (
            inspect_history(root, subjects=subjects, active_operation=operation_id)
            if _owned_export is None
            else _inspect_history(
                root,
                subjects=subjects,
                active_operation=operation_id,
                _metadata_only=True,
                _owners=_owners,
            )
        )
        cancelled = type(_owners) is _ApplyReviewOwners and _owners._read_cancelled
        if not cancelled and (
            tip.status != "intact"
            or tip.checkpoint is None
            or tip.checkpoint.manifest.boundary != "prepared"
        ):
            raise OSError("Prepared checkpoint could not be rediscovered")
        cancelled = cancelled or cancel_requested()
    return None if cancelled else tip


def _retain_apply_intent(
    root,
    state,
    manifest,
    operation_id,
    kind,
    changed,
    before,
    before_metadata,
    result_metadata,
    prepared_parent_metadata,
    undo_target,
):
    intent = VaultOperationIntent(
        schema_id="brz2obsidian.vault-operation-intent",
        schema_version=1,
        operation_id=operation_id,
        kind=kind,
        generation=manifest.generation,
        direction="finish",
        undo_of_receipt_commit=(undo_target.receipt_commit if undo_target else None),
        association_id=manifest.association_id,
        prepared_commit=state.prepared_commit,
        before=manifest.preimage,
        proposed=manifest.proposed,
        affected_paths=tuple(sorted(changed)),
        protected_paths=tuple(sorted(set(before) - changed)),
        before_metadata=tuple(
            VaultPathMetadata(
                path=path, mode=value[0], attributes=value[1], security=value[2]
            )
            for path, value in sorted(before_metadata.items())
        ),
        result_metadata=tuple(
            VaultPathMetadata(
                path=path, mode=value[0], attributes=value[1], security=value[2]
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
                prepared_parent_metadata.items(),
                key=lambda item: item[0].as_posix(),
            )
        ),
    )
    git = _Git(root)
    op_ref = (
        "refs/brz2obsidian/imports/"
        + manifest.association_id
        + "/operations/"
        + operation_id
    )
    state.phase = "intent"
    state.intent_commit = _journal(
        git, "intent.json", intent, parents=(state.prepared_commit,), ref=op_ref
    )
    return git, op_ref


def _move_apply_file(
    root,
    proposed_root,
    prior,
    proposed,
    path,
    executor,
    prepared_parents,
    prepared_parent_metadata,
    result_metadata,
):
    target = root / path
    old = prior.get(path)
    new = proposed.get(path)
    if old is None:
        if os.path.lexists(target):
            raise OSError("Selected creation path became occupied")
    elif not _same_file(root, old):
        raise OSError("Selected current bytes changed before transition")
    if new is None:
        destination = proposed_root / (
            "removed-" + hashlib.sha256(path.encode()).hexdigest()
        )
        executor.remove(target, destination)
    else:
        stage = proposed_root / path
        if not _same_file(proposed_root, new):
            raise OSError("Prepared staged bytes changed")
        _ensure_parents(
            root,
            target,
            prepared_parents,
            prepared_parent_metadata,
            executor,
        )
        executor.move(stage, target, replace=old is not None)
        metadata = result_metadata[path]
        if not _same_file(root, new) or retained_metadata(target) != metadata:
            raise OSError("Published bytes did not match prepared result")


def _publish_apply_files(
    publication,
    proposed_root,
    state,
    manifest,
    changed,
    prepared_parents,
    prepared_parent_metadata,
    result_metadata,
    git,
    op_ref,
):
    from brz2obsidian.application.vault_progress_contracts import report_progress

    state.phase = "publication"
    report_progress(
        publication.progress,
        "publication",
        operation_id=publication.operation_id,
        operation_generation=state.operation_generation,
        intent_commit=state.intent_commit,
        completed_units=state.published,
        total_units=len(changed),
        unit="files",
    )
    proposed = {row.path: row for row in manifest.proposed}
    prior = {row.path: row for row in manifest.preimage}
    for path in sorted(changed):
        if publication.cancel_requested():
            stopped = VaultOperationStop(
                schema_id="brz2obsidian.vault-operation-stop",
                schema_version=1,
                operation_id=publication.operation_id,
                kind=publication.kind,
                generation=manifest.generation,
                direction="finish",
                status="cancelled",
                intent_commit=state.intent_commit,
                acknowledged_after_files=state.published,
            )
            stop_commit = _journal(
                git,
                "stop.json",
                stopped,
                parents=(state.intent_commit,),
                previous=state.intent_commit,
                ref=op_ref,
            )
            return publication.outcome(
                "cancelled",
                "cancelled_after_intent",
                start=publication.start,
                operation_id=publication.operation_id,
                generation=state.operation_generation,
                phase="publication",
                publication="partial" if state.published else "not_published",
                history="intent",
                planned=len(changed),
                published=state.published,
                changed=bool(state.published),
                checkpoint=state.prepared_commit,
                intent=state.intent_commit,
                stop=stop_commit,
                recovery=True,
                message="Cancellation stopped at a recoverable file boundary.",
            )
        _move_apply_file(
            publication.root,
            proposed_root,
            prior,
            proposed,
            path,
            publication.executor,
            prepared_parents,
            prepared_parent_metadata,
            result_metadata,
        )
        state.published += 1
        report_progress(
            publication.progress,
            "publication",
            operation_id=publication.operation_id,
            operation_generation=state.operation_generation,
            intent_commit=state.intent_commit,
            completed_units=state.published,
            total_units=len(changed),
            unit="files",
        )
    report_progress(
        publication.progress,
        "final_verification",
        operation_id=publication.operation_id,
        operation_generation=state.operation_generation,
        intent_commit=state.intent_commit,
    )
    for path, row in proposed.items():
        if not _same_file(publication.root, row):
            raise OSError("Complete proposed inventory disagrees")
    if any(
        os.path.lexists(publication.root / path) for path in set(prior) - set(proposed)
    ):
        raise OSError("Removed path remains visible")
    return None


def _retain_apply_completion(publication, state, manifest, changed, git, op_ref):
    from brz2obsidian.application.vault_progress_contracts import report_progress

    state.phase = "result"
    report_progress(
        publication.progress,
        "final_reporting",
        operation_id=publication.operation_id,
        operation_generation=state.operation_generation,
        intent_commit=state.intent_commit,
    )
    result_observation = _inspect_update_observation(
        publication.root, _owners=publication.owners
    )
    authority = result_observation[1]
    if (
        authority is None
        or result_observation[0].operation_id != publication.operation_id
        or result_observation[0].intent_commit != state.intent_commit
        or authority.graph.intent.prepared_commit != state.prepared_commit
    ):
        raise OSError("Actual result operation observation changed")
    current = _inspect_retained_history(
        publication.root,
        authority,
        subjects=publication.subjects,
        active_operation=publication.operation_id,
    )
    result_checkpoint = capture_checkpoint(
        publication.root,
        publication.source,
        vault_id=publication.vault_id,
        import_id=publication.import_id,
        identity=publication.review.facts.incoming_identity,
        admission=current.admission,
        boundary="result",
        expected_prepared=state.prepared_commit,
        active_operation=publication.operation_id,
        operation_intent_commit=state.intent_commit,
        subjects=publication.subjects,
        _observation=result_observation,
        _owned_export=publication.owned_export,
        _owners=publication.owners,
        progress=publication.progress,
    )
    if result_checkpoint.status != "captured":
        state.failure_code = "result_" + result_checkpoint.code
        raise OSError("Actual result checkpoint could not be retained")
    state.result_commit = result_checkpoint.commit
    receipt = VaultOperationReceipt(
        schema_id="brz2obsidian.vault-operation-receipt",
        schema_version=1,
        operation_id=publication.operation_id,
        kind=publication.kind,
        generation=manifest.generation,
        status="undone"
        if publication.undo_target
        else "applied"
        if changed
        else "no_content_change",
        direction="finish",
        intent_commit=state.intent_commit,
        prepared_commit=state.prepared_commit,
        result_commit=state.result_commit,
        published_paths=tuple(sorted(changed)),
    )
    state.phase = "terminal"
    state.receipt_commit = _journal(
        git,
        "receipt.json",
        receipt,
        parents=(state.intent_commit, state.result_commit),
        previous=state.intent_commit,
        ref=op_ref,
    )


def _report_apply_failure(root, operation_id, state, outcome, start):
    observed_failure = (
        inspect_update_status(root)
        if state.phase in ("intent", "publication", "result", "terminal")
        else None
    )
    if (
        observed_failure is not None
        and observed_failure.operation_id == operation_id
        and observed_failure.intent_commit is not None
    ):
        state.intent_commit = observed_failure.intent_commit
        if observed_failure.status in (
            "applied",
            "no_content_change",
            "undone",
            "restored",
        ):
            return outcome(
                "content_complete",
                "terminal_reporting_failed",
                start=start,
                operation_id=operation_id,
                generation=state.operation_generation,
                phase="terminal",
                publication="complete",
                history="terminal",
                planned=state.planned,
                published=observed_failure.published_files,
                changed=observed_failure.authored_files_changed,
                checkpoint=state.prepared_commit,
                intent=state.intent_commit,
                result=observed_failure.result_commit,
                receipt=observed_failure.receipt_commit,
                recovery=False,
                message="Exact content and receipt are complete; final reporting failed.",
            )
        return outcome(
            observed_failure.status,
            state.failure_code + "_" + observed_failure.code,
            start=start,
            operation_id=operation_id,
            generation=state.operation_generation,
            phase=state.phase,
            publication=observed_failure.publication,
            history=(
                "result"
                if state.result_commit is not None
                and observed_failure.status == "content_complete"
                else observed_failure.history
            ),
            planned=state.planned,
            published=observed_failure.published_files,
            changed=observed_failure.authored_files_changed,
            checkpoint=state.prepared_commit,
            intent=state.intent_commit,
            result=observed_failure.result_commit or state.result_commit,
            receipt=observed_failure.receipt_commit,
            stop=observed_failure.stop_commit,
            recovery=True,
        )
    if (
        state.phase == "intent"
        and not state.scoped
        and state.intent_commit is None
        and state.prepared_commit is not None
        and state.published == 0
        and observed_failure is not None
        and observed_failure.code == "operation_absent"
    ):
        return outcome(
            "failed",
            "intent_ref_unavailable",
            start=start,
            operation_id=operation_id,
            generation=state.operation_generation,
            phase="prepared",
            publication="not_published",
            history="prepared",
            planned=state.planned,
            published=0,
            changed=False,
            checkpoint=state.prepared_commit,
            recovery=False,
            message=(
                "Git could not record the operation ref. The review was retained. "
                "Check write access and path length for Git, then resume the review."
            ),
        )
    if (
        state.scoped
        and state.prepared_commit is not None
        and state.intent_commit is None
        and state.phase == "prepared"
    ):
        return outcome(
            "incomplete",
            "scoped_preparation_retained",
            start=start,
            operation_id=operation_id,
            generation=state.operation_generation,
            phase="prepared",
            publication="not_published",
            history="prepared",
            planned=state.planned,
            published=0,
            changed=False,
            checkpoint=state.prepared_commit,
            recovery=True,
        )
    authority_unknown = state.phase == "intent" and state.intent_commit is None
    cleanup_pending = not state.acquired and _lock_path(root).exists()
    publication_unknown = state.intent_commit is not None
    return outcome(
        "content_complete"
        if state.result_commit is not None
        else "unknown"
        if authority_unknown or publication_unknown or cleanup_pending
        else "failed",
        "owned_acquire_failed" if cleanup_pending else state.failure_code,
        start=start,
        operation_id=operation_id if state.acquired or cleanup_pending else None,
        generation=state.operation_generation,
        phase=state.phase,
        publication="complete"
        if state.result_commit is not None
        else "unknown"
        if publication_unknown
        else "not_published"
        if authority_unknown
        else "not_started",
        history="unknown"
        if authority_unknown
        else "result"
        if state.result_commit
        else "intent"
        if state.intent_commit
        else "prepared"
        if state.prepared_commit
        else "none",
        planned=state.planned,
        published=state.published,
        changed=True
        if state.result_commit is not None and state.planned
        else None
        if publication_unknown
        else False,
        checkpoint=state.prepared_commit,
        intent=state.intent_commit,
        result=state.result_commit,
        receipt=state.receipt_commit,
        recovery=bool(state.intent_commit) or authority_unknown or cleanup_pending,
        message="Existing-vault operation requires exact recovery inspection.",
    )


def _release_apply_lease(root, operation_id, state, outcome, start):
    from .collection_publication import release_native_operation

    if state.acquired and (
        state.intent_commit is not None
        or state.scoped
        and state.prepared_commit is not None
    ):
        _park(root, operation_id)
    elif state.acquired:
        pending_exception = sys.exc_info()[0]
        try:
            release_native_operation(root, operation_id)
        except OSError, ValueError, TypeError:
            if pending_exception is None or issubclass(
                pending_exception, (OSError, ValueError, TypeError)
            ):
                raise _OwnedCleanupFailure(
                    outcome(
                        "unknown" if state.phase == "intent" else "incomplete",
                        "owned_cleanup_failed",
                        start=start,
                        operation_id=operation_id,
                        generation=state.operation_generation,
                        phase=state.phase,
                        publication="not_published"
                        if state.phase == "intent"
                        else "not_started",
                        history="unknown"
                        if state.phase == "intent"
                        else "prepared"
                        if state.prepared_commit is not None
                        else "none",
                        planned=state.planned,
                        published=0,
                        changed=False,
                        checkpoint=state.prepared_commit,
                        recovery=True,
                        message="Owned marker cleanup failed; inspect before another operation.",
                    )
                ) from None


def _selected_apply_effects(review, _owned_export):
    if _owned_export is not None:
        from brz2obsidian.application.review_session import _OwnedReviewExport

        if type(_owned_export) is not _OwnedReviewExport:
            raise OSError("Canonical publication owner required")
        _owned_export.check(review)
        selected = _owned_export.effects
        if _owned_export.session._selected is not selected:
            raise OSError("Current canonical selected effects required")
    else:
        selected = select_review_effects(review)
    return selected


class _StagedApplyInputs(NamedTuple):
    root: object
    source: object
    review: object
    vault_id: object
    import_id: object
    subjects: object
    binding: object
    observed_source: object
    undo_target: object
    retained_history: object
    owned_export: object
    owners: object
    progress: object
    format_parent: object
    executor: object
    cancel_requested: object
    operation_id: object
    kind: object
    outcome: object
    start: object


def _execute_staged_apply(name, publication, paths, observed, state):
    before, selected_files, selected_rows, removals, changed = paths
    proposed_root = Path(name)
    if proposed_root.stat().st_dev != publication.root.stat().st_dev:
        return publication.outcome(
            "refused", "same_volume_stage_required", start=publication.start
        )
    stage_parent_security(publication.root, proposed_root, Path("."))
    staged = _stage_apply_files(
        publication.root,
        proposed_root,
        before,
        selected_files,
        selected_rows,
        removals,
        changed,
        publication.owned_export,
    )
    if staged is None:
        return publication.outcome(
            "refused", "current_bytes_changed", start=publication.start
        )
    before_metadata, result_metadata, prepared_parents, prepared_parent_metadata = (
        staged
    )
    refused = _retain_apply_preparation(publication, observed, proposed_root, state)
    if refused is not None:
        return refused
    tip = _rediscover_prepared_apply(
        publication.root,
        publication.subjects,
        publication.operation_id,
        publication.cancel_requested,
        publication.owned_export,
        publication.owners,
    )
    if tip is None:
        from .collection_undo_publication import SCOPED_UNDO_PENDING

        code = (
            (
                SCOPED_UNDO_PENDING
                if publication.undo_target is not None
                else "unpublished_collection_prepared"
            )
            if state.scoped
            else "cancelled_before_intent"
        )
        return publication.outcome(
            "cancelled",
            code,
            start=publication.start,
            operation_id=publication.operation_id,
            generation=state.operation_generation,
            phase="prepared",
            publication="not_started",
            history="prepared",
            planned=len(changed),
            checkpoint=state.prepared_commit,
            recovery=state.scoped,
            message="Cancellation retained preparation without publishing files.",
        )
    manifest = tip.checkpoint.manifest
    state.operation_generation = manifest.generation
    git, op_ref = _retain_apply_intent(
        publication.root,
        state,
        manifest,
        publication.operation_id,
        publication.kind,
        changed,
        before,
        before_metadata,
        result_metadata,
        prepared_parent_metadata,
        publication.undo_target,
    )
    stopped = _publish_apply_files(
        publication,
        proposed_root,
        state,
        manifest,
        changed,
        prepared_parents,
        prepared_parent_metadata,
        result_metadata,
        git,
        op_ref,
    )
    if stopped is not None:
        return stopped
    _retain_apply_completion(publication, state, manifest, changed, git, op_ref)
    return None


def _completed_apply(root, operation_id, state, outcome, start, undo_target, changed):
    from .collection_publication import release_native_operation

    release_native_operation(root, operation_id)
    state.acquired = False
    return outcome(
        "undone" if undo_target else "applied" if changed else "no_content_change",
        "undone" if undo_target else "applied" if changed else "no_content_change",
        start=start,
        operation_id=operation_id,
        generation=state.operation_generation,
        phase="terminal",
        publication="complete",
        history="terminal",
        planned=len(changed),
        published=state.published,
        changed=bool(changed),
        checkpoint=state.prepared_commit,
        intent=state.intent_commit,
        result=state.result_commit,
        receipt=state.receipt_commit,
        recovery=False,
        message="Reviewed exact result and terminal receipt retained.",
    )


def _publish_staged_apply(publication, paths, observed, state):
    root = publication.root
    before, selected_files, _, removals, _ = paths
    # Observe the peak copy/overwrite footprint before creating the stage.
    # Checkpoint capture performs its separate spool and Git check afterward.
    stage_need = (
        sum(row.size for path, row in before.items() if path not in removals)
        + sum(content_size(data) for data in selected_files.values())
        + 64 * 1024 * 1024
        + 4096 * (len(before) + len(selected_files))
    )
    if shutil.disk_usage(root.parent).free < stage_need:
        return publication.outcome(
            "refused", "insufficient_stage_resources", start=publication.start
        )
    with _proposed_directory(root.parent) as name:
        return _execute_staged_apply(name, publication, paths, observed, state)


def _acquire_reviewed_apply(root, operation_id, checkpoint, undo_target):
    from .collection_publication import acquire_collection_apply, scoped_undo_target
    from .vault_history import _scoped_saved_checkpoint

    scoped = (
        _scoped_saved_checkpoint(checkpoint.manifest)
        if undo_target is None
        else scoped_undo_target(undo_target)
    )
    if scoped:
        acquire_collection_apply(
            root,
            operation_id,
            checkpoint.locator,
            undo_receipt=undo_target.receipt_commit
            if undo_target is not None
            else None,
        )
    else:
        _acquire(root, operation_id)
    return scoped


def _qualify_collection_apply(source, review, selected, observed):
    from .collection_placement import (
        collection_write_refusal,
        reviewed_connections,
        scoped_update_classification_refusal,
    )

    checkpoint = observed.checkpoint
    if review.facts.format_operation.kind == "source_update":
        return scoped_update_classification_refusal(
            observed.admission,
            checkpoint,
            source,
            checkpoint.manifest.collection_record_path,
            review,
        )
    if review.facts.format_operation.kind != "collection_import":
        return None
    retained = checkpoint.review
    if retained is None or checkpoint.manifest.boundary != "local":
        return "current_review_required"
    return collection_write_refusal(
        observed.admission,
        checkpoint,
        source,
        checkpoint.manifest.collection_record_path,
        review,
        choices=reviewed_connections(retained.saved.plan),
        selected=selected,
    )


def _held_apply_refusal(first, observed, source, review, selected, *, undo_target):
    if (
        observed.status != "intact"
        or observed.admission.status != "supported"
        or observed.admission.inventory != first.admission.inventory
        or observed.admission.policy_fingerprint != first.admission.policy_fingerprint
        or observed.checkpoint.locator.commit != first.checkpoint.locator.commit
    ):
        return "current_admission_required"
    if undo_target is not None:
        if (
            observed.checkpoint.locator.commit
            != undo_target.observation.checkpoint.locator.commit
        ):
            return "undo_review_stale"
        return None
    return _qualify_collection_apply(source, review, selected, observed)


def _apply_reviewed_update(
    vault,
    source,
    *,
    review,
    vault_id,
    import_id,
    source_binding=None,
    observed_source=None,
    cancel=None,
    progress=None,
    executor=None,
    undo_target=None,
    _owned_export=None,
    _owners=None,
):
    """Retain intent before exact selected publication and verify terminal history."""
    start = time.monotonic()
    from brz2obsidian.application.vault_progress_contracts import report_progress

    report_progress(progress, "review_validation")
    kind = "undo" if undo_target is not None else "apply"
    outcome = partial(_outcome, kind=kind, direction="finish" if undo_target else None)
    selected = _selected_apply_effects(review, _owned_export)
    if selected.status != "selected":
        return outcome("refused", selected.code, start=start)
    purpose = (
        {"new_operation": "format_transition"}
        if undo_target is None
        and review.facts.format_operation.kind == "format_transition"
        else {}
    )
    root, source = Path(vault).absolute(), Path(source).absolute()
    if not supported_durable_volume(root):
        return outcome("refused", "unsupported_durable_volume", start=start)
    binding = _apply_source_binding(
        source, source_binding, review, undo_target, outcome, start
    )
    if isinstance(binding, VaultApplyResult):
        return binding
    try:
        subjects = _review_subjects(review, selected)
    except ValueError, TypeError:
        return outcome("refused", "invalid_review_scope", start=start)
    operation_id = uuid4().hex
    state = _ApplyProgress()
    cancel_requested = cancel if cancel is not None else lambda: False
    executor = executor if executor is not None else _NativeExecutor()
    retained_history = (
        (undo_target.status, undo_target.observation)
        if undo_target is not None
        else None
    )
    try:
        first, reviewed_observation, format_parent, retained_history = (
            _observe_apply_inputs(
                root,
                subjects,
                purpose,
                undo_target,
                retained_history,
                _owned_export,
                _owners,
            )
        )
        refusal = _apply_admission_refusal(
            source,
            review,
            first,
            reviewed_observation,
            undo_target,
            format_parent,
            vault_id,
            import_id,
        )
        if refusal is not None:
            return outcome("refused", refusal, start=start)
        state.scoped = _acquire_reviewed_apply(
            root, operation_id, first.checkpoint, undo_target
        )
        state.acquired = True
        observed = _observe_apply_under_lease(
            root,
            subjects,
            retained_history,
            operation_id,
            purpose,
            _owned_export,
            _owners,
        )
        refusal = _held_apply_refusal(
            first, observed, source, review, selected, undo_target=undo_target
        )
        if refusal is not None:
            return outcome("refused", refusal, start=start)
        state.operation_generation = observed.checkpoint.manifest.generation + 1
        paths = _apply_path_plan(
            observed, review, selected, subjects, undo_target, outcome, start
        )
        if isinstance(paths, VaultApplyResult):
            return paths
        changed = paths[-1]
        state.planned = len(changed)
        publication = _StagedApplyInputs(
            root,
            source,
            review,
            vault_id,
            import_id,
            subjects,
            binding,
            observed_source,
            undo_target,
            retained_history,
            _owned_export,
            _owners,
            progress,
            format_parent,
            executor,
            cancel_requested,
            operation_id,
            kind,
            outcome,
            start,
        )
        stopped = _publish_staged_apply(publication, paths, observed, state)
        if stopped is not None:
            return stopped
        return _completed_apply(
            root, operation_id, state, outcome, start, undo_target, changed
        )
    except OSError, ValueError, TypeError:
        return _report_apply_failure(root, operation_id, state, outcome, start)
    finally:
        _release_apply_lease(root, operation_id, state, outcome, start)


def apply_reviewed_update(
    vault,
    source,
    *,
    review,
    vault_id,
    import_id,
    source_binding=None,
    observed_source=None,
    cancel=None,
    progress=None,
    executor=None,
    _owned_export=None,
):
    """Retain intent before exact selected publication and verify terminal history."""
    try:
        reusable_local_review = (
            _owned_export is not None
            and type(review) is ReviewPlan
            and review.facts.format_operation.kind == "source_update"
        )
        borrowed = (
            getattr(_owned_export, "_apply_review_owners", None)
            if reusable_local_review
            else None
        )
        owners = (
            _ApplyReviewOwners(
                local_owner=borrowed,
                retain_prepared=True,
                memory_spool=type(borrowed) is _ApplyReviewOwners,
            )
            if reusable_local_review
            else ExitStack()
        )
        with owners:
            return _apply_reviewed_update(
                vault,
                source,
                review=review,
                vault_id=vault_id,
                import_id=import_id,
                source_binding=source_binding,
                observed_source=observed_source,
                cancel=cancel,
                progress=progress,
                executor=executor,
                _owned_export=_owned_export,
                _owners=owners if _owned_export is not None else None,
            )
    except _OwnedCleanupFailure as failure:
        return failure.result
