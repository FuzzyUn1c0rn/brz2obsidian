"""Source-neutral absence joins and generated display obligations."""

import re

from brz2obsidian.contracts import GeneratedPresentationTarget, SourceGapDiagnostic

from .appearance import icon_lookup_paths, icon_snapshots


def validate_source_gaps(snapshot, policy, refuse):
    items = {i.key: i for i in snapshot.items}
    assets = {a.asset_id: a for a in snapshot.assets}
    dispositions = {d.rule_id: d for d in policy.finding_dispositions}
    gaps = {}
    owners = set()
    for gap in snapshot.source_gaps:
        asset = assets.get(gap.asset_id)
        item = items.get(gap.owner)
        disposition = dispositions.get(gap.rule_id)
        findings = [
            f
            for f in snapshot.findings
            if f.rule_id == gap.rule_id and f.affected == (gap.asset_id,)
        ]
        if (
            gap.asset_id in gaps
            or (gap.owner, gap.role) in owners
            or asset is None
            or item is None
            or not item.live
            or asset.owner != gap.owner
            or asset.availability != "absent"
            or asset.actual_length is not None
            or asset.actual_sha256 is not None
            or asset.external_uri is not None
            or asset.role
            != ("icon" if gap.role == "definition_icon" else "note_original")
            or item.role
            != ("ordinary" if gap.role == "ordinary_note" else "definition")
            or gap.role == "definition_icon"
            and (
                gap.asset_id not in item.resource_ids
                or item.declared_appearance is None
                or item.declared_appearance.icon_asset_id != gap.asset_id
            )
            or disposition is None
            or disposition.disposition != "warning"
            or not disposition.permits_absent_payload
            or len(findings) != 1
            or findings[0].kind != disposition.kind
            or not gap.evidence
            or gap.evidence != findings[0].evidence
            or not set(asset.evidence) <= set(gap.evidence)
        ):
            refuse(
                "invalid_reference",
                "Source gap lacks consistent owner, absent asset and reviewed finding joins",
            )
        if gap.role.endswith("note") and any(
            d.owner == gap.owner for d in snapshot.documents
        ):
            refuse(
                "invalid_reference", "Absent note conflicts with a supplied document"
            )
        gaps[gap.asset_id] = gap
        owners.add((gap.owner, gap.role))
    presentations = set()
    for presentation in snapshot.generated_presentations:
        gap = gaps.get(presentation.source_gap_asset_id)
        expected = tuple(
            sorted(
                a.asset_id
                for a in snapshot.assets
                if a.owner == presentation.owner and a.role == "image"
            )
        )
        if (
            gap is None
            or gap.role != "ordinary_note"
            or gap.owner != presentation.owner
            or gap.asset_id in presentations
            or not expected
            or presentation.image_asset_ids != expected
        ):
            refuse(
                "invalid_reference",
                "Generated presentation lacks complete unique canonical owned-image joins",
            )
        for key in expected:
            asset = assets[key]
            if (
                asset.availability != "present"
                or type(asset.actual_length) is not int
                or asset.actual_length <= 0
                or not asset.actual_sha256
                or re.fullmatch(r"[0-9a-f]{64}", asset.actual_sha256) is None
                or not set(asset.evidence) <= set(gap.evidence)
            ):
                refuse(
                    "invalid_reference",
                    "Generated image lacks present measured inventory and gap evidence",
                )
        presentations.add(gap.asset_id)
    if any(
        g.role == "ordinary_note" and g.asset_id not in presentations
        for g in gaps.values()
    ):
        refuse(
            "invalid_reference",
            "Absent ordinary note lacks a generated image presentation",
        )
    if any(
        a.availability == "absent"
        and a.role in {"note_original", "icon"}
        and a.asset_id not in gaps
        for a in snapshot.assets
    ):
        refuse("invalid_reference", "Absent note or icon lacks a source gap")


def source_gap_targets(snapshot, item_targets, asset_targets):
    targets = {t.item_key: t for t in item_targets}
    paths = {t.asset_id: t.relative_path for t in asset_targets}
    presentations = tuple(
        GeneratedPresentationTarget(
            presentation=p,
            note_path=targets[p.owner].relative_path,
            image_paths=tuple(paths[key] for key in p.image_asset_ids),
        )
        for p in snapshot.generated_presentations
    )
    images = {
        p.presentation.source_gap_asset_id: p.presentation.image_asset_ids
        for p in presentations
    }
    selections = icon_snapshots(
        snapshot, {t.item_key for t in item_targets if t.created}
    )
    lookup_paths = icon_lookup_paths(snapshot, {s.item_key for s in selections})
    effective_icons = {s.item_key: s.effective_icon_asset_id for s in selections}
    images.update(
        (g.asset_id, (effective_icons[g.owner],))
        for g in snapshot.source_gaps
        if g.role == "definition_icon" and effective_icons.get(g.owner) is not None
    )
    diagnostics = tuple(
        SourceGapDiagnostic(
            gap=g,
            owner_target=targets[g.owner].relative_path,
            owner_created=targets[g.owner].created,
            outcome="image_fallback"
            if g.asset_id in images
            else "neutral_icon"
            if g.role == "definition_icon"
            else "unknown_note",
            provider_key=g.owner if g.role == "definition_icon" else None,
            affected_member_keys=tuple(
                sorted(
                    s.item_key
                    for s in selections
                    if g.role == "definition_icon"
                    and s.item_key != g.owner
                    and g.owner in lookup_paths[s.item_key]
                )
            ),
            image_asset_ids=images.get(g.asset_id, ()),
        )
        for g in snapshot.source_gaps
    )
    return diagnostics, presentations


def source_gap_issues(snapshot, issues):
    """Describe the actual planned fallback, retaining original finding evidence."""
    gaps = {
        (g.rule_id, (g.asset_id,)): g
        for g in snapshot.source_gaps
        if g.role == "definition_icon"
    }
    available = {
        s.item_key: s.effective_icon_asset_id
        for s in icon_snapshots(snapshot, {g.owner for g in gaps.values()})
    }
    observed = {(f.rule_id, f.affected): f.observed_json for f in snapshot.findings}
    result = []
    for issue in issues:
        key = issue.rule_id, issue.affected
        gap = gaps.get(key)
        if gap is not None:
            outcome = (
                "a farther selected appearance-category icon is available for migration-time lookup."
                if available[gap.owner] is not None
                else "no farther selected appearance-category icon is available; affected migration-time appearance is neutral."
            )
            issue = issue.model_copy(
                update={
                    "message": "Source category icon is absent; "
                    + outcome
                    + " Observed: "
                    + observed[key]
                }
            )
        result.append(issue)
    return tuple(result)
