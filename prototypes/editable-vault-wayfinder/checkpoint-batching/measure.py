"""One bounded raw-byte batching experiment for #253, never a production optimizer."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import uuid

PROJECT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = PROJECT / "tmp/merge-wayfinding/followups/batching"
BASELINE = "823c21445646f09059ac8e9bf8dc15cdbbbaca86"
FROZEN = "273233fb4020ceb156ed6b3ab33785adcedfdda9"
BOUND = 300


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf8", newline="\n")


def extract(commit, path, target):
    raw = subprocess.run(["git", "show", commit + ":" + path], cwd=PROJECT,
                         check=True, capture_output=True, timeout=30).stdout
    target.write_bytes(raw)
    spec = importlib.util.spec_from_file_location(target.stem.replace("-", "_"), target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, sha(raw)


def peak_working_set():
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ["PeakWorkingSetSize", "WorkingSetSize",
            "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage"]]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    process = ctypes.windll.kernel32.GetCurrentProcess()
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    if not ctypes.windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
        raise OSError("Cannot query experiment memory")
    return counters.PeakWorkingSetSize


def main():
    started = time.perf_counter()
    run = OUTPUT / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    save(run / "PROTOTYPE-OWNED.json", {"issue": 253, "baseline": BASELINE})
    reference = json.loads((HERE / "baseline-reference.json").read_text())
    (run / "author-measure-as-run.py").write_bytes(Path(__file__).read_bytes())
    (run / "baseline-reference.json").write_bytes((HERE / "baseline-reference.json").read_bytes())
    scale, scale_hash = extract(BASELINE, "prototypes/editable-vault-wayfinder/checkpoint-scale/measure.py", run / "frozen-scale.py")
    git_module, git_hash = extract(FROZEN, "prototypes/editable-vault-wayfinder/git/experiment.py", run / "frozen-git.py")
    if scale_hash != "abefbea9bec6e277f979fa4f9d1dff7875f24932e0b6554a06b3ca7cf0861c9b":
        raise ValueError("Frozen fixture/allocation input differs")
    if git_hash != reference["frozen_git_source_sha256"]:
        raise ValueError("Frozen Git input differs")
    git_module.OUTPUT = OUTPUT
    source, vault, changed, result = scale.fixture()
    contents = dict(zip(["source_initial", "vault_initial", "source_changed", "vault_changed"], [source, vault, changed, result]))
    expected = {"inputs": {k: scale.summary(v) for k, v in contents.items()},
                "commits": {k: v["commit"] for k, v in reference["measurements"].items()},
                "converter_refs": reference["converter_refs"], "objects": {"blob": 1753, "tree": 22, "commit": 6},
                "all_objects": 1781, "ref_reachable": 1780, "index_only_staged": 1,
                "git_calls_per_capture": 7, "changed_binary_bytes": 17329582,
                "preserved_user_state": True, "raw_working_bytes": True,
                "same_all_object_ids_as_baseline": True, "wall_bound_seconds": BOUND,
                "resource_estimates": {"disk_bytes_upper_estimate": 3 * 1024**3, "peak_memory_upper_estimate": 2 * 1024**3}}
    if any(expected["inputs"][k] != reference["measurements"][k]["input"] for k in contents):
        raise ValueError("Fixture inventories differ from accepted baseline")
    save(run / "expected-before-run.json", expected)
    print("RUN " + str(run), flush=True)
    print("Expected 1750 vault files /380117374 bytes; four exact baseline commits; seven Git calls/capture", flush=True)
    calls = []
    original_git = git_module.git
    def budget():
        if time.perf_counter() - started > BOUND:
            raise TimeoutError("Declared 300-second experiment bound reached")
    def git(repo, *args, **kwargs):
        budget()
        t = time.perf_counter()
        try:
            return original_git(repo, *args, **kwargs)
        finally:
            calls.append({"command": list(args), "seconds": time.perf_counter() - t})
    git_module.git = git
    measurements = {}
    observations = {"baseline": BASELINE, "frozen_git": FROZEN,
                    "source_sha256": sha(Path(__file__).read_bytes()), "baseline_reference_sha256": sha((HERE / "baseline-reference.json").read_bytes()),
                    "frozen_git_sha256": git_hash, "frozen_scale_lf_sha256": scale_hash,
                    "python": sys.executable, "python_version": sys.version, "platform": platform.platform(),
                    "measurements": measurements, "expected": expected}
    try:
        repo = git_module.initialize(run, "vault", seeded=False)
        git_module.put(repo, "Imports/notes/0000.md", b"Independent user base\n")
        git(repo, "add", "Imports/notes/0000.md")
        git(repo, "commit", "-m", "Independent synthetic user history")
        git(repo, "branch", "independent-branch")
        git(repo, "tag", "independent-tag")
        git(repo, "remote", "add", "origin", "https://example.invalid/never-contacted.git")
        git_module.put(repo, "Imports/notes/0000.md", b"Staged user draft\n")
        git(repo, "add", "Imports/notes/0000.md")
        for p, b in vault.items():
            budget()
            git_module.put(repo, p, b)
        before = git_module.user_state(repo)
        observations["initial_user_state"] = before
        observations["git_version"] = git(repo, "--version").decode().strip()
        observations["initial_storage"] = scale.storage(repo, git)
        ids = {}
        for label, content in contents.items():
            budget()
            t = time.perf_counter()
            stage = run / "capture-input" / label
            paths = []
            for p, b in sorted(content.items()):
                budget()
                target = stage / p
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b)
                paths.append(target)
            staging_seconds = time.perf_counter() - t
            git_t = time.perf_counter()
            first_call = len(calls)
            index = repo / ".git" / ("prototype-index-" + uuid.uuid4().hex)
            git(repo, "read-tree", "--empty", index=index)
            # Generated ASCII paths are bounded by this run and contain no quotes/newlines.
            names = ("\n".join(p.resolve().as_posix() for p in paths) + "\n").encode()
            oids = git(repo, "hash-object", "-w", "--no-filters", "--stdin-paths", data=names).decode().splitlines()
            if len(oids) != len(content):
                raise ValueError("Batch returned an unexpected object count")
            entries = b"".join(b"100644 " + oid.encode() + b"\t" + p.encode() + b"\0"
                               for (p, _b), oid in zip(sorted(content.items()), oids))
            git(repo, "update-index", "-z", "--index-info", data=entries, index=index)
            tree = git(repo, "write-tree", index=index).decode().strip()
            ref = git_module.NS + ("source" if label.startswith("source") else "vault" if label == "vault_initial" else "accepted")
            old = git_module.resolve(repo, ref)
            parents = list(dict.fromkeys(([old] if old else []) + ([ids["vault_initial"]] if label == "vault_changed" else [])))
            args = ["commit-tree", tree]
            for parent in parents:
                args += ["-p", parent]
            oid = git(repo, *args, data=b"Synthetic prototype checkpoint\n").decode().strip()
            git(repo, "update-ref", ref, oid, old or "0" * len(oid))
            index.unlink()
            ids[label] = oid
            capture_seconds = time.perf_counter() - t
            git_seconds = time.perf_counter() - git_t
            measurements[label] = {"materialization_seconds": staging_seconds, "git_capture_seconds": git_seconds,
                                   "inclusive_capture_seconds": capture_seconds, "git_processes": len(calls) - first_call,
                                   "commit": oid, "storage": scale.storage(repo, git)}
            save(run / "partial-results.json", observations)
            print(f"{label}: {capture_seconds:.3f}s inclusive; {git_seconds:.3f}s Git; {len(oids)} payloads", flush=True)
        manifest = {"version": 1, "status": "applied", "pre": ids["vault_initial"], "result": ids["vault_changed"],
                    "source": ids["source_changed"], "format": 1, "policy": "controlled ordinary/raw bytes",
                    "review": "synthetic approved whole change", "rows": {}}
        git_module.persist(repo, manifest)
        for p in ["Imports/notes/0001.md", "Imports/attachments/0664.bin"]:
            git_module.put(repo, p, result[p])
        final_state = git_module.user_state(repo)
        object_rows = git(repo, "cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype) %(objectsize)").decode().splitlines()
        objects = {row.split()[0] for row in object_rows}
        counts = {kind: sum(row.split()[1] == kind for row in object_rows) for kind in ["blob", "tree", "commit"]}
        reachable = {row.split()[0] for row in git(repo, "rev-list", "--objects", "--all").decode().splitlines()}
        staged = {row.split()[1] for row in git(repo, "ls-files", "--stage").decode().splitlines()}
        tree_checks = {}
        for label, content in contents.items():
            rows = git(repo, "ls-tree", "-r", "-z", ids[label]).split(b"\0")
            actual = {row.split(b"\t", 1)[1].decode(): row.split(b"\t", 1)[0].decode().split()[2] for row in rows if row}
            wanted = {p: hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest() for p, b in content.items()}
            tree_checks[label] = actual == wanted
        # Independently validate every retained loose object's zlib/header/identity.
        import zlib
        raw_objects_ok = True
        for path in (repo / ".git/objects").glob("[0-9a-f][0-9a-f]/*"):
            budget()
            decoded = zlib.decompress(path.read_bytes())
            header, data = decoded.split(b"\0", 1)
            raw_objects_ok &= int(header.split()[1]) == len(data) and hashlib.sha1(decoded).hexdigest() == path.parent.name + path.name
        working = git_module.files(repo)
        converter_refs = git_module.refs(repo)
        checks = {"literal_object_counts": counts == expected["objects"], "all_object_ids_identical_to_accepted_baseline": objects == set(reference["all_object_ids"]),
                  "all_four_commit_ids_match_baseline": ids == expected["commits"], "converter_refs_identical_to_baseline": converter_refs == expected["converter_refs"],
                  "all_four_path_blob_inventories_match_literal_fixture": all(tree_checks.values()), "all_loose_objects_raw_identity_valid": raw_objects_ok,
                  "all_required_history_ref_reachable": len(reachable) == 1780 and all(oid in reachable for oid in ids.values()),
                  "only_independent_staged_blob_index_only": objects - reachable == staged and len(staged) == 1,
                  "user_index_HEAD_refs_config_exactly_preserved": before == final_state, "working_bytes_exact_approved_result": working == result,
                  "seven_git_calls_each_capture": all(m["git_processes"] == 7 for m in measurements.values())}
        all_files = [p for p in run.rglob("*") if p.is_file()]
        observations.update({"checks": checks, "tree_checks": tree_checks, "final_user_state": final_state,
                             "converter_refs": converter_refs, "object_counts": counts, "all_object_count": len(objects), "ref_reachable_objects": len(reachable),
                             "final_storage": scale.storage(repo, git), "final_working_inventory": scale.summary(working),
                             "retained_run_files_logical_bytes": sum(p.stat().st_size for p in all_files),
                             "retained_run_files_allocated_bytes": sum(scale.allocation(p) for p in all_files),
                             "peak_python_working_set_bytes": peak_working_set()})
        observations["verdict"] = "PASS" if all(checks.values()) else "FAIL"
    except Exception as exc:
        observations["verdict"] = "INCOMPLETE"
        observations["exception"] = repr(exc)
    observations["total_elapsed_seconds"] = time.perf_counter() - started
    save(run / "commands.json", calls)
    save(run / "results.json", observations)
    print(observations["verdict"] + " " + str(run / "results.json"), flush=True)
    return 0 if observations["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
