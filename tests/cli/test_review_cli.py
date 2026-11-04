"""Public CLI consumers of the shared saved-review and history lifecycle."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.mark.parametrize(
    ("command", "options"),
    (
        ("apply", ()),
        (
            "apply",
            (
                "--proposal-id",
                "review:one",
                "--generation",
                "invalid",
                "--checkpoint",
                "a" * 40,
            ),
        ),
        ("status", ("--not-a-review-option",)),
    ),
)
def test_review_argument_errors_report_actionable_refusal_without_touching_vault(
    tmp_path, capsys, command, options
):
    from brz2obsidian.cli import main

    vault = tmp_path / "untouched-vault"
    code = main(["review", command, str(vault), *options, "--json"])
    captured = capsys.readouterr()
    assert code == 2
    value = json.loads(captured.out)
    assert value["schema"] == "brz2obsidian.cli-review-result"
    assert value["schema_version"] == 1 and value["command"] == command
    assert value["status"] == "refused"
    assert value["code"] == "invalid_review_arguments" and value["ready"] is False
    assert "use --help" in captured.err
    assert not vault.exists()


def test_review_status_reports_initialization_without_creating_history(tmp_path):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-286-status-"))
    owner = uuid4().hex
    (root / "owner.json").write_text(json.dumps({"owner": owner}), encoding="utf-8")
    (tmp_path / "owned-fixture.json").write_text(
        json.dumps({"root": str(root), "owner": owner}), encoding="utf-8"
    )
    vault = root / "vault"
    vault.mkdir()
    note = vault / "Authored.md"
    note.write_bytes(b"Keep authored bytes\r\n")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "brz2obsidian",
            "review",
            "status",
            str(vault),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=25,
    )

    assert result.returncode == 2
    assert result.stderr == ""
    value = json.loads(result.stdout)
    assert value["schema"] == "brz2obsidian.cli-review-result"
    assert value["schema_version"] == 1
    assert value["command"] == "status"
    assert value["status"] == "initialization_required"
    assert value["code"] == "repository_initialization_required"
    assert value["ready"] is False
    assert value["history_retained"] is False
    assert value["next_actions"] == ["initialize_vault"]
    assert note.read_bytes() == b"Keep authored bytes\r\n"
    assert sorted(path.name for path in vault.iterdir()) == ["Authored.md"]
