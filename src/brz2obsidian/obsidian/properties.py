"""The small canonical property vocabulary for imported object notes."""

from collections import defaultdict

from ._frontmatter import frontmatter


def property_memberships(plan, targets):
    categories = defaultdict(list)
    for assignment in plan.analysis.snapshot.classification_assignments:
        path = targets[assignment.definition_key].relative_path
        categories[assignment.item_key].append("[[" + path + "]]")
    tokens = {t.tag_key: t.token for t in plan.tag_targets}
    tags = defaultdict(set)
    for membership in plan.tag_memberships:
        if membership.native:
            tags[membership.item_key].add(tokens[membership.tag_key])
    return categories, tags


def property_frontmatter(item, source_id, categories, native_tags, asset_paths):
    tags = set(native_tags)
    if item.role == "definition":
        tags.add("categories")
    dates = item.calendar_dates
    appearance = item.declared_appearance
    icon = appearance.icon_asset_id if appearance else None
    return frontmatter(
        {
            "categories": categories,
            "appearance_category": categories[0] if categories else None,
            "icon": "[[" + asset_paths[icon] + "]]"
            if icon and asset_paths[icon]
            else None,
            "created": dates.created if dates else None,
            "updated": dates.updated if dates else None,
            "tags": sorted(tags, key=str.casefold),
            "aliases": [],
            "source_collection_id": source_id,
            "source_item_id": item.original_identity,
        }
    )
