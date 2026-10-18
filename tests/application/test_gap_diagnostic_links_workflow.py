"""Canonical diagnostic links through actual public inspection and publication."""

import json
from zipfile import ZipFile

from tests.application.test_absent_note_images_workflow import png_bytes
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_verified_coverage import add_attachment

BODY = "café source prose\r\n[authored brackets] | pipe\rUnchanged `literal`\n".encode()


def diagnostic_parts(tmp_path, role, title):
    names = {1: "Home", 2: "Card", 3: "Category", 4: "Member"}
    names[2 if role == "ordinary_note" else 3] = title
    if role == "definition_icon":
        names[4] = title
    source = graph_archive(
        tmp_path / "base.brz",
        names,
        [(3, 4, 1, 2, -1)],
        kinds={3: 2},
        notes={1: (BODY, 4), 2: (b"unknown card", 4), 3: (BODY, 4), 4: (BODY, 4)},
    )
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    thoughts[-1]["TypeId"] = identity(3)
    parts["thoughts.json"] = b"\n".join(json.dumps(t).encode() for t in thoughts)
    if role in {"ordinary_note", "definition_note"}:
        owner = 2 if role == "ordinary_note" else 3
        parts.pop(identity(owner) + "/Notes.md")
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"][identity(2000 + owner)] = 3
        parts["meta.json"] = json.dumps(meta).encode()
        if role == "ordinary_note":
            add_attachment(
                parts, identity(3001), 12, "card.png", png_bytes(), owner=identity(2)
            )
    else:
        add_attachment(
            parts, identity(3001), 5, "type.png", declared=7, state=3, owner=identity(3)
        )
    return parts


TITLE_ALIASES = [
    ("Plain card", "Plain card"),
    ("Card [Example]", "Card Example"),
    ("Card|Example", "Card Example"),
    ("Card  Example", "Card Example"),
    ("Card\r\nExample", "Card Example"),
    ("  Card Example  ", "Card Example"),
    ("Card\t[Example] | Details", "Card Example Details"),
    (" 雲\u3000[例]\t|\u00a0café ", "雲 例 café"),
]
