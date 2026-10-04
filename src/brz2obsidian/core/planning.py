"""Pure target selection and assignment."""

from pathlib import PurePosixPath

from brz2obsidian.contracts import Adaptation, Analysis, MigrationPlan

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
        reserved_support_paths=tuple(
            a.relative_path for a in SUPPORT_NAMESPACE if a not in supporting
        ),
        adaptations=tuple(
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
        ),
        issues=analysis.issues,
        counts=counts,
    )
