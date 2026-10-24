"""Run and validate repository checks through one public process interface.

Only standard-library orchestration lives here. Commands execute installed tools
in the selected virtual environment, without changing installations or sources.
"""

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

VERSION = "1"
CHECKS = ("dependency", "pytest", "lint", "format")


class Invalid(ValueError):
    """A setup, execution or evidence contract could not be established."""


def now():
    return datetime.now(UTC).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def git(root, *args, input=None):
    result = subprocess.run(
        ["git", "-C", str(root), *args], input=input, capture_output=True, check=False
    )
    if result.returncode:
        raise Invalid(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


def snapshot(root):
    paths = sorted(
        set(
            git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
            .decode("utf-8")
            .split("\0")
        )
        - {""}
    )
    existing = [name for name in paths if (root / name).is_file()]
    # Git performs the same clean/eol normalization used when committing. This
    # does not touch the index. Quoted stdin paths preserve Unicode and spaces.
    names = "".join(
        json.dumps(name, ensure_ascii=False) + "\n" for name in existing
    ).encode("utf-8")
    oids = (
        git(root, "hash-object", "--stdin-paths", input=names)
        .decode("ascii")
        .splitlines()
        if existing
        else []
    )
    normalized = dict(zip(existing, oids, strict=True))
    files = [
        {
            "path": name,
            "git_blob": normalized[name],
            "disk_sha256": digest((root / name).read_bytes()),
        }
        for name in existing
    ]
    identity = digest(
        encoded([{"path": row["path"], "git_blob": row["git_blob"]} for row in files])
    )
    return {
        "identity": identity,
        "disk_identity": digest(encoded(files)),
        "files": files,
    }


def snapshot_ref(root, ref):
    resolved = git(root, "rev-parse", "--verify", ref + "^{commit}").decode().strip()
    if resolved != ref:
        raise Invalid("--ref must be a full resolved commit ID")
    files = []
    for entry in git(root, "ls-tree", "-r", "-z", ref).decode("utf-8").split("\0"):
        if entry:
            metadata, name = entry.split("\t", 1)
            _, kind, blob = metadata.split()
            if kind != "blob":
                raise Invalid("Source tree contains unsupported non-file entries")
            files.append({"path": name, "git_blob": blob})
    # A historical blob may predate today's normalization policy. Read Git
    # objects in one batch, then apply the reference tree's effective filters
    # where conversion can matter. Never rewrite the index or fixture bytes.
    blobs = list(dict.fromkeys(item["git_blob"] for item in files))
    stream = io.BytesIO(
        git(
            root, "cat-file", "--batch", input=("\n".join(blobs) + "\n").encode("ascii")
        )
    )
    contents = {}
    for blob in blobs:
        header = stream.readline().decode("ascii").split()
        if len(header) != 3 or header[0] != blob or header[1] != "blob":
            raise Invalid("Cannot read complete reference source blobs")
        contents[blob] = stream.read(int(header[2]))
        if stream.read(1) != b"\n":
            raise Invalid("Truncated reference source blob")
    attributes = (
        git(
            root,
            "--attr-source=" + ref,
            "check-attr",
            "-z",
            "--stdin",
            "filter",
            "ident",
            "working-tree-encoding",
            input=("\0".join(item["path"] for item in files) + "\0").encode("utf-8"),
        )
        .decode("utf-8")
        .split("\0")[:-1]
    )
    filtered = set()
    for index in range(0, len(attributes), 3):
        filename, _attribute, value = attributes[index : index + 3]
        if value not in ("unspecified", "unset"):
            filtered.add(filename)
    for item in files:
        raw = contents[item["git_blob"]]
        if b"\r\n" in raw or item["path"] in filtered:
            if item["path"] in filtered:
                raw = git(
                    root,
                    "--attr-source=" + ref,
                    "cat-file",
                    "--filters",
                    "--path=" + item["path"],
                    item["git_blob"],
                )
            item["git_blob"] = (
                git(
                    root,
                    "--attr-source=" + ref,
                    "hash-object",
                    "--path=" + item["path"],
                    "--stdin",
                    input=raw,
                )
                .decode("ascii")
                .strip()
            )
    return {
        "identity": digest(encoded(sorted(files, key=lambda item: item["path"]))),
        "files": files,
    }


def save(path, data):
    temporary = path.with_suffix(".pending")
    with temporary.open("xb") as handle:
        handle.write(encoded(data))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def evidence(path, root):
    return {
        "path": str(path.relative_to(root)),
        "sha256": digest(path.read_bytes()),
        "size": path.stat().st_size,
    }


def selection(args):
    chosen = {
        "scope": "focused" if args.test or args.keyword or args.marker else "full",
        "selectors": [selector_spelling(node) for node in args.test],
        "keyword": args.keyword,
        "marker": args.marker,
        "require_gui": args.require_gui,
    }
    if args.workers > 1:
        chosen["workers"] = args.workers
    return chosen


def selector_spelling(node):
    filename, separator, suffix = node.partition("::")
    return Path(filename).as_posix() + separator + suffix


def command_for(python, run_dir, check, chosen):
    argv = [str(python), "-m"]
    if check == "dependency":
        return argv + ["pip", "check"]
    if check in ("lint", "format"):
        return argv + [
            "ruff",
            *(["check"] if check == "lint" else ["format", "--check"]),
            "--cache-dir",
            str(run_dir / "ruff-cache"),
            ".",
        ]
    argv += [
        "pytest",
        "-q",
        "--durations=20",
        "-p",
        "tools.check_pytest",
        "--basetemp",
        str(run_dir / "pytest"),
        "-o",
        f"cache_dir={run_dir / 'pytest-cache'}",
        *chosen["selectors"],
    ]
    if chosen["keyword"]:
        argv += ["-k", chosen["keyword"]]
    if chosen["marker"]:
        argv += ["-m", chosen["marker"]]
    if chosen.get("workers", 1) > 1:
        argv += [
            "-n",
            str(chosen["workers"]),
            "--dist=loadscope",
            "--no-loadscope-reorder",
            "--max-worker-restart=0",
        ]
    return argv


def parse():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "run", help="Run all four checks, or explicitly selected checks"
    )
    run.add_argument(
        "--checkout", type=Path, default=Path(__file__).resolve().parents[1]
    )
    run.add_argument(
        "--python",
        type=Path,
        help="Absolute project virtual-environment interpreter override",
    )
    run.add_argument("--environment", choices=("auto", "base", "gui"), default="auto")
    run.add_argument("--check", action="append", choices=CHECKS)
    run.add_argument(
        "--test",
        action="append",
        default=[],
        help="Pytest relative file/directory/node; repeatable",
    )
    run.add_argument("-k", dest="keyword")
    run.add_argument("-m", dest="marker")
    run.add_argument("--require-gui", action="store_true")
    run.add_argument("--workers", type=int, choices=(1, 2, 3), default=1)
    validate = commands.add_parser(
        "validate",
        help="Validate completed evidence against independent scope requirements",
    )
    validate.add_argument("--receipt", type=Path, required=True)
    validate.add_argument("--checkout", type=Path, required=True)
    validate.add_argument("--requirements", type=Path, required=True)
    validate.add_argument("--reuse-reason")
    validate.add_argument(
        "--allow-failed",
        action="store_true",
        help="Check integrity of executed failing evidence; never qualifies completion",
    )
    validate.add_argument(
        "--ref",
        help="Bind evidence to this full tracked Git commit instead of present checkout files",
    )
    return parser.parse_args()


def child_environment(root, run_dir):
    env = os.environ.copy()
    env.update(
        PYTHONPATH=os.pathsep.join((str(root / "src"), str(root))),
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
        QT_QPA_PLATFORM="offscreen",
        BRZ_CHECK_COUNTS=str(run_dir / "counts.json"),
        RUFF_CACHE_DIR=str(run_dir / "ruff-cache"),
    )
    # Caller plugin/argument injections would make the declared selection false.
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_PLUGINS", None)
    return env


def probe(python, root, env, checks, mode, workers):
    if not python.is_absolute() or not python.is_file():
        raise Invalid(
            "Select an existing absolute project virtual-environment interpreter with --python; bootstrap the project .venv first"
        )
    code = """
import importlib, importlib.metadata, importlib.util, json, pathlib, sys
info = {'executable': sys.executable, 'prefix': sys.prefix, 'base_prefix': sys.base_prefix, 'version': list(sys.version_info[:3]), 'tools': {}, 'imports': {}}
for name in ('brz2obsidian', 'brz2obsidian_ui'):
    module = importlib.import_module(name)
    info['imports'][name] = str(pathlib.Path(module.__file__).resolve())
for name in json.loads(sys.argv[1]):
    info['tools'][name] = importlib.metadata.version(name)
info['qt_present'] = importlib.util.find_spec('PySide6') is not None
if info['qt_present']:
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    info['qt_version'] = QtCore.qVersion()
print(json.dumps(info))
"""
    packages = sorted(
        {
            "pytest"
            if check == "pytest"
            else "ruff"
            if check in ("lint", "format")
            else "pip"
            for check in checks
        }
    )
    if workers > 1:
        packages += ["pytest-xdist", "execnet"]
    result = subprocess.run(
        [str(python), "-c", code, json.dumps(packages)],
        cwd=root,
        env=env,
        capture_output=True,
        timeout=45,
        check=False,
    )
    if result.returncode:
        raise Invalid(
            "Interpreter/tool/import setup failed:\n"
            + result.stdout.decode("utf-8", errors="replace")
            + result.stderr.decode("utf-8", errors="replace")
        )
    info = json.loads(result.stdout)
    if info["prefix"] == info["base_prefix"] or info["version"] < [3, 14, 0]:
        raise Invalid("Python must be >=3.14 in a project virtual environment")
    for name, location in info["imports"].items():
        if not Path(location).is_relative_to(root / "src" / name):
            raise Invalid(
                f"Project import {name} resolved outside assessed checkout: {location}"
            )
    detected = "gui" if info["qt_present"] else "base"
    if mode != "auto" and detected != mode:
        raise Invalid(
            f"Requested {mode} environment but detected {detected}; base requires absent Qt and gui requires usable Qt"
        )
    return info, detected


def execute(argv, root, env, run_dir, check):
    import codecs

    paths = {
        stream: run_dir / f"{check}.{stream}.bin" for stream in ("stdout", "stderr")
    }
    logs = {stream: run_dir / f"{check}.{stream}.log" for stream in paths}
    process = subprocess.Popen(
        argv, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    failures = []

    def drain(stream, pipe):
        try:
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            with (
                paths[stream].open("xb") as raw,
                logs[stream].open("x", encoding="utf-8", newline="") as readable,
            ):
                while block := pipe.read1(8192):
                    raw.write(block)
                    chunk = decoder.decode(block)
                    readable.write(chunk)
                    target = sys.stdout if stream == "stdout" else sys.stderr
                    target.write(chunk)
                    target.flush()
                readable.write(decoder.decode(b"", final=True))
        except (OSError, ValueError) as error:
            failures.append(str(error))
        finally:
            pipe.close()

    threads = [
        threading.Thread(target=drain, args=(stream, getattr(process, stream)))
        for stream in paths
    ]
    for thread in threads:
        thread.start()
    interrupted = False
    try:
        code = process.wait()
    except KeyboardInterrupt:
        interrupted = True
        process.terminate()
        try:
            code = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            code = process.wait()
    finally:
        for thread in threads:
            thread.join()
    if failures:
        raise Invalid("Output capture failed: " + "; ".join(failures))
    return (
        code,
        interrupted,
        [evidence(path, run_dir) for path in (*paths.values(), *logs.values())],
    )


def run(args):
    root = args.checkout.resolve()
    checks = list(dict.fromkeys(args.check or CHECKS))
    if (
        args.test or args.keyword or args.marker or args.require_gui or args.workers > 1
    ) and "pytest" not in checks:
        raise Invalid("Test selectors require the pytest check")
    for node in args.test:
        path = Path(node.split("::", 1)[0])
        if (
            not node
            or path.is_absolute()
            or not (root / path).resolve().is_relative_to(root)
            or not (root / path).exists()
        ):
            raise Invalid(f"Invalid checkout-relative test selector: {node!r}")
    run_dir = root / "tmp" / "checks" / uuid.uuid4().hex[:8]
    run_dir.mkdir(parents=True, exist_ok=False)
    if git(root, "check-ignore", str(run_dir)).strip() == b"":
        raise Invalid("tmp/checks must be Git-ignored development output")
    python = (
        args.python
        if args.python
        else root
        / ".venv"
        / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    receipt = {
        "schema_version": 1,
        "run_id": run_dir.name,
        "checkout": str(root),
        "revision": git(root, "rev-parse", "HEAD").decode().strip(),
        "working_tree": git(root, "status", "--porcelain=v1", "-z").decode("utf-8"),
        "runner": {"version": VERSION, "sha256": digest(Path(__file__).read_bytes())},
        "requested_environment": args.environment,
        "environment": None,
        "settings": {
            key: value
            for key, value in child_environment(root, run_dir).items()
            if key
            in (
                "PYTHONPATH",
                "PYTHONUTF8",
                "PYTHONIOENCODING",
                "QT_QPA_PLATFORM",
                "RUFF_CACHE_DIR",
            )
        },
        "started": now(),
        "ended": None,
        "snapshot_before": snapshot(root),
        "snapshot_after": None,
        "checks": [
            {
                "id": check,
                "status": "not_run",
                "exit_code": None,
                "argv": [],
                "cwd": str(root),
                "selection": selection(args) if check == "pytest" else None,
                "started": None,
                "ended": None,
                "evidence": [],
                "counts": None,
            }
            for check in checks
        ],
        "aggregate": "incomplete",
        "error": None,
    }
    save(run_dir / "partial.json", receipt)
    env = child_environment(root, run_dir)
    code = 2
    try:
        if (
            digest((root / "tools" / "check.py").read_bytes())
            != receipt["runner"]["sha256"]
        ):
            raise Invalid("Invoked runner differs from assessed checkout runner")
        info, mode = probe(python, root, env, checks, args.environment, args.workers)
        info["git_version"] = git(root, "--version").decode("utf-8").strip()
        receipt["interpreter"] = info
        receipt["environment"] = mode
        if args.require_gui and mode != "gui":
            raise Invalid("Executed GUI coverage requires the GUI environment")
        any_failed = False
        for row in receipt["checks"]:
            check = row["id"]
            if (
                snapshot(root)["disk_identity"]
                != receipt["snapshot_before"]["disk_identity"]
            ):
                raise Invalid(
                    "Assessed repository source changed during execution; remaining checks not run"
                )
            argv = command_for(python, run_dir, check, row["selection"])
            row.update(argv=argv, status="running", started=now())
            save(run_dir / "partial.json", receipt)
            exit_code, interrupted, outputs = execute(argv, root, env, run_dir, check)
            row.update(
                exit_code=exit_code,
                ended=now(),
                evidence=outputs,
                status="interrupted"
                if interrupted
                else "passed"
                if exit_code == 0
                else "failed",
            )
            if check == "pytest" and (run_dir / "counts.json").exists():
                row["counts"] = json.loads(
                    (run_dir / "counts.json").read_text(encoding="utf-8")
                )
                row["evidence"].append(evidence(run_dir / "counts.json", run_dir))
                if row["counts"]["collected"] == 0 or (
                    row["counts"]["passed"] + row["counts"]["failed"] == 0
                ):
                    row["status"] = "failed"
                    row["detail"] = "No tests executed"
                if (
                    args.require_gui
                    or (mode == "gui" and row["selection"]["scope"] == "full")
                ) and row["counts"]["gui_executed"] == 0:
                    row["status"] = "failed"
                    row["detail"] = "Required GUI tests did not execute"
            elif check == "pytest" and not interrupted:
                raise Invalid("Pytest execution counts missing")
            if interrupted:
                receipt["aggregate"] = "interrupted"
                code = 3
                break
            any_failed |= row["status"] != "passed"
        else:
            receipt["aggregate"] = "failed" if any_failed else "passed"
            code = 1 if any_failed else 0
    except KeyboardInterrupt:
        receipt.update(
            aggregate="interrupted", error="Interrupted before execution completed"
        )
        code = 3
    except (Invalid, OSError, ValueError, subprocess.SubprocessError) as error:
        receipt.update(aggregate="error", error=str(error))
        print(str(error), file=sys.stderr)
        code = 2
    finally:
        receipt["ended"] = now()
        receipt["snapshot_after"] = snapshot(root)
        if (
            receipt["snapshot_after"]["disk_identity"]
            != receipt["snapshot_before"]["disk_identity"]
        ):
            receipt.update(
                aggregate="error", error="Assessed source changed during execution"
            )
            code = 2
        save(run_dir / "receipt.json", receipt)
        print(f"RECEIPT: {run_dir / 'receipt.json'}", flush=True)
    return code


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Invalid(f"Cannot read complete JSON evidence {path}: {error}") from error


def validate(args):
    receipt = load_json(args.receipt)
    expected = load_json(args.requirements)
    if (
        not isinstance(receipt, dict)
        or type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != 1
        or not isinstance(expected, dict)
        or type(expected.get("schema_version")) is not int
        or expected.get("schema_version") != 1
    ):
        raise Invalid("Unknown or malformed receipt/requirements schema version")
    required_fields = {
        "schema_version",
        "run_id",
        "checkout",
        "revision",
        "working_tree",
        "runner",
        "requested_environment",
        "environment",
        "settings",
        "started",
        "ended",
        "snapshot_before",
        "snapshot_after",
        "checks",
        "aggregate",
        "error",
        "interpreter",
    }
    if set(receipt) != required_fields or set(expected) != {
        "schema_version",
        "environment",
        "checks",
    }:
        raise Invalid("Receipt/requirements required fields are missing or unsupported")
    if (
        args.receipt.name != "receipt.json"
        or args.receipt.parent.name != receipt["run_id"]
    ):
        raise Invalid("Receipt is not a completed identified run publication")
    for key in ("snapshot_before", "snapshot_after"):
        facts = receipt[key]
        identity = digest(
            encoded(
                [
                    {"path": item["path"], "git_blob": item["git_blob"]}
                    for item in facts["files"]
                ]
            )
        )
        if identity != facts["identity"]:
            raise Invalid("Malformed source snapshot manifest identity")
        if digest(encoded(facts["files"])) != facts["disk_identity"]:
            raise Invalid("Malformed source snapshot disk identity")
    interpreter = receipt["interpreter"]
    if (
        interpreter["prefix"] == interpreter["base_prefix"]
        or interpreter["version"] < [3, 14, 0]
        or ("gui" if interpreter["qt_present"] else "base") != receipt["environment"]
    ):
        raise Invalid("Declared interpreter/environment identity is inconsistent")
    if (
        expected.get("environment") not in ("base", "gui")
        or receipt.get("environment") != expected["environment"]
    ):
        raise Invalid("Required environment is not established by this receipt")
    allowed = ("passed", "failed") if args.allow_failed else ("passed",)
    if receipt.get("aggregate") not in allowed or not receipt.get("ended"):
        raise Invalid("Receipt does not establish completed successful execution")
    root = args.checkout.resolve()
    if (
        Path(receipt["checkout"]).resolve() != root
        and not (args.reuse_reason or "").strip()
    ):
        raise Invalid(
            "Different checkout requires explicit evidence reuse applicability reason"
        )
    current = snapshot_ref(root, args.ref) if args.ref else snapshot(root)
    if (
        receipt["snapshot_before"]["identity"] != receipt["snapshot_after"]["identity"]
        or receipt["snapshot_before"]["disk_identity"]
        != receipt["snapshot_after"]["disk_identity"]
        or current["identity"] != receipt["snapshot_after"]["identity"]
    ):
        raise Invalid("Receipt source snapshot is stale or changed during execution")
    runner_bytes = (
        git(root, "show", args.ref + ":tools/check.py")
        if args.ref
        else (root / "tools" / "check.py").read_bytes()
    )
    if digest(runner_bytes) != receipt["runner"]["sha256"]:
        raise Invalid("Receipt runner identity differs from assessed runner")
    rows = receipt.get("checks")
    if (
        not isinstance(rows, list)
        or not rows
        or len({row["id"] for row in rows}) != len(rows)
    ):
        raise Invalid("Missing or duplicated completed checks")
    requirements = expected.get("checks")
    if not isinstance(requirements, list) or not requirements:
        raise Invalid("Independent required check selection must be nonempty")
    for row in rows:
        if (
            row["id"] not in CHECKS
            or row["status"]
            not in (("passed", "failed") if args.allow_failed else ("passed",))
            or type(row["exit_code"]) is not int
            or (row["status"] == "passed" and row["exit_code"] != 0)
            or not row["started"]
            or not row["ended"]
            or not row["argv"]
            or not row["evidence"]
        ):
            raise Invalid("Check lacks complete successful execution facts")
        origin = Path(receipt["checkout"])
        origin_run = origin / "tmp" / "checks" / receipt["run_id"]
        if (
            row["cwd"] != str(origin)
            or Path(row["argv"][0]).resolve()
            != Path(interpreter["executable"]).resolve()
        ):
            raise Invalid(
                "Command working directory/interpreter differs from assessed context"
            )
        chosen = row["selection"]
        if row["id"] == "pytest":
            if (
                not isinstance(chosen, dict)
                or set(chosen)
                not in (
                    {"scope", "selectors", "keyword", "marker", "require_gui"},
                    {
                        "scope",
                        "selectors",
                        "keyword",
                        "marker",
                        "require_gui",
                        "workers",
                    },
                )
                or (
                    "workers" in chosen
                    and (
                        type(chosen["workers"]) is not int
                        or chosen["workers"] not in (2, 3)
                    )
                )
                or not isinstance(chosen["selectors"], list)
                or any(not isinstance(node, str) for node in chosen["selectors"])
                or any(
                    chosen[key] is not None and not isinstance(chosen[key], str)
                    for key in ("keyword", "marker")
                )
                or not isinstance(chosen["require_gui"], bool)
            ):
                raise Invalid("Malformed executed pytest selection")
            actual_scope = (
                "focused"
                if chosen["selectors"] or chosen["keyword"] or chosen["marker"]
                else "full"
            )
            if chosen["scope"] != actual_scope:
                raise Invalid("Recorded pytest scope contradicts executed selection")
        elif chosen is not None or row["counts"] is not None:
            raise Invalid("Non-pytest check cannot declare pytest selection or counts")
        if row["argv"] != command_for(
            row["argv"][0], origin_run, row["id"], row["selection"]
        ):
            raise Invalid(
                "Recorded check arguments disagree with declared execution selection"
            )
        tool = (
            "pytest"
            if row["id"] == "pytest"
            else "ruff"
            if row["id"] in ("lint", "format")
            else "pip"
        )
        if not interpreter["tools"].get(tool):
            raise Invalid("Executed tool version missing")
        if (
            row["id"] == "pytest"
            and chosen.get("workers", 1) > 1
            and any(
                not interpreter["tools"].get(package)
                for package in ("pytest-xdist", "execnet")
            )
        ):
            raise Invalid("Parallel execution tool version missing")
        for item in row["evidence"]:
            path = (args.receipt.parent / item["path"]).resolve()
            if (
                not path.is_relative_to(args.receipt.parent.resolve())
                or not path.is_file()
                or path.stat().st_size != item["size"]
                or digest(path.read_bytes()) != item["sha256"]
            ):
                raise Invalid(f"Missing or altered output evidence: {item['path']}")
        expected_paths = {
            f"{row['id']}.{stream}.{suffix}"
            for stream in ("stdout", "stderr")
            for suffix in ("bin", "log")
        }
        if row["id"] == "pytest":
            expected_paths.add("counts.json")
        if {item["path"] for item in row["evidence"]} != expected_paths or len(
            row["evidence"]
        ) != len(expected_paths):
            raise Invalid(
                "Required original stream/log/count evidence is missing or duplicated"
            )
        for stream in ("stdout", "stderr"):
            raw = (args.receipt.parent / f"{row['id']}.{stream}.bin").read_bytes()
            readable = (args.receipt.parent / f"{row['id']}.{stream}.log").read_bytes()
            if raw.decode("utf-8", errors="replace").encode("utf-8") != readable:
                raise Invalid("Readable log does not match original output bytes")
        if row["id"] == "pytest" and encoded(
            load_json(args.receipt.parent / "counts.json")
        ) != encoded(row["counts"]):
            raise Invalid("Receipt execution counts differ from captured pytest counts")
    for required in requirements:
        if not isinstance(required, dict) or required.get("id") not in CHECKS:
            raise Invalid("Unknown required check selector")
        row = next((row for row in rows if row["id"] == required["id"]), None)
        if row is None:
            raise Invalid(f"Required check not executed: {required['id']}")
        if row["id"] == "pytest":
            if set(required) != {
                "id",
                "scope",
                "selectors",
                "keyword",
                "marker",
                "require_gui",
            } or required["scope"] not in ("full", "focused"):
                raise Invalid("Malformed required pytest scope")
            if required["scope"] == "full" and (
                required["selectors"] or required["keyword"] or required["marker"]
            ):
                raise Invalid("Full required pytest scope cannot narrow selection")
            chosen = row["selection"]
            required = {
                **required,
                "selectors": [
                    selector_spelling(node) for node in required["selectors"]
                ],
            }
            if any(chosen[key] != required[key] for key in ("keyword", "marker")):
                raise Invalid(
                    "Focused expression requirements need the exact executed expression selection"
                )
            if chosen["scope"] != "full" and any(
                chosen[key] != required[key]
                for key in ("scope", "selectors", "keyword", "marker")
            ):
                raise Invalid(
                    "Executed pytest selection is insufficient for required scope"
                )
            counts = row["counts"]
            if (
                not counts
                or counts["collected"] <= 0
                or (
                    not args.allow_failed
                    and (counts["passed"] <= 0 or counts["failed"] or counts["errors"])
                )
            ):
                raise Invalid(
                    "Required pytest execution counts do not establish success"
                )
            if required["scope"] == "focused":
                for selector in required["selectors"]:
                    if not any(
                        node == selector
                        or (
                            "::" in selector
                            and "[" not in selector.split("::", 1)[1]
                            and node.startswith(selector + "[")
                        )
                        or selector == "."
                        or node.startswith(
                            (selector.rstrip("/") + "/", selector + "::")
                        )
                        for node in counts["executed_nodes"]
                    ):
                        raise Invalid(
                            "Recorded suite did not execute required focused selector"
                        )
            if (
                required["require_gui"]
                or (expected["environment"] == "gui" and required["scope"] == "full")
            ) and counts["gui_executed"] <= 0:
                raise Invalid("Required GUI coverage did not execute")
        elif set(required) != {"id"}:
            raise Invalid("Unsupported check requirement fields")
    print(f"VALID: {args.receipt}")
    return 0


def main():
    import signal

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, interrupted)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace", newline="")
    args = parse()
    try:
        return run(args) if args.command == "run" else validate(args)
    except (
        Invalid,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        print(f"CHECK ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
