"""The maintained check command is tested only through its public processes."""

import json
import os
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
    result, path, receipt = run(
        checkout, "--check", "pytest", "--test", "tests/test_selected.py"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    assert receipt["aggregate"] == "passed"
    assert receipt["checks"][0]["counts"]["passed"] == 1
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


@pytest.mark.parametrize(
    "defect,check,diagnostic",
    [
        ("unused import", "lint", "F401"),
        ("format", "format", "would be reformatted"),
    ],
)
def test_real_ruff_failure_cannot_be_erased_by_later_check(
    checkout, defect, check, diagnostic
):
    target = checkout / "tests" / "test_selected.py"
    target.write_text(
        "import pathlib\n\ndef test_ok():\n    assert True\n"
        if defect == "unused import"
        else "def test_ok( ):\n assert True\n"
    )
    result, _, receipt = run(checkout, "--check", check, "--check", "dependency")
    assert result.returncode == 1
    assert diagnostic in result.stdout + result.stderr
    assert [row["status"] for row in receipt["checks"]] == ["failed", "passed"]


@pytest.mark.parametrize(
    "fault",
    [
        "altered_log",
        "missing_log",
        "truncated_json",
        "wrong_source",
        "wrong_checkout",
        "wrong_environment",
        "full_claim",
        "missing_check",
        "unknown_schema",
        "unknown_selector",
        "altered_args",
    ],
)
def test_public_validation_refuses_damaged_stale_or_insufficient_evidence(
    checkout, fault, tmp_path
):
    result, receipt_path, receipt = run(
        checkout, "--check", "pytest", "--test", "tests/test_selected.py"
    )
    assert result.returncode == 0
    required = [pytest_requirement("focused", ["tests/test_selected.py"])]
    root = checkout
    mode = receipt["environment"]
    if fault in ("altered_log", "missing_log"):
        log = receipt_path.parent / receipt["checks"][0]["evidence"][0]["path"]
        log.unlink() if fault == "missing_log" else log.write_bytes(
            b"substituted output"
        )
    elif fault == "truncated_json":
        receipt_path.write_text('{"schema_version":')
    elif fault == "wrong_source":
        (checkout / "src" / "brz2obsidian" / "__init__.py").write_text(
            'VERSION = "changed"\n'
        )
    elif fault == "wrong_checkout":
        root = tmp_path / "other"
        shutil.copytree(checkout, root)
    elif fault == "wrong_environment":
        mode = "gui" if mode == "base" else "base"
    elif fault == "full_claim":
        required = [pytest_requirement()]
    elif fault == "missing_check":
        required += [{"id": "lint"}]
    elif fault == "unknown_schema":
        receipt["schema_version"] = 99
        receipt_path.write_text(json.dumps(receipt))
    elif fault == "altered_args":
        receipt["checks"][0]["argv"] += ["-k", "silently_narrowed"]
        receipt_path.write_text(json.dumps(receipt))
    else:
        required = [{"id": "invented"}]
    expected = requirements(checkout, required, mode)
    refused = command(
        "validate",
        "--receipt",
        receipt_path,
        "--checkout",
        root,
        "--requirements",
        expected,
    )
    assert refused.returncode == 2, refused.stdout + refused.stderr


def test_unchanged_dirty_snapshot_binds_later_commit_and_explicit_equivalent_reuse(
    checkout, tmp_path
):
    (checkout / "tests" / "test_selected.py").write_text(
        "def test_precommit():\n    assert True\n"
    )
    result, path, receipt = run(
        checkout, "--check", "pytest", "--test", "tests/test_selected.py"
    )
    assert result.returncode == 0
    original = path.read_bytes()
    subprocess.run(["git", "-C", str(checkout), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-m",
            "unchanged contents",
        ],
        check=True,
        capture_output=True,
    )
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
    equivalent = tmp_path / "equivalent checkout"
    commit = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    committed = command(
        "validate",
        "--receipt",
        path,
        "--checkout",
        checkout,
        "--requirements",
        expected,
        "--ref",
        commit,
    )
    assert committed.returncode == 0, committed.stdout + committed.stderr
    shutil.copytree(
        checkout, equivalent, ignore=shutil.ignore_patterns("tmp", "__pycache__")
    )
    reused = command(
        "validate",
        "--receipt",
        path,
        "--checkout",
        equivalent,
        "--requirements",
        expected,
        "--reuse-reason",
        "same tested normalized files, no fresh execution claimed",
    )
    assert reused.returncode == 0, reused.stdout + reused.stderr
    assert path.read_bytes() == original


def test_full_default_suite_does_not_satisfy_undiscovered_external_test(checkout):
    extra = checkout / ".agents" / "test_external.py"
    extra.parent.mkdir()
    extra.write_text("def test_external():\n    assert True\n")
    result, path, receipt = run(checkout, "--check", "pytest")
    if receipt["environment"] == "gui":
        assert result.returncode == 1  # fixture has no marked GUI coverage
        return
    assert result.returncode == 0
    expected = requirements(
        checkout,
        [pytest_requirement("focused", [".agents/test_external.py"])],
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


@pytest.mark.parametrize(
    "extra",
    [
        ("--python", "C:/missing/python.exe"),
        ("--test", "does-not-exist.py"),
        ("-k", "no_such_test"),
        ("--require-gui",),
    ],
)
def test_setup_or_zero_selection_never_qualifies(checkout, extra):
    result = command(
        "run",
        "--checkout",
        checkout,
        "--python",
        sys.executable,
        "--environment",
        "base",
        "--check",
        "pytest",
        *extra,
    )
    assert result.returncode != 0


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


def test_receipt_counts_must_match_preserved_execution_evidence(checkout):
    result, path, receipt = run(
        checkout, "--check", "pytest", "--test", "tests/test_selected.py"
    )
    assert result.returncode == 0
    receipt["checks"][0]["counts"]["gui_executed"] = 100
    path.write_text(json.dumps(receipt))
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


def test_concurrent_runs_keep_separate_test_cache_and_evidence_directories(checkout):
    (checkout / "tests" / "test_selected.py").write_text(
        "import time\ndef test_bounded(tmp_path):\n    (tmp_path / 'own.txt').write_text('owned')\n    time.sleep(0.4)\n"
    )
    argv = [
        sys.executable,
        str(RUNNER),
        "run",
        "--checkout",
        str(checkout),
        "--python",
        sys.executable,
        "--environment",
        "auto",
        "--check",
        "pytest",
        "--test",
        "tests/test_selected.py",
    ]
    processes = [
        subprocess.Popen(
            argv, cwd=ROOT.parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        for _ in range(2)
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=45)
        assert process.returncode == 0, (stdout + stderr).decode("utf-8")
    paths = list((checkout / "tmp" / "checks").glob("*/receipt.json"))
    assert len(paths) == 2
    receipts = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert receipts[0]["run_id"] != receipts[1]["run_id"]
    for path, receipt in zip(paths, receipts, strict=True):
        assert (path.parent / "pytest").is_dir()
        assert (path.parent / "pytest-cache").is_dir()
        assert str(path.parent / "ruff-cache") == receipt["settings"]["RUFF_CACHE_DIR"]
        assert all(
            (path.parent / item["path"]).is_file()
            for item in receipt["checks"][0]["evidence"]
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
        "from pathlib import Path\nimport time\ndef test_wait():\n    Path('tmp/started').write_text('started')\n    time.sleep(30)\n"
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


def test_isolated_environment_missing_tool_and_actual_dependency_inconsistency(
    checkout,
):
    isolated = checkout / ".venv" / "é isolated environment"
    subprocess.run(
        [sys.executable, "-m", "venv", str(isolated)],
        check=True,
        capture_output=True,
        timeout=45,
    )
    python = isolated / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    missing = command(
        "run",
        "--checkout",
        checkout,
        "--python",
        python,
        "--environment",
        "base",
        "--check",
        "pytest",
    )
    assert missing.returncode == 2
    assert "pytest" in missing.stderr
    library = isolated / (
        "Lib/site-packages"
        if os.name == "nt"
        else f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    )
    metadata = library / "controlled_inconsistent-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: controlled-inconsistent\nVersion: 1.0\nRequires-Dist: missing-check-runner-control>=1\n"
    )
    failed = command(
        "run",
        "--checkout",
        checkout,
        "--python",
        python,
        "--environment",
        "base",
        "--check",
        "dependency",
    )
    assert failed.returncode == 1
    assert "missing-check-runner-control" in failed.stdout
    shutil.rmtree(metadata)
    restored = command(
        "run",
        "--checkout",
        checkout,
        "--python",
        python,
        "--environment",
        "base",
        "--check",
        "dependency",
    )
    assert restored.returncode == 0, restored.stdout + restored.stderr


def test_explicit_environment_and_required_gui_execution(checkout):
    (checkout / "tests" / "test_gui.py").write_text(
        "import pytest\n@pytest.mark.gui\ndef test_gui():\n    pytest.importorskip('PySide6')\n    from PySide6.QtWidgets import QApplication, QLabel\n    app = QApplication.instance() or QApplication([])\n    label = QLabel('real GUI execution')\n    assert app is not None and label.text() == 'real GUI execution'\n"
    )
    result, path, receipt = run(checkout, "--check", "pytest")
    assert result.returncode == 0, result.stdout + result.stderr
    counts = receipt["checks"][0]["counts"]
    expected = requirements(checkout, [pytest_requirement(require_gui=True)], "gui")
    validated = command(
        "validate",
        "--receipt",
        path,
        "--checkout",
        checkout,
        "--requirements",
        expected,
    )
    if receipt["environment"] == "base":
        assert counts["skipped"] == 1 and counts["gui_executed"] == 0
        assert validated.returncode == 2
        wrong = "gui"
    else:
        assert counts["gui_executed"] == 1 and counts["passed"] == 2
        assert validated.returncode == 0
        wrong = "base"
    refused = command(
        "run",
        "--checkout",
        checkout,
        "--python",
        sys.executable,
        "--environment",
        wrong,
        "--check",
        "dependency",
    )
    assert refused.returncode == 2


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


def test_on_disk_line_ending_change_during_execution_invalidates_receipt(checkout):
    (checkout / "tests" / "test_selected.py").write_text(
        "from pathlib import Path\ndef test_change():\n"
        "    p = Path('src/brz2obsidian/__init__.py')\n"
        "    contents = p.read_bytes()\n"
        "    normalized = contents.replace(b'\\r\\n', b'\\n')\n"
        "    p.write_bytes(normalized if contents != normalized else normalized.replace(b'\\n', b'\\r\\n'))\n"
    )
    result, _, receipt = run(checkout, "--check", "pytest", "--check", "dependency")
    assert result.returncode == 2
    assert receipt["checks"][1]["status"] == "not_run"


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


def test_two_different_checkouts_override_shared_editable_installation(
    checkout, tmp_path
):
    second = tmp_path / "漢 second checkout"
    shutil.copytree(
        checkout, second, ignore=shutil.ignore_patterns("tmp", "__pycache__")
    )
    (second / "src" / "brz2obsidian" / "__init__.py").write_text('VERSION = "second"\n')
    (second / "tests" / "test_selected.py").write_text(
        "import brz2obsidian\ndef test_second():\n    assert brz2obsidian.VERSION == 'second'\n"
    )
    first_result, _, first_receipt = run(
        checkout, "--check", "pytest", "--test", "tests/test_selected.py"
    )
    second_result, _, second_receipt = run(
        second, "--check", "pytest", "--test", "tests/test_selected.py"
    )
    assert first_result.returncode == second_result.returncode == 0
    assert (
        first_receipt["snapshot_before"]["identity"]
        != second_receipt["snapshot_before"]["identity"]
    )
    assert Path(
        second_receipt["interpreter"]["imports"]["brz2obsidian"]
    ).is_relative_to(second)


def test_runner_from_other_content_cannot_assess_selected_checkout(checkout):
    with (checkout / "tools" / "check.py").open("a", encoding="utf-8") as target:
        target.write("\n# distinguishable other runner\n")
    result, _, receipt = run(checkout, "--check", "dependency")
    assert result.returncode == 2
    assert receipt["checks"][0]["status"] == "not_run"
    assert "differs" in result.stderr


@pytest.mark.parametrize("focused", [False, True])
def test_skipped_node_cannot_satisfy_requirement_for_its_execution(checkout, focused):
    (checkout / "tests" / "test_selected.py").write_text(
        "import pytest\ndef test_passed():\n    assert True\n"
        "def test_skipped():\n    pytest.skip('deliberate unavailable observation')\n"
        "@pytest.mark.gui\ndef test_actual_gui():\n"
        "    pytest.importorskip('PySide6')\n"
        "    from PySide6.QtCore import qVersion\n"
        "    assert qVersion()\n"
    )
    selectors = (
        ["tests/test_selected.py::test_passed", "tests/test_selected.py::test_skipped"]
        if focused
        else ["tests/test_selected.py::test_skipped"]
    )
    result, path, receipt = run(
        checkout,
        "--check",
        "pytest",
        *[value for selector in selectors for value in ("--test", selector)]
        if focused
        else [],
    )
    assert result.returncode == 0
    expected = requirements(
        checkout,
        [pytest_requirement("focused", selectors)],
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


@pytest.mark.skipif(os.name != "nt", reason="Windows relative path spelling")
def test_windows_selector_spelling_retains_valid_execution_scope(checkout):
    result, path, receipt = run(
        checkout, "--check", "pytest", "--test", "tests\\test_selected.py"
    )
    assert result.returncode == 0
    expected = requirements(
        checkout,
        [pytest_requirement("focused", ["tests\\test_selected.py"])],
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


@pytest.mark.parametrize("expression", ["keyword", "marker"])
def test_full_receipt_does_not_infer_execution_for_unmatched_expression(
    checkout, expression
):
    (checkout / "tests" / "test_gui.py").write_text(
        "import pytest\n@pytest.mark.gui\ndef test_gui():\n    pytest.importorskip('PySide6')\n    from PySide6.QtCore import qVersion\n    assert qVersion()\n"
    )
    result, path, receipt = run(checkout, "--check", "pytest")
    assert result.returncode == 0
    required = pytest_requirement(
        "focused", **{expression: "nonexistent_requested_selection"}
    )
    expected = requirements(checkout, [required], receipt["environment"])
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
