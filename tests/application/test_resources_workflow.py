import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow

FIXTURE = Path(__file__).parents[1] / "fixtures" / "minimal"
HOME = "22222222-2222-4222-8222-222222222222"
BRAIN = "11111111-1111-4111-8111-111111111111"


def resource_archive(path, resources, *, thoughts=(), extras=(), reverse=False):
    files = {
        p.relative_to(FIXTURE).as_posix(): p.read_bytes()
        for p in FIXTURE.rglob("*")
        if p.is_file()
    }
    attachments = [json.loads(files["attachments.json"])]
    meta = json.loads(files["meta.json"])
    for index, resource in enumerate(resources, 1):
        record = {
            "Id": f"aaaaaaaa-0000-4000-8000-{index:012x}",
            "BrainId": BRAIN,
            "SourceId": HOME,
            "SourceType": 2,
            "Type": 1,
            "NoteType": 0,
            "Location": "file.bin",
            "DataLength": 0,
        }
        record.update(resource[0])
        data = resource[1]
        attachments.append(record)
        if data is not None:
            record.setdefault("DataLength", len(data))
            if "DataLength" not in resource[0]:
                record["DataLength"] = len(data)
            meta["AttachmentFileStates"][record["Id"]] = 1
            prefix = (
                ".data/"
                if record["Type"] == 5
                else (".data/md-images/" if record["Type"] == 12 else "")
            )
            files[record["SourceId"] + "/" + prefix + record["Location"]] = data
    files.update(extras)
    files["meta.json"] = json.dumps(meta).encode()
    files["attachments.json"] = "\n".join(
        json.dumps(r) for r in (reversed(attachments) if reverse else attachments)
    ).encode()
    items = [json.loads(files["thoughts.json"])] + list(thoughts)
    files["thoughts.json"] = "\n".join(
        json.dumps(r) for r in (reversed(items) if reverse else items)
    ).encode()
    with ZipFile(path, "w") as archive:
        for name, data in reversed(list(files.items())) if reverse else files.items():
            archive.writestr(name, data)
    return path


def test_generic_files_and_external_resources_preserve_bytes_and_destinations(tmp_path):
    source = resource_archive(
        tmp_path / "source.brz",
        [
            ({"Location": "manual.weird", "Name": "Manual"}, b"\x00\x01binary\xff"),
            (
                {
                    "Type": 3,
                    "Location": "https://example.invalid/path?q=1",
                    "Name": "Website",
                },
                None,
            ),
            (
                {
                    "Type": 8,
                    "Location": "C:\\unavailable\\directory",
                    "Name": "Directory",
                },
                None,
            ),
        ],
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean"
    copied = vault / "Attachments/22222222/manual.weird"
    assert copied.read_bytes() == b"\x00\x01binary\xff"
    assert (
        hashlib.sha256(copied.read_bytes()).hexdigest()
        == "045dd13b31563c2e7ab2cd6676c484b542d64b39f01d66ad563ce3a0ecdc1b18"
    )
    home = (vault / "Home — Entry thought.md").read_text(encoding="utf-8")
    assert "## Resources" in home
    assert "[[Attachments/22222222/manual.weird|Manual]]" in home
    assert "[Website](<https://example.invalid/path?q=1>)" in home
    assert "[Directory](<file:///C:/unavailable/directory>)" in home
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert len(record["asset_targets"]) == 4
    assert result.counts.planned_assets == 2


def thought(key, title):
    return {
        "Id": key,
        "BrainId": BRAIN,
        "Kind": 1,
        "ACType": 0,
        "Name": title,
        "TagIds": [],
    }


def test_resource_eligibility_and_original_backups_use_verified_roles(tmp_path):
    file_owner = "bbbbbbbb-0000-4000-8000-000000000001"
    image_owner = "bbbbbbbb-1111-4000-8000-000000000002"
    decoration_owner = "cccccccc-0000-4000-8000-000000000003"
    source = resource_archive(
        tmp_path / "source.brz",
        [
            (
                {"SourceId": file_owner, "Location": "authored.md"},
                b"generic markdown attachment",
            ),
            (
                {"SourceId": image_owner, "Type": 12, "Location": "photo.png"},
                b"image bytes",
            ),
            (
                {
                    "SourceId": decoration_owner,
                    "Type": 5,
                    "IsIcon": True,
                    "Location": "icon.png",
                },
                b"icon bytes",
            ),
            ({"SourceId": decoration_owner, "Location": "Notes.md"}, b"\xef\xbb\xbf"),
        ],
        thoughts=[
            thought(file_owner, "File owner"),
            thought(image_owner, "Image owner"),
            thought(decoration_owner, "Decorated"),
        ],
    )
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean"
    selected = {t.item_key: t.created for t in inspected.inspection.item_targets}
    assert selected == {
        HOME: True,
        file_owner: True,
        image_owner: True,
        decoration_owner: False,
    }
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "clean"
    assert (
        vault / "Attachments/bbbbbbbb0000/authored.md"
    ).read_bytes() == b"generic markdown attachment"
    assert (vault / "Attachments/bbbbbbbb1111/photo.png").read_bytes() == b"image bytes"
    assert (vault / "Attachments/cccccccc/icon.png").read_bytes() == b"icon bytes"
    assert (
        vault / "Attachments/cccccccc/Notes.md.original"
    ).read_bytes() == b"\xef\xbb\xbf"
    assert not (vault / "Notes/Decorated.md").exists()
    assert (
        "generic markdown attachment" not in (vault / "Notes/File owner.md").read_text()
    )
    assert (
        "[[Attachments/bbbbbbbb1111/photo.png|photo.png]]"
        in (vault / "Notes/Image owner.md").read_text()
    )
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert (
        len(
            [
                e
                for e in record["source_accounting"]["entries"]
                if e["identity"].startswith("payload:")
            ]
        )
        == 5
    )


def test_whitespace_canonical_note_does_not_force_materialization(tmp_path):
    owner = "cccccccc-0000-4000-8000-000000000003"
    source = resource_archive(
        tmp_path / "source.brz",
        [({"SourceId": owner, "Location": "Notes.md"}, b" \r\n")],
        thoughts=[thought(owner, "Whitespace")],
    )
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    result = workflow.convert(source, tmp_path / "vault")
    assert inspected.outcome == result.outcome == "clean"
    target = next(t for t in inspected.inspection.item_targets if t.item_key == owner)
    assert not target.created
    assert not (tmp_path / "vault/Notes/Whitespace.md").exists()
    assert (
        tmp_path / "vault/Attachments/cccccccc/Notes.md.original"
    ).read_bytes() == b" \r\n"


def test_resource_collisions_extend_seeds_preserve_extensions_and_ignore_record_order(
    tmp_path,
):
    resources = [
        ({"Location": "report?.pdf"}, b"first"),
        ({"Location": "REPORT*.pdf"}, b"second"),
        ({"Location": "Notes.md.original"}, b"ordinary file"),
    ]
    records = []
    for index, reverse in enumerate((False, True)):
        source = resource_archive(
            tmp_path / f"source{index}.brz", resources, reverse=reverse
        )
        vault = tmp_path / f"vault{index}"
        result = default_workflow().convert(source, vault)
        assert result.outcome == "clean"
        record = json.loads((vault / "migration-record.json").read_bytes())
        mappings = {a["asset_id"]: a["relative_path"] for a in record["asset_targets"]}
        records.append(mappings)
        assert (
            vault / "Attachments/22222222/report — aaaaaaaa000040008000000000000001.pdf"
        ).read_bytes() == b"first"
        assert (
            vault / "Attachments/22222222/REPORT — aaaaaaaa000040008000000000000002.pdf"
        ).read_bytes() == b"second"
        assert (
            vault / "Attachments/22222222/Notes — 33333333.md.original"
        ).read_bytes() == b"Authored body.\r\n"
        assert (
            vault / "Attachments/22222222/Notes.md — aaaaaaaa.original"
        ).read_bytes() == b"ordinary file"
        assert len({p.casefold() for p in mappings.values()}) == 4
    assert records[0] == records[1]


@pytest.mark.parametrize(
    "record,data,extras,code",
    [
        (
            {"Type": 15, "Location": "absent.txt", "DataLength": 100},
            None,
            (),
            "unsupported_feature",
        ),
        ({"Type": 99}, b"unknown", (), "unsupported_feature"),
        (
            {"Type": 5, "IsIcon": True, "Location": "icon.png", "DataLength": -1},
            b"icon",
            (),
            "invalid_source",
        ),
        ({"DataLength": 99}, b"file", (), "invalid_source"),
        ({"SourceType": True}, b"file", (), "invalid_source"),
        ({"Type": True}, b"file", (), "invalid_source"),
        ({"IsWallpaper": True}, b"file", (), "unsupported_feature"),
        ({}, None, (), "missing_required_payload"),
        ({"Type": 12, "Location": "image.png"}, None, (), "missing_required_payload"),
        (
            {"Type": 5, "IsIcon": True, "Location": "icon.png"},
            None,
            (),
            "missing_required_payload",
        ),
        ({}, b"file", ((HOME + "/unaccounted.bin", b"orphan"),), "unsupported_feature"),
    ],
)
def test_unsupported_roles_missing_bytes_and_unaccounted_payloads_refuse(
    tmp_path, record, data, extras, code
):
    source = resource_archive(tmp_path / "source.brz", [(record, data)], extras=extras)
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    result = workflow.convert(source, tmp_path / "vault")
    assert inspected.outcome == result.outcome == "refused"
    assert result.issues[0].code == code
    assert result.receipt is None
    assert not (tmp_path / "vault").exists()


def test_local_binary_inventory_and_copy_use_streams(tmp_path, monkeypatch):
    data = b"stream this binary" * 200000
    source = resource_archive(
        tmp_path / "source.brz", [({"Location": "large.bin"}, data)]
    )
    original_read = ZipFile.read

    def metadata_or_document_read(archive, name, *args, **kwargs):
        assert not str(name).endswith(".bin"), "binary payload must be streamed"
        return original_read(archive, name, *args, **kwargs)

    monkeypatch.setattr(ZipFile, "read", metadata_or_document_read)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean"
    assert (vault / "Attachments/22222222/large.bin").read_bytes() == data


def test_corrupt_binary_crc_prevents_publication(tmp_path):
    source = resource_archive(
        tmp_path / "source.brz",
        [({"Location": "file.bin"}, b"distinctive binary payload")],
    )
    raw = source.read_bytes()
    source.write_bytes(
        raw.replace(b"distinctive binary payload", b"DISTINCTIVE binary payload")
    )
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "refused"
    assert result.issues[0].code == "invalid_source"
    assert not (tmp_path / "vault").exists()


def test_inline_image_adaptation_is_available_through_inspection(tmp_path):
    source = resource_archive(
        tmp_path / "source.brz",
        [({"Type": 12, "Location": "photo.png"}, b"image bytes")],
    )
    with ZipFile(source) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files[HOME + "/Notes.md"] = b"![photo](.data/md-images/photo.png)"
    records = [json.loads(line) for line in files["attachments.json"].splitlines()]
    records[0]["DataLength"] = len(files[HOME + "/Notes.md"])
    files["attachments.json"] = "\n".join(json.dumps(r) for r in records).encode()
    with ZipFile(source, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    result = default_workflow().inspect(source)
    assert result.outcome == "clean"
    assert result.counts.planned_references == 1
