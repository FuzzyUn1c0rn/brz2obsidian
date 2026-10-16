import json

import pytest

from brz2obsidian.cli import main


@pytest.mark.parametrize("operation", ["inspect", "convert"])
def test_api_help_explains_source_bounds_and_capture_limits(
    operation, capsys, monkeypatch
):
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", "KEY_CANARY")
    assert main([operation, "--help"]) == 0
    captured = capsys.readouterr()
    help_text = " ".join(captured.out.split())
    for required in (
        "BRZ archive path or canonical lowercase Brain UUID",
        "default brz",
        "TheBrain settings",
        "1..2147483647",
        "0.001..86400",
        "whole milliseconds",
        "1..9223372036854775807",
        "default 5000",
        "default 300",
        "default 128000000",
        "default disabled",
        "not an atomic snapshot",
        "Inspection releases its capture; conversion acquires again",
        "retained copy",
        "empirical",
        "universal discovery completeness",
        "THE_BRAIN_LOCAL_API_KEY",
    ):
        assert required in help_text
    assert "CANARY" not in captured.out + captured.err
    assert "--api-key" not in captured.out
    assert captured.err == ""


@pytest.mark.parametrize(
    "options",
    [
        ["--api-search-initial-results", "0"],
        ["--api-search-initial-results", "2147483648"],
        ["--api-search-max-results", "-1"],
        ["--api-search-max-results", "2147483648"],
        ["--api-search-max-response-bytes", "0"],
        ["--api-search-max-response-bytes", "9223372036854775808"],
        ["--api-search-timeout", "nan"],
        ["--api-search-timeout", "inf"],
        ["--api-search-timeout", "0.0001"],
        ["--api-search-timeout", "0.0015"],
        ["--api-search-timeout", "86400.001"],
        ["--api-url", "http://example.invalid/api"],
        ["--api-url", "http://127.0.0.1:65536/api"],
        ["--api-url", "http://127.0.0.1/api?token=SERVICE_TOKEN_CANARY"],
        ["--api-url", "http://user:KEY_CANARY@127.0.0.1/api"],
        ["--api-url", "http://127.0.0.1/other"],
        ["--api-url", "http://127.0.0.1/api#HEADER_CANARY"],
    ],
)
def test_invalid_api_bounds_and_origins_have_actionable_safe_json(options, capsys):
    from tests.support.local_api import BRAIN

    assert (
        main(["inspect", BRAIN, "--source-kind", "local-api", *options, "--json"]) == 1
    )
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["outcome"] == "refused" and result["receipt"] is None
    assert [issue["code"] for issue in result["issues"]] == [
        "invalid_source_configuration"
    ]
    assert "--help" in result["issues"][0]["guidance"]
    assert "CANARY" not in captured.out + captured.err
    assert captured.err == ""


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("fault", ["acquisition", "payload", "filesystem", "teardown"])
def test_real_cli_failure_surfaces_preserve_safe_errors_and_publication_receipt(
    tmp_path, monkeypatch, capsys, as_json, fault
):
    import shutil
    import tempfile
    from pathlib import Path

    from tests.support.local_api import BRAIN, KEY, api_server
    from tests.support.local_api_payloads import (
        TYPE_ICON,
        RichPayloadApi,
        assert_published_payloads,
    )

    captures = tmp_path / "captures"
    captures.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(captures))
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    real_write, real_remove = Path.write_bytes, shutil.rmtree

    def fail_write(path, value):
        if path.name == "metadata.json":
            raise OSError("KEY_CANARY HEADER_CANARY SERVICE_TOKEN_CANARY")
        return real_write(path, value)

    def fail_remove(path, *args, **kwargs):
        if (Path(path) / "manifest.json").is_file():
            raise OSError("KEY_CANARY HEADER_CANARY SERVICE_TOKEN_CANARY")
        return real_remove(path, *args, **kwargs)

    if fault == "filesystem":
        monkeypatch.setattr(Path, "write_bytes", fail_write)
    elif fault == "teardown":
        monkeypatch.setattr(shutil, "rmtree", fail_remove)
    api = RichPayloadApi(explicit=True, jpeg=True)
    if fault in {"acquisition", "payload"}:
        path = (
            f"/api/brains/{BRAIN}"
            if fault == "acquisition"
            else f"/api/attachments/{BRAIN}/{TYPE_ICON}/file-content"
        )
        api.overrides[path] = (
            401 if fault == "acquisition" else 404,
            b"KEY_CANARY HEADER_CANARY SERVICE_TOKEN_CANARY",
            {"X-Secret": "HEADER_CANARY"},
        )
    vault = tmp_path / "vault"
    with api_server(api) as (_, address):
        arguments = [
            "convert",
            BRAIN,
            str(vault),
            "--source-kind",
            "local-api",
            "--api-url",
            address,
        ]
        if as_json:
            arguments.append("--json")
        assert main(arguments) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "CANARY" not in captured.out
    if as_json:
        result = json.loads(captured.out)
        assert result["outcome"] in {"failed", "refused"}
        if fault == "teardown":
            assert result["receipt"]["published"] and result["receipt"]["verified"]
            assert "publication_occurred" in {
                issue["code"] for issue in result["issues"]
            }
        else:
            assert result["receipt"] is None
    elif fault == "teardown":
        assert "Verified vault published" in captured.out
        assert "publication_occurred" in captured.out
    if fault == "teardown":
        assert_published_payloads(vault, explicit=True, jpeg=True)
        monkeypatch.setattr(shutil, "rmtree", real_remove)
    else:
        assert not vault.exists()
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert b"CANARY" not in path.read_bytes()


@pytest.mark.parametrize(
    "option",
    [
        "--api-url",
        "--api-search-initial-results",
        "--api-search-timeout",
        "--api-search-max-response-bytes",
        "--api-search-max-results",
    ],
)
def test_default_brz_source_rejects_every_api_option(option, capsys):
    value = "http://127.0.0.1/api" if option == "--api-url" else "1"
    assert main(["inspect", "archive.brz", option, value, "--json"]) == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["outcome"] == "refused"
    assert result["issues"][0]["code"] == "invalid_source_configuration"
    assert captured.err == ""


@pytest.mark.parametrize("stage", ["search", "relationship", "resource"])
@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("operation", ["inspect", "convert"])
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
    assert SHAPE_MESSAGES[stage] in captured.out
    assert f"api_{stage}_shape_unsupported" in captured.out
    assert "CANARY" not in captured.out
    if as_json:
        result = json.loads(captured.out)
        assert result["receipt"] is None
        assert result["issues"][0]["message"] == SHAPE_MESSAGES[stage]
    assert not (tmp_path / "refused").exists()


@pytest.mark.parametrize("as_json", [False, True])
def test_cli_discovers_reverse_hierarchy_from_relationship_only_search(
    tmp_path, monkeypatch, capsys, as_json
):
    from tests.sources.test_local_api_relationship_candidates import (
        CHILD,
        LINK,
        PARENT,
        LinkCandidateApi,
    )
    from tests.support.local_api import BRAIN, KEY, api_server

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    destination = tmp_path / "vault"
    with api_server(LinkCandidateApi(direction=3)) as (_, address):
        options = ["--source-kind", "local-api", "--api-url", address]
        if as_json:
            options.append("--json")
        assert main(["inspect", BRAIN, *options]) == 0
        inspected = capsys.readouterr()
        assert main(["convert", BRAIN, str(destination), *options]) == 0
    converted = capsys.readouterr()
    assert inspected.err == converted.err == ""
    assert "CANARY" not in inspected.out + converted.out
    if as_json:
        assert json.loads(inspected.out)["outcome"] == "clean"
        assert json.loads(converted.out)["outcome"] == "clean"
    record = json.loads((destination / "migration-record.json").read_bytes())
    assert [
        (r["key"], r["kind"], r["item_a"], r["item_b"]) for r in record["relationships"]
    ] == [(LINK, "hierarchy", PARENT, CHILD)]
    parent = (destination / "Notes/Parent.md").read_text(encoding="utf-8")
    assert "## Children\n\n- [[Notes/Child.md|Child]]" in parent
    assert "## Parents" not in parent


@pytest.mark.parametrize("as_json", [False, True])
def test_cli_external_only_owner_keeps_reference_links_without_target_access(
    tmp_path, monkeypatch, capsys, as_json
):
    from tests.sources.test_local_api_external_references import (
        ExternalReferenceApi,
        forbid_external_target_io,
    )
    from tests.support.local_api import BRAIN, KEY, api_server

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    forbid_external_target_io(monkeypatch)
    destination = tmp_path / "vault"
    with api_server(ExternalReferenceApi()) as (api, address):
        options = ["--source-kind", "local-api", "--api-url", address]
        if as_json:
            options.append("--json")
        assert main(["inspect", BRAIN, *options]) == 0
        inspected = capsys.readouterr()
        assert main(["convert", BRAIN, str(destination), *options]) == 0
    converted = capsys.readouterr()
    assert inspected.err == converted.err == ""
    if as_json:
        assert json.loads(inspected.out)["outcome"] == "clean"
        assert json.loads(converted.out)["outcome"] == "clean"
    note = (destination / "Notes/External owner.md").read_text(encoding="utf-8")
    assert "file:///C:/Source/caf%C3%A9%20%25%23.pdf" in note
    assert "file:///D:/Projects/Folder%20Name" in note
    assert not any(path.endswith("/file-content") for path, _, _ in api.requests)


@pytest.mark.parametrize("family", ["jpeg", "inert-a.ico", "inert-b.ico"])
@pytest.mark.parametrize("as_json", [False, True])
def test_cli_preserves_new_jpeg_and_finite_ico_bytes(
    tmp_path, monkeypatch, capsys, family, as_json
):
    from tests.sources.test_local_api_images_v3 import (
        ICON,
        INPUTS,
        IcoIconApi,
        JpegImageApi,
    )
    from tests.support.local_api import BRAIN, KEY, api_server
    from tests.support.local_api_payloads import IMAGE, JPEG

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    raw = JPEG if family == "jpeg" else (INPUTS / family).read_bytes()
    api = JpegImageApi() if family == "jpeg" else IcoIconApi(raw)
    destination = tmp_path / "vault"
    with api_server(api) as (_, address):
        options = ["--source-kind", "local-api", "--api-url", address]
        if as_json:
            options.append("--json")
        assert main(["inspect", BRAIN, *options]) == 0
        inspected = capsys.readouterr()
        assert main(["convert", BRAIN, str(destination), *options]) == 0
    converted = capsys.readouterr()
    assert inspected.err == converted.err == ""
    if as_json:
        assert json.loads(inspected.out)["outcome"] == "clean"
        assert json.loads(converted.out)["outcome"] == "clean"
    record = json.loads((destination / "migration-record.json").read_bytes())
    asset = next(
        row
        for row in record["asset_targets"]
        if row["asset_id"] == (IMAGE if family == "jpeg" else ICON)
    )
    assert (destination / asset["relative_path"]).read_bytes() == raw
    assert asset["role"] == ("image" if family == "jpeg" else "icon")


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("operation", ["inspect", "convert"])
def test_corrupt_new_jpeg_has_safe_cli_refusal_without_publication(
    tmp_path, monkeypatch, capsys, as_json, operation
):
    import struct

    from tests.sources.test_local_api_images_v3 import INPUTS, JpegImageApi
    from tests.support.local_api import BRAIN, HOME, KEY, api_server
    from tests.support.local_api_payloads import IMAGE

    raw = (INPUTS / "inert-blue.jpg").read_bytes()
    marker = raw.index(b"\xff\xda")
    start = marker + 2 + struct.unpack_from(">H", raw, marker + 2)[0]
    damaged = raw[: start + 6] + b"\xff\xd9"
    api = JpegImageApi()
    api.payloads[IMAGE] = damaged
    api.attachments[IMAGE]["dataLength"] = len(damaged)
    api.thoughts[HOME]["name"] = "PRIVATE_JPEG_TITLE_CANARY"
    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    with api_server(api) as (_, address):
        arguments = [operation, BRAIN]
        if operation == "convert":
            arguments.append(str(tmp_path / "bad-jpeg"))
        arguments += ["--source-kind", "local-api", "--api-url", address]
        if as_json:
            arguments.append("--json")
        assert main(arguments) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert (
        "Required JPEG image bytes cannot be decoded without recovery" in captured.out
    )
    assert "CANARY" not in captured.out
    if as_json:
        result = json.loads(captured.out)
        assert result["issues"][0]["code"] == "invalid_source"
        assert result["receipt"] is None
    assert not (tmp_path / "bad-jpeg").exists()


@pytest.mark.parametrize("as_json", [False, True])
def test_standard_cli_preserves_static_svg_with_truthful_profile(
    tmp_path, monkeypatch, capsys, as_json
):
    from tests.sources.test_local_api_svg_v3 import SVG, SvgApi
    from tests.support.local_api import BRAIN, KEY, api_server
    from tests.support.local_api_payloads import IMAGE

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
    with api_server(SvgApi()) as (_, address):
        source = ["--source-kind", "local-api", "--api-url", address]
        output = ["--json"] if as_json else []
        assert main(["inspect", BRAIN, *source, *output]) == 0
        inspected = capsys.readouterr()
        assert inspected.err == ""
        if as_json:
            assert json.loads(inspected.out)["outcome"] == "clean"
        assert main(["convert", BRAIN, str(tmp_path / "vault"), *source, *output]) == 0
        converted = capsys.readouterr()
        assert converted.err == ""
        assert "CANARY" not in inspected.out + converted.out
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert record["profile_version"] == "3"
    asset = next(row for row in record["asset_targets"] if row["asset_id"] == IMAGE)
    assert asset["role"] == "image"
    assert (tmp_path / "vault" / asset["relative_path"]).read_bytes() == SVG
