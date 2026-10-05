"""Independently authored mixed-feature BRZ fixture; no production expectations."""

import base64
import hashlib
import json
from pathlib import Path
from uuid import UUID
from zipfile import ZipFile

from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_verified_coverage import add_attachment, change_record

VIDEO_URL = "https://www.youtube.com/watch?v=SYNTHVID001&t=18s"
VIDEO_EMBED = "https://www.youtube.com/embed/SYNTHVID001?start=18"
VIDEO_HTML = (
    "<iframe width='100%' height='100%' "
    "src='https://www.youtube.com/embed/SYNTHVID001?start=0' "
    "frameborder='0'></iframe>"
)
HOME_BYTES = b"Home prose.\r\n`created: yesterday`\r\n"
TAG_BYTES = b"Tag-owned description.\r\n"
IMAGE_BYTES = b"synthetic local image\x00\xff"
CATEGORY_ICON = b"synthetic category image\x00\xff"
OVERRIDE_ICON = b"synthetic override image\x00\xff"
MANUAL_BYTES = b"manual bytes\x00\xff"
PDF_BYTES = b"%PDF-1.4 synthetic mixed control\r\n%%EOF\r\n"
COMPACT = base64.urlsafe_b64encode(UUID(identity(10)).bytes_le).decode().rstrip("=")
EXCEPTIONAL_TEXT = (
    "# Authored heading\r\n"
    f"> [Reserved](brain://{COMPACT}/ignored)\r"
    '![photo](.data/md-images/photo.png "Caption")\n'
    f"`[literal](brain://{COMPACT}/literal)`\r\n"
    "```md\r\n![literal](.data/md-images/missing.png)\r\n```\r\nTail\r"
)
EXCEPTIONAL_BYTES = b"\xef\xbb\xbf" + EXCEPTIONAL_TEXT.encode()
SUPPORT_PATHS = frozenset(
    {
        "MIGRATION REPORT.md",
        "migration-record.json",
        "Uncreated targets.md",
        "Tag memberships.md",
        "Categories.md",
        "Vault guide.md",
        "Templates/New note.md",
        "Templates/Concept.md",
        "Templates/Category starter.md",
        "Templates/Member template starter.md",
        "Templates/Bases/Members.base",
        "Templates/Bases/Gallery.base",
        "Templates/Bases/Categories.base",
        "Templates/Bases/Starter.base",
        ".obsidian/app.json",
        ".obsidian/bookmarks.json",
        ".obsidian/core-plugins.json",
        ".obsidian/templates.json",
        ".obsidian/types.json",
    }
)
ITEM_PATHS = {
    1: "Home — Opening.md",
    2: "Categories/Concept.md",
    3: "Notes/Empty.md",
    4: "Notes/Override.md",
    5: "Notes/First.md",
    6: "Notes/Middle.md",
    7: "Notes/Last.md",
    8: "Notes/Focus.md",
    9: "Notes/Different marker.md",
    10: "Notes/Reserved.md",
    12: "Notes/Alone.md",
}
CREATED_ITEMS = {1, 2, 3, 4, 6, 8, 9}


def mixed_archive(path):
    graph_archive(
        path,
        {
            1: "Opening",
            2: "Concept",
            3: "Empty",
            4: "Override",
            5: "First",
            6: "Middle",
            7: "Last",
            8: "Focus",
            9: "Different marker",
            10: "Reserved",
            11: "System",
            12: "Alone",
        },
        [
            (2, 3, 1, 2, -1),
            (2, 4, 1, 2, -1),
            (2, 9, 1, 2, -1),
            (5, 6, 1, 1, -1),
            (6, 7, 1, 1, -1),
            (1, 9, 3, 1, -1),
            (8, 1, 1, 5, -1),
            (8, 7, 1, 5, -1),
            (11, 2, 1, 6, -1),
        ],
        kinds={2: 2, 8: 4, 11: 5},
        labels={2: "Definition label", 4: "Own label"},
        notes={1: (HOME_BYTES, 4), 8: (TAG_BYTES, 4), 9: (EXCEPTIONAL_BYTES, 0)},
    )
    with ZipFile(path) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    for t in thoughts:
        n = UUID(t["Id"]).int
        if n in {3, 4, 9}:
            t["TypeId"] = identity(2)
        if n in {2, 4, 8, 9}:
            t.update(
                CreationDateTime="2024-02-29T23:59:58.1234567-11:00",
                ModificationDateTime="2025-01-01T00:00:00+14:00",
            )
        if n == 2:
            t.update(ForegroundColor=-65536, BackgroundColor=-16711936)
        if n == 3:
            t["ThoughtIconInfo"] = "opaque token retained without interpretation"
    parts["thoughts.json"] = "\n".join(json.dumps(t) for t in thoughts).encode()
    for number, kind, name, data, owner in (
        (3001, 5, "type.png", CATEGORY_ICON, 2),
        (3002, 5, "override.png", OVERRIDE_ICON, 4),
        (3003, 12, "photo.png", IMAGE_BYTES, 9),
        (3004, 1, "manual.bin", MANUAL_BYTES, 1),
        (3005, 1, "manual.pdf", PDF_BYTES, 9),
    ):
        add_attachment(parts, identity(number), kind, name, data, owner=identity(owner))
    add_attachment(
        parts,
        identity(3006),
        15,
        identity(3005) + ".txt",
        declared=0,
        state=2,
        owner=identity(9),
    )
    add_attachment(parts, identity(3007), 3, VIDEO_URL, state=None, owner=identity(9))
    change_record(parts, identity(3007), Name="Reviewed video", VideoHtml=VIDEO_HTML)
    add_attachment(
        parts,
        identity(3008),
        8,
        "C:\\unavailable\\directory",
        state=None,
        owner=identity(1),
    )
    with ZipFile(path, "w") as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    return path


def inventory(vault):
    return {
        p.relative_to(vault).as_posix(): (
            len(p.read_bytes()),
            hashlib.sha256(p.read_bytes()).hexdigest(),
        )
        for p in Path(vault).rglob("*")
        if p.is_file()
    }
