"""Required native embeds and Markdown images in active Markdown contexts."""

import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from markdown_it import MarkdownIt

from ._references import IMAGE_EXTENSIONS

_NATIVE_EMBED = re.compile(r"!\[\[([^\[\]\r\n]+)\]\]")


def _native_embed(state, silent):
    match = _NATIVE_EMBED.match(state.src, state.pos)
    if not match:
        return False
    if not silent:
        state.push("vault_embed", "", 0).content = match[1]
    state.pos = match.end()
    return True


def required_references(body):
    parser = MarkdownIt("commonmark")
    # Native embeds bind their whole target before CommonMark emphasis can split it.
    parser.inline.ruler.before("image", "vault_embed", _native_embed)
    # Parse otherwise rejected schemes as syntax to diagnose them, never to open them.
    parser.validateLink = lambda reference: True
    for token in parser.parse(body):
        if token.type != "inline":
            continue
        for child in token.children or ():
            if child.type == "image":
                reference = child.attrGet("src")
                scheme = urlsplit(reference).scheme.lower()
                if scheme in {"http", "https", "data"}:
                    continue
                yield reference, "image", True
            elif child.type == "vault_embed":
                target = child.content.split("|", 1)[0].split("#", 1)[0]
                extension = PurePosixPath(target).suffix.lower()
                if extension == ".base":
                    yield "[[" + child.content + "]]", "base", False
                elif extension in IMAGE_EXTENSIONS:
                    yield "[[" + child.content + "]]", "image", False
