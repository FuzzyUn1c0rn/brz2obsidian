"""#249 bounded recovery direction/Undo experiment; synthetic disposable Git only.

Run with .venv/Scripts/python.exe. --help documents fresh-process worker options.
Frozen Git plumbing is loaded read-only from the recorded local commit. This is
throwaway executable evidence, not production update/recovery implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time
import types
import uuid


PROJECT = Path(__file__).resolve().parents[3]
OUTPUT = PROJECT / "tmp/merge-wayfinding/followups/recovery"
SCRIPT = Path(__file__).resolve()
FROZEN = "273233fb4020ceb156ed6b3ab33785adcedfdda9"
FROZEN_PATH = "prototypes/editable-vault-wayfinder/git/experiment.py"
FROZEN_SHA = "fddfe131e1d0ad791abdcaeb2939a2c51311a95143fe80f81f0c0771664be6df"
NS = "refs/brz2obsidian/recovery-evidence/"
OP = NS + "operation"
TERMINAL = ("applied", "undone", "restored")

# Literal expectations are retained before any repository is initialized. These
# are the independently authored fixture outcomes, not values read from history.
PRE = {"A.md": b"id: A.md\nunstaged author draft\n",
       "B.md": b"id: B.md\nbase\n", "C.md": b"id: C.md\nbase\n"}
INCOMING = {"A.md": b"id: A.md\nSOURCE A accepted\n",
            "B.md": b"id: B.md\nSOURCE B accepted\n",
            "C.md": b"id: C.md\nSOURCE C accepted\n"}
B_BEFORE_UNDO = b"id: B.md\nSOURCE B accepted\nAUTHOR before Undo\n"
A_AFTER_UNDO_STOP = b"id: A.md\nunstaged author draft\nAUTHOR after Undo stop\n"
A_AFTER_APPLY_STOP = b"id: A.md\nSOURCE A accepted\nAUTHOR after apply stop\n"
B_AFTER_FINISH_STOP = b"id: B.md\nSOURCE B accepted\nAUTHOR after finish stop\n"
B_AFTER_RESTORE_STOP = b"id: B.md\nSOURCE B accepted\nAUTHOR after restore stop\n"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def packed(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def frozen_helpers():
    result = subprocess.run(["git", "-C", str(PROJECT), "show", FROZEN + ":" + FROZEN_PATH],
                            capture_output=True, timeout=30)
    if result.returncode or sha(result.stdout) != FROZEN_SHA:
        raise RuntimeError("Frozen plumbing input is unavailable or differs from provenance")
    module = types.ModuleType("frozen_git_plumbing")
    module.__file__ = str(PROJECT / FROZEN_PATH)
    exec(compile(result.stdout, module.__file__, "exec"), module.__dict__)
    module.OUTPUT = OUTPUT
    module.NS = NS
    module.OP = OP
    return module


B = frozen_helpers()


def load(repo):
    return json.loads(B.git(repo, "show", OP + ":manifest.json"))


def save(repo, manifest):
    manifest["generation"] += 1
    parents = list(manifest["snapshots"].values())
    if manifest.get("undo_of"):
        parents.append(manifest["undo_of"])
    return B.snapshot(repo, {"manifest.json": packed(manifest)}, OP, parents)


def required(manifest):
    return sorted(set(manifest["snapshots"].values()) |
                  {oid for row in manifest["rows"].values() for oid in row.values()})


def unavailable(repo, manifest):
    return [oid for oid in required(manifest)
            if not B.git(repo, "cat-file", "-t", oid, ok=(0, 128))]


def reachable(repo, manifest):
    output = B.git(repo, "rev-list", "--objects", OP, ok=(0, 128)).decode()
    objects = {line.split()[0] for line in output.splitlines() if line}
    return {oid: oid in objects for oid in required(manifest)}


def current(repo, path):
    return (repo / path).read_bytes() if (repo / path).is_file() else None


def classify(repo, manifest):
    states = {}
    for path, row in manifest["rows"].items():
        value = current(repo, path)
        before, after = (B.read_blob(repo, row[key]) for key in ("before", "after"))
        states[path] = ("unchanged-by-plan" if before == after == value else
                        "before" if value == before else "after" if value == after else "later-edit")
    return states


def review_assumptions(repo, manifest):
    return {p: sha(current(repo, p) or b"") for p in manifest["rows"]}


def next_actions(manifest, blocked=None, stale_review=False):
    if blocked:
        return ["resolve-policy-or-history; recovery remains required"]
    if manifest["outcome"] in TERMINAL:
        return ["complete; ordinary preparation can be reconsidered"]
    if manifest["phase"] == "reviewed":
        return ["run-reviewed-" + manifest["kind"]]
    if manifest["phase"] == "publishing":
        return ["choose-finish", "choose-restore"]
    if manifest["phase"] == "recovering":
        return ["continue-saved-" + manifest["direction"]]
    if stale_review:
        return ["refresh-review"]
    return ["review-keep", "refresh-review"]


def guard(repo, manifest):
    scope = sorted(set(B.tracked_scope(repo)) | set(manifest["rows"]))
    findings = B.preflight(repo, scope)
    if findings:
        return {"reason": "changed-or-unsupported-effective-policy", "findings": findings}
    absent = unavailable(repo, manifest)
    if absent:
        return {"reason": "indispensable-history-unavailable", "objects": absent}
    return None


def inspect(repo):
    manifest = load(repo)
    blocked = guard(repo, manifest)
    stale_review = (manifest["phase"] == "review-later-edits" and
                    review_assumptions(repo, manifest) != manifest["review_assumptions"])
    return {"operation_id": manifest["operation_id"], "kind": manifest["kind"],
            "generation": manifest["generation"], "phase": manifest["phase"],
            "direction": manifest["direction"], "outcome": manifest["outcome"],
            "status": "recovery-required" if blocked or manifest["outcome"] is None else manifest["outcome"],
            "blocked": blocked, "next_actions": next_actions(manifest, blocked, stale_review),
            "review_stale": stale_review,
            "paths": None if blocked else classify(repo, manifest),
            "new_import_allowed": manifest["outcome"] in TERMINAL and not blocked,
            "onboarding_allowed": manifest["outcome"] in TERMINAL and not blocked}


def prepare(repo, kind):
    old = load(repo) if B.resolve(repo, OP) else None
    if old and old["outcome"] not in TERMINAL:
        return {"status": "recovery-required", "mutation": "none"}
    findings = B.preflight(repo, B.tracked_scope(repo))
    if findings:
        return {"refused": findings, "mutation": "none"}
    before = B.capture(repo)
    target = dict(before)
    if kind == "apply":
        target.update(INCOMING)
        source = B.snapshot(repo, INCOMING, NS + "source")
        undo_of = None
    else:
        if not old or old["kind"] != "apply" or old["outcome"] != "applied":
            return {"refused": "only latest completed apply is offered for Undo", "mutation": "none"}
        if guard(repo, old):
            return {"refused": "latest apply history/policy unavailable", "mutation": "none"}
        # Explicit synthetic review: keep the WHOLE B note, including its source
        # changes and later writing. Other paths reverse to apply preimages.
        target.update({p: B.read_blob(repo, old["rows"][p]["before"])
                       for p in old["rows"] if p != "B.md"})
        source = old["snapshots"]["source"]
        undo_of = B.resolve(repo, OP)
    pre = B.snapshot(repo, before, NS + "vault")
    result = B.snapshot(repo, target, NS + "planned", [pre])
    manifest = {"schema": "recovery-evidence-v1", "operation_id": kind + "-1", "kind": kind,
                "generation": old["generation"] if old else 0, "phase": "reviewed", "direction": kind,
                "outcome": None, "snapshots": {"pre": pre, "result": result, "source": source},
                "undo_of": undo_of, "reviewed_keep_whole_note": ["B.md"] if kind == "undo" else [],
                "rows": {p: {"before": B.blob(repo, before[p]), "after": B.blob(repo, target[p])}
                         for p in ("A.md", "B.md", "C.md")}, "protected": []}
    save(repo, manifest)
    return inspect(repo)


def terminal(manifest):
    if manifest["direction"] == "restore":
        return "restored"
    return "undone" if manifest["kind"] == "undo" else "applied"


def publish(repo, path, data):
    target = B.contained(repo / path, repo)
    temporary = target.with_name(target.name + ".recovery-publish")
    temporary.write_bytes(data)
    os.replace(temporary, target)


def publish_selected(repo, manifest, target_key, cut_after):
    states = classify(repo, manifest)
    protected = []
    count = 0
    for path, state in states.items():
        if state == "later-edit":
            protected.append(path)
            continue
        desired = B.read_blob(repo, manifest["rows"][path][target_key])
        if current(repo, path) != desired:
            publish(repo, path, desired)
            count += 1
            if cut_after and count == cut_after:
                # Deliberately stop AFTER a physical write, BEFORE progress or
                # completion journaling. Direction/generation already persisted.
                os._exit(73)
    manifest["protected"] = protected
    manifest["phase"] = "review-later-edits" if protected else "complete"
    manifest["outcome"] = None if protected else terminal(manifest)
    manifest["review_assumptions"] = review_assumptions(repo, manifest)
    save(repo, manifest)
    return inspect(repo)


def worker(repo, action, expected_generation=None, target=None, cut_after=0):
    manifest = load(repo)
    if action == "inspect":
        return inspect(repo)
    if action in ("new-import", "onboard"):
        return {"action": action, "status": "recovery-required" if manifest["outcome"] is None else "outside-bounded-scope",
                "mutation": "none", "incomplete_operation": manifest["operation_id"]}
    if expected_generation != manifest["generation"]:
        return {"status": "stale-generation", "expected": expected_generation,
                "current": manifest["generation"], "mutation": "none"}
    blocked = guard(repo, manifest)
    if blocked:
        return {"status": "recovery-required", "blocked": blocked, "mutation": "none"}
    if action == "run":
        if manifest["phase"] != "reviewed":
            return {"status": "illegal-transition", "mutation": "none"}
        if any(state not in ("before", "unchanged-by-plan") for state in classify(repo, manifest).values()):
            return {"status": "stale-review", "mutation": "none"}
        manifest["phase"] = "publishing"
        save(repo, manifest)
        return publish_selected(repo, manifest, "after", cut_after)
    if action == "recover":
        if manifest["phase"] in ("recovering", "review-later-edits") and manifest["direction"] != target:
            return {"status": "direction-conflict", "saved_direction": manifest["direction"], "mutation": "none"}
        if manifest["phase"] != "publishing" or target not in ("finish", "restore"):
            return {"status": "illegal-transition", "mutation": "none"}
        manifest["direction"] = target
        manifest["phase"] = "recovering"
        save(repo, manifest)
        return publish_selected(repo, manifest, "before" if target == "restore" else "after", cut_after)
    if action == "continue":
        if manifest["phase"] != "recovering":
            return {"status": "illegal-transition", "mutation": "none"}
        return publish_selected(repo, manifest, "before" if manifest["direction"] == "restore" else "after", cut_after)
    if action == "refresh-review":
        if manifest["phase"] != "review-later-edits":
            return {"status": "illegal-transition", "mutation": "none"}
        assumptions = review_assumptions(repo, manifest)
        changed = [p for p, value in assumptions.items() if value != manifest["review_assumptions"][p]]
        manifest["protected"] = sorted(set(manifest["protected"]) | set(changed))
        manifest["review_refresh_from_generation"] = manifest["generation"]
        manifest["review_refresh_changed_paths"] = changed
        manifest["review_assumptions"] = assumptions
        # Refresh records new assumptions only. It is not approval of the later
        # bytes, does not publish vault files, and leaves the operation blocked.
        save(repo, manifest)
        return inspect(repo)
    if action == "review-keep":
        if manifest["phase"] != "review-later-edits":
            return {"status": "illegal-transition", "mutation": "none"}
        if review_assumptions(repo, manifest) != manifest["review_assumptions"]:
            return {"status": "stale-review", "mutation": "none"}
        manifest["reviewed_keep_later"] = manifest["protected"]
        manifest["snapshots"]["accepted_current"] = B.snapshot(repo, B.capture(repo), NS + "vault",
                                                               [manifest["snapshots"]["result"]])
        manifest["phase"] = "complete"
        manifest["outcome"] = terminal(manifest)
        save(repo, manifest)
        return inspect(repo)
    raise ValueError(action)


def child(repo, action, *, target=None, cut=0, expected_exit=0, generation=None):
    command = [sys.executable, str(SCRIPT), "--repo", str(repo), "--worker", action]
    if action not in ("inspect", "new-import", "onboard"):
        command += ["--generation", str(load(repo)["generation"] if generation is None else generation)]
    if target:
        command += ["--target", target]
    if cut:
        command += ["--cut-after", str(cut)]
    result = subprocess.run(command, capture_output=True, timeout=60)
    if result.returncode != expected_exit:
        raise RuntimeError(f"Worker {action} exit {result.returncode}, expected {expected_exit}: {result.stderr.decode(errors='replace')}")
    return {"command": command, "exit": result.returncode,
            "result": json.loads(result.stdout) if result.stdout else None}


def observation(repo):
    manifest = load(repo)
    return {"files": B.inventory(repo), "affected_bytes_hex": {p: (current(repo, p) or b"").hex() for p in PRE},
            "manifest": manifest, "owned_refs": B.refs(repo), "reachable_required": reachable(repo, manifest),
            "user_git": B.user_state(repo), "fresh_status": child(repo, "inspect")}


def new_repo(run, name):
    repo = B.initialize(run, name)
    if {p: current(repo, p) for p in PRE} != PRE:
        raise RuntimeError("Frozen fixture differs from independently expected literal inputs")
    return repo


def literal_match(repo, values):
    return all(current(repo, p) == value for p, value in values.items())


def blocked_actions(repo):
    return [child(repo, action) for action in ("new-import", "onboard")]


def complete_apply(repo):
    prepare(repo, "apply")
    return child(repo, "run")


def run_direction_case(run, name, target):
    repo = new_repo(run, name)
    original_user = B.user_state(repo)
    prepare(repo, "apply")
    saved = observation(repo)
    first_stop = child(repo, "run", cut=2 if target == "restore" else 1, expected_exit=73)
    after_first_stop = observation(repo)
    if target == "finish":
        B.put(repo, "A.md", A_AFTER_APPLY_STOP)
    second_stop = child(repo, "recover", target=target, cut=1, expected_exit=73)
    after_second_stop = observation(repo)
    B.put(repo, "B.md", B_AFTER_RESTORE_STOP if target == "restore" else B_AFTER_FINISH_STOP)
    restarted = observation(repo)
    before_refusal = observation(repo)
    opposite = child(repo, "recover", target="finish" if target == "restore" else "restore")
    stale = child(repo, "continue", generation=load(repo)["generation"] - 1)
    prohibited = blocked_actions(repo)
    after_refusal = observation(repo)
    continued = child(repo, "continue")
    review = observation(repo)
    reviewed = child(repo, "review-keep")
    final = observation(repo)
    expected = ({"A.md": PRE["A.md"], "B.md": B_AFTER_RESTORE_STOP, "C.md": PRE["C.md"]}
                if target == "restore" else
                {"A.md": A_AFTER_APPLY_STOP, "B.md": B_AFTER_FINISH_STOP, "C.md": INCOMING["C.md"]})
    outcomes = {
        "first_process_really_partially_published": first_stop["exit"] == 73 and
            after_first_stop["affected_bytes_hex"]["A.md"] == INCOMING["A.md"].hex(),
        "second_process_really_partially_recovered": second_stop["exit"] == 73 and
            after_second_stop["affected_bytes_hex"]["A.md" if target == "restore" else "B.md"] ==
            (PRE["A.md"] if target == "restore" else INCOMING["B.md"]).hex(),
        "restart_retains_direction_generation": restarted["manifest"]["direction"] == target and
            restarted["manifest"]["generation"] == 3 and restarted["manifest"]["phase"] == "recovering",
        "truthful_next_action": restarted["fresh_status"]["result"]["next_actions"] == ["continue-saved-" + target],
        "opposite_direction_and_stale_generation_refused": opposite["result"]["status"] == "direction-conflict" and stale["result"]["status"] == "stale-generation",
        "refusals_and_new_work_make_no_mutation": before_refusal == after_refusal and
            all(c["result"]["status"] == "recovery-required" for c in prohibited),
        "later_edits_require_review_before_completion": review["manifest"]["phase"] == "review-later-edits" and review["manifest"]["outcome"] is None,
        "literal_expected_final_bytes": literal_match(repo, expected),
        "correct_terminal_outcome": final["manifest"]["outcome"] == ("restored" if target == "restore" else "applied"),
        "normal_user_Git_state_identical_all_stages": all(stage["user_git"] == original_user for stage in (saved, after_first_stop, after_second_stop, restarted, final)),
        "indispensable_history_reachable_all_stages": all(all(stage["reachable_required"].values()) for stage in (saved, after_first_stop, after_second_stop, restarted, final)),
    }
    return {"case": name, "saved": saved, "first_stop": first_stop, "after_first_stop": after_first_stop,
            "second_stop": second_stop, "after_second_stop": after_second_stop, "restart_after_later_edit": restarted,
            "opposite_direction_attempt": opposite, "stale_generation_attempt": stale, "new_work_attempts": prohibited,
            "continued": continued, "review": review, "explicit_review_keep": reviewed, "final": final,
            "outcomes": outcomes, "pass": all(outcomes.values())}


def run_undo_case(run):
    repo = new_repo(run, "interrupted-latest-undo")
    original_user = B.user_state(repo)
    applied = complete_apply(repo)
    B.put(repo, "B.md", B_BEFORE_UNDO)
    prepared = prepare(repo, "undo")
    before_undo = observation(repo)
    stop = child(repo, "run", cut=1, expected_exit=73)
    partial = observation(repo)
    B.put(repo, "A.md", A_AFTER_UNDO_STOP)
    restarted = observation(repo)
    prohibited = blocked_actions(repo)
    finish = child(repo, "recover", target="finish")
    awaiting_review = observation(repo)
    keep = child(repo, "review-keep")
    final = observation(repo)
    outcomes = {
        "Undo_prepared_from_latest_completed_apply": prepared["kind"] == "undo" and before_undo["manifest"]["undo_of"] is not None,
        "whole_note_B_retained_with_source_and_later_writing": current(repo, "B.md") == B_BEFORE_UNDO,
        "real_partial_Undo_reverses_A_before_stop": stop["exit"] == 73 and partial["affected_bytes_hex"]["A.md"] == PRE["A.md"].hex()
            and partial["affected_bytes_hex"]["C.md"] == INCOMING["C.md"].hex(),
        "restart_has_Undo_direction_generation": restarted["manifest"]["kind"] == "undo" and
            restarted["manifest"]["direction"] == "undo" and restarted["manifest"]["generation"] == 5,
        "restart_truthful_finish_restore_choices": restarted["fresh_status"]["result"]["next_actions"] == ["choose-finish", "choose-restore"],
        "import_and_onboarding_blocked": all(c["result"]["status"] == "recovery-required" for c in prohibited),
        "later_A_preserved_and_requires_review": awaiting_review["affected_bytes_hex"]["A.md"] == A_AFTER_UNDO_STOP.hex()
            and awaiting_review["manifest"]["protected"] == ["A.md"] and awaiting_review["manifest"]["outcome"] is None,
        "literal_expected_reviewed_Undo_result": literal_match(repo, {"A.md": A_AFTER_UNDO_STOP, "B.md": B_BEFORE_UNDO, "C.md": PRE["C.md"]}),
        "completed_Undo_reports_undone": final["manifest"]["outcome"] == "undone",
        "normal_user_Git_state_identical": all(stage["user_git"] == original_user for stage in (before_undo, partial, restarted, final)),
        "all_indispensable_versions_reachable": all(all(stage["reachable_required"].values()) for stage in (before_undo, partial, restarted, final)),
    }
    return {"applied": applied, "before_Undo": before_undo, "partial_Undo": stop, "after_partial": partial,
            "restart": restarted, "new_work_attempts": prohibited, "finish": finish, "review_required": awaiting_review,
            "explicit_review_keep": keep, "final": final, "outcomes": outcomes, "pass": all(outcomes.values())}


def run_blocked_case(run, kind):
    repo = new_repo(run, "blocked-" + kind)
    prepare(repo, "apply")
    child(repo, "run", cut=1, expected_exit=73)
    missing_oid = None
    if kind == "missing-preimage":
        missing_oid = load(repo)["rows"]["A.md"]["before"]
        # Deliberate corruption of a unique converter-only loose blob in this
        # freshly generated repository. No recursive deletion or user vault.
        object_path = B.contained(repo / ".git/objects" / missing_oid[:2] / missing_oid[2:], repo / ".git/objects")
        # Git creates read-only loose objects on Windows. Alter this one owned
        # fixture object's bit only, so the deliberate loss can be exercised.
        object_path.chmod(object_path.stat().st_mode | stat.S_IWRITE)
        object_path.unlink()
    else:
        external = run / "changed-effective-attributes"
        external.write_bytes(b"A.md filter=encrypted\n")
        B.git(repo, "config", "core.attributesFile", str(external))
        (repo / ".git/sentinel.sh").write_text("#!/bin/sh\necho ran > .git/SENTINEL-RAN\ncat\n")
        B.git(repo, "config", "filter.encrypted.clean", "sh .git/sentinel.sh")
    before = observation(repo)
    objects_before = sorted(str(p.relative_to(repo / ".git/objects")) for p in (repo / ".git/objects").rglob("*") if p.is_file())
    finish = child(repo, "recover", target="finish")
    restore = child(repo, "recover", target="restore")
    prohibited = blocked_actions(repo)
    repeated_restart = child(repo, "inspect")
    after = observation(repo)
    objects_after = sorted(str(p.relative_to(repo / ".git/objects")) for p in (repo / ".git/objects").rglob("*") if p.is_file())
    reason = "indispensable-history-unavailable" if missing_oid else "changed-or-unsupported-effective-policy"
    outcomes = {
        "both_recovery_directions_refused_truthfully": all(c["result"]["status"] == "recovery-required" and c["result"]["blocked"]["reason"] == reason for c in (finish, restore)),
        "recovery_required_persists_across_restart": repeated_restart["result"]["status"] == "recovery-required" and after["manifest"]["outcome"] is None,
        "import_onboarding_cannot_bypass_incomplete_operation": all(c["result"]["status"] == "recovery-required" for c in prohibited),
        "no_file_ref_index_HEAD_userref_config_status_mutation": before == after,
        "no_new_objects": objects_before == objects_after,
        "sentinel_unexecuted": not (repo / ".git/SENTINEL-RAN").exists(),
        "expected_unavailable_preimage_or_policy_detected": missing_oid in repeated_restart["result"]["blocked"].get("objects", []) if missing_oid else
            any("C06" in finding for finding in repeated_restart["result"]["blocked"].get("findings", [])),
    }
    return {"injected_condition": kind, "missing_converter_only_blob": missing_oid, "before_attempts": before,
            "finish_attempt": finish, "restore_attempt": restore, "new_work_attempts": prohibited,
            "repeat_fresh_restart": repeated_restart, "after_attempts": after,
            "outcomes": outcomes, "pass": all(outcomes.values())}


def expected_plan():
    return {"authored_before_any_repository_mutation": True,
            "literal_initial_affected_bytes_hex": {p: b.hex() for p, b in PRE.items()},
            "literal_final_affected_bytes_hex": {
                "interrupted_Undo_finish": {"A.md": A_AFTER_UNDO_STOP.hex(), "B.md": B_BEFORE_UNDO.hex(), "C.md": PRE["C.md"].hex()},
                "interrupted_finish": {"A.md": A_AFTER_APPLY_STOP.hex(), "B.md": B_AFTER_FINISH_STOP.hex(), "C.md": INCOMING["C.md"].hex()},
                "interrupted_restore": {"A.md": PRE["A.md"].hex(), "B.md": B_AFTER_RESTORE_STOP.hex(), "C.md": PRE["C.md"].hex()}},
            "expected_transitions": {
                "apply": "reviewed generation 1 -> publishing generation 2 -> complete applied generation 3",
                "Undo": "after applied generation 3: reviewed Undo generation 4 -> publishing Undo generation 5 -> recovering finish generation 6 -> later-edit review generation 7 -> undone generation 8",
                "finish_or_restore_recovery": "apply publishing generation 2 -> recovering saved direction generation 3 -> restart offers only continue-saved-direction -> later-edit review generation 4 -> applied/restored generation 5"},
            "before_each_restart": {"partial_Undo": ["choose-finish", "choose-restore"],
                                    "partial_finish": ["continue-saved-finish"], "partial_restore": ["continue-saved-restore"],
                                    "unavailable_preimage_or_changed_policy": ["resolve-policy-or-history; recovery remains required"]},
            "all_incomplete_states": "new import and onboarding blocked, later bytes preserved, user Git state exact",
            "restore_terminal": "restored; never applied; explicit keep later note may retain source changes",
            "missing_preimage": "no mutation; report unavailable indispensable history; no onboarding escape",
            "changed_policy": "C06 refusal before any sentinel execution or mutation; incomplete journal retained"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, help="Worker only: an existing owned synthetic repository")
    parser.add_argument("--worker", choices=["inspect", "run", "recover", "continue", "refresh-review", "review-keep", "new-import", "onboard"])
    parser.add_argument("--generation", type=int, help="Mutating worker's reviewed manifest generation")
    parser.add_argument("--target", choices=["finish", "restore"], help="Choose recovery direction once")
    parser.add_argument("--cut-after", type=int, default=0, help="Exit 73 after N actual replacements, before progress journaling")
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(B.owned_repo(args.repo), args.worker, args.generation, args.target, args.cut_after)))
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    run = B.contained(OUTPUT / (time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]), OUTPUT)
    run.mkdir()
    (run / "PROTOTYPE-OWNED.json").write_bytes(packed({"purpose": "#249 synthetic recovery direction evidence", "root": str(run)}))
    (run / "empty-global-config").write_bytes(b"")
    (run / "expected-before-run.json").write_bytes(packed(expected_plan()))
    start = time.perf_counter()
    result = {"ticket": "https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/249", "run": str(run),
              "frozen_commit": FROZEN, "frozen_path": FROZEN_PATH, "frozen_source_sha256": FROZEN_SHA,
              "source_sha256": sha(SCRIPT.read_bytes()), "python": sys.executable, "git_executable": shutil.which("git"),
              "git_version": subprocess.run(["git", "--version"], capture_output=True, text=True).stdout.strip(),
              "expected_before_run": expected_plan(), "interrupted_Undo": run_undo_case(run),
              "interrupted_finish": run_direction_case(run, "interrupted-finish-recovery", "finish"),
              "interrupted_restore": run_direction_case(run, "interrupted-restore-recovery", "restore"),
              "missing_preimage": run_blocked_case(run, "missing-preimage"),
              "changed_policy": run_blocked_case(run, "changed-policy")}
    result["elapsed_seconds"] = round(time.perf_counter() - start, 3)
    names = ("interrupted_Undo", "interrupted_finish", "interrupted_restore", "missing_preimage", "changed_policy")
    result["pass"] = all(result[name]["pass"] for name in names)
    result["limits"] = ["Single controlled Git for Windows executable; ordinary newly generated repositories only",
                        "No power-loss/fsync, production I/O failure, concurrency/locking or policy-change race evidence",
                        "Whole-note keep decisions are scripted reviewed choices, not new human decisions",
                        "Missing blob is deliberate converter-only corruption; no restoration/backup or alternate-store feature",
                        "No native UI, structured reconciliation, real vault/archive, broad regressions or production implementation"]
    (run / "results.json").write_bytes(packed(result))
    report = ["# #249 recovery direction and interrupted Undo observations", "", f"Run: `{run}`", "",
              f"Frozen input: `{FROZEN}`, source SHA-256 `{FROZEN_SHA}`.", "",
              f"Experiment SHA-256: `{result['source_sha256']}`.", "",
              f"{result['git_version']}; Python `{sys.executable}`; elapsed {result['elapsed_seconds']} s.", "",
              "Bounded independently stated observations: " + ("PASS" if result["pass"] else "FAIL"), "",
              "Literal expected bytes and next actions were retained in expected-before-run.json before any repository initialization.", ""]
    for name in names:
        report += ["## " + name, ""] + [f"- {key}: {value}" for key, value in result[name]["outcomes"].items()] + [""]
    report += ["## Criterion evidence", "", "| #249 criterion | Evidence |", "| --- | --- |",
               "| Direction/generation and reachable versions | All normal stages retain explicit kind/direction/generation and graph-reachable before/result/source versions; missing fixture reports actual loss |",
               "| Real partial Undo and partial finish/restore restart | Child exits 73 after actual replacement, fresh inspection and continuation; later edits preserved for review; restore ends restored |",
               "| New work blocked; changed policy and missing preimage | Both import/onboard blocked while incomplete; C06 refusal and actual missing blob preserve incomplete metadata and bytes |",
               "| File/Git evidence | Full inventories, literal affected bytes, manifests, refs/reachability and normal index/HEAD/branches/tags/config recorded in results.json |",
               "| Reproducible public-contract evidence | Commands, executable identity, provenance, limits and recommendations in source README; independent review required |", "",
               "## Remaining limits", ""] + ["- " + value for value in result["limits"]]
    (run / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"run": str(run), "pass": result["pass"], "seconds": result["elapsed_seconds"],
                      "source_sha256": result["source_sha256"], "report": str(run / "REPORT.md")}, indent=2))
    if not result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
