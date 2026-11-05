"""Small independently authored source versions for public update journeys."""

import json
import struct
import zlib
from zipfile import ZipFile

from tests.application.test_graph_workflow import identity
from tests.support.type_tag_sources import BRAIN, EDGES, TYPE_FIELDS, brz_source

INDEPENDENT = identity(19)


def pixel(red, green, blue):
    def chunk(kind, value):
        return (
            struct.pack(">I", len(value))
            + kind
            + value
            + struct.pack(">I", zlib.crc32(kind + value))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">2I5B", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes((0, red, green, blue))))
        + chunk(b"IEND", b"")
    )


GREEN = pixel(0, 255, 0)
BLUE = pixel(0, 0, 255)
YELLOW = pixel(255, 255, 0)


def update_source(path, *, version=1):
    fields = dict(TYPE_FIELDS)
    edges = EDGES
    if version >= 2:
        fields[11] = 14  # B moves from A to E; C remains a direct member of B.
        edges = tuple(
            (14, 11, 1, 3, -1)
            if e == (10, 11, 1, 3, -1)
            else (17, 18, 1, 7, -1)
            if e == (18, 17, 1, 7, -1)
            else e
            for e in edges
        ) + ((17, 12, 1, 5, -1), (13, 15, 3, 1, -1))
    brz_source(path, edges=edges, type_fields=fields)
    with ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    thoughts.append(
        {
            "Id": INDEPENDENT,
            "BrainId": BRAIN,
            "Name": "Independent",
            "Kind": 1,
            "ACType": 0,
            "Label": None,
            "ForgottenDateTime": None,
        }
    )
    parts["thoughts.json"] = b"\n".join(json.dumps(row).encode() for row in thoughts)
    attachments = [json.loads(line) for line in parts["attachments.json"].splitlines()]
    meta = json.loads(parts["meta.json"])
    for number, label in ((11, "B"), (12, "C"), (17, "T"), (19, "Independent")):
        raw = f"Source {label} v{version}.\r\n".encode()
        asset = identity(2100 + number)
        attachments.append(
            {
                "Id": asset,
                "BrainId": BRAIN,
                "SourceId": identity(number),
                "SourceType": 2,
                "Type": 1,
                "NoteType": 4,
                "Location": "Notes.md",
                "Name": "Notes.md",
                "DataLength": len(raw),
            }
        )
        meta["AttachmentFileStates"][asset] = 1
        parts[identity(number) + "/Notes.md"] = raw
    icon = GREEN if version == 1 else BLUE
    attachments[0]["DataLength"] = len(icon)
    parts[identity(10) + "/.data/Icon.png"] = icon
    parts["attachments.json"] = b"\n".join(
        json.dumps(row).encode() for row in attachments
    )
    parts["meta.json"] = json.dumps(meta).encode()
    with ZipFile(path, "w") as archive:
        for name, raw in parts.items():
            archive.writestr(name, raw)
    return path
