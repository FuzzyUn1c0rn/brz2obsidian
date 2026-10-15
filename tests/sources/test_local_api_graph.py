"""Reviewed API graph facts through public frozen sessions and actual output."""

import pytest

from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, api_server
from tests.support.local_api_graph import HIERARCHY, GraphApi


@pytest.mark.parametrize(
    "mutation", ["phantom_child", "phantom_tag", "missing_endpoint_link"]
)
def test_graph_adjacency_requires_complete_matching_authoritative_relationships(
    mutation,
):
    from tests.support.local_api import thought
    from tests.support.local_api_graph import PEER

    api = GraphApi()
    api.thoughts[PEER] = thought(PEER, "Other")
    api.search.append(
        {
            "brainId": BRAIN,
            "isFromOtherBrain": False,
            "sourceThought": {"id": PEER, "brainId": BRAIN, "kind": 0},
            "sourceLink": None,
        }
    )
    key = HOME
    graph = api.response(f"/api/thoughts/{BRAIN}/{key}/graph", {})[1]
    if mutation == "phantom_child":
        graph["children"].append(api.thoughts[PEER])
    elif mutation == "phantom_tag":
        graph["tags"].append(api.thoughts[PEER])
    else:
        graph["links"] = []
    api.overrides[f"/api/thoughts/{BRAIN}/{key}/graph"] = (200, graph)
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with pytest.raises(MigrationRefused), module.open(LocalApiSourceRef(BRAIN)):
            pytest.fail("Contradictory included graph must refuse")


@pytest.mark.parametrize("role", [1, 5])
def test_qualified_excluded_endpoint_retains_only_minimal_scope_and_no_authored_values(
    role,
):
    import json

    api = GraphApi()
    api.thoughts[ALONE].update(
        kind=role,
        name="EXCLUDED_CONTENT_CANARY",
        label="EXCLUDED_CONTENT_CANARY",
        aliases=["EXCLUDED_CONTENT_CANARY"],
        foregroundColor="EXCLUDED_CONTENT_CANARY",
    )
    if role == 1:
        api.thoughts[ALONE]["forgottenDateTime"] = "2026-01-01T00:00:00"
    # Meaning6 has no general semantic grant; a known excluded endpoint removes
    # its association before tuple/content interpretation (LA-C03/04).
    api.links[HIERARCHY].update(
        meaning=6, name="EXCLUDED_CONTENT_CANARY", color="EXCLUDED_CONTENT_CANARY"
    )
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            s = session.snapshot
            assert [i.key for i in s.items] == [HOME]
            assert s.relationships == ()
            assert "EXCLUDED_CONTENT_CANARY" not in s.model_dump_json()
            originals = {
                e.key: json.loads(e.original_json) for e in s.original_evidence
            }
            assert all(
                ALONE not in values and HIERARCHY not in values
                for values in originals["graph:" + HOME].values()
            )
            assert originals["exclusion:" + ALONE] == {
                "id": ALONE,
                "brainId": BRAIN,
                "kind": role,
                "acType": 0,
                "forgottenDateTime": "2026-01-01T00:00:00" if role == 1 else None,
            }
            assert any(
                v.get("outcome") == "excluded_association" for v in originals.values()
            )
            session.verify_consistency()


def test_complete_qualified_graph_keeps_every_direction_and_exact_classification():
    from tests.support.local_api_graph import (
        ARROW,
        CHILD,
        DEFINITION,
        FORWARD,
        JUMP,
        ONE_WAY_FORWARD,
        ONE_WAY_REVERSE,
        PEER,
        PLAIN,
        REVERSE,
        REVERSE_ARROW,
        TAG,
        TAG_LINK,
        TYPE_LINK,
        CompleteGraphApi,
    )

    with api_server(CompleteGraphApi()) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            s = session.snapshot
            assert {(r.key, r.kind, r.item_a, r.item_b) for r in s.relationships} == {
                (HIERARCHY, "hierarchy", HOME, ALONE),
                (ARROW, "hierarchy", HOME, CHILD),
                (JUMP, "related", HOME, PEER),
                (REVERSE_ARROW, "related", HOME, PLAIN),
                (ONE_WAY_FORWARD, "related", HOME, FORWARD),
                (ONE_WAY_REVERSE, "related", HOME, REVERSE),
                (TYPE_LINK, "classification", DEFINITION, HOME),
                (TAG_LINK, "tag", TAG, HOME),
            }
            assert [
                (a.relationship_key, a.definition_key, a.item_key)
                for a in s.classification_assignments
            ] == [(TYPE_LINK, DEFINITION, HOME)]
            assert {i.key: i.role for i in s.items}[TAG] == "tag"
            # Four jumps survive native one-way visibility simplification.
            import json

            originals = {
                e.key: json.loads(e.original_json) for e in s.original_evidence
            }
            assert [
                originals["link:" + k]["direction"]
                for k in (JUMP, REVERSE_ARROW, ONE_WAY_FORWARD, ONE_WAY_REVERSE)
            ] == [-1, 3, 5, 7]
            session.verify_consistency()


def test_qualified_hierarchy_preserves_parent_child_and_scoped_source_tuple():
    # local-api.relationships.v1 / LA-C05: A is parent, B is child.
    with api_server(GraphApi()) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            snapshot = session.snapshot
            assert [
                (r.key, r.kind, r.item_a, r.item_b) for r in snapshot.relationships
            ] == [(HIERARCHY, "hierarchy", HOME, ALONE)]
            assert any(e.key == "link:" + HIERARCHY for e in snapshot.original_evidence)
            session.verify_consistency()


@pytest.mark.parametrize(
    "change",
    [
        "custom_meaning",
        "custom_type",
        "unknown_direction",
        "boolean_direction",
        "foreign_link",
        "self_link",
        "missing_field",
        "link_conflict",
        "metadata_conflict",
        "missing_type_inventory",
        "missing_tag_inventory",
        "null_graph_type",
        "null_type_field",
        "wrong_type_field",
        "wrong_type_role",
        "duplicate_assignment",
        "missing_tag_join",
        "missing_type_children",
        "missing_jump_join",
        "private_endpoint",
        "unknown_role",
        "missing_endpoint",
        "bad_date",
        "bad_colour",
        "link_inventory_null",
        "link_inventory_populated",
        "link_inventory_failed",
        "explicit_icon",
        "inherited_icon",
        "graph_icon_only",
    ],
)
def test_unqualified_or_incomplete_graph_content_refuses_without_publishing(
    tmp_path, change
):
    from brz2obsidian.application.wiring import local_api_workflow
    from tests.support.local_api_graph import (
        DEFINITION,
        ONE_WAY_FORWARD,
        TAG,
        TYPE_LINK,
        CompleteGraphApi,
    )

    api = CompleteGraphApi()
    graph_owner, graph_field = None, None
    if change == "custom_meaning":
        api.links[HIERARCHY]["meaning"] = 6
    elif change == "custom_type":
        api.links[HIERARCHY]["typeId"] = DEFINITION
    elif change == "unknown_direction":
        api.links[HIERARCHY]["direction"] = 9
    elif change == "boolean_direction":
        api.links[HIERARCHY]["direction"] = True
    elif change == "foreign_link":
        api.links[HIERARCHY]["brainId"] = DEFINITION
    elif change == "self_link":
        api.links[HIERARCHY]["thoughtIdB"] = HOME
    elif change == "missing_field":
        del api.links[HIERARCHY]["direction"]
    elif change == "link_conflict":
        api.overrides[f"/api/links/{BRAIN}/{HIERARCHY}"] = (
            200,
            api.links[HIERARCHY] | {"name": "AUTHOR_CANARY"},
        )
    elif change == "metadata_conflict":
        api.overrides[f"/api/thoughts/{BRAIN}/{HOME}"] = (
            200,
            api.thoughts[HOME] | {"name": "AUTHOR_CANARY"},
        )
    elif change == "missing_type_inventory":
        api.types = []
    elif change == "missing_tag_inventory":
        api.tags = []
    elif change == "null_graph_type":
        graph_owner, graph_field = HOME, "type"
    elif change == "null_type_field":
        api.thoughts[HOME]["typeId"] = None
    elif change == "wrong_type_field":
        api.thoughts[HOME]["typeId"] = TAG
    elif change == "wrong_type_role":
        api.thoughts[DEFINITION]["kind"] = 1
    elif change == "duplicate_assignment":
        extra = "60000000-0000-4000-8000-000000000009"
        api.links[extra] = api.links[TYPE_LINK] | {"id": extra}
    elif change == "missing_tag_join":
        graph_owner, graph_field = HOME, "tags"
    elif change == "missing_type_children":
        graph_owner, graph_field = DEFINITION, "children"
    elif change == "missing_jump_join":
        graph_owner, graph_field = HOME, "jumps"
    elif change == "private_endpoint":
        api.thoughts[ALONE].update(acType=1, name="PRIVATE_CANARY")
    elif change == "unknown_role":
        api.thoughts[ALONE]["kind"] = 3
    elif change == "missing_endpoint":
        api.overrides[f"/api/thoughts/{BRAIN}/{ALONE}"] = (
            404,
            b"REMOTE_SERVICE_TOKEN_CANARY",
        )
    elif change == "bad_date":
        api.thoughts[HOME]["creationDateTime"] = "0001-01-01T00:00:00"
    elif change == "bad_colour":
        api.thoughts[HOME]["foregroundColor"] = "red"
    elif change.startswith("link_inventory"):
        api.overrides[f"/api/links/{BRAIN}/{ONE_WAY_FORWARD}/attachments"] = {
            "link_inventory_null": (200, None),
            "link_inventory_populated": (
                200,
                [{"name": "PRIVATE_CANARY", "url": "SERVICE_TOKEN_CANARY"}],
            ),
            "link_inventory_failed": (404, b"REMOTE_SERVICE_TOKEN_CANARY"),
        }[change]
    else:
        owner = DEFINITION if change == "inherited_icon" else HOME
        asset = [
            {
                "id": "70000000-0000-4000-8000-000000000001",
                "brainId": BRAIN,
                "sourceId": owner,
                "sourceType": 2,
                "type": 5,
                "isNotes": False,
                "location": "Icon.png",
                "name": None,
            }
        ]
        if change == "graph_icon_only":
            graph_owner, graph_field = owner, "attachments"
        else:
            api.overrides[f"/api/thoughts/{BRAIN}/{owner}/attachments"] = (200, asset)
    if graph_owner:
        graph = api.response(f"/api/thoughts/{BRAIN}/{graph_owner}/graph", {})[1]
        graph[graph_field] = (
            None
            if graph_field == "type"
            else asset
            if graph_field == "attachments"
            else []
        )
        api.overrides[f"/api/thoughts/{BRAIN}/{graph_owner}/graph"] = (200, graph)
    with api_server(api) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert inspected.outcome in {"refused", "failed"}
    assert result.outcome == inspected.outcome
    assert not (tmp_path / "vault").exists()
    for safe in (inspected.model_dump_json(), result.model_dump_json()):
        assert "CANARY" not in safe


def test_graph_transport_order_and_identical_duplicates_do_not_change_content_identity():
    import copy

    from tests.support.local_api_graph import CompleteGraphApi

    class Reordered(CompleteGraphApi):
        def response(self, path, query):
            status, value = super().response(path, query)
            value = copy.deepcopy(value)
            if isinstance(value, list):
                value.reverse()
                if path.endswith(("/types", "/tags")):
                    value += copy.deepcopy(value)
            if path.endswith("/graph"):
                for name in (
                    "parents",
                    "children",
                    "jumps",
                    "siblings",
                    "tags",
                    "links",
                ):
                    value[name].reverse()
                    value[name] += copy.deepcopy(value[name])
            return status, value

    identities = []
    for api in (CompleteGraphApi(), Reordered()):
        with api_server(api) as (_, address):
            module = LocalApiSourceModule(
                LocalApiConfig(api_url=address), credentials=lambda: KEY
            )
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                identities.append(session.source_identity)
    assert identities[0] == identities[1]


@pytest.mark.parametrize(
    "change", ["direction", "endpoint", "colour", "date", "alias_order"]
)
def test_real_graph_and_metadata_changes_change_both_content_digests(change):
    from tests.support.local_api_graph import (
        CHILD,
        FORWARD,
        ONE_WAY_FORWARD,
        CompleteGraphApi,
    )

    identities = []
    for changed in (False, True):
        api = CompleteGraphApi()
        api.thoughts[HOME]["aliases"] = ["first", "second"]
        api.search.append(
            {
                "brainId": BRAIN,
                "isFromOtherBrain": False,
                "sourceThought": {"id": FORWARD, "brainId": BRAIN, "kind": 0},
                "sourceLink": None,
            }
        )
        if changed:
            if change == "direction":
                api.links[ONE_WAY_FORWARD]["direction"] = 3
            elif change == "endpoint":
                api.links[ONE_WAY_FORWARD]["thoughtIdB"] = CHILD
            elif change == "colour":
                api.thoughts[HOME]["backgroundColor"] = "#aabbcc"
            elif change == "date":
                api.thoughts[HOME]["creationDateTime"] = "2026-01-02T00:15:30+14:00"
            else:
                api.thoughts[HOME]["aliases"].reverse()
        with api_server(api) as (_, address):
            module = LocalApiSourceModule(
                LocalApiConfig(api_url=address), credentials=lambda: KEY
            )
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                identities.append(session.source_identity)
    assert identities[0].source_sha256 != identities[1].source_sha256
    assert identities[0].snapshot_digest != identities[1].snapshot_digest


def test_excluded_definition_removes_assignment_and_inherited_content_only():
    from tests.support.local_api_graph import DEFINITION, TYPE_LINK, CompleteGraphApi

    api = CompleteGraphApi()
    api.thoughts[DEFINITION].update(
        forgottenDateTime="2026-01-01T00:00:00",
        label="EXCLUDED_CANARY",
        foregroundColor="EXCLUDED_CANARY",
    )
    statistics = api.response(f"/api/brains/{BRAIN}/statistics", {})[1]
    api.overrides[f"/api/brains/{BRAIN}/statistics"] = (
        200,
        statistics | {"thoughtTypes": 0},
    )
    api.overrides[f"/api/thoughts/{BRAIN}/{DEFINITION}/attachments"] = (
        200,
        [{"location": "Icon.png", "name": "EXCLUDED_CANARY"}],
    )
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            snapshot = session.snapshot
            assert DEFINITION not in {item.key for item in snapshot.items}
            assert TYPE_LINK not in {r.key for r in snapshot.relationships}
            assert snapshot.classification_assignments == ()
            assert snapshot.assets == ()
            assert "EXCLUDED_CANARY" not in snapshot.model_dump_json()
            assert not any(
                path == f"/api/thoughts/{BRAIN}/{DEFINITION}/attachments"
                for path, _, _ in api.requests
            )
            import json

            graph = next(
                json.loads(e.original_json)
                for e in snapshot.original_evidence
                if e.key == "graph:" + HOME
            )
            assert graph["type_ids"] == []
            assert TYPE_LINK not in graph["link_ids"]


@pytest.mark.parametrize(
    "field",
    [
        "parents_ids",
        "children_ids",
        "jump_ids",
        "sibling_ids",
        "tag_ids",
        "type_ids",
        "link_ids",
    ],
)
def test_capture_refuses_reintroduced_excluded_graph_ids_with_recomputed_digests(
    tmp_path, monkeypatch, field
):
    import json
    import tempfile

    from brz2obsidian.sources.thebrain.local_api import LocalApiSession

    api = GraphApi()
    api.thoughts[ALONE]["forgottenDateTime"] = "2026-01-01T00:00:00"
    api.links[HIERARCHY]["meaning"] = 6
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            graph = next(r for r in source["records"] if r["key"] == "graph:" + HOME)
            # Establish a correctly scoped starting control even on the old
            # implementation; the mutation must prove acceptance of reintroduced
            # excluded IDs rather than merely a duplicate or stale-digest error.
            for name, values in graph["value"].items():
                graph["value"][name] = [
                    v for v in values if v not in {ALONE, HIERARCHY}
                ]
            identity = session.snapshot.identity.model_copy(
                update={"source_sha256": "", "snapshot_digest": ""}
            )

            def corresponding_snapshot():
                originals = tuple(
                    e.model_copy(update={"original_json": json.dumps(graph["value"])})
                    if e.key == graph["key"]
                    else e
                    for e in session.snapshot.original_evidence
                )
                return session.snapshot.model_copy(
                    update={"identity": identity, "original_evidence": originals}
                )

            clean = LocalApiSession(
                source=source, snapshot=corresponding_snapshot(), audit=audit
            )
            clean.verify_consistency()
            clean.close()
            graph["value"][field].append(HIERARCHY if field == "link_ids" else ALONE)
            with pytest.raises(MigrationRefused):
                LocalApiSession(
                    source=source, snapshot=corresponding_snapshot(), audit=audit
                )


@pytest.mark.parametrize(
    "a,b,relation", [(HOME, ALONE, 1), (ALONE, HOME, 1), (HOME, ALONE, 3)]
)
def test_acquired_graph_scopes_excluded_parent_child_jump_and_sibling(a, b, relation):
    import json

    api = GraphApi()
    api.thoughts[ALONE]["forgottenDateTime"] = "2026-01-01T00:00:00"
    api.links[HIERARCHY].update(thoughtIdA=a, thoughtIdB=b, relation=relation)
    path = f"/api/thoughts/{BRAIN}/{HOME}/graph"
    graph = api.response(path, {})[1]
    graph["siblings"] = [api.thoughts[ALONE]]
    api.overrides[path] = 200, graph
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            scoped = next(
                json.loads(e.original_json)
                for e in session.snapshot.original_evidence
                if e.key == "graph:" + HOME
            )
            assert all(values == [] for values in scoped.values())
            assert session.snapshot.relationships == ()
            session.verify_consistency()


def test_acquired_graph_scopes_excluded_tag_without_removing_other_relationships():
    import json

    from tests.support.local_api_graph import TAG, TAG_LINK, CompleteGraphApi

    api = CompleteGraphApi()
    api.thoughts[TAG]["forgottenDateTime"] = "2026-01-01T00:00:00"
    stats = api.response(f"/api/brains/{BRAIN}/statistics", {})[1]
    api.overrides[f"/api/brains/{BRAIN}/statistics"] = 200, stats | {"tags": 0}
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            scoped = next(
                json.loads(e.original_json)
                for e in session.snapshot.original_evidence
                if e.key == "graph:" + HOME
            )
            assert scoped["tag_ids"] == []
            assert TAG_LINK not in scoped["link_ids"]
            assert HIERARCHY in scoped["link_ids"]
            assert len(session.snapshot.relationships) == 7
            session.verify_consistency()


@pytest.mark.parametrize(
    "mutation",
    [
        "omit_relationship",
        "swap_orientation",
        "omit_assignment",
        "change_colour",
        "change_calendar",
        "duplicate_assignment",
        "unknown_link_reference",
        "unknown_sibling_reference",
    ],
)
@pytest.mark.parametrize("profile_version", ["1", "3"])
def test_frozen_capture_binds_graph_and_metadata_facts_to_scoped_originals(
    tmp_path, monkeypatch, mutation, profile_version
):
    import json
    import tempfile
    from datetime import date

    from brz2obsidian.contracts import CalendarDates, DeclaredAppearance
    from brz2obsidian.sources.thebrain.local_api import LocalApiSession
    from tests.support.local_api_graph import CompleteGraphApi

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with api_server(CompleteGraphApi()) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=profile_version,
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            # Retained filenames are the accepted public capture format. No
            # session internals or private normalization helpers are consulted.
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            snapshot = session.snapshot
            identity = snapshot.identity.model_copy(
                update={"source_sha256": "", "snapshot_digest": ""}
            )
            changed = {"identity": identity}
            if mutation == "omit_relationship":
                changed["relationships"] = snapshot.relationships[1:]
            elif mutation == "swap_orientation":
                first = snapshot.relationships[0]
                changed["relationships"] = (
                    first.model_copy(
                        update={"item_a": first.item_b, "item_b": first.item_a}
                    ),
                ) + snapshot.relationships[1:]
            elif mutation == "omit_assignment":
                changed["classification_assignments"] = ()
            elif mutation == "duplicate_assignment":
                changed["classification_assignments"] = (
                    snapshot.classification_assignments * 2
                )
            elif mutation in {"unknown_link_reference", "unknown_sibling_reference"}:
                field = (
                    "link_ids"
                    if mutation == "unknown_link_reference"
                    else "sibling_ids"
                )
                graph = next(
                    r for r in source["records"] if r["key"] == "graph:" + HOME
                )
                graph["value"][field].append("99999999-9999-4999-8999-999999999999")
                changed["original_evidence"] = tuple(
                    evidence.model_copy(
                        update={"original_json": json.dumps(graph["value"])}
                    )
                    if evidence.key == graph["key"]
                    else evidence
                    for evidence in snapshot.original_evidence
                )
            else:
                items = list(snapshot.items)
                index = next(i for i, item in enumerate(items) if item.key == HOME)
                field = (
                    {
                        "declared_appearance": DeclaredAppearance(
                            foreground_color="#abcdef"
                        )
                    }
                    if mutation == "change_colour"
                    else {
                        "calendar_dates": CalendarDates(
                            created=date(2000, 1, 1), updated=date(2000, 1, 1)
                        )
                    }
                )
                items[index] = items[index].model_copy(update=field)
                changed["items"] = tuple(items)
            with pytest.raises(MigrationRefused):
                LocalApiSession(
                    source=source,
                    snapshot=snapshot.model_copy(update=changed),
                    audit=audit,
                    profile_version=profile_version,
                )


@pytest.mark.parametrize("case", ["stable", "missing_join", "missing_link", "drift"])
def test_excluded_association_does_not_invent_a_link_counter_equation(case):
    from tests.support.local_api import thought
    from tests.support.local_api_graph import PEER, link

    api = GraphApi()
    api.thoughts[PEER] = thought(PEER, "EXCLUDED_CANARY") | {
        "forgottenDateTime": "2026-01-01T00:00:00"
    }
    excluded_link = "60000000-0000-4000-8000-000000000009"
    api.links[excluded_link] = link(excluded_link, HOME, PEER, meaning=6) | {
        "name": "EXCLUDED_CANARY"
    }
    stats = api.response(f"/api/brains/{BRAIN}/statistics", {})[1]
    readings = []

    def statistics(query):
        readings.append(True)
        # Known included hierarchy count is1; do not infer excluded tuple scope.
        return 200, stats | {"links": 8 if case == "drift" and len(readings) > 1 else 7}

    api.overrides[f"/api/brains/{BRAIN}/statistics"] = statistics
    if case in {"missing_join", "missing_link"}:
        graph = api.response(f"/api/thoughts/{BRAIN}/{ALONE}/graph", {})[1]
        graph["parents" if case == "missing_join" else "links"] = []
        api.overrides[f"/api/thoughts/{BRAIN}/{ALONE}/graph"] = 200, graph
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        if case == "stable":
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                assert [
                    (r.key, r.kind, r.item_a, r.item_b)
                    for r in session.snapshot.relationships
                ] == [(HIERARCHY, "hierarchy", HOME, ALONE)]
                assert "EXCLUDED_CANARY" not in session.snapshot.model_dump_json()
        else:
            with pytest.raises(MigrationRefused), module.open(LocalApiSourceRef(BRAIN)):
                pytest.fail("Exclusions cannot excuse missing included facts or drift")
