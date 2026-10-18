"""Profile3 relationship discovery through real public HTTP/source workflows."""

import copy
import json

import pytest

from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, api_server, thought
from tests.support.local_api_graph import GraphApi, link

ZERO = "00000000-0000-0000-0000-000000000000"
PARENT = "80000000-0000-4000-8000-000000000001"
CHILD = "80000000-0000-4000-8000-000000000002"
LINK = "90000000-0000-4000-8000-000000000001"
HINT = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def relationship_match(*, legacy=False, hints=None):
    candidate = {
        "brainId": BRAIN if legacy else ZERO,
        "isFromOtherBrain": False,
        "sourceThought": None,
        "sourceLink": {"id": LINK, "brainId": BRAIN},
        "searchResultType": 1,
        "entityType": 3,
        "sourceType": 0,
        "name": "IGNORED_SEARCH_HINT_CANARY",
        "brainName": None,
    }
    if not legacy:
        candidate["attachmentId"] = ZERO
    if hints:
        candidate["sourceLink"].update(hints)
    return candidate


class LinkCandidateApi(GraphApi):
    def __init__(self, candidate=None, *, direction=-1):
        super().__init__()
        self.thoughts[PARENT] = thought(PARENT, "Parent")
        self.thoughts[CHILD] = thought(CHILD, "Child")
        self.links = {LINK: link(LINK, PARENT, CHILD, direction=direction)}
        self.search = [
            {
                "brainId": BRAIN,
                "isFromOtherBrain": False,
                "sourceThought": {"id": ALONE, "brainId": BRAIN},
                "sourceLink": None,
            },
            relationship_match() if candidate is None else candidate,
        ]


def test_zero_brain_link_discovers_authoritative_disconnected_endpoints(tmp_path):
    api = LinkCandidateApi()
    with api_server(api) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "clean", inspected.issues
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
        assert result.outcome == "clean", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert {
        (r["key"], r["kind"], r["item_a"], r["item_b"]) for r in record["relationships"]
    } == {(LINK, "hierarchy", PARENT, CHILD)}
    assert {t["item_key"] for t in record["item_targets"]} == {
        HOME,
        ALONE,
        PARENT,
        CHILD,
    }
    paths = [path for path, _, _ in api.requests]
    assert paths.index(f"/api/links/{BRAIN}/{LINK}") < paths.index(
        f"/api/thoughts/{BRAIN}/{PARENT}"
    )
    assert not any(ZERO in path or HINT in path for path in paths)
    assert "CANARY" not in json.dumps(record)


def test_reverse_arrow_hierarchy_retains_parent_child_and_raw_direction(tmp_path):
    api = LinkCandidateApi(direction=3)
    from tests.support.local_api_payloads import NOTE, attachment

    for owner, note_id, body in (
        (PARENT, NOTE, b"Parent body"),
        (CHILD, "a1111111-1111-4111-8111-111111111112", b"Child body"),
    ):
        note = attachment(
            note_id, owner, 1, "Notes.md", is_notes=True, length=len(body)
        )
        graph = api.response(f"/api/thoughts/{BRAIN}/{owner}/graph", {})[1]
        graph["attachments"] = [note]
        api.overrides.update(
            {
                f"/api/thoughts/{BRAIN}/{owner}/graph": (200, graph),
                f"/api/thoughts/{BRAIN}/{owner}/attachments": (200, [note]),
                f"/api/attachments/{BRAIN}/{note_id}/metadata": (200, note),
                f"/api/attachments/{BRAIN}/{note_id}/file-content": (200, body),
            }
        )
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            relationship = session.snapshot.relationships[0]
            assert (
                relationship.key,
                relationship.kind,
                relationship.item_a,
                relationship.item_b,
            ) == (LINK, "hierarchy", PARENT, CHILD)
            original = next(
                e for e in session.snapshot.original_evidence if e.key == "link:" + LINK
            )
            raw = json.loads(original.original_json)
            assert (
                raw["kind"],
                raw["relation"],
                raw["meaning"],
                raw["direction"],
                raw["typeId"],
            ) == (1, 1, 1, 3, None)
            session.verify_consistency()
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
        assert result.outcome == "clean", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    published = next(
        row["records"]
        for row in record["original_evidence"]
        if row["key"] == "link:" + LINK
    )
    assert tuple(
        published[field]
        for field in ("kind", "relation", "meaning", "direction", "typeId")
    ) == (1, 1, 1, 3, None)
    assert {
        "identity": "link:" + LINK,
        "disposition": "normalized",
        "references": [LINK],
    } in record["source_accounting"]["entries"]
    assert "## Children\n\n- [[Notes/Child.md|Child]]" in (
        tmp_path / "vault/Notes/Parent.md"
    ).read_text(encoding="utf-8")
    assert "## Parents\n\n- [[Notes/Parent.md|Parent]]" in (
        tmp_path / "vault/Notes/Child.md"
    ).read_text(encoding="utf-8")


def assert_source_refuses(api, *, version="3", code=None):
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=version,
        )
        with (
            pytest.raises(MigrationRefused) as refused,
            module.open(LocalApiSourceRef(BRAIN)),
        ):
            pytest.fail("Unqualified source must refuse")
        if code:
            assert refused.value.issues[0].code == code
        assert "CANARY" not in str(refused.value)


@pytest.mark.parametrize(
    "change",
    [
        "wrong_get_id",
        "foreign_get_brain",
        "unresolved_endpoint",
        "private_endpoint",
        "parent_inventory",
        "child_inventory",
        "parent_children",
        "child_parents",
        "unexplained_neighbor",
        "populated_content",
        "failed_content",
        "null_content",
        "parent_definition",
        "child_tag",
        "self_link",
    ],
)
def test_reverse_hierarchy_requires_authoritative_endpoints_and_complete_joins(
    tmp_path, change
):
    api = LinkCandidateApi(direction=3)
    if change == "wrong_get_id":
        api.overrides[f"/api/links/{BRAIN}/{LINK}"] = (
            200,
            api.links[LINK] | {"id": HINT},
        )
    elif change == "foreign_get_brain":
        api.overrides[f"/api/links/{BRAIN}/{LINK}"] = (
            200,
            api.links[LINK] | {"brainId": HINT},
        )
    elif change == "unresolved_endpoint":
        api.overrides[f"/api/thoughts/{BRAIN}/{CHILD}"] = (404, b"PRIVATE_CANARY")
    elif change == "private_endpoint":
        api.thoughts[CHILD]["acType"] = 1
    elif change == "parent_definition":
        api.thoughts[PARENT]["kind"] = 2
        api.types = [api.thoughts[PARENT]]
    elif change == "child_tag":
        api.thoughts[CHILD]["kind"] = 4
        api.tags = [api.thoughts[CHILD]]
    elif change == "self_link":
        api.links[LINK]["thoughtIdB"] = PARENT
    elif change.endswith("content"):
        response = {
            "populated_content": (200, [{"CANARY": True}]),
            "failed_content": (404, b"PRIVATE_CANARY"),
            "null_content": (200, None),
        }[change]
        api.overrides[f"/api/links/{BRAIN}/{LINK}/attachments"] = response
    else:
        owner = CHILD if change.startswith("child_") else PARENT
        graph = copy.deepcopy(
            api.response(f"/api/thoughts/{BRAIN}/{owner}/graph", {})[1]
        )
        if change.endswith("inventory"):
            graph["links"] = []
        elif change == "unexplained_neighbor":
            graph["children"].append(api.thoughts[ALONE])
        else:
            graph["parents" if owner == CHILD else "children"] = []
        api.overrides[f"/api/thoughts/{BRAIN}/{owner}/graph"] = (200, graph)
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome in {"refused", "failed"}
    assert result.receipt is None
    assert not (tmp_path / "vault").exists()
    assert "CANARY" not in result.model_dump_json()
