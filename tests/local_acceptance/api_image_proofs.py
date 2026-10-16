"""API-local finite ICO proof from source bytes; no production imports.

Native WIC invocation follows the separately qualified source-input measurement;
finite structure and byte bindings are independently enforced before decoding.
"""

import ctypes as c
import hashlib
import os
import struct

from .images import GUID, AuditUnavailable, guid


def ico_proof(raw):
    assert len(raw) >= 6, "ICO directory header"
    reserved, kind, count = struct.unpack_from("<HHH", raw)
    assert (reserved, kind) == (0, 1) and count in {2, 3}, "finite ICO directory"
    dimensions, tails = (
        ([32, 16], [0, 0]) if count == 2 else ([16, 32, 48], [0, 128, 192])
    )
    cursor = 6 + 16 * count
    assert len(raw) >= cursor, "complete ICO directory"
    frames = []
    for index, (size, tail) in enumerate(zip(dimensions, tails, strict=True)):
        entry = raw[6 + 16 * index : 22 + 16 * index]
        width, height, colours, spare, planes, bits, length, offset = struct.unpack(
            "<BBBBHHII", entry
        )
        assert (width, height, colours, spare, planes, bits) == (
            size,
            size,
            0,
            0,
            1,
            32,
        ), "finite ICO entry"
        mask_length = 4 * ((width + 31) // 32) * height
        exact = 40 + 4 * width * height + mask_length + tail
        assert length == exact and offset == cursor and offset + length <= len(raw), (
            "exact ICO body extent/order"
        )
        body = raw[offset : offset + length]
        assert struct.unpack_from("<IiiHHIIiiII", body) == (
            40,
            width,
            2 * height,
            1,
            32,
            0,
            0,
            0,
            0,
            0,
            0,
        ), "finite ICO DIB fields"
        mask_start = 40 + 4 * width * height
        mask = body[mask_start : mask_start + mask_length]
        extra = body[mask_start + mask_length :]
        assert len(extra) == tail and not any(extra), "exact ICO zero tail"
        if count == 3 and width in {32, 48}:
            assert not any(mask), "finite ICO zero mask"
        wrapper = (
            struct.pack("<HHH", 0, 1, 1)
            + struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32, length, 22)
            + body
        )
        proof = decode_ico_variant(wrapper)
        assert proof["format"] == "ICO", "ICO variant decoded classification"
        assert (proof["width"], proof["height"]) == (width, height), (
            "ICO variant decoded dimensions"
        )
        assert proof["decoded_bytes"] == width * height * 4, (
            "ICO complete variant pixels"
        )
        proof.update(
            body_sha256=hashlib.sha256(body).hexdigest(),
            body_length=length,
            offset=offset,
            mask_length=mask_length,
            extra_zero_tail_length=tail,
        )
        frames.append(proof)
        cursor += length
    assert cursor == len(raw), "ICO complete-container trailer"
    return {
        "format": "ICO",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "status": "complete-all-variant-pixel-decode",
        "frames": frames,
    }


def decode_ico_variant(data):
    """Read full BGRA8 through native WIC, retaining no source/output handles."""
    if os.name != "nt":
        raise AuditUnavailable("Windows WIC ICO decoder unavailable")
    HR, U, P = c.c_long, c.c_uint32, c.c_void_p

    def call(obj, index, types, *args):
        table = c.cast(obj, c.POINTER(c.POINTER(P))).contents
        status = c.WINFUNCTYPE(HR, P, *types)(table[index])(obj, *args)
        if status < 0:
            code = status & 0xFFFFFFFF
            if code in {0x8007000E, 0x80004001, 0x88982F50, 0x88982F80, 0x80040154}:
                raise AuditUnavailable(f"WIC ICO capability unavailable: {code:#x}")
            raise AssertionError(f"invalid complete ICO decode: {index}, {code:#x}")

    def release(obj):
        if obj.value:
            table = c.cast(obj, c.POINTER(c.POINTER(P))).contents
            c.WINFUNCTYPE(U, P)(table[2])(obj)

    ole, sh = c.WinDLL("ole32"), c.WinDLL("shlwapi")
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
    assert ole.CoInitializeEx(None, 0) >= 0
    objects = []
    try:
        factory = P()
        clsid = guid("cacaf262-9370-4615-a13b-9f5539da4c0a")
        iid = guid("ec5ec8a9-c395-4314-9c77-54d7a935ff70")
        assert (
            ole.CoCreateInstance(
                c.byref(clsid), None, 1, c.byref(iid), c.byref(factory)
            )
            >= 0
        )
        objects.append(factory)
        sh.SHCreateMemStream.argtypes = [c.POINTER(c.c_ubyte), U]
        sh.SHCreateMemStream.restype = P
        source = (c.c_ubyte * len(data)).from_buffer_copy(data)
        stream = P(sh.SHCreateMemStream(source, len(data)))
        assert stream.value
        objects.append(stream)
        decoder, info = P(), P()
        call(factory, 4, [P, P, U, c.POINTER(P)], stream, None, 0, c.byref(decoder))
        objects.append(decoder)
        call(decoder, 6, [c.POINTER(P)], c.byref(info))
        objects.append(info)
        container = GUID()
        call(decoder, 5, [c.POINTER(GUID)], c.byref(container))
        assert bytes(container.data) == bytes(
            guid("a3a860c4-338f-4c17-919a-fba4b5628f21").data
        ), "ICO native container classification"
        count = U()
        call(decoder, 12, [c.POINTER(U)], c.byref(count))
        assert count.value == 1
        length = U()
        call(info, 10, [U, c.c_wchar_p, c.POINTER(U)], 0, None, c.byref(length))
        name = c.create_unicode_buffer(length.value)
        call(
            info,
            10,
            [U, c.c_wchar_p, c.POINTER(U)],
            length.value,
            name,
            c.byref(length),
        )
        frame, converter = P(), P()
        try:
            call(decoder, 13, [U, c.POINTER(P)], 0, c.byref(frame))
            width, height = U(), U()
            call(
                frame, 3, [c.POINTER(U), c.POINTER(U)], c.byref(width), c.byref(height)
            )
            assert width.value and height.value, "positive ICO dimensions"
            if width.value * height.value * 4 > 256 * 1024 * 1024:
                raise AuditUnavailable("ICO pixel resource bound")
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
            pixels = (c.c_ubyte * (width.value * height.value * 4))()
            call(
                converter,
                7,
                [P, U, U, c.POINTER(c.c_ubyte)],
                None,
                width.value * 4,
                len(pixels),
                pixels,
            )
            rgba = bytes(
                channel
                for index in range(0, len(pixels), 4)
                for channel in (
                    pixels[index + 2],
                    pixels[index + 1],
                    pixels[index],
                    pixels[index + 3],
                )
            )
            assert "ico" in name.value.casefold(), "ICO native decoder classification"
            return {
                "format": "ICO",
                "codec": name.value,
                "width": width.value,
                "height": height.value,
                "decoded_bytes": len(rgba),
                "rgba_sha256": hashlib.sha256(rgba).hexdigest(),
            }
        finally:
            release(converter)
            release(frame)
    finally:
        for obj in reversed(objects):
            release(obj)
        ole.CoUninitialize()


def jpeg_headers(raw):
    """Reject only certain absent JPEG prerequisites before native decoding.

    WIC still establishes actual dimensions and complete pixels. This scan does
    not constrain marker order, scan count or progressive coding choices.
    """
    assert raw.startswith(b"\xff\xd8\xff"), "JPEG original signature"
    assert raw.rfind(b"\xff\xd9") >= 3, "JPEG complete original end marker"
    frame_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    assert (
        any(bytes((255, marker)) in raw for marker in frame_markers)
        and b"\xff\xda" in raw
    ), "JPEG required image/scan segments"
