"""Independent destination answers through public import and checking seams."""

import json

import pytest
import yaml

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.vault_check import check_vault
from tests.application.test_graph_workflow import identity
from tests.support.type_tag_sources import DEEP_ICON, EDGES, ICON, IDS, brz_source


def test_full_finite_icon_snapshots_keep_owned_icons_and_direct_membership(tmp_path):
    source = brz_source(tmp_path / "source.brz", deep=True)
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "warnings", inspected.issues
    icons = {s.item_key: s for s in inspected.inspection.icon_snapshots}
    assert {icons[IDS[name]].effective_icon_asset_id for name in "ABCDEFG"} == {ICON}
    assert icons[IDS["D"]].appearance_category_key == IDS["C"]
    assert icons[IDS["D"]].explicit_icon_asset_id is None
    assert icons[identity(40)].effective_icon_asset_id == DEEP_ICON
    assert icons[identity(41)].effective_icon_asset_id == DEEP_ICON
    destination = tmp_path / "vault"
    converted = workflow.convert(source, destination)
    assert converted.outcome == "warnings", converted.issues
    record = json.loads((destination / "migration-record.json").read_bytes())
    targets = {t["item_key"]: t for t in record["item_targets"]}
    adaptation = next(
        a
        for a in record["adaptations"]
        if a["kind"] == "body_icon_snapshot" and a["affected"] == IDS["D"]
    )
    assert (
        "through the selected appearance-category chain starting at " + IDS["C"]
        in adaptation["description"]
    )
    assert sum(t["created"] for t in targets.values()) == 21
    for name, provider in (("B", "A"), ("C", "B"), ("D", "C"), ("F", "E")):
        text = (destination / targets[IDS[name]]["relative_path"]).read_text(
            encoding="utf-8"
        )
        properties = yaml.safe_load(text.split("---", 2)[1])
        assert properties["categories"] == [f"[[Categories/{provider}.md]]"]
        assert properties["appearance_category"] == f"[[Categories/{provider}.md]]"
        assert properties["icon"] is None
    assert len(list((destination / "Categories").glob("*.md"))) == 14
    starter = yaml.safe_load(
        (destination / "Templates/Category starter.md")
        .read_text(encoding="utf-8")
        .split("---", 2)[1]
    )
    assert starter["tags"] == ["categories"] and starter["categories"] == []
    assert starter["appearance_category"] is None
    member = yaml.safe_load(
        (destination / "Templates/B.md").read_text(encoding="utf-8").split("---", 2)[1]
    )
    assert member["categories"] == ["[[Categories/B.md]]"]
    assert member["appearance_category"] == "[[Categories/B.md]]"
    assert member["icon"] is None and member["tags"] == []
    assert not any(key.startswith("source_") for key in member)
    instruction = "Close and reopen the affected category dashboards and [[Categories.md|Categories overview]]"
    for relative in (
        "Categories/B.md",
        "Categories.md",
        "Templates/Category starter.md",
        "Vault guide.md",
    ):
        text = (destination / relative).read_text(encoding="utf-8")
        assert instruction in text
        assert "stale or inconsistent icons and statuses" in text
        if relative == "Categories/B.md":
            assert (
                text.index("## Parents")
                < text.index(instruction)
                < text.index("## Members")
            )
        elif relative == "Categories.md":
            assert text.index(instruction) < text.index(
                "![[Templates/Bases/Categories.base]]"
            )
    n9 = (destination / "Notes/N9.md").read_text(encoding="utf-8")
    owned_path = next(
        a["relative_path"]
        for a in record["asset_targets"]
        if a["asset_id"] == DEEP_ICON
    )
    assert f"![[{owned_path}]]" in n9
    assert "![[Attachments/" not in (destination / "Categories/B.md").read_text(
        encoding="utf-8"
    )


def test_native_bases_share_eight_link_lookup_and_report_depth_without_refusal(
    tmp_path,
):
    source = brz_source(tmp_path / "source.brz", deep=True)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings", result.issues
    assert {(i.code, i.affected[0]) for i in result.issues} == {
        ("icon_lookup_depth", identity(39)),
        ("icon_lookup_depth", identity(41)),
    }
    assert all(i.severity == "warning" for i in result.issues)
    vault = tmp_path / "vault"
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert record["schema_version"] == 9 and record["renderer_version"] == "9"
    assert record["source_identity"]["format_version"] == "5"
    bases = [
        yaml.safe_load((vault / f"Templates/Bases/{name}.base").read_bytes())
        for name in ("Members", "Gallery", "Categories")
    ]
    assert bases[0]["formulas"] == bases[1]["formulas"] == bases[2]["formulas"]
    assert all(
        base["views"][0]["columnSize"]["formula.provider_status"] == 240
        for base in (bases[0], bases[2])
    )
    formulas = bases[0]["formulas"]
    assert all(
        expression.count("(") == expression.count(")")
        for expression in formulas.values()
    )
    assert "Icon lookup exceeds 8 links." in formulas["provider_status"]
    assert "formula.r8" in formulas["effective_icon"]
    assert "r9" not in formulas and "p9" not in formulas
    for index in range(9):
        assert 'isType("link")' in formulas[f"r{index}"]
        assert '"webp"' in formulas[f"r{index}"] and "size > 0" in formulas[f"r{index}"]
    assert all("formula.provider_status" in base["views"][0]["order"] for base in bases)
    assert "list(categories).contains(this)" in bases[0]["filters"]["and"]
    report = (vault / "MIGRATION REPORT.md").read_text(encoding="utf-8")
    assert "Icon lookup exceeds 8 links." in report
    assert "Notes/N9.md" in report and "Categories/H0.md" in report
    assert {(i.code, i.artifact) for i in check_vault(vault).issues} == {
        ("icon_lookup_depth", "Categories/H9.md"),
        ("icon_lookup_depth", "Notes/N9.md"),
    }


@pytest.mark.parametrize("fallback", [False, True])
def test_missing_category_icon_reports_transitive_members_and_farther_fallback(
    tmp_path,
    fallback,
):
    from zipfile import ZipFile

    from tests.application.test_verified_coverage import add_attachment, write_source

    source = brz_source(tmp_path / "base.brz")
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    absent = identity(503)
    add_attachment(parts, absent, 5, "Missing.png", declared=7, state=3, owner=IDS["B"])
    if not fallback:
        parts["attachments.json"] = b"\n".join(
            line
            for line in parts["attachments.json"].splitlines()
            if json.loads(line)["Id"] != ICON
        )
        meta = json.loads(parts["meta.json"])
        del meta["AttachmentFileStates"][ICON]
        parts["meta.json"] = json.dumps(meta).encode()
        del parts[IDS["A"] + "/.data/Icon.png"]
    source = write_source(tmp_path, parts)
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings", inspected.issues
    (gap,) = inspected.inspection.source_gaps
    assert gap.gap.asset_id == absent
    assert gap.provider_key == IDS["B"]
    assert gap.affected_member_keys == (IDS["C"], IDS["D"])
    assert gap.outcome == ("image_fallback" if fallback else "neutral_icon")
    assert gap.image_asset_ids == ((ICON,) if fallback else ())
    icons = {s.item_key: s for s in inspected.inspection.icon_snapshots}
    assert icons[IDS["B"]].explicit_icon_asset_id is None
    assert {icons[IDS[n]].effective_icon_asset_id for n in "BCD"} == (
        {ICON} if fallback else {None}
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "warnings", result.issues
    for relative in ("Categories/B.md", "Categories/C.md", "Notes/D.md"):
        text = (vault / relative).read_text(encoding="utf-8")
        assert ("farther selected appearance-category icon" in text) is fallback
        assert ("appearance is neutral" in text) is (not fallback)
        assert yaml.safe_load(text.split("---", 2)[1])["icon"] is None
    report = (vault / "MIGRATION REPORT.md").read_text(encoding="utf-8")
    assert "Affected included members (2)" in report
    assert "Categories/C.md" in report and "Notes/D.md" in report
    assert f"outcome {gap.outcome}" in report
    record = json.loads((vault / "migration-record.json").read_bytes())
    warning = next(
        i
        for i in record["issues"]
        if i["code"] == "approved_source_gap" and i["affected"] == [absent]
    )
    if fallback:
        assert (
            "farther selected appearance-category icon is available"
            in warning["message"]
        )
        assert "have neutral appearance" not in warning["message"]
    else:
        assert (
            "no farther selected appearance-category icon is available"
            in warning["message"]
        )
        assert "neutral" in warning["message"]
    assert check_vault(vault).issues == ()


@pytest.mark.parametrize("created", [False, True])
def test_nested_tag_facts_stay_readable_with_independent_tokens(tmp_path, created):
    from zipfile import ZipFile

    from tests.application.test_verified_coverage import (
        add_attachment,
        change_record,
        write_source,
    )

    source = brz_source(
        tmp_path / "base.brz",
        edges=tuple(edge for edge in EDGES if edge != (11, 17, 3, 1, -1)),
    )
    if created:
        with ZipFile(source) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        note = identity(504)
        add_attachment(
            parts, note, 1, "Notes.md", b"Tag T source prose.", owner=IDS["T"]
        )
        change_record(parts, note, NoteType=4)
        source = write_source(tmp_path, parts)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.issues
    record = json.loads((vault / "migration-record.json").read_bytes())
    targets = {t["item_key"]: t for t in record["item_targets"]}
    assert targets[IDS["T"]]["created"] is created
    assert targets[IDS["U"]]["created"] is False
    assert {
        t["vault_tag_token"] for t in record["item_targets"] if t["vault_tag_token"]
    } == {"T", "U"}
    properties = yaml.safe_load(
        (vault / "Categories/B.md").read_text(encoding="utf-8").split("---", 2)[1]
    )
    assert properties["tags"] == ["categories", "T"]
    listing = (vault / "Tag memberships.md").read_text(encoding="utf-8")
    assert "## #U" in listing and "Nested source tag: [[Notes/T.md|T]] (#T)" in listing
    assert ("; uncreated target" in listing) is (not created)
    (nested,) = [m for m in record["tag_memberships"] if m["tag_key"] == IDS["U"]]
    assert (
        nested["item_key"] == IDS["T"]
        and nested["listing_path"] == "Tag memberships.md"
    )
    if created:
        t_properties = yaml.safe_load(
            (vault / "Notes/T.md").read_text(encoding="utf-8").split("---", 2)[1]
        )
        assert t_properties["tags"] == ["U"]
    assert "U/T" not in listing


def test_nearest_owned_icon_wins_without_changing_immediate_classification(tmp_path):
    from zipfile import ZipFile

    from tests.application.test_verified_coverage import add_attachment, write_source
    from tests.support.local_api_payloads import PNG

    source = brz_source(tmp_path / "base.brz")
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    bear, own = identity(505), identity(506)
    add_attachment(parts, bear, 5, "Bear.png", PNG, owner=IDS["B"])
    add_attachment(parts, own, 5, "Own.png", PNG, owner=IDS["D"])
    result = default_workflow().inspect(write_source(tmp_path, parts))
    assert result.outcome == "clean", result.issues
    icons = {s.item_key: s for s in result.inspection.icon_snapshots}
    assert {n: icons[IDS[n]].effective_icon_asset_id for n in "ABCDEFG"} == {
        "A": ICON,
        "B": bear,
        "C": bear,
        "D": own,
        "E": ICON,
        "F": ICON,
        "G": ICON,
    }
    assert icons[IDS["C"]].explicit_icon_asset_id is None
    assert icons[IDS["D"]].appearance_category_key == IDS["C"]
    assert result.counts.classification_assignments == 6
