"""Independent URI facts from authored Markdown, with explicit source namespace."""

import base64
import re
import string
import unicodedata
from dataclasses import dataclass
from html.entities import html5
from urllib.parse import quote
from uuid import UUID


@dataclass(frozen=True)
class ThoughtDestination:
    local_id: str | None
    source_target: str
    qualified: bool


def markdown_destination(authored):
    """One lexical pass: escaped openers and emitted text are never reparsed."""

    def replacement(match):
        escaped, entity = match.groups()
        if escaped is not None:
            return escaped
        if entity.startswith("#"):
            hexadecimal = entity[1:2] in {"x", "X"}
            value = int(
                entity[2:] if hexadecimal else entity[1:], 16 if hexadecimal else 10
            )
            # The pinned destination grammar retains invalid references as
            # literal text (then the qualified URI's '#' guard refuses them).
            if (
                value > 0x10FFFF
                or value & 0xFFFF in {0xFFFE, 0xFFFF}
                or 0xFDD0 <= value <= 0xFDEF
            ):
                return match[0]
            character = chr(value)
            if unicodedata.category(character) == "Cs" or (
                unicodedata.category(character) == "Cc" and value not in {9, 10, 12, 13}
            ):
                return match[0]
            return character
        return html5.get(entity + ";", match[0])

    return re.sub(
        r"\\(["
        + re.escape(string.punctuation)
        + r"])|&(#(?:[0-9]{1,8}|[xX][0-9A-Fa-f]{1,8})|[A-Za-z][A-Za-z0-9]{0,31});",
        replacement,
        authored,
    )


def thought_destination(authored, *, qualified_brain=None):
    """An absent local ID means a validated foreign URI, never a missing target.

    The capability comes from original BRZ metadata or the selected raw API
    profile. Defaults preserve the independent historical compact-only oracle.
    """
    assert not any(ord(c) < 32 or ord(c) == 127 for c in authored), (
        "authored URI controls"
    )
    destination = markdown_destination(authored)
    match = re.fullmatch(
        r"brain://api\.thebrain\.com/([A-Za-z0-9_-]{22})/([A-Za-z0-9_-]{22})(?:/([^/?#\\]*))?",
        destination,
    )
    if match:
        assert qualified_brain is not None, (
            "qualified URI outside retained source profile"
        )
        assert not any(ord(c) < 32 or ord(c) == 127 for c in destination), (
            "decoded URI controls"
        )
        suffix = match[3] or ""
        assert not re.search(r"%(?![0-9A-Fa-f]{2})", suffix), (
            "malformed opaque percent data"
        )
        for byte in re.findall(r"%([0-9A-Fa-f]{2})", suffix):
            assert int(byte, 16) not in {*range(32), 127, 92}, (
                "unsafe direct percent byte"
            )
        identities = []
        for token in match.group(1, 2):
            raw = base64.b64decode(token + "==", altchars=b"-_", validate=True)
            assert (
                len(raw) == 16
                and base64.b64encode(raw, altchars=b"-_").decode().rstrip("=") == token
            ), "canonical GUID token"
            identities.append(str(UUID(bytes_le=raw)))
        href = quote(destination, safe="/:?#[]@!$&'()*+,;=-._~%")
        return ThoughtDestination(
            identities[1] if identities[0] == qualified_brain else None, href, True
        )
    spelling = authored[8:].split("/", 1)[0]
    assert re.fullmatch(r"[A-Za-z0-9_-]{22}", spelling), "unqualified thought URI"
    return ThoughtDestination(
        str(UUID(bytes_le=base64.urlsafe_b64decode(spelling + "=="))), authored, False
    )


def assert_no_omitted(values, tokens):
    """Screen admitted semantic fields with the existing single-pass policy."""
    for value in values:
        decoded = re.sub(r"%([0-9a-fA-F]{2})", lambda m: chr(int(m[1], 16)), value)
        decoded = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)), decoded)
        assert not any(
            token in candidate for candidate in (value, decoded) for token in tokens
        ), "unremoved excluded note association"
        assert not any(
            m[0].lower() in tokens
            for m in re.finditer(
                r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", decoded
            )
        ), "unremoved excluded note association"
