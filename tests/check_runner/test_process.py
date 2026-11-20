"""The maintained check command is tested only through its public processes."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tools" / "check.py"


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "é selected checkout"
    root.mkdir()
    (root / "tools").mkdir()
    for path in (ROOT / "tools").glob("check*.py"):
        shutil.copy2(path, root / "tools" / path.name)
    for package in ("brz2obsidian", "brz2obsidian_ui"):
        target = root / "src" / package
        target.mkdir(parents=True)
        (target / "__init__.py").write_text('VERSION = "selected"\n')
    (root / "tests").mkdir()
    (root / "tests" / "test_selected.py").write_text(
        "import brz2obsidian\n\n\n"
        "def test_selected():\n"
        "    assert brz2obsidian.VERSION == 'selected'\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        'addopts = "--basetemp=tmp/pytest"\nmarkers = ["gui: GUI checks"]\n'
        '[tool.ruff]\ntarget-version = "py314"\n',
    )
    (root / ".gitignore").write_text("tmp/\n__pycache__/\n.venv/\n")
    (root / ".gitattributes").write_text("* text=auto eol=lf\n")
    for args in (
        ("init",),
        ("add", "."),
        (
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "fixture",
        ),
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def command(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(RUNNER), *map(str, args)],
        cwd=cwd or ROOT.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        check=False,
    )


def run(root, *args):
    result = command(
        "run",
        "--checkout",
        root,
        "--python",
        sys.executable,
        "--environment",
        "auto",
        *args,
    )
    receipts = list((root / "tmp" / "checks").glob("*/receipt.json"))
    assert receipts, result.stdout + result.stderr
    receipt = max(receipts, key=lambda path: path.stat().st_mtime_ns)
    return result, receipt, json.loads(receipt.read_text(encoding="utf-8"))


def requirements(root, checks, environment):
    path = root / "tmp" / "requirements.json"
    path.write_text(
        json.dumps({"schema_version": 1, "environment": environment, "checks": checks}),
        encoding="utf-8",
    )
    return path


def pytest_requirement(scope="full", selectors=None, **extra):
    return {
        "id": "pytest",
        "scope": scope,
        "selectors": selectors or [],
        "keyword": None,
        "marker": None,
        "require_gui": False,
        **extra,
    }


def test_lint_rejects_new_comments_even_with_an_existing_comment_removed(checkout):
    selected = checkout / "tests" / "test_selected.py"
    value = selected.read_text(encoding="utf-8")
    selected.write_text(
        value + '\nLABEL = "# data"\n# new explanation\n', encoding="utf-8"
    )
    sibling = checkout / "tests" / "test_new.py"
    sibling.write_text("import sys  # noqa: F401\n", encoding="utf-8")
    (checkout / "tools" / "comment-baseline.json").write_text(
        json.dumps(
            {"tests/test_selected.py": [hashlib.sha256(b"# old note").hexdigest()]}
        ),
        encoding="utf-8",
    )

    result, _, receipt = run(checkout, "--check", "lint")

    assert result.returncode == 1, result.stdout + result.stderr
    assert receipt["checks"][0]["status"] == "failed"
    assert "tests/test_selected.py:8:1: new Python comment" in result.stdout
    assert "tests/test_new.py:1:13: new Python comment" in result.stdout
    assert "# data" not in result.stdout

    baseline = checkout / "tools" / "comment-baseline.json"
    old_baseline = baseline.read_bytes()
    prune = subprocess.run(
        [sys.executable, "-m", "tools.check_lint", "--prune-comments"],
        cwd=checkout,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert prune.returncode == 1, prune.stdout + prune.stderr
    assert baseline.read_bytes() == old_baseline


def test_lint_requires_pruning_and_accepts_shifted_comments(checkout):
    baseline = checkout / "tools" / "comment-baseline.json"
    selected = checkout / "tests" / "test_selected.py"
    source = selected.read_text(encoding="utf-8")
    selected.write_text(
        source + '\nLABEL = "# literal data"\n# retained note\n', encoding="utf-8"
    )
    retained = hashlib.sha256(b"# retained note").hexdigest()
    retired = hashlib.sha256(b"# retired note").hexdigest()
    baseline.write_text(
        json.dumps({"tests/test_selected.py": [retained, retired]}), encoding="utf-8"
    )

    result, _, _ = run(checkout, "--check", "lint")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Remove 1 retired entries" in result.stdout

    prune = subprocess.run(
        [sys.executable, "-m", "tools.check_lint", "--prune-comments"],
        cwd=checkout,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert prune.returncode == 0, prune.stdout + prune.stderr
    assert json.loads(baseline.read_bytes()) == {"tests/test_selected.py": [retained]}

    selected.write_text("\n" + selected.read_text(encoding="utf-8"), encoding="utf-8")
    passing, receipt_path, receipt = run(checkout, "--check", "lint")
    assert passing.returncode == 0, passing.stdout + passing.stderr
    need = requirements(checkout, [{"id": "lint"}], receipt["environment"])
    validated = command(
        "validate",
        "--checkout",
        checkout,
        "--receipt",
        receipt_path,
        "--requirements",
        need,
    )
    assert validated.returncode == 0, validated.stdout + validated.stderr


def test_focused_check_uses_selected_checkout_and_publishes_valid_receipt(checkout):
    original_path = os.environ.get("PYTHONPATH")
    selected = checkout / "tests" / "test_selected.py"
    selected.write_text(
        selected.read_text() + "    import time\n    time.sleep(0.02)\n",
        encoding="utf-8",
    )
    (checkout / "tests" / "test_excluded.py").write_text(
        "def test_excluded():\n    raise AssertionError('excluded case executed')\n",
        encoding="utf-8",
    )
    result, path, receipt = run(
        checkout, "--check", "pytest", "--test", "tests/test_selected.py"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    assert re.search(
        r"\d+\.\d+s call\s+tests/test_selected.py::test_selected", result.stdout
    )
    assert "excluded case executed" not in result.stdout
    assert receipt["aggregate"] == "passed"
    assert receipt["checks"][0]["counts"]["passed"] == 1
    assert receipt["checks"][0]["counts"]["executed_nodes"] == [
        "tests/test_selected.py::test_selected"
    ]
    timings = [
        json.loads(line)
        for line in (path.parent / "pytest-timings.jsonl").read_text().splitlines()
    ]
    assert [row["nodeid"] for row in timings] == [
        "tests/test_selected.py::test_selected"
    ] * 3
    assert [row["when"] for row in timings] == ["setup", "call", "teardown"]
    assert all(row["outcome"] == "passed" for row in timings)
    assert timings[1]["duration"] > 0
    expected = requirements(
        checkout,
        [pytest_requirement("focused", ["tests/test_selected.py"])],
        receipt["environment"],
    )
    accepted = command(
        "validate",
        "--receipt",
        path,
        "--checkout",
        checkout,
        "--requirements",
        expected,
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert os.environ.get("PYTHONPATH") == original_path


def test_individual_parameter_selection_cannot_cover_another_variant(checkout):
    (checkout / "tests" / "test_selected.py").write_text(
        "import pytest\n"
        "@pytest.mark.parametrize('value', ['alpha', 'beta'])\n"
        "def test_selected(value):\n"
        "    assert value in ('alpha', 'beta')\n"
    )
    result, path, receipt = run(
        checkout,
        "--check",
        "pytest",
        "--test",
        "tests/test_selected.py::test_selected[alpha]",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert receipt["checks"][0]["counts"]["passed"] == 1
    for variant, status in (("alpha", 0), ("beta", 2)):
        expected = requirements(
            checkout,
            [
                pytest_requirement(
                    "focused", [f"tests/test_selected.py::test_selected[{variant}]"]
                )
            ],
            receipt["environment"],
        )
        validated = command(
            "validate",
            "--receipt",
            path,
            "--checkout",
            checkout,
            "--requirements",
            expected,
        )
        assert validated.returncode == status, validated.stdout + validated.stderr


def test_source_mutation_prevents_success_and_remaining_checks(checkout):
    (checkout / "tests" / "test_selected.py").write_text(
        "from pathlib import Path\ndef test_mutation():\n    Path('src/brz2obsidian/__init__.py').write_text('VERSION = 42\\n')\n"
    )
    result, _, receipt = run(checkout, "--check", "pytest", "--check", "dependency")
    assert result.returncode == 2
    assert receipt["aggregate"] == "error"
    assert receipt["checks"][1]["status"] == "not_run"
    assert (
        receipt["snapshot_before"]["identity"] != receipt["snapshot_after"]["identity"]
    )


def test_large_both_streams_preserve_bytes_and_readable_logs(checkout):
    (checkout / "tests" / "conftest.py").write_text(
        "import sys\ndef pytest_sessionstart():\n"
        "    sys.stdout.write('é stdout ' * 30000)\n    sys.stdout.flush()\n"
        "    sys.stderr.write('漢 stderr ' * 30000)\n    sys.stderr.flush()\n",
        encoding="utf-8",
    )
    result, path, _receipt = run(
        checkout, "--check", "pytest", "--test", "tests/test_selected.py"
    )
    assert result.returncode == 0
    for stream, literal in (("stdout", "é stdout "), ("stderr", "漢 stderr ")):
        raw = (path.parent / f"pytest.{stream}.bin").read_bytes()
        assert len(raw) > 200000
        assert literal.encode("utf-8") in raw
        assert (path.parent / f"pytest.{stream}.log").read_bytes() == raw


def test_interrupted_execution_retains_partial_identity_and_original_output(checkout):
    import signal

    (checkout / "tests" / "test_selected.py").write_text(
        "from pathlib import Path\nimport os\nimport time\n"
        "def test_completed():\n    time.sleep(0.01)\n"
        "def test_wait():\n    Path('tmp/started').write_text(str(os.getpid()))\n    time.sleep(30)\n"
    )
    argv = [
        sys.executable,
        str(RUNNER),
        "run",
        "--checkout",
        str(checkout),
        "--python",
        sys.executable,
        "--check",
        "pytest",
        "--test",
        "tests/test_selected.py",
        "--check",
        "dependency",
        "--workers",
        "2",
    ]
    process = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )

    def ready_to_interrupt():
        if not (checkout / "tmp" / "started").exists():
            return False
        logs = list((checkout / "tmp" / "checks").glob("*/pytest-timings.jsonl"))
        if not logs:
            return False
        text = logs[0].read_text(encoding="utf-8")
        lines = text.splitlines()
        reports = []
        for index, line in enumerate(lines):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                if index == len(lines) - 1 and not text.endswith("\n"):
                    break
                raise
            if row["nodeid"] == "tests/test_selected.py::test_completed":
                reports.append(row["when"])
        return reports == ["setup", "call", "teardown"]

    deadline = time.monotonic() + 20
    while (
        not ready_to_interrupt()
        and time.monotonic() < deadline
        and process.poll() is None
    ):
        time.sleep(0.05)
    assert ready_to_interrupt()
    handle = None
    if os.name == "nt":
        import ctypes

        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
        kernel.WaitForSingleObject.restype = ctypes.c_ulong
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        pid = int((checkout / "tmp" / "started").read_text())
        handle = kernel.OpenProcess(0x00100000, 0, pid)
        assert handle, "The waiting worker must be alive before interruption"
    try:
        process.send_signal(
            signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM
        )
        stdout, stderr = process.communicate(timeout=15)
        if handle:
            assert kernel.WaitForSingleObject(handle, 2000) == 0
    finally:
        if handle:
            kernel.CloseHandle(handle)
    assert process.returncode == 3, (stdout + stderr).decode("utf-8", errors="replace")
    paths = list((checkout / "tmp" / "checks").glob("*/receipt.json"))
    assert len(paths) == 1
    receipt = json.loads(paths[0].read_text(encoding="utf-8"))
    assert receipt["aggregate"] == "interrupted"
    assert receipt["checks"][0]["status"] == "interrupted"
    assert receipt["checks"][1]["status"] == "not_run"
    assert (paths[0].parent / "partial.json").is_file()
    timings = [
        json.loads(line)
        for line in (paths[0].parent / "pytest-timings.jsonl").read_text().splitlines()
    ]
    completed = [
        row
        for row in timings
        if row["nodeid"] == "tests/test_selected.py::test_completed"
    ]
    assert [row["when"] for row in completed] == ["setup", "call", "teardown"]
    assert all(row["outcome"] == "passed" for row in completed)
    assert completed[1]["duration"] > 0


def test_failed_pytest_keeps_original_exception_and_later_dependency_pass(checkout):
    (checkout / "tests" / "test_selected.py").write_text(
        "def test_failure():\n    raise OSError(13, 'original é permission diagnostic')\n",
        encoding="utf-8",
    )
    result, path, receipt = run(
        checkout, "--check", "pytest", "--check", "dependency", "--workers", "2"
    )
    assert result.returncode == 1
    assert receipt["aggregate"] == "failed"
    assert [row["status"] for row in receipt["checks"]] == ["failed", "passed"]
    assert "original é permission diagnostic" in result.stdout
    expected = requirements(
        checkout,
        [pytest_requirement("focused", ["tests/test_selected.py"])],
        receipt["environment"],
    )
    refused = command(
        "validate",
        "--receipt",
        path,
        "--checkout",
        checkout,
        "--requirements",
        expected,
    )
    assert refused.returncode == 2
    intact_failure = command(
        "validate",
        "--receipt",
        path,
        "--checkout",
        checkout,
        "--requirements",
        expected,
        "--allow-failed",
    )
    assert intact_failure.returncode == 0, intact_failure.stdout + intact_failure.stderr


def test_inherited_pytest_options_cannot_narrow_declared_selection(
    checkout, monkeypatch
):
    monkeypatch.setenv(
        "PYTEST_ADDOPTS", "-k nonexistent_test --basetemp=tmp/unsafe-shared"
    )
    monkeypatch.setenv("PYTEST_PLUGINS", "missing_injected_plugin")
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw9")
    monkeypatch.setenv("PYTEST_XDIST_WORKER_COUNT", "2")
    result, _, receipt = run(
        checkout, "--check", "pytest", "--test", "tests/test_selected.py"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert receipt["checks"][0]["counts"]["passed"] == 1
    assert os.environ["PYTEST_PLUGINS"] == "missing_injected_plugin"
    assert "nonexistent_test" in os.environ["PYTEST_ADDOPTS"]
    assert not (checkout / "tmp" / "unsafe-shared").exists()


def test_selector_file_receipt_preserves_scope_and_refuses_altered_evidence(checkout):
    relative = "tests/é selected/test_transport.py"
    target = checkout / relative
    target.parent.mkdir()
    target.write_text(
        'import pytest\n\n\n@pytest.mark.parametrize("value", ["alpha", "beta"], '
        'ids=["alpha " * 2900, "beta " * 3500])\n'
        'def test_selected(value):\n    assert value in ("alpha", "beta")\n',
        encoding="utf-8",
    )
    (checkout / "tests" / "test_excluded.py").write_text(
        'def test_excluded():\n    raise AssertionError("excluded discovery ran")\n',
        encoding="utf-8",
    )
    selectors = [
        f"{relative}::test_selected[{'alpha ' * 2900}]",
        f"{relative}::test_selected[{'beta ' * 3500}]",
    ]
    assert sum(len(node) for node in selectors) > 32767
    assert all(len(node + " (teardown)") < 32767 for node in selectors)
    source = checkout / "tmp" / "requested é selection.json"
    source.parent.mkdir()
    original_input = (
        json.dumps(selectors, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    source.write_bytes(original_input)
    keyword = "selected and not excluded"
    marker = "parametrize and not skip"
    result, path, receipt = run(
        checkout,
        "--check",
        "pytest",
        "--tests-file",
        source,
        "-k",
        keyword,
        "-m",
        marker,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    selected = receipt["checks"][0]
    assert selected["counts"]["passed"] == 2
    assert selected["counts"]["executed_nodes"] == selectors
    assert selected["selection"]["keyword"] == keyword
    assert selected["selection"]["marker"] == marker
    archived = path.parent / "selectors.json"
    assert archived.read_bytes() == original_input
    if os.name == "nt":
        argument_path = path.parent / "pytest.args"
        assert argument_path.read_bytes() == ("\n".join(selectors) + "\n").encode(
            "utf-8"
        )
        assert "@" + str(argument_path) in selected["argv"]
        assert all(node not in selected["argv"] for node in selectors)
    else:
        assert "pytest_args" not in selected
        assert all(node in selected["argv"] for node in selectors)
    expected = requirements(
        checkout,
        [pytest_requirement("focused", selectors, keyword=keyword, marker=marker)],
        receipt["environment"],
    )
    original_receipt = path.read_bytes()
    originals = {archived: original_input}
    if os.name == "nt":
        originals[argument_path] = argument_path.read_bytes()

    def restore():
        path.write_bytes(original_receipt)
        source.write_bytes(original_input)
        for filename, raw in originals.items():
            filename.write_bytes(raw)

    def observe(label, exit_code):
        observed = command(
            "validate",
            "--receipt",
            path,
            "--checkout",
            checkout,
            "--requirements",
            expected,
        )
        output = observed.stdout + observed.stderr
        (checkout / "tmp" / f"validate-{label}.log").write_text(
            output, encoding="utf-8"
        )
        assert observed.returncode == exit_code, output

    def replace_bytes(field, raw):
        altered = json.loads(original_receipt)
        row = altered["checks"][0]
        facts = row[field]
        (path.parent / facts["path"]).write_bytes(raw)
        for item in (facts, *row["evidence"]):
            if item["path"] == facts["path"]:
                item.update(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        path.write_text(json.dumps(altered), encoding="utf-8")

    try:
        # Validation is self-contained even if the original external input changes.
        source.write_bytes(b"changed after execution")
        observe("accepted-archived-input", 0)
        restore()

        archived.unlink()
        observe("missing-input", 2)
        restore()

        archived.write_bytes(original_input + b" ")
        observe("changed-bytes", 2)
        restore()

        altered = json.loads(original_receipt)
        altered["checks"][0]["selector_input"]["path"] = "copied-selectors.json"
        path.write_text(json.dumps(altered), encoding="utf-8")
        (path.parent / "copied-selectors.json").write_bytes(original_input)
        observe("wrong-fixed-path", 2)
        restore()

        altered = json.loads(original_receipt)
        altered["checks"][0]["selector_input"]["role"] = "pytest_args"
        path.write_text(json.dumps(altered), encoding="utf-8")
        observe("wrong-role", 2)
        restore()

        # Matching replacement hashes cannot hide a different complete selection.
        other_selector = "tests/test_selected.py::test_selected"
        replace_bytes("selector_input", json.dumps([other_selector]).encode("utf-8"))
        observe("input-scope-disagreement", 2)
        restore()

        if os.name == "nt":
            replace_bytes("pytest_args", (other_selector + "\n").encode("utf-8"))
            observe("argument-scope-disagreement", 2)
            restore()
    finally:
        restore()
