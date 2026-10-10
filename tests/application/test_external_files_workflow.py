"""External files are archive-only references through the public workflow."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from brz2obsidian.contracts import RunResult
from tests.application.test_forgotten_workflow import rewrite
from tests.application.test_resources_workflow import HOME, resource_archive, thought

OWNER = "bbbbbbbb-0000-4000-8000-000000000001"


def test_external_files_preserve_destinations_and_materialize_their_only_owner(
    tmp_path,
):
    locations = [
        r"C:\unavailable\lesson.html",
        r"D:\unavailable\lesson.mp4",
        r"E:\unavailable\lesson.pdf",
    ]
    source = resource_archive(
        tmp_path / "source.brz",
        [
            (
                {
                    "SourceId": OWNER,
                    "Type": 2,
                    "Location": location,
                    "DataLength": 1234,
                },
                None,
            )
            for location in locations
        ],
        thoughts=[thought(OWNER, "External only")],
    )
    before = source.read_bytes()
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "clean"
    vault = tmp_path / "vault"
    converted = operation.convert(source, vault)
    assert converted.outcome == "clean"
    assert inspected.counts.planned_notes == converted.counts.actual_notes == 2
    assert inspected.counts.present_assets == converted.counts.actual_assets == 1
    assert inspected.counts.source_gaps == converted.counts.source_gaps == 0
    assert len(list((vault / "Attachments").rglob("*.original"))) == 1
    note = (vault / "Notes/External only.md").read_text(encoding="utf-8")
    for filename, drive in (
        ("lesson.html", "C"),
        ("lesson.mp4", "D"),
        ("lesson.pdf", "E"),
    ):
        assert f"- [{filename}](<file:///{drive}:/unavailable/{filename}>)" in note
    assets = inspected.inspection.assets
    external = [asset for asset in assets if asset.owner == OWNER]
    assert len(external) == 3
    assert all(
        asset.role == "file" and asset.availability == "external" for asset in external
    )
    assert all(
        asset.actual_length is None and asset.actual_sha256 is None
        for asset in external
    )
    record = json.loads((vault / "migration-record.json").read_bytes())
    original = next(
        e["records"]
        for e in record["original_evidence"]
        if e["key"] == "attachments.json"
    )
    assert [r["Location"] for r in original if r["SourceId"] == OWNER] == locations
    assert source.read_bytes() == before


def test_distinct_same_named_resources_encode_paths_and_preserve_internal_bytes(
    tmp_path, monkeypatch
):
    locations = [
        r"C:\Missing courses\naïve #50% & (one).pdf",
        r"D:\Missing courses\naïve #50% & (one).pdf",
    ]
    resources = [
        ({"Type": 2, "Location": location, "Name": "Training PDF"}, None)
        for location in locations
    ]
    resources.append(
        (
            {"Location": "naïve #50% & (one).pdf", "Name": "Training PDF"},
            b"independent PDF bytes",
        )
    )
    source = resource_archive(tmp_path / "source.brz", resources)
    before = source.read_bytes()
    original_stat, original_open = Path.stat, Path.open

    def deny_target_stat(path, *args, **kwargs):
        assert str(path) not in locations, "external target must not be checked"
        return original_stat(path, *args, **kwargs)

    def deny_target_open(path, *args, **kwargs):
        assert str(path) not in locations, "external target must not be read or copied"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", deny_target_stat)
    monkeypatch.setattr(Path, "open", deny_target_open)
    operation = default_workflow()
    inspected = operation.inspect(source)
    converted = operation.convert(source, tmp_path / "vault")
    assert inspected.outcome == converted.outcome == "clean"
    assert inspected.counts.planned_assets == converted.counts.actual_assets == 2
    assert inspected.counts.source_references == converted.counts.actual_references == 0
    note = (tmp_path / "vault/Home — Entry thought.md").read_text(encoding="utf-8")
    assert note.count("Training PDF") == 3
    assert (
        "[Training PDF](<file:///C:/Missing%20courses/na%C3%AFve%20%2350%25%20%26%20%28one%29.pdf>)"
        in note
    )
    assert (
        "[Training PDF](<file:///D:/Missing%20courses/na%C3%AFve%20%2350%25%20%26%20%28one%29.pdf>)"
        in note
    )
    assert "[[Attachments/22222222/naïve 50 & (one).pdf|Training PDF]]" in note
    assert (
        tmp_path / "vault/Attachments/22222222/naïve 50 & (one).pdf"
    ).read_bytes() == b"independent PDF bytes"
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    entries = [
        asset
        for asset in record["asset_targets"]
        if asset["asset_id"].startswith("aaaaaaaa")
    ]
    assert len(entries) == len({asset["asset_id"] for asset in entries}) == 3
    assert sum(asset["relative_path"] is not None for asset in entries) == 1
    assert (
        "Retained 2 external file references"
        in (tmp_path / "vault/MIGRATION REPORT.md").read_text()
    )
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "location",
    [
        r"\\host\share\file.pdf",
        "relative.pdf",
        r"C:relative.pdf",
        r"\rooted.pdf",
        r"\\?\C:\file.pdf",
        r"C:\folder\..\file.pdf",
        r"C:\folder\file.pdf:stream",
        r"C:\folder\NUL.pdf",
        "C:\\folder\\file\x00.pdf",
        r"C:\folder\file?.pdf",
        "C:/",
        "C://folder/file.pdf",
    ],
)
def test_unreviewed_or_unsafe_external_locations_refuse_with_scoped_guidance(
    tmp_path, location
):
    source = resource_archive(
        tmp_path / "source.brz", [({"Type": 2, "Location": location}, None)]
    )
    original = source.read_bytes()
    operation = default_workflow()
    for result in (
        operation.inspect(source),
        operation.convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused"
        issue = result.issues[0]
        assert issue.code == "unsupported_feature"
        assert (
            HOME in issue.affected
            and "aaaaaaaa-0000-4000-8000-000000000001" in issue.affected
        )
        assert "attachments.json:1" in issue.evidence
        assert "external-file" in issue.guidance
        assert "Home" not in issue.guidance
        assert result.receipt is None
    assert source.read_bytes() == original
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize(
    "change,code",
    [
        ({"SourceType": 1}, "unsupported_feature"),
        ({"SourceType": True}, "invalid_source"),
        ({"NoteType": 4}, "unsupported_feature"),
        ({"DataLength": -1}, "invalid_source"),
        ({"DataLength": "4"}, "invalid_source"),
        ({"IsIcon": True}, "unsupported_feature"),
        ({"IsWallpaper": True}, "unsupported_feature"),
        ({"IsIcon": 0}, "invalid_source"),
        ({"IsUnreviewed": True}, "unsupported_feature"),
        ({"TypeId": "custom"}, "unsupported_feature"),
    ],
)
def test_external_role_scalar_and_flag_near_misses_refuse(tmp_path, change, code):
    record = {"Type": 2, "Location": r"C:\unavailable\manual.pdf", **change}
    source = resource_archive(tmp_path / "source.brz", [(record, None)])
    operation = default_workflow()
    for result in (
        operation.inspect(source),
        operation.convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused" and result.issues[0].code == code
        assert HOME in result.issues[0].affected
        assert result.issues[0].evidence
        assert "Home" not in result.issues[0].guidance
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize("local_state", [1, 2, 3])
def test_external_file_with_local_state_refuses(tmp_path, local_state):
    source = resource_archive(
        tmp_path / "source.brz",
        [({"Type": 2, "Location": r"C:\unavailable\manual.pdf"}, None)],
    )

    def add_state(parts):
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"]["aaaaaaaa-0000-4000-8000-000000000001"] = (
            local_state
        )
        parts["meta.json"] = json.dumps(meta).encode()

    rewrite(source, add_state)
    operation = default_workflow()
    for result in (
        operation.inspect(source),
        operation.convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused"
        assert result.issues[0].code == "invalid_source"
        assert "local file state" in result.issues[0].message
        assert HOME in result.issues[0].affected
        assert "meta.json" in result.issues[0].evidence
    assert not (tmp_path / "vault").exists()


def test_external_file_cannot_claim_unassigned_local_payload(tmp_path):
    source = resource_archive(
        tmp_path / "source.brz",
        [({"Type": 2, "Location": r"C:\unavailable\manual.pdf"}, None)],
        extras=[(HOME + "/manual.pdf", b"unassigned local bytes")],
    )
    operation = default_workflow()
    for result in (
        operation.inspect(source),
        operation.convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused"
        assert result.issues[0].code == "invalid_source"
        assert "local payload claim" in result.issues[0].message
        assert HOME in result.issues[0].affected
        assert "payload:" + HOME + "/manual.pdf" in result.issues[0].evidence
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize(
    "change",
    [
        {"Id": "invalid"},
        {"BrainId": OWNER},
        {"SourceId": OWNER},
        {"Id": "33333333-3333-4333-8333-333333333333"},
    ],
)
def test_invalid_external_identity_and_ownership_refuse_without_home_advice(
    tmp_path, change
):
    source = resource_archive(
        tmp_path / "source.brz",
        [({"Type": 2, "Location": r"C:\unavailable\manual.pdf", **change}, None)],
    )
    for result in (
        default_workflow().inspect(source),
        default_workflow().convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused" and result.issues[0].code == "invalid_source"
        assert result.issues[0].evidence == ("attachments.json:1",)
        assert result.issues[0].affected
        assert "external-file" in result.issues[0].guidance
        assert "Home" not in result.issues[0].guidance
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize("reverse", [False, True])
def test_forgotten_owners_and_excluded_associations_leave_no_external_trace(
    tmp_path, reverse
):
    forgotten = thought(OWNER, "Private owner")
    forgotten["ForgottenDateTime"] = "2026-10-01T12:00:00Z"
    source = resource_archive(
        tmp_path / "source.brz",
        [
            (
                {
                    "SourceId": OWNER,
                    "Type": 2,
                    "Location": "private unsafe relative.pdf",
                    "IsWallpaper": True,
                },
                None,
            ),
            (
                {
                    "Type": 2,
                    "Location": r"C:\private\excluded association.pdf",
                    "TargetId": OWNER,
                },
                None,
            ),
            ({"Type": 2, "Location": r"C:\unavailable\included.pdf"}, None),
        ],
        thoughts=[forgotten],
        reverse=reverse,
    )
    operation = default_workflow()
    inspected = operation.inspect(source)
    converted = operation.convert(source, tmp_path / "vault")
    assert inspected.outcome == converted.outcome == "clean"
    assert inspected.counts.source_items == 1
    external = [a for a in inspected.inspection.assets if a.availability == "external"]
    assert (
        len(external) == 1
        and external[0].original_name == r"C:\unavailable\included.pdf"
    )
    output = b"\n".join(
        p.read_bytes() for p in (tmp_path / "vault").rglob("*") if p.is_file()
    )
    for secret in (
        OWNER,
        "Private owner",
        "private unsafe relative.pdf",
        "excluded association.pdf",
    ):
        assert secret not in inspected.model_dump_json()
        assert secret.encode() not in output


@pytest.mark.parametrize("json_output", [False, True])
def test_cli_external_html_video_pdf_agrees_with_library(tmp_path, capsys, json_output):
    source = resource_archive(
        tmp_path / "source.brz",
        [
            ({"Type": 2, "Location": location}, None)
            for location in (
                r"C:\unavailable\lesson.html",
                r"C:\unavailable\lesson.mp4",
                r"C:\unavailable\lesson.pdf",
            )
        ],
    )
    flags = ["--json"] if json_output else []
    expected = default_workflow().inspect(source)
    assert main(["inspect", str(source), *flags]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    if json_output:
        actual = json.loads(captured.out)
        assert actual == json.loads(expected.model_dump_json(by_alias=True))
        assert actual["schema_version"] == 6
        assert (
            actual["profile_version"]
            == actual["source_identity"]["module_version"]
            == "9"
        )
        assert RunResult.model_validate_json(captured.out) == expected
        actual["schema_version"] = 3
        with pytest.raises(ValidationError):
            RunResult.model_validate_json(json.dumps(actual))
    else:
        assert "inspect: clean" in captured.out
        assert "present payloads: 1" in captured.out
    assert main(["convert", str(source), str(tmp_path / "vault"), *flags]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    if json_output:
        actual = json.loads(captured.out)
        assert actual["outcome"] == "clean"
        assert actual["counts"]["actual_assets"] == 1
        assert (
            actual["counts"]["actual_references"]
            == actual["counts"]["source_references"]
            == 0
        )
        assert actual["receipt"]["verified"]
        assert (
            actual["source_identity"]
            == json.loads(expected.model_dump_json())["source_identity"]
        )
    else:
        assert "convert: clean" in captured.out
        assert "Verified vault published:" in captured.out
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert record["schema_version"] == 6 and record["renderer_version"] == "6"
    assert (
        record["profile_version"] == record["source_identity"]["module_version"] == "9"
    )


@pytest.mark.parametrize("json_output", [False, True])
def test_cli_refusal_identifies_external_attachment_without_home_advice(
    tmp_path, capsys, json_output
):
    source = resource_archive(
        tmp_path / "source.brz", [({"Type": 2, "Location": "relative.pdf"}, None)]
    )
    flags = ["--json"] if json_output else []
    for args in (
        ["inspect", str(source)],
        ["convert", str(source), str(tmp_path / "vault")],
    ):
        assert main([*args, *flags]) == 1
        captured = capsys.readouterr()
        assert captured.err == ""
        assert "Home" not in captured.out
        assert "external-file" in captured.out
        assert HOME in captured.out
        assert "attachments.json:1" in captured.out
        if json_output:
            actual = json.loads(captured.out)
            expected = (
                default_workflow().inspect(source)
                if args[0] == "inspect"
                else default_workflow().convert(source, tmp_path / "vault")
            )
            assert actual == json.loads(expected.model_dump_json(by_alias=True))
    assert not (tmp_path / "vault").exists()


def association(identity, form):
    if form == "direct":
        return {"AttachmentId": identity}
    if form == "nested":
        return {"Metadata": {"Rows": [{"AttachmentId": identity.upper()}]}}
    if form == "serialized":
        return {"Metadata": json.dumps({"ObjectId": identity})}
    return {
        "Metadata": '{"AttachmentId":"public","AttachmentId":'
        + json.dumps(identity)
        + "}"
    }


@pytest.mark.parametrize(
    "form", ["direct", "nested", "serialized", "duplicate_serialized"]
)
@pytest.mark.parametrize("reverse", [False, True])
def test_invalid_transitive_excluded_attachment_refuses_privately_in_workflow_and_cli(
    tmp_path, capsys, form, reverse
):
    private_ids = [f"aaaaaaaa-0000-4000-8000-{n:012x}" for n in (1, 2, 3)]
    forgotten = thought(OWNER, "Private owner")
    forgotten["ForgottenDateTime"] = "2026-10-01T12:00:00Z"
    source = resource_archive(
        tmp_path / "source.brz",
        [
            (
                {"SourceId": OWNER, "Type": 2, "Location": r"C:\private\original.pdf"},
                None,
            ),
            (
                {
                    "Type": 2,
                    "Location": r"C:\private\association.pdf",
                    **association(private_ids[0], form),
                },
                None,
            ),
            (
                {
                    "Type": 2,
                    "Location": r"C:\private\transitive.pdf",
                    "BrainId": "cccccccc-0000-4000-8000-000000000001",
                    **association(private_ids[1], form),
                },
                None,
            ),
        ],
        thoughts=[forgotten],
        reverse=reverse,
    )
    original = source.read_bytes()
    operation = default_workflow()
    for result in (
        operation.inspect(source),
        operation.convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused" and result.issues[0].code == "invalid_source"
        assert result.issues[0].affected == result.issues[0].evidence == ()
        for private_id in [OWNER, *private_ids]:
            assert private_id not in result.model_dump_json()
    for json_output in (False, True):
        for args in (
            ["inspect", str(source)],
            ["convert", str(source), str(tmp_path / "vault")],
        ):
            assert main([*args, *(["--json"] if json_output else [])]) == 1
            captured = capsys.readouterr()
            assert captured.err == "" and "attachments.json:" not in captured.out
            assert all(
                private_id not in captured.out for private_id in [OWNER, *private_ids]
            )
    assert source.read_bytes() == original and not (tmp_path / "vault").exists()

    def correct_collection(parts):
        rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
        for row in rows:
            if row["Id"] == private_ids[2]:
                row["BrainId"] = "11111111-1111-4111-8111-111111111111"
        parts["attachments.json"] = "\n".join(json.dumps(row) for row in rows).encode()
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"].update(
            zip(private_ids, (0, {"bad": 1}, False), strict=True)
        )
        parts["meta.json"] = json.dumps(meta).encode()

    rewrite(source, correct_collection)
    assert operation.inspect(source).outcome == "clean"
    assert operation.convert(source, tmp_path / "valid-vault").outcome == "clean"
    output = b"\n".join(
        p.read_bytes() for p in (tmp_path / "valid-vault").rglob("*") if p.is_file()
    )
    assert all(
        private_id.encode() not in output for private_id in [OWNER, *private_ids]
    )


@pytest.mark.parametrize("state", [0, -1, 4, True, None, "1", []])
def test_malformed_external_state_refuses_with_context_in_workflow_and_cli(
    tmp_path, capsys, state
):
    source = resource_archive(
        tmp_path / "source.brz",
        [({"Type": 2, "Location": r"C:\unavailable\manual.pdf"}, None)],
    )
    asset_id = "aaaaaaaa-0000-4000-8000-000000000001"

    def malformed_state(parts):
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"][asset_id] = state
        parts["meta.json"] = json.dumps(meta).encode()

    rewrite(source, malformed_state)
    original = source.read_bytes()
    operation = default_workflow()
    for result in (
        operation.inspect(source),
        operation.convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused" and result.issues[0].code == "invalid_source"
        issue = result.issues[0]
        assert set(issue.affected) == {HOME, asset_id}
        assert set(issue.evidence) == {"attachments.json:1", "meta.json"}
        assert "external-file" in issue.guidance and "Home" not in issue.guidance
    for json_output in (False, True):
        for args in (
            ["inspect", str(source)],
            ["convert", str(source), str(tmp_path / "vault")],
        ):
            assert main([*args, *(["--json"] if json_output else [])]) == 1
            captured = capsys.readouterr()
            assert captured.err == ""
            assert all(
                part in captured.out
                for part in (
                    HOME,
                    asset_id,
                    "attachments.json:1",
                    "meta.json",
                    "external-file",
                )
            )
            assert "Home" not in captured.out
    assert source.read_bytes() == original and not (tmp_path / "vault").exists()
