"""Portable destination paths and names for an import into an existing vault."""

import re
import unicodedata
from pathlib import PurePosixPath

from brz2obsidian.contracts import Issue, MigrationRefused


def import_name_key(value):
    leaf = value.rsplit("/", 1)[-1]
    normalized = unicodedata.normalize("NFC", leaf).casefold()
    return normalized.removesuffix(".md")


def validate_import_location(location):
    if (
        not isinstance(location, str)
        or not location
        or len(location.encode("utf-16-le")) // 2 > 180
        or unicodedata.normalize("NFC", location) != location
        or any(not _portable_folder(part) for part in location.split("/"))
    ):
        raise MigrationRefused(
            (
                Issue(
                    code="import_location_invalid",
                    phase="planning",
                    message="Choose a portable relative import folder inside the vault.",
                    guidance="Use visible folder names with no absolute or parent paths.",
                ),
            )
        )
    return location


def _portable_folder(part):
    return (
        bool(part)
        and part == part.strip(" .")
        and len(part.encode("utf-16-le")) // 2 <= 120
        and not re.search(r'[<>:"\\|?*#^%\[\]\x00-\x1f]', part)
        and not re.match(
            r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", part, re.IGNORECASE
        )
    )


def qualify_import_path(location, path):
    return path if location is None else location + "/" + path


def scoped_support_paths(location, artifacts, occupied):
    paths = {}
    for artifact in artifacts:
        logical = artifact.relative_path
        if artifact.purpose == "configuration":
            continue
        path = PurePosixPath(logical)
        leaf = path.name
        next_suffix = 1
        while (
            artifact.purpose != "migration_record" and import_name_key(leaf) in occupied
        ):
            suffix = " — Import" if next_suffix == 1 else f" — Import {next_suffix}"
            leaf = path.stem + suffix + path.suffix
            next_suffix += 1
        paths[logical] = qualify_import_path(location, str(path.with_name(leaf)))
        occupied.add(import_name_key(leaf))
    return paths
