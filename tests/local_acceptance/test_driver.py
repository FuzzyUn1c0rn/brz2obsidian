"""Independent archive order/conservation and accepted-source corruption controls."""

import ast
import sys
from pathlib import Path

import pytest

from tests.local_acceptance.run import check_input, fingerprint
from tests.sources.test_reader import rewrite
from tests.support.v2_collection import mixed_archive


def test_final_fingerprint_guard_detects_same_count_opaque_source_change(tmp_path):
    source = mixed_archive(tmp_path / "source.brz")
    rewrite(
        source, "modificationlogs.json", b'{"Opaque":"initial independent history"}'
    )
    before = fingerprint(source)
    check_input(source, before)
    rewrite(
        source,
        "modificationlogs.json",
        b'{"Opaque":"changed without converter meanings"}',
    )
    with pytest.raises(AssertionError, match="accepted source changed"):
        check_input(source, before)


def test_expected_fact_oracle_has_only_reviewed_imports():
    root = Path(__file__).parent
    modules = {
        "api_checker",
        "api_manifest",
        "api_generated",
        "api_image_proofs",
        "api_note_text",
        "api_scope",
        "api_scope_inputs",
        "api_svg",
        "checker",
        "facts",
        "support",
        "scope",
        "images",
        "gaps",
        "text",
    }
    assert {
        p.stem for p in root.glob("*.py") if not p.stem.startswith("test_")
    } == modules | {"run", "__init__"}
    for name in (m + ".py" for m in modules):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    a.name.split(".")[0] in sys.stdlib_module_names for a in node.names
                ) or (
                    name == "api_checker.py"
                    and len(node.names) == 1
                    and node.names[0].name == "yaml"
                    and node.names[0].asname is None
                )
            elif isinstance(node, ast.ImportFrom):
                assert (node.level == 1 and node.module in modules) or (
                    node.level == 0
                    and node.module.split(".")[0] in sys.stdlib_module_names
                )
