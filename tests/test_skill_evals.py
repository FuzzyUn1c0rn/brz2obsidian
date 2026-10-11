"""Observable evaluation guards reject side effects and incomplete evidence."""

import importlib.util
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "skill_evals.py"
SPEC = importlib.util.spec_from_file_location("skill_evals", SCRIPT)
EVALS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALS)


def case(**overrides):
    return {
        "id": "fixture",
        "allowed_writes": [],
        "expect_no_questions": True,
        "rubric": ["Answer the requested question"],
        **overrides,
    }


def answer(**overrides):
    return {
        "answer": "Supported format is JSON",
        "questions": [],
        "skills_used": [],
        **overrides,
    }


def test_read_only_guard_detects_modified_created_and_deleted_files():
    before = {"source.py": "original", "docs.md": "original"}
    after = {"source.py": "modified", "report.md": "created"}
    result = EVALS.grade(case(), before, after, [], answer(), 0)
    assert not result["guards_passed"]
    assert result["changed_files"] == ["docs.md", "report.md", "source.py"]


def test_missing_artifact_and_failed_or_incomplete_run_cannot_pass():
    required = case(allowed_writes=["report.md"], required_writes=["report.md"])
    result = EVALS.grade(required, {"report.md": "before"}, {}, [], answer(), 0)
    assert not result["guards"]["required_artifacts"]
    assert not EVALS.grade(case(), {}, {}, [], {}, 0)["guards_passed"]
    assert not EVALS.grade(case(), {}, {}, [], answer(), 124)["guards_passed"]


def test_actual_commands_and_questions_establish_routing_and_scope_guards():
    request = case(
        must_read_skills=["research"], forbidden_skill_reads=["domain-modeling"]
    )
    events = [
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": r"Get-Content .agents\\skills\\research\\SKILL.md",
            },
        }
    ]
    passed = EVALS.grade(request, {}, {}, events, answer(), 0)
    assert passed["guards_passed"]
    assert passed["semantic_review"] == "pending"
    events.append(
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": "python tools/check.py run",
            },
        }
    )
    result = EVALS.grade(
        request, {}, {}, events, answer(questions=["Approve again?"]), 0
    )
    assert not result["guards"]["bounded_checks"]
    assert not result["guards"]["no_redundant_questions"]


def test_fixture_has_its_own_git_root_and_metadata_does_not_count_as_artifact_changes(
    tmp_path,
):
    workspace = tmp_path / "fixture"
    EVALS.prepare(workspace)
    result = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert Path(result.stdout.strip()).resolve() == workspace.resolve()
    result = subprocess.run(
        ["git", "-C", str(workspace), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == ""
    files = EVALS.snapshot(workspace)
    assert "GLOSSARY.md" in files
    assert not any(name.startswith(".git/") for name in files)
