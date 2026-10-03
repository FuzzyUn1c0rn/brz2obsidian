"""Pure consistency checks over canonical facts and reviewed policy."""

from brz2obsidian.contracts import (
    Analysis,
    Counts,
    Issue,
    MigrationRefused,
    SourcePolicy,
    SourceSnapshot,
)


def analyze(snapshot: SourceSnapshot, policy: SourcePolicy) -> Analysis:
    def refuse(code, message):
        raise MigrationRefused(
            (
                Issue(
                    code=code,
                    phase="analysis",
                    message=message,
                    guidance="Correct the source or select a compatible reviewed source profile.",
                ),
            )
        )

    identity = snapshot.identity
    if (
        identity.module_id,
        identity.module_version,
        identity.format_version,
        snapshot.contract_version,
    ) != (
        policy.module_id,
        policy.module_version,
        policy.format_version,
        policy.contract_version,
    ):
        refuse(
            "unsupported_format",
            "Source identity and reviewed profile are incompatible",
        )
    items = {item.key: item for item in snapshot.items}
    if len(items) != len(snapshot.items):
        refuse("invalid_source", "Duplicate canonical item keys")
    if (
        snapshot.entry_key not in items
        or not items[snapshot.entry_key].live
        or items[snapshot.entry_key].role != "ordinary"
    ):
        refuse("invalid_entry", "A valid live ordinary entry item is required")
    documents = {document.key: document for document in snapshot.documents}
    assets = {asset.asset_id: asset for asset in snapshot.assets}
    if len(documents) != len(snapshot.documents) or len(assets) != len(snapshot.assets):
        refuse("invalid_source", "Duplicate canonical document or asset identity")
    for item in snapshot.items:
        if any(key not in documents for key in item.document_ids) or any(
            key not in assets for key in item.resource_ids
        ):
            refuse(
                "invalid_reference", "Item references an absent document or resource"
            )
        if any(documents[key].owner != item.key for key in item.document_ids) or any(
            assets[key].owner != item.key for key in item.resource_ids
        ):
            refuse("invalid_reference", "Item references another owner's content")
    for document in snapshot.documents:
        if document.owner not in items or document.original_asset_id not in assets:
            refuse("invalid_reference", "Document owner/original payload is invalid")
    for asset in snapshot.assets:
        if asset.owner not in items:
            refuse("invalid_reference", "Asset owner is invalid")
        if asset.availability == "present" and (
            asset.actual_length is None or asset.actual_sha256 is None
        ):
            refuse("invalid_source", "Present asset lacks actual byte inventory")
    for relation in snapshot.relationships:
        if relation.item_a not in items or relation.item_b not in items:
            refuse("invalid_reference", "Relationship endpoint is absent")
    entries = snapshot.accounting.entries
    if len({entry.identity for entry in entries}) != len(entries) or any(
        entry.disposition == "unresolved" or not entry.references for entry in entries
    ):
        refuse(
            "invalid_source",
            "Declared source accounting is duplicate, unresolved or incomplete",
        )
    if snapshot.findings:
        refuse("unsupported_feature", "Source findings require a reviewed disposition")
    counts = Counts(
        source_items=len(items),
        source_relationships=len(snapshot.relationships),
        present_assets=sum(
            asset.availability == "present" for asset in assets.values()
        ),
    )
    return Analysis(
        snapshot=snapshot, policy=policy, entry_key=snapshot.entry_key, counts=counts
    )
