"""Native frontmatter and focused fallback tag navigation."""

import json

from .relationships import note_link


def tag_frontmatter(plan, item_key):
    tokens = {t.tag_key: t.token for t in plan.tag_targets}
    assigned = {
        tokens[m.tag_key]
        for m in plan.tag_memberships
        if m.item_key == item_key and m.native
    }
    item = next(i for i in plan.analysis.snapshot.items if i.key == item_key)
    if item.role == "definition":
        assigned.add("categories")
    assigned = sorted(assigned, key=str.casefold)
    return (
        "---\ntags:\n"
        + "".join(
            "  - " + json.dumps(token, ensure_ascii=False) + "\n" for token in assigned
        )
        + "---\n\n"
        if assigned
        else ""
    )


def tag_listing(plan):
    if plan.tag_memberships_path is None:
        return ""
    targets = {t.item_key: t for t in plan.item_targets}
    items = {i.key: i for i in plan.analysis.snapshot.items}
    text = "# Tag memberships\n\nAssignments on uncreated targets and source tags without assignments. Use native tag search for created assigned notes.\n\n"
    for tag in plan.tag_targets:
        memberships = [m for m in plan.tag_memberships if m.tag_key == tag.tag_key]
        hidden = sorted({m.item_key for m in memberships if not m.native})
        if memberships and not hidden:
            continue
        text += "## #" + tag.token + "\n\n"
        text += (
            "Source tag: " + note_link(targets[tag.tag_key], tag.original_name) + "\n\n"
        )
        if hidden:
            text += (
                "".join(
                    "- " + note_link(targets[key], items[key].title) + "\n"
                    for key in hidden
                )
                + "\n"
            )
        else:
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
            listing_path=None if m.native else plan.tag_memberships_path,
        )
        for m in plan.tag_memberships
    ]
