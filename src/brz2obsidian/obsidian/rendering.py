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

from .relationships import relationship_sections, uncreated_listing
from .resources import resource_section


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
    documents = {document.key: document for document in snapshot.documents}
    files = []

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
        text = "# " + heading + "\n\n"
        if item.label:
            text += item.label + "\n\n"
        text += "\n\n".join(documents[key].text for key in item.document_ids)
        resources = resource_section(plan, item.key)
        if resources:
            text += "\n\n" + resources
        relationships = relationship_sections(plan, item.key)
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
    listing = uncreated_listing(plan)
    if listing:
        add("Uncreated targets.md", listing.encode("utf-8"))
        report += "\n[[Uncreated targets.md|Uncreated targets]] lists otherwise unrepresented empty thoughts and Related pairs.\n"
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
    record = {
        "schema": "brz2obsidian.migration",
        "schema_version": 1,
        "converter_version": run_metadata.converter_version,
        "renderer_version": run_metadata.renderer_version,
        "source_identity": plan.source_identity.model_dump(),
        "profile_id": plan.profile_id,
        "profile_version": plan.profile_version,
        "run_metadata": run_metadata.model_dump(),
        "item_targets": [target.model_dump() for target in plan.item_targets],
        "asset_targets": [
            dict(
                **assets[target.asset_id].model_dump(),
                **target.model_dump(exclude={"asset_id"}),
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
        "tag_memberships": [],
        "adaptations": [value.model_dump() for value in plan.adaptations],
        "source_accounting": snapshot.accounting.model_dump(),
        "issues": [issue.model_dump() for issue in plan.issues],
        "counts": plan.counts.model_dump(),
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
        counts=plan.counts,
    )


class ObsidianRenderer:
    render = staticmethod(render)
