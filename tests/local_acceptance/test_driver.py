"""Independent archive order/conservation and accepted-source corruption controls."""

import ast
import shutil
import sys
from pathlib import Path

import pytest

from tests.local_acceptance.run import check_input, fingerprint
from tests.sources.test_reader import rewrite
from tests.support.import_routes import literal_imports
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
    assert_expected_fact_imports(Path(__file__).parent)


@pytest.mark.parametrize(
    ("filename", "source", "reason"),
    [
        ("__init__.py", "from brz2obsidian import contracts\n", "unreviewed import"),
        (
            "facts.py",
            "from importlib import import_module as load\nload(name)\n",
            "requires static imports",
        ),
    ],
)
def test_expected_fact_import_policy(tmp_path, filename, source, reason):
    root = tmp_path / "local_acceptance"
    shutil.copytree(
        Path(__file__).parent, root, ignore=shutil.ignore_patterns("__pycache__")
    )
    (root / filename).write_text(source, encoding="utf-8")

    with pytest.raises(AssertionError, match=rf"{filename}:\d+:.*{reason}"):
        assert_expected_fact_imports(root)


def assert_expected_fact_imports(root):
    modules = {
        "api_recording",
        "api_baseline",
        "appearance",
        "note_links",
        "api_checker",
        "api_manifest",
        "api_generated",
        "api_image_proofs",
        "api_icon_inputs",
        "resource_calibration",
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
        "unavailable_images",
    }
    assert {
        p.stem for p in root.glob("*.py") if not p.stem.startswith("test_")
    } == modules | {"run", "audit_run", "__init__"}
    for name in sorted(m + ".py" for m in modules | {"__init__"}):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        for node, _ in literal_imports(tree, "tests.local_acceptance"):
            raise AssertionError(
                f"{name}:{node.lineno}: expected-fact code requires static imports"
            )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    a.name.split(".")[0] in sys.stdlib_module_names for a in node.names
                ) or (
                    name == "api_checker.py"
                    and len(node.names) == 1
                    and node.names[0].name == "yaml"
                    and node.names[0].asname is None
                ), f"{name}:{node.lineno}: unreviewed import"
            elif isinstance(node, ast.ImportFrom):
                assert (node.level == 1 and node.module in modules) or (
                    node.level == 0
                    and node.module.split(".")[0] in sys.stdlib_module_names
                ), f"{name}:{node.lineno}: unreviewed import"
    # The explicit test-support orchestrator is allowed only public workflow
    # construction. It is separate from every expected-source-fact module.
    public = {
        "brz2obsidian.application.wiring": {"local_api_workflow"},
        "brz2obsidian.sources.thebrain.local_api": {
            "LocalApiConfig",
            "LocalApiSourceRef",
        },
    }
    tree = ast.parse((root / "audit_run.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(
                name.name.split(".")[0] in sys.stdlib_module_names
                for name in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            assert (node.level == 1 and node.module in modules) or (
                node.level == 0
                and (
                    node.module.split(".")[0] in sys.stdlib_module_names
                    or node.module in public
                    and {name.name for name in node.names} <= public[node.module]
                )
            )
