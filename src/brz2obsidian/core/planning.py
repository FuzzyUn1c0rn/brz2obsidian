"""Pure target selection and assignment."""

from pathlib import PurePosixPath

from brz2obsidian.contracts import Adaptation, Analysis, AssetTarget, MigrationPlan

from .items import assign_item_targets, select_fallbacks


def plan(analysis: Analysis) -> MigrationPlan:
    snapshot = analysis.snapshot
    targets = assign_item_targets(analysis)
    isolated, related_pairs = select_fallbacks(snapshot, targets)
    owners = {item.key: item.naming_seed[:8] for item in snapshot.items}
    asset_targets = tuple(
        AssetTarget(
            asset_id=asset.asset_id,
            relative_path=f"Attachments/{owners[asset.owner]}/{asset.original_name}.original",
        )
        for asset in snapshot.assets
    )
    counts = analysis.counts.model_copy(
        update={
            "planned_notes": sum(target.created for target in targets),
            "planned_assets": len(asset_targets),
        }
    )
    return MigrationPlan(
        analysis=analysis,
        source_identity=snapshot.identity,
        profile_id=analysis.policy.profile_id,
        profile_version=analysis.policy.profile_version,
        item_targets=tuple(targets),
        asset_targets=asset_targets,
        isolated_item_keys=isolated,
        uncreated_related_pairs=related_pairs,
        adaptations=tuple(
            Adaptation(
                kind="item_target",
                affected=t.item_key,
                description="Original title reserved as " + t.relative_path,
            )
            for t in targets
            if PurePosixPath(t.relative_path).stem != t.original_title
        ),
        issues=analysis.issues,
        counts=counts,
    )
