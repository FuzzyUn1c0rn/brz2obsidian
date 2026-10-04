"""Reviewed external video resources through real workflow and CLI boundaries."""

import json
import socket
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from tests.application.test_links_workflow import COMPACT, TARGET
from tests.application.test_verified_coverage import (
    OWNER,
    add_attachment,
    change_record,
    source_parts,
    write_source,
)

VIDEO = "88888888-8888-4888-8888-888888888888"
VIDEO_ID = "SYNTHVID001"
URL = "https://www.youtube.com/watch?v=SYNTHVID001&t=18s"
HTML = (
    "<iframe width='100%' height='100%' "
    "src='https://www.youtube.com/embed/SYNTHVID001?start=0' "
    "frameborder='0'></iframe>"
)
EMBED = "https://www.youtube.com/embed/SYNTHVID001?start=18"


def video_parts(tmp_path, url=URL, html=HTML):
    parts = source_parts(tmp_path)
    add_attachment(parts, VIDEO, 3, url, state=None)
    change_record(parts, VIDEO, Name="Reviewed video", VideoHtml=html)
    return parts


def test_video_keeps_exact_source_link_and_derives_separate_native_timing(tmp_path):
    parts = video_parts(tmp_path)
    source = write_source(tmp_path, parts)
    original_bytes = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    asset = next(a for a in inspected.inspection.assets if a.asset_id == VIDEO)
    assert asset.external_uri == URL
    assert asset.video_presentation is not None
    assert asset.video_presentation.model_dump() == {
        "provider": "youtube",
        "embed_uri": EMBED,
        "start_seconds": 18,
    }
    target = next(a for a in inspected.inspection.asset_targets if a.asset_id == VIDEO)
    assert target.resource_link == URL and target.relative_path is None
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "clean", result.issues
    assert result.receipt.published and result.receipt.verified
    note = (vault / "Home — Entry thought.md").read_text()
    assert f"- [Reviewed video](<{URL}>)" in note
    assert f'<iframe src="{EMBED}"' in note
    assert HTML not in note
    record = json.loads((vault / "migration-record.json").read_bytes())
    retained = next(a for a in record["asset_targets"] if a["asset_id"] == VIDEO)
    assert retained["external_uri"] == URL and retained["resource_link"] == URL
    assert retained["video_presentation"] == asset.video_presentation.model_dump()
    originals = next(
        e["records"]
        for e in record["original_evidence"]
        if e["key"] == "attachments.json"
    )
    original_video = next(a for a in originals if a["Id"] == VIDEO)
    assert original_video["Location"] == URL and original_video["VideoHtml"] == HTML
    assert source.read_bytes() == original_bytes
    assert result.counts.actual_assets == 1
    assert not list(vault.rglob("*.mp4"))


def test_video_embed_and_timing_are_independent_inspect_and_record_adaptations(
    tmp_path,
):
    source = write_source(tmp_path, video_parts(tmp_path))
    inspected = default_workflow().inspect(source)
    adaptations = [a for a in inspected.inspection.adaptations if a.affected == VIDEO]
    assert {a.kind for a in adaptations} == {"video_embed", "video_timing"}
    assert EMBED in next(a.description for a in adaptations if a.kind == "video_embed")
    assert "18 seconds" in next(
        a.description for a in adaptations if a.kind == "video_timing"
    )
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "clean", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert [a for a in record["adaptations"] if a["affected"] == VIDEO] == [
        a.model_dump() for a in adaptations
    ]


def test_remote_video_limit_is_once_and_separate_from_pdf_and_source_gaps(tmp_path):
    parts = video_parts(tmp_path)
    second = "99999999-9999-4999-8999-999999999999"
    add_attachment(parts, second, 3, URL.split("&t=", 1)[0], state=None)
    change_record(parts, second, VideoHtml=HTML)
    add_attachment(
        parts,
        "66666666-6666-4666-8666-666666666666",
        1,
        "manual.pdf",
        b"%PDF synthetic",
    )
    result = default_workflow().convert(
        write_source(tmp_path, parts), tmp_path / "vault"
    )
    assert result.outcome == "clean" and result.issues == ()
    report = (tmp_path / "vault/MIGRATION REPORT.md").read_text()
    assert report.count("Video playback depends on the remote service and network") == 1
    assert "Offline playback and service availability are not guaranteed" in report
    assert "The original resource links remain available" in report
    assert report.count("Vault Search does not search PDF body text") == 1
    assert "Source warnings" not in report


@pytest.mark.parametrize(
    "updates",
    [
        {"Location": "https://example.test/watch?v=SYNTHVID001&t=18s"},
        {"Location": "https://www.youtube.com.evil.test/watch?v=SYNTHVID001"},
        {"Location": "https://www.youtube.com@evil.test/watch?v=SYNTHVID001"},
        {"Location": "https://user@www.youtube.com/watch?v=SYNTHVID001"},
        {"Location": "http://www.youtube.com/watch?v=SYNTHVID001"},
        {"Location": "https://youtu.be/SYNTHVID001"},
        {"Location": "https://www.youtube.com/watch?v=OTHERVID001"},
        {"Location": "https://www.youtube.com/watch?v=short"},
        {"Location": URL + "&v=SYNTHVID001"},
        {"Location": URL + "&t=18s"},
        {"Location": URL + "&start=20"},
        {"Location": URL + "&list=unreviewed"},
        {"Location": URL + "#unreviewed"},
        {"Location": URL.replace("18s", "1m18s")},
        {"Location": URL.replace("18s", "18")},
        {"Location": URL.replace("18s", "-1s")},
        {"Location": URL.replace("18s", "")},
        {"VideoHtml": HTML.replace("SYNTHVID001", "OTHERVID001")},
        {"VideoHtml": HTML.replace("youtube.com", "example.test")},
        {"VideoHtml": HTML.replace("start=0", "start=18")},
        {"VideoHtml": HTML.replace("start=0", "start=7")},
        {"VideoHtml": HTML + "<script>alert('unreviewed')</script>"},
        {"VideoHtml": HTML.replace("frameborder='0'", "onload='unreviewed()'")},
        {"VideoHtml": True},
        {"VideoHtml": 18},
        {"VideoHtml": {"src": "https://www.youtube.com/embed/SYNTHVID001"}},
        {"DataLength": 1},
        {"Type": 8, "Location": r"C:\\External"},
        {"Type": 1, "Location": "video.html"},
        {"SourceType": 1},
        {"NoteType": 4},
    ],
)
def test_unreviewed_or_conflicting_video_facts_refuse_without_publication(
    tmp_path, updates
):
    parts = video_parts(tmp_path)
    change_record(parts, VIDEO, **updates)
    source = write_source(tmp_path, parts)
    before = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "refused", inspected.issues
    assert inspected.receipt is None
    vault = tmp_path / "vault"
    converted = workflow.convert(source, vault)
    assert converted.outcome == "refused", converted.issues
    assert converted.receipt is None and not vault.exists()
    assert source.read_bytes() == before


@pytest.mark.parametrize("html", [None, ""])
@pytest.mark.parametrize("url", [URL, "https://example.test/plain?a=1&b=two%20words"])
def test_plain_external_urls_remain_exact_links_without_video_inference(
    tmp_path, html, url
):
    source = write_source(tmp_path, video_parts(tmp_path, url=url, html=html))
    inspected = default_workflow().inspect(source)
    asset = next(a for a in inspected.inspection.assets if a.asset_id == VIDEO)
    assert asset.video_presentation is None and asset.external_uri == url
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "clean", result.issues
    note = (tmp_path / "vault/Home — Entry thought.md").read_text()
    assert f"- [Reviewed video](<{url}>)" in note
    assert "<iframe" not in note
    report = (tmp_path / "vault/MIGRATION REPORT.md").read_text()
    assert "Video playback" not in report


def test_inspection_and_conversion_never_contact_remote_video_services(
    tmp_path, monkeypatch
):
    def unexpected_network(*args, **kwargs):
        raise AssertionError("Migration attempted network access")

    monkeypatch.setattr(socket, "socket", unexpected_network)
    source = write_source(tmp_path, video_parts(tmp_path))
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    assert {p.name for p in tmp_path.iterdir()} == {"base.brz", "source.brz"}
    converted = workflow.convert(source, tmp_path / "vault")
    assert converted.outcome == "clean", converted.issues
    assert converted.counts.actual_assets == 1
    assert sorted(
        p.name for p in (tmp_path / "vault/Attachments/22222222").iterdir()
    ) == ["Notes.md.original"]


def test_video_cli_agrees_with_library_facts_and_refuses_unknown_metadata(
    tmp_path, capsys
):
    source = write_source(tmp_path, video_parts(tmp_path))
    assert main(["inspect", str(source), "--json"]) == 0
    inspected = json.loads(capsys.readouterr().out)
    asset = next(a for a in inspected["inspection"]["assets"] if a["asset_id"] == VIDEO)
    assert asset["external_uri"] == URL
    assert asset["video_presentation"] == {
        "provider": "youtube",
        "embed_uri": EMBED,
        "start_seconds": 18,
    }
    assert main(["convert", str(source), str(tmp_path / "vault"), "--json"]) == 0
    converted = json.loads(capsys.readouterr().out)
    assert converted["receipt"]["published"] and converted["receipt"]["verified"]
    assert EMBED in (tmp_path / "vault/Home — Entry thought.md").read_text()
    parts = video_parts(tmp_path)
    change_record(
        parts,
        VIDEO,
        VideoHtml="<iframe src='https://example.test/unreviewed'></iframe>",
    )
    source = write_source(tmp_path, parts)
    assert main(["convert", str(source), str(tmp_path / "refused"), "--json"]) == 1
    refused = json.loads(capsys.readouterr().out)
    assert refused["outcome"] == "refused" and refused["receipt"] is None
    assert not (tmp_path / "refused").exists()


def test_video_resource_append_preserves_original_bytes_and_only_bound_note_spans(
    tmp_path,
):
    parts = video_parts(tmp_path)
    target = json.loads(parts["thoughts.json"])
    target.update(Id=TARGET, Name="Topic.v2")
    parts["thoughts.json"] += b"\n" + json.dumps(target).encode()
    body = (
        f"> [Topic](brain://{COMPACT}/title)\r\n"
        '![photo](.data/md-images/photo.png "Caption")\r'
        f"`[literal](brain://{COMPACT}/example)`\n"
        "```md\r\n![literal](.data/md-images/missing.png)\r\n```\r\n"
        "<!-- retained -->\rTail\r\n"
    )
    original = b"\xef\xbb\xbf" + body.encode()
    parts[OWNER + "/Notes.md"] = original
    note_id = json.loads(parts["attachments.json"].splitlines()[0])["Id"]
    change_record(parts, note_id, DataLength=len(original))
    image = "77777777-7777-4777-8777-777777777777"
    add_attachment(parts, image, 12, "photo.png", b"synthetic image bytes")
    source = write_source(tmp_path, parts)
    before = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    document = inspected.inspection.documents[0]
    assert [(r.kind, r.target) for r in document.references] == [
        ("item", TARGET),
        ("image", image),
    ]
    assert (
        document.references[0].expected_original == f"[Topic](brain://{COMPACT}/title)"
    )
    assert (
        document.references[1].expected_original
        == '![photo](.data/md-images/photo.png "Caption")'
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.issues
    active = (vault / "Home — Entry thought.md").read_bytes().decode()
    expected = (
        "> [[Notes/Topic.v2.md|Topic]]\r\n"
        '![photo](Attachments/22222222/photo.png "Caption")\r'
        f"`[literal](brain://{COMPACT}/example)`\n"
        "```md\r\n![literal](.data/md-images/missing.png)\r\n```\r\n"
        "<!-- retained -->\rTail\r\n"
    )
    assert expected in active
    assert active.index(expected) < active.index("## Resources") < active.index(EMBED)
    assert (vault / "Attachments/22222222/Notes.md.original").read_bytes() == original
    assert (
        vault / "Attachments/22222222/photo.png"
    ).read_bytes() == b"synthetic image bytes"
    assert result.counts.actual_references == 2 and result.counts.actual_assets == 2
    assert source.read_bytes() == before


def test_repeated_and_zip_record_reordered_video_inputs_keep_logical_output(tmp_path):
    parts = video_parts(tmp_path)
    second = "99999999-9999-4999-8999-999999999999"
    add_attachment(parts, second, 3, URL.split("&t=", 1)[0], state=None)
    change_record(parts, second, Name="Untimed video", VideoHtml=HTML)
    source = write_source(tmp_path, parts)
    workflow = default_workflow()
    vaults = [tmp_path / name for name in ("first", "repeat", "reordered")]
    for vault in vaults[:2]:
        result = workflow.convert(source, vault)
        assert result.outcome == "clean", result.issues
    parts["attachments.json"] = b"\n".join(
        reversed(parts["attachments.json"].splitlines())
    )
    reordered = tmp_path / "reordered.brz"
    with ZipFile(reordered, "w") as archive:
        for name, data in reversed(list(parts.items())):
            archive.writestr(name, data)
    result = workflow.convert(reordered, vaults[2])
    assert result.outcome == "clean", result.issues
    for name in (
        "Home — Entry thought.md",
        "Attachments/22222222/Notes.md.original",
        "MIGRATION REPORT.md",
    ):
        expected = (vaults[0] / name).read_bytes()
        assert all((vault / name).read_bytes() == expected for vault in vaults[1:])
    records = [
        json.loads((vault / "migration-record.json").read_bytes()) for vault in vaults
    ]
    for record in records:
        assets = {a["asset_id"]: a for a in record["asset_targets"]}
        assert (
            assets[VIDEO]["external_uri"] == URL
            and assets[VIDEO]["video_presentation"]["embed_uri"] == EMBED
        )
        assert assets[second]["video_presentation"] == {
            "provider": "youtube",
            "embed_uri": "https://www.youtube.com/embed/SYNTHVID001?start=0",
            "start_seconds": 0,
        }
        assert (
            assets[VIDEO]["actual_length"] is None
            and assets[VIDEO]["relative_path"] is None
        )
    assert (
        records[0]["adaptations"]
        == records[1]["adaptations"]
        == records[2]["adaptations"]
    )
    assert records[0]["counts"] == records[1]["counts"] == records[2]["counts"]


@pytest.mark.parametrize("local_state", [1, 2, None])
def test_video_metadata_does_not_authorize_local_states_or_unassigned_video_bytes(
    tmp_path, local_state
):
    parts = video_parts(tmp_path)
    if local_state is None:
        parts[OWNER + "/unassigned.mp4"] = b"unassigned remote-video claim"
    else:
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"][VIDEO] = local_state
        parts["meta.json"] = json.dumps(meta).encode()
    source = write_source(tmp_path, parts)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "refused", result.issues
    assert result.receipt is None and not (tmp_path / "vault").exists()
