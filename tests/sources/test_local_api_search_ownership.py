import copy
import json

import pytest

from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, MetadataApi, api_server

ZERO = "00000000-0000-0000-0000-000000000000"


def thought_match(owner):
    return {
        "brainId": ZERO,
        "isFromOtherBrain": False,
        "sourceThought": {"id": owner, "brainId": BRAIN, "kind": 0},
        "sourceLink": None,
        "searchResultType": 1,
        "entityType": 2,
        "sourceType": 0,
        "attachmentId": ZERO,
        "name": "Search display hint",
        "brainName": None,
    }


def test_zero_search_envelope_discovers_disconnected_thought_without_zero_identity(
    tmp_path,
):
    api = MetadataApi()
    api.search = [thought_match(HOME), thought_match(ALONE)]
    with api_server(api) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "clean"
        assert inspected.counts.source_items == 2
        converted = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert converted.outcome == "clean"
    assert converted.receipt.verified
    record = json.loads(
        (tmp_path / "vault/migration-record.json").read_text(encoding="utf-8")
    )
    assert {row["item_key"] for row in record["item_targets"]} == {HOME, ALONE}
    assert record["asset_targets"] == []
    assert "Search display hint" not in json.dumps(record)
    assert ZERO not in json.dumps(record)


@pytest.mark.parametrize("result_type", [3, 4])
def test_zero_attachment_search_match_discovers_its_disconnected_thought_owner(
    result_type,
):
    api = MetadataApi()
    api.search = [
        thought_match(ALONE)
        | {
            "searchResultType": result_type,
            "entityType": 4,
            "sourceType": 2,
            "attachmentId": "44444444-4444-4444-8444-444444444444",
        }
    ]
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="2",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            assert {item.key: item.title for item in session.snapshot.items} == {
                HOME: "Entry",
                ALONE: "Alone",
            }
            assert session.snapshot.assets == ()
            assert ZERO not in session.snapshot.model_dump_json()
            session.verify_consistency()


@pytest.mark.parametrize(
    "envelope", ["legacy", "zero", "local-zero-auxiliary", "local-null-auxiliary"]
)
def test_equivalent_candidate_envelopes_and_order_keep_content_identity(envelope):
    identities = []
    for changed in (False, True):
        api = MetadataApi()
        if changed:
            if envelope == "zero":
                api.search = [thought_match(ALONE), thought_match(HOME)]
            elif envelope in {"local-zero-auxiliary", "local-null-auxiliary"}:
                api.search = [
                    thought_match(ALONE) | {"brainId": BRAIN},
                    thought_match(HOME) | {"brainId": BRAIN},
                ]
                if envelope == "local-null-auxiliary":
                    for candidate in api.search:
                        candidate["attachmentId"] = None
            else:
                api.search.reverse()
            api.search.append(copy.deepcopy(api.search[0]))
        with api_server(api) as (_, address):
            module = LocalApiSourceModule(
                LocalApiConfig(api_url=address),
                credentials=lambda: KEY,
                profile_version="2",
            )
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                identities.append(session.source_identity)
    assert identities[0] == identities[1]


REQUIRED = (
    "brainId",
    "isFromOtherBrain",
    "sourceThought",
    "sourceLink",
    "searchResultType",
    "entityType",
    "sourceType",
    "attachmentId",
)


@pytest.mark.parametrize("missing", REQUIRED)
def test_zero_search_envelope_requires_every_qualified_field(missing):
    api = MetadataApi()
    candidate = thought_match(ALONE)
    del candidate[missing]
    api.search = [candidate]
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).inspect(LocalApiSourceRef(BRAIN))
    assert result.outcome == "refused"
    assert result.inspection is None and result.receipt is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("brainId", None),
        ("brainId", "foreign"),
        ("brainId", "99999999-9999-4999-8999-999999999999"),
        ("isFromOtherBrain", True),
        ("isFromOtherBrain", 0),
        ("isFromOtherBrain", None),
        ("isFromOtherBrain", "false"),
        ("sourceThought", None),
        ("sourceThought", []),
        ("sourceThought", {}),
        ("sourceLink", {}),
        ("sourceLink", {"id": HOME, "brainId": BRAIN}),
        ("name", 7),
        ("brainName", []),
        ("unknown", "SERVICE_TOKEN_CANARY"),
        ("attachmentId", None),
        ("attachmentId", "44444444-4444-4444-8444-444444444444"),
        ("attachmentId", "malformed"),
    ]
    + [
        (field, value)
        for field in ("searchResultType", "entityType", "sourceType")
        for value in (999, True, 1.0, "1")
    ],
)
def test_unqualified_search_envelope_refuses_without_retaining_hints(field, value):
    api = MetadataApi()
    api.search = [thought_match(ALONE) | {field: value}]
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).inspect(LocalApiSourceRef(BRAIN))
    assert result.outcome == "refused"
    assert result.inspection is None and result.receipt is None
    assert "CANARY" not in result.model_dump_json()


@pytest.mark.parametrize(
    "field,value",
    [
        (field, value)
        for field in ("id", "brainId")
        for value in (None, ZERO, "malformed", [], "missing")
    ]
    + [("brainId", "99999999-9999-4999-8999-999999999999")],
)
def test_zero_envelope_cannot_supply_invalid_nested_owner(field, value):
    api = MetadataApi()
    candidate = thought_match(ALONE)
    if value == "missing":
        del candidate["sourceThought"][field]
    else:
        candidate["sourceThought"][field] = value
    api.search = [candidate]
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).inspect(LocalApiSourceRef(BRAIN))
    assert result.outcome == "refused"
    assert result.receipt is None


@pytest.mark.parametrize("result_type", [3, 4])
@pytest.mark.parametrize("attachment", [None, ZERO, "malformed", "missing"])
def test_attachment_match_requires_its_present_nonzero_candidate_identity(
    result_type, attachment
):
    api = MetadataApi()
    candidate = thought_match(ALONE) | {
        "searchResultType": result_type,
        "entityType": 4,
        "sourceType": 2,
        "attachmentId": attachment,
    }
    if attachment == "missing":
        del candidate["attachmentId"]
    api.search = [candidate]
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).inspect(LocalApiSourceRef(BRAIN))
    assert result.outcome == "refused"
    assert result.receipt is None


@pytest.mark.parametrize(
    "change",
    [
        {"brainId": "99999999-9999-4999-8999-999999999999"},
        {"id": HOME},
        {"acType": 1, "name": "PRIVATE_CANARY"},
        {"kind": 3, "name": "UNSUPPORTED_CANARY"},
    ],
)
def test_zero_candidate_still_requires_qualified_authoritative_owner(change):
    api = MetadataApi()
    api.search = [thought_match(ALONE)]
    api.thoughts[ALONE] |= change
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).inspect(LocalApiSourceRef(BRAIN))
    assert result.outcome == "refused"
    assert result.inspection is None and result.receipt is None
    assert "CANARY" not in result.model_dump_json()


@pytest.mark.parametrize("outer", [BRAIN, ZERO])
def test_link_only_search_retains_local_path_and_refuses_unqualified_zero_path(outer):
    from tests.support.local_api_graph import HIERARCHY, GraphApi

    api = GraphApi()
    api.search = [
        {
            "brainId": outer,
            "isFromOtherBrain": False,
            "sourceThought": None,
            "sourceLink": api.links[HIERARCHY],
        }
    ]
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).inspect(LocalApiSourceRef(BRAIN))
    if outer == BRAIN:
        assert result.outcome == "clean"
        assert result.counts.source_items == 2
        assert result.counts.source_relationships == 1
    else:
        assert result.outcome == "refused"
        assert result.inspection is None
