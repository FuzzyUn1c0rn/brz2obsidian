import json
import subprocess
import sys
from pathlib import Path

from brz2obsidian.cli import main
from brz2obsidian.vault_check import check_vault
from tests.vault_check.test_check_vault import inventory


def test_check_vault_cli_text_json_and_exit_codes_match_public_operation(
    tmp_path, capsys
):
    vault = tmp_path / "vault"
    vault.mkdir()
    for outcome, code in (("clean", 0), ("issues", 2), ("failed", 1)):
        if outcome == "issues":
            (vault / "Manual.md").write_text(
                "---\ncreated: wrong\n---\n", encoding="utf-8"
            )
        target = vault if outcome != "failed" else tmp_path / "absent"
        expected = check_vault(target)
        before = inventory(vault)
        assert expected.outcome == outcome
        assert main(["check-vault", str(target), "--json"]) == code
        captured = capsys.readouterr()
        assert captured.err == ""
        assert json.loads(captured.out) == json.loads(
            expected.model_dump_json(by_alias=True)
        )
        assert main(["check-vault", str(target)]) == code
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out.startswith(f"check-vault: {outcome}\n")
        for issue in expected.issues:
            assert issue.code in captured.out
            assert issue.message in captured.out
            if issue.artifact:
                assert issue.artifact in captured.out
        assert inventory(vault) == before
    assert main(["check-vault", "--json"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage:" in captured.err


def test_installed_console_and_module_check_source_free_vaults(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    console = Path(sys.executable).with_name("brz2obsidian.exe")
    for outcome, code in (("clean", 0), ("issues", 2), ("failed", 1)):
        if outcome == "issues":
            (vault / "Manual.md").write_text(
                "---\nicon: '[[Missing.png]]'\n---\n", encoding="utf-8"
            )
        target = vault if outcome != "failed" else tmp_path / "absent"
        expected = json.loads(check_vault(target).model_dump_json(by_alias=True))
        before = inventory(vault)
        for command in ([str(console)], [sys.executable, "-m", "brz2obsidian"]):
            result = subprocess.run(
                [*command, "check-vault", str(target), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == code
            assert result.stderr == ""
            assert json.loads(result.stdout) == expected
            assert inventory(vault) == before


def test_api_and_cli_work_with_source_workflow_renderer_and_publisher_imports_blocked(
    tmp_path,
):
    code = """
import importlib.abc
import json
import sys
class BlockOuter(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + ".") for name in (
            "brz2obsidian.sources", "brz2obsidian.application", "brz2obsidian.core",
            "brz2obsidian.obsidian", "brz2obsidian.publication", "tests.local_acceptance"
        )):
            raise AssertionError("Forbidden checker dependency: " + fullname)
sys.meta_path.insert(0, BlockOuter())
from brz2obsidian.vault_check import check_vault
assert check_vault(sys.argv[1]).outcome == "clean"
from brz2obsidian.cli import main
assert main(["check-vault", sys.argv[1], "--json"]) == 0
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["schema"] == "brz2obsidian.vault-check"
