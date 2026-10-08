import ast
import subprocess
import sys
from pathlib import Path


def test_backend_and_worker_have_no_gui_import_routes():
    package = Path(__file__).parents[2] / "src/brz2obsidian"
    for file in package.rglob("*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imports = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            assert not any(
                name.startswith(("PySide6", "brz2obsidian_ui")) for name in imports
            ), file


def test_public_operations_and_cli_remain_usable_with_gui_imports_blocked():
    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    program = """
import importlib.abc, sys
class BlockGUI(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('PySide6', 'brz2obsidian_ui')):
            raise ImportError('GUI imports are blocked')
sys.meta_path.insert(0, BlockGUI())
from pathlib import Path
from brz2obsidian.application.operations import inspect, ApplicationSession
from brz2obsidian.application.transport import Supervisor
from brz2obsidian.cli import main
assert inspect(Path(sys.argv[1])).status == 'inspection_clean'
assert ApplicationSession().snapshot.source is None
sys.argv = ['brz2obsidian', 'inspect', sys.argv[1]]
assert main() == 0
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(source)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
