"""Admission is observed through Operations; real storage is an independent oracle."""

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import pytest

from brz2obsidian.application.operations import Operations


def fixture_root(label="vault"):
    # C12 requires genuine roots outside the checkout's containing repository.
    # The coordinator authorizes these uniquely owned physical fixtures.
    token = uuid4().hex
    container = Path(tempfile.mkdtemp(prefix="brz2obsidian-271-" + label + "-"))
    root = container / "vault"
    root.mkdir()
    manifest = Path(__file__).resolve().parents[2] / "tmp" / "issue-271" / "fixtures"
    manifest.mkdir(parents=True, exist_ok=True)
    marker = container / ".fixture-owner.json"
    record = {
        "root": str(container.resolve()),
        "vault": str(root.resolve()),
        "base": str(Path(tempfile.gettempdir()).resolve()),
        "owner": token,
        "marker": str(marker),
    }
    marker.write_text(json.dumps(record), encoding="utf-8")
    (manifest / (token + ".json")).write_text(json.dumps(record), encoding="utf-8")
    return root


def timing(kind, elapsed):
    path = Path(__file__).resolve().parents[2] / "tmp" / "issue-271" / "timings.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(
            json.dumps(
                {
                    "kind": kind,
                    "seconds": elapsed,
                    "test": os.environ.get("PYTEST_CURRENT_TEST"),
                }
            )
            + "\n"
        )


@pytest.fixture
def vault():
    root = fixture_root()
    git(root, "init", "-q")
    return root


def git(root, *args, input=None):
    start = time.perf_counter()
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Admission fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-C",
            str(root),
            *args,
        ],
        input=input,
        capture_output=True,
        check=False,
    )
    timing("fixture_git", time.perf_counter() - start)
    assert result.returncode == 0, result.stderr
    return result.stdout


def inspect(root, **kwargs):
    start = time.perf_counter()
    result = Operations().inspect_vault(root, **kwargs)
    timing("public_inspection", time.perf_counter() - start)
    return result


def test_unborn_root_inventory_is_complete_exact_and_observation_only(vault):
    (vault / "note.md").write_bytes(b"User note\r\n")
    (vault / "asset.bin").write_bytes(b"\x00\xff\x80" * 6000000)
    (vault / ".obsidian").mkdir()
    (vault / ".obsidian" / "app.json").write_bytes(b'{"user":true}')
    before = {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }
    result = inspect(vault)
    assert result.status == "supported"
    assert result.repository.head == "unborn"
    assert [(f.path, f.size, f.mode, f.tracked) for f in result.inventory] == [
        (".obsidian/app.json", 13, "100644", False),
        ("asset.bin", 18000000, "100644", False),
        ("note.md", 11, "100644", False),
    ]
    assert (
        result.inventory[1].sha256
        == "b743ea3aa0502f706974c9129174e86dad5855c85ac3188bc09f3c89048976f7"
    )
    assert result.inventory_complete
    assert result.preflight.state_status == "unknown"
    assert result.preflight.operation_status == "unknown"
    assert result.admitted_actions == ("review_history",)
    assert len(result.observation_fingerprint) == 64
    assert before == {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }


def test_parent_repository_is_refused_even_with_own_root(vault):
    child = vault / "child"
    child.mkdir()
    git(child, "init", "-q")
    result = inspect(child)
    assert result.status == "refused"
    assert "parent_repository" in {f.code for f in result.findings}
    assert result.admitted_actions == ()


def storage(root):
    return {
        p.relative_to(root).as_posix(): (
            stat.S_IMODE(p.stat().st_mode),
            p.stat().st_dev,
            p.stat().st_ino,
            p.read_bytes(),
        )
        for p in root.rglob("*")
        if p.is_file()
    }


def test_dirty_partial_staging_detached_and_user_refs_are_observed_without_writes(
    vault,
):
    (vault / "note.md").write_bytes(b"committed\n")
    git(vault, "add", "note.md")
    git(vault, "commit", "-qm", "user")
    git(vault, "tag", "user-tag")
    git(vault, "checkout", "-qb", "\u00e9dit\u00e9")
    git(vault, "remote", "add", "origin", "https://invalid.example/no-contact")
    (vault / "note.md").write_bytes(b"staged\n")
    git(vault, "add", "note.md")
    (vault / "note.md").write_bytes(b"working\r\n")
    (vault / "untracked.md").write_bytes(b"new")
    before = storage(vault)
    entries = git(vault, "ls-files", "--stage", "-z")
    staged = git(vault, "show", ":note.md")
    head = git(vault, "rev-parse", "HEAD").decode().strip()
    result = inspect(vault)
    assert result.status == "supported"
    assert result.repository.head == head
    assert [(f.path, f.tracked) for f in result.inventory] == [
        ("note.md", True),
        ("untracked.md", False),
    ]
    assert result.inventory[0].sha256 == hashlib.sha256(b"working\r\n").hexdigest()
    assert storage(vault) == before
    assert git(vault, "ls-files", "--stage", "-z") == entries
    assert git(vault, "show", ":note.md") == staged == b"staged\n"
    git(vault, "checkout", "--detach", "-q")
    detached_before = storage(vault)
    detached = inspect(vault)
    assert detached.status == "supported"
    assert detached.repository.head == head
    assert detached.observation_fingerprint != result.observation_fingerprint
    assert storage(vault) == detached_before


def test_effective_builtin_storage_and_inclusion_are_distinct_scoped_current_choices(
    vault,
):
    from brz2obsidian.application.vault_contracts import VaultSubject

    (vault / "note.md").write_bytes(b"raw\r\n")
    (vault / "excluded.md").write_bytes(b"excluded authored bytes")
    (vault / "unrelated.md").write_bytes(b"keep unrelated")
    (vault / ".gitignore").write_bytes(b"excluded.md\nunrelated.md\n")
    (vault / ".gitattributes").write_bytes(b"*.md text eol=lf\n")
    git(vault, "config", "core.autocrlf", "true")
    subjects = (VaultSubject(path="excluded.md", subject_id="reviewed-note"),)
    before = storage(vault)
    result = inspect(vault, subjects=subjects)
    assert result.status == "supported"
    storage_choice, inclusion = result.preflight.consents
    assert (
        storage_choice.kind,
        storage_choice.policy,
        storage_choice.requirement,
        storage_choice.subjects,
    ) == ("storage", "builtin_transform", "required", ("reviewed-note",))
    assert (inclusion.kind, inclusion.policy, inclusion.subjects) == (
        "tracking",
        "ordinary",
        ("reviewed-note",),
    )
    assert result.recovery_gaps == ("excluded.md", "unrelated.md")
    assert [
        (f.path, f.excluded) for f in result.inventory if f.path.endswith(".md")
    ] == [("excluded.md", True), ("note.md", False), ("unrelated.md", True)]
    assert storage(vault) == before
    (vault / ".git" / "info" / "attributes").write_bytes(b"*.md -text\n")
    changed = inspect(vault, subjects=subjects)
    assert changed.policy_fingerprint != result.policy_fingerprint
    assert changed.preflight.consents[0].fingerprint != storage_choice.fingerprint
    assert changed.preflight.consents[1].fingerprint != inclusion.fingerprint
    # Already tracked ignore matches retain tracking and need no inclusion.
    git(vault, "add", "-f", "excluded.md")
    tracked = inspect(vault, subjects=subjects)
    assert tracked.recovery_gaps == ("unrelated.md",)
    assert [c.kind for c in tracked.preflight.consents] == ["storage"]


@pytest.mark.parametrize(
    "policy,config,attributes,expected",
    [
        (
            "custom filter",
            ("filter.secret.clean", "CANARY"),
            b"*.md filter=secret\n",
            "custom_filter",
        ),
        ("missing nonrequired filter", None, b"*.md filter=missing\n", "custom_filter"),
        ("LFS with local payload", None, b"*.md filter=lfs\n", "lfs"),
        (
            "custom diff",
            ("diff.secret.textconv", "CANARY"),
            b"*.md diff=secret\n",
            "custom_driver",
        ),
        (
            "custom merge",
            ("merge.secret.driver", "CANARY"),
            b"*.md merge=secret\n",
            "custom_driver",
        ),
        ("fsmonitor", ("core.fsmonitor", "CANARY"), b"", "fsmonitor"),
    ],
)
def test_applicable_execution_policy_refuses_without_running_canaries(
    vault, policy, config, attributes, expected
):
    marker = vault / "EXECUTED"
    script = vault.parent / (vault.name + "-canary.py")
    script.write_text(
        "from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b'executed')",
        encoding="utf-8",
    )
    command = [sys.executable, str(script), str(marker)]
    subprocess.run(command, check=True)
    assert marker.read_bytes() == b"executed"
    marker.unlink()
    canary = " ".join('"' + value + '"' for value in command)
    (vault / "note.md").write_bytes(b"current binary payload\x00")
    (vault / ".gitattributes").write_bytes(attributes)
    if config:
        git(vault, "config", config[0], canary if config[1] == "CANARY" else config[1])
    before = storage(vault)
    result = inspect(vault)
    assert result.status == "refused", policy
    assert expected in {f.code for f in result.findings}
    assert result.admitted_actions == ()
    assert not marker.exists()
    assert storage(vault) == before
    assert "secret" not in result.model_dump_json()


def test_inactive_samples_unused_definitions_and_binary_are_supported_but_active_reference_hook_refuses(
    vault,
):
    (vault / "asset.bin").write_bytes(b"\x00\xff\x80")
    (vault / ".gitattributes").write_bytes(b"asset.bin -text -diff -merge\n")
    git(vault, "config", "filter.unused.clean", "!touch SHOULD_NOT_RUN")
    (vault / ".git" / "hooks" / "notes.lock").write_bytes(b"inactive hook notes")
    assert inspect(vault).status == "supported"
    (vault / "asset.bin").write_bytes(
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:0000000000000000000000000000000000000000000000000000000000000000\n"
        b"size 3\n"
    )
    pointer = inspect(vault)
    assert pointer.status == "refused"
    assert "lfs" in {f.code for f in pointer.findings}
    (vault / "asset.bin").write_bytes(b"\x00\xff\x80")
    hook = vault / ".git" / "hooks" / "reference-transaction"
    hook.write_bytes(b"#!/bin/sh\necho canary > EXECUTED\n")
    before = storage(vault)
    result = inspect(vault)
    assert result.status == "refused"
    assert "active_hook" in {f.code for f in result.findings}
    assert storage(vault) == before


def test_empty_configured_hook_location_is_inactive(vault):
    git(vault, "config", "core.hooksPath", ".empty-hooks")
    assert inspect(vault).status == "supported"
    (vault / ".empty-hooks").mkdir()
    (vault / ".empty-hooks" / "reference-transaction").write_bytes(
        b"#!/bin/sh\nexit 1\n"
    )
    result = inspect(vault)
    assert result.status == "refused"
    assert "active_hook" in {f.code for f in result.findings}


@pytest.mark.parametrize(
    "case,expected,status",
    [
        ("merge", "git_operation", "recovery_first"),
        ("lock", "foreign_lock", "recovery_first"),
        ("converter", "converter_operation", "recovery_first"),
        ("sparse", "sparse_checkout", "refused"),
        ("skip", "index_flags", "refused"),
        ("assume", "index_flags", "refused"),
        ("shallow", "incomplete_store", "refused"),
        ("alternate", "external_store", "refused"),
        ("promisor", "incomplete_store", "refused"),
        ("graft", "incomplete_store", "refused"),
        ("nested", "nested_repository", "refused"),
        ("nested-uppercase", "nested_repository", "refused"),
        ("redirected", "redirected_layout", "refused"),
        ("missing", "object_integrity", "refused"),
        ("corrupt", "object_integrity", "refused"),
    ],
)
def test_storage_layout_and_operation_states_are_precisely_refused_without_repair(
    vault, case, expected, status, monkeypatch
):
    (vault / "note.md").write_bytes(b"committed\n")
    git(vault, "add", "note.md")
    git(vault, "commit", "-qm", "user")
    store = vault / ".git"
    if case == "merge":
        (store / "MERGE_HEAD").write_bytes(git(vault, "rev-parse", "HEAD"))
    elif case == "lock":
        (store / "index.lock").write_bytes(b"foreign")
    elif case == "converter":
        (store / "brz2obsidian").mkdir()
        (store / "brz2obsidian" / "intent.json").write_bytes(
            b"incomplete unknown intent"
        )
    elif case == "sparse":
        git(vault, "config", "core.sparseCheckout", "true")
    elif case in ("skip", "assume"):
        git(
            vault,
            "update-index",
            "--skip-worktree" if case == "skip" else "--assume-unchanged",
            "note.md",
        )
    elif case == "shallow":
        (store / "shallow").write_bytes(git(vault, "rev-parse", "HEAD"))
    elif case == "alternate":
        (store / "objects" / "info" / "alternates").write_bytes(
            b"C:/external/objects\n"
        )
    elif case == "promisor":
        git(vault, "config", "remote.origin.promisor", "true")
    elif case == "graft":
        parent = git(vault, "rev-parse", "HEAD").strip()
        (vault / "note.md").write_bytes(b"child\n")
        git(vault, "add", "note.md")
        git(vault, "commit", "-qm", "child")
        child = git(vault, "rev-parse", "HEAD").strip()
        assert b"parent " + parent + b"\n" in git(vault, "cat-file", "-p", "HEAD")
        (store / "info" / "grafts").write_bytes(child + b"\n")
        raw_parent = store / "objects" / parent[:2].decode() / parent[2:].decode()
        raw_parent.chmod(0o600)
        raw_parent.unlink()
        # Actual Git can validate substituted connectivity despite the missing
        # raw parent. Admission must refuse this advanced history view first.
        git(vault, "fsck", "--full", "--no-reflogs", "--no-progress")
    elif case in ("nested", "nested-uppercase"):
        (vault / "nested").mkdir()
        git(vault / "nested", "init", "-q")
        if case == "nested-uppercase":
            (vault / "nested" / ".git").rename(vault / "nested" / ".GIT")
    elif case == "redirected":
        moved = vault / "moved-store"
        store.rename(moved)
        store.write_text("gitdir: moved-store\n", encoding="utf-8")
    elif case in ("missing", "corrupt"):
        oid = git(vault, "rev-parse", "HEAD").decode().strip()
        obj = store / "objects" / oid[:2] / oid[2:]
        obj.chmod(0o600)
        if case == "missing":
            obj.unlink()
        else:
            obj.write_bytes(b"corrupt")
    before = storage(vault)
    nested_scans = []
    scandir = os.scandir

    def observed_scandir(path):
        if "nested" in case and Path(path).is_relative_to(vault / "nested" / ".git"):
            nested_scans.append(str(path))
        return scandir(path)

    with monkeypatch.context() as audit:
        audit.setattr(os, "scandir", observed_scandir)
        result = inspect(vault)
    assert not nested_scans
    assert result.status == status
    assert expected in {f.code for f in result.findings}
    assert result.admitted_actions == (
        ("resolve_operation",) if status == "recovery_first" else ()
    )
    assert storage(vault) == before


def test_no_repository_is_supported_but_missing_git_is_typed_and_safe(vault):
    # Make a second, genuinely repository-free sibling.
    root = fixture_root("none")
    (root / "note.md").write_bytes(b"authored")
    result = inspect(root)
    assert result.status == "supported"
    assert result.repository.kind == "none"
    assert result.admitted_actions == ("review_initialization",)
    assert not (root / ".git").exists()
    unavailable = inspect(root, git_executable=root / "missing-git.exe")
    assert unavailable.status == "refused"
    assert unavailable.findings[0].code == "git_unavailable"
    assert unavailable.admitted_actions == ()
    assert (root / "note.md").read_bytes() == b"authored"


def test_actual_junction_hardlink_and_selected_readonly_paths_are_refused(vault):
    from brz2obsidian.application.vault_contracts import VaultSubject

    authored = vault / "note.md"
    authored.write_bytes(b"readable unrelated authored bytes")
    authored.chmod(stat.S_IREAD)
    try:
        assert inspect(vault).status == "supported"
        selected = inspect(
            vault, subjects=(VaultSubject(path="note.md", subject_id="selected"),)
        )
        assert selected.status == "refused"
        assert "write_access" in {f.code for f in selected.findings}
    finally:
        authored.chmod(stat.S_IREAD | stat.S_IWRITE)
    os.link(authored, vault / "hardlink.md")
    hardlink = inspect(vault)
    assert hardlink.status == "refused"
    assert "unsafe_file" in {f.code for f in hardlink.findings}
    (vault / "hardlink.md").unlink()
    outside = fixture_root("junction")
    (outside / "outside.md").write_bytes(b"outside should never be traversed")
    linked = vault / "junction"
    process = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(linked), str(outside)],
        capture_output=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    result = inspect(vault)
    assert result.status == "refused"
    assert "reparse_path" in {f.code for f in result.findings}
    assert result.inventory == ()
    assert (outside / "outside.md").read_bytes() == b"outside should never be traversed"


def test_policy_before_initialization_requires_real_repository_rediscovery(
    vault, monkeypatch
):
    root = fixture_root("policy")
    (root / "note.md").write_bytes(b"authored")
    rules = root.parent / (root.name + "-attrs")
    rules.write_bytes(b"*.md filter=unavailable\n")
    included = root.parent / (root.name + "-include")
    included.write_text(
        '[core]\n attributesFile = "' + rules.as_posix() + '"\n', encoding="utf-8"
    )
    global_config = root.parent / (root.name + "-config")
    global_config.write_text(
        '[includeIf "gitdir/i:'
        + (root / ".git").as_posix()
        + '"]\n path = "'
        + included.as_posix()
        + '"\n[includeIf "gitdir/i:**/brz2obsidian-policy-*"]\n path = "'
        + included.as_posix()
        + '"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    before = inspect(root)
    assert before.status == "supported"
    assert before.policy_scope == "before_initialization"
    assert before.admitted_actions == ("review_initialization",)
    assert before.preflight.state_status == "unknown"
    git(root, "init", "-q")
    after = inspect(root)
    assert after.status == "refused"
    assert after.policy_scope == "current_repository"
    assert after.policy_fingerprint != before.policy_fingerprint
    assert "custom_filter" in {f.code for f in after.findings}


def test_trace_sinks_and_unrelated_edits_do_not_grant_or_invalidate_authority(
    vault, monkeypatch
):
    trace = vault.parent / (vault.name + "-trace")
    monkeypatch.setenv("GIT_TRACE", str(trace))
    monkeypatch.setenv("GIT_TRACE2_EVENT", str(trace))
    monkeypatch.setenv("GIT_REDIRECT_STDOUT", str(trace))
    monkeypatch.setenv("GIT_REDIRECT_STDERR", str(trace))
    monkeypatch.setenv("GIT_REDIRECT_STDIN", str(trace))
    (vault / "note.md").write_bytes(b"one")
    before = inspect(vault)
    assert not trace.exists()
    assert before.status == "supported"
    (vault / "note.md").write_bytes(b"two")
    after = inspect(vault)
    assert before.observation_fingerprint != after.observation_fingerprint
    assert after.status == "supported"
    assert before.preflight.state_fingerprint == after.preflight.state_fingerprint
    assert before.preflight.state_status == after.preflight.state_status == "unknown"


def test_denied_directory_listing_is_unknown_not_an_empty_inventory(vault):
    hidden = vault / "authored"
    hidden.mkdir()
    authored = hidden / "keep.md"
    authored.write_bytes(b"must never be inferred deleted")
    sid = (
        subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            check=True,
        )
        .stdout.strip()
        .split(",")[-1]
        .strip('"')
    )
    deny = subprocess.run(
        ["icacls", str(hidden), "/deny", "*" + sid + ":(RD)"],
        capture_output=True,
        check=False,
    )
    assert deny.returncode == 0, deny.stderr
    try:
        result = inspect(vault)
        assert result.status in ("refused", "unknown")
        assert not result.inventory_complete
        assert result.admitted_actions == ()
        assert "observation_unavailable" in {f.code for f in result.findings}
        assert authored.read_bytes() == b"must never be inferred deleted"
    finally:
        restore = subprocess.run(
            ["icacls", str(hidden), "/remove:d", "*" + sid],
            capture_output=True,
            check=False,
        )
        assert restore.returncode == 0, restore.stderr


def test_new_subject_under_denied_parent_and_unsafe_metadata_aliases_refuse(vault):
    from brz2obsidian.application.vault_contracts import VaultSubject

    parent = vault / "incoming"
    parent.mkdir()
    sid = (
        subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            check=True,
        )
        .stdout.strip()
        .split(",")[-1]
        .strip('"')
    )
    deny = subprocess.run(
        ["icacls", str(parent), "/deny", "*" + sid + ":(WD)"],
        capture_output=True,
        check=False,
    )
    assert deny.returncode == 0
    try:
        result = inspect(
            vault, subjects=(VaultSubject(path="incoming/new.md", subject_id="new"),)
        )
        assert result.status == "refused"
        assert "write_access" in {f.code for f in result.findings}
        assert not (parent / "new.md").exists()
    finally:
        restore = subprocess.run(
            ["icacls", str(parent), "/remove:d", "*" + sid],
            capture_output=True,
            check=False,
        )
        assert restore.returncode == 0
    for path in (".GIT/config", "note. ", "NUL.md", "a/../b", "a:b", "a\\b"):
        bad = inspect(vault, subjects=({"path": path, "subject_id": "unsafe"},))
        assert bad.status == "refused"
        assert bad.findings[0].code == "unsafe_subject"


def test_effective_system_global_repository_and_info_rules_are_observed(
    vault, monkeypatch
):
    (vault / "note.md").write_bytes(b"tracked")
    git(vault, "add", "note.md")
    (vault / "excluded.md").write_bytes(b"global excluded")
    (vault / "info.md").write_bytes(b"info excluded")
    (vault / "repo.md").write_bytes(b"repo excluded")
    (vault / ".gitignore").write_bytes(b"repo.md\n")
    (vault / ".git" / "info" / "exclude").write_bytes(b"info.md\nnote.md\n")
    global_attrs = vault.parent / (vault.name + "-attributes")
    global_attrs.write_bytes(b"*.md text ident working-tree-encoding=UTF-8\n")
    global_ignores = vault.parent / (vault.name + "-ignores")
    global_ignores.write_bytes(b"excluded.md\n")
    global_config = vault.parent / (vault.name + "-global")
    global_config.write_text(
        '[core]\n attributesFile = "'
        + global_attrs.as_posix()
        + '"\n excludesFile = "'
        + global_ignores.as_posix()
        + '"\n',
        encoding="utf-8",
    )
    system = vault.parent / (vault.name + "-system")
    system.write_bytes(
        b'[core]\n autocrlf = false\n[filter "unused"]\n clean = never-execute\n'
    )
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(system))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    outside = {
        p: p.read_bytes() for p in (global_attrs, global_ignores, global_config, system)
    }
    before = storage(vault)
    result = inspect(vault)
    assert result.status == "supported"
    assert result.recovery_gaps == ("excluded.md", "info.md", "repo.md")
    assert next(f for f in result.inventory if f.path == "note.md").tracked
    assert [(c.kind, c.policy) for c in result.preflight.consents] == [
        ("storage", "builtin_transform")
    ]
    assert storage(vault) == before
    assert outside == {p: p.read_bytes() for p in outside}
    (vault / ".git" / "info" / "attributes").write_bytes(b"note.md filter=private\n")
    refused = inspect(vault)
    assert refused.status == "refused"
    assert "custom_filter" in {f.code for f in refused.findings}


def test_oversized_effective_policy_returns_safe_unknown_without_unbounded_output(
    vault, monkeypatch
):
    config = vault.parent / (vault.name + "-large-config")
    with config.open("wb") as stream:
        stream.write(b"[user]\n name = ")
        for _ in range(17):
            stream.write(b"x" * (1024 * 1024))
        stream.write(b"\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    result = inspect(vault)
    assert result.status in ("refused", "unknown")
    assert not result.inventory_complete
    assert result.findings[0].code == "observation_unavailable"
    assert len(result.model_dump_json()) < 10000


def test_no_repository_requires_actual_format_option_support(vault):
    import shutil

    root = fixture_root("old-option")
    script = root.parent / (root.name + "-git.py")
    script.write_text(
        "import subprocess,sys\nif '--show-ref-format' in sys.argv:\n print('--show-ref-format')\nelse:\n raise SystemExit(subprocess.call(["
        + repr(shutil.which("git"))
        + ",*sys.argv[1:]]))\n",
        encoding="utf-8",
    )
    wrapper = root.parent / (root.name + "-git.cmd")
    wrapper.write_text(
        '@echo off\r\n"' + sys.executable + '" "' + str(script) + '" %*\r\n',
        encoding="utf-8",
    )
    result = inspect(root, git_executable=str(wrapper))
    assert result.status == "refused"
    assert "git_capability" in {f.code for f in result.findings}
    assert result.admitted_actions == ()
    assert not (root / ".git").exists()


def test_owned_git_launcher_descendant_is_terminated_before_return(vault):
    import ctypes
    import shutil
    from ctypes import wintypes

    marker = vault.parent / (vault.name + "-descendant-marker")
    pid_file = vault.parent / (vault.name + "-descendant-pid")
    child = vault.parent / (vault.name + "-child.py")
    child.write_text(
        "import pathlib,sys,time\nif sys.argv[2] == 'hold': time.sleep(10)\npathlib.Path(sys.argv[1]).write_bytes(b'executed')\n",
        encoding="utf-8",
    )
    subprocess.run([sys.executable, str(child), str(marker), "qualify"], check=True)
    assert marker.read_bytes() == b"executed"
    marker.unlink()
    script = vault.parent / (vault.name + "-launcher.py")
    script.write_text(
        "import pathlib,subprocess,sys\nif '--version' in sys.argv:\n child=subprocess.Popen(["
        + repr(sys.executable)
        + ","
        + repr(str(child))
        + ","
        + repr(str(marker))
        + ",'hold'])\n pathlib.Path("
        + repr(str(pid_file))
        + ").write_text(str(child.pid))\nraise SystemExit(subprocess.call(["
        + repr(shutil.which("git"))
        + ",*sys.argv[1:]]))\n",
        encoding="utf-8",
    )
    wrapper = vault.parent / (vault.name + "-launcher.cmd")
    wrapper.write_text(
        '@echo off\r\n"' + sys.executable + '" "' + str(script) + '" %*\r\n',
        encoding="utf-8",
    )
    # The measured ordinary admission path was redundant here (10.21s).
    # Stop on a real recognized hook; retain actual descendant/pipe proof.
    (vault / ".git" / "hooks" / "pre-commit").write_bytes(b"#!/bin/sh\nexit 0\n")
    before = storage(vault)
    result = inspect(vault, git_executable=str(wrapper))
    assert result.status == "refused"
    assert "active_hook" in {f.code for f in result.findings}
    assert storage(vault) == before
    pid = int(pid_file.read_text())
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if handle:
        try:
            code = wintypes.DWORD()
            assert kernel.GetExitCodeProcess(handle, ctypes.byref(code))
            assert code.value != 259
        finally:
            kernel.CloseHandle(handle)
    assert not marker.exists()


def test_known_cache_exclusions_are_disclosed_without_traversing_cached_payloads(
    vault,
):
    cache = vault / ".obsidian" / "cache"
    cache.mkdir(parents=True)
    (cache / "private.dat").write_bytes(b"version https://git-lfs.github.com/spec/v1\n")
    (vault / "note.md").write_bytes(b"authored")
    (vault / ".gitattributes").write_bytes(b".obsidian/cache/* filter=private\n")
    before = storage(vault)
    result = inspect(vault)
    assert result.status == "supported"
    assert result.exclusions == (".obsidian/cache",)
    assert [f.path for f in result.inventory] == [".gitattributes", "note.md"]
    assert result.recovery_gaps == ()
    assert storage(vault) == before


def test_unknown_access_environment_and_resource_observations_never_claim_deletion(
    vault, monkeypatch
):
    from collections import namedtuple

    (vault / "note.md").write_bytes(b"preserved")
    before = storage(vault)
    monkeypatch.setenv("GIT_ATTR_SOURCE", "HEAD")
    source = inspect(vault)
    assert source.status == "refused"
    assert source.findings[0].code == "attribute_source"
    monkeypatch.delenv("GIT_ATTR_SOURCE")
    monkeypatch.setenv("GIT_DIR", str(vault / ".git"))
    redirected = inspect(vault)
    assert redirected.status == "refused"
    assert redirected.findings[0].code == "redirected_environment"
    monkeypatch.delenv("GIT_DIR")
    graft_file = vault.parent / "external-grafts"
    graft_file.write_bytes(b"external history must not be consulted\n")
    monkeypatch.setenv("GIT_GRAFT_FILE", str(graft_file))
    graft_redirect = inspect(vault)
    assert graft_redirect.status == "refused"
    assert graft_redirect.findings[0].code == "redirected_environment"
    assert graft_file.read_bytes() == b"external history must not be consulted\n"
    monkeypatch.delenv("GIT_GRAFT_FILE")
    # Filesystem-space observation is a system seam; no real volume is filled.
    usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr("shutil.disk_usage", lambda _: usage(100, 100, 0))
    space = inspect(vault)
    assert space.status == "refused"
    assert space.inventory_complete
    assert "insufficient_space" in {f.code for f in space.findings}
    assert [f.path for f in space.inventory] == ["note.md"]
    assert storage(vault) == before
    monkeypatch.undo()
    (vault / ".git" / "config").write_bytes(b"[broken secret\n")
    unknown = inspect(vault)
    assert unknown.status in ("refused", "unknown")
    assert not unknown.inventory_complete
    assert unknown.admitted_actions == ()
    assert "secret" not in unknown.model_dump_json()


def test_admission_records_reject_unsupported_duplicate_unknown_and_inconsistent_fields(
    vault,
):
    from brz2obsidian.application.vault_contracts import VaultAdmission

    (vault / "note.md").write_bytes(b"one known file")
    result = inspect(vault)
    encoded = result.model_dump_json()
    assert VaultAdmission.model_validate_json(encoded) == result
    for broken in (
        encoded.replace('"schema_version":1', '"schema_version":true', 1),
        encoded.replace('"schema_version":1', '"schema_version":2', 1),
        encoded.replace(
            '"schema_version":1', '"schema_version":1,"schema_version":1', 1
        ),
        encoded[:-1] + ',"trusted":true}',
    ):
        with pytest.raises(ValueError):
            VaultAdmission.model_validate_json(broken)
    values = result.model_dump()
    values["inventory_complete"] = False
    with pytest.raises(ValueError):
        VaultAdmission.model_validate(values)
    duplicate = result.model_dump()
    duplicate["inventory"] = result.inventory + result.inventory
    with pytest.raises(ValueError):
        VaultAdmission.model_validate(duplicate)
    refused = result.model_dump()
    refused["status"] = "refused"
    with pytest.raises(ValueError):
        VaultAdmission.model_validate(refused)
    invalid = inspect(
        vault, subjects=({"path": "note.md", "subject_id": 1, "trusted": True},)
    )
    assert invalid.status == "refused"
    assert invalid.findings[0].code == "unsafe_subject"


def test_fresh_process_policy_view_never_allocates_inside_the_vault(vault):
    root = fixture_root("temp-policy")
    (root / "note.md").write_bytes(b"untouched authored")
    script = root.parent / (root.name + "-inspect.py")
    script.write_text(
        "import json,os,sys,tempfile\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[2])\ncreated=[]\ncreated_files=[]\ndef audit(event,args):\n if event=='tempfile.mkdtemp': created.append(args[0])\n if event=='open' and isinstance(args[0],str) and args[2] & os.O_CREAT and Path(args[0]).is_relative_to(sys.argv[1]): created_files.append(args[0])\nsys.addaudithook(audit)\ntempfile.tempdir=None\nfrom brz2obsidian.application.operations import Operations\nresult=Operations().inspect_vault(sys.argv[1])\nprint(json.dumps({'status':result.status,'codes':[f.code for f in result.findings],'created':created,'created_files':created_files,'left':[p for p in created if Path(p).exists()]}))\n",
        encoding="utf-8",
    )
    args = [
        sys.executable,
        str(script),
        str(root),
        str(Path(__file__).resolve().parents[2] / "src"),
    ]
    ordinary = subprocess.run(args, capture_output=True, text=True, check=True)
    facts = json.loads(ordinary.stdout)
    assert facts["status"] == "supported"
    assert len(facts["created"]) == 1
    assert root not in Path(facts["created"][0]).parents
    assert facts["left"] == []
    before = storage(root)
    unsafe = subprocess.run(
        args,
        env={**os.environ, "TEMP": str(root), "TMP": str(root)},
        capture_output=True,
        text=True,
        check=True,
    )
    facts = json.loads(unsafe.stdout)
    assert facts["status"] == "refused"
    assert "unsafe_temp_location" in facts["codes"]
    assert facts["created"] == facts["left"] == facts["created_files"] == []
    assert storage(root) == before


def test_actual_concurrent_authored_change_is_unknown_and_keeps_new_user_bytes(vault):
    import shutil

    (vault / "note.md").write_bytes(b"observed before race")
    script = vault.parent / "race-git.py"
    script.write_text(
        "import pathlib,subprocess,sys\ncode=subprocess.call(["
        + repr(shutil.which("git"))
        + ",*sys.argv[1:]])\nif 'check-attr' in sys.argv: pathlib.Path("
        + repr(str(vault / "note.md"))
        + ").write_bytes(b'raced by another process\\n')\nraise SystemExit(code)\n",
        encoding="utf-8",
    )
    wrapper = vault.parent / "race-git.cmd"
    wrapper.write_text(
        '@echo off\r\n"' + sys.executable + '" "' + str(script) + '" %*\r\n',
        encoding="utf-8",
    )
    before = storage(vault)
    result = inspect(vault, git_executable=str(wrapper))
    assert result.status in ("refused", "unknown")
    assert not result.inventory_complete
    assert result.admitted_actions == ()
    assert "observation_unavailable" in {f.code for f in result.findings}
    assert (vault / "note.md").read_bytes() == b"raced by another process\n"
    assert {p: data for p, data in storage(vault).items() if p != "note.md"} == {
        p: data for p, data in before.items() if p != "note.md"
    }
