"""Standard profile5 composition against unchanged independent source evidence."""

import hashlib
import json
import struct
from shutil import copytree

import pytest
import yaml

from brz2obsidian.application.contracts import (
    LocalApiSourceSelection,
    ReviewedInspection,
)
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.application.workflow import SourceModuleBinding, Workflow
from brz2obsidian.obsidian import ObsidianRenderer
from brz2obsidian.publication import FilesystemPublisher
from brz2obsidian.sources.thebrain.local_api import (
    LOCAL_API_POLICY_V4,
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from brz2obsidian.vault_check import check_vault
from tests.application.test_graph_workflow import identity
from tests.local_acceptance.api_checker import check_api_vault
from tests.local_acceptance.api_icon_inputs import bmp, ico, icon_source_packet
from tests.local_acceptance.test_api_scope_v3 import packet_baseline
from tests.support.local_api import KEY, api_server
from tests.support.local_api_packet import RawPacketApi
from tests.support.local_api_payloads import JPEG, PNG, attachment
from tests.support.type_tag_sources import DEEP_ICON, DIRECT, IDS, TypeTagApi

BRAIN = "00000000-0000-4000-8000-000000000001"
HOME = "00000000-0000-4000-8000-000000000002"
ICON = "00000000-0000-4000-8000-000000000206"


@pytest.mark.parametrize("kind", ["bmp", "ico"])
def test_standard5_output_matches_independent_icon_baseline(tmp_path, kind):
    fixture = bmp() if kind == "bmp" else ico((2, 3), physical=(1, 0))
    packet = icon_source_packet(fixture["raw"])
    baseline = packet_baseline(tmp_path / "source", packet)
    vault = tmp_path / "vault"
    with api_server(RawPacketApi.from_source_packet(packet)) as (_, origin):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=origin), credentials=lambda: KEY
        )
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "clean", inspected.issues
        assert workflow.binding.policy.profile_version == "5"
        assert workflow.binding.source.profile_version == "5"
        assert inspected.profile_version == "5"
        converted = workflow.convert(LocalApiSourceRef(BRAIN), vault)
        assert converted.outcome == "clean", converted.issues
        assert converted.receipt.verified
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert record["profile_version"] == "5"
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == ICON)
    assert (
        asset["owner"],
        asset["role"],
        asset["original_name"],
        asset["actual_length"],
        asset["actual_sha256"],
    ) == (HOME, "icon", "Icon.png", fixture["length"], fixture["sha256"])
    assert (vault / asset["relative_path"]).read_bytes() == fixture["raw"]
    check_api_vault(baseline, vault, profile_version="5")
    if kind == "ico":
        for damage in (
            "omitted",
            "missing_copy",
            "dropped_frame",
            "changed_artwork",
            "owner",
            "effective_icon",
            "count",
            "profile",
        ):
            target = tmp_path / damage
            copytree(vault, target)
            path = target / "migration-record.json"
            changed = json.loads(path.read_bytes())
            row = next(a for a in changed["asset_targets"] if a["asset_id"] == ICON)
            copied = target / row["relative_path"]
            if damage == "omitted":
                changed["asset_targets"].remove(row)
                for count in ("present_assets", "planned_assets"):
                    changed["counts"][count] -= 1
            elif damage == "missing_copy":
                copied.unlink()
            elif damage in {"dropped_frame", "changed_artwork"}:
                if damage == "dropped_frame":
                    original = fixture["raw"]
                    assert struct.unpack_from("<HHH", original) == (0, 1, 2)
                    preferred = fixture["frames"][1]
                    assert (preferred["width"], preferred["height"]) == (3, 3)
                    entry = original[22:38]
                    assert entry[:2] == b"\x03\x03"
                    length, offset = struct.unpack_from("<II", entry, 8)
                    assert (length, offset) == (
                        preferred["body_length"],
                        preferred["offset"],
                    )
                    body = original[offset : offset + length]
                    assert hashlib.sha256(body).hexdigest() == preferred["body_sha256"]
                    raw = original[:4] + struct.pack("<H", 1)
                    raw += entry[:12] + struct.pack("<I", 22) + body
                    assert struct.unpack_from("<HHH", raw) == (0, 1, 1)
                    assert raw[6:8] == b"\x03\x03" and raw[22:] == body
                    assert len(raw) == 22 + preferred["body_length"]
                    replacement = {
                        "raw": raw,
                        "length": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                else:
                    replacement = ico((2, 3), physical=(1, 0), opaque=True)
                    assert replacement["length"] == fixture["length"]
                copied.write_bytes(replacement["raw"])
                row.update(
                    actual_length=replacement["length"],
                    actual_sha256=replacement["sha256"],
                )
            elif damage == "owner":
                row["owner"] = "00000000-0000-4000-8000-000000000003"
            elif damage == "effective_icon":
                item = next(t for t in changed["item_targets"] if t["item_key"] == HOME)
                item["icon_snapshot"]["effective_icon_asset_id"] = None
                note = target / item["relative_path"]
                note.write_text(
                    note.read_text(encoding="utf-8").replace(
                        "![[" + row["relative_path"] + "]]\n\n", ""
                    ),
                    encoding="utf-8",
                )
            elif damage == "count":
                changed["counts"]["present_assets"] += 1
            else:
                changed["profile_version"] = "4"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with pytest.raises(AssertionError):
                check_api_vault(baseline, target, profile_version="5")
        check_api_vault(baseline, vault, profile_version="5")


def test_standard5_full_chain_preserves_owned_icons_and_accounting(tmp_path):
    from tests.support.local_api import BRAIN as SOURCE_BRAIN
    from tests.support.local_api import HOME as ENTRY
    from tests.support.type_tag_sources import ICON as A_ICON

    api = TypeTagApi(deep=True)
    b_icon, d_icon, entry_icon = identity(505), identity(506), identity(507)
    originals = {
        A_ICON: (IDS["A"], ico((2, 3), physical=(1, 0))["raw"]),
        b_icon: (IDS["B"], bmp()["raw"]),
        d_icon: (IDS["D"], PNG),
        DEEP_ICON: (identity(30), JPEG),
        entry_icon: (ENTRY, JPEG),
    }
    for key, (owner, raw) in originals.items():
        api.attachments[key] = attachment(key, owner, 5, "Icon.png", length=len(raw))
        api.payloads[key] = raw
    with api_server(api) as (_, origin):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=origin), credentials=lambda: KEY
        )
        inspected = workflow.inspect(LocalApiSourceRef(SOURCE_BRAIN))
        assert inspected.outcome == "warnings", inspected.issues
        icons = {s.item_key: s for s in inspected.inspection.icon_snapshots}
        assert {
            name: icons[IDS[name]].effective_icon_asset_id for name in "ABCDEFG"
        } == {
            "A": A_ICON,
            "B": b_icon,
            "C": b_icon,
            "D": d_icon,
            "E": A_ICON,
            "F": A_ICON,
            "G": A_ICON,
        }
        for key in (identity(40), identity(41)):
            assert icons[key].effective_icon_asset_id == DEEP_ICON
        converted = workflow.convert(
            LocalApiSourceRef(SOURCE_BRAIN), tmp_path / "vault"
        )
        assert converted.outcome == "warnings" and converted.receipt.verified
    vault = tmp_path / "vault"
    record = json.loads((vault / "migration-record.json").read_bytes())
    targets = {t["item_key"]: t for t in record["item_targets"]}
    assets = {a["asset_id"]: a for a in record["asset_targets"]}
    assert set(assets) == set(originals)
    assert inspected.counts.present_assets == converted.counts.present_assets == 5
    assert converted.counts.planned_assets == converted.counts.actual_assets == 5
    assert sum(a["actual_length"] for a in assets.values()) == sum(
        len(raw) for _owner, raw in originals.values()
    )
    assert {
        (a["definition_key"], a["item_key"])
        for a in record["classification_assignments"]
        if a["item_key"] in IDS.values()
    } == {(IDS[parent], IDS[member]) for parent, member in DIRECT}
    for key, (owner, raw) in originals.items():
        asset = assets[key]
        assert (asset["owner"], asset["role"], asset["original_name"]) == (
            owner,
            "icon",
            "Icon.png",
        )
        assert (asset["actual_length"], asset["actual_sha256"]) == (
            len(raw),
            hashlib.sha256(raw).hexdigest(),
        )
        assert (vault / asset["relative_path"]).read_bytes() == raw
        accounting = next(
            a
            for a in record["source_accounting"]["entries"]
            if a["identity"] == "attachment:" + key
        )
        assert accounting["disposition"] == "normalized"
        assert accounting["references"] == [key]
    assert assets[DEEP_ICON]["actual_sha256"] == assets[entry_icon]["actual_sha256"]
    assert assets[DEEP_ICON]["owner"] != assets[entry_icon]["owner"]
    for key in (IDS["C"], IDS["E"], IDS["F"], IDS["G"], identity(40), identity(41)):
        text = (vault / targets[key]["relative_path"]).read_text(encoding="utf-8")
        props = yaml.safe_load(text.split("---", 2)[1])
        assert props["icon"] is None
        assert targets[key]["icon_snapshot"]["explicit_icon_asset_id"] is None
    for child, parent in (
        ("B", "A"),
        ("C", "B"),
        ("D", "C"),
        ("E", "A"),
        ("F", "E"),
        ("G", "A"),
    ):
        text = (vault / targets[IDS[child]]["relative_path"]).read_text(
            encoding="utf-8"
        )
        props = yaml.safe_load(text.split("---", 2)[1])
        assert props["categories"] == [f"[[Categories/{parent}.md]]"]
        assert props["appearance_category"] == f"[[Categories/{parent}.md]]"
    for target in targets.values():
        if target["relative_path"] and target["relative_path"].startswith(
            "Categories/"
        ):
            assert "![[Attachments/" not in (vault / target["relative_path"]).read_text(
                encoding="utf-8"
            )
    for key in (identity(40), identity(41)):
        assert "![[" + assets[DEEP_ICON]["relative_path"] + "]]" in (
            vault / targets[key]["relative_path"]
        ).read_text(encoding="utf-8")
    bases = [
        yaml.safe_load((vault / f"Templates/Bases/{name}.base").read_bytes())
        for name in ("Members", "Gallery", "Categories")
    ]
    assert bases[0]["formulas"] == bases[1]["formulas"] == bases[2]["formulas"]
    assert "formula.r8" in bases[0]["formulas"]["effective_icon"]
    assert "r9" not in bases[0]["formulas"]
    assert {(i.code, i.affected[0]) for i in converted.issues} == {
        ("icon_lookup_depth", identity(39)),
        ("icon_lookup_depth", identity(41)),
    }
    assert {(i.code, i.artifact) for i in check_vault(vault).issues} == {
        ("icon_lookup_depth", "Categories/H9.md"),
        ("icon_lookup_depth", "Notes/N9.md"),
    }


@pytest.mark.parametrize("source_version", ["4", "5"])
def test_standard5_refuses_profile4_review(tmp_path, source_version):
    from tests.sources.test_local_api_images_v3 import IcoIconApi
    from tests.support.local_api import BRAIN as SOURCE_BRAIN

    with api_server(IcoIconApi(PNG)) as (_, origin):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=origin),
            credentials=lambda: KEY,
            profile_version=source_version,
        )
        workflow = Workflow(
            SourceModuleBinding(module, LOCAL_API_POLICY_V4),
            ObsidianRenderer(),
            FilesystemPublisher(),
        )
        inspected = workflow.inspect(LocalApiSourceRef(SOURCE_BRAIN))
        assert inspected.outcome == "clean", inspected.issues
        selection = LocalApiSourceSelection(
            brain_id=SOURCE_BRAIN, config={"api_url": origin}
        )
        reviewed = ReviewedInspection(
            source_selection=selection,
            source_identity=inspected.source_identity,
            converter_version=inspected.converter_version,
            output_format=inspected.inspection.output_format,
            profile_id=inspected.profile_id,
            profile_version=inspected.profile_version,
            outcome="clean",
        )
        operations = Operations(credentials=lambda: KEY)
        stale = operations.convert_reviewed(selection, tmp_path, "stale", reviewed)
        assert stale.outcome == "refused" and stale.review_required
        assert {f.code for f in stale.findings} == {"review_changed"}
        assert (
            not stale.publication.receipt_verified and not (tmp_path / "stale").exists()
        )
        if source_version == "5":
            current = operations.inspect(selection)
            assert current.reviewed.profile_version == "5"
            assert current.reviewed.source_identity == reviewed.source_identity
            result = operations.convert_reviewed(
                selection, tmp_path, "current", current.reviewed
            )
            assert result.publication.receipt_verified


def test_standard5_required_icon_refusal_leaves_no_output(tmp_path):
    from tests.sources.test_local_api_images_v3 import IcoIconApi
    from tests.support.local_api import BRAIN as SOURCE_BRAIN

    broken = ico((2, 3), physical=(1, 0))["raw"][:-1]
    with api_server(IcoIconApi(broken)) as (_, origin):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=origin), credentials=lambda: KEY
        )
        result = workflow.convert(LocalApiSourceRef(SOURCE_BRAIN), tmp_path / "refused")
        assert result.outcome == "refused" and result.receipt is None
        assert {issue.code for issue in result.issues} == {"invalid_source"}
        assert KEY not in result.model_dump_json()
        assert not (tmp_path / "refused").exists()
