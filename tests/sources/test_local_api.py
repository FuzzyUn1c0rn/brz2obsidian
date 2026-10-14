import json
from pathlib import Path

import pytest

from brz2obsidian.contracts import MigrationFailed, MigrationRefused, SourceSnapshot
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/local_api_capture"


def golden_inputs():
    vector = json.loads(
        (FIXTURES / "capture-vectors.json").read_text(encoding="utf-8")
    )["cases"][0]
    files = {
        f["storage_key"]: f["utf8"].encode("utf-8") for f in vector["retained_files"]
    }
    source, snapshot, audit = (
        json.loads(files[name])
        for name in ("source.json", "snapshot.json", "audit.json")
    )
    payloads = {
        binding["asset_id"]: files[binding["storage_key"]]
        for binding in json.loads(files["manifest.json"])["payload_bindings"]
    }
    return source, snapshot, audit, payloads


@pytest.mark.parametrize(
    "mutation",
    [
        "extra_source",
        "extra_record",
        "unbound_evidence",
        "duplicate_items",
        "foreign_identity",
        "foreign_audit",
        "extra_audit",
        "duplicate_inventory",
        "unbound_title",
        "unbound_finding",
        "unbound_accounting",
        "foreign_owner",
        "boolean_length",
        "boolean_note_flag",
        "wrong_scope_rule",
        "numeric_atomic",
        "scope_cycle",
        "unknown_subject",
    ],
)
def test_public_capture_rejects_unqualified_shapes_before_writing(tmp_path, mutation):
    source, snapshot, audit, payloads = golden_inputs()
    snapshot["identity"]["source_sha256"] = snapshot["identity"]["snapshot_digest"] = ""
    if mutation == "extra_source":
        source["Authorization"] = "HEADER_CANARY"
    elif mutation == "extra_record":
        source["records"][0]["value"]["renderedUrl"] = "SERVICE_TOKEN_CANARY"
    elif mutation == "unbound_evidence":
        snapshot["original_evidence"].append(
            {
                "key": "transport",
                "kind": "records",
                "original_json": '{"token":"SERVICE_TOKEN_CANARY"}',
            }
        )
    elif mutation == "duplicate_items":
        snapshot["items"].append(snapshot["items"][0])
    elif mutation == "foreign_identity":
        snapshot["identity"]["source_id"] = "11111111-1111-4111-8111-111111111111"
    elif mutation == "foreign_audit":
        audit["requests"][0]["brain_id"] = "11111111-1111-4111-8111-111111111111"
    elif mutation == "extra_audit":
        audit["headers"] = {"Authorization": "HEADER_CANARY"}
    elif mutation == "duplicate_inventory":
        source["inventories"]["ordinary_ids"] *= 2
    elif mutation == "unbound_title":
        snapshot["items"][0]["title"] = "SERVICE_TOKEN_CANARY"
    elif mutation == "unbound_finding":
        snapshot["findings"] = [
            {
                "rule_id": "unknown",
                "kind": "unknown",
                "observed_json": '{"token":"SERVICE_TOKEN_CANARY"}',
            }
        ]
    elif mutation == "unbound_accounting":
        snapshot["accounting"]["entries"][0]["references"] = ["SERVICE_TOKEN_CANARY"]
    elif mutation == "foreign_owner":
        owner = "11111111-1111-4111-8111-111111111111"
        for record in source["records"]:
            if record["domain"] == "attachment":
                record["owner_id"] = record["value"]["sourceId"] = owner
        for fact in source["payloads"]:
            fact["owner_id"] = owner
        for asset in snapshot["assets"]:
            asset["owner"] = owner
        for evidence in snapshot["original_evidence"]:
            matching = next(
                (
                    record
                    for record in source["records"]
                    if record["key"] == evidence["key"]
                ),
                None,
            )
            if matching:
                evidence["original_json"] = json.dumps(matching["value"])
    elif mutation in {"boolean_length", "boolean_note_flag"}:
        record = next(
            record for record in source["records"] if record["domain"] == "attachment"
        )
        record["value"]["dataLength" if mutation == "boolean_length" else "isNotes"] = (
            True if mutation == "boolean_length" else 1
        )
        evidence = next(
            e for e in snapshot["original_evidence"] if e["key"] == record["key"]
        )
        evidence["original_json"] = json.dumps(record["value"])
    elif mutation == "wrong_scope_rule":
        decision = source["scope"]["decisions"][0]
        decision["rule_id"] = "local-api.forgotten.v1"
        evidence = next(
            e for e in snapshot["original_evidence"] if e["key"] == decision["key"]
        )
        evidence["original_json"] = json.dumps(decision)
    elif mutation == "numeric_atomic":
        audit["atomic"] = 0
    elif mutation in {"scope_cycle", "unknown_subject"}:
        import copy

        decisions = source["scope"]["decisions"]
        if mutation == "scope_cycle":
            extra = copy.deepcopy(decisions[0])
            extra["key"] += ":second"
            decisions.append(extra)
            snapshot["original_evidence"].append(
                {
                    "key": extra["key"],
                    "kind": "records",
                    "original_json": json.dumps(extra),
                }
            )
            snapshot["accounting"]["entries"].append(
                {
                    "identity": extra["key"],
                    "disposition": "retained_only",
                    "references": [extra["key"]],
                }
            )
            decisions[0]["evidence"] = [decisions[1]["key"]]
            decisions[1]["evidence"] = [decisions[0]["key"]]
        else:
            decisions[0]["subjects"] = ["thought:99999999-9999-4999-8999-999999999999"]
        for decision in decisions:
            evidence = next(
                e for e in snapshot["original_evidence"] if e["key"] == decision["key"]
            )
            evidence["original_json"] = json.dumps(decision)
    with pytest.raises((MigrationFailed, MigrationRefused)) as error:
        LocalApiSession(
            source=source,
            snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
            audit=audit,
            payloads=payloads,
            capture_parent=tmp_path,
        )
    assert "CANARY" not in str(error.value)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "target",
    [
        "source.json",
        "snapshot.json",
        "metadata.json",
        "audit.json",
        "manifest.json",
        "payload/0000000000000001.bin",
        "extra.json",
    ],
)
def test_pinned_capture_detects_every_file_mutation_and_revokes_streams(
    tmp_path, target
):
    source, snapshot, audit, payloads = golden_inputs()
    session = LocalApiSession(
        source=source,
        snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        audit=audit,
        payloads=payloads,
        capture_parent=tmp_path,
    )
    root = next(tmp_path.iterdir())
    identity = session.source_identity
    path = root / target
    path.write_bytes(path.read_bytes() + b" " if path.exists() else b"{}")
    with pytest.raises(MigrationRefused):
        session.verify_consistency()
    assert session.source_identity == identity
    with (
        pytest.raises(MigrationRefused),
        session.open_payload(next(iter(payloads))),
    ):
        pass
    session.close()
    assert list(tmp_path.iterdir()) == []


def test_closing_capture_revokes_outstanding_stream_and_unknown_access(tmp_path):
    source, snapshot, audit, payloads = golden_inputs()
    session = LocalApiSession(
        source=source,
        snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        audit=audit,
        payloads=payloads,
        capture_parent=tmp_path,
    )
    with pytest.raises(MigrationRefused), session.open_payload("unknown"):
        pass
    with session.open_payload(next(iter(payloads))) as stream:
        assert stream.read(1) == b"A"
        session.close()
        assert stream.closed
        with pytest.raises(MigrationRefused):
            stream.read()
    with pytest.raises(MigrationRefused):
        session.verify_consistency()
    assert list(tmp_path.iterdir()) == []


def test_session_never_cleans_replacement_storage_owned_by_caller(tmp_path):
    import shutil

    source, snapshot, audit, payloads = golden_inputs()
    session = LocalApiSession(
        source=source,
        snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        audit=audit,
        payloads=payloads,
        capture_parent=tmp_path,
    )
    root = next(tmp_path.iterdir())
    moved = root.with_name(root.name + "-moved")
    root.rename(moved)
    root.mkdir()
    sentinel = root / "caller.txt"
    sentinel.write_bytes(b"caller owns this")
    with pytest.raises(MigrationRefused):
        session.verify_consistency()
    with pytest.raises(MigrationFailed):
        session.close()
    assert sentinel.read_bytes() == b"caller owns this"
    assert (moved / "snapshot.json").is_file()
    shutil.rmtree(moved)


def test_capture_read_errors_are_typed_and_do_not_echo_filesystem_text(
    tmp_path, monkeypatch
):
    source, snapshot, audit, payloads = golden_inputs()
    session = LocalApiSession(
        source=source,
        snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        audit=audit,
        payloads=payloads,
        capture_parent=tmp_path,
    )
    original = Path.read_bytes

    def failed_read(path):
        if path.name == "source.json":
            raise OSError("HEADER_CANARY SERVICE_TOKEN_CANARY")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", failed_read)
    with pytest.raises(MigrationFailed) as error:
        session.verify_consistency()
    assert "CANARY" not in str(error.value)
    session.close()


@pytest.mark.parametrize(
    "vector",
    json.loads((FIXTURES / "capture-vectors.json").read_text(encoding="utf-8"))[
        "cases"
    ],
    ids=lambda v: v["id"],
)
def test_public_session_matches_independent_golden_capture_and_opens_frozen_payload(
    tmp_path, vector
):
    files = {
        f["storage_key"]: f["utf8"].encode("utf-8") for f in vector["retained_files"]
    }
    source = vector.get(
        "input_source_with_unordered_records", json.loads(files["source.json"])
    )
    snapshot = (
        SourceSnapshot.model_validate_json(
            json.dumps(vector["input_snapshot_with_unordered_records"])
        )
        if "input_snapshot_with_unordered_records" in vector
        else SourceSnapshot.model_validate_json(files["snapshot.json"])
    )
    audit = json.loads(files["audit.json"])
    manifest = json.loads(files["manifest.json"])
    bindings = manifest["payload_bindings"]
    payloads = {b["asset_id"]: files[b["storage_key"]] for b in bindings}
    sentinel = tmp_path / "caller.txt"
    sentinel.write_bytes(b"caller owns this")
    session = LocalApiSession(
        source=source,
        snapshot=snapshot,
        audit=audit,
        payloads=payloads,
        capture_parent=tmp_path,
        storage_keys={b["asset_id"]: b["storage_key"] for b in bindings},
    )
    try:
        assert session.source_identity.source_sha256 == vector["expected_source_sha256"]
        assert (
            session.source_identity.snapshot_digest
            == vector["expected_snapshot_digest"]
        )
        assert (
            session.acquisition.integrity_sha256 == vector["expected_integrity_sha256"]
        )
        assert session.acquisition.audit.model_dump(mode="json") == audit
        session.verify_consistency()
        with session.open_payload(bindings[0]["asset_id"]) as stream:
            assert stream.read() == files[bindings[0]["storage_key"]]
        capture = next(p for p in tmp_path.iterdir() if p.is_dir())
        assert (capture / "manifest.json").read_bytes() == files["manifest.json"]
    finally:
        session.close()
    assert list(tmp_path.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"caller owns this"


@pytest.mark.parametrize(
    "address",
    [
        "https://example.com/api",
        "http://user:API_KEY_CANARY@127.0.0.1/api",
        "http://127.0.0.1/api?token=SERVICE_TOKEN_CANARY",
        "http://127.0.0.1/api#fragment",
        "http://127.0.0.1/not-api",
        "http://127.0.0.1:0/api",
        "file:///api",
    ],
)
def test_connection_configuration_refuses_unsafe_origin_without_echoing_values(address):
    with pytest.raises(ValueError) as error:
        LocalApiConfig(api_url=address)
    assert "CANARY" not in str(error.value)


@pytest.mark.parametrize(
    "options",
    [
        {"search_initial_results": True},
        {"search_initial_results": 0},
        {"search_initial_results": 2147483648},
        {"search_max_results": -1},
        {"search_timeout": 0},
        {"search_timeout": float("inf")},
        {"search_max_response_bytes": 0},
        {"max_requests": False},
        {"max_traversal_items": 0},
        {"max_total_capture_bytes": -1},
    ],
)
def test_operational_limits_are_explicit_and_validated(options):
    with pytest.raises(ValueError):
        LocalApiConfig(**options)


def test_finite_millisecond_configuration_does_not_use_binary_rounding_as_validation():
    configuration = LocalApiConfig(search_timeout=1.001, request_timeout=0.029)
    assert configuration.audit_limits()["search_budget_ms"] == 1001
    assert configuration.audit_limits()["request_timeout_ms"] == 29
    with pytest.raises(ValueError):
        LocalApiConfig(search_timeout=1.0001)


def test_source_reference_requires_canonical_uuid_and_has_no_credential_field():
    with pytest.raises(ValueError):
        LocalApiSourceRef("not-a-uuid-API_KEY_CANARY")
    with pytest.raises(ValueError):
        LocalApiSourceRef("ABCDEF00-0000-4000-8000-000000000001")
    assert "CANARY" not in repr(LocalApiConfig())


def test_authoritative_definitions_siblings_pins_and_attachment_owner_candidates():
    from tests.support.local_api import (
        ALONE,
        BRAIN,
        HOME,
        KEY,
        MetadataApi,
        api_server,
        thought,
    )

    api = MetadataApi()
    definition, tag, pinned = (
        f"{n:08x}-4444-4444-8444-444444444444" for n in (4, 5, 6)
    )
    api.thoughts[definition] = thought(definition, "Definition") | {"kind": 2}
    api.thoughts[tag] = thought(tag, "Tag") | {"kind": 4}
    api.thoughts[pinned] = thought(pinned, "Pin")
    api.types = [api.thoughts[definition]]
    api.tags = [api.thoughts[tag]]
    api.pins = [api.thoughts[pinned]]
    api.search = [api.search[0]]
    # Attachment matches seed their owner, not an invented attachment item.
    api.search.append(
        {
            "brainId": BRAIN,
            "isFromOtherBrain": False,
            "searchResultType": 2,
            "attachmentId": "77777777-7777-4777-8777-777777777777",
            "sourceThought": {"id": HOME, "brainId": BRAIN, "kind": 0},
            "sourceLink": None,
        }
    )
    graph = api.response(f"/api/thoughts/{BRAIN}/{HOME}/graph", {})[1]
    graph["siblings"] = [api.thoughts[ALONE]]
    api.overrides[f"/api/thoughts/{BRAIN}/{HOME}/graph"] = 200, graph
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address, include_pins=True), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            assert {item.key: item.role for item in session.snapshot.items} == {
                HOME: "ordinary",
                ALONE: "ordinary",
                pinned: "ordinary",
                definition: "definition",
                tag: "tag",
            }
            assert all(item.title != "search stub" for item in session.snapshot.items)
            originals = {
                e.key: json.loads(e.original_json)
                for e in session.snapshot.original_evidence
            }
            assert originals[f"graph:{HOME}"]["sibling_ids"] == [ALONE]
            assert (
                len([key for key in originals if key.startswith("scope:included:")])
                == 5
            )
    assert any(path == "/api/brains" for path, _, _ in api.requests)
    assert any(path.endswith("/pins") for path, _, _ in api.requests)
    assert all(
        query.get("includeSiblings") == ["true"]
        for path, query, _ in api.requests
        if path.endswith("/graph")
    )


def test_identical_authoritative_observations_collapse_without_losing_scope():
    from tests.support.local_api import (
        ALONE,
        BRAIN,
        HOME,
        KEY,
        MetadataApi,
        api_server,
        thought,
    )

    api = MetadataApi()
    definition = "44444444-4444-4444-8444-444444444444"
    api.thoughts[definition] = thought(definition, "Definition") | {"kind": 2}
    api.types = [api.thoughts[definition], dict(api.thoughts[definition])]
    brain = api.response(f"/api/brains/{BRAIN}", {})[1]
    api.overrides["/api/brains"] = 200, [brain, dict(brain)]
    api.overrides[f"/api/brains/{BRAIN}/statistics"] = (
        200,
        {
            "brainId": BRAIN,
            "thoughts": 2,
            "thoughtTypes": 1,
            "tags": 0,
            "forgottenThoughts": 0,
            "links": 0,
        },
    )
    path = f"/api/thoughts/{BRAIN}/{HOME}/graph"
    graph = api.response(path, {})[1]
    graph["siblings"] = [api.thoughts[ALONE], dict(api.thoughts[ALONE])]
    api.overrides[path] = 200, graph
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        assert len(session.snapshot.items) == 3
        assert sum(item.key == definition for item in session.snapshot.items) == 1
        graph_fact = next(
            e for e in session.snapshot.original_evidence if e.key == "graph:" + HOME
        )
        assert json.loads(graph_fact.original_json)["sibling_ids"] == [ALONE]


def test_known_forgotten_and_system_items_retain_only_minimal_scope_evidence():
    from tests.support.local_api import (
        BRAIN,
        KEY,
        MetadataApi,
        api_server,
        thought,
    )

    api = MetadataApi()
    forgotten, system = (
        "44444444-4444-4444-8444-444444444444",
        "55555555-5555-4555-8555-555555555555",
    )
    api.thoughts[forgotten] = thought(forgotten, "EXCLUDED_PRIVATE_TITLE") | {
        "forgottenDateTime": "2026-10-01T12:00:00"
    }
    api.thoughts[system] = thought(system, "EXCLUDED_SYSTEM_TITLE") | {"kind": 5}
    api.search.extend(
        {
            "brainId": BRAIN,
            "isFromOtherBrain": False,
            "sourceThought": {"id": key, "brainId": BRAIN},
            "sourceLink": None,
        }
        for key in (forgotten, system)
    )
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            assert len(session.snapshot.items) == 2
            encoded = session.snapshot.model_dump_json()
            assert "EXCLUDED_" not in encoded
            values = {
                entry.key: json.loads(entry.original_json)
                for entry in session.snapshot.original_evidence
            }
            assert (
                values[f"scope:excluded:{forgotten}"]["outcome"] == "excluded_forgotten"
            )
            assert values[f"scope:excluded:{system}"]["outcome"] == "excluded_system"
            assert set(values[f"exclusion:{forgotten}"]) == {
                "id",
                "brainId",
                "kind",
                "acType",
                "forgottenDateTime",
            }
    assert not any(
        path.endswith(f"/{key}/graph") or path == f"/api/notes/{BRAIN}/{key}"
        for path, _, _ in api.requests
        for key in (forgotten, system)
    )


def test_link_search_candidate_resolves_authoritative_endpoints_then_refuses_later_content():
    from tests.support.local_api import ALONE, BRAIN, HOME, KEY, MetadataApi, api_server

    api = MetadataApi()
    link = "88888888-8888-4888-8888-888888888888"
    api.search = [
        {
            "brainId": BRAIN,
            "isFromOtherBrain": False,
            "sourceThought": None,
            "sourceLink": {
                "id": link,
                "brainId": BRAIN,
                "thoughtIdA": HOME,
                "thoughtIdB": ALONE,
            },
        }
    ]
    api.overrides[f"/api/links/{BRAIN}/{link}"] = 200, api.search[0]["sourceLink"]
    with (
        api_server(api) as (_, address),
        pytest.raises(MigrationRefused, match="not implemented"),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).open(LocalApiSourceRef(BRAIN)),
    ):
        pytest.fail("Encountered relationships cannot be silently discarded")
    paths = {path for path, _, _ in api.requests}
    assert f"/api/links/{BRAIN}/{link}" in paths
    assert f"/api/thoughts/{BRAIN}/{ALONE}" in paths


def test_wildcard_retries_share_one_monotonic_budget_including_wait_and_decode():
    from tests.support.local_api import BRAIN, KEY, MetadataApi, api_server

    api = MetadataApi()

    class Clock:
        value = 0

        def __call__(self):
            return self.value

    clock = Clock()

    def search(query):
        limit = int(query["maxResults"][0])
        clock.value += 200
        return 200, [api.search[0]] * limit if limit == 5000 else api.search

    api.overrides[f"/api/search/{BRAIN}"] = search
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address, request_timeout=300),
            credentials=lambda: KEY,
            clock=clock,
        )
        with (
            pytest.raises(MigrationRefused, match="deadline"),
            module.open(LocalApiSourceRef(BRAIN)),
        ):
            pytest.fail("Timed-out discovery must not yield")
    assert [
        int(query["maxResults"][0])
        for path, query, _ in api.requests
        if "/search/" in path
    ] == [5000, 10000]


@pytest.mark.parametrize(
    "mode", ["truncated", "gzip_truncated", "gzip_trailing", "wait"]
)
def test_required_response_is_complete_and_wait_is_within_total_search_deadline(mode):
    import gzip
    import time

    from tests.support.local_api import BRAIN, KEY, MetadataApi, api_server

    api = MetadataApi()
    raw = json.dumps(api.search).encode()
    if mode == "truncated":
        response = 200, raw, {"Content-Length": str(len(raw) + 10)}
    elif mode == "gzip_truncated":
        response = 200, gzip.compress(raw)[:-5], {"Content-Encoding": "gzip"}
    elif mode == "gzip_trailing":
        response = (
            200,
            gzip.compress(raw) + b"SERVICE_TOKEN_CANARY",
            {"Content-Encoding": "gzip"},
        )
    else:

        def slow(query):
            time.sleep(0.1)
            return 200, raw

        response = slow
    api.overrides[f"/api/search/{BRAIN}"] = response
    with (
        api_server(api) as (_, address),
        pytest.raises((MigrationFailed, MigrationRefused)) as error,
        LocalApiSourceModule(
            LocalApiConfig(api_url=address, search_timeout=0.03),
            credentials=lambda: KEY,
        ).open(LocalApiSourceRef(BRAIN)),
    ):
        pytest.fail("Incomplete or timed-out responses cannot yield a capture")
    assert "CANARY" not in str(error.value)


def test_nonsearch_request_deadline_covers_drip_reads_after_http_connection_close():
    import time

    from tests.support.local_api import BRAIN, KEY, MetadataApi, api_server

    api = MetadataApi()
    api.response_chunks[f"/api/brains/{BRAIN}"] = (1, 0.005)
    with api_server(api) as (_, address):
        started = time.monotonic()
        with (
            pytest.raises(MigrationFailed) as error,
            LocalApiSourceModule(
                LocalApiConfig(api_url=address, request_timeout=0.03),
                credentials=lambda: KEY,
            ).open(LocalApiSourceRef(BRAIN)),
        ):
            pytest.fail("Drip reads must not renew a per-request timeout")
        assert time.monotonic() - started < 0.2
    assert error.value.issues[0].code == "api_request_timeout"


def test_transport_headers_and_search_snippets_never_enter_any_frozen_file(
    tmp_path, monkeypatch
):
    import tempfile

    from tests.support.local_api import BRAIN, KEY, MetadataApi, api_server

    api = MetadataApi()
    api.search[0]["name"] = "SERVICE_TOKEN_CANARY"
    api.overrides[f"/api/search/{BRAIN}"] = (
        200,
        api.search,
        {"X-Secret": "HEADER_CANARY", "Set-Cookie": "HEADER_CANARY"},
    )
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        root = next(tmp_path.iterdir())
        files = {
            path.name: path.read_bytes() for path in root.rglob("*") if path.is_file()
        }
        assert set(files) == {
            "source.json",
            "snapshot.json",
            "metadata.json",
            "audit.json",
            "manifest.json",
        }
        assert all(b"CANARY" not in value for value in files.values())
        assert session.snapshot.items[0].title == "Entry"
        assert session.acquisition.audit.atomic is False
    assert all(authorization == "Bearer " + KEY for _, _, authorization in api.requests)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "collection,owner_inventory,expected",
    [
        ("attachments", [], "clean"),
        ("attachments", None, "refused"),
        ("siblings", [], "refused"),
    ],
)
def test_null_graph_collections_require_their_qualified_inventory_proof(
    collection, owner_inventory, expected
):
    from brz2obsidian.application.wiring import local_api_workflow
    from tests.support.local_api import BRAIN, HOME, KEY, MetadataApi, api_server

    api = MetadataApi()
    path = f"/api/thoughts/{BRAIN}/{HOME}"
    graph = api.response(path + "/graph", {})[1]
    graph[collection] = None
    api.overrides[path + "/graph"] = 200, graph
    api.overrides[path + "/attachments"] = 200, owner_inventory
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).inspect(LocalApiSourceRef(BRAIN))
    assert result.outcome == expected
    if expected == "clean":
        assert any(request[0] == path + "/attachments" for request in api.requests)


@pytest.mark.parametrize(
    "endpoint,status",
    [("tags", 401), ("tags", 403), ("tags", 404), ("tags", 500), ("types", 400)],
)
def test_plaintext_tag_message_cannot_qualify_other_status_or_inventory(
    endpoint, status
):
    from brz2obsidian.application.wiring import local_api_workflow
    from tests.support.local_api import BRAIN, KEY, MetadataApi, api_server

    api = MetadataApi()
    api.overrides[f"/api/thoughts/{BRAIN}/{endpoint}"] = (
        status,
        ("Could not retrieve list of Tags for brain " + BRAIN).encode(),
    )
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).inspect(LocalApiSourceRef(BRAIN))
    assert result.outcome == "failed" and result.source_identity is None


def test_aggregate_reply_bytes_are_bounded_before_capture_materialization():
    from tests.support.local_api import BRAIN, KEY, MetadataApi, api_server

    api = MetadataApi()
    statistics = api.response(f"/api/brains/{BRAIN}/statistics", {})[1]
    statistics["operationalMetric"] = "x" * 25000
    api.overrides[f"/api/brains/{BRAIN}/statistics"] = 200, statistics
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address, max_total_capture_bytes=45000),
            credentials=lambda: KEY,
        )
        with (
            pytest.raises(MigrationRefused, match="aggregate"),
            module.open(LocalApiSourceRef(BRAIN)),
        ):
            pytest.fail("Aggregate reads must stop before freezing")


def test_public_capture_identity_ignores_response_order_but_binds_authored_dates_and_scope():
    from tests.support.local_api import ALONE, BRAIN, KEY, MetadataApi, api_server

    identities = []
    for change in ("baseline", "order", "title", "date", "scope"):
        api = MetadataApi()
        if change == "order":
            api.search.reverse()
            api.thoughts = {
                key: dict(reversed(list(value.items())))
                for key, value in reversed(list(api.thoughts.items()))
            }
        elif change == "title":
            api.thoughts[ALONE]["name"] = "Changed authored title"
        elif change == "date":
            api.thoughts[ALONE]["modificationDateTime"] = "2026-10-15T00:00:00"
        elif change == "scope":
            api.thoughts[ALONE]["forgottenDateTime"] = "2026-10-15T00:00:00"
        with (
            api_server(api) as (_, address),
            LocalApiSourceModule(
                LocalApiConfig(api_url=address), credentials=lambda: KEY
            ).open(LocalApiSourceRef(BRAIN)) as session,
        ):
            identities.append(session.source_identity)
    assert identities[0] == identities[1]
    assert len({identity.source_sha256 for identity in identities}) == 4
    assert len({identity.snapshot_digest for identity in identities}) == 4


@pytest.mark.parametrize(
    "mutation",
    [
        "private",
        "unknown_role",
        "boolean_role",
        "negative_zero",
        "foreign_metadata",
        "unknown_field",
        "invalid_date",
        "invalid_offset_minute",
        "sentinel_date",
        "missing_forgotten",
        "graph_conflict",
        "definition_conflict",
        "foreign_search",
        "stub_only",
        "note_token",
        "note_float_source_type",
        "resource",
        "appearance",
        "stats_boolean",
        "stats_drift",
        "foreign_statistics",
        "missing_statistics",
        "tag_nonzero",
        "tag_contradiction",
        "forgotten_tag_contradiction",
        "pins_failure",
        "malformed_json",
        "malformed_utf8",
        "credential_echo",
    ],
)
def test_incomplete_or_unimplemented_source_never_publishes_or_echoes_transport_data(
    tmp_path, mutation
):
    from brz2obsidian.application.wiring import local_api_workflow
    from tests.support.local_api import ALONE, BRAIN, HOME, KEY, MetadataApi, api_server

    api = MetadataApi()
    key = f"/api/thoughts/{BRAIN}/{HOME}"
    if mutation == "private":
        api.thoughts[HOME]["acType"] = 1
    elif mutation == "unknown_role":
        api.thoughts[HOME]["kind"] = 9
    elif mutation == "boolean_role":
        api.thoughts[HOME]["kind"] = True
    elif mutation == "negative_zero":
        raw = json.dumps(api.thoughts[HOME]).encode()
        assert raw.count(b'"acType": 0') == 1
        api.overrides[key] = 200, raw.replace(b'"acType": 0', b'"acType": -0')
    elif mutation == "foreign_metadata":
        api.thoughts[HOME]["brainId"] = ALONE
    elif mutation == "unknown_field":
        api.thoughts[HOME]["renderedUrl"] = "SERVICE_TOKEN_CANARY"
    elif mutation == "invalid_date":
        api.thoughts[HOME]["creationDateTime"] = "2026-10-14T10:00:00+15:00"
    elif mutation == "invalid_offset_minute":
        api.thoughts[HOME]["creationDateTime"] = "2026-10-14T10:00:00+00:99"
    elif mutation == "sentinel_date":
        api.thoughts[HOME]["forgottenDateTime"] = "0001-01-01T00:00:00"
    elif mutation == "missing_forgotten":
        del api.thoughts[HOME]["forgottenDateTime"]
    elif mutation == "graph_conflict":
        graph = api.response(key + "/graph", {})[1]
        graph["activeThought"] = dict(api.thoughts[HOME], name="CONFLICT_CANARY")
        api.overrides[key + "/graph"] = 200, graph
    elif mutation == "definition_conflict":
        api.types = [dict(api.thoughts[ALONE], kind=2)]
    elif mutation == "foreign_search":
        api.search[0]["isFromOtherBrain"] = True
    elif mutation == "stub_only":
        api.search = [
            {
                "brainId": BRAIN,
                "isFromOtherBrain": False,
                "sourceThought": {
                    "id": "99999999-9999-4999-8999-999999999999",
                    "brainId": BRAIN,
                },
            }
        ]
    elif mutation == "note_token":
        api.overrides[f"/api/notes/{BRAIN}/{HOME}"] = (
            200,
            {"markdown": "", "html": "SERVICE_TOKEN_CANARY"},
        )
    elif mutation == "note_float_source_type":
        note_path = f"/api/notes/{BRAIN}/{HOME}"
        note = api.response(note_path, {})[1]
        note["sourceType"] = 2.0
        api.overrides[note_path] = 200, note
    elif mutation == "resource":
        api.overrides[key + "/attachments"] = (
            200,
            [{"location": "SERVICE_TOKEN_CANARY"}],
        )
    elif mutation == "appearance":
        api.thoughts[HOME]["foregroundColor"] = "#ffffff"
    elif mutation == "stats_boolean":
        api.overrides[f"/api/brains/{BRAIN}/statistics"] = (
            200,
            {
                "brainId": BRAIN,
                "thoughts": True,
                "thoughtTypes": 0,
                "tags": 0,
                "forgottenThoughts": 0,
                "links": 0,
            },
        )
    elif mutation == "stats_drift":
        calls = [0]

        def statistics(query):
            calls[0] += 1
            return 200, {
                "brainId": BRAIN,
                "thoughts": 2 if calls[0] == 1 else 3,
                "thoughtTypes": 0,
                "tags": 0,
                "forgottenThoughts": 0,
                "links": 0,
            }

        api.overrides[f"/api/brains/{BRAIN}/statistics"] = statistics
    elif mutation in {"foreign_statistics", "missing_statistics"}:
        statistics = api.response(f"/api/brains/{BRAIN}/statistics", {})[1]
        if mutation == "foreign_statistics":
            statistics["brainId"] = ALONE
        else:
            del statistics["brainId"]
        api.overrides[f"/api/brains/{BRAIN}/statistics"] = 200, statistics
    elif mutation in {
        "tag_nonzero",
        "tag_contradiction",
        "forgotten_tag_contradiction",
    }:
        api.overrides[f"/api/thoughts/{BRAIN}/tags"] = (
            400,
            ("Could not retrieve list of Tags for brain " + BRAIN).encode(),
        )
        if mutation == "tag_nonzero":
            api.tags = [api.thoughts[ALONE]]
        else:
            api.thoughts[ALONE]["kind"] = 4
            if mutation == "forgotten_tag_contradiction":
                api.thoughts[ALONE]["forgottenDateTime"] = "2026-10-14T11:00:00"
    elif mutation == "pins_failure":
        api.overrides[f"/api/thoughts/{BRAIN}/pins"] = 400, b"SERVICE_TOKEN_CANARY"
    elif mutation == "malformed_json":
        api.overrides[key] = 200, b'{"name":"SERVICE_TOKEN_CANARY",'
    elif mutation == "malformed_utf8":
        api.overrides[key] = 200, b"\xffSERVICE_TOKEN_CANARY"
    elif mutation == "credential_echo":
        api.thoughts[HOME]["name"] = KEY
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address, include_pins=mutation == "pins_failure"),
            credentials=lambda: KEY,
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome in {"refused", "failed"}, result
    assert not (tmp_path / "vault").exists()
    assert "CANARY" not in result.model_dump_json()


@pytest.mark.parametrize(
    "ceiling,second_count,expected_limits",
    [(None, 5001, [5000, 10000]), (7500, 6000, [5000, 7500])],
)
def test_saturated_raw_hits_grow_before_owner_deduplication(
    ceiling, second_count, expected_limits
):
    from tests.support.local_api import ALONE, BRAIN, HOME, KEY, MetadataApi, api_server

    api = MetadataApi()

    def search(query):
        limit = int(query["maxResults"][0])
        hit = api.search[0]
        return 200, [hit] * 5000 if limit == 5000 else [
            *([hit] * (second_count - 1)),
            api.search[1],
        ]

    api.overrides[f"/api/search/{BRAIN}"] = search
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address, search_max_results=ceiling),
            credentials=lambda: KEY,
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            assert {item.key for item in session.snapshot.items} == {HOME, ALONE}
    assert [
        int(q["maxResults"][0])
        for path, q, _ in api.requests
        if path.startswith("/api/search/")
    ] == expected_limits


def test_saturated_non_power_of_two_ceiling_refuses_without_partial_session():
    from tests.support.local_api import BRAIN, KEY, MetadataApi, api_server

    api = MetadataApi()
    api.overrides[f"/api/search/{BRAIN}"] = lambda query: (
        200,
        [api.search[0]] * int(query["maxResults"][0]),
    )
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address, search_max_results=7500),
            credentials=lambda: KEY,
        )
        with (
            pytest.raises(MigrationRefused) as error,
            module.open(LocalApiSourceRef(BRAIN)),
        ):
            pytest.fail("partial acquisition was yielded")
    assert error.value.issues[0].code == "incomplete_source"
    assert [
        int(q["maxResults"][0])
        for path, q, _ in api.requests
        if path.startswith("/api/search/")
    ] == [5000, 7500]


@pytest.mark.parametrize("compressed", [False, True])
def test_search_response_limit_is_enforced_after_decompression(compressed):
    import gzip

    from tests.support.local_api import BRAIN, KEY, MetadataApi, api_server

    api = MetadataApi()
    raw = json.dumps([api.search[0]] * 1000).encode()
    body = gzip.compress(raw) if compressed else raw
    assert len(body) < 5000 if compressed else len(body) > 5000
    api.overrides[f"/api/search/{BRAIN}"] = (
        200,
        body,
        {"Content-Encoding": "gzip"} if compressed else {},
    )
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address, search_max_response_bytes=5000),
            credentials=lambda: KEY,
        )
        with (
            pytest.raises(MigrationRefused) as error,
            module.open(LocalApiSourceRef(BRAIN)),
        ):
            pytest.fail("oversize search yielded")
    assert error.value.issues[0].code == "incomplete_source"
    assert "search_max_response_bytes" in str(error.value)


def test_valid_gzip_search_is_decoded_without_changing_content_identity():
    import gzip

    from tests.support.local_api import BRAIN, KEY, MetadataApi, api_server

    identities = []
    for compressed in [False, True]:
        api = MetadataApi()
        if compressed:
            api.overrides[f"/api/search/{BRAIN}"] = (
                200,
                gzip.compress(json.dumps(api.search).encode()),
                {"Content-Encoding": "gzip"},
            )
        with (
            api_server(api) as (_, address),
            LocalApiSourceModule(
                LocalApiConfig(api_url=address), credentials=lambda: KEY
            ).open(LocalApiSourceRef(BRAIN)) as session,
        ):
            identities.append(session.source_identity)
    assert identities[0] == identities[1]


def test_redirect_is_rejected_without_forwarding_credentials():
    from brz2obsidian.contracts import MigrationFailed
    from tests.support.local_api import BRAIN, KEY, MetadataApi, api_server

    target = MetadataApi()
    origin = MetadataApi()
    with api_server(target) as (_, target_address):
        origin.overrides[f"/api/brains/{BRAIN}"] = (
            302,
            b"SERVICE_TOKEN_CANARY",
            {
                "Location": target_address
                + f"/brains/{BRAIN}?token=SERVICE_TOKEN_CANARY"
            },
        )
        with (
            api_server(origin) as (_, address),
            pytest.raises(MigrationFailed) as error,
            LocalApiSourceModule(
                LocalApiConfig(api_url=address), credentials=lambda: KEY
            ).open(LocalApiSourceRef(BRAIN)),
        ):
            pytest.fail("redirect followed")
    assert target.requests == []
    assert error.value.issues[0].code == "api_redirect_refused"
    assert "CANARY" not in str(error.value)


@pytest.mark.parametrize(
    "options",
    [
        {"max_requests": 3},
        {"max_response_bytes": 10},
        {"max_traversal_items": 1},
        {"max_total_capture_bytes": 1000},
    ],
)
def test_non_search_operational_bounds_prevent_complete_acquisition(options):
    from tests.support.local_api import BRAIN, KEY, api_server

    with (
        api_server() as (_, address),
        pytest.raises(MigrationRefused) as error,
        LocalApiSourceModule(
            LocalApiConfig(api_url=address, **options), credentials=lambda: KEY
        ).open(LocalApiSourceRef(BRAIN)),
    ):
        pytest.fail("bound was ignored")
    assert error.value.issues[0].code == "incomplete_source"


def test_exact_plaintext_zero_tag_failure_is_scoped_failed_inventory_not_empty_success():
    from tests.support.local_api import BRAIN, KEY, MetadataApi, api_server

    api = MetadataApi()
    api.overrides[f"/api/thoughts/{BRAIN}/tags"] = (
        400,
        ("\u2003Could not retrieve list of Tags for brain " + BRAIN + "\r\n").encode(),
    )
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        originals = [
            json.loads(e.original_json) for e in session.snapshot.original_evidence
        ]
        assert any(
            isinstance(e, dict)
            and e.get("outcome") == "tag400_zero"
            and e.get("rule_id") == "local-api.tag400.v1"
            for e in originals
        )
        assert "Could not retrieve" not in session.snapshot.model_dump_json()


@pytest.mark.parametrize(
    "body",
    [
        b"Could not retrieve list of Tags for brain 00000000-0000-4000-8000-000000000001",
        b"Could not retrieve list of Tags for brain 11111111-1111-4111-8111-111111111111 extra",
        b"Could  not retrieve list of Tags for brain 11111111-1111-4111-8111-111111111111",
        b"\xef\xbb\xbfCould not retrieve list of Tags for brain 11111111-1111-4111-8111-111111111111",
        b"\xff",
        b"SERVICE_TOKEN_CANARY",
    ],
)
def test_other_tag400_bodies_never_qualify_or_escape_public_results(body):
    from brz2obsidian.application.wiring import local_api_workflow
    from tests.support.local_api import BRAIN, KEY, MetadataApi, api_server

    api = MetadataApi()
    api.overrides[f"/api/thoughts/{BRAIN}/tags"] = (400, body)
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).inspect(LocalApiSourceRef(BRAIN))
    assert result.outcome in {"refused", "failed"} and result.source_identity is None
    assert "CANARY" not in result.model_dump_json()
