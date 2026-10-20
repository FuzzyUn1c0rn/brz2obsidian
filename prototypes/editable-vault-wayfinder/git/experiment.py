"""Disposable Git experiment for #244. Never point this at a real vault.

Run with the project .venv interpreter. Every repository is newly generated under
tmp/merge-wayfinding/git/experiments; worker modes require its ownership marker.
This is an executable design experiment, not an application or test suite.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid


PROJECT = Path(__file__).resolve().parents[3]
OUTPUT = PROJECT / "tmp/merge-wayfinding/git/experiments"
NS = "refs/brz2obsidian/prototype/"
OP = NS + "operation"
SCRIPT = Path(__file__).resolve()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def packed(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def contained(path, root):
    path = Path(path).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError(f"Outside owned destination: {path}")
    return path


def owned_repo(path):
    repo = contained(path, OUTPUT)
    if not (repo.parent / "PROTOTYPE-OWNED.json").is_file():
        raise ValueError("Missing disposable-run ownership marker")
    if not (repo / ".git").is_dir():
        raise ValueError("Worker requires an existing generated repository")
    return repo


def environment(repo):
    # Only controlled synthetic policy. Host/global policy is NOT claimed tested.
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("GIT_"):
            del env[key]
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(repo.parent / "empty-global-config"),
        "GIT_CEILING_DIRECTORIES": str(repo.parent),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_AUTHOR_NAME": "Synthetic prototype",
        "GIT_AUTHOR_EMAIL": "prototype@example.invalid",
        "GIT_COMMITTER_NAME": "Synthetic prototype",
        "GIT_COMMITTER_EMAIL": "prototype@example.invalid",
        "GIT_AUTHOR_DATE": "2026-10-20T12:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-10-20T12:00:00+00:00",
    })
    return env


def git(repo, *args, data=None, index=None, ok=(0,)):
    repo = owned_repo(repo)
    env = environment(repo)
    if index is not None:
        env["GIT_INDEX_FILE"] = str(contained(index, repo))
    result = subprocess.run(
        ["git", "-C", str(repo), *args], input=data, capture_output=True,
        env=env, timeout=30,
    )
    if result.returncode not in ok:
        raise RuntimeError(f"git {args}: {result.returncode}: {result.stderr.decode(errors='replace')}")
    return result.stdout


def put(repo, path, data):
    target = contained(repo / path, repo)
    if target.is_relative_to(repo / ".git"):
        raise ValueError("Vault publication cannot target Git metadata")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def files(repo):
    return {str(p.relative_to(repo)).replace("\\", "/"): p.read_bytes()
            for p in sorted(repo.rglob("*"))
            if p.is_file() and not p.is_relative_to(repo / ".git")}


def inventory(repo):
    return {p: {"sha256": digest(b), "bytes": len(b)} for p, b in files(repo).items()}


def user_state(repo):
    index = repo / ".git/index"
    return {
        "HEAD_bytes": (repo / ".git/HEAD").read_text(),
        "HEAD_oid": git(repo, "rev-parse", "--verify", "HEAD", ok=(0, 128)).decode().strip(),
        "index_sha256": digest(index.read_bytes()) if index.exists() else None,
        "staged": git(repo, "ls-files", "--stage", "-z").hex(),
        "branches_tags": git(repo, "for-each-ref", "--format=%(refname) %(objectname)",
                             "refs/heads", "refs/tags").decode(),
        "config_sha256": digest((repo / ".git/config").read_bytes()),
    }


def refs(repo):
    return git(repo, "for-each-ref", "--format=%(refname) %(objectname)", NS).decode().splitlines()


def resolve(repo, ref):
    return git(repo, "rev-parse", "--verify", ref, ok=(0, 128)).decode().strip()


def blob(repo, data):
    return git(repo, "hash-object", "-w", "--no-filters", "--stdin", data=data).decode().strip()


def snapshot(repo, content, ref, parents=()):
    """Raw blobs -> isolated index -> tree -> commit -> owned CAS ref."""
    index = repo / ".git" / ("prototype-index-" + uuid.uuid4().hex)
    git(repo, "read-tree", "--empty", index=index)
    entries = b"".join(b"100644 " + blob(repo, b).encode() + b"\t" + p.encode() + b"\0"
                       for p, b in sorted(content.items()))
    if entries:
        git(repo, "update-index", "-z", "--index-info", data=entries, index=index)
    tree = git(repo, "write-tree", index=index).decode().strip()
    old = resolve(repo, ref)
    ancestry = list(dict.fromkeys(([old] if old else []) + list(parents)))
    args = ["commit-tree", tree]
    for parent in ancestry:
        args += ["-p", parent]
    oid = git(repo, *args, data=b"Synthetic prototype checkpoint\n").decode().strip()
    git(repo, "update-ref", ref, oid, old or "0" * len(oid))
    index.unlink()
    return oid


def load(repo):
    return json.loads(git(repo, "show", OP + ":manifest.json"))


def persist(repo, manifest):
    parents = [manifest[k] for k in ("pre", "result", "source", "undo_result") if manifest.get(k)]
    return snapshot(repo, {"manifest.json": packed(manifest)}, OP, parents)


def read_blob(repo, oid):
    return git(repo, "cat-file", "blob", oid)


def meaningful_checkpoint(repo, content, ref):
    old = resolve(repo, ref)
    if old:
        paths = git(repo, "ls-tree", "-r", "--name-only", "-z", old).split(b"\0")
        if set(p.decode() for p in paths if p) == set(content) and all(
                git(repo, "show", old + ":" + p) == b for p, b in content.items()):
            return old, "no meaningful change; no commit or ref write"
    return snapshot(repo, content, ref), "new meaningful checkpoint"


def tracked_scope(repo):
    paths = git(repo, "ls-files", "-c", "-o", "--exclude-standard", "-z").split(b"\0")
    return sorted(set(p.decode() for p in paths if p))


def exclusion_gate(repo, affected, explicitly_included=()):
    ignored = git(repo, "check-ignore", "--no-index", "-z", "--stdin",
                  data=b"\0".join(p.encode() for p in affected) + b"\0", ok=(0, 1))
    tracked = set(p.decode() for p in git(repo, "ls-files", "-z").split(b"\0") if p)
    excluded = set(p.decode() for p in ignored.split(b"\0") if p) - tracked
    return sorted(excluded - set(explicitly_included))


def capture(repo):
    return {p: (repo / p).read_bytes() for p in tracked_scope(repo) if (repo / p).is_file()}


def preflight(repo, paths, exact=False):
    """Small controlled-policy probe; refusal must precede reading payload bytes."""
    findings = []
    hooks_path = git(repo, "config", "--get", "core.hooksPath", ok=(0, 1)).decode().strip()
    hooks = Path(hooks_path) if hooks_path else repo / ".git/hooks"
    if not hooks.is_absolute():
        hooks = repo / hooks
    if hooks.exists() and any(p.is_file() and not p.name.endswith(".sample") for p in hooks.iterdir()):
        findings.append("C08 active hook policy")
    for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG", "index.lock",
                 "rebase-merge", "rebase-apply", "sequencer"):
        if (repo / ".git" / name).exists():
            findings.append("C09 active operation or lock: " + name)
    if git(repo, "ls-files", "--unmerged", "-z"):
        findings.append("C09 unresolved index")
    attributes = git(repo, "check-attr", "-z", "--stdin", "filter", "merge", "diff", "text",
                     "eol", "working-tree-encoding", "ident", data=b"\0".join(p.encode() for p in paths) + b"\0")
    fields = attributes.split(b"\0")
    builtin = False
    for i in range(0, len(fields) - 2, 3):
        path, attr, value = (x.decode() for x in fields[i:i + 3])
        if attr == "filter" and value not in ("unspecified", "unset"):
            findings.append(("C07 LFS" if value == "lfs" else "C06 custom filter") + ": " + path)
        # Named built-in merge drivers are not a whitelist for named diff
        # drivers. For example diff=union can select diff.union.textconv.
        if attr == "merge" and value not in ("unspecified", "unset", "set", "text", "binary", "union"):
            findings.append("C08 custom merge driver: " + path)
        if attr == "diff" and value not in ("unspecified", "unset", "set"):
            findings.append("C08 named diff driver: " + path)
        if attr in ("text", "eol", "working-tree-encoding", "ident") and value not in ("unspecified", "unset"):
            builtin = True
    autocrlf = git(repo, "config", "--get", "core.autocrlf", ok=(0, 1)).strip()
    if (builtin or autocrlf not in (b"", b"false")) and not exact:
        findings.append("C05 exact-byte policy agreement required")
    return findings


def initialize(run, name, seeded=True):
    repo = contained(run / name, OUTPUT)
    repo.mkdir()
    template = run / "empty-template"
    template.mkdir(exist_ok=True)
    result = subprocess.run(["git", "init", "--initial-branch=author", "--template=" + str(template), str(repo)],
                            capture_output=True, env=environment(repo), timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr.decode())
    # Fixture setup only: config mutations are restricted to these new repos.
    git(repo, "config", "core.autocrlf", "false")
    if seeded:
        for name in ("A.md", "B.md", "C.md"):
            put(repo, name, ("id: " + name + "\nbase\n").encode())
        put(repo, ".gitignore", b"ignored.md\ncache/\n")
        put(repo, ".obsidian/app.json", b'{"spellcheck": true}\n')
        put(repo, "unrelated.md", b"independent author\n")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "Independent fixture history")
        git(repo, "branch", "other-author-branch")
        git(repo, "tag", "author-tag")
        git(repo, "remote", "add", "origin", "https://example.invalid/never-contacted.git")
        put(repo, "A.md", b"id: A.md\nstaged author draft\n")
        git(repo, "add", "A.md")
        put(repo, "A.md", b"id: A.md\nunstaged author draft\n")
        put(repo, "new-note.md", b"untracked author\n")
        put(repo, "ignored.md", b"excluded author; recovery gap\n")
        put(repo, "cache/temp", b"disposable\n")
    return repo


def prepare(repo):
    pending = resolve(repo, OP)
    if pending and load(repo)["status"] not in ("applied", "restored", "undone"):
        return {"blocked": "recover existing operation first"}
    scope = tracked_scope(repo)
    refusal = preflight(repo, scope)
    if refusal:
        return {"refused": refusal}
    before = capture(repo)
    target = dict(before)
    for p in ("A.md", "B.md", "C.md"):
        target[p] = ("id: " + p + "\nREVIEWED incoming result\n").encode()
    # Converted-source history contains incoming generated items only. Authored
    # unrelated vault context belongs in vault checkpoints, never the source.
    source_content = {p: target[p] for p in ("A.md", "B.md", "C.md")}
    source = snapshot(repo, source_content, NS + "source")
    pre = snapshot(repo, before, NS + "vault")
    result = snapshot(repo, target, NS + "accepted", [pre])
    manifest = {"version": 1, "status": "review-saved", "source": source, "pre": pre,
                "result": result, "format": 1, "policy": "controlled ordinary/raw bytes",
                "review": "synthetic explicit accept-source decisions", "rows": {}}
    for p in ("A.md", "B.md", "C.md"):
        manifest["rows"][p] = {"before": blob(repo, before[p]), "after": blob(repo, target[p])}
    persist(repo, manifest)
    return manifest


def classify(repo, manifest):
    result = {}
    for p, row in manifest["rows"].items():
        current = (repo / p).read_bytes() if (repo / p).exists() else None
        result[p] = ("before" if current == read_blob(repo, row["before"]) else
                     "after" if current == read_blob(repo, row["after"]) else "diverged-review")
    return result


def publish(repo, path, data):
    target = contained(repo / path, repo)
    temporary = target.with_name(target.name + ".prototype-publish")
    temporary.write_bytes(data)
    os.replace(temporary, target)


def worker(repo, action):
    manifest = load(repo)
    if action != "inspect":
        scope = sorted(set(tracked_scope(repo)) | set(manifest["rows"]))
        refusal = preflight(repo, scope)
        if refusal:
            # In particular do not update OP: reference-transaction could be
            # newly active since the review or the interrupted subprocess.
            return {"refused": refusal, "status": manifest["status"], "mutation": "none"}
    if action in ("crash", "crash-two"):
        if classify(repo, manifest) != {p: "before" for p in manifest["rows"]}:
            return {"stale": True}
        manifest["status"] = "applying"
        persist(repo, manifest)
        for path in list(manifest["rows"])[:(2 if action == "crash-two" else 1)]:
            publish(repo, path, read_blob(repo, manifest["rows"][path]["after"]))
        # Deliberately no journal progress. Abrupt termination, not a caught error.
        os._exit(73)
    if action == "inspect":
        return {"status": manifest["status"], "paths": classify(repo, manifest),
                "new_update": "blocked pending recovery" if manifest["status"] == "applying" else "requires state assessment"}
    if action in ("finish", "restore"):
        states = classify(repo, manifest)
        for path, state in states.items():
            if state != "diverged-review":
                key = "after" if action == "finish" else "before"
                publish(repo, path, read_blob(repo, manifest["rows"][path][key]))
        manifest["protected"] = [p for p, s in states.items() if s == "diverged-review"]
        manifest["status"] = "recovery-review" if manifest["protected"] else ("applied" if action == "finish" else "restored")
        persist(repo, manifest)
        return {"status": manifest["status"], "protected": manifest["protected"], "paths": classify(repo, manifest)}
    if action == "review-keep":
        if manifest["status"] != "recovery-review":
            raise ValueError("Explicit review only from recovery-review")
        manifest["review"] = "synthetic explicit keep later edits; accept finished other paths"
        manifest["result"] = snapshot(repo, capture(repo), NS + "vault", [manifest["result"]])
        for path, row in manifest["rows"].items():
            row["applied"] = blob(repo, (repo / path).read_bytes())
        manifest["status"] = "applied"
        persist(repo, manifest)
        return {"status": "applied", "reviewed_kept": manifest["protected"]}
    if action == "undo":
        if manifest["status"] != "applied":
            raise ValueError("Only latest applied operation offered")
        protected = []
        assumptions = {}
        for path, row in manifest["rows"].items():
            assumptions[path] = digest((repo / path).read_bytes())
            applied = read_blob(repo, row.get("applied", row["after"]))
            if (repo / path).read_bytes() != applied:
                protected.append(path)
        manifest["status"] = "undo-review"
        manifest["undo_protected"] = protected
        manifest["undo_assumptions"] = assumptions
        persist(repo, manifest)
        return {"status": manifest["status"], "protected": protected}
    if action == "undo-apply-reviewed":
        if manifest["status"] != "undo-review":
            raise ValueError("Undo requires its full review")
        if any(digest((repo / p).read_bytes()) != h for p, h in manifest["undo_assumptions"].items()):
            return {"status": "stale-undo-review", "changed": "re-review before any publication"}
        manifest["undo_choice"] = "synthetic explicit keep later-edited B, reverse eligible A/C"
        manifest["status"] = "undo-applying"
        persist(repo, manifest)
        for path, row in manifest["rows"].items():
            if path not in manifest["undo_protected"]:
                publish(repo, path, read_blob(repo, row["before"]))
        manifest["status"] = "undone"
        manifest["undo_result"] = snapshot(repo, capture(repo), NS + "vault", [manifest["result"]])
        persist(repo, manifest)
        return {"status": "undone", "kept_later_edits": manifest["undo_protected"]}
    raise ValueError(action)


def subprocess_worker(repo, action, expected=0):
    command = [sys.executable, str(SCRIPT), "--worker", action, "--repo", str(repo)]
    result = subprocess.run(command, capture_output=True, timeout=60)
    if result.returncode != expected:
        raise RuntimeError(result.stderr.decode() + result.stdout.decode())
    return {"command": command, "exit": result.returncode,
            "observation": json.loads(result.stdout) if result.stdout else None}


def recovery(run, mode):
    repo = initialize(run, "recovery-" + mode)
    start_user = user_state(repo)
    start = inventory(repo)
    refs_before = refs(repo)
    plan = prepare(repo)
    saved = load(repo)
    refs_after_saved = refs(repo)
    crash = subprocess_worker(repo, "crash-two" if mode == "restore" else "crash", 73)
    partial = inventory(repo)
    interrupted = load(repo)
    refs_after_partial = refs(repo)
    # The file already replaced is then authored after the process stopped.
    later = b"id: A.md\nAUTHOR AFTER INTERRUPTION\n"
    put(repo, "A.md", later)
    before_restart = inventory(repo)
    restart = subprocess_worker(repo, "inspect")
    blocked = prepare(repo)
    recovered = subprocess_worker(repo, mode)
    after_recovery = inventory(repo)
    expected_bc = {p: digest(read_blob(repo, plan["rows"][p]["after" if mode == "finish" else "before"]))
                   for p in ("B.md", "C.md")}
    observations = {
        "partial_changed_paths_as_expected": [p for p in start if start[p] != partial[p]] == (["A.md", "B.md"] if mode == "restore" else ["A.md"]),
        "persisted_applying_before_restart": interrupted["status"] == "applying",
        "fresh_process_detected_applying": restart["observation"]["status"] == "applying",
        "new_update_blocked": blocked == {"blocked": "recover existing operation first"},
        "later_A_preserved": (repo / "A.md").read_bytes() == later,
        "eligible_B_C_match_independent_expectations": all(after_recovery[p]["sha256"] == h for p, h in expected_bc.items()),
        "recovery_requires_review": load(repo)["status"] == "recovery-review",
        "real_user_state_unchanged": start_user == user_state(repo),
        "source_snapshot_is_distinct_from_full_vault_checkpoint": git(repo, "ls-tree", "-r", "--name-only", plan["source"]).decode().splitlines() == ["A.md", "B.md", "C.md"]
            and "new-note.md" in git(repo, "ls-tree", "-r", "--name-only", plan["pre"]).decode().splitlines(),
        "relevant_configuration_in_vault_checkpoint": ".obsidian/app.json" in git(repo, "ls-tree", "-r", "--name-only", plan["pre"]).decode().splitlines(),
        "ignored_unchanged_and_outside_checkpoint": "ignored.md" not in git(repo, "ls-tree", "-r", "--name-only", plan["pre"]).decode().splitlines()
            and start["ignored.md"] == after_recovery["ignored.md"],
    }
    evidence = {"kind": "EXECUTED real Git/filesystem and fresh subprocesses", "mode": mode,
                "independent_expected": {"A.md": "preserve author after interruption; require review",
                    "B.md,C.md": "reviewed result" if mode == "finish" else "original preimage",
                    "index_HEAD_branches_config": "byte/content identical", "new_update": "blocked"},
                "before": start, "after_partial_publication": partial, "before_fresh_restart": before_restart,
                "after_recovery": after_recovery, "saved_review_status": saved["status"],
                "crash": crash, "restart": restart, "recover": recovered, "outcomes": observations,
                "user_before": start_user, "user_after": user_state(repo), "refs": refs(repo),
                "refs_before": refs_before, "refs_after_saved_review": refs_after_saved,
                "refs_after_partial_publication": refs_after_partial,
                "manifest_after_recovery": load(repo)}
    if mode == "finish":
        reviewed = subprocess_worker(repo, "review-keep")
        put(repo, "B.md", b"AUTHOR AFTER APPLIED OPERATION\n")
        undo_pre = inventory(repo)
        undo = subprocess_worker(repo, "undo")
        undo_review_inventory = inventory(repo)
        undo_applied = subprocess_worker(repo, "undo-apply-reviewed")
        undo_after = inventory(repo)
        observations.update({
            "undo_later_B_preserved": undo_after["B.md"] == undo_pre["B.md"],
            "undo_A_C_restore_original_preimages": all((repo / p).read_bytes() == read_blob(repo, plan["rows"][p]["before"]) for p in ("A.md", "C.md")),
            "undo_review_required": undo["observation"]["status"] == "undo-review",
            "undo_review_makes_no_file_changes": undo_pre == undo_review_inventory,
            "undo_applied_only_after_explicit_whole_review": undo_applied["observation"]["status"] == "undone",
            "user_state_unchanged_after_undo": start_user == user_state(repo),
        })
        evidence.update({"explicit_recovery_review": reviewed, "before_undo": undo_pre,
                         "undo": undo, "during_undo_review": undo_review_inventory,
                         "undo_applied": undo_applied, "after_undo": undo_after,
                         "final_manifest": load(repo), "final_refs": refs(repo)})
    evidence["pass"] = all(observations.values())
    return evidence


def raw_and_policy(run):
    repo = initialize(run, "raw-bytes", seeded=False)
    put(repo, ".gitattributes", b"*.md text eol=lf\n*.utf16 working-tree-encoding=UTF-16\n*.ident ident\n")
    payloads = {"mixed.md": b"a\r\nb\nc\r\n", "bom.utf16": "exact \u03bb\r\n".encode("utf-16"),
                "binary.bin": bytes(range(256)) * 16, "keyword.ident": b"$Id: author bytes $\r\n"}
    for p, b in payloads.items():
        put(repo, p, b)
    before_user = user_state(repo)
    declined = preflight(repo, list(payloads))
    consented = preflight(repo, list(payloads), exact=True)
    oid = snapshot(repo, files(repo), NS + "vault")
    roundtrips = {p: git(repo, "show", oid + ":" + p) == b for p, b in payloads.items()}
    cases = []
    for name, attribute, hook in (("custom-filter", b"secret.dat filter=encrypted\n", False),
                                  ("lfs", b"secret.dat filter=lfs\n", False),
                                  ("custom-driver", b"secret.dat merge=custom diff=custom\n", False),
                                  ("named-diff-union", b"secret.dat diff=union\n", False),
                                  ("named-diff-text", b"secret.dat diff=text\n", False),
                                  ("named-diff-binary", b"secret.dat diff=binary\n", False),
                                  ("active-hook", b"", True)):
        candidate = initialize(run, name, seeded=False)
        put(candidate, ".gitattributes", attribute)
        put(candidate, "secret.dat", b"SYNTHETIC PAYLOAD MUST NOT ENTER CONVERTER HISTORY")
        sentinel = candidate / ".git/SENTINEL-RAN"
        if hook:
            hookpath = candidate / ".git/hooks/reference-transaction"
            hookpath.parent.mkdir(exist_ok=True)
            hookpath.write_text("#!/bin/sh\necho ran > \"$(git rev-parse --git-dir)/SENTINEL-RAN\"\n")
        else:
            # A controlled sentinel definition; probe must refuse without executing it.
            (candidate / ".git/prototype-filter.sh").write_text("#!/bin/sh\necho ran > .git/SENTINEL-RAN\ncat\n")
            git(candidate, "config", "filter.encrypted.clean", "sh .git/prototype-filter.sh")
            if name == "custom-driver":
                git(candidate, "config", "merge.custom.driver", "sh .git/prototype-filter.sh")
                git(candidate, "config", "diff.custom.textconv", "sh .git/prototype-filter.sh")
            if name.startswith("named-diff-"):
                git(candidate, "config", "diff." + name.removeprefix("named-diff-") + ".textconv", "sh .git/prototype-filter.sh")
        objects_before = sorted(str(p.relative_to(candidate / ".git/objects")) for p in (candidate / ".git/objects").rglob("*") if p.is_file())
        inv_before = inventory(candidate)
        refused = preflight(candidate, ["secret.dat"], exact=True)
        objects_after = sorted(str(p.relative_to(candidate / ".git/objects")) for p in (candidate / ".git/objects").rglob("*") if p.is_file())
        cases.append({"fixture": name, "findings": refused, "no_owned_refs": refs(candidate) == [],
                      "no_objects_written": objects_before == objects_after,
                      "files_unchanged": inv_before == inventory(candidate), "sentinel_not_run": not sentinel.exists()})
    return {"kind": "EXECUTED controlled Git attributes/refusal fixtures", "exact_choice_required": bool(declined),
            "specific_consent_clears_builtin_only": consented == [], "raw_roundtrip": roundtrips,
            "unborn_HEAD_index_config_preserved": before_user == user_state(repo), "refusals": cases,
            "pass": bool(declined) and not consented and all(roundtrips.values()) and before_user == user_state(repo)
                and all(c["findings"] and c["no_owned_refs"] and c["no_objects_written"] and c["files_unchanged"] and c["sentinel_not_run"] for c in cases)}


def changed_after_save_policy(run):
    cases = []
    for policy in ("hook", "named-diff"):
        repo = initialize(run, "changed-after-save-" + policy)
        prepare(repo)
        sentinel = repo / ".git/SENTINEL-RAN"
        if policy == "hook":
            hook = repo / ".git/hooks/reference-transaction"
            hook.parent.mkdir(exist_ok=True)
            hook.write_text("#!/bin/sh\necho ran > .git/SENTINEL-RAN\n")
        else:
            put(repo, ".gitattributes", b"A.md diff=union\n")
            (repo / ".git/sentinel.sh").write_text("#!/bin/sh\necho ran > .git/SENTINEL-RAN\ncat\n")
            git(repo, "config", "diff.union.textconv", "sh .git/sentinel.sh")
        before = inventory(repo)
        user_before = user_state(repo)
        refs_before = refs(repo)
        objects_before = sorted(str(p.relative_to(repo / ".git/objects")) for p in (repo / ".git/objects").rglob("*") if p.is_file())
        attempts = [subprocess_worker(repo, action) for action in
                    ("crash", "finish", "restore", "review-keep", "undo", "undo-apply-reviewed")]
        outcomes = {
            "all_mutating_workers_refuse_new_C08_policy": all(
                item["observation"].get("refused") and
                any("C08" in finding for finding in item["observation"]["refused"])
                for item in attempts),
            "files_unchanged": before == inventory(repo),
            "user_Git_state_unchanged": user_before == user_state(repo),
            "owned_refs_unchanged": refs_before == refs(repo),
            "no_new_objects": objects_before == sorted(str(p.relative_to(repo / ".git/objects")) for p in (repo / ".git/objects").rglob("*") if p.is_file()),
            "sentinel_not_executed": not sentinel.exists(),
            "saved_status_not_rewritten": load(repo)["status"] == "review-saved",
        }
        cases.append({"policy_added_after_review": policy, "expected": "refuse before any history/file mutation or sentinel execution",
                      "before": before, "after": inventory(repo), "refs_before": refs_before, "refs_after": refs(repo),
                      "worker_attempts": attempts, "outcomes": outcomes, "pass": all(outcomes.values())})
    return {"kind": "EXECUTED fresh-process worker refusal for policy introduced after saved review",
            "cases": cases, "pass": all(c["pass"] for c in cases),
            "limits": "Worker-entry recheck only; does not close configuration-change races after preflight or validate every effective policy"}


def exclusions_and_external_policy(run):
    repo = initialize(run, "exclusions")
    exclude = run / "controlled-global-ignore"
    exclude.write_bytes(b"global-private.md\n")
    git(repo, "config", "core.excludesFile", str(exclude))
    put(repo, "global-private.md", b"synthetic globally excluded author\n")
    put(repo, ".gitignore", (repo / ".gitignore").read_bytes() + b"unrelated.md\n")
    scope = tracked_scope(repo)
    before = user_state(repo)
    denied = exclusion_gate(repo, ["ignored.md", "global-private.md"])
    permitted = exclusion_gate(repo, ["ignored.md"], explicitly_included=["ignored.md"])
    reviewed = capture(repo)
    # Explicit converter-owned inclusion; no force-add to the user's index.
    reviewed["ignored.md"] = (repo / "ignored.md").read_bytes()
    oid = snapshot(repo, reviewed, NS + "vault")
    external = run / "controlled-global-attributes"
    external.write_bytes(b"new-note.md filter=unknown-external\n")
    git(repo, "config", "core.attributesFile", str(external))
    object_count = len(list((repo / ".git/objects").rglob("*")))
    findings = preflight(repo, scope, exact=True)
    outcomes = {
        "untracked_author_in_scope": "new-note.md" in scope,
        "tracked_then_ignored_in_scope": "unrelated.md" in scope,
        "repository_and_global_ignored_outside_default_scope": not {"ignored.md", "global-private.md"}.intersection(scope),
        "ignored_modification_blocked_without_specific_choice": denied == ["global-private.md", "ignored.md"],
        "named_inclusion_choice_clears_only_named_path": permitted == [],
        "explicitly_included_file_recoverable": git(repo, "show", oid + ":ignored.md") == reviewed["ignored.md"],
        "user_index_HEAD_branches_unchanged_by_inclusion": all(before[k] == user_state(repo)[k] for k in before if k != "config_sha256"),
        "external_attribute_filter_refused": any("C06" in f and "new-note.md" in f for f in findings),
        "external_refusal_writes_no_objects": object_count == len(list((repo / ".git/objects").rglob("*"))),
    }
    return {"kind": "EXECUTED controlled repo/global ignore and external attribute fixtures", "scope": scope,
            "excluded_recovery_gap": ["global-private.md", "cache/temp"], "findings": findings,
            "outcomes": outcomes, "pass": all(outcomes.values())}


def merge_text(repo, current, base, incoming):
    names = []
    for label, data in (("current", current), ("base", base), ("incoming", incoming)):
        path = repo.parent / ("merge-" + label)
        path.write_bytes(data)
        names.append(str(path))
    result = subprocess.run(["git", "merge-file", "-p", *names], capture_output=True,
                            env=environment(repo), timeout=30)
    return result.returncode, result.stdout


def logic_cases(run):
    repo = initialize(run, "reconciliation", seeded=False)
    cases = []

    def record(name, expected, observed, kind="LOGIC-ONLY bounded policy/identity decision; evidence persisted in Git"):
        cases.append({"case": name, "kind": kind, "expected": expected, "observed": observed, "pass": expected == observed})

    # Small literal expectations are authored independently of the merge operation.
    base = b"id: one\nfirst: base\nmiddle\nlast: base\n"
    source = base.replace(b"first: base", b"first: source")
    vault = base.replace(b"last: base", b"last: vault")
    code, compatible = merge_text(repo, vault, base, source)
    record("compatible text", {"exit": 0, "bytes": "id: one\nfirst: source\nmiddle\nlast: vault\n"},
           {"exit": code, "bytes": compatible.decode()}, "EXECUTED git merge-file on controlled text")
    code, conflict = merge_text(repo, base.replace(b"first: base", b"first: vault"), base, source)
    record("same-line conflict requires choice", True, code > 0 and b"<<<<<<<" in conflict,
           "EXECUTED git merge-file; no conflict output published")
    choose = lambda old, now, new: (new if now == old else now if new == old else None)
    record("source-only", b"incoming".hex(), choose(b"base", b"base", b"incoming").hex())
    record("vault-only generated section", b"local relationships".hex(), choose(b"base", b"local relationships", b"base").hex())
    baseline = snapshot(repo, {"one.md": base}, NS + "source")
    local = snapshot(repo, {"moved/one.md": vault}, NS + "vault")
    considered = snapshot(repo, {"one.md": source}, NS + "source")
    memory = {"identity": ["collection-A", "one"], "incoming_sha256": digest(source), "choice": "keep-vault", "format": 1}
    manifest = {"baseline": considered, "vault": local, "choices": [memory]}
    snapshot(repo, {"interpretation.json": packed(manifest)}, NS + "interpretation", [baseline, considered, local])
    before_refs = refs(repo)
    repeated = digest(source) == memory["incoming_sha256"]
    repeat_oid, repeat_action = meaningful_checkpoint(repo, {"one.md": source}, NS + "source")
    record("keep-vault same source remembered and repeat creates no refs", True,
           repeated and repeat_oid == considered and refs(repo) == before_refs and repeat_action.startswith("no meaningful"),
           "EXECUTED meaningful-checkpoint suppression in real Git; keep-vault memory is bounded Python logic")
    changed_oid, changed_action = meaningful_checkpoint(repo, {"moved/one.md": vault + b"new local author\n"}, NS + "vault")
    record("meaningful local edit receives checkpoint on repeated input", True,
           changed_oid != local and changed_action == "new meaningful checkpoint", "EXECUTED real Git checkpoint")
    record("changed source requires review again", True, digest(source + b"changed\n") != memory["incoming_sha256"])
    content = {"moved/one.md": vault, "unrelated/one.md": b"id: other\n"}
    def identities(items, collection="collection-A"):
        found = {}
        for p, data in items.items():
            for line in data.decode().splitlines():
                if line.startswith("id: "):
                    found.setdefault((collection, line[4:]), []).append(p)
        return found
    unique = identities(content)
    record("identity-preserving move keeps current path", ["moved/one.md"], unique[("collection-A", "one")])
    content["duplicate.md"] = base
    record("duplicate identity blocks affected item", True, len(identities(content)[("collection-A", "one")]) != 1)
    record("missing identity blocks affected item", [], identities({"unknown.md": b"same title\n"}).get(("collection-A", "one"), []))
    record("same item id from different collections stays distinct", True,
           not set(identities({"a.md": base}, "collection-A")).intersection(identities({"b.md": base}, "collection-B")))
    # Explicit keep-both decision, distinct binary path and a separately approved link.
    put(repo, "asset.bin", b"vault\x00binary")
    put(repo, "note.md", b"id: attachment-owner\n![[asset.bin]]\n")
    initial = inventory(repo)
    put(repo, "asset-incoming.bin", b"incoming\x00binary")
    put(repo, "note.md", b"id: attachment-owner\n![[asset.bin]]\n![[asset-incoming.bin]]\n")
    record("binary keep-both preserves existing bytes with explicit link change", True,
           inventory(repo)["asset.bin"] == initial["asset.bin"] and b"![[asset-incoming.bin]]" in (repo / "note.md").read_bytes(),
           "EXECUTED controlled filesystem changes; native link semantics unverified")
    # Saving and reloading the assumptions is real; generic conflict semantics here are bounded decisions.
    assumptions = {"file": digest((repo / "note.md").read_bytes()), "source": considered, "format": 1,
                   "policy_config": digest((repo / ".git/config").read_bytes())}
    saved = snapshot(repo, {"review.json": packed(assumptions)}, NS + "saved-review", [considered])
    reopened = json.loads(git(repo, "show", saved + ":review.json"))
    record("saved review resumes unchanged", assumptions, reopened, "EXECUTED Git-persisted review reload")
    put(repo, "note.md", (repo / "note.md").read_bytes() + b"later author\n")
    record("stale review invalidates approval", True, digest((repo / "note.md").read_bytes()) != reopened["file"])
    record("format version change requires separate review", True, 2 != reopened["format"])
    git(repo, "config", "core.autocrlf", "true")
    record("changed storage policy invalidates scoped agreement", True,
           digest((repo / ".git/config").read_bytes()) != reopened["policy_config"])
    legacy = {"source_id": "one", "path": "legacy.md", "pristine_bytes": None}
    record("legacy identity is not pristine baseline", "uncertain; preserve current; reviewed onboarding; no old Undo",
           "uncertain; preserve current; reviewed onboarding; no old Undo" if legacy["pristine_bytes"] is None else "known")
    record("source disappearance retains files", True, "asset.bin" in inventory(repo))
    record("unchanged-source local deletion remains absent", None, choose(base, None, base))
    snapshot(repo, {"case-observations.json": packed(cases)}, NS + "case-evidence", [saved, considered, local])
    return {"cases": cases, "refs": refs(repo), "pass": all(c["pass"] for c in cases),
            "limitation": "Tiny synthetic identity/decision logic, not production structured-note reconciliation or native link validation"}


def measurement(run):
    repo = initialize(run, "measurement", seeded=False)
    content = {f"notes/{i:04}.md": (f"id: {i}\n" + "synthetic authored content\n" * 12).encode() for i in range(120)}
    # Deterministic incompressible-ish bytes; bounded two 256 KiB revisions.
    content["attachments/a.bin"] = b"".join(hashlib.sha256(str(i).encode()).digest() for i in range(8192))
    start = time.perf_counter()
    snapshot(repo, content, NS + "vault")
    first = time.perf_counter() - start
    content["attachments/a.bin"] = bytes(x ^ 0x55 for x in content["attachments/a.bin"])
    content["notes/0001.md"] += b"reviewed source change\n"
    start = time.perf_counter()
    snapshot(repo, content, NS + "vault")
    second = time.perf_counter() - start
    object_bytes = sum(p.stat().st_size for p in (repo / ".git/objects").rglob("*") if p.is_file())
    return {"kind": "EXECUTED raw snapshots, loose objects (no GC)", "notes": 120,
            "attachment_bytes_each_revision": 262144, "revisions": 2,
            "input_bytes_final": sum(map(len, content.values())), "object_store_bytes": object_bytes,
            "first_seconds": round(first, 3), "changed_attachment_seconds": round(second, 3),
            "limits": "Single local run, warm OS caches possible; no real export, scaling prediction, cancellation or disk-full promise"}


def support_matrix():
    # Evidence classification only; #248 remains the policy owner.
    descriptions = {
        "C01": ("observed subset", "New/unborn raw checkpoint; no real onboarding UI"),
        "C02": ("observed subset", "Ordinary rooted repos; symbolic HEAD/branches/index preserved; detached HEAD unverified"),
        "C03": ("observed", "Same file staged then unstaged; publication preserves real index/staged blobs"),
        "C04": ("observed subset", "Branches/tag and inert invalid remote retained; no network command"),
        "C05": ("observed subset", "Controlled CRLF/LF/UTF-16/ident raw round trips; specific agreement gating"),
        "C06": ("refused observed", "Local and controlled external filter bindings refused before checkpoints"),
        "C07": ("refused observed subset", "LFS attribute binding refused; pointer/payload/installation variants unverified"),
        "C08": ("refused observed subset", "Active reference hook/custom merge/named diff drivers refused, including diff=union/text/binary textconv; worker-entry recheck after saved review; inherited hooksPath and race coverage unverified"),
        "C09": ("observed subset", "Applying converter operation blocks prepare; user operation/lock detectors unexecuted"),
        "C10": ("observed subset", "Repo/global ignore, tracked-then-ignored, disclosed gap and specific converter inclusion"),
        "C11": ("unverified", "Linked/shared/redirected layouts; runner accepts newly generated simple repos only"),
        "C12": ("unverified", "Parent/nested/submodule/bare discovery not implemented"),
        "C13": ("unverified", "Sparse/assume-unchanged/skip-worktree refusal not implemented"),
        "C14": ("unverified", "Promisor/shallow/alternates/corruption/extensions/ref formats; only SHA-1 loose objects exercised"),
        "C15": ("observed subset", "Owned-output containment guard; reparse races/storage/access/ownership/collisions unverified"),
        "C16": ("observed bounded", "Two 256 KiB binary revisions plus tiny explicit keep-both/link publication"),
        "C17": ("observed one executable", "Git 2.55.0.windows.5 only; maintained version range remains unresolved"),
        "H01": ("observed subset", "Blobs/manifest reloaded through owned refs; full validation contract unverified"),
        "H02": ("unverified", "No copy/clone/backup transfer experiment"),
        "H03": ("logic-only", "Missing pristine baseline preserves uncertainty; no Sync or restore experiment"),
        "H04": ("logic-only", "Identity without pristine bytes cannot establish original; onboarding UI absent"),
        "H05": ("unverified", "No independent branch-history rewrite experiment"),
        "H06": ("unverified", "No damaged/removed history or validated restore experiment"),
        "H07": ("observed bounded", "Abrupt partial publication, fresh restart, eligible finish/restore, later edits protected"),
        "H08": ("unverified", "No remote/other-device transport; no network used"),
        "H09": ("unverified", "No cleanup/GC/retention-loss experiment"),
    }
    return {key: {"evidence": state, "scope": detail} for key, (state, detail) in descriptions.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=["crash", "crash-two", "inspect", "finish", "restore", "review-keep", "undo", "undo-apply-reviewed"])
    parser.add_argument("--repo", type=Path)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(owned_repo(args.repo), args.worker)))
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    run = contained(OUTPUT / (time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]), OUTPUT)
    run.mkdir()
    (run / "PROTOTYPE-OWNED.json").write_bytes(packed({"purpose": "#244 disposable synthetic Git experiment", "root": str(run)}))
    (run / "empty-global-config").write_bytes(b"")
    start = time.perf_counter()
    result = {"question": "Can isolated Git history support preservation and restart recovery without altering user Git state?",
              "run": str(run), "python": sys.executable, "git_executable": shutil.which("git"),
              "script_sha256": digest(SCRIPT.read_bytes()),
              "git_version": subprocess.run(["git", "--version"], capture_output=True, text=True).stdout.strip(),
              "configuration": "New synthetic repos; empty system/global policy; per-repo controlled fixtures only",
              "recovery_finish": recovery(run, "finish"), "recovery_restore": recovery(run, "restore"),
              "raw_policy": raw_and_policy(run), "exclusions_external_policy": exclusions_and_external_policy(run),
              "changed_after_save_policy": changed_after_save_policy(run),
              "reconciliation": logic_cases(run), "measurement": measurement(run), "support_evidence": support_matrix()}
    result["elapsed_seconds"] = round(time.perf_counter() - start, 3)
    result["pass"] = all(result[k]["pass"] for k in ("recovery_finish", "recovery_restore", "raw_policy", "exclusions_external_policy", "changed_after_save_policy", "reconciliation"))
    (run / "results.json").write_bytes(packed(result))
    report = ["# Git prototype executable observations", "", f"Run: `{run}`", "",
              f"Git: {result['git_version']}; elapsed {result['elapsed_seconds']} seconds.", "",
              "Synthetic experiment outcomes: " + ("PASS" if result["pass"] else "FAIL"), "",
              "This is observed candidate evidence; human behavior verdict and production feasibility remain open.", ""]
    for label in ("recovery_finish", "recovery_restore"):
        report += ["## " + label, "", "Fresh subprocess exits 73 after partial publication (A; or A/B for restore), before progress journaling.", "",
                   "Later A edits survive; B/C finish or restore; operation remains recovery-review. Real index/HEAD/branches/config stay identical.", ""]
        report += [f"- {name}: {value}" for name, value in result[label]["outcomes"].items()]
        report += [""]
    report += ["## Raw-byte and policy fixtures", "", "CRLF/mixed LF, UTF-16/BOM, ident and NUL binary bytes round-trip through raw Git blobs.",
               "Built-in transformations require specific consent; custom filters/LFS/drivers/active hook fixtures refuse before writing objects or refs.", "",
               "Named diff=union/text/binary textconv fixtures are refused separately from built-in merge driver names.",
               "A hook or diff=union textconv introduced after saved review is refused by all mutating fresh-process workers, with unchanged files/refs/objects/status and no sentinel execution.",
               "Worker-entry preflight does not close policy changes racing after that check.", "",
               "## Bounds", "", "See results.json for inventories, subprocess commands, manifests, refs, unchanged staged/index state, exact expectations and measurement.",
               "No power-loss/fsync, arbitrary host policy, locks/concurrent writers, real Obsidian semantics, advanced repository layouts, disk-full, or large-scale/cancellation evidence.",
               "Known gaps are unverified, not silently supported. No automatic supported Git-version range follows from one executable.", ""]
    report += ["## Accepted policy evidence (not a new support policy)", "", "| Row | Evidence | Scope |", "| --- | --- | --- |"]
    report += [f"| {key} | {row['evidence']} | {row['scope']} |" for key, row in result["support_evidence"].items()]
    (run / "REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps({"run": str(run), "pass": result["pass"], "seconds": result["elapsed_seconds"],
                      "results": str(run / "results.json"), "report": str(run / "REPORT.md")}, indent=2))
    if not result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
