"""Independent profile5 checker controls; no profile5 production is invoked."""

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path

import pytest

from tests.local_acceptance.api_checker import (
    audit_baseline,
    check_api_vault,
    expected_asset,
)
from tests.local_acceptance.api_icon_inputs import (
    bmp,
    ico,
    icon_source_packet,
    json_bytes,
    patch,
    support_base8,
)
from tests.local_acceptance.test_api_scope_v3 import (
    complete_raster_support,
    packet_baseline,
    raster_scope_baseline,
    raster_scope_case,
    scope_baseline,
)

ICON = "00000000-0000-4000-8000-000000000206"
HOME = "00000000-0000-4000-8000-000000000002"


def handcrafted_icon_vault(directory, raw=None, *, output_version=7):
    """Full handwritten support fixture. Never a conversion or sealed capture."""
    from tests.local_acceptance.api_generated import STATIC

    raw = bmp()["raw"] if raw is None else raw
    # Reuse an independently handwritten full7 support example; add the two
    # explicitly declared icon representations below. No checker supplies output.
    _, vault = raster_scope_case(directory / "example", excluded=True, profile="3")
    baseline = packet_baseline(directory / "icon-source", icon_source_packet(raw))
    complete_raster_support(baseline, vault)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["profile_version"] = "5"
    row = baseline.json(baseline.data["attachment_metadata"][ICON]["path"])
    pointer = "attachment:" + ICON
    relative = "Attachments/" + ICON + "/Icon.png"
    target = vault / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(raw)
    record["asset_targets"].append(
        {
            "asset_id": ICON,
            "owner": HOME,
            "naming_seed": ICON.replace("-", ""),
            "original_name": "Icon.png",
            "display_name": None,
            "role": "icon",
            "availability": "present",
            "actual_length": len(raw),
            "actual_sha256": hashlib.sha256(raw).hexdigest(),
            "external_uri": None,
            "video_presentation": None,
            "evidence": [pointer],
            "relative_path": relative,
            "resource_link": None,
            "source_findings": [],
            "retained_documents": [],
        }
    )
    record["original_evidence"].append(
        {
            "key": pointer,
            "kind": "records",
            "records": dict(row, position={"decimal": "2"}),
        }
    )
    graph = next(
        e["records"] for e in record["original_evidence"] if e["key"] == "graph:" + HOME
    )
    graph["attachment_ids"].append(ICON)
    record["source_accounting"]["entries"].append(
        {"identity": pointer, "disposition": "normalized", "references": [ICON]}
    )
    home = next(t for t in record["item_targets"] if t["item_key"] == HOME)
    home["declared_appearance"] = {
        "icon_asset_id": ICON,
        "foreground_color": None,
        "background_color": None,
    }
    home["icon_snapshot"].update(
        explicit_icon_asset_id=ICON, effective_icon_asset_id=ICON
    )
    for kind, description in (
        ("declared_appearance", STATIC["GP07-DESCRIPTION-10"]),
        (
            "body_icon_snapshot",
            STATIC["GP07-DESCRIPTION-17"]
            + ICON
            + STATIC["GP07-DESCRIPTION-18"]
            + STATIC["GP07-DESCRIPTION-11"],
        ),
    ):
        record["adaptations"].append(
            {
                "kind": kind,
                "affected": HOME,
                "description": description,
                "document_key": None,
                "owner": None,
                "evidence": [],
                "text_edit": None,
            }
        )
    for key in ("present_assets", "planned_assets"):
        record["counts"][key] = 2
    text = (vault / "Home.md").read_text(encoding="utf8")
    text = text.replace("\nicon:\n", '\nicon: "[[' + relative + ']]"\n', 1)
    text = text.replace("# Home\n\n", "# Home\n\n![[" + relative + "]]\n\n", 1)
    (vault / "Home.md").write_text(text, encoding="utf8", newline="\n")
    report = (vault / "MIGRATION REPORT.md").read_text(encoding="utf8")
    (vault / "MIGRATION REPORT.md").write_text(
        report.replace(
            "preserved 1 present payloads.", "preserved 2 present payloads."
        ),
        encoding="utf8",
        newline="\n",
    )
    if output_version == 8:
        from tests.local_acceptance.api_generated import versioned_static
        from tests.local_acceptance.support import REOPEN_GUIDANCE

        record.update(schema_version=8, renderer_version="8")
        record["run_metadata"]["renderer_version"] = "8"
        for title, role in (
            ("Members", "members"),
            ("Gallery", "gallery"),
            ("Categories", "categories"),
            ("Starter", "members"),
        ):
            (vault / ("Templates/Bases/" + title + ".base")).write_text(
                support_base8(role), encoding="utf8", newline="\n"
            )
        (vault / "Categories.md").write_text(
            "# Categories\n\n"
            + REOPEN_GUIDANCE
            + "![[Templates/Bases/Categories.base]]\n",
            encoding="utf8",
            newline="\n",
        )
        category = vault / "Templates/Category starter.md"
        category.write_text(
            category.read_text(encoding="utf8").replace(
                "## Members", REOPEN_GUIDANCE + "## Members", 1
            ),
            encoding="utf8",
            newline="\n",
        )
        guide = vault / "Vault guide.md"
        guide.write_text(
            guide.read_text(encoding="utf8").replace(
                STATIC["GP05-GUIDE-00"], versioned_static(8)["GP05-GUIDE-00"], 1
            ),
            encoding="utf8",
            newline="\n",
        )
    path.write_bytes(json_bytes(record))
    return baseline, vault


def test_complete_handcrafted_icon_output_is_source_bound(tmp_path):
    baseline, vault = handcrafted_icon_vault(tmp_path)
    assert check_api_vault(baseline, vault, profile_version="5") == {
        "thoughts": 2,
        "relationships": 3,
        "payloads": 2,
    }


def test_complete_current_format8_icon_output_is_independently_handcrafted(tmp_path):
    baseline, vault = handcrafted_icon_vault(tmp_path, output_version=8)
    assert check_api_vault(baseline, vault, profile_version="5") == {
        "thoughts": 2,
        "relationships": 3,
        "payloads": 2,
    }


def change_packet_declaration(packet, field, value):
    """Change every raw declaration observation consistently, not its owner join."""

    def visit(row):
        if isinstance(row, dict):
            if row.get("id") == ICON:
                row[field] = value
            for child in row.values():
                visit(child)
        elif isinstance(row, list):
            for child in row:
                visit(child)

    for path, raw in list(packet["files"].items()):
        if path.endswith(".json"):
            try:
                row = json.loads(raw)
            except ValueError, UnicodeError:
                continue
            visit(row)
            packet["files"][path] = json_bytes(row)


@pytest.mark.parametrize(
    "field,value",
    [
        ("brainId", "11111111-1111-4111-8111-111111111111"),
        ("sourceId", "00000000-0000-4000-8000-000000000003"),
        ("sourceType", 1),
        ("sourceType", True),
        ("type", 1),
        ("type", 12),
        ("name", "Icon"),
        ("location", "Other.png"),
        ("isNotes", True),
    ],
)
def test_checker_rejects_wrong_original_icon_declarations(tmp_path, field, value):
    packet = icon_source_packet()
    change_packet_declaration(packet, field, value)
    baseline = packet_baseline(tmp_path / "source", packet)
    with pytest.raises(AssertionError):
        audit_baseline(baseline, profile_version="5")


def add_packet_icon(packet, owner):
    key = "00000000-0000-4000-8000-000000000207"
    data, files = packet["baseline_inputs"], packet["files"]
    original = json.loads(files[data["attachment_metadata"][ICON]["path"]])
    row = dict(original, id=key, sourceId=owner)
    for path in (data["graphs"][owner], data["attachment_inventories"][owner]):
        value = json.loads(files[path])
        (value["attachments"] if isinstance(value, dict) else value).append(row)
        files[path] = json_bytes(value)
    metadata = "responses/second-icon-metadata.json"
    files[metadata] = json_bytes(row)
    data["attachment_metadata"][key] = {"status": 200, "path": metadata}
    data["payloads"][key] = dict(data["payloads"][ICON])
    data["scope"]["attachment_ids"].append(key)
    ledger_path = data["source_packet_ledger"]
    ledger = json.loads(files[ledger_path])
    ledger["routes"].extend(
        [
            {
                "method": "GET",
                "route": f"/api/attachments/{row['brainId']}/{key}/metadata",
                "status": 200,
                "body_path": metadata,
                "optional": False,
            },
            {
                "method": "GET",
                "route": f"/api/attachments/{row['brainId']}/{key}/file-content",
                "status": 200,
                "body_path": data["payloads"][key]["path"],
                "optional": False,
            },
        ]
    )
    files[ledger_path] = json_bytes(ledger)
    return key


@pytest.mark.parametrize(
    "damage", ["ambiguous", "payload-omitted", "declaration-omitted"]
)
def test_checker_rejects_missing_or_ambiguous_icon_inputs(tmp_path, damage):
    packet = icon_source_packet()
    if damage == "ambiguous":
        add_packet_icon(packet, HOME)
    elif damage == "payload-omitted":
        del packet["baseline_inputs"]["payloads"][ICON]
    else:
        for path in (
            packet["baseline_inputs"]["graphs"][HOME],
            packet["baseline_inputs"]["attachment_inventories"][HOME],
        ):
            value = json.loads(packet["files"][path])
            rows = value["attachments"] if isinstance(value, dict) else value
            rows[:] = [row for row in rows if row["id"] != ICON]
            packet["files"][path] = json_bytes(value)
    baseline = packet_baseline(tmp_path / "source", packet)
    with pytest.raises(AssertionError):
        audit_baseline(baseline, profile_version="5")


def test_equal_payloads_keep_distinct_source_identities_and_owners(tmp_path):
    packet = icon_source_packet()
    second = add_packet_icon(packet, "00000000-0000-4000-8000-000000000003")
    baseline = packet_baseline(tmp_path / "source", packet)
    audited = audit_baseline(baseline, profile_version="5")
    assert audited["payloads"] == 3
    proofs = audited["resource_eligibility"]
    assert (
        ICON != second
        and proofs[ICON]["source_sha256"] == proofs[second]["source_sha256"]
    )


@pytest.mark.parametrize(
    "damage",
    [
        "owner",
        "role",
        "name",
        "omitted-asset",
        "missing-copy",
        "altered-output",
        "output-hash",
        "effective-icon",
        "declared-icon",
        "count",
        "profile",
        "renamed-copy",
        "dropped-nondefault-frame",
    ],
)
def test_complete_checker_rejects_coherent_icon_output_corruptions(tmp_path, damage):
    raw = ico((2, 3))["raw"] if damage == "dropped-nondefault-frame" else None
    baseline, vault = handcrafted_icon_vault(tmp_path, raw)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    icon = next(row for row in record["asset_targets"] if row["asset_id"] == ICON)
    home = next(row for row in record["item_targets"] if row["item_key"] == HOME)
    copied = vault / icon["relative_path"]
    if damage == "owner":
        icon["owner"] = "00000000-0000-4000-8000-000000000003"
    elif damage == "role":
        icon["role"] = "file"
    elif damage == "name":
        icon["original_name"] = "icon.bmp"
    elif damage == "omitted-asset":
        record["asset_targets"].remove(icon)
        record["counts"]["present_assets"] -= 1
        record["counts"]["planned_assets"] -= 1
    elif damage == "missing-copy":
        copied.unlink()
    elif damage in {"altered-output", "dropped-nondefault-frame"}:
        changed = (
            ico((2,))["raw"]
            if damage.startswith("dropped")
            else patch(copied.read_bytes(), 54, "<B", 93)
        )
        copied.write_bytes(changed)
        icon.update(
            actual_length=len(changed),
            actual_sha256=hashlib.sha256(changed).hexdigest(),
        )
    elif damage == "output-hash":
        icon["actual_sha256"] = "f" * 64
    elif damage in {"effective-icon", "declared-icon"}:
        if damage == "effective-icon":
            home["icon_snapshot"]["effective_icon_asset_id"] = None
        else:
            home["declared_appearance"]["icon_asset_id"] = None
        text = (vault / "Home.md").read_text(encoding="utf8")
        (vault / "Home.md").write_text(
            text.replace("![[" + icon["relative_path"] + "]]\n\n", ""), encoding="utf8"
        )
    elif damage == "count":
        record["counts"]["present_assets"] += 1
    elif damage == "profile":
        record["profile_version"] = "4"
    else:
        relative = icon["relative_path"].removesuffix(".png") + ".bmp"
        (vault / relative).write_bytes(copied.read_bytes())
        icon["relative_path"] = relative
    path.write_bytes(json_bytes(record))
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="5")


def test_pinned_unrequested_artwork_and_untrusted_manifest_cannot_refresh_the_pin(
    tmp_path,
):
    from tests.local_acceptance.api_manifest import load_baseline

    baseline = packet_baseline(tmp_path / "source", icon_source_packet())
    path = baseline.manifest_path.parent / baseline.data["payloads"][ICON]["path"]
    before = path.stat()
    raw = path.read_bytes()
    changed = patch(raw, 54, "<B", 93)
    path.write_bytes(changed)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert (
        path.stat().st_size == before.st_size
        and path.stat().st_mtime_ns == before.st_mtime_ns
    )
    unrelated = baseline.json(
        baseline.data["attachment_metadata"]["00000000-0000-4000-8000-000000000202"][
            "path"
        ]
    )
    with pytest.raises(AssertionError, match="baseline evidence changed"):
        expected_asset(baseline, unrelated, "5")
    forged = deepcopy(baseline.data)
    forged["files"][baseline.data["payloads"][ICON]["path"]]["sha256"] = hashlib.sha256(
        changed
    ).hexdigest()
    baseline.manifest_path.write_bytes(json_bytes(forged))
    with pytest.raises(AssertionError, match="baseline manifest changed"):
        load_baseline(baseline.manifest_path, baseline.fingerprint)
    fresh = packet_baseline(tmp_path / "fresh", icon_source_packet(changed))
    assert (
        audit_baseline(fresh, profile_version="5")["resource_eligibility"][ICON][
            "source_sha256"
        ]
        != hashlib.sha256(raw).hexdigest()
    )
    assert fresh.fingerprint != baseline.fingerprint


def test_profile5_qualified_uri_semantics_do_not_relabel_historical_profiles():
    from tests.local_acceptance.api_scope import scope_note

    uri = "brain://api.thebrain.com/EREREREREUGBEREREREREQ/MzMzMzMzM0ODMzMzMzMzMw/title"
    authored = "[Target](" + uri + ")"
    assert scope_note(
        authored,
        {},
        qualified_brain="11111111-1111-4111-8111-111111111111",
        profile_version="5",
    ) == (authored, frozenset())
    with pytest.raises(AssertionError, match="qualified URI outside"):
        scope_note(authored, {}, profile_version="3")


def test_profile5_raw_mixed_metadata_keeps_type_tag_and_navigation_roles(tmp_path):
    from tests.local_acceptance.api_checker import source_facts

    baseline = scope_baseline(tmp_path / "mixed")
    thoughts, relations, attachments, _ = source_facts(baseline, profile_version="5")

    def identity(n):
        return f"00000000-0000-4000-8000-{n:012d}"

    assert set(thoughts) == {identity(n) for n in range(2, 10)}
    assert relations[identity(104)] == {
        "key": identity(104),
        "kind": "classification",
        "item_a": identity(4),
        "item_b": identity(3),
    }
    assert relations[identity(105)] == {
        "key": identity(105),
        "kind": "tag",
        "item_a": identity(5),
        "item_b": identity(3),
    }
    assert thoughts[identity(3)]["typeId"] == identity(4)
    assert {row["kind"] for row in relations.values()} == {
        "hierarchy",
        "related",
        "classification",
        "tag",
    }
    assert attachments[identity(301)]["type"] == attachments[identity(302)]["type"] == 5


def test_component_owned_icon_priority_and_inherited_markup_are_independent():
    from tests.local_acceptance.api_checker import check_image_icon_markup
    from tests.local_acceptance.appearance import source_icon

    member, category = "member", "type"
    bindings = {
        "own": {"role": "icon", "relative_path": "Attachments/member/Icon.png"},
        "inherited": {"role": "icon", "relative_path": "Attachments/type/Icon.png"},
    }
    names = {member: "Notes/Member.md", category: "Categories/Type.md"}
    thought = {"name": "Member", "kind": 1}
    for explicit, expected in ((None, "inherited"), ("own", "own")):
        icons = {category: "inherited"} | ({member: explicit} if explicit else {})
        assert (
            source_icon(member, icons, {member: category}, {category}).asset == expected
        )
        own_property = (
            '\nicon: "[[Attachments/member/Icon.png]]"' if explicit else "\nicon:"
        )
        text = (
            "---"
            + own_property
            + '\nappearance_category: "[[Categories/Type.md]]"\n---\n\n# Member\n\n![[Attachments/'
            + ("member" if explicit else "type")
            + "/Icon.png]]\n\nAuthored.\n"
        )
        check_image_icon_markup(
            text,
            thought,
            explicit,
            category,
            expected,
            names,
            bindings,
            ["Authored.\n"],
        )
        wrong = text.replace(
            "![[Attachments/" + ("member" if explicit else "type"),
            "![[Attachments/" + ("type" if explicit else "member"),
        )
        with pytest.raises(AssertionError, match="effective icon introduction"):
            check_image_icon_markup(
                wrong,
                thought,
                explicit,
                category,
                expected,
                names,
                bindings,
                ["Authored.\n"],
            )


def test_explicit_profile5_icon_wire_dispatch_preserves_old_eligibility(tmp_path):
    for index, raw in enumerate((ico()["raw"], bmp()["raw"])):
        baseline = packet_baseline(tmp_path / str(index), icon_source_packet(raw))
        row = baseline.json(baseline.data["attachment_metadata"][ICON]["path"])
        proofs = {}
        assert expected_asset(baseline, row, "5", proofs) == ("icon", "present", raw)
        assert proofs[ICON]["format"] == ("BMP" if raw[:2] == b"BM" else "ICO")
        for old in ("1", "2", "3", "4"):
            with pytest.raises(AssertionError):
                expected_asset(baseline, row, old)


def test_new_wire_formats_stay_owned_icon_only(tmp_path):
    packet = icon_source_packet()
    change_packet_declaration(packet, "type", 12)
    change_packet_declaration(packet, "location", ICON + ".png")
    baseline = packet_baseline(tmp_path / "image", packet)
    row = baseline.json(baseline.data["attachment_metadata"][ICON]["path"])
    with pytest.raises(AssertionError):
        expected_asset(baseline, row, "5")
    packet = icon_source_packet()
    change_packet_declaration(packet, "type", 1)
    change_packet_declaration(packet, "location", "ordinary.bmp")
    baseline = packet_baseline(tmp_path / "file", packet)
    row = baseline.json(baseline.data["attachment_metadata"][ICON]["path"])
    assert expected_asset(baseline, row, "5")[:2] == ("file", "present")


def test_profile5_inherits_pinned_png_and_jpeg_icon_formats(tmp_path):
    root = Path(__file__).parents[1] / "fixtures/local_api_scope_v3"
    provenance = json.loads((root / "input-provenance.json").read_bytes())["inputs"]
    for name in ("red-pixel.png", "inert-blue.jpg"):
        pin = next(row for row in provenance if row["file"] == name)
        raw = (root / name).read_bytes()
        assert (
            len(raw) == pin["length"]
            and hashlib.sha256(raw).hexdigest() == pin["sha256"]
        )
        baseline = packet_baseline(tmp_path / name, icon_source_packet(raw))
        row = baseline.json(baseline.data["attachment_metadata"][ICON]["path"])
        proofs = {}
        assert expected_asset(baseline, row, "5", proofs) == ("icon", "present", raw)
        assert proofs[ICON]["format"] == ("PNG" if name.endswith(".png") else "JPEG")
        assert expected_asset(baseline, row, "4") == ("icon", "present", raw)


def test_explicit_profile5_inherits_qualified_source_rules(tmp_path):
    baseline = raster_scope_baseline(
        tmp_path / "source", excluded=False, profile_version="3"
    )
    image = baseline.json(
        baseline.data["attachment_metadata"]["00000000-0000-4000-8000-000000000202"][
            "path"
        ]
    )
    assert expected_asset(baseline, image, profile_version="5")[:2] == (
        "image",
        "present",
    )


def test_unknown_profile_remains_refused(tmp_path):
    baseline = raster_scope_baseline(
        tmp_path / "source", excluded=False, profile_version="3"
    )
    with pytest.raises(AssertionError, match="unsupported API profile"):
        expected_asset(baseline, {}, profile_version="6")


def test_profile5_image_gap_preparation_keeps_current_table_interpretation(tmp_path):
    from tests.local_acceptance.unavailable_images import api_preparation, expectation

    baseline = raster_scope_baseline(
        tmp_path / "source", excluded=False, profile_version="3"
    )
    raw = "|A|B|\n|![Gone](.data/md-images/missing.png)|value|\n"
    expected = "| | |\n|---|---|\n|A|B|\n|Image unavailable: Gone|value|\n"
    text, _, events = api_preparation(
        baseline, "00000000-0000-4000-8000-000000000201", raw, "5"
    )
    assert text == expected and len(events) == 1
    assert (
        expectation(
            raw,
            "00000000-0000-4000-8000-000000000002",
            {},
            {},
            basis="api_undeclared_inventory",
            profile_version="5",
        )[0]
        == expected
    )


def test_profile5_image_gap_findings_require_actual_acquisition_census():
    from types import SimpleNamespace

    from tests.local_acceptance.unavailable_images import api_findings

    key, owner, brain = (f"00000000-0000-4000-8000-{n:012d}" for n in (202, 2, 1))
    row = {
        "id": key,
        "sourceId": owner,
        "brainId": brain,
        "type": 12,
        "sourceType": 2,
        "isNotes": False,
        "name": None,
        "location": key + ".png",
    }
    values = {
        "inventory": [row],
        "metadata": row,
        "brain": {"id": brain},
        "ledger": {
            "occurrences": [
                {
                    "phase": "source-acquisition",
                    "target": f"http://localhost/api/attachments/{brain}/{key}/metadata",
                    "status": 200,
                },
                {
                    "phase": "source-acquisition",
                    "target": f"http://localhost/api/attachments/{brain}/{key}/file-content",
                    "status": 404,
                },
            ]
        },
    }
    baseline = SimpleNamespace(
        data={
            "attachment_inventories": {owner: "inventory"},
            "attachment_metadata": {key: {"status": 200, "path": "metadata"}},
            "payloads": {key: {"status": 404}},
            "brain": "brain",
            "http_responses": "ledger",
        },
        json=values.__getitem__,
    )
    record = {
        "item_targets": [],
        "asset_targets": [],
        "run_metadata": {"source_acquisition": {"audit": {"requests": []}}},
    }
    with pytest.raises(AssertionError, match="acquisition absence census"):
        api_findings(record, baseline, SimpleNamespace(safe_notes={}), "5")
