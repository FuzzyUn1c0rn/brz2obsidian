"""Independent strict PNG checks and full existing Windows WIC pixel decoding.

Only stdlib Python imports. WIC and its installed codecs are native dependencies;
missing capabilities and resource bounds are unverified audits, never invalid
images or successful header-only fallbacks.
"""

import ctypes as c
import hashlib
import os
import struct
import uuid
import zlib
from pathlib import PurePosixPath


class AuditUnavailable(RuntimeError):
    """A required complete decoder capability could not be established."""


def png_content(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "invalid PNG signature"
    chunks, offset = [], 8
    while offset < len(data):
        assert offset + 12 <= len(data), "invalid PNG chunk bounds"
        size = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + size]
        assert size <= len(data) - offset - 12, "invalid PNG chunk length"
        assert (
            zlib.crc32(kind + payload)
            == struct.unpack_from(">I", data, offset + 8 + size)[0]
        ), "invalid PNG chunk CRC"
        assert all(65 <= b <= 90 or 97 <= b <= 122 for b in kind), (
            "invalid PNG chunk type"
        )
        assert kind in {b"IHDR", b"PLTE", b"IDAT", b"IEND"} or kind[0] & 32, (
            "unknown critical PNG chunk"
        )
        chunks.append((kind, payload))
        offset += size + 12
    kinds = [k for k, _ in chunks]
    assert chunks, "invalid PNG missing chunks"
    assert (
        kinds[0] == b"IHDR"
        and kinds.count(b"IHDR") == 1
        and kinds[-1] == b"IEND"
        and kinds.count(b"IEND") == 1
    ), "invalid PNG chunk order"
    assert len(chunks[0][1]) == 13 and not chunks[-1][1], "invalid PNG header/end"
    width, height, depth, color, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", chunks[0][1]
    )
    allowed = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
    assert (
        width
        and height
        and depth in allowed.get(color, ())
        and compression == filtering == 0
        and interlace in {0, 1}
    ), "invalid PNG dimensions/mode"
    if b"acTL" in kinds or b"fdAT" in kinds:
        raise AuditUnavailable("APNG strict frame-stream audit is unavailable")
    assert kinds.count(b"PLTE") <= 1 and b"IDAT" in kinds, "invalid PNG palette/data"
    first, last = kinds.index(b"IDAT"), len(kinds) - 1 - kinds[::-1].index(b"IDAT")
    assert all(k == b"IDAT" for k in kinds[first : last + 1]), (
        "invalid PNG noncontiguous data"
    )
    palette = next((p for k, p in chunks if k == b"PLTE"), None)
    if palette is not None:
        assert (
            0 < len(palette) <= 768
            and len(palette) % 3 == 0
            and kinds.index(b"PLTE") < first
            and color not in {0, 4}
        ), "invalid PNG palette"
    assert color != 3 or palette is not None and len(palette) // 3 <= 2**depth, (
        "invalid indexed PNG palette"
    )
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    bits = depth * channels
    passes = (
        [(0, 0, 1, 1)]
        if not interlace
        else [
            (0, 0, 8, 8),
            (4, 0, 8, 8),
            (0, 4, 4, 8),
            (2, 0, 4, 4),
            (0, 2, 2, 4),
            (1, 0, 2, 2),
            (0, 1, 1, 2),
        ]
    )
    sizes = [
        (max(0, (width - x + dx - 1) // dx), max(0, (height - y + dy - 1) // dy))
        for x, y, dx, dy in passes
    ]
    expected = sum(((w * bits + 7) // 8 + 1) * h for w, h in sizes if w and h)
    if expected > 256 * 1024 * 1024:
        raise AuditUnavailable(
            "PNG scanline resource bound; content remains unverified"
        )
    stream = zlib.decompressobj()
    try:
        decoded = stream.decompress(
            b"".join(p for k, p in chunks if k == b"IDAT"), expected + 1
        )
    except zlib.error as exc:
        raise AssertionError("invalid PNG compressed stream") from exc
    except MemoryError as exc:
        raise AuditUnavailable("PNG scanline memory unavailable") from exc
    assert (
        stream.eof
        and not stream.unused_data
        and not stream.unconsumed_tail
        and len(decoded) == expected
    ), "invalid PNG complete scanlines"
    offset = 0
    bpp = max(1, (bits + 7) // 8)
    for w, h in sizes:
        if not w or not h:
            continue
        rowbytes = (w * bits + 7) // 8
        previous = bytearray(rowbytes)
        for _ in range(h):
            mode = decoded[offset]
            row = bytearray(decoded[offset + 1 : offset + 1 + rowbytes])
            offset += rowbytes + 1
            assert mode <= 4, "invalid PNG scanline filter"
            for i, value in enumerate(row):
                left = row[i - bpp] if i >= bpp else 0
                above = previous[i]
                corner = previous[i - bpp] if i >= bpp else 0
                p = left + above - corner
                distances = (abs(p - left), abs(p - above), abs(p - corner))
                predictor = (left, above, corner)[distances.index(min(distances))]
                row[i] = (
                    value + (0, left, above, (left + above) // 2, predictor)[mode]
                ) & 255
            if color == 3:
                for i in range(w):
                    sample = (row[i * depth // 8] >> (8 - depth - (i * depth % 8))) & (
                        (1 << depth) - 1
                    )
                    assert sample < len(palette) // 3, "invalid PNG palette index"
            previous = row
    return width, height


class GUID(c.Structure):
    _fields_ = [("data", c.c_ubyte * 16)]


def guid(value):
    return GUID((c.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))


def decode_image(data, name):
    """Return source-hash-bound proof only after every accepted frame has pixels."""
    formats = {
        ".png": "PNG",
        ".webp": "WEBP",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".gif": "GIF",
        ".bmp": "BMP",
        ".avif": "AVIF",
    }
    fmt = formats.get(PurePosixPath(name).suffix.casefold())
    assert fmt, "unsupported raw fallback image extension"
    signatures = {
        "PNG": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "WEBP": data[:4] == b"RIFF" and data[8:12] == b"WEBP",
        "JPEG": data[:3] == b"\xff\xd8\xff",
        "GIF": data[:6] in {b"GIF87a", b"GIF89a"},
        "BMP": data[:2] == b"BM",
        "AVIF": data[4:8] == b"ftyp" and data[8:12] in {b"avif", b"avis"},
    }
    assert signatures[fmt], "invalid raw fallback image format"
    try:
        strict_dimensions = png_content(data) if fmt == "PNG" else None
    except MemoryError as exc:
        raise AuditUnavailable("PNG content memory unavailable") from exc
    if fmt == "WEBP":
        assert len(data) >= 20 and struct.unpack_from("<I", data, 4)[0] + 8 == len(
            data
        ), "invalid WebP container length"
        offset = 12
        while offset < len(data):
            assert offset + 8 <= len(data), "invalid WebP chunk bounds"
            size = struct.unpack_from("<I", data, offset + 4)[0]
            offset += 8 + size + (size & 1)
            assert offset <= len(data), "invalid WebP chunk length"
        assert offset == len(data), "invalid WebP container bounds"
    if os.name != "nt":
        raise AuditUnavailable(
            "Windows WIC complete pixel decoder unavailable on this host"
        )
    HR, U, P = c.c_long, c.c_uint32, c.c_void_p
    pointers = []

    def call(obj, index, types, *args):
        table = c.cast(obj, c.POINTER(c.POINTER(P))).contents
        status = c.WINFUNCTYPE(HR, P, *types)(table[index])(obj, *args)
        if status < 0:
            code = status & 0xFFFFFFFF
            if code == 0x8007000E:
                raise AuditUnavailable(f"WIC memory unavailable: HRESULT {code:#x}")
            if code == 0x80004001:
                raise AuditUnavailable(f"WIC operation unavailable: HRESULT {code:#x}")
            if code in {0x88982F50, 0x88982F80, 0x80040154}:
                raise AuditUnavailable(
                    f"required WIC codec unavailable: HRESULT {code:#x}"
                )
            raise AssertionError(
                f"invalid full {fmt} pixel decode: method {index}, HRESULT {code:#x}"
            )

    def release(obj):
        if obj.value:
            table = c.cast(obj, c.POINTER(c.POINTER(P))).contents
            c.WINFUNCTYPE(U, P)(table[2])(obj)

    try:
        ole = c.WinDLL("ole32")
        sh = c.WinDLL("shlwapi")
    except OSError as exc:
        raise AuditUnavailable("required native WIC libraries unavailable") from exc
    ole.CoInitializeEx.argtypes, ole.CoInitializeEx.restype = [P, U], HR
    ole.CoCreateInstance.argtypes = [
        c.POINTER(GUID),
        P,
        U,
        c.POINTER(GUID),
        c.POINTER(P),
    ]
    ole.CoCreateInstance.restype = HR
    ole.CoUninitialize.argtypes, ole.CoUninitialize.restype = [], None
    status = ole.CoInitializeEx(None, 0)
    if status < 0:
        raise AuditUnavailable(
            f"WIC COM apartment unavailable: HRESULT {status & 0xFFFFFFFF:#x}"
        )
    try:
        factory = P()
        clsid, iid = (
            guid("cacaf262-9370-4615-a13b-9f5539da4c0a"),
            guid("ec5ec8a9-c395-4314-9c77-54d7a935ff70"),
        )
        status = ole.CoCreateInstance(
            c.byref(clsid), None, 1, c.byref(iid), c.byref(factory)
        )
        if status < 0:
            raise AuditUnavailable("WIC factory unavailable")
        pointers.append(factory)
        sh.SHCreateMemStream.argtypes, sh.SHCreateMemStream.restype = (
            [c.POINTER(c.c_ubyte), U],
            P,
        )
        buf = (c.c_ubyte * len(data)).from_buffer_copy(data)
        stream = P(sh.SHCreateMemStream(buf, len(data)))
        if not stream.value:
            raise AuditUnavailable("WIC memory stream unavailable")
        pointers.append(stream)
        decoder, info = P(), P()
        call(factory, 4, [P, P, U, c.POINTER(P)], stream, None, 0, c.byref(decoder))
        pointers.append(decoder)
        call(decoder, 6, [c.POINTER(P)], c.byref(info))
        pointers.append(info)
        codec_id = GUID()
        call(info, 4, [c.POINTER(GUID)], c.byref(codec_id))

        def string_info(index):
            size = U()
            call(info, index, [U, c.c_wchar_p, c.POINTER(U)], 0, None, c.byref(size))
            text = c.create_unicode_buffer(size.value)
            call(
                info,
                index,
                [U, c.c_wchar_p, c.POINTER(U)],
                size.value,
                text,
                c.byref(size),
            )
            return text.value

        codec = {
            "clsid": str(uuid.UUID(bytes_le=bytes(codec_id.data))),
            "name": string_info(10),
            "version": string_info(8),
        }
        count = U()
        call(decoder, 12, [c.POINTER(U)], c.byref(count))
        assert count.value > 0, "invalid empty decoded image frames"
        if count.value > 100:
            raise AuditUnavailable(
                "WIC frame resource bound; content remains unverified"
            )
        frames = []
        for index in range(count.value):
            frame, converter = P(), P()
            try:
                call(decoder, 13, [U, c.POINTER(P)], index, c.byref(frame))
                width, height = U(), U()
                call(
                    frame,
                    3,
                    [c.POINTER(U), c.POINTER(U)],
                    c.byref(width),
                    c.byref(height),
                )
                nbytes = width.value * height.value * 4
                assert width.value and height.value, "invalid zero image dimensions"
                if nbytes > 256 * 1024 * 1024:
                    raise AuditUnavailable(
                        "WIC pixel resource bound; content remains unverified"
                    )
                call(factory, 10, [c.POINTER(P)], c.byref(converter))
                bgra = guid("6fddc324-4e03-4bfe-b185-3d77768dc90f")
                call(
                    converter,
                    8,
                    [P, c.POINTER(GUID), U, P, c.c_double, U],
                    frame,
                    c.byref(bgra),
                    0,
                    None,
                    0.0,
                    0,
                )
                pixels = (c.c_ubyte * nbytes)()
                call(
                    converter,
                    7,
                    [P, U, U, c.POINTER(c.c_ubyte)],
                    None,
                    width.value * 4,
                    nbytes,
                    pixels,
                )
                frames.append(
                    {
                        "width": width.value,
                        "height": height.value,
                        "decoded_bytes": nbytes,
                        "pixel_sha256": hashlib.sha256(pixels).hexdigest(),
                    }
                )
            finally:
                release(converter)
                release(frame)
        assert strict_dimensions is None or strict_dimensions == (
            frames[0]["width"],
            frames[0]["height"],
        ), "PNG independent/native dimensions"
        return {
            "status": "complete-pixel-decode",
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "format": fmt,
            "width": frames[0]["width"],
            "height": frames[0]["height"],
            "codec": codec,
            "frames": frames,
        }
    except MemoryError as exc:
        raise AuditUnavailable("WIC decode memory unavailable") from exc
    finally:
        for pointer in reversed(pointers):
            release(pointer)
        ole.CoUninitialize()
