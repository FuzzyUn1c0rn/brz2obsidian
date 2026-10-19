import json

import pytest

from brz2obsidian.cli import main


@pytest.mark.parametrize(
    "operation,as_json,stage",
    [
        ("inspect", True, "resource"),
        ("convert", False, "search"),
        ("convert", True, "relationship"),
    ],
    ids=["inspect-True-resource", "convert-False-search", "convert-True-relationship"],
)
def test_profile3_stage_diagnostics_reach_cli_without_source_hints(
    tmp_path, monkeypatch, capsys, stage, as_json, operation
):
    from tests.support.local_api import BRAIN, KEY, api_server
    from tests.support.local_api_payloads import SHAPE_MESSAGES, unsupported_shape_api

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    with api_server(unsupported_shape_api(stage)) as (_, address):
        arguments = [operation, BRAIN]
        if operation == "convert":
            arguments.append(str(tmp_path / "refused"))
        arguments += ["--source-kind", "local-api", "--api-url", address]
        if as_json:
            arguments.append("--json")
        assert main(arguments) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert f"api_{stage}_shape_unsupported" in captured.out
    assert "CANARY" not in captured.out
    if as_json:
        result = json.loads(captured.out)
        assert result["receipt"] is None
        assert result["issues"][0]["message"] == SHAPE_MESSAGES[stage]
    else:
        assert "Conversion stopped" in captured.out
        assert (
            "converter does not support the search results returned by the local API"
            in captured.out
        )
        assert "Report this limitation with the diagnostic report" in captured.out
        assert "source shape" not in captured.out
    assert not (tmp_path / "refused").exists()
