import json
import subprocess
import sys
from pathlib import Path

from tests.application.test_minimal_workflow import make_archive


def test_installed_console_and_module_emit_one_json_envelope(tmp_path):
    source = make_archive(tmp_path / "brain.brz")
    console = Path(sys.executable).with_name("brz2obsidian.exe")
    for command in ([str(console)], [sys.executable, "-m", "brz2obsidian"]):
        result = subprocess.run(
            [*command, "inspect", str(source), "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert result.stderr == ""
        envelope = json.loads(result.stdout)
        assert envelope["schema"] == "brz2obsidian.result"
        assert envelope["schema_version"] == 1
        assert envelope["receipt"] is None
        assert envelope["counts"]["actual_notes"] is None
    converted = subprocess.run(
        [
            sys.executable,
            "-m",
            "brz2obsidian",
            "convert",
            str(source),
            str(tmp_path / "vault"),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert converted.returncode == 0
    envelope = json.loads(converted.stdout)
    assert envelope["receipt"]["published"] is True
    assert envelope["counts"]["actual_notes"] == 1
