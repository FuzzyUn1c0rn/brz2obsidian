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
        fields[11] = 14
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
    for number, label in (
        (11, "B"),
        (12, "C"),
        (13, "D"),
        (16, "G"),
        (17, "T"),
        (19, "Independent"),
    ):
        raw = f"Source {label} v{version}.\r\n".encode()
        if number == 13:
            label = "Original reference" if version == 1 else "Updated reference"
            raw += (
                f"[{label}](brain://api.thebrain.com/EREREREREUGBEREREREREQ/"
                f"AAAAAAAAAAAAAAAAAAAAEw/version-{version})\r\n"
            ).encode()
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
    attachments.append(
        {
            "Id": identity(2200),
            "BrainId": BRAIN,
            "SourceId": INDEPENDENT,
            "SourceType": 2,
            "Type": 3,
            "NoteType": 0,
            "DataLength": 0,
            "Location": (
                "https://www.youtube.com/watch?index=00&list=original%2Fcontext&v=SYNTHVID001"
                if version == 1
                else "https://www.youtube.com/watch?list=updated%2Bcontext&v=SYNTHVID002&index=next"
            ),
            "Name": "Original video" if version == 1 else "Updated video",
            "VideoHtml": (
                "<iframe width='100%' height='100%' "
                "src='https://www.youtube.com/embed/SYNTHVID001?start=0' "
                "frameborder='0'></iframe>"
            ).replace("SYNTHVID001", "SYNTHVID002" if version >= 2 else "SYNTHVID001"),
        }
    )
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
