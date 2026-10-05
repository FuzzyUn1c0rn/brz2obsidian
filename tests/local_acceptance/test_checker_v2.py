"""Synthetic controls against internally consistent false migration receipts."""

import hashlib
import json
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_graph_workflow import identity
from tests.local_acceptance.checker import check_vault, compare_vaults
from tests.local_acceptance.run import reordered_archive
from tests.support.v2_collection import mixed_archive


def rewrite_record(vault, record, result):
    (vault / "migration-record.json").write_text(json.dumps(record), encoding="utf-8")
    result["counts"] = record["counts"] | {
        "actual_notes": record["counts"]["planned_notes"],
        "actual_assets": record["counts"]["planned_assets"],
        "actual_category_notes": record["counts"]["planned_category_notes"],
        "actual_support_files": record["counts"]["planned_support_files"],
        "actual_files": sum(p.is_file() for p in vault.rglob("*")),
    }
    result["receipt"]["counts"] = result["counts"]
    result["issues"] = record["issues"]
    result["source_identity"] = result["receipt"]["source_identity"] = record[
        "source_identity"
    ]
    result["receipt"]["manifest"] = [
        {
            "relative_path": p.relative_to(vault).as_posix(),
            "length": len(p.read_bytes()),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in vault.rglob("*")
        if p.is_file()
    ]
    assert all(
        (vault / m["relative_path"]).stat().st_size == m["length"]
        and hashlib.sha256((vault / m["relative_path"]).read_bytes()).hexdigest()
        == m["sha256"]
        for m in result["receipt"]["manifest"]
    )


def fixture(tmp_path):
    source = mixed_archive(tmp_path / "source.brz")
    vault = tmp_path / "vault"
    result = (
        default_workflow().convert(source, vault).model_dump(mode="json", by_alias=True)
    )
    check_vault(source, vault)
    record = json.loads((vault / "migration-record.json").read_bytes())
    return source, vault, result, record


@pytest.mark.parametrize(
    "damage",
    [
        "classification_duplicate",
        "relationship_duplicate",
        "tag_duplicate",
        "membership",
        "provider",
        "assignment_evidence",
        "relationship_evidence",
        "asset_evidence",
        "document_evidence",
        "reference_source",
        "reference_image_span",
        "member_selection",
        "definition_selection",
        "false_hierarchy_reason",
        "inherited_snapshot",
        "borrowed_declared_icon",
        "borrowed_colours",
        "borrowed_label",
        "migration_dates",
        "exceptional_demoted",
        "exceptional_image",
        "exceptional_body",
        "exceptional_backup",
        "gap_pdf_identity",
        "gap_pdf_owner",
        "gap_pdf_state",
        "gap_pdf_length",
        "gap_pdf_hash",
        "gap_pdf_crc",
        "gap_rule",
        "gap_finding",
        "gap_issue",
        "gap_notice",
        "gap_file",
        "video_start",
        "video_url",
        "video_missing_embed",
        "video_copied_html",
        "video_fabricated",
        "ordinary_url_video",
        "video_metadata",
        "base_filter",
        "base_provider",
        "base_precedence",
        "base_order",
        "base_gallery",
        "base_starter",
        "template_identity",
        "template_dates",
        "template_membership",
        "template_provider",
        "template_missing",
        "guide_missing",
        "guide_obligation",
        "configuration",
        "config_missing",
        "adaptation",
        "adaptation_fact",
        "report_counts",
        "report_limits",
        "reservation",
    ],
)
def test_oracle_detects_v2_lies_after_receipt_rehash_and_recount(tmp_path, damage):
    source, vault, result, record = fixture(tmp_path)
    items = {t["item_key"]: t for t in record["item_targets"]}
    assets = {a["asset_id"]: a for a in record["asset_targets"]}
    empty, category, exceptional = (
        items[identity(3)],
        items[identity(2)],
        items[identity(9)],
    )
    gap, reviewed = (
        assets[identity(3006)],
        assets[identity(3007)],
    )

    def replace(path, old, new):
        p = vault / path
        data = p.read_bytes()
        assert old in data, "corruption hook must fire"
        p.write_bytes(data.replace(old, new))

    if damage.endswith("_duplicate"):
        field = {
            "classification_duplicate": "classification_assignments",
            "relationship_duplicate": "relationships",
            "tag_duplicate": "tag_memberships",
        }[damage]
        record[field].append(record[field][0].copy())
    elif damage in {"membership", "provider", "assignment_evidence"}:
        assignment = record["classification_assignments"][0]
        if damage == "assignment_evidence":
            assignment["evidence"] = ["thoughts.json:0", "links.json:0"]
        elif damage == "membership":
            assignment["item_key"] = identity(5)
        else:
            assignment["definition_key"] = identity(8)
    elif damage.endswith("_evidence"):
        if damage == "relationship_evidence":
            record["relationships"][0]["evidence"] = ["links.json:8"]
        elif damage == "asset_evidence":
            assets[identity(3001)]["evidence"] = ["attachments.json:0"]
        else:
            exceptional["documents"][0]["evidence"] = ["attachments.json:0"]
    elif damage in {"reference_source", "reference_image_span"}:
        ref = exceptional["documents"][0]["references"][
            0 if damage == "reference_source" else 1
        ]
        ref[
            "source_target" if damage == "reference_source" else "destination_start"
        ] = "brain://fabricated" if damage == "reference_source" else 0
    elif damage in {"member_selection", "definition_selection"}:
        target = empty if damage == "member_selection" else category
        (vault / target["relative_path"]).unlink()
        target["created"] = False
        target["creation_reasons"] = []
        target["icon_snapshot"] = None
        record["counts"]["planned_notes"] -= 1
        if damage == "definition_selection":
            record["counts"]["planned_category_notes"] -= 1
    elif damage == "false_hierarchy_reason":
        empty["creation_reasons"] = ["hierarchy"]
    elif damage == "inherited_snapshot":
        wrong = assets[identity(3002)]["relative_path"]
        original = assets[identity(3001)]["relative_path"]
        empty["icon_snapshot"]["effective_icon_asset_id"] = identity(3002)
        replace(empty["relative_path"], original.encode(), wrong.encode())
    elif damage == "borrowed_declared_icon":
        empty["declared_appearance"]["icon_asset_id"] = identity(3001)
    elif damage == "borrowed_colours":
        empty["declared_appearance"]["foreground_color"] = "#FF0000"
    elif damage == "borrowed_label":
        replace(empty["relative_path"], b"# Empty", b"# Empty\n\nDefinition label")
    elif damage == "migration_dates":
        exceptional["calendar_dates"] = {
            "created": "2026-10-05",
            "updated": "2026-10-05",
        }
        replace(exceptional["relative_path"], b"2024-02-29", b"2026-10-05")
        replace(exceptional["relative_path"], b"2025-01-01", b"2026-10-05")
    elif damage == "exceptional_demoted":
        assets[exceptional["documents"][0]["key"]]["role"] = "file"
        exceptional["documents"] = []
    elif damage in {"exceptional_image", "exceptional_body", "exceptional_backup"}:
        if damage == "exceptional_backup":
            (
                vault / assets[exceptional["documents"][0]["key"]]["relative_path"]
            ).write_bytes(b"changed original")
        else:
            replace(
                exceptional["relative_path"],
                b"photo.png" if damage == "exceptional_image" else b"Authored heading",
                b"wrong.png" if damage == "exceptional_image" else b"Changed heading",
            )
    elif damage.startswith("gap_pdf_"):
        observation = json.loads(gap["source_findings"][0]["observed_json"])
        if damage == "gap_pdf_identity":
            observation["pdf_attachment_id"] = identity(3004)
        else:
            field = damage.removeprefix("gap_pdf_")
            field = {
                "hash": "actual_sha256",
                "length": "actual_length",
                "crc": "crc_valid",
            }.get(field, field)
            observation["pdf"][field] = {
                "owner": identity(1),
                "state": 2,
                "actual_length": 0,
                "actual_sha256": "0" * 64,
                "crc_valid": False,
            }[field]
        gap["source_findings"][0]["observed_json"] = json.dumps(observation)
        record["issues"][0]["message"] = (
            "False but consistent. Observed: "
            + gap["source_findings"][0]["observed_json"]
        )
    elif damage in {"gap_rule", "gap_finding", "gap_issue"}:
        if damage == "gap_rule":
            gap["source_findings"][0]["rule_id"] = record["issues"][0]["rule_id"] = (
                "thebrain-format5/absent-txt/v1"
            )
        elif damage == "gap_finding":
            gap["source_findings"] = []
        else:
            record["issues"] = []
    elif damage == "gap_notice":
        replace(
            exceptional["relative_path"], b"Absent source file", b"Optional cache file"
        )
    elif damage == "gap_file":
        copied = "Attachments/00000000/invented.txt"
        (vault / copied).parent.mkdir(exist_ok=True)
        (vault / copied).write_bytes(b"")
        gap.update(
            relative_path=copied,
            availability="present",
            actual_length=0,
            actual_sha256=hashlib.sha256(b"").hexdigest(),
            resource_link=copied,
        )
        record["counts"]["planned_assets"] += 1
    elif damage == "video_start":
        reviewed["video_presentation"].update(
            start_seconds=0,
            embed_uri=reviewed["video_presentation"]["embed_uri"].replace("18", "0"),
        )
        replace(exceptional["relative_path"], b"?start=18", b"?start=0")
    elif damage == "video_url":
        reviewed["external_uri"] = reviewed["resource_link"] = reviewed[
            "external_uri"
        ].replace("18s", "18")
        replace(exceptional["relative_path"], b"&t=18s", b"&t=18")
    elif damage == "video_missing_embed":
        p = vault / exceptional["relative_path"]
        p.write_bytes(p.read_bytes().replace(b'<iframe src="', b'<deleted src="'))
    elif damage == "video_copied_html":
        replace(
            exceptional["relative_path"],
            b'<iframe src="',
            b"<iframe onclick='evil()' src=\"",
        )
    elif damage == "video_fabricated":
        assets[identity(3008)]["video_presentation"] = reviewed[
            "video_presentation"
        ].copy()
    elif damage == "ordinary_url_video":
        with ZipFile(source) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
        ordinary = next(a for a in rows if a["Id"] == identity(3008))
        ordinary.update(Type=3, Location="https://example.test/resource")
        parts["attachments.json"] = "\n".join(json.dumps(a) for a in rows).encode()
        with ZipFile(source, "w") as archive:
            for name, data in parts.items():
                archive.writestr(name, data)
        next(e for e in record["original_evidence"] if e["key"] == "attachments.json")[
            "records"
        ] = rows
        record["source_identity"]["source_sha256"] = hashlib.sha256(
            source.read_bytes()
        ).hexdigest()
        assets[identity(3008)].update(
            role="url",
            original_name=ordinary["Location"],
            external_uri=ordinary["Location"],
            resource_link=ordinary["Location"],
            video_presentation=reviewed["video_presentation"].copy(),
        )
    elif damage == "video_metadata":
        reviewed["video_presentation"]["provider"] = "arbitrary"
    elif damage.startswith("base_"):
        role = (
            "Gallery"
            if damage == "base_gallery"
            else "Starter"
            if damage == "base_starter"
            else "Members"
        )
        path = f"Templates/Bases/{role}.base"
        old, new = {
            "base_filter": (b"list(categories).contains(this)", b"true"),
            "base_provider": (
                b"list(categories).contains(appearance_category)",
                b"true",
            ),
            "base_precedence": (
                b"formula.explicit_icon, formula.explicit_icon, formula.inherited_icon",
                b"formula.inherited_icon, formula.inherited_icon, formula.explicit_icon",
            ),
            "base_order": (
                b"      - formula.picture\n      - file.name",
                b"      - file.name\n      - formula.picture",
            ),
            "base_gallery": (b"image: formula.effective_icon", b"image: note.icon"),
            "base_starter": (b"list(categories).contains(this)", b"false"),
        }[damage]
        replace(path, old, new)
    elif damage.startswith("template_"):
        path = "Templates/Concept.md"
        if damage == "template_missing":
            (vault / path).unlink()
            record["support_artifacts"] = [
                a for a in record["support_artifacts"] if a["relative_path"] != path
            ]
            record["counts"]["planned_support_files"] -= 1
        else:
            old, new = {
                "template_identity": (
                    b"aliases: []",
                    b'aliases: []\nsource_item_id: "borrowed"',
                ),
                "template_dates": (b'"{{date:YYYY-MM-DD}}"', b"2026-10-05"),
                "template_membership": (
                    b'  - "[[Categories/Concept.md]]"',
                    b'  - "[[Notes/Focus.md]]"',
                ),
                "template_provider": (
                    b'appearance_category: "[[Categories/Concept.md]]"',
                    b"appearance_category:",
                ),
            }[damage]
            replace(path, old, new)
    elif damage in {"guide_missing", "config_missing"}:
        path = "Vault guide.md" if damage == "guide_missing" else ".obsidian/types.json"
        (vault / path).unlink()
        record["support_artifacts"] = [
            a for a in record["support_artifacts"] if a["relative_path"] != path
        ]
        record["counts"]["planned_support_files"] -= 1
    elif damage == "guide_obligation":
        replace(
            "Vault guide.md",
            b"New objects omit both source IDs",
            b"New objects copy all source IDs",
        )
    elif damage == "configuration":
        config = {"folder": "Notes", "dateFormat": "DD/MM/YYYY"}
        (vault / ".obsidian/templates.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        record["obsidian_templates_configuration"] = config
    elif damage == "adaptation":
        record["adaptations"] = [
            a for a in record["adaptations"] if a["kind"] != "canonical_properties"
        ]
    elif damage == "adaptation_fact":
        next(a for a in record["adaptations"] if a["kind"] == "body_icon_snapshot")[
            "description"
        ] = "Editable snapshot from an unrelated valid image."
    elif damage == "report_counts":
        replace(
            "MIGRATION REPORT.md",
            b"Created 7 thought notes",
            b"Created 99 thought notes",
        )
    elif damage == "report_limits":
        replace(
            "MIGRATION REPORT.md",
            b"Vault Search does not search PDF body text",
            b"Vault Search searches all PDF body text",
        )
    else:
        # Mixed fixture has both conditional listings; add a false inactive one.
        record["reserved_support_paths"] = ["Tag memberships.md"]
    rewrite_record(vault, record, result)
    with pytest.raises((AssertionError, FileNotFoundError)):
        check_vault(source, vault)


def test_independent_mixed_reorder_checks_provenance_before_equivalence(tmp_path):
    source = mixed_archive(tmp_path / "source.brz")
    shuffled = tmp_path / "reordered.brz"
    reordered_archive(source, shuffled)
    first, second = tmp_path / "first", tmp_path / "second"
    default_workflow().convert(source, first)
    default_workflow().convert(shuffled, second)
    assert check_vault(source, first) == check_vault(shuffled, second)
    compare_vaults(first, second)
    path = second / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["classification_assignments"][0]["evidence"] = [
        "thoughts.json:0",
        "links.json:0",
    ]
    path.write_text(json.dumps(record), encoding="utf-8")
    compare_vaults(first, second)
    with pytest.raises(AssertionError, match="classification"):
        check_vault(shuffled, second)


@pytest.mark.parametrize(
    "damage",
    [
        "duplicate_item",
        "field_link",
        "exceptional_competitor",
        "zero_bool",
        "pdf_owner",
        "pdf_state",
        "pdf_length",
    ],
)
def test_oracle_rejects_false_raw_facts_even_with_updated_originals_and_fingerprint(
    tmp_path, damage
):
    source, vault, result, record = fixture(tmp_path)
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    attachments = [json.loads(line) for line in parts["attachments.json"].splitlines()]
    meta = json.loads(parts["meta.json"])
    if damage == "duplicate_item":
        thoughts.append(thoughts[0].copy())
    elif damage == "field_link":
        next(t for t in thoughts if t["Id"] == identity(3))["TypeId"] = None
    elif damage == "exceptional_competitor":
        other = next(
            a for a in attachments if a["Type"] == 1 and a["NoteType"] == 4
        ).copy()
        other.update(Id=identity(3999), SourceId=identity(9), Location="Other.md")
        attachments.append(other)
        meta["AttachmentFileStates"][other["Id"]] = 1
        parts[identity(9) + "/Other.md"] = parts[identity(1) + "/Notes.md"]
    elif damage == "zero_bool":
        next(a for a in attachments if a["Id"] == identity(3006))["DataLength"] = False
    else:
        pdf = next(a for a in attachments if a["Id"] == identity(3005))
        if damage == "pdf_owner":
            pdf["SourceId"] = identity(1)
        elif damage == "pdf_state":
            meta["AttachmentFileStates"][pdf["Id"]] = 2
        else:
            pdf["DataLength"] += 1
    for name, value in (
        ("thoughts.json", thoughts),
        ("attachments.json", attachments),
        ("meta.json", meta),
    ):
        parts[name] = (
            json.dumps(value).encode()
            if name == "meta.json"
            else "\n".join(json.dumps(r) for r in value).encode()
        )
        next(e for e in record["original_evidence"] if e["key"] == name)["records"] = (
            [value] if name == "meta.json" else value
        )
    with ZipFile(source, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    record["source_identity"]["source_sha256"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    rewrite_record(vault, record, result)
    with pytest.raises((AssertionError, KeyError)):
        check_vault(source, vault)
