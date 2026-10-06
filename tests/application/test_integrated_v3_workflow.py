"""Public mixed-workflow facts with independently chosen source expectations."""

import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

from brz2obsidian.application import SourceModuleBinding, Workflow
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from brz2obsidian.contracts import RunResult
from brz2obsidian.obsidian import ObsidianRenderer
from brz2obsidian.publication import FilesystemPublisher
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from brz2obsidian.vault_check import check_vault
from tests.application.test_graph_workflow import identity
from tests.application.test_module_seams import METADATA
from tests.support.v2_collection import (
    COMPACT,
    EXCEPTIONAL_BYTES,
    EXCEPTIONAL_TEXT,
    HOME_BYTES,
    IMAGE_BYTES,
    MANUAL_BYTES,
    OVERRIDE_ICON,
    PDF_BYTES,
    SUPPORT_PATHS,
    TAG_BYTES,
    VIDEO_EMBED,
    VIDEO_URL,
    inventory,
)
from tests.support.v3_collection import CARD_BYTES, ZIP_BYTES, mixed_v3_archive

EMPTY = "Notes/Empty — 00000000000000000000000000000003.md"
RESERVED = "Notes/Empty — 0000000000000000000000000000000a.md"


def properties(body):
    return yaml.safe_load(body.decode().split("---", 2)[1])


def test_mixed_v3_inspection_measures_included_scope_and_distinct_display(tmp_path):
    source = mixed_v3_archive(tmp_path / "mixed.brz")
    before = source.read_bytes()
    result = default_workflow().inspect(source)
    assert result.outcome == "warnings", result.issues
    assert result.counts.source_items == 11
    assert result.counts.source_gaps == 3
    assert result.counts.planned_generated_embeds == 2
    assert result.receipt is None and result.counts.actual_generated_embeds is None
    assert source.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["mixed.brz"]


def test_complete_mixed_v3_output_matches_independent_bytes_graph_and_counts(tmp_path):
    source = mixed_v3_archive(tmp_path / "mixed.brz")
    source_before = source.read_bytes()
    inspected = default_workflow().inspect(source)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "warnings", result.issues
    assert result.schema_version == 3 and result.profile_version == "3"
    assert result.converter_version == "0.3.0"
    assert (
        RunResult.model_validate_json(result.model_dump_json(by_alias=True)) == result
    )
    assert result.receipt.published and result.receipt.verified
    assert result.source_identity == inspected.source_identity
    assert result.issues == inspected.issues
    assert (
        result.counts.source_items,
        result.counts.source_relationships,
        result.counts.source_gaps,
        result.counts.actual_generated_embeds,
        result.counts.actual_notes,
        result.counts.actual_assets,
        result.counts.actual_references,
        result.counts.actual_support_files,
        result.counts.actual_files,
    ) == (11, 11, 3, 2, 7, 11, 2, 18, 36)
    copies = {
        "Attachments/00000000000000000000000000000001/Notes.md.original": HOME_BYTES,
        "Attachments/00000000000000000000000000000008/Notes.md.original": TAG_BYTES,
        "Attachments/00000000000000000000000000000009/Notes.md.original": EXCEPTIONAL_BYTES,
        "Attachments/00000000000000000000000000000004/Notes.md.original": b"",
        "Attachments/00000000000000000000000000000004/override.png": OVERRIDE_ICON,
        "Attachments/00000000000000000000000000000009/photo.png": IMAGE_BYTES,
        "Attachments/00000000000000000000000000000001/manual.bin": MANUAL_BYTES,
        "Attachments/00000000000000000000000000000009/manual.pdf": PDF_BYTES,
        "Attachments/00000000000000000000000000000009/archive.zip": ZIP_BYTES,
        "Attachments/00000000000000000000000000000003/z-first.png": CARD_BYTES,
        "Attachments/00000000000000000000000000000003/a-second.png": CARD_BYTES,
    }
    notes = {
        "Home — Opening.md",
        "Categories/Concept.md",
        EMPTY,
        "Notes/Override.md",
        "Notes/Middle.md",
        "Notes/Focus.md",
        "Notes/Different marker.md",
    }
    actual = inventory(vault)
    assert set(actual) == set(copies) | notes | (
        SUPPORT_PATHS - {"Uncreated targets.md"}
    )
    assert {
        f.relative_path: (f.length, f.sha256) for f in result.receipt.manifest
    } == actual
    for name, body in copies.items():
        assert (vault / name).read_bytes() == body
    card = (vault / EMPTY).read_text(encoding="utf-8")
    assert card.index("Source note text is absent") < card.index("z-first.png]]")
    assert card.index("z-first.png]]") < card.index("a-second.png]]")
    assert card.count("![[Attachments/00000000000000000000000000000003/") == 2
    assert "## Resources" not in card and "Available note images" not in card
    assert properties(card.encode())["icon"] is None
    assert (
        properties(card.encode())["appearance_category"] == "[[Categories/Concept.md]]"
    )
    category = (vault / "Categories/Concept.md").read_text(encoding="utf-8")
    assert category.index("## Parents") < category.index("Members.base#Members")
    assert "[[Home — Opening.md|Opening]]" in category
    assert "[[Notes/Override.md|Override]]" in category
    for path in ("Home — Opening.md", "Notes/Override.md"):
        assert "[[Categories/Concept.md|Concept]]" in (vault / path).read_text(
            encoding="utf-8"
        )
    override = properties((vault / "Notes/Override.md").read_bytes())
    assert (
        override["icon"]
        == "[[Attachments/00000000000000000000000000000004/override.png]]"
    )
    assert (
        str(override["created"]) == "2024-02-29"
        and str(override["updated"]) == "2025-01-01"
    )
    exceptional = (vault / "Notes/Different marker.md").read_bytes()
    expected = EXCEPTIONAL_TEXT.replace(
        f"[Reserved](brain://{COMPACT}/ignored)", f"[[{RESERVED}|Reserved]]"
    ).replace(
        ".data/md-images/photo.png",
        "../Attachments/00000000000000000000000000000009/photo.png",
    )
    assert expected.encode() in exceptional
    assert VIDEO_URL.encode() in exceptional and VIDEO_EMBED.encode() in exceptional
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert record["source_identity"] == result.source_identity.model_dump()
    assert {a["item_key"] for a in record["classification_assignments"]} == {
        identity(3),
        identity(4),
        identity(9),
    }
    assert {
        (r["target_a"], r["target_b"])
        for r in record["relationships"]
        if r["kind"] == "hierarchy"
    } == {
        ("Notes/First.md", "Notes/Middle.md"),
        ("Notes/Middle.md", "Notes/Last.md"),
        ("Home — Opening.md", "Categories/Concept.md"),
        ("Notes/Override.md", "Categories/Concept.md"),
    }
    assert {(g["gap"]["owner"], g["outcome"]) for g in record["source_gaps"]} == {
        (identity(3), "image_fallback"),
        (identity(2), "unknown_note"),
        (identity(2), "neutral_icon"),
    }
    icon_gap = next(g for g in record["source_gaps"] if g["outcome"] == "neutral_icon")
    assert icon_gap["affected_member_keys"] == [identity(3), identity(9)]
    for private in (
        identity(12),
        identity(4013),
        "Excluded secret",
        "secret.bin",
        "forgotten private payload",
    ):
        assert private not in inspected.model_dump_json() + result.model_dump_json()
        assert all(
            private.encode() not in (vault / path).read_bytes() for path in actual
        )
    assert source.read_bytes() == source_before
    source.unlink()
    assert check_vault(vault).outcome == "clean"
    assert inventory(vault) == actual


def test_mixed_cli_and_source_free_checker_report_current_images_read_only(
    tmp_path, capsys
):
    source = mixed_v3_archive(tmp_path / "mixed.brz")
    assert main(["inspect", str(source), "--json"]) == 2
    inspected = json.loads(capsys.readouterr().out)
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 2
    converted = json.loads(capsys.readouterr().out)
    assert inspected["issues"] == converted["issues"]
    assert inspected["receipt"] is None and inspected["counts"]["actual_files"] is None
    assert converted["counts"]["actual_generated_embeds"] == 2
    assert main(["check-vault", str(vault), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == 1
    # A historical verified receipt cannot establish current image existence.
    (vault / "Attachments/00000000000000000000000000000003/z-first.png").unlink()
    before = inventory(tmp_path)
    assert main(["check-vault", str(vault), "--json"]) == 2
    checked = json.loads(capsys.readouterr().out)
    assert any(i["code"] == "missing_image" for i in checked["issues"])
    assert main(["convert", str(source), str(vault), "--json"]) == 1
    refused = json.loads(capsys.readouterr().out)
    assert refused["outcome"] == "refused" and refused["receipt"] is None
    assert refused["counts"]["actual_generated_embeds"] is None
    assert inventory(tmp_path) == before


def reordered(source, destination):
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    for name in ("thoughts.json", "links.json", "attachments.json"):
        parts[name] = b"\n".join(reversed(parts[name].splitlines()))
    with ZipFile(destination, "w") as archive:
        for name, body in reversed(list(parts.items())):
            archive.writestr(name, body)


def test_mixed_repeats_and_zip_root_order_preserve_all_logical_output(tmp_path):
    source = mixed_v3_archive(tmp_path / "mixed.brz")
    other = tmp_path / "reordered.brz"
    reordered(source, other)
    with ZipFile(source) as a, ZipFile(other) as b:
        assert set(a.namelist()) == set(b.namelist())
        for path in a.namelist():
            if path in {"thoughts.json", "links.json", "attachments.json"}:
                assert sorted(a.read(path).splitlines()) == sorted(
                    b.read(path).splitlines()
                )
            else:
                assert a.read(path) == b.read(path)
    results = []
    for name, current in (("exact", source), ("repeat", source), ("reorder", other)):
        vault = tmp_path / name
        result = default_workflow().convert(current, vault)
        assert result.outcome == "warnings" and result.receipt.verified
        assert check_vault(vault).outcome == "clean"
        results.append(result)
    assert results[0].counts == results[1].counts == results[2].counts
    for name in ("repeat", "reorder"):
        exact = inventory(tmp_path / "exact")
        assert exact.keys() == inventory(tmp_path / name).keys()
        for path in exact:
            if path in {
                "migration-record.json",
                "MIGRATION REPORT.md",
                ".obsidian/bookmarks.json",
            }:
                continue
            assert (tmp_path / "exact" / path).read_bytes() == (
                tmp_path / name / path
            ).read_bytes()
        left = json.loads((tmp_path / "exact/migration-record.json").read_bytes())
        right = json.loads((tmp_path / name / "migration-record.json").read_bytes())
        reports = [
            (tmp_path / n / "MIGRATION REPORT.md").read_text(encoding="utf-8")
            for n in ("exact", name)
        ]
        for record in (left, right):
            for key in ("source_sha256", "snapshot_digest"):
                reports = [
                    report.replace(
                        record["source_identity"][key], "<source provenance>"
                    )
                    for report in reports
                ]
        assert reports[0] == reports[1]
        bookmarks = [
            json.loads((tmp_path / n / ".obsidian/bookmarks.json").read_bytes())
            for n in ("exact", name)
        ]
        for bookmark in bookmarks:
            bookmark["items"][0].pop("ctime")
        assert bookmarks[0] == bookmarks[1]
        # Every retained evidence record survives; only stream/member order may vary.
        evidence = []
        for record in (left, right):
            current = []
            for original in record["original_evidence"]:
                original = dict(original)
                if isinstance(original["records"], list):
                    original["records"] = sorted(
                        original["records"], key=lambda r: json.dumps(r, sort_keys=True)
                    )
                current.append(original)
            evidence.append(sorted(current, key=lambda e: (e["kind"], e["key"])))
        assert evidence[0] == evidence[1]
        for record in (left, right):
            for key in ("source_identity", "run_metadata", "original_evidence"):
                record.pop(key)
            record["relationships"].sort(key=lambda r: r["key"])
            record["source_accounting"]["entries"].sort(key=lambda e: e["identity"])
            record["adaptations"].sort(
                key=lambda a: (a["kind"], a["affected"] or "", a["description"])
            )

        def without_pointers(value):
            if isinstance(value, dict):
                return {
                    k: without_pointers(v)
                    for k, v in value.items()
                    if k not in {"evidence", "metadata_evidence"}
                }
            if isinstance(value, list):
                return [without_pointers(v) for v in value]
            return value

        assert without_pointers(left) == without_pointers(right)


@pytest.mark.parametrize(
    "defect", ["missing_card", "wrong_owner", "type_state", "video"]
)
def test_combined_near_miss_refuses_without_changing_caller(tmp_path, defect):
    source = mixed_v3_archive(tmp_path / "mixed.brz")
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    if defect == "missing_card":
        parts.pop(identity(3) + "/.data/md-images/z-first.png")
    elif defect == "type_state":
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"][identity(3001)] = 1
        parts["meta.json"] = json.dumps(meta).encode()
    else:
        records = [json.loads(line) for line in parts["attachments.json"].splitlines()]
        if defect == "wrong_owner":
            next(r for r in records if r["Id"] == identity(4010))["SourceId"] = (
                identity(4)
            )
        else:
            next(r for r in records if r["Id"] == identity(3007))["VideoHtml"] += (
                "<script>bad()</script>"
            )
        parts["attachments.json"] = b"\n".join(json.dumps(r).encode() for r in records)
    with ZipFile(source, "w") as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    (tmp_path / "caller.bin").write_bytes(b"caller\x00\xff")
    before = inventory(tmp_path)
    for result in (
        default_workflow().inspect(source),
        default_workflow().convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused" and result.receipt is None
        assert result.counts is None or result.counts.actual_files is None
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("entry", ["console", "module"])
def test_actual_mixed_console_module_text_json_routes_agree(
    tmp_path, monkeypatch, entry
):
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")
    source = mixed_v3_archive(tmp_path / "mixed.brz")
    command = (
        [str(Path(sys.executable).with_name("brz2obsidian.exe"))]
        if entry == "console"
        else [sys.executable, "-m", "brz2obsidian"]
    )
    for json_mode in (False, True):
        before = inventory(tmp_path)
        inspected = subprocess.run(
            [*command, "inspect", str(source), *(["--json"] if json_mode else [])],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert inspected.returncode == 2 and inspected.stderr == ""
        if json_mode:
            envelope = json.loads(inspected.stdout)
            assert (
                envelope["schema_version"] == 3 and envelope["profile_version"] == "3"
            )
            assert envelope["counts"]["planned_generated_embeds"] == 2
        else:
            assert "approved_source_gap" in inspected.stdout
        assert inventory(tmp_path) == before
        vault = tmp_path / ("json" if json_mode else "text")
        converted = subprocess.run(
            [
                *command,
                "convert",
                str(source),
                str(vault),
                *(["--json"] if json_mode else []),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert converted.returncode == 2 and converted.stderr == ""
        if json_mode:
            assert json.loads(converted.stdout)["counts"]["actual_files"] == 36
        checked = subprocess.run(
            [*command, "check-vault", str(vault), "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert (
            checked.returncode == 0
            and json.loads(checked.stdout)["schema_version"] == 1
        )


def test_mixed_injected_metadata_and_reprepared_source_bind_actual_publication(
    tmp_path,
):
    source = mixed_v3_archive(tmp_path / "mixed.brz")
    workflow = Workflow(
        SourceModuleBinding(BrzSourceModule(), BRZ_POLICY),
        ObsidianRenderer(),
        FilesystemPublisher(),
        metadata_factory=lambda: METADATA.model_copy(
            update={"converter_version": "0.3.0"}
        ),
    )
    inspection = workflow.inspect(source)
    # The caller replaces a valid archive after inspection. Convert must prepare it
    # afresh and bind to the new supplied body rather than retaining stale facts.
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    body = b"Fresh Home source.\r\n"
    parts[identity(1) + "/Notes.md"] = body
    records = [json.loads(line) for line in parts["attachments.json"].splitlines()]
    next(r for r in records if r["Id"] == identity(2001))["DataLength"] = len(body)
    parts["attachments.json"] = b"\n".join(json.dumps(r).encode() for r in records)
    with ZipFile(source, "w") as archive:
        for name, payload in parts.items():
            archive.writestr(name, payload)
    result = workflow.convert(source, tmp_path / "vault")
    assert result.outcome == "warnings" and result.receipt.verified
    assert (
        inspection.source_identity.source_sha256 != result.source_identity.source_sha256
    )
    assert result.source_identity == result.receipt.source_identity
    assert (
        tmp_path
        / "vault/Attachments/00000000000000000000000000000001/Notes.md.original"
    ).read_bytes() == body
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert record["run_metadata"]["run_id"] == "test-run"
    assert record["source_identity"] == result.source_identity.model_dump()
