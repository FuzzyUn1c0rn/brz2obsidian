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
from brz2obsidian.core.appearance import icon_snapshots as expected_icon_snapshots
from brz2obsidian.core.references import validate_references

from .bases import CATEGORY_VIEWS, HOME_CATEGORIES, support_files
from .categories import classification_records
from .documents import render_document
from .markdown import append_boundary
from .properties import property_frontmatter
from .relationships import relationship_sections, uncreated_listing
from .resources import resource_section
from .tags import tag_listing, tag_records
from .templates import (
    PROPERTY_TYPES,
    TEMPLATE_CONFIGURATION,
)
from .templates import (
    support_files as template_support_files,
)


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def render(plan: MigrationPlan, run_metadata: RunMetadata) -> RenderedVault:
    snapshot = plan.analysis.snapshot
    if (
        run_metadata.renderer_version != "2"
        or snapshot.contract_version != 2
        or plan.analysis.policy.contract_version != 2
    ):
        raise MigrationRefused(
            (
                Issue(
                    code="unsupported_format",
                    phase="rendering",
                    message="Renderer requires version-2 contracts and renderer metadata",
                    guidance="Use the current contract and set renderer_version to 2.",
                ),
            )
        )
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
    if plan.icon_snapshots != expected_icon_snapshots(
        snapshot, {t.item_key for t in plan.item_targets if t.created}
    ):
        raise MigrationRefused(
            (
                Issue(
                    code="invalid_reference",
                    phase="rendering",
                    message="Planned icon snapshots differ from owned declarations and classification defaults",
                    guidance="Analyze and plan this snapshot again before rendering.",
                ),
            )
        )
    documents = {document.key: document for document in snapshot.documents}
    icon_snapshots = {s.item_key: s for s in plan.icon_snapshots}
    asset_paths = {t.asset_id: t.relative_path for t in plan.asset_targets}
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
        text = property_frontmatter(plan, item) + "# " + heading + "\n\n"
        icon = icon_snapshots[item.key].effective_icon_asset_id
        if icon is not None:
            text += "![[" + asset_paths[icon] + "]]\n\n"
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
        navigation = ""
        if item.role == "definition":
            navigation += CATEGORY_VIEWS
        if item.key == plan.analysis.entry_key:
            if navigation:
                navigation += "\n"
            navigation += HOME_CATEGORIES
        if navigation:
            text += append_boundary(text)
            endings = text.replace("\r\n", "\n").replace("\r", "\n")
            text += (
                ""
                if endings.endswith("\n\n")
                else "\n"
                if endings.endswith("\n")
                else "\n\n"
            ) + navigation
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
        "alwaysUpdateLinks": True,
        "attachmentFolderPath": "Attachments",
    }
    add(".obsidian/app.json", _json(configuration))
    core_plugins = dict.fromkeys(
        (
            "file-explorer",
            "global-search",
            "switcher",
            "graph",
            "backlink",
            "tag-pane",
            "page-preview",
            "command-palette",
            "bookmarks",
            "properties",
            "bases",
            "templates",
        ),
        True,
    )
    add(".obsidian/core-plugins.json", _json(core_plugins))
    for path, content in support_files():
        add(path, content.encode("utf-8"))
    add(".obsidian/templates.json", _json(TEMPLATE_CONFIGURATION))
    add(".obsidian/types.json", _json({"types": PROPERTY_TYPES}))
    for path, content in template_support_files(plan):
        add(path, content.encode("utf-8"))
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
    report += "\n[[Vault guide.md|Vault guide]] explains manual full-template selection for new objects, direct membership edits on existing notes, canonical properties and future-category starters. Bundled Templates is configured for insertion-day ISO dates; update dates are maintained explicitly.\n"
    report += (
        "\nOpen [[Categories.md|Categories]] from Home, then a category dashboard "
        "for its native Members table and Gallery. These contextual Bases use the "
        "embedding category and follow link-preserving category renames; a standalone "
        "member Base has no category context. Edit categories to change membership "
        "and appearance_category to choose a member's icon provider independently "
        "of membership order. A valid local icon override wins, an empty provider "
        "opts out, and an invalid provider is shown without selecting a substitute. "
        "Category icon edits update inherited dashboard images; note-body image "
        "references remain separately editable migration-time snapshots. Declared "
        "colours remain in migration-record.json only. Bundled Bases and link updates are configured.\n"
    )
    if any(
        a.availability == "present" and a.original_name.casefold().endswith(".pdf")
        for a in snapshot.assets
    ):
        report += "\nPDF files are preserved and can be opened in Obsidian. Vault Search does not search PDF body text; this conversion does not extract or index it, or reproduce TheBrain's PDF body search.\n"
    if any(a.video_presentation for a in snapshot.assets):
        report += "\nVideo playback depends on the remote service and network. Offline playback and service availability are not guaranteed. The original resource links remain available; no remote video bytes were archived or downloaded by this conversion.\n"
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
        "schema_version": 2,
        "converter_version": run_metadata.converter_version,
        "renderer_version": run_metadata.renderer_version,
        "source_identity": plan.source_identity.model_dump(),
        "profile_id": plan.profile_id,
        "profile_version": plan.profile_version,
        "run_metadata": run_metadata.model_dump(),
        "item_targets": [
            dict(
                **target.model_dump(),
                declared_appearance=items[
                    target.item_key
                ].declared_appearance.model_dump()
                if items[target.item_key].declared_appearance
                else None,
                calendar_dates=items[target.item_key].calendar_dates.model_dump(
                    mode="json"
                )
                if items[target.item_key].calendar_dates
                else None,
                metadata_evidence=list(items[target.item_key].evidence),
                icon_snapshot=icon_snapshots[target.item_key].model_dump()
                if target.created
                else None,
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
                    "classification": "linked category membership",
                }[relation.kind],
            )
            for relation in snapshot.relationships
        ],
        "tag_memberships": tag_records(plan),
        "classification_assignments": classification_records(plan),
        "support_artifacts": [a.model_dump() for a in plan.support_artifacts],
        "reserved_support_paths": list(plan.reserved_support_paths),
        "adaptations": [value.model_dump() for value in plan.adaptations],
        "source_accounting": snapshot.accounting.model_dump(),
        "issues": [issue.model_dump() for issue in plan.issues],
        "counts": counts.model_dump(),
        "obsidian_configuration": configuration,
        "obsidian_core_plugins_configuration": core_plugins,
        "obsidian_templates_configuration": TEMPLATE_CONFIGURATION,
        "obsidian_property_types_configuration": {"types": PROPERTY_TYPES},
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
    generated_support = {f.relative_path for f in files} - {
        t.relative_path for t in plan.item_targets if t.created
    }
    if generated_support != {a.relative_path for a in plan.support_artifacts}:
        raise MigrationRefused(
            (
                Issue(
                    code="invalid_source",
                    phase="rendering",
                    message="Generated support differs from planned artifact obligations",
                    guidance="Plan all generated support artifacts before rendering.",
                ),
            )
        )
    return RenderedVault(
        source_identity=plan.source_identity,
        renderer_version=run_metadata.renderer_version,
        generated_files=tuple(files),
        copies=copies,
        manifest=manifest,
        reserved_paths=tuple(
            t.relative_path for t in plan.item_targets if not t.created
        )
        + plan.reserved_support_paths,
        support_artifacts=plan.support_artifacts,
        counts=counts,
    )


class ObsidianRenderer:
    render = staticmethod(render)
