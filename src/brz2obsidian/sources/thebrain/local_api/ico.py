"""The two finite profile3 ICO/DIB signatures; original bytes stay intact."""

import struct
import warnings
from io import BytesIO
from pathlib import Path

from PIL import Image

from .errors import refuse


def validate_ico(raw):
    """Qualify exact storage extents and fully decode every advertised variant."""
    if isinstance(raw, Path):
        with raw.open("rb") as stream:
            data = stream.read(15407)
    else:
        data = raw
    try:
        if len(data) not in {5430, 15406}:
            raise ValueError
        reserved, kind, count = struct.unpack_from("<HHH", data)
        if reserved != 0 or kind != 1 or count not in {2, 3}:
            raise ValueError
        dimensions = (32, 16) if count == 2 else (16, 32, 48)
        tails = (0, 0) if count == 2 else (0, 128, 192)
        cursor = 6 + 16 * count
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            for index, (width, tail) in enumerate(zip(dimensions, tails)):
                entry = struct.unpack_from("<BBBBHHII", data, 6 + index * 16)
                size, offset = entry[-2:]
                mask_length = 4 * ((width + 31) // 32) * width
                body_length = 40 + 4 * width * width + mask_length + tail
                if (
                    entry[:6] != (width, width, 0, 0, 1, 32)
                    or size != body_length
                    or offset != cursor
                    or offset + size > len(data)
                ):
                    raise ValueError
                body = data[offset : offset + size]
                if struct.unpack_from("<IiiHHIIiiII", body) != (
                    40,
                    width,
                    width * 2,
                    1,
                    32,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                ):
                    raise ValueError
                mask_start = 40 + 4 * width * width
                if tail and any(body[mask_start:]):
                    raise ValueError
                # A one-entry wrapper forces decoding of this exact body rather
                # than the decoder's preferred whole-container resolution.
                wrapper = (
                    struct.pack(
                        "<HHHBBBBHHII", 0, 1, 1, width, width, 0, 0, 1, 32, size, 22
                    )
                    + body
                )
                with Image.open(BytesIO(wrapper), formats=("ICO",)) as image:
                    if image.format != "ICO" or image.size != (width, width):
                        raise ValueError
                    image.verify()
                with Image.open(BytesIO(wrapper), formats=("ICO",)) as image:
                    if image.format != "ICO" or image.size != (width, width):
                        raise ValueError
                    image.load()
                    with image.convert("RGBA") as pixels:
                        pixels.load()
                cursor += size
        if cursor != len(data):
            raise ValueError
    except (
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
        struct.error,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        refuse("Required icon bytes do not match the finite ICO qualification")
