"""Category hierarchy observed through archive inspection and published vaults."""

import json
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from brz2obsidian.vault_check import check_vault
from tests.application.test_alternate_source import workflow as source_workflow
from tests.application.test_graph_workflow import graph_archive, identity
from tests.local_acceptance.checker import check_vault as audit_preservation
from tests.local_acceptance.checker import compare_vaults
from tests.local_acceptance.run import reordered_archive
from tests.sources.test_reader import rewrite
from tests.support.folio_source import FOLIO_POLICY, FolioSourceModule


def complete_hierarchy_archive(path, *, excluded_parent=True):
    source = graph_archive(
        path,
        {
            1: "Entry",
            2: "Concept",
            3: "Assigned parent",
            4: "Unassigned parent",
            5: "Empty parent",
            6: "Cycle A",
            7: "Cycle B",
            8: "Empty leaf",
            9: "Excluded parent",
            10: "Related",
            11: "Other category",
        },
        [
            (2, 3, 1, 2, -1),
            (3, 2, 1, 1, -1),
            (4, 2, 1, 1, -1),
            (5, 2, 1, 1, -1),
            (6, 7, 1, 1, -1),
            (7, 6, 1, 1, -1),
            (6, 8, 1, 1, -1),
            (9, 2, 1, 1, -1),
            (4, 10, 3, 1, -1),
            (4, 2, 1, 1, -1),
        ],
        kinds={2: 2, 11: 2},
        labels={2: "Category label"},
        notes={2: (b"Category source.\r\n", 4), 4: (b"Parent source.\r\n", 4)},
    )
    with ZipFile(source) as archive:
        thoughts = [
            json.loads(line) for line in archive.read("thoughts.json").splitlines()
        ]
    thoughts[2]["TypeId"] = identity(2)
    thoughts[8]["ForgottenDateTime"] = "2020-01-01"
    if not excluded_parent:
        thoughts.pop(8)
        with ZipFile(source) as archive:
            links = [
                json.loads(line) for line in archive.read("links.json").splitlines()
            ]
        links.pop(7)
        rewrite(source, "links.json", "\n".join(map(json.dumps, links)).encode())
    rewrite(source, "thoughts.json", "\n".join(map(json.dumps, thoughts)).encode())
    return source


def test_ordinary_parent_and_category_child_preserve_reciprocal_graph(tmp_path):
    source = graph_archive(
        tmp_path / "hierarchy.brz",
        {1: "Entry", 2: "Concept"},
        [(1, 2, 1, 1, -1)],
        kinds={2: 2},
    )
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    assert inspected.counts.source_relationships == 1
    assert inspected.counts.classification_assignments == 0
    vault = tmp_path / "vault"
    converted = workflow.convert(source, vault)
    assert converted.outcome == "clean", converted.issues
    assert "## Children\n\n- [[Categories/Concept.md|Concept]]" in (
        vault / "Home — Entry.md"
    ).read_text(encoding="utf-8")
    assert "## Parents\n\n- [[Home — Entry.md|Entry]]" in (
        vault / "Categories/Concept.md"
    ).read_text(encoding="utf-8")
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert record["relationships"] == [
        {
            "key": identity(1000),
            "kind": "hierarchy",
            "item_a": identity(1),
            "item_b": identity(2),
            "evidence": ["links.json:0"],
            "target_a": "Home — Entry.md",
            "target_b": "Categories/Concept.md",
            "presentation": "Parents/Children",
        }
    ]


def test_complete_category_hierarchy_precedes_members_and_preserves_selection(
    tmp_path, capsys
):
    source = complete_hierarchy_archive(tmp_path / "complete.brz")
    source_bytes = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    targets = {t.item_key: t for t in inspected.inspection.item_targets}
    assert {k for k, t in targets.items() if t.created} == {
        identity(n) for n in (1, 2, 3, 4, 6, 11)
    }
    assert identity(9) not in targets
    assert targets[identity(3)].creation_reasons == ("classification",)
    assert targets[identity(6)].creation_reasons == ("hierarchy",)
    assert inspected.counts.source_relationships == 9
    assert inspected.counts.classification_assignments == 1
    assert inspected.counts.typed_members == 1
    assert main(["inspect", str(source), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == inspected.model_dump(
        mode="json", by_alias=True
    )
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 0
    converted = json.loads(capsys.readouterr().out)
    assert converted["receipt"]["published"] and converted["receipt"]["verified"]
    assert converted["counts"]["actual_notes"] == inspected.counts.planned_notes == 6
    category = (vault / "Categories/Concept.md").read_text(encoding="utf-8")
    expected_parents = (
        "## Parents\n\n"
        "- [[Notes/Assigned parent.md|Assigned parent]]\n"
        "- [[Notes/Unassigned parent.md|Unassigned parent]]\n"
        "- [[Notes/Empty parent.md|Empty parent]]\n\n"
    )
    assert category.split("---\n", 2)[2].startswith(
        "\n# Concept\n\n" + expected_parents + "## Members\n\n"
    )
    assert category.count("## Parents") == 1
    assert category.index("## Gallery") < category.index("Category label")
    assert b"Category source.\r\n" in (vault / "Categories/Concept.md").read_bytes()
    assigned = (vault / "Notes/Assigned parent.md").read_text(encoding="utf-8")
    assert 'categories:\n  - "[[Categories/Concept.md]]"' in assigned
    assert assigned.endswith("## Children\n\n- [[Categories/Concept.md|Concept]]\n")
    unassigned = (vault / "Notes/Unassigned parent.md").read_bytes()
    assert b"categories: []\n" in unassigned
    assert unassigned.endswith(
        b"Parent source.\r\n\n## Children\n\n"
        b"- [[Categories/Concept.md|Concept]]\n\n"
        b"## Related\n\n- [[Notes/Related.md|Related]]\n"
    )
    cycle = (vault / "Notes/Cycle A.md").read_text(encoding="utf-8")
    assert "## Parents\n\n- [[Notes/Cycle B.md|Cycle B]]" in cycle
    assert (
        "## Children\n\n- [[Notes/Cycle B.md|Cycle B]]\n- [[Notes/Empty leaf.md|Empty leaf]]"
        in cycle
    )
    for name in ("Empty parent", "Cycle B", "Empty leaf", "Related", "Excluded parent"):
        assert not (vault / ("Notes/" + name + ".md")).exists()
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert len(record["relationships"]) == 9
    assert len(record["classification_assignments"]) == 1
    assert {
        (r["item_a"], r["item_b"])
        for r in record["relationships"]
        if r["kind"] == "hierarchy" and r["item_b"] == identity(2)
    } == {(identity(n), identity(2)) for n in (3, 4, 5)}
    assert all(
        identity(9).encode() not in p.read_bytes()
        and b"Excluded parent" not in p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    )
    repeat = tmp_path / "repeat"
    reordered = tmp_path / "reordered.brz"
    reordered_archive(source, reordered)
    assert workflow.convert(source, repeat).outcome == "clean"
    assert workflow.convert(reordered, tmp_path / "reordered").outcome == "clean"
    compare_vaults(vault, repeat)
    compare_vaults(vault, tmp_path / "reordered")
    assert check_vault(vault).outcome == "clean"
    control = complete_hierarchy_archive(
        tmp_path / "included.brz", excluded_parent=False
    )
    assert workflow.convert(control, tmp_path / "included").outcome == "clean"
    audit_preservation(control, tmp_path / "included")
    for path in vault.rglob("*.md"):
        relative = path.relative_to(vault)
        if relative.as_posix() != "MIGRATION REPORT.md":
            assert path.read_bytes() == (tmp_path / "included" / relative).read_bytes()
    assert source.read_bytes() == source_bytes


@pytest.mark.parametrize(
    "change, expected_code",
    [
        ({"Direction": 1}, "unsupported_feature"),
        ({"Direction": 7}, "unsupported_feature"),
        ({"Direction": 0}, "unsupported_feature"),
        ({"Direction": "-1"}, "unsupported_feature"),
        ({"Kind": 2}, "unsupported_feature"),
        ({"Kind": True}, "unsupported_feature"),
        ({"Relation": 3}, "unsupported_feature"),
        ({"Meaning": 3}, "unsupported_feature"),
        ({"Meaning": 2}, "unsupported_feature"),
        ({"TypeId": identity(99)}, "unsupported_feature"),
        ({"LinkTypeId": identity(99)}, "unsupported_feature"),
        ({"ThoughtIdA": identity(2), "ThoughtIdB": identity(1)}, "unsupported_feature"),
        ({"ThoughtIdA": identity(3)}, "unsupported_feature"),
        ({"ThoughtIdB": identity(99)}, "invalid_reference"),
        ({"ThoughtIdB": "invalid"}, "invalid_source"),
        ({"BrainId": identity(99)}, "invalid_source"),
    ],
)
def test_category_hierarchy_near_misses_refuse_without_publication(
    tmp_path, change, expected_code
):
    source = graph_archive(
        tmp_path / "unsupported.brz",
        {1: "Entry", 2: "Concept", 3: "Other category"},
        [(1, 2, 1, 1, -1)],
        kinds={2: 2, 3: 2},
    )
    with ZipFile(source) as archive:
        link = json.loads(archive.read("links.json"))
    rewrite(source, "links.json", json.dumps(link | change).encode())
    original = source.read_bytes()
    workflow = default_workflow()
    for result in (
        workflow.inspect(source),
        workflow.convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused", result.issues
        assert result.issues[0].code == expected_code
        assert result.receipt is None
    assert source.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ["unsupported.brz"]


def test_hierarchy_does_not_satisfy_type_assignment_correspondence(tmp_path):
    source = graph_archive(
        tmp_path / "assignment.brz",
        {1: "Entry", 2: "Concept"},
        [(1, 2, 1, 1, -1)],
        kinds={2: 2},
    )
    with ZipFile(source) as archive:
        thoughts = [
            json.loads(line) for line in archive.read("thoughts.json").splitlines()
        ]
    thoughts[0]["TypeId"] = identity(2)
    rewrite(source, "thoughts.json", "\n".join(map(json.dumps, thoughts)).encode())
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "refused"
    assert result.issues[0].code == "invalid_reference"
    assert result.receipt is None and not (tmp_path / "vault").exists()


def test_source_neutral_category_children_precede_bases_and_related_follows_content(
    tmp_path,
):
    source = tmp_path / "folio.json"
    source.write_text(
        json.dumps(
            {
                "collection": "Opaque hierarchy",
                "start": "entry",
                "entries": [
                    {"key": "entry", "seed": "01", "title": "Entry"},
                    {
                        "key": "category",
                        "seed": "02",
                        "title": "Concept",
                        "role": "definition",
                        "label": "Category content",
                    },
                    {"key": "child", "seed": "03", "title": "Child"},
                    {"key": "related", "seed": "04", "title": "Related"},
                ],
                "connections": [
                    {
                        "key": "parent",
                        "kind": "hierarchy",
                        "item_a": "entry",
                        "item_b": "category",
                    },
                    {
                        "key": "child",
                        "kind": "hierarchy",
                        "item_a": "category",
                        "item_b": "child",
                    },
                    {
                        "key": "related",
                        "kind": "related",
                        "item_a": "category",
                        "item_b": "related",
                    },
                ],
                "assets": [],
                "documents": [],
            }
        ),
        encoding="utf-8",
    )
    operation = source_workflow(FolioSourceModule(), FOLIO_POLICY)
    inspected = operation.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    assert inspected.counts.classification_assignments == 0
    vault = tmp_path / "vault"
    converted = operation.convert(source, vault)
    assert converted.outcome == "clean", converted.issues
    body = (
        (vault / "Categories/Concept.md")
        .read_text(encoding="utf-8")
        .split("---\n", 2)[2]
    )
    assert body == (
        "\n# Concept\n\n## Parents\n\n- [[Home — Entry.md|Entry]]\n\n"
        "## Children\n\n- [[Notes/Child.md|Child]]\n\n"
        "## Members\n\n![[Templates/Bases/Members.base#Members]]\n\n"
        "## Gallery\n\n![[Templates/Bases/Gallery.base#Gallery]]\n\n"
        "Category content\n\n## Related\n\n- [[Notes/Related.md|Related]]\n"
    )
