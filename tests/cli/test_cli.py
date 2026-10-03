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


def test_cli_argument_failures_return_unsuccessful_code_and_keep_stdout_empty(capsys):
    from brz2obsidian.cli import main

    assert main(["convert", "--json"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage:" in captured.err
    assert main(["--help"]) == 0


def test_installed_cli_arguments_and_destination_failure_match_library(tmp_path):
    from brz2obsidian.application.wiring import default_workflow

    console = Path(sys.executable).with_name("brz2obsidian.exe")
    bad_arguments = subprocess.run(
        [str(console), "convert", "--json"], capture_output=True, text=True, check=False
    )
    assert bad_arguments.returncode == 1
    assert bad_arguments.stdout == ""
    source = make_archive(tmp_path / "source.brz")
    destination = tmp_path / "vault"
    destination.mkdir()
    sentinel = destination / "caller.txt"
    sentinel.write_bytes(b"keep caller content")
    expected = default_workflow().convert(source, destination)
    actual = subprocess.run(
        [str(console), "convert", str(source), str(destination), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert actual.returncode == 1
    assert actual.stderr == ""
    envelope = json.loads(actual.stdout)
    assert envelope == json.loads(expected.model_dump_json(by_alias=True))
    assert sentinel.read_bytes() == b"keep caller content"
    assert list(tmp_path.glob(".brz2obsidian-*")) == []
