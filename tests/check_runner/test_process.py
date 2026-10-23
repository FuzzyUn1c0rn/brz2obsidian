"""The maintained check command is tested only through its public processes."""

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
        "import brz2obsidian\n"
        "import pytest\n"
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
        "from pathlib import Path\nimport time\n"
        "def test_completed():\n    time.sleep(0.01)\n"
        "def test_wait():\n    Path('tmp/started').write_text('started')\n    time.sleep(30)\n"
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
    ]
    process = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    deadline = time.monotonic() + 20
    while (
        not (checkout / "tmp" / "started").exists()
        and time.monotonic() < deadline
        and process.poll() is None
    ):
        time.sleep(0.05)
    assert (checkout / "tmp" / "started").exists()
    process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
    stdout, stderr = process.communicate(timeout=15)
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
    result, path, receipt = run(checkout, "--check", "pytest", "--check", "dependency")
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
    result, _, receipt = run(
        checkout, "--check", "pytest", "--test", "tests/test_selected.py"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert receipt["checks"][0]["counts"]["passed"] == 1
    assert os.environ["PYTEST_PLUGINS"] == "missing_injected_plugin"
    assert "nonexistent_test" in os.environ["PYTEST_ADDOPTS"]
    assert not (checkout / "tmp" / "unsafe-shared").exists()
