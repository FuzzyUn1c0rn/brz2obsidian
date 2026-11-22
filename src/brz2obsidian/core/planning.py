"""Pure target selection and assignment."""

from pathlib import PurePosixPath

from brz2obsidian.contracts import (
    Adaptation,
    Analysis,
    ImportLinkConnection,
    MigrationPlan,
)

from .appearance import icon_snapshots, native_icon_limits
from .import_categories import checked_choices, view_artifacts
from .import_placement import (
    import_name_key,
    scoped_support_paths,
    validate_import_location,
)
from .items import assign_item_targets, select_fallbacks
from .resources import assign_asset_targets, resource_owners
from .source_gaps import source_gap_targets
from .support import SUPPORT_NAMESPACE, support_artifacts
from .tags import assign_tags, scoped_tags


def plan(
    analysis: Analysis,
    *,
    output_format: int = 8,
    import_location: str | None = None,
    reserved_names: tuple[str, ...] = (),
    import_link_connections: tuple[ImportLinkConnection, ...] = (),
    existing_vault_tags: tuple[str, ...] = (),
    tag_reuse: tuple[tuple[str, str], ...] = (),
    remembered_tags=(),
    remembered_item_paths=(),
    category_choices=(),
) -> MigrationPlan:
    if import_location is not None:
        import_location = validate_import_location(import_location)
    reserved = frozenset(import_name_key(name) for name in reserved_names)
    retained_paths = _remembered_paths(import_location, remembered_item_paths)
    snapshot = analysis.snapshot
    category_choices = checked_choices(snapshot, import_location, category_choices)
    shared = {row.source_identity for row in category_choices if row.destination_path}
    targets = assign_item_targets(
        analysis,
        resource_owners(snapshot),
        output_format=output_format,
        import_location=import_location,
        reserved_names=reserved
        | {import_name_key(path) for path in retained_paths.values()},
        source_references=shared,
    )
    targets = tuple(
        row.model_copy(
            update={
                "relative_path": retained_paths.get(
                    row.original_identity, row.relative_path
                )
            }
        )
        for row in targets
    )
    isolated, related_pairs = select_fallbacks(snapshot, targets)
    asset_targets = assign_asset_targets(
        snapshot, import_location=import_location, reserved_names=reserved
    )
    created = {t.item_key for t in targets if t.created}
    snapshots = icon_snapshots(snapshot, created)
    definitions = {i.key for i in snapshot.items if i.role == "definition"}
    tag_targets, tag_memberships, listing_path = assign_tags(snapshot, targets)
    if import_location is not None:
        tag_targets = scoped_tags(
            snapshot, tag_targets, existing_vault_tags, tag_reuse, remembered_tags
        )
    supporting = support_artifacts(
        bool(isolated or related_pairs),
        listing_path,
        tuple(t for t in targets if t.item_key in definitions),
    ) + view_artifacts(snapshot, targets, category_choices)
    reserved_support = tuple(a for a in SUPPORT_NAMESPACE if a not in supporting)
    scoped_paths = {}
    if import_location is not None:
        occupied = set(reserved)
        occupied.update(import_name_key(row.relative_path) for row in targets)
        occupied.update(
            import_name_key(row.relative_path)
            for row in asset_targets
            if row.relative_path is not None
        )
        scoped_paths = scoped_support_paths(
            import_location, supporting + reserved_support, occupied
        )
        supporting = _scoped_support(supporting, scoped_paths)
        reserved_support = _scoped_support(reserved_support, scoped_paths)
        listing_path = scoped_paths.get(listing_path)
    tokens = {t.tag_key: t.token for t in tag_targets}
    targets = tuple(
        t.model_copy(update={"vault_tag_token": tokens.get(t.item_key)})
        for t in targets
    )
    gaps, presentations = source_gap_targets(snapshot, targets, asset_targets)
    counts = analysis.counts.model_copy(
        update={
            "planned_generated_embeds": sum(len(p.image_paths) for p in presentations),
            "planned_notes": sum(target.created for target in targets),
            "planned_category_notes": len(created & definitions),
            "planned_support_files": len(supporting),
            "planned_assets": sum(
                asset.availability == "present" for asset in snapshot.assets
            ),
            "planned_references": sum(
                len(d.references) for d in snapshot.documents if d.owner in created
            ),
            "source_tags": len(tag_targets),
            "tag_memberships": len(tag_memberships),
            "native_tag_memberships": sum(m.native for m in tag_memberships),
            "uncreated_tag_memberships": sum(not m.native for m in tag_memberships),
            "created_tag_items": sum(
                t.created for t in targets if t.item_key in tokens
            ),
            "uncreated_tag_items": sum(
                not t.created for t in targets if t.item_key in tokens
            ),
        }
    )
    migration_plan = MigrationPlan(
        analysis=analysis,
        source_identity=snapshot.identity,
        profile_id=analysis.policy.profile_id,
        profile_version=analysis.policy.profile_version,
        output_format=output_format,
        item_targets=tuple(targets),
        asset_targets=asset_targets,
        import_location=import_location,
        reserved_import_names=tuple(sorted(reserved)),
        import_link_connections=import_link_connections,
        import_support_paths=scoped_paths,
        existing_vault_tags=existing_vault_tags,
        tag_reuse=tag_reuse,
        remembered_tags=remembered_tags,
        remembered_item_paths=remembered_item_paths,
        category_choices=category_choices,
        tag_targets=tag_targets,
        tag_memberships=tag_memberships,
        tag_memberships_path=listing_path,
        isolated_item_keys=isolated,
        uncreated_related_pairs=related_pairs,
        support_artifacts=supporting,
        icon_snapshots=snapshots,
        source_gaps=gaps,
        generated_presentations=presentations,
        reserved_support_paths=tuple(a.relative_path for a in reserved_support),
        adaptations=tuple(
            Adaptation(
                kind="image_presentation",
                affected=f"reference:{document.key}:{index}",
                document_key=document.key,
                owner=document.owner,
                evidence=document.evidence,
                description="Original declaration "
                + reference.presentation_normalization.declaration
                + " normalized to ordinary responsive inline Markdown presentation; exact percentage sizing is not reproduced.",
            )
            for document in sorted(snapshot.documents, key=lambda d: d.key)
            for index, reference in enumerate(document.references)
            if reference.presentation_normalization
        )
        + tuple(
            Adaptation(
                kind=edit.kind,
                affected=f"text:{document.key}:{index}",
                document_key=document.key,
                owner=document.owner,
                evidence=document.evidence,
                text_edit=edit,
                description="Exact scoped text normalization for editable Markdown; before/after text, kind and coordinate bases remain in document evidence.",
            )
            for document in sorted(snapshot.documents, key=lambda d: d.key)
            for index, edit in enumerate(document.text_adaptations)
        )
        + tuple(
            Adaptation(
                kind="category_dashboard",
                affected=key,
                description="Parents/Children navigation immediately follows the category title when present; native contextual Members and Gallery Bases follow that navigation, before retained source content, without a generated introductory icon image; linked membership discovery survives link-preserving renames.",
            )
            for key in sorted(created & definitions)
        )
        + (
            Adaptation(
                kind="native_templates_configuration",
                affected=".obsidian/templates.json",
                description="Enabled bundled Templates for manual selection, Templates folder and ISO insertion dates; configured canonical native property types without unrelated reference toggles.",
            ),
            Adaptation(
                kind="vault_maintenance_guide",
                affected="Vault guide.md",
                description="Documented new-object templates, direct existing-note membership edits, explicit update dates and category/member/Base starters without a custom registry.",
            ),
            Adaptation(
                kind="categories_overview",
                affected=analysis.entry_key,
                description=(
                    "Added the Categories overview entry to the scoped Home."
                    if import_location is not None
                    else "Preserved Home with an added Categories overview entry; overview uses the Categories folder and native categories tag role guard."
                ),
            ),
            Adaptation(
                kind="native_bases_configuration",
                affected=".obsidian/core-plugins.json",
                description="Enabled bundled Bases and required native navigation; preserved Home/bookmark settings and enabled link-preserving renames.",
            ),
        )
        + tuple(
            Adaptation(
                kind="category_template",
                affected=key,
                description="Full native new-note template initializes linked category membership/provider and insertion-day dates, with blank overrides and no imported identities.",
            )
            for key in sorted(created & definitions)
        )
        + tuple(
            Adaptation(
                kind="canonical_properties",
                affected=key,
                description="Generated canonical linked properties and paired original identities; no prose-derived aliases or semantic fields.",
            )
            for key in sorted(created)
        )
        + tuple(
            Adaptation(
                kind="source_calendar_dates",
                affected=item.key,
                description="Creation/overall-modification calendar components without timezone conversion; full source timestamps remain in item evidence and migration time remains separate.",
            )
            for item in sorted(snapshot.items, key=lambda i: i.key)
            if item.key in created
            and item.calendar_dates
            and (item.calendar_dates.created or item.calendar_dates.updated)
        )
        + tuple(
            Adaptation(
                kind="declared_appearance",
                affected=item.key,
                description="Owned icon and normalized declared colours remain separate from category defaults; original encoding and opaque tokens remain in item evidence.",
            )
            for item in sorted(snapshot.items, key=lambda i: i.key)
            if item.key in created
            and item.declared_appearance
            and any(item.declared_appearance.model_dump().values())
        )
        + tuple(
            Adaptation(
                kind="body_icon_snapshot",
                affected=s.item_key,
                description="Editable migration-time image reference to "
                + s.effective_icon_asset_id
                + (
                    " from its owned icon."
                    if s.explicit_icon_asset_id
                    else " through the selected appearance-category chain starting at "
                    + s.appearance_category_key
                    + "."
                )
                + " Later category/property edits do not rewrite this body snapshot.",
            )
            for s in snapshots
            if s.effective_icon_asset_id is not None and s.item_key not in definitions
        )
        + tuple(
            Adaptation(
                kind="item_target",
                affected=t.item_key,
                description="Original title reserved as " + t.relative_path,
            )
            for t in targets
            if PurePosixPath(t.relative_path).stem != t.original_title
        )
        + tuple(
            Adaptation(
                kind="relationship_presentation",
                affected=r.key,
                description="Simple "
                + ("Parents/Children" if r.kind == "hierarchy" else "Related")
                + " links; original source arrow and visibility details remain in evidence.",
            )
            for r in snapshot.relationships
            if r.kind in {"hierarchy", "related"}
        )
        + tuple(
            Adaptation(
                kind=reference.kind + "_reference",
                affected=f"reference:{document.key}:{index}",
                description="Inline source reference resolves to canonical "
                + reference.target
                + "; original display and syntax remain in document evidence.",
            )
            for document in sorted(snapshot.documents, key=lambda d: d.key)
            for index, reference in enumerate(document.references)
            if document.owner in created
        )
        + tuple(
            Adaptation(
                kind="video_embed",
                affected=asset.asset_id,
                description="Native "
                + asset.video_presentation.provider
                + " embed derived from validated presentation facts: "
                + asset.video_presentation.embed_uri
                + ". The exact original external URI remains the resource link; archived HTML remains source evidence.",
            )
            for asset in sorted(snapshot.assets, key=lambda a: a.asset_id)
            if asset.video_presentation
        )
        + tuple(
            Adaptation(
                kind="video_timing",
                affected=asset.asset_id,
                description=f"Native video start at {asset.video_presentation.start_seconds} seconds from validated source URL timing; original metadata remains independent evidence.",
            )
            for asset in sorted(snapshot.assets, key=lambda a: a.asset_id)
            if asset.video_presentation and asset.video_presentation.start_seconds
        ),
        issues=analysis.issues + native_icon_limits(snapshot, created),
        counts=counts,
    )
    if import_location is None:
        return migration_plan
    return migration_plan.model_copy(
        update={
            "adaptations": tuple(
                row
                for row in migration_plan.adaptations
                if row.kind
                not in ("native_templates_configuration", "native_bases_configuration")
            ),
        }
    )


def _remembered_paths(location, remembered):
    paths = dict(remembered)
    if (
        len(paths) != len(remembered)
        or len({path.casefold() for path in paths.values()}) != len(paths)
        or any(
            location is None
            or not path.startswith(location + "/")
            or not path.casefold().endswith(".md")
            for path in paths.values()
        )
    ):
        raise ValueError("Retained item paths do not uniquely belong to the collection")
    for path in paths.values():
        for part in path.split("/"):
            validate_import_location(part)
    return paths


def _scoped_support(artifacts, paths):
    return tuple(
        artifact.model_copy(update={"relative_path": paths[artifact.relative_path]})
        for artifact in artifacts
        if artifact.relative_path in paths
    )
