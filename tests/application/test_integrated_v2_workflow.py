"""Combined actual-output acceptance at public workflow/command/checker seams."""

import hashlib
import json
import tomllib
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

import brz2obsidian
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from brz2obsidian.contracts import RunResult
from brz2obsidian.vault_check import check_vault
from tests.application.test_graph_workflow import identity
from tests.application.test_verified_coverage import add_attachment
from tests.local_acceptance.checker import compare_vaults
from tests.local_acceptance.run import reordered_archive
from tests.support.v2_collection import (
    CATEGORY_ICON,
    COMPACT,
    CREATED_ITEMS,
    EXCEPTIONAL_BYTES,
    EXCEPTIONAL_TEXT,
    HOME_BYTES,
    IMAGE_BYTES,
    ITEM_PATHS,
    MANUAL_BYTES,
    OVERRIDE_ICON,
    PDF_BYTES,
    SUPPORT_PATHS,
    TAG_BYTES,
    VIDEO_EMBED,
    VIDEO_HTML,
    VIDEO_URL,
    inventory,
    mixed_archive,
)


def properties(data):
    return yaml.safe_load(data.decode().split("---", 2)[1])


def test_combined_v2_vault_preserves_independent_facts_and_checks_without_source(
    tmp_path,
):
    source = mixed_archive(tmp_path / "mixed.brz")
    source_before = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings", inspected.issues
    assert inspected.receipt is None and inspected.counts.actual_files is None
    assert sorted(p.name for p in tmp_path.iterdir()) == ["mixed.brz"]
    assert {t.relative_path: t.created for t in inspected.inspection.item_targets} == {
        path: n in CREATED_ITEMS for n, path in ITEM_PATHS.items()
    }
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "warnings", result.issues
    assert result.receipt.published and result.receipt.verified
    assert result.schema_version == 3 and result.profile_version == "3"
    assert result.converter_version == brz2obsidian.__version__ == "0.3.0"
    package = tomllib.loads(
        (Path(brz2obsidian.__file__).parents[2] / "pyproject.toml").read_text()
    )
    assert package["project"]["version"] == "0.3.0"
    assert (
        RunResult.model_validate_json(result.model_dump_json(by_alias=True)) == result
    )
    assert [(i.code, i.rule_id, i.affected) for i in result.issues] == [
        (
            "approved_source_gap",
            "thebrain-format5/zero-length-absent-txt/v1",
            (identity(3006),),
        )
    ]
    counts = result.counts
    assert (
        counts.source_items,
        counts.source_relationships,
        counts.actual_notes,
        counts.actual_assets,
        counts.actual_references,
    ) == (12, 9, 7, 8, 2)
    assert (
        counts.source_definitions,
        counts.classification_assignments,
        counts.typed_members,
        counts.actual_category_notes,
        counts.actual_support_files,
    ) == (1, 3, 3, 1, 19)
    assert (
        counts.source_tags,
        counts.tag_memberships,
        counts.native_tag_memberships,
        counts.uncreated_tag_memberships,
    ) == (1, 2, 1, 1)
    assert counts.planned_notes == counts.actual_notes == inspected.counts.planned_notes
    copied = {
        "Attachments/00000000000000000000000000000001/Notes.md.original": HOME_BYTES,
        "Attachments/00000000000000000000000000000008/Notes.md.original": TAG_BYTES,
        "Attachments/00000000000000000000000000000009/Notes.md.original": EXCEPTIONAL_BYTES,
        "Attachments/00000000000000000000000000000002/type.png": CATEGORY_ICON,
        "Attachments/00000000000000000000000000000004/override.png": OVERRIDE_ICON,
        "Attachments/00000000000000000000000000000009/photo.png": IMAGE_BYTES,
        "Attachments/00000000000000000000000000000001/manual.bin": MANUAL_BYTES,
        "Attachments/00000000000000000000000000000009/manual.pdf": PDF_BYTES,
    }
    expected_paths = (
        SUPPORT_PATHS | set(copied) | {ITEM_PATHS[n] for n in CREATED_ITEMS}
    )
    actual = inventory(vault)
    assert set(actual) == expected_paths and counts.actual_files == 34
    assert {
        f.relative_path: (f.length, f.sha256) for f in result.receipt.manifest
    } == actual
    for path, body in copied.items():
        assert (vault / path).read_bytes() == body
        assert actual[path] == (len(body), hashlib.sha256(body).hexdigest())
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert (
        record["schema"],
        record["schema_version"],
        record["converter_version"],
        record["renderer_version"],
    ) == ("brz2obsidian.migration", 3, "0.3.0", "3")
    assert {s["relative_path"] for s in record["support_artifacts"]} == SUPPORT_PATHS
    assert {a["item_key"] for a in record["classification_assignments"]} == {
        identity(3),
        identity(4),
        identity(9),
    }
    assert {t["relative_path"]: t["created"] for t in record["item_targets"]} == {
        path: n in CREATED_ITEMS for n, path in ITEM_PATHS.items()
    }
    assert record["source_identity"] == result.source_identity.model_dump()
    assert record["issues"] == [i.model_dump(mode="json") for i in result.issues]
    assert {r["kind"] for r in record["relationships"]} == {
        "hierarchy",
        "related",
        "tag",
        "system",
        "classification",
    }
    assert {
        (r["kind"], r["target_a"], r["target_b"]) for r in record["relationships"]
    } == {
        ("classification", "Categories/Concept.md", "Notes/Empty.md"),
        ("classification", "Categories/Concept.md", "Notes/Override.md"),
        ("classification", "Categories/Concept.md", "Notes/Different marker.md"),
        ("hierarchy", "Notes/First.md", "Notes/Middle.md"),
        ("hierarchy", "Notes/Middle.md", "Notes/Last.md"),
        ("related", "Home — Opening.md", "Notes/Different marker.md"),
        ("tag", "Notes/Focus.md", "Home — Opening.md"),
        ("tag", "Notes/Focus.md", "Notes/Last.md"),
        ("system", None, "Categories/Concept.md"),
    }
    assert (
        next(r for r in record["relationships"] if r["kind"] == "system")[
            "presentation"
        ]
        == "retained_only"
    )
    assert {
        (t["item_target"], t["token"], t["native"]) for t in record["tag_memberships"]
    } == {("Home — Opening.md", "Focus", True), ("Notes/Last.md", "Focus", False)}
    with ZipFile(source) as archive:
        for original in record["original_evidence"]:
            if original["kind"] != "records":
                continue
            raw = archive.read(original["key"])
            try:
                expected = json.loads(raw)
            except json.JSONDecodeError:
                expected = [
                    json.loads(line) for line in raw.splitlines() if line.strip()
                ]
            if isinstance(expected, dict):
                expected = [expected]
            assert original["records"] == expected
        source_payloads = {
            "payload:" + name for name in archive.namelist() if "/" in name
        }
    accounting = record["source_accounting"]["entries"]
    assert {
        a["identity"] for a in accounting if a["identity"].startswith("payload:")
    } == source_payloads
    assert all(a["disposition"] in {"normalized", "retained_only"} for a in accounting)
    inherited = properties((vault / ITEM_PATHS[3]).read_bytes())
    override = properties((vault / ITEM_PATHS[4]).read_bytes())
    assert (
        inherited["categories"]
        == override["categories"]
        == ["[[Categories/Concept.md]]"]
    )
    assert inherited["appearance_category"] == "[[Categories/Concept.md]]"
    assert inherited["icon"] is None
    assert (
        override["icon"]
        == "[[Attachments/00000000000000000000000000000004/override.png]]"
    )
    assert (
        str(override["created"]) == "2024-02-29"
        and str(override["updated"]) == "2025-01-01"
    )
    assert properties((vault / ITEM_PATHS[1]).read_bytes())["tags"] == ["Focus"]
    assert (
        b"![[Attachments/00000000000000000000000000000002/type.png]]"
        in (vault / ITEM_PATHS[3]).read_bytes()
    )
    unusual = (vault / ITEM_PATHS[9]).read_bytes()
    expected_authored = EXCEPTIONAL_TEXT.replace(
        f"[Reserved](brain://{COMPACT}/ignored)",
        "[[Notes/Reserved.md|Reserved]]",
    ).replace(
        ".data/md-images/photo.png",
        "../Attachments/00000000000000000000000000000009/photo.png",
    )
    assert expected_authored.encode() in unusual
    assert f"- [Reviewed video](<{VIDEO_URL}>)".encode() in unusual
    assert VIDEO_EMBED.encode() in unusual and VIDEO_HTML.encode() not in unusual
    assert (identity(3005) + ".txt").encode() in unusual
    assert not list(vault.rglob("*.txt"))
    absent = next(a for a in record["asset_targets"] if a["asset_id"] == identity(3006))
    assert absent["relative_path"] is absent["resource_link"] is None
    finding = json.loads(absent["source_findings"][0]["observed_json"])
    assert finding["pdf_attachment_id"] == identity(3005)
    assert (
        finding["declared_length"] == 0
        and finding["state"] == 2
        and finding["present"] is False
    )
    assert finding["pdf"]["actual_length"] == len(PDF_BYTES)
    assert finding["pdf"]["actual_sha256"] == hashlib.sha256(PDF_BYTES).hexdigest()
    video = next(a for a in record["asset_targets"] if a["asset_id"] == identity(3007))
    assert video["external_uri"] == video["resource_link"] == VIDEO_URL
    assert video["video_presentation"] == {
        "provider": "youtube",
        "embed_uri": VIDEO_EMBED,
        "start_seconds": 18,
    }
    report = (vault / "MIGRATION REPORT.md").read_text()
    assert report.count("Vault Search does not search PDF body text") == 1
    assert report.count("Video playback depends on the remote service and network") == 1
    middle = (vault / "Notes/Middle.md").read_bytes()
    assert b"## Parents\n\n- [[Notes/First.md|First]]" in middle
    assert b"## Children\n\n- [[Notes/Last.md|Last]]" in middle
    originals = next(
        e["records"] for e in record["original_evidence"] if e["key"] == "thoughts.json"
    )
    assert (
        originals[2]["ThoughtIconInfo"]
        == "opaque token retained without interpretation"
    )
    assert originals[1]["CreationDateTime"] == "2024-02-29T23:59:58.1234567-11:00"
    for path in (vault / "Templates").glob("*.md"):
        text = path.read_text()
        assert 'created: "{{date:YYYY-MM-DD}}"' in text
        assert 'updated: "{{date:YYYY-MM-DD}}"' in text
        assert "source_item_id" not in text and "source_collection_id" not in text
    base = (vault / "Templates/Bases/Members.base").read_text()
    assert "list(categories).contains(this)" in base
    assert "      - formula.picture\n      - file.name" in base
    assert "Appearance" not in base
    assert json.loads((vault / ".obsidian/templates.json").read_bytes()) == {
        "folder": "Templates",
        "dateFormat": "YYYY-MM-DD",
    }
    assert json.loads((vault / ".obsidian/core-plugins.json").read_bytes())["bases"]
    expected_configuration = {
        "showInlineTitle": False,
        "defaultViewMode": "preview",
        "newFileLocation": "folder",
        "newFileFolderPath": "Notes",
        "useMarkdownLinks": False,
        "newLinkFormat": "absolute",
        "openBehavior": "file:Home — Opening.md",
        "alwaysUpdateLinks": True,
        "attachmentFolderPath": "Attachments",
    }
    assert (
        json.loads((vault / ".obsidian/app.json").read_bytes())
        == record["obsidian_configuration"]
        == expected_configuration
    )
    for filename, key in (
        ("core-plugins.json", "obsidian_core_plugins_configuration"),
        ("templates.json", "obsidian_templates_configuration"),
        ("types.json", "obsidian_property_types_configuration"),
    ):
        assert json.loads((vault / ".obsidian" / filename).read_bytes()) == record[key]
    assert json.loads((vault / ".obsidian/types.json").read_bytes()) == {
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
    }
    assert source.read_bytes() == source_before
    source.unlink()  # Convention checking depends only on the editable vault.
    checked = check_vault(vault)
    assert checked.outcome == "clean", checked.issues
    assert checked.schema_version == 1 and checked.counts.imported_notes == 7
    assert checked == check_vault(vault) and inventory(vault) == actual


def test_mixed_cli_warning_publication_clean_checker_and_fresh_destination_contract(
    tmp_path, capsys
):
    source = mixed_archive(tmp_path / "mixed.brz")
    before = source.read_bytes()
    assert main(["inspect", str(source), "--json"]) == 2
    inspected = json.loads(capsys.readouterr().out)
    assert (
        inspected["schema"] == "brz2obsidian.result"
        and inspected["schema_version"] == 3
    )
    assert inspected["converter_version"] == "0.3.0" and inspected["receipt"] is None
    assert inspected["counts"]["actual_files"] is None
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 2
    converted = json.loads(capsys.readouterr().out)
    assert converted["outcome"] == "warnings" and converted["receipt"]["verified"]
    assert converted["counts"]["actual_files"] == 34
    assert converted["issues"] == inspected["issues"]
    actual = inventory(vault)
    assert main(["check-vault", str(vault), "--json"]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked == check_vault(vault).model_dump(mode="json", by_alias=True)
    assert inventory(vault) == actual and source.read_bytes() == before
    (vault / "caller.bin").write_bytes(b"caller edited vault\x00\xff")
    edited = inventory(vault)
    assert main(["convert", str(source), str(vault), "--json"]) == 1
    refused = json.loads(capsys.readouterr().out)
    assert refused["outcome"] == "refused" and refused["receipt"] is None
    assert [i["code"] for i in refused["issues"]] == [
        "approved_source_gap",
        "destination_not_empty",
    ]
    assert inventory(vault) == edited and source.read_bytes() == before
    assert main(["inspect", str(source)]) == 2
    text = capsys.readouterr()
    assert "approved_source_gap" in text.out and text.err == ""


@pytest.mark.parametrize(
    "fault",
    ["assignment", "competing_note", "absent_pdf", "unsafe_video", "invalid_date"],
)
def test_one_mixed_feature_conflict_refuses_the_entire_conversion(tmp_path, fault):
    source = mixed_archive(tmp_path / "mixed.brz")
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    if fault in {"assignment", "invalid_date"}:
        thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
        if fault == "assignment":
            thoughts[3].pop("TypeId")
        else:
            thoughts[3]["CreationDateTime"] = "2025-02-29T01:02:03"
        parts["thoughts.json"] = "\n".join(json.dumps(t) for t in thoughts).encode()
    elif fault == "competing_note":
        add_attachment(
            parts, identity(3999), 1, "Notes.md", EXCEPTIONAL_BYTES, owner=identity(9)
        )
    elif fault == "absent_pdf":
        parts.pop(identity(9) + "/manual.pdf")
    else:
        attachments = [
            json.loads(line) for line in parts["attachments.json"].splitlines()
        ]
        next(a for a in attachments if a["Id"] == identity(3007))["VideoHtml"] += (
            "<script>unreviewed()</script>"
        )
        parts["attachments.json"] = "\n".join(
            json.dumps(a) for a in attachments
        ).encode()
    with ZipFile(source, "w") as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    before = source.read_bytes()
    caller = tmp_path / "caller.bin"
    caller.write_bytes(b"caller content\x00\xff")
    for result in (
        default_workflow().inspect(source),
        default_workflow().convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused" and result.receipt is None
        assert (
            result.issues[-1].code
            == {
                "assignment": "invalid_reference",
                "competing_note": "invalid_source",
                "absent_pdf": "missing_required_payload",
                "unsafe_video": "unsupported_feature",
                "invalid_date": "invalid_source",
            }[fault]
        )
        assert result.counts is None or result.counts.actual_files is None
    assert not (tmp_path / "vault").exists() and not list(
        tmp_path.glob(".brz2obsidian-*")
    )
    assert (
        source.read_bytes() == before
        and caller.read_bytes() == b"caller content\x00\xff"
    )


def test_mixed_feature_selection_output_and_support_are_repeat_and_reorder_stable(
    tmp_path,
):
    source = mixed_archive(tmp_path / "mixed.brz")
    reordered = tmp_path / "reordered.brz"
    reordered_archive(source, reordered)
    results = []
    for name, current in (
        ("first", source),
        ("repeat", source),
        ("reordered", reordered),
    ):
        result = default_workflow().convert(current, tmp_path / name)
        assert result.outcome == "warnings" and result.receipt.verified
        assert check_vault(tmp_path / name).outcome == "clean"
        results.append(result)
    assert results[0].counts == results[1].counts == results[2].counts
    compare_vaults(tmp_path / "first", tmp_path / "repeat")
    compare_vaults(tmp_path / "first", tmp_path / "reordered")
