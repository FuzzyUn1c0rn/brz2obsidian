"""Converter-owned exact-byte Git graph, independent of user branch ancestry."""

import hashlib
import io
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

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
from brz2obsidian.contracts import (
    ExactContent,
    OutputIdentity,
    SafetyFact,
    SavedReview,
    SourceMemoryProvenance,
    reconciliation_subject_id,
)
from brz2obsidian.core import load_review, save_review, select_review_effects
from brz2obsidian.publication.git_payload import verify_blobs
from brz2obsidian.publication.git_read import OUTPUT_BUDGET, read_git
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
                for name in type(value).model_fields
                if name != "fingerprint"
            }
        if isinstance(value, ExactContent):
            return {
                "sha256": hashlib.sha256(value.data).hexdigest(),
                "size": len(value.data),
            }
        if isinstance(value, SourceMemoryProvenance):
            return None
        if hasattr(type(value), "model_fields"):
            return {
                name: meaning(getattr(value, name))
                for name in type(value).model_fields
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
):
    return digest(
        (
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
        rows = []
        for name, value in sorted(children.items()):
            if isinstance(value, list):
                mode, oid = "040000", self.tree(value)
            else:
                mode, oid = value
            rows.append(
                f"{mode} {'tree' if mode == '040000' else 'blob'} {oid}\t".encode()
                + name.encode("utf-8")
                + b"\0"
            )
        return self.call("mktree", "-z", input=b"".join(rows)).decode().strip()


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


def _capture_resources(root, source, proposed, temp_base, vault_size, saved):
    """Observe ordinary spool and Git capacity before writing captured bytes."""

    def scope_size(path):
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

    unique = {}

    def review_bytes(value):
        if type(value) is bytes:
            sha = hashlib.sha256(value).hexdigest()
            if sha in unique and unique[sha] != value:
                raise OSError("Ambiguous review bytes during checkpoint sizing")
            unique[sha] = value
        elif hasattr(type(value), "model_fields"):
            for name in type(value).model_fields:
                review_bytes(getattr(value, name))
        elif isinstance(value, (tuple, list)):
            for item in value:
                review_bytes(item)

    if saved is not None:
        try:
            review_bytes(saved)
        except RecursionError as error:
            raise OSError("Saved review exceeds bounded checkpoint sizing") from error
    input_size = (
        scope_size(source)
        + vault_size
        + (scope_size(proposed) if proposed is not None else 0)
    )
    review_size = sum(len(value) for value in unique.values())
    margin = 64 * 1024 * 1024
    # Review bytes absent from raw roles are also spooled before their Git
    # objects are written. Counting every unique review byte is a conservative
    # upper bound and leaves the margin for the compact shape/control files.
    spool_need = input_size + review_size + margin
    git_need = input_size + review_size + margin
    if os.stat(root).st_dev == os.stat(temp_base).st_dev:
        enough_space = shutil.disk_usage(root).free >= spool_need + git_need
    else:
        enough_space = (
            shutil.disk_usage(temp_base).free >= spool_need
            and shutil.disk_usage(root).free >= git_need
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
                name: project(getattr(value, name)) for name in type(value).model_fields
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

    def collect(value):
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
                    collect(item)
        elif type(value) is list:
            for item in value:
                collect(item)
        elif type(value) not in (str, int, float, bool, type(None)):
            raise ValueError("Invalid saved-review scalar")

    collect(envelope["record"])
    return envelope["record"], references


def _restore_review(record, payloads):
    def restore(value):
        if type(value) is dict:
            if _REVIEW_BYTES_KEY in value:
                return payloads[value[_REVIEW_BYTES_KEY]]
            return {key: restore(item) for key, item in value.items()}
        if type(value) is list:
            return tuple(restore(item) for item in value)
        return value

    saved = SavedReview.model_validate(restore(record))
    restored = load_review(saved)
    if restored.status != "loaded":
        raise OSError("Saved S1 review is unavailable or invalid")
    return restored.loaded


def _load_review_payload(git, manifest, verified):
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
    # The actual 36 MiB distinct-byte review reached roughly 294 MiB peak
    # commit while core replay rebuilt its immutable graph. Budget that demand
    # from unique bytes, rather than the compact envelope's few KiB.
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
            record, {sha: sink.getvalue() for sha, sink in sinks.items()}
        )
    except RecursionError as error:
        raise OSError("Saved review value exceeds its bounded nesting") from error
    return restored, references


def _read(root, git):
    locator_path = root / ".brz2obsidian/locator.json"
    if not locator_path.exists():
        if (root / ".brz2obsidian").exists() or git.call(
            "for-each-ref", "--format=%(refname)", "refs/brz2obsidian/imports"
        ):
            raise OSError("Owned graph or metadata has no current locator")
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
    if association.vault_anchor != verify_directory(
        root
    ) or association.git_anchor != verify_directory(root / ".git"):
        raise OSError("Association physical context does not match")
    if set(os.listdir(root / ".brz2obsidian")) != {"locator.json"}:
        raise OSError("Unknown converter operation metadata")
    if (
        git.call("rev-parse", "--verify", association.ref).decode().strip()
        != locator.commit
    ):
        raise OSError("Owned checkpoint root is missing or changed")
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
    blobs, controls, reviewed, verified = {}, {}, {}, set()
    current, generation = locator.commit, locator.generation
    tip_manifest = tip_review = None
    visited = set()
    while current is not None:
        if current in visited:
            raise OSError("Cyclic owned checkpoint history")
        visited.add(current)
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
        requested = {trees[0]: "tree"}
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
        if (
            actual_association != association
            or manifest.association_id != expected_id
            or manifest.generation != generation
            or (manifest.identity.collection_id, manifest.identity.module_id)
            != (association.collection_id, association.module_id)
        ):
            raise OSError(
                "Retained checkpoint identity, generation or association disagrees"
            )
        if parents != (
            [manifest.previous] if manifest.previous is not None else []
        ) or (generation == 1) != (manifest.previous is None):
            raise OSError("Checkpoint history has no matching real parent edge")
        if ("review-content" in entries) != bool(manifest.review_content):
            raise OSError("Saved review content has no matching role tree")
        for role in (
            "source",
            "vault",
            "preimage",
            "proposed",
            *(("review-content",) if manifest.review_content else ()),
        ):
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
                    raise OSError(
                        "Shared object has inconsistent semantic declarations"
                    )
                blobs[entry.object_id] = declaration
            actual_directories = {
                path
                for path, (_, kind, _) in entries.items()
                if kind == "tree" and (path == role or path.startswith(role + "/"))
            }
            if directories != actual_directories:
                raise OSError("Unknown retained tree structure")
        review = None
        if manifest.review_object is None:
            if "review.json" in entries:
                raise OSError("Unaccounted saved review")
        else:
            if entries.get("review.json") != ("100644", "blob", manifest.review_object):
                raise OSError("Saved review has no matching graph edge")
            if manifest.review_object not in reviewed:
                review, references = _load_review_payload(git, manifest, verified)
                reviewed[manifest.review_object] = (
                    manifest.review_size,
                    manifest.review_sha256,
                    _review_meaning(review.saved),
                    references,
                )
            elif reviewed[manifest.review_object][:2] != (
                manifest.review_size,
                manifest.review_sha256,
            ):
                raise OSError("Shared review payload has inconsistent declarations")
            else:
                references = reviewed[manifest.review_object][3]
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
                if references - role_hashes != {
                    row.sha256 for row in manifest.review_content
                }:
                    raise OSError(
                        "Repeated saved review references changed their owned graph"
                    )
        meaning = (
            reviewed[manifest.review_object][2]
            if manifest.review_object is not None
            else None
        )
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
            )
            != manifest.semantic_fingerprint
        ):
            raise OSError("Retained checkpoint semantic interpretation disagrees")
        if tip_manifest is None:
            tip_manifest, tip_review = manifest, review
        # Each generation is independently checked; retaining its raw control
        # bodies would turn the per-response budget into a lifetime limit.
        controls = {}
        current, generation = manifest.previous, generation - 1
    if generation != 0:
        raise OSError("Retained checkpoint chain is incomplete")
    verify_blobs(
        [*git.prefix, "cat-file", "--batch"],
        env=git.env,
        objects=tuple(row for oid, row in blobs.items() if oid not in verified),
        timeout=120,
    )
    return CheckpointRead(
        schema_id="brz2obsidian.checkpoint-read",
        schema_version=1,
        status="valid",
        code="validated",
        locator=locator,
        manifest=tip_manifest,
        review=tip_review,
        message="Complete owned local checkpoint graph validated.",
    )


def inspect_history(vault, *, subjects=(), git_executable=None, active_operation=None):
    root = Path(vault).absolute()
    admission, history = _observe_vault(
        root,
        subjects=subjects,
        git_executable=git_executable,
        active_operation=active_operation,
    )
    status = "unavailable"
    try:
        if admission.status == "supported" and admission.repository.kind == "root":
            if history is None:
                history = _read(root, _Git(root, git_executable))
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
    return VaultHistoryInspection(
        schema_id="brz2obsidian.vault-history-inspection",
        schema_version=1,
        status=status,
        admission=admission,
        checkpoint=history,
    )


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
):
    root, source = Path(vault).absolute(), Path(source).absolute()
    objects = False
    object_storage = "not_started"
    written_declarations = ()
    control_write_pending = False
    retained = False
    commit = ref = None
    try:
        subjects = tuple(VaultSubject.model_validate(s) for s in subjects)
        if (
            boundary not in ("local", "prepared", "result")
            or (boundary == "prepared") != (proposed is not None)
            or (boundary == "result") != (expected_prepared is not None)
        ):
            return result("refused", "invalid_checkpoint_boundary")
        observed_history = inspect_history(
            root,
            subjects=subjects,
            git_executable=git_executable,
            active_operation=active_operation,
        )
        current = observed_history.admission
        if (
            current.status != "supported"
            or current.repository.kind != "root"
            or current.observation_fingerprint != admission.observation_fingerprint
        ):
            return result("refused", "current_admission_required")
        identity = OutputIdentity.model_validate(identity)
        if source == root or root in source.parents or source in root.parents:
            return result("refused", "distinct_source_required")
        git = _Git(root, git_executable)
        association_id = digest(
            (vault_id, import_id, identity.collection_id, identity.module_id)
        )
        ref = "refs/brz2obsidian/imports/" + association_id + "/checkpoints"
        association = VaultAssociation(
            schema_id="brz2obsidian.vault-association",
            schema_version=1,
            association_id=association_id,
            vault_id=vault_id,
            import_id=import_id,
            collection_id=identity.collection_id,
            module_id=identity.module_id,
            vault_anchor=verify_directory(root),
            git_anchor=verify_directory(root / ".git"),
            ref=ref,
        )
        prior = observed_history.checkpoint
        if observed_history.status == "unavailable" or prior is None:
            return result("refused", "current_history_unavailable")
        if prior.status == "valid" and prior.locator.association != association:
            return result("refused", "association_mismatch")
        if boundary == "result" and (
            prior.status != "valid"
            or prior.locator.commit != expected_prepared
            or prior.manifest.boundary != "prepared"
            or prior.manifest.identity != identity
        ):
            return result("refused", "prepared_history_required")
        saved = None
        if review is not None:
            saved_result = save_review(review)
            if (
                saved_result.status != "saved"
                or review.facts.incoming_identity != identity
            ):
                return result("refused", "invalid_current_review")
            saved = saved_result.record
        retaining_prepared = boundary == "result"
        if retaining_prepared:
            if saved is not None and _review_meaning(saved) != _review_meaning(
                prior.review.saved if prior.review is not None else None
            ):
                return result("refused", "prepared_review_changed")
            saved = prior.review.saved if prior.review is not None else None
            if (
                current.policy_continuity_fingerprint
                != prior.manifest.policy_continuity_fingerprint
            ):
                return result("refused", "prepared_policy_changed")
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
                return result("refused", "scoped_review_required")
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
                return result("refused", "scoped_review_required")
            if required.kind == "tracking":
                included_subjects.update(required.subjects)
        if saved is not None:
            scopes = {
                reconciliation_subject_id(
                    identity.module_id, identity.collection_id, s.item_id, s.facet
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
            if boundary != "local":
                selected_effects = select_review_effects(saved.plan)
                if selected_effects.status == "selected":
                    for effect in selected_effects.files:
                        if effect.subject_id not in scopes:
                            return result("refused", "review_scope_changed")
                        scopes[effect.subject_id].add(effect.path)
            if any(
                s.subject_id not in scopes or s.path not in scopes[s.subject_id]
                for s in subjects
            ):
                return result("refused", "review_scope_changed")
        included_paths = {s.path for s in subjects if s.subject_id in included_subjects}
        if proposed is not None:
            proposed = Path(proposed).absolute()
            if proposed == root or root in proposed.parents or proposed in root.parents:
                return result("refused", "distinct_proposed_required")
        temp_base = git.inspection.temporary_base()
        if temp_base is None:
            return result("refused", "temporary_storage_unavailable")
        if (
            temp_base == source
            or source in temp_base.parents
            or proposed is not None
            and (temp_base == proposed or proposed in temp_base.parents)
        ):
            return result("refused", "temporary_storage_overlaps_input")
        vault_size = sum(
            f.size
            for f in current.inventory
            if not f.excluded or f.path in included_paths
        )
        if not _capture_resources(root, source, proposed, temp_base, vault_size, saved):
            return result("refused", "insufficient_checkpoint_resources")
        with tempfile.TemporaryDirectory(
            prefix="brz2obsidian-capture-", dir=temp_base
        ) as name:
            directory = Path(name)
            git.suppress_hooks(directory)
            source_files, source_spools = _spool(source, directory)
            if source_binding is not None:
                from brz2obsidian.application.source_payload_contracts import (
                    ReviewedSourceBinding,
                )

                binding = ReviewedSourceBinding.model_validate(source_binding)
                observed_rows = tuple(
                    (row.path, row.mode, row.size, row.sha256) for row in binding.files
                )
                if tuple(
                    row[:4] for row in source_files
                ) != observed_rows or binding.source_anchor != verify_directory(source):
                    return result("refused", "source_payload_changed")
            vault_files, vault_spools = _spool(
                root,
                directory,
                [
                    f.path
                    for f in current.inventory
                    if not f.excluded or f.path in included_paths
                ],
                offset=len(source_files),
            )
            proposed_files, proposed_spools = [], []
            if proposed is not None:
                proposed_files, proposed_spools = _spool(
                    proposed, directory, offset=len(source_files) + len(vault_files)
                )
                if any(
                    row[0] in current.recovery_gaps and row[0] not in included_paths
                    for row in proposed_files
                ):
                    return result("refused", "scoped_inclusion_required")
            admitted = [
                (f.path, f.mode, f.size, f.sha256, f.identity)
                for f in current.inventory
                if not f.excluded or f.path in included_paths
            ]
            if vault_files != admitted:
                return result("refused", "capture_changed")
            if boundary == "result":
                semantic_inventory = lambda rows: [
                    (row[0], row[1], row[2], row[3]) for row in rows
                ]
                declared = lambda files: [
                    (f.path, f.mode, f.size, f.sha256) for f in files
                ]
                if semantic_inventory(vault_files) != declared(
                    prior.manifest.proposed
                ) or semantic_inventory(source_files) != declared(
                    prior.manifest.source
                ):
                    return result(
                        "refused",
                        "result_inventory_mismatch",
                        commit=prior.locator.commit,
                        ref=ref,
                        retained=True,
                    )
            inputs = source_spools + vault_spools + proposed_spools
            if saved is not None:
                selected_review = (
                    boundary == "prepared"
                    and select_review_effects(saved.plan).status == "selected"
                )
                identified = {
                    (item.identity.item_id, item.facet)
                    for item in saved.plan.facts.identity_inventory
                    if item.identity_state == "valid" and item.identity is not None
                }
                for subject in saved.plan.facts.subjects:
                    for expected, path, inventory in (
                        (subject.incoming, subject.path, source_files),
                    ) + (
                        ()
                        if retaining_prepared
                        or (
                            selected_review
                            and (subject.item_id, subject.facet) in identified
                        )
                        else (
                            (
                                subject.current.content,
                                subject.current.path,
                                vault_files,
                            ),
                        )
                    ):
                        observed = next(
                            (row for row in inventory if row[0] == path), None
                        )
                        if (
                            (expected is None) != (observed is None)
                            or expected is not None
                            and (
                                len(expected.data) != observed[2]
                                or hashlib.sha256(expected.data).hexdigest()
                                != observed[3]
                            )
                        ):
                            return result("refused", "review_bytes_changed")
                if selected_review:
                    for item in saved.plan.facts.identity_inventory:
                        if item.identity_state != "valid":
                            continue
                        expected, path = item.current.content, item.current.path
                        observed = next(
                            (row for row in vault_files if row[0] == path), None
                        )
                        if (
                            (expected is None) != (observed is None)
                            or expected is not None
                            and (
                                len(expected.data) != observed[2]
                                or hashlib.sha256(expected.data).hexdigest()
                                != observed[3]
                            )
                        ):
                            return result("refused", "review_bytes_changed")
            # Git reads regular app-owned spools; raw payload never enters the
            # bounded control pipe or passes through attributes/filters.
            expected_oids = [
                _spool_oid(directory, path, record[2], record[3])
                for path, record in zip(
                    inputs, source_files + vault_files + proposed_files, strict=True
                )
            ]
            written_declarations = tuple(
                (oid, row[2], row[3], None)
                for oid, row in zip(
                    expected_oids,
                    source_files + vault_files + proposed_files,
                    strict=True,
                )
            )
            rows = [
                CheckpointFile(path=p, mode=m, size=size, sha256=sha, object_id=oid)
                for (p, m, size, sha, _), oid in zip(
                    source_files + vault_files + proposed_files,
                    expected_oids,
                    strict=True,
                )
            ]
            source_rows = tuple(rows[: len(source_files)])
            vault_rows = tuple(
                rows[len(source_files) : len(source_files) + len(vault_files)]
            )
            proposed_rows = (
                tuple(rows[len(source_files) + len(vault_files) :])
                if boundary == "prepared"
                else prior.manifest.proposed
                if retaining_prepared
                else ()
            )
            preimage_rows = (
                prior.manifest.preimage if retaining_prepared else vault_rows
            )
            gaps = tuple(
                path for path in current.recovery_gaps if path not in included_paths
            )
            semantic = _semantic(
                association,
                identity,
                source_rows,
                vault_rows,
                preimage_rows,
                proposed_rows,
                gaps,
                boundary,
                current.policy_fingerprint,
                saved,
            )
            if (
                prior.status == "valid"
                and prior.manifest.semantic_fingerprint == semantic
            ):
                if (
                    not _source_matches(source, source_files)
                    or proposed is not None
                    and not _source_matches(proposed, proposed_files)
                ):
                    return result("refused", "capture_changed")
                return result(
                    "unchanged",
                    "already_retained",
                    commit=prior.locator.commit,
                    ref=ref,
                    retained=True,
                )
            if stale_history and not retaining_prepared:
                return result("refused", "current_history_review_required")
            object_storage = "possible"
            oids = (
                git.call(
                    "hash-object",
                    "-w",
                    "--no-filters",
                    "--stdin-paths",
                    input=_quoted_paths(inputs),
                )
                .decode()
                .splitlines()
            )
            if oids != expected_oids:
                raise OSError("Incomplete raw object write")
            verify_blobs(
                [*git.prefix, "cat-file", "--batch"],
                env=git.env,
                objects=written_declarations,
            )
            objects, object_storage = (
                bool(inputs),
                "verified" if inputs else "not_started",
            )
            if (
                not _source_matches(source, source_files)
                or proposed is not None
                and not _source_matches(proposed, proposed_files)
            ):
                return result("refused", "capture_changed", objects=objects)
            review_raw, review_payloads = (
                _review_shape(saved) if saved is not None else (None, {})
            )
            role_hashes = {
                row.sha256
                for inventory in (source_rows, vault_rows, preimage_rows, proposed_rows)
                for row in inventory
            }
            review_content = []
            for sha in sorted(set(review_payloads) - role_hashes):
                payload = review_payloads[sha]
                spool = directory / ("review-content-" + sha)
                spool.write_bytes(payload)
                expected_oid = _spool_oid(directory, spool, len(payload), sha)
                declaration = (expected_oid, len(payload), sha, None)
                written_declarations += (declaration,)
                object_storage = "possible"
                actual_oid = (
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
                if actual_oid != expected_oid:
                    raise OSError("Saved review byte object write changed")
                verify_blobs(
                    [*git.prefix, "cat-file", "--batch"],
                    env=git.env,
                    objects=(declaration,),
                )
                objects, object_storage = True, "verified"
                review_content.append(
                    CheckpointFile(
                        path=sha,
                        mode="100644",
                        size=len(payload),
                        sha256=sha,
                        object_id=actual_oid,
                    )
                )
            review_oid = None
            if review_raw is not None:
                spool = directory / "saved-review"
                spool.write_bytes(review_raw)
                review_sha = hashlib.sha256(review_raw).hexdigest()
                expected_oid = _spool_oid(directory, spool, len(review_raw), review_sha)
                declaration = (expected_oid, len(review_raw), review_sha, None)
                written_declarations += (declaration,)
                object_storage = "possible"
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
                objects, object_storage = True, "verified"
            previous = prior.locator.commit if prior.status == "valid" else None
            generation = prior.manifest.generation + 1 if previous else 1
            manifest = CheckpointManifest(
                schema_id="brz2obsidian.checkpoint-manifest",
                schema_version=1,
                association_id=association_id,
                generation=generation,
                boundary=boundary,
                identity=identity,
                source=source_rows,
                vault=vault_rows,
                preimage=preimage_rows,
                proposed=proposed_rows,
                review_content=tuple(review_content),
                recovery_gaps=gaps,
                semantic_fingerprint=semantic,
                previous=previous,
                review_object=review_oid,
                review_size=len(review_raw) if review_raw is not None else None,
                review_sha256=hashlib.sha256(review_raw).hexdigest()
                if review_raw is not None
                else None,
                policy_fingerprint=current.policy_fingerprint,
                policy_continuity_fingerprint=current.policy_continuity_fingerprint,
            )
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
                written_declarations += (declaration,)
                object_storage = "possible"
                oid = (
                    git.call("hash-object", "-w", "--stdin", input=payload)
                    .decode()
                    .strip()
                )
                if oid != expected_oid:
                    raise OSError("Checkpoint metadata object write changed")
                verify_blobs(
                    [*git.prefix, "cat-file", "--batch"],
                    env=git.env,
                    objects=(declaration,),
                )
                objects, object_storage = True, "verified"
                metadata.append((path, "100644", oid))
            if review_oid is not None:
                metadata.append(("review.json", "100644", review_oid))
            roots = []
            for role, inventory in (
                ("source", source_rows),
                ("vault", vault_rows),
                ("preimage", preimage_rows),
                ("proposed", proposed_rows),
            ):
                control_write_pending = True
                object_storage = "possible"
                role_tree = git.tree([(f.path, f.mode, f.object_id) for f in inventory])
                _control_objects(git, {role_tree: "tree"}, {})
                objects, object_storage, control_write_pending = True, "verified", False
                roots.append((role, "040000", role_tree))
            if review_content:
                control_write_pending = True
                object_storage = "possible"
                review_tree = git.tree(
                    [(f.path, f.mode, f.object_id) for f in review_content]
                )
                _control_objects(git, {review_tree: "tree"}, {})
                objects, object_storage, control_write_pending = True, "verified", False
                roots.append(("review-content", "040000", review_tree))
            control_write_pending = True
            object_storage = "possible"
            tree = git.tree([*metadata, *roots])
            _control_objects(git, {tree: "tree"}, {})
            objects, object_storage, control_write_pending = True, "verified", False
            control_write_pending = True
            object_storage = "possible"
            commit = (
                git.call(
                    "commit-tree",
                    tree,
                    *(["-p", previous] if previous else []),
                    input=b"brz2obsidian checkpoint\n",
                )
                .decode()
                .strip()
            )
            _control_objects(git, {commit: "commit"}, {})
            objects, object_storage, control_write_pending = True, "verified", False
            git.call("update-ref", ref, commit, previous or "0" * 40)
            if git.call("rev-parse", "--verify", ref).decode().strip() != commit:
                raise OSError("Owned checkpoint ref did not retain its commit")
            retained = True
            metadata_dir = root / ".brz2obsidian"
            metadata_dir.mkdir(exist_ok=True)
            locator = CheckpointLocator(
                schema_id="brz2obsidian.checkpoint-locator",
                schema_version=1,
                association=association,
                generation=generation,
                commit=commit,
            )
            temporary = metadata_dir / "locator.pending"
            with temporary.open("xb") as output:
                output.write(locator.model_dump_json().encode())
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, metadata_dir / "locator.json")
        return result(
            "captured",
            "retained",
            commit=commit,
            ref=ref,
            retained=True,
            objects=objects,
        )
    except OSError, ValueError, TypeError, UnicodeError:
        if (
            object_storage == "possible"
            and written_declarations
            and not control_write_pending
        ):
            try:
                verify_blobs(
                    [*git.prefix, "cat-file", "--batch"],
                    env=git.env,
                    objects=written_declarations,
                )
                objects, object_storage = True, "verified"
            except OSError, ValueError, TypeError, UnicodeError:
                pass
        if commit is not None and ref is not None and not retained:
            try:
                retained = (
                    git.call("rev-parse", "--verify", ref).decode().strip() == commit
                )
            except OSError, ValueError, TypeError, UnicodeError:
                pass
        return result(
            "failed",
            "capture_unavailable",
            commit=commit,
            ref=ref,
            retained=retained,
            objects=objects,
            object_storage=object_storage,
        )


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
