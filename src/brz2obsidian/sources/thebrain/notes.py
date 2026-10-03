"""Exact-source reference tracing over Markdown parser-recognized links."""

from hashlib import sha256

from markdown_it import MarkdownIt
from markdown_it.rules_inline import image, link

from brz2obsidian.contracts import Issue, MigrationRefused, ReferenceSpan


def trace_note_references(text: str) -> tuple[ReferenceSpan, ...]:
    """Return exact spans for active inline local links; code is excluded.

    Parser rules identify syntax; per-block provenance maps inline offsets
    back to the original text, retaining all original newline spelling.
    No whole-document reconstruction or regex link discovery is used.
    """
    parser = MarkdownIt("commonmark")
    # TheBrain's observed scheme is a local protocol, accepted by Markdown.
    hits = []

    def instrument(rule, kind):
        def run(state, silent):
            begin, count = state.pos, len(state.tokens)
            success = rule(state, silent)
            if success and not silent:
                new = state.tokens[count:]
                token = next(
                    (
                        t
                        for t in new
                        if t.type == ("image" if kind == "image" else "link_open")
                    ),
                    None,
                )
                if token:
                    target = token.attrGet("src" if kind == "image" else "href")
                    if target and target.startswith(("brain://", ".data/")):
                        display = (
                            token.content
                            if kind == "image"
                            else "".join(
                                part.content
                                for part in new[new.index(token) + 1 :]
                                if part.type in {"text", "code_inline", "image"}
                            )
                        )
                        hits.append(
                            (state.src, begin, state.pos, kind, target, display)
                        )
            return success

        return run

    parser.inline.ruler.at("link", instrument(link, "item"))
    parser.inline.ruler.at("image", instrument(image, "image"))
    # Parse blocks first, then inline individually, preserving token ownership.
    env = {}
    tokens = []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    parser.block.parse(normalized, parser, env, tokens)
    raw_lines = text.splitlines(keepends=True)
    starts = []
    offset = 0
    for line_text in raw_lines:
        starts.append(offset)
        offset += len(line_text)
    result = []
    digest = sha256(text.encode("utf-8")).hexdigest()

    def check_html(token):
        if token.type in {"html_inline", "html_block"} and any(
            marker in token.content for marker in ("brain://", ".data/")
        ):
            raise MigrationRefused(
                (
                    Issue(
                        code="unsupported_feature",
                        phase="source",
                        message="HTML source-local references are not supported",
                        guidance="Use supported inline Markdown local references or investigate this source feature.",
                    ),
                )
            )

    for block in tokens:
        check_html(block)
        if block.type != "inline":
            continue
        hits.clear()
        inline_tokens = []
        parser.inline.parse(block.content, parser, env, inline_tokens)
        for token in inline_tokens:
            check_html(token)
        provenance = []
        source_line = block.map[0]
        for inline_line in block.content.split("\n"):
            while source_line < block.map[1]:
                raw = raw_lines[source_line].rstrip("\r\n")
                col = raw.find(inline_line)
                if col >= 0:
                    provenance.extend(
                        starts[source_line] + col + n for n in range(len(inline_line))
                    )
                    provenance.append(starts[source_line] + len(raw))
                    source_line += 1
                    break
                source_line += 1
            else:
                raise ValueError("Cannot establish exact Markdown source provenance")
        for _, begin, end, kind, target, display in hits:
            start, stop = provenance[begin], provenance[end - 1] + 1
            original = text[start:stop]
            if (
                original.replace("\r\n", "\n").replace("\r", "\n")
                != block.content[begin:end]
            ):
                raise ValueError("Markdown reference provenance is not exact")
            result.append(
                ReferenceSpan(
                    start=start,
                    end=stop,
                    expected_original=original,
                    kind=kind,
                    target=target,
                    display_text=display,
                    document_digest=digest,
                )
            )
    return tuple(sorted(result, key=lambda span: span.start))
