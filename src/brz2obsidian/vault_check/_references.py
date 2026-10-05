"""Resolve required targets using the complete inventory before role checks."""

import re
import unicodedata
from pathlib import PurePosixPath
from urllib.parse import unquote

from ._filesystem import UnsafePath, guard, read_failure
from .contracts import VaultCheckIssue

IMAGE_EXTENSIONS = {".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}


def _key(value):
    return unicodedata.normalize("NFC", value).casefold()


def target_path(reference, artifact, relative):
    target = reference[2:-2] if reference.startswith("[[") else reference
    target = target.split("|", 1)[0].split("#", 1)[0]
    if relative:
        target = unquote(target)
    if (
        not target
        or re.search(r'[\\:*?"<>\x00-\x1f\x7f]', target)
        or target.startswith("/")
    ):
        raise ValueError("Unsafe required reference")
    parts = list(PurePosixPath(artifact).parent.parts) if relative else []
    for part in target.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise ValueError("Required reference escapes the vault")
            parts.pop()
        else:
            if part.endswith((".", " ")) or re.fullmatch(
                r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.IGNORECASE
            ):
                raise ValueError("Unsafe Windows path component")
            parts.append(part)
    return "/".join(parts), relative or "/" in target


def resolve(root, files, reference, artifact, kind, property=None, relative=False):
    context = {"artifact": artifact, "property": property, "reference": reference}
    try:
        target, qualified = target_path(reference, artifact, relative)
        guard(root / target, root)
    except ValueError, UnsafePath:
        return None, VaultCheckIssue(
            code="unsafe_reference",
            **context,
            message="Required reference is not a contained vault path.",
            guidance="Use a vault-local path; Markdown images may use contained ../ paths.",
        )
    except OSError:
        return None, read_failure(artifact)
    names = {target}
    if kind in {"category", "provider"} and not target.lower().endswith(".md"):
        names.add(target + ".md")
    names = {_key(name) for name in names}
    candidates = tuple(
        sorted(
            name
            for name in files
            if _key(name if qualified else PurePosixPath(name).name) in names
        )
    )
    if len(candidates) > 1:
        return None, VaultCheckIssue(
            code="ambiguous_reference",
            **context,
            candidates=candidates,
            message="Required reference has multiple matching files.",
            guidance="Qualify the link with its intended vault path.",
        )
    missing_code = {
        "category": "invalid_category",
        "provider": "invalid_provider",
        "base": "missing_base",
        "image": "missing_image",
    }[kind]
    if not candidates:
        return None, VaultCheckIssue(
            code=missing_code,
            **context,
            message=f"Required {kind} target does not exist as a regular file.",
            guidance="Restore the intended file or edit the required reference.",
        )
    candidate = candidates[0]
    suffix = PurePosixPath(candidate).suffix.lower()
    try:
        guard(root / candidate, root)
        size = (root / candidate).stat().st_size
    except UnsafePath:
        return None, VaultCheckIssue(
            code="unsafe_reference",
            **context,
            message="Required target is a symbolic link or reparse path.",
            guidance="Use a regular file contained in the vault.",
        )
    except OSError:
        return None, read_failure(artifact)
    if (
        (kind in {"category", "provider"} and suffix != ".md")
        or (kind == "base" and suffix != ".base")
        or (kind == "image" and (suffix not in IMAGE_EXTENSIONS or size == 0))
    ):
        return None, VaultCheckIssue(
            code=missing_code,
            **context,
            message=f"Required {kind} target has the wrong file kind or is empty.",
            guidance="Use a category note, .base file or nonempty supported image as appropriate.",
        )
    return candidate, None
