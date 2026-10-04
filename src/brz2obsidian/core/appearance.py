"""Owned image validation and migration-time defaults over neutral facts."""

from brz2obsidian.contracts import IconSnapshot


def validate_appearance(snapshot, refuse):
    assets = {a.asset_id: a for a in snapshot.assets}
    for item in snapshot.items:
        declaration = item.declared_appearance
        if declaration is None or declaration.icon_asset_id is None:
            continue
        asset = assets.get(declaration.icon_asset_id)
        if (
            asset is None
            or asset.owner != item.key
            or asset.asset_id not in item.resource_ids
            or asset.role not in {"icon", "image"}
            or asset.availability != "present"
            or not asset.actual_length
        ):
            refuse(
                "invalid_reference",
                "Declared icon must be its owner's present local image",
            )


def icon_snapshots(snapshot, created):
    items = {i.key: i for i in snapshot.items}
    providers = {
        a.item_key: a.definition_key for a in snapshot.classification_assignments
    }

    def own_icon(item):
        return (
            item.declared_appearance.icon_asset_id if item.declared_appearance else None
        )

    return tuple(
        IconSnapshot(
            item_key=key,
            explicit_icon_asset_id=own_icon(items[key]),
            appearance_category_key=providers.get(key),
            effective_icon_asset_id=own_icon(items[key])
            or (own_icon(items[providers[key]]) if key in providers else None),
        )
        for key in sorted(created)
    )
