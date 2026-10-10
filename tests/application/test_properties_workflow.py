"""Canonical object metadata observed through real archives and vault files."""

import hashlib
import json
import struct
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import render
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from brz2obsidian.vault_check import check_vault
from tests.application.test_graph_workflow import BRAIN, graph_archive, identity
from tests.application.test_module_seams import METADATA
from tests.application.test_verified_coverage import add_attachment, write_source


def parts(source):
    with ZipFile(source) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def set_thoughts(files, changes):
    thoughts = [json.loads(line) for line in files["thoughts.json"].splitlines()]
    for thought in thoughts:
        thought.update(changes.get(thought["Id"], {}))
    files["thoughts.json"] = "\n".join(json.dumps(t) for t in thoughts).encode()


def property_block(note):
    assert note.startswith(b"---\n")
    return note.split(b"---\n", 2)[1].decode()


def test_imported_ordinary_definition_and_authored_tag_share_canonical_properties(
    tmp_path,
):
    tag_body = b"# Authored tag\r\n> Keep this.\r\n`created: yesterday`\r"
    source = graph_archive(
        tmp_path / "objects.brz",
        {1: "Entry", 2: "Concept", 3: "Member", 4: "true"},
        [(2, 3, 1, 2, -1), (4, 3, 1, 5, -1)],
        kinds={2: 2, 4: 4},
        notes={4: (tag_body, 4)},
    )
    files = parts(source)
    set_thoughts(
        files,
        {
            identity(3): {"TypeId": identity(2)},
            identity(4): {
                "CreationDateTime": "2024-02-29T23:59:58.1234567-11:00",
                "ModificationDateTime": "2025-01-01T00:00:00+14:00",
                "NotesModificationDateTime": "2026-10-04T11:12:13",
            },
        },
    )
    source = write_source(tmp_path, files)
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "clean", result.issues
    tag = (vault / "Notes/true.md").read_bytes()
    assert property_block(tag) == (
        "categories: []\nappearance_category:\nicon:\n"
        "created: 2024-02-29\nupdated: 2025-01-01\n"
        "tags: []\naliases: []\n"
        f'source_collection_id: "{BRAIN}"\nsource_item_id: "{identity(4)}"\n'
    )
    assert tag.endswith(b"# true\n\n" + tag_body)
    ordinary = property_block((vault / "Notes/Member.md").read_bytes())
    assert 'categories:\n  - "[[Categories/Concept.md]]"\n' in ordinary
    assert 'appearance_category: "[[Categories/Concept.md]]"\n' in ordinary
    assert 'tags:\n  - "true"\n' in ordinary
    assert "aliases: []\n" in ordinary
    category = property_block((vault / "Categories/Concept.md").read_bytes())
    assert 'tags:\n  - "categories"\n' in category
    assert f'source_item_id: "{identity(2)}"\n' in category
    record = json.loads((vault / "migration-record.json").read_bytes())
    original = next(
        e["records"] for e in record["original_evidence"] if e["key"] == "thoughts.json"
    )
    assert original[3]["CreationDateTime"] == "2024-02-29T23:59:58.1234567-11:00"
    assert record["run_metadata"]["run_time"] != original[3]["CreationDateTime"]
    assert (
        vault
        / next(
            a["relative_path"]
            for a in record["asset_targets"]
            if a["owner"] == identity(4)
        )
    ).read_bytes() == tag_body


@pytest.mark.parametrize("field", ["CreationDateTime", "ModificationDateTime"])
@pytest.mark.parametrize(
    "value", ["2025-02-29T01:02:03", "2026-10-04T25:00:00", "yesterday", 42, False]
)
def test_populated_invalid_dates_refuse_inspection_and_conversion(
    tmp_path, field, value
):
    files = parts(graph_archive(tmp_path / "dates.brz", {1: "Entry"}))
    set_thoughts(files, {identity(1): {field: value}})
    source = write_source(tmp_path, files)
    workflow = default_workflow()
    for result in (
        workflow.inspect(source),
        workflow.convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused", result.issues
        assert result.issues[0].code == "invalid_source"
        assert field in result.issues[0].message
    assert not (tmp_path / "vault").exists()


def test_icons_and_archived_colours_survive_without_exposing_colour_properties(
    tmp_path,
):
    source = graph_archive(
        tmp_path / "icons.brz",
        {1: "Entry", 2: "Concept", 3: "Inherited", 4: "Override", 5: "Icon only"},
        [(2, 3, 1, 2, -1), (2, 4, 1, 2, -1)],
        kinds={2: 2},
        labels={2: "Type label", 4: "Own label"},
        notes={
            3: (
                b"# Authored heading\r\n> Unicode: \xc3\xa9\r\n````md\r\nicon: original\r\n````\r",
                4,
            )
        },
    )
    files = parts(source)
    set_thoughts(
        files,
        {
            identity(2): {"ForegroundColor": -10456833, "BackgroundColor": -8112},
            identity(3): {
                "TypeId": identity(2),
                "ThoughtIconInfo": "4:file.pdf:1:False:False:0:",
            },
            identity(4): {"TypeId": identity(2), "ForegroundColor": -65536},
        },
    )
    add_attachment(
        files, identity(3002), 5, "type.png", b"type image", owner=identity(2)
    )
    add_attachment(
        files, identity(3004), 5, "override.png", b"override image", owner=identity(4)
    )
    add_attachment(
        files, identity(3005), 5, "alone.png", b"untyped image", owner=identity(5)
    )
    source = write_source(tmp_path, files)
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "clean", result.issues
    record = json.loads((vault / "migration-record.json").read_bytes())
    assets = {a["asset_id"]: a["relative_path"] for a in record["asset_targets"]}
    default_icon = assets[identity(3002)]
    override_icon = assets[identity(3004)]
    category = (vault / "Categories/Concept.md").read_bytes()
    inherited = (vault / "Notes/Inherited.md").read_bytes()
    override = (vault / "Notes/Override.md").read_bytes()
    assert f'icon: "[[{default_icon}]]"\n' in property_block(category)
    assert "icon:\ncreated:" in property_block(inherited)
    assert f'icon: "[[{override_icon}]]"\n' in property_block(override)
    for generated in vault.rglob("*"):
        if generated.is_file() and generated.suffix in {".md", ".base", ".json"}:
            if generated.name == "migration-record.json":
                continue
            content = generated.read_bytes()
            assert b"foreground_color" not in content
            assert b"background_color" not in content
    assert ("![[" + default_icon + "]]\n\n").encode() in inherited
    assert ("![[" + override_icon + "]]\n\n").encode() in override
    assert b"Type label" not in inherited and b"Own label" in override
    assert b"## Resources" not in inherited and b"## Resources" not in override
    assert inherited.endswith(
        b"# Authored heading\r\n> Unicode: \xc3\xa9\r\n````md\r\nicon: original\r\n````\r"
    )
    assert not (vault / "Notes/Icon only.md").exists()
    assert sum(p.name == "type.png" for p in vault.rglob("*")) == 1
    assert (vault / default_icon).read_bytes() == b"type image"
    assert (vault / override_icon).read_bytes() == b"override image"
    decisions = {s.item_key: s for s in inspected.inspection.icon_snapshots}
    assert decisions[identity(3)].explicit_icon_asset_id is None
    assert decisions[identity(3)].appearance_category_key == identity(2)
    assert decisions[identity(3)].effective_icon_asset_id == identity(3002)
    assert decisions[identity(4)].explicit_icon_asset_id == identity(3004)
    assert decisions[identity(4)].effective_icon_asset_id == identity(3004)
    imported = {t["item_key"]: t for t in record["item_targets"]}
    assert imported[identity(2)]["declared_appearance"] == {
        "icon_asset_id": identity(3002),
        "foreground_color": "#6070FF",
        "background_color": "#FFE050",
    }
    assert imported[identity(4)]["declared_appearance"] == {
        "icon_asset_id": identity(3004),
        "foreground_color": "#FF0000",
        "background_color": None,
    }
    assert imported[identity(3)]["declared_appearance"] == {
        "icon_asset_id": None,
        "foreground_color": None,
        "background_color": None,
    }
    assert imported[identity(3)]["metadata_evidence"] == ["thoughts.json:2"]
    assert imported[identity(3)]["icon_snapshot"] == decisions[identity(3)].model_dump()
    original = next(
        e["records"] for e in record["original_evidence"] if e["key"] == "thoughts.json"
    )
    assert original[2]["ThoughtIconInfo"] == "4:file.pdf:1:False:False:0:"
    assert (
        original[1]["ForegroundColor"] == -10456833
        and original[1]["BackgroundColor"] == -8112
    )
    assert any(
        a["kind"] == "body_icon_snapshot" and a["affected"] == identity(3)
        for a in record["adaptations"]
    )
    snapshots = {
        a["affected"]
        for a in record["adaptations"]
        if a["kind"] == "body_icon_snapshot"
    }
    assert snapshots == {identity(3), identity(4)}
    assert {
        a.affected
        for a in inspected.inspection.adaptations
        if a.kind == "body_icon_snapshot"
    } == snapshots
    assert imported[identity(2)]["icon_snapshot"] == decisions[identity(2)].model_dump()


def test_public_renderer_refuses_a_changed_effective_icon_obligation(tmp_path):
    files = parts(
        graph_archive(tmp_path / "icon.brz", {1: "Entry"}, notes={1: (b"", 4)})
    )
    add_attachment(
        files, identity(3001), 5, "icon.png", b"local image", owner=identity(1)
    )
    with BrzSourceModule().open(write_source(tmp_path, files)) as session:
        migration = plan(analyze(session.snapshot, BRZ_POLICY))
    changed = migration.icon_snapshots[0].model_copy(
        update={"effective_icon_asset_id": "invented"}
    )
    migration = migration.model_copy(update={"icon_snapshots": (changed,)})
    with pytest.raises(MigrationRefused) as refused:
        render(migration, METADATA)
    assert refused.value.issues[0].phase == "rendering"


@pytest.mark.parametrize("owner", [2, 3], ids=["category-default", "member-override"])
def test_unsupported_destination_icon_is_refused_before_publication(
    tmp_path, capsys, owner
):
    # A genuine 1x1 PNG-backed ICO, rather than arbitrary bytes with an ICO name.
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010804000000b51c0c02"
        "0000000b4944415478da6364f80f00010501012718e3660000000049454e44ae426082"
    )
    ico = struct.pack("<HHHBBBBHHII", 0, 1, 1, 1, 1, 0, 0, 1, 32, len(png), 22) + png
    files = parts(
        graph_archive(
            tmp_path / "icons.brz",
            {1: "Entry", 2: "Concept", 3: "Member"},
            [(2, 3, 1, 2, -1)],
            kinds={2: 2},
            notes={1: (b"", 4)},
        )
    )
    set_thoughts(files, {identity(3): {"TypeId": identity(2)}})
    add_attachment(files, identity(3001), 5, "icon.ico", ico, owner=identity(owner))
    source = write_source(tmp_path, files)
    original = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    assert "destination feasibility" in inspected.inspection.pending_checks
    icon = next(a for a in inspected.inspection.assets if a.asset_id == identity(3001))
    assert icon.owner == identity(owner) and icon.role == "icon"
    assert icon.actual_length == len(ico)
    assert icon.actual_sha256 == hashlib.sha256(ico).hexdigest()
    assert inspected.receipt is None and inspected.counts.actual_notes is None

    absent = tmp_path / "absent-vault"
    empty = tmp_path / "empty-vault"
    empty.mkdir()
    for destination in (absent, empty):
        result = workflow.convert(source, destination)
        assert result.outcome == "refused", result.issues
        assert result.receipt is None and result.counts.actual_notes is None
        issue = result.issues[0]
        assert issue.code == "unsupported_feature" and issue.phase == "rendering"
        assert issue.affected == (identity(owner), identity(3001))
        assert ".ico" in issue.message and "image" in issue.guidance.lower()
    assert not absent.exists() and list(empty.iterdir()) == []
    assert main(["convert", str(source), str(absent), "--json"]) == 1
    serialized = json.loads(capsys.readouterr().out)
    assert serialized["outcome"] == "refused" and serialized["receipt"] is None
    assert not absent.exists() and source.read_bytes() == original


@pytest.mark.parametrize(
    "extension", ["avif", "bmp", "gif", "jpeg", "jpg", "png", "SVG", "webp"]
)
def test_reviewed_image_extensions_remain_eligible_for_imported_icons(
    tmp_path, extension
):
    files = parts(
        graph_archive(tmp_path / "icon.brz", {1: "Entry"}, notes={1: (b"", 4)})
    )
    # Public conversion/checking validates file kind and preservation, not codecs.
    payload = b"nonempty synthetic image payload"
    add_attachment(
        files, identity(3001), 5, "icon." + extension, payload, owner=identity(1)
    )
    source = write_source(tmp_path, files)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.issues
    checked = check_vault(vault)
    assert checked.outcome == "clean", checked.issues
    assert next(vault.rglob("icon." + extension)).read_bytes() == payload


def test_unselected_decorative_icon_is_preserved_without_fabricating_presentation(
    tmp_path,
):
    files = parts(
        graph_archive(
            tmp_path / "icon.brz",
            {1: "Entry", 2: "Uncreated"},
            notes={1: (b"", 4)},
        )
    )
    add_attachment(
        files, identity(3001), 5, "unselected.ico", b"preserve me", owner=identity(2)
    )
    source = write_source(tmp_path, files)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.issues
    assert not (vault / "Notes/Uncreated.md").exists()
    assert next(vault.rglob("unselected.ico")).read_bytes() == b"preserve me"
    assert check_vault(vault).outcome == "clean"


@pytest.mark.parametrize(
    "value", [0, 0xFF6070FF, -2147483648, -16777217, "#6070FF", True]
)
def test_unreviewed_colour_encodings_are_refused_without_invented_normalization(
    tmp_path, value
):
    files = parts(graph_archive(tmp_path / "colour.brz", {1: "Entry"}))
    set_thoughts(files, {identity(1): {"ForegroundColor": value}})
    source = write_source(tmp_path, files)
    workflow = default_workflow()
    assert workflow.inspect(source).outcome == "refused"
    result = workflow.convert(source, tmp_path / "vault")
    assert result.outcome == "refused" and result.receipt is None
    assert "colour" in result.issues[0].message
    assert not (tmp_path / "vault").exists()


def test_missing_empty_and_null_dates_stay_empty_with_exact_original_distinctions(
    tmp_path,
):
    files = parts(
        graph_archive(
            tmp_path / "dates.brz",
            {1: "Entry", 2: "Empty dates"},
            notes={2: (b"Authored.\r", 4)},
        )
    )
    set_thoughts(
        files,
        {
            identity(1): {"CreationDateTime": None},
            identity(2): {"CreationDateTime": "", "ModificationDateTime": None},
        },
    )
    source = write_source(tmp_path, files)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.issues
    for name in ("Home — Entry.md", "Notes/Empty dates.md"):
        assert "created:\nupdated:\n" in property_block((vault / name).read_bytes())
    record = json.loads((vault / "migration-record.json").read_bytes())
    originals = next(
        e["records"] for e in record["original_evidence"] if e["key"] == "thoughts.json"
    )
    assert (
        originals[0]["CreationDateTime"] is None
        and "ModificationDateTime" not in originals[0]
    )
    assert (
        originals[1]["CreationDateTime"] == ""
        and originals[1]["ModificationDateTime"] is None
    )
    assert all(
        t["calendar_dates"] == {"created": None, "updated": None}
        for t in record["item_targets"]
    )


def test_duplicate_owned_icons_are_not_chosen_by_attachment_order(tmp_path):
    files = parts(
        graph_archive(tmp_path / "icons.brz", {1: "Entry"}, notes={1: (b"", 4)})
    )
    add_attachment(
        files, identity(3001), 5, "first.png", b"first image", owner=identity(1)
    )
    add_attachment(
        files, identity(3002), 5, "second.png", b"second image", owner=identity(1)
    )
    source = write_source(tmp_path, files)
    assert default_workflow().inspect(source).outcome == "refused"
    files["attachments.json"] = b"\n".join(
        reversed(files["attachments.json"].splitlines())
    )
    source = write_source(tmp_path, files)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "refused" and result.issues[0].code == "invalid_source"
    assert "ambiguous owned icon" in result.issues[0].message


@pytest.mark.parametrize(
    "change", ["another_owner", "file_role", "zero_length", "unknown_asset"]
)
def test_public_core_refuses_inconsistent_declared_image_facts(tmp_path, change):
    files = parts(
        graph_archive(
            tmp_path / "icon.brz", {1: "Entry", 2: "Other"}, notes={1: (b"", 4)}
        )
    )
    add_attachment(files, identity(3001), 5, "icon.png", b"image", owner=identity(1))
    with BrzSourceModule().open(write_source(tmp_path, files)) as session:
        snapshot = session.snapshot
    icon = next(a for a in snapshot.assets if a.asset_id == identity(3001))
    if change == "unknown_asset":
        item = snapshot.items[0]
        item = item.model_copy(
            update={
                "declared_appearance": item.declared_appearance.model_copy(
                    update={"icon_asset_id": "unknown"}
                )
            }
        )
        snapshot = snapshot.model_copy(update={"items": (item, snapshot.items[1])})
    else:
        icon = icon.model_copy(
            update={"owner": identity(2)}
            if change == "another_owner"
            else {"role": "file"}
            if change == "file_role"
            else {"actual_length": 0}
        )
        snapshot = snapshot.model_copy(
            update={
                "assets": tuple(
                    icon if a.asset_id == icon.asset_id else a for a in snapshot.assets
                )
            }
        )
    with pytest.raises(MigrationRefused):
        analyze(snapshot, BRZ_POLICY)


def test_cli_metadata_obligations_agree_with_read_only_library_inspection(
    tmp_path, capsys
):
    files = parts(
        graph_archive(tmp_path / "icon.brz", {1: "Entry"}, notes={1: (b"Body.\r", 4)})
    )
    set_thoughts(files, {identity(1): {"CreationDateTime": "2024-02-29T23:00:00Z"}})
    add_attachment(files, identity(3001), 5, "icon.png", b"image", owner=identity(1))
    source = write_source(tmp_path, files)
    expected = default_workflow().inspect(source)
    assert main(["inspect", str(source), "--json"]) == 0
    actual = json.loads(capsys.readouterr().out)
    assert actual["inspection"]["icon_snapshots"] == [
        s.model_dump() for s in expected.inspection.icon_snapshots
    ]
    assert actual["inspection"]["adaptations"] == [
        a.model_dump(mode="json") for a in expected.inspection.adaptations
    ]
    assert actual["receipt"] is None and actual["counts"]["actual_notes"] is None
    assert main(["convert", str(source), str(tmp_path / "vault"), "--json"]) == 0
    converted = json.loads(capsys.readouterr().out)
    assert converted["receipt"]["published"] and converted["receipt"]["verified"]
    assert "created: 2024-02-29\n" in property_block(
        (tmp_path / "vault/Home — Entry.md").read_bytes()
    )


def test_generic_renderer_quotes_opaque_identity_strings_as_yaml_data():
    from tests.application.test_graph_modules import POLICY, snapshot

    facts = snapshot(())
    collection = 'source: "quoted"\n---\ncreated: fake'
    original = 'item: "quoted"\nicon: fake'
    facts = facts.model_copy(
        update={
            "identity": facts.identity.model_copy(update={"source_id": collection}),
            "items": (
                facts.items[0].model_copy(update={"original_identity": original}),
            ),
        }
    )
    artifacts = render(plan(analyze(facts, POLICY)), METADATA)
    note = next(
        f.content
        for f in artifacts.generated_files
        if f.relative_path == "Home — Entry.md"
    )
    metadata = property_block(note)
    assert (
        'source_collection_id: "source: \\"quoted\\"\\n---\\ncreated: fake"\n'
        in metadata
    )
    assert 'source_item_id: "item: \\"quoted\\"\\nicon: fake"\n' in metadata
    assert note.endswith(
        b"---\n\n# Entry\n\n## Categories\n\n[[Categories.md|Browse categories]]\n"
    )
