"""Reviewed external-file locations, interpreted without filesystem access."""

import re
from pathlib import PureWindowsPath
from urllib.parse import quote


def external_file_uri(location, refuse):
    """Keep exact source spelling in evidence; encode a drive-qualified file URI."""
    path = PureWindowsPath(location)
    parts = re.split(r"[\\/]", location)
    if (
        not re.match(r"^[A-Za-z]:[\\/]", location)
        or not path.is_absolute()
        or len(parts) < 2
        or any(not part or part in {".", ".."} for part in parts[1:])
        or any(ord(char) < 32 or char in '<>"|?*' for char in location)
        or ":" in location[2:]
        or any(part.endswith((".", " ")) for part in parts[1:])
        or any(
            re.fullmatch(
                r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.IGNORECASE
            )
            for part in parts[1:]
        )
    ):
        refuse(
            "unsupported_feature",
            "External file requires a safe absolute drive-qualified Windows file path",
        )
    return "file:///" + quote(path.as_posix(), safe="/:")
