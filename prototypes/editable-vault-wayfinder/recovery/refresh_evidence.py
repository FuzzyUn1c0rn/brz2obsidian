"""Focused #249 repair evidence: stale recovery review -> refresh -> explicit keep.

Creates only new owned synthetic repositories. Run with the project .venv Python.
The unchanged 47-case-observation run is retained as prior evidence; this command
executes only the affected shared review transition in finish/restore/Undo paths.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid


sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("recovery_candidate", HERE / "experiment.py")
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)

FIRST_C = b"id: C.md\nINDEPENDENT writing after recovery stop\r\n"
LATEST_C = b"id: C.md\nINDEPENDENT writing after recovery stop\r\nSECOND edit during recovery review\r\n"


def expected():
    return {"authored_before_repository_creation": True,
            "first_later_C_hex": FIRST_C.hex(), "second_later_C_hex": LATEST_C.hex(),
            "final_literal_bytes_hex": {
                "finish": {"A.md": b"id: A.md\nSOURCE A accepted\n".hex(), "B.md": b"id: B.md\nSOURCE B accepted\n".hex(), "C.md": LATEST_C.hex()},
                "restore": {"A.md": b"id: A.md\nunstaged author draft\n".hex(), "B.md": b"id: B.md\nbase\n".hex(), "C.md": LATEST_C.hex()},
                "undo-finish": {"A.md": b"id: A.md\nunstaged author draft\n".hex(), "B.md": b"id: B.md\nSOURCE B accepted\nAUTHOR before Undo\n".hex(), "C.md": LATEST_C.hex()}},
            "transitions": ["additional edit makes keep stale; no mutation", "inspect offers executable refresh-review",
                            "refresh records assumptions and generation +1; no publication/approval",
                            "old generation keep is refused; new work still blocked",
                            "separate fresh-generation keep completes; latest writing remains exact"],
            "outcomes": {"finish": "applied", "restore": "restored", "undo-finish": "undone"},
            "normal_user_Git": "exact index/HEAD/staged selection/branches/tags/config unchanged",
            "history": "saved direction and kind unchanged; all indispensable pre/result/source versions reachable"}


def scenario(run, name):
    repo = E.new_repo(run, "refresh-" + name)
    user_original = E.B.user_state(repo)
    if name == "undo-finish":
        E.complete_apply(repo)
        E.B.put(repo, "B.md", E.B_BEFORE_UNDO)
        E.prepare(repo, "undo")
        stopped = E.child(repo, "run", cut=1, expected_exit=73)
    else:
        E.prepare(repo, "apply")
        stopped = E.child(repo, "run", cut=2, expected_exit=73)
    E.B.put(repo, "C.md", FIRST_C)
    selected = E.child(repo, "recover", target="restore" if name == "restore" else "finish")
    review = E.observation(repo)
    E.B.put(repo, "C.md", LATEST_C)
    before_stale = E.observation(repo)
    stale = E.child(repo, "review-keep")
    after_stale = E.observation(repo)
    old_generation = E.load(repo)["generation"]
    refreshed = E.child(repo, "refresh-review")
    after_refresh = E.observation(repo)
    stale_generation = E.child(repo, "review-keep", generation=old_generation)
    new_work = E.blocked_actions(repo)
    after_refusals = E.observation(repo)
    kept = E.child(repo, "review-keep")
    final = E.observation(repo)
    literal = {p: bytes.fromhex(value) for p, value in expected()["final_literal_bytes_hex"][name].items()}
    stable_refs_before = [r for r in before_stale["owned_refs"] if not r.startswith(E.OP + " ")]
    stable_refs_after = [r for r in after_refresh["owned_refs"] if not r.startswith(E.OP + " ")]
    stages = (review, before_stale, after_stale, after_refresh, after_refusals, final)
    outcomes = {
        "real_process_partial_publication": stopped["exit"] == 73,
        "later_C_requires_review": review["manifest"]["phase"] == "review-later-edits" and review["manifest"]["protected"] == ["C.md"],
        "additional_edit_makes_keep_stale_without_mutation": stale["result"]["status"] == "stale-review" and before_stale == after_stale,
        "fresh_inspection_offers_executable_refresh": after_stale["fresh_status"]["result"]["next_actions"] == ["refresh-review"],
        "refresh_publishes_no_vault_files_or_user_Git_changes": after_refresh["files"] == before_stale["files"] and after_refresh["user_git"] == before_stale["user_git"],
        "refresh_changes_only_operation_ref": stable_refs_before == stable_refs_after and before_stale["owned_refs"] != after_refresh["owned_refs"],
        "refresh_advances_generation_and_captures_current_C": after_refresh["manifest"]["generation"] == old_generation + 1 and
            after_refresh["manifest"]["review_assumptions"]["C.md"] == E.sha(LATEST_C) and
            after_refresh["manifest"]["review_refresh_changed_paths"] == ["C.md"],
        "refresh_retains_incomplete_state_without_approval": after_refresh["manifest"]["outcome"] is None and
            after_refresh["manifest"]["phase"] == "review-later-edits" and
            after_refresh["fresh_status"]["result"]["next_actions"] == ["review-keep", "refresh-review"],
        "old_generation_cannot_approve_refreshed_review": stale_generation["result"]["status"] == "stale-generation" and after_refresh == after_refusals,
        "import_and_onboarding_remain_blocked_during_fresh_review": all(c["result"]["status"] == "recovery-required" for c in new_work),
        "separate_explicit_keep_completes_expected_direction": kept["result"]["outcome"] == expected()["outcomes"][name] and
            final["manifest"]["generation"] == old_generation + 2,
        "literal_expected_latest_bytes_preserved": E.literal_match(repo, literal),
        "kind_direction_and_required_versions_retained": all(stage["manifest"]["kind"] == review["manifest"]["kind"] and
            stage["manifest"]["direction"] == review["manifest"]["direction"] and all(stage["reachable_required"].values()) for stage in stages),
        "normal_user_Git_state_exact_throughout": all(stage["user_git"] == user_original for stage in stages),
        "completed_recovery_can_continue_to_ordinary_preparation": final["fresh_status"]["result"]["new_import_allowed"] and
            final["fresh_status"]["result"]["onboarding_allowed"],
    }
    return {"case": name, "partial_publication": stopped, "recover_to_review": selected, "first_review": review,
            "before_stale_keep": before_stale, "stale_keep": stale, "after_stale_keep": after_stale,
            "refresh": refreshed, "after_refresh": after_refresh, "old_generation_keep": stale_generation,
            "blocked_new_work": new_work, "after_refusals": after_refusals, "explicit_current_keep": kept,
            "final": final, "outcomes": outcomes, "pass": all(outcomes.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    E.OUTPUT.mkdir(parents=True, exist_ok=True)
    run = E.B.contained(E.OUTPUT / ("refresh-repair-" + time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]), E.OUTPUT)
    run.mkdir()
    (run / "PROTOTYPE-OWNED.json").write_bytes(E.packed({"purpose": "#249 focused stale review repair", "root": str(run)}))
    (run / "empty-global-config").write_bytes(b"")
    (run / "expected-before-run.json").write_bytes(E.packed(expected()))
    start = time.perf_counter()
    result = {"ticket": "https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/249", "run": str(run),
              "frozen_commit": E.FROZEN, "frozen_source_sha256": E.FROZEN_SHA,
              "candidate_source_sha256": E.sha((HERE / "experiment.py").read_bytes()),
              "focused_driver_sha256": E.sha(Path(__file__).read_bytes()),
              "prior_unaffected_evidence": "tmp/merge-wayfinding/followups/recovery/20261021-121901-712f3a00/",
              "python": sys.executable, "python_version": sys.version,
              "git_version": subprocess.run(["git", "--version"], capture_output=True, text=True).stdout.strip(),
              "expected_before_run": expected(), "cases": [scenario(run, name) for name in ("finish", "restore", "undo-finish")]}
    result["elapsed_seconds"] = round(time.perf_counter() - start, 3)
    result["pass"] = all(case["pass"] for case in result["cases"])
    result["scope"] = "Focused real-process re-review transition and shared finish/restore/Undo symmetry; no blanket repetition of prior 159-second suite"
    (run / "results.json").write_bytes(E.packed(result))
    report = ["# #249 focused stale-review repair observations", "", f"Run: `{run}`", "",
              f"Candidate SHA-256: `{result['candidate_source_sha256']}`.",
              f"Focused driver SHA-256: `{result['focused_driver_sha256']}`.",
              f"Frozen plumbing `{E.FROZEN}`, SHA-256 `{E.FROZEN_SHA}`.", "",
              f"{result['git_version']}; Python `{sys.executable}`; elapsed {result['elapsed_seconds']} s.", "",
              "Focused outcomes: " + ("PASS" if result["pass"] else "FAIL"), "",
              "Expected literals and next actions were recorded before repository creation. Refresh is not approval or publication.",
              "Explicit fresh-generation keep completes the already eligible recovery; ordinary preparation can then be reconsidered.", ""]
    for case in result["cases"]:
        report += ["## " + case["case"], ""] + [f"- {key}: {value}" for key, value in case["outcomes"].items()] + [""]
    report += ["## Evidence reuse and limits", "", result["scope"], "",
               "Prior missing-preimage/effective-policy and original interruption observations remain bound to their recorded earlier source; independent review must assess reuse with this additive shared-review repair.",
               "No production tests, power-loss/concurrency/complete failure coverage, source restoration, native or scale claims are added.", ""]
    (run / "REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps({"run": str(run), "pass": result["pass"], "seconds": result["elapsed_seconds"],
                      "candidate_source_sha256": result["candidate_source_sha256"],
                      "focused_driver_sha256": result["focused_driver_sha256"]}, indent=2))
    if not result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
