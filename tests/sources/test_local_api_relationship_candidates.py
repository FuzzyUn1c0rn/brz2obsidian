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


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize(
    "hint_value",
    [None, True, 7, 1.5, "RAW_HINT_CANARY", [], {"nested": "RAW_HINT_CANARY"}],
)
def test_all_optional_link_hints_are_ignored_for_identity_and_discovery(
    legacy, hint_value
):
    fields = (
        "thoughtIdA",
        "thoughtIdB",
        "kind",
        "relation",
        "direction",
        "meaning",
        "typeId",
        "name",
        "cleanedUpName",
        "color",
        "thickness",
        "creationDateTime",
        "modificationDateTime",
    )
    identities = []
    for hints in (None, dict.fromkeys(fields, hint_value)):
        api = LinkCandidateApi(relationship_match(legacy=legacy, hints=hints))
        with (
            api_server(api) as (_, address),
            LocalApiSourceModule(
                LocalApiConfig(api_url=address),
                credentials=lambda: KEY,
                profile_version="3",
            ).open(LocalApiSourceRef(BRAIN)) as session,
        ):
            session.verify_consistency()
            identities.append(session.source_identity)
            assert {item.key for item in session.snapshot.items} == {
                HOME,
                ALONE,
                PARENT,
                CHILD,
            }
            assert "CANARY" not in session.snapshot.model_dump_json()
        assert not any(HINT in path or ZERO in path for path, _, _ in api.requests)
    assert identities[0] == identities[1]


@pytest.mark.parametrize("extra_unique", [False, True])
def test_pending_link_ids_are_bounded_before_authoritative_requests(extra_unique):
    from brz2obsidian.contracts import MigrationRefused

    api = LinkCandidateApi()
    api.thoughts.pop(PARENT)
    api.thoughts.pop(CHILD)
    api.links = {LINK: link(LINK, HOME, ALONE)}
    api.search.append(copy.deepcopy(api.search[-1]))
    if extra_unique:
        extra = copy.deepcopy(api.search[-1])
        extra["sourceLink"]["id"] = "90000000-0000-4000-8000-000000000002"
        api.search.append(extra)
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address, max_traversal_items=3),
            credentials=lambda: KEY,
            profile_version="3",
        )
        if extra_unique:
            with (
                pytest.raises(MigrationRefused) as refused,
                module.open(LocalApiSourceRef(BRAIN)),
            ):
                pytest.fail("A new unique pending ID exceeds the bound")
            assert refused.value.issues[0].code == "incomplete_source"
            assert not any(
                path.startswith(f"/api/links/{BRAIN}/") for path, _, _ in api.requests
            )
        else:
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                assert len(session.snapshot.relationships) == 1
                session.verify_consistency()


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
    "field",
    [
        "brainId",
        "isFromOtherBrain",
        "sourceThought",
        "sourceLink",
        "searchResultType",
        "entityType",
        "sourceType",
        "attachmentId",
    ],
)
def test_zero_link_envelope_requires_every_field(field):
    candidate = relationship_match()
    del candidate[field]
    assert_source_refuses(LinkCandidateApi(candidate))


@pytest.mark.parametrize(
    "field,values",
    [
        ("searchResultType", [True, 1.0, "1", 2]),
        ("entityType", [True, 3.0, "3", 2]),
        ("sourceType", [False, 0.0, "0", 1]),
        ("isFromOtherBrain", [True, 0, None, "false"]),
        ("attachmentId", [None, LINK, "", "00000000000000000000000000000000"]),
        ("name", [False, [], {}]),
        ("brainName", [1, [], {}]),
    ],
)
def test_zero_link_envelope_rejects_each_scalar_near_miss(field, values):
    for value in values:
        candidate = relationship_match()
        candidate[field] = value
        assert_source_refuses(LinkCandidateApi(candidate))


@pytest.mark.parametrize(
    "change",
    [
        "extra_outer",
        "extra_nested",
        "mixed_thought",
        "null_link",
        "missing_id",
        "missing_brain",
        "null_id",
        "zero_id",
        "noncanonical_id",
        "foreign_link",
        "null_brain",
        "zero_brain",
        "foreign_thought",
    ],
)
def test_zero_link_envelope_rejects_keysets_identity_and_mixed_owners(change):
    candidate = relationship_match()
    if change == "extra_outer":
        candidate["UNKNOWN_CANARY"] = 1
    elif change == "extra_nested":
        candidate["sourceLink"]["UNKNOWN_CANARY"] = 1
    elif change == "mixed_thought":
        candidate["sourceThought"] = {"id": ALONE, "brainId": BRAIN}
    elif change == "null_link":
        candidate["sourceLink"] = None
    elif change.startswith("missing_"):
        del candidate["sourceLink"]["id" if change == "missing_id" else "brainId"]
    elif change.endswith("_id"):
        candidate["sourceLink"]["id"] = {
            "null_id": None,
            "zero_id": ZERO,
            "noncanonical_id": LINK.replace("-", ""),
        }[change]
    elif change == "foreign_thought":
        candidate["sourceThought"] = {"id": ALONE, "brainId": HINT}
    else:
        candidate["sourceLink"]["brainId"] = {
            "foreign_link": HINT,
            "null_brain": None,
            "zero_brain": ZERO,
        }[change]
    ownership = change in {
        "foreign_link",
        "null_brain",
        "zero_brain",
        "foreign_thought",
        "missing_brain",
    }
    assert_source_refuses(
        LinkCandidateApi(candidate), code="invalid_source" if ownership else None
    )


@pytest.mark.parametrize(
    "names",
    [
        {},
        {"name": None},
        {"brainName": "Display"},
        {"name": "Display", "brainName": None},
    ],
)
def test_zero_link_optional_names_are_absent_null_or_strings(names):
    candidate = relationship_match()
    candidate.pop("name")
    candidate.pop("brainName")
    candidate.update(names)
    with (
        api_server(LinkCandidateApi(candidate)) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        assert len(session.snapshot.relationships) == 1


@pytest.mark.parametrize("auxiliary", ["absent", None, HINT])
def test_legacy_link_keeps_auxiliary_and_unknown_field_permissiveness(auxiliary):
    candidate = relationship_match(legacy=True, hints={"unknownLegacy": {"CANARY": []}})
    candidate["unknownLegacy"] = ["CANARY"]
    candidate["searchResultType"] = "ignored legacy scalar"
    if auxiliary != "absent":
        candidate["attachmentId"] = auxiliary
    # This thought is not an endpoint, Home, pin or separate wildcard hit.
    candidate["sourceThought"] = {"id": ALONE, "brainId": BRAIN}
    api = LinkCandidateApi(candidate)
    api.search = [candidate]
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        assert {i.key for i in session.snapshot.items} == {
            HOME,
            ALONE,
            PARENT,
            CHILD,
        }
        assert "CANARY" not in session.snapshot.model_dump_json()


@pytest.mark.parametrize("auxiliary", [ZERO, "malformed", "", False])
def test_legacy_link_auxiliary_cannot_authorize_zero_or_malformed_identity(auxiliary):
    candidate = relationship_match(legacy=True)
    candidate["attachmentId"] = auxiliary
    assert_source_refuses(LinkCandidateApi(candidate))


@pytest.mark.parametrize("version", ["1", "2"])
@pytest.mark.parametrize(
    "case", ["zero", "missing_hints", "malformed_hints", "qualified_hints", "reverse"]
)
def test_older_profiles_preserve_search_and_hierarchy_boundaries(version, case):
    hints = {"thoughtIdA": PARENT, "thoughtIdB": CHILD}
    if case == "missing_hints":
        hints = None
    elif case == "malformed_hints":
        hints = {"thoughtIdA": [], "thoughtIdB": CHILD}
    api = LinkCandidateApi(
        relationship_match(legacy=case != "zero", hints=hints),
        direction=3 if case == "reverse" else -1,
    )
    if case != "qualified_hints":
        assert_source_refuses(api, version=version)
    else:
        with (
            api_server(api) as (_, address),
            LocalApiSourceModule(
                LocalApiConfig(api_url=address),
                credentials=lambda: KEY,
                profile_version=version,
            ).open(LocalApiSourceRef(BRAIN)) as session,
        ):
            assert len(session.snapshot.relationships) == 1
            session.verify_consistency()


def test_equivalent_envelopes_order_and_duplicates_preserve_both_identities():
    identities = []
    for legacy in (False, True):
        api = LinkCandidateApi(
            relationship_match(
                legacy=legacy, hints={"thoughtIdA": HINT, "thoughtIdB": ZERO}
            )
        )
        api.search += copy.deepcopy(api.search)
        if legacy:
            api.search.reverse()
        with (
            api_server(api) as (_, address),
            LocalApiSourceModule(
                LocalApiConfig(api_url=address),
                credentials=lambda: KEY,
                profile_version="3",
            ).open(LocalApiSourceRef(BRAIN)) as session,
        ):
            identities.append(session.source_identity)
    assert identities[0] == identities[1]


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", True),
        ("kind", 1.0),
        ("kind", "1"),
        ("relation", True),
        ("relation", 1.0),
        ("relation", "1"),
        ("meaning", True),
        ("meaning", 1.0),
        ("meaning", "1"),
        ("direction", True),
        ("direction", 3.0),
        ("direction", "3"),
        ("relation", 2),
        ("meaning", 6),
        ("direction", 5),
        ("typeId", HINT),
    ],
)
def test_reverse_hierarchy_authoritative_tuple_is_exact(field, value):
    api = LinkCandidateApi(direction=3)
    api.links[LINK][field] = value
    assert_source_refuses(api)


@pytest.mark.parametrize("first_invalid", [False, True])
@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", True),
        ("kind", 1.0),
        ("kind", "1"),
        ("relation", True),
        ("relation", 1.0),
        ("relation", "1"),
        ("meaning", True),
        ("meaning", 1.0),
        ("meaning", "1"),
        ("direction", True),
        ("direction", 3.0),
        ("direction", "3"),
    ],
)
def test_repeated_relationship_scalar_conflicts_refuse_in_both_orders(
    first_invalid, field, value
):
    api = LinkCandidateApi(direction=3)
    changed = api.links[LINK] | {field: value}
    if first_invalid:
        api.overrides[f"/api/links/{BRAIN}/{LINK}"] = (200, changed)
    else:
        graph = copy.deepcopy(
            api.response(f"/api/thoughts/{BRAIN}/{PARENT}/graph", {})[1]
        )
        graph["links"] = [changed]
        api.overrides[f"/api/thoughts/{BRAIN}/{PARENT}/graph"] = (200, graph)
    assert_source_refuses(api, code="invalid_source")


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


@pytest.mark.parametrize("role", [1, 5])
def test_profile3_excludes_known_scope_before_relationship_meaning(role):
    api = LinkCandidateApi(direction=3)
    api.thoughts[CHILD].update(
        kind=role, name="EXCLUDED_CANARY", label="EXCLUDED_CANARY"
    )
    if role == 1:
        api.thoughts[CHILD]["forgottenDateTime"] = "2026-01-01T00:00:00"
    api.links[LINK].update(meaning=6, name="EXCLUDED_CANARY", color="EXCLUDED_CANARY")
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        assert session.snapshot.relationships == ()
        assert CHILD not in {i.key for i in session.snapshot.items}
        assert "CANARY" not in session.snapshot.model_dump_json()
        session.verify_consistency()
    assert not any(
        path.endswith((f"/{CHILD}/attachments", f"/{CHILD}/graph"))
        for path, _, _ in api.requests
    )


@pytest.mark.parametrize(
    "mutation", ["profile1", "profile2", "direction", "role", "graph", "accounting"]
)
def test_fresh_frozen_reverse_hierarchy_revalidates_semantics(
    tmp_path, monkeypatch, mutation
):
    import tempfile

    from brz2obsidian.contracts import SourceSnapshot
    from brz2obsidian.sources.thebrain.local_api import LocalApiSession

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with (
        api_server(LinkCandidateApi(direction=3)) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        capture = next(tmp_path.glob("brz2obsidian-api-*"))
        source = json.loads((capture / "source.json").read_bytes())
        audit = json.loads((capture / "audit.json").read_bytes())
        snapshot = json.loads(session.snapshot.model_dump_json())
    clean = LocalApiSession(
        source=source,
        snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        audit=audit,
        profile_version="3",
    )
    clean.verify_consistency()
    clean.close()
    version = mutation[-1] if mutation.startswith("profile") else "3"
    if mutation.startswith("profile"):
        source["identifiers"]["profile_version"] = version
    elif mutation == "direction":
        next(r for r in source["records"] if r["key"] == "link:" + LINK)["value"][
            "direction"
        ] = 5
    elif mutation == "role":
        next(r for r in source["records"] if r["key"] == "thought:" + PARENT)["value"][
            "kind"
        ] = 2
    elif mutation == "graph":
        next(r for r in source["records"] if r["key"] == "graph:" + CHILD)["value"][
            "parents_ids"
        ] = []
    else:
        snapshot["accounting"]["entries"] = []
    retained = {row["key"]: row["value"] for row in source["records"]}
    for evidence in snapshot["original_evidence"]:
        if evidence["key"] in retained:
            evidence["original_json"] = json.dumps(retained[evidence["key"]])
    snapshot["identity"].update(source_sha256="", snapshot_digest="")
    with pytest.raises(MigrationRefused):
        fresh = LocalApiSession(
            source=source,
            snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
            audit=audit,
            profile_version=version,
        )
        fresh.close()
