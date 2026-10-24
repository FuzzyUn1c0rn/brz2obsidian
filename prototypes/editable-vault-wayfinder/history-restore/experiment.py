"""Bounded #250 experiment. All Git mutations stay inside new owned fixtures.

The association file and Git envelope are experimental contract proposals, not
accepted production formats. No histories live outside Git; the current file
holds only association and a generation marker, never historical payloads.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time
import uuid
import zlib

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[3]
SCRIPT = Path(__file__).resolve()
SCRIPT_SHA = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
BASE = PROJECT / "prototypes/editable-vault-wayfinder/git/experiment.py"
BASE_SHA = "fddfe131e1d0ad791abdcaeb2939a2c51311a95143fe80f81f0c0771664be6df"
OUTPUT = PROJECT / "tmp/merge-wayfinding/followups/history"
assert hashlib.sha256(BASE.read_bytes()).hexdigest() == BASE_SHA
spec = importlib.util.spec_from_file_location("frozen_git_experiment", BASE)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
g.OUTPUT = OUTPUT
NS = g.NS
IDENTITY = NS + "identity"
HISTORY = NS + "history"
ASSOCIATION = ".brz2obsidian/association.json"
COMMANDS = []


def git(repo, *args, data=None, index=None, ok=(0,)):
    g.owned_repo(repo)
    env = g.environment(repo)
    if index is not None:
        env["GIT_INDEX_FILE"] = str(g.contained(index, repo))
    result = subprocess.run(["git", "-C", str(repo), *args], input=data,
                            capture_output=True, env=env, timeout=30)
    COMMANDS.append({"repo": str(repo), "args": list(args), "exit": result.returncode,
                     "isolated_index": str(index) if index else None,
                     "stdin_hex": data.hex() if data is not None else None,
                     "stderr": result.stderr.decode(errors="replace")})
    if result.returncode not in ok:
        raise ValueError("Git object/layout validation failed: " + result.stderr.decode(errors="replace"))
    return result.stdout


# Preserve the frozen helper's logic while recording every helper Git command.
g.git = git


def state(repo, all_git=False):
    contents = {str(p.relative_to(repo)).replace("\\", "/"): p.read_bytes()
                for p in sorted(repo.rglob("*")) if p.is_file()
                and (all_git or not p.is_relative_to(repo / ".git"))}
    return {p: {"sha256": g.digest(b), "bytes": len(b), "hex": b.hex()}
            for p, b in contents.items()}


def user(repo):
    value = g.user_state(repo)
    value["index_hex"] = (repo / ".git/index").read_bytes().hex()
    value["HEAD_hex"] = (repo / ".git/HEAD").read_bytes().hex()
    value["config_hex"] = (repo / ".git/config").read_bytes().hex()
    return value


def closure(repo, roots):
    return set(git(repo, "rev-list", "--objects", "--no-object-names", *roots).decode().split())


def object_data(repo, oid):
    kind = git(repo, "cat-file", "-t", oid).strip()
    data = git(repo, "cat-file", kind.decode(), oid)
    raw = kind + b" " + str(len(data)).encode() + b"\0" + data
    if hashlib.sha1(raw).hexdigest() != oid:
        raise ValueError("Object hash/integrity mismatch: " + oid)
    return raw


def tree_inventory(repo, oid):
    entries = git(repo, "ls-tree", "-r", "-z", oid).split(b"\0")
    answer = {}
    for entry in filter(None, entries):
        header, path = entry.split(b"\t", 1)
        mode, kind, blob = header.decode().split()
        if kind != "blob" or mode != "100644":
            raise ValueError("Unexpected fixture snapshot entry")
        data = git(repo, "cat-file", "blob", blob)
        answer[path.decode()] = {"mode": mode, "oid": blob,
                                 "sha256": g.digest(data), "bytes": len(data)}
    return answer


def seal(repo, identity, status="applied"):
    manifest = g.load(repo)
    manifest["status"] = status
    manifest["association"] = identity
    g.persist(repo, manifest)
    g.snapshot(repo, {"identity.json": g.packed(identity)}, IDENTITY)
    refs = dict(line.split() for line in g.refs(repo) if not line.startswith(HISTORY + " "))
    envelope = {"schema": 1, "identity": identity, "required_refs": refs,
                "snapshots": {ref: tree_inventory(repo, oid) for ref, oid in refs.items()},
                "operation": manifest, "complete": True}
    g.snapshot(repo, {"history.json": g.packed(envelope)}, HISTORY, list(refs.values()))
    return envelope


def validate(repo, expected):
    """Read-only, rejecting before any target object/ref writes."""
    root = g.resolve(repo, HISTORY)
    if not root:
        raise ValueError("Required history root absent")
    envelope = json.loads(git(repo, "show", root + ":history.json"))
    if envelope.get("schema") != 1 or not envelope.get("complete"):
        raise ValueError("Incomplete/unsupported history envelope")
    if envelope["identity"] != expected:
        raise ValueError("Supplied history does not match independent current association")
    refs = envelope["required_refs"]
    required = {NS + p for p in ("source", "vault", "accepted", "operation", "identity")}
    if set(refs) != required:
        raise ValueError("Required owned ref set incomplete/unknown")
    for ref, oid in refs.items():
        if g.resolve(repo, ref) != oid:
            raise ValueError("Required owned ref missing/changed: " + ref)
    roots = [root, *refs.values()]
    reachable = closure(repo, [root])
    if not set(refs.values()) <= reachable:
        raise ValueError("Ref mentioned by manifest but not retained by history root")
    objects = {oid: object_data(repo, oid) for oid in closure(repo, roots)}
    # Full-copy prerequisite, including existing independent history, is checked
    # without contacting the inert remote or changing configuration.
    git(repo, "fsck", "--full", "--strict", "--no-reflogs")
    for ref, oid in refs.items():
        if tree_inventory(repo, oid) != envelope["snapshots"][ref]:
            raise ValueError("Snapshot inventory mismatch: " + ref)
    identity = json.loads(git(repo, "show", refs[IDENTITY] + ":identity.json"))
    manifest = json.loads(git(repo, "show", refs[g.OP] + ":manifest.json"))
    if identity != expected or manifest != envelope["operation"] or manifest["association"] != expected:
        raise ValueError("Identity/operation envelope inconsistent")
    # Each indispensable dependency must be retained from operation itself;
    # another ref or a textual OID in JSON is insufficient retention.
    operation_closure = closure(repo, [refs[g.OP]])
    for field, ref in (("source", NS + "source"), ("pre", NS + "vault"),
                       ("result", NS + "accepted")):
        if manifest.get(field) != refs[ref] or manifest[field] not in operation_closure:
            raise ValueError("Indispensable operation dependency absent/unreachable: " + field)
    for path, row in manifest["rows"].items():
        for key, snapshot in (("before", "pre"), ("after", "result")):
            actual = git(repo, "rev-parse", manifest[snapshot] + ":" + path).decode().strip()
            if row[key] != actual or actual not in operation_closure:
                raise ValueError("Operation row does not match retained snapshot")
    return {"envelope": envelope, "refs": {**refs, HISTORY: root}, "objects": objects,
            "operation_closure": sorted(operation_closure)}


def gate(target):
    # Suspicion marker is outside history and survives notes-only copying in this
    # controlled fixture. No marker is claimed universally available/detectable.
    suspicion = target / ".brz2obsidian/recovery-required.json"
    if suspicion.exists():
        return {"outcome": "recovery-required", "onboarding": "blocked",
                "reason": "Known interrupted operation; validate indispensable history first"}
    if g.resolve(target, g.OP):
        try:
            operation = g.load(target)
        except (ValueError, KeyError, json.JSONDecodeError):
            return {"outcome": "recovery-required", "onboarding": "blocked",
                    "reason": "Existing operation state cannot be read; interruption cannot be excluded"}
        if operation.get("status") in ("applying", "recovery-review", "undo-applying"):
            return {"outcome": "recovery-required", "onboarding": "blocked",
                    "reason": "Git-persisted incomplete operation takes precedence over history restoration"}
    anchor = target / ASSOCIATION
    if not anchor.exists():
        return {"outcome": "association-review-required", "onboarding": "separate-reviewed-option",
                "reason": "No independent current association; backup identity cannot prove itself"}
    return None


def restore(target, supplied):
    current_gate = gate(target)
    if current_gate:
        return current_gate
    anchor = json.loads((target / ASSOCIATION).read_bytes())
    try:
        checked = validate(supplied, anchor)
        findings = g.preflight(target, g.tracked_scope(target))
        if findings:
            raise ValueError("Target policy refusal: " + "; ".join(findings))
        # No rollback of valid newer converter history under the restore label.
        old = g.resolve(target, HISTORY)
        if old and old != checked["refs"][HISTORY]:
            try:
                validate(target, anchor)
            except (ValueError, KeyError, json.JSONDecodeError):
                pass  # Damaged owned history may be repaired from matching copy.
            else:
                raise ValueError("Different intact target history requires separate reconciliation")
    except (ValueError, KeyError, json.JSONDecodeError) as error:
        return {"outcome": "refused", "reason": str(error), "mutation": "none"}
    prior = {ref: g.resolve(target, ref) for ref in checked["refs"]}
    user_roots = git(target, "for-each-ref", "--format=%(objectname)", "refs/heads", "refs/tags").decode().split()
    user_objects = closure(target, user_roots)
    written = []
    # Only validated reachable converter objects are copied. Correct loose
    # objects can replace a damaged same-OID converter object. No normal index,
    # worktree, configuration, user refs or source backup is copied over target.
    for oid, raw in checked["objects"].items():
        object_path = target / ".git/objects" / oid[:2] / oid[2:]
        object_path.parent.mkdir(exist_ok=True)
        if object_path.exists():
            try:
                if zlib.decompress(object_path.read_bytes()) == raw:
                    continue
            except zlib.error:
                pass
            # Git's loose objects are read-only on Windows. Only a verified
            # same-OID damaged converter object is made replaceable here.
            object_path.chmod(stat.S_IWRITE | stat.S_IREAD)
        temp = object_path.with_name(object_path.name + ".restore-tmp")
        temp.write_bytes(zlib.compress(raw))
        os.replace(temp, object_path)
        written.append(oid)
    transaction = "start\n" + "".join(
        f"update {ref} {oid} {prior[ref] or '0' * 40}\n"
        for ref, oid in checked["refs"].items()) + "prepare\ncommit\n"
    git(target, "update-ref", "--stdin", data=transaction.encode())
    verified = validate(target, anchor)
    return {"outcome": "history-restored", "refs": verified["refs"],
            "reachable_objects": sorted(verified["objects"]),
            "written_objects": sorted(written),
            "converter_closure_also_in_user_history": sorted(set(checked["objects"]) & user_objects),
            "written_objects_also_in_user_history": sorted(set(written) & user_objects),
            "review": "Previous approvals require fresh review against newer current files"}


def worker(target, supplied, output):
    before = state(target, True)
    supplied_before = state(supplied, True)
    current = state(target)
    user_before = user(target)
    result = restore(target, supplied)
    snapshots = {}
    if result["outcome"] == "history-restored":
        for suffix in ("source", "vault", "accepted"):
            ref = NS + suffix
            paths = git(target, "ls-tree", "-r", "--name-only", "-z", ref).split(b"\0")
            snapshots[suffix] = {p.decode(): git(target, "show", ref + ":" + p.decode()).hex()
                                 for p in paths if p}
    output.write_bytes(g.packed({"result": result, "all_before": before,
                                "all_after": state(target, True),
                                "files_before": current, "files_after": state(target),
                                "user_before": user_before, "user_after": user(target),
                                "restored_literal_snapshots": snapshots, "commands": COMMANDS}))
    # Separate immutable-backup assertion, including rejected/corrupt fixtures.
    record = json.loads(output.read_bytes())
    record["supplied_copy_unchanged"] = supplied_before == state(supplied, True)
    output.write_bytes(g.packed(record))


def run_case(run, name, source, target, expectation, expected_snapshots=None):
    evidence = run / (name + ".json")
    command = [sys.executable, str(SCRIPT), "--worker", str(target), str(source), str(evidence)]
    result = subprocess.run(command, capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    record = json.loads(evidence.read_bytes())
    outcome = record["result"]["outcome"]
    checks = {"outcome": outcome == expectation,
              "supplied_copy_unchanged": record["supplied_copy_unchanged"],
              "exact_current_file_bytes": record["files_before"] == record["files_after"],
              "exact_user_git_state": record["user_before"] == record["user_after"]}
    if expectation != "history-restored":
        checks["zero_target_mutation"] = record["all_before"] == record["all_after"]
    else:
        checks["independent_literal_history_bytes"] = record["restored_literal_snapshots"] == expected_snapshots
    return {"name": name, "expected": expectation, "observed": record["result"],
            "checks": checks, "pass": all(checks.values()), "command": command,
            "evidence": str(evidence)}


def copy_repo(run, source, name):
    target = run / name
    shutil.copytree(source, target)
    return target


def remove_owned_history(repo, corrupt=False):
    anchor = json.loads((repo / ASSOCIATION).read_bytes())
    checked = validate(repo, anchor)
    if corrupt:
        oid = checked["envelope"]["operation"]["rows"]["A.md"]["before"]
        path = repo / ".git/objects" / oid[:2] / oid[2:]
        path.chmod(stat.S_IWRITE | stat.S_IREAD)
        path.write_bytes(b"corrupt object\n")
        return
    # Simulate selectively lost converter objects while preserving user closure.
    user_roots = git(repo, "for-each-ref", "--format=%(objectname)", "refs/heads", "refs/tags").decode().split()
    user_objects = closure(repo, user_roots)
    for ref in checked["refs"]:
        git(repo, "update-ref", "-d", ref)
    for oid in set(checked["objects"]) - user_objects:
        path = repo / ".git/objects" / oid[:2] / oid[2:]
        if path.exists():
            path.chmod(stat.S_IWRITE | stat.S_IREAD)
            path.unlink()


def main():
    started = time.perf_counter()
    run = OUTPUT / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    (run / "PROTOTYPE-OWNED.json").write_bytes(g.packed({"issue": 250, "synthetic": True}))
    identity = {"schema": 1, "vault_id": "synthetic-vault-250",
                "source_collection_id": "synthetic-brain-250",
                "lineage": "reviewed-fixture-association-250", "generation": "generation-1"}
    # These expected bytes are stated independently of snapshot/tree/restore
    # results and include exactly the frozen fixture's disclosed authored scope.
    expected_pre = {"A.md": b"id: A.md\nunstaged author draft\n",
                    "B.md": b"id: B.md\nbase\n", "C.md": b"id: C.md\nbase\n",
                    ".gitignore": b"ignored.md\ncache/\n",
                    ".obsidian/app.json": b'{"spellcheck": true}\n',
                    "unrelated.md": b"independent author\n", "new-note.md": b"untracked author\n",
                    ASSOCIATION: g.packed(identity)}
    expected_source = {p: ("id: " + p + "\nREVIEWED incoming result\n").encode()
                       for p in ("A.md", "B.md", "C.md")}
    expected_snapshots = {kind: {p: b.hex() for p, b in content.items()}
                          for kind, content in (("source", expected_source), ("vault", expected_pre),
                                                ("accepted", {**expected_pre, **expected_source}))}
    original = g.initialize(run, "original")
    g.put(original, ASSOCIATION, g.packed(identity))
    g.prepare(original)
    envelope = seal(original, identity)
    supplied = copy_repo(run, original, "complete-history-copy")
    current = copy_repo(run, original, "newer-current")
    # Literal independently authored current states; backups have older bytes.
    newer = {"A.md": b"id: A.md\nnewer staged text\n",
             "B.md": b"id: B.md\nnewer B author writing\r\n",
             "newer-untracked.md": b"new authored file after backup\n"}
    g.put(current, "A.md", newer["A.md"])
    git(current, "add", "A.md")
    newer["A.md"] = b"id: A.md\nnewer unstaged text after staging\n"
    for path, data in newer.items():
        g.put(current, path, data)
    rows = []
    rows.append(run_case(run, "intact-matching", supplied, copy_repo(run, current, "intact"), "history-restored", expected_snapshots))
    missing = copy_repo(run, current, "missing-target")
    remove_owned_history(missing)
    missing_object_count = len(list((missing / ".git/objects").glob("??/*")))
    rows.append(run_case(run, "restore-missing-onto-newer", supplied, missing, "history-restored", expected_snapshots))
    damaged = copy_repo(run, current, "damaged-target")
    remove_owned_history(damaged, True)
    rows.append(run_case(run, "restore-corrupt-target", supplied, damaged, "history-restored", expected_snapshots))
    rewritten = copy_repo(run, current, "rewritten-user-ancestry")
    tree = git(rewritten, "rev-parse", "HEAD^{tree}").decode().strip()
    orphan = git(rewritten, "commit-tree", tree, data=b"Independent rewritten user ancestry\n").decode().strip()
    git(rewritten, "update-ref", "refs/heads/author", orphan)
    rows.append(run_case(run, "rewritten-user-ancestry", supplied, rewritten, "history-restored", expected_snapshots))
    newer_history = copy_repo(run, current, "different-intact-current-history")
    seal(newer_history, identity, status="restored")
    rows.append(run_case(run, "different-intact-current-history", supplied, newer_history, "refused"))
    for name, mutation in (("mismatch", "identity"), ("missing-ref", "ref"),
                           ("missing-object", "missing"), ("corrupt-object", "corrupt"),
                           ("json-only-dependency", "unreachable")):
        bad = copy_repo(run, supplied, "bad-" + name)
        if mutation == "identity":
            wrong = dict(identity, vault_id="another-vault")
            seal(bad, wrong)
        elif mutation == "ref":
            git(bad, "update-ref", "-d", NS + "source")
        elif mutation in ("missing", "corrupt"):
            oid = envelope["operation"]["rows"]["B.md"]["after"]
            path = bad / ".git/objects" / oid[:2] / oid[2:]
            path.chmod(stat.S_IWRITE | stat.S_IREAD)
            if mutation == "missing":
                path.unlink()
            else:
                path.write_bytes(b"damaged compressed object")
        else:
            manifest = g.load(bad)
            old_op = g.resolve(bad, g.OP)
            # Keep object available and JSON unchanged, but remove actual parent
            # retention. A root textually naming an OID must fail completeness.
            index = bad / ".git/temporary-isolated-index"
            manifest_tree = git(bad, "rev-parse", old_op + "^{tree}").decode().strip()
            detached = git(bad, "commit-tree", manifest_tree, data=b"JSON only; no required parents\n").decode().strip()
            git(bad, "update-ref", g.OP, detached)
            adjusted = copy.deepcopy(envelope)
            adjusted["required_refs"][g.OP] = detached
            g.snapshot(bad, {"history.json": g.packed(adjusted)}, HISTORY,
                       list(adjusted["required_refs"].values()))
        rows.append(run_case(run, name, bad, copy_repo(run, current, "target-" + name), "refused"))
        if name == "missing-ref":
            corrupt_target = copy_repo(run, current, "corrupt-target-invalid-copy")
            remove_owned_history(corrupt_target, True)
            rows.append(run_case(run, "corrupt-target-invalid-copy", bad, corrupt_target, "refused"))
    absent = copy_repo(run, current, "association-absent")
    (absent / ASSOCIATION).unlink()
    rows.append(run_case(run, "missing-current-association", supplied, absent, "association-review-required"))
    interrupted = copy_repo(run, current, "interrupted-missing-preimage")
    interrupted_manifest = g.load(interrupted)
    interrupted_manifest["status"] = "applying"
    incomplete_operation_oid = g.persist(interrupted, interrupted_manifest)
    indispensable = interrupted_manifest["rows"]["A.md"]["before"]
    missing_path = interrupted / ".git/objects" / indispensable[:2] / indispensable[2:]
    missing_path.chmod(stat.S_IWRITE | stat.S_IREAD)
    missing_path.unlink()
    git(interrupted, "cat-file", "-e", indispensable, ok=(1, 128))
    # The physically persisted operation and its absent indispensable blob are
    # independent of the tiny current suspicion signal. The older supplied copy
    # does not include this interrupted operation generation.
    suspicion_bytes = g.packed({
        "operation": "incomplete-update", "operation_oid": incomplete_operation_oid,
        "indispensable_preimage_oid": indispensable, "preimage": "missing"})
    # No current marker in this first case: available Git operation state must
    # independently establish interruption before any old refs can overwrite it.
    rows.append(run_case(run, "interrupted-missing-preimage", supplied, interrupted, "recovery-required"))
    missing_identity_interrupted = copy_repo(run, interrupted, "interrupted-also-missing-association")
    g.put(missing_identity_interrupted, ".brz2obsidian/recovery-required.json", suspicion_bytes)
    (missing_identity_interrupted / ASSOCIATION).unlink()
    rows.append(run_case(run, "interruption-priority-before-association", supplied,
                         missing_identity_interrupted, "recovery-required"))
    results = {"issue": 250, "base_commit": "273233fb4020ceb156ed6b3ab33785adcedfdda9",
               "base_sha256": BASE_SHA, "source_sha256": SCRIPT_SHA,
               "python": sys.executable, "git": shutil.which("git"),
               "git_version": git(original, "--version").decode().strip(),
               "identity": identity, "literal_newer_current": {p: b.hex() for p, b in newer.items()},
               "independent_expected_history_bytes": expected_snapshots,
               "incomplete_operation": {"operation_oid": incomplete_operation_oid,
                                        "persisted_status": g.load(interrupted)["status"],
                                        "missing_preimage_oid": indispensable},
               "initial_envelope": envelope, "cases": rows,
               "missing_target_objects_before_restore": missing_object_count,
               "elapsed_seconds": round(time.perf_counter() - started, 3),
               "pass": all(row["pass"] for row in rows), "setup_commands": COMMANDS}
    if g.digest(SCRIPT.read_bytes()) != SCRIPT_SHA:
        raise RuntimeError("Source changed during run; evidence is not an exact-candidate result")
    (run / "results.json").write_bytes(g.packed(results))
    report = ["# #250 bounded matching-history evidence", "", f"PASS: {results['pass']}; elapsed {results['elapsed_seconds']} seconds.",
              "", f"Source SHA-256: `{results['source_sha256']}`", "", "| Scenario | Expected | Observed | Verdict |", "| --- | --- | --- | --- |"]
    report += [f"| {r['name']} | {r['expected']} | {r['observed']['outcome']} | {'PASS' if r['pass'] else 'FAIL'} |" for r in rows]
    report += ["", "All observations are synthetic, ordinary local SHA-1 Git repositories. See README.md for scope, proposed formats and unverified failure modes.",
               "Each scenario uses a new Python process. Evidence contains exact current file/index/HEAD/config bytes, user refs/staged entries and commands."]
    (run / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"run": str(run), "pass": results["pass"], "seconds": results["elapsed_seconds"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", nargs=3)
    args = parser.parse_args()
    if args.worker:
        target, supplied, output = map(Path, args.worker)
        g.contained(output, OUTPUT)
        worker(g.owned_repo(target), g.owned_repo(supplied), output)
    else:
        main()
