"""Exact bounded source signatures through authored ZIPs and published navigation."""

import json
from uuid import UUID
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from tests.application.test_graph_workflow import graph_archive, identity
from tests.sources.test_reader import rewrite
from tests.support.notes import note_body


def edit_rows(source, name, edit):
    with ZipFile(source) as archive:
        rows = [json.loads(line) for line in archive.read(name).splitlines()]
    edit(rows)
    rewrite(source, name, "\n".join(map(json.dumps, rows)).encode())


@pytest.mark.parametrize(
    "token",
    [
        "a1b2c3d4-e5f6-4a78-9abc-def012345678",
        "A1B2C3D4-E5F6-4A78-9ABC-DEF012345678",
        "1MOyofbleEqavN7wEjRWeA",
        "%31%4D%4F%79%6F%66%62%6C%65%45%71%61%76%4E%37%77%45%6A%52%57%65%41",
        r"\u0031\u004d\u004f\u0079\u006f\u0066\u0062\u006c\u0065\u0045\u0071\u0061\u0076\u004e\u0037\u0077\u0045\u006a\u0052\u0057\u0065\u0041",
    ],
)
def test_relationship_pre_scope_signature_diagnostic_never_echoes_excluded_spellings(
    tmp_path, capsys, token
):
    private = int(UUID("a1b2c3d4-e5f6-4a78-9abc-def012345678"))
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Entry", 2: "Child", private: "Private"},
        [(1, 2, 1, 1, 3)],
    )
    edit_rows(
        source,
        "thoughts.json",
        lambda rows: rows[2].update(ForgottenDateTime="2020-01-01"),
    )
    edit_rows(
        source,
        "links.json",
        lambda rows: rows[0].update(Direction=token, BrainId=identity(900)),
    )
    before = source.read_bytes()
    for result in (
        default_workflow().inspect(source),
        default_workflow().convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused"
        assert result.issues[0].affected == result.issues[0].evidence == ()
        for secret in (token, identity(private), "1MOyofbleEqavN7wEjRWeA"):
            assert secret not in result.model_dump_json()
    for flags in ([], ["--json"]):
        assert main(["inspect", str(source), *flags]) == 1
        output = capsys.readouterr().out
        for secret in (token, identity(private), "1MOyofbleEqavN7wEjRWeA"):
            assert secret not in output
    assert source.read_bytes() == before
    assert not (tmp_path / "vault").exists()


def test_category_jump_keeps_empty_ordinary_endpoint_uncreated(tmp_path):
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Entry", 2: "Empty", 3: "Concept"},
        [(2, 3, 3, 1, -1)],
        kinds={3: 2},
    )
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    targets = {t.item_key: t for t in inspected.inspection.item_targets}
    assert not targets[identity(2)].created
    assert targets[identity(3)].created
    assert inspected.counts.classification_assignments == 0
    vault = tmp_path / "vault"
    assert operation.convert(source, vault).outcome == "clean"
    assert not (vault / "Notes/Empty.md").exists()
    assert note_body((vault / "Categories/Concept.md").read_bytes()) == (
        b"# Concept\n\n## Members\n\n![[Templates/Bases/Members.base#Members]]\n\n"
        b"## Gallery\n\n![[Templates/Bases/Gallery.base#Gallery]]\n\n"
        b"## Related\n\n- [[Notes/Empty.md|Empty]]\n"
    )


@pytest.mark.parametrize("duplicate_identity", [False, True])
def test_relationship_identity_is_not_merged_or_fabricated(
    tmp_path, duplicate_identity
):
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Entry", 2: "Concept"},
        [(1, 2, 3, 1, -1)],
        kinds={2: 2},
    )
    edit_rows(
        source,
        "links.json",
        lambda rows: rows.append(
            {**rows[0], "Id": identity(1000 if duplicate_identity else 1001)}
        ),
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    if duplicate_identity:
        assert result.outcome == "refused"
        assert result.issues[0].code == "invalid_source"
        assert set(result.issues[0].affected) == {
            identity(1000),
            identity(1),
            identity(2),
        }
        assert "links.json:1" in result.issues[0].evidence
        assert not vault.exists()
    else:
        assert result.outcome == "clean", result.issues
        assert result.counts.source_relationships == 2
        record = json.loads((vault / "migration-record.json").read_bytes())
        assert [r["key"] for r in record["relationships"]] == [
            identity(1000),
            identity(1001),
        ]
        assert (vault / "Home — Entry.md").read_bytes().count(
            b"- [[Categories/Concept.md|Concept]]"
        ) == 1
        assert (vault / "Categories/Concept.md").read_bytes().count(
            "- [[Home — Entry.md|Entry]]".encode()
        ) == 1


@pytest.mark.parametrize(
    "association", ["included_array", "excluded_array", "excluded_serialized"]
)
@pytest.mark.parametrize("foreign", [False, True])
def test_relationship_opaque_association_lists_keep_existing_scope_and_diagnostics(
    tmp_path, association, foreign
):
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Entry", 2: "Child", 3: "Private"},
        [(1, 2, 1, 1, 3)],
    )
    edit_rows(
        source,
        "thoughts.json",
        lambda rows: rows[2].update(ForgottenDateTime="2020-01-01"),
    )
    associated_id = identity(1) if association == "included_array" else identity(3)
    value = (
        [associated_id]
        if association != "excluded_serialized"
        else json.dumps([associated_id])
    )
    edit_rows(
        source,
        "links.json",
        lambda rows: rows[0].update(
            SourceId=value, BrainId=identity(900) if foreign else rows[0]["BrainId"]
        ),
    )
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == ("refused" if foreign else "clean"), result.issues
    if foreign:
        issue = result.issues[0]
        if association == "included_array":
            assert set(issue.affected) == {identity(1000), identity(1), identity(2)}
            assert "links.json:0" in issue.evidence
        else:
            assert issue.affected == issue.evidence == ()
        assert not (tmp_path / "vault").exists()
    else:
        record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
        assert len(record["relationships"]) == (
            1 if association == "included_array" else 0
        )
        assert identity(3) not in json.dumps(record)


def test_reverse_arrow_hierarchy_keeps_parent_a_child_b_and_raw_evidence(
    tmp_path, capsys
):
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Entry", 2: "Child"},
        [(1, 2, 1, 1, 3)],
        notes={2: (b"Child source.\n", 4)},
    )
    before = source.read_bytes()
    with ZipFile(source) as archive:
        raw_link = json.loads(archive.read("links.json"))
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    assert inspected.receipt is None
    assert inspected.counts.source_relationships == 1
    assert inspected.counts.classification_assignments == 0
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "clean", result.issues
    assert note_body((vault / "Home — Entry.md").read_bytes()) == (
        b"# Entry\n\n## Children\n\n- [[Notes/Child.md|Child]]\n\n"
        b"## Categories\n\n[[Categories.md|Browse categories]]\n"
    )
    assert note_body((vault / "Notes/Child.md").read_bytes()) == (
        "# Child\n\nChild source.\n\n## Parents\n\n- [[Home — Entry.md|Entry]]\n".encode()
    )
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert record["relationships"] == [
        {
            "key": identity(1000),
            "kind": "hierarchy",
            "item_a": identity(1),
            "item_b": identity(2),
            "evidence": ["links.json:0"],
            "target_a": "Home — Entry.md",
            "target_b": "Notes/Child.md",
            "presentation": "Parents/Children",
        }
    ]
    evidence = next(e for e in record["original_evidence"] if e["key"] == "links.json")
    assert evidence["records"] == [raw_link]
    assert raw_link["Direction"] == 3
    assert main(["inspect", str(source), "--json"]) == 0
    cli = json.loads(capsys.readouterr().out)
    assert cli["counts"]["source_relationships"] == 1
    assert cli["receipt"] is None
    cli_vault = tmp_path / "cli-vault"
    assert main(["convert", str(source), str(cli_vault), "--json"]) == 0
    cli_result = json.loads(capsys.readouterr().out)
    assert cli_result["outcome"] == "clean"
    assert (cli_vault / "Home — Entry.md").read_bytes() == (
        vault / "Home — Entry.md"
    ).read_bytes()
    assert (cli_vault / "Notes/Child.md").read_bytes() == (
        vault / "Notes/Child.md"
    ).read_bytes()
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "shape,field,value,roles",
    [
        *(("hierarchy", "Direction", value, (1, 1)) for value in (0, 2, 4, 5, 6, 8)),
        *(("hierarchy", "Relation", value, (1, 1)) for value in (0, 2, 4)),
        *(("hierarchy", "Meaning", value, (1, 1)) for value in (0, 2, 5, 6)),
        *(("hierarchy", "Kind", value, (1, 1)) for value in (0, 2)),
        *(
            ("hierarchy", "Direction", 3, roles)
            for roles in ((1, 2), (2, 1), (1, 4), (1, 5))
        ),
        *(("jump", "Direction", value, (1, 2)) for value in (0, 1, 3, 5, 7)),
        *(("jump", "Relation", value, (1, 2)) for value in (0, 2, 4)),
        *(("jump", "Meaning", value, (1, 2)) for value in (0, 2, 5, 6)),
        *(("jump", "Kind", value, (1, 2)) for value in (0, 2)),
        *(
            ("jump", "Direction", -1, roles)
            for roles in ((2, 1), (1, 4), (1, 5), (2, 2))
        ),
        *(
            (shape, field, value, roles)
            for shape, roles in [("hierarchy", (1, 1)), ("jump", (1, 2))]
            for field in ("Kind", "Relation", "Meaning", "Direction")
            for value in (True, 1.0, "1", None)
        ),
        *(
            (shape, field, value, roles)
            for shape, roles in [("hierarchy", (1, 1)), ("jump", (1, 2))]
            for field, value in [
                ("TypeId", identity(800)),
                ("LinkTypeId", identity(801)),
                ("IsCustom", True),
                ("IsCustom", 1),
                ("LinkTypeId", False),
            ]
        ),
    ],
)
def test_only_exact_new_signatures_and_roles_admit(
    tmp_path, shape, field, value, roles
):
    edges = [(2, 3, 1, 1, 3)] if shape == "hierarchy" else [(2, 3, 3, 1, -1)]
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Entry", 2: "A", 3: "B"},
        edges,
        kinds={2: roles[0], 3: roles[1]},
    )
    edit_rows(source, "links.json", lambda rows: rows[0].update({field: value}))
    before = source.read_bytes()
    operation = default_workflow()
    vault = tmp_path / "vault"
    for result in (operation.inspect(source), operation.convert(source, vault)):
        assert result.outcome == "refused", (shape, field, value, roles, result.issues)
        assert result.counts is None or result.counts.actual_files is None
        assert "Home" not in result.issues[0].guidance
    assert not vault.exists()
    assert source.read_bytes() == before


@pytest.mark.parametrize("shape", ["hierarchy", "jump"])
@pytest.mark.parametrize("foreign", [False, True])
@pytest.mark.parametrize("transitive", [False, True])
def test_excluded_relationships_do_not_leak_inclusion_diagnostics_or_records(
    tmp_path, capsys, shape, foreign, transitive
):
    edges = [(1, 2, 1, 1, 3)] if shape == "hierarchy" else [(1, 2, 3, 1, -1)]
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Entry", 2: "Private endpoint", 3: "Included"},
        edges,
        kinds={2: 1 if shape == "hierarchy" else 2},
    )
    edit_rows(
        source,
        "thoughts.json",
        lambda rows: rows[1].update(ForgottenDateTime="2020-01-01"),
    )
    if transitive:
        # Valid endpoints alone do not make an associated excluded relation public.
        edit_rows(
            source,
            "links.json",
            lambda rows: rows[0].update(ThoughtIdB=identity(3), ObjectId=identity(2)),
        )
    if foreign:
        edit_rows(
            source, "links.json", lambda rows: rows[0].update(BrainId=identity(900))
        )
    before = source.read_bytes()
    operation = default_workflow()
    vault = tmp_path / "vault"
    result = operation.convert(source, vault)
    assert result.outcome == ("refused" if foreign else "clean"), result.issues
    serialized = result.model_dump_json()
    if foreign:
        assert result.issues[0].affected == ()
        assert result.issues[0].evidence == ()
        assert not vault.exists()
    else:
        record = json.loads((vault / "migration-record.json").read_bytes())
        assert record["relationships"] == []
        assert record["classification_assignments"] == []
        serialized += "".join(
            p.read_text(encoding="utf-8") for p in vault.rglob("*") if p.is_file()
        )
    for secret in (identity(2), identity(1000), "Private endpoint"):
        assert secret not in serialized
    for flags in ([], ["--json"]):
        assert main(["inspect", str(source), *flags]) == (1 if foreign else 0)
        output = capsys.readouterr().out
        for secret in (identity(2), identity(1000), "Private endpoint"):
            assert secret not in output
    assert source.read_bytes() == before


def test_normal_jump_does_not_satisfy_or_replace_explicit_instance_assignment(tmp_path):
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Entry", 2: "Concept"},
        [(1, 2, 3, 1, -1)],
        kinds={2: 2},
    )
    edit_rows(source, "thoughts.json", lambda rows: rows[0].update(TypeId=identity(2)))
    operation = default_workflow()
    assert operation.inspect(source).outcome == "refused"
    assert operation.convert(source, tmp_path / "invalid").outcome == "refused"
    assert not (tmp_path / "invalid").exists()
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
    result = operation.convert(source, vault)
    assert result.outcome == "clean", result.issues
    assert result.counts.source_relationships == 2
    assert result.counts.classification_assignments == result.counts.typed_members == 1
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert [(r["key"], r["kind"]) for r in record["relationships"]] == [
        (identity(1000), "related"),
        (identity(1001), "classification"),
    ]
    assert record["classification_assignments"] == [
        {
            "relationship_key": identity(1001),
            "definition_key": identity(2),
            "item_key": identity(1),
            "evidence": ["thoughts.json:0", "links.json:1"],
            "definition_target": "Categories/Concept.md",
            "item_target": "Home — Entry.md",
        }
    ]
    assert b"## Related" in (vault / "Home — Entry.md").read_bytes()
    assert b"## Related" in (vault / "Categories/Concept.md").read_bytes()


@pytest.mark.parametrize(
    "patch",
    [
        {"Direction": 0},
        {"Meaning": True},
        {"Direction": "3"},
        {"TypeId": identity(900)},
        {"BrainId": identity(901)},
        {"ThoughtIdB": identity(902)},
    ],
)
def test_included_relationship_refusal_has_identity_endpoints_and_evidence(
    tmp_path, capsys, patch
):
    source = graph_archive(
        tmp_path / "source.brz", {1: "Entry", 2: "Child"}, [(1, 2, 1, 1, 3)]
    )
    with ZipFile(source) as archive:
        link = json.loads(archive.read("links.json"))
    link.update(patch)
    rewrite(source, "links.json", json.dumps(link).encode())
    before = source.read_bytes()
    workflow = default_workflow()
    vault = tmp_path / "vault"
    for result in (workflow.inspect(source), workflow.convert(source, vault)):
        assert result.outcome == "refused"
        issue = result.issues[0]
        assert set(issue.affected) == {
            link["Id"],
            link["ThoughtIdA"],
            link["ThoughtIdB"],
        }
        assert "links.json:0" in issue.evidence
        assert "relationship" in issue.guidance.lower()
        assert "Home" not in issue.guidance
    assert not vault.exists()
    for command in (["inspect", str(source)], ["convert", str(source), str(vault)]):
        for flags in ([], ["--json"]):
            assert main([*command, *flags]) == 1
            output = capsys.readouterr().out
            assert "links.json:0" in output
            assert link["Id"] in output
            assert link["ThoughtIdA"] in output
            assert link["ThoughtIdB"] in output
            assert "Home" not in output
    assert source.read_bytes() == before
    assert not vault.exists()


def test_ordinary_to_definition_jump_is_reciprocal_related_without_membership(
    tmp_path, capsys
):
    authored = b"Category source.\r\n"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Entry", 2: "Concept"},
        [(1, 2, 3, 1, -1)],
        kinds={2: 2},
        notes={2: (authored, 4)},
    )
    before = source.read_bytes()
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    assert inspected.counts.source_relationships == 1
    assert inspected.counts.classification_assignments == 0
    assert inspected.counts.typed_members == 0
    assert inspected.inspection.classification_assignments == ()
    vault = tmp_path / "vault"
    converted = operation.convert(source, vault)
    assert converted.outcome == "clean", converted.issues
    assert note_body((vault / "Home — Entry.md").read_bytes()) == (
        b"# Entry\n\n## Related\n\n- [[Categories/Concept.md|Concept]]\n\n"
        b"## Categories\n\n[[Categories.md|Browse categories]]\n"
    )
    assert (
        note_body((vault / "Categories/Concept.md").read_bytes())
        == (
            "# Concept\n\n## Members\n\n![[Templates/Bases/Members.base#Members]]\n\n"
            "## Gallery\n\n![[Templates/Bases/Gallery.base#Gallery]]\n\n"
            "Category source.\r\n\n## Related\n\n- [[Home — Entry.md|Entry]]\n"
        ).encode()
    )
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert record["classification_assignments"] == []
    assert record["relationships"] == [
        {
            "key": identity(1000),
            "kind": "related",
            "item_a": identity(1),
            "item_b": identity(2),
            "evidence": ["links.json:0"],
            "target_a": "Home — Entry.md",
            "target_b": "Categories/Concept.md",
            "presentation": "Related",
        }
    ]
    raw = next(e for e in record["original_evidence"] if e["key"] == "links.json")
    with ZipFile(source) as archive:
        assert raw["records"] == [json.loads(archive.read("links.json"))]
    assert raw["records"][0]["Direction"] == -1
    original = next(a for a in record["asset_targets"] if a["role"] == "note_original")
    assert original["owner"] == identity(2)
    assert (vault / original["relative_path"]).read_bytes() == authored
    assert main(["inspect", str(source), "--json"]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["counts"]["classification_assignments"] == 0
    assert envelope["receipt"] is None
    cli_vault = tmp_path / "cli-vault"
    assert main(["convert", str(source), str(cli_vault), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["typed_members"] == 0
    for relative in ("Home — Entry.md", "Categories/Concept.md"):
        assert (cli_vault / relative).read_bytes() == (vault / relative).read_bytes()
    assert source.read_bytes() == before
