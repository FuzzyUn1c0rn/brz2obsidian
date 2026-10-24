"""Compact review corruption refuses through public checkpoint operations."""

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.core import prepare_review, resolve_review
from tests.application.test_vault_checkpoint_integrity import _blob, _call, _git, _state
from tests.application.test_vault_checkpoints import fixture_case
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links

_BASELINE = b"baseline-only\n"
_CURRENT = b"authored current\r\n"
_INCOMING = b"incoming next\n"
_UNUSED = b"unused owned review bytes\n"


@dataclass(frozen=True)
class ReviewCase:
    operations: object
    vault: object
    source: object
    plan: object
    result: object
    locator: bytes
    manifest: bytes
    review: bytes
    root_rows: tuple[bytes, ...]


def _capture(case):
    return _call(
        case.operations.capture_checkpoint,
        case.vault,
        case.source,
        vault_id="compact-vault",
        import_id="compact-import",
        identity=case.plan.facts.incoming_identity,
        admission=_call(case.operations.inspect_vault, case.vault),
        review=case.plan,
    )


def _assert_intact(case):
    reopened = _call(case.operations.read_checkpoint, case.vault)
    assert reopened.status == "valid", reopened.code
    assert reopened.locator.commit == case.result.commit
    assert reopened.review.ready is False
    assert reopened.review.saved.plan == case.plan
    assert reopened.review.saved.plan.approvals[0].result.data == _CURRENT
    assert (
        reopened.review.saved.plan.approvals[0].source_memory.reviewed_incoming.data
        == _INCOMING
    )
    assert (case.vault / "Notes/Opening.md").read_bytes() == _CURRENT
    assert (case.source / "Notes/Opening.md").read_bytes() == _INCOMING


@pytest.fixture(scope="module")
def compact_checkpoint():
    facts = with_review_links(
        request(original=_BASELINE, current=_CURRENT, incoming=_INCOMING)
    )
    initial = prepare_review(facts, preflight=preflight())
    chosen = resolve_review(
        initial, action(initial, choice="current", decision_id="compact:keep-current")
    )
    assert chosen.status == "accepted" and chosen.plan.ready
    vault, source = fixture_case()
    (vault / "Notes").mkdir()
    (source / "Notes").mkdir()
    (vault / "Notes/Opening.md").write_bytes(_CURRENT)
    (source / "Notes/Opening.md").write_bytes(_INCOMING)
    _git(vault, "init", "-q")
    _git(vault, "config", "core.autocrlf", "false")
    _git(vault, "config", "compact.literal", "preserve user settings")
    _git(vault, "add", ".")
    _git(vault, "commit", "-qm", "independent user checkpoint baseline")
    (vault / "unrelated.bin").write_bytes(b"\x00\xffunrelated")
    operations = Operations()
    captured = _call(
        operations.capture_checkpoint,
        vault,
        source,
        vault_id="compact-vault",
        import_id="compact-import",
        identity=facts.incoming_identity,
        admission=_call(operations.inspect_vault, vault),
        review=chosen.plan,
    )
    assert captured.status == "captured", captured.code
    assert captured.history_retained and not captured.authored_files_changed
    review = _git(vault, "cat-file", "blob", captured.commit + ":review.json")
    manifest = _git(vault, "cat-file", "blob", captured.commit + ":manifest.json")
    baseline_sha = hashlib.sha256(_BASELINE).hexdigest()
    assert json.loads(review)["schema_id"] == "brz2obsidian.saved-review-refs"
    assert baseline_sha.encode("ascii") in review
    assert json.loads(manifest)["review_content"] == [
        {
            "path": baseline_sha,
            "mode": "100644",
            "size": len(_BASELINE),
            "sha256": baseline_sha,
            "object_id": _blob(_BASELINE),
        }
    ]
    assert (
        _git(
            vault,
            "cat-file",
            "blob",
            captured.commit + ":review-content/" + baseline_sha,
        )
        == _BASELINE
    )
    case = ReviewCase(
        operations,
        vault,
        source,
        chosen.plan,
        captured,
        (vault / ".brz2obsidian/locator.json").read_bytes(),
        manifest,
        review,
        tuple(
            row
            for row in _git(vault, "ls-tree", "-z", captured.commit).split(b"\0")
            if row
        ),
    )
    _assert_intact(case)
    return case


@contextmanager
def _restored(case):
    locator = case.vault / ".brz2obsidian/locator.json"
    assert locator.read_bytes() == case.locator
    assert (
        _git(case.vault, "rev-parse", case.result.ref).decode().strip()
        == case.result.commit
    )
    try:
        yield
    finally:
        _git(case.vault, "update-ref", case.result.ref, case.result.commit)
        locator.write_bytes(case.locator)
        _assert_intact(case)


def _retarget(case, *, review=None, review_content=None):
    """Keep public metadata pointers coherent with the one deliberate corruption."""
    manifest = json.loads(case.manifest)
    rows = {row.split(b"\t", 1)[1]: row for row in case.root_rows}
    if review is not None:
        oid = _git(
            case.vault, "hash-object", "-w", "--no-filters", "--stdin", input=review
        ).strip()
        assert oid.decode() == _blob(review)
        rows[b"review.json"] = b"100644 blob " + oid + b"\treview.json"
        manifest.update(
            review_object=oid.decode(),
            review_size=len(review),
            review_sha256=hashlib.sha256(review).hexdigest(),
        )
    if review_content is not None:
        manifest["review_content"] = review_content
        if review_content:
            role_rows = [
                b"100644 blob "
                + row["object_id"].encode()
                + b"\t"
                + row["path"].encode()
                for row in review_content
            ]
            role = _git(
                case.vault, "mktree", "-z", input=b"\0".join(role_rows) + b"\0"
            ).strip()
            rows[b"review-content"] = b"040000 tree " + role + b"\treview-content"
        else:
            rows.pop(b"review-content")
    manifest_raw = json.dumps(manifest).encode("utf-8")
    manifest_oid = _git(
        case.vault, "hash-object", "-w", "--no-filters", "--stdin", input=manifest_raw
    ).strip()
    rows[b"manifest.json"] = b"100644 blob " + manifest_oid + b"\tmanifest.json"
    tree = (
        _git(case.vault, "mktree", "-z", input=b"\0".join(rows.values()) + b"\0")
        .decode()
        .strip()
    )
    commit = (
        _git(
            case.vault,
            "commit-tree",
            tree,
            input=b"controlled compact review corruption\n",
        )
        .decode()
        .strip()
    )
    locator = json.loads(case.locator)
    locator["commit"] = commit
    _git(case.vault, "update-ref", case.result.ref, commit)
    (case.vault / ".brz2obsidian/locator.json").write_text(
        json.dumps(locator), encoding="utf-8"
    )
    assert _git(case.vault, "rev-parse", case.result.ref).decode().strip() == commit
    assert (
        json.loads((case.vault / ".brz2obsidian/locator.json").read_bytes())["commit"]
        == commit
    )
    assert (
        _git(case.vault, "cat-file", "blob", commit + ":manifest.json") == manifest_raw
    )
    assert _git(case.vault, "cat-file", "blob", commit + ":review.json") == (
        case.review if review is None else review
    )
    return commit


def _assert_refused_without_repair(case):
    before = _state(case.vault.parent)
    reopened = _call(case.operations.read_checkpoint, case.vault)
    assert _state(case.vault.parent) == before
    refused = _capture(case)
    assert _state(case.vault.parent) == before
    assert reopened.status == "refused"
    assert refused.status == "refused"
    assert refused.authored_files_changed is False


def test_compact_review_duplicate_interpretation_key_refuses(compact_checkpoint):
    case = compact_checkpoint
    with _restored(case):
        assert case.review.endswith(b"}")
        duplicate = case.review[:-1] + b',"schema_version":1}'
        assert (
            duplicate.count(b'"schema_version":1')
            == case.review.count(b'"schema_version":1') + 1
        )
        _retarget(case, review=duplicate)
        _assert_refused_without_repair(case)


def test_deep_compact_malformed_shape_returns_typed_refusal(compact_checkpoint):
    case = compact_checkpoint
    with _restored(case):
        # Small transport, deliberately beyond ordinary JSON recursion depth;
        # malformed SavedReview shape must not escape as RecursionError.
        malformed = (
            b'{"schema_id":"brz2obsidian.saved-review-refs",'
            b'"schema_version":1,"record":' + b"[" * 1500 + b"0" + b"]" * 1500 + b"}"
        )
        assert len(malformed) < 4096
        _retarget(case, review=malformed)
        _assert_refused_without_repair(case)


@pytest.mark.parametrize("kind", ("unused", "missing"))
def test_compact_byte_references_close_over_owned_roles(compact_checkpoint, kind):
    case = compact_checkpoint
    baseline_sha = hashlib.sha256(_BASELINE).hexdigest()
    with _restored(case):
        if kind == "unused":
            unused_sha = hashlib.sha256(_UNUSED).hexdigest()
            assert unused_sha.encode("ascii") not in case.review
            oid = (
                _git(
                    case.vault,
                    "hash-object",
                    "-w",
                    "--no-filters",
                    "--stdin",
                    input=_UNUSED,
                )
                .decode()
                .strip()
            )
            assert oid == _blob(_UNUSED)
            rows = json.loads(case.manifest)["review_content"] + [
                {
                    "path": unused_sha,
                    "mode": "100644",
                    "size": len(_UNUSED),
                    "sha256": unused_sha,
                    "object_id": oid,
                }
            ]
            commit = _retarget(
                case, review_content=sorted(rows, key=lambda row: row["path"])
            )
            assert (
                _git(
                    case.vault,
                    "cat-file",
                    "blob",
                    commit + ":review-content/" + unused_sha,
                )
                == _UNUSED
            )
        else:
            # The literal baseline is still a valid stored object, but has no
            # owned role edge. Refusal must not rely on loose-object absence.
            assert baseline_sha.encode("ascii") in case.review
            commit = _retarget(case, review_content=[])
            assert _git(case.vault, "cat-file", "blob", _blob(_BASELINE)) == _BASELINE
            assert b"review-content" not in [
                row.split(b"\t", 1)[1]
                for row in _git(case.vault, "ls-tree", "-z", commit).split(b"\0")
                if row
            ]
        _assert_refused_without_repair(case)
