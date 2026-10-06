"""Combined v3 archive authored from synthetic source records."""

import json
from zipfile import ZipFile

from tests.application.test_absent_note_images_workflow import png_bytes
from tests.application.test_graph_workflow import identity
from tests.application.test_verified_coverage import add_attachment, change_record
from tests.support.v2_collection import mixed_archive

CARD_BYTES = png_bytes()
ZIP_BYTES = b"PK\x03\x04synthetic opaque ZIP resource\x00\xff"
FORGOTTEN_BYTES = b"forgotten private payload\x00\xff"


def mixed_v3_archive(path):
    mixed_archive(path)
    with ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    thoughts[-1].update(Name="Excluded secret", ForgottenDateTime="2025-01-02T01:02:03")
    # Collision naming must consider the included reserved and created subjects.
    thoughts[9]["Name"] = "Empty"
    parts["thoughts.json"] = b"\n".join(json.dumps(t).encode() for t in thoughts)
    links = [json.loads(line) for line in parts["links.json"].splitlines()]
    for number, parent in ((5001, 1), (5002, 4), (5003, 12)):
        links.append(
            dict(
                links[3],
                Id=identity(number),
                ThoughtIdA=identity(parent),
                ThoughtIdB=identity(2),
            )
        )
    parts["links.json"] = b"\n".join(json.dumps(t).encode() for t in links)
    # Present blank member remains a Document; absence is a separate obligation.
    add_attachment(parts, identity(4001), 1, "Notes.md", b"", owner=identity(4))
    change_record(parts, identity(4001), NoteType=4)
    for key, owner in ((4002, 3), (4003, 2)):
        add_attachment(
            parts,
            identity(key),
            1,
            "Notes.md",
            declared=97,
            state=3,
            owner=identity(owner),
        )
        change_record(parts, identity(key), NoteType=4)
    parts.pop(identity(2) + "/.data/type.png")
    meta = json.loads(parts["meta.json"])
    meta["AttachmentFileStates"][identity(3001)] = 3
    parts["meta.json"] = json.dumps(meta).encode()
    for key, name in ((4010, "z-first.png"), (4011, "a-second.png")):
        add_attachment(parts, identity(key), 12, name, CARD_BYTES, owner=identity(3))
    add_attachment(
        parts, identity(4012), 1, "archive.zip", ZIP_BYTES, owner=identity(9)
    )
    add_attachment(
        parts, identity(4013), 1, "secret.bin", FORGOTTEN_BYTES, owner=identity(12)
    )
    with ZipFile(path, "w") as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    return path
