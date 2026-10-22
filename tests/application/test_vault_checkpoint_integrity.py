"""H01 refusal and preservation through public checkpoint operations."""

import hashlib
import json
import os
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest

from brz2obsidian.application.checkpoint_contracts import (
    CheckpointLocator,
    CheckpointManifest,
    VaultAssociation,
)
from brz2obsidian.application.operations import Operations

_EVIDENCE = Path(__file__).resolve().parents[2] / "tmp/issue-272-integrity"
_SOURCE = {"Assets/source.bin": b"\x00source\xff", "Note.md": b"converted source\r\n"}
_VAULT = {
    ".obsidian/app.json": b'{"readableLineLength":false}\n',
    "Assets/vault.bin": b"\xffvault\x00\x80",
    "Note.md": b"authored mixed\r\nending\n",
    "unrelated.md": b"independent authored note\n",
}
_IDENTITY = {
    "collection_id": "integrity-collection",
    "module_id": "integrity-fixture",
    "module_version": "1",
    "profile_id": "literal-profile",
    "profile_version": "1",
    "output_format": 7,
    "settings_digest": "literal-settings",
}


def _timing(kind, started):
    _EVIDENCE.mkdir(parents=True, exist_ok=True)
    with (_EVIDENCE / "timings.jsonl").open("a", encoding="utf-8") as output:
        output.write(
            json.dumps(
                {
                    "kind": kind,
                    "seconds": time.perf_counter() - started,
                    "test": os.environ.get("PYTEST_CURRENT_TEST"),
                }
            )
            + "\n"
        )


def _git(vault, *args, input=None):
    started = time.perf_counter()
    value = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Integrity fixture",
            "-c",
            "user.email=integrity@example.invalid",
            "-C",
            str(vault),
            *args,
        ],
        input=input,
        capture_output=True,
        check=False,
        timeout=15,
    )
    _timing("fixture_git", started)
    assert value.returncode == 0, value.stderr
    return value.stdout


def _call(method, *args, **kwargs):
    started = time.perf_counter()
    try:
        return method(*args, **kwargs)
    finally:
        _timing(method.__name__, started)


def _blob(data):
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data,
        usedforsecurity=False,
    ).hexdigest()


def _state(container):
    return {
        path.relative_to(container).as_posix(): (
            path.stat().st_mode,
            path.read_bytes() if path.is_file() else None,
        )
        for path in sorted(container.rglob("*"))
    }


def _capture(operations, vault, source):
    return _call(
        operations.capture_checkpoint,
        vault,
        source,
        vault_id="integrity-vault",
        import_id="integrity-import",
        identity=_IDENTITY,
        admission=_call(operations.inspect_vault, vault),
    )


def _assert_intact(operations, vault, commit):
    value = _call(operations.read_checkpoint, vault)
    assert value.status == "valid"
    assert value.locator.commit == commit
    for role, files in (
        ("source", _SOURCE),
        ("vault", _VAULT),
        ("preimage", _VAULT),
        ("proposed", {}),
    ):
        assert [
            (row.path, row.mode, row.size, row.sha256, row.object_id)
            for row in getattr(value.manifest, role)
        ] == [
            (path, "100644", len(data), hashlib.sha256(data).hexdigest(), _blob(data))
            for path, data in sorted(files.items())
        ]
    return value


def _retarget(
    vault, result, *, manifest=None, association=None, omit=(), locator_changes=None
):
    rows = _git(vault, "ls-tree", "-z", result.commit).split(b"\0")
    replacements = {}
    for path, raw in (("manifest.json", manifest), ("association.json", association)):
        if raw is not None:
            oid = _git(vault, "hash-object", "-w", "--stdin", input=raw).strip()
            replacements[path] = b"100644 blob " + oid + b"\t" + path.encode()
    updated = []
    for row in rows:
        if row:
            path = row.split(b"\t", 1)[1].decode()
            if path not in omit:
                updated.append(replacements.get(path, row))
    tree = (
        _git(vault, "mktree", "-z", input=b"\0".join(updated) + b"\0").strip().decode()
    )
    commit = (
        _git(vault, "commit-tree", tree, input=b"controlled metadata tamper\n")
        .decode()
        .strip()
    )
    locator = vault / ".brz2obsidian/locator.json"
    value = json.loads(locator.read_bytes())
    value["commit"] = commit
    value.update(locator_changes or {})
    _git(vault, "update-ref", result.ref, commit)
    locator.write_text(json.dumps(value), encoding="utf-8")
    assert _git(vault, "rev-parse", result.ref).decode().strip() == commit
    assert json.loads(locator.read_bytes())["commit"] == commit
    for path, raw in (("manifest.json", manifest), ("association.json", association)):
        if raw is not None:
            assert _git(vault, "cat-file", "blob", commit + ":" + path) == raw
    return commit


def _assert_refused_without_repair(operations, container, vault, source):
    before = _state(container)
    reopened = _call(operations.read_checkpoint, vault)
    read_after = _state(container)
    refused = _capture(operations, vault, source)
    capture_after = _state(container)
    assert read_after == before
    assert capture_after == before
    assert (reopened.status, refused.status) == ("refused", "refused")
    assert not refused.authored_files_changed


@contextmanager
def _restored(captured):
    operations, _, vault, _, result = captured
    locator = vault / ".brz2obsidian/locator.json"
    original = locator.read_bytes()
    assert json.loads(original)["commit"] == result.commit
    assert _git(vault, "rev-parse", result.ref).decode().strip() == result.commit
    try:
        yield
    finally:
        _git(vault, "update-ref", result.ref, result.commit)
        locator.write_bytes(original)
        _assert_intact(operations, vault, result.commit)


@pytest.fixture(scope="module")
def captured():
    base = Path(tempfile.gettempdir()).resolve()
    assert not any((parent / ".git").exists() for parent in (base, *base.parents))
    container = Path(
        tempfile.mkdtemp(prefix="brz2obsidian-272-integrity-", dir=base)
    ).resolve()
    assert container.parent == base
    token = uuid4().hex
    record = {
        "owner": token,
        "base": str(base),
        "root": str(container),
        "vault": str(container / "vault"),
        "source": str(container / "converted"),
        "git": str(container / "vault/.git"),
    }
    (container / ".fixture-owner.json").write_text(json.dumps(record), encoding="utf-8")
    _EVIDENCE.mkdir(parents=True, exist_ok=True)
    (_EVIDENCE / (token + ".json")).write_text(json.dumps(record), encoding="utf-8")
    vault, source = container / "vault", container / "converted"
    vault.mkdir()
    source.mkdir()
    with pytest.MonkeyPatch.context() as environment:
        environment.setenv("GIT_CONFIG_NOSYSTEM", "1")
        environment.setenv("GIT_CONFIG_GLOBAL", os.devnull)
        for root, files in ((vault, _VAULT), (source, _SOURCE)):
            for path, data in files.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        _git(vault, "init", "-q", "-b", "user-main")
        _git(vault, "config", "core.autocrlf", "false")
        _git(vault, "config", "integrity.literal", "preserve exact user configuration")
        _git(vault, "add", ".")
        _git(vault, "commit", "-qm", "independent user history")
        _git(vault, "update-ref", "refs/tags/user-tag", "HEAD")
        (vault / "Note.md").write_bytes(b"independent staged bytes\n")
        _git(vault, "add", "Note.md")
        _git(vault, "update-index", "--chmod=+x", "Note.md")
        (vault / "Note.md").write_bytes(_VAULT["Note.md"])
        index = (vault / ".git/index").read_bytes()
        config = (vault / ".git/config").read_bytes()
        user_refs = _git(vault, "show-ref")
        staged = b"100755 " + _blob(b"independent staged bytes\n").encode()
        assert staged + b" 0\tNote.md\0" in _git(vault, "ls-files", "--stage", "-z")
        operations = Operations()
        result = _capture(operations, vault, source)
        assert result.status == "captured"
        assert result.history_retained and not result.authored_files_changed
        assert (vault / ".git/index").read_bytes() == index
        assert (vault / ".git/config").read_bytes() == config
        after_refs = _git(vault, "show-ref").splitlines()
        assert all(row in after_refs for row in user_refs.splitlines())
        _assert_intact(operations, vault, result.commit)
        actual = {
            path.decode(): data.split()
            for row in _git(vault, "ls-tree", "-r", "-z", result.commit).split(b"\0")
            if row
            for data, path in (row.split(b"\t", 1),)
        }
        for role, files in (
            ("source", _SOURCE),
            ("vault", _VAULT),
            ("preimage", _VAULT),
        ):
            for path, data in files.items():
                assert actual[role + "/" + path] == [
                    b"100644",
                    b"blob",
                    _blob(data).encode(),
                ]
        batch = _git(
            vault,
            "cat-file",
            "--batch",
            input=b"".join(
                _blob(data).encode() + b"\n"
                for data in (*_SOURCE.values(), *_VAULT.values())
            ),
        )
        expected_batch = b"".join(
            _blob(data).encode()
            + b" blob "
            + str(len(data)).encode()
            + b"\n"
            + data
            + b"\n"
            for data in (*_SOURCE.values(), *_VAULT.values())
        )
        assert batch == expected_batch
        yield operations, container, vault, source, result
    # Retain this explicitly owned fixture and its audit evidence.


def test_missing_required_blob_refuses_read_and_capture_without_repair(captured):
    operations, container, vault, source, result = captured
    oid = _blob(_VAULT["Assets/vault.bin"])
    object_path = vault / ".git/objects" / oid[:2] / oid[2:]
    backup = container / ("owned-object-backup-" + uuid4().hex)
    original = object_path.read_bytes()
    object_path.rename(backup)
    try:
        _assert_refused_without_repair(operations, container, vault, source)
    finally:
        backup.rename(object_path)
        assert object_path.read_bytes() == original
        _assert_intact(operations, vault, result.commit)


@pytest.mark.parametrize(
    "record", ("manifest.json", "association.json", "locator.json")
)
def test_duplicate_interpretation_field_refuses_coherently_rooted_history(
    captured, record
):
    operations, container, vault, source, result = captured
    with _restored(captured):
        raw = (
            (vault / ".brz2obsidian/locator.json").read_bytes()
            if record == "locator.json"
            else _git(vault, "cat-file", "blob", result.commit + ":" + record)
        )
        duplicate = raw[:-1] + b',"schema_version":1}'
        assert (
            duplicate.count(b'"schema_version":1')
            == raw.count(b'"schema_version":1') + 1
        )
        if record == "locator.json":
            (vault / ".brz2obsidian/locator.json").write_bytes(duplicate)
        elif record == "manifest.json":
            _retarget(vault, result, manifest=duplicate)
        else:
            _retarget(vault, result, association=duplicate)
        _assert_refused_without_repair(operations, container, vault, source)


def test_association_identity_must_match_reachable_manifest_identity(captured):
    operations, container, vault, source, result = captured
    with _restored(captured):
        association = json.loads(
            _git(vault, "cat-file", "blob", result.commit + ":association.json")
        )
        assert association["collection_id"] == "integrity-collection"
        association["collection_id"] = "different-unrelated-collection"
        _retarget(
            vault,
            result,
            association=json.dumps(association).encode(),
            locator_changes={"association": association},
        )
        _assert_refused_without_repair(operations, container, vault, source)


def test_persisted_malformed_manifest_refuses_without_repair(captured):
    operations, container, vault, source, result = captured
    with _restored(captured):
        _retarget(vault, result, manifest=b'{"schema_id":')
        _assert_refused_without_repair(operations, container, vault, source)


@pytest.mark.parametrize("record", ("manifest", "association", "locator"))
@pytest.mark.parametrize("fault", ("missing", "unknown", "version", "type"))
def test_public_checkpoint_records_are_closed_strict_version_one_values(record, fault):
    association_id = hashlib.sha256(
        b'["integrity-vault","integrity-import","integrity-collection","integrity-fixture"]'
    ).hexdigest()
    association = {
        "schema_id": "brz2obsidian.vault-association",
        "schema_version": 1,
        "association_id": association_id,
        "vault_id": "integrity-vault",
        "import_id": "integrity-import",
        "collection_id": "integrity-collection",
        "module_id": "integrity-fixture",
        "vault_anchor": "literal-schema-anchor-vault",
        "git_anchor": "literal-schema-anchor-git",
        "ref": "refs/brz2obsidian/imports/" + association_id + "/checkpoints",
    }
    manifest = {
        "schema_id": "brz2obsidian.checkpoint-manifest",
        "schema_version": 1,
        "association_id": association_id,
        "generation": 1,
        "boundary": "local",
        "identity": _IDENTITY,
        "source": [],
        "vault": [],
        "preimage": [],
        "proposed": [],
        "recovery_gaps": [],
        "semantic_fingerprint": "a" * 64,
        "previous": None,
        "review_object": None,
    }
    locator = {
        "schema_id": "brz2obsidian.checkpoint-locator",
        "schema_version": 1,
        "association": association,
        "generation": 1,
        "commit": "1" * 40,
    }
    model, value, required = {
        "manifest": (CheckpointManifest, manifest, "identity"),
        "association": (VaultAssociation, association, "module_id"),
        "locator": (CheckpointLocator, locator, "commit"),
    }[record]
    assert model.model_validate_json(json.dumps(value)).schema_version == 1
    if fault == "missing":
        del value[required]
    elif fault == "unknown":
        value["unknown_interpretation"] = "unaccepted meaning"
    elif fault == "version":
        value["schema_version"] = 2
    elif fault == "type":
        value["schema_version"] = True
    with pytest.raises(ValueError):
        model.model_validate_json(json.dumps(value))


def test_missing_owned_ref_refuses_without_recreating_it(captured):
    operations, container, vault, source, result = captured
    with _restored(captured):
        _git(vault, "update-ref", "-d", result.ref)
        assert _git(vault, "for-each-ref", result.ref) == b""
        _assert_refused_without_repair(operations, container, vault, source)


def test_json_blob_names_cannot_replace_required_source_graph_edge(captured):
    operations, container, vault, source, result = captured
    with _restored(captured):
        commit = _retarget(vault, result, omit=("source",))
        reachable = {
            row.split(b" ", 1)[0]
            for row in _git(vault, "rev-list", "--objects", result.ref).splitlines()
        }
        assert all(_blob(data).encode() not in reachable for data in _SOURCE.values())
        manifest = json.loads(
            _git(vault, "cat-file", "blob", commit + ":manifest.json")
        )
        assert {row["object_id"] for row in manifest["source"]} == {
            _blob(data) for data in _SOURCE.values()
        }
        _assert_refused_without_repair(operations, container, vault, source)


def test_locator_and_reachable_association_must_agree(captured):
    operations, container, vault, source, result = captured
    with _restored(captured):
        association = json.loads(
            _git(vault, "cat-file", "blob", result.commit + ":association.json")
        )
        association["import_id"] = "different-import"
        _retarget(vault, result, association=json.dumps(association).encode())
        _assert_refused_without_repair(operations, container, vault, source)


def test_previous_checkpoint_requires_real_parent_edge(captured):
    operations, container, vault, source, result = captured
    with _restored(captured):
        value = json.loads(
            _git(vault, "cat-file", "blob", result.commit + ":manifest.json")
        )
        value.update({"generation": 2, "previous": result.commit})
        commit = _retarget(
            vault,
            result,
            manifest=json.dumps(value).encode(),
            locator_changes={"generation": 2},
        )
        assert (
            _git(vault, "rev-list", "--parents", "-n", "1", commit)
            == commit.encode() + b"\n"
        )
        _assert_refused_without_repair(operations, container, vault, source)
