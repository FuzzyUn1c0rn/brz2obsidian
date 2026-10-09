"""Pure consistency checks over canonical facts and reviewed policy."""

from brz2obsidian.contracts import (
    Analysis,
    Counts,
    Issue,
    MigrationRefused,
    SourcePolicy,
    SourceSnapshot,
)

from .appearance import validate_appearance
from .classifications import validate_classifications
from .references import validate_references
from .source_gaps import validate_source_gaps


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
    if snapshot.contract_version != 4 or policy.contract_version != 4:
        refuse(
            "unsupported_format",
            "Only source snapshot and policy contract version 4 is supported",
        )
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
    if len({i.original_identity for i in snapshot.items}) != len(snapshot.items):
        refuse("invalid_source", "Duplicate original item identities")
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
        if document.original_copy_omitted:
            if document.owner not in items or document.original_asset_id is not None:
                refuse(
                    "invalid_reference",
                    "Omitted original must have a valid owner and no copied asset",
                )
            continue
        if document.owner not in items or document.original_asset_id not in assets:
            refuse("invalid_reference", "Document owner/original payload is invalid")
        original = assets[document.original_asset_id]
        if (
            original.owner != document.owner
            or original.role != "note_original"
            or original.availability != "present"
        ):
            refuse(
                "invalid_reference",
                "Document original must be its owner's present note-original asset",
            )
    for asset in snapshot.assets:
        if asset.owner not in items:
            refuse("invalid_reference", "Asset owner is invalid")
        if asset.availability == "present" and (
            asset.actual_length is None or asset.actual_sha256 is None
        ):
            refuse("invalid_source", "Present asset lacks actual byte inventory")
        if asset.availability == "external" and (
            asset.role not in {"file", "url", "directory"} or not asset.external_uri
        ):
            refuse(
                "invalid_reference",
                "External resource lacks its destination URI or supported role",
            )
    validate_references(snapshot)
    validate_appearance(snapshot, refuse)
    if len({r.key for r in snapshot.relationships}) != len(snapshot.relationships):
        refuse("invalid_source", "Duplicate canonical relationship keys")
    for relation in snapshot.relationships:
        if relation.item_a not in items or relation.item_b not in items:
            refuse("invalid_reference", "Relationship endpoint is absent")
        endpoints = items[relation.item_a], items[relation.item_b]
        if relation.kind == "tag" and (
            endpoints[0].role != "tag" or relation.item_a == relation.item_b
        ):
            refuse(
                "invalid_reference",
                "Tag classification requires a source tag and a distinct assigned item",
            )
        if any(not item.live for item in endpoints) or (
            relation.kind != "system"
            and any(item.role == "system" for item in endpoints)
        ):
            refuse(
                "invalid_reference",
                "Navigation relationship endpoint is not a live nonsystem item",
            )
    entries = snapshot.accounting.entries
    validate_classifications(snapshot, refuse)
    if len({entry.identity for entry in entries}) != len(entries) or any(
        entry.disposition == "unresolved" or not entry.references for entry in entries
    ):
        refuse(
            "invalid_source",
            "Declared source accounting is duplicate, unresolved or incomplete",
        )
    dispositions = {d.rule_id: d for d in policy.finding_dispositions}
    if len(dispositions) != len(policy.finding_dispositions):
        refuse("unsupported_feature", "Reviewed finding dispositions are ambiguous")
    if any(
        d.disposition == "warning"
        and d.issue_code not in {"approved_source_gap", "approved_metadata_discrepancy"}
        for d in policy.finding_dispositions
    ):
        refuse(
            "unsupported_feature",
            "A reviewed profile cannot downgrade required refusal codes to warnings",
        )
    issues = []
    known_evidence = {e.identity for e in entries} | {
        e.key for e in snapshot.original_evidence
    }
    known_subjects = (
        set(items)
        | set(assets)
        | set(documents)
        | {r.key for r in snapshot.relationships}
    )
    for finding in sorted(snapshot.findings, key=lambda f: (f.rule_id, f.affected)):
        disposition = dispositions.get(finding.rule_id)
        if (
            disposition is None
            or disposition.kind != finding.kind
            or not finding.evidence
            or not finding.affected
            or not set(finding.evidence) <= known_evidence
            or not set(finding.affected) <= known_subjects
        ):
            refuse(
                "unsupported_feature",
                "Source finding lacks a compatible reviewed disposition or evidence",
            )
        issue = Issue(
            code=disposition.issue_code,
            severity="warning" if disposition.disposition == "warning" else "error",
            phase="analysis",
            message=disposition.message + " Observed: " + finding.observed_json,
            affected=finding.affected,
            evidence=finding.evidence,
            rule_id=finding.rule_id,
            guidance=disposition.guidance,
        )
        if disposition.disposition == "refuse":
            raise MigrationRefused(tuple(issues) + (issue,))
        issues.append(issue)
    recognized_absences = {
        key
        for f in snapshot.findings
        for key in f.affected
        if dispositions[f.rule_id].disposition == "warning"
        and dispositions[f.rule_id].permits_absent_payload
    }
    if any(
        a.availability == "absent" and a.asset_id not in recognized_absences
        for a in assets.values()
    ):
        refuse(
            "missing_required_payload", "Absent asset lacks a reviewed source finding"
        )
    validate_source_gaps(snapshot, policy, refuse)
    counts = Counts(
        source_gaps=len(snapshot.source_gaps),
        generated_presentations=len(snapshot.generated_presentations),
        source_items=len(items),
        source_relationships=len(snapshot.relationships),
        source_references=sum(len(d.references) for d in snapshot.documents),
        present_assets=sum(
            asset.availability == "present" for asset in assets.values()
        ),
        source_definitions=sum(i.role == "definition" for i in snapshot.items),
        classification_assignments=len(snapshot.classification_assignments),
        typed_members=len({a.item_key for a in snapshot.classification_assignments}),
    )
    return Analysis(
        snapshot=snapshot,
        policy=policy,
        entry_key=snapshot.entry_key,
        counts=counts,
        issues=tuple(issues),
    )
