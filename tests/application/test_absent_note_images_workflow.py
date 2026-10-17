import json
import struct
import zlib

from tests.application.test_verified_coverage import OWNER, add_attachment, source_parts

IMAGE = "77777777-7777-4777-8777-777777777777"
NOTE = "33333333-3333-4333-8333-333333333333"


def png_bytes():
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )


def fallback_parts(tmp_path):
    parts = source_parts(tmp_path)
    records = [json.loads(line) for line in parts["attachments.json"].splitlines()]
    assert len(records) == 1
    note = records[0]
    assert note["Id"] == NOTE
    parts.pop(OWNER + "/" + note["Location"])
    meta = json.loads(parts["meta.json"])
    meta["AttachmentFileStates"][NOTE] = 3
    parts["meta.json"] = json.dumps(meta).encode()
    add_attachment(parts, IMAGE, 12, "card.png", png_bytes())
    return parts


OTHER_IMAGE = "66666666-6666-4666-8666-666666666666"
