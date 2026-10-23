"""Durable existing-vault publication of one whole reviewed S1 result."""

import hashlib
import os
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path
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
    VaultUpdateDetailPage,
)
from brz2obsidian.core import select_review_effects
from brz2obsidian.publication.git_payload import verify_blobs
from brz2obsidian.publication.vault_admission import _safe_relative
from brz2obsidian.publication.vault_history import (
    _control_objects,
    _Git,
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
    for change in review.proposal.changes:
        if change.path in selected.remove_paths:
            existing = paths.get(change.path)
            if existing is not None and existing != change.subject_id:
                raise ValueError("Selected removal has conflicting owner")
            paths[change.path] = change.subject_id
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


def _prepared_for_intent(intent, manifest, loaded):
    """A retained prepared review authorizes exactly its selected transition."""
    if loaded is None:
        return False
    plan = loaded.saved.plan
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
    source = {row.path: row for row in manifest.source}

    def matches(row, content):
        return (
            row is not None
            and row.size == len(content.data)
            and row.sha256 == hashlib.sha256(content.data).hexdigest()
        )

    def saved_current(path, expected):
        if not _safe_relative(path):
            return False
        row = before.get(path)
        return row is None if expected is None else matches(row, expected)

    def saved_incoming(path, expected):
        if not _safe_relative(path):
            return False
        row = source.get(path)
        return row is None if expected is None else matches(row, expected)

    if not _review_fact_paths_match(plan.producer_facts, saved_current, saved_incoming):
        return False
    selected_files = {row.path: row.content for row in selected.files}
    removals = set(selected.remove_paths)
    if any(path not in before or path in proposed for path in removals):
        return False
    for path, content in selected_files.items():
        row = proposed.get(path)
        if not matches(row, content):
            return False
        if path in before and before[path].mode != row.mode:
            return False
    return all(
        before.get(path) == proposed.get(path)
        for path in (before.keys() | proposed.keys()) - selected_files.keys() - removals
    )


def _terminal_files_match(root, intent):
    proposed = {row.path: row for row in intent.proposed}
    metadata = {row.path: row for row in intent.result_metadata}
    return all(state == "after" for state in _directory_states(root, intent)) and all(
        _metadata_matches(root, path, metadata.get(path))
        and (proposed.get(path) is None or _same_file(root, proposed[path]))
        for path in intent.affected_paths
    )


def inspect_update_status(vault):
    """Discover the latest owned intent independently of the current locator."""
    start = time.monotonic()
    root = Path(vault).absolute()
    try:
        git = _Git(root)
        raw = git.call(
            "for-each-ref",
            "--format=%(refname) %(objectname)",
            "refs/brz2obsidian/imports",
        )
        operations = []
        for line in raw.decode("ascii").splitlines():
            ref, oid = line.split(" ")
            parts = ref.split("/")
            if (
                len(parts) == 6
                and parts[:3] == ["refs", "brz2obsidian", "imports"]
                and parts[4] == "operations"
            ):
                operations.append((parts[3], parts[5], oid))
        if not operations:
            linked_intents = []
            _read(root, git, linked_intents=linked_intents)
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
            return _outcome("refused", "operation_absent", start=start)
        records = []
        for association, operation_id, commit in operations:
            entry = git.call("ls-tree", "--name-only", commit).decode().splitlines()
            if entry == ["receipt.json"]:
                receipt, parents = _read_record(
                    git, commit, "receipt.json", VaultOperationReceipt
                )
                if len(parents) != 2 or parents != (
                    receipt.intent_commit,
                    receipt.result_commit,
                ):
                    raise OSError("Terminal receipt has wrong real parent edges")
                intent, intent_parents = _read_record(
                    git, receipt.intent_commit, "intent.json", VaultOperationIntent
                )
                if intent_parents != (intent.prepared_commit,):
                    raise OSError("Prepared intent has wrong real parent edge")
                if (
                    receipt.operation_id != operation_id
                    or intent.operation_id != operation_id
                    or intent.association_id != association
                    or receipt.generation != intent.generation
                    or receipt.direction != intent.direction
                    or receipt.prepared_commit != intent.prepared_commit
                    or receipt.published_paths != intent.affected_paths
                ):
                    raise OSError("Terminal intent/receipt identity changed")
                records.append((intent.generation, intent, receipt, None, commit))
            elif entry == ["stop.json"]:
                stopped, parents = _read_record(
                    git, commit, "stop.json", VaultOperationStop
                )
                if parents != (stopped.intent_commit,):
                    raise OSError("Stopped intent has wrong real parent edge")
                intent, intent_parents = _read_record(
                    git, stopped.intent_commit, "intent.json", VaultOperationIntent
                )
                if (
                    intent_parents != (intent.prepared_commit,)
                    or stopped.operation_id != intent.operation_id
                    or stopped.operation_id != operation_id
                    or intent.association_id != association
                    or stopped.generation != intent.generation
                    or stopped.direction != intent.direction
                    or stopped.acknowledged_after_files > len(intent.affected_paths)
                ):
                    raise OSError("Stopped intent identity changed")
                records.append((intent.generation, intent, None, stopped, commit))
            elif entry == ["intent.json"]:
                intent, parents = _read_record(
                    git, commit, "intent.json", VaultOperationIntent
                )
                if (
                    parents != (intent.prepared_commit,)
                    or intent.operation_id != operation_id
                    or intent.association_id != association
                ):
                    raise OSError("Prepared intent identity changed")
                records.append((intent.generation, intent, None, None, commit))
            else:
                raise OSError("Unknown operation record graph")
        records.sort(key=lambda row: row[0])
        if len({row[0] for row in records}) != len(records):
            raise OSError("Multiple operation intents claim one generation")
        targets = {row[1].prepared_commit for row in records}
        targets.update(row[2].result_commit for row in records if row[2] is not None)
        linked_intents = []
        checkpoint, owned = _read(
            root, git, targets=targets, linked_intents=linked_intents
        )
        rooted_intents = {
            row[2].intent_commit
            if row[2] is not None
            else row[3].intent_commit
            if row[3] is not None
            else row[4]
            for row in records
        }
        if len(linked_intents) != len(set(linked_intents)) or not set(
            linked_intents
        ).issubset(rooted_intents):
            raise OSError(
                "Application result has a missing or duplicate operation root"
            )
        for _, candidate, terminal, _, _ in records:
            prepared, saved = owned[candidate.prepared_commit]
            if candidate.direction != "finish" or not _prepared_for_intent(
                candidate, prepared, saved
            ):
                raise OSError("Operation intent lacks a selected prepared review")
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
                ):
                    raise OSError("Terminal receipt lacks its exact result checkpoint")
        _, intent, receipt, stopped, commit = records[-1]
        try:
            manifest = checkpoint.manifest
            if (
                checkpoint.status != "valid"
                or manifest.association_id != intent.association_id
                or manifest.generation < intent.generation
                or (
                    manifest.boundary == "prepared"
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
                    ("result", "local")
                    if receipt is not None
                    else ("prepared", "result")
                )
            ):
                raise OSError("Operation intent and owned checkpoint disagree")
        except OSError, ValueError, TypeError, UnicodeError:
            return _outcome(
                "unknown",
                "operation_checkpoint_invalid",
                start=start,
                operation_id=intent.operation_id,
                generation=intent.generation,
                phase="intent",
                publication="unknown",
                history="unknown",
                planned=len(intent.affected_paths),
                changed=None,
                checkpoint=intent.prepared_commit,
                intent=receipt.intent_commit
                if receipt is not None
                else stopped.intent_commit
                if stopped is not None
                else commit,
                receipt=commit if receipt is not None else None,
                stop=commit if stopped is not None else None,
                recovery=True,
            )
        if receipt is not None:
            complete_history = (
                checkpoint.status == "valid"
                and _terminal_result_in_history(git, checkpoint, intent, receipt)
            )
            if complete_history and not _lock_path(root).exists():
                return _outcome(
                    receipt.status,
                    receipt.status,
                    start=start,
                    operation_id=intent.operation_id,
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
                and _terminal_files_match(root, intent)
            ):
                return _outcome(
                    "content_complete",
                    "terminal_cleanup_required",
                    start=start,
                    operation_id=intent.operation_id,
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
        all_states = states + directory_states
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
            generation=intent.generation,
            phase="publication",
            publication=publication,
            history="intent",
            planned=len(intent.affected_paths),
            published=states.count("after"),
            changed="after" in all_states,
            checkpoint=intent.prepared_commit,
            intent=stopped.intent_commit if stopped is not None else commit,
            stop=commit if stopped is not None else None,
            recovery=True,
        )
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


def read_update_details(vault, *, offset=0, limit=100):
    """Page only validated owned before/result comparison facts, never bytes."""
    if (
        type(offset) is not int
        or offset < 0
        or type(limit) is not int
        or not 1 <= limit <= 100
    ):
        raise ValueError("Detail offset or limit is outside the bounded page")

    def page(status, code, operation_id=None, total=0, items=()):
        next_offset = offset + len(items) if offset + len(items) < total else None
        return VaultUpdateDetailPage(
            schema_id="brz2obsidian.vault-update-detail-page",
            schema_version=1,
            status=status,
            code=code,
            operation_id=operation_id,
            offset=offset,
            limit=limit,
            total=total,
            items=tuple(items),
            next_offset=next_offset,
        )

    observed = inspect_update_status(vault)
    if observed.status in ("unknown", "refused") or observed.intent_commit is None:
        return page("unavailable", "operation_authority_unavailable")
    try:
        git = _Git(Path(vault).absolute())
        intent, parents = _read_record(
            git, observed.intent_commit, "intent.json", VaultOperationIntent
        )
        if (
            parents != (intent.prepared_commit,)
            or intent.operation_id != observed.operation_id
            or intent.generation != observed.generation
            or intent.prepared_commit != observed.checkpoint_commit
            or intent.direction != "finish"
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
        return page("available", "validated", intent.operation_id, len(paths), items)
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
            and row.size == len(expected.data)
            and row.sha256 == hashlib.sha256(expected.data).hexdigest()
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
        return (
            info.st_size == len(expected.data)
            and sha == hashlib.sha256(expected.data).hexdigest()
        )

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
        kind="apply",
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


def _apply_reviewed_update(
    vault,
    source,
    *,
    review,
    vault_id,
    import_id,
    source_binding=None,
    cancel=None,
    executor=None,
):
    """Retain intent before exact selected publication and verify terminal history."""
    start = time.monotonic()
    selected = select_review_effects(review)
    if selected.status != "selected":
        return _outcome("refused", selected.code, start=start)
    root, source = Path(vault).absolute(), Path(source).absolute()
    if not supported_durable_volume(root):
        return _outcome("refused", "unsupported_durable_volume", start=start)
    from brz2obsidian.application.source_payload_contracts import ReviewedSourceBinding
    from brz2obsidian.publication.source_payload import observe_reviewed_source

    try:
        if source_binding is None:
            return _outcome("refused", "source_binding_required", start=start)
        binding = ReviewedSourceBinding.model_validate(source_binding)
        if (
            binding.proposal_id != review.proposal.proposal_id
            or binding.generation != review.proposal.generation
            or binding.incoming_identity != review.facts.incoming_identity
            or binding.target_source_version
            != review.facts.format_operation.target_source_version
        ):
            return _outcome("refused", "source_binding_mismatch", start=start)
        if observe_reviewed_source(source, review) != binding:
            return _outcome("refused", "source_payload_changed", start=start)
    except OSError, ValueError, TypeError, UnicodeError:
        return _outcome("refused", "source_payload_unavailable", start=start)
    try:
        subjects = _review_subjects(review, selected)
    except ValueError, TypeError:
        return _outcome("refused", "invalid_review_scope", start=start)
    operation_id = uuid4().hex
    phase = "admission"
    prepared_commit = intent_commit = result_commit = receipt_commit = None
    published = 0
    planned = 0
    operation_generation = None
    acquired = False
    failure_code = "apply_unavailable"
    cancel_requested = cancel if cancel is not None else lambda: False
    executor = executor if executor is not None else _NativeExecutor()
    try:
        reviewed_observation = inspect_history(root)
        first = inspect_history(root, subjects=subjects)
        scoped_preflight = first.admission.preflight
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
            return _outcome("refused", "current_review_required", start=start)
        if first.status != "intact" or first.admission.status != "supported":
            return _outcome("refused", "scoped_admission_required", start=start)
        if (
            first.checkpoint.locator.commit
            != reviewed_observation.checkpoint.locator.commit
            or first.checkpoint.locator.association.vault_id != vault_id
            or first.checkpoint.locator.association.import_id != import_id
            or first.checkpoint.manifest.identity != review.facts.baseline_identity
        ):
            return _outcome("refused", "current_review_required", start=start)
        if not _review_inputs_match(review, first.admission, source):
            return _outcome("refused", "review_inputs_changed", start=start)
        _acquire(root, operation_id)
        acquired = True
        observed = inspect_history(
            root, subjects=subjects, active_operation=operation_id
        )
        if (
            observed.status != "intact"
            or observed.admission.status != "supported"
            or observed.admission.inventory != first.admission.inventory
            or observed.admission.policy_fingerprint
            != first.admission.policy_fingerprint
            or observed.checkpoint.locator.commit != first.checkpoint.locator.commit
        ):
            return _outcome("refused", "current_admission_required", start=start)
        operation_generation = observed.checkpoint.manifest.generation + 1
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
            subject.path
            for subject in subjects
            if subject.subject_id in accepted_tracking
        }
        before = {
            row.path: row
            for row in observed.admission.inventory
            if not row.excluded or row.path in included_paths
        }
        selected_files = {row.path: row.content.data for row in selected.files}
        removals = set(selected.remove_paths)
        if any(not _safe_relative(path) for path in (*selected_files, *removals)):
            return _outcome("refused", "unsafe_selected_path", start=start)
        if any(path not in before for path in removals):
            return _outcome("refused", "selected_removal_missing", start=start)
        changed = {
            path
            for path, data in selected_files.items()
            if path not in before
            or before[path].size != len(data)
            or before[path].sha256 != hashlib.sha256(data).hexdigest()
        } | removals
        planned = len(changed)
        before_metadata = {}
        result_metadata = {}
        # Observe the peak copy/overwrite footprint before creating the stage.
        # Checkpoint capture performs its separate spool and Git check afterward.
        stage_need = (
            sum(row.size for path, row in before.items() if path not in removals)
            + sum(len(data) for data in selected_files.values())
            + 64 * 1024 * 1024
            + 4096 * (len(before) + len(selected_files))
        )
        if shutil.disk_usage(root.parent).free < stage_need:
            return _outcome("refused", "insufficient_stage_resources", start=start)
        with _proposed_directory(root.parent) as name:
            proposed_root = Path(name)
            if proposed_root.stat().st_dev != root.stat().st_dev:
                return _outcome("refused", "same_volume_stage_required", start=start)
            stage_parent_security(root, proposed_root, Path("."))
            for path, row in before.items():
                if path in removals:
                    continue
                target = proposed_root / path
                stage_parent_security(root, proposed_root, Path(path).parent)
                if not _same_file(root, row):
                    return _outcome("refused", "current_bytes_changed", start=start)
                if path in changed:
                    before_metadata[path] = retained_metadata(root / path)
                if path in changed:
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
            prepared_parent_metadata = {
                path: retained_directory_metadata(stage)
                for path, stage in prepared_parents.items()
            }
            phase = "prepared"
            prepared = capture_checkpoint(
                root,
                source,
                vault_id=vault_id,
                import_id=import_id,
                identity=review.facts.incoming_identity,
                admission=observed.admission,
                review=review,
                boundary="prepared",
                proposed=proposed_root,
                active_operation=operation_id,
                subjects=subjects,
                source_binding=binding,
            )
            if prepared.status != "captured":
                return _outcome(
                    "refused" if prepared.status == "refused" else "failed",
                    "prepare_" + prepared.code,
                    start=start,
                    operation_id=operation_id,
                    generation=operation_generation,
                    phase=phase,
                    history="prepared" if prepared.history_retained else "none",
                    checkpoint=prepared.commit,
                )
            prepared_commit = prepared.commit
            if cancel_requested():
                return _outcome(
                    "cancelled",
                    "cancelled_before_intent",
                    start=start,
                    operation_id=operation_id,
                    generation=operation_generation,
                    phase="prepared",
                    publication="not_started",
                    history="prepared",
                    planned=len(changed),
                    checkpoint=prepared_commit,
                    recovery=False,
                    message="Cancellation retained preparation without publishing files.",
                )
            tip = inspect_history(
                root, subjects=subjects, active_operation=operation_id
            )
            manifest = tip.checkpoint.manifest
            if tip.status != "intact" or manifest.boundary != "prepared":
                raise OSError("Prepared checkpoint could not be rediscovered")
            operation_generation = manifest.generation
            intent = VaultOperationIntent(
                schema_id="brz2obsidian.vault-operation-intent",
                schema_version=1,
                operation_id=operation_id,
                kind="apply",
                generation=manifest.generation,
                direction="finish",
                association_id=manifest.association_id,
                prepared_commit=prepared_commit,
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
            phase = "intent"
            intent_commit = _journal(
                git, "intent.json", intent, parents=(prepared_commit,), ref=op_ref
            )
            phase = "publication"
            proposed = {row.path: row for row in manifest.proposed}
            prior = {row.path: row for row in manifest.preimage}
            for path in sorted(changed):
                if cancel_requested():
                    stopped = VaultOperationStop(
                        schema_id="brz2obsidian.vault-operation-stop",
                        schema_version=1,
                        operation_id=operation_id,
                        kind="apply",
                        generation=manifest.generation,
                        direction="finish",
                        status="cancelled",
                        intent_commit=intent_commit,
                        acknowledged_after_files=published,
                    )
                    stop_commit = _journal(
                        git,
                        "stop.json",
                        stopped,
                        parents=(intent_commit,),
                        previous=intent_commit,
                        ref=op_ref,
                    )
                    return _outcome(
                        "cancelled",
                        "cancelled_after_intent",
                        start=start,
                        operation_id=operation_id,
                        generation=operation_generation,
                        phase="publication",
                        publication="partial" if published else "not_published",
                        history="intent",
                        planned=len(changed),
                        published=published,
                        changed=bool(published),
                        checkpoint=prepared_commit,
                        intent=intent_commit,
                        stop=stop_commit,
                        recovery=True,
                        message="Cancellation stopped at a recoverable file boundary.",
                    )
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
                    if (
                        not _same_file(root, new)
                        or retained_metadata(target) != metadata
                    ):
                        raise OSError("Published bytes did not match prepared result")
                published += 1
            for path, row in proposed.items():
                if not _same_file(root, row):
                    raise OSError("Complete proposed inventory disagrees")
            if any(os.path.lexists(root / path) for path in set(prior) - set(proposed)):
                raise OSError("Removed path remains visible")
            phase = "result"
            current = inspect_history(
                root, subjects=subjects, active_operation=operation_id
            )
            result_checkpoint = capture_checkpoint(
                root,
                source,
                vault_id=vault_id,
                import_id=import_id,
                identity=review.facts.incoming_identity,
                admission=current.admission,
                boundary="result",
                expected_prepared=prepared_commit,
                active_operation=operation_id,
                operation_intent_commit=intent_commit,
                subjects=subjects,
            )
            if result_checkpoint.status != "captured":
                failure_code = "result_" + result_checkpoint.code
                raise OSError("Actual result checkpoint could not be retained")
            result_commit = result_checkpoint.commit
            receipt = VaultOperationReceipt(
                schema_id="brz2obsidian.vault-operation-receipt",
                schema_version=1,
                operation_id=operation_id,
                kind="apply",
                generation=manifest.generation,
                status="applied" if changed else "no_content_change",
                direction="finish",
                intent_commit=intent_commit,
                prepared_commit=prepared_commit,
                result_commit=result_commit,
                published_paths=tuple(sorted(changed)),
            )
            phase = "terminal"
            receipt_commit = _journal(
                git,
                "receipt.json",
                receipt,
                parents=(intent_commit, result_commit),
                previous=intent_commit,
                ref=op_ref,
            )
        _release(root, operation_id)
        acquired = False
        return _outcome(
            "applied" if changed else "no_content_change",
            "applied" if changed else "no_content_change",
            start=start,
            operation_id=operation_id,
            generation=operation_generation,
            phase="terminal",
            publication="complete",
            history="terminal",
            planned=len(changed),
            published=published,
            changed=bool(changed),
            checkpoint=prepared_commit,
            intent=intent_commit,
            result=result_commit,
            receipt=receipt_commit,
            recovery=False,
            message="Reviewed exact result and terminal receipt retained.",
        )
    except OSError, ValueError, TypeError:
        observed_failure = (
            inspect_update_status(root)
            if phase in ("intent", "publication", "result", "terminal")
            else None
        )
        if (
            observed_failure is not None
            and observed_failure.operation_id == operation_id
            and observed_failure.intent_commit is not None
        ):
            intent_commit = observed_failure.intent_commit
            if observed_failure.status in ("applied", "no_content_change"):
                return _outcome(
                    "content_complete",
                    "terminal_reporting_failed",
                    start=start,
                    operation_id=operation_id,
                    generation=operation_generation,
                    phase="terminal",
                    publication="complete",
                    history="terminal",
                    planned=planned,
                    published=observed_failure.published_files,
                    changed=observed_failure.authored_files_changed,
                    checkpoint=prepared_commit,
                    intent=intent_commit,
                    result=observed_failure.result_commit,
                    receipt=observed_failure.receipt_commit,
                    recovery=False,
                    message="Exact content and receipt are complete; final reporting failed.",
                )
            return _outcome(
                observed_failure.status,
                failure_code + "_" + observed_failure.code,
                start=start,
                operation_id=operation_id,
                generation=operation_generation,
                phase=phase,
                publication=observed_failure.publication,
                history=(
                    "result"
                    if result_commit is not None
                    and observed_failure.status == "content_complete"
                    else observed_failure.history
                ),
                planned=planned,
                published=observed_failure.published_files,
                changed=observed_failure.authored_files_changed,
                checkpoint=prepared_commit,
                intent=intent_commit,
                result=observed_failure.result_commit or result_commit,
                receipt=observed_failure.receipt_commit,
                stop=observed_failure.stop_commit,
                recovery=True,
            )
        authority_unknown = phase == "intent" and intent_commit is None
        cleanup_pending = not acquired and _lock_path(root).exists()
        publication_unknown = intent_commit is not None
        return _outcome(
            "content_complete"
            if result_commit is not None
            else "unknown"
            if authority_unknown or publication_unknown or cleanup_pending
            else "failed",
            "owned_acquire_failed" if cleanup_pending else failure_code,
            start=start,
            operation_id=operation_id if acquired or cleanup_pending else None,
            generation=operation_generation,
            phase=phase,
            publication="complete"
            if result_commit is not None
            else "unknown"
            if publication_unknown
            else "not_published"
            if authority_unknown
            else "not_started",
            history="unknown"
            if authority_unknown
            else "result"
            if result_commit
            else "intent"
            if intent_commit
            else "prepared"
            if prepared_commit
            else "none",
            planned=planned,
            published=published,
            changed=True
            if result_commit is not None and planned
            else None
            if publication_unknown
            else False,
            checkpoint=prepared_commit,
            intent=intent_commit,
            result=result_commit,
            receipt=receipt_commit,
            recovery=bool(intent_commit) or authority_unknown or cleanup_pending,
            message="Existing-vault operation requires exact recovery inspection.",
        )
    finally:
        if acquired and intent_commit is None:
            pending_exception = sys.exc_info()[0]
            try:
                _release(root, operation_id)
            except OSError, ValueError, TypeError:
                if pending_exception is None or issubclass(
                    pending_exception, (OSError, ValueError, TypeError)
                ):
                    raise _OwnedCleanupFailure(
                        _outcome(
                            "unknown" if phase == "intent" else "incomplete",
                            "owned_cleanup_failed",
                            start=start,
                            operation_id=operation_id,
                            generation=operation_generation,
                            phase=phase,
                            publication="not_published"
                            if phase == "intent"
                            else "not_started",
                            history="unknown"
                            if phase == "intent"
                            else "prepared"
                            if prepared_commit is not None
                            else "none",
                            planned=planned,
                            published=0,
                            changed=False,
                            checkpoint=prepared_commit,
                            recovery=True,
                            message="Owned marker cleanup failed; inspect before another operation.",
                        )
                    ) from None


def apply_reviewed_update(
    vault,
    source,
    *,
    review,
    vault_id,
    import_id,
    source_binding=None,
    cancel=None,
    executor=None,
):
    """Retain intent before exact selected publication and verify terminal history."""
    try:
        return _apply_reviewed_update(
            vault,
            source,
            review=review,
            vault_id=vault_id,
            import_id=import_id,
            source_binding=source_binding,
            cancel=cancel,
            executor=executor,
        )
    except _OwnedCleanupFailure as failure:
        return failure.result
