"""The narrowly reviewed active NoteType-0 note, through real BRZ workflows."""

import hashlib
import json
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from tests.application.test_links_workflow import COMPACT, TARGET
from tests.application.test_resources_workflow import resource_archive, thought

OWNER = "cccccccc-0000-4000-8000-000000000003"
NOTE = "aaaaaaaa-0000-4000-8000-000000000001"
IMAGE = "aaaaaaaa-0000-4000-8000-000000000002"


def exceptional_archive(path, body, *, resources=(), reverse=False):
    return resource_archive(
        path,
        [
            ({"SourceId": OWNER, "Location": "Notes.md"}, body),
            *resources,
        ],
        thoughts=[thought(OWNER, "Different marker"), thought(TARGET, "Topic.v2")],
        reverse=reverse,
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_sole_ordinary_canonical_note_is_active_with_exact_backup_and_bound_edits(
    tmp_path, reverse
):
    body = (
        "# Authored heading\r\n"
        f"> [Topic](brain://{COMPACT}/informational-title)\r"
        '![photo](.data/md-images/photo.png "Caption")\n'
        f"`[literal](brain://{COMPACT}/example)`\r\n"
        "```md\r\n![literal](.data/md-images/missing.png)\r\n```\r\n"
        "Tail\r"
    )
    original = b"\xef\xbb\xbf" + body.encode()
    source = exceptional_archive(
        tmp_path / "source.brz",
        original,
        resources=[
            ({"SourceId": OWNER, "Type": 12, "Location": "photo.png"}, b"image bytes")
        ],
        reverse=reverse,
    )
    source_before = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    assert inspected.receipt is None and inspected.counts.actual_notes is None
    targets = {t.item_key: t for t in inspected.inspection.item_targets}
    assert targets[OWNER].created and targets[OWNER].creation_reasons == ("content",)
    assert not targets[TARGET].created
    document = next(d for d in inspected.inspection.documents if d.key == NOTE)
    assert document.owner == OWNER and document.original_asset_id == NOTE
    assert document.text_digest == hashlib.sha256(body.encode()).hexdigest()
    assert [(r.kind, r.target) for r in document.references] == [
        ("item", TARGET),
        ("image", IMAGE),
    ]
    assets = {a.asset_id: a for a in inspected.inspection.assets}
    assert assets[NOTE].role == "note_original"
    assert assets[NOTE].actual_length == len(original)
    assert assets[NOTE].actual_sha256 == hashlib.sha256(original).hexdigest()
    assert {a.kind for a in inspected.inspection.adaptations} >= {
        "item_reference",
        "image_reference",
    }
    backup = next(t for t in inspected.inspection.asset_targets if t.asset_id == NOTE)
    assert backup.relative_path == "Attachments/cccccccc/Notes.md.original"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source.brz"]

    vault = tmp_path / "vault"
    converted = workflow.convert(source, vault)
    assert converted.outcome == "clean", converted.issues
    assert converted.receipt.verified and converted.receipt.published
    assert converted.counts.actual_notes == inspected.counts.planned_notes == 2
    assert converted.counts.actual_assets == inspected.counts.planned_assets == 3
    assert (
        converted.counts.actual_references == inspected.counts.planned_references == 2
    )
    expected_authored = (
        "# Authored heading\r\n"
        "> [[Notes/Topic.v2.md|Topic]]\r"
        '![photo](../Attachments/cccccccc/photo.png "Caption")\n'
        f"`[literal](brain://{COMPACT}/example)`\r\n"
        "```md\r\n![literal](.data/md-images/missing.png)\r\n```\r\n"
        "Tail\r"
    )
    active = (vault / "Notes/Different marker.md").read_bytes().decode()
    assert active.endswith("# Different marker\n\n" + expected_authored)
    assert "## Resources" not in active
    assert (vault / backup.relative_path).read_bytes() == original
    assert (vault / "Attachments/cccccccc/photo.png").read_bytes() == b"image bytes"
    manifest = {f.relative_path: f for f in converted.receipt.manifest}
    assert manifest[backup.relative_path].sha256 == hashlib.sha256(original).hexdigest()
    record = json.loads((vault / "migration-record.json").read_bytes())
    retained_attachments = next(
        e["records"]
        for e in record["original_evidence"]
        if e["key"] == "attachments.json"
    )
    source_attachment = next(r for r in retained_attachments if r["Id"] == NOTE)
    assert source_attachment["Type"] == 1
    assert source_attachment["NoteType"] == 0
    imported = next(t for t in record["item_targets"] if t["item_key"] == OWNER)
    assert imported["created"] and imported["creation_reasons"] == ["content"]
    assert imported["documents"][0]["text_digest"] == document.text_digest
    assert record["counts"]["actual_references"] == 2
    report = (vault / "MIGRATION REPORT.md").read_text(encoding="utf-8")
    assert "Created 2 thought notes; preserved 3 present payloads." in report
    assert "Safe original note bytes are retained under Attachments." in report
    assert source.read_bytes() == source_before


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("competitor", [b"Other authored note", b"", b"\xef\xbb\xbf"])
def test_competing_canonical_and_marked_note_candidates_refuse_in_either_order(
    tmp_path, reverse, competitor
):
    source = exceptional_archive(
        tmp_path / "source.brz",
        b"Canonical authored note",
        resources=[
            (
                {"SourceId": OWNER, "Location": "Other.md", "NoteType": 4},
                competitor,
            )
        ],
        reverse=reverse,
    )
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    converted = workflow.convert(source, tmp_path / "vault")
    assert inspected.outcome == converted.outcome == "refused"
    assert inspected.issues == converted.issues
    assert converted.issues[0].code == "invalid_source"
    assert "Multiple thought notes" in converted.issues[0].message
    assert inspected.inspection is None and converted.receipt is None
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize("owner_kind", [2, 4, 5])
def test_nonempty_note_type_zero_is_not_promoted_for_definition_tag_or_system(
    tmp_path, owner_kind
):
    source = exceptional_archive(tmp_path / "source.brz", b"Authored content")
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    next(t for t in thoughts if t["Id"] == OWNER)["Kind"] = owner_kind
    parts["thoughts.json"] = "\n".join(json.dumps(t) for t in thoughts).encode()
    with ZipFile(source, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    converted = workflow.convert(source, tmp_path / "vault")
    assert inspected.outcome == converted.outcome == "refused"
    assert converted.issues[0].code == "unsupported_feature"
    assert "ordinary thought owner" in converted.issues[0].message
    assert converted.receipt is None and not (tmp_path / "vault").exists()


@pytest.mark.parametrize("location", ["draft.md", "nested/Notes.md"])
def test_arbitrary_markdown_file_beside_active_note_stays_a_byte_preserved_resource(
    tmp_path, location
):
    file_body = b"![not an active-note reference](.data/md-images/missing.png)\r\n"
    source = exceptional_archive(
        tmp_path / "source.brz",
        b"Canonical authored note\r",
        resources=[({"SourceId": OWNER, "Location": location}, file_body)],
    )
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    assert [d.key for d in inspected.inspection.documents if d.owner == OWNER] == [NOTE]
    assert inspected.counts.source_references == 0
    asset = next(a for a in inspected.inspection.assets if a.asset_id == IMAGE)
    assert asset.role == "file" and asset.original_name == location
    target = next(t for t in inspected.inspection.asset_targets if t.asset_id == IMAGE)
    assert target.resource_link and not target.relative_path.endswith(".original")
    vault = tmp_path / "vault"
    converted = workflow.convert(source, vault)
    assert converted.outcome == "clean", converted.issues
    assert (vault / target.relative_path).read_bytes() == file_body
    active = (vault / "Notes/Different marker.md").read_bytes()
    assert b"Canonical authored note\r" in active
    assert file_body not in active
    assert b"## Resources" in active


def test_lowercase_filename_alone_is_a_resource_not_a_canonical_thought_note(tmp_path):
    body = b"![not active](.data/md-images/missing.png)\r\n"
    source = exceptional_archive(tmp_path / "source.brz", body)
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    records = [json.loads(line) for line in parts["attachments.json"].splitlines()]
    next(r for r in records if r["Id"] == NOTE)["Location"] = "notes.md"
    parts["attachments.json"] = "\n".join(json.dumps(r) for r in records).encode()
    parts[OWNER + "/notes.md"] = parts.pop(OWNER + "/Notes.md")
    with ZipFile(source, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    assert not any(d.owner == OWNER for d in inspected.inspection.documents)
    assert (
        next(a for a in inspected.inspection.assets if a.asset_id == NOTE).role
        == "file"
    )
    assert inspected.counts.source_references == 0
    vault = tmp_path / "vault"
    converted = workflow.convert(source, vault)
    assert converted.outcome == "clean", converted.issues
    assert (vault / "Attachments/cccccccc/notes.md").read_bytes() == body
    active = (vault / "Notes/Different marker.md").read_bytes()
    assert body not in active and b"## Resources" in active


@pytest.mark.parametrize(
    "change,code",
    [
        ("missing_bytes", "missing_required_payload"),
        ("state", "missing_required_payload"),
        ("length", "invalid_source"),
        ("invalid_utf8", "invalid_source"),
        ("foreign_brain", "invalid_source"),
        ("missing_owner", "invalid_source"),
        ("foreign_source_type", "unsupported_feature"),
        ("icon_flag", "unsupported_feature"),
        ("special_role", "unsupported_feature"),
        ("unknown_note_type", "unsupported_feature"),
        ("duplicate_physical_candidate", "invalid_source"),
        ("crc", "invalid_source"),
    ],
)
def test_exceptional_candidate_does_not_bypass_integrity_ownership_or_role_checks(
    tmp_path, change, code
):
    body = b"Distinctive authored note"
    source = exceptional_archive(tmp_path / "source.brz", body)
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    records = [json.loads(line) for line in parts["attachments.json"].splitlines()]
    note = next(r for r in records if r["Id"] == NOTE)
    meta = json.loads(parts["meta.json"])
    if change == "missing_bytes":
        del parts[OWNER + "/Notes.md"]
    elif change == "state":
        meta["AttachmentFileStates"][NOTE] = 2
    elif change == "length":
        note["DataLength"] += 1
    elif change == "invalid_utf8":
        parts[OWNER + "/Notes.md"] = b"\xff" + body[1:]
    elif change == "foreign_brain":
        note["BrainId"] = "eeeeeeee-0000-4000-8000-000000000004"
    elif change == "missing_owner":
        note["SourceId"] = "eeeeeeee-0000-4000-8000-000000000004"
    elif change == "foreign_source_type":
        note["SourceType"] = 1
    elif change == "icon_flag":
        note["IsIcon"] = True
    elif change == "special_role":
        note["IsWallpaper"] = True
    elif change == "unknown_note_type":
        note["NoteType"] = 1
    elif change == "duplicate_physical_candidate":
        records.append(dict(note, Id=IMAGE))
        meta["AttachmentFileStates"][IMAGE] = 1
    parts["attachments.json"] = "\n".join(json.dumps(r) for r in records).encode()
    parts["meta.json"] = json.dumps(meta).encode()
    with ZipFile(source, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    if change == "crc":
        raw = source.read_bytes()
        assert raw.count(body) == 1
        source.write_bytes(raw.replace(body, b"DISTINCTIVE authored note"))
    source_before = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    converted = workflow.convert(source, tmp_path / "vault")
    assert inspected.outcome == converted.outcome == "refused"
    assert inspected.issues == converted.issues
    assert converted.issues[0].code == code
    assert converted.issues[0].guidance
    assert inspected.inspection is None and converted.receipt is None
    assert not (tmp_path / "vault").exists()
    assert source.read_bytes() == source_before


@pytest.mark.parametrize(
    "body,code",
    [
        ("![missing](.data/md-images/missing.png)", "invalid_reference"),
        ("[missing](brain://AAAAAAAAAAAAAAAAAAAAAA/title)", "invalid_reference"),
        (f"[Topic][ref]\n\n[ref]: brain://{COMPACT}/title", "unsupported_feature"),
        (f'<a href="brain://{COMPACT}/title">Topic</a>', "unsupported_feature"),
    ],
)
def test_active_note_type_zero_requires_supported_resolvable_references(
    tmp_path, body, code
):
    source = exceptional_archive(tmp_path / "source.brz", body.encode())
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    converted = workflow.convert(source, tmp_path / "vault")
    assert inspected.outcome == converted.outcome == "refused"
    assert inspected.issues == converted.issues
    assert converted.issues[0].code == code
    assert converted.receipt is None and not (tmp_path / "vault").exists()


def test_cli_inspection_and_verified_conversion_agree_on_exceptional_note(
    tmp_path, capsys
):
    source = exceptional_archive(
        tmp_path / "source.brz", f"[Topic](brain://{COMPACT}/title)\r\n".encode()
    )
    assert main(["inspect", str(source), "--json"]) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["outcome"] == "clean" and planned["receipt"] is None
    assert planned["counts"]["planned_notes"] == 2
    assert planned["counts"]["planned_references"] == 1
    assert (
        next(d for d in planned["inspection"]["documents"] if d["key"] == NOTE)[
            "original_asset_id"
        ]
        == NOTE
    )
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 0
    captured = capsys.readouterr()
    actual = json.loads(captured.out)
    assert captured.err == ""
    assert actual["outcome"] == "clean"
    assert actual["receipt"]["verified"] and actual["receipt"]["published"]
    assert actual["counts"]["actual_notes"] == planned["counts"]["planned_notes"]
    assert (
        actual["counts"]["actual_references"] == planned["counts"]["planned_references"]
    )
    assert (vault / "Attachments/cccccccc/Notes.md.original").read_bytes() == (
        f"[Topic](brain://{COMPACT}/title)\r\n".encode()
    )


def test_cli_refuses_competing_candidates_without_a_published_receipt(tmp_path, capsys):
    source = exceptional_archive(
        tmp_path / "source.brz",
        b"Canonical content",
        resources=[
            ({"SourceId": OWNER, "Location": "Other.md", "NoteType": 4}, b"Other")
        ],
    )
    assert main(["inspect", str(source), "--json"]) == 1
    planned = json.loads(capsys.readouterr().out)
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 1
    captured = capsys.readouterr()
    actual = json.loads(captured.out)
    assert planned["outcome"] == actual["outcome"] == "refused"
    assert planned["issues"] == actual["issues"]
    assert actual["issues"][0]["code"] == "invalid_source"
    assert actual["receipt"] is None and captured.err == ""
    assert not vault.exists()
