"""Independent URI facts from authored Markdown, with explicit source namespace."""

import base64
import html
import re
import string
from dataclasses import dataclass
from urllib.parse import quote
from uuid import UUID


@dataclass(frozen=True)
class ThoughtDestination:
    local_id: str | None
    source_target: str
    qualified: bool


def markdown_destination(authored):
    return html.unescape(
        re.sub(r"\\([" + re.escape(string.punctuation) + r"])", r"\1", authored)
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
