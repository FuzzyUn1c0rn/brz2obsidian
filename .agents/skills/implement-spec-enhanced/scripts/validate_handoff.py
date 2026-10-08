"""Validate a handoff transition without mutating records or Git state."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


class InvalidHandoff(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidHandoff(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def strings(value, label, *, nonempty=False):
    require(isinstance(value, list), f"{label} must be an array")
    require(all(text(item) for item in value), f"{label} must contain strings")
    require(not nonempty or bool(value), f"{label} must not be empty")


def commit(value, label):
    require(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value),
        f"{label} must be a full lowercase Git object ID",
    )


def relative_path(value, label):
    require(text(value), f"{label} must be a path")
    path = Path(value)
    require(
        not path.is_absolute() and not path.drive and ".." not in path.parts,
        f"{label} must be repository-relative without parent traversal",
    )


def evidence(value, bundle, label):
    strings(value, label, nonempty=True)
    for item in value:
        require((bundle / item).is_file(), f"{label}: missing evidence file {item}")


def checks(value, bundle):
    require(isinstance(value, list), "checks must be an array")
    for check in value:
        require(isinstance(check, dict), "each check must be an object")
        require(text(check.get("name")), "check.name is required")
        require(text(check.get("method")), "check.method is required")
        status = check.get("status")
        require(
            status in ("passed", "failed", "unavailable", "reused"),
            "invalid check.status",
        )
        require("exit_code" in check, "check.exit_code is required")
        code = check["exit_code"]
        require(code is None or type(code) is int, "exit_code must be integer or null")
        if status == "passed":
            require(code is None or code == 0, "passed check has nonzero exit_code")
        elif status == "failed":
            require(code is None or code != 0, "failed check has zero exit_code")
        else:
            require(code is None, "unavailable/reused checks require null exit_code")
        if status != "passed":
            require(text(check.get("reason")), f"{status} check requires reason")
        if status == "reused":
            commit(check.get("source_commit"), "check.source_commit")
        evidence(check.get("evidence"), bundle, "check.evidence")


def load(bundle, kind, records=None):
    path = bundle / f"{kind}.json"
    record = (
        records[kind]
        if records is not None and kind in records
        else json.loads(path.read_text(encoding="utf-8"))
    )
    require(isinstance(record, dict), f"{kind} must be an object")
    require(type(record.get("schema_version")) is int, "schema_version must be integer")
    require(record["schema_version"] == 1, "unsupported schema_version")
    require(record.get("kind") == kind, f"expected kind {kind}")
    require(text(record.get("actor")), f"{kind}.actor is required")
    relative_path(record.get("ticket"), f"{kind}.ticket")
    commit(record.get("candidate_commit"), f"{kind}.candidate_commit")
    strings(record.get("limits"), f"{kind}.limits")
    checks(record.get("checks"), bundle)
    return record


def same_candidate(candidate, record):
    for key in ("ticket", "candidate_commit"):
        require(
            record[key] == candidate[key],
            f"{record['kind']}.{key} mismatches candidate",
        )


def all_passed(record):
    return all(check["status"] in ("passed", "reused") for check in record["checks"])


def git(checkout, *args):
    result = subprocess.run(
        ["git", "-C", str(checkout), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    require(result.returncode == 0, f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def ancestor(checkout, earlier, later):
    git(checkout, "merge-base", "--is-ancestor", earlier, later)


def validate(bundle, stage, checkout, records=None):
    candidate = load(bundle, "candidate", records)
    relative_path(candidate.get("spec"), "candidate.spec")
    for key in ("ticket", "spec"):
        require((checkout / candidate[key]).is_file(), f"missing {key} in checkout")
    commit(candidate.get("base_commit"), "candidate.base_commit")
    require(
        text(candidate.get("worktree")) and Path(candidate["worktree"]).is_absolute(),
        "candidate.worktree must be absolute",
    )
    strings(candidate.get("owned_files"), "candidate.owned_files", nonempty=True)
    for path in candidate["owned_files"]:
        relative_path(path, "candidate.owned_files entry")
    strings(candidate.get("criteria"), "candidate.criteria", nonempty=True)
    require(
        len(set(candidate["criteria"])) == len(candidate["criteria"]),
        "duplicate candidate criterion",
    )
    ancestor(checkout, candidate["base_commit"], candidate["candidate_commit"])
    expected_head = candidate["candidate_commit"]
    allowed = not any(check["status"] == "failed" for check in candidate["checks"])

    if stage in ("verification", "integration"):
        verification = load(bundle, "verification", records)
        same_candidate(candidate, verification)
        require(
            verification["actor"] != candidate["actor"], "verifier must be independent"
        )
        verdict = verification.get("verdict")
        require(
            verdict in ("PASS", "REWORK", "BLOCKED"), "invalid verification.verdict"
        )
        strings(verification.get("findings"), "verification.findings")
        criteria = verification.get("criteria")
        require(isinstance(criteria, list), "verification.criteria must be an array")
        ids = []
        for criterion in criteria:
            require(isinstance(criterion, dict), "verified criterion must be an object")
            require(text(criterion.get("id")), "verified criterion.id is required")
            ids.append(criterion["id"])
            require(
                criterion.get("status") in ("satisfied", "failed", "unverified"),
                "invalid criterion.status",
            )
            evidence(criterion.get("evidence"), bundle, "criterion.evidence")
        require(
            len(ids) == len(set(ids)) and set(ids) == set(candidate["criteria"]),
            "verification must cover every candidate criterion exactly once",
        )
        if verdict == "PASS":
            require(all_passed(verification), "PASS requires passing or reused checks")
            require(not verification["findings"], "PASS has blocking findings")
            require(
                all(item["status"] == "satisfied" for item in criteria),
                "PASS has unsatisfied criteria",
            )
        allowed = allowed and verdict == "PASS"

    if stage == "integration":
        integration = load(bundle, "integration", records)
        same_candidate(candidate, integration)
        require(
            integration.get("status") in ("integrated", "failed"),
            "invalid integration.status",
        )
        digest = hashlib.sha256((bundle / "verification.json").read_bytes()).hexdigest()
        require(
            integration.get("verification_sha256") == digest,
            "verification digest mismatch",
        )
        commit(integration.get("previous_tip"), "integration.previous_tip")
        commit(integration.get("integration_commit"), "integration.integration_commit")
        expected_head = integration["integration_commit"]
        if integration["status"] == "integrated":
            require(allowed, "integration requires an approved candidate")
            require(all_passed(integration), "integration checks have not passed")
            ancestor(checkout, integration["previous_tip"], expected_head)
            ancestor(checkout, candidate["candidate_commit"], expected_head)
        allowed = allowed and integration["status"] == "integrated"

    require(
        git(checkout, "rev-parse", "HEAD") == expected_head,
        "checkout HEAD mismatches record",
    )
    require(
        not git(checkout, "status", "--porcelain", "--untracked-files=normal"),
        "checkout must be clean",
    )
    return allowed


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory", type=Path, help="absolute or relative handoff directory"
    )
    parser.add_argument(
        "--stage", choices=("candidate", "verification", "integration"), required=True
    )
    parser.add_argument(
        "--checkout", type=Path, required=True, help="checkout being assessed"
    )
    args = parser.parse_args()
    try:
        allowed = validate(
            args.directory.resolve(), args.stage, args.checkout.resolve()
        )
    except (InvalidHandoff, OSError, ValueError) as error:
        print(f"Invalid handoff: {error}", file=sys.stderr)
        return 1
    print(
        "Transition allowed"
        if allowed
        else "Transition held: repair or prerequisite required"
    )
    return 0 if allowed else 2


if __name__ == "__main__":
    sys.exit(main())
