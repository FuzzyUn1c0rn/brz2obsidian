"""Pure Obsidian byte generation, with explicit run metadata."""

import hashlib
import json
import re

from brz2obsidian.contracts import (
    CopyEntry,
    GeneratedFile,
    Issue,
    MigrationPlan,
    MigrationRefused,
    RenderedVault,
    RunMetadata,
)
from brz2obsidian.core.references import validate_references

from .documents import render_document
from .markdown import append_boundary
from .relationships import relationship_sections, uncreated_listing
from .resources import resource_section
from .tags import tag_frontmatter, tag_listing, tag_records


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def render(plan: MigrationPlan, run_metadata: RunMetadata) -> RenderedVault:
    snapshot = plan.analysis.snapshot
    if plan.source_identity != snapshot.identity:
        raise MigrationRefused(
            (
                Issue(
                    code="source_changed",
                    phase="rendering",
                    message="Plan is bound to a different source snapshot",
                    guidance="Analyze and plan this snapshot again before rendering.",
                ),
            )
        )
    items = {item.key: item for item in snapshot.items}
    validate_references(snapshot, "rendering")
    documents = {document.key: document for document in snapshot.documents}
    files = []
    counts = plan.counts.model_copy(
        update={
            "actual_references": sum(
                len(documents[key].references)
                for target in plan.item_targets
                if target.created
                for key in items[target.item_key].document_ids
            )
        }
    )

    def add(path, content):
        files.append(
            GeneratedFile(
                relative_path=path,
                content=content,
                sha256=hashlib.sha256(content).hexdigest(),
            )
        )

    for target in plan.item_targets:
        if not target.created:
            continue
        item = items[target.item_key]
        heading = re.sub(r"([\\`*_{}\[\]<>#])", r"\\\1", item.title)
        text = tag_frontmatter(plan, item.key) + "# " + heading + "\n\n"
        if item.label:
            text += item.label + "\n\n"
        for index, key in enumerate(item.document_ids):
            text += append_boundary(text)
            if index:
                text += "\n\n"
            text += render_document(documents[key], target.relative_path, plan)
        resources = resource_section(plan, item.key)
        relationships = relationship_sections(plan, item.key)
        if resources or relationships:
            text += append_boundary(text)
        if resources:
            text += "\n\n" + resources
        if relationships:
            endings = text.replace("\r\n", "\n").replace("\r", "\n")
            separator = (
                ""
                if endings.endswith("\n\n")
                else "\n"
                if endings.endswith("\n")
                else "\n\n"
            )
            text += separator + relationships
        add(target.relative_path, text.encode("utf-8"))
    home = next(
        target.relative_path
        for target in plan.item_targets
        if target.item_key == plan.analysis.entry_key
    )
    configuration = {
        "showInlineTitle": False,
        "defaultViewMode": "preview",
        "newFileLocation": "folder",
        "newFileFolderPath": "Notes",
        "useMarkdownLinks": False,
        "newLinkFormat": "absolute",
        "openBehavior": "file:" + home,
    }
    add(".obsidian/app.json", _json(configuration))
    add(
        ".obsidian/bookmarks.json",
        _json(
            {
                "items": [
                    {
                        "type": "file",
                        "ctime": run_metadata.bookmark_time,
                        "path": home,
                        "title": "Home",
                    }
                ]
            }
        ),
    )
    report = "# Migration report\n\nOpen the root Home note to begin. Original note bytes are retained under Attachments.\n\n"
    report += f"Created {plan.counts.planned_notes} thought notes; preserved {plan.counts.planned_assets} present payloads.\n\n"
    report += "Unsupported feature classes are refused explicitly.\n"
    if plan.issues:
        report += "\n## Source warnings\n\n"
        for issue in plan.issues:
            message = (
                re.sub(r"([\\`*_{}\[\]<>#])", r"\\\1", issue.message)
                .replace("\r", " ")
                .replace("\n", " ")
            )
            report += f"- {issue.code} ({issue.rule_id}): {message} {issue.guidance}\n"
    if any(r.kind in {"hierarchy", "related"} for r in snapshot.relationships):
        report += "\nRelationships use simple Parents, Children and Related links. Original arrows and one-way visibility details remain in the migration record.\n"
    listing = uncreated_listing(plan)
    if listing:
        add("Uncreated targets.md", listing.encode("utf-8"))
        report += "\n[[Uncreated targets.md|Uncreated targets]] lists otherwise unrepresented empty thoughts and Related pairs.\n"
    listing = tag_listing(plan)
    if listing:
        add(plan.tag_memberships_path, listing.encode("utf-8"))
        report += "\n[[Tag memberships.md|Tag memberships]] lists assignments on uncreated targets and source tags without assignments.\n"
    add("MIGRATION REPORT.md", report.encode())
    assets = {asset.asset_id: asset for asset in snapshot.assets}
    item_targets = {target.item_key: target for target in plan.item_targets}
    copies = tuple(
        CopyEntry(
            relative_path=target.relative_path,
            asset_id=target.asset_id,
            expected_length=assets[target.asset_id].actual_length,
            expected_sha256=assets[target.asset_id].actual_sha256,
        )
        for target in plan.asset_targets
        if target.relative_path is not None
        and assets[target.asset_id].availability == "present"
    )
    document_records = {
        d.key: dict(
            **d.model_dump(exclude={"text"}),
            owner_target=item_targets[d.owner].relative_path
            if d.owner in item_targets
            else None,
        )
        for d in snapshot.documents
    }
    record = {
        "schema": "brz2obsidian.migration",
        "schema_version": 1,
        "converter_version": run_metadata.converter_version,
        "renderer_version": run_metadata.renderer_version,
        "source_identity": plan.source_identity.model_dump(),
        "profile_id": plan.profile_id,
        "profile_version": plan.profile_version,
        "run_metadata": run_metadata.model_dump(),
        "item_targets": [
            dict(
                **target.model_dump(),
                documents=[
                    document_records[d.key]
                    for d in snapshot.documents
                    if d.owner == target.item_key
                ],
            )
            for target in plan.item_targets
        ],
        "asset_targets": [
            dict(
                **assets[target.asset_id].model_dump(),
                **target.model_dump(exclude={"asset_id"}),
                source_findings=[
                    finding.model_dump()
                    for finding in snapshot.findings
                    if target.asset_id in finding.affected
                ],
                retained_documents=[
                    document_records[d.key]
                    for d in snapshot.documents
                    if d.owner not in item_targets
                    and d.original_asset_id == target.asset_id
                ],
            )
            for target in plan.asset_targets
        ],
        "relationships": [
            dict(
                **relation.model_dump(),
                target_a=item_targets[relation.item_a].relative_path
                if relation.item_a in item_targets
                else None,
                target_b=item_targets[relation.item_b].relative_path
                if relation.item_b in item_targets
                else None,
                presentation={
                    "hierarchy": "Parents/Children",
                    "related": "Related",
                    "tag": "native tags",
                    "system": "retained_only",
                }[relation.kind],
            )
            for relation in snapshot.relationships
        ],
        "tag_memberships": tag_records(plan),
        "adaptations": [value.model_dump() for value in plan.adaptations],
        "source_accounting": snapshot.accounting.model_dump(),
        "issues": [issue.model_dump() for issue in plan.issues],
        "counts": counts.model_dump(),
        "obsidian_configuration": configuration,
    }
    # Embed retained JSON directly: decoding/dumping would round large or
    # high-precision numeric source values. Never reconstruct evidence from facts.
    original_values = ",\n".join(
        '{"key":'
        + json.dumps(evidence.key)
        + ',"kind":'
        + json.dumps(evidence.kind)
        + ',"records":'
        + evidence.original_json
        + "}"
        for evidence in snapshot.original_evidence
    )
    record_json = json.dumps(record, ensure_ascii=False, indent=2)[:-1]
    add(
        "migration-record.json",
        (record_json + ',"original_evidence":[' + original_values + "]}\n").encode(
            "utf-8"
        ),
    )
    manifest = tuple(file.relative_path for file in files) + tuple(
        copy.relative_path for copy in copies
    )
    return RenderedVault(
        source_identity=plan.source_identity,
        renderer_version=run_metadata.renderer_version,
        generated_files=tuple(files),
        copies=copies,
        manifest=manifest,
        reserved_paths=tuple(
            t.relative_path for t in plan.item_targets if not t.created
        ),
        counts=counts,
    )


class ObsidianRenderer:
    render = staticmethod(render)
