"""Literal retained-byte answers through the public checkpoint payload reader."""

import json
import stat
import subprocess
import tempfile
import zlib
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from brz2obsidian.application.checkpoint_contracts import CheckpointLocator
from brz2obsidian.application.checkpoint_payload_contracts import (
    CheckpointPayloadChunk,
    CheckpointPayloadRead,
    CheckpointPayloadRequest,
)
from brz2obsidian.application.operations import Operations
from brz2obsidian.publication.checkpoint_payload import read_checkpoint_payload


@pytest.fixture(scope="module")
def retained():
    container = Path(tempfile.mkdtemp(prefix="brz2obsidian-280-reader-"))
    record = {
        "owner": uuid4().hex,
        "root": str(container.resolve()),
        "base": str(Path(tempfile.gettempdir()).resolve()),
    }
    (container / ".fixture-owner.json").write_text(json.dumps(record), encoding="utf-8")
    evidence = Path(__file__).resolve().parents[2] / "tmp/issue-280-reader/fixtures"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (record["owner"] + ".json")).write_text(
        json.dumps(record), encoding="utf-8"
    )
    vault, source = container / "vault", container / "source"
    vault.mkdir()
    source.mkdir()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "note.md").write_bytes(b"authored\r\n")
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "user history")
    (vault / "note.md").write_bytes(b"staged\n")
    git(vault, "add", ".")
    (vault / "note.md").write_bytes(b"later\xff")
    (source / "note.md").write_bytes(b"A\r\nB\x00\xffZ")
    (source / "empty.bin").write_bytes(b"")
    operations = Operations()
    captured = operations.capture_checkpoint(
        vault,
        source,
        vault_id="reader-vault",
        import_id="reader-import",
        identity={
            "collection_id": "reader-collection",
            "module_id": "fixture",
            "module_version": "1",
            "profile_id": "profile",
            "profile_version": "1",
            "output_format": 7,
            "settings_digest": "literal-settings",
        },
        admission=operations.inspect_vault(vault),
    )
    assert captured.status == "captured"
    checkpoint = operations.read_checkpoint(vault)
    assert checkpoint.status == "valid"
    return vault, checkpoint.locator


def git(vault, *args, input=None):
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Reader fixture",
            "-c",
            "user.email=reader@example.invalid",
            "-C",
            str(vault),
            *args,
        ],
        input=input,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def state(vault):
    return {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }


def literal_page():
    return {
        "path": "note.md",
        "mode": "100644",
        "object_id": "55dc89bc315a91e1c3dc4216c8b9b3a345447eab",
        "sha256": "12a79bc9e4a98a1c672d9be2118a83017128bf98b4bbe36037bc25e93c2c7245",
        "size": 7,
        "offset": 2,
        "data": b"\nB\x00",
        "eof": False,
        "omitted": True,
        "next_offset": 5,
    }


def test_byte_page_cannot_claim_eof_while_its_suffix_is_omitted():
    fields = literal_page()
    chunk = CheckpointPayloadChunk(**fields)
    assert chunk.data == b"\nB\x00" and chunk.next_offset == 5
    # Each literal counterexample contradicts one independent range statement.
    for contradiction in (
        {"size": 4, "next_offset": None},
        {"eof": True},
        {"omitted": False},
        {"next_offset": 4},
        {"data": b"", "next_offset": 2},
    ):
        with pytest.raises(ValidationError):
            CheckpointPayloadChunk(**(fields | contradiction))


def test_refused_read_cannot_release_a_verified_page_and_codes_are_closed():
    # Contract shape alone conveys no physical history or publication authority.
    locator = CheckpointLocator(
        schema_id="brz2obsidian.checkpoint-locator",
        schema_version=1,
        association={
            "schema_id": "brz2obsidian.vault-association",
            "schema_version": 1,
            "association_id": "1" * 64,
            "vault_id": "literal-vault",
            "import_id": "literal-import",
            "collection_id": "literal-collection",
            "module_id": "fixture",
            "vault_anchor": "literal-vault-anchor",
            "git_anchor": "literal-git-anchor",
            "ref": "refs/brz2obsidian/imports/" + "1" * 64 + "/checkpoints",
        },
        generation=1,
        commit="2" * 40,
    )
    fields = {
        "schema_id": "brz2obsidian.checkpoint-payload-read",
        "schema_version": 1,
        "status": "available",
        "code": "verified",
        "locator": locator,
        "role": "source",
        "chunks": (CheckpointPayloadChunk(**literal_page()),),
        "message": "Literal available page.",
    }
    available = CheckpointPayloadRead(**fields)
    assert available.chunks[0].data == b"\nB\x00"
    refused = {
        "status": "refused",
        "code": "history_unavailable",
        "locator": None,
        "chunks": (),
    }
    assert CheckpointPayloadRead(**(fields | refused)).chunks == ()
    # Separate contradictions keep one check from masking another check.
    for contradiction in (
        {"code": "history_unavailable"},
        {"locator": None},
        {"chunks": ()},
        refused | {"code": "verified"},
        refused | {"chunks": fields["chunks"]},
        refused | {"locator": locator},
    ):
        with pytest.raises(ValidationError):
            CheckpointPayloadRead(**(fields | contradiction))
    with pytest.raises(ValidationError):
        CheckpointPayloadRead(**(fields | {"code": "invented"}))


def test_retained_pages_are_exact_bound_and_read_only(retained):
    vault, locator = retained
    before = state(vault)
    page = read_checkpoint_payload(
        vault,
        locator=locator,
        requests=(
            CheckpointPayloadRequest(path="note.md", offset=2, limit=3),
            CheckpointPayloadRequest(path="empty.bin", limit=1),
        ),
        byte_limit=4,
    )
    assert page.status == "available"
    assert page.locator == locator and page.role == "source"
    note, empty = page.chunks
    assert (
        note.path,
        note.data,
        note.size,
        note.offset,
        note.mode,
        note.eof,
        note.omitted,
        note.next_offset,
    ) == ("note.md", b"\nB\x00", 7, 2, "100644", False, True, 5)
    assert (
        note.sha256
        == "12a79bc9e4a98a1c672d9be2118a83017128bf98b4bbe36037bc25e93c2c7245"
    )
    assert note.object_id == "55dc89bc315a91e1c3dc4216c8b9b3a345447eab"
    assert (
        empty.data,
        empty.size,
        empty.eof,
        empty.omitted,
        empty.next_offset,
    ) == (b"", 0, True, False, None)
    tail = read_checkpoint_payload(
        vault,
        locator=locator,
        requests=(
            CheckpointPayloadRequest(path="note.md", offset=note.next_offset, limit=3),
        ),
        byte_limit=3,
    )
    assert tail.status == "available"
    assert (
        tail.chunks[0].data,
        tail.chunks[0].eof,
        tail.chunks[0].next_offset,
    ) == (b"\xffZ", True, None)
    assert state(vault) == before


def test_empty_payload_uses_zero_budget_and_eof_is_a_valid_empty_page(retained):
    vault, locator = retained
    result = read_checkpoint_payload(
        vault,
        locator=locator,
        requests=(
            CheckpointPayloadRequest(path="empty.bin", limit=0),
            CheckpointPayloadRequest(path="note.md", offset=7, limit=0),
        ),
        byte_limit=0,
    )
    assert result.status == "available"
    assert [
        (chunk.data, chunk.offset, chunk.size, chunk.eof, chunk.omitted)
        for chunk in result.chunks
    ] == [(b"", 0, 0, True, False), (b"", 7, 7, True, True)]


def test_current_identity_role_path_and_finite_range_are_required(retained):
    vault, locator = retained
    default = {
        "locator": locator,
        "requests": (CheckpointPayloadRequest(path="note.md", limit=1),),
        "byte_limit": 1,
    }
    cases = [
        ({"locator": locator.model_copy(update={"generation": 2})}, "stale_locator"),
        ({"locator": locator.model_copy(update={"commit": "0" * 40})}, "stale_locator"),
        (
            {
                "locator": locator.model_copy(
                    update={
                        "association": locator.association.model_copy(
                            update={"collection_id": "foreign"}
                        )
                    }
                )
            },
            "stale_locator",
        ),
        ({"role": "not-a-role"}, "invalid_request"),
        ({"requests": ()}, "invalid_request"),
        (
            {"requests": (CheckpointPayloadRequest(path="note.md ", limit=1),)},
            "invalid_request",
        ),
        (
            {"requests": ({"path": "../note.md", "limit": 1},)},
            "payload_unavailable",
        ),
        (
            {"requests": (CheckpointPayloadRequest(path="Note.md", limit=1),)},
            "path_unavailable",
        ),
        ({"role": "proposed"}, "path_unavailable"),
        (
            {
                "requests": (
                    CheckpointPayloadRequest(path="note.md", offset=8, limit=1),
                )
            },
            "invalid_range",
        ),
        (
            {"requests": (CheckpointPayloadRequest(path="note.md", limit=0),)},
            "invalid_range",
        ),
        ({"byte_limit": 0}, "invalid_request"),
        ({"byte_limit": True}, "invalid_request"),
        (
            {
                "requests": (
                    CheckpointPayloadRequest(path="note.md", limit=(1 << 63) - 1),
                ),
                "byte_limit": (1 << 63) - 1,
            },
            "insufficient_memory",
        ),
    ]
    before = state(vault)
    for overrides, expected in cases:
        result = read_checkpoint_payload(vault, **(default | overrides))
        assert (result.status, result.code, result.chunks, result.locator) == (
            "refused",
            expected,
            (),
            None,
        )
        assert "A\r\nB" not in result.message and str(vault) not in result.message
    vault_page = read_checkpoint_payload(vault, **(default | {"role": "vault"}))
    assert vault_page.status == "available"
    assert (vault_page.chunks[0].data, vault_page.chunks[0].size) == (b"l", 6)
    assert state(vault) == before
    with pytest.raises(ValidationError):
        CheckpointPayloadRequest(path="note.md", limit=1, object_id="0" * 40)
    with pytest.raises(ValidationError):
        CheckpointPayloadRequest(path="note.md", offset=-1, limit=1)
    with pytest.raises(ValidationError):
        CheckpointPayloadRequest(path="../note.md", limit=1)
    with pytest.raises(ValidationError):
        vault_page.chunks[0].data = b"changed"


def test_even_prefix_bytes_require_complete_blob_integrity(retained):
    vault, locator = retained
    # Literal Git blob identity for the seven fixture bytes, independent of the reader.
    blob = vault / ".git/objects/55/dc89bc315a91e1c3dc4216c8b9b3a345447eab"
    original = blob.read_bytes()
    original_mode = blob.stat().st_mode
    args = {
        "locator": locator,
        "requests": (CheckpointPayloadRequest(path="note.md", limit=1),),
        "byte_limit": 1,
    }
    before = state(vault)
    blob.chmod(original_mode | stat.S_IWRITE)
    try:
        # The requested prefix remains A, but the unread suffix is corrupt.
        blob.write_bytes(zlib.compress(b"blob 7\0A\r\nB\x00\xffX"))
        corrupt = read_checkpoint_payload(vault, **args)
        assert corrupt.status == "refused" and corrupt.chunks == ()
        blob.unlink()
        missing = read_checkpoint_payload(vault, **args)
        assert missing.status == "refused" and missing.chunks == ()
    finally:
        blob.write_bytes(original)
        blob.chmod(original_mode)
    assert state(vault) == before


def test_reachable_role_edge_and_mode_must_match_manifest(retained):
    vault, locator = retained
    locator_path = vault / ".brz2obsidian/locator.json"
    original_locator = locator_path.read_bytes()
    original_root = git(vault, "ls-tree", "-z", locator.commit)
    source_tree = git(vault, "ls-tree", "-z", locator.commit + ":source")
    original_source_oid = git(vault, "rev-parse", locator.commit + ":source").strip()
    changes = (
        original_root.replace(b"\tsource\0", b"\tforeign-role\0"),
        original_root.replace(
            original_source_oid,
            git(
                vault,
                "mktree",
                "-z",
                input=source_tree.replace(
                    b"100644 blob 55dc89bc315a91e1c3dc4216c8b9b3a345447eab",
                    b"100755 blob 55dc89bc315a91e1c3dc4216c8b9b3a345447eab",
                ),
            ).strip(),
        ),
    )
    try:
        for entries in changes:
            tree = git(vault, "mktree", "-z", input=entries).decode().strip()
            commit = (
                git(vault, "commit-tree", tree, input=b"altered role edge\n")
                .decode()
                .strip()
            )
            git(vault, "update-ref", locator.association.ref, commit)
            current = locator.model_copy(update={"commit": commit})
            locator_path.write_bytes(current.model_dump_json().encode())
            before_read = state(vault)
            result = read_checkpoint_payload(
                vault,
                locator=current,
                requests=(CheckpointPayloadRequest(path="note.md", limit=1),),
                byte_limit=1,
            )
            assert result.status == "refused" and result.chunks == ()
            assert state(vault) == before_read
    finally:
        git(vault, "update-ref", locator.association.ref, locator.commit)
        locator_path.write_bytes(original_locator)
