"""Exact bounded source signatures through authored ZIPs and published navigation."""

import json
from zipfile import ZipFile

from tests.sources.test_reader import rewrite


def edit_rows(source, name, edit):
    with ZipFile(source) as archive:
        rows = [json.loads(line) for line in archive.read(name).splitlines()]
    edit(rows)
    rewrite(source, name, "\n".join(map(json.dumps, rows)).encode())


def nested_diagnostic_token(identity_text, layers):
    """Author nested escapes; later layers encode only escape introducers."""
    token = identity_text
    for index, layer in enumerate(layers):
        if index == 0:
            token = "".join(
                (f"%{ord(char):02X}" if layer == "P" else rf"\u{ord(char):04x}")
                for char in token
            )
        elif layer == "P":
            token = token.replace("%", "%25").replace("\\", "%5C")
        else:
            token = token.replace("\\", r"\u005c").replace("%", r"\u0025")
    return token
