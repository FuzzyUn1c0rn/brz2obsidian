"""The small canonical property vocabulary for imported object notes."""

from ._frontmatter import frontmatter


def imported_properties(plan, item):
    targets = {t.item_key: t for t in plan.item_targets}
    categories = [
        "[[" + targets[a.definition_key].relative_path + "]]"
        for a in plan.analysis.snapshot.classification_assignments
        if a.item_key == item.key
    ]
    tokens = {t.tag_key: t.token for t in plan.tag_targets}
    tags = {
        tokens[m.tag_key]
        for m in plan.tag_memberships
        if m.item_key == item.key and m.native
    }
    if item.role == "definition":
        tags.add("categories")
    dates = item.calendar_dates
    appearance = item.declared_appearance
    asset_targets = {t.asset_id: t.relative_path for t in plan.asset_targets}
    icon = appearance.icon_asset_id if appearance else None
    return {
        "categories": categories,
        "appearance_category": categories[0] if categories else None,
        "icon": "[[" + asset_targets[icon] + "]]" if icon else None,
        "created": dates.created if dates else None,
        "updated": dates.updated if dates else None,
        "tags": sorted(tags, key=str.casefold),
        "aliases": [],
        "source_collection_id": plan.source_identity.source_id,
        "source_item_id": item.original_identity,
    }


def property_frontmatter(plan, item):
    return frontmatter(imported_properties(plan, item))
