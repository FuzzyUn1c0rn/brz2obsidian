"""Keep appended material outside trailing authored Markdown blocks."""

from markdown_it import MarkdownIt

from brz2obsidian.contracts import Issue, MigrationRefused


def append_boundary(text):
    """Return generated closing syntax without modifying any authored characters."""
    parser = MarkdownIt("commonmark")

    def probe(boundary):
        prefix = (text + boundary + "\n\n").replace("\r\n", "\n").replace("\r", "\n")
        line = prefix.count("\n")
        tokens = parser.parse(prefix + "## Appended material\n")
        visible = any(
            token.type == "heading_open" and token.level == 0 and token.map[0] == line
            for token in tokens
        )
        return visible, tokens, line

    visible, tokens, line = probe("")
    if visible:
        return ""
    for token in reversed(tokens):
        if token.map is None or not token.map[0] <= line < token.map[1]:
            continue
        if token.type == "fence":
            boundary = "\n\n" + token.markup + "\n"
        elif token.type == "html_block" and token.content.lstrip().startswith("<!--"):
            boundary = "\n\n-->\n"
        else:
            break
        if probe(boundary)[0]:
            return boundary
        break
    raise MigrationRefused(
        (
            Issue(
                code="unsupported_feature",
                phase="rendering",
                message="A trailing Markdown block prevents safely appending note content or navigation",
                guidance="Close the trailing Markdown block in the source note and retry.",
            ),
        )
    )
