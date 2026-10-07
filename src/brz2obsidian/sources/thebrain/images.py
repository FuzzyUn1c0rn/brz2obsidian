"""Full decoding only for the reviewed generated note-image basis."""

import warnings
from pathlib import PurePosixPath

from PIL import Image

FORMATS = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".webp": "WEBP",
    ".gif": "GIF",
    ".bmp": "BMP",
    ".avif": "AVIF",
}


def validate_note_image(stream, name, refuse, asset_id):
    expected = FORMATS.get(PurePosixPath(name).suffix.casefold())
    if expected is None:
        refuse(
            "unsupported_feature",
            "Fallback note image has an unsupported content kind",
            (asset_id,),
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(stream, formats=(expected,)) as image:
                image.verify()
            stream.seek(0)
            with Image.open(stream, formats=(expected,)) as image:
                width, height = image.size
                if width <= 0 or height <= 0:
                    raise ValueError("Empty image dimensions")
                for index in range(getattr(image, "n_frames", 1)):
                    image.seek(index)
                    image.load()
                return {"format": expected, "width": width, "height": height}
    except (
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        refuse(
            "invalid_source",
            "Fallback note image is not fully decodable usable content",
            (asset_id,),
        )
