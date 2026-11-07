"""Inert #348 byte recipes and pre-encoding pixel facts, independent of decoders.

The literal 2x2 has separately written top-down RGBA and bottom-up BGRA bytes.
Larger artwork repeats those literal colors; no source data or product imports.
"""

import hashlib
import json
import struct
from pathlib import Path

from .api_scope_inputs import raster_scope_packet

LITERAL_RGBA = bytes.fromhex("f0 0a 14 ff 07 50 09 80 0b 16 21 00 01 02 c8 40")
LITERAL_BGRA = bytes.fromhex("21 16 0b 00 c8 02 01 40 14 0a f0 ff 09 50 07 80")
LITERAL_MASK = bytes.fromhex("80 7f a5 5a 40 3f c3 69")
LITERAL_BMP_RGBA = bytes.fromhex("f0 0a 14 ff 07 50 09 ff 0b 16 21 ff 01 02 c8 ff")
COLORS = ((240, 10, 20, 255), (7, 80, 9, 128), (11, 22, 33, 0), (1, 2, 200, 64))
DECLARATION = {
    "sourceType": 2,
    "type": 5,
    "isNotes": False,
    "name": None,
    "location": "Icon.png",
}
SPEC_SHA256 = "44a60d1144e3e6c7429719b87e56cfd6d44733bc863627d0d964a76108727056"
FIXTURES = Path(__file__).parents[1] / "fixtures/local_api_icons_v5"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pixels(width, height, phase=0, *, opaque=False):
    """Pre-encoding artwork: stripes of four explicitly declared color tuples."""
    return bytes(
        channel
        for y in range(height)
        for x in range(width)
        for channel in (
            (*COLORS[(2 * y + x + phase) % 4][:3], 255)
            if opaque
            else COLORS[(2 * y + x + phase) % 4]
        )
    )


def ico(
    sizes=(2,),
    *,
    physical=None,
    size_images=None,
    opaque=False,
    masks=True,
    retain_pixels=True,
):
    """Encode known artwork; return original bytes plus pre-decoder expectations."""
    sizes = tuple(sizes)
    assert 1 <= len(sizes) <= 16 and len(set(sizes)) == len(sizes)
    physical = tuple(range(len(sizes))) if physical is None else tuple(physical)
    assert sorted(physical) == list(range(len(sizes)))
    size_images = tuple(0 for _ in sizes) if size_images is None else tuple(size_images)
    assert len(size_images) == len(sizes)
    bodies, expected = {}, []
    for index, size in enumerate(sizes):
        rgba = pixels(size, size, index, opaque=opaque)
        # The 2x2 phase0 control is handwritten independently of this encoder.
        if size == 2 and index == 0 and not opaque:
            rgba, xor = LITERAL_RGBA, LITERAL_BGRA
        else:
            xor = bytearray()
            for row in range(size - 1, -1, -1):
                for col in range(size):
                    pos = (row * size + col) * 4
                    r, g, b, a = rgba[pos : pos + 4]
                    xor.extend((b, g, r, a))
            xor = bytes(xor)
        stride = ((size + 31) // 32) * 4
        mask = bytes((0xA5 if masks else 0,)) * (stride * size)
        if size == 2 and masks:
            mask = LITERAL_MASK
        image_size = size_images[index]
        assert image_size in (0, size * size * 4)
        body = (
            struct.pack(
                "<IiiHHIIiiII", 40, size, 2 * size, 1, 32, 0, image_size, 0, 0, 0, 0
            )
            + xor
            + mask
        )
        bodies[index] = body
        expected.append(
            {
                "index": index,
                "width": size,
                "height": size,
                "body_length": len(body),
                "body_sha256": digest(body),
                "rgba_sha256": digest(rgba),
                "rgba_length": len(rgba),
                "sizeImage": image_size,
                "dib_header": [40, size, 2 * size, 1, 32, 0, image_size, 0, 0, 0, 0],
                "mask_sha256": digest(mask),
            }
        )
        if retain_pixels:
            expected[-1]["rgba"] = rgba
    offset = 6 + 16 * len(sizes)
    for index in physical:
        expected[index]["offset"] = offset
        expected[index]["pixel_offset"] = offset + 40
        offset += len(bodies[index])
    directory = b"".join(
        struct.pack(
            "<BBBBHHII",
            size % 256,
            size % 256,
            0,
            0,
            1,
            32,
            len(bodies[index]),
            expected[index]["offset"],
        )
        for index, size in enumerate(sizes)
    )
    raw = (
        struct.pack("<HHH", 0, 1, len(sizes))
        + directory
        + b"".join(bodies[i] for i in physical)
    )
    return {"raw": raw, "sha256": digest(raw), "length": len(raw), "frames": expected}


def bmp(width=2, height=3, *, x="mixed", size_image=False, phase=0, retain_pixels=True):
    rgba = pixels(width, height, phase, opaque=True) if retain_pixels else None
    expected_digest = hashlib.sha256()
    for row in range(height):
        expected_digest.update(
            bytes(
                channel
                for col in range(width)
                for channel in (*COLORS[(2 * row + col + phase) % 4][:3], 255)
            )
        )
    storage = bytearray()
    for row in range(height - 1, -1, -1):
        for col in range(width):
            r, g, b, _ = (*COLORS[(2 * row + col + phase) % 4][:3], 255)
            unused = (
                0 if x == "zero" else 255 if x == "255" else (row * width + col) % 256
            )
            storage.extend((b, g, r, unused))
    header = struct.pack("<2sIHHI", b"BM", 54 + len(storage), 0, 0, 54)
    body = struct.pack(
        "<IiiHHIIiiII",
        40,
        width,
        height,
        1,
        32,
        0,
        len(storage) if size_image else 0,
        0,
        0,
        0,
        0,
    )
    raw = header + body + storage
    return {
        "raw": raw,
        "sha256": digest(raw),
        "length": len(raw),
        "frames": [
            {
                "index": 0,
                "offset": 14,
                "pixel_offset": 54,
                "width": width,
                "height": height,
                **({"rgba": rgba} if retain_pixels else {}),
                "rgba_sha256": expected_digest.hexdigest(),
                "rgba_length": width * height * 4,
                "body_sha256": digest(raw[14:]),
                "body_length": len(raw) - 14,
                "dib_header": [
                    40,
                    width,
                    height,
                    1,
                    32,
                    0,
                    len(storage) if size_image else 0,
                    0,
                    0,
                    0,
                    0,
                ],
            }
        ],
    }


def positive_cases():
    yield "literal-zero", ico()
    yield "literal-exact", ico(size_images=(16,))
    yield "mixed-physical", ico((2, 3, 4), physical=(2, 0, 1), size_images=(0, 36, 0))
    yield "five", ico((16, 24, 32, 48, 64), opaque=True, masks=False)
    yield "reverse", ico((48, 32, 16), size_images=(9216, 4096, 1024))
    yield "bmp-minimum", bmp(1, 1, x="zero")
    for x in ("zero", "255", "mixed"):
        yield "bmp-" + x, bmp(x=x, size_image=x == "255")


def legacy_zero_alpha_control():
    """Exact old32/16 layout, separately declared mask-only transparency.

    The old 0RGB interpretation uses the mask; new alpha-bearing bodies retain
    stored alpha instead. Microsoft's documented distinction is at
    https://devblogs.microsoft.com/oldnewthing/20101021-00/?p=12483/ .
    This is new inert artwork in the old predicate, not an edited old fixture.
    """
    fixture = ico((32, 16), opaque=True, masks=False)
    raw = bytearray(fixture["raw"])
    for frame in fixture["frames"]:
        width, begin = frame["width"], frame["offset"]
        for pos in range(begin + 43, begin + 40 + 4 * width * width, 4):
            raw[pos] = 0
        stride = ((width + 31) // 32) * 4
        mask_start = begin + 40 + 4 * width * width
        raw[mask_start + (width - 1) * stride] = 0x80
        # AND1/XOR0 is unambiguous transparency; avoid legacy screen inversion.
        top_left = begin + 40 + (width - 1) * width * 4
        raw[top_left : top_left + 3] = b"\0\0\0"
        expected = bytearray(frame["rgba"])
        expected[:3] = b"\0\0\0"
        expected[3] = 0  # Logical top-left only; all other mask bits are zero.
        frame["rgba"] = bytes(expected)
        frame["rgba_sha256"] = digest(expected)
        frame["mask_sha256"] = digest(raw[mask_start : begin + frame["body_length"]])
        frame["body_sha256"] = digest(raw[begin : begin + frame["body_length"]])
    fixture.update(raw=bytes(raw), sha256=digest(raw))
    return fixture


def support_base8(role):
    """Source-free accepted #292 stock8 input, never renderer/checker output.

    Re-state its fixed formula text to exercise current-format checker routing.
    This is not a new qualification of the existing native eight-link engine.
    """
    assert role in {"members", "gallery", "categories"}
    types = '["avif", "bmp", "gif", "jpeg", "jpg", "png", "svg", "webp"]'

    def image_test(value):
        return f'{value}.isType("link") && {value}.asFile() && {types}.contains({value}.asFile().ext.lower()) && {value}.asFile().size > 0'

    formulas = {
        "p0": "file",
        "r0": "if(" + image_test("icon") + ", icon, null)",
        "s0": 'if(formula.r0, "found", "continue")',
    }
    for depth in range(1, 10):
        prior = "formula.p" + str(depth - 1)
        selected = prior + ".properties.appearance_category"
        target = selected + ".asFile()"
        terms = [
            selected + '.isType("link")',
            target,
            target + '.ext == "md"',
            target + '.inFolder("Categories")',
            "!" + target + '.folder.split("/").contains("Templates")',
            "!" + target + '.folder.split("/").contains("Attachments")',
            "list(" + target + '.properties.tags).contains("categories")',
            "list(" + prior + ".properties.categories).contains(" + selected + ")",
        ]
        formulas["blank" + str(depth)] = (
            "if(" + prior + ", " + selected + ".isEmpty(), true)"
        )
        formulas["valid" + str(depth)] = (
            "if(" + prior + ", " + " && ".join(terms) + ", false)"
        )
        seen = ", ".join(
            "if(formula.p" + str(i) + ", formula.p" + str(i) + ".path, null)"
            for i in range(depth)
        )
        formulas["cycle" + str(depth)] = (
            "if(formula.valid"
            + str(depth)
            + ", ["
            + seen
            + "].contains("
            + target
            + ".path), false)"
        )
        guard = f'if(formula.blank{depth}, "none", if(!formula.valid{depth}, "invalid", if(formula.cycle{depth}, "cycle", '
        if depth == 9:
            formulas["result"] = (
                'if(formula.s8 != "continue", formula.s8, ' + guard + '"limit"))))'
            )
            break
        formulas["p" + str(depth)] = (
            f'if(formula.s{depth - 1} == "continue" && formula.valid{depth} && !formula.cycle{depth}, {target}, null)'
        )
        value = "formula.p" + str(depth) + ".properties.icon"
        formulas["r" + str(depth)] = (
            f"if(formula.p{depth} && {image_test(value)}, {value}, null)"
        )
        formulas["s" + str(depth)] = (
            f'if(formula.s{depth - 1} != "continue", formula.s{depth - 1}, '
            + guard
            + f'if(formula.r{depth}, "found", "continue")))))'
        )
    formulas["effective_icon"] = (
        "[" + ", ".join("formula.r" + str(i) for i in range(9)) + "].filter(value)[0]"
    )
    formulas["picture"] = (
        "if(formula.effective_icon, image(formula.effective_icon.asFile()), null)"
    )
    formulas["provider_status"] = (
        'if(formula.result == "limit", "Icon lookup exceeds 8 links.", if(formula.result == "cycle", "Icon provider cycle.", if(formula.result == "invalid", "Invalid appearance category.", if(formula.result == "none", "No inherited icon.", "Icon found."))))'
    )
    filters = 'filters:\n  and:\n    - file.ext == "md"\n'
    if role == "categories":
        filters += '    - file.inFolder("Categories")\n    - \'!file.folder.split("/").contains("Templates")\'\n    - \'!file.folder.split("/").contains("Attachments")\'\n    - list(tags).contains("categories")\n'
    else:
        filters += "    - '!file.inFolder(\"Templates\")'\n    - '!file.inFolder(\"Attachments\")'\n    - list(categories).contains(this)\n"
    text = (
        filters
        + "formulas:\n"
        + "".join(
            "  " + key + ": " + json.dumps(value) + "\n"
            for key, value in formulas.items()
        )
    )
    label = "Category" if role == "categories" else "Note"
    text += f"properties:\n  formula.picture:\n    displayName: Icon\n  file.name:\n    displayName: {label}\n  formula.provider_status:\n    displayName: Inheritance\n"
    if role == "gallery":
        text += "views:\n  - type: cards\n    name: Gallery\n    image: formula.effective_icon\n    imageFit: contain\n    imageAspectRatio: 0.4\n    cardSize: 230\n    order:\n      - file.name\n      - formula.provider_status\n"
    else:
        text += (
            "views:\n  - type: table\n    name: "
            + ("Categories" if role == "categories" else "Members")
            + "\n    columnSize:\n      formula.provider_status: 240\n    order:\n      - formula.picture\n      - file.name\n      - formula.provider_status\n"
        )
        if role != "categories":
            text += (
                "      - note.categories\n      - note.created\n      - note.updated\n"
            )
    return text + "    sort:\n      - property: file.name\n        direction: ASC\n"


def patch(raw, offset, fmt, value):
    changed = bytearray(raw)
    struct.pack_into(fmt, changed, offset, value)
    return bytes(changed)


def ico_mutations():
    """One failure per structural distinction; target nonpreferred frame as well."""
    fixture = ico((2, 3), physical=(1, 0), size_images=(0, 36))
    raw = fixture["raw"]
    start = fixture["frames"][0]["offset"]
    for name, offset, fmt, value in (
        ("reserved", 0, "<H", 1),
        ("type", 2, "<H", 2),
        ("count-zero", 4, "<H", 0),
        ("count17", 4, "<H", 17),
        ("color-count", 8, "<B", 1),
        ("entry-reserved", 9, "<B", 1),
        ("entry-planes", 10, "<H", 2),
        ("entry-bits", 12, "<H", 24),
        ("entry-height", 7, "<B", 3),
        ("zero-length", 14, "<I", 0),
        ("inside-directory", 18, "<I", 6),
        ("alias", 18, "<I", 38),
        ("wrap-offset", 18, "<I", 0xFFFFFFF0),
        ("header-size", start, "<I", 108),
        ("dib-width", start + 4, "<i", 3),
        ("width-negative", start + 4, "<i", -2),
        ("height-zero", start + 8, "<i", 0),
        ("height-negative", start + 8, "<i", -4),
        ("height-odd", start + 8, "<i", 3),
        ("height-oversize", start + 8, "<i", 514),
        ("planes", start + 12, "<H", 2),
        ("bits", start + 14, "<H", 24),
        ("compression", start + 16, "<I", 3),
        ("sizeimage-and", start + 20, "<I", 24),
        ("sizeimage-frame", start + 20, "<I", 64),
        ("sizeimage-double", start + 20, "<I", 32),
        ("sizeimage-arbitrary", start + 20, "<I", 17),
        ("x-density", start + 24, "<i", 1),
        ("y-density", start + 28, "<i", 1),
        ("colors", start + 32, "<I", 1),
        ("important", start + 36, "<I", 1),
    ):
        yield name, patch(raw, offset, fmt, value)
    body = ico()["raw"][22:]
    yield (
        "coherent-duplicate-size",
        (
            struct.pack("<HHH", 0, 1, 2)
            + struct.pack("<BBBBHHII", 2, 2, 0, 0, 1, 32, 64, 38)
            + struct.pack("<BBBBHHII", 2, 2, 0, 0, 1, 32, 64, 102)
            + body
            + body
        ),
    )
    gap = raw[:38] + b"\0" + raw[38:]
    gap = patch(patch(gap, 18, "<I", start + 1), 34, "<I", 39)
    yield "coherent-gap", gap
    overlap = raw[:38] + raw[38 : start - 1] + raw[start:]
    yield "coherent-overlap", patch(overlap, 18, "<I", start - 1)
    yield "truncated-directory", raw[:30]
    yield "truncated-xor", raw[: start + 48]
    yield "truncated-mask", raw[:-1]
    yield "missing-mask", raw[:-8]
    yield "trailer", raw + b"\0"
    yield "png-body", raw[:start] + b"\x89PNG\r\n\x1a\n" + raw[start + 8 :]
    zero = bytearray(raw)
    zero[start + 43 : start + 56 : 4] = bytes(4)
    yield "all-zero-alpha-nonpreferred", bytes(zero)


def bmp_mutations():
    raw = bmp()["raw"]
    for name, offset, fmt, value in (
        ("signature", 0, "<H", 0),
        ("size", 2, "<I", len(raw) + 1),
        ("reserved1", 6, "<H", 1),
        ("reserved2", 8, "<H", 1),
        ("offset", 10, "<I", 55),
        ("header-v4", 14, "<I", 108),
        ("header-v5", 14, "<I", 124),
        ("width-zero", 18, "<i", 0),
        ("width-negative", 18, "<i", -2),
        ("width1025", 18, "<i", 1025),
        ("height-zero", 22, "<i", 0),
        ("top-down", 22, "<i", -3),
        ("height1025", 22, "<i", 1025),
        ("planes", 26, "<H", 2),
        ("24bpp", 28, "<H", 24),
        ("palette", 28, "<H", 8),
        ("rle", 30, "<I", 1),
        ("bitfields", 30, "<I", 3),
        ("sizeimage", 34, "<I", 23),
        ("x-density", 38, "<i", 1),
        ("y-density", 42, "<i", 1),
        ("colors", 46, "<I", 1),
        ("important", 50, "<I", 1),
    ):
        yield name, patch(raw, offset, fmt, value)
    yield "truncate", raw[:-1]
    yield "trailer", patch(raw + b"\0", 2, "<I", len(raw) + 1)
    yield "pixel-gap", patch(raw[:54] + b"\0" + raw[54:], 2, "<I", len(raw) + 1)


def public_facts(fixture):
    """Persist expectations authored before parsing/decoding, without raw dumps."""
    return {
        k: (
            [{a: b for a, b in f.items() if a != "rgba"} for f in v]
            if k == "frames"
            else v
        )
        for k, v in fixture.items()
        if k != "raw"
    }


def json_bytes(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()


def icon_source_packet(raw=None, *, excluded=True):
    """A source-only packet: reuse inert non-icon facts, add explicit own icon."""
    packet = raster_scope_packet(excluded=excluded, profile_version="3")
    raw = bmp()["raw"] if raw is None else raw
    data, files = packet["baseline_inputs"], packet["files"]
    home = "00000000-0000-4000-8000-000000000002"
    key = "00000000-0000-4000-8000-000000000206"
    brain = "00000000-0000-4000-8000-000000000001"
    row = dict(
        DECLARATION,
        id=key,
        brainId=brain,
        sourceId=home,
        position=2,
        dataLength=len(raw),
    )
    for path in (data["graphs"][home], data["attachment_inventories"][home]):
        value = json.loads(files[path])
        (value["attachments"] if isinstance(value, dict) else value).append(row)
        files[path] = json_bytes(value)
    metadata, payload = "responses/icon-metadata.json", "payloads/icon.bin"
    files[metadata], files[payload] = json_bytes(row), raw
    data["attachment_metadata"][key] = {"status": 200, "path": metadata}
    data["payloads"][key] = {"status": 200, "path": payload}
    data["scope"]["attachment_ids"].append(key)
    ledger_path = data["source_packet_ledger"]
    ledger = json.loads(files[ledger_path])
    ledger["configuration"]["profile_version"] = "5"
    ledger["routes"].extend(
        [
            {
                "method": "GET",
                "route": f"/api/attachments/{brain}/{key}/metadata",
                "status": 200,
                "body_path": metadata,
                "optional": False,
            },
            {
                "method": "GET",
                "route": f"/api/attachments/{brain}/{key}/file-content",
                "status": 200,
                "body_path": payload,
                "optional": False,
            },
        ]
    )
    files[ledger_path] = json_bytes(ledger)
    return packet


def capture_json(value):
    """Independent CJSON1 spelling from the frozen capture-vector contract."""
    if isinstance(value, str):
        return (
            '"'
            + "".join(
                '\\"'
                if char == '"'
                else "\\\\"
                if char == "\\"
                else f"\\u{ord(char):04x}"
                if ord(char) < 32
                else char
                for char in value
            )
            + '"'
        ).encode("utf8")
    if isinstance(value, dict):
        return (
            b"{"
            + b",".join(
                capture_json(key) + b":" + capture_json(value[key])
                for key in sorted(value, key=lambda x: x.encode("utf8"))
            )
            + b"}"
        )
    if isinstance(value, list):
        return b"[" + b",".join(capture_json(item) for item in value) + b"]"
    assert value is None or type(value) in (int, bool), "CJSON1 literal scalar"
    return json.dumps(value).encode("ascii")


def capture_digest(domain, value):
    return digest(
        ("brz2obsidian.local-api." + domain + ".v1\n").encode("ascii")
        + capture_json(value)
    )


def profile5_capture_vector():
    """Worked synthetic profile5 vector, never a production capture or live seal.

    Existing inert profile3 bytes supply the frozen canonical contract example.
    Add one independent literal icon and its explicit joins, then calculate every
    retained byte/hash with stdlib. The qualifier reproduces this construction.
    """
    root = Path(__file__).parents[1] / "fixtures/local_api_capture"
    seed_raw = (root / "profile3-capture-vector.json").read_bytes()
    seed = json.loads(seed_raw)
    files = {
        row["storage_key"]: (
            bytes.fromhex(row["hex"]) if "hex" in row else row["utf8"].encode()
        )
        for row in seed["retained_files"]
    }
    source, snapshot, metadata = (
        json.loads(files[key])
        for key in ("source.json", "snapshot.json", "metadata.json")
    )
    assert capture_digest("source", source) == seed["expected_source_sha256"], (
        "independent seed source equation"
    )
    projected = dict(
        snapshot,
        identity={
            k: v for k, v in snapshot["identity"].items() if k != "snapshot_digest"
        },
    )
    assert capture_digest("snapshot", projected) == seed["expected_snapshot_digest"], (
        "independent seed snapshot equation"
    )
    old_manifest = json.loads(files["manifest.json"])
    assert (
        capture_digest(
            "integrity",
            {k: v for k, v in old_manifest.items() if k != "integrity_sha256"},
        )
        == seed["expected_integrity_sha256"]
    ), "independent seed integrity equation"
    home = "00000000-0000-4000-8000-000000000002"
    key = "00000000-0000-4000-8000-000000000005"
    pointer = "attachment:" + key
    artwork = ico()["raw"]
    declaration = dict(
        DECLARATION,
        id=key,
        brainId=source["brain"]["id"],
        sourceId=home,
        position={"decimal": "2"},
        dataLength=len(artwork),
    )
    source["identifiers"]["profile_version"] = "5"
    source["records"].append(
        {"domain": "attachment", "key": pointer, "owner_id": home, "value": declaration}
    )
    graph = next(row for row in source["records"] if row["domain"] == "graph")
    graph["value"]["attachment_ids"].append(key)
    source["records"].sort(key=lambda row: row["key"])
    source["payloads"].append(
        {
            "asset_id": key,
            "owner_id": home,
            "availability": "present",
            "actual_length": len(artwork),
            "actual_sha256": digest(artwork),
            "external_uri": None,
        }
    )
    source["payloads"].sort(key=lambda row: row["asset_id"])
    snapshot["assets"].append(
        {
            "asset_id": key,
            "owner": home,
            "naming_seed": key.replace("-", ""),
            "original_name": "Icon.png",
            "display_name": None,
            "role": "icon",
            "availability": "present",
            "actual_length": len(artwork),
            "actual_sha256": digest(artwork),
            "external_uri": None,
            "video_presentation": None,
            "evidence": [pointer],
        }
    )
    snapshot["assets"].sort(key=lambda row: row["asset_id"])
    snapshot["items"][0]["declared_appearance"]["icon_asset_id"] = key
    snapshot["accounting"]["entries"].append(
        {"identity": pointer, "disposition": "normalized", "references": [key]}
    )
    snapshot["accounting"]["entries"].sort(key=lambda row: row["identity"])
    next(row for row in snapshot["original_evidence"] if row["key"] == graph["key"])[
        "original_json"
    ] = capture_json(graph["value"]).decode()
    snapshot["original_evidence"].append(
        {
            "key": pointer,
            "kind": "records",
            "original_json": capture_json(declaration).decode(),
        }
    )
    snapshot["original_evidence"].sort(key=lambda row: row["key"])
    source_hash = capture_digest("source", source)
    snapshot["identity"]["source_sha256"] = source_hash
    del snapshot["identity"]["snapshot_digest"]
    snapshot_hash = capture_digest("snapshot", snapshot)
    snapshot["identity"]["snapshot_digest"] = snapshot_hash
    metadata["identifiers"]["profile_version"] = "5"
    metadata["identity"] = snapshot["identity"]
    # These inherited4 literals label a synthetic worked vector; they are not a
    # current-source observation or a new profile5 qualification fingerprint.
    metadata["schema_sha256"] = (
        "02fd25ff4f6a393f85aa0eab1597fb728f9a752a517497229715d834f5b49c5f"
    )
    metadata["desktop_build"] = "15.0.647.0"
    files.update(
        {
            "source.json": capture_json(source),
            "snapshot.json": capture_json(snapshot),
            "metadata.json": capture_json(metadata),
            "payload/0000000000000002.bin": artwork,
        }
    )
    del files["manifest.json"]
    manifest = {
        "format_id": "thebrain-local-api-capture",
        "format_version": "1",
        "source_sha256": source_hash,
        "snapshot_digest": snapshot_hash,
        "files": [
            {
                "role": "payload" if path.startswith("payload/") else path[:-5],
                "storage_key": path,
                "actual_length": len(raw),
                "actual_sha256": digest(raw),
            }
            for path, raw in sorted(files.items())
        ],
        "payload_bindings": [
            *old_manifest["payload_bindings"],
            {
                "asset_id": key,
                "owner_id": home,
                "storage_key": "payload/0000000000000002.bin",
            },
        ],
    }
    integrity = capture_digest("integrity", manifest)
    manifest["integrity_sha256"] = integrity
    files["manifest.json"] = capture_json(manifest)
    return {
        "id": "PROFILE5-ICON-CAP01",
        "schema": "independent.synthetic-capture-vector/1",
        "synthetic": True,
        "seed_sha256": digest(seed_raw),
        "spec_sha256": SPEC_SHA256,
        "qualification_metadata": "Inherited4 synthetic literals; no live source/schema/build or production seal is claimed.",
        "expected_source_sha256": source_hash,
        "expected_snapshot_digest": snapshot_hash,
        "expected_integrity_sha256": integrity,
        "retained_files": [
            {
                "storage_key": path,
                "hex": raw.hex(),
                "actual_length": len(raw),
                "actual_sha256": digest(raw),
            }
            for path, raw in sorted(files.items())
        ],
    }
