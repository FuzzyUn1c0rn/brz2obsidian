"""Typed migration behavior observed through actual archives and vaults."""

import hashlib
import json
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.core import analyze
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from brz2obsidian.vault_check import check_vault
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_verified_coverage import add_attachment, write_source
from tests.local_acceptance.checker import check_vault as audit_preservation
from tests.local_acceptance.checker import compare_vaults
from tests.local_acceptance.run import reordered_archive
from tests.sources.test_reader import rewrite


def typed_archive(path):
    source = graph_archive(
        path,
        {1: "Entry", 2: "Concept", 3: "Empty member", 4: "Untyped empty"},
        [(2, 3, 1, 2, -1)],
        kinds={2: 2},
    )
    with ZipFile(source) as archive:
        thoughts = [
            json.loads(line) for line in archive.read("thoughts.json").splitlines()
        ]
    thoughts[2]["TypeId"] = identity(2)
    rewrite(
        source, "thoughts.json", "\n".join(json.dumps(t) for t in thoughts).encode()
    )
    return source


def test_category_bases_precede_preserved_source_content_without_introductory_icon(
    tmp_path,
):
    authored = b"Category prose.\r\n![authored](.data/md-images/photo.png)\r\nTail\r"
    source = graph_archive(
        tmp_path / "dashboard.brz",
        {1: "Entry", 2: "Concept", 3: "Member", 4: "Related", 5: "Child"},
        [(2, 3, 1, 2, -1), (3, 5, 1, 1, -1), (3, 4, 3, 1, -1), (1, 2, 1, 1, -1)],
        kinds={2: 2},
        labels={2: "Definition label"},
        notes={2: (authored, 4)},
    )
    with ZipFile(source) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    thoughts = [json.loads(line) for line in files["thoughts.json"].splitlines()]
    thoughts[2]["TypeId"] = identity(2)
    thoughts[1].update(
        CreationDateTime="2024-02-29T23:59:00-11:00",
        ModificationDateTime="2025-01-01T00:00:00+14:00",
    )
    files["thoughts.json"] = "\n".join(json.dumps(t) for t in thoughts).encode()
    for number, kind, filename, data in (
        (3001, 5, "type.png", b"category icon"),
        (3002, 12, "photo.png", b"authored image"),
        (3003, 1, "manual.bin", b"category resource"),
    ):
        add_attachment(files, identity(number), kind, filename, data, owner=identity(2))
    source = write_source(tmp_path, files)
    source_bytes = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    category_icon = next(
        s for s in inspected.inspection.icon_snapshots if s.item_key == identity(2)
    )
    assert category_icon.effective_icon_asset_id == identity(3001)
    vault = tmp_path / "vault"
    converted = workflow.convert(source, vault)
    assert converted.outcome == "clean", converted.issues
    folder = "Attachments/00000000000000000000000000000002/"
    category = (vault / "Categories/Concept.md").read_bytes()
    dashboard = (
        b"# Concept\n\n## Parents\n\n- [[Home \xe2\x80\x94 Entry.md|Entry]]\n\n"
        b"## Members\n\n![[Templates/Bases/Members.base#Members]]\n\n"
        b"## Gallery\n\n![[Templates/Bases/Gallery.base#Gallery]]\n\n"
    )
    assert category.split(b"---\n", 2)[2].startswith(b"\n" + dashboard)
    assert ("![[" + folder + "type.png]]").encode() not in category
    assert category.split(dashboard, 1)[1] == (
        b"Definition label\n\nCategory prose.\r\n"
        b"![authored](../Attachments/00000000000000000000000000000002/photo.png)\r\n"
        b"Tail\r\n\n## Resources\n\n"
        b"- [[Attachments/00000000000000000000000000000002/manual.bin|manual.bin]]\n"
    )
    assert ('icon: "[[' + folder + 'type.png]]"\n').encode() in category
    assert b"created: 2024-02-29\nupdated: 2025-01-01\n" in category
    assert ('source_item_id: "' + identity(2) + '"\n').encode() in category
    member = (vault / "Notes/Member.md").read_bytes()
    assert ("# Member\n\n![[" + folder + "type.png]]\n\n").encode() in member
    assert member.endswith(
        b"## Children\n\n- [[Notes/Child.md|Child]]\n\n"
        b"## Related\n\n- [[Notes/Related.md|Related]]\n"
    )
    assert (vault / (folder + "type.png")).read_bytes() == b"category icon"
    assert (vault / (folder + "photo.png")).read_bytes() == b"authored image"
    assert (vault / (folder + "manual.bin")).read_bytes() == b"category resource"
    assert (vault / (folder + "Notes.md.original")).read_bytes() == authored
    assert check_vault(vault).outcome == "clean"
    audit_preservation(source, vault)
    assert source.read_bytes() == source_bytes


def test_inspection_and_conversion_materialize_categories_and_typed_empty_members(
    tmp_path,
):
    source = typed_archive(tmp_path / "typed.brz")
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    assert inspected.schema_version == 6 and inspected.profile_version == "7"
    assert inspected.receipt is None and inspected.counts.actual_notes is None
    assert inspected.counts.planned_notes == 3
    assert inspected.counts.source_definitions == 1
    assert inspected.counts.classification_assignments == 1
    assert inspected.counts.typed_members == 1
    assert inspected.counts.planned_category_notes == 1
    targets = {t.item_key: t for t in inspected.inspection.item_targets}
    assert targets[identity(2)].relative_path == "Categories/Concept.md"
    assert targets[identity(2)].creation_reasons == ("definition",)
    assert targets[identity(3)].creation_reasons == ("classification",)
    assert not targets[identity(4)].created
    assert len(inspected.inspection.classification_assignments) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["typed.brz"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original

    vault = tmp_path / "vault"
    converted = workflow.convert(source, vault)
    assert converted.outcome == "clean", converted.issues
    assert converted.receipt.published and converted.receipt.verified
    assert converted.counts.actual_notes == 3
    assert converted.counts.actual_category_notes == 1
    assert converted.counts.planned_notes == inspected.counts.planned_notes
    body = (vault / "Notes/Empty member.md").read_text(encoding="utf-8")
    assert 'categories:\n  - "[[Categories/Concept.md]]"' in body
    assert 'appearance_category: "[[Categories/Concept.md]]"' in body
    assert (
        (vault / "Categories/Concept.md")
        .read_text(encoding="utf-8")
        .endswith(
            "# Concept\n\n## Members\n\n![[Templates/Bases/Members.base#Members]]\n\n## Gallery\n\n![[Templates/Bases/Gallery.base#Gallery]]\n\n"
        )
    )
    assert not (vault / "Notes/Untyped empty.md").exists()
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert record["schema_version"] == 6 and record["renderer_version"] == "6"
    assert (
        record["classification_assignments"][0]["definition_target"]
        == "Categories/Concept.md"
    )
    assert record["relationships"][0]["presentation"] == "linked category membership"
    assert {f.relative_path for f in converted.receipt.manifest} == {
        p.relative_to(vault).as_posix() for p in vault.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize(
    "change",
    [
        "missing_assignment",
        "duplicate_assignment",
        "wrong_member",
        "wrong_definition",
        "missing_relationship",
        "old_contract",
        "missing_evidence",
        "invented_evidence",
    ],
)
def test_public_core_refuses_inconsistent_classification_contracts(tmp_path, change):
    with BrzSourceModule().open(typed_archive(tmp_path / "typed.brz")) as session:
        snapshot = session.snapshot
    assignment = snapshot.classification_assignments[0]
    policy = BRZ_POLICY
    if change == "missing_assignment":
        snapshot = snapshot.model_copy(update={"classification_assignments": ()})
    elif change == "duplicate_assignment":
        snapshot = snapshot.model_copy(
            update={"classification_assignments": (assignment, assignment)}
        )
    elif change in {"wrong_member", "wrong_definition"}:
        assignment = assignment.model_copy(
            update={"item_key": identity(2)}
            if change == "wrong_member"
            else {"definition_key": identity(1)}
        )
        snapshot = snapshot.model_copy(
            update={"classification_assignments": (assignment,)}
        )
    elif change == "missing_relationship":
        snapshot = snapshot.model_copy(update={"relationships": ()})
    elif change in {"missing_evidence", "invented_evidence"}:
        assignment = assignment.model_copy(
            update={"evidence": () if change == "missing_evidence" else ("invented",)}
        )
        snapshot = snapshot.model_copy(
            update={"classification_assignments": (assignment,)}
        )
    else:
        snapshot = snapshot.model_copy(update={"contract_version": 1})
        policy = policy.model_copy(update={"contract_version": 1})
    with pytest.raises(MigrationRefused):
        analyze(snapshot, policy)


def test_category_content_resources_graph_tags_and_support_names_are_preserved(
    tmp_path,
):
    source = graph_archive(
        tmp_path / "rich.brz",
        {
            1: "Entry",
            2: "Categories",
            3: "Member",
            4: "Untyped",
            5: "Parent",
            6: "Leaf",
            7: "categories",
            8: "System",
            9: "Empty definition",
        },
        [
            (2, 3, 1, 2, -1),
            (5, 3, 1, 1, -1),
            (5, 6, 1, 1, -1),
            (7, 3, 1, 5, -1),
            (8, 2, 1, 6, -1),
        ],
        kinds={2: 2, 7: 4, 8: 5, 9: 2},
        labels={2: "Definition-only label"},
        notes={1: (b"Home content.\r\n", 4), 2: (b"Definition-owned Markdown.\r\n", 4)},
    )
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    thoughts[2]["TypeId"] = identity(2)
    parts["thoughts.json"] = "\n".join(json.dumps(t) for t in thoughts).encode()
    payload = b"definition-owned bytes\x00\xff"
    add_attachment(parts, identity(3001), 1, "owned.bin", payload, owner=identity(2))
    source = write_source(tmp_path, parts)
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    targets = {t.item_key: t for t in inspected.inspection.item_targets}
    category = targets[identity(2)].relative_path
    assert category.startswith("Categories/Categories — ")
    assert targets[identity(7)].relative_path.startswith("Notes/categories — ")
    assert targets[identity(9)].created
    assert targets[identity(5)].creation_reasons == ("hierarchy",)
    assert not targets[identity(4)].created and not targets[identity(6)].created
    assert identity(8) not in targets
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "clean", result.issues
    definition = (vault / category).read_bytes()
    member = (vault / targets[identity(3)].relative_path).read_text(encoding="utf-8")
    assert (
        b"Definition-only label" in definition
        and b"Definition-owned Markdown.\r\n" in definition
    )
    assert (
        "Definition-only label" not in member
        and "Definition-owned" not in member
        and "owned.bin" not in member
    )
    assert "## Parents" in member and "[[Notes/Parent.md|Parent]]" in member
    assert 'tags:\n  - "categories"' in member
    assert "## Parents" not in definition.decode()
    record = json.loads((vault / "migration-record.json").read_bytes())
    retained = next(
        e["records"] for e in record["original_evidence"] if e["key"] == "thoughts.json"
    )
    assert retained == thoughts
    system = next(r for r in record["relationships"] if r["kind"] == "system")
    assert system["presentation"] == "retained_only" and system["target_a"] is None
    original = next(
        a for a in record["asset_targets"] if a["asset_id"] == identity(2002)
    )
    copied = next(a for a in record["asset_targets"] if a["asset_id"] == identity(3001))
    assert (
        vault / original["relative_path"]
    ).read_bytes() == b"Definition-owned Markdown.\r\n"
    assert (vault / copied["relative_path"]).read_bytes() == payload
    assert result.counts.actual_notes == 5 and result.counts.actual_assets == 3
    assert (
        result.counts.planned_support_files == result.counts.actual_support_files == 19
    )
    assert len(record["support_artifacts"]) == 19
    before = {
        p.relative_to(vault): p.read_bytes() for p in vault.rglob("*") if p.is_file()
    }
    refused = workflow.convert(source, vault)
    assert (
        refused.outcome == "refused"
        and refused.issues[0].code == "destination_not_empty"
    )
    assert refused.receipt is None
    assert {
        p.relative_to(vault): p.read_bytes() for p in vault.rglob("*") if p.is_file()
    } == before


@pytest.mark.parametrize(
    "corruption",
    [
        "field_missing",
        "link_missing",
        "duplicate",
        "conflict",
        "dangling",
        "wrong_role",
        "definition_assigned",
        "reverse",
        "subtype",
        "custom_link",
        "malformed_id",
    ],
)
def test_assignment_corruption_and_unreviewed_type_meanings_refuse_without_publication(
    tmp_path, corruption
):
    source = typed_archive(tmp_path / "typed.brz")
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    links = [json.loads(line) for line in parts["links.json"].splitlines()]
    if corruption == "field_missing":
        del thoughts[2]["TypeId"]
    elif corruption == "link_missing":
        links = []
    elif corruption in {"duplicate", "conflict"}:
        second = links[0] | {"Id": identity(1002)}
        if corruption == "conflict":
            thoughts.append(thoughts[1] | {"Id": identity(5), "Name": "Other type"})
            second["ThoughtIdA"] = identity(5)
        links.append(second)
    elif corruption == "dangling":
        thoughts[2]["TypeId"] = identity(999)
    elif corruption == "wrong_role":
        thoughts[1]["Kind"] = 4
    elif corruption == "definition_assigned":
        thoughts[1]["TypeId"] = identity(2)
    elif corruption == "reverse":
        links[0]["ThoughtIdA"], links[0]["ThoughtIdB"] = (
            links[0]["ThoughtIdB"],
            links[0]["ThoughtIdA"],
        )
    elif corruption == "subtype":
        links[0]["Meaning"] = 3
    elif corruption == "custom_link":
        links[0]["LinkTypeId"] = identity(999)
    else:
        thoughts[2]["TypeId"] = "not-an-identity"
    parts["thoughts.json"] = "\n".join(json.dumps(t) for t in thoughts).encode()
    parts["links.json"] = "\n".join(json.dumps(link) for link in links).encode()
    result = default_workflow().convert(
        write_source(tmp_path, parts), tmp_path / "vault"
    )
    assert result.outcome == "refused", result.issues
    assert result.receipt is None and not (tmp_path / "vault").exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


def test_typed_cli_matches_read_only_inspection_obligations_and_verified_conversion(
    tmp_path, capsys
):
    source = typed_archive(tmp_path / "typed.brz")
    expected = default_workflow().inspect(source)
    assert main(["inspect", str(source), "--json"]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope == expected.model_dump(mode="json", by_alias=True)
    assert envelope["inspection"]["asset_targets"] == []
    assert envelope["inspection"]["documents"] == []
    assert len(envelope["inspection"]["support_artifacts"]) == 18
    assert (
        envelope["receipt"] is None
        and envelope["counts"]["actual_support_files"] is None
    )
    assert main(["convert", str(source), str(tmp_path / "vault"), "--json"]) == 0
    converted = json.loads(capsys.readouterr().out)
    assert converted["schema_version"] == 6 and converted["inspection"] is None
    assert converted["receipt"]["verified"] and converted["counts"]["actual_notes"] == 3
    assert (
        converted["counts"]["planned_support_files"]
        == converted["counts"]["actual_support_files"]
        == 18
    )
    assert main(["convert", str(source), str(tmp_path / "vault"), "--json"]) == 1
    refused = json.loads(capsys.readouterr().out)
    assert refused["outcome"] == "refused" and refused["receipt"] is None


@pytest.mark.parametrize(
    "title",
    ["Categories", "Vault guide", "New note", "Member template starter", "Members"],
)
def test_future_support_names_are_reserved_for_imported_definitions(tmp_path, title):
    source = typed_archive(tmp_path / "typed.brz")
    with ZipFile(source) as archive:
        thoughts = [
            json.loads(line) for line in archive.read("thoughts.json").splitlines()
        ]
    thoughts[1]["Name"] = title
    rewrite(
        source, "thoughts.json", "\n".join(json.dumps(t) for t in thoughts).encode()
    )
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    category = next(
        t for t in inspected.inspection.item_targets if t.item_key == identity(2)
    )
    assert category.original_title == title
    assert category.relative_path == "Categories/" + title + " — 00000000.md"
    assert "Templates/New note.md" not in inspected.inspection.reserved_support_paths
    assert "Templates/" + title + " — 00000000.md" in {
        a.relative_path for a in inspected.inspection.support_artifacts
    }
    assert "Categories.md" in {
        a.relative_path for a in inspected.inspection.support_artifacts
    }


def test_definition_owned_reference_spans_and_payloads_agree_with_inspection(tmp_path):
    body = b"Before\r\n[member](brain://AAAAAAAAAAAAAAAAAAAAAw/ignored)\r\n![photo](.data/md-images/photo.png)\r\nAfter\r"
    source = graph_archive(
        tmp_path / "typed.brz",
        {1: "Entry", 2: "Concept", 3: "Member"},
        [(2, 3, 1, 2, -1)],
        kinds={2: 2},
        notes={2: (body, 4)},
    )
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    thoughts[2]["TypeId"] = identity(2)
    parts["thoughts.json"] = "\n".join(json.dumps(t) for t in thoughts).encode()
    add_attachment(
        parts,
        identity(3001),
        12,
        "photo.png",
        b"original image\x00\xff",
        owner=identity(2),
    )
    source = write_source(tmp_path, parts)
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    assert (
        len(inspected.inspection.asset_targets) == len(inspected.inspection.assets) == 2
    )
    assert inspected.inspection.documents[0].original_asset_id == identity(2002)
    assert len(inspected.inspection.documents[0].references) == 2
    assert {a.kind for a in inspected.inspection.adaptations} >= {
        "item_reference",
        "image_reference",
    }
    vault = tmp_path / "vault"
    converted = workflow.convert(source, vault)
    assert converted.outcome == "clean", converted.issues
    assert (
        b"Before\r\n[[Notes/Member.md|member]]\r\n![photo](../Attachments/00000000000000000000000000000002/photo.png)\r\nAfter\r"
        in (vault / "Categories/Concept.md").read_bytes()
    )
    assert (
        vault / "Attachments/00000000000000000000000000000002/Notes.md.original"
    ).read_bytes() == body
    assert (
        vault / "Attachments/00000000000000000000000000000002/photo.png"
    ).read_bytes() == b"original image\x00\xff"
    assert (
        converted.counts.actual_references == inspected.counts.planned_references == 2
    )


def test_typed_home_and_category_output_repeat_across_record_and_zip_reordering(
    tmp_path,
):
    source = typed_archive(tmp_path / "typed.brz")
    with ZipFile(source) as archive:
        thoughts = [
            json.loads(line) for line in archive.read("thoughts.json").splitlines()
        ]
        links = [json.loads(line) for line in archive.read("links.json").splitlines()]
    thoughts[0]["TypeId"] = identity(2)
    links.append(links[0] | {"Id": identity(1002), "ThoughtIdB": identity(1)})
    rewrite(
        source, "thoughts.json", "\n".join(json.dumps(t) for t in thoughts).encode()
    )
    rewrite(
        source, "links.json", "\n".join(json.dumps(link) for link in links).encode()
    )
    reordered = tmp_path / "reordered.brz"
    reordered_archive(source, reordered)
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    home = next(
        t for t in inspected.inspection.item_targets if t.item_key == identity(1)
    )
    assert home.relative_path == "Home — Entry.md" and home.creation_reasons == (
        "home",
        "classification",
    )
    first = workflow.convert(source, tmp_path / "first")
    second = workflow.convert(reordered, tmp_path / "second")
    assert first.outcome == second.outcome == "clean"
    assert first.counts == second.counts
    assert first.counts.typed_members == 2 and first.counts.actual_notes == 3
    compare_vaults(tmp_path / "first", tmp_path / "second")
