"""Real Git layouts stay untouched when public vault admission refuses them."""

import hashlib
import json
import os
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import pytest

from brz2obsidian.application.operations import Operations

EVIDENCE = Path(__file__).resolve().parents[2] / "tmp" / "issue-271-layouts"


def _record(name, value):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with (EVIDENCE / name).open("a", encoding="utf-8") as output:
        output.write(json.dumps(value) + "\n")


@pytest.fixture
def owned_layout(monkeypatch):
    # C12's physical-parent check requires fixtures outside the checkout. These
    # explicitly authorized, uniquely marked system-temp fixtures are retained.
    token = uuid4().hex
    base = Path(tempfile.gettempdir()).resolve()
    root = Path(
        tempfile.mkdtemp(prefix="brz2obsidian-271-layouts-", dir=base)
    ).resolve()
    marker = root / ".fixture-owner.json"
    record = {
        "temp_base": str(base),
        "root": str(root),
        "owner": token,
        "marker": str(marker),
        "targets": [str(root / name) for name in ("main", "linked", "bare")],
        "cleanup": "retained; no recursive cleanup performed",
    }
    marker.write_text(json.dumps(record), encoding="utf-8")
    _record("fixtures.jsonl", record)
    global_config = root / "global.gitconfig"
    global_config.write_bytes(b"")
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    return root


def _git(root, *args, input=None, allow_unsupported=False):
    started = time.perf_counter()
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Layout fixture",
            "-c",
            "user.email=layout@example.invalid",
            "-c",
            "core.autocrlf=false",
            "-C",
            str(root),
            *args,
        ],
        input=input,
        capture_output=True,
        timeout=15,
        check=False,
    )
    _record(
        "timings.jsonl",
        {
            "kind": "fixture_git",
            "command": args[0],
            "seconds": time.perf_counter() - started,
        },
    )
    if result.returncode and allow_unsupported:
        message = result.stderr.decode("utf-8", errors="replace")
        if "unknown option" in message or "unknown ref storage format" in message:
            pytest.skip(
                "Installed Git cannot create this repository format: " + message
            )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _init(root, *options):
    root.mkdir()
    _git(root, "init", "-q", "--initial-branch=user-main", *options)


def _commit_authored(root):
    (root / "note.md").write_bytes(b"committed user note\n")
    _git(root, "add", "note.md")
    _git(root, "commit", "-qm", "User history")
    _git(root, "tag", "user-tag")


def _storage(root):
    """Independently enumerate every fixture directory/file, including Git stores."""
    result = {}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        result[path.relative_to(root).as_posix()] = (
            stat.S_IMODE(info.st_mode),
            None if path.is_dir() else path.read_bytes(),
        )
    return result


def _user_state(root):
    return {
        "head": _git(root, "rev-parse", "HEAD"),
        "head_kind": _git(root, "symbolic-ref", "HEAD"),
        "refs": _git(root, "for-each-ref", "--format=%(refname) %(objectname)"),
        "index": _git(root, "ls-files", "--stage", "-z"),
    }


def _refused(root, code, *, status="refused"):
    started = time.perf_counter()
    result = Operations().inspect_vault(root)
    _record(
        "timings.jsonl",
        {
            "kind": "public_inspection",
            "finding": code,
            "seconds": time.perf_counter() - started,
        },
    )
    assert result.status == status
    assert code in {finding.code for finding in result.findings}
    assert result.admitted_actions == (
        ("resolve_operation",) if status == "recovery_first" else ()
    )
    return result


def test_main_and_real_linked_worktree_refuse_without_changing_either_store(
    owned_layout,
):
    main, linked = owned_layout / "main", owned_layout / "linked"
    _init(main)
    _commit_authored(main)
    _git(main, "worktree", "add", "-q", "-b", "user-linked", str(linked))
    (main / "note.md").write_bytes(b"main staged\n")
    _git(main, "add", "note.md")
    (main / "note.md").write_bytes(b"main working\r\n")
    (linked / "note.md").write_bytes(b"linked staged\n")
    _git(linked, "add", "note.md")
    (linked / "note.md").write_bytes(b"linked working\r\n")
    (linked / "untracked.bin").write_bytes(b"\x00\xfflinked")
    assert (linked / ".git").is_file()
    assert _git(
        linked, "rev-parse", "--path-format=absolute", "--git-common-dir"
    ).strip() == (str(main / ".git").replace("\\", "/").encode())
    states = {root: _user_state(root) for root in (main, linked)}
    before = _storage(owned_layout)

    _refused(main, "shared_layout")
    assert _storage(owned_layout) == before
    _refused(linked, "redirected_layout")
    assert _storage(owned_layout) == before
    for root, staged in ((main, b"main staged\n"), (linked, b"linked staged\n")):
        assert _user_state(root) == states[root]
        assert _git(root, "show", ":note.md") == staged


def test_genuine_bare_repository_refuses_without_touching_history(owned_layout):
    bare = owned_layout / "bare"
    bare.mkdir()
    _git(bare, "init", "--bare", "-q", "--initial-branch=user-main")
    blob = _git(bare, "hash-object", "-w", "--stdin", input=b"bare authored\n").strip()
    tree = _git(bare, "mktree", input=b"100644 blob " + blob + b"\tbare.md\n").strip()
    commit = _git(
        bare, "commit-tree", tree.decode(), input=b"Independent bare history\n"
    ).strip()
    _git(bare, "update-ref", "refs/heads/user-main", commit.decode())
    _git(bare, "update-ref", "refs/tags/user-tag", commit.decode())
    assert _git(bare, "rev-parse", "--is-bare-repository") == b"true\n"
    refs = _git(bare, "for-each-ref", "--format=%(refname) %(objectname)")
    before = _storage(owned_layout)

    _refused(bare, "bare_repository")

    assert _storage(owned_layout) == before
    assert _git(bare, "for-each-ref", "--format=%(refname) %(objectname)") == refs
    assert _git(bare, "show", "HEAD:bare.md") == b"bare authored\n"


def _blob_oid(payload):
    return hashlib.sha1(
        b"blob " + str(len(payload)).encode() + b"\0" + payload
    ).hexdigest()


def test_real_unmerged_stages_require_resolution_and_preserve_each_blob_mode_path(
    owned_layout,
):
    main = owned_layout / "main"
    _init(main)
    _commit_authored(main)
    payloads = (b"base\n", b"ours\r\n", b"theirs\x00\xff\n")
    modes = ("100644", "100755", "100644")
    entries = []
    for stage, (payload, mode) in enumerate(zip(payloads, modes, strict=True), 1):
        oid = _blob_oid(payload)
        assert (
            _git(main, "hash-object", "-w", "--stdin", input=payload).strip()
            == oid.encode()
        )
        entries.append(f"{mode} {oid} {stage}\tconflict.md".encode())
    _git(main, "update-index", "--index-info", input=b"\n".join(entries) + b"\n")
    working = (
        b"<<<<<<< ours\r\nUser resolution in progress\r\n=======\r\n>>>>>>> theirs\r\n"
    )
    (main / "conflict.md").write_bytes(working)
    (main / "untracked.bin").write_bytes(b"untracked user payload\x00")
    expected_stages = b"\0".join(entries) + b"\0"
    assert _git(main, "ls-files", "--unmerged", "-z") == expected_stages
    before_state = _user_state(main)
    before = _storage(owned_layout)

    _refused(main, "unmerged_index", status="recovery_first")

    assert _storage(owned_layout) == before
    assert _user_state(main) == before_state
    assert _git(main, "ls-files", "--unmerged", "-z") == expected_stages
    for stage, payload in enumerate(payloads, 1):
        assert _git(main, "show", f":{stage}:conflict.md") == payload
    assert (main / "conflict.md").read_bytes() == working


@pytest.mark.parametrize(
    "option,object_format,ref_format",
    [
        ("--object-format=sha256", b"sha256\n", b"files\n"),
        ("--ref-format=reftable", b"sha1\n", b"reftable\n"),
    ],
    ids=("sha256-objects", "reftable-refs"),
)
def test_actual_unqualified_repository_format_refuses_without_conversion(
    owned_layout, option, object_format, ref_format
):
    main = owned_layout / "main"
    main.mkdir()
    _git(
        main,
        "init",
        "-q",
        "--initial-branch=user-main",
        option,
        allow_unsupported=True,
    )
    _commit_authored(main)
    (main / "note.md").write_bytes(b"staged independently\n")
    _git(main, "add", "note.md")
    (main / "note.md").write_bytes(b"working independently\r\n")
    assert _git(main, "rev-parse", "--show-object-format") == object_format
    assert _git(main, "rev-parse", "--show-ref-format") == ref_format
    before_state = _user_state(main)
    before = _storage(owned_layout)

    _refused(main, "unsupported_format")

    assert _storage(owned_layout) == before
    assert _user_state(main) == before_state
    assert _git(main, "show", ":note.md") == b"staged independently\n"
