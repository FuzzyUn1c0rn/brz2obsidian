import json
from pathlib import Path
from zipfile import ZipFile

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


def thought(key, title):
    return {
        "Id": key,
        "BrainId": BRAIN,
        "Kind": 1,
        "ACType": 0,
        "Name": title,
        "TagIds": [],
    }


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
