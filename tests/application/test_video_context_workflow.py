"""Qualified video context through public BRZ admission and vault generation."""

import json

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.vault_check import check_vault
from tests.application.test_module_seams import METADATA
from tests.application.test_verified_coverage import (
    add_attachment,
    change_record,
    source_parts,
    write_source,
)
from tests.application.test_video_workflow import HTML
from tests.local_acceptance.facts import video as source_video

EMBED_ZERO = "https://www.youtube.com/embed/SYNTHVID001?start=0"
EMBED_TIMED = "https://www.youtube.com/embed/SYNTHVID001?start=18"


def video_source(directory, declarations):
    directory.mkdir(parents=True, exist_ok=True)
    parts = source_parts(directory)
    for number, (url, updates) in enumerate(declarations, 1):
        key = f"aaaaaaaa-0000-4000-8000-{number:012x}"
        add_attachment(parts, key, 3, url, state=None)
        change_record(parts, key, Name=f"Video {number}", **updates)
    records = [json.loads(line) for line in parts["attachments.json"].splitlines()]
    return write_source(directory, parts), records[1:]


def files(directory):
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def test_public_brz_playlist_context_preserves_original_links_and_single_video_players(
    tmp_path,
):
    declarations = (
        ("https://www.youtube.com/watch?v=SYNTHVID001&list=short", {"VideoHtml": HTML}),
        (
            "https://www.youtube.com/watch?index=00&list=other%2Fcontext&v=SYNTHVID001",
            {"VideoHtml": HTML},
        ),
        ("https://www.youtube.com/watch?v=SYNTHVID001", {"VideoHtml": HTML}),
        (
            "https://www.youtube.com/watch?v=SYNTHVID001&t=18s",
            {"VideoHtml": HTML},
        ),
        ("https://www.youtube.com/playlist?list=only%2Bcontext", {}),
    )
    source, originals = video_source(tmp_path / "source", declarations)
    original_bytes = source.read_bytes()
    workflow = default_workflow()
    workflow.metadata_factory = lambda: METADATA
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    assert inspected.receipt is None and not (tmp_path / "vault").exists()
    result = workflow.convert(source, tmp_path / "vault")
    assert result.outcome == "clean", result.issues
    assert result.receipt.verified and result.receipt.published
    assert (result.counts.actual_notes, result.counts.actual_assets) == (1, 1)
    assert result.counts.planned_references == result.counts.actual_references == 0
    vault = tmp_path / "vault"
    note = (vault / "Home — Entry thought.md").read_text(encoding="utf-8")
    record = json.loads((vault / "migration-record.json").read_bytes())
    targets = {asset["asset_id"]: asset for asset in record["asset_targets"]}
    evidence = [
        raw for group in record["original_evidence"] for raw in group["records"]
    ]
    for index, raw in enumerate(originals):
        target = targets[raw["Id"]]
        uri = declarations[index][0]
        assert target["external_uri"] == target["resource_link"] == uri
        assert f"- [Video {index + 1}](<{uri}>)" in note
        assert raw in evidence
        expected = (
            None
            if index == 4
            else {
                "provider": "youtube",
                "embed_uri": EMBED_TIMED if index == 3 else EMBED_ZERO,
                "start_seconds": 18 if index == 3 else 0,
            }
        )
        assert target["video_presentation"] == expected
        assert source_video(raw) == expected
    assert "VideoHtml" not in originals[4]
    assert note.count('<iframe src="' + EMBED_ZERO + '"') == 3
    assert note.count('<iframe src="' + EMBED_TIMED + '"') == 1
    assert note.count("<iframe ") == 4
    adaptations = record["adaptations"]
    assert sum(a["kind"] == "video_embed" for a in adaptations) == 4
    assert sum(a["kind"] == "video_timing" for a in adaptations) == 1
    report = (vault / "MIGRATION REPORT.md").read_text(encoding="utf-8")
    assert "The original resource links remain available" in report
    before_check = files(vault)
    assert check_vault(vault).outcome == "clean"
    assert files(vault) == before_check
    repeated = workflow.convert(source, tmp_path / "repeat")
    assert repeated.receipt.verified and files(tmp_path / "repeat") == before_check
    assert source.read_bytes() == original_bytes


def test_public_brz_opaque_context_variations_do_not_change_player_identity(tmp_path):
    urls = (
        "https://www.youtube.com/watch?v=SYNTHVID001&list=0",
        "https://www.youtube.com/watch?v=SYNTHVID001&list=not-a-PL-prefix-or-fixed-length",
        "https://www.youtube.com/watch?v=SYNTHVID001&list=x&index=0",
        "https://www.youtube.com/watch?v=SYNTHVID001&list=x&index=01",
        "https://www.youtube.com/watch?v=SYNTHVID001&list=x&index=next",
        "https://www.youtube.com/watch?index=%3Copaque%3E&list=%2B%26%3D&v=SYNTHVID001",
    )
    source, originals = video_source(
        tmp_path, tuple((url, {"VideoHtml": HTML}) for url in urls)
    )
    before = source.read_bytes()
    with BrzSourceModule().open(source) as session:
        assets = {asset.asset_id: asset for asset in session.snapshot.assets}
        evidence = [
            raw
            for group in session.snapshot.original_evidence
            for raw in json.loads(group.original_json)
        ]
        for url, raw in zip(urls, originals, strict=True):
            asset = assets[raw["Id"]]
            assert (asset.owner, asset.role, asset.availability) == (
                "22222222-2222-4222-8222-222222222222",
                "url",
                "external",
            )
            assert asset.external_uri == url and raw in evidence
            assert asset.video_presentation.model_dump() == {
                "provider": "youtube",
                "embed_uri": EMBED_ZERO,
                "start_seconds": 0,
            }
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    ("query", "updates", "code"),
    (
        ("v=SYNTHVID001&list=", {}, "unsupported_feature"),
        ("v=SYNTHVID001&list=x&%6cist=y", {}, "unsupported_feature"),
        ("v=SYNTHVID001&list=x&index=", {}, "unsupported_feature"),
        ("v=SYNTHVID001&list=x&index=0&index=1", {}, "unsupported_feature"),
        ("v=SYNTHVID001&v=SYNTHVID001&list=x", {}, "unsupported_feature"),
        ("v=SYNTHVID001&index=1", {}, "unsupported_feature"),
        ("v=SYNTHVID001&list=x&autoplay=1", {}, "unsupported_feature"),
        ("v=SYNTHVID001&list=x&t=18s", {}, "unsupported_feature"),
        ("v=SYNTHVID001&t=18", {}, "unsupported_feature"),
        ("v=SYNTHVID001&t=18s&t=19s", {}, "unsupported_feature"),
        ("v=too-short&list=x", {}, "unsupported_feature"),
        ("list=x", {}, "unsupported_feature"),
        ("v=SYNTHVID002&list=x", {}, "invalid_source"),
        ("v=SYNTHVID001&list=x#fragment", {}, "unsupported_feature"),
        ("v=SYNTHVID001&list=<unsafe>", {}, "invalid_source"),
        ("v=SYNTHVID001&list=x", {"DataLength": 1}, "unsupported_feature"),
        ("v=SYNTHVID001&list=x", {"DataLength": True}, "invalid_source"),
        ("v=SYNTHVID001&list=x", {"Type": 2}, "unsupported_feature"),
        ("v=SYNTHVID001&list=x", {"VideoHtml": True}, "invalid_source"),
        ("v=SYNTHVID001&list=x", {"VideoHtml": HTML + " "}, "unsupported_feature"),
        (
            "v=SYNTHVID001&list=x",
            {"VideoHtml": HTML.replace("www.youtube.com", "other.example")},
            "unsupported_feature",
        ),
        (
            "v=SYNTHVID001&list=x",
            {"BrainId": "99999999-9999-4999-8999-999999999999"},
            "invalid_source",
        ),
    ),
    ids=(
        "empty-list",
        "duplicate-decoded-list",
        "empty-index",
        "duplicate-index",
        "duplicate-video",
        "index-without-list",
        "unknown-key",
        "unqualified-list-timing",
        "invalid-timing",
        "duplicate-timing",
        "invalid-video-id",
        "missing-video",
        "conflicting-video-id",
        "fragment",
        "unsafe-uri",
        "nonzero-length",
        "invalid-length-scalar",
        "non-url-role",
        "nontext-html",
        "unreviewed-html",
        "unreviewed-provider",
        "foreign-brain",
    ),
)
def test_public_brz_video_context_refuses_unsafe_or_ambiguous_source_before_publication(
    tmp_path, query, updates, code
):
    source, _ = video_source(
        tmp_path / "source",
        (("https://www.youtube.com/watch?" + query, {"VideoHtml": HTML, **updates}),),
    )
    before = source.read_bytes()
    sentinel = tmp_path / "caller-owned.txt"
    sentinel.write_bytes(b"Keep exact caller writing.\r\n")
    workflow = default_workflow()
    for result in (
        workflow.inspect(source),
        workflow.convert(source, tmp_path / "unpublished"),
    ):
        assert result.outcome == "refused" and result.receipt is None
        assert result.counts is None
        assert result.issues[0].code == code, result.issues
        assert result.issues[0].phase == "source"
        assert "aaaaaaaa-0000-4000-8000-000000000001" in result.issues[0].affected
    assert source.read_bytes() == before
    assert sentinel.read_bytes() == b"Keep exact caller writing.\r\n"
    assert not (tmp_path / "unpublished").exists()
