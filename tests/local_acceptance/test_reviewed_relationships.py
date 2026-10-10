"""Raw relationship evidence defeats internally consistent navigation forgeries."""

import json

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_reviewed_relationships_workflow import edit_rows
from tests.local_acceptance.checker import check_run_result, check_vault
from tests.local_acceptance.test_checker_v2 import rewrite_record


def relationship_archive(path, shape):
    return graph_archive(
        path,
        {1: "Entry", 2: "Other"},
        [(1, 2, 1, 1, 3)] if shape == "hierarchy" else [(1, 2, 3, 1, -1)],
        kinds={2: 1 if shape == "hierarchy" else 2},
        notes={2: (b"Other source.\r\n", 4)},
    )


def test_raw_instance_assignment_remains_independent_of_normal_category_jump(tmp_path):
    source = relationship_archive(tmp_path / "source.brz", "jump")
    edit_rows(source, "thoughts.json", lambda rows: rows[0].update(TypeId=identity(2)))
    edit_rows(
        source,
        "links.json",
        lambda rows: rows.append(
            {
                **rows[0],
                "Id": identity(1001),
                "ThoughtIdA": identity(2),
                "ThoughtIdB": identity(1),
                "Relation": 1,
                "Meaning": 2,
            }
        ),
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    assert result["outcome"] == "clean"
    assert (
        result["counts"]["classification_assignments"]
        == result["counts"]["typed_members"]
        == 1
    )
    summary = check_vault(source, vault)
    check_run_result(result, vault, summary)


@pytest.mark.parametrize("shape", ["hierarchy", "jump"])
def test_raw_source_complete_note_audit_accepts_only_exact_new_relationships(
    tmp_path, shape
):
    source = relationship_archive(tmp_path / "source.brz", shape)
    before = source.read_bytes()
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    assert result["outcome"] == "clean", result["issues"]
    summary = check_vault(source, vault)
    check_run_result(result, vault, summary)
    assert source.read_bytes() == before


@pytest.mark.parametrize("shape", ["hierarchy", "jump"])
@pytest.mark.parametrize(
    "damage",
    [
        "drop",
        "swap",
        "reclassify",
        "reverse_navigation",
        "delete_a",
        "delete_b",
        "hierarchy_heading",
        "raw_direction",
    ],
)
def test_raw_relationship_oracle_rejects_rehashed_semantic_corruption(
    tmp_path, shape, damage
):
    source = relationship_archive(tmp_path / "source.brz", shape)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    check_vault(source, vault)
    record = json.loads((vault / "migration-record.json").read_bytes())
    relationship = record["relationships"][0]
    a = vault / "Home — Entry.md"
    b = vault / ("Notes/Other.md" if shape == "hierarchy" else "Categories/Other.md")
    before = {p: p.read_bytes() for p in (a, b)}
    old_record = json.dumps(record, sort_keys=True)
    if damage == "drop":
        record["relationships"] = []
        record["counts"]["source_relationships"] = 0
        record["adaptations"] = [
            d for d in record["adaptations"] if d["kind"] != "relationship_presentation"
        ]
    elif damage == "swap":
        relationship["item_a"], relationship["item_b"] = (
            relationship["item_b"],
            relationship["item_a"],
        )
        relationship["target_a"], relationship["target_b"] = (
            relationship["target_b"],
            relationship["target_a"],
        )
    elif damage == "reclassify":
        relationship.update(
            kind="classification",
            item_a=identity(2),
            item_b=identity(1),
            target_a=relationship["target_b"],
            target_b=relationship["target_a"],
        )
        record["classification_assignments"] = [
            {
                "relationship_key": identity(1000),
                "definition_key": identity(2),
                "item_key": identity(1),
                "evidence": ["thoughts.json:0", "links.json:0"],
                "definition_target": relationship["target_a"],
                "item_target": relationship["target_b"],
            }
        ]
        record["counts"]["classification_assignments"] = record["counts"][
            "typed_members"
        ] = 1
    elif damage == "raw_direction":
        evidence = next(
            e for e in record["original_evidence"] if e["key"] == "links.json"
        )
        evidence["records"][0]["Direction"] = -1 if shape == "hierarchy" else 3
    elif damage == "reverse_navigation":
        for path in (a, b):
            body = path.read_bytes()
            path.write_bytes(
                body.replace(b"## Children", b"## Parents")
                if path == a
                else body.replace(b"## Parents", b"## Children")
                if shape == "hierarchy"
                else body.replace(b"## Related", b"## Parents")
            )
        if shape == "jump":
            a.write_bytes(a.read_bytes().replace(b"## Related", b"## Children"))
    elif damage == "hierarchy_heading":
        a.write_bytes(
            a.read_bytes().replace(
                b"## Children" if shape == "hierarchy" else b"## Related", b"## Parents"
            )
        )
    else:
        path = a if damage == "delete_a" else b
        header = (
            b"## Children"
            if shape == "hierarchy" and path == a
            else b"## Parents"
            if shape == "hierarchy"
            else b"## Related"
        )
        body = path.read_bytes()
        start = body.index(header)
        end = body.find(b"\n\n## ", start)
        path.write_bytes(body[:start] + (body[end + 2 :] if end != -1 else b""))
    assert old_record != json.dumps(record, sort_keys=True) or any(
        before[p] != p.read_bytes() for p in (a, b)
    )
    rewrite_record(vault, record, result)
    with pytest.raises(AssertionError):
        summary = check_vault(source, vault)
        check_run_result(result, vault, summary)
