"""Shared readable filenames and stable collision progression."""

import re
import unicodedata


def readable_filename(original):
    value = unicodedata.normalize("NFC", original)
    value = value.replace(":", " - ").replace("[", "(").replace("]", ")")
    value = re.sub(r'[<>"/\\|?*#^%\x00-\x1f]', " ", value)
    value = " ".join(value.split()).strip(" .") or "Untitled"
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", value, re.IGNORECASE):
        value = "Note - " + value
    return value


def collision_keys(names, widths, seeds, reserved=()):
    groups = {}
    for key, name in names.items():
        groups.setdefault(name.casefold(), []).append(key)
    collisions = set()
    for name, group in groups.items():
        if name in reserved:
            collisions.update(group)
        elif len(group) > 1:
            extendable = [
                key for key in group if widths[key] and widths[key] < len(seeds[key])
            ]
            natural = [key for key in group if not widths[key]]
            collisions.update(extendable or natural or group)
    return collisions


def extended_seed_width(width, seed):
    if width and width >= len(seed):
        return None
    return width + 4 if width else 8
