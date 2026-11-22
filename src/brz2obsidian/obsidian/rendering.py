"""Pure Obsidian byte generation, with explicit run metadata."""

import hashlib
import json
import re
from collections import defaultdict
from pathlib import PurePosixPath

from brz2obsidian.contracts import (
    CopyEntry,
    GeneratedFile,
    Issue,
    MigrationPlan,
    MigrationRefused,
    RenderedVault,
    RunMetadata,
)
from brz2obsidian.core import analyze
from brz2obsidian.core import plan as build_plan
from brz2obsidian.core.appearance import icon_snapshots as expected_icon_snapshots
from brz2obsidian.core.appearance import native_icon_limits
from brz2obsidian.core.references import validate_references

from .bases import CATEGORY_VIEWS, HOME_CATEGORIES, support_files
from .categories import classification_records
from .documents import render_document
from .gaps import gap_report
from .markdown import append_boundary
from .properties import property_frontmatter, property_memberships
from .relationships import (
    navigation_index,
    note_link,
    relationship_sections,
    uncreated_listing,
)
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


def _check_plan(plan, run_metadata):
    snapshot = plan.analysis.snapshot
    if (
        plan.output_format not in (8, 9)
        or run_metadata.renderer_version != str(plan.output_format)
        or snapshot.contract_version != 7
        or plan.analysis.policy.contract_version != 7
    ):
        raise MigrationRefused(
            (
                Issue(
                    code="unsupported_format",
                    phase="rendering",
                    message="Renderer requires source contract 7 and matching plan and renderer formats (8 or 9).",
                    guidance="Plan the snapshot for the selected renderer format.",
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
    checked_analysis = analyze(snapshot, plan.analysis.policy)
    checked_plan = build_plan(
        checked_analysis,
        output_format=plan.output_format,
        import_location=plan.import_location,
        reserved_names=plan.reserved_import_names,
        import_link_connections=plan.import_link_connections,
    )
    if plan.import_location is not None and (
        plan.import_support_paths != checked_plan.import_support_paths
        or plan.support_artifacts != checked_plan.support_artifacts
        or plan.reserved_support_paths != checked_plan.reserved_support_paths
        or plan.asset_targets != checked_plan.asset_targets
    ):
        raise MigrationRefused(
            (
                Issue(
                    code="import_placement_changed",
                    phase="rendering",
                    message="Scoped artifacts no longer match their validated placement.",
                    guidance="Plan the collection again before rendering.",
                ),
            )
        )
    _check_document_evidence(plan, checked_analysis, checked_plan)
    _check_gap_obligations(plan, checked_analysis, checked_plan)


def _check_document_evidence(plan, checked_analysis, checked_plan):
    if (
        plan.counts.text_adaptations != checked_analysis.counts.text_adaptations
        or plan.counts.image_presentation_normalizations
        != checked_analysis.counts.image_presentation_normalizations
        or tuple(
            a
            for a in plan.adaptations
            if a.kind
            in {
                "literal_text",
                "image_presentation",
                "image_unavailable",
                "markdown_insert_image_unavailable",
            }
        )
        != tuple(
            a
            for a in checked_plan.adaptations
            if a.kind
            in {
                "literal_text",
                "image_presentation",
                "image_unavailable",
                "markdown_insert_image_unavailable",
            }
        )
        or tuple(i for i in plan.issues if i.code == "image_presentation_normalized")
        != tuple(
            i
            for i in checked_analysis.issues
            if i.code == "image_presentation_normalized"
        )
    ):
        raise MigrationRefused(
            (
                Issue(
                    code="invalid_reference",
                    phase="rendering",
                    message="Planned text or image presentation evidence, warnings or counts differ from validated document facts",
                    guidance="Analyze and plan this snapshot again before rendering.",
                ),
            )
        )


def _check_gap_obligations(plan, checked_analysis, checked_plan):
    snapshot = plan.analysis.snapshot
    expected_targets = checked_plan.item_targets
    expected_gaps, expected_presentations = (
        checked_plan.source_gaps,
        checked_plan.generated_presentations,
    )
    gap_subjects = {g.owner for g in snapshot.source_gaps} | {
        key for g in expected_gaps for key in g.affected_member_keys
    }
    if (
        bool(snapshot.source_gaps)
        and plan.asset_targets != checked_plan.asset_targets
        or plan.output_format == 9
        and plan.item_targets != expected_targets
        or {
            (t.item_key, t.relative_path, t.created)
            for t in plan.item_targets
            if t.item_key in gap_subjects
        }
        != {
            (t.item_key, t.relative_path, t.created)
            for t in expected_targets
            if t.item_key in gap_subjects
        }
        or plan.issues
        != checked_analysis.issues
        + native_icon_limits(
            snapshot, {t.item_key for t in plan.item_targets if t.created}
        )
        or plan.source_gaps != expected_gaps
        or plan.generated_presentations != expected_presentations
        or any(
            not next(
                t.created
                for t in plan.item_targets
                if t.item_key == p.presentation.owner
            )
            for p in expected_presentations
        )
        or plan.counts.source_gaps != checked_analysis.counts.source_gaps
        or plan.counts.generated_presentations
        != checked_analysis.counts.generated_presentations
        or plan.counts.planned_generated_embeds
        != sum(len(p.image_paths) for p in expected_presentations)
        or plan.profile_id != plan.analysis.policy.profile_id
        or plan.profile_version != plan.analysis.policy.profile_version
    ):
        raise MigrationRefused(
            (
                Issue(
                    code="invalid_reference",
                    phase="rendering",
                    message="Source-gap plan differs from verified obligations",
                    guidance="Analyze and plan this snapshot again.",
                ),
            )
        )


def _check_icon_kinds(plan, asset_paths):
    # Destination eligibility matches the native Base views and source-free
    # checker. A neutral source icon may be valid without being an Obsidian image.
    for selection in plan.icon_snapshots:
        icon = selection.effective_icon_asset_id
        if icon is not None:
            suffix = PurePosixPath(asset_paths[icon]).suffix.lower()
            if suffix not in {
                ".avif",
                ".bmp",
                ".gif",
                ".jpeg",
                ".jpg",
                ".png",
                ".svg",
                ".webp",
            }:
                raise MigrationRefused(
                    (
                        Issue(
                            code="unsupported_feature",
                            phase="rendering",
                            message=f"Selected icon has an unsupported Obsidian image kind: {suffix}",
                            affected=(selection.item_key, icon),
                            guidance="Use a supported local image for the source icon, then convert into a fresh vault.",
                        ),
                    )
                )


def _note_appearance(item, icon, neighbors, plan, asset_paths, item_targets, items):
    text = ""
    if item.role == "definition":
        hierarchy = relationship_sections(
            neighbors, item_targets, items, headings=("Parents", "Children")
        )
        if hierarchy:
            text += hierarchy + "\n"
        if any(
            g.gap.owner == item.key and g.outcome == "unknown_note"
            for g in plan.source_gaps
        ):
            text += "> [!warning] Source category note unavailable\n> Source category note text is absent and remains unknown. No prose, captions or layout were recovered. See [[MIGRATION REPORT.md|Migration report]] for evidence and optional repair steps.\n\n"
    elif icon is not None:
        text += "![[" + asset_paths[icon] + "]]\n\n"
    return text


def _note_icon_warnings(item, icon, source_gaps, items, item_targets):
    text = ""
    for gap in source_gaps:
        if gap.gap.role != "definition_icon":
            continue
        appearance = (
            "a farther selected appearance-category icon is used"
            if icon is not None
            else "appearance is neutral"
        )
        if gap.gap.owner == item.key:
            text += (
                "> [!warning] Source category icon unavailable\n> Source category icon is absent; "
                + appearance
                + ". See [[MIGRATION REPORT.md|Migration report]] for provider evidence and optional repair steps.\n\n"
            )
        elif item.key in gap.affected_member_keys:
            provider = items[gap.provider_key]
            provider_target = item_targets[provider.key]
            text += (
                "> [!warning] Inherited icon unavailable\n> The inherited icon is unavailable from "
                + note_link(provider_target, provider.title)
                + "; "
                + appearance
                + ". See [[MIGRATION REPORT.md|Migration report]] for evidence and optional repair steps.\n\n"
            )
    return text


def _append_note_sections(text, resources, relationships, navigation):
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
    return text


def _support_path(plan, path):
    return plan.import_support_paths.get(path, path)


def _scope_support_links(plan, text):
    if plan.import_location is None:
        return text
    return re.sub(
        r"\[\[([^\]\n#|]+)(?=[#|\]])",
        lambda match: "[[" + _support_path(plan, match[1]),
        text,
    )


def _add_notes(
    plan,
    add,
    items,
    documents,
    icon_snapshots,
    item_targets,
    asset_targets,
    asset_paths,
    memberships,
):
    snapshot = plan.analysis.snapshot
    presentations = {p.presentation.owner: p for p in plan.generated_presentations}
    neighbors_by_item = navigation_index(snapshot.relationships)
    category_links, native_tags = memberships
    resources_by_owner = defaultdict(list)
    for asset in sorted(snapshot.assets, key=lambda asset: asset.asset_id):
        resources_by_owner[asset.owner].append(asset)
    for target in plan.item_targets:
        if not target.created:
            continue
        item = items[target.item_key]
        heading = re.sub(r"([\\`*_{}\[\]<>#])", r"\\\1", item.title)
        text = (
            property_frontmatter(
                item,
                plan.source_identity.source_id,
                category_links.get(item.key, []),
                native_tags.get(item.key, []),
                asset_paths,
            )
            + "# "
            + heading
            + "\n\n"
        )
        neighbors = neighbors_by_item.get(item.key, {})
        presentation = presentations.get(item.key)
        if presentation:
            text += _scope_support_links(
                plan,
                "> [!warning] Source note unavailable\n> Source note text is absent. Unknown prose, captions and layout were not recovered. See [[MIGRATION REPORT.md|Migration report]] for evidence and optional repair steps.\n\n",
            )
        icon = icon_snapshots[item.key].effective_icon_asset_id
        text += _note_appearance(
            item, icon, neighbors, plan, asset_paths, item_targets, items
        )
        text += _note_icon_warnings(item, icon, plan.source_gaps, items, item_targets)
        if item.role == "definition":
            text += _scope_support_links(plan, CATEGORY_VIEWS) + "\n"
        if item.label:
            text += item.label + "\n\n"
        for index, key in enumerate(item.document_ids):
            text += append_boundary(text)
            if index:
                text += "\n\n"
            text += render_document(
                documents[key], target.relative_path, item_targets, asset_targets
            )
        if presentation:
            text += (
                "\n\n".join("![[" + path + "]]" for path in presentation.image_paths)
                + "\n\n"
            )
        resources = resource_section(
            resources_by_owner.get(item.key, ()), asset_targets
        )
        relationships = relationship_sections(
            neighbors,
            item_targets,
            items,
            headings=("Related",)
            if item.role == "definition"
            else ("Parents", "Children", "Related"),
        )
        navigation = (
            _scope_support_links(plan, HOME_CATEGORIES)
            if item.key == plan.analysis.entry_key
            else ""
        )
        text = _append_note_sections(text, resources, relationships, navigation)
        add(target.relative_path, text.encode("utf-8"))


def _add_scoped_support(plan, add):
    for path, content in support_files() + template_support_files(plan):
        content = _scope_support_links(plan, content)
        if path.endswith(".base"):
            for folder in ("Categories", "Templates", "Attachments"):
                content = content.replace(
                    f'inFolder("{folder}")',
                    f'inFolder("{plan.import_location}/{folder}")',
                )
        add(_support_path(plan, path), content.encode("utf-8"))
    return {}, {}


def _add_configuration(plan, run_metadata, add):
    if plan.import_location is not None:
        return _add_scoped_support(plan, add)
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
    return configuration, core_plugins


def _image_normalization_report(plan):
    if not plan.counts.image_presentation_normalizations:
        return ""
    snapshot = plan.analysis.snapshot
    report = "\n> [!warning] Image sizing normalized\n> Original image sizing declarations use ordinary responsive inline Markdown presentation; exact percentage sizing is not reproduced. Review placement and readability in each affected note, and adjust manually if desired. Images retain their original bytes and aspect ratio.\n\n"
    for document in sorted(snapshot.documents, key=lambda d: d.key):
        target = next(t for t in plan.item_targets if t.item_key == document.owner)
        for reference in document.references:
            normalization = reference.presentation_normalization
            if normalization:
                declaration = (
                    normalization.declaration.replace("`", "\\`")
                    .replace("\r", " ")
                    .replace("\n", " ")
                )
                report += (
                    "- "
                    + note_link(target, target.original_title)
                    + ": `"
                    + declaration
                    + "`; exact declaration, scoped document codepoint span/digest and original reference remain in migration-record.json.\n"
                )
    return report


def _source_warning_report(plan):
    report = ""
    depth_warnings = [i for i in plan.issues if i.code == "icon_lookup_depth"]
    if depth_warnings:
        target_by_key = {t.item_key: t for t in plan.item_targets}
        report += "\n## Native icon lookup warnings\n\nIcon lookup exceeds 8 links. Native dashboards display no inherited icon for these lookups; ordinary body snapshots use the full finite migration-time chain. Memberships and owned icon declarations are unchanged. After category icon, membership or provider edits, close and reopen affected category dashboards and Categories overview; open views may retain stale or inconsistent icons and statuses.\n\n"
        for issue in depth_warnings:
            report += (
                "- "
                + " -> ".join(
                    note_link(target_by_key[key], target_by_key[key].original_title)
                    for key in issue.affected
                )
                + "\n"
            )
    if plan.issues:
        report += "\n## Source warnings\n\n"
        for issue in plan.issues:
            affected_notes = [
                note_link(t, t.original_title)
                for t in plan.item_targets
                if t.created and t.item_key in issue.affected
            ]
            message = (
                re.sub(r"([\\`*_{}\[\]<>#])", r"\\\1", issue.message)
                .replace("\r", " ")
                .replace("\n", " ")
            )
            report += f"- {', '.join(affected_notes)} — {issue.code} ({issue.rule_id}): {message} {issue.guidance}\n"
    return report


def _scoped_migration_report(plan, report):
    if plan.import_location is not None:
        report = report.replace(
            "Open the root Home note", "Open this import’s Home note"
        )
        report = report.replace("Bundled Bases and link updates are configured.", "")
        report = report.replace(
            "Bundled Templates is configured for insertion-day ISO dates; update dates are maintained explicitly.",
            "The import leaves the vault’s existing settings in place.",
        )
        return _scope_support_links(plan, report)
    return report


def _add_migration_report(plan, add):
    snapshot = plan.analysis.snapshot
    report = "# Migration report\n\nOpen the root Home note to begin. Safe original note bytes are retained under Attachments. Forgotten thoughts are excluded by default; unsafe originals and unscopable history are omitted. Counts describe included scope.\n\n"
    report += f"Created {plan.counts.planned_notes} thought notes; preserved {plan.counts.planned_assets} present payloads.\n\n"
    if plan.counts.text_adaptations:
        report += f"Applied {plan.counts.text_adaptations} exact text adaptations for Markdown display, including literal escaping and insert normalization where present. Exact edits in migration-record.json use scoped source Unicode codepoint offsets before adaptation, with a scoped source digest; reference spans use adapted document text offsets and digest. Safe originals retain exact source bytes. Generated ToCs are static: update their links and heading block IDs after heading edits. Native callouts retain Obsidian's colours and icons; authored icon metadata uses a visible title fallback.\n\n"
        for owner in sorted(
            {d.owner for d in snapshot.documents if d.text_adaptations}
        ):
            target = next(t for t in plan.item_targets if t.item_key == owner)
            if target.created:
                report += "- " + note_link(target, target.original_title) + "\n"
        report += "\n"
    external_files = sum(
        a.role == "file" and a.availability == "external" for a in snapshot.assets
    )
    if external_files:
        report += f"Retained {external_files} external file references as ordinary Resources links. Their original locations remain in migration-record.json. External targets were not checked, opened or copied; historical lengths do not establish accessibility.\n\n"
    report += "Unsupported feature classes are refused explicitly.\n"
    report += "\n[[Vault guide.md|Vault guide]] explains manual full-template selection for new objects, direct membership edits on existing notes, canonical properties and future-category starters. Bundled Templates is configured for insertion-day ISO dates; update dates are maintained explicitly.\n"
    report += (
        "\nOpen [[Categories.md|Categories]] from Home, then a category dashboard "
        "for its native Members table and Gallery after the title and any "
        "Parents/Children navigation, "
        "without a generated introductory category image. Retained source content "
        "and resources follow the Bases; category icon properties remain available "
        "for dashboard images. These contextual Bases use the "
        "embedding category and follow link-preserving category renames; a standalone "
        "member Base has no category context. Edit categories to change membership "
        "and appearance_category to choose a member's icon provider independently "
        "of membership order. A valid local icon override wins, an empty provider "
        "opts out, and an invalid provider is shown without selecting a substitute. "
        "Category icon edits update inherited dashboard images; ordinary/member note-body image "
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
    report = _scoped_migration_report(plan, report)
    report += gap_report(plan)
    report += _image_normalization_report(plan)
    report += _source_warning_report(plan)
    if any(r.kind in {"hierarchy", "related"} for r in snapshot.relationships):
        report += "\nRelationships use simple Parents, Children and Related links. Original arrows and one-way visibility details remain in the migration record.\n"
    listing = uncreated_listing(plan)
    if listing:
        add(_support_path(plan, "Uncreated targets.md"), listing.encode("utf-8"))
        report += _scope_support_links(
            plan,
            "\n[[Uncreated targets.md|Uncreated targets]] lists otherwise unrepresented empty thoughts"
            + (" and Related pairs" if plan.output_format == 8 else "")
            + ".\n",
        )
    listing = tag_listing(plan)
    if listing:
        add(plan.tag_memberships_path, listing.encode("utf-8"))
        report += _scope_support_links(
            plan,
            "\n[[Tag memberships.md|Tag memberships]] lists assignments on uncreated targets and source tags without assignments.\n",
        )
    add(_support_path(plan, "MIGRATION REPORT.md"), report.encode())


def _migration_record(
    plan,
    run_metadata,
    counts,
    configuration,
    core_plugins,
    items,
    item_targets,
    icon_snapshots,
    assets,
):
    snapshot = plan.analysis.snapshot
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
        "schema_version": plan.output_format,
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
        "source_gaps": [gap.model_dump() for gap in plan.source_gaps],
        "generated_presentations": [
            p.model_dump() for p in plan.generated_presentations
        ],
        "support_artifacts": [a.model_dump() for a in plan.support_artifacts],
        "reserved_support_paths": list(plan.reserved_support_paths),
        "adaptations": [value.model_dump() for value in plan.adaptations],
        "source_accounting": snapshot.accounting.model_dump(),
        "issues": [issue.model_dump() for issue in plan.issues],
        "counts": counts.model_dump(),
        "obsidian_configuration": configuration,
        "obsidian_core_plugins_configuration": core_plugins,
        "obsidian_templates_configuration": TEMPLATE_CONFIGURATION
        if plan.import_location is None
        else {},
        "obsidian_property_types_configuration": {"types": PROPERTY_TYPES}
        if plan.import_location is None
        else {},
    }
    if plan.import_location is not None:
        record["collection_location"] = plan.import_location
        record["import_reserved_names"] = plan.reserved_import_names
        record["import_link_connections"] = [
            choice.model_dump() for choice in plan.import_link_connections
        ]
        record["import_support_paths"] = plan.import_support_paths
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
    return (record_json + ',"original_evidence":[' + original_values + "]}\n").encode(
        "utf-8"
    )


def render(plan: MigrationPlan, run_metadata: RunMetadata) -> RenderedVault:
    _check_plan(plan, run_metadata)
    snapshot = plan.analysis.snapshot
    items = {item.key: item for item in snapshot.items}
    documents = {document.key: document for document in snapshot.documents}
    icon_snapshots = {s.item_key: s for s in plan.icon_snapshots}
    item_targets = {target.item_key: target for target in plan.item_targets}
    asset_targets = {target.asset_id: target for target in plan.asset_targets}
    asset_paths = {key: target.relative_path for key, target in asset_targets.items()}
    memberships = property_memberships(plan, item_targets)
    _check_icon_kinds(plan, asset_paths)
    files = []
    counts = plan.counts.model_copy(
        update={
            "actual_generated_embeds": sum(
                len(p.image_paths) for p in plan.generated_presentations
            ),
            "actual_references": sum(
                len(documents[key].references)
                for target in plan.item_targets
                if target.created
                for key in items[target.item_key].document_ids
            ),
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

    _add_notes(
        plan,
        add,
        items,
        documents,
        icon_snapshots,
        item_targets,
        asset_targets,
        asset_paths,
        memberships,
    )
    configuration, core_plugins = _add_configuration(plan, run_metadata, add)
    _add_migration_report(plan, add)
    assets = {asset.asset_id: asset for asset in snapshot.assets}
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
    add(
        _support_path(plan, "migration-record.json"),
        _migration_record(
            plan,
            run_metadata,
            counts,
            configuration,
            core_plugins,
            items,
            item_targets,
            icon_snapshots,
            assets,
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
