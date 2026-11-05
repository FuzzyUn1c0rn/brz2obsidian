"""Type/tag qualification through public inspection and complete publication."""

import hashlib
import json
from contextlib import nullcontext
from zipfile import ZipFile

import pytest

from brz2obsidian.application.diagnostics import finding_for
from brz2obsidian.application.wiring import default_workflow, local_api_workflow
from brz2obsidian.sources.thebrain.local_api import LocalApiConfig, LocalApiSourceRef
from tests.support.local_api import BRAIN, KEY, api_server
from tests.support.type_tag_sources import (
    DIRECT,
    EDGES,
    ICON,
    IDS,
    NAVIGATION,
    PNG,
    TYPE_FIELDS,
    TypeTagApi,
    brz_source,
)


def source_transport(adapter, api=None, **values):
    if adapter == "brz":
        return nullcontext((None, None))
    return api_server(api or TypeTagApi(**values))


@pytest.mark.parametrize("adapter", ["brz", "api"])
def test_paired_direct_type_tag_facts_inspect_and_convert(tmp_path, adapter):
    with source_transport(adapter) as (_, address):
        workflow = (
            default_workflow()
            if adapter == "brz"
            else local_api_workflow(
                LocalApiConfig(api_url=address), credentials=lambda: KEY
            )
        )
        source = (
            brz_source(tmp_path / "source.brz")
            if adapter == "brz"
            else LocalApiSourceRef(BRAIN)
        )
        result = workflow.inspect(source)
        assert result.outcome == "clean", result.issues
        assert result.counts.source_definitions == 4
        assert result.counts.classification_assignments == 6
        assert result.counts.typed_members == 6
        names = {value: key for key, value in IDS.items()}
        assert {
            (names[a.definition_key], names[a.item_key])
            for a in result.inspection.classification_assignments
        } == DIRECT
        assert {
            (names[t.tag_key], names[t.item_key])
            for t in result.inspection.tag_memberships
        } == {("T", "B"), ("U", "T")}
        destination = tmp_path / "vault"
        converted = workflow.convert(source, destination)
        assert converted.outcome == "clean", converted.issues
        record = json.loads((destination / "migration-record.json").read_bytes())
        targets = {t["item_key"]: t for t in record["item_targets"]}
        assert sum(t["created"] for t in record["item_targets"]) == 8
        assert {targets[IDS[n]]["relative_path"] for n in "ABCDEFG"} == {
            "Categories/A.md",
            "Categories/B.md",
            "Categories/C.md",
            "Categories/E.md",
            "Notes/D.md",
            "Notes/F.md",
            "Notes/G.md",
        }
        names.update(
            {t["item_key"]: t["original_title"] for t in record["item_targets"]}
        )
        assert {
            (r["kind"], names[r["item_a"]], names[r["item_b"]])
            for r in record["relationships"]
            if r["kind"] in {"hierarchy", "related"}
        } == NAVIGATION
        assert converted.counts.classification_assignments == 6
        assert result.counts.present_assets == 1
        assert [
            (a.asset_id, a.owner, a.role, a.actual_sha256)
            for a in result.inspection.assets
        ] == [(ICON, IDS["A"], "icon", hashlib.sha256(PNG).hexdigest())]
        assert len(record["asset_targets"]) == 1
        assert (
            destination / record["asset_targets"][0]["relative_path"]
        ).read_bytes() == PNG
        evidence = {
            e["key"]: e["records"]
            for e in record["original_evidence"]
            if e["kind"] == "records"
        }
        if adapter == "brz":
            assert [
                (r["item_a"], r["item_b"])
                for r in record["relationships"]
                if r["kind"] == "system"
            ] == [
                (
                    "00000000-0000-0000-0000-000000000002",
                    "00000000-0000-0000-0000-000000000001",
                )
            ]
            a = next(v for v in evidence["thoughts.json"] if v["Id"] == IDS["A"])
            b = next(v for v in evidence["thoughts.json"] if v["Id"] == IDS["B"])
            assert "TypeId" not in a and b["TypeId"] == IDS["A"]
            assert (
                evidence["links.json"][0]["Kind"],
                evidence["links.json"][0]["Relation"],
                evidence["links.json"][0]["Meaning"],
                evidence["links.json"][0]["Direction"],
            ) == (1, 1, 3, -1)
        else:
            assert evidence["thought:" + IDS["A"]]["typeId"] is None
            assert evidence["thought:" + IDS["B"]]["typeId"] == IDS["A"]
            edge = evidence[
                "link:"
                + next(
                    r["key"]
                    for r in record["relationships"]
                    if r["item_a"] == IDS["A"] and r["item_b"] == IDS["B"]
                )
            ]
            assert (
                edge["kind"],
                edge["relation"],
                edge["meaning"],
                edge["direction"],
            ) == (1, 1, 3, -1)


@pytest.mark.parametrize("adapter", ["brz", "api"])
@pytest.mark.parametrize("self_assignment", [False, True])
def test_type_cycles_refuse_with_chain_and_subject_before_publication(
    tmp_path, adapter, self_assignment
):
    # B already has type A; making A's type B closes A -> B -> A.
    extra = (10, 10, 1, 3, -1) if self_assignment else (11, 10, 1, 3, -1)
    fields = TYPE_FIELDS | {10: 10 if self_assignment else 11}
    with source_transport(adapter, edges=(*EDGES, extra), type_fields=fields) as (
        _,
        address,
    ):
        workflow = (
            default_workflow()
            if adapter == "brz"
            else local_api_workflow(
                LocalApiConfig(api_url=address), credentials=lambda: KEY
            )
        )
        source = (
            brz_source(
                tmp_path / "source.brz", edges=(*EDGES, extra), type_fields=fields
            )
            if adapter == "brz"
            else LocalApiSourceRef(BRAIN)
        )
        destination = tmp_path / "vault"
        result = workflow.convert(source, destination)
        assert result.outcome == "refused", result.issues
        issue = result.issues[0]
        assert issue.code == "source_type_cycle"
        assert "A" in issue.message and (self_assignment or "B" in issue.message)
        assert issue.affected
        assert "00000000-0000-0000-0000-0000000003f5" in issue.affected
        assert issue.subject is not None
        finding = finding_for(issue, "convert")
        assert finding.code == "source_type_cycle"
        assert "cycle" in finding.message and "type" in finding.message
        assert not destination.exists()


@pytest.mark.parametrize("adapter", ["brz", "api"])
@pytest.mark.parametrize("self_tag", [False, True])
def test_unqualified_source_tag_cycle_remains_unsupported(tmp_path, adapter, self_tag):
    edges = (*EDGES, (17, 17 if self_tag else 18, 1, 7, -1))
    with source_transport(adapter, edges=edges) as (_, address):
        workflow = (
            default_workflow()
            if adapter == "brz"
            else local_api_workflow(
                LocalApiConfig(api_url=address), credentials=lambda: KEY
            )
        )
        source = (
            brz_source(tmp_path / "source.brz", edges=edges)
            if adapter == "brz"
            else LocalApiSourceRef(BRAIN)
        )
        destination = tmp_path / "vault"
        result = workflow.convert(source, destination)
        assert result.outcome == "refused", result.issues
        issue = result.issues[0]
        assert issue.code == (
            "unsupported_feature"
            if adapter == "brz"
            else "api_relationship_shape_unsupported"
        )
        assert issue.subject is not None
        assert not destination.exists()


def test_api_type_assignment_requires_observed_parent_projection(tmp_path):
    api = TypeTagApi()
    path = f"/api/thoughts/{BRAIN}/{IDS['B']}/graph"
    status, graph = api.response(path, {})
    assert status == 200
    graph["parents"] = [node for node in graph["parents"] if node["id"] != IDS["A"]]
    api.overrides[path] = (200, graph)
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "refused", result.issues
    assert result.issues[0].subject.name == "B"
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize("adapter", ["brz", "api"])
def test_deep_type_chain_counts_are_direct_and_navigation_cycles_remain_allowed(
    tmp_path, adapter
):
    with source_transport(adapter, deep=True) as (_, address):
        workflow = (
            default_workflow()
            if adapter == "brz"
            else local_api_workflow(
                LocalApiConfig(api_url=address), credentials=lambda: KEY
            )
        )
        source = (
            brz_source(tmp_path / "source.brz", deep=True)
            if adapter == "brz"
            else LocalApiSourceRef(BRAIN)
        )
        result = workflow.inspect(source)
    assert result.outcome == "clean", result.issues
    # Base has 13 links, deep direct assignments add 11, ordinary D -> F -> D
    # contributes two navigation links. BRZ additionally retains the system pin.
    assert result.counts.source_relationships == (27 if adapter == "brz" else 26)
    assert (
        result.counts.source_definitions,
        result.counts.classification_assignments,
        result.counts.typed_members,
    ) == (14, 17, 17)
    targets = result.inspection.item_targets
    selected = {
        t.original_title for t in targets if t.created and t.original_title != "Entry"
    }
    assert selected == set("ABCDEFG") | {f"H{i}" for i in range(10)} | {"N8", "N9"}
    assert len(selected) == 19
    assert sum(t.created for t in targets) == 20
    assert result.counts.present_assets == 2
    names = {t.item_key: t.original_title for t in targets}
    assert {
        (names[a.definition_key], names[a.item_key])
        for a in result.inspection.classification_assignments
        if names[a.item_key] in {"N8", "N9", "H9"}
    } == {("H7", "N8"), ("H8", "N9"), ("H8", "H9")}


@pytest.mark.parametrize("adapter", ["brz", "api"])
def test_source_type_cycle_beyond_native_icon_limit_refuses_whole_chain(
    tmp_path, adapter
):
    # H0's provider H9 closes all ten type definitions into a source cycle.
    fields = TYPE_FIELDS | {30: 39}
    edges = (*EDGES, (39, 30, 1, 3, -1))
    with source_transport(adapter, edges=edges, type_fields=fields, deep=True) as (
        _,
        address,
    ):
        workflow = (
            default_workflow()
            if adapter == "brz"
            else local_api_workflow(
                LocalApiConfig(api_url=address), credentials=lambda: KEY
            )
        )
        source = (
            brz_source(
                tmp_path / "source.brz", edges=edges, type_fields=fields, deep=True
            )
            if adapter == "brz"
            else LocalApiSourceRef(BRAIN)
        )
        result = workflow.convert(source, tmp_path / "vault")
    assert result.outcome == "refused", result.issues
    issue = result.issues[0]
    assert issue.code == "source_type_cycle"
    assert all(f"H{i}" in issue.message for i in range(10))
    assert len(issue.affected) == 20  # Ten distinct items and ten relationships.
    assert issue.subject is not None and issue.evidence
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize("adapter", ["brz", "api"])
@pytest.mark.parametrize(
    "extra", [(10, 12, 1, 1, -1), (10, 12, 3, 1, 3), (17, 13, 3, 1, -1)]
)
def test_unobserved_navigation_endpoint_signatures_remain_unsupported(
    tmp_path, adapter, extra
):
    edges = (*EDGES, extra)
    with source_transport(adapter, edges=edges) as (_, address):
        workflow = (
            default_workflow()
            if adapter == "brz"
            else local_api_workflow(
                LocalApiConfig(api_url=address), credentials=lambda: KEY
            )
        )
        source = (
            brz_source(tmp_path / "source.brz", edges=edges)
            if adapter == "brz"
            else LocalApiSourceRef(BRAIN)
        )
        result = workflow.convert(source, tmp_path / "vault")
    assert result.outcome == "refused", result.issues
    assert result.issues[0].code == (
        "unsupported_feature"
        if adapter == "brz"
        else "api_relationship_shape_unsupported"
    )
    assert result.issues[0].subject is not None
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize("adapter", ["brz", "api"])
@pytest.mark.parametrize(
    "defect",
    [
        "wrong_provider",
        "missing_assignment",
        "missing_type_field",
        "duplicate_assignment",
        "dangling_provider",
        "foreign_link",
        "custom_link",
        "missing_direction",
        "boolean_direction",
        "typed_tag",
    ],
)
def test_malformed_type_joins_and_link_declarations_refuse_before_publication(
    tmp_path, adapter, defect
):
    fields, edges = dict(TYPE_FIELDS), EDGES
    if defect in {"wrong_provider", "dangling_provider"}:
        fields[11] = 12 if defect == "wrong_provider" else 99
    if defect == "missing_assignment":
        edges = EDGES[1:]
    if defect == "missing_type_field":
        fields.pop(11)
    if defect == "duplicate_assignment":
        edges = (*EDGES, EDGES[0])
    if defect == "typed_tag":
        edges, fields = (*EDGES, (10, 17, 1, 3, -1)), fields | {17: 10}
    api = TypeTagApi(edges=edges, type_fields=fields)
    changes = {
        "foreign_link": {"brainId": "99999999-9999-4999-8999-999999999999"},
        "custom_link": {"typeId": IDS["C"]},
        "boolean_direction": {"direction": True},
    }
    first = next(iter(api.links.values()))
    first.update(changes.get(defect, {}))
    if defect == "missing_direction":
        first.pop("direction")
    source = brz_source(tmp_path / "source.brz", edges=edges, type_fields=fields)
    if defect in changes or defect == "missing_direction":
        with ZipFile(source) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        links = [json.loads(line) for line in parts["links.json"].splitlines()]
        links[0].update(
            {
                {"brainId": "BrainId", "typeId": "TypeId", "direction": "Direction"}[
                    key
                ]: value
                for key, value in changes.get(defect, {}).items()
            }
        )
        if defect == "missing_direction":
            links[0].pop("Direction")
        parts["links.json"] = b"\n".join(json.dumps(link).encode() for link in links)
        with ZipFile(source, "w") as archive:
            for name, raw in parts.items():
                archive.writestr(name, raw)
    with source_transport(adapter, api=api) as (_, address):
        workflow = (
            default_workflow()
            if adapter == "brz"
            else local_api_workflow(
                LocalApiConfig(api_url=address), credentials=lambda: KEY
            )
        )
        result = workflow.convert(
            source if adapter == "brz" else LocalApiSourceRef(BRAIN), tmp_path / "vault"
        )
    assert result.outcome == "refused", result.issues
    issue = result.issues[0]
    expected = (
        {
            "wrong_provider": "invalid_reference",
            "missing_assignment": "invalid_reference",
            "missing_type_field": "invalid_reference",
            "duplicate_assignment": "invalid_reference",
            "dangling_provider": "invalid_reference",
            "foreign_link": "invalid_source",
            "custom_link": "unsupported_feature",
            "missing_direction": "unsupported_feature",
            "boolean_direction": "unsupported_feature",
            "typed_tag": "unsupported_feature",
        }
        if adapter == "brz"
        else {
            "wrong_provider": "invalid_source",
            "missing_assignment": "invalid_source",
            "missing_type_field": "invalid_source",
            "duplicate_assignment": "invalid_source",
            "dangling_provider": "invalid_source",
            "foreign_link": "invalid_source",
            "custom_link": "api_relationship_shape_unsupported",
            "missing_direction": "invalid_source",
            "boolean_direction": "invalid_source",
            "typed_tag": "invalid_source",
        }
    )
    assert issue.code == expected[defect], issue
    if defect == "foreign_link" and adapter == "brz":
        assert issue.subject is None and issue.affected and issue.evidence
    else:
        assert issue.subject is not None, issue
    if defect in {
        "wrong_provider",
        "missing_assignment",
        "missing_type_field",
        "duplicate_assignment",
        "dangling_provider",
    }:
        assert ("TypeId" if adapter == "brz" else "Type field") in issue.message
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize(
    "defect", ["missing_endpoint_link", "unexplained_parent", "missing_nested_parent"]
)
def test_api_graph_inventories_and_adjacency_must_be_completely_explained(
    tmp_path, defect
):
    api = TypeTagApi()
    key = (
        IDS["A"]
        if defect == "missing_endpoint_link"
        else IDS["B"]
        if defect == "unexplained_parent"
        else IDS["T"]
    )
    path = f"/api/thoughts/{BRAIN}/{key}/graph"
    _, graph = api.response(path, {})
    if defect == "missing_endpoint_link":
        graph["links"] = [
            value
            for value in graph["links"]
            if not (value["thoughtIdA"] == IDS["A"] and value["thoughtIdB"] == IDS["B"])
        ]
    elif defect == "unexplained_parent":
        graph["parents"].append(api.thoughts[IDS["E"]])
    else:
        graph["parents"] = []
    api.overrides[path] = (200, graph)
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "refused", result.issues
    assert result.issues[0].code == "invalid_source"
    assert result.issues[0].subject is not None
    assert (
        "endpoint graph" if defect == "missing_endpoint_link" else "Graph adjacency"
    ) in result.issues[0].message
    assert not (tmp_path / "vault").exists()


def test_forgotten_type_with_dangling_provider_refuses_without_omitted_context(
    tmp_path,
):
    source = brz_source(tmp_path / "source.brz", type_fields=TYPE_FIELDS | {11: 99})
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    forgotten = next(value for value in thoughts if value["Id"] == IDS["B"])
    forgotten.update(
        Name="FORGOTTEN_TYPE_CANARY", ForgottenDateTime="2026-10-14T10:00:00"
    )
    parts["thoughts.json"] = b"\n".join(
        json.dumps(value).encode() for value in thoughts
    )
    with ZipFile(source, "w") as archive:
        for name, raw in parts.items():
            archive.writestr(name, raw)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "refused", result.issues
    issue = result.issues[0]
    assert issue.code == "invalid_reference"
    assert "provider is not live" in issue.message
    assert issue.affected == () and issue.evidence == () and issue.subject is None
    assert IDS["B"] not in result.model_dump_json()
    assert "FORGOTTEN_TYPE_CANARY" not in result.model_dump_json()
    assert not (tmp_path / "vault").exists()
