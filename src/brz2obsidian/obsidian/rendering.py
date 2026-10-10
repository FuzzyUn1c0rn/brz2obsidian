"""Pure Obsidian byte generation, with explicit run metadata."""

import hashlib
import json
import re
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
from brz2obsidian.core.items import assign_item_targets
from brz2obsidian.core.references import validate_references
from brz2obsidian.core.resources import assign_asset_targets, resource_owners
from brz2obsidian.core.source_gaps import source_gap_targets

from .bases import CATEGORY_VIEWS, HOME_CATEGORIES, support_files
from .categories import classification_records
from .documents import render_document
from .gaps import gap_report
from .markdown import append_boundary
from .properties import property_frontmatter
from .relationships import note_link, relationship_sections, uncreated_listing
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
        run_metadata.renderer_version != "7"
        or snapshot.contract_version != 7
        or plan.analysis.policy.contract_version != 7
    ):
        raise MigrationRefused(
            (
                Issue(
                    code="unsupported_format",
                    phase="rendering",
                    message="Renderer requires version-7 contracts and renderer metadata",
                    guidance="Use the current contract and set renderer_version to 7.",
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
    checked_analysis = analyze(snapshot, plan.analysis.policy)
    if (
        plan.counts.text_adaptations != checked_analysis.counts.text_adaptations
        or plan.counts.image_presentation_normalizations
        != checked_analysis.counts.image_presentation_normalizations
        or tuple(
            a
            for a in plan.adaptations
            if a.kind in {"literal_text", "image_presentation"}
        )
        != tuple(
            a
            for a in build_plan(checked_analysis).adaptations
            if a.kind in {"literal_text", "image_presentation"}
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
    expected_targets = assign_item_targets(checked_analysis, resource_owners(snapshot))
    expected_gaps, expected_presentations = source_gap_targets(
        snapshot, expected_targets, assign_asset_targets(snapshot)
    )
    gap_subjects = {g.owner for g in snapshot.source_gaps} | {
        key for g in expected_gaps for key in g.affected_member_keys
    }
    if (
        bool(snapshot.source_gaps)
        and plan.asset_targets != assign_asset_targets(snapshot)
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
        or bool(gap_subjects)
        and plan.issues != checked_analysis.issues
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
    presentations = {p.presentation.owner: p for p in plan.generated_presentations}
    documents = {document.key: document for document in snapshot.documents}
    icon_snapshots = {s.item_key: s for s in plan.icon_snapshots}
    asset_paths = {t.asset_id: t.relative_path for t in plan.asset_targets}
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

    for target in plan.item_targets:
        if not target.created:
            continue
        item = items[target.item_key]
        heading = re.sub(r"([\\`*_{}\[\]<>#])", r"\\\1", item.title)
        text = property_frontmatter(plan, item) + "# " + heading + "\n\n"
        presentation = presentations.get(item.key)
        if presentation:
            text += "> [!warning] Source note unavailable\n> Source note text is absent. Unknown prose, captions and layout were not recovered. See [[MIGRATION REPORT.md|Migration report]] for evidence and optional repair steps.\n\n"
        icon = icon_snapshots[item.key].effective_icon_asset_id
        if item.role == "definition":
            hierarchy = relationship_sections(
                plan, item.key, headings=("Parents", "Children")
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
        for gap in plan.source_gaps:
            if gap.outcome != "neutral_icon":
                continue
            if gap.gap.owner == item.key:
                text += "> [!warning] Source category icon unavailable\n> Source category icon is absent; appearance is neutral. See [[MIGRATION REPORT.md|Migration report]] for provider evidence and optional repair steps.\n\n"
            elif item.key in gap.affected_member_keys:
                provider = items[gap.provider_key]
                provider_target = next(
                    t for t in plan.item_targets if t.item_key == provider.key
                )
                text += (
                    "> [!warning] Inherited icon unavailable\n> The inherited icon is unavailable from "
                    + note_link(provider_target, provider.title)
                    + "; appearance is neutral. See [[MIGRATION REPORT.md|Migration report]] for evidence and optional repair steps.\n\n"
                )
        if item.role == "definition":
            text += CATEGORY_VIEWS + "\n"
        if item.label:
            text += item.label + "\n\n"
        for index, key in enumerate(item.document_ids):
            text += append_boundary(text)
            if index:
                text += "\n\n"
            text += render_document(documents[key], target.relative_path, plan)
        if presentation:
            text += (
                "\n\n".join("![[" + path + "]]" for path in presentation.image_paths)
                + "\n\n"
            )
        resources = resource_section(plan, item.key)
        relationships = relationship_sections(
            plan,
            item.key,
            headings=("Related",)
            if item.role == "definition"
            else ("Parents", "Children", "Related"),
        )
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
        if item.key == plan.analysis.entry_key:
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
    report = "# Migration report\n\nOpen the root Home note to begin. Safe original note bytes are retained under Attachments. Forgotten thoughts are excluded by default; unsafe originals and unscopable history are omitted. Counts describe included scope.\n\n"
    report += f"Created {plan.counts.planned_notes} thought notes; preserved {plan.counts.planned_assets} present payloads.\n\n"
    if plan.counts.text_adaptations:
        report += f"Applied {plan.counts.text_adaptations} exact text adaptations for Markdown display, including literal escaping and insert normalization where present. Exact edits in migration-record.json use scoped source Unicode codepoint offsets before adaptation, with a scoped source digest; reference spans use adapted document text offsets and digest. Safe originals retain exact archived bytes. Generated ToCs are static: update their links and heading block IDs after heading edits. Native callouts retain Obsidian's colours and icons; authored icon metadata uses a visible title fallback.\n\n"
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
    report += gap_report(plan)
    if plan.counts.image_presentation_normalizations:
        report += "\n> [!warning] Image sizing normalized\n> Original image sizing declarations use ordinary responsive inline Markdown presentation; exact percentage sizing is not reproduced. Review placement and readability in each affected note, and adjust manually if desired. Images retain their original bytes and aspect ratio.\n\n"
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
        "schema_version": 7,
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
