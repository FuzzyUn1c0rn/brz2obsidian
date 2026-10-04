"""Pure target selection and assignment."""

from pathlib import PurePosixPath

from brz2obsidian.contracts import Adaptation, Analysis, MigrationPlan

from .appearance import icon_snapshots
from .items import assign_item_targets, select_fallbacks
from .resources import assign_asset_targets, resource_owners
from .support import SUPPORT_NAMESPACE, support_artifacts
from .tags import assign_tags


def plan(analysis: Analysis) -> MigrationPlan:
    snapshot = analysis.snapshot
    targets = assign_item_targets(analysis, resource_owners(snapshot))
    isolated, related_pairs = select_fallbacks(snapshot, targets)
    asset_targets = assign_asset_targets(snapshot)
    created = {t.item_key for t in targets if t.created}
    snapshots = icon_snapshots(snapshot, created)
    definitions = {i.key for i in snapshot.items if i.role == "definition"}
    tag_targets, tag_memberships, listing_path = assign_tags(snapshot, targets)
    supporting = support_artifacts(bool(isolated or related_pairs), listing_path)
    tokens = {t.tag_key: t.token for t in tag_targets}
    targets = tuple(
        t.model_copy(update={"vault_tag_token": tokens.get(t.item_key)})
        for t in targets
    )
    counts = analysis.counts.model_copy(
        update={
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
    return MigrationPlan(
        analysis=analysis,
        source_identity=snapshot.identity,
        profile_id=analysis.policy.profile_id,
        profile_version=analysis.policy.profile_version,
        item_targets=tuple(targets),
        asset_targets=asset_targets,
        tag_targets=tag_targets,
        tag_memberships=tag_memberships,
        tag_memberships_path=listing_path,
        isolated_item_keys=isolated,
        uncreated_related_pairs=related_pairs,
        support_artifacts=supporting,
        icon_snapshots=snapshots,
        reserved_support_paths=tuple(
            a.relative_path for a in SUPPORT_NAMESPACE if a not in supporting
        ),
        adaptations=tuple(
            Adaptation(
                kind="category_dashboard",
                affected=key,
                description="Embedded native contextual Members and Gallery Bases discover linked memberships from this category after link-preserving renames.",
            )
            for key in sorted(created & definitions)
        )
        + (
            Adaptation(
                kind="categories_overview",
                affected=analysis.entry_key,
                description="Preserved Home with an added Categories overview entry; overview uses the Categories folder and native categories tag role guard.",
            ),
            Adaptation(
                kind="native_bases_configuration",
                affected=".obsidian/core-plugins.json",
                description="Enabled bundled Bases and required native navigation; preserved Home/bookmark settings and enabled link-preserving renames.",
            ),
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
                    else " from appearance category " + s.appearance_category_key + "."
                )
                + " Later category/property edits do not rewrite this body snapshot.",
            )
            for s in snapshots
            if s.effective_icon_asset_id is not None
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
        issues=analysis.issues,
        counts=counts,
    )
