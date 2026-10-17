"""Observable evaluation guards reject side effects and incomplete evidence."""

import importlib.util
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
