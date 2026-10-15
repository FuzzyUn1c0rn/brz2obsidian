"""Run small skill evaluations in disposable fixtures and score observable guards."""

import argparse
import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / ".agents" / "evals" / "cases.json"
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "questions": {"type": "array", "items": {"type": "string"}},
        "skills_used": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "questions", "skills_used"],
    "additionalProperties": False,
}


def snapshot(directory):
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in directory.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(directory).parts
    }


def grade(case, before, after, events, answer, exit_code):
    changes = sorted(
        name
        for name in before.keys() | after.keys()
        if before.get(name) != after.get(name)
    )
    commands = [
        event["item"].get("command", "")
        for event in events
        if event.get("type") == "item.completed"
        and event.get("item", {}).get("type") == "command_execution"
    ]
    reads = set()
    for command in commands:
        normalized = re.sub(r"[\\/]+", "/", command).lower()
        for skill in case.get("must_read_skills", []) + case.get(
            "forbidden_skill_reads", []
        ):
            if f"{skill}/skill.md" in normalized:
                reads.add(skill)
    checks = sum(
        "tools/check.py" in re.sub(r"[\\/]+", "/", command).lower() and "run" in command
        for command in commands
    )
    guards = {
        "completed": exit_code == 0
        and isinstance(answer, dict)
        and isinstance(answer.get("answer"), str),
        "writes_in_scope": all(
            any(
                fnmatch.fnmatchcase(name, pattern) for pattern in case["allowed_writes"]
            )
            for name in changes
        ),
        "required_artifacts": all(
            any(
                name in after and fnmatch.fnmatchcase(name, pattern) for name in changes
            )
            for pattern in case.get("required_writes", [])
        ),
        "no_redundant_questions": not case.get("expect_no_questions", False)
        or answer.get("questions") == [],
        "required_skill_reads": set(case.get("must_read_skills", [])) <= reads,
        "no_unrelated_skill_reads": not reads.intersection(
            case.get("forbidden_skill_reads", [])
        ),
        "bounded_checks": checks <= case.get("max_check_commands", 0),
    }
    return {
        "case": case["id"],
        "guards": guards,
        "guards_passed": all(guards.values()),
        "changed_files": changes,
        "observed_skill_references": sorted(reads),
        "command_count": len(commands),
        "check_commands": checks,
        "semantic_review": "pending",
        "rubric": case["rubric"],
    }


def prepare(workspace, case=None):
    case = case or {}
    workspace.mkdir(parents=True)
    shutil.copytree(
        ROOT / ".agents" / "skills",
        workspace / ".agents" / "skills",
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    files = {
        "AGENTS.md": "Use repository skills when applicable. Preserve the user's task scope.\n"
        "Disposable demos belong under tmp/<effort>/ and research drafts under .scratch/<effort>/.\n"
        "Run checks only when they establish an affected obligation. Do not delegate in this fixture.\n"
        "Use only local fixture files; do not access external trackers, network services or private data.\n",
        "README.md": "Synthetic skill evaluation fixture. Read docs/facts.md for supported facts.\n",
        "docs/facts.md": "The export format is JSON. It contains records and attachments.\n"
        "The public boundary is export_records. XML export is unsupported.\n",
        "GLOSSARY.md": "# Glossary\n\n## Record\nA single exported item.\n",
        "src/example.py": 'def export_records(records):\n    return {"records": records, "attachments": []}\n',
        **case.get("fixture_files", {}),
    }
    for name, content in files.items():
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for name in ("workspace.md", "testing.md"):
        shutil.copyfile(ROOT / "docs" / name, workspace / "docs" / name)
    shutil.copytree(ROOT / "docs" / "agents", workspace / "docs" / "agents")
    # A fixture under tmp must never discover or mutate the parent checkout's Git state.
    for args in (
        ["init", "-b", "main" if "initial_branch" in case else "fixture"],
        ["config", "user.name", "Skill Evaluation"],
        ["config", "user.email", "evaluation@example.invalid"],
        ["config", "commit.gpgsign", "false"],
        ["config", "core.hooksPath", str(workspace / ".git" / "disabled-hooks")],
        ["add", "--all"],
        ["commit", "-m", "Synthetic skill evaluation fixture"],
    ):
        subprocess.run(
            ["git", "-C", str(workspace), *args], capture_output=True, check=True
        )
    branch = case.get("initial_branch", "fixture")
    if "initial_branch" in case and branch != "main":
        subprocess.run(
            ["git", "-C", str(workspace), "switch", "-c", branch],
            capture_output=True,
            check=True,
        )
    prior_work = case.get("prior_work", {})
    if prior_work:
        for name, content in prior_work.items():
            path = workspace / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        for args in (["add", "--all"], ["commit", "-m", "Existing feature work"]):
            subprocess.run(
                ["git", "-C", str(workspace), *args], capture_output=True, check=True
            )


def git_state(workspace):
    return {
        name: subprocess.check_output(
            ["git", "-C", str(workspace), *args], text=True, encoding="utf-8"
        ).strip()
        for name, args in {
            "branch": ["branch", "--show-current"],
            "head": ["rev-parse", "HEAD"],
            "refs": ["show-ref", "--heads"],
            "status": ["status", "--porcelain"],
        }.items()
    }


def run_case(case, destination, executable, timeout):
    destination.mkdir(parents=True)
    workspace = destination / "workspace"
    prepare(workspace, case)
    before = snapshot(workspace)
    (destination / "before.json").write_text(json.dumps(before), encoding="utf-8")
    (destination / "before-git.json").write_text(
        json.dumps(git_state(workspace), indent=2), encoding="utf-8"
    )
    schema = destination / "response.schema.json"
    schema.write_text(json.dumps(RESPONSE_SCHEMA), encoding="utf-8")
    prompt = (
        case["prompt"]
        + "\nReturn the requested result in answer. Put any questions you need answered in questions; otherwise use an empty array. List the skills you actually used."
    )
    (destination / "prompt.txt").write_text(prompt, encoding="utf-8")
    command = [
        executable,
        "--ask-for-approval",
        "never",
        "exec",
        "--ephemeral",
        "--json",
        "--sandbox",
        "workspace-write" if case["allowed_writes"] else "read-only",
        "--skip-git-repo-check",
        "-C",
        str(workspace),
        "--output-schema",
        str(schema),
        "--output-last-message",
        str(destination / "answer.json"),
        "-",
    ]
    metadata = {
        "command": command,
        "case": case,
        "model": "inherited from current Codex configuration",
    }
    (destination / "run.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    with (
        (destination / "trace.jsonl").open("w", encoding="utf-8") as trace,
        (destination / "stderr.txt").open("w", encoding="utf-8") as errors,
    ):
        try:
            result = subprocess.run(
                command,
                input=prompt,
                stdout=trace,
                stderr=errors,
                text=True,
                encoding="utf-8",
                timeout=timeout,
                check=False,
            )
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            exit_code = 124
    metadata["exit_code"] = exit_code
    (destination / "after-git.json").write_text(
        json.dumps(git_state(workspace), indent=2), encoding="utf-8"
    )
    (destination / "run.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return score(destination)


def score(destination):
    metadata = json.loads((destination / "run.json").read_text(encoding="utf-8"))
    events = []
    for line in (destination / "trace.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    try:
        answer = json.loads((destination / "answer.json").read_text(encoding="utf-8"))
    except OSError, ValueError:
        answer = {}
    result = grade(
        metadata["case"],
        json.loads((destination / "before.json").read_text()),
        snapshot(destination / "workspace"),
        events,
        answer,
        metadata.get("exit_code"),
    )
    (destination / "score.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    run = sub.add_parser("run")
    run.add_argument("--case", action="append", default=[])
    run.add_argument("--codex", default=shutil.which("codex"))
    run.add_argument("--timeout", type=int, default=180)
    scoring = sub.add_parser("score")
    scoring.add_argument("directory", type=Path)
    args = parser.parse_args()
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if args.action == "list":
        for case in cases:
            print(f"{case['id']}: {case['prompt']}")
        return 0
    if args.action == "score":
        result = score(args.directory.resolve())
        print(json.dumps(result, indent=2))
        return 0 if result["guards_passed"] else 1
    if not args.codex:
        parser.error("Codex CLI is unavailable; pass --codex with its executable path")
    unknown = set(args.case) - {case["id"] for case in cases}
    if unknown:
        parser.error(f"Unknown cases: {', '.join(sorted(unknown))}")
    destination = ROOT / "tmp" / "skill-evals" / uuid.uuid4().hex[:8]
    selected = [case for case in cases if not args.case or case["id"] in args.case]
    results = []
    for case in selected:
        print(f"Evaluating {case['id']} in {destination / case['id']}", flush=True)
        result = run_case(case, destination / case["id"], args.codex, args.timeout)
        results.append(result)
        print(
            f"{case['id']}: observable guards {'PASS' if result['guards_passed'] else 'FAIL'}; semantic review pending",
            flush=True,
        )
    print(f"EVIDENCE: {destination}", flush=True)
    return 0 if all(result["guards_passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
