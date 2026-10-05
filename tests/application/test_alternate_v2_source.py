"""Source-neutral v2 meanings, independently authored in an opaque format."""

import argparse
import json
import sys
from contextlib import contextmanager

import pytest
import yaml
from pydantic import ValidationError

from brz2obsidian.contracts import (
    MigrationRefused,
    RunResult,
    SourcePolicy,
    SourceSnapshot,
)
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import render
from brz2obsidian.publication import publish
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from brz2obsidian.vault_check import check_vault
from tests.application.test_alternate_source import update_folio, workflow
from tests.application.test_module_seams import METADATA
from tests.support.folio_source import FOLIO_POLICY, FolioSourceModule
from tests.support.paired_sources import identity
from tests.support.paired_v2_sources import (
    DEFINITION_BODY,
    EMBED,
    MEMBER_IMAGE,
    TYPE_IMAGE,
    URL,
    paired_v2_sources,
)
from tests.support.v2_collection import SUPPORT_PATHS, inventory


def test_opaque_source_reuses_categories_dates_icons_video_and_support(tmp_path):
    brz, folio = paired_v2_sources(tmp_path)
    results, vaults, records = [], [], []
    for n, (module, policy, source) in enumerate(
        (
            (BrzSourceModule(), BRZ_POLICY, brz),
            (FolioSourceModule(), FOLIO_POLICY, folio),
        )
    ):
        vault = tmp_path / f"vault-{n}"
        inspected = workflow(module, policy).inspect(source)
        assert inspected.outcome == "clean", inspected.issues
        result = workflow(module, policy).convert(source, vault)
        assert result.outcome == "clean", result.issues
        assert result.receipt.verified and result.receipt.published
        assert (
            result.counts.actual_notes,
            result.counts.actual_assets,
            result.counts.source_definitions,
            result.counts.typed_members,
            result.counts.classification_assignments,
        ) == (5, 7, 1, 2, 2)
        actual = inventory(vault)
        assert set(actual) == SUPPORT_PATHS | {
            "Home — Opening.md",
            "Notes/Empty.md",
            "Notes/Middle.md",
            "Notes/Focus.md",
            "Categories/Concept.md",
            "Attachments/00000001/Notes.md.original",
            "Attachments/00000006/Notes.md.original",
            "Attachments/00000001/map.png",
            "Attachments/00000001/manual.bin",
            "Attachments/0000000b/type.png",
            "Attachments/00000004/override.png",
            "Attachments/0000000b/Notes.md.original",
        }
        assert result.counts.actual_files == 31
        assert {
            f.relative_path: (f.length, f.sha256) for f in result.receipt.manifest
        } == actual
        assert check_vault(vault).outcome == "clean"
        assert inventory(vault) == actual
        record = json.loads((vault / "migration-record.json").read_bytes())
        assert {t["relative_path"]: t["created"] for t in record["item_targets"]} == {
            "Home — Opening.md": True,
            "Notes/Empty.md": True,
            "Notes/First.md": False,
            "Notes/Middle.md": True,
            "Notes/Last.md": False,
            "Notes/Focus.md": True,
            "Notes/Unused.md": False,
            "Notes/Left.md": False,
            "Notes/Right.md": False,
            "Notes/Alone.md": False,
            "Categories/Concept.md": True,
        }
        assert (vault / "Attachments/0000000b/type.png").read_bytes() == TYPE_IMAGE
        assert (
            vault / "Attachments/00000004/override.png"
        ).read_bytes() == MEMBER_IMAGE
        assert (
            vault / "Attachments/0000000b/Notes.md.original"
        ).read_bytes() == DEFINITION_BODY
        results.append(result)
        vaults.append(vault)
        records.append(record)
    assert results[0].counts == results[1].counts
    assert results[0].source_identity != results[1].source_identity
    for path, number, key in (
        ("Home — Opening.md", 1, "entry:opening"),
        ("Notes/Empty.md", 2, "empty:leaf"),
        ("Notes/Middle.md", 4, "chain:middle"),
        ("Notes/Focus.md", 6, "tag:focus"),
        ("Categories/Concept.md", 11, "category:concept"),
    ):
        notes = [(v / path).read_bytes() for v in vaults]
        props = [yaml.safe_load(t.decode().split("---", 2)[1]) for t in notes]
        for n, p in enumerate(props):
            assert p.pop("source_collection_id") == results[n].source_identity.source_id
            assert p.pop("source_item_id") == (identity(number) if n == 0 else key)
        assert props[0] == props[1]
        assert notes[0].split(b"---\n", 2)[2] == notes[1].split(b"---\n", 2)[2]
        if key == "chain:middle":
            assert str(props[1]["created"]) == "2024-02-29"
            assert str(props[1]["updated"]) == "2025-01-01"
            assert props[1]["icon"] == "[[Attachments/00000004/override.png]]"
        if key == "empty:leaf":
            assert props[1]["categories"] == ["[[Categories/Concept.md]]"]
            assert props[1]["appearance_category"] == "[[Categories/Concept.md]]"
            assert props[1]["icon"] is None
    video = next(
        a for a in records[1]["asset_targets"] if a["asset_id"] == "asset:110:video"
    )
    assert video["external_uri"] == video["resource_link"] == URL
    assert video["video_presentation"] == {
        "provider": "youtube",
        "embed_uri": EMBED,
        "start_seconds": 18,
    }
    assert (
        f"- [Video](<{URL}>)".encode() in (vaults[1] / "Home — Opening.md").read_bytes()
    )
    assert EMBED.encode() in (vaults[1] / "Home — Opening.md").read_bytes()
    assert {a["item_key"] for a in records[1]["classification_assignments"]} == {
        "empty:leaf",
        "chain:middle",
    }
    targets = {t["item_key"]: t for t in records[1]["item_targets"]}
    assert targets["empty:leaf"]["creation_reasons"] == ["classification"]
    assert (
        targets["empty:leaf"]["icon_snapshot"]["effective_icon_asset_id"]
        == "asset:107:category-image"
    )
    assert (
        targets["chain:middle"]["icon_snapshot"]["effective_icon_asset_id"]
        == "asset:108:owned-image"
    )
    assert targets["chain:middle"]["calendar_dates"] == {
        "created": "2024-02-29",
        "updated": "2025-01-01",
    }
    assert records[1]["original_evidence"][0]["records"] == json.loads(
        folio.read_bytes()
    )
    assert targets["category:concept"]["original_identity"] == "category:concept"
    assert targets["category:concept"]["original_identity"] != identity(11)
    for artifact in records[1]["support_artifacts"]:
        if artifact["purpose"] not in {"migration_record", "report"}:
            assert (vaults[0] / artifact["relative_path"]).read_bytes() == (
                vaults[1] / artifact["relative_path"]
            ).read_bytes()


@pytest.mark.parametrize(
    "fault",
    [
        "missing_assignment",
        "duplicate_assignment",
        "missing_relation",
        "wrong_definition",
        "wrong_member",
        "missing_icon",
        "foreign_icon",
        "missing_evidence",
        "invented_evidence",
    ],
)
def test_opaque_classification_and_owned_icons_refuse_inconsistent_facts(
    tmp_path, fault
):
    _, source = paired_v2_sources(tmp_path)

    def change(data):
        if fault == "missing_assignment":
            data["assignments"].pop()
        elif fault == "duplicate_assignment":
            data["assignments"].append(data["assignments"][0])
        elif fault == "missing_relation":
            data["connections"].pop()
        elif fault == "wrong_definition":
            data["assignments"][0]["definition_key"] = "entry:opening"
        elif fault == "wrong_member":
            data["assignments"][0]["item_key"] = "category:concept"
        elif fault in {"missing_icon", "foreign_icon"}:
            data["entries"][3]["appearance"]["icon_asset_id"] = (
                "absent:icon" if fault == "missing_icon" else "asset:107:category-image"
            )

    update_folio(source, change)

    class EvidenceControl(FolioSourceModule):
        @contextmanager
        def open(self, path):
            with super().open(path) as session:
                if fault in {"missing_evidence", "invented_evidence"}:
                    assignments = session.snapshot.classification_assignments
                    changed = assignments[0].model_copy(
                        update={
                            "evidence": ()
                            if fault == "missing_evidence"
                            else ("invented",)
                        }
                    )
                    session.snapshot = session.snapshot.model_copy(
                        update={
                            "classification_assignments": (changed,) + assignments[1:]
                        }
                    )
                yield session

    result = workflow(EvidenceControl(), FOLIO_POLICY).convert(
        source, tmp_path / "vault"
    )
    assert result.outcome == "refused" and result.issues[0].code == "invalid_reference"
    assert result.receipt is None and not (tmp_path / "vault").exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


@pytest.mark.parametrize("version", [1, 3])
@pytest.mark.parametrize("contract", ["snapshot", "policy"])
def test_opaque_current_contract_rejects_other_versions_at_constructor_and_public_core(
    tmp_path, version, contract
):
    _, source = paired_v2_sources(tmp_path)
    with FolioSourceModule().open(source) as session:
        snapshot = session.snapshot
    value = snapshot if contract == "snapshot" else FOLIO_POLICY
    cls = SourceSnapshot if contract == "snapshot" else SourcePolicy
    with pytest.raises(ValidationError):
        cls(**(value.model_dump() | {"contract_version": version}))
    # Explicitly bypass construction to prove analyze revalidates inbound versions.
    bypassed = value.model_copy(update={"contract_version": version})
    with pytest.raises(MigrationRefused) as refused:
        analyze(
            bypassed if contract == "snapshot" else snapshot,
            bypassed if contract == "policy" else FOLIO_POLICY,
        )
    assert refused.value.issues[0].code == "unsupported_format"


def test_opaque_v2_public_modules_and_another_presentation_need_no_cli(
    tmp_path, monkeypatch, capsys
):
    _, source = paired_v2_sources(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("Library use must not parse arguments or exit")

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", forbidden)
    monkeypatch.setattr(sys, "exit", forbidden)
    with FolioSourceModule().open(source) as session:
        analysis = analyze(session.snapshot, FOLIO_POLICY)
        migration = plan(analysis)
        receipt = publish(render(migration, METADATA), session, tmp_path / "direct")
    assert (
        receipt.counts.actual_notes == 5 and receipt.counts.actual_category_notes == 1
    )
    result = workflow(FolioSourceModule(), FOLIO_POLICY).inspect(source)
    consumed = RunResult.model_validate_json(result.model_dump_json(by_alias=True))
    view = {
        "status": consumed.outcome,
        "categories": consumed.counts.planned_category_notes,
        "members": consumed.counts.typed_members,
        "support": consumed.counts.planned_support_files,
    }
    assert view == {"status": "clean", "categories": 1, "members": 2, "support": 19}
    assert capsys.readouterr() == ("", "")
