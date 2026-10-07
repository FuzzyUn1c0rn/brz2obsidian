"""Actionable absence evidence without inventing recovery or source launch links."""

import re

from .relationships import note_link


def plain(value):
    return (
        re.sub(r"([\\`*_{}\[\]<>#])", r"\\\1", str(value))
        .replace("\r", " ")
        .replace("\n", " ")
    )


def gap_report(plan):
    snapshot = plan.analysis.snapshot
    findings = [f for f in snapshot.findings if f.kind == "known_absent_payload"]
    if not findings:
        return ""
    items = {i.key: i for i in snapshot.items}
    assets = {a.asset_id: a for a in snapshot.assets}
    targets = {t.item_key: t for t in plan.item_targets}
    paths = {t.asset_id: t.relative_path for t in plan.asset_targets}
    gaps = {g.gap.asset_id: g for g in plan.source_gaps}
    text = "\n## Source-gap evidence and optional repair checklist\n\n"
    text += "Conversion used archived material only. Optionally locate the thought by title/ID, restore missing content in the source and re-export into a fresh vault. Unknown prose, captions and layout were not recovered.\n\n"
    if plan.source_gaps:
        text += f"Source fingerprint: {snapshot.identity.source_sha256}; scoped digest: {snapshot.identity.snapshot_digest}; collection: {plain(snapshot.collection_title)} ({plain(snapshot.identity.source_id)}).\n\n"
    else:
        text += f"Collection: {plain(snapshot.collection_title)} ({plain(snapshot.identity.source_id)}); fingerprint and scoped digest are recorded in migration-record.json.\n\n"
    for finding in sorted(findings, key=lambda f: (f.rule_id, f.affected)):
        for asset_id in finding.affected:
            asset = assets.get(asset_id)
            if asset is None or asset.availability != "absent":
                continue
            item = items[asset.owner]
            target = targets.get(asset.owner)
            if target and target.created:
                owner = note_link(target, item.title)
            elif target:
                owner = (
                    plain(item.title)
                    + " (uncreated target: "
                    + plain(target.relative_path)
                    + ")"
                )
            else:
                owner = plain(item.title) + " (no vault-note target)"
            diagnostic = gaps.get(asset_id)
            role = diagnostic.gap.role if diagnostic else asset.role
            outcome = (
                diagnostic.outcome if diagnostic else "metadata retained; bytes absent"
            )
            text += f"- [ ] {owner}; thought ID {plain(asset.owner)}; attachment {plain(asset_id)}; role {role}; outcome {outcome}.\n"
            text += (
                "  Declaration and physical absence: "
                + plain(finding.observed_json)
                + "\n"
            )
            if diagnostic:
                if diagnostic.provider_key:
                    text += "  Provider: " + owner + ".\n"
                    text += f"  Affected included members ({len(diagnostic.affected_member_keys)}):\n"
                    for key in diagnostic.affected_member_keys:
                        member = items[key]
                        text += (
                            "  - "
                            + note_link(targets[key], member.title)
                            + "; thought ID "
                            + plain(key)
                            + "\n"
                        )
                for image_id in diagnostic.image_asset_ids:
                    text += (
                        "  - Image "
                        + plain(image_id)
                        + ": [["
                        + paths[image_id]
                        + "]]\n"
                    )
    return text
