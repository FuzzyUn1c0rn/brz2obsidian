import copy
import json
import tempfile

import pytest

from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, api_server, thought
from tests.support.local_api_graph import HIERARCHY, GraphApi, link

SIBLING = "44444444-4444-4444-8444-444444444444"
OTHER_LINK = "55555555-5555-4555-8555-555555555555"


def test_forgotten_population_does_not_invent_included_link_count_equation(tmp_path):
    api = GraphApi()
    path = f"/api/brains/{BRAIN}/statistics"
    stats = api.response(path, {})[1] | {"forgottenThoughts": 1, "links": 7}
    api.overrides[path] = 200, stats
    with api_server(api) as (_, address):
        converted = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert converted.outcome == "clean"
    assert converted.receipt.verified
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert {row["item_key"] for row in record["item_targets"]} == {HOME, ALONE}
    assert {
        (row["key"], row["kind"], row["item_a"], row["item_b"])
        for row in record["relationships"]
    } == {(HIERARCHY, "hierarchy", HOME, ALONE)}
    originals = {row["key"]: row["records"] for row in record["original_evidence"]}
    assert (
        originals["statistics:start"]
        == originals["statistics:end"]
        == {
            "thoughts": 2,
            "thoughtTypes": 0,
            "tags": 0,
            "forgottenThoughts": 1,
            "links": 7,
        }
    )
    assert not any(key.startswith("exclusion:") for key in originals)


@pytest.mark.parametrize(
    "damage",
    [
        "missing_join",
        "missing_endpoint_link",
        "counter_drift",
        "forgotten_drift",
        "zero_forgotten",
        "wrong_ordinary_count",
        "wrong_type_count",
        "wrong_tag_count",
        "wrong_type_field",
        "missing_authoritative_link",
        "boolean_forgotten",
        "boolean_links",
        "missing_counter",
        "foreign_statistics",
        "forgotten_exceeds_report",
    ],
)
def test_forgotten_population_does_not_excuse_incomplete_facts_or_counters(
    tmp_path, damage
):
    if damage == "wrong_type_field":
        from tests.support.local_api_graph import CompleteGraphApi

        api = CompleteGraphApi()
        api.thoughts[HOME]["typeId"] = None
    else:
        api = GraphApi()
    path = f"/api/brains/{BRAIN}/statistics"
    stats = api.response(path, {})[1] | {"forgottenThoughts": 1, "links": 7}
    if damage in {"missing_join", "missing_endpoint_link"}:
        graph_path = f"/api/thoughts/{BRAIN}/{ALONE}/graph"
        graph = api.response(graph_path, {})[1]
        graph["parents" if damage == "missing_join" else "links"] = []
        api.overrides[graph_path] = 200, graph
    elif damage == "zero_forgotten":
        stats["forgottenThoughts"] = 0
    elif damage == "wrong_ordinary_count":
        stats["thoughts"] = 3
    elif damage in {"wrong_type_count", "wrong_tag_count"}:
        stats["thoughtTypes" if damage == "wrong_type_count" else "tags"] = 1
    elif damage == "missing_authoritative_link":
        api.overrides[f"/api/links/{BRAIN}/{HIERARCHY}"] = 404, b"not found"
    elif damage == "boolean_forgotten":
        stats["forgottenThoughts"] = True
    elif damage == "boolean_links":
        stats["links"] = True
    elif damage == "missing_counter":
        del stats["links"]
    elif damage == "foreign_statistics":
        stats["brainId"] = SIBLING
    elif damage == "forgotten_exceeds_report":
        api.thoughts[ALONE]["forgottenDateTime"] = "2026-01-01T00:00:00"
        stats.update(thoughts=1, forgottenThoughts=0)
    if damage in {"counter_drift", "forgotten_drift"}:
        readings = []

        def drifting(query):
            readings.append(True)
            field, first, second = (
                ("links", 7, 8)
                if damage == "counter_drift"
                else ("forgottenThoughts", 1, 2)
            )
            return 200, stats | {field: first if len(readings) == 1 else second}

        api.overrides[path] = drifting
    else:
        api.overrides[path] = 200, stats
    with api_server(api) as (_, address):
        converted = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert converted.outcome == (
        "failed" if damage == "missing_authoritative_link" else "refused"
    )
    if damage == "missing_authoritative_link":
        assert [issue.code for issue in converted.issues] == ["api_request_failed"]
    assert converted.receipt is None
    assert not (tmp_path / "vault").exists()


def test_type_provider_also_displayed_as_parent_keeps_only_actual_relationships(
    tmp_path,
):
    from tests.support.local_api_graph import (
        DEFINITION,
        EXPECTED_RELATIONSHIPS,
        TYPE_LINK,
        CompleteGraphApi,
    )

    api = CompleteGraphApi()
    api.links[HIERARCHY].update(thoughtIdA=ALONE, thoughtIdB=HOME)
    path = f"/api/thoughts/{BRAIN}/{HOME}/graph"
    graph = api.response(path, {})[1]
    graph["parents"].append(api.thoughts[DEFINITION])
    api.overrides[path] = 200, graph
    with api_server(api) as (_, address):
        converted = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert converted.outcome == "clean"
    assert converted.receipt.verified
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert {
        (row["key"], row["kind"], row["item_a"], row["item_b"])
        for row in record["relationships"]
    } == EXPECTED_RELATIONSHIPS - {(HIERARCHY, "hierarchy", HOME, ALONE)} | {
        (HIERARCHY, "hierarchy", ALONE, HOME)
    }
    assert [
        (row["relationship_key"], row["definition_key"], row["item_key"])
        for row in record["classification_assignments"]
    ] == [(TYPE_LINK, DEFINITION, HOME)]


@pytest.mark.parametrize(
    "damage",
    [
        "unassigned_definition",
        "tag_parent",
        "ordinary_parent",
        "missing_assignment",
        "wrong_type_field",
        "missing_type_graph",
        "missing_provider_child",
        "missing_endpoint_link",
    ],
)
def test_parent_overlap_requires_complete_exact_type_assignment(tmp_path, damage):
    from tests.support.local_api_graph import (
        DEFINITION,
        TAG,
        TYPE_LINK,
        CompleteGraphApi,
    )

    api = CompleteGraphApi()
    path = f"/api/thoughts/{BRAIN}/{HOME}/graph"
    graph = api.response(path, {})[1]
    graph["parents"].append(api.thoughts[DEFINITION])
    if damage == "unassigned_definition":
        api.thoughts[SIBLING] = thought(SIBLING, "Unassigned definition") | {"kind": 2}
        api.types.append(api.thoughts[SIBLING])
        graph["parents"].append(api.thoughts[SIBLING])
    elif damage in {"tag_parent", "ordinary_parent"}:
        graph["parents"].append(api.thoughts[TAG if damage == "tag_parent" else ALONE])
    elif damage == "missing_assignment":
        del api.links[TYPE_LINK]
        graph["links"] = [row for row in graph["links"] if row["id"] != TYPE_LINK]
    elif damage == "wrong_type_field":
        api.thoughts[HOME]["typeId"] = None
    elif damage == "missing_type_graph":
        graph["type"] = None
    elif damage == "missing_provider_child":
        provider_path = f"/api/thoughts/{BRAIN}/{DEFINITION}/graph"
        provider = api.response(provider_path, {})[1]
        provider["children"] = []
        api.overrides[provider_path] = 200, provider
    else:
        graph["links"] = [row for row in graph["links"] if row["id"] != TYPE_LINK]
    api.overrides[path] = 200, graph
    with api_server(api) as (_, address):
        converted = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert converted.outcome == "refused"
    assert converted.receipt is None
    assert not (tmp_path / "vault").exists()


def test_type_parent_overlap_is_retained_in_consistent_frozen_capture():
    from tests.support.local_api_graph import DEFINITION, TYPE_LINK, CompleteGraphApi

    api = CompleteGraphApi()
    api.links[HIERARCHY].update(thoughtIdA=ALONE, thoughtIdB=HOME)
    path = f"/api/thoughts/{BRAIN}/{HOME}/graph"
    graph = api.response(path, {})[1]
    graph["parents"].append(api.thoughts[DEFINITION])
    api.overrides[path] = 200, graph
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            originals = {
                row.key: json.loads(row.original_json)
                for row in session.snapshot.original_evidence
            }
            assert originals["graph:" + HOME]["parents_ids"] == [ALONE, DEFINITION]
            assert originals["graph:" + HOME]["type_ids"] == [DEFINITION]
            assert [
                (row.relationship_key, row.definition_key, row.item_key)
                for row in session.snapshot.classification_assignments
            ] == [(TYPE_LINK, DEFINITION, HOME)]
            session.verify_consistency()


def test_recomputed_capture_cannot_add_an_unexplained_type_parent(
    tmp_path, monkeypatch
):
    from tests.support.local_api_graph import DEFINITION, CompleteGraphApi

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with api_server(CompleteGraphApi()) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            identity = session.snapshot.identity.model_copy(
                update={"source_sha256": "", "snapshot_digest": ""}
            )
            clean_snapshot = session.snapshot.model_copy(update={"identity": identity})
            graph = next(
                row for row in source["records"] if row["key"] == "graph:" + ALONE
            )
            graph["value"]["parents_ids"].append(DEFINITION)
            changed = clean_snapshot.model_copy(
                update={
                    "original_evidence": tuple(
                        row.model_copy(
                            update={"original_json": json.dumps(graph["value"])}
                        )
                        if row.key == graph["key"]
                        else row
                        for row in clean_snapshot.original_evidence
                    )
                }
            )
            with pytest.raises(MigrationRefused):
                LocalApiSession(source=source, snapshot=changed, audit=audit)


class SiblingGraphApi(GraphApi):
    def __init__(self):
        super().__init__()
        self.thoughts[SIBLING] = thought(SIBLING, "Sibling")
        self.links[OTHER_LINK] = link(OTHER_LINK, HOME, SIBLING, direction=1)

    def response(self, path, query):
        if path in self.overrides:
            return super().response(path, query)
        status, value = super().response(path, query)
        if path == f"/api/thoughts/{BRAIN}/{ALONE}/graph" and status == 200:
            value["siblings"] = [self.thoughts[SIBLING]]
            value["links"].append(self.links[OTHER_LINK])
        if path == f"/api/thoughts/{BRAIN}/{SIBLING}/graph" and status == 200:
            value["siblings"] = [self.thoughts[ALONE]]
            if HIERARCHY in self.links:
                value["links"].append(self.links[HIERARCHY])
        return status, value


def test_displayed_parent_sibling_context_preserves_only_real_hierarchy(tmp_path):
    with api_server(SiblingGraphApi()) as (_, address):
        converted = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert converted.outcome == "clean"
    assert converted.receipt.verified
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert {row["item_key"] for row in record["item_targets"]} == {
        HOME,
        ALONE,
        SIBLING,
    }
    assert {
        (row["key"], row["kind"], row["item_a"], row["item_b"])
        for row in record["relationships"]
    } == {
        (HIERARCHY, "hierarchy", HOME, ALONE),
        (OTHER_LINK, "hierarchy", HOME, SIBLING),
    }


def test_context_order_and_duplicates_keep_identity_and_endpoint_only_projection():
    class Reordered(SiblingGraphApi):
        def response(self, path, query):
            status, value = super().response(path, query)
            value = copy.deepcopy(value)
            if path.endswith("/graph") and status == 200:
                value["links"].reverse()
                value["links"] += copy.deepcopy(value["links"])
            return status, value

    identities = []
    for api in (SiblingGraphApi(), Reordered()):
        with api_server(api) as (_, address):
            module = LocalApiSourceModule(
                LocalApiConfig(api_url=address), credentials=lambda: KEY
            )
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                originals = {
                    row.key: json.loads(row.original_json)
                    for row in session.snapshot.original_evidence
                }
                assert originals["graph:" + ALONE]["link_ids"] == [HIERARCHY]
                assert originals["graph:" + SIBLING]["link_ids"] == [OTHER_LINK]
                assert set(originals["graph:" + HOME]["link_ids"]) == {
                    HIERARCHY,
                    OTHER_LINK,
                }
                assert originals["graph:" + ALONE]["sibling_ids"] == [SIBLING]
                assert session.snapshot.classification_assignments == ()
                session.verify_consistency()
                identities.append(session.source_identity)
    assert identities[0] == identities[1]


@pytest.mark.parametrize(
    "damage",
    [
        "parent_not_displayed",
        "sibling_not_displayed",
        "other_displayed_arrays",
        "reversed",
        "classification",
        "jump",
        "direction",
        "boolean_kind",
        "custom_type",
        "foreign_brain",
        "zero_identity",
        "self_link",
        "conflicting_colour",
        "missing_parent_hierarchy",
        "endpoint_graph_missing_link",
        "authoritative_contradiction",
        "private_endpoint",
        "link_owned_content",
    ],
)
def test_unqualified_context_or_global_contradiction_prevents_publication(
    tmp_path, damage
):
    api = SiblingGraphApi()
    path = f"/api/thoughts/{BRAIN}/{ALONE}/graph"
    graph = copy.deepcopy(api.response(path, {})[1])
    context = next(row for row in graph["links"] if row["id"] == OTHER_LINK)
    if damage == "parent_not_displayed":
        graph["parents"] = []
    elif damage == "sibling_not_displayed":
        graph["siblings"] = []
    elif damage == "other_displayed_arrays":
        graph["children"], graph["parents"] = graph["parents"], []
        graph["jumps"], graph["siblings"] = graph["siblings"], []
    elif damage == "reversed":
        context["thoughtIdA"], context["thoughtIdB"] = SIBLING, HOME
    elif damage in {
        "classification",
        "jump",
        "direction",
        "boolean_kind",
        "custom_type",
    }:
        field, value = {
            "classification": ("meaning", 2),
            "jump": ("relation", 3),
            "direction": ("direction", 3),
            "boolean_kind": ("kind", True),
            "custom_type": ("typeId", SIBLING),
        }[damage]
        context[field] = value
    elif damage == "foreign_brain":
        context["brainId"] = "99999999-9999-4999-8999-999999999999"
    elif damage == "zero_identity":
        context["id"] = "00000000-0000-0000-0000-000000000000"
    elif damage == "self_link":
        context["thoughtIdB"] = HOME
        graph["siblings"] = [api.thoughts[HOME]]
    elif damage == "conflicting_colour":
        context["color"] = "#abcdef"
    elif damage == "missing_parent_hierarchy":
        del api.links[HIERARCHY]
        graph["links"] = [context]
    elif damage == "endpoint_graph_missing_link":
        sibling_path = f"/api/thoughts/{BRAIN}/{SIBLING}/graph"
        sibling = api.response(sibling_path, {})[1]
        sibling["links"] = [api.links[HIERARCHY]]
        api.overrides[sibling_path] = 200, sibling
    elif damage == "authoritative_contradiction":
        api.overrides[f"/api/links/{BRAIN}/{OTHER_LINK}"] = (
            200,
            api.links[OTHER_LINK] | {"direction": -1},
        )
    elif damage == "private_endpoint":
        api.thoughts[SIBLING] |= {"acType": 1, "name": "PRIVATE_CANARY"}
    else:
        api.overrides[f"/api/links/{BRAIN}/{OTHER_LINK}/attachments"] = (
            200,
            [{"name": "LINK_CONTENT_CANARY"}],
        )
    api.overrides[path] = 200, graph
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "refused"
    assert result.receipt is None
    assert not (tmp_path / "vault").exists()
    assert "CANARY" not in result.model_dump_json()


def test_recomputed_capture_cannot_assign_context_link_to_active_owner(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with api_server(SiblingGraphApi()) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            identity = session.snapshot.identity.model_copy(
                update={"source_sha256": "", "snapshot_digest": ""}
            )
            clean_snapshot = session.snapshot.model_copy(update={"identity": identity})
            clean = LocalApiSession(source=source, snapshot=clean_snapshot, audit=audit)
            clean.verify_consistency()
            clean.close()
            graph = next(
                row for row in source["records"] if row["key"] == "graph:" + ALONE
            )
            graph["value"]["link_ids"].append(OTHER_LINK)
            changed = clean_snapshot.model_copy(
                update={
                    "original_evidence": tuple(
                        row.model_copy(
                            update={"original_json": json.dumps(graph["value"])}
                        )
                        if row.key == graph["key"]
                        else row
                        for row in clean_snapshot.original_evidence
                    )
                }
            )
            with pytest.raises(MigrationRefused):
                LocalApiSession(source=source, snapshot=changed, audit=audit)


@pytest.mark.parametrize("excluded_kind", [1, 5])
def test_qualified_excluded_context_retains_only_minimal_scope(tmp_path, excluded_kind):
    api = SiblingGraphApi()
    api.thoughts[SIBLING] |= {
        "kind": excluded_kind,
        "name": "EXCLUDED_CONTENT_CANARY",
        "label": "EXCLUDED_CONTENT_CANARY",
        "aliases": ["EXCLUDED_CONTENT_CANARY"],
    }
    if excluded_kind == 1:
        api.thoughts[SIBLING]["forgottenDateTime"] = "2026-01-01T00:00:00"
    api.links[OTHER_LINK] |= {
        "meaning": 6,
        "name": "EXCLUDED_CONTENT_CANARY",
        "color": "EXCLUDED_CONTENT_CANARY",
    }
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "clean"
    assert result.receipt.verified
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert {row["item_key"] for row in record["item_targets"]} == {HOME, ALONE}
    assert [row["key"] for row in record["relationships"]] == [HIERARCHY]
    assert "EXCLUDED_CONTENT_CANARY" not in json.dumps(record)


@pytest.mark.parametrize(
    "contradiction", ["included", "not_displayed", "get_disagrees"]
)
def test_context_exclusion_requires_authoritative_scope_and_structural_roles(
    tmp_path, contradiction
):
    api = SiblingGraphApi()
    api.links[OTHER_LINK]["meaning"] = 6
    if contradiction != "included":
        api.thoughts[SIBLING]["forgottenDateTime"] = "2026-01-01T00:00:00"
    if contradiction == "not_displayed":
        path = f"/api/thoughts/{BRAIN}/{ALONE}/graph"
        graph = api.response(path, {})[1]
        graph["siblings"] = []
        api.overrides[path] = 200, graph
    elif contradiction == "get_disagrees":
        api.overrides[f"/api/thoughts/{BRAIN}/{SIBLING}"] = (
            200,
            api.thoughts[SIBLING] | {"forgottenDateTime": None},
        )
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "refused"
    assert result.receipt is None and not (tmp_path / "vault").exists()
