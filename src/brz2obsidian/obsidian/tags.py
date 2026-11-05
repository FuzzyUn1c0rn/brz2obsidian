"""Focused fallback tag navigation and retained membership evidence."""

from .relationships import note_link


def tag_listing(plan):
    if plan.tag_memberships_path is None:
        return ""
    targets = {t.item_key: t for t in plan.item_targets}
    items = {i.key: i for i in plan.analysis.snapshot.items}
    tokens = {t.tag_key: t.token for t in plan.tag_targets}
    text = "# Tag memberships\n\nExplicit nested source-tag facts, assignments on uncreated targets and source tags without assignments. Tokens are independent: a parent tag is not inferred on a child tag's members. Use native tag search for created assigned notes.\n\n"
    for tag in plan.tag_targets:
        memberships = [m for m in plan.tag_memberships if m.tag_key == tag.tag_key]
        nested = sorted({m.item_key for m in memberships if m.item_key in tokens})
        hidden = sorted(
            {
                m.item_key
                for m in memberships
                if not m.native and m.item_key not in tokens
            }
        )
        if memberships and not hidden and not nested:
            continue
        text += "## #" + tag.token + "\n\n"
        text += (
            "Source tag: " + note_link(targets[tag.tag_key], tag.original_name) + "\n\n"
        )
        for key in nested:
            text += (
                "- Nested source tag: "
                + note_link(targets[key], items[key].title)
                + " (#"
                + tokens[key]
                + ")"
                + ("; uncreated target" if not targets[key].created else "")
                + ".\n"
            )
        if nested:
            text += "\n"
        if hidden:
            text += (
                "".join(
                    "- " + note_link(targets[key], items[key].title) + "\n"
                    for key in hidden
                )
                + "\n"
            )
        elif not nested:
            text += "No source assignments.\n\n"
    return text.rstrip("\n") + "\n"


def tag_records(plan):
    tags = {t.tag_key: t for t in plan.tag_targets}
    targets = {t.item_key: t for t in plan.item_targets}
    relations = {r.key: r for r in plan.analysis.snapshot.relationships}
    return [
        dict(
            **m.model_dump(),
            tag_name=tags[m.tag_key].original_name,
            token=tags[m.tag_key].token,
            tag_original_identity=tags[m.tag_key].original_identity,
            tag_target=targets[m.tag_key].relative_path,
            item_target=targets[m.item_key].relative_path,
            evidence=relations[m.relationship_key].evidence,
            listing_path=plan.tag_memberships_path
            if not m.native or m.item_key in tags
            else None,
        )
        for m in plan.tag_memberships
    ]
