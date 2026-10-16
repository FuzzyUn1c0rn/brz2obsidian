"""Strict full JPEG eligibility for the new profile3 note-image branch."""

from pathlib import Path

import simplejpeg

from .errors import refuse


def validate_jpeg(raw, size, mode):
    """Reject decoder recovery; discard native pixels and keep original bytes."""
    try:
        colours = {
            "L": ("GRAY", 1),
            "CMYK": ("CMYK", 4),
            "YCbCr": ("RGB", 3),
            "RGB": ("RGB", 3),
        }
        if mode not in colours:
            raise ValueError
        colour, components = colours[mode]
        data = raw.read_bytes() if isinstance(raw, Path) else raw
        pixels = simplejpeg.decode_jpeg(
            data,
            colorspace=colour,
            fastdct=False,
            fastupsample=False,
            min_height=0,
            min_width=0,
            min_factor=1,
            strict=True,
        )
        if pixels.shape != (size[1], size[0], components):
            raise ValueError
    except OSError, ValueError, RuntimeError:
        refuse("Required JPEG image bytes cannot be decoded without recovery")
