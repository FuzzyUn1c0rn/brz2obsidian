"""Authored raw records for the three adaptations, with established v3 coverage."""

import base64
import json
from uuid import UUID
from zipfile import ZipFile

from tests.application.test_graph_workflow import identity
from tests.application.test_sized_images_workflow import images
from tests.application.test_verified_coverage import add_attachment, change_record
from tests.support.v3_collection import mixed_v3_archive


def compact(number):
    return (
        base64.urlsafe_b64encode(UUID(identity(number)).bytes_le).decode().rstrip("=")
    )


HOME_TEXT = (
    "α <Enter> / <type>\r\n"
    f"[private <Secret>](brain://{compact(12)}/ignored)"
    f"[<Value>](brain://{compact(5)}/ignored) "
    '![<Alt>](.data/md-images/picture.png#$width=75p$ "Caption")\r'
    "`<Code> </Enter>` \\<Escaped> <https://example.invalid>\n"
    "```md\n<Enter></Enter> ![fake](.data/md-images/missing.png)\n```\n"
)
SECOND_TEXT = (
    "Press <Password> / <username> / <IP-Adress>.\n"
    '![blue](.data/md-images/picture.png#$width=90p$ "Second")\r\n'
    f"[live](brain://{compact(1)}/ignored)\n"
)
EXTERNAL_LOCATIONS = (
    r"C:\training\é #1\manual.pdf",
    r"D:\other\manual.pdf",
    r"C:\training\only.pdf",
)


def combined_archive(path):
    mixed_v3_archive(path)
    with ZipFile(path) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    for owner, body in ((1, HOME_TEXT.encode()), (9, SECOND_TEXT.encode())):
        rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
        document = next(
            r
            for r in rows
            if r["SourceId"] == identity(owner) and r["Location"] == "Notes.md"
        )
        parts[identity(owner) + "/Notes.md"] = body
        change_record(parts, document["Id"], DataLength=len(body))
    red, blue = images()
    for key, owner, data in ((6001, 1, red), (6002, 9, blue)):
        add_attachment(
            parts, identity(key), 12, "picture.png", data, owner=identity(owner)
        )
    for key, owner, location in (
        (6011, 9, EXTERNAL_LOCATIONS[0]),
        (6012, 9, EXTERNAL_LOCATIONS[1]),
        (6013, 5, EXTERNAL_LOCATIONS[2]),
        (6014, 12, r"C:\private\secret.pdf"),
    ):
        add_attachment(
            parts, identity(key), 2, location, state=None, owner=identity(owner)
        )
        change_record(parts, identity(key), Name="manual.pdf", DataLength=971)
    add_attachment(
        parts,
        identity(6015),
        8,
        r"C:\combined\directory",
        state=None,
        owner=identity(9),
    )
    with ZipFile(path, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return path
