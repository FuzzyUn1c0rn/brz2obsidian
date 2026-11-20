"""API-local JPEG/finite ICO proof from source bytes; no production imports.

Native WIC invocation follows the separately qualified source-input measurement;
finite structure and byte bindings are independently enforced before decoding.
"""

import ctypes as c
import hashlib
import json
import os
import platform
import struct
import subprocess
import sys
import uuid
from functools import lru_cache
from pathlib import Path

from .images import GUID, AuditUnavailable, guid


def ico_proof(raw, *, native_details=None):
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
        proof = decode_ico_variant(wrapper, include_pixels=native_details is not None)
        if native_details is not None:
            proof.pop("rgba")
            provenance = proof["codec"]
            native_details.append({"index": index, "codec": provenance})
            proof["codec"] = provenance["name"]
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


def decode_ico_variant(data, *, kind="ICO", include_pixels=False):
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
            guid(
                {
                    "ICO": "a3a860c4-338f-4c17-919a-fba4b5628f21",
                    "BMP": "0af1d87e-fcfe-4188-bdeb-a7906471cbe3",
                }[kind]
            ).data
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
            if width.value * height.value * 4 > (
                4 * 1024 * 1024 if include_pixels else 256 * 1024 * 1024
            ):
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
            assert kind.casefold() in name.value.casefold(), (
                "native decoder classification"
            )
            result = {
                "format": kind,
                "codec": name.value,
                "width": width.value,
                "height": height.value,
                "decoded_bytes": len(rgba),
                "rgba_sha256": hashlib.sha256(rgba).hexdigest(),
            }
            if include_pixels:
                result["rgba"] = rgba
                result["codec"] = icon_codec_provenance(info, decoder, ole, sh, call)
            return result
        finally:
            release(converter)
            release(frame)
    finally:
        for obj in reversed(objects):
            release(obj)
        ole.CoUninitialize()


_ICON_MODULES = {}


def icon_codec_provenance(info, decoder, ole, sh, call):
    """Bind actual decoder COM methods to a mapped DLL, not its friendly name."""
    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.GetModuleHandleExW.argtypes = [c.c_uint32, c.c_void_p, c.POINTER(c.c_void_p)]
    kernel.GetModuleHandleExW.restype = c.c_int
    kernel.GetModuleFileNameW.argtypes = [c.c_void_p, c.c_wchar_p, c.c_uint32]
    kernel.GetModuleFileNameW.restype = c.c_uint32
    address = c.cast(decoder, c.POINTER(c.POINTER(c.c_void_p))).contents[13]
    mapped = c.c_void_p()
    if not kernel.GetModuleHandleExW(6, address, c.byref(mapped)):
        raise AuditUnavailable("actual WIC decoder module unresolved")
    modules = []
    for handle in (mapped.value, ole._handle, sh._handle):
        buffer = c.create_unicode_buffer(32768)
        length = kernel.GetModuleFileNameW(handle, buffer, len(buffer))
        if not 0 < length < len(buffer):
            raise AuditUnavailable("mapped WIC/support DLL path unavailable")
        path = Path(buffer.value).resolve()
        key = str(path).casefold()
        if key not in _ICON_MODULES:
            if len(_ICON_MODULES) >= 4:
                raise AuditUnavailable("four mapped DLL provenance bound")
            before = path.stat()
            if (
                before.st_size > 16 * 1024 * 1024
                or sum(v["length"] for v in _ICON_MODULES.values()) + before.st_size
                > 32 * 1024 * 1024
            ):
                raise AuditUnavailable("mapped DLL provenance byte bound")
            digest = hashlib.sha256()
            measured = 0
            with path.open("rb") as stream:
                while block := stream.read(
                    min(131072, 16 * 1024 * 1024 + 1 - measured)
                ):
                    measured += len(block)
                    if measured > 16 * 1024 * 1024:
                        raise AuditUnavailable(
                            "mapped DLL changed beyond provenance bound"
                        )
                    digest.update(block)
            after = path.stat()
            assert (before.st_size, before.st_mtime_ns, before.st_ino) == (
                after.st_size,
                after.st_mtime_ns,
                after.st_ino,
            ) and measured == before.st_size, "mapped DLL changed during measurement"
            _ICON_MODULES[key] = {
                "path": str(path),
                "length": measured,
                "sha256": digest.hexdigest(),
                "file_version": icon_dll_version(path),
            }
        modules.append(dict(_ICON_MODULES[key]))
    codec_id = GUID()
    call(info, 4, [c.POINTER(GUID)], c.byref(codec_id))

    def text(index):
        size = c.c_uint32()
        call(
            info,
            index,
            [c.c_uint32, c.c_wchar_p, c.POINTER(c.c_uint32)],
            0,
            None,
            c.byref(size),
        )
        assert 0 < size.value < 4096, "bounded WIC codec string"
        value = c.create_unicode_buffer(size.value)
        call(
            info,
            index,
            [c.c_uint32, c.c_wchar_p, c.POINTER(c.c_uint32)],
            size.value,
            value,
            c.byref(size),
        )
        if not value.value:
            raise AuditUnavailable("empty actual WIC codec name/version")
        return value.value

    return {
        "clsid": str(uuid.UUID(bytes_le=bytes(codec_id.data))),
        "name": text(10),
        "version": text(8),
        "decoder_mapped_dll": modules[0],
        "support_mapped_dlls": modules[1:],
        "windows": platform.platform(),
        "python": sys.version,
        "helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def icon_dll_version(path):
    version = c.WinDLL("version", use_last_error=True)
    version.GetFileVersionInfoSizeW.argtypes = [c.c_wchar_p, c.POINTER(c.c_uint32)]
    version.GetFileVersionInfoSizeW.restype = c.c_uint32
    ignored = c.c_uint32()
    size = version.GetFileVersionInfoSizeW(str(path), c.byref(ignored))
    if not 0 < size <= 1024 * 1024:
        raise AuditUnavailable("bounded mapped DLL version resource unavailable")
    raw = c.create_string_buffer(size)
    version.GetFileVersionInfoW.argtypes = [
        c.c_wchar_p,
        c.c_uint32,
        c.c_uint32,
        c.c_void_p,
    ]
    version.GetFileVersionInfoW.restype = c.c_int
    version.VerQueryValueW.argtypes = [
        c.c_void_p,
        c.c_wchar_p,
        c.POINTER(c.c_void_p),
        c.POINTER(c.c_uint32),
    ]
    version.VerQueryValueW.restype = c.c_int
    pointer, length = c.c_void_p(), c.c_uint32()
    if (
        not version.GetFileVersionInfoW(str(path), 0, size, raw)
        or not version.VerQueryValueW(raw, "\\", c.byref(pointer), c.byref(length))
        or length.value < 52
    ):
        raise AuditUnavailable("actual mapped DLL version resource unavailable")
    fields = struct.unpack("<13I", c.string_at(pointer, 52))
    assert fields[0] == 0xFEEF04BD, "mapped DLL fixed-version signature"
    return ".".join(
        str(x)
        for x in (
            fields[2] >> 16,
            fields[2] & 65535,
            fields[3] >> 16,
            fields[3] & 65535,
        )
    )


def icon_process_memory():
    """Absolute process observations, including native allocations; no peak delta."""
    if os.name != "nt":
        raise AuditUnavailable("Windows process-memory observation unavailable")

    class Counters(c.Structure):
        _fields_ = [("cb", c.c_uint32), ("faults", c.c_uint32)] + [
            (name, c.c_size_t)
            for name in (
                "peak_working_set",
                "working_set",
                "peak_paged_pool",
                "paged_pool",
                "peak_nonpaged_pool",
                "nonpaged_pool",
                "pagefile",
                "peak_pagefile",
                "private_commit",
            )
        ]

    kernel, psapi = c.WinDLL("kernel32"), c.WinDLL("psapi")
    kernel.GetCurrentProcess.restype = c.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [c.c_void_p, c.c_void_p, c.c_uint32]
    psapi.GetProcessMemoryInfo.restype = c.c_int
    counters = Counters()
    counters.cb = c.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(
        kernel.GetCurrentProcess(), c.byref(counters), counters.cb
    ):
        raise AuditUnavailable("actual Windows process-memory observation unavailable")
    return {
        name: getattr(counters, name)
        for name in (
            "peak_working_set",
            "working_set",
            "private_commit",
            "peak_pagefile",
        )
    }


def canonical_icon_pixels(rgba):
    result = bytearray(rgba)
    for pos in range(0, len(result), 4):
        if result[pos + 3] == 0:
            result[pos : pos + 3] = b"\0\0\0"
    return bytes(result)


def compare_icon_pixels(expected, native):
    assert len(expected) == len(native) and len(expected) % 4 == 0, "icon pixel length"
    alpha = sum(a != b for a, b in zip(expected[3::4], native[3::4], strict=True))
    visible, hidden = 0, 0
    for pos in range(0, len(expected), 4):
        differences = sum(
            a != b
            for a, b in zip(expected[pos : pos + 3], native[pos : pos + 3], strict=True)
        )
        if expected[pos + 3]:
            visible += differences
        else:
            hidden += differences
    result = {
        "raw_equal": expected == native,
        "canonical_equal": canonical_icon_pixels(expected)
        == canonical_icon_pixels(native),
        "alpha_mismatches": alpha,
        "visible_rgb_mismatches": visible,
        "hidden_rgb_mismatches": hidden,
        "native_rgba_sha256": hashlib.sha256(native).hexdigest(),
        "native_canonical_sha256": hashlib.sha256(
            canonical_icon_pixels(native)
        ).hexdigest(),
    }
    assert not alpha and not visible and result["canonical_equal"], (
        f"icon native visible/alpha mismatch: {result}"
    )
    return result


def _legacy_icon_layout(raw):
    """Preflight the entire unchanged historical alternative before native decode."""
    assert len(raw) in {5430, 15406}, "historical ICO complete length"
    reserved, kind, count = struct.unpack_from("<HHH", raw)
    assert (reserved, kind, count) == (0, 1, 2 if len(raw) == 5430 else 3), (
        "historical ICO directory"
    )
    sizes, tails = ((32, 16), (0, 0)) if count == 2 else ((16, 32, 48), (0, 128, 192))
    cursor = 6 + 16 * count
    for index, (size, tail) in enumerate(zip(sizes, tails, strict=True)):
        w, h, colors, spare, planes, bits, length, offset = struct.unpack_from(
            "<BBBBHHII", raw, 6 + 16 * index
        )
        mask_bytes = 4 * ((size + 31) // 32) * size
        assert (w, h, colors, spare, planes, bits) == (size, size, 0, 0, 1, 32), (
            "historical ICO entry"
        )
        assert (
            offset == cursor
            and length == 40 + size * size * 4 + mask_bytes + tail
            and offset + length <= len(raw)
        ), "historical ICO extent"
        assert struct.unpack_from("<IiiHHIIiiII", raw, offset) == (
            40,
            size,
            2 * size,
            1,
            32,
            0,
            0,
            0,
            0,
            0,
            0,
        ), "historical ICO DIB"
        mask_start = offset + 40 + size * size * 4
        assert not any(raw[mask_start + mask_bytes : offset + length]), (
            "historical ICO zero tail"
        )
        if count == 3 and size in {32, 48}:
            assert not any(raw[mask_start : mask_start + mask_bytes]), (
                "historical ICO zero mask"
            )
        cursor += length
    assert cursor == len(raw), "historical ICO final extent"


def _new_icon_layout(raw):
    assert 6 <= len(raw) <= 8 * 1024 * 1024, "ICO byte bound"
    reserved, kind, count = struct.unpack_from("<HHH", raw)
    assert reserved == 0 and kind == 1 and 1 <= count <= 16, "ICO directory"
    directory_end = 6 + 16 * count
    assert directory_end <= len(raw), "ICO complete directory"
    frames, pixels, sizes = [], 0, []
    for index in range(count):
        w, h, colors, spare, planes, bits, length, offset = struct.unpack_from(
            "<BBBBHHII", raw, 6 + 16 * index
        )
        w, h = w or 256, h or 256
        assert w == h and (colors, spare, planes, bits) == (0, 0, 1, 32), (
            "ICO entry fields"
        )
        pixels += w * h
        assert pixels <= 1048576, "ICO advertised pixel bound before duplicate checks"
        sizes.append((w, h))
        mask_length = 4 * ((w + 31) // 32) * h
        assert (
            length == 40 + 4 * w * h + mask_length
            and directory_end <= offset <= len(raw)
            and length <= len(raw) - offset
        ), "ICO body extent"
        header = struct.unpack_from("<IiiHHIIiiII", raw, offset)
        assert (
            header[:6] == (40, w, 2 * h, 1, 32, 0)
            and header[6] in {0, 4 * w * h}
            and header[7:] == (0, 0, 0, 0)
        ), (
            f"ICO DIB actual={header}; expected width={w},height={2 * h},sizeImage0or{4 * w * h}"
        )
        assert any(raw[offset + 43 : offset + 40 + 4 * w * h : 4]), (
            "ICO new family requires stored alpha"
        )
        frames.append(
            {
                "index": index,
                "width": w,
                "height": h,
                "offset": offset,
                "body_length": length,
                "pixel_offset": offset + 40,
                "mask_length": mask_length,
                "sizeImage": header[6],
                "dib_header": list(header),
            }
        )
    assert len(set(sizes)) == len(sizes), "ICO duplicate dimensions"
    cursor = directory_end
    for frame in sorted(frames, key=lambda f: f["offset"]):
        assert frame["offset"] == cursor, "ICO exact interval tiling"
        cursor += frame["body_length"]
    assert cursor == len(raw), "ICO complete container without trailer"
    return frames


def _bmp_icon_layout(raw):
    assert 54 <= len(raw) <= 4194358, "BMP byte bound"
    assert struct.unpack_from("<2sIHHI", raw) == (b"BM", len(raw), 0, 0, 54), (
        "BMP file header"
    )
    header = struct.unpack_from("<IiiHHIIiiII", raw, 14)
    _, w, h, *_ = header
    assert 1 <= w <= 1024 and 1 <= h <= 1024 and w * h <= 1048576, (
        "BMP dimensions/pixels"
    )
    assert (
        header[:6] == (40, w, h, 1, 32, 0)
        and header[6] in {0, 4 * w * h}
        and header[7:] == (0, 0, 0, 0)
    ), f"BMP DIB actual={header}"
    assert len(raw) == 54 + 4 * w * h, "BMP exact pixel extent without gap/tail"
    return [
        {
            "index": 0,
            "width": w,
            "height": h,
            "offset": 14,
            "body_length": len(raw) - 14,
            "pixel_offset": 54,
            "dib_header": list(header),
        }
    ]


def _manual_icon_rgba(raw, frame, kind):
    width, height, begin = frame["width"], frame["height"], frame["pixel_offset"]
    output = bytearray(4 * width * height)
    for y in range(height):
        start = begin + (height - y - 1) * width * 4
        row = raw[start : start + width * 4]
        target = y * width * 4
        output[target : target + width * 4 : 4] = row[2::4]
        output[target + 1 : target + width * 4 : 4] = row[1::4]
        output[target + 2 : target + width * 4 : 4] = row[0::4]
        output[target + 3 : target + width * 4 : 4] = (
            row[3::4] if kind == "ICO" else bytes([255]) * width
        )
    return bytes(output)


def icon_proof(raw, *, native=True):
    """Explicit profile5 independent union. Manual-only proofs never claim native."""
    assert isinstance(raw, bytes), "icon proof requires bound original bytes"
    if raw.startswith(b"BM"):
        kind, frames = "BMP", _bmp_icon_layout(raw)
    else:
        try:
            _legacy_icon_layout(raw)
        except AssertionError:
            kind, frames = "ICO", _new_icon_layout(raw)
        else:
            assert native, (
                "historical icon proof requires unchanged native interpretation"
            )
            details = []
            old = ico_proof(raw, native_details=details)
            return {
                "format": "ICO",
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "alternative": "unchanged-historical",
                "legacy_proof": old,
                "frames": [
                    dict(frame, index=index, pixel_offset=frame["offset"] + 40)
                    for index, frame in enumerate(old["frames"])
                ],
                "native_details": details,
                "status": "complete-unchanged-historical-pixels",
            }
    proved = []
    for frame in frames:
        rgba = _manual_icon_rgba(raw, frame, kind)
        origin = frame["offset"] if kind == "ICO" else 14
        result = dict(frame)
        result.update(
            body_sha256=hashlib.sha256(
                raw[origin : origin + frame["body_length"]]
            ).hexdigest(),
            rgba_sha256=hashlib.sha256(rgba).hexdigest(),
            canonical_rgba_sha256=hashlib.sha256(
                canonical_icon_pixels(rgba)
            ).hexdigest(),
            decoded_bytes=len(rgba),
        )
        if kind == "ICO":
            end = frame["offset"] + frame["body_length"]
            result["mask_sha256"] = hashlib.sha256(
                raw[end - frame["mask_length"] : end]
            ).hexdigest()
        if native:
            data = raw
            if kind == "ICO":
                size, length = frame["width"], frame["body_length"]
                data = (
                    struct.pack(
                        "<HHHBBBBHHII",
                        0,
                        1,
                        1,
                        size % 256,
                        size % 256,
                        0,
                        0,
                        1,
                        32,
                        length,
                        22,
                    )
                    + raw[origin : origin + length]
                )
            decoded = decode_ico_variant(data, kind=kind, include_pixels=True)
            assert (decoded["width"], decoded["height"]) == (
                frame["width"],
                frame["height"],
            ), "icon native dimensions"
            native_rgba = decoded.pop("rgba")
            result["comparison"] = compare_icon_pixels(rgba, native_rgba)
            result["native"] = decoded
            del native_rgba, decoded
        proved.append(result)
        del rgba
    return {
        "format": kind,
        "alternative": "structural-alpha" if kind == "ICO" else "opaque-bgrx",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "frames": proved,
        "status": "complete-independent-icon-pixels"
        if native
        else "manual-only-unqualified-native",
    }


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


_JPEG_CORRUPT = b"Corrupt JPEG data:"
_JPEG_PREMATURE = b"Corrupt JPEG data: premature end of data segment"
_WIC_JPEG_WORKER = """import json, sys
from tests.local_acceptance.images import AuditUnavailable, decode_image
try:
    proof = decode_image(sys.stdin.buffer.read(), "measured.jpg")
    result = {"status": "decoded", "proof": proof}
except AuditUnavailable as error:
    result = {"status": "unavailable", "message": str(error)}
except AssertionError as error:
    result = {"status": "invalid", "message": str(error)}
print(json.dumps(result))
"""


def isolated_jpeg_decode(raw):
    """Retain native stderr; HRESULT success alone may conceal recovery."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", _WIC_JPEG_WORKER],
            input=raw,
            capture_output=True,
            timeout=60,
            check=False,
            cwd=Path(__file__).resolve().parents[2],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired, MemoryError) as error:
        raise AuditUnavailable(
            "isolated WIC JPEG diagnostic capability unavailable"
        ) from error
    if result.returncode:
        raise AuditUnavailable("isolated WIC JPEG diagnostic process failed")
    try:
        response = json.loads(result.stdout)
    except (ValueError, UnicodeError) as error:
        raise AuditUnavailable(
            "isolated WIC JPEG diagnostic response unavailable"
        ) from error
    if response["status"] == "unavailable":
        raise AuditUnavailable(response["message"])
    assert response["status"] == "decoded", "invalid full JPEG decode: " + response.get(
        "message", ""
    )
    proof = response["proof"]
    assert (
        proof["format"] == "JPEG"
        and proof["source_sha256"] == hashlib.sha256(raw).hexdigest()
    ), "isolated JPEG source-bound classification"
    return proof, result.stderr


@lru_cache(maxsize=1)
def jpeg_diagnostic_capability():
    """A known source-pinned corrupt challenge guards against silent codecs."""
    try:
        raw = (
            Path(__file__).parents[1] / "fixtures/local_api_images_v3/inert-blue.jpg"
        ).read_bytes()
    except OSError as error:
        raise AuditUnavailable("JPEG diagnostic challenge unavailable") from error
    if (
        hashlib.sha256(raw).hexdigest()
        != "e3a2954fee014acf9f0b399791f49458604d6592ab22844bcebecc0e666be5ed"
    ):
        raise AuditUnavailable("JPEG diagnostic challenge source pin differs")
    # Independent literal source facts: entropy623:630, EOI630:632. Removing
    # its final entropy byte retains all headers and still triggers recovery.
    codec = None
    for challenge, expected in (
        (raw[:629] + b"\xff\xd9", _JPEG_PREMATURE),
        (
            raw[:20] + b"junk" + raw[20:],
            b"Corrupt JPEG data: 4 extraneous bytes before marker",
        ),
    ):
        proof, diagnostics = isolated_jpeg_decode(challenge)
        if expected not in diagnostics:
            raise AuditUnavailable(
                "WIC JPEG strict corrupt-data diagnostic unavailable"
            )
        if codec is not None and proof["codec"] != codec:
            raise AuditUnavailable("WIC JPEG challenge codecs disagree")
        codec = proof["codec"]
    return codec


def jpeg_proof(raw):
    """Complete native pixels plus definite native corrupt-data recovery refusal."""
    jpeg_headers(raw)
    codec = jpeg_diagnostic_capability()
    proof, diagnostics = isolated_jpeg_decode(raw)
    if proof["codec"] != codec:
        raise AuditUnavailable(
            "WIC JPEG diagnostic codec differs from capability challenge"
        )
    assert _JPEG_CORRUPT not in diagnostics, (
        "JPEG definite corrupt data recovery: "
        + diagnostics.decode("utf-8", errors="replace")
    )
    # Unknown diagnostics cannot establish either valid or invalid content.
    # A benign allowance requires independent qualification of its context.
    if diagnostics.strip():
        raise AuditUnavailable(
            "unclassified WIC JPEG native diagnostic: "
            + diagnostics.decode("utf-8", errors="replace")
        )
    proof["native_diagnostics"] = diagnostics.decode("utf-8", errors="replace")
    proof["corrupt_data_diagnostic_capability"] = codec
    return proof
