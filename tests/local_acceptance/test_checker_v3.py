"""Public raw-source oracle controls for the reviewed scoped conversion."""

import base64
import hashlib
import json
import struct
import zlib
from uuid import UUID
from zipfile import ZipFile

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_absent_note_images_workflow import (
    IMAGE,
    fallback_parts,
    png_bytes,
)
from tests.application.test_forgotten_workflow import forget
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_verified_coverage import add_attachment, write_source
from tests.local_acceptance.checker import ROOTS, check_vault, load_json
from tests.local_acceptance.test_checker_v2 import rewrite_record


def mixed_v3_archive(path):
    """Independent synthetic raw joins covering interacting v3 behavior."""
    compact = base64.urlsafe_b64encode(UUID(identity(8)).bytes_le).decode().rstrip("=")
    live = base64.urlsafe_b64encode(UUID(identity(9)).bytes_le).decode().rstrip("=")
    body = f"Home prose\r\n[![private](https://example.invalid/card)](brain://{compact}/private)\rafter [reserved](brain://{live}/same-title)\n![authored](.data/md-images/home.png)\n`literal brain://{live}`"
    graph_archive(
        path,
        {
            1: "Home",
            2: "Concept",
            3: "Member",
            4: "Override",
            5: "Image owner",
            6: "TXT owner",
            7: "Excluded provider",
            8: "Same title",
            9: "Same title",
            10: "Excluded member",
        },
        [
            (1, 2, 1, 1, -1),
            (2, 3, 1, 2, -1),
            (2, 4, 1, 2, -1),
            (7, 9, 1, 2, -1),
            (2, 10, 1, 2, -1),
            (1, 8, 1, 1, -1),
        ],
        kinds={2: 2, 7: 2},
        labels={2: "Retained category label", 8: "Private label"},
        notes={
            1: (body.encode(), 4),
            2: (b"absent definition", 4),
            3: (b"\xef\xbb\xbf", 4),
            5: (b"unknown", 4),
            8: (b"private payload", 4),
        },
    )
    with ZipFile(path) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    forget(parts, 7, 8, 10)
    rows = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    for row in rows:
        if row["Id"] in {identity(3), identity(4), identity(10)}:
            row["TypeId"] = identity(2)
        if row["Id"] == identity(9):
            row["TypeId"] = identity(7)
    parts["thoughts.json"] = b"\n".join(json.dumps(r).encode() for r in rows)
    meta = json.loads(parts["meta.json"])
    for n in (2, 5):
        parts.pop(identity(n) + "/Notes.md")
        meta["AttachmentFileStates"][identity(2000 + n)] = 3
    parts["meta.json"] = json.dumps(meta).encode()
    add_attachment(
        parts, identity(3001), 5, "type.png", declared=9, state=3, owner=identity(2)
    )
    add_attachment(
        parts, identity(3002), 5, "override.png", png_bytes(), owner=identity(4)
    )
    add_attachment(
        parts,
        identity(3003),
        12,
        "z-first.webp",
        base64.b64decode("UklGRhwAAABXRUJQVlA4TA8AAAAvAQAAAAfQ/4j+ByKi/wEA"),
        owner=identity(5),
    )
    add_attachment(
        parts, identity(3004), 12, "a-last.png", png_bytes(), owner=identity(5)
    )
    add_attachment(
        parts, identity(3005), 12, "home.png", png_bytes(), owner=identity(1)
    )
    add_attachment(
        parts, identity(3008), 12, "private.png", png_bytes(), owner=identity(8)
    )
    add_attachment(parts, identity(3006), 1, "empty.pdf", b"", owner=identity(6))
    add_attachment(
        parts,
        identity(3007),
        15,
        identity(3006) + ".txt",
        declared=0,
        state=2,
        owner=identity(6),
    )
    parts["brainusers.json"] = (
        '{"Id":"'
        + identity(8201)
        + '","Nested":"{\\"SourceId\\":\\"'
        + identity(8)
        + '\\"}","Value":"private sibling"}\n'
        '{"Id":"'
        + identity(8202)
        + '","Nested":{"AttachmentId":"'
        + identity(8201)
        + '"},"Value":"private transitive"}\n'
        '{"Id":"'
        + identity(8203)
        + '","Precise":0.12345678901234567890123456789,"Null":null}'
    ).encode()
    with ZipFile(path, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return path


def image_candidate(tmp_path):
    source = write_source(tmp_path, fallback_parts(tmp_path))
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    check_vault(source, vault)
    return (
        source,
        vault,
        result,
        load_json((vault / "migration-record.json").read_bytes()),
    )


def forge_image_source(source, vault, record, result, image_bytes, name="card.png"):
    """Forge raw declarations, exact output bytes, observations and honest receipts."""
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    rows = [
        json.loads(line)
        for line in parts["attachments.json"].decode("utf-8-sig").splitlines()
        if line.strip()
    ]
    candidate = next(r for r in rows if r["Id"] == IMAGE)
    old_member = candidate["SourceId"] + "/.data/md-images/" + candidate["Location"]
    candidate.update(DataLength=len(image_bytes), Location=name, Name=name)
    new_member = candidate["SourceId"] + "/.data/md-images/" + name
    parts.pop(old_member)
    parts[new_member] = image_bytes
    parts["attachments.json"] = b"\n".join(json.dumps(r).encode() for r in rows)
    with ZipFile(source, "w") as archive:
        for filename, data in parts.items():
            archive.writestr(filename, data)
    digest = hashlib.sha256(image_bytes).hexdigest()
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == IMAGE)
    (vault / asset["relative_path"]).write_bytes(image_bytes)
    asset.update(
        actual_length=len(image_bytes),
        actual_sha256=digest,
        original_name=name,
        display_name=name,
    )
    for evidence in record["original_evidence"]:
        if evidence["key"] == "attachments.json":
            evidence["records"] = rows
        elif evidence["key"] == "payload:" + old_member:
            evidence["key"] = "payload:" + new_member
            evidence["records"] = {
                "member": new_member,
                "length": len(image_bytes),
                "sha256": digest,
            }
    observed = next(a for a in record["asset_targets"] if a["source_findings"])[
        "source_findings"
    ][0]
    fact = json.loads(observed["observed_json"])
    fact["images"][0].update(
        member=new_member,
        declared_length=len(image_bytes),
        actual_length=len(image_bytes),
        actual_sha256=digest,
    )
    observed["observed_json"] = json.dumps(fact)
    record["issues"][0]["message"] = (
        "Forged structurally valid receipt. Observed: " + observed["observed_json"]
    )
    record["source_identity"]["source_sha256"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    root_parts = [
        "["
        + ",".join(
            [data.decode("utf-8-sig")]
            if n == "meta.json"
            else [
                line for line in data.decode("utf-8-sig").splitlines() if line.strip()
            ]
        )
        + "]"
        for n in ROOTS
        for data in [parts[n]]
    ]
    record["source_identity"]["snapshot_digest"] = hashlib.sha256(
        (
            "".join(root_parts)
            + json.dumps(
                {"member": new_member, "length": len(image_bytes), "sha256": digest}
            )
        ).encode()
    ).hexdigest()
    rewrite_record(vault, record, result)


def png_chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data))
    )
