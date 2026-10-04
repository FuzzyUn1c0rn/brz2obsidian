"""Keep exact authored/body assertions separate from newly generated metadata."""


def note_body(content):
    """Remove only the generated canonical core, never authored characters."""
    opening = b"---\n" if isinstance(content, bytes) else "---\n"
    ending = b"\n---\n\n" if isinstance(content, bytes) else "\n---\n\n"
    assert content.startswith(opening), "generated imported properties"
    metadata, body = content[len(opening) :].split(ending, 1)
    decoded = metadata.decode() if isinstance(metadata, bytes) else metadata
    assert {
        line.split(":", 1)[0]
        for line in decoded.splitlines()
        if line and not line.startswith(" ")
    } == {
        "categories",
        "appearance_category",
        "icon",
        "foreground_color",
        "background_color",
        "created",
        "updated",
        "tags",
        "aliases",
        "source_collection_id",
        "source_item_id",
    }, "canonical property core"
    return body
