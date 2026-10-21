"""Exercise maintained coverage orchestration through its public command."""

import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "tools" / "coverage_suite.py"


@pytest.fixture
def coverage_checkout(tmp_path):
    pytest.importorskip("PySide6")
    root = tmp_path / "coverage example"
    (root / "tools").mkdir(parents=True)
    for name in ("check.py", "check_pytest.py", "coverage_report.py"):
        shutil.copy2(ROOT / "tools" / name, root / "tools" / name)
    for package, yes, no in (
        ("brz2obsidian", "yes", "no"),
        ("brz2obsidian_ui", "open", "closed"),
    ):
        target = root / "src" / package
        target.mkdir(parents=True)
        (target / "__init__.py").write_text("", encoding="utf-8")
        (target / "decisions.py").write_text(
            f'def choose(value):\n    if value:\n        return "{yes}"\n    return "{no}"\n',
            encoding="utf-8",
        )
    (root / "tests").mkdir()
    (root / "tests" / "test_decisions.py").write_text(
        (
            "import pytest\n\n"
            "from brz2obsidian.decisions import choose\n\n\n"
            "def test_yes():\n    assert choose(True) == 'yes'\n\n\n"
            "def test_all_choices():\n"
            "    from brz2obsidian_ui.decisions import choose as ui_choose\n\n"
            "    assert choose(False) == 'no'\n"
            "    assert ui_choose(True) == 'open'\n"
            "    assert ui_choose(False) == 'closed'\n\n\n"
            "@pytest.mark.gui\ndef test_gui():\n"
            "    from PySide6.QtWidgets import QApplication\n\n"
            "    app = QApplication.instance() or QApplication([])\n"
            "    assert app.platformName() == 'offscreen'\n"
        ).replace("'", '"'),
        encoding="utf-8",
    )
    (root / "tools" / "test-suite.json").write_text(
        json.dumps({"schema_version": 1, "selectors": ["tests/test_decisions.py"]}),
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\nmarkers = ["gui: GUI checks"]\n'
        '[tool.ruff]\ntarget-version = "py314"\n',
        encoding="utf-8",
    )
    (root / ".gitignore").write_text("tmp/\n__pycache__/\n", encoding="utf-8")
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
            "coverage example",
        ),
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def invoke(root, *args):
    return subprocess.run(
        [
            sys.executable,
            str(SUITE),
            "--checkout",
            str(root),
            "--python",
            sys.executable,
            *args,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def summary(root):
    paths = list((root / "tmp" / "coverage-suite").glob("*/summary.json"))
    assert len(paths) == 1
    return json.loads(paths[0].read_text(encoding="utf-8")), paths[0].parent


def test_default_command_validates_four_checks_and_reports_all_production(
    coverage_checkout,
):
    decisions = coverage_checkout / "src" / "brz2obsidian" / "decisions.py"
    with decisions.open("a", encoding="utf-8") as handle:
        handle.write(
            "\n\nclass Decision:\n    def choose(self, value):\n        return choose(value)\n"
        )
    (decisions.parent / "unexecuted.py").write_text("answer = 42\n", encoding="utf-8")
    tests = coverage_checkout / "tests" / "test_decisions.py"
    tests.write_text(
        tests.read_text(encoding="utf-8").replace(
            '    assert choose(True) == "yes"\n',
            '    assert choose(True) == "yes"\n'
            "    from brz2obsidian.decisions import Decision\n\n"
            '    assert Decision().choose(True) == "yes"\n',
        ),
        encoding="utf-8",
    )
    result = invoke(coverage_checkout)
    assert result.returncode == 0, result.stdout + result.stderr
    report, output = summary(coverage_checkout)
    assert report["status"] == "passed"
    assert report["measurement"] == "default suite"
    assert report["lines"] == {"covered": 11, "total": 12, "percent": 100 * 11 / 12}
    assert report["branches"] == {"covered": 4, "total": 4, "percent": 100.0}
    assert report["production_files"] == 5
    assert report["elapsed_seconds"] < 60
    assert 0 < report["pytest_seconds"] < report["runner_seconds"]
    assert report["test_counts"]["passed"] == 3
    assert report["test_counts"]["gui_executed"] == 1
    requirements = json.loads(
        (output / "requirements.json").read_text(encoding="utf-8")
    )
    assert {row["id"] for row in requirements["checks"]} == {
        "pytest",
        "lint",
        "format",
        "dependency",
    }
    assert requirements["checks"][0]["require_gui"] is True
    assert "VALID:" in (output / "validate.log").read_text(encoding="utf-8")
    assert any("test_yes" in row["context"] for row in report["contexts"])
    assert (output / "html" / "index.html").is_file()
    raw = json.loads((output / "coverage.json").read_text(encoding="utf-8"))
    files = {Path(name).as_posix(): details for name, details in raw["files"].items()}
    decision = files["src/brz2obsidian/decisions.py"]
    assert raw["meta"]["show_contexts"] is True
    assert raw["meta"]["context_scope"] == "file"
    assert decision["contexts"]["3"] == ["test_decisions.test_yes"]
    assert decision["contexts"]["4"] == ["test_decisions.test_all_choices"]
    assert decision["contexts"]["9"] == ["test_decisions.test_yes"]
    assert decision["contexts"]["1"] == [""]
    assert sorted(decision["executed_branches"]) == [[2, 3], [2, 4]]
    assert decision["missing_branches"] == []
    assert decision["functions"]["choose"]["summary"]["covered_branches"] == 2
    assert decision["functions"]["Decision.choose"]["executed_lines"] == [9]
    assert decision["classes"]["Decision"]["executed_lines"] == [9]
    assert decision["classes"]["Decision"]["summary"]["num_statements"] == 1
    for regions in (decision["functions"], decision["classes"]):
        assert all("contexts" not in region for region in regions.values())
    unexecuted = files["src/brz2obsidian/unexecuted.py"]
    assert unexecuted["contexts"] == {} and unexecuted["executed_lines"] == []
    assert unexecuted["missing_lines"] == [1]


def test_focused_measurement_uses_all_source_denominator_and_rejects_threshold(
    coverage_checkout,
):
    result = invoke(
        coverage_checkout,
        "--test",
        "tests/test_decisions.py::test_yes",
        "--min-branch",
        "50",
        "--measurement-intent",
        "known four-branch example",
    )
    assert result.returncode == 1, result.stdout + result.stderr
    report, output = summary(coverage_checkout)
    assert report["status"] == "failed"
    assert report["measurement"] == "focused selection; partial suite evidence"
    assert report["branches"] == {"covered": 1, "total": 4, "percent": 25.0}
    assert report["lines"] == {"covered": 3, "total": 8, "percent": 37.5}
    assert "branch threshold" in report["error"]
    requirements = json.loads(
        (output / "requirements.json").read_text(encoding="utf-8")
    )
    assert [row["id"] for row in requirements["checks"]] == ["pytest"]
    assert requirements["checks"][0]["require_gui"] is False


def test_measurement_override_needs_explicit_intent(tmp_path):
    result = invoke(tmp_path, "--min-branch", "1")
    assert result.returncode == 2
    assert "--measurement-intent" in result.stderr
    assert not (tmp_path / "tmp").exists()


def test_source_change_during_reporting_rejects_success(coverage_checkout):
    stopped = threading.Event()
    changed = threading.Event()

    def change_after_html_starts():
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not stopped.is_set():
            if list((coverage_checkout / "tmp" / "coverage-suite").glob("*/html.log")):
                source = coverage_checkout / "src" / "brz2obsidian" / "decisions.py"
                with source.open("a", encoding="utf-8") as handle:
                    handle.write(
                        "\n# Source changed after the initial receipt validation.\n"
                    )
                changed.set()
                return
            stopped.wait(0.01)

    editor = threading.Thread(target=change_after_html_starts)
    editor.start()
    try:
        result = invoke(
            coverage_checkout, "--test", "tests/test_decisions.py::test_yes"
        )
    finally:
        stopped.set()
        editor.join(timeout=1)
    assert not editor.is_alive()
    assert changed.is_set(), "The public reporting phase was not reached"
    assert result.returncode == 1, result.stdout + result.stderr
    report, output = summary(coverage_checkout)
    assert report["status"] == "failed"
    assert "stale or changed" in (output / "validate-final.log").read_text(
        encoding="utf-8"
    )
