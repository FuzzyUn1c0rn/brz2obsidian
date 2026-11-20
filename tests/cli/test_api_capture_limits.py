"""Finite capture budgets through the public CLI and real synthetic HTTP."""

import json

import pytest

from brz2obsidian.cli import main
from tests.support.local_api import BRAIN, KEY, api_server


@pytest.mark.parametrize(
    "value,expected", [(None, 1000000000), ("4294967296", 4294967296)]
)
def test_cli_convert_preserves_default_or_above_32bit_total_limit_in_audit(
    tmp_path, monkeypatch, capsys, value, expected
):
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    destination = tmp_path / "vault"
    with api_server() as (_, address):
        arguments = [
            "convert",
            BRAIN,
            str(destination),
            "--source-kind",
            "local-api",
            "--api-url",
            address,
            "--json",
        ]
        if value is not None:
            arguments += ["--api-max-total-capture-bytes", value]
        result = main(arguments)
    captured = capsys.readouterr()
    assert result == 0, captured.out + captured.err
    assert captured.err == ""
    assert json.loads(captured.out)["outcome"] == "clean"
    record = json.loads((destination / "migration-record.json").read_bytes())
    limits = record["run_metadata"]["source_acquisition"]["audit"]["limits"]
    assert limits["max_total_capture_bytes"] == expected
    assert limits["max_payload_bytes"] == 256000000
    assert limits["max_response_bytes"] == 16000000


@pytest.mark.parametrize("operation", ("inspect", "convert"))
def test_cli_tiny_total_bound_refuses_then_finite_bound_completes(
    tmp_path, monkeypatch, capsys, operation
):
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    destination = tmp_path / "vault"
    sentinel = tmp_path / "caller.txt"
    sentinel.write_bytes(b"Preserve caller bytes.")
    with api_server() as (_, address):
        arguments = [operation, BRAIN]
        if operation == "convert":
            arguments.append(str(destination))
        arguments += ["--source-kind", "local-api", "--api-url", address]
        assert main([*arguments, "--api-max-total-capture-bytes", "1"]) == 1
        refused = capsys.readouterr()
        assert "--api-max-total-capture-bytes" in refused.out
        assert "finite larger" in refused.out
        assert KEY not in refused.out + refused.err
        assert not destination.exists()
        assert sentinel.read_bytes() == b"Preserve caller bytes."
        assert (
            main([*arguments, "--api-max-total-capture-bytes", "20000", "--json"]) == 0
        )
    result = json.loads(capsys.readouterr().out)
    assert result["outcome"] == "clean"
    assert result["counts"]["planned_notes"] == 1
    if operation == "convert":
        record = json.loads((destination / "migration-record.json").read_bytes())
        assert (
            record["run_metadata"]["source_acquisition"]["audit"]["limits"][
                "max_total_capture_bytes"
            ]
            == 20000
        )
    else:
        assert result["receipt"] is None and not destination.exists()


@pytest.mark.parametrize("value", ("0", "-1", "1.5", "9223372036854775808", "CANARY"))
def test_invalid_total_limit_refuses_before_http_or_publication(
    tmp_path, monkeypatch, capsys, value
):
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    destination = tmp_path / "never-created"
    with api_server() as (api, address):
        assert (
            main(
                [
                    "convert",
                    BRAIN,
                    str(destination),
                    "--source-kind",
                    "local-api",
                    "--api-url",
                    address,
                    "--api-max-total-capture-bytes",
                    value,
                    "--json",
                ]
            )
            == 1
        )
        assert not api.requests
    captured = capsys.readouterr()
    assert "CANARY" not in captured.out + captured.err
    assert not destination.exists()
    if captured.out:
        assert (
            json.loads(captured.out)["issues"][0]["code"]
            == "invalid_source_configuration"
        )
    else:
        assert "use --help" in captured.err


def test_explicit_total_limit_requires_local_api_and_help_explains_default(
    tmp_path, capsys
):
    from tests.application.test_minimal_workflow import make_archive

    source = make_archive(tmp_path / "source.brz")
    assert (
        main(
            [
                "inspect",
                str(source),
                "--api-max-total-capture-bytes",
                "1000000000",
                "--json",
            ]
        )
        == 1
    )
    assert (
        json.loads(capsys.readouterr().out)["issues"][0]["code"]
        == "invalid_source_configuration"
    )
    assert main(["inspect", "--help"]) == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "--api-max-total-capture-bytes" in help_text
    assert "1000000000 = 1 GB decimal" in help_text
    assert "9223372036854775807" in help_text
