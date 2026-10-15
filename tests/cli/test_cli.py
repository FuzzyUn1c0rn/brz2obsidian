import json
import os
import subprocess
import sys
from pathlib import Path

from tests.application.test_minimal_workflow import make_archive


def test_both_api_cli_entrypoints_preserve_qualified_graph_and_refuse_link_content(
    tmp_path,
):
    from tests.support.local_api import BRAIN, KEY, api_server
    from tests.support.local_api_graph import (
        HIERARCHY,
        CompleteGraphApi,
        assert_published_graph,
    )

    environment = dict(os.environ, THE_BRAIN_LOCAL_API_KEY=KEY)
    console = Path(sys.executable).with_name("brz2obsidian.exe")
    with api_server(CompleteGraphApi()) as (api, address):
        for index, command in enumerate(
            ([str(console)], [sys.executable, "-m", "brz2obsidian"])
        ):
            common = ["--source-kind", "local-api", "--api-url", address, "--json"]
            inspected = subprocess.run(
                [*command, "inspect", BRAIN, *common],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            assert inspected.returncode == 0, inspected.stdout + inspected.stderr
            assert json.loads(inspected.stdout)["counts"]["source_items"] == 9
            destination = tmp_path / str(index)
            converted = subprocess.run(
                [*command, "convert", BRAIN, str(destination), *common],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            assert converted.returncode == 0, converted.stdout + converted.stderr
            assert json.loads(converted.stdout)["receipt"]["verified"]
            assert_published_graph(destination)
            api.overrides[f"/api/links/{BRAIN}/{HIERARCHY}/attachments"] = (
                200,
                [{"name": "SECRET_CANARY", "renderedUrl": "SERVICE_TOKEN_CANARY"}],
            )
            refused = subprocess.run(
                [
                    *command,
                    "convert",
                    BRAIN,
                    str(tmp_path / f"refused{index}"),
                    *common,
                ],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            assert refused.returncode == 1
            assert json.loads(refused.stdout)["outcome"] == "refused"
            assert not (tmp_path / f"refused{index}").exists()
            assert (
                "CANARY"
                not in refused.stdout
                + refused.stderr
                + inspected.stdout
                + converted.stdout
            )
            api.overrides.clear()


def test_local_api_installed_and_module_inspect_convert_json_and_text(tmp_path):
    from tests.support.local_api import BRAIN, KEY, api_server

    environment = dict(os.environ, THE_BRAIN_LOCAL_API_KEY=KEY)
    console = Path(sys.executable).with_name("brz2obsidian.exe")
    with api_server() as (_, address):
        for index, command in enumerate(
            ([str(console)], [sys.executable, "-m", "brz2obsidian"])
        ):
            common = [
                "--source-kind",
                "local-api",
                "--api-url",
                address,
                "--api-search-initial-results",
                "5000",
                "--api-search-timeout",
                "300",
                "--api-search-max-response-bytes",
                "128000000",
                "--api-search-max-results",
                "7500",
            ]
            inspected = subprocess.run(
                [*command, "inspect", BRAIN, *common, "--json"],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            assert inspected.returncode == 0, inspected.stderr + inspected.stdout
            assert inspected.stderr == ""
            envelope = json.loads(inspected.stdout)
            assert (
                envelope["schema_version"] == 7
                and envelope["counts"]["source_items"] == 2
            )
            converted = subprocess.run(
                [*command, "convert", BRAIN, str(tmp_path / f"vault{index}"), *common],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            assert converted.returncode == 0, converted.stderr + converted.stdout
            assert "not an atomic snapshot" in converted.stdout
            assert (
                KEY
                not in inspected.stdout
                + inspected.stderr
                + converted.stdout
                + converted.stderr
            )
            assert "Verified vault published" in converted.stdout


def test_cli_local_api_configuration_errors_are_safe_json_and_brz_rejects_api_options(
    capsys,
):
    from brz2obsidian.cli import main

    for options in (
        [
            "--source-kind",
            "local-api",
            "--api-url",
            "http://user:SECRET_CANARY@127.0.0.1/api",
        ],
        ["--source-kind", "local-api", "--api-search-max-results", "-1"],
        ["--api-url", "http://127.0.0.1/api"],
    ):
        assert main(["inspect", "UUID_CANARY", *options, "--json"]) == 1
        captured = capsys.readouterr()
        assert "CANARY" not in captured.out + captured.err
        assert json.loads(captured.out)["outcome"] == "refused"
    assert main(["inspect", "value", "--source-kind", "SECRET_CANARY"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "CANARY" not in captured.err
    assert "invalid command arguments; use --help" in captured.err
    assert main(["inspect", "value", "--SECRET_CANARY", "VALUE_CANARY"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "CANARY" not in captured.err
    assert "unrecognized arguments; use --help" in captured.err


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
        assert envelope["schema_version"] == 7
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
