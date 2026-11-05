"""Owned image validation and migration-time defaults over neutral facts."""

from brz2obsidian.contracts import IconSnapshot, Issue


def validate_appearance(snapshot, refuse):
    assets = {a.asset_id: a for a in snapshot.assets}
    missing_icons = {
        (g.owner, g.asset_id)
        for g in snapshot.source_gaps
        if g.role == "definition_icon"
    }
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
            or not (
                asset.availability == "present"
                and asset.actual_length
                or asset.availability == "absent"
                and item.role == "definition"
                and asset.role == "icon"
                and (item.key, asset.asset_id) in missing_icons
            )
        ):
            refuse(
                "invalid_reference",
                "Declared icon must be its owner's present local image or reviewed missing definition icon",
            )


def icon_lookup_paths(snapshot, created):
    items = {i.key: i for i in snapshot.items}
    available = {a.asset_id for a in snapshot.assets if a.availability == "present"}
    providers = {
        a.item_key: a.definition_key for a in snapshot.classification_assignments
    }

    def own_icon(item):
        icon = (
            item.declared_appearance.icon_asset_id if item.declared_appearance else None
        )
        return icon if icon in available else None

    paths = {}
    for start in sorted(created):
        key, visited, path = start, set(), []
        while key is not None and key not in visited:
            visited.add(key)
            path.append(key)
            if own_icon(items[key]):
                break
            key = providers.get(key)
        paths[start] = tuple(path)
    return paths


def native_icon_limits(snapshot, created):
    assignments = {a.item_key: a for a in snapshot.classification_assignments}
    return tuple(
        Issue(
            code="icon_lookup_depth",
            severity="warning",
            phase="planning",
            message="Icon lookup exceeds 8 links.",
            affected=path,
            evidence=tuple(
                dict.fromkeys(e for key in path[:-1] for e in assignments[key].evidence)
            ),
            guidance="Native dashboards check up to eight selected appearance-category links. Assign a nearer valid icon or change a selected provider, then close and reopen affected category dashboards and Categories overview. Migration-time body snapshots use the full finite chain.",
        )
        for path in icon_lookup_paths(snapshot, created).values()
        if len(path) > 9
    )


def icon_snapshots(snapshot, created):
    items = {i.key: i for i in snapshot.items}
    available = {a.asset_id for a in snapshot.assets if a.availability == "present"}
    providers = {
        a.item_key: a.definition_key for a in snapshot.classification_assignments
    }
    paths = icon_lookup_paths(snapshot, created)

    def own_icon(key):
        declaration = items[key].declared_appearance
        icon = declaration.icon_asset_id if declaration else None
        return icon if icon in available else None

    return tuple(
        IconSnapshot(
            item_key=key,
            explicit_icon_asset_id=own_icon(key),
            appearance_category_key=providers.get(key),
            effective_icon_asset_id=own_icon(paths[key][-1]),
        )
        for key in sorted(created)
    )
