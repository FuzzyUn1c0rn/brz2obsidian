"""Bounded profile5 owned-icon formats; all original bytes remain unchanged."""

import struct
import warnings
from io import BytesIO
from pathlib import Path

from PIL import Image

from .errors import check_cancel, refuse
from .ico import _legacy_decode, _legacy_frames

ICO_LIMIT = 8_388_608
BMP_LIMIT = 4_194_358


def encoded_limit(prefix, configured):
    if prefix.startswith(b"\0\0\1\0"):
        return min(configured, ICO_LIMIT)
    if prefix.startswith(b"BM"):
        return min(configured, BMP_LIMIT)
    return configured


def validate_structural_icon(raw, *, cancel=None):
    """Select new wire families without an eager buffer or duplicate Path read."""
    try:
        check_cancel(cancel)
        if isinstance(raw, Path):
            with raw.open("rb") as stream:
                prefix = stream.read(4)
                check_cancel(cancel)
                if not (prefix.startswith(b"BM") or prefix == b"\0\0\1\0"):
                    return False
                limit = encoded_limit(prefix, ICO_LIMIT)
                if raw.stat().st_size > limit:
                    raise ValueError
                raw = prefix + stream.read(limit + 1 - len(prefix))
                check_cancel(cancel)
        else:
            prefix = bytes(raw[:4])
            if not (prefix.startswith(b"BM") or prefix == b"\0\0\1\0"):
                return False
        if prefix.startswith(b"BM"):
            validate_bmp(raw, cancel=cancel)
        else:
            validate_ico5(raw, cancel=cancel)
        return True
    except OSError, ValueError:
        refuse("Required icon bytes exceed the bounded acquisition qualification")


def _read(raw, limit):
    if isinstance(raw, Path):
        if raw.stat().st_size > limit:
            raise ValueError
        with raw.open("rb") as stream:
            raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError
    return raw


def _decode(data, format, width, height, expected, cancel):
    check_cancel(cancel)
    with Image.open(BytesIO(data), formats=(format,)) as image:
        if image.format != format or image.size != (width, height):
            raise ValueError
        image.verify()
    check_cancel(cancel)
    with Image.open(BytesIO(data), formats=(format,)) as image:
        if image.format != format or image.size != (width, height):
            raise ValueError
        image.load()
        with image.convert("RGBA") as pixels:
            pixels.load()
            actual = pixels.tobytes()
    check_cancel(cancel)
    if len(actual) != 4 * width * height or actual != expected:
        raise ValueError


def _rgba(data, offset, width, height, *, opaque=False):
    stride = 4 * width
    result = bytearray(stride * height)
    for row in range(height):
        source_start = offset + (height - row - 1) * stride
        source = data[source_start : source_start + stride]
        start, end = row * stride, (row + 1) * stride
        result[start:end:4] = source[2::4]
        result[start + 1 : end : 4] = source[1::4]
        result[start + 2 : end : 4] = source[0::4]
        result[start + 3 : end : 4] = b"\xff" * width if opaque else source[3::4]
    return result


def validate_bmp(raw, *, cancel=None):
    try:
        check_cancel(cancel)
        data = _read(raw, BMP_LIMIT)
        check_cancel(cancel)
        magic, size, reserved1, reserved2, offset = struct.unpack_from("<2sIHHI", data)
        header = struct.unpack_from("<IiiHHIIiiII", data, 14)
        width, height = header[1:3]
        if not 1 <= width <= 1024 or not 1 <= height <= 1024:
            raise ValueError
        pixel_bytes = 4 * width * height
        if (
            (magic, size, reserved1, reserved2, offset) != (b"BM", len(data), 0, 0, 54)
            or header != (40, width, height, 1, 32, 0, header[6], 0, 0, 0, 0)
            or header[6] not in (0, pixel_bytes)
            or len(data) != 54 + pixel_bytes
        ):
            raise ValueError
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            _decode(
                data,
                "BMP",
                width,
                height,
                _rgba(data, 54, width, height, opaque=True),
                cancel,
            )
    except (
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
        struct.error,
        Image.DecompressionBombError,
        Warning,
    ):
        refuse("Required icon bytes do not match the bounded BMP qualification")


def _icon_directory(data):
    reserved, kind, count = struct.unpack_from("<HHH", data)
    if (reserved, kind) != (0, 1) or not 1 <= count <= 16:
        raise ValueError
    directory_end = 6 + count * 16
    if len(data) < directory_end:
        raise ValueError
    entries = [
        struct.unpack_from("<BBBBHHII", data, 6 + index * 16) for index in range(count)
    ]
    if sum((entry[0] or 256) * (entry[1] or 256) for entry in entries) > 1_048_576:
        raise ValueError
    return entries, directory_end


def _frames(data):
    entries, directory_end = _icon_directory(data)
    frames, dimensions = [], set()
    for w, h, colors, reserved, planes, bits, size, offset in entries:
        width, height = w or 256, h or 256
        if (
            width != height
            or width in dimensions
            or (colors, reserved, planes, bits) != (0, 0, 1, 32)
            or offset < directory_end
            or size <= 0
            or size > len(data) - offset
        ):
            raise ValueError
        dimensions.add(width)
        xor_bytes = 4 * width * height
        and_bytes = 4 * ((width + 31) // 32) * height
        if size != 40 + xor_bytes + and_bytes:
            raise ValueError
        header = struct.unpack_from("<IiiHHIIiiII", data, offset)
        if (
            header != (40, width, 2 * height, 1, 32, 0, header[6], 0, 0, 0, 0)
            or header[6] not in (0, xor_bytes)
            or not any(data[offset + 43 : offset + 40 + xor_bytes : 4])
        ):
            raise ValueError
        frames.append((width, size, offset))
    cursor = directory_end
    for width, size, offset in sorted(frames, key=lambda f: f[2]):
        if offset != cursor:
            raise ValueError
        cursor += size
    if cursor != len(data):
        raise ValueError
    return frames


def validate_ico5(raw, *, cancel=None):
    try:
        check_cancel(cancel)
        data = _read(raw, ICO_LIMIT)
        check_cancel(cancel)
        try:
            frames = _legacy_frames(data)
            legacy = True
        except ValueError:
            frames = _frames(data)
            legacy = False
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            if legacy:
                _legacy_decode(data, frames, lambda: check_cancel(cancel))
            else:
                warnings.simplefilter("error")
                for width, size, offset in frames:
                    check_cancel(cancel)
                    wrapper = (
                        struct.pack(
                            "<HHHBBBBHHII",
                            0,
                            1,
                            1,
                            width % 256,
                            width % 256,
                            0,
                            0,
                            1,
                            32,
                            size,
                            22,
                        )
                        + data[offset : offset + size]
                    )
                    _decode(
                        wrapper,
                        "ICO",
                        width,
                        width,
                        _rgba(data, offset + 40, width, width),
                        cancel,
                    )
                    del wrapper
    except (
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
        struct.error,
        Image.DecompressionBombError,
        Warning,
    ):
        refuse("Required icon bytes do not match the bounded ICO qualification")
