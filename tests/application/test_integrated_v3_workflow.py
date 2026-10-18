"""Public mixed-workflow facts with independently chosen source expectations."""

from zipfile import ZipFile

import yaml

EMPTY = "Notes/Empty — 00000000000000000000000000000003.md"
RESERVED = "Notes/Empty — 0000000000000000000000000000000a.md"


def properties(body):
    return yaml.safe_load(body.decode().split("---", 2)[1])


def reordered(source, destination):
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    for name in ("thoughts.json", "links.json", "attachments.json"):
        parts[name] = b"\n".join(reversed(parts[name].splitlines()))
    with ZipFile(destination, "w") as archive:
        for name, body in reversed(list(parts.items())):
            archive.writestr(name, body)
