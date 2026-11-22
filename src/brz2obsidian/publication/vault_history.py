"""Converter-owned exact-byte Git graph, independent of user branch ancestry."""

import hashlib
import io
import json
import os
import shutil
import stat
import tempfile
import zlib
from contextlib import ExitStack
from dataclasses import dataclass
from itertools import batched
from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

from brz2obsidian.application.checkpoint_contracts import (
    CheckpointFile,
    CheckpointLocator,
    CheckpointManifest,
    CheckpointRead,
    CheckpointResult,
    VaultAssociation,
    VaultHistoryInspection,
    VaultInitializationDecision,
    VaultInitializationResult,
)
from brz2obsidian.application.vault_contracts import VaultSubject
from brz2obsidian.content_fingerprints import canonical_equal
from brz2obsidian.content_values import content_sha, content_size
from brz2obsidian.contracts import (
    ExactContent,
    OpaqueContent,
    OutputIdentity,
    SafetyFact,
    SavedReview,
    SourceMemoryProvenance,
    legacy_content_fields,
    reconciliation_subject_id,
)
from brz2obsidian.core import (
    load_review,
    review_owned_targets,
    save_review,
    select_review_effects,
)
from brz2obsidian.publication.git_payload import verify_blobs
from brz2obsidian.publication.git_read import OUTPUT_BUDGET, _GitTimeout, read_git
from brz2obsidian.publication.vault_admission import (
    HOOKS,
    _configured_hook_state,
    _Inspection,
    _observe_vault,
    _safe_relative,
    _walk,
    inspect_vault,
)
from brz2obsidian.publication.vault_native import (
    available_memory,
    observe_file,
    verify_directory,
)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def result(
    status,
    code,
    *,
    commit=None,
    ref=None,
    retained=False,
    objects=False,
    object_storage=None,
    locator=None,
):
    return CheckpointResult(
        schema_id="brz2obsidian.checkpoint-result",
        schema_version=1,
        status=status,
        code=code,
        commit=commit,
        ref=ref,
        history_retained=retained,
        objects_written=objects,
        object_storage=object_storage or ("verified" if objects else "not_started"),
        authored_files_changed=False,
        message="Checkpoint history " + code.replace("_", " ") + ".",
        locator=locator,
    )


def _review_meaning(saved):
    """Checkpoint duplicate meaning only; never an authorization comparison."""
    if saved is None:
        return None
    proof_fields = {
        "proposal_id",
        "generation",
        "decision_id",
        "change_id",
        "reviewed_change_id",
        "reviewed_assumptions",
        "assumptions",
        "validation_fingerprint",
        "context_fingerprint",
    }

    def meaning(value):
        if isinstance(value, SafetyFact) and value.kind in {"operation", "history"}:
            return {
                name: meaning(getattr(value, name))
                for name in _stored_model_fields(value)
                if name != "fingerprint"
            }
        if isinstance(value, (ExactContent, OpaqueContent)):
            return {
                "sha256": value.identity.sha256,
                "size": value.identity.size,
            }
        if isinstance(value, SourceMemoryProvenance):
            return None
        if hasattr(type(value), "model_fields"):
            return {
                name: meaning(getattr(value, name))
                for name in _stored_model_fields(value)
                if name not in proof_fields
            }
        if isinstance(value, dict):
            return {key: meaning(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [meaning(item) for item in value]
        if isinstance(value, bytes):
            return {"sha256": hashlib.sha256(value).hexdigest(), "size": len(value)}
        return value

    plan = saved.plan
    return meaning((plan.facts, plan.producer_facts, plan.approvals, plan.consents))


def _review_source_signature(saved):
    facts = saved.plan.facts
    rows = tuple(
        sorted(
            (s.path, s.incoming.identity.size, s.incoming.identity.sha256)
            for s in facts.subjects
            if s.incoming is not None
        )
    )
    return (
        facts.proposal_id,
        facts.generation,
        facts.incoming_identity,
        facts.format_operation.target_source_version,
        rows,
    )


def _binding_signature(binding):
    return (
        binding.proposal_id,
        binding.generation,
        binding.incoming_identity,
        binding.target_source_version,
        tuple((row.path, row.size, row.sha256) for row in binding.files),
    )


def _reviewed_source_matches(saved, binding):
    return _review_source_signature(saved) == _binding_signature(binding)


def _source_observation_matches(observed, binding):
    return binding is not None and (
        observed.source_id,
        observed.module_id,
        observed.module_version,
        observed.snapshot_digest,
    ) == (
        binding.incoming_identity.collection_id,
        binding.incoming_identity.module_id,
        binding.incoming_identity.module_version,
        binding.target_source_version,
    )


def _semantic(
    association,
    identity,
    source,
    vault,
    preimage,
    proposed,
    gaps,
    boundary,
    policy,
    saved,
    operation_intent_commit=None,
    recovery_origin_intent_commit=None,
    recovery_previous_operation_commit=None,
    recovery_direction=None,
    undo_of_receipt_commit=None,
    observed_source=None,
    reviewed_source=None,
    collection_record_path=None,
    collection_baseline_commit=None,
    collection_preparation_owner=None,
):
    return _semantic_meaning(
        association,
        identity,
        source,
        vault,
        preimage,
        proposed,
        gaps,
        boundary,
        policy,
        _review_meaning(saved),
        operation_intent_commit,
        recovery_origin_intent_commit,
        recovery_previous_operation_commit,
        recovery_direction,
        undo_of_receipt_commit,
        observed_source,
        reviewed_source,
        collection_record_path=collection_record_path,
        collection_baseline_commit=collection_baseline_commit,
        collection_preparation_owner=collection_preparation_owner,
    )


def _semantic_meaning(
    association,
    identity,
    source,
    vault,
    preimage,
    proposed,
    gaps,
    boundary,
    policy,
    meaning,
    operation_intent_commit=None,
    recovery_origin_intent_commit=None,
    recovery_previous_operation_commit=None,
    recovery_direction=None,
    undo_of_receipt_commit=None,
    observed_source=None,
    reviewed_source=None,
    discarded_review=None,
    collection_record_path=None,
    collection_baseline_commit=None,
    collection_preparation_owner=None,
    abandoned_collection_preparation=None,
):
    parts = (
        association.model_dump(mode="json"),
        identity.model_dump(mode="json"),
        [
            [row.model_dump(mode="json") for row in inventory]
            for inventory in (source, vault, preimage, proposed)
        ],
        gaps,
        boundary,
        policy,
        meaning,
    )
    if observed_source is not None or reviewed_source is not None:
        parts += (
            "source-observation",
            observed_source.model_dump(mode="json")
            if observed_source is not None
            else None,
            reviewed_source.model_dump(mode="json")
            if reviewed_source is not None
            else None,
        )
    if discarded_review is not None:
        parts += ("discarded-review", discarded_review)
    if collection_record_path is not None:
        parts += ("collection-record", collection_record_path)
    if collection_baseline_commit is not None:
        parts += ("collection-baseline", collection_baseline_commit)
    if collection_preparation_owner is not None:
        parts += ("collection-preparation-owner", collection_preparation_owner)
    if abandoned_collection_preparation is not None:
        parts += ("abandoned-collection-preparation", abandoned_collection_preparation)
    if undo_of_receipt_commit is not None:
        return digest((*parts, "undo-prepared", undo_of_receipt_commit))
    if recovery_origin_intent_commit is not None:
        return digest(
            (
                *parts,
                "recovery-prepared",
                recovery_origin_intent_commit,
                recovery_previous_operation_commit,
                recovery_direction,
            )
        )
    return digest(
        parts if operation_intent_commit is None else (*parts, operation_intent_commit)
    )


class _Git:
    def __init__(self, root, executable=None):
        self.root = Path(root).absolute()
        self.inspection = _Inspection(root, (), executable)
        self.env = dict(self.inspection.env)
        self.env.update(
            {
                "GIT_AUTHOR_NAME": "brz2obsidian",
                "GIT_AUTHOR_EMAIL": "history@brz2obsidian.invalid",
                "GIT_COMMITTER_NAME": "brz2obsidian",
                "GIT_COMMITTER_EMAIL": "history@brz2obsidian.invalid",
                "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000",
                "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000",
            }
        )
        self.prefix = [
            self.inspection.executable,
            "--no-pager",
            "--no-replace-objects",
            "-C",
            str(self.root),
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.fsync=objects,reference",
            "-c",
            "core.fsyncMethod=fsync",
            "-c",
            "core.bigFileThreshold=1m",
            "-c",
            "gc.auto=0",
            "-c",
            "maintenance.auto=false",
        ]

    def suppress_hooks(self, directory):
        hooks = directory / "empty-hooks"
        hooks.mkdir()
        verify_directory(hooks)
        if os.listdir(hooks):
            raise OSError("Owned hook directory is not empty")
        _, friendly, _ = _configured_hook_state(
            self.inspection.effective_config(), self.inspection.hook_boolean
        )
        self.prefix += ["-c", "core.hooksPath=" + str(hooks)]
        for name in sorted(HOOKS | friendly):
            self.prefix += ["-c", "hook." + name + ".enabled=false"]
        for name in sorted(friendly):
            self.prefix += ["-c", "hook." + name + ".event="]

    def call(self, *args, input=None, allowed=(0,)):
        value = read_git([*self.prefix, *args], env=self.env, input=input)
        if value.returncode not in allowed or value.stderr:
            raise OSError("Complete local Git history observation unavailable")
        return value.stdout

    def tree(self, entries):
        children = {}
        for path, mode, oid in entries:
            head, separator, tail = path.partition("/")
            if separator:
                children.setdefault(head, []).append((tail, mode, oid))
            else:
                children[head] = (mode, oid)
        for name, value in sorted(children.items()):
            if isinstance(value, list):
                children[name] = "040000", self.tree(value)
        return (
            self.call("mktree", "-z", input=self._tree_rows(children)).decode().strip()
        )

    @staticmethod
    def _tree_rows(entries):
        return b"".join(
            f"{mode} {'tree' if mode == '040000' else 'blob'} {oid}\t".encode("ascii")
            + name.encode("utf-8")
            + b"\0"
            for name, (mode, oid) in sorted(entries.items())
        )

    @staticmethod
    def _tree_oid(entries):
        # Git sorts directory names as if followed by a slash.
        rows = [
            (name.encode("utf-8"), mode, oid) for name, (mode, oid) in entries.items()
        ]
        rows.sort(key=lambda row: row[0] + (b"/" if row[1] == "040000" else b""))
        body = b"".join(
            mode.lstrip("0").encode("ascii") + b" " + name + b"\0" + bytes.fromhex(oid)
            for name, mode, oid in rows
        )
        return hashlib.sha1(
            f"tree {len(body)}\0".encode("ascii") + body, usedforsecurity=False
        ).hexdigest()

    def _checkpoint_tree_levels(self, inventories):
        levels = [{}]
        for role, inventory in inventories:
            levels[0][(role,)] = {}
            for row in inventory:
                parts = (role, *row.path.split("/"))
                depth = len(parts) - 2
                while len(levels) <= depth:
                    levels.append({})
                levels[depth].setdefault(parts[:-1], {})[parts[-1]] = (
                    row.mode,
                    row.object_id,
                )
        return levels

    def _write_checkpoint_tree_batch(self, trees):
        batch = b"".join(self._tree_rows(rows) + b"\0" for rows in trees.values())
        expected = [self._tree_oid(rows) for rows in trees.values()]
        try:
            raw = self.call("mktree", "-z", "--batch", input=batch)
        except _GitTimeout as error:
            if len(trees) == 1:
                raise
            _check_timed_out_object_ids(
                error, expected, "Checkpoint tree batch output changed"
            )
            for rows, expected_oid in zip(trees.values(), expected, strict=True):
                oid = self.tree(
                    (name, mode, object_id) for name, (mode, object_id) in rows.items()
                )
                if oid != expected_oid:
                    raise OSError("Checkpoint tree write changed")
        else:
            if raw.decode().splitlines() != expected:
                raise OSError("Checkpoint tree batch output changed")
        return expected

    def checkpoint_trees(self, inventories):
        """Write trees by depth, with per-tree deadlines after a clean timeout."""
        levels = self._checkpoint_tree_levels(inventories)
        controls = {}
        for depth in range(len(levels) - 1, -1, -1):
            trees = levels[depth]
            expected = self._write_checkpoint_tree_batch(trees)
            controls.update(dict.fromkeys(expected, "tree"))
            if depth:
                for path, oid in zip(trees, expected, strict=True):
                    levels[depth - 1].setdefault(path[:-1], {})[path[-1]] = (
                        "040000",
                        oid,
                    )
        _control_objects(self, controls, {})
        return [
            (path[0], "040000", oid) for path, oid in zip(trees, expected, strict=True)
        ]


def _spool(root, directory, paths=None, *, offset=0):
    root = Path(root).absolute()
    inventory, spools = [], []
    if paths is None:
        paths = []
        for parent, names, files in _walk(root):
            for name in (*names, *files):
                relative = (Path(parent) / name).relative_to(root).as_posix()
                if not _safe_relative(relative) or relative.casefold().startswith(
                    ".brz2obsidian/"
                ):
                    raise OSError("Unsafe converted inventory")
            paths.extend(
                (Path(parent) / name).relative_to(root).as_posix() for name in files
            )
    for path in sorted(paths):
        spool = directory / ("payload-" + str(offset + len(spools)))
        with spool.open("xb") as output:
            info, sha, _, identity = observe_file(root, root / path, sink=output)
            output.flush()
        mode = "100755" if os.name != "nt" and info.st_mode & stat.S_IXUSR else "100644"
        inventory.append((path, mode, info.st_size, sha, identity))
        spools.append(spool)
    return inventory, spools


def _source_matches(root, expected):
    paths = []
    for parent, _, files in _walk(root):
        paths.extend(
            (Path(parent) / name).relative_to(root).as_posix() for name in files
        )
    if sorted(paths) != [row[0] for row in expected]:
        return False
    for path, mode, size, sha, identity in expected:
        info, current_sha, _, current_identity = observe_file(
            root, root / path, prefix_limit=0
        )
        current_mode = (
            "100755" if os.name != "nt" and info.st_mode & stat.S_IXUSR else "100644"
        )
        if (mode, size, sha, identity) != (
            current_mode,
            info.st_size,
            current_sha,
            current_identity,
        ):
            return False
    return True


def _capture_scope_size(path):
    verify_directory(path)
    total = 0
    for parent, _, files in _walk(path):
        verify_directory(Path(parent))
        for name in files:
            item = Path(parent) / name
            relative = item.relative_to(path).as_posix()
            info = item.lstat()
            if (
                not _safe_relative(relative)
                or not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
            ):
                raise OSError("Unsafe input path for checkpoint sizing")
            total += info.st_size
    return total


def _capture_review_bytes(value, unique):
    if type(value) is bytes:
        sha = hashlib.sha256(value).hexdigest()
        if sha in unique and unique[sha] != value:
            raise OSError("Ambiguous review bytes during checkpoint sizing")
        unique[sha] = value
    elif hasattr(type(value), "model_fields"):
        for name in type(value).model_fields:
            _capture_review_bytes(getattr(value, name), unique)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _capture_review_bytes(item, unique)


def _capture_resources(
    root, source, proposed, temp_base, vault_size, saved, *, _owned_export=None
):
    """Observe ordinary spool and Git capacity before writing captured bytes."""

    unique = {}

    if saved is not None and _owned_export is None:
        try:
            _capture_review_bytes(saved, unique)
        except RecursionError as error:
            raise OSError("Saved review exceeds bounded checkpoint sizing") from error
    input_size = (
        _capture_scope_size(source)
        + vault_size
        + (_capture_scope_size(proposed) if proposed is not None else 0)
    )
    review_size = (
        sum(value.identity.size for value in _owned_export.values.values())
        if _owned_export is not None
        else sum(len(value) for value in unique.values())
    )
    margin = 64 * 1024 * 1024
    spool_need = input_size + review_size + margin
    git_need = input_size + review_size + margin
    if os.stat(root).st_dev == os.stat(temp_base).st_dev:
        enough_space = shutil.disk_usage(root).free >= spool_need + git_need
    else:
        enough_space = (
            shutil.disk_usage(temp_base).free >= spool_need
            and shutil.disk_usage(root).free >= git_need
        )
    if _owned_export is not None:
        _owned_export.check(saved.plan)
        return (
            enough_space and available_memory() >= 4 * len(_owned_export.raw) + margin
        )
    return enough_space and available_memory() >= 9 * review_size + margin


def _quoted_paths(paths):
    return b"".join(
        b'"'
        + b"".join(
            bytes((value,))
            if 32 <= value < 127 and value not in (34, 92)
            else f"\\{value:03o}".encode()
            for value in str(path).replace("\\", "/").encode("utf-8")
        )
        + b'"\n'
        for path in paths
    )


def _spool_oid(directory, path, size, sha):
    oid = hashlib.sha1(b"blob " + str(size).encode() + b"\0")

    class Sink:
        def write(self, block):
            oid.update(block)
            return len(block)

    info, actual_sha, _, _ = observe_file(directory, path, prefix_limit=0, sink=Sink())
    if info.st_size != size or actual_sha != sha:
        raise OSError("Captured spool changed")
    return oid.hexdigest()


def _check_timed_out_object_ids(error, expected, message):
    partial = error.stdout.replace(b"\r\n", b"\n")
    if partial.endswith(b"\r"):
        partial = partial[:-1] + b"\n"
    expected_stdout = "".join(f"{oid}\n" for oid in expected).encode("ascii")
    if not expected_stdout.startswith(partial):
        raise OSError(message) from error


def _write_review_spools(git, spools, declarations):
    expected = [oid for oid, _, _, _ in declarations]
    try:
        raw = git.call(
            "hash-object",
            "-w",
            "--no-filters",
            "--stdin-paths",
            input=_quoted_paths(spools),
        )
    except _GitTimeout as error:
        _check_timed_out_object_ids(
            error, expected, "Saved review byte object write changed"
        )
        raise
    if raw.decode().splitlines() != expected:
        raise OSError("Saved review byte object write changed")
    verify_blobs(
        [*git.prefix, "cat-file", "--batch"],
        env=git.env,
        objects=tuple(declarations),
    )


def _control_objects(git, requested, cache):
    missing = {oid: kind for oid, kind in requested.items() if oid not in cache}
    if missing:
        raw = git.call(
            "cat-file",
            "--batch",
            input="".join(oid + "\n" for oid in missing).encode("ascii"),
        )
        offset = 0
        for oid, kind in missing.items():
            end = raw.find(b"\n", offset)
            if end < 0 or end - offset > 128:
                raise OSError("Invalid owned control-object header")
            fields = raw[offset:end].split()
            if (
                len(fields) != 3
                or fields[:2] != [oid.encode("ascii"), kind.encode("ascii")]
                or not fields[2].isdigit()
            ):
                raise OSError("Owned control-object type or identity changed")
            size = int(fields[2])
            offset = end + 1
            body = raw[offset : offset + size]
            if len(body) != size or raw[offset + size : offset + size + 1] != b"\n":
                raise OSError("Incomplete owned control object")
            actual = hashlib.sha1(
                kind.encode() + b" " + str(size).encode() + b"\0" + body,
                usedforsecurity=False,
            ).hexdigest()
            if actual != oid:
                raise OSError("Owned control-object bytes do not match their Git name")
            cache[oid] = (kind, body)
            offset += size + 1
        if (
            offset != len(raw)
            or sum(len(body) + 128 for _, body in cache.values()) > OUTPUT_BUDGET
        ):
            raise OSError("Owned control graph exceeds its bounded observation budget")
    if any(cache[oid][0] != kind for oid, kind in requested.items()):
        raise OSError("Owned object has inconsistent graph roles")
    return {oid: cache[oid][1] for oid in requested}


_REVIEW_BYTES_KEY = "__brz2obsidian_review_blob__"


def _stored_model_fields(value):
    """Mirror intentional field omission without copying large review payloads."""
    if isinstance(value, (ExactContent, OpaqueContent)):
        for name, _ in legacy_content_fields(value):
            yield name
        return
    for name, field in type(value).model_fields.items():
        if field.exclude_if is None or not field.exclude_if(getattr(value, name)):
            yield name


def _review_shape(saved):
    """Keep exact S1 values while naming each distinct byte value once."""
    payloads = {}

    def project(value):
        if type(value) is bytes:
            sha = hashlib.sha256(value).hexdigest()
            if sha in payloads and payloads[sha] != value:
                raise OSError("Saved review bytes have an ambiguous digest")
            payloads[sha] = value
            return {_REVIEW_BYTES_KEY: sha}
        if hasattr(type(value), "model_fields"):
            return {
                name: project(getattr(value, name))
                for name in _stored_model_fields(value)
            }
        if isinstance(value, (tuple, list)):
            return [project(item) for item in value]
        if type(value) in (str, int, float, bool) or value is None:
            return value
        raise OSError("Saved review contains an unsupported value")

    envelope = {
        "schema_id": "brz2obsidian.saved-review-refs",
        "schema_version": 1,
        "record": project(saved),
    }
    return json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8"), payloads


def _strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate saved-review field")
        result[key] = value
    return result


def _collect_review_references(value, references):
    if type(value) is dict:
        if _REVIEW_BYTES_KEY in value:
            if (
                set(value) != {_REVIEW_BYTES_KEY}
                or type(value[_REVIEW_BYTES_KEY]) is not str
                or len(value[_REVIEW_BYTES_KEY]) != 64
                or set(value[_REVIEW_BYTES_KEY]) - set("0123456789abcdef")
            ):
                raise ValueError("Invalid saved-review byte reference")
            references.add(value[_REVIEW_BYTES_KEY])
        else:
            for item in value.values():
                _collect_review_references(item, references)
    elif type(value) is list:
        for item in value:
            _collect_review_references(item, references)
    elif type(value) not in (str, int, float, bool, type(None)):
        raise ValueError("Invalid saved-review scalar")


def _review_references(raw):
    def invalid_constant(_):
        raise ValueError("Nonfinite saved-review scalar")

    envelope = json.loads(
        raw, object_pairs_hook=_strict_pairs, parse_constant=invalid_constant
    )
    if (
        type(envelope) is not dict
        or set(envelope) != {"schema_id", "schema_version", "record"}
        or envelope["schema_id"] != "brz2obsidian.saved-review-refs"
        or type(envelope["schema_version"]) is not int
        or envelope["schema_version"] != 1
    ):
        raise ValueError("Unsupported saved-review reference envelope")
    references = set()

    _collect_review_references(envelope["record"], references)
    return envelope["record"], references


def _restore_review(record, payloads, manifest):
    def restore(value):
        if type(value) is dict:
            if _REVIEW_BYTES_KEY in value:
                return payloads[value[_REVIEW_BYTES_KEY]]
            return {key: restore(item) for key, item in value.items()}
        if type(value) is list:
            return tuple(restore(item) for item in value)
        return value

    saved = SavedReview.model_validate(restore(record))
    if manifest.boundary == "local" and not manifest.proposed:
        from brz2obsidian.core.resume import _load_local_review

        restored = _load_local_review(saved)
    else:
        restored = load_review(saved)
    if restored.status != "loaded":
        raise OSError("Saved S1 review is unavailable or invalid")
    return restored.loaded


class _ExactBlobSink:
    def __init__(self, expected):
        self.expected = memoryview(expected)
        self.offset = 0

    def write(self, block):
        end = self.offset + len(block)
        if self.expected[self.offset : end] != block:
            raise OSError("Retained review blob differs from the owned export")
        self.offset = end
        return len(block)


def _verify_review_batches(git, declarations, *, compact):
    argv = [*git.prefix, "cat-file", "--batch"]
    if compact:
        complete = tuple(declarations())
        try:
            verify_blobs(argv, env=git.env, objects=complete, timeout=120)
        except _GitTimeout:
            del complete
        else:
            return
    for batch in batched(declarations(), 32):
        verify_blobs(argv, env=git.env, objects=batch, timeout=120)


class _ApplyReviewOwners(ExitStack):
    """Retain exact local and prepared proofs during otherwise fresh inspections."""

    def __init__(
        self,
        *,
        local_owner=None,
        retain_prepared=False,
        memory_spool=False,
        cancel=None,
    ):
        super().__init__()
        self._proofs = {}
        self._local_owner = local_owner
        self._retain_prepared = retain_prepared
        self._memory_spool = memory_spool
        self._resume_cancel = cancel
        self._borrowed_session = None
        self._prepared_export = None
        self._prepared_metadata = None
        self._read_cancelled = False
        self._checkpoint_graphs = (
            local_owner._checkpoint_graphs
            if type(local_owner) is _ApplyReviewOwners
            else {}
        )

    def _retain_prepared_export(self, git, commit, manifest, export):
        if (
            self._retain_prepared
            and type(self._local_owner) is _ApplyReviewOwners
            and manifest.boundary == "prepared"
            and manifest.recovery_direction is None
            and manifest.undo_of_receipt_commit is None
            and self._prepared_export is None
            and export is not None
            and len(export.raw) <= 2 * 1024 * 1024
            and sum(value.identity.size for value in export.values.values())
            <= 2 * 1024 * 1024
        ):
            self._prepared_export = (git.root, commit, manifest, export)

    def _read_prepared_export(self, git, manifest, verified, commit, include_review):
        from brz2obsidian.core.resume import _load_result

        root, expected_commit, expected_manifest, export = self._prepared_export
        if (git.root, commit) != (root, expected_commit):
            return None
        if manifest != expected_manifest:
            raise OSError("Captured prepared checkpoint has a different manifest")
        if available_memory() < 4 * len(export.raw) + 64 * 1024 * 1024:
            return None
        export.check()
        references = frozenset(export.values)
        available = _review_role_objects(manifest, references)

        def declarations():
            yield (
                manifest.review_object,
                manifest.review_size,
                manifest.review_sha256,
                _ExactBlobSink(export.raw),
            )
            for sha in sorted(references):
                oid, size = available[sha]
                if size != export.values[sha].identity.size:
                    raise OSError("Captured prepared payload differs in size")
                with io.BytesIO() as expected:
                    export.copy(sha, expected)
                    yield oid, size, sha, _ExactBlobSink(expected.getvalue())

        _verify_review_batches(git, declarations, compact=32 <= len(references) < 128)
        export.check()
        if self._prepared_metadata is None:
            review = _load_result("loaded", export.saved, export.effects).loaded
            self._prepared_metadata = (
                _checkpoint_review_metadata(manifest, review, references),
                review,
            )
        metadata, review = self._prepared_metadata
        verified.update(available[sha][0] for sha in references)
        return metadata, review if include_review else None

    def _borrow_local(self, observed, checkpoint):
        """Attach an admitted Current observation to the exact retained owner."""
        proof = self._proofs.get("local")
        if self._borrowed_session is not None or proof is None:
            return None
        root, commit, manifest, session, _, review, _ = proof
        if (root, commit, manifest) != (
            observed._root,
            checkpoint.locator.commit,
            checkpoint.manifest,
        ) or session._ledger.budget.cancel is not self._resume_cancel:
            return None
        self._read_proof(
            _Git(root, observed._executable),
            manifest,
            set(),
            commit,
            False,
            self,
            "local",
        )
        session._content._attach(observed)
        session._batch_current = True
        session._content._spool_acquisitions = True
        self._borrowed_session = session
        return session, review

    def read(self, git, manifest, verified, *, commit, include_review):
        cache = self if self._local_owner is None else self._local_owner
        local = cache._proofs.get("local")
        if (
            self._retain_prepared
            and local is not None
            and manifest.boundary == "prepared"
            and manifest.recovery_direction is None
            and manifest.undo_of_receipt_commit is None
            and (git.root, manifest.previous) == local[:2]
        ):
            if self._prepared_export is not None:
                prepared = self._read_prepared_export(
                    git, manifest, verified, commit, include_review
                )
                if prepared is not None:
                    return prepared
            return self._read_proof(
                git, manifest, verified, commit, include_review, self, "prepared"
            )
        if manifest.boundary == "local" and not manifest.proposed:
            return cache._read_proof(
                git, manifest, verified, commit, include_review, self, "local"
            )
        return None

    def _read_proof(self, git, manifest, verified, commit, include_review, phase, role):
        proof = self._proofs.get(role)
        if proof is None:
            if not include_review:
                return None
            with ExitStack() as trial:
                review, references, session = _read_owned_checkpoint_review(
                    git,
                    manifest,
                    verified,
                    commit=commit,
                    owners=trial,
                    memory_spool=self._memory_spool,
                    resume_cancel=self._resume_cancel if role == "local" else None,
                )
                metadata = _checkpoint_review_metadata(
                    manifest, review, frozenset(references)
                )
                if metadata[10] == "source_update":
                    self.enter_context(trial.pop_all())
                    self._proofs[role] = (
                        git.root,
                        commit,
                        manifest,
                        session,
                        metadata,
                        review,
                        tuple(session._closure.view.records.values()),
                    )
                    self.callback(self._proofs.pop, role)
                else:
                    phase.enter_context(trial.pop_all())
            return metadata, review

        root, retained_commit, retained_manifest, session, metadata, review, records = (
            proof
        )
        if (git.root, commit) != (root, retained_commit):
            return None
        if manifest != retained_manifest:
            raise OSError("Repeated checkpoint has a different manifest")

        references = metadata[3]
        available = _review_role_objects(manifest, references)
        envelope = (
            manifest.review_object,
            manifest.review_size,
            manifest.review_sha256,
            None,
        )

        def declarations():
            yield envelope
            for sha in sorted(references):
                oid, size = available[sha]
                yield oid, size, sha, None

        compact = (
            self._resume_cancel is not None
            and 32 <= len(references) < 128
            and manifest.review_size + sum(available[sha][1] for sha in references)
            <= 4 * 1024 * 1024
        )
        _verify_review_batches(git, declarations, compact=compact)
        session._verify_retained_backings(records)
        verified.update(available[sha][0] for sha in references)
        return metadata, review if include_review else None


class CheckpointReviewMemo:
    """Per-traversal review metadata with at most one retained parsed tip.

    Callers own full checkpoint admission, as for ``read_checkpoint_review``.
    Requesting the parsed review does not bypass declaration or closure checks.
    """

    def __init__(self):
        self._entries = {}
        self._tip_key = None
        self._tip_review = None

    def _read_with_owners(
        self, git, manifest, verified, commit, include_review, _owners
    ):
        if type(_owners) is _ApplyReviewOwners and commit is not None:
            try:
                retained = _owners.read(
                    git,
                    manifest,
                    verified,
                    commit=commit,
                    include_review=include_review,
                )
            except OSError as error:
                from brz2obsidian.application.review_session import _ReviewCancelled

                if isinstance(error, _ReviewCancelled):
                    _owners._read_cancelled = True
                raise
            if retained is not None:
                return retained
        return None

    def _check_shared_review(self, key, manifest):
        metadata = self._entries[key]
        if metadata[:2] != (manifest.review_size, manifest.review_sha256):
            raise OSError("Shared review payload has inconsistent declarations")
        role_hashes = {
            row.sha256
            for role in (
                manifest.source,
                manifest.vault,
                manifest.preimage,
                manifest.proposed,
            )
            for row in role
        }
        if metadata[3] - role_hashes != {row.sha256 for row in manifest.review_content}:
            raise OSError("Repeated saved review references changed their owned graph")

    def read(
        self,
        git,
        manifest,
        verified,
        *,
        include_review=False,
        commit=None,
        _owners=None,
    ):
        retained = self._read_with_owners(
            git, manifest, verified, commit, include_review, _owners
        )
        if retained is not None:
            return retained
        key = (
            manifest.review_object,
            manifest.boundary == "local" and not manifest.proposed,
        )
        review = None
        if key not in self._entries:
            if include_review or commit is None:
                review, references = (
                    read_checkpoint_review(git, manifest, verified)
                    if _owners is None
                    else _read_owned_checkpoint_review(
                        git, manifest, verified, commit=commit, owners=_owners
                    )[:2]
                )
                self._entries[key] = _checkpoint_review_metadata(
                    manifest, review, references
                )
            else:
                self._entries[key] = _read_checkpoint_review_metadata(
                    git,
                    manifest,
                    verified,
                    commit=commit,
                )
        else:
            self._check_shared_review(key, manifest)
        if include_review:
            if self._tip_key == key:
                review = self._tip_review
            elif review is None:
                review, _ = (
                    read_checkpoint_review(git, manifest, verified)
                    if _owners is None
                    else _read_owned_checkpoint_review(
                        git, manifest, verified, commit=commit, owners=_owners
                    )[:2]
                )
            if self._tip_review is None:
                self._tip_key, self._tip_review = key, review
        return self._entries[key], review if include_review else None


def _checkpoint_review_metadata(manifest, review, references):
    from .attachment_ownership import review_ownership_claims

    return (
        manifest.review_size,
        manifest.review_sha256,
        _review_meaning(review.saved),
        references,
        _review_parent_fingerprint(review),
        _review_source_signature(review.saved),
        review.saved.plan.facts.baseline_identity,
        _initial_absence_review(review),
        review_ownership_claims(review.saved.plan, review.historical_effects),
        _review_queries(review),
        review.saved.plan.facts.format_operation.kind,
    )


def _read_checkpoint_review_metadata(git, manifest, verified, *, commit):
    with ExitStack() as owners:
        review, references, _ = _read_owned_checkpoint_review(
            git, manifest, verified, commit=commit, owners=owners
        )
        return _checkpoint_review_metadata(manifest, review, references)


def _read_owned_checkpoint_review(
    git, manifest, verified, *, commit, owners, memory_spool=False, resume_cancel=None
):
    from brz2obsidian.application.review_session import ReviewSession

    if type(owners) not in (ExitStack, _ApplyReviewOwners):
        raise OSError("Lexical retained review ownership required")
    record, references, available = _review_reference_graph(git, manifest)
    if memory_spool:
        kind = record
        for key in ("plan", "facts", "format_operation", "kind"):
            kind = kind.get(key) if type(kind) is dict else None
        memory_spool = kind == "source_update"
    session = owners.enter_context(
        ReviewSession._retained_review(
            git,
            manifest,
            commit,
            capacity=available_memory(),
            memory_spool=memory_spool,
            cancel=resume_cancel,
        )
    )
    session._batch_current = memory_spool and resume_cancel is not None
    review = session._load_retained(
        record,
        available,
        references,
        local=manifest.boundary == "local" and not manifest.proposed,
    )
    verified.update(available[sha][0] for sha in references)
    return review, references, session


def _review_reference_graph(git, manifest):
    size = manifest.review_size
    if available_memory() < 4 * size + 64 * 1024 * 1024:
        raise OSError("Insufficient current memory for the saved review envelope")
    base = git.inspection.temporary_base()
    if base is None or shutil.disk_usage(base).free < size + 8 * 1024 * 1024:
        raise OSError("Insufficient current temporary space for saved review")
    with tempfile.TemporaryFile(mode="w+b", dir=base) as output:
        verify_blobs(
            [*git.prefix, "cat-file", "--batch"],
            env=git.env,
            objects=((manifest.review_object, size, manifest.review_sha256, output),),
            timeout=120,
        )
        output.seek(0)
        raw = output.read(size + 1)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != manifest.review_sha256:
        raise OSError("Saved review spool bytes changed")
    try:
        record, references = _review_references(raw)
    except RecursionError as error:
        raise OSError("Saved review envelope exceeds its bounded nesting") from error
    return record, references, _review_role_objects(manifest, references)


def _review_role_objects(manifest, references):
    all_roles = (
        *manifest.source,
        *manifest.vault,
        *manifest.preimage,
        *manifest.proposed,
        *manifest.review_content,
    )
    available = {}
    for row in all_roles:
        old = available.setdefault(row.sha256, (row.object_id, row.size))
        if old != (row.object_id, row.size):
            raise OSError("Saved review digest has inconsistent owned objects")
    if not references.issubset(available) or {
        row.sha256 for row in manifest.review_content
    } != references - {
        row.sha256
        for row in (
            *manifest.source,
            *manifest.vault,
            *manifest.preimage,
            *manifest.proposed,
        )
    }:
        raise OSError("Saved review references are not closed over the owned graph")
    return available


def read_checkpoint_review(git, manifest, verified):
    """Return an inline review only within caller-owned full history admission.

    This result alone is not authority. The unchanged returned-tip/explicit
    target path verifies its envelope, five-role closure and all payloads.
    """
    record, references, available = _review_reference_graph(git, manifest)
    size = manifest.review_size
    if (
        available_memory()
        < 4 * size + 9 * sum(available[sha][1] for sha in references) + 64 * 1024 * 1024
    ):
        raise OSError("Insufficient current memory for the saved S1 review")
    sinks = {sha: io.BytesIO() for sha in references}
    declarations = tuple(
        (available[sha][0], available[sha][1], sha, sinks[sha])
        for sha in sorted(references)
    )
    verify_blobs(
        [*git.prefix, "cat-file", "--batch"],
        env=git.env,
        objects=declarations,
        timeout=120,
    )
    verified.update(available[sha][0] for sha in references)
    try:
        restored = _restore_review(
            record, {sha: sink.getvalue() for sha, sink in sinks.items()}, manifest
        )
    except RecursionError as error:
        raise OSError("Saved review value exceeds its bounded nesting") from error
    return restored, references


class _ReviewQueries(NamedTuple):
    local: tuple
    selected: tuple | None
    requirements: tuple
    grants: tuple


class _RolePolicy(NamedTuple):
    subjects: tuple
    fingerprints: tuple
    requirements: tuple
    grants: tuple
    context_basis: str
    memo_basis: str
    prepared_commit: str | None


def _review_queries(review):
    """Retain finite queries and grants, never the parsed review's byte bodies."""
    from brz2obsidian.application.update_subjects import review_subjects

    from .vault_apply import _review_subjects

    plan = review.saved.plan
    effects = review.historical_effects
    return _ReviewQueries(
        review_subjects(plan.producer_facts, plan, effects=effects)
        if plan.preflight.consents
        else (),
        _review_subjects(plan, effects)
        if effects is not None and effects.status == "selected"
        else None,
        tuple(plan.preflight.consents),
        tuple(
            grant
            for grant in plan.consents
            if not any(
                requirement.change_id == "consent:" + grant.consent_id
                for requirement in plan.requirements
            )
        ),
    )


def _role_policy(association, manifest, queries, *, pending_format=False):
    if (manifest.boundary not in ("local", "result") and not pending_format) or (
        manifest.boundary == "local" and manifest.proposed
    ):
        return None
    if manifest.boundary != "local" and (queries is None or queries.selected is None):
        return None
    return _RolePolicy(
        (
            ()
            if queries is None
            else queries.local
            if manifest.boundary == "local"
            else queries.selected
        ),
        (manifest.policy_fingerprint, manifest.policy_continuity_fingerprint),
        () if queries is None else queries.requirements,
        () if queries is None else queries.grants,
        digest(
            {
                "association": association.model_dump(mode="json"),
                "identity": manifest.identity.model_dump(mode="json"),
                "source": [row.model_dump(mode="json") for row in manifest.source],
                "recovery_gaps": manifest.recovery_gaps,
            }
        ),
        digest(
            manifest.model_dump(
                mode="json",
                exclude={
                    "generation",
                    "previous",
                    "semantic_fingerprint",
                    "review_content",
                    "review_object",
                    "review_size",
                    "review_sha256",
                    "observed_source",
                    "reviewed_source",
                    "vault",
                    "preimage",
                    "policy_fingerprint",
                    "policy_continuity_fingerprint",
                },
            )
        ),
        manifest.previous if manifest.boundary == "result" else None,
    )


class _CheckpointRole(NamedTuple):
    """Validated scalar lineage; raw control bodies remain per-generation."""

    commit: str
    previous: str | None
    generation: int
    boundary: str
    operation_intent_commit: str | None
    undo_of_receipt_commit: str | None
    recovery_origin_intent_commit: str | None
    recovery_previous_operation_commit: str | None
    recovery_direction: str | None
    memo_fingerprint: str | None = None
    review_parent_fingerprint: str | None = None
    onboarding_absence: bool = False
    review_context_fingerprint: str | None = None
    policy_context: _RolePolicy | None = None
    review_kind: str | None = None
    identity: OutputIdentity | None = None
    review_baseline_identity: OutputIdentity | None = None
    baseline_source: tuple | None = None
    reviewed_payload: str | None = None
    collection_baseline_commit: str | None = None
    discarded_review: str | None = None
    saved_proposal_id: str | None = None
    collection_preparation_owner: str | None = None
    abandoned_collection_preparation: str | None = None


def _review_context_fingerprint(association, manifest):
    """Project common context; callers consume roles only after graph validation."""
    if manifest.boundary not in ("result", "local") or (
        manifest.boundary == "local" and manifest.proposed
    ):
        return None
    return digest(
        {
            "association": association.model_dump(mode="json"),
            "identity": manifest.identity.model_dump(mode="json"),
            "source": [row.model_dump(mode="json") for row in manifest.source],
            "recovery_gaps": manifest.recovery_gaps,
            "policy_fingerprint": manifest.policy_fingerprint,
            "policy_continuity_fingerprint": manifest.policy_continuity_fingerprint,
        }
    )


def _initial_absence_review(review):
    plan = review.saved.plan
    preflight = plan.preflight
    return (
        plan.facts.format_operation.kind in ("onboarding", "collection_import")
        and preflight.operation_status == "idle"
        and preflight.state_status == "absent"
        and preflight.state_schema is None
        and preflight.state_version is None
    )


def _review_parent_fingerprint(review):
    preflight = review.saved.plan.preflight
    if (
        preflight.operation_status == "idle"
        and preflight.state_status == "supported"
        and preflight.state_schema == "brz2obsidian.checkpoint-manifest"
        and preflight.state_version == 1
    ) or _initial_absence_review(review):
        return preflight.state_fingerprint
    return None


class _LooseBlobCheck:
    """Check one bounded loose object without materializing its payload."""

    def __init__(self, oid, size, sha):
        self.oid = oid
        self.size = size
        self.sha = sha
        self.header = f"blob {size}\0".encode("ascii")
        self.limit = len(self.header) + size
        self.decoder = zlib.decompressobj()
        self.git_hash = hashlib.sha1()
        self.payload_hash = hashlib.sha256()
        self.header_bytes = bytearray()
        self.count = 0
        self.invalid = False

    def write(self, block):
        if self.invalid:
            return len(block)
        pending = block
        while pending and not self.invalid:
            remaining = self.limit - self.count
            try:
                decoded = self.decoder.decompress(
                    pending, min(1024 * 1024, remaining + 1)
                )
            except zlib.error:
                self.invalid = True
                break
            if self.decoder.unused_data or self.count + len(decoded) > self.limit:
                self.invalid = True
                break
            self.git_hash.update(decoded)
            self.count += len(decoded)
            prefix_needed = max(0, len(self.header) - len(self.header_bytes))
            self.header_bytes.extend(decoded[:prefix_needed])
            self.payload_hash.update(decoded[prefix_needed:])
            if self.header_bytes != self.header[: len(self.header_bytes)]:
                self.invalid = True
            if self.decoder.unconsumed_tail == pending and not decoded:
                self.invalid = True
            pending = self.decoder.unconsumed_tail
        return len(block)

    def valid(self):
        return (
            not self.invalid
            and self.decoder.eof
            and self.count == self.limit
            and self.header_bytes == self.header
            and self.git_hash.hexdigest() == self.oid
            and self.payload_hash.hexdigest() == self.sha
        )


def _damaged_loose_payload(root, row):
    oid, size, sha, _ = row
    path = root / ".git/objects" / oid[:2] / oid[2:]
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    verifier = _LooseBlobCheck(oid, size, sha)
    observe_file(root / ".git/objects", path, sink=verifier, prefix_limit=0)
    if verifier.valid():
        raise OSError("A valid loose object has an uncertain Git read failure")
    return True


@dataclass(frozen=True)
class _MetadataCheckpoint:
    """Full graph projection; an explicit lexical owner may retain its review."""

    locator: object
    manifest: object
    metadata: object
    status: str = "valid"
    review: object = None
    discarded_manifest: CheckpointManifest | None = None
    collection_baselines: dict | None = None


@dataclass(frozen=True)
class _MetadataHistory:
    admission: object
    checkpoint: object
    status: str = "intact"


def _checkpoint_graph_entries(git, current):
    raw = git.call("ls-tree", "-r", "-t", "-z", current)
    entries = {}
    for row in raw.split(b"\0"):
        if not row:
            continue
        data, path = row.split(b"\t", 1)
        mode, kind, oid = data.decode("ascii").split()
        path = path.decode("utf-8")
        if path in entries or not _safe_relative(path):
            raise OSError("Unsafe or duplicate owned graph path")
        if kind not in ("blob", "tree"):
            raise OSError("Unknown owned graph object kind")
        entries[path] = mode, kind, oid
    root_names = {path for path in entries if "/" not in path}
    required_names = {
        "association.json",
        "manifest.json",
        "source",
        "vault",
        "preimage",
        "proposed",
    }
    if root_names not in (
        required_names,
        required_names | {"review.json"},
        required_names | {"review.json", "review-content"},
    ):
        raise OSError("Required checkpoint graph roles are missing or unknown")
    return raw, entries


def _checkpoint_graph(git, current, controls, owners):
    graphs = owners._checkpoint_graphs if type(owners) is _ApplyReviewOwners else None
    key = git.root, current
    previous = graphs.get(key) if graphs is not None else None
    if previous is not None:
        requested, original, decoded = previous
        fresh = _control_objects(git, requested, controls)
        if fresh != original:
            raise OSError("Owned checkpoint control bytes changed")
        return decoded

    commit_raw = _control_objects(git, {current: "commit"}, controls)[current]
    headers, separator, _ = commit_raw.partition(b"\n\n")
    trees = [
        line[5:].decode("ascii")
        for line in headers.splitlines()
        if line.startswith(b"tree ")
    ]
    parents = [
        line[7:].decode("ascii")
        for line in headers.splitlines()
        if line.startswith(b"parent ")
    ]
    if (
        not separator
        or len(trees) != 1
        or any(
            len(oid) != 40 or set(oid) - set("0123456789abcdef")
            for oid in (*trees, *parents)
        )
    ):
        raise OSError("Invalid owned commit edges")
    raw, entries = _checkpoint_graph_entries(git, current)
    requested = {current: "commit", trees[0]: "tree"}
    requested.update(
        {oid: "tree" for _, kind, oid in entries.values() if kind == "tree"}
    )
    for path in ("association.json", "manifest.json"):
        mode, kind, oid = entries[path]
        if (mode, kind) != ("100644", "blob"):
            raise OSError("Invalid checkpoint metadata edge")
        requested[oid] = "blob"
    objects = _control_objects(git, requested, controls)
    manifest = CheckpointManifest.model_validate_json(
        objects[entries["manifest.json"][2]]
    )
    actual_association = VaultAssociation.model_validate_json(
        objects[entries["association.json"][2]]
    )

    decoded = parents, entries, manifest, actual_association
    if (
        graphs is not None
        and len(graphs) < 4
        and len(raw) <= 128 * 1024
        and sum(len(value) for value in objects.values()) <= 256 * 1024
    ):
        graphs[key] = requested, objects, decoded
    return decoded


def _bound_checkpoint_locator(root, git, targets, trusted_association):
    locator_path = root / ".brz2obsidian/locator.json"
    if not locator_path.exists():
        if (root / ".brz2obsidian").exists() or git.call(
            "for-each-ref", "--format=%(refname)", "refs/brz2obsidian/imports"
        ):
            raise OSError("Owned graph or metadata has no current locator")
        if targets is not None:
            raise OSError("Requested operation checkpoint has no owned history")
        return CheckpointRead(
            schema_id="brz2obsidian.checkpoint-read",
            schema_version=1,
            status="absent",
            code="absent",
            locator=None,
            manifest=None,
            review=None,
            message="No current checkpoint locator.",
        )
    _, _, raw, _ = observe_file(root, locator_path, prefix_limit=OUTPUT_BUDGET + 1)
    locator = CheckpointLocator.model_validate_json(raw)
    association = locator.association
    if trusted_association is None:
        if association.vault_anchor != verify_directory(
            root
        ) or association.git_anchor != verify_directory(root / ".git"):
            raise OSError("Association physical context does not match")
    elif association != trusted_association:
        raise OSError("Copied association differs from the target-owned association")
    expected_id = digest(
        (
            association.vault_id,
            association.import_id,
            association.collection_id,
            association.module_id,
        )
    )
    expected_ref = "refs/brz2obsidian/imports/" + expected_id + "/checkpoints"
    if association.association_id != expected_id or association.ref != expected_ref:
        raise OSError("Invalid stable checkpoint association")
    return _locator_at_owned_tip(root, git, locator, trusted_association)


def _locator_at_owned_tip(root, git, locator, trusted_association):
    names = set(os.listdir(root / ".brz2obsidian"))
    tip = git.call("rev-parse", "--verify", locator.association.ref).decode().strip()
    if tip == locator.commit and names == {"locator.json"}:
        return locator
    if trusted_association is None:
        from .collection_result_locator import locator_after_scoped_result
        from .unpublished_collection import locator_after_unpublished_preparation

        advanced = locator_after_unpublished_preparation(root, git, locator, tip, names)
        if advanced is not None:
            return advanced
        result_locator = locator_after_scoped_result(root, git, locator, tip, names)
        if result_locator is not None:
            return result_locator
    raise OSError("Owned checkpoint root or locator metadata changed")


class _CheckpointChain(NamedTuple):
    manifest: CheckpointManifest
    review: object
    metadata: object
    target_records: dict
    pending: tuple
    ownership_demands: list
    ownership_roles: list
    discarded_review: object
    discarded_manifest: CheckpointManifest | None
    collection_baselines: dict


def _check_checkpoint_edges(
    association, generation, parents, entries, manifest, actual_association
):
    if (
        actual_association != association
        or manifest.association_id != association.association_id
        or manifest.generation != generation
        or manifest.collection_record_path is None
        and (manifest.identity.collection_id, manifest.identity.module_id)
        != (association.collection_id, association.module_id)
    ):
        raise OSError(
            "Retained checkpoint identity, generation or association disagrees"
        )
    if parents != ([manifest.previous] if manifest.previous is not None else []) or (
        generation == 1
    ) != (manifest.previous is None):
        raise OSError("Checkpoint history has no matching real parent edge")
    if ("review-content" in entries) != bool(manifest.review_content):
        raise OSError("Saved review content has no matching role tree")


def _add_checkpoint_role_blobs(role, manifest, entries, blobs):
    if entries[role][:2] != ("040000", "tree"):
        raise OSError("Checkpoint role is not a real tree")
    expected = getattr(manifest, role.replace("-", "_"))
    actual = sorted(
        (path[len(role) + 1 :], mode, oid)
        for path, (mode, kind, oid) in entries.items()
        if path.startswith(role + "/") and kind == "blob"
    )
    if actual != [(f.path, f.mode, f.object_id) for f in expected]:
        raise OSError("Retained checkpoint graph does not match its inventory")
    directories = {role}
    for entry in expected:
        if not _safe_relative(entry.path):
            raise OSError("Unsafe retained authored path")
        directories.update(
            role + "/" + str(parent).replace("\\", "/")
            for parent in Path(entry.path).parents
            if str(parent) != "."
        )
        declaration = (entry.object_id, entry.size, entry.sha256, None)
        if entry.object_id in blobs and blobs[entry.object_id] != declaration:
            raise OSError("Shared object has inconsistent semantic declarations")
        blobs[entry.object_id] = declaration
    actual_directories = {
        path
        for path, (_, kind, _) in entries.items()
        if kind == "tree" and (path == role or path.startswith(role + "/"))
    }
    if directories != actual_directories:
        raise OSError("Unknown retained tree structure")


def _read_checkpoint_memo(
    review_memo, git, manifest, verified, entries, current, include_review, _owners
):
    review_metadata = review = None
    if manifest.review_object is None:
        if "review.json" in entries:
            raise OSError("Unaccounted saved review")
    else:
        if entries.get("review.json") != ("100644", "blob", manifest.review_object):
            raise OSError("Saved review has no matching graph edge")
        review_metadata, review = review_memo.read(
            git,
            manifest,
            verified,
            include_review=include_review,
            commit=current,
            _owners=_owners,
        )
    return review_metadata, review


def _accumulate_checkpoint_claims(
    manifest, current, review_metadata, association, ownership_demands, ownership_roles
):
    if manifest.review_object is not None:
        claims, missing = review_metadata[8]
        if claims or missing:
            ownership_demands.append(
                (current, manifest.recovery_origin_intent_commit, claims, missing)
            )
    if ownership_demands:
        ownership_roles.append(
            _CheckpointRole(
                current,
                manifest.previous,
                manifest.generation,
                manifest.boundary,
                manifest.operation_intent_commit,
                manifest.undo_of_receipt_commit,
                manifest.recovery_origin_intent_commit,
                manifest.recovery_previous_operation_commit,
                manifest.recovery_direction,
                onboarding_absence=review_metadata[7]
                if manifest.review_object is not None
                else False,
                review_context_fingerprint=_review_context_fingerprint(
                    association, manifest
                ),
                policy_context=_role_policy(
                    association,
                    manifest,
                    review_metadata[9] if manifest.review_object is not None else None,
                ),
                review_kind=review_metadata[10]
                if manifest.review_object is not None
                else None,
            )
        )


def _check_checkpoint_meaning(association, manifest, review_metadata, meaning):
    if (
        manifest.collection_record_path is not None
        and manifest.boundary == "local"
        and not manifest.source
        and manifest.discarded_review is None
        and (review_metadata is None or review_metadata[10] != "collection_import")
    ):
        raise OSError("Empty collection baseline lacks a retained import review")
    if manifest.reviewed_source is not None and (
        manifest.review_object is None
        or review_metadata[5] != _binding_signature(manifest.reviewed_source)
        or (
            review_metadata[6]
            if manifest.boundary == "local"
            else manifest.reviewed_source.incoming_identity
        )
        != manifest.identity
    ):
        raise OSError("Retained incoming payload binding disagrees with review")
    if manifest.observed_source is not None and not _source_observation_matches(
        manifest.observed_source, manifest.reviewed_source
    ):
        raise OSError("Retained source observation disagrees with incoming payload")
    if (
        _semantic_meaning(
            association,
            manifest.identity,
            manifest.source,
            manifest.vault,
            manifest.preimage,
            manifest.proposed,
            manifest.recovery_gaps,
            manifest.boundary,
            manifest.policy_fingerprint,
            meaning,
            manifest.operation_intent_commit,
            manifest.recovery_origin_intent_commit,
            manifest.recovery_previous_operation_commit,
            manifest.recovery_direction,
            manifest.undo_of_receipt_commit,
            manifest.observed_source,
            manifest.reviewed_source,
            manifest.discarded_review,
            manifest.collection_record_path,
            manifest.collection_baseline_commit,
            manifest.collection_preparation_owner,
            manifest.abandoned_collection_preparation,
        )
        != manifest.semantic_fingerprint
    ):
        raise OSError("Retained checkpoint semantic interpretation disagrees")


def _accumulate_checkpoint_role(
    checkpoint_roles,
    current,
    manifest,
    review_metadata,
    association,
    is_tip,
    memo_roles,
    format_roles,
):
    format_review = (
        manifest.reviewed_source is not None
        and review_metadata[10] == "format_transition"
        and manifest.preimage == manifest.vault
    )
    if is_tip:
        format_roles = format_review and manifest.boundary in (
            "local",
            "prepared",
        )
    pending_format = (
        format_roles
        and format_review
        and manifest.boundary == "prepared"
        and manifest.undo_of_receipt_commit is None
        and manifest.recovery_direction is None
    )
    memo_roles = memo_roles or pending_format
    checkpoint_roles.append(
        _CheckpointRole(
            current,
            manifest.previous,
            manifest.generation,
            manifest.boundary,
            manifest.operation_intent_commit,
            manifest.undo_of_receipt_commit,
            manifest.recovery_origin_intent_commit,
            manifest.recovery_previous_operation_commit,
            manifest.recovery_direction,
            # A LOCAL review memo records current authored context.
            # Source, policy and lineage retain the parent authority;
            # full graph/semantic validation still binds every byte.
            digest(
                manifest.model_dump(
                    mode="json",
                    exclude={
                        "generation",
                        "previous",
                        "semantic_fingerprint",
                        "review_content",
                        "review_object",
                        "review_size",
                        "review_sha256",
                        "observed_source",
                        "reviewed_source",
                        "vault",
                        "preimage",
                    },
                )
            )
            if memo_roles
            else None,
            review_metadata[4]
            if memo_roles and manifest.review_object is not None
            else None,
            review_metadata[7] if manifest.review_object is not None else False,
            review_context_fingerprint=_review_context_fingerprint(
                association, manifest
            ),
            policy_context=_role_policy(
                association,
                manifest,
                review_metadata[9] if manifest.review_object is not None else None,
                pending_format=pending_format,
            ),
            review_kind=review_metadata[10]
            if manifest.review_object is not None
            else None,
            identity=manifest.identity,
            review_baseline_identity=review_metadata[6] if pending_format else None,
            baseline_source=manifest.source
            if len(checkpoint_roles) == 1
            and checkpoint_roles[0].review_baseline_identity is not None
            else None,
            reviewed_payload=digest(
                manifest.reviewed_source.model_dump(
                    mode="json", exclude={"source_anchor", "generation"}
                )
            )
            if pending_format or format_review and manifest.boundary == "local"
            else None,
            collection_baseline_commit=manifest.collection_baseline_commit,
            discarded_review=manifest.discarded_review,
            saved_proposal_id=(
                manifest.reviewed_source.proposal_id
                if manifest.boundary == "local" and manifest.reviewed_source is not None
                else None
            ),
            collection_preparation_owner=manifest.collection_preparation_owner,
            abandoned_collection_preparation=manifest.abandoned_collection_preparation,
        )
    )
    return memo_roles, format_roles


class _CollectionLineage:
    def __init__(self):
        self.baselines = {}
        self.demands = {}
        self.discard = None
        self.discarded_review = self.discarded_manifest = None
        self.restored = None
        self.restored_parent = None

    def check_discard(self, manifest):
        if self.discard is not None and (
            manifest.boundary != "local"
            or manifest.reviewed_source is None
            or manifest.identity != self.discard.identity
            or manifest.source != self.discard.source
            or manifest.vault != self.discard.vault
            or manifest.recovery_gaps != self.discard.recovery_gaps
        ):
            raise OSError("Discarded review lacks its exact saved checkpoint")
        self.discard = manifest if manifest.discarded_review is not None else None

    def check_restoration(self, current, manifest):
        if self.restored_parent is not None:
            from .unpublished_collection import restored_roles_match

            if current != self.restored_parent or not restored_roles_match(
                self.restored, manifest, current
            ):
                raise OSError("Restored collection review changed its saved authority")
            self.restored = self.restored_parent = None
        elif self.restored is not None:
            if (
                manifest.collection_preparation_owner is None
                or manifest.previous is None
            ):
                raise OSError("Abandoned collection preparation lacks its owner")
            self.restored_parent = manifest.previous
        if manifest.abandoned_collection_preparation is not None:
            if self.restored is not None:
                raise OSError("Overlapping collection preparation restoration")
            self.restored = manifest

    def observe(self, current, manifest, tip_manifest, review_metadata, review):
        if manifest.boundary != "prepared":
            key = (manifest.identity.module_id, manifest.identity.collection_id)
            demanded = self.demands.pop(key, None)
            if demanded is not None and (
                demanded.collection_baseline_commit != current
                or demanded.identity != manifest.identity
                or demanded.collection_record_path != manifest.collection_record_path
                or demanded.source != manifest.source
            ):
                raise OSError(
                    "Collection selection changed its retained source baseline"
                )
            if manifest.collection_baseline_commit is not None:
                self.demands[key] = manifest
            pending_onboarding = (
                manifest.boundary == "local"
                and review_metadata is not None
                and review_metadata[7]
            )
            self.baselines.setdefault(
                key,
                (current, manifest)
                if manifest.source and not pending_onboarding
                else None,
            )
        if tip_manifest is not None and current == tip_manifest.discarded_review:
            self.discarded_review = review
            self.discarded_manifest = manifest


def _read_checkpoint_chain(
    git, locator, targets, linked_intents, checkpoint_roles, _metadata_only, _owners
):
    association = locator.association
    blobs, controls, verified = {}, {}, set()
    review_memo = CheckpointReviewMemo()
    current, generation = locator.commit, locator.generation
    tip_manifest = tip_review = tip_metadata = None
    collections = _CollectionLineage()
    memo_roles = format_roles = False
    target_records = {}
    ownership_demands, ownership_roles = [], []
    visited = set()
    while current is not None:
        if current in visited:
            raise OSError("Cyclic owned checkpoint history")
        visited.add(current)
        parents, entries, manifest, actual_association = _checkpoint_graph(
            git, current, controls, _owners
        )
        _check_checkpoint_edges(
            association, generation, parents, entries, manifest, actual_association
        )
        collections.check_discard(manifest)
        collections.check_restoration(current, manifest)
        for role in (
            "source",
            "vault",
            "preimage",
            "proposed",
            *(("review-content",) if manifest.review_content else ()),
        ):
            _add_checkpoint_role_blobs(role, manifest, entries, blobs)
        review_metadata, review = _read_checkpoint_memo(
            review_memo,
            git,
            manifest,
            verified,
            entries,
            current,
            (not _metadata_only or _owners is not None)
            and (
                tip_manifest is None
                or not _metadata_only
                and current == tip_manifest.discarded_review
                or (targets is not None and current in targets)
            ),
            _owners,
        )
        meaning = review_metadata[2] if manifest.review_object is not None else None
        collections.observe(current, manifest, tip_manifest, review_metadata, review)
        _accumulate_checkpoint_claims(
            manifest,
            current,
            review_metadata,
            association,
            ownership_demands,
            ownership_roles,
        )
        _check_checkpoint_meaning(association, manifest, review_metadata, meaning)
        if linked_intents is not None and manifest.operation_intent_commit is not None:
            linked_intents.append(manifest.operation_intent_commit)
        if tip_manifest is None:
            tip_metadata = (
                review_metadata if manifest.review_object is not None else None
            )
            memo_roles = (
                checkpoint_roles is not None
                and manifest.boundary == "local"
                and manifest.review_object is not None
            )
        if checkpoint_roles is not None:
            memo_roles, format_roles = _accumulate_checkpoint_role(
                checkpoint_roles,
                current,
                manifest,
                review_metadata,
                association,
                tip_manifest is None,
                memo_roles,
                format_roles,
            )
        if tip_manifest is None:
            tip_manifest, tip_review = manifest, review
        if targets is not None and current in targets:
            target_records[current] = manifest, review
        controls = {}
        current, generation = manifest.previous, generation - 1
    if generation != 0 or collections.demands or collections.restored is not None:
        raise OSError("Retained checkpoint chain is incomplete")
    return _CheckpointChain(
        tip_manifest,
        tip_review,
        tip_metadata,
        target_records,
        tuple(row for oid, row in blobs.items() if oid not in verified),
        ownership_demands,
        ownership_roles,
        collections.discarded_review,
        collections.discarded_manifest,
        collections.baselines,
    )


def _checkpoint_payload_responses(root, git, pending, damaged_payloads):
    query = b"".join(row[0].encode("ascii") + b"\n" for row in pending)
    if len(query) > OUTPUT_BUDGET:
        raise OSError("Retained payload request exceeds its control budget")
    try:
        responses = git.call(
            "cat-file",
            "--batch-check=%(objectname) %(objecttype) %(objectsize)",
            input=query,
        ).splitlines()
    except OSError:
        responses = ()
    if not responses and damaged_payloads is not None:
        responses = []
        for row in pending:
            oid = row[0]
            try:
                response = git.call(
                    "cat-file",
                    "--batch-check=%(objectname) %(objecttype) %(objectsize)",
                    input=oid.encode("ascii") + b"\n",
                ).strip()
            except OSError:
                if not _damaged_loose_payload(root, row):
                    raise
                response = None
            responses.append(response)
    return responses


def _separate_unavailable_checkpoint_payloads(root, git, pending, damaged_payloads):
    responses = _checkpoint_payload_responses(root, git, pending, damaged_payloads)
    if len(responses) != len(pending):
        raise OSError("Retained payload inventory has no complete Git response")
    available, absent, damaged = [], [], []
    for row, response in zip(pending, responses, strict=True):
        oid, size, _, _ = row
        if response == f"{oid} blob {size}".encode("ascii"):
            available.append(row)
        elif response is None:
            damaged.append(row)
        elif response == f"{oid} missing".encode("ascii"):
            if damaged_payloads is not None and _damaged_loose_payload(root, row):
                damaged.append(row)
            else:
                absent.append(row)
        else:
            raise OSError("Retained payload has a wrong type or size")
    return tuple(available), absent, damaged


def _verify_checkpoint_payloads(root, git, pending, missing_payloads, damaged_payloads):
    absent = damaged = ()
    if (missing_payloads is not None or damaged_payloads is not None) and pending:
        pending, absent, damaged = _separate_unavailable_checkpoint_payloads(
            root, git, pending, damaged_payloads
        )
    try:
        verify_blobs(
            [*git.prefix, "cat-file", "--batch"],
            env=git.env,
            objects=pending,
            timeout=120,
        )
    except OSError:
        if damaged_payloads is None:
            raise
        for row in pending:
            try:
                verify_blobs(
                    [*git.prefix, "cat-file", "--batch"],
                    env=git.env,
                    objects=(row,),
                    timeout=120,
                )
            except OSError:
                if _damaged_loose_payload(root, row):
                    damaged.append(row)
                else:
                    raise
    return absent, damaged


def _validate_checkpoint_claims(
    root, git, locator, chain, ownership_demands_out, trusted_association, _owners
):
    association = locator.association
    if chain.ownership_demands:
        from .attachment_ownership import validate_history_claims

        if ownership_demands_out is not None:
            ownership_demands_out.append(
                (
                    association,
                    tuple(chain.ownership_roles),
                    tuple(chain.ownership_demands),
                )
            )
        elif any(role.boundary == "result" for role in chain.ownership_roles) or any(
            claim.continuation is not None
            for _, _, claims, _ in chain.ownership_demands
            for claim in claims
        ):
            from .vault_apply import _inspect_update_status

            completed_observations = []
            _inspect_update_status(
                root,
                observations=completed_observations,
                trusted_association=trusted_association,
                _owners=_owners,
            )
            observation = completed_observations[0] if completed_observations else None
            if (
                observation is None
                or observation.checkpoint.locator != locator
                or observation.checkpoint.manifest != chain.manifest
            ):
                raise OSError("Cleanup history lacks current native operation proof")
        else:
            validate_history_claims(
                git,
                association=association,
                roles=tuple(chain.ownership_roles),
                demands=chain.ownership_demands,
            )


def _checkpoint_read_result(locator, chain, targets, _metadata_only, _owners):
    if _metadata_only or _owners is not None:
        if targets is not None and _owners is None:
            raise OSError("Metadata admission cannot return operation review models")
        result = _MetadataCheckpoint(
            locator,
            chain.manifest,
            chain.metadata,
            review=chain.review if _owners is not None else None,
            discarded_manifest=chain.discarded_manifest,
            collection_baselines=chain.collection_baselines,
        )
        if targets is not None:
            if set(chain.target_records) != set(targets):
                raise OSError(
                    "Operation checkpoint is outside the retained owned chain"
                )
            return result, chain.target_records
        return result
    result = CheckpointRead(
        schema_id="brz2obsidian.checkpoint-read",
        schema_version=1,
        status="valid",
        code="validated",
        locator=locator,
        manifest=chain.manifest,
        review=chain.review,
        message="Complete owned local checkpoint graph validated.",
    )
    _retain_review_effects(result.review, chain.review)
    result._discarded_review = chain.discarded_review
    result._collection_baselines = chain.collection_baselines
    if targets is not None:
        if set(chain.target_records) != set(targets):
            raise OSError("Operation checkpoint is outside the retained owned chain")
        return result, chain.target_records
    return result


def _read(
    root,
    git,
    *,
    targets=None,
    linked_intents=None,
    checkpoint_roles=None,
    trusted_association=None,
    missing_payloads=None,
    damaged_payloads=None,
    ownership_demands_out=None,
    _metadata_only=False,
    _owners=None,
):
    locator = _bound_checkpoint_locator(root, git, targets, trusted_association)
    if isinstance(locator, CheckpointRead):
        return locator
    chain = _read_checkpoint_chain(
        git, locator, targets, linked_intents, checkpoint_roles, _metadata_only, _owners
    )
    absent, damaged = _verify_checkpoint_payloads(
        root, git, chain.pending, missing_payloads, damaged_payloads
    )
    if absent or damaged:
        if missing_payloads is not None:
            missing_payloads.extend(absent)
        if damaged_payloads is not None:
            damaged_payloads.extend(damaged)
        return CheckpointRead(
            schema_id="brz2obsidian.checkpoint-read",
            schema_version=1,
            status="refused",
            code="payloads_missing" if not damaged else "payloads_unavailable",
            locator=locator,
            manifest=chain.manifest,
            review=None,
            message="Retained checkpoint graph names unavailable exact Git payloads.",
        )
    _validate_checkpoint_claims(
        root, git, locator, chain, ownership_demands_out, trusted_association, _owners
    )
    return _checkpoint_read_result(locator, chain, targets, _metadata_only, _owners)


def _retain_review_effects(destination, admitted):
    """Keep this read's derived comparison after strict result construction.

    Only trusted local assemblers call this; generic model validation continues
    discarding private state. The cache never supplies current write authority.
    """
    if admitted is not None:
        if destination is None or destination.saved != admitted.saved:
            raise OSError("Admitted saved review changed during result construction")
        destination._historical_effects = admitted.historical_effects


def _history_result(*, status, admission, checkpoint):
    result = VaultHistoryInspection(
        schema_id="brz2obsidian.vault-history-inspection",
        schema_version=1,
        status=status,
        admission=admission,
        checkpoint=checkpoint,
    )
    if checkpoint is not None:
        _retain_review_effects(result.checkpoint.review, checkpoint.review)
        result.checkpoint._discarded_review = checkpoint._discarded_review
        result.checkpoint._collection_baselines = checkpoint._collection_baselines
    return result


def _inspect_retained_history(vault, observation, *, subjects=(), active_operation):
    """Reobserve current admission beneath this call's already validated graph."""
    from brz2obsidian.publication.vault_apply import _OperationObservation

    if not isinstance(observation, _OperationObservation) or active_operation is None:
        raise OSError("Current operation observation and owned lease are required")
    admission, checkpoint = _observe_vault(
        vault,
        subjects=subjects,
        active_operation=active_operation,
        recovery_observation=observation,
    )
    if type(checkpoint) is _MetadataCheckpoint:
        return _MetadataHistory(admission, checkpoint)
    return _history_result(
        status="intact" if checkpoint is not None else "unavailable",
        admission=admission,
        checkpoint=checkpoint,
    )


def _inspect_history(
    vault,
    *,
    subjects=(),
    git_executable=None,
    active_operation=None,
    checkpoint_observation=None,
    recovery_observation=None,
    _capture=None,
    _metadata_only=False,
    new_operation=None,
    _owners=None,
):
    root = Path(vault).absolute()
    admission, history = _observe_vault(
        root,
        subjects=subjects,
        git_executable=git_executable,
        active_operation=active_operation,
        checkpoint_observation=checkpoint_observation,
        recovery_observation=recovery_observation,
        _capture=_capture,
        _new_operation=new_operation,
        _metadata_only=_metadata_only,
        _owners=_owners,
    )
    status = "unavailable"
    try:
        if admission.status == "supported" and admission.repository.kind == "root":
            if history is None:
                history = _read(
                    root, _Git(root, git_executable), _metadata_only=_metadata_only
                )
            status = "intact" if history.status == "valid" else "absent"
            if history.status == "absent":
                authority = digest(
                    (
                        "currently-absent",
                        verify_directory(root),
                        verify_directory(root / ".git"),
                    )
                )
                preflight = admission.preflight.model_copy(
                    update={
                        "operation_status": "idle",
                        "state_status": "absent",
                        "state_schema": None,
                        "state_version": None,
                        "state_fingerprint": authority,
                    }
                )
                admission = admission.model_copy(update={"preflight": preflight})
    except OSError, ValueError, TypeError, UnicodeError:
        history = None
    if _metadata_only:
        return _MetadataHistory(admission, history, status)
    return _history_result(
        status=status,
        admission=admission,
        checkpoint=history,
    )


def inspect_history(
    vault,
    *,
    subjects=(),
    git_executable=None,
    active_operation=None,
    new_operation=None,
):
    return _inspect_history(
        vault,
        subjects=subjects,
        git_executable=git_executable,
        active_operation=active_operation,
        new_operation=new_operation,
    )


class _UpdateRead:
    """Single-use lexical reader; never accepted by capture or apply."""

    def __init__(
        self,
        vault,
        *,
        git_executable=None,
        _metadata_only=False,
        _recovery=False,
        _apply_review_owners=None,
    ):
        self._root = Path(vault).absolute()
        self._executable = git_executable
        self._used = False
        self._open = False
        self._history = None
        self._bound_history = None
        self._inspection = None
        self._idle = None
        self._absence = None
        self._terminal = None
        self._fresh_scope = None
        self._metadata_only = _metadata_only
        self._recovery = _recovery
        self._recovery_status = None
        self._owners = (
            _ApplyReviewOwners(local_owner=_apply_review_owners)
            if _apply_review_owners is not None
            else ExitStack()
        )

    def __enter__(self):
        from .vault_admission import (
            _AbsentHistoryObservation,
            _IdleCheckpointObservation,
        )

        if self._used:
            raise OSError("Update input reader cannot be reused")
        self._used = True
        try:
            self._open = True
            captured = []
            recovery = None
            if self._recovery:
                from .vault_apply import _inspect_update_observation

                self._recovery_status, recovery = _inspect_update_observation(
                    self._root, _owners=self._owners
                )
                if recovery is None:
                    raise OSError("Validated current recovery observation required")
            self._history = _inspect_history(
                self._root,
                git_executable=self._executable,
                _capture=lambda inspection, admission: captured.append(
                    (inspection, admission)
                ),
                _metadata_only=self._metadata_only,
                _owners=self._owners if self._metadata_only else None,
                recovery_observation=recovery,
            )
            if (
                self._history.status == "intact"
                and self._history.admission.status == "supported"
                and self._history.admission.inventory_complete
                and captured
            ):
                inspection, admission = captured[0]
                if (
                    inspection.history is None
                    or inspection.history.locator != self._history.checkpoint.locator
                    or inspection.history.manifest != self._history.checkpoint.manifest
                ):
                    raise OSError(
                        "History did not originate in the completed inspection"
                    )
                self._inspection = inspection
                self._bound_history = (
                    _MetadataHistory(admission, inspection.history)
                    if self._metadata_only
                    else _history_result(
                        status="intact",
                        admission=admission,
                        checkpoint=inspection.history,
                    )
                )
                self._terminal = inspection.recovery_observation
                if self._terminal is None:
                    self._idle = _IdleCheckpointObservation(inspection, admission)
                self._check()
            elif (
                self._history.status == "absent"
                and self._history.admission.status == "supported"
                and self._history.admission.inventory_complete
                and captured
            ):
                inspection, _ = captured[0]
                self._absence = _AbsentHistoryObservation(inspection, self._history)
                self._inspection = inspection
                self._bound_history = self._history
                self._check()
            return self
        except BaseException:
            self.__exit__()
            raise

    def __exit__(self, *exc):
        self._open = False
        self._history = None
        self._bound_history = None
        self._inspection = None
        self._idle = None
        self._absence = None
        self._terminal = None
        self._fresh_scope = None
        self._owners.close()

    @property
    def history(self):
        """Immutable entry snapshot; byte and scope reads recheck current facts."""
        if not self._open:
            raise OSError("Update input reader is closed")
        return self._history

    def _check(self):
        from .vault_admission import _check_read_snapshot

        if not self._open or self._inspection is None:
            self._fresh_scope = None
            raise OSError("Completed current input observation required")
        try:
            if self._absence is not None:
                self._absence.check(_Git(self._root, self._inspection.executable))
                return
            _check_read_snapshot(
                self._root,
                _Git(self._root, self._inspection.executable),
                self._inspection.history,
                self._inspection.current_refs,
                terminal=self._terminal,
            )
        except BaseException:
            self._fresh_scope = None
            raise

    @staticmethod
    def _physical_scope_value(value):
        """Named payload-free fields only: never traverse checkpoint.review."""
        from brz2obsidian.application.vault_contracts import VaultAdmission

        if (
            type(value) not in (VaultHistoryInspection, _MetadataHistory)
            or type(value.admission) is not VaultAdmission
            or type(value.checkpoint) not in (CheckpointRead, _MetadataCheckpoint)
        ):
            raise OSError("Completed physical scoped admission required")
        checkpoint = value.checkpoint
        return (
            "brz2obsidian.vault-history-inspection",
            1,
            value.status,
            value.admission,
            "brz2obsidian.checkpoint-read",
            1,
            checkpoint.status,
            "validated" if type(checkpoint) is _MetadataCheckpoint else checkpoint.code,
            checkpoint.locator,
            checkpoint.manifest,
        )

    def _scope_context(self):
        terminal = self._terminal
        lease = (
            ("idle",)
            if terminal is None
            else (
                "terminal",
                terminal.graph.intent.operation_id,
                terminal.graph.intent.kind,
                terminal.graph.intent.generation,
                terminal.graph.intent_commit,
            )
        )
        return (
            str(self._root),
            self._inspection.executable,
            self._inspection.current_refs,
            self._inspection.history.locator if self._absence is None else None,
            self._absence.anchors if self._absence is not None else None,
            lease,
        )

    def _consume_fresh_scope(self, value, *, purpose, ledger):
        """Consume an actual latest local inspection, even on mismatched input."""
        from brz2obsidian.content_fingerprints import canonical_equal

        pending, self._fresh_scope = self._fresh_scope, None
        self._check()
        if pending is None:
            raise OSError("A new completed scoped inspection is required")
        physical, subjects, actual_purpose, context = pending
        ledger.retain_metadata(64 + 16 * 10)
        candidate = self._physical_scope_value(value)
        ledger.admit_metadata((physical, subjects, context, candidate))
        if (
            purpose != actual_purpose
            or context != self._scope_context()
            or not canonical_equal(physical, candidate)
        ):
            raise OSError("Scoped admission is not the latest completed input")
        return physical[3], subjects

    def _discard_fresh_scope(self):
        self._fresh_scope = None

    def _current_history(self):
        self._check()
        return self._bound_history

    def format_baseline_files(self):
        """Return the original source inventory bound to the observed preparation."""
        self._check()
        parent = self._inspection._format_prepared_parent()
        if parent is None or parent.baseline_source is None:
            raise OSError("Current format preparation has no qualified baseline")
        return parent.baseline_source

    def content_session(self, *, scratch_parent):
        """Own disposable exact content after this observation's full admission."""
        from .content_session import ContentSession

        self._check()
        return ContentSession(self, scratch_parent=scratch_parent)

    def read_payload(self, *, locator, requests, byte_limit, role="source"):
        from .checkpoint_payload import _read_checkpoint_payload

        return _read_checkpoint_payload(
            self._root,
            locator=locator,
            requests=requests,
            byte_limit=byte_limit,
            role=role,
            git_executable=(
                self._inspection.executable
                if self._inspection is not None
                else self._executable
            ),
            _read_history=self._current_history,
            _guard=self._check,
        )

    def read_attachment_ownership(self, *, locator, paths):
        from .attachment_ownership import read_attachment_ownership

        self._check()
        if (
            self._absence is not None
            or locator != self._bound_history.checkpoint.locator
            or type(paths) is not tuple
            or not paths
            or len(set(paths)) != len(paths)
            or not set(paths).issubset(row.path for row in self._inspection.inventory)
        ):
            raise OSError("Current finite attachment ownership request required")
        for path in paths:
            CheckpointRead.relative_vault_path(path)
        result = read_attachment_ownership(
            _Git(self._root, self._inspection.executable),
            association=locator.association,
            roles=tuple(self._inspection.checkpoint_roles),
            paths=set(paths),
            observation=self._inspection.recovery_observation,
        )
        self._check()
        return result

    def current_domain_matcher(self):
        """Retain the entry observation for comparison after this reader closes."""
        from .vault_admission import _same_current_domain

        if not self._open or self._inspection is None:
            raise OSError("Completed current input observation required")
        initial = self._inspection

        def matches(current):
            return (
                current._open
                and current._inspection is not None
                and _same_current_domain(initial, current._inspection)
            )

        return matches

    def inspect(self, *, subjects, new_operation=None):
        from .vault_admission import _same_current_domain

        self._fresh_scope = None
        self._check()
        captured = []
        scoped = _inspect_history(
            self._root,
            subjects=subjects,
            git_executable=self._executable,
            checkpoint_observation=self._idle,
            recovery_observation=self._terminal,
            _capture=lambda inspection, admission: captured.append(
                (inspection, admission)
            ),
            new_operation=new_operation,
            _metadata_only=self._metadata_only,
            _owners=self._owners if self._metadata_only else None,
        )
        self._check()
        if (
            scoped.status != ("absent" if self._absence is not None else "intact")
            or scoped.admission.status != "supported"
            or not captured
            or not _same_current_domain(self._inspection, captured[0][0])
        ):
            raise OSError("Current scoped admission changed or is incomplete")
        actual = captured[0][0]
        self._fresh_scope = (
            self._physical_scope_value(scoped),
            actual.subjects,
            actual.new_operation,
            self._scope_context(),
        )
        return scoped


def inspect_update_inputs(vault, *, git_executable=None):
    return _UpdateRead(vault, git_executable=git_executable)


def read_checkpoint(vault, *, git_executable=None):
    observed = inspect_history(vault, git_executable=git_executable)
    if observed.status != "unavailable" and observed.checkpoint is not None:
        return observed.checkpoint
    return CheckpointRead(
        schema_id="brz2obsidian.checkpoint-read",
        schema_version=1,
        status="refused",
        code="history_invalid",
        locator=None,
        manifest=None,
        review=None,
        message="Required local history, association or exact bytes are unavailable; resolve recovery before updating.",
    )


class _CaptureRequest(NamedTuple):
    root: object
    source: object
    vault_id: object
    import_id: object
    identity: object
    admission: object
    subjects: object
    review: object
    boundary: object
    proposed: object
    expected_prepared: object
    git_executable: object
    active_operation: object
    source_binding: object
    review_source: object
    observed_source: object
    operation_intent_commit: object
    recovery_direction: object
    undo_of_receipt_commit: object
    progress: object
    observation: object
    owned_export: object
    owners: object
    collection_record_path: str | None


class _CaptureBase(NamedTuple):
    saved_result: object
    current: object
    identity: object
    git: object
    association: object
    association_id: object
    prior: object
    format_parent: object
    captured_inspections: object
    collection_record_path: str | None
    selected_baseline: CheckpointManifest | None
    selected_baseline_commit: str | None


class _CaptureLineage(NamedTuple):
    recovery_target: object
    recovery_origin_plan: object
    recovery_origin_effects: object
    recovery_origin_intent_commit: object
    recovery_previous_operation_commit: object
    target_direction: object
    authority: object
    original: object
    target_origin_commit: object


class _CapturePlan(NamedTuple):
    saved: object
    proposed: object
    temp_base: object
    review_source: object
    observed_source: object
    reviewed_source: object
    review_source_rows: object
    retaining_prepared: object
    retained_recovery_incoming: object
    selected_effects: object
    included_paths: object
    stale_history: object
    retry_format: object


class _SpooledCapture(NamedTuple):
    source_files: object
    vault_files: object
    proposed_files: object
    inputs: object
    reviewed_source: object


class _DescribedCapture(NamedTuple):
    expected_oids: object
    source_rows: object
    vault_rows: object
    preimage_rows: object
    proposed_rows: object
    gaps: object
    reviewed_source: object
    semantic: object


@dataclass
class _CaptureWrites:
    """Keep the write and read-back facts needed to report an interrupted capture."""

    git: _Git | None = None
    objects: bool = False
    object_storage: str = "not_started"
    written_declarations: tuple = ()
    control_write_pending: bool = False
    retained: bool = False
    commit: str | None = None
    ref: str | None = None


class _CaptureDecision(Exception):
    """Carry a completed refusal or unchanged result out of the current stage."""

    def __init__(self, value):
        self.value = value


def _validate_capture_export(request):
    if request.owned_export is not None:
        from brz2obsidian.application.review_session import _OwnedReviewExport

        local_export = request.boundary == "local" and (
            request.review_source is not None
            or request.review is not None
            and request.review.facts.format_operation.kind == "onboarding"
            and request.source_binding is not None
            and request.observed_source is not None
        )
        prepared_export = (
            request.boundary == "prepared"
            and request.proposed is not None
            and request.active_operation is not None
            and request.review is not None
            and (
                request.source_binding is not None
                and request.observed_source is not None
                and request.undo_of_receipt_commit is None
                or request.source_binding is None
                and request.observed_source is None
                and request.undo_of_receipt_commit is not None
                and request.observation is not None
                or request.source_binding is None
                and request.observed_source is None
                and request.undo_of_receipt_commit is None
                and request.recovery_direction in ("finish", "restore")
                and request.observation is not None
            )
            and request.review_source is None
            and request.owners is not None
        )
        result_export = (
            request.boundary == "result"
            and request.expected_prepared is not None
            and request.active_operation is not None
            and request.operation_intent_commit is not None
            and request.observation is not None
            and request.owners is not None
            and request.review_source is None
        )
        if type(request.owned_export) is not _OwnedReviewExport or not (
            local_export or prepared_export or result_export
        ):
            raise OSError("Closed canonical owner export required")
        request.owned_export.check(request.review)
        if (
            prepared_export
            or result_export
            or local_export
            and request.review.ready
            and request.review.facts.format_operation.kind == "attachment_cleanup"
        ) and (
            request.owned_export.effects is None
            or request.owned_export.effects.status != "selected"
            or request.owned_export.session._selected
            is not request.owned_export.effects
        ):
            raise OSError("Current canonical selected effects required")


def _capture_subjects(request):
    subjects = request.subjects
    from brz2obsidian.application.vault_progress_contracts import report_progress

    report_progress(
        request.progress,
        "final_reporting" if request.boundary == "result" else "snapshot_preparation",
        operation_id=request.active_operation,
        intent_commit=request.operation_intent_commit,
    )
    if request.observation is not None:
        from brz2obsidian.application.vault_update_contracts import VaultApplyResult
        from brz2obsidian.publication.vault_apply import _OperationObservation

        if (
            type(request.observation) is not tuple
            or len(request.observation) != 2
            or not isinstance(request.observation[0], VaultApplyResult)
            or not isinstance(request.observation[1], _OperationObservation)
            or request.active_operation is None
        ):
            raise _CaptureDecision(
                result("refused", "current_operation_observation_required")
            )
    subjects = tuple(VaultSubject.model_validate(s) for s in subjects)
    if (
        request.boundary not in ("local", "prepared", "result")
        or (request.boundary == "prepared") != (request.proposed is not None)
        or (request.boundary == "result") != (request.expected_prepared is not None)
        or request.operation_intent_commit is not None
        and (
            request.boundary != "result"
            or request.active_operation is None
            or type(request.operation_intent_commit) is not str
            or len(request.operation_intent_commit) != 40
            or set(request.operation_intent_commit) - set("0123456789abcdef")
        )
        or request.recovery_direction is not None
        and (
            request.boundary != "prepared"
            or request.active_operation is None
            or request.review is None
            or request.recovery_direction not in ("finish", "restore")
        )
        or request.undo_of_receipt_commit is not None
        and (
            request.boundary != "prepared"
            or request.active_operation is None
            or request.review is None
            or request.recovery_direction is not None
        )
    ):
        raise _CaptureDecision(result("refused", "invalid_checkpoint_boundary"))
    return subjects


def _capture_base(request, subjects, writes):
    identity = request.identity
    saved_result = (
        save_review(request.review)
        if request.review is not None
        and request.review.facts.format_operation.kind == "format_transition"
        and request.owned_export is None
        else None
    )
    if saved_result is not None and saved_result.status != "saved":
        raise _CaptureDecision(result("refused", "invalid_current_review"))
    new_operation = (
        "format_transition"
        if request.review is not None
        and request.review.facts.format_operation.kind == "format_transition"
        else None
    )
    captured_inspections = []
    observed_history = (
        _inspect_history(
            request.root,
            subjects=subjects,
            git_executable=request.git_executable,
            active_operation=request.active_operation,
            new_operation=new_operation,
            _capture=lambda inspection, admission: captured_inspections.append(
                inspection
            ),
            _metadata_only=request.owned_export is not None,
            _owners=request.owners,
        )
        if request.observation is None
        else _inspect_retained_history(
            request.root,
            request.observation[1],
            subjects=subjects,
            active_operation=request.active_operation,
        )
    )
    current = observed_history.admission
    if (
        current.status != "supported"
        or current.repository.kind != "root"
        or current.observation_fingerprint != request.admission.observation_fingerprint
    ):
        raise _CaptureDecision(result("refused", "current_admission_required"))
    identity = OutputIdentity.model_validate(identity)
    if (
        request.source == request.root
        or request.root in request.source.parents
        or request.source in request.root.parents
    ):
        raise _CaptureDecision(result("refused", "distinct_source_required"))
    git = _Git(request.root, request.git_executable)
    writes.git = git
    association_id = digest(
        (
            request.vault_id,
            request.import_id,
            identity.collection_id,
            identity.module_id,
        )
    )
    writes.ref = "refs/brz2obsidian/imports/" + association_id + "/checkpoints"
    association = VaultAssociation(
        schema_id="brz2obsidian.vault-association",
        schema_version=1,
        association_id=association_id,
        vault_id=request.vault_id,
        import_id=request.import_id,
        collection_id=identity.collection_id,
        module_id=identity.module_id,
        vault_anchor=verify_directory(request.root),
        git_anchor=verify_directory(request.root / ".git"),
        ref=writes.ref,
    )
    prior = observed_history.checkpoint
    if observed_history.status == "unavailable" or prior is None:
        raise _CaptureDecision(result("refused", "current_history_unavailable"))
    association, record_path, selected_baseline, selected_baseline_commit = (
        _capture_collection_scope(request, prior, association, identity)
    )
    writes.ref = association.ref
    format_parent = (
        captured_inspections[0]._format_prepared_parent()
        if new_operation is not None and captured_inspections
        else None
    )
    return _CaptureBase(
        saved_result,
        current,
        identity,
        git,
        association,
        association.association_id,
        prior,
        format_parent,
        captured_inspections,
        record_path,
        selected_baseline,
        selected_baseline_commit,
    )


def _capture_collection_scope(request, prior, association, identity):
    record_path = request.collection_record_path
    if record_path is None:
        return _current_capture_scope(request, prior, association, identity)
    initial = _first_collection_review(request)
    if prior.status != "valid":
        if initial:
            return association, record_path, None, None
        raise _CaptureDecision(result("refused", "collection_not_active"))
    current = _retained_vault_association(request, prior)
    key = (identity.module_id, identity.collection_id)
    baseline = collection_baselines(prior).get(key)
    if initial:
        if baseline is not None:
            raise _CaptureDecision(result("refused", "collection_already_active"))
        return current, record_path, None, None
    selection = (
        request.boundary == "local"
        and request.review is not None
        and request.review.facts.format_operation.kind == "source_update"
        and request.review_source is not None
    )
    if not selection:
        raise _CaptureDecision(result("refused", "collection_update_review_required"))
    if baseline is None:
        raise _CaptureDecision(result("refused", "collection_not_active"))
    commit, manifest = baseline
    if record_path != (manifest.collection_record_path or "migration-record.json"):
        raise _CaptureDecision(result("refused", "collection_scope_changed"))
    return current, manifest.collection_record_path, manifest, commit


def _retained_vault_association(request, prior):
    current = prior.locator.association
    if (current.vault_id, current.import_id) != (request.vault_id, request.import_id):
        raise _CaptureDecision(result("refused", "association_mismatch"))
    return current


def _current_capture_scope(request, prior, association, identity):
    if prior.status != "valid":
        return association, None, None, None
    retained = _retained_vault_association(request, prior)
    previous = prior.manifest.identity
    key = identity.module_id, identity.collection_id
    if (previous.module_id, previous.collection_id) != key:
        target = collection_baselines(prior).get(key)
        if request.undo_of_receipt_commit is not None and target is not None:
            _, manifest = target
            return retained, manifest.collection_record_path, None, None
        raise _CaptureDecision(result("refused", "association_mismatch"))
    scope = prior.manifest.collection_record_path
    if scope is not None:
        if request.boundary == "local":
            raise _CaptureDecision(
                result("refused", "collection_update_review_required")
            )
        return retained, scope, None, None
    if retained != association:
        raise _CaptureDecision(result("refused", "association_mismatch"))
    return retained, None, None, None


def collection_baselines(checkpoint):
    if isinstance(checkpoint, _MetadataCheckpoint):
        return checkpoint.collection_baselines or {}
    return checkpoint._collection_baselines


def _first_collection_review(request):
    return (
        request.boundary == "local"
        and request.collection_record_path is not None
        and request.review is not None
        and request.review.facts.format_operation.kind == "collection_import"
        and request.review.facts.format_operation.baseline_source_version is None
        and request.review.facts.format_operation.established_baseline is None
        and request.review_source is not None
    )


def _capture_lineage(request, base):
    recovery_target = None
    recovery_origin_plan = None
    recovery_origin_effects = None
    authority = original = target_origin_commit = None
    recovery_origin_intent_commit = None
    recovery_previous_operation_commit = None
    retained_recovery_direction = (
        base.prior.manifest.recovery_direction
        if request.boundary == "result" and base.prior.status == "valid"
        else None
    )
    target_direction = request.recovery_direction or retained_recovery_direction
    undo_receipt = request.undo_of_receipt_commit or (
        base.prior.manifest.undo_of_receipt_commit
        if request.boundary == "result" and base.prior.status == "valid"
        else None
    )
    if undo_receipt is not None:
        from brz2obsidian.publication.vault_undo import _capture_target

        undo_target = _capture_target(
            request.root,
            receipt_commit=undo_receipt,
            active_operation=request.active_operation,
            prior=base.prior,
            boundary=request.boundary,
            retained=request.observation,
        )
        authority = undo_target.observation
        original = undo_target.intent
        recovery_origin_plan = undo_target.plan
        target_origin_commit = undo_target.graph.origin_intent_commit
        target_direction = "restore"
        recovery_target = (
            {row.path: row for row in original.before},
            undo_target.lineage.source,
        )
        if base.identity != undo_target.lineage.identity:
            raise _CaptureDecision(result("refused", "undo_source_identity_changed"))
    elif target_direction is not None:
        from brz2obsidian.application.vault_update_contracts import (
            VaultRecoveryIntent,
        )
        from brz2obsidian.publication.vault_apply import (
            _inspect_update_observation,
            owns_operation,
        )

        status, authority = (
            _inspect_update_observation(request.root)
            if request.observation is None
            else request.observation
        )
        if (
            authority is None
            or status.operation_id != request.active_operation
            or not status.recovery_required
            or not owns_operation(request.root, request.active_operation)
            or isinstance(authority.graph.intent, VaultRecoveryIntent)
            and authority.graph.intent.direction != target_direction
        ):
            raise _CaptureDecision(result("refused", "recovery_authority_required"))
        original = authority.graph.authorities[-1][1]
        target_origin_commit = authority.graph.origin_intent_commit
        origin_loaded = authority.owned[original.prepared_commit][1]
        if origin_loaded is None:
            raise _CaptureDecision(result("refused", "recovery_review_required"))
        recovery_origin_plan = origin_loaded.saved.plan
        recovery_origin_effects = origin_loaded.historical_effects
        original_prepared = authority.owned[original.prepared_commit][0]
        source_manifest = (
            original_prepared
            if target_direction == "finish"
            else authority.owned[original_prepared.previous][0]
        )
        if (
            original.operation_id != request.active_operation
            or original.association_id != base.association_id
            or source_manifest.identity != base.identity
            or request.recovery_direction is not None
            and (
                select_review_effects(request.review)
                if request.owned_export is None
                else request.owned_export.effects
            ).status
            != "selected"
        ):
            raise _CaptureDecision(result("refused", "recovery_review_required"))
        if retained_recovery_direction is not None and (
            not isinstance(authority.graph.intent, VaultRecoveryIntent)
            or authority.graph.intent.prepared_commit != request.expected_prepared
            or status.intent_commit != request.operation_intent_commit
            or base.prior.manifest.recovery_origin_intent_commit
            != authority.graph.origin_intent_commit
            or base.prior.manifest.recovery_previous_operation_commit
            != authority.graph.intent.previous_operation_commit
        ):
            raise _CaptureDecision(
                result("refused", "recovery_result_authority_changed")
            )
        recovery_target = (
            {
                row.path: row
                for row in (
                    original.proposed
                    if target_direction == "finish"
                    else original.before
                )
            },
            source_manifest.source,
        )
        if request.recovery_direction is not None:
            recovery_origin_intent_commit = authority.graph.origin_intent_commit
            recovery_previous_operation_commit = authority.graph.commit
    if request.boundary == "result" and (
        base.prior.status != "valid"
        or base.prior.locator.commit != request.expected_prepared
        or base.prior.manifest.boundary != "prepared"
        or base.prior.manifest.identity != base.identity
    ):
        raise _CaptureDecision(result("refused", "prepared_history_required"))
    return _CaptureLineage(
        recovery_target,
        recovery_origin_plan,
        recovery_origin_effects,
        recovery_origin_intent_commit,
        recovery_previous_operation_commit,
        target_direction,
        authority,
        original,
        target_origin_commit,
    )


def _require_current_saved_review(request, base):
    prior = base.prior
    if (
        prior.status != "valid"
        or prior.manifest.boundary != "local"
        or prior.manifest.reviewed_source is None
    ):
        return
    if prior.review is not None:
        plan = prior.review.saved.plan
        pending_id = plan.proposal.proposal_id
        onboarding = (
            plan.facts.format_operation.kind == "onboarding"
            and _initial_absence_review(prior.review)
        )
    elif isinstance(prior, _MetadataCheckpoint):
        pending_id = prior.metadata[5][0]
        onboarding = prior.metadata[7] and prior.metadata[10] == "onboarding"
    else:
        raise _CaptureDecision(result("refused", "current_history_unavailable"))
    incoming = (
        request.review.facts.incoming_identity if request.review is not None else None
    )
    pending = prior.manifest.reviewed_source.incoming_identity
    if incoming is not None and (
        request.review.proposal.proposal_id == pending_id
        and (incoming.module_id, incoming.collection_id)
        == (pending.module_id, pending.collection_id)
        or onboarding
        and request.review.facts.format_operation.kind == "format_transition"
        and request.review.facts.baseline_identity == prior.manifest.identity
    ):
        return
    raise _CaptureDecision(result("refused", "saved_review_pending"))


def _capture_saved_review(request, base, lineage):
    saved_result = base.saved_result
    saved = None
    if request.review is not None:
        if saved_result is None and request.owned_export is None:
            saved_result = save_review(request.review)
        if (request.owned_export is None and saved_result.status != "saved") or (
            request.review.facts.baseline_identity
            if request.boundary == "local"
            and (
                request.review_source is not None
                or request.review.facts.format_operation.kind == "onboarding"
                and request.source_binding is not None
                and request.observed_source is not None
            )
            else request.review.facts.incoming_identity
        ) != base.identity:
            raise _CaptureDecision(result("refused", "invalid_current_review"))
        saved = (
            request.owned_export.saved
            if request.owned_export is not None
            else saved_result.record
        )
        from .attachment_ownership import review_ownership_claims, validate_claims

        claims, missing = review_ownership_claims(
            saved.plan,
            request.owned_export.effects if request.owned_export is not None else None,
        )
        if claims or missing:
            try:
                roles = (
                    tuple(base.captured_inspections[0].checkpoint_roles)
                    if base.captured_inspections
                    else request.observation[1].checkpoint_roles
                )
                origin_claims = (
                    review_ownership_claims(
                        lineage.recovery_origin_plan, lineage.recovery_origin_effects
                    )[0]
                    if lineage.recovery_origin_plan is not None
                    else ()
                )
                observed_operation = (
                    lineage.authority
                    if lineage.recovery_origin_plan is not None
                    else base.captured_inspections[0].recovery_observation
                    if base.captured_inspections
                    else request.observation[1]
                )
                cutoff = (
                    lineage.authority.owned[lineage.original.prepared_commit][
                        0
                    ].previous
                    if lineage.recovery_origin_plan is not None
                    else None
                )
                validate_claims(
                    base.git,
                    association=base.association,
                    roles=roles,
                    claims=claims,
                    missing=missing,
                    origin_claims=origin_claims,
                    cutoff=cutoff,
                    observation=observed_operation,
                    continuation_origin=lineage.original
                    if lineage.recovery_origin_plan is not None
                    else None,
                    continuation_plan=lineage.recovery_origin_plan,
                    continuation_origin_commit=(
                        lineage.target_origin_commit
                        if lineage.recovery_origin_plan is not None
                        else None
                    ),
                    continuation_before=(
                        base.prior.manifest.preimage
                        if request.boundary == "result"
                        else base.current.inventory
                    ),
                    continuation_direction=lineage.target_direction,
                    continuation_effects=lineage.recovery_origin_effects,
                )
            except OSError, ValueError, TypeError, KeyError:
                raise _CaptureDecision(result("refused", "cleanup_ownership_unbound"))
    return saved


def _capture_observed_source(request, base):
    observed_source = request.observed_source
    if observed_source is not None:
        from brz2obsidian.contracts import SourceIdentity

        observed_source = SourceIdentity.model_validate(observed_source)
        if request.review is None or (
            observed_source.source_id,
            observed_source.module_id,
            observed_source.snapshot_digest,
        ) != (
            base.identity.collection_id,
            base.identity.module_id,
            request.review.facts.format_operation.target_source_version,
        ):
            raise _CaptureDecision(result("refused", "source_observation_mismatch"))
    elif request.boundary == "result" and base.prior.status == "valid":
        observed_source = base.prior.manifest.observed_source
    return observed_source


def _capture_local_source(request, base, saved):
    review_source = request.review_source
    reviewed_source = None
    review_source_rows = None
    if review_source is not None:
        from brz2obsidian.application.source_payload_contracts import (
            ReviewedSourceBinding,
        )
        from brz2obsidian.publication.source_payload import observe_reviewed_source

        if (
            request.boundary != "local"
            or saved is None
            or request.source_binding is None
        ):
            raise _CaptureDecision(result("refused", "local_review_source_required"))
        if (
            not _first_collection_review(request)
            and (
                base.prior.status != "valid"
                or request.review.facts.baseline_identity
                != (
                    base.selected_baseline.identity
                    if base.selected_baseline is not None
                    else base.format_parent.identity
                    if base.format_parent
                    else base.prior.manifest.identity
                )
            )
            or request.review.preflight != base.current.preflight
        ):
            raise _CaptureDecision(
                result("refused", "current_baseline_review_required")
            )
        review_source = Path(review_source).absolute()
        if (
            review_source == request.root
            or request.root in review_source.parents
            or review_source in request.root.parents
        ):
            raise _CaptureDecision(result("refused", "distinct_review_source_required"))
        reviewed_source = ReviewedSourceBinding.model_validate(request.source_binding)
        if observe_reviewed_source(
            review_source, request.review
        ) != reviewed_source or not _reviewed_source_matches(saved, reviewed_source):
            raise _CaptureDecision(result("refused", "source_payload_changed"))
        review_source_rows = tuple(
            (row.path, row.mode, row.size, row.sha256, None)
            for row in reviewed_source.files
        )
    return review_source, reviewed_source, review_source_rows


def _retain_prepared_review(request, base, saved, retaining_prepared):
    if retaining_prepared:
        if saved is not None and _review_meaning(saved) != _review_meaning(
            base.prior.review.saved if base.prior.review is not None else None
        ):
            raise _CaptureDecision(result("refused", "prepared_review_changed"))
        saved = base.prior.review.saved if base.prior.review is not None else None
        if request.owned_export is not None:
            if saved is None:
                raise _CaptureDecision(result("refused", "prepared_review_changed"))
            request.owned_export.check(saved.plan)
        if (
            base.current.policy_continuity_fingerprint
            != base.prior.manifest.policy_continuity_fingerprint
        ):
            raise _CaptureDecision(result("refused", "prepared_policy_changed"))
    return saved


def _check_retained_finish_incoming(subject, origin_subjects, finish_incoming_rows):
    origin_subject = origin_subjects.get((subject.item_id, subject.facet))
    if origin_subject is None or subject.path != origin_subject.path:
        raise _CaptureDecision(result("refused", "recovery_review_required"))
    source_row = next(
        (row for row in finish_incoming_rows if row.path == subject.path),
        None,
    )
    expected = origin_subject.incoming
    if (
        (expected is None) != (source_row is None)
        or expected is not None
        and (
            content_size(expected) != source_row.size
            or content_sha(expected) != source_row.sha256
        )
    ):
        raise _CaptureDecision(result("refused", "review_bytes_changed"))
    return expected


def _retained_finish_source(lineage):
    finish_incoming_rows = lineage.recovery_target[1]
    if lineage.target_direction == "finish" and lineage.original.kind == "undo":
        undo_target = lineage.authority.origin_undo_target
        if (
            lineage.original.undo_of_receipt_commit is None
            or undo_target is None
            or undo_target.receipt_commit != lineage.original.undo_of_receipt_commit
            or undo_target.intent.association_id != lineage.original.association_id
        ):
            raise _CaptureDecision(result("refused", "recovery_review_required"))
        finish_incoming_rows = undo_target.intent.before
    return finish_incoming_rows


def _capture_recovery_inputs(lineage, saved):
    retained_recovery_incoming = {}
    if lineage.recovery_target is not None and saved is not None:
        from brz2obsidian.publication.vault_apply import (
            _operation_history_fingerprint,
        )

        finish_incoming_rows = _retained_finish_source(lineage)
        origin_subjects = {
            (subject.item_id, subject.facet): subject
            for subject in lineage.recovery_origin_plan.producer_facts.subjects
        }
        origin_approvals = {
            approval.change_id: approval
            for approval in lineage.recovery_origin_plan.approvals
        }
        for subject in saved.plan.facts.subjects:
            proof = subject.operation_reversal
            if subject.path in lineage.original.affected_paths:
                if lineage.target_direction != "finish" or proof is not None:
                    continue
                retained_recovery_incoming[(subject.item_id, subject.facet)] = (
                    _check_retained_finish_incoming(
                        subject, origin_subjects, finish_incoming_rows
                    )
                )
                continue
            origin_subject = origin_subjects.get((subject.item_id, subject.facet))
            if proof is None:
                if origin_subject is None or subject.path != origin_subject.path:
                    raise _CaptureDecision(
                        result("refused", "recovery_review_required")
                    )
                retained_recovery_incoming[(subject.item_id, subject.facet)] = (
                    origin_subject.incoming
                )
                continue
            approval = origin_approvals.get(proof.origin_change_id)
            if (
                origin_subject is None
                or subject.path != origin_subject.path
                or approval is None
                or approval.decision_id != proof.origin_decision_id
                or proof.operation_id != lineage.original.operation_id
                or proof.operation_kind != lineage.original.kind
                or proof.direction != lineage.target_direction
                or proof.operation_generation != lineage.original.generation
                or proof.history_fingerprint
                != _operation_history_fingerprint(
                    lineage.target_origin_commit, lineage.original
                )
            ):
                raise _CaptureDecision(result("refused", "recovery_review_required"))
            try:
                owned = review_owned_targets(
                    lineage.recovery_origin_plan,
                    proof.origin_change_id,
                    proof.origin_decision_id,
                )
            except ValueError:
                raise _CaptureDecision(result("refused", "recovery_review_required"))
            if proof.owned_targets != owned:
                raise _CaptureDecision(result("refused", "recovery_review_required"))
            retained_recovery_incoming[(subject.item_id, subject.facet)] = (
                origin_subject.incoming
            )
    return retained_recovery_incoming


def _capture_consents(current, saved, retaining_prepared):
    stale_history = False
    included_subjects = set()
    for required in current.preflight.consents:
        prior_consent = (
            None
            if saved is None
            else next(
                (
                    candidate
                    for candidate in saved.plan.preflight.consents
                    if candidate.consent_id == required.consent_id
                    and candidate.kind == required.kind
                ),
                None,
            )
        )
        same_consent = prior_consent == required or (
            retaining_prepared
            and prior_consent is not None
            and prior_consent.model_dump(exclude={"fingerprint"})
            == required.model_dump(exclude={"fingerprint"})
        )
        if required.requirement != "required" or not same_consent:
            raise _CaptureDecision(result("refused", "scoped_review_required"))
        if any(
            pending.domain == required.kind
            and pending.change_id == "consent:" + required.consent_id
            for pending in saved.plan.requirements
        ):
            raise _CaptureDecision(result("refused", "scoped_review_required"))
        if (
            saved.plan.preflight.state_fingerprint
            != current.preflight.state_fingerprint
        ):
            stale_history = True
        decision = next(
            (
                c
                for c in saved.plan.consents
                if c.consent_id == required.consent_id and c.kind == required.kind
            ),
            None,
        )
        if decision is None or decision.choice != "accept":
            raise _CaptureDecision(result("refused", "scoped_review_required"))
        if required.kind == "tracking":
            included_subjects.update(required.subjects)
    return included_subjects, stale_history


def _capture_subject_scopes(request, base, saved, review_source):
    scopes = {
        reconciliation_subject_id(
            base.identity.module_id, base.identity.collection_id, s.item_id, s.facet
        ): {s.path, s.current.path}
        for s in saved.plan.facts.subjects
    }
    for item in saved.plan.facts.identity_inventory:
        if item.identity_state != "valid" or item.identity is None:
            continue
        subject_id = reconciliation_subject_id(
            item.identity.module_id,
            item.identity.collection_id,
            item.identity.item_id,
            item.facet,
        )
        if subject_id in scopes:
            scopes[subject_id].add(item.current.path)
    if request.boundary == "local" and review_source is not None:
        from brz2obsidian.application.update_subjects import (
            approved_attachment_subjects,
        )

        for subject in approved_attachment_subjects(saved.plan):
            if subject.subject_id not in scopes:
                raise _CaptureDecision(result("refused", "review_scope_changed"))
            scopes[subject.subject_id].add(subject.path)
    return scopes


def _add_recovery_removed_paths(identity, saved, selected_effects, scopes):
    # The canonical recovery proof may own an additional
    # physical output selected for removal. Its exact
    # origin membership is checked by the operation graph.
    removals = set(selected_effects.remove_paths)
    for subject in saved.plan.facts.subjects:
        proof = subject.operation_reversal
        if proof is None:
            continue
        subject_id = reconciliation_subject_id(
            identity.module_id,
            identity.collection_id,
            subject.item_id,
            subject.facet,
        )
        scopes[subject_id].update(
            row.path
            for row in proof.outputs
            if row.target_existence == "absent" and row.path in removals
        )


def _capture_effect_scope(request, base, lineage, saved, retaining_prepared, scopes):
    selected_effects = None
    if (
        retaining_prepared
        and base.prior.review is not None
        and saved is base.prior.review.saved
    ):
        selected_effects = base.prior.review.historical_effects
    if selected_effects is None:
        if request.owned_export is not None:
            request.owned_export.check(saved.plan)
            selected_effects = request.owned_export.effects
        else:
            selected_effects = select_review_effects(saved.plan)
    if selected_effects.status == "selected":
        for effect in selected_effects.files:
            if effect.subject_id not in scopes:
                raise _CaptureDecision(result("refused", "review_scope_changed"))
            scopes[effect.subject_id].add(effect.path)
        if lineage.recovery_target is not None:
            _add_recovery_removed_paths(base.identity, saved, selected_effects, scopes)
    return selected_effects


def _capture_review_scope(
    request, base, lineage, saved, subjects, review_source, retaining_prepared
):
    selected_effects = None
    if saved is not None:
        scopes = _capture_subject_scopes(request, base, saved, review_source)
        if request.boundary != "local":
            selected_effects = _capture_effect_scope(
                request, base, lineage, saved, retaining_prepared, scopes
            )
        if any(
            s.subject_id not in scopes or s.path not in scopes[s.subject_id]
            for s in subjects
        ):
            raise _CaptureDecision(result("refused", "review_scope_changed"))
    return selected_effects


def _capture_spool_capacity(request, base, saved, included_paths):
    proposed = request.proposed
    if proposed is not None:
        proposed = Path(proposed).absolute()
        if (
            proposed == request.root
            or request.root in proposed.parents
            or proposed in request.root.parents
        ):
            raise _CaptureDecision(result("refused", "distinct_proposed_required"))
    temp_base = base.git.inspection.temporary_base()
    if temp_base is None:
        raise _CaptureDecision(result("refused", "temporary_storage_unavailable"))
    if (
        temp_base == request.source
        or request.source in temp_base.parents
        or proposed is not None
        and (temp_base == proposed or proposed in temp_base.parents)
    ):
        raise _CaptureDecision(result("refused", "temporary_storage_overlaps_input"))
    vault_size = sum(
        f.size
        for f in base.current.inventory
        if not f.excluded or f.path in included_paths
    )
    if not _capture_resources(
        request.root,
        request.source,
        proposed,
        temp_base,
        vault_size,
        saved,
        _owned_export=request.owned_export,
    ):
        raise _CaptureDecision(result("refused", "insufficient_checkpoint_resources"))
    return proposed, temp_base


def _prepare_checkpoint_capture(request, writes):
    _validate_capture_export(request)
    subjects = _capture_subjects(request)
    base = _capture_base(request, subjects, writes)
    if request.boundary == "local":
        _require_current_saved_review(request, base)
    retry_format = request.boundary == "prepared" and base.format_parent is not None
    lineage = _capture_lineage(request, base)
    saved = _capture_saved_review(request, base, lineage)
    observed_source = _capture_observed_source(request, base)
    review_source, reviewed_source, review_source_rows = _capture_local_source(
        request, base, saved
    )
    retaining_prepared = request.boundary == "result"
    saved = _retain_prepared_review(request, base, saved, retaining_prepared)
    retained_recovery_incoming = _capture_recovery_inputs(lineage, saved)
    included_subjects, stale_history = _capture_consents(
        base.current, saved, retaining_prepared
    )
    selected_effects = _capture_review_scope(
        request, base, lineage, saved, subjects, review_source, retaining_prepared
    )
    included_paths = {s.path for s in subjects if s.subject_id in included_subjects}
    proposed, temp_base = _capture_spool_capacity(request, base, saved, included_paths)
    return (
        base,
        lineage,
        _CapturePlan(
            saved,
            proposed,
            temp_base,
            review_source,
            observed_source,
            reviewed_source,
            review_source_rows,
            retaining_prepared,
            retained_recovery_incoming,
            selected_effects,
            included_paths,
            stale_history,
            retry_format,
        ),
    )


def _spool_capture_source(request, base, lineage, plan, directory):
    reviewed_source = plan.reviewed_source
    source_files, source_spools = _spool(request.source, directory)
    if plan.review_source is not None and tuple(
        row[:4] for row in source_files
    ) != tuple(
        (row.path, row.mode, row.size, row.sha256)
        for row in (
            ()
            if _first_collection_review(request)
            else base.selected_baseline.source
            if base.selected_baseline is not None
            else base.format_parent.baseline_source
            if base.format_parent is not None
            else base.prior.manifest.source
        )
    ):
        raise _CaptureDecision(result("refused", "source_baseline_changed"))
    if lineage.recovery_target is not None and tuple(
        row[:4] for row in source_files
    ) != tuple(
        (row.path, row.mode, row.size, row.sha256) for row in lineage.recovery_target[1]
    ):
        raise _CaptureDecision(result("refused", "recovery_source_lineage_changed"))
    if request.source_binding is not None and plan.review_source is None:
        from brz2obsidian.application.source_payload_contracts import (
            ReviewedSourceBinding,
        )

        binding = ReviewedSourceBinding.model_validate(request.source_binding)
        observed_rows = tuple(
            (row.path, row.mode, row.size, row.sha256) for row in binding.files
        )
        if tuple(
            row[:4] for row in source_files
        ) != observed_rows or binding.source_anchor != verify_directory(request.source):
            raise _CaptureDecision(result("refused", "source_payload_changed"))
        if plan.saved is not None and plan.observed_source is not None:
            reviewed_source = binding
            if not _reviewed_source_matches(plan.saved, binding):
                raise _CaptureDecision(result("refused", "source_binding_mismatch"))
    if plan.observed_source is not None and not _source_observation_matches(
        plan.observed_source,
        reviewed_source
        if request.boundary != "result"
        else base.prior.manifest.reviewed_source,
    ):
        raise _CaptureDecision(result("refused", "source_observation_mismatch"))
    return source_files, source_spools, reviewed_source


def _spool_capture_inventory(
    request, base, plan, directory, source_files, source_spools, reviewed_source, writes
):
    vault_files, vault_spools = _spool(
        request.root,
        directory,
        [
            f.path
            for f in base.current.inventory
            if not f.excluded or f.path in plan.included_paths
        ],
        offset=len(source_files),
    )
    proposed_files, proposed_spools = [], []
    if plan.proposed is not None:
        proposed_files, proposed_spools = _spool(
            plan.proposed, directory, offset=len(source_files) + len(vault_files)
        )
        if any(
            row[0] in base.current.recovery_gaps and row[0] not in plan.included_paths
            for row in proposed_files
        ):
            raise _CaptureDecision(result("refused", "scoped_inclusion_required"))
    admitted = [
        (f.path, f.mode, f.size, f.sha256, f.identity)
        for f in base.current.inventory
        if not f.excluded or f.path in plan.included_paths
    ]
    if vault_files != admitted:
        raise _CaptureDecision(result("refused", "capture_changed"))
    if request.boundary == "result":
        semantic_inventory = lambda rows: [
            (row[0], row[1], row[2], row[3]) for row in rows
        ]
        declared = lambda files: [(f.path, f.mode, f.size, f.sha256) for f in files]
        if semantic_inventory(vault_files) != declared(
            base.prior.manifest.proposed
        ) or semantic_inventory(source_files) != declared(base.prior.manifest.source):
            raise _CaptureDecision(
                result(
                    "refused",
                    "result_inventory_mismatch",
                    commit=base.prior.locator.commit,
                    ref=writes.ref,
                    retained=True,
                )
            )
    inputs = source_spools + vault_spools + proposed_spools
    return _SpooledCapture(
        source_files, vault_files, proposed_files, inputs, reviewed_source
    )


def _check_spooled_review(request, lineage, plan, spooled):
    if plan.saved is not None:
        selected_review = (
            request.boundary == "prepared"
            and plan.selected_effects is not None
            and plan.selected_effects.status == "selected"
        )
        identified = {
            (item.identity.item_id, item.facet)
            for item in plan.saved.plan.facts.identity_inventory
            if item.identity_state == "valid" and item.identity is not None
        }
        for subject in plan.saved.plan.facts.subjects:
            key = (subject.item_id, subject.facet)
            retained_incoming = key in plan.retained_recovery_incoming
            if (
                retained_incoming
                and subject.incoming != plan.retained_recovery_incoming[key]
            ):
                raise _CaptureDecision(result("refused", "review_bytes_changed"))
            incoming_checks = (
                ()
                if retained_incoming
                else (
                    (
                        subject.incoming,
                        subject.path,
                        plan.review_source_rows
                        if plan.review_source_rows is not None
                        else spooled.source_files
                        if lineage.recovery_target is None
                        else tuple(
                            (row.path, row.mode, row.size, row.sha256, None)
                            for row in lineage.recovery_target[0].values()
                        ),
                    ),
                )
            )
            current_checks = (
                ()
                if plan.retaining_prepared or (selected_review and key in identified)
                else (
                    (
                        subject.current.content,
                        subject.current.path,
                        spooled.vault_files,
                    ),
                )
            )
            for expected, path, inventory in incoming_checks + current_checks:
                observed = next((row for row in inventory if row[0] == path), None)
                if (
                    (expected is None) != (observed is None)
                    or expected is not None
                    and (
                        expected.identity.size != observed[2]
                        or expected.identity.sha256 != observed[3]
                    )
                ):
                    raise _CaptureDecision(result("refused", "review_bytes_changed"))
        if selected_review:
            for item in plan.saved.plan.facts.identity_inventory:
                if item.identity_state != "valid":
                    continue
                expected, path = item.current.content, item.current.path
                observed = next(
                    (row for row in spooled.vault_files if row[0] == path), None
                )
                if (
                    (expected is None) != (observed is None)
                    or expected is not None
                    and (
                        expected.identity.size != observed[2]
                        or expected.identity.sha256 != observed[3]
                    )
                ):
                    raise _CaptureDecision(result("refused", "review_bytes_changed"))


def _describe_capture(request, base, lineage, plan, spooled, directory, writes):
    from brz2obsidian.publication.source_payload import observe_reviewed_source

    reviewed_source = spooled.reviewed_source
    expected_oids = [
        _spool_oid(directory, path, record[2], record[3])
        for path, record in zip(
            spooled.inputs,
            spooled.source_files + spooled.vault_files + spooled.proposed_files,
            strict=True,
        )
    ]
    writes.written_declarations = tuple(
        (oid, row[2], row[3], None)
        for oid, row in zip(
            expected_oids,
            spooled.source_files + spooled.vault_files + spooled.proposed_files,
            strict=True,
        )
    )
    rows = [
        CheckpointFile(path=p, mode=m, size=size, sha256=sha, object_id=oid)
        for (p, m, size, sha, _), oid in zip(
            spooled.source_files + spooled.vault_files + spooled.proposed_files,
            expected_oids,
            strict=True,
        )
    ]
    source_rows = tuple(rows[: len(spooled.source_files)])
    vault_rows = tuple(
        rows[
            len(spooled.source_files) : len(spooled.source_files)
            + len(spooled.vault_files)
        ]
    )
    proposed_rows = (
        tuple(rows[len(spooled.source_files) + len(spooled.vault_files) :])
        if request.boundary == "prepared"
        else base.prior.manifest.proposed
        if plan.retaining_prepared
        else ()
    )
    preimage_rows = (
        base.prior.manifest.preimage if plan.retaining_prepared else vault_rows
    )
    gaps = tuple(
        path for path in base.current.recovery_gaps if path not in plan.included_paths
    )
    if plan.retry_format:
        old_binding = base.prior.manifest.reviewed_source
        if (
            plan.saved is None
            or base.prior.review is None
            or not canonical_equal(plan.saved.plan, base.prior.review.saved.plan)
            or reviewed_source is None
            or old_binding is None
            or reviewed_source.model_copy(
                update={"source_anchor": old_binding.source_anchor}
            )
            != old_binding
        ):
            raise _CaptureDecision(result("refused", "prepared_review_changed"))
        reviewed_source = old_binding
    semantic = _semantic(
        base.association,
        base.identity,
        source_rows,
        vault_rows,
        preimage_rows,
        proposed_rows,
        gaps,
        request.boundary,
        base.current.policy_fingerprint,
        plan.saved,
        request.operation_intent_commit,
        lineage.recovery_origin_intent_commit,
        lineage.recovery_previous_operation_commit,
        request.recovery_direction,
        request.undo_of_receipt_commit,
        plan.observed_source,
        reviewed_source
        if request.boundary != "result"
        else base.prior.manifest.reviewed_source,
        collection_record_path=base.collection_record_path,
        collection_baseline_commit=base.selected_baseline_commit,
        collection_preparation_owner=_collection_preparation_owner(request, base),
    )
    # Duplicate meaning omits proof identities. An owned prepared
    # export must retain the complete plan its result capture checks.
    if (
        base.prior.status == "valid"
        and base.prior.manifest.semantic_fingerprint == semantic
        and (
            request.owned_export is None
            or request.boundary != "prepared"
            or base.prior.review is not None
            and canonical_equal(plan.saved.plan, base.prior.review.saved.plan)
        )
    ):
        if (
            not _source_matches(request.source, spooled.source_files)
            or plan.proposed is not None
            and not _source_matches(plan.proposed, spooled.proposed_files)
        ):
            raise _CaptureDecision(result("refused", "capture_changed"))
        raise _CaptureDecision(
            result(
                "unchanged",
                "already_retained",
                commit=base.prior.locator.commit,
                locator=base.prior.locator,
                ref=writes.ref,
                retained=True,
            )
        )
    if plan.retry_format:
        raise _CaptureDecision(result("refused", "prepared_review_changed"))
    if plan.stale_history and not plan.retaining_prepared:
        raise _CaptureDecision(result("refused", "current_history_review_required"))
    if (
        plan.review_source is not None
        and observe_reviewed_source(plan.review_source, request.review)
        != reviewed_source
    ):
        raise _CaptureDecision(result("refused", "source_payload_changed"))
    return _DescribedCapture(
        expected_oids,
        source_rows,
        vault_rows,
        preimage_rows,
        proposed_rows,
        gaps,
        reviewed_source,
        semantic,
    )


def _write_capture_inputs(base, spooled, described, writes):
    writes.object_storage = "possible"
    oids = (
        base.git.call(
            "hash-object",
            "-w",
            "--no-filters",
            "--stdin-paths",
            input=_quoted_paths(spooled.inputs),
        )
        .decode()
        .splitlines()
    )
    if oids != described.expected_oids:
        raise OSError("Incomplete raw object write")
    verify_blobs(
        [*base.git.prefix, "cat-file", "--batch"],
        env=base.git.env,
        objects=writes.written_declarations,
    )
    writes.objects, writes.object_storage = (
        bool(spooled.inputs),
        "verified" if spooled.inputs else "not_started",
    )


def _recheck_capture_sources(request, plan, spooled, described, writes):
    from brz2obsidian.publication.source_payload import observe_reviewed_source

    if (
        not _source_matches(request.source, spooled.source_files)
        or plan.proposed is not None
        and not _source_matches(plan.proposed, spooled.proposed_files)
    ):
        raise _CaptureDecision(
            result("refused", "capture_changed", objects=writes.objects)
        )
    if (
        plan.review_source is not None
        and observe_reviewed_source(plan.review_source, request.review)
        != described.reviewed_source
    ):
        raise _CaptureDecision(
            result("refused", "source_payload_changed", objects=writes.objects)
        )


def _write_capture_review_envelope(git, directory, review_raw, writes):
    review_oid = None
    if review_raw is not None:
        spool = directory / "saved-review"
        spool.write_bytes(review_raw)
        review_sha = hashlib.sha256(review_raw).hexdigest()
        expected_oid = _spool_oid(directory, spool, len(review_raw), review_sha)
        declaration = (expected_oid, len(review_raw), review_sha, None)
        writes.written_declarations += (declaration,)
        writes.object_storage = "possible"
        review_oid = (
            git.call(
                "hash-object",
                "-w",
                "--no-filters",
                "--stdin-paths",
                input=_quoted_paths((spool,)),
            )
            .decode()
            .strip()
        )
        if review_oid != expected_oid:
            raise OSError("Saved review shape object write changed")
        verify_blobs(
            [*git.prefix, "cat-file", "--batch"],
            env=git.env,
            objects=(declaration,),
        )
        writes.objects, writes.object_storage = True, "verified"
    return review_oid


def _write_capture_review(request, base, plan, described, directory, writes):
    review_raw, review_payloads = (
        (request.owned_export.raw, request.owned_export.values)
        if request.owned_export is not None
        else _review_shape(plan.saved)
        if plan.saved is not None
        else (None, {})
    )
    role_hashes = {
        row.sha256
        for inventory in (
            described.source_rows,
            described.vault_rows,
            described.preimage_rows,
            described.proposed_rows,
        )
        for row in inventory
    }
    review_content = []
    review_hashes = sorted(set(review_payloads) - role_hashes)
    group_size = 1
    if (
        type(request.owners) is _ApplyReviewOwners
        and request.owned_export is not None
        and sum(review_payloads[sha].identity.size for sha in review_hashes)
        <= 4 * 1024 * 1024
    ):
        group_size = 32
    for hashes in batched(review_hashes, group_size):
        spools, declarations = [], []
        for sha in hashes:
            payload = review_payloads[sha]
            spool = directory / ("review-content-" + sha)
            if request.owned_export is None:
                spool.write_bytes(payload)
                payload_size = len(payload)
            else:
                with spool.open("xb", buffering=0) as output:
                    request.owned_export.copy(sha, output)
                payload_size = payload.identity.size
            oid = _spool_oid(directory, spool, payload_size, sha)
            spools.append(spool)
            declarations.append((oid, payload_size, sha, None))
        writes.written_declarations += tuple(declarations)
        writes.object_storage = "possible"
        try:
            _write_review_spools(base.git, spools, declarations)
        except _GitTimeout:
            if len(spools) == 1:
                raise
            for spool, declaration in zip(spools, declarations, strict=True):
                request.owned_export.check()
                request.owned_export.session._ledger.check()
                _write_review_spools(base.git, (spool,), (declaration,))
        if group_size > 1:
            request.owned_export.check()
            # After the last successful group, Apply handles
            # cancellation once the prepared checkpoint is retained.
            if hashes[-1] != review_hashes[-1]:
                request.owned_export.session._ledger.check()
        writes.objects, writes.object_storage = True, "verified"
        review_content.extend(
            CheckpointFile(
                path=sha,
                mode="100644",
                size=size,
                sha256=sha,
                object_id=oid,
            )
            for oid, size, sha, _ in declarations
        )
    review_oid = _write_capture_review_envelope(base.git, directory, review_raw, writes)
    return review_raw, review_content, review_oid


def _capture_manifest(
    request, base, lineage, plan, described, review_raw, review_content, review_oid
):
    previous = base.prior.locator.commit if base.prior.status == "valid" else None
    generation = base.prior.manifest.generation + 1 if previous else 1
    manifest = CheckpointManifest(
        schema_id="brz2obsidian.checkpoint-manifest",
        schema_version=1,
        association_id=base.association_id,
        generation=generation,
        boundary=request.boundary,
        identity=base.identity,
        collection_record_path=base.collection_record_path,
        collection_baseline_commit=base.selected_baseline_commit,
        collection_preparation_owner=_collection_preparation_owner(request, base),
        observed_source=plan.observed_source,
        reviewed_source=described.reviewed_source
        if request.boundary != "result"
        else base.prior.manifest.reviewed_source,
        source=described.source_rows,
        vault=described.vault_rows,
        preimage=described.preimage_rows,
        proposed=described.proposed_rows,
        review_content=tuple(review_content),
        recovery_gaps=described.gaps,
        semantic_fingerprint=described.semantic,
        previous=previous,
        operation_intent_commit=request.operation_intent_commit,
        recovery_origin_intent_commit=lineage.recovery_origin_intent_commit,
        recovery_previous_operation_commit=lineage.recovery_previous_operation_commit,
        recovery_direction=request.recovery_direction,
        undo_of_receipt_commit=request.undo_of_receipt_commit,
        review_object=review_oid,
        review_size=len(review_raw) if review_raw is not None else None,
        review_sha256=hashlib.sha256(review_raw).hexdigest()
        if review_raw is not None
        else None,
        policy_fingerprint=base.current.policy_fingerprint,
        policy_continuity_fingerprint=base.current.policy_continuity_fingerprint,
    )
    return manifest


def _collection_preparation_owner(request, base):
    if (
        request.boundary == "prepared"
        and request.undo_of_receipt_commit is None
        and request.recovery_direction is None
        and base.prior.status == "valid"
        and base.prior.manifest.boundary == "local"
        and base.prior.manifest.reviewed_source is not None
        and (
            base.prior.manifest.collection_record_path is not None
            or base.prior.manifest.collection_baseline_commit is not None
        )
    ):
        return request.active_operation
    return None


def _write_capture_metadata(git, association, manifest, review_oid, writes):
    metadata = []
    for path, value in (
        ("association.json", association),
        ("manifest.json", manifest),
    ):
        payload = value.model_dump_json().encode()
        sha = hashlib.sha256(payload).hexdigest()
        expected_oid = hashlib.sha1(
            b"blob " + str(len(payload)).encode() + b"\0" + payload,
            usedforsecurity=False,
        ).hexdigest()
        declaration = (expected_oid, len(payload), sha, None)
        writes.written_declarations += (declaration,)
        writes.object_storage = "possible"
        oid = git.call("hash-object", "-w", "--stdin", input=payload).decode().strip()
        if oid != expected_oid:
            raise OSError("Checkpoint metadata object write changed")
        verify_blobs(
            [*git.prefix, "cat-file", "--batch"],
            env=git.env,
            objects=(declaration,),
        )
        writes.objects, writes.object_storage = True, "verified"
        metadata.append((path, "100644", oid))
    if review_oid is not None:
        metadata.append(("review.json", "100644", review_oid))
    return metadata


def _write_capture_commit(
    request, base, described, manifest, metadata, review_content, writes
):
    inventories = (
        ("source", described.source_rows),
        ("vault", described.vault_rows),
        ("preimage", described.preimage_rows),
        ("proposed", described.proposed_rows),
    )
    if review_content:
        inventories += (("review-content", review_content),)
    batch_trees = (
        type(request.owners) is _ApplyReviewOwners
        and type(request.owners._local_owner) is _ApplyReviewOwners
        and sum(len(rows) for _, rows in inventories) <= 512
        and sum(len(f.path) for _, rows in inventories for f in rows) <= 65536
    )
    if batch_trees:
        writes.control_write_pending = True
        writes.object_storage = "possible"
        roots = base.git.checkpoint_trees(inventories)
        writes.objects, writes.object_storage, writes.control_write_pending = (
            True,
            "verified",
            False,
        )
    else:
        roots = []
        for role, inventory in inventories:
            writes.control_write_pending = True
            writes.object_storage = "possible"
            role_tree = base.git.tree(
                [(f.path, f.mode, f.object_id) for f in inventory]
            )
            _control_objects(base.git, {role_tree: "tree"}, {})
            writes.objects, writes.object_storage, writes.control_write_pending = (
                True,
                "verified",
                False,
            )
            roots.append((role, "040000", role_tree))
    _commit_checkpoint_tree(base.git, manifest, [*metadata, *roots], writes)


def _commit_checkpoint_tree(git, manifest, entries, writes):
    writes.control_write_pending = True
    writes.object_storage = "possible"
    tree = git.tree(entries)
    _control_objects(git, {tree: "tree"}, {})
    writes.objects, writes.object_storage, writes.control_write_pending = (
        True,
        "verified",
        False,
    )
    writes.control_write_pending = True
    writes.object_storage = "possible"
    writes.commit = (
        git.call(
            "commit-tree",
            tree,
            *(["-p", manifest.previous] if manifest.previous else []),
            input=b"brz2obsidian checkpoint\n",
        )
        .decode()
        .strip()
    )
    _control_objects(git, {writes.commit: "commit"}, {})
    writes.objects, writes.object_storage, writes.control_write_pending = (
        True,
        "verified",
        False,
    )


def _publish_locator(root, git, association, manifest, writes):
    previous = manifest.previous
    generation = manifest.generation
    git.call("update-ref", writes.ref, writes.commit, previous or "0" * 40)
    if git.call("rev-parse", "--verify", writes.ref).decode().strip() != writes.commit:
        raise OSError("Owned checkpoint ref did not retain its commit")
    writes.retained = True
    locator = CheckpointLocator(
        schema_id="brz2obsidian.checkpoint-locator",
        schema_version=1,
        association=association,
        generation=generation,
        commit=writes.commit,
    )
    _persist_checkpoint_locator(root, locator)
    return locator


def _persist_checkpoint_locator(root, locator, *, replace_pending=False):
    metadata_dir = root / ".brz2obsidian"
    metadata_dir.mkdir(exist_ok=True)
    temporary = metadata_dir / "locator.pending"
    if replace_pending and os.path.lexists(temporary):
        observe_file(root, temporary, prefix_limit=0)
        temporary.unlink()
    with temporary.open("xb") as output:
        output.write(locator.model_dump_json().encode())
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, metadata_dir / "locator.json")


def _publish_capture_locator(request, base, manifest, writes):
    locator = _publish_locator(
        request.root, base.git, base.association, manifest, writes
    )
    if type(request.owners) is _ApplyReviewOwners:
        request.owners._retain_prepared_export(
            base.git, writes.commit, manifest, request.owned_export
        )
    return locator


def _capture_in_scratch(request, base, lineage, plan, writes, directory):
    base.git.suppress_hooks(directory)
    source_files, source_spools, reviewed_source = _spool_capture_source(
        request, base, lineage, plan, directory
    )
    spooled = _spool_capture_inventory(
        request,
        base,
        plan,
        directory,
        source_files,
        source_spools,
        reviewed_source,
        writes,
    )
    _check_spooled_review(request, lineage, plan, spooled)
    described = _describe_capture(
        request, base, lineage, plan, spooled, directory, writes
    )
    _write_capture_inputs(base, spooled, described, writes)
    _recheck_capture_sources(request, plan, spooled, described, writes)
    review_raw, review_content, review_oid = _write_capture_review(
        request, base, plan, described, directory, writes
    )
    manifest = _capture_manifest(
        request, base, lineage, plan, described, review_raw, review_content, review_oid
    )
    metadata = _write_capture_metadata(
        base.git, base.association, manifest, review_oid, writes
    )
    _write_capture_commit(
        request, base, described, manifest, metadata, review_content, writes
    )
    return _publish_capture_locator(request, base, manifest, writes)


def _failed_capture(writes):
    git = writes.git
    if (
        writes.object_storage == "possible"
        and writes.written_declarations
        and not writes.control_write_pending
    ):
        try:
            verify_blobs(
                [*git.prefix, "cat-file", "--batch"],
                env=git.env,
                objects=writes.written_declarations,
            )
            writes.objects, writes.object_storage = True, "verified"
        except OSError, ValueError, TypeError, UnicodeError:
            pass
    if writes.commit is not None and writes.ref is not None and not writes.retained:
        try:
            writes.retained = (
                git.call("rev-parse", "--verify", writes.ref).decode().strip()
                == writes.commit
            )
        except OSError, ValueError, TypeError, UnicodeError:
            pass
    return result(
        "failed",
        "capture_unavailable",
        commit=writes.commit,
        ref=writes.ref,
        retained=writes.retained,
        objects=writes.objects,
        object_storage=writes.object_storage,
    )


def discard_saved_review(vault, *, expected_commit):
    """Append a local discard while retaining the prior review as history."""
    from brz2obsidian.publication.vault_apply import _acquire, _park, _release

    root = Path(vault).absolute()
    history = inspect_history(root)
    if history.status != "intact" or history.admission.status != "supported":
        return result("refused", "current_history_unavailable")
    operation = uuid4().hex
    writes = _CaptureWrites()
    try:
        _acquire(root, operation)
    except OSError, ValueError, TypeError:
        return result("refused", "operation_lease_unavailable")
    try:
        discarded = _discard_under_lease(root, operation, expected_commit, writes)
    except OSError, ValueError, TypeError, UnicodeError:
        discarded = _failed_capture(writes)
    finally:
        try:
            _release(root, operation)
        except OSError, ValueError, TypeError:
            _park(root, operation)
            discarded = result(
                "failed",
                "owned_cleanup_failed",
                commit=writes.commit,
                ref=writes.ref,
                retained=writes.retained,
                objects=writes.objects,
                object_storage=writes.object_storage,
            )
    return discarded


def _discard_under_lease(root, operation, expected_commit, writes):
    history = inspect_history(root, active_operation=operation)
    if history.status != "intact" or history.admission.status != "supported":
        return result("refused", "current_history_unavailable")
    checkpoint = history.checkpoint
    locator, prior = checkpoint.locator, checkpoint.manifest
    if locator.commit != expected_commit:
        return result("refused", "saved_review_changed")
    if (
        prior.boundary != "local"
        or prior.reviewed_source is None
        or checkpoint.review is None
    ):
        return result("refused", "saved_review_unavailable")
    if checkpoint.review.saved.plan.facts.format_operation.kind == "onboarding":
        return result("refused", "onboarding_has_no_established_baseline")
    association = locator.association
    git = writes.git = _Git(root)
    writes.ref = association.ref
    semantic = _semantic_meaning(
        association,
        prior.identity,
        prior.source,
        prior.vault,
        prior.vault,
        (),
        prior.recovery_gaps,
        "local",
        prior.policy_fingerprint,
        None,
        discarded_review=locator.commit,
        collection_record_path=prior.collection_record_path,
    )
    manifest = CheckpointManifest.model_validate(
        prior.model_dump()
        | {
            "generation": locator.generation + 1,
            "previous": locator.commit,
            "discarded_review": locator.commit,
            "collection_baseline_commit": None,
            "abandoned_collection_preparation": None,
            "preimage": prior.vault,
            "proposed": (),
            "observed_source": None,
            "reviewed_source": None,
            "review_object": None,
            "review_size": None,
            "review_sha256": None,
            "review_content": (),
            "semantic_fingerprint": semantic,
        }
    )
    _parents, entries, _prior, _association = _checkpoint_graph(
        git, locator.commit, {}, None
    )
    with tempfile.TemporaryDirectory(prefix="brz2obsidian-discard-") as directory:
        git.suppress_hooks(Path(directory))
        metadata = _write_capture_metadata(git, association, manifest, None, writes)
        roots = [
            (role, "040000", entries[previous][2])
            for role, previous in (
                ("source", "source"),
                ("vault", "vault"),
                ("preimage", "vault"),
                ("proposed", "proposed"),
            )
        ]
        _commit_checkpoint_tree(git, manifest, [*metadata, *roots], writes)
        published = _publish_locator(root, git, association, manifest, writes)
    return result(
        "captured",
        "saved_review_discarded",
        commit=writes.commit,
        locator=published,
        ref=writes.ref,
        retained=True,
        objects=writes.objects,
    )


def capture_checkpoint(
    vault,
    source,
    *,
    vault_id,
    import_id,
    identity,
    admission,
    subjects=(),
    review=None,
    boundary="local",
    proposed=None,
    expected_prepared=None,
    git_executable=None,
    active_operation=None,
    source_binding=None,
    review_source=None,
    observed_source=None,
    operation_intent_commit=None,
    recovery_direction=None,
    undo_of_receipt_commit=None,
    progress=None,
    _observation=None,
    _owned_export=None,
    _owners=None,
    collection_record_path=None,
):
    root, source = Path(vault).absolute(), Path(source).absolute()
    request = _CaptureRequest(
        root,
        source,
        vault_id,
        import_id,
        identity,
        admission,
        subjects,
        review,
        boundary,
        proposed,
        expected_prepared,
        git_executable,
        active_operation,
        source_binding,
        review_source,
        observed_source,
        operation_intent_commit,
        recovery_direction,
        undo_of_receipt_commit,
        progress,
        _observation,
        _owned_export,
        _owners,
        collection_record_path,
    )
    writes = _CaptureWrites()
    try:
        try:
            base, lineage, plan = _prepare_checkpoint_capture(request, writes)
        except _CaptureDecision as stopped:
            return stopped.value
        with tempfile.TemporaryDirectory(
            prefix="brz2obsidian-capture-", dir=plan.temp_base
        ) as name:
            try:
                locator = _capture_in_scratch(
                    request, base, lineage, plan, writes, Path(name)
                )
            except _CaptureDecision as stopped:
                return stopped.value
        return result(
            "captured",
            "retained",
            commit=writes.commit,
            locator=locator,
            ref=writes.ref,
            retained=True,
            objects=writes.objects,
        )
    except OSError, ValueError, TypeError, UnicodeError:
        return _failed_capture(writes)


def initialize_vault(vault, *, decision, git_executable=None):
    root = Path(vault).absolute()
    current = inspect_vault(root, git_executable=git_executable)
    status, created, attempted = "refused", False, False
    try:
        decision = VaultInitializationDecision.model_validate(decision)
        if (
            current.status == "supported"
            and current.repository.kind == "none"
            and decision.observation_fingerprint == current.observation_fingerprint
        ):
            if decision.choice == "decline":
                status = "declined"
            else:
                git = _Git(root, git_executable)
                directory = git.inspection.temporary_base()
                if directory is None:
                    raise OSError("Initialization temporary storage unavailable")
                with tempfile.TemporaryDirectory(
                    prefix="brz2obsidian-init-", dir=directory
                ) as name:
                    template = Path(name)
                    git.suppress_hooks(template)
                    attempted = True
                    git.call(
                        "init", "-q", "--template=" + str(template / "empty-hooks")
                    )
                    created = True
                current = inspect_vault(root, git_executable=git_executable)
                status = "initialized_review_required"
    except OSError, ValueError, TypeError:
        created = attempted and (root / ".git").exists()
        current = inspect_vault(root, git_executable=git_executable)
        status = "failed"
    return VaultInitializationResult(
        schema_id="brz2obsidian.vault-initialization-result",
        schema_version=1,
        status=status,
        repository_created=created,
        history_retained=False,
        admission=current,
        message="Initialization "
        + status.replace("_", " ")
        + "; current repository policy must be reviewed before any payload capture.",
    )
