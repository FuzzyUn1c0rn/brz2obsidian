"""Independently authored BRZ and Folio representations of one logical collection."""

import base64
import json
from uuid import UUID, uuid5
from zipfile import ZipFile

from tests.application.test_minimal_workflow import FIXTURE

KEYS = (
    "entry:opening",
    "empty:leaf",
    "chain:first",
    "chain:middle",
    "chain:last",
    "tag:focus",
    "tag:unused",
    "peer:left",
    "peer:right",
    "orphan:alone",
)
TITLES = (
    "Opening",
    "Empty",
    "First",
    "Middle",
    "Last",
    "Focus",
    "Unused",
    "Left",
    "Right",
    "Alone",
)
BRAIN = "11111111-1111-4111-8111-111111111111"
CONNECTIONS = (
    (3, 4, "hierarchy"),
    (4, 5, "hierarchy"),
    (8, 9, "related"),
    (6, 1, "tag"),
    (6, 2, "tag"),
)
TAG_BODY = b"Authored tag description.\r\n"
MAP_BYTES = b"synthetic map bytes\x00\xff"
MANUAL_BYTES = b"\x00\x01synthetic manual\xff"


def seed(number):
    return f"{number:08x}000040008000000000000000"


def identity(number):
    return str(UUID(hex=seed(number)))


def paired_sources(path):
    directory = path / "folio"
    directory.mkdir()
    folio_body = b"Welcome [Empty](folio:empty).\r\n![Map](folio:map)\r\n"
    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    brz_body = f"Welcome [Empty](brain://{compact}/Empty).\r\n![Map](.data/md-images/map.png)\r\n".encode()
    folio = {
        "collection": "Synthetic Folio collection",
        "start": KEYS[0],
        "entries": [
            {
                "key": key,
                "seed": seed(n),
                "title": title,
                "role": "tag" if n in (6, 7) else "ordinary",
            }
            for n, (key, title) in enumerate(zip(KEYS, TITLES, strict=True), 1)
        ],
        "connections": [
            {
                "key": f"connection:{n}",
                "kind": kind,
                "item_a": KEYS[a - 1],
                "item_b": KEYS[b - 1],
            }
            for n, (a, b, kind) in enumerate(CONNECTIONS, 1)
        ],
        "assets": [],
        "documents": [],
        "uninterpreted": {
            "explicit_null": None,
            "date": "2026-10-03T12:34:56",
            "number": 1.25,
        },
    }
    asset_specs = (
        (
            101,
            "asset:101:original-opening",
            1,
            "Notes.md",
            "note_original",
            folio_body,
            None,
        ),
        (102, "asset:102:original-tag", 6, "Notes.md", "note_original", TAG_BODY, None),
        (103, "asset:103:image-map", 1, "map.png", "image", MAP_BYTES, None),
        (104, "asset:104:file-manual", 1, "manual.bin", "file", MANUAL_BYTES, None),
        (
            105,
            "asset:105:reference-web",
            1,
            "Website",
            "url",
            None,
            "https://example.invalid/resource",
        ),
        (
            106,
            "asset:106:reference-directory",
            1,
            "Directory",
            "directory",
            None,
            "file:///C:/unavailable/directory",
        ),
    )
    for number, key, owner, name, role, body, uri in asset_specs:
        asset = {
            "key": key,
            "owner": KEYS[owner - 1],
            "seed": seed(number),
            "name": name,
            "role": role,
        }
        if body is not None:
            asset["file"] = f"payload-{number}"
            (directory / asset["file"]).write_bytes(body)
        else:
            asset.update(uri=uri, label=name)
        folio["assets"].append(asset)
    text = folio_body.decode()
    references = []
    for original, kind, target, label in (
        ("[Empty](folio:empty)", "item", KEYS[1], "Empty"),
        ("![Map](folio:map)", "image", "asset:103:image-map", "Map"),
    ):
        start = text.index(original)
        reference = {
            "start": start,
            "end": start + len(original),
            "expected_original": original,
            "kind": kind,
            "target": target,
            "display_text": label,
        }
        if kind == "image":
            reference.update(
                destination_start=text.index("folio:map"),
                destination_end=text.index("folio:map") + len("folio:map"),
            )
        references.append(reference)
    folio["documents"] = [
        {
            "key": "document:opening",
            "owner": KEYS[0],
            "original": "asset:101:original-opening",
            "references": references,
        },
        {"key": "document:tag", "owner": KEYS[5], "original": "asset:102:original-tag"},
    ]
    folio_path = directory / "folio.json"
    folio_path.write_text(json.dumps(folio, ensure_ascii=False), encoding="utf-8")

    records = {f.name: f.read_bytes() for f in FIXTURE.iterdir() if f.is_file()}
    records["thoughts.json"] = "\n".join(
        json.dumps(
            {
                "Id": identity(n),
                "BrainId": BRAIN,
                "Name": title,
                "Kind": 4 if n in (6, 7) else 1,
                "ACType": 0,
            }
        )
        for n, title in enumerate(TITLES, 1)
    ).encode()
    records["links.json"] = "\n".join(
        json.dumps(
            {
                "Id": identity(200 + n),
                "BrainId": BRAIN,
                "ThoughtIdA": identity(a),
                "ThoughtIdB": identity(b),
                "Kind": 1,
                "Relation": 3 if kind == "related" else 1,
                "Meaning": 5 if kind == "tag" else 1,
                "Direction": -1,
            }
        )
        for n, (a, b, kind) in enumerate(CONNECTIONS, 1)
    ).encode()
    records["settings.json"] = json.dumps(
        {"Id": str(uuid5(UUID(BRAIN), "20")), "Value": identity(1)}
    ).encode()
    attachments, states = [], {}
    for number, key, owner, name, role, body, uri in asset_specs:
        body = brz_body if key == "asset:101:original-opening" else body
        attachment = {
            "Id": identity(number),
            "BrainId": BRAIN,
            "SourceId": identity(owner),
            "SourceType": 2,
            "Type": {
                "note_original": 1,
                "image": 12,
                "file": 1,
                "url": 3,
                "directory": 8,
            }[role],
            "NoteType": 4 if role == "note_original" else 0,
            "Location": name,
            "Name": name,
            "DataLength": len(body) if body is not None else 0,
        }
        if role == "url":
            attachment["Location"] = uri
        if role == "directory":
            attachment["Location"] = "C:\\unavailable\\directory"
        attachments.append(attachment)
        if body is not None:
            states[identity(number)] = 1
            prefix = ".data/md-images/" if role == "image" else ""
            records[f"{identity(owner)}/{prefix}{name}"] = body
    records["attachments.json"] = "\n".join(json.dumps(a) for a in attachments).encode()
    records["meta.json"] = json.dumps(
        {"BrainId": BRAIN, "ExchangeFormatVersion": 5, "AttachmentFileStates": states}
    ).encode()
    brz = path / "paired.brz"
    with ZipFile(brz, "w") as archive:
        for name, data in records.items():
            archive.writestr(name, data)
    return brz, folio_path
