"""Pure target selection and assignment."""

import re
import unicodedata

from brz2obsidian.contracts import Analysis, AssetTarget, ItemTarget, MigrationPlan


def _stem(title):
    value = (
        unicodedata.normalize("NFC", title)
        .replace(":", " - ")
        .replace("[", "(")
        .replace("]", ")")
    )
    value = re.sub(r'[<>"/\\|?*#^%\x00-\x1f]', " ", value)
    value = " ".join(value.split()).strip(" .") or "Untitled"
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", value, re.IGNORECASE):
        value = "Note - " + value
    while len(value.encode("utf-16-le")) // 2 > 100:
        value = value[:-1]
    return value.rstrip(" .")


def plan(analysis: Analysis) -> MigrationPlan:
    snapshot = analysis.snapshot
    targets = []
    docs = {document.key: document for document in snapshot.documents}
    stems = {item.key: _stem(item.title) for item in snapshot.items}
    for item in sorted(snapshot.items, key=lambda item: item.key):
        stem = stems[item.key]
        if sum(
            value.casefold() == stem.casefold() for value in stems.values()
        ) > 1 or stem.casefold() in {
            "migration report",
            "tag memberships",
            "uncreated targets",
        }:
            stem += " — " + item.naming_seed[:8]
        is_home = item.key == analysis.entry_key
        if is_home:
            stem = "Home — " + stem
        content = any(docs[key].text.strip() for key in item.document_ids)
        created = is_home or content
        reasons = ("home",) if is_home else (("content",) if content else ())
        targets.append(
            ItemTarget(
                item_key=item.key,
                original_identity=item.original_identity,
                original_title=item.title,
                relative_path=("" if is_home else "Notes/") + stem + ".md",
                created=created,
                creation_reasons=reasons,
            )
        )
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
        issues=analysis.issues,
        counts=counts,
    )
