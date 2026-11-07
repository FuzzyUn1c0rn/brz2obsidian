"""Current CLI composition preserves independent original BMP icon bytes."""

import json

from brz2obsidian.cli import main
from tests.local_acceptance.api_icon_inputs import bmp
from tests.sources.test_local_api_images_v3 import ICON, IcoIconApi
from tests.support.local_api import BRAIN, HOME, KEY, api_server


def test_cli_standard5_inspect_convert_preserves_original_icon(
    tmp_path, monkeypatch, capsys
):
    fixture = bmp()
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    vault = tmp_path / "vault"
    with api_server(IcoIconApi(fixture["raw"])) as (_, origin):
        options = ["--source-kind", "local-api", "--api-url", origin, "--json"]
        assert main(["inspect", BRAIN, *options]) == 0
        inspected = capsys.readouterr()
        assert inspected.err == "" and KEY not in inspected.out
        result = json.loads(inspected.out)
        assert result["profile_version"] == "5" and result["receipt"] is None
        assert main(["convert", BRAIN, str(vault), *options]) == 0
    converted = capsys.readouterr()
    assert converted.err == "" and KEY not in converted.out
    result = json.loads(converted.out)
    assert result["profile_version"] == "5" and result["receipt"]["verified"]
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert record["profile_version"] == "5"
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == ICON)
    assert (asset["owner"], asset["role"], asset["original_name"]) == (
        HOME,
        "icon",
        "Icon.png",
    )
    assert (asset["actual_length"], asset["actual_sha256"]) == (
        fixture["length"],
        fixture["sha256"],
    )
    assert (vault / asset["relative_path"]).read_bytes() == fixture["raw"]
