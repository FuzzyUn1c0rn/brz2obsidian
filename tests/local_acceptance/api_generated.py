"""API-local generated representation proofs; no product modules are imported.

Format checks establish only a scalar's protocol role at its closed location.
They do not establish fingerprint truth, run history, or source normalization.
"""

import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import PurePosixPath
from uuid import UUID

from .api_manifest import read_json
from .api_note_text import (
    KINDS,
    callouts,
    contents,
    document_references,
    expected_document_text,
    insert_activity,
    markdown_lines,
    protect_cross_container_code,
    tables,
)
from .api_scope import strict
from .checker import contender_keys, escaped, wiki
from .support import check_support_content
from .text import literal_edits


def check_complete_shape(record):
    """Contract7 required/closed containers, fixed independently of output data."""
    envelope = {
        "schema",
        "schema_version",
        "converter_version",
        "renderer_version",
        "source_identity",
        "profile_id",
        "profile_version",
        "run_metadata",
        "item_targets",
        "asset_targets",
        "relationships",
        "tag_memberships",
        "classification_assignments",
        "source_gaps",
        "generated_presentations",
        "support_artifacts",
        "reserved_support_paths",
        "adaptations",
        "source_accounting",
        "issues",
        "counts",
        "obsidian_configuration",
        "obsidian_core_plugins_configuration",
        "obsidian_templates_configuration",
        "obsidian_property_types_configuration",
        "original_evidence",
    }
    assert type(record) is dict and set(record) == envelope, (
        "closed complete support record envelope"
    )
    identity = record["source_identity"]
    assert type(identity) is dict and set(identity) == {
        "source_id",
        "module_id",
        "module_version",
        "format_version",
        "source_sha256",
        "snapshot_digest",
    }, "closed complete source identity"
    shapes = {
        "item_targets": {
            "item_key",
            "original_identity",
            "original_title",
            "relative_path",
            "created",
            "creation_reasons",
            "vault_tag_token",
            "declared_appearance",
            "calendar_dates",
            "metadata_evidence",
            "icon_snapshot",
            "documents",
        },
        "asset_targets": {
            "asset_id",
            "owner",
            "naming_seed",
            "original_name",
            "display_name",
            "role",
            "availability",
            "actual_length",
            "actual_sha256",
            "external_uri",
            "video_presentation",
            "evidence",
            "relative_path",
            "resource_link",
            "source_findings",
            "retained_documents",
        },
        "relationships": {
            "key",
            "kind",
            "item_a",
            "item_b",
            "evidence",
            "target_a",
            "target_b",
            "presentation",
        },
    }
    for field, shape in shapes.items():
        assert type(record[field]) is list and all(
            type(row) is dict and set(row) == shape for row in record[field]
        ), "closed complete generated " + field


def checked_generated_regions(
    baseline,
    vault,
    record,
    scoped,
    thoughts,
    relationships,
    targets,
    assets,
    attachments,
    *,
    require_complete,
):
    """Return only complete proved generated regions; absent regions grant nothing."""
    check_protocol(record)
    bindings = {
        key: {
            "asset_id": key,
            "owner": row["sourceId"],
            "role": assets[key]["role"],
            "original_name": row["location"],
            "relative_path": assets[key]["relative_path"],
        }
        for key, row in attachments.items()
        if key in assets
    }
    references = {
        key: (
            note.owner,
            document_references(
                expected_document_text(note.scoped_text), note.owner, bindings
            ),
        )
        for key, note in scoped.safe_notes.items()
    }
    projection_fields = check_projection_protocol(
        baseline,
        record,
        scoped,
        thoughts,
        relationships,
        targets,
        assets,
        attachments,
        references,
    )
    support_present = bool(
        set(record) & {"support_artifacts", "reserved_support_paths"}
    ) or any(
        (vault / path).exists()
        for path in (
            "Vault guide.md",
            "MIGRATION REPORT.md",
            "Categories.md",
            ".obsidian",
            "Templates",
        )
    )
    assert support_present or not require_complete, (
        "required complete generated support envelope"
    )
    if not support_present:
        return set(), set(), projection_fields
    assert {
        "support_artifacts",
        "reserved_support_paths",
        "schema",
        "schema_version",
        "converter_version",
        "renderer_version",
        "run_metadata",
    } <= set(record), "complete generated support/protocol envelope"
    support, conditional = check_support(
        baseline, vault, record, thoughts, relationships, targets, assets, references
    )
    fields = {
        "support_artifacts",
        "reserved_support_paths",
        "obsidian_configuration",
        "obsidian_core_plugins_configuration",
        "obsidian_templates_configuration",
        "obsidian_property_types_configuration",
    }
    if require_complete:
        assert {
            "source_gaps",
            "generated_presentations",
            "adaptations",
            "counts",
        } <= set(record), "complete generated record obligations"
    for field in ("source_gaps", "generated_presentations"):
        if field in record:
            assert record[field] == [], (
                "API TXT absence cannot fabricate note/icon diagnostics"
            )
            fields.add(field)
    check_counts(record, thoughts, relationships, targets, assets, references, support)
    fields.add("counts")
    check_adaptation_records(
        record,
        baseline,
        scoped,
        thoughts,
        relationships,
        targets,
        assets,
        attachments,
        references,
    )
    fields.add("adaptations")
    warnings, findings = check_warning_records(
        record, baseline, scoped, targets, assets, attachments, references
    )
    fields.add("issues")
    check_complete_report(
        baseline,
        vault,
        record,
        scoped,
        thoughts,
        relationships,
        targets,
        assets,
        attachments,
        references,
        conditional,
        warnings,
        findings,
    )
    proved = set(support) - {"migration-record.json"}
    return fields, proved, projection_fields


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def formatting_observations(raw):
    """Recognize source-owned declarations with the independent note grammar."""
    _, edits = literal_edits(protect_cross_container_code(raw))
    text = raw
    for edit in reversed(edits):
        text = text[: edit["start"]] + edit["after"] + text[edit["end"] :]
    mask = insert_activity(text)
    observations, offset = [], 0

    def add(feature, declaration, change):
        observations.append(
            {
                "feature": feature,
                "declaration": declaration,
                "change": STATIC["GP07-LOSS-" + change],
            }
        )

    table_operations = []
    table_text = tables(text, table_operations)
    for line in markdown_lines(text):
        body = line.rstrip("\r\n")
        active = mask[offset : offset + len(body)]
        marker = re.fullmatch(
            r"( {0,3}(?:> ?)+)\[!([A-Za-z]+)([^\]]*)\]([+-]?)([^\r\n]*)", body
        )
        if marker and active[len(marker[1]) : len(marker[1]) + 2] == "[!":
            if marker[2].lower() not in KINDS:
                add("callout", body, "03")
            elif marker[3]:
                metadata = marker[3]
                icon = metadata.removeprefix("|icon:")
                emoji = (
                    metadata.startswith("|icon:")
                    and icon
                    and all(
                        not char.isspace()
                        and not char.isascii()
                        and char not in "|:[]\\`<>"
                        for char in icon
                    )
                )
                add("callout_icon", metadata, "04" if emoji else "05")
        elif re.match(r" {0,3}(?:> ?)+\[![A-Za-z]", active):
            add("callout", body, "12")
        starts = [
            match.start()
            for match in re.finditer(re.escape(":(table="), body)
            if active[match.start() : match.start() + 2] == ":("
            and (len(body[: match.start()]) - len(body[: match.start()].rstrip("\\")))
            % 2
            == 0
        ]
        if starts:
            declaration = body[starts[0] :]
            # A successful header operation owns this exact source line and
            # removes its terminal declaration. Sheltered spellings elsewhere
            # in the header are source content, not another active declaration.
            valid = any(
                begin == offset
                and end == offset + len(line)
                and not replacement.rstrip("\r\n").endswith(declaration)
                for begin, end, replacement in table_operations
            )
            add("table", body[starts[0] :], "01" if valid else "08")
        declaration = body.strip()
        if (
            re.fullmatch(r"\[/toc[^\]]*\]", declaration)
            and declaration != "[/toc/]"
            and active.lstrip().startswith("[/toc")
        ):
            add("table_of_contents", declaration, "10")
        offset += len(line)
    normalized = callouts(table_text)
    operations = []
    contents(normalized, operations)
    for begin, end, replacement in operations:
        before = normalized[begin:end].rstrip("\r\n")
        declared = re.search(r"\^[A-Za-z0-9-]+$", before)
        if declared and declared[0] not in replacement:
            add("table_of_contents", declared[0], "14")
    return observations


def check_warning_records(
    record, baseline, scoped, targets, assets, attachments, references
):
    expected, findings = (
        [],
        list(missing_findings(baseline, attachments, assets).values()),
    )
    for key, note in scoped.safe_notes.items():
        for observation in formatting_observations(note.scoped_text):
            findings.append(
                {
                    "rule_id": "local-api.note-formatting.v1",
                    "kind": "formatting_loss",
                    "affected": sorted([note.owner, key]),
                    "evidence": ["attachment:" + key],
                    "observed_json": observation,
                }
            )
    for key, (owner, refs) in sorted(references.items()):
        for index, ref in enumerate(refs):
            if ref["presentation_normalization"]:
                expected.append(
                    {
                        "code": "image_presentation_normalized",
                        "severity": "warning",
                        "phase": "analysis",
                        "message": STATIC["GP07-SIZING-01"]
                        + ref["presentation_normalization"]["declaration"]
                        + STATIC["GP07-SIZING-02"],
                        "guidance": STATIC["GP07-SIZING-00"],
                        "affected": [
                            owner,
                            key,
                            ref["target"],
                            "reference:" + key + ":" + str(index),
                        ],
                        "evidence": ["attachment:" + key],
                        "rule_id": None,
                        "leftover_path": None,
                    }
                )
    # Findings are canonical unordered source facts. Their shared rule/affected
    # order retains the separately canonical full-finding order for ties.
    findings.sort(
        key=lambda row: canonical_json(
            dict(row, observed_json=canonical_json(row["observed_json"]))
        ).encode("utf-8")
    )
    findings.sort(key=lambda row: (row["rule_id"], row["affected"]))
    for finding in findings:
        missing = finding["kind"] == "known_absent_payload"
        message, guidance = ("00", "01") if missing else ("02", "03")
        expected.append(
            {
                "code": "approved_source_gap" if missing else "formatting_loss",
                "severity": "warning",
                "phase": "analysis",
                "message": STATIC["GP05-WARNING-" + message]
                + STATIC["GP07-OBSERVED-00"]
                + canonical_json(finding["observed_json"]),
                "guidance": STATIC["GP05-WARNING-" + guidance],
                "affected": finding["affected"],
                "evidence": finding["evidence"],
                "rule_id": finding["rule_id"],
                "leftover_path": None,
            }
        )
    assert strict(record["issues"]) == strict(expected), (
        "closed source-bound warning census/observations"
    )
    return expected, findings


def check_complete_report(
    baseline,
    vault,
    record,
    scoped,
    thoughts,
    relationships,
    targets,
    assets,
    attachments,
    references,
    conditional,
    warnings,
    findings,
):
    names = {key: row["relative_path"] for key, row in targets.items()}
    linked = lambda key: wiki(names[key], thoughts[key]["name"])
    plain = lambda value: escaped(value).replace("\r", " ").replace("\n", " ")
    created = {key for key, row in targets.items() if row["created"]}
    present = sum(row["availability"] == "present" for row in assets.values())
    text = (
        STATIC["GP05-REPORT-00"]
        + STATIC["GP05-REPORT-04"]
        + str(len(created))
        + STATIC["GP05-REPORT-05"]
        + str(present)
        + STATIC["GP05-REPORT-06"]
    )
    documents = source_documents(record)
    edits = sum(len(row["text_adaptations"]) for row in documents.values())
    if edits:
        text += STATIC["GP05-REPORT-15"] + str(edits) + STATIC["GP05-REPORT-16"]
        owners = sorted(
            {
                note.owner
                for note in scoped.safe_notes.values()
                if expected_document_text(note.scoped_text) != note.scoped_text
            }
        )
        text += (
            "".join("- " + linked(key) + "\n" for key in owners if key in created)
            + "\n"
        )
    external = sum(row["type"] == 2 for row in attachments.values())
    if external:
        text += STATIC["GP05-REPORT-17"] + str(external) + STATIC["GP05-REPORT-18"]
    text += (
        STATIC["GP05-REPORT-01"] + STATIC["GP05-REPORT-02"] + STATIC["GP05-REPORT-03"]
    )
    if any(
        key in assets
        and assets[key]["availability"] == "present"
        and row["location"].lower().endswith(".pdf")
        for key, row in attachments.items()
    ):
        text += STATIC["GP05-REPORT-08"]
    missing = [
        finding for finding in findings if finding["kind"] == "known_absent_payload"
    ]
    if missing:
        brain = baseline.json(baseline.data["brain"])
        text += (
            STATIC["GP05-GAP-00"]
            + STATIC["GP05-GAP-01"]
            + STATIC["GP05-GAP-07"]
            + plain(brain["name"])
            + STATIC["GP05-GAP-08"]
            + plain(brain["id"])
            + STATIC["GP05-GAP-09"]
        )
        for finding in missing:
            key = finding["affected"][0]
            owner = attachments[key]["sourceId"]
            # Existing independent checker.py2394/2383-2387 literals, explicitly
            # qualified for reuse in GP07; whole source SHA25629e32b232c945aec6f306cff4b3e94ff745846ee503d88e6c3aa471bf175383f.
            title = (
                linked(owner)
                if owner in created
                else plain(thoughts[owner]["name"])
                + " (uncreated target: "
                + plain(names[owner])
                + ")"
            )
            text += (
                STATIC["GP05-GAP-10"]
                + title
                + STATIC["GP05-GAP-11"]
                + plain(owner)
                + STATIC["GP05-GAP-12"]
                + plain(key)
                + STATIC["GP05-GAP-13"]
                + assets[key]["role"]
                + STATIC["GP05-GAP-14"]
                + "metadata retained; bytes absent"
                + STATIC["GP05-GAP-15"]
            )
            text += (
                STATIC["GP05-GAP-17"]
                + plain(canonical_json(finding["observed_json"]))
                + STATIC["GP05-GAP-16"]
            )
    normalized = [
        (key, ref)
        for key, (_, refs) in sorted(references.items())
        for ref in refs
        if ref["presentation_normalization"]
    ]
    if normalized:
        text += STATIC["GP05-REPORT-10"]
        for key, ref in normalized:
            declaration = (
                ref["presentation_normalization"]["declaration"]
                .replace("`", "\\`")
                .replace("\r", " ")
                .replace("\n", " ")
            )
            text += (
                STATIC["GP05-REPORT-30"]
                + linked(scoped.safe_notes[key].owner)
                + STATIC["GP05-REPORT-29"]
                + declaration
                + STATIC["GP05-REPORT-27"]
            )
    if warnings:
        text += STATIC["GP05-REPORT-11"]
        for warning in warnings:
            affected = [
                linked(key) for key in sorted(created) if key in warning["affected"]
            ]
            text += (
                STATIC["GP05-REPORT-19"]
                + STATIC["GP05-REPORT-28"].join(affected)
                + STATIC["GP05-REPORT-20"]
                + warning["code"]
                + STATIC["GP05-REPORT-21"]
                + (warning["rule_id"] or "None")
                + STATIC["GP05-REPORT-22"]
                + plain(warning["message"])
                + STATIC["GP05-REPORT-23"]
                + warning["guidance"]
                + STATIC["GP05-REPORT-24"]
            )
    if any(row["kind"] in {"hierarchy", "related"} for row in relationships.values()):
        text += STATIC["GP05-REPORT-12"]
    for path, chunk in (
        ("Uncreated targets.md", "GP05-REPORT-13"),
        ("Tag memberships.md", "GP05-REPORT-14"),
    ):
        if conditional[path]:
            text += STATIC[chunk]
    assert (vault / "MIGRATION REPORT.md").read_bytes() == text.encode("utf-8"), (
        "closed source-derived complete report"
    )


def tag_tokens(thoughts):
    bases = {}
    for key, row in thoughts.items():
        if row["kind"] == 4:
            value = (
                re.sub(r"[\W_]+", "-", unicodedata.normalize("NFC", row["name"])).strip(
                    "-"
                )
                or "source-tag"
            )
            bases[key] = "tag-" + value if value.isnumeric() else value
    widths = dict.fromkeys(bases, 0)
    while True:
        result, groups = {}, defaultdict(list)
        for key, value in bases.items():
            suffix = "-" + key.replace("-", "")[: widths[key]] if widths[key] else ""
            stem = value[: 120 - len(suffix)].rstrip("-")
            if stem.isnumeric():
                stem = "tag-" + stem[: 116 - len(suffix)]
            result[key] = stem + suffix
            groups[result[key].casefold()].append(key)
        clashes = contender_keys(
            groups, widths, {key: key.replace("-", "") for key in bases}
        )
        if not clashes:
            return result
        for key in clashes:
            assert widths[key] < 32, "source tag token identity"
            widths[key] = widths[key] + 4 if widths[key] else 8


def missing_findings(baseline, attachments, assets):
    result = {}
    for key, row in attachments.items():
        if key not in assets or assets[key]["availability"] != "absent":
            continue
        pdfs = sorted(
            other
            for other, candidate in attachments.items()
            if candidate["sourceId"] == row["sourceId"]
            and candidate["type"] == 1
            and not candidate["isNotes"]
            and candidate["location"].lower().endswith(".pdf")
            and other in assets
            and assets[other]["availability"] == "present"
        )
        assert pdfs and baseline.data["payloads"][key]["status"] == 404, (
            "source-bound TXT finding"
        )
        observation = {
            "asset_id": key,
            "owner_id": row["sourceId"],
            "filename": row["location"],
            "retrieval": {"status": 404, "outcome": "missing_txt_404"},
            "preserved_same_owner_pdf_ids": pdfs,
        }
        result[key] = {
            "rule_id": "local-api.missing-txt-pdf.v1",
            "kind": "known_absent_payload",
            "affected": [key],
            "evidence": sorted(
                ["attachment:" + other for other in [key, *pdfs]]
                + ["scope:missing-txt404:" + key]
            ),
            "observed_json": observation,
        }
    return result


def check_projection_protocol(
    baseline,
    record,
    scoped,
    thoughts,
    relationships,
    targets,
    assets,
    attachments,
    references,
):
    tokens = tag_tokens(thoughts)
    home = baseline.json(baseline.data["brain"])["homeThoughtId"]
    classified = {
        row["item_b"]
        for row in relationships.values()
        if row["kind"] == "classification"
    }
    content = {
        note.owner
        for note in scoped.safe_notes.values()
        if expected_document_text(note.scoped_text).strip()
    }
    content.update(
        row["owner"]
        for row in assets.values()
        if row["availability"] == "external"
        and row["role"] in {"file", "url", "directory"}
        or row["availability"] == "present"
        and row["role"] in {"file", "image"}
        and row["actual_length"] > 0
    )
    item_fields = {
        "creation_reasons",
        "calendar_dates",
        "metadata_evidence",
        "vault_tag_token",
    }
    for key, target in targets.items():
        reasons = [
            reason
            for condition, reason in (
                (key in content, "content"),
                (key == home, "home"),
                (thoughts[key]["kind"] == 2, "definition"),
                (key in classified, "classification"),
            )
            if condition
        ]
        if not reasons and target["created"]:
            reasons = ["hierarchy"]
        calendar = {
            field: datetime.fromisoformat(thoughts[key][source]).date().isoformat()
            if thoughts[key].get(source)
            else None
            for field, source in (
                ("created", "creationDateTime"),
                ("updated", "modificationDateTime"),
            )
        }
        expected = {
            "creation_reasons": reasons,
            "calendar_dates": calendar if any(calendar.values()) else None,
            "metadata_evidence": ["thought:" + key],
            "vault_tag_token": tokens.get(key),
        }
        for field, value in expected.items():
            if field in target:
                assert strict(target[field]) == strict(value), (
                    "source-bound generated item projection"
                )
    findings = missing_findings(baseline, attachments, assets)
    asset_fields = {"naming_seed", "evidence", "video_presentation", "source_findings"}
    for key, asset in assets.items():
        expected = {
            "naming_seed": key.replace("-", ""),
            "evidence": ["attachment:" + key],
            "video_presentation": None,
        }
        for field, value in expected.items():
            if field in asset:
                assert strict(asset[field]) == strict(value), (
                    "source-bound generated asset projection"
                )
        if "source_findings" in asset:
            values = asset["source_findings"]
            assert type(values) is list and len(values) == int(key in findings), (
                "source-bound asset finding census"
            )
            for value in values:
                value = dict(value)
                value["observed_json"] = read_json(
                    value["observed_json"].encode("utf-8")
                )
                assert strict(value) == strict(findings[key]), (
                    "closed source-bound asset observation"
                )
    relation_fields = {"evidence", "target_a", "target_b", "presentation"}
    labels = {
        "hierarchy": "Parents/Children",
        "related": "Related",
        "tag": "native tags",
        "system": "retained_only",
        "classification": "linked category membership",
    }
    for row in record["relationships"]:
        source = relationships[row["key"]]
        expected = {
            "evidence": ["link:" + row["key"]],
            "target_a": targets[source["item_a"]]["relative_path"],
            "target_b": targets[source["item_b"]]["relative_path"],
            "presentation": labels[source["kind"]],
        }
        for field, value in expected.items():
            if field in row:
                assert strict(row[field]) == strict(value), (
                    "source-bound generated relationship projection"
                )
    return item_fields, asset_fields, relation_fields


def source_documents(record):
    return {
        row["key"]: row
        for target in record["item_targets"]
        for row in target["documents"]
    } | {
        row["key"]: row
        for target in record["asset_targets"]
        for row in target["retained_documents"]
    }


def check_counts(record, thoughts, relationships, targets, assets, references, support):
    created = {key for key, row in targets.items() if row["created"]}
    definitions = {key for key, row in thoughts.items() if row["kind"] == 2}
    tags = {key for key, row in thoughts.items() if row["kind"] == 4}
    assigned = [row for row in relationships.values() if row["kind"] == "tag"]
    classified = [
        row for row in relationships.values() if row["kind"] == "classification"
    ]
    present = sum(row["availability"] == "present" for row in assets.values())
    live = sum(len(refs) for owner, refs in references.values() if owner in created)
    native = sum(row["item_b"] in created for row in assigned)
    # Cardinality of independently validated source-bound edit representations;
    # no favored edit segmentation is inferred from source or declared counts.
    edits = sum(
        len(row["text_adaptations"]) for row in source_documents(record).values()
    )
    expected = {
        "image_presentation_normalizations": sum(
            bool(ref["presentation_normalization"])
            for _, refs in references.values()
            for ref in refs
        ),
        "text_adaptations": edits,
        "source_gaps": 0,
        "generated_presentations": 0,
        "planned_generated_embeds": 0,
        "actual_generated_embeds": 0,
        "source_items": len(thoughts),
        "source_relationships": len(relationships),
        "source_references": sum(len(refs) for _, refs in references.values()),
        "present_assets": present,
        "planned_notes": len(created),
        "planned_assets": present,
        "planned_references": live,
        "actual_notes": None,
        "actual_assets": None,
        "actual_files": None,
        "actual_references": live,
        "source_tags": len(tags),
        "tag_memberships": len(assigned),
        "native_tag_memberships": native,
        "uncreated_tag_memberships": len(assigned) - native,
        "created_tag_items": len(tags & created),
        "uncreated_tag_items": len(tags - created),
        "source_definitions": len(definitions),
        "classification_assignments": len(classified),
        "typed_members": len({row["item_b"] for row in classified}),
        "planned_category_notes": len(definitions & created),
        "actual_category_notes": None,
        "planned_support_files": len(support),
        "actual_support_files": None,
    }
    assert strict(record["counts"]) == strict(expected), (
        "closed independently derived counts"
    )


def check_adaptation_records(
    record,
    baseline,
    scoped,
    thoughts,
    relationships,
    targets,
    assets,
    attachments,
    references,
):
    expected = {}

    def add(kind, affected, description, **extra):
        expected[kind, affected] = {
            "kind": kind,
            "affected": affected,
            "description": description,
            "document_key": None,
            "owner": None,
            "evidence": [],
            "text_edit": None,
        } | extra

    home = baseline.json(baseline.data["brain"])["homeThoughtId"]
    for kind, target, index in (
        ("native_templates_configuration", ".obsidian/templates.json", 19),
        ("vault_maintenance_guide", "Vault guide.md", 20),
        ("categories_overview", home, 21),
        ("native_bases_configuration", ".obsidian/core-plugins.json", 22),
    ):
        add(kind, target, STATIC[f"GP07-DESCRIPTION-{index:02d}"])
    documents = source_documents(record)
    icons = {
        row["sourceId"]: key for key, row in attachments.items() if row["type"] == 5
    }
    providers = {
        row["item_b"]: row["item_a"]
        for row in relationships.values()
        if row["kind"] == "classification"
    }
    for key, target in targets.items():
        if PurePosixPath(target["relative_path"]).stem != thoughts[key]["name"]:
            add(
                "item_target",
                key,
                STATIC["GP07-DESCRIPTION-07"] + target["relative_path"],
            )
        if not target["created"]:
            continue
        add("canonical_properties", key, STATIC["GP07-DESCRIPTION-16"])
        if thoughts[key].get("creationDateTime") or thoughts[key].get(
            "modificationDateTime"
        ):
            add("source_calendar_dates", key, STATIC["GP07-DESCRIPTION-14"])
        if (
            icons.get(key)
            or thoughts[key]["foregroundColor"]
            or thoughts[key]["backgroundColor"]
        ):
            add("declared_appearance", key, STATIC["GP07-DESCRIPTION-10"])
        if thoughts[key]["kind"] == 2:
            add("category_dashboard", key, STATIC["GP07-DESCRIPTION-26"])
            add("category_template", key, STATIC["GP07-DESCRIPTION-23"])
        else:
            effective = icons.get(key) or icons.get(providers.get(key))
            if effective:
                suffix = (
                    STATIC["GP07-DESCRIPTION-18"]
                    if icons.get(key)
                    else STATIC["GP07-DESCRIPTION-25"]
                    + providers[key]
                    + STATIC["GP07-DESCRIPTION-24"]
                )
                add(
                    "body_icon_snapshot",
                    key,
                    STATIC["GP07-DESCRIPTION-17"]
                    + effective
                    + suffix
                    + STATIC["GP07-DESCRIPTION-11"],
                )
    for key, relation in relationships.items():
        if relation["kind"] in {"hierarchy", "related"}:
            label = (
                STATIC["GP07-DESCRIPTION-12"]
                if relation["kind"] == "hierarchy"
                else STATIC["GP07-DESCRIPTION-13"]
            )
            add(
                "relationship_presentation",
                key,
                STATIC["GP07-DESCRIPTION-08"] + label + STATIC["GP07-DESCRIPTION-04"],
            )
    for key, (owner, refs) in references.items():
        for index, ref in enumerate(refs):
            affected = "reference:" + key + ":" + str(index)
            if targets[owner]["created"]:
                add(
                    ref["kind"] + "_reference",
                    affected,
                    STATIC["GP07-DESCRIPTION-05"]
                    + ref["target"]
                    + STATIC["GP07-DESCRIPTION-03"],
                )
            if ref["presentation_normalization"]:
                add(
                    "image_presentation",
                    affected,
                    STATIC["GP07-DESCRIPTION-29"]
                    + ref["presentation_normalization"]["declaration"]
                    + STATIC["GP07-DESCRIPTION-28"],
                    owner=owner,
                    document_key=key,
                    evidence=["attachment:" + key],
                )
        for index, edit in enumerate(documents[key]["text_adaptations"]):
            add(
                edit["kind"],
                "text:" + key + ":" + str(index),
                STATIC["GP07-DESCRIPTION-27"],
                owner=owner,
                document_key=key,
                evidence=["attachment:" + key],
                text_edit=edit,
            )
    actual = {(row["kind"], row["affected"]): row for row in record["adaptations"]}
    assert len(actual) == len(record["adaptations"]) and strict(actual) == strict(
        expected
    ), "closed source-bound generated adaptation census/content"


def check_support(
    baseline, vault, record, thoughts, relationships, targets, assets, references
):
    """Prove complete support ownership and stock configuration from source roles.

    Target/path/materialization and references arrive only after their independent
    raw-source audits. A record's support declaration never decides this census.
    """
    names = {key: row["relative_path"] for key, row in targets.items()}
    created = {key for key, row in targets.items() if row["created"]}
    definitions = {key for key, row in thoughts.items() if row["kind"] == 2}
    represented, pairs = set(), set()
    for relation in relationships.values():
        a, b = relation["item_a"], relation["item_b"]
        if relation["kind"] in {"hierarchy", "related", "tag"}:
            represented.update((a, b))
        if relation["kind"] == "related" and not {a, b} & created:
            pairs.add(tuple(sorted((a, b))))
    for owner, refs in references.values():
        if owner in created:
            represented.update(ref["target"] for ref in refs if ref["kind"] == "item")
    isolated = sorted(
        key
        for key, row in thoughts.items()
        if row["kind"] == 1 and key not in created | represented
    )
    listing = ""
    if isolated or pairs:
        listing = "# Uncreated targets\n\n"
        if isolated:
            listing += (
                "## Isolated thoughts\n\n"
                + "".join(
                    "- " + wiki(names[key], thoughts[key]["name"]) + "\n"
                    for key in isolated
                )
                + "\n"
            )
        if pairs:
            listing += "## Related pairs\n\n" + "".join(
                "- "
                + wiki(names[a], thoughts[a]["name"])
                + " — "
                + wiki(names[b], thoughts[b]["name"])
                + "\n"
                for a, b in sorted(pairs)
            )
        listing = listing.rstrip("\n") + "\n"
    tokens = tag_tokens(thoughts)
    tag_rows = [
        {
            "tag_key": row["item_a"],
            "item_key": row["item_b"],
            "native": row["item_b"] in created,
            "token": tokens[row["item_a"]],
        }
        for row in relationships.values()
        if row["kind"] == "tag"
    ]
    tags = {key for key, row in thoughts.items() if row["kind"] == 4}
    focused = sorted(
        key
        for key in tags
        if not any(row["tag_key"] == key for row in tag_rows)
        or any(row["tag_key"] == key and not row["native"] for row in tag_rows)
    )
    tag_listing = ""
    if focused:
        tag_listing = "# Tag memberships\n\nAssignments on uncreated targets and source tags without assignments. Use native tag search for created assigned notes.\n\n"
        for key in focused:
            tag_listing += (
                "## #"
                + tokens[key]
                + "\n\nSource tag: "
                + wiki(names[key], thoughts[key]["name"])
                + "\n\n"
            )
            hidden = sorted(
                {
                    row["item_key"]
                    for row in tag_rows
                    if row["tag_key"] == key and not row["native"]
                }
            )
            tag_listing += (
                "".join(
                    "- " + wiki(names[item], thoughts[item]["name"]) + "\n"
                    for item in hidden
                )
                + "\n"
                if hidden
                else "No source assignments.\n\n"
            )
        tag_listing = tag_listing.rstrip("\n") + "\n"
    support = {
        ".obsidian/app.json": "configuration",
        ".obsidian/bookmarks.json": "configuration",
        ".obsidian/core-plugins.json": "configuration",
        ".obsidian/templates.json": "configuration",
        ".obsidian/types.json": "configuration",
        "Categories.md": "overview",
        "Vault guide.md": "guide",
        "MIGRATION REPORT.md": "report",
        "migration-record.json": "migration_record",
        "Templates/New note.md": "template",
        "Templates/Category starter.md": "starter",
        "Templates/Member template starter.md": "starter",
        "Templates/Bases/Members.base": "base",
        "Templates/Bases/Gallery.base": "base",
        "Templates/Bases/Categories.base": "base",
        "Templates/Bases/Starter.base": "starter",
    }
    support.update(
        {
            "Templates/" + PurePosixPath(names[key]).name: "template"
            for key in definitions
        }
    )
    conditional = {"Uncreated targets.md": listing, "Tag memberships.md": tag_listing}
    support.update({path: "listing" for path, text in conditional.items() if text})
    declared = record["support_artifacts"]
    assert type(declared) is list and all(
        type(row) is dict and set(row) == {"relative_path", "purpose"}
        for row in declared
    ), "closed support associations"
    assert (
        len(declared) == len(support)
        and {row["relative_path"]: row["purpose"] for row in declared} == support
    ), "source-derived complete support census"
    inactive = {path for path, text in conditional.items() if not text}
    assert (
        type(record["reserved_support_paths"]) is list
        and len(record["reserved_support_paths"]) == len(inactive)
        and set(record["reserved_support_paths"]) == inactive
    ), "source-derived support reservations"
    payloads = {
        row["relative_path"]
        for row in assets.values()
        if row["availability"] == "present"
    }
    expected = set(support) | {names[key] for key in created} | payloads
    assert len(expected) == len(support) + len(created) + len(payloads), (
        "unique source/support path ownership"
    )
    actual = {
        path.relative_to(vault).as_posix()
        for path in vault.rglob("*")
        if path.is_file()
    }
    assert actual == expected, "complete actual source/support file census"
    for path, text in conditional.items():
        if text:
            assert (vault / path).read_bytes() == text.encode("utf-8"), (
                "closed conditional support listing"
            )
    assert (
        vault / "Categories.md"
    ).read_bytes() == b"# Categories\n\n![[Templates/Bases/Categories.base]]\n", (
        "closed categories overview"
    )
    home = baseline.json(baseline.data["brain"])["homeThoughtId"]
    configurations = {
        ".obsidian/app.json": (
            "obsidian_configuration",
            {
                "showInlineTitle": False,
                "defaultViewMode": "preview",
                "newFileLocation": "folder",
                "newFileFolderPath": "Notes",
                "useMarkdownLinks": False,
                "newLinkFormat": "absolute",
                "openBehavior": "file:" + names[home],
                "alwaysUpdateLinks": True,
                "attachmentFolderPath": "Attachments",
            },
        ),
        ".obsidian/core-plugins.json": (
            "obsidian_core_plugins_configuration",
            dict.fromkeys(
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
            ),
        ),
        ".obsidian/templates.json": (
            "obsidian_templates_configuration",
            {"folder": "Templates", "dateFormat": "YYYY-MM-DD"},
        ),
        ".obsidian/types.json": (
            "obsidian_property_types_configuration",
            {
                "types": {
                    "categories": "multitext",
                    "appearance_category": "text",
                    "icon": "text",
                    "created": "date",
                    "updated": "date",
                    "tags": "tags",
                    "aliases": "aliases",
                    "source_collection_id": "text",
                    "source_item_id": "text",
                }
            },
        ),
    }
    for path, (field, value) in configurations.items():
        assert strict(read_json((vault / path).read_bytes())) == strict(
            value
        ) and strict(record[field]) == strict(value), "closed support configuration"
    bookmarks = {
        "items": [
            {
                "type": "file",
                "ctime": record["run_metadata"]["bookmark_time"],
                "path": names[home],
                "title": "Home",
            }
        ]
    }
    assert strict(
        read_json((vault / ".obsidian/bookmarks.json").read_bytes())
    ) == strict(bookmarks), "closed source/protocol bookmark"
    check_support_content(vault, names, definitions)
    mappings = [
        "- [[Templates/"
        + PurePosixPath(names[key]).name
        + "]] → [["
        + names[key]
        + "]]"
        for key in sorted(definitions)
    ]
    guide = (
        STATIC["GP05-GUIDE-00"]
        + STATIC["GP05-GUIDE-02"]
        + ("\n".join(mappings) + "\n" if mappings else STATIC["GP05-GUIDE-03"])
    )
    assert (vault / "Vault guide.md").read_bytes() == guide.encode("utf-8"), (
        "closed source-derived complete guide"
    )
    return support, conditional


def check_protocol(record):
    """Check present protocol envelopes before their exact locations are trusted."""
    for name, expected in (("schema", "brz2obsidian.migration"), ("schema_version", 7)):
        if name in record:
            assert type(record[name]) is type(expected) and record[name] == expected, (
                "generated protocol schema"
            )
    identity = record["source_identity"]
    assert type(identity) is dict and set(identity) <= {
        "module_id",
        "module_version",
        "format_version",
        "source_id",
        "source_sha256",
        "snapshot_digest",
    }, "closed generated source identity"
    for name in ("source_sha256", "snapshot_digest"):
        if name in identity:
            assert type(identity[name]) is str and re.fullmatch(
                r"[0-9a-f]{64}", identity[name]
            ), "generated digest representation"
    if "converter_version" in record:
        assert type(record["converter_version"]) is str and re.fullmatch(
            r"[0-9]+\.[0-9]+\.[0-9]+(?:[.+-][0-9A-Za-z.-]+)?",
            record["converter_version"],
        ), "generated converter version"
    if "renderer_version" in record:
        assert record["renderer_version"] == "7", "generated renderer version"
    if "run_metadata" not in record:
        return
    run = record["run_metadata"]
    required = {
        "converter_version",
        "renderer_version",
        "run_id",
        "run_time",
        "obsidian_version",
        "bookmark_time",
    }
    assert type(run) is dict and required <= set(run) <= required | {
        "source_acquisition"
    }, "closed generated run metadata"
    assert run["converter_version"] == record.get("converter_version") and run[
        "renderer_version"
    ] == record.get("renderer_version"), "generated run version binding"
    assert type(run["run_id"]) is str, "generated run identity"
    try:
        parsed = UUID(run["run_id"])
    except ValueError as error:
        raise AssertionError("generated run identity") from error
    assert str(parsed) == run["run_id"] and parsed.int, "generated run identity"
    stamp = run["run_time"]
    assert type(stamp) is str and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-5][0-9](?:\.[0-9]{1,7})?(?:Z|[+-](?:0[0-9]|1[0-4]):[0-5][0-9])",
        stamp,
    ), "generated run timestamp"
    try:
        parsed_date = datetime.fromisoformat(stamp)
    except ValueError as error:
        raise AssertionError("generated run calendar") from error
    assert (
        parsed_date.year > 1 and abs(parsed_date.utcoffset().total_seconds()) <= 50400
    ), "generated run calendar"
    assert type(run["obsidian_version"]) is str and re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+(?:[.+-][0-9A-Za-z.-]+)?", run["obsidian_version"]
    ), "generated Obsidian version"
    assert type(run["bookmark_time"]) is int and run["bookmark_time"] >= 0, (
        "generated bookmark timestamp"
    )
    if "source_acquisition" in run:
        check_acquisition_protocol(run["source_acquisition"], identity["source_id"])


def check_acquisition_protocol(value, collection):
    """Normative capture audit representation, not request-history truth.

    docs/local-api-capture.md104-108 defines these closed protocol locations.
    Source preservation is independently checked from the baseline; this proof
    does not assert audit completeness or reproduce an integrity digest.
    """
    assert type(value) is dict and set(value) == {"audit", "integrity_sha256"}, (
        "closed acquisition wrapper"
    )
    assert type(value["integrity_sha256"]) is str and re.fullmatch(
        r"[0-9a-f]{64}", value["integrity_sha256"]
    ), "acquisition integrity representation"
    audit = value["audit"]
    assert type(audit) is dict and set(audit) == {
        "atomic",
        "method",
        "started_at",
        "finished_at",
        "limits",
        "requests",
        "consistency_limits",
    }, "closed acquisition audit"
    assert (
        audit["atomic"] is False and audit["method"] == "bounded-read-only-local-api"
    ), "acquisition protocol method"
    assert audit["consistency_limits"] == [
        "non-atomic-multi-request",
        "captured-copy-integrity-only",
        "empirical-discovery-no-completeness-guarantee",
    ], "acquisition limits disclosure"

    def timestamp(text):
        assert type(text) is str and re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-5][0-9]\.[0-9]{6}Z", text
        ), "acquisition timestamp representation"
        try:
            result = datetime.fromisoformat(text)
        except ValueError as error:
            raise AssertionError("acquisition timestamp calendar") from error
        assert result.year > 1, "acquisition timestamp calendar"
        return result

    start, finish = timestamp(audit["started_at"]), timestamp(audit["finished_at"])
    assert start <= finish, "acquisition interval"
    limits = audit["limits"]
    assert type(limits) is dict and set(limits) == {
        "initial_search_results",
        "search_budget_ms",
        "search_max_response_bytes",
        "max_search_results",
        "request_timeout_ms",
        "max_response_bytes",
        "max_total_capture_bytes",
        "max_requests",
        "max_traversal_items",
        "max_payload_bytes",
    }, "closed acquisition bounds"
    assert all(
        key == "max_search_results"
        and number is None
        or type(number) is int
        and number > 0
        for key, number in limits.items()
    ), "acquisition bound representations"
    assert type(audit["requests"]) is list, "acquisition request collection"
    prior = start
    for index, request in enumerate(audit["requests"], 1):
        assert type(request) is dict and set(request) == {
            "sequence",
            "operation",
            "brain_id",
            "subject_id",
            "status",
            "outcome",
            "started_at",
            "finished_at",
            "actual_length",
        }, "closed acquisition request"
        assert type(request["sequence"]) is int and request["sequence"] == index, (
            "acquisition request sequence"
        )
        assert request["brain_id"] == collection, "acquisition collection binding"
        operation = request["operation"]
        assert operation in {
            "brain",
            "statistics",
            "search",
            "types",
            "tags",
            "thought",
            "graph",
            "link",
            "attachments",
            "note",
            "attachment-content",
        }, "acquisition operation enum"
        subject = request["subject_id"]
        if subject is not None:
            assert type(subject) is str, "acquisition subject representation"
            try:
                parsed = UUID(subject)
            except ValueError as error:
                raise AssertionError("acquisition subject representation") from error
            assert str(parsed) == subject and parsed.int, (
                "acquisition subject representation"
            )
        assert type(request["status"]) is int and (
            request["status"],
            request["outcome"],
        ) in {
            (200, "success"),
            (400, "tag_inventory_zero_exception"),
            (404, "missing_txt_404"),
        }, "acquisition HTTP/outcome protocol"
        if request["status"] == 400:
            assert operation == "tags", "acquisition tag400 protocol"
        elif request["status"] == 404:
            assert operation == "attachment-content", "acquisition TXT404 protocol"
        assert (
            type(request["actual_length"]) is int and request["actual_length"] >= 0
        ), "acquisition length representation"
        began, ended = (
            timestamp(request["started_at"]),
            timestamp(request["finished_at"]),
        )
        assert start <= prior <= began <= ended <= finish, (
            "acquisition request interval"
        )
        prior = began


# Prior C4 static-reference author /root/baseline_owner_resume; qualifier /root/reviewer_resume.
# GP05 proposal SHA256 4ea3a44e7545daf1c675ff8e41288bf57c0817f15b77a79ca9644c9607b43e95
# Qualification SHA256 225304632f6e5877123d269b70d6d5fa8a695662c3d781e233b2b50808baeeee
# Exact approved stock literals only; no runtime dependency on ignored evidence.
STATIC = {
    "GP05-GUIDE-00": '# Vault guide\n\n## Imported Markdown inserts\n\nGenerated tables of contents are static links to the authored headings. Their\nblock IDs distinguish repeated headings and Unicode or punctuation labels.\nAfter heading edits, update the list and retain its destination block IDs, or\nedit the links manually; there is no automatic ToC maintenance.\n\nReviewed source tables become ordinary editable Markdown tables. Native layout\nis responsive; source column widths and justification remain in the migration\nrecord and are not reproduced. Table link aliases use native pipe escaping;\ncode spans containing pipes use narrowly generated, escaped code elements so\nthe displayed code and cells remain intact. Review disclosed malformed tables before\nediting their cell structure.\n\nAll 13 standard source callout types use their corresponding native Obsidian\ncolours and icons. Consecutive callouts become separate panels; titles, folding\nand nested bodies remain editable. Authored emoji icons appear in the title,\nalongside Obsidian\'s native icon. This is a visible fallback, not an icon\nreplacement. Unsupported icon declarations remain visible with warnings.\nNo community plugin, generated CSS or custom standard icon assets are required.\nCompatible mathematics is retained. The Migration report links affected notes;\nthe migration record retains exact declarations and adaptation edits, and safe\noriginal note bytes remain under Attachments.\n\n## Find and create an object\n\nBefore creating a note, look up existing names and aliases using Search or the\nQuick switcher. Reuse an existing entity when appropriate; matching titles alone\ndo not prove identity. Imported source_collection_id and source_item_id form a\nstable pair and must survive native renames. New objects omit both source IDs.\n\nCreate a suitably named note, switch to Editing view, run **Templates: Insert template**,\nand choose the full template for its category, or [[Templates/New note.md]]\nfor an unclassified object. The configured Templates folder is Templates; nested\n.base files are views, not Markdown templates. Native Templates resolves title\nand date variables on insertion. Both dates begin on the insertion day, not the\nconversion day. Maintain updated explicitly after later meaningful edits.\n\nKeep template date variables quoted as literal strings, for example\ncreated: "{{date:YYYY-MM-DD}}". Native Templates still inserts the date; quoting\nalso protects the variable when Obsidian rewrites YAML during link updates.\n\nA full category template initializes linked categories and appearance_category;\nthe optional icon override stays blank. Templates initialize structure rather\nthan enforcing a continuing schema. Selecting a category in a property does not\nselect or apply a template, and Base queries discover membership independently.\n\n## Maintain existing notes\n\nOn existing notes, edit categories directly using the Properties editor or\nfrontmatter. Adding or reordering memberships preserves established dates,\ncontent, provider and imported identity. Full native templates can replace shared\nscalar properties, including dates and the provider; use them for new notes.\nThere are no additive category-only templates or promises of overwrite protection.\n\nIn the reviewed Obsidian build, saving a Properties edit normalized existing\nCRLF line endings to LF without changing authored text. Keep the pristine\nconverter output and original note backups when exact pre-edit bytes matter.\nManual editor saves are separate from the converter\'s byte-preservation checks.\n\nChoose appearance_category explicitly from memberships, independently of\nmembership order. Empty means no inheritance. A populated invalid/nonmember\nprovider shows Invalid provider; it never selects a substitute. A valid local\nicon override wins even with an empty or invalid provider. Otherwise dashboards\nuse the valid provider\'s current local image. Category changes do not rewrite\nordinary/member body-icon snapshots; those image references are separately editable. Declared\nsource colours remain in migration-record.json without vault colour properties\nor the decorative Appearance display.\n\nWhen a source category icon is absent, its icon property is empty and inheriting\nmembers keep their categories and appearance_category links with neutral\nappearance. A valid explicit member icon still wins. Add a valid local image to\nthe category\'s icon property to supply future dashboard defaults. The Migration\nreport identifies the missing provider and affected included members separately.\nMissing source category text remains unknown; its notice does not reconstruct a\nbody from images or declared length. Source repair and re-export are optional.\n\nImported created/updated are source creation/overall-modification calendar dates,\nwithout timezone conversion. Full timestamps remain in migration-record.json.\nAn ordinary manual membership edit does not automatically change updated.\n\n## Canonical properties and relationships\n\n| Property | Meaning |\n| --- | --- |\n| categories | List of links to category notes; empty is valid. |\n| appearance_category | Optional single category link also in categories. |\n| icon | Optional single link to a local image; category default or member override. |\n| created, updated | Optional ISO calendar dates; new templates initialize insertion day. |\n| tags, aliases | Native lists; source tags are distinct from categories. |\n| source_collection_id, source_item_id | Paired opaque imported identity; absent for new objects. |\n\nReference another meaningful entity through an Obsidian link instead of duplicating\nits information. Before adding a property, reuse the existing canonical vocabulary\nor document a deliberate extension with its meaning and cardinality. Custom future\nvocabulary is allowed; do not infer domain fields from prose or casually introduce\nsynonyms. Semantic relationships belong in properties/links, not folder nesting.\nKeep notes human-readable and preserve their authored content.\n\n## Browse and extend categories\n\nOpen [[Categories.md]] from Home, then open the category dashboard for its Members\ntable and Gallery after the title and any Parents/Children navigation.\nEvery direct included parent is linked; hierarchy does not create membership.\nCategory notes have no generated\nintroductory icon image; their icon property still supplies dashboard images.\nRetained source labels, authored text/images, resources and Related links follow\nthe Bases. Ordinary/member notes keep their separately editable body snapshots.\nA standalone contextual Base has no selected embedding\ncategory. Discovery follows linked membership, with Templates and Attachments\nexcluded; filenames containing Template remain valid members. Category role uses\nthe Categories folder and native categories tag. Members can live in Notes or\nother ordinary areas; folders are not their type system.\n\nFor a future category such as Experiments:\n\n1. Create Categories/Experiments.md, switch to Editing view, and insert\n   [[Templates/Category starter.md]]. It initializes the categories role tag,\n   insertion dates and contextual Members/Gallery embeds. Add an optional local\n   icon by linking an image under Attachments.\n2. A handwritten new note can already join it without inserting a member template.\n   Use the following properties; leave the provider empty to opt out instead:\n\n```yaml\ncategories:\n  - "[[Categories/Experiments]]"\nappearance_category: "[[Categories/Experiments]]"\n```\n\n3. Duplicate [[Templates/Member template starter.md]] as Templates/Experiments.md.\n   Edit its categories/provider to the existing category links shown above. Keep\n   the insertion variables literal in the template. Select that full template\n   manually when creating another new object. The unadapted starter leaves\n   categories/provider empty, so it has no dangling example references.\n4. Reuse Members/Gallery, or copy [[Templates/Bases/Starter.base]] under\n   Templates/Bases with a distinct name and customize its view. Embed it in the\n   category dashboard, retaining list(categories).contains(this) for contextual\n   membership. The Base starter already uses Icon before Note and excludes the\n   operational support areas. No template/base/vault_role registry is needed.\n\nUse Obsidian\'s native rename with automatic link updates enabled. Qualified\ncategory/member-template links may become shorter unambiguous links. Contextual\nmember queries follow the renamed dashboard; source IDs remain unchanged. Prefer\nqualified links when similarly named targets are ambiguous.\n\n## Check current vault conventions\n\nFrom the installed converter environment, run these read-only commands with\nthis vault\'s folder path:\n\n```text\nbrz2obsidian check-vault "C:/vaults/this-vault"\nbrz2obsidian check-vault "C:/vaults/this-vault" --json\n```\n\nPython callers use brz2obsidian.vault_check.check_vault(vault). The checker reads\nactual current notes, properties, Bases and required local-image references;\nit needs no source archive or migration-record.json and never repairs files.\nCustom properties, template date variables and intentional uncreated ordinary\ntargets are allowed. Required category/provider/media links must resolve\nunambiguously; blank appearance providers opt out. Results are clean/issues/failed\nwith command exits 0/2/1 and a separate version-1 brz2obsidian.vault-check JSON\nenvelope. Read failures retain other readable-note diagnostics and unavailable\nmeasurements are null. This checks structural conventions, not Base formula\nexecution, native rendering or continuing date maintenance. A clean editable\nvault does not replace the independent migration source-preservation audit.\n\n## Reference adaptations and migration limits\n\nThis follows kepano\'s real vault: manual full-template selection, linked category\nproperties, independent native Bases and embeds in category-note bodies. It adapts\nthat pattern using faithful imported names, complete typed membership, explicit\nicon providers, qualified collision-safe links, operational folder exclusions and\ncontextual queries that survive native category renames. It adds the canonical\ncore, quoted date variables that survive native link updates and explicit\nupdate-date maintenance; it does not clone reference domain\nproperties, unrelated plugin toggles, styling or community plugins.\n\nThe original Home/bookmark, source content/resources, source tags and graph links\nremain available. [[MIGRATION REPORT.md]] explains preserved material, source\nwarnings and resource limits, including PDF Search and remote/offline video\navailability. migration-record.json is migration evidence, not current editable\nstate. Conversion is a one-time fresh-vault operation, not synchronization.\n',
    "GP05-GUIDE-01": "]]",
    "GP05-GUIDE-02": "\n## Imported category templates\n\n",
    "GP05-GUIDE-03": "This source has no imported categories; use the generic template and future-category recipe.\n",
    "GP05-GUIDE-05": "\n",
    "GP05-GUIDE-06": "]] → [[",
    "GP05-GUIDE-07": "- [[",
    "GP05-GUIDE-08": "\n",
    "GP05-REPORT-00": "# Migration report\n\nOpen the root Home note to begin. Safe original note bytes are retained under Attachments. Forgotten thoughts are excluded by default; unsafe originals and unscopable history are omitted. Counts describe included scope.\n\n",
    "GP05-REPORT-01": "Unsupported feature classes are refused explicitly.\n",
    "GP05-REPORT-02": "\n[[Vault guide.md|Vault guide]] explains manual full-template selection for new objects, direct membership edits on existing notes, canonical properties and future-category starters. Bundled Templates is configured for insertion-day ISO dates; update dates are maintained explicitly.\n",
    "GP05-REPORT-03": "\nOpen [[Categories.md|Categories]] from Home, then a category dashboard for its native Members table and Gallery after the title and any Parents/Children navigation, without a generated introductory category image. Retained source content and resources follow the Bases; category icon properties remain available for dashboard images. These contextual Bases use the embedding category and follow link-preserving category renames; a standalone member Base has no category context. Edit categories to change membership and appearance_category to choose a member's icon provider independently of membership order. A valid local icon override wins, an empty provider opts out, and an invalid provider is shown without selecting a substitute. Category icon edits update inherited dashboard images; ordinary/member note-body image references remain separately editable migration-time snapshots. Declared colours remain in migration-record.json only. Bundled Bases and link updates are configured.\n",
    "GP05-REPORT-04": "Created ",
    "GP05-REPORT-05": " thought notes; preserved ",
    "GP05-REPORT-06": " present payloads.\n\n",
    "GP05-REPORT-07": "\n",
    "GP05-REPORT-08": "\nPDF files are preserved and can be opened in Obsidian. Vault Search does not search PDF body text; this conversion does not extract or index it, or reproduce TheBrain's PDF body search.\n",
    "GP05-REPORT-09": "\nVideo playback depends on the remote service and network. Offline playback and service availability are not guaranteed. The original resource links remain available; no remote video bytes were archived or downloaded by this conversion.\n",
    "GP05-REPORT-10": "\n> [!warning] Image sizing normalized\n> Original image sizing declarations use ordinary responsive inline Markdown presentation; exact percentage sizing is not reproduced. Review placement and readability in each affected note, and adjust manually if desired. Images retain their original bytes and aspect ratio.\n\n",
    "GP05-REPORT-11": "\n## Source warnings\n\n",
    "GP05-REPORT-12": "\nRelationships use simple Parents, Children and Related links. Original arrows and one-way visibility details remain in the migration record.\n",
    "GP05-REPORT-13": "\n[[Uncreated targets.md|Uncreated targets]] lists otherwise unrepresented empty thoughts and Related pairs.\n",
    "GP05-REPORT-14": "\n[[Tag memberships.md|Tag memberships]] lists assignments on uncreated targets and source tags without assignments.\n",
    "GP05-REPORT-15": "Applied ",
    "GP05-REPORT-16": " exact text adaptations for Markdown display, including literal escaping and insert normalization where present. Exact edits in migration-record.json use scoped source Unicode codepoint offsets before adaptation, with a scoped source digest; reference spans use adapted document text offsets and digest. Safe originals retain exact source bytes. Generated ToCs are static: update their links and heading block IDs after heading edits. Native callouts retain Obsidian's colours and icons; authored icon metadata uses a visible title fallback.\n\n",
    "GP05-REPORT-17": "Retained ",
    "GP05-REPORT-18": " external file references as ordinary Resources links. Their original locations remain in migration-record.json. External targets were not checked, opened or copied; historical lengths do not establish accessibility.\n\n",
    "GP05-REPORT-19": "- ",
    "GP05-REPORT-20": " — ",
    "GP05-REPORT-21": " (",
    "GP05-REPORT-22": "): ",
    "GP05-REPORT-23": " ",
    "GP05-REPORT-24": "\n",
    "GP05-REPORT-25": "\n",
    "GP05-REPORT-26": "- ",
    "GP05-REPORT-27": "`; exact declaration, scoped document codepoint span/digest and original reference remain in migration-record.json.\n",
    "GP05-REPORT-28": ", ",
    "GP05-REPORT-29": ": `",
    "GP05-REPORT-30": "- ",
    "GP05-GAP-00": "\n## Source-gap evidence and optional repair checklist\n\n",
    "GP05-GAP-01": "Conversion used captured source material only. Optionally locate the thought by title/ID, restore missing content in the source and convert the updated source into a fresh vault. Unknown prose, captions and layout were not recovered.\n\n",
    "GP05-GAP-02": "Source fingerprint: ",
    "GP05-GAP-03": "; scoped digest: ",
    "GP05-GAP-04": "; collection: ",
    "GP05-GAP-05": " (",
    "GP05-GAP-06": ").\n\n",
    "GP05-GAP-07": "Collection: ",
    "GP05-GAP-08": " (",
    "GP05-GAP-09": "); fingerprint and scoped digest are recorded in migration-record.json.\n\n",
    "GP05-GAP-10": "- [ ] ",
    "GP05-GAP-11": "; thought ID ",
    "GP05-GAP-12": "; attachment ",
    "GP05-GAP-13": "; role ",
    "GP05-GAP-14": "; outcome ",
    "GP05-GAP-15": ".\n",
    "GP05-GAP-16": "\n",
    "GP05-GAP-17": "  Declaration and unavailable bytes: ",
    "GP05-GAP-18": ".\n",
    "GP05-GAP-19": "  Affected included members (",
    "GP05-GAP-20": "):\n",
    "GP05-GAP-21": "]]\n",
    "GP05-GAP-22": "  Provider: ",
    "GP05-GAP-23": "\n",
    "GP05-GAP-24": ": [[",
    "GP05-GAP-25": "; thought ID ",
    "GP05-GAP-26": "  - Image ",
    "GP05-GAP-27": "  - ",
    "GP05-WARNING-00": "A qualified non-note TXT could not be retrieved (HTTP404); same-owner PDF bytes were preserved.",
    "GP05-WARNING-01": "Review the missing TXT declaration and preserved PDF separately; no equivalence is claimed.",
    "GP05-WARNING-02": "Included thought-note formatting uses a reviewed visible fallback.",
    "GP05-WARNING-03": "Review exact formatting adaptations and preserved source bytes in the Migration report.",
}


# GP07 stock-reference qualifier /root/reviewer_resume, qualification SHA256
# 2ddb0dfa89d9b0dbd4cdec4f96b5dae49816b1152b559aa8c09e964ce5340b87.
# Existing GP05 authority remains separate; predicates/source fragments excluded.
STATIC.update(
    {
        "GP07-DESCRIPTION-00": "Native video start at ",
        "GP07-DESCRIPTION-01": " seconds from validated source URL timing; original metadata remains independent evidence.",
        "GP07-DESCRIPTION-02": ". The exact original external URI remains the resource link; archived HTML remains source evidence.",
        "GP07-DESCRIPTION-03": "; original display and syntax remain in document evidence.",
        "GP07-DESCRIPTION-04": " links; original source arrow and visibility details remain in evidence.",
        "GP07-DESCRIPTION-05": "Inline source reference resolves to canonical ",
        "GP07-DESCRIPTION-06": " embed derived from validated presentation facts: ",
        "GP07-DESCRIPTION-07": "Original title reserved as ",
        "GP07-DESCRIPTION-08": "Simple ",
        "GP07-DESCRIPTION-09": "Native ",
        "GP07-DESCRIPTION-10": "Owned icon and normalized declared colours remain separate from category defaults; original encoding and opaque tokens remain in item evidence.",
        "GP07-DESCRIPTION-11": " Later category/property edits do not rewrite this body snapshot.",
        "GP07-DESCRIPTION-12": "Parents/Children",
        "GP07-DESCRIPTION-13": "Related",
        "GP07-DESCRIPTION-14": "Creation/overall-modification calendar components without timezone conversion; full source timestamps remain in item evidence and migration time remains separate.",
        "GP07-DESCRIPTION-16": "Generated canonical linked properties and paired original identities; no prose-derived aliases or semantic fields.",
        "GP07-DESCRIPTION-17": "Editable migration-time image reference to ",
        "GP07-DESCRIPTION-18": " from its owned icon.",
        "GP07-DESCRIPTION-19": "Enabled bundled Templates for manual selection, Templates folder and ISO insertion dates; configured canonical native property types without unrelated reference toggles.",
        "GP07-DESCRIPTION-20": "Documented new-object templates, direct existing-note membership edits, explicit update dates and category/member/Base starters without a custom registry.",
        "GP07-DESCRIPTION-21": "Preserved Home with an added Categories overview entry; overview uses the Categories folder and native categories tag role guard.",
        "GP07-DESCRIPTION-22": "Enabled bundled Bases and required native navigation; preserved Home/bookmark settings and enabled link-preserving renames.",
        "GP07-DESCRIPTION-23": "Full native new-note template initializes linked category membership/provider and insertion-day dates, with blank overrides and no imported identities.",
        "GP07-DESCRIPTION-24": ".",
        "GP07-DESCRIPTION-25": " from appearance category ",
        "GP07-DESCRIPTION-26": "Parents/Children navigation immediately follows the category title when present; native contextual Members and Gallery Bases follow that navigation, before retained source content, without a generated introductory icon image; linked membership discovery survives link-preserving renames.",
        "GP07-DESCRIPTION-27": "Exact scoped text normalization for editable Markdown; before/after text, kind and coordinate bases remain in document evidence.",
        "GP07-DESCRIPTION-28": " normalized to ordinary responsive inline Markdown presentation; exact percentage sizing is not reproduced.",
        "GP07-DESCRIPTION-29": "Original declaration ",
        "GP07-SIZING-00": "Review image placement and readability in the affected note. Adjust the note manually if desired; intact source image bytes and exact declarations remain preserved.",
        "GP07-SIZING-01": "Original image declaration ",
        "GP07-SIZING-02": " uses ordinary responsive inline Markdown presentation; exact percentage sizing is not reproduced.",
        "GP07-OBSERVED-00": " Observed: ",
        "GP07-LOSS-00": "table",
        "GP07-LOSS-01": "Column widths and justification become native responsive table layout; edit the table in Obsidian to adjust its presentation.",
        "GP07-LOSS-02": "callout",
        "GP07-LOSS-03": "Unsupported callout type retained as source text; change it to a supported native type.",
        "GP07-LOSS-04": "Emoji is visible in the title; Obsidian's native icon remains. Edit the title to adjust this fallback.",
        "GP07-LOSS-05": "Unsupported or ambiguous icon metadata is retained visibly in the title; replace it with a title emoji or remove it manually.",
        "GP07-LOSS-06": "callout_icon",
        "GP07-LOSS-07": "table",
        "GP07-LOSS-08": "Malformed or ambiguous table retained as source text; supply an ordinary Markdown table with a matching header separator.",
        "GP07-LOSS-09": "table_of_contents",
        "GP07-LOSS-10": "Unsupported ToC declaration retained; use a standalone [/toc/] marker and reconvert, or author links manually.",
        "GP07-LOSS-11": "callout",
        "GP07-LOSS-12": "Malformed callout declaration retained as source text; use [!type] with an optional folding flag and title.",
        "GP07-LOSS-13": "table_of_contents",
        "GP07-LOSS-14": "A duplicate authored block ID was replaced with a distinct ToC destination; update authored links to this heading if needed.",
    }
)
