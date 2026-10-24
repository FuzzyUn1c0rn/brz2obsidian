"""Run the maintained suite, validate its receipt, and report all-src coverage.

Default: four checks, actual GUI execution, 80% production branch coverage.
Explicit --test selections are partial measurements and default to pytest only.
"""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

CHECKS = ("pytest", "lint", "format", "dependency")


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkout", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--python", type=Path)
    parser.add_argument("--manifest", type=Path, default=Path("tools/test-suite.json"))
    parser.add_argument("--test", action="append", default=[])
    parser.add_argument("--require-gui", action="store_true")
    parser.add_argument("--workers", type=int, choices=(1, 2, 3, 4))
    parser.add_argument("--check", action="append", choices=CHECKS)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--min-branch", type=float)
    parser.add_argument("--measurement-intent")
    args = parser.parse_args()
    if not 0 < args.timeout <= 600:
        parser.error("--timeout must be greater than zero and at most 600 seconds")
    if args.min_branch is not None and (
        not 0 <= args.min_branch <= 100 or not (args.measurement_intent or "").strip()
    ):
        parser.error("--min-branch needs 0..100 and an explicit --measurement-intent")
    if args.check and "pytest" not in args.check:
        parser.error("coverage measurement requires the pytest check")
    if not args.test and args.check:
        parser.error(
            "--check is for explicit --test measurements; default requires all four"
        )
    return args


def execute(argv, root, output, name, deadline):
    """Keep every command within the shared deadline, retaining original output."""
    remaining = deadline - time.perf_counter()
    if remaining <= 0:
        raise TimeoutError("Global verification deadline exhausted")
    flags = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    with (output / f"{name}.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            argv, cwd=root, stdout=log, stderr=subprocess.STDOUT, **flags
        )
        try:
            code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired, KeyboardInterrupt:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=5,
                    check=False,
                )
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            raise TimeoutError(
                f"Global verification deadline interrupted {name}"
            ) from None
    text = (output / f"{name}.log").read_text(encoding="utf-8")
    print(text, end="", flush=True)
    if code:
        raise RuntimeError(
            f"{name} failed with exit {code}; inspect {output / (name + '.log')}"
        )
    return text


def metrics(data, root):
    files = data["files"]
    inventory = {path.resolve() for path in (root / "src").rglob("*.py")}
    reported = {(root / path).resolve() for path in files}
    if not inventory or inventory != reported:
        raise ValueError(
            "Coverage must report every src Python file, including GUI modules"
        )
    totals = data["totals"]
    if not data["meta"]["branch_coverage"] or totals["num_branches"] <= 0:
        raise ValueError(
            "Coverage must contain a nonempty production branch denominator"
        )
    if totals["excluded_lines"]:
        raise ValueError("Production coverage must not exclude lines")
    contexts = Counter()
    repeated = []
    for filename, details in files.items():
        for line, names in details["contexts"].items():
            names = set(names) - {""}
            contexts.update(names)
            if len(names) > 1:
                repeated.append(
                    {"file": filename, "line": int(line), "test_contexts": len(names)}
                )
    if not contexts:
        raise ValueError("Coverage did not capture test function contexts")

    def ratio(covered, total):
        return {
            "covered": covered,
            "total": total,
            "percent": 100 * covered / total if total else 100.0,
        }

    return {
        "denominator": "all src/**/*.py, including GUI; no line or partial-branch exclusions",
        "production_files": len(inventory),
        "lines": ratio(totals["covered_lines"], totals["num_statements"]),
        "branches": ratio(totals["covered_branches"], totals["num_branches"]),
        "contexts": [
            {"context": name, "file_lines": count}
            for name, count in contexts.most_common()
        ],
        "context_limit": "Function contexts aggregate parameters; empty import context is retained in coverage.json",
        "repeated_lines": sorted(
            repeated, key=lambda row: (-row["test_contexts"], row["file"], row["line"])
        )[:30],
    }


def main():
    started = time.perf_counter()
    args = arguments()
    deadline = started + args.timeout
    root = args.checkout.resolve()
    python = (
        args.python
        or root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    ).resolve()
    output = root / "tmp" / "coverage-suite" / uuid.uuid4().hex[:8]
    result = {
        "status": "failed",
        "error": None,
        "measurement": "focused selection; partial suite evidence"
        if args.test
        else "default suite",
        "measurement_intent": args.measurement_intent,
        "timeout_seconds": args.timeout,
    }
    try:
        if not (root / "tools" / "check.py").is_file() or not python.is_file():
            raise ValueError(
                "Select a checkout with tools/check.py and its project virtual environment"
            )
        selectors = args.test
        if not selectors:
            manifest_path = (root / args.manifest).resolve()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                set(manifest) != {"schema_version", "selectors"}
                or manifest["schema_version"] != 1
            ):
                raise ValueError(
                    "Unsupported suite manifest; expected schema_version 1 and selectors"
                )
            selectors = manifest["selectors"]
            result["manifest"] = {
                "path": str(manifest_path),
                "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            }
        if (
            not isinstance(selectors, list)
            or not selectors
            or any(not isinstance(node, str) or not node for node in selectors)
            or len(set(selectors)) != len(selectors)
        ):
            raise ValueError(
                "Suite selectors must be a nonempty unique list of strings"
            )
        for node in selectors:
            path = Path(node.split("::", 1)[0])
            if (
                path.is_absolute()
                or not (root / path).resolve().is_relative_to(root)
                or not (root / path).exists()
            ):
                raise ValueError(f"Invalid checkout-relative selector: {node!r}")
        selectors = [
            Path(node.split("::", 1)[0]).as_posix()
            + ("::" + node.split("::", 1)[1] if "::" in node else "")
            for node in selectors
        ]
        checks = list(
            dict.fromkeys(args.check or (["pytest"] if args.test else CHECKS))
        )
        require_gui = not bool(args.test) or args.require_gui
        threshold = (
            args.min_branch
            if args.min_branch is not None
            else (None if args.test else 80)
        )
        result["minimum_branch_percent"] = threshold
        workers = args.workers if args.workers is not None else (1 if args.test else 4)
        output.mkdir(parents=True, exist_ok=False)
        requirement = {
            "id": "pytest",
            "scope": "focused",
            "selectors": selectors,
            "keyword": None,
            "marker": None,
            "require_gui": require_gui,
        }
        save(
            output / "requirements.json",
            {
                "schema_version": 1,
                "environment": "gui",
                "checks": [
                    requirement,
                    *({"id": check} for check in checks if check != "pytest"),
                ],
            },
        )
        config = output / "coverage.ini"
        config.write_text(
            "[run]\nbranch = true\nparallel = true\npatch = subprocess\n"
            "dynamic_context = test_function\n"
            f"source = {(root / 'src').as_posix()}\n"
            f"data_file = {(output / '.coverage').as_posix()}\n"
            "[report]\nexclude_lines = (?!)\npartial_branches = (?!)\n"
            "[html]\nshow_contexts = true\n",
            encoding="utf-8",
        )
        runner = [str(python), str(root / "tools" / "check.py")]
        command = [
            str(python),
            "-m",
            "coverage",
            "run",
            "--rcfile",
            str(config),
            str(root / "tools" / "check.py"),
            "run",
            "--checkout",
            str(root),
            "--python",
            str(python),
            "--environment",
            "gui",
            "--workers",
            str(workers),
        ]
        for check in checks:
            command += ["--check", check]
        for node in selectors:
            command += ["--test", node]
        if require_gui:
            command += ["--require-gui"]
        save(
            output / "plan.json",
            {
                **result,
                "command": command,
                "requirements": str(output / "requirements.json"),
                "coverage_config": str(config),
            },
        )
        run_log = execute(command, root, output, "run", deadline)
        receipts = [
            line.removeprefix("RECEIPT:").strip()
            for line in run_log.splitlines()
            if line.startswith("RECEIPT:")
        ]
        if len(receipts) != 1:
            raise ValueError("Runner did not publish exactly one receipt")
        result["receipt"] = receipts[0]
        validation = [
            *runner,
            "validate",
            "--receipt",
            receipts[0],
            "--checkout",
            str(root),
            "--requirements",
            str(output / "requirements.json"),
        ]
        execute(validation, root, output, "validate", deadline)
        receipt = json.loads(Path(receipts[0]).read_text(encoding="utf-8"))
        pytest = next(row for row in receipt["checks"] if row["id"] == "pytest")
        result["pytest_seconds"] = (
            datetime.fromisoformat(pytest["ended"])
            - datetime.fromisoformat(pytest["started"])
        ).total_seconds()
        result["runner_seconds"] = (
            datetime.fromisoformat(receipt["ended"])
            - datetime.fromisoformat(receipt["started"])
        ).total_seconds()
        result["timing_definition"] = (
            "pytest_seconds includes check process startup/teardown; "
            "runner_seconds includes all runner checks; elapsed_seconds includes "
            "setup, validation, coverage reports and summary preparation"
        )
        result["test_counts"] = pytest["counts"]
        coverage = [str(python), "-m", "coverage"]
        for name, command in (
            (
                "combine",
                [*coverage, "combine", "--rcfile", str(config), "--keep", str(output)],
            ),
            (
                "json",
                [
                    str(python),
                    str(root / "tools" / "coverage_report.py"),
                    "--rcfile",
                    str(config),
                    "--output",
                    str(output / "coverage.json"),
                ],
            ),
            (
                "html",
                [
                    *coverage,
                    "html",
                    "--rcfile",
                    str(config),
                    "-d",
                    str(output / "html"),
                ],
            ),
        ):
            execute(command, root, output, name, deadline)
        result.update(
            metrics(
                json.loads((output / "coverage.json").read_text(encoding="utf-8")), root
            )
        )
        result["coverage_json_sha256"] = hashlib.sha256(
            (output / "coverage.json").read_bytes()
        ).hexdigest()
        execute(validation, root, output, "validate-final", deadline)
        if threshold is not None and result["branches"]["percent"] < threshold:
            raise RuntimeError(
                f"Production branch threshold {threshold}% was not reached"
            )
        if time.perf_counter() >= deadline:
            raise TimeoutError(
                "Global verification deadline exhausted during reporting"
            )
        result["status"] = "passed"
        return_code = 0
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        TimeoutError,
        subprocess.SubprocessError,
    ) as error:
        result["error"] = str(error)
        print(f"COVERAGE SUITE ERROR: {error}", file=sys.stderr)
        return_code = 1 if isinstance(error, (RuntimeError, TimeoutError)) else 2
    result["elapsed_seconds"] = time.perf_counter() - started
    if result["elapsed_seconds"] >= args.timeout:
        result["status"] = "failed"
        result["error"] = "Global verification deadline exhausted"
        return_code = 1
    if output.is_dir():
        save(output / "summary.json", result)
        print(f"COVERAGE SUMMARY: {output / 'summary.json'}", flush=True)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
