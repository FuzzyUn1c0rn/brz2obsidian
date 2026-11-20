"""Exercise maintained coverage orchestration through its public command."""

import importlib.metadata
import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from coverage import CoverageData

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "tools" / "coverage_suite.py"


@pytest.fixture
def coverage_checkout(tmp_path):
    pytest.importorskip("PySide6")
    root = tmp_path / "coverage example"
    (root / "tools").mkdir(parents=True)
    for name in ("check.py", "check_lint.py", "check_pytest.py", "coverage_report.py"):
        shutil.copy2(ROOT / "tools" / name, root / "tools" / name)
    (root / "tools" / "comment-baseline.json").write_text("{}\n", encoding="utf-8")
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
    (root / "tmp").mkdir()
    (root / "tests" / "test_decisions.py").write_text(
        (
            "import os\nfrom pathlib import Path\n\n"
            "from brz2obsidian.decisions import choose\n\n\n"
            "def test_yes():\n    assert choose(True) == 'yes'\n"
            "    Path('tmp/yes-pid').write_text(str(os.getpid()))\n"
        ).replace("'", '"'),
        encoding="utf-8",
    )
    (root / "tests" / "test_other.py").write_text(
        (
            "import os\nfrom pathlib import Path\n\n"
            "from brz2obsidian.decisions import choose\n\n\n"
            "def test_no():\n"
            "    assert choose(False) == 'no'\n"
            "    Path('tmp/other-pid').write_text(str(os.getpid()))\n"
        ).replace("'", '"'),
        encoding="utf-8",
    )
    (root / "tests" / "test_ui.py").write_text(
        (
            "import os\nfrom pathlib import Path\n\n"
            "from brz2obsidian_ui.decisions import choose\n\n\n"
            "def test_ui_choices():\n"
            "    assert choose(True) == 'open'\n"
            "    assert choose(False) == 'closed'\n"
            "    Path('tmp/ui-pid').write_text(str(os.getpid()))\n"
        ).replace("'", '"'),
        encoding="utf-8",
    )
    (root / "tests" / "test_gui.py").write_text(
        (
            "import os\nfrom pathlib import Path\n\nimport pytest\n\n\n"
            "@pytest.mark.gui\ndef test_gui():\n"
            "    from PySide6.QtWidgets import QApplication\n\n"
            "    app = QApplication.instance() or QApplication([])\n"
            "    assert app.platformName() == 'offscreen'\n"
            "    Path('tmp/gui-pid').write_text(str(os.getpid()))\n"
        ).replace("'", '"'),
        encoding="utf-8",
    )
    (root / "tools" / "test-suite.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "selectors": [
                    "tests/test_decisions.py",
                    "tests/test_other.py",
                    "tests/test_gui.py",
                    "tests/test_ui.py",
                ],
            }
        ),
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
    assert report["timeout_seconds"] is None
    assert report["status"] == "passed"
    assert report["measurement"] == "default suite"
    assert report["lines"] == {"covered": 11, "total": 12, "percent": 100 * 11 / 12}
    assert report["branches"] == {"covered": 4, "total": 4, "percent": 100.0}
    assert report["production_files"] == 5
    assert report["elapsed_seconds"] > 0
    assert 0 < report["pytest_seconds"] < report["runner_seconds"]
    assert report["test_counts"]["passed"] == 4
    assert report["test_counts"]["collected"] == 4
    assert report["test_counts"]["gui_executed"] == 1
    assert report["test_counts"]["executed_nodes"] == [
        "tests/test_decisions.py::test_yes",
        "tests/test_gui.py::test_gui",
        "tests/test_other.py::test_no",
        "tests/test_ui.py::test_ui_choices",
    ]
    assert (
        len(
            {
                (coverage_checkout / "tmp" / name).read_text()
                for name in ("yes-pid", "other-pid", "gui-pid", "ui-pid")
            }
        )
        == 4
    )
    receipt = json.loads(Path(report["receipt"]).read_text(encoding="utf-8"))
    selected = next(row for row in receipt["checks"] if row["id"] == "pytest")
    assert selected["selection"]["workers"] == 4
    parallel = selected["argv"].index("-n")
    assert selected["argv"][parallel : parallel + 5] == [
        "-n",
        "4",
        "--dist=loadscope",
        "--no-loadscope-reorder",
        "--max-worker-restart=0",
    ]
    for package in ("pytest-xdist", "execnet"):
        assert receipt["interpreter"]["tools"][package] == importlib.metadata.version(
            package
        )
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
    assert decision["contexts"]["4"] == ["test_other.test_no"]
    assert decision["contexts"]["9"] == ["test_decisions.test_yes"]
    assert decision["contexts"]["1"] == [""]
    assert sorted(decision["executed_branches"]) == [[2, 3], [2, 4]]
    assert decision["missing_branches"] == []
    ui_decision = files["src/brz2obsidian_ui/decisions.py"]
    assert ui_decision["contexts"]["3"] == ["test_ui.test_ui_choices"]
    assert ui_decision["contexts"]["4"] == ["test_ui.test_ui_choices"]
    assert decision["functions"]["choose"]["summary"]["covered_branches"] == 2
    assert decision["functions"]["Decision.choose"]["executed_lines"] == [9]
    assert decision["classes"]["Decision"]["executed_lines"] == [9]
    assert decision["classes"]["Decision"]["summary"]["num_statements"] == 1
    for regions in (decision["functions"], decision["classes"]):
        assert all("contexts" not in region for region in regions.values())
    unexecuted = files["src/brz2obsidian/unexecuted.py"]
    assert unexecuted["contexts"] == {} and unexecuted["executed_lines"] == []
    assert unexecuted["missing_lines"] == [1]

    retained = {}
    for path in output.glob(".coverage.*"):
        data = CoverageData(basename=str(path))
        data.read()
        for context in data.measured_contexts():
            data.set_query_context(context)
            for filename in data.measured_files():
                key = (Path(filename), context)
                retained.setdefault(key, set()).update(data.arcs(filename) or ())
    ui_decisions = coverage_checkout / "src" / "brz2obsidian_ui" / "decisions.py"
    assert (2, 3) in retained.get((decisions, "test_decisions.test_yes"), set())
    assert (2, 4) in retained.get((decisions, "test_other.test_no"), set())
    assert {(2, 3), (2, 4)} <= retained.get(
        (ui_decisions, "test_ui.test_ui_choices"), set()
    )


def test_focused_measurement_uses_all_source_denominator_and_rejects_threshold(
    coverage_checkout,
):
    result = invoke(
        coverage_checkout,
        "--test",
        "tests/test_decisions.py::test_yes",
        "--timeout",
        "4500",
        "--min-branch",
        "50",
        "--measurement-intent",
        "known four-branch example",
    )
    assert result.returncode == 1, result.stdout + result.stderr
    report, output = summary(coverage_checkout)
    assert report["status"] == "failed"
    assert report["timeout_seconds"] == 4500
    assert report["measurement"] == "focused selection; partial suite evidence"
    assert report["branches"] == {"covered": 1, "total": 4, "percent": 25.0}
    assert report["lines"] == {"covered": 3, "total": 8, "percent": 37.5}
    receipt = json.loads(Path(report["receipt"]).read_text(encoding="utf-8"))
    selected = receipt["checks"][0]
    assert set(selected["selection"]) == {
        "scope",
        "selectors",
        "keyword",
        "marker",
        "require_gui",
    }
    assert "-n" not in selected["argv"]
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


def test_ordinary_verification_accepts_explicit_timeout_above_900(coverage_checkout):
    result = invoke(coverage_checkout, "--timeout", "901")
    assert result.returncode == 0, result.stdout + result.stderr
    report, _ = summary(coverage_checkout)
    assert report["timeout_seconds"] == 901
    assert report["status"] == "passed"


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_timeout_must_be_positive_and_finite(tmp_path, value):
    result = invoke(tmp_path, "--timeout", value)
    assert result.returncode == 2
    assert "--timeout must be positive and finite" in result.stderr


def test_explicit_timeout_reports_failure(coverage_checkout):
    result = invoke(coverage_checkout, "--timeout", "0.001")
    assert result.returncode == 1, result.stdout + result.stderr
    report, _ = summary(coverage_checkout)
    assert report["status"] == "failed"
    assert "deadline" in report["error"].lower()
    assert report["timeout_seconds"] == 0.001


def test_source_change_during_reporting_rejects_success(coverage_checkout):
    stopped = threading.Event()
    changed = threading.Event()

    def change_after_html_starts():
        while not stopped.is_set():
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
        editor.join()
    assert not editor.is_alive()
    assert changed.is_set(), "The public reporting phase was not reached"
    assert result.returncode == 1, result.stdout + result.stderr
    report, output = summary(coverage_checkout)
    assert report["status"] == "failed"
    assert "stale or changed" in (output / "validate-final.log").read_text(
        encoding="utf-8"
    )


def test_long_maintained_selection_preserves_exact_scope_and_validates(
    coverage_checkout,
):
    """A long manifest remains the same public four-check coverage operation."""
    relative = "tests/é selected/test_many.py"
    target = coverage_checkout / relative
    target.parent.mkdir()
    names = [f"test_case_{index:04d}_" + "independent_" * 4 for index in range(400)]
    target.write_text(
        "from brz2obsidian.decisions import choose\n\n\n"
        + "\n\n".join(
            f'def {name}():\n    assert choose(True) == "yes"\n' for name in names
        ),
        encoding="utf-8",
    )
    (coverage_checkout / "tests" / "test_excluded_failure.py").write_text(
        "def test_excluded_failure():\n"
        '    raise AssertionError("excluded discovery ran")\n',
        encoding="utf-8",
    )
    manifest_path = coverage_checkout / "tools" / "test-suite.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["selectors"] += [f"{relative}::{name}" for name in names]
    selectors = manifest["selectors"]
    # This is a real unique selection beyond the native Windows command line,
    # not repeated arguments for the same test or a mocked process failure.
    assert len(selectors) == len(set(selectors)) == 404
    assert sum(len(node) for node in selectors) > 32767
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    result = invoke(coverage_checkout)
    assert result.returncode == 0, result.stdout + result.stderr
    report, _output = summary(coverage_checkout)
    assert report["status"] == "passed"
    assert report["measurement"] == "default suite"
    assert report["timeout_seconds"] is None
    assert report["minimum_branch_percent"] == 80
    assert report["production_files"] == 4
    assert report["branches"] == {
        "covered": 4,
        "total": 4,
        "percent": 100.0,
    }
    receipt_path = Path(report["receipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert {row["id"]: row["status"] for row in receipt["checks"]} == {
        "pytest": "passed",
        "lint": "passed",
        "format": "passed",
        "dependency": "passed",
    }
    selected = next(row for row in receipt["checks"] if row["id"] == "pytest")
    assert selected["selection"]["selectors"] == selectors
    assert selected["selection"]["keyword"] is None
    assert selected["selection"]["marker"] is None
    assert selected["selection"]["require_gui"] is True
    assert selected["selection"]["workers"] == 4
    assert selected["counts"]["collected"] == 404
    assert selected["counts"]["passed"] == 404
    assert selected["counts"]["failed"] == 0
    assert selected["counts"]["gui_executed"] == 1
    assert selected["counts"]["executed_nodes"] == sorted(
        [
            "tests/test_decisions.py::test_yes",
            "tests/test_other.py::test_no",
            "tests/test_gui.py::test_gui",
            "tests/test_ui.py::test_ui_choices",
            *(f"{relative}::{name}" for name in names),
        ]
    )
    # Independent requirements come from the requested manifest in this test,
    # not the coverage command's own generated requirements.
    expected = coverage_checkout / "tmp" / "independent-long-required.json"
    expected.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "environment": "gui",
                "checks": [
                    {
                        "id": "pytest",
                        "scope": "focused",
                        "selectors": selectors,
                        "keyword": None,
                        "marker": None,
                        "require_gui": True,
                    },
                    {"id": "lint"},
                    {"id": "format"},
                    {"id": "dependency"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    validated = subprocess.run(
        [
            sys.executable,
            str(coverage_checkout / "tools" / "check.py"),
            "validate",
            "--checkout",
            str(coverage_checkout),
            "--receipt",
            str(receipt_path),
            "--requirements",
            str(expected),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert validated.returncode == 0, validated.stdout + validated.stderr
    assert "excluded discovery ran" not in result.stdout + result.stderr
