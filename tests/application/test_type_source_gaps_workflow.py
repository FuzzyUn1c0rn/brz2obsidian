"""Reviewed category absences through real source ZIPs and public workflows."""

import json
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from brz2obsidian.contracts import MigrationRefused, RunMetadata
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import ObsidianRenderer
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from brz2obsidian.vault_check import check_vault
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_verified_coverage import (
    add_attachment,
    change_record,
    write_source,
)


def type_parts(tmp_path):
    source = graph_archive(
        tmp_path / "base.brz",
        {1: "Entry", 2: "Concept", 3: "Member"},
        [(2, 3, 1, 2, -1)],
        kinds={2: 2},
        notes={2: (b"unknown", 4), 3: (b"Member prose.\r\n", 4)},
    )
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    thoughts[2]["TypeId"] = identity(2)
    parts["thoughts.json"] = b"\n".join(json.dumps(t).encode() for t in thoughts)
    return parts


def remove_type_note(parts, declared=7):
    parts.pop(identity(2) + "/Notes.md")
    meta = json.loads(parts["meta.json"])
    meta["AttachmentFileStates"][identity(2002)] = 3
    parts["meta.json"] = json.dumps(meta).encode()
    change_record(parts, identity(2002), DataLength=declared)


def test_absent_category_note_is_unknown_and_needs_no_image_basis(tmp_path):
    parts = type_parts(tmp_path)
    remove_type_note(parts, declared=0)
    source = write_source(tmp_path, parts)
    original = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings", inspected.issues
    assert inspected.counts.source_gaps == 1
    assert inspected.counts.planned_generated_embeds == 0
    assert [d.owner for d in inspected.inspection.documents] == [identity(3)]
    gap = inspected.inspection.source_gaps[0]
    assert gap.gap.role == "definition_note" and gap.outcome == "unknown_note"
    assert gap.owner_created and gap.owner_target == "Categories/Concept.md"
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings", result.issues
    vault = tmp_path / "vault"
    category = (vault / "Categories/Concept.md").read_text(encoding="utf-8")
    assert (
        "> [!warning] Source category note unavailable\n> Source category note text is absent"
        in category
    )
    assert category.index("[!warning]") < category.index("Members.base#Members")
    assert "Source category note text is absent" in category
    assert "unknown" in category.lower()
    assert "[[MIGRATION REPORT.md|Migration report]]" in category
    assert "Templates/Bases/Members.base#Members" in category
    assert not (
        vault / "Attachments" / identity(2).replace("-", "") / "Notes.md.original"
    ).exists()
    report = (vault / "MIGRATION REPORT.md").read_text(encoding="utf-8")
    assert "[[Categories/Concept.md|Concept]]" in report
    assert '"state": 3' in report and '"declared\\_length": 0' in report
    assert check_vault(vault).outcome == "clean"
    assert source.read_bytes() == original


@pytest.mark.parametrize("role", ["note", "icon"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("SourceType", 1),
        ("SourceType", True),
        ("SourceType", "2"),
        ("Type", 12),
        ("Type", True),
        ("NoteType", 5),
        ("NoteType", False),
        ("IsIcon", "false"),
        ("IsBrainAttachment", True),
        ("IsBrainIcon", True),
        ("IsWallpaper", True),
        ("IsAiScriptsFile", True),
        ("IsKeyboardShortcutsFile", True),
        ("IsToolbarConfigFile", True),
        ("Location", "../Notes.md"),
        ("Location", "/Notes.md"),
        ("Location", "folder\\Notes.md"),
        ("Location", "folder//Notes.md"),
        ("DataLength", -1),
        ("DataLength", True),
        ("DataLength", "0"),
        ("Id", "invalid"),
        ("Id", identity(2003)),
        ("SourceId", identity(999)),
        ("BrainId", identity(999)),
    ],
)
def test_type_absence_near_miss_refuses_without_publication(
    tmp_path, role, field, value
):
    parts = type_parts(tmp_path)
    if role == "note":
        remove_type_note(parts)
        key = identity(2002)
    else:
        key = identity(3001)
        add_attachment(
            parts, key, 5, "type.png", declared=7, state=3, owner=identity(2)
        )
    change_record(parts, key, **{field: value})
    source = write_source(tmp_path, parts)
    before = source.read_bytes()
    marker = tmp_path / "caller.bin"
    marker.write_bytes(b"caller\r\n")
    assert default_workflow().inspect(source).outcome == "refused"
    assert default_workflow().convert(source, tmp_path / "vault").outcome == "refused"
    assert not (tmp_path / "vault").exists()
    assert marker.read_bytes() == b"caller\r\n" and source.read_bytes() == before


@pytest.mark.parametrize("role", ["note", "icon"])
@pytest.mark.parametrize(
    "state,payload",
    [
        (None, None),
        (9, None),
        (True, None),
        (1, None),
        (2, None),
        (3, b""),
        (3, b"present"),
    ],
)
def test_type_absence_state_and_physical_presence_must_agree(
    tmp_path, role, state, payload
):
    parts = type_parts(tmp_path)
    if role == "note":
        remove_type_note(parts)
        key, member = identity(2002), identity(2) + "/Notes.md"
    else:
        key, member = identity(3001), identity(2) + "/.data/type.png"
        add_attachment(
            parts, key, 5, "type.png", declared=7, state=3, owner=identity(2)
        )
    meta = json.loads(parts["meta.json"])
    meta["AttachmentFileStates"].pop(key)
    if state is not None:
        meta["AttachmentFileStates"][key] = state
    parts["meta.json"] = json.dumps(meta).encode()
    if payload is not None:
        parts[member] = payload
    source = write_source(tmp_path, parts)
    assert default_workflow().inspect(source).outcome == "refused"
    assert default_workflow().convert(source, tmp_path / "vault").outcome == "refused"
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize("role", ["note", "icon"])
@pytest.mark.parametrize("kind", [1, 4, 5])
def test_type_gap_does_not_generalize_to_other_owner_roles(tmp_path, role, kind):
    parts = type_parts(tmp_path)
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    thoughts[1]["Kind"] = kind
    thoughts[2].pop("TypeId")
    parts["thoughts.json"] = b"\n".join(json.dumps(t).encode() for t in thoughts)
    parts["links.json"] = b""
    if role == "note":
        remove_type_note(parts)
    else:
        add_attachment(
            parts, identity(3001), 5, "type.png", declared=7, state=3, owner=identity(2)
        )
    source = write_source(tmp_path, parts)
    assert default_workflow().inspect(source).outcome == "refused"
    assert default_workflow().convert(source, tmp_path / "vault").outcome == "refused"
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize("role", ["note", "icon"])
@pytest.mark.parametrize("present", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_type_absence_has_no_competing_declaration(tmp_path, role, present, reverse):
    parts = type_parts(tmp_path)
    if role == "note":
        remove_type_note(parts)
        add_attachment(
            parts,
            identity(3002),
            1,
            "Competing.md",
            b"\xef\xbb\xbf" if present else None,
            declared=3,
            state=1 if present else 3,
            owner=identity(2),
        )
        change_record(parts, identity(3002), NoteType=4)
    else:
        add_attachment(
            parts, identity(3001), 5, "type.png", declared=7, state=3, owner=identity(2)
        )
        add_attachment(
            parts,
            identity(3002),
            5,
            "Competing.png",
            b"other icon" if present else None,
            declared=10,
            state=1 if present else 3,
            owner=identity(2),
        )
    if reverse:
        parts["attachments.json"] = b"\n".join(
            reversed(parts["attachments.json"].splitlines())
        )
    source = write_source(tmp_path, parts)
    assert default_workflow().inspect(source).outcome == "refused"
    assert default_workflow().convert(source, tmp_path / "vault").outcome == "refused"
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("NoteType", 0),
        ("Location", "Other.md"),
        ("Location", "folder/Notes.md"),
        ("IsIcon", True),
    ],
)
def test_absent_type_note_requires_exact_marked_canonical_declaration(
    tmp_path, field, value
):
    parts = type_parts(tmp_path)
    remove_type_note(parts)
    change_record(parts, identity(2002), **{field: value})
    source = write_source(tmp_path, parts)
    assert default_workflow().inspect(source).outcome == "refused"
    assert default_workflow().convert(source, tmp_path / "vault").outcome == "refused"
    assert not (tmp_path / "vault").exists()


def test_absent_type_icon_requires_agreeing_icon_flag(tmp_path):
    parts = type_parts(tmp_path)
    add_attachment(
        parts, identity(3001), 5, "type.png", declared=7, state=3, owner=identity(2)
    )
    change_record(parts, identity(3001), IsIcon=False)
    source = write_source(tmp_path, parts)
    assert default_workflow().inspect(source).outcome == "refused"
    assert default_workflow().convert(source, tmp_path / "vault").outcome == "refused"
    assert not (tmp_path / "vault").exists()


def test_public_analysis_requires_missing_icon_to_be_the_declared_provider_icon(
    tmp_path,
):
    parts = type_parts(tmp_path)
    add_attachment(
        parts, identity(3001), 5, "type.png", declared=7, state=3, owner=identity(2)
    )
    source = write_source(tmp_path, parts)
    with BrzSourceModule().open(source) as session:
        snapshot = session.snapshot
    snapshot = snapshot.model_copy(
        update={
            "items": tuple(
                i.model_copy(update={"declared_appearance": None})
                if i.key == identity(2)
                else i
                for i in snapshot.items
            )
        }
    )
    with pytest.raises(MigrationRefused):
        analyze(snapshot, BRZ_POLICY)


def test_absent_category_icon_is_neutral_for_provider_and_inheriting_member(tmp_path):
    parts = type_parts(tmp_path)
    add_attachment(
        parts, identity(3001), 5, "type.png", declared=99, state=3, owner=identity(2)
    )
    source = write_source(tmp_path, parts)
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings", inspected.issues
    gap = inspected.inspection.source_gaps[0]
    assert gap.gap.role == "definition_icon" and gap.outcome == "neutral_icon"
    assert gap.provider_key == identity(2)
    assert gap.affected_member_keys == (identity(3),)
    icons = {s.item_key: s for s in inspected.inspection.icon_snapshots}
    assert icons[identity(2)].effective_icon_asset_id is None
    assert icons[identity(3)].effective_icon_asset_id is None
    assert icons[identity(3)].appearance_category_key == identity(2)
    assert default_workflow().convert(source, tmp_path / "vault").outcome == "warnings"
    vault = tmp_path / "vault"
    category = (vault / "Categories/Concept.md").read_text(encoding="utf-8")
    member = (vault / "Notes/Member.md").read_text(encoding="utf-8")
    assert (
        "> [!warning] Source category icon unavailable\n> Source category icon is absent"
        in category
    )
    assert category.index("[!warning]") < category.index("Members.base#Members")
    assert (
        "> [!warning] Inherited icon unavailable\n> The inherited icon is unavailable from [[Categories/Concept.md|Concept]]"
        in member
    )
    assert member.index("[!warning]") < member.index("Member prose.")
    assert "icon:\n" in category and "icon:\n" in member
    assert 'appearance_category: "[[Categories/Concept.md]]"' in member
    assert "Source category icon is absent" in category
    assert "[[Categories/Concept.md|Concept]]" in member
    assert "inherited icon is unavailable" in member
    assert "Member prose.\n" in member
    assert "type.png]]" not in category + member
    report = (vault / "MIGRATION REPORT.md").read_text(encoding="utf-8")
    assert "Provider: [[Categories/Concept.md|Concept]]" in report
    assert "Affected included members (1):" in report
    assert "[[Notes/Member.md|Member]]" in report
    assert check_vault(vault).outcome == "clean"


@pytest.mark.parametrize("declared", [0, 777])
def test_combined_type_gaps_keep_cards_overrides_and_other_icons(
    tmp_path, capsys, declared
):
    parts = type_parts(tmp_path)
    remove_type_note(parts, declared=declared)
    add_attachment(
        parts,
        identity(3001),
        5,
        "missing.png",
        declared=declared,
        state=3,
        owner=identity(2),
    )
    add_attachment(
        parts, identity(3002), 5, "override.png", b"explicit icon", owner=identity(3)
    )
    add_attachment(
        parts, identity(3003), 5, "entry.png", b"unaffected icon", owner=identity(1)
    )
    add_attachment(
        parts, identity(3004), 12, "card.png", b"authored card", owner=identity(3)
    )
    body = b"Member prose.\r\n![card](.data/md-images/card.png)\r\n"
    parts[identity(3) + "/Notes.md"] = body
    change_record(parts, identity(2003), DataLength=len(body))
    source = write_source(tmp_path, parts)
    assert main(["inspect", str(source), "--json"]) == 2
    inspected = json.loads(capsys.readouterr().out)
    gaps = inspected["inspection"]["source_gaps"]
    assert len(gaps) == 2
    icon_gap = next(g for g in gaps if g["outcome"] == "neutral_icon")
    assert icon_gap["affected_member_keys"] == []
    assert inspected["counts"]["planned_generated_embeds"] == 0
    assert main(["convert", str(source), str(tmp_path / "vault"), "--json"]) == 2
    converted = json.loads(capsys.readouterr().out)
    assert converted["counts"]["source_gaps"] == 2
    vault = tmp_path / "vault"
    member = (vault / "Notes/Member.md").read_bytes()
    folder = "Attachments/00000000000000000000000000000003/"
    assert ('icon: "[[' + folder + 'override.png]]"').encode() in member
    assert ("![[" + folder + "override.png]]").encode() in member
    assert ("![card](../" + folder + "card.png)\r\n").encode() in member
    assert b"inherited icon is unavailable" not in member
    assert (vault / folder / "Notes.md.original").read_bytes() == body
    assert (vault / folder / "override.png").read_bytes() == b"explicit icon"
    category = (vault / "Categories/Concept.md").read_text(encoding="utf-8")
    assert "Source category note text is absent" in category
    assert "Source category icon is absent" in category
    assert "## Resources" not in category
    assert "card.png" not in category
    record = json.loads((vault / "migration-record.json").read_bytes())
    missing = [
        a
        for a in record["asset_targets"]
        if a["asset_id"] in {identity(2002), identity(3001)}
    ]
    assert len(missing) == 2
    assert all(
        a["actual_sha256"] is None
        and a["actual_length"] is None
        and a["relative_path"] is None
        for a in missing
    )
    assert record["generated_presentations"] == []
    before = inventory(vault)
    assert check_vault(vault).outcome == "clean"
    assert inventory(vault) == before
    (vault / folder / "card.png").unlink()
    before = inventory(vault)
    assert any(i.code == "missing_image" for i in check_vault(vault).issues)
    assert inventory(vault) == before


def inventory(root):
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize("reverse", [False, True])
def test_scoped_provider_diagnostics_separate_overrides_other_types_and_exclusions(
    tmp_path, reverse
):
    source = graph_archive(
        tmp_path / "mixed.brz",
        {
            1: "Entry",
            2: "Concept",
            3: "Member",
            4: "Override",
            5: "Available",
            6: "Other member",
            7: "Private member",
            8: "Private provider",
            9: "Included former member",
            10: "Member",
        },
        [
            (2, 3, 1, 2, -1),
            (2, 4, 1, 2, -1),
            (5, 6, 1, 2, -1),
            (2, 7, 1, 2, -1),
            (8, 9, 1, 2, -1),
        ],
        kinds={2: 2, 5: 2, 8: 2},
        notes={
            3: (b"Included card body.", 4),
            9: (b"Included former member body.", 4),
            10: (b"Independent same title body.", 4),
        },
    )
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    for member, provider in [(3, 2), (4, 2), (6, 5), (7, 2), (9, 8)]:
        thoughts[member - 1]["TypeId"] = identity(provider)
    for number in [7, 8]:
        thoughts[number - 1]["ForgottenDateTime"] = "2026-10-05T00:00:00"
    parts["thoughts.json"] = b"\n".join(json.dumps(t).encode() for t in thoughts)
    add_attachment(
        parts, identity(3001), 5, "missing.png", declared=7, state=3, owner=identity(2)
    )
    add_attachment(
        parts, identity(3002), 5, "override.png", b"override pixels", owner=identity(4)
    )
    add_attachment(
        parts,
        identity(3003),
        5,
        "available.png",
        b"available pixels",
        declared=1,
        owner=identity(5),
    )
    add_attachment(
        parts, identity(3008), 5, "private.png", declared=19, state=3, owner=identity(8)
    )
    if reverse:
        for name in ["thoughts.json", "links.json", "attachments.json"]:
            parts[name] = b"\n".join(reversed(parts[name].splitlines()))
        parts = dict(reversed(list(parts.items())))
    source = write_source(tmp_path, parts)
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings", inspected.issues
    assert inspected.counts.source_gaps == 1
    gap = inspected.inspection.source_gaps[0]
    assert gap.provider_key == identity(2) and gap.affected_member_keys == (
        identity(3),
    )
    icons = {s.item_key: s for s in inspected.inspection.icon_snapshots}
    assert icons[identity(4)].effective_icon_asset_id == identity(3002)
    assert icons[identity(6)].effective_icon_asset_id == identity(3003)
    assert icons[identity(9)].appearance_category_key is None
    assert icons[identity(10)].appearance_category_key is None
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "warnings", result.issues
    assert len(result.issues) == 2
    assert {i.rule_id for i in result.issues} == {
        "thebrain-format5/absent-type-icon/v1",
        "thebrain-format5/icon-length/v1",
    }
    record = json.loads((vault / "migration-record.json").read_bytes())
    available = next(
        a for a in record["asset_targets"] if a["asset_id"] == identity(3003)
    )
    assert available["actual_length"] == 16
    assert (vault / available["relative_path"]).read_bytes() == b"available pixels"
    assert (vault / "Notes/Other member.md").read_text(encoding="utf-8").count(
        "available.png]]"
    ) == 1
    included = (vault / "Notes/Included former member.md").read_text(encoding="utf-8")
    assert "appearance_category:\n" in included and "categories: []" in included
    all_bytes = (
        b"\n".join(inventory(vault).values())
        + result.model_dump_json().encode()
        + inspected.model_dump_json().encode()
    )
    for private in [
        identity(7),
        identity(8),
        identity(3008),
        "Private member",
        "Private provider",
        "private.png",
    ]:
        assert private.encode() not in all_bytes
    report = (vault / "MIGRATION REPORT.md").read_text(encoding="utf-8")
    assert "Affected included members (1):" in report
    assert "[[Notes/Member — 00000000000000000000000000000003.md|Member]]" in report
    assert "inherited icon is unavailable" not in (
        vault / "Notes/Override.md"
    ).read_text(encoding="utf-8")
    assert check_vault(vault).outcome == "clean"


@pytest.mark.parametrize(
    "body", [b"", b" \r\n\t", b"\xef\xbb\xbf", b"Category prose.\r\n"]
)
def test_present_category_text_keeps_original_even_with_missing_icon(tmp_path, body):
    parts = type_parts(tmp_path)
    parts[identity(2) + "/Notes.md"] = body
    change_record(parts, identity(2002), DataLength=len(body))
    add_attachment(
        parts, identity(3001), 5, "missing.png", declared=7, state=3, owner=identity(2)
    )
    source = write_source(tmp_path, parts)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings", result.issues
    category = (tmp_path / "vault/Categories/Concept.md").read_bytes()
    assert b"Source category note text is absent" not in category
    assert body.decode("utf-8-sig").encode() in category
    assert (
        tmp_path
        / "vault/Attachments/00000000000000000000000000000002/Notes.md.original"
    ).read_bytes() == body
    assert result.counts.source_gaps == 1 and result.counts.actual_generated_embeds == 0


def test_absent_category_text_does_not_reconstruct_from_its_owned_card(tmp_path):
    parts = type_parts(tmp_path)
    remove_type_note(parts)
    add_attachment(
        parts, identity(3001), 12, "card.png", b"type card", owner=identity(2)
    )
    source = write_source(tmp_path, parts)
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings", inspected.issues
    assert inspected.counts.planned_generated_embeds == 0
    assert inspected.inspection.generated_presentations == ()
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings", result.issues
    category = (tmp_path / "vault/Categories/Concept.md").read_text(encoding="utf-8")
    assert "Source category note text is absent" in category
    assert "![[Attachments/00000000000000000000000000000002/card.png]]" not in category
    assert "icon:\n" in category
    assert (
        tmp_path / "vault/Attachments/00000000000000000000000000000002/card.png"
    ).read_bytes() == b"type card"


@pytest.mark.parametrize("reverse", [False, True])
def test_type_gap_diagnostics_follow_canonical_asset_identity_order(tmp_path, reverse):
    parts = type_parts(tmp_path)
    remove_type_note(parts)
    add_attachment(
        parts, identity(3001), 5, "missing.png", declared=7, state=3, owner=identity(2)
    )
    if reverse:
        parts["attachments.json"] = b"\n".join(
            reversed(parts["attachments.json"].splitlines())
        )
        parts = dict(reversed(list(parts.items())))
    source = write_source(tmp_path, parts)
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings", inspected.issues
    assert [g.gap.asset_id for g in inspected.inspection.source_gaps] == [
        identity(2002),
        identity(3001),
    ]
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert [g["gap"]["asset_id"] for g in record["source_gaps"]] == [
        identity(2002),
        identity(3001),
    ]


@pytest.mark.parametrize("mutation", ["absent_icon_target", "affected_member_target"])
def test_renderer_refuses_forged_type_gap_destination_obligations(tmp_path, mutation):
    parts = type_parts(tmp_path)
    add_attachment(
        parts, identity(3001), 5, "missing.png", declared=7, state=3, owner=identity(2)
    )
    source = write_source(tmp_path, parts)
    with BrzSourceModule().open(source) as session:
        planned = plan(analyze(session.snapshot, BRZ_POLICY))
    if mutation == "absent_icon_target":
        forged = planned.model_copy(
            update={
                "asset_targets": tuple(
                    a.model_copy(update={"relative_path": "Attachments/invented.png"})
                    if a.asset_id == identity(3001)
                    else a
                    for a in planned.asset_targets
                )
            }
        )
    else:
        forged = planned.model_copy(
            update={
                "item_targets": tuple(
                    t.model_copy(update={"relative_path": "Notes/forged.md"})
                    if t.item_key == identity(3)
                    else t
                    for t in planned.item_targets
                )
            }
        )
    metadata = RunMetadata(
        converter_version="0.3.0",
        renderer_version="6",
        run_id="test",
        run_time="2026-10-06T00:00:00Z",
        obsidian_version="1.12.4",
        bookmark_time=1,
    )
    with pytest.raises(MigrationRefused):
        ObsidianRenderer().render(forged, metadata)
