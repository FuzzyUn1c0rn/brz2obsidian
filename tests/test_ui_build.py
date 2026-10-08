import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools.build_ui import build

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Local Windows launcher")


def test_launcher_uses_unicode_spaced_source_and_explicit_interpreter_from_unrelated_cwd(
    tmp_path,
):
    pytest.importorskip("PySide6")
    root = tmp_path / "Été checkout with spaces"
    module = root / "src/brz2obsidian_ui/__main__.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "import json,sys\nfrom pathlib import Path\nPath(__file__).with_name('started.json').write_text(json.dumps(sys.argv), encoding='utf-8')\n",
        encoding="utf-8",
    )
    launcher = build(root, Path(sys.executable))
    elsewhere = tmp_path / "unrelated directory"
    elsewhere.mkdir()
    launched = subprocess.run(
        ["cmd.exe", "/d", "/c", str(launcher)],
        cwd=elsewhere,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert launched.returncode == 0, launched.stderr
    receipt = module.with_name("started.json")
    deadline = time.monotonic() + 10
    while not receipt.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert receipt.is_file(), launched.stdout
    argv = json.loads(receipt.read_text(encoding="utf-8"))
    assert argv[1:] == [
        "--python",
        str(Path(sys.executable).resolve()),
        "--source-root",
        str(root / "src"),
    ]


def test_build_reports_missing_environment_without_downloading(tmp_path):
    with pytest.raises(ValueError, match="missing or moved"):
        build(tmp_path, tmp_path / ".venv/Scripts/python.exe")


def test_launcher_retains_readable_setup_error_after_source_moves(tmp_path):
    pytest.importorskip("PySide6")
    source = tmp_path / "src/brz2obsidian_ui/__main__.py"
    source.parent.mkdir(parents=True)
    source.write_text("", encoding="utf-8")
    launcher = build(tmp_path, Path(sys.executable))
    source.unlink()
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", str(launcher)],
        input="\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 1
    assert "missing or moved" in result.stdout
    assert "README.md" in result.stdout
