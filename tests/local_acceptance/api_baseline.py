"""Independent raw HTTP coverage closure and acceptance/2 indexing."""

import gzip
import hashlib
import json
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from .api_manifest import load_baseline, read_json, safe_path
from .api_recording import write_json
from .api_scope import strict


def observations(directory, ledger):
    """Verify every occurrence, preserving raw and content-decoded bytes."""
    indexed = {}
    for ordinal, row in enumerate(ledger["occurrences"], 1):
        assert row["ordinal"] == ordinal and row["method"] == "GET", (
            "ordered GET evidence"
        )
        for field, length, digest in (
            ("body", "length", "sha256"),
            ("decoded_body", "decoded_length", "decoded_sha256"),
        ):
            raw = safe_path(directory, row[field]).read_bytes()
            assert (
                len(raw) == row[length]
                and hashlib.sha256(raw).hexdigest() == row[digest]
            ), "changed HTTP response evidence"
        wire = safe_path(directory, row["body"]).read_bytes()
        decoded = safe_path(directory, row["decoded_body"]).read_bytes()
        limit = ledger.get("limits", {}).get("max_body_bytes", 256000000)
        assert len(wire) <= limit and len(decoded) <= limit, (
            "recorded transport body bound"
        )
        if row["content_encoding"] == "gzip":
            with gzip.GzipFile(fileobj=BytesIO(wire)) as stream:
                expected = stream.read(len(decoded) + 1)
        else:
            assert row["content_encoding"] == "identity", "recorded transport encoding"
            expected = wire
        assert expected == decoded, (
            "decoded transport representation disagrees with raw entity"
        )
        path = urlsplit(row["target"]).path
        indexed.setdefault(path, []).append(row)
        previous = indexed[path][:-1]
        if not path.startswith("/api/search/"):
            assert all(
                p["status"] == row["status"]
                and p["decoded_sha256"] == row["decoded_sha256"]
                for p in previous
            ), "contradictory repeated source observation"
    return indexed


def coverage(directory, ledger, *, allow_missing=False):
    """Derive necessary requests from raw discovery, ownership and graph facts.

    This is the completeness oracle, not the converter's request list. Missing
    requirements can be acquired explicitly while the recorder remains open;
    sealing itself never invents or acquires evidence.
    """
    rows = observations(directory, ledger)
    brain = ledger["brain_id"]
    assert str(UUID(brain)) == brain and UUID(brain).int, "recorded Brain identity"
    missing = []

    def required(path, statuses=(200,)):
        found = rows.get(path)
        if not found:
            missing.append(
                path + ("?includeSiblings=true" if path.endswith("/graph") else "")
            )
            return None
        row = found[0]
        assert row["status"] in statuses, "required source HTTP outcome"
        return row

    def value(row):
        return read_json(
            safe_path(directory, row["decoded_body"]).read_bytes(), parse_float=Decimal
        )

    base = "/" + brain
    schema_row = required("/api/v1/docs.json")
    if schema_row:
        schema = value(schema_row)
        assert (
            schema["openapi"].startswith("3.")
            and type(schema["info"]["version"]) is str
        ), "current recorded OpenAPI evidence"
        for endpoint in (
            "/api/brains",
            "/api/brains/{brainId}",
            "/api/brains/{brainId}/statistics",
            "/api/search/{brainId}",
            "/api/thoughts/{brainId}/types",
            "/api/thoughts/{brainId}/tags",
            "/api/thoughts/{brainId}/{thoughtId}",
            "/api/thoughts/{brainId}/{thoughtId}/graph",
            "/api/thoughts/{brainId}/{thoughtId}/attachments",
            "/api/links/{brainId}/{linkId}",
            "/api/links/{brainId}/{linkId}/attachments",
            "/api/attachments/{brainId}/{attachmentId}/metadata",
            "/api/attachments/{brainId}/{attachmentId}/file-content",
            "/api/notes/{brainId}/{thoughtId}",
        ):
            assert "get" in schema["paths"][endpoint], (
                "recorded schema documents required GET"
            )
    accessible_row = required("/api/brains")
    brain_row = required("/api/brains" + base)
    types = required("/api/thoughts" + base + "/types")
    tags = required("/api/thoughts" + base + "/tags", (200, 400))
    statistics = rows.get("/api/brains" + base + "/statistics", [])
    if len(statistics) < 2:
        missing.extend(["/api/brains" + base + "/statistics"] * (2 - len(statistics)))
    searches = rows.get("/api/search" + base, [])
    if not searches:
        missing.append(
            "/api/search"
            + base
            + "?queryText=*&maxResults=5000&onlySearchThoughtNames=false"
        )
    candidates, relationship_ids = set(), set()
    if brain_row:
        collection = value(brain_row)
        assert collection["id"] == brain, "raw Brain ownership"
        candidates.add(collection["homeThoughtId"])
        if accessible_row:
            matches = [row for row in value(accessible_row) if row["id"] == brain]
            assert len(matches) == 1 and strict(matches[0]) == strict(collection), (
                "current accessible Brain identity"
            )
    for inventory in (types, tags):
        if inventory and inventory["status"] == 200:
            for row in value(inventory):
                assert row["brainId"] == brain, "definition namespace"
                candidates.add(row["id"])
    unsaturated = False
    for search in searches:
        assert search["status"] == 200, "required wildcard search"
        query = parse_qs(urlsplit(search["target"]).query, strict_parsing=True)
        assert query.get("queryText") == ["*"] and query.get(
            "onlySearchThoughtNames"
        ) == ["false"], "full wildcard search parameters"
        limit = query.get("maxResults", [])
        assert len(limit) == 1 and limit[0].isdigit() and int(limit[0]) > 0, (
            "bounded wildcard search"
        )
        hits = value(search)
        assert isinstance(hits, list), "raw wildcard response array"
        unsaturated |= len(hits) < int(limit[0])
        for hit in hits:
            assert hit.get("isFromOtherBrain") is False, "foreign discovery refused"
            for name, destination in (
                ("sourceThought", candidates),
                ("sourceLink", relationship_ids),
            ):
                item = hit.get(name)
                if item:
                    assert item["brainId"] == brain, "discovered source namespace"
                    destination.add(item["id"])
    if searches:
        assert unsaturated, "truncated or saturated wildcard discovery"

    thoughts, graphs, links, attachments = {}, {}, {}, {}
    # A wildcard result can expose only a link in a disconnected component.
    # Its authoritative endpoints must enter the thought frontier first.
    for key in tuple(relationship_ids):
        row = required("/api/links" + base + "/" + key)
        if row:
            edge = value(row)
            assert edge["id"] == key and edge["brainId"] == brain, (
                "discovered relationship namespace"
            )
            links[key] = edge
            candidates.update((edge["thoughtIdA"], edge["thoughtIdB"]))
    # Frontier growth is bounded by the retained response byte/request limits.
    pending = set(candidates)
    while pending:
        key = pending.pop()
        assert str(UUID(key)) == key and UUID(key).int, "canonical discovered thought"
        metadata = required("/api/thoughts" + base + "/" + key)
        if metadata is None:
            continue
        thought = value(metadata)
        assert thought["id"] == key and thought["brainId"] == brain, "thought namespace"
        assert type(thought["acType"]) is int and thought["acType"] == 0, (
            "private source metadata refuses content acquisition"
        )
        thoughts[key] = (thought, metadata)
        if thought["kind"] == 5 or thought["forgottenDateTime"] is not None:
            continue
        graph_row = required("/api/thoughts" + base + "/" + key + "/graph")
        if graph_row is None:
            continue
        graph = value(graph_row)
        assert strict(graph["activeThought"]) == strict(thought), (
            "same-counter thought/graph disagreement"
        )
        graphs[key] = graph_row
        for field in ("parents", "children", "jumps", "siblings", "tags"):
            assert isinstance(graph[field], list), "complete graph neighbor array"
            for neighbor in graph[field]:
                assert neighbor["brainId"] == brain, "neighbor namespace"
                if neighbor["id"] not in candidates:
                    candidates.add(neighbor["id"])
                    pending.add(neighbor["id"])
        if graph["type"]:
            provider = graph["type"]
            assert provider["brainId"] == brain, "provider namespace"
            if provider["id"] not in candidates:
                candidates.add(provider["id"])
                pending.add(provider["id"])
        for edge in graph["links"]:
            assert edge["brainId"] == brain, "relationship namespace"
            if edge["id"] in links:
                assert strict(links[edge["id"]]) == strict(edge), (
                    "contradictory graph relationship"
                )
            links[edge["id"]] = edge
            relationship_ids.add(edge["id"])
            for endpoint in (edge["thoughtIdA"], edge["thoughtIdB"]):
                if endpoint not in candidates:
                    candidates.add(endpoint)
                    pending.add(endpoint)
        inventory = required("/api/thoughts" + base + "/" + key + "/attachments")
        if inventory is None:
            continue
        owned = value(inventory)
        assert isinstance(owned, list), "authoritative attachment array"
        if graph["attachments"] is not None:
            assert strict(graph["attachments"]) == strict(owned), (
                "same-counter attachment disagreement"
            )
        for attachment in owned:
            assert attachment["sourceId"] == key and attachment["brainId"] == brain, (
                "raw attachment ownership"
            )
            assert attachment["id"] not in attachments, "unique owned attachment"
            attachments[attachment["id"]] = attachment
        if not any(a["isNotes"] for a in owned):
            required("/api/notes" + base + "/" + key)
    for key in relationship_ids:
        row = required("/api/links" + base + "/" + key)
        if row:
            edge = value(row)
            assert edge["id"] == key and edge["brainId"] == brain, (
                "standalone relationship ownership"
            )
            if key in links:
                assert strict(edge) == strict(links[key]), (
                    "same-counter relationship disagreement"
                )
            else:
                links[key] = edge
            if all(
                endpoint in thoughts
                for endpoint in (edge["thoughtIdA"], edge["thoughtIdB"])
            ) and all(
                thoughts[endpoint][0]["kind"] != 5
                and thoughts[endpoint][0]["forgottenDateTime"] is None
                for endpoint in (edge["thoughtIdA"], edge["thoughtIdB"])
            ):
                required("/api/links" + base + "/" + key + "/attachments", (200, 404))
    for key, attachment in attachments.items():
        metadata = required("/api/attachments" + base + "/" + key + "/metadata")
        if metadata:
            assert strict(value(metadata)) == strict(attachment), (
                "same-counter attachment metadata disagreement"
            )
        if attachment["type"] not in {2, 3, 8}:
            required(
                "/api/attachments" + base + "/" + key + "/file-content", (200, 404)
            )
    if not allow_missing:
        assert not missing, "missing required acquisition coverage"
    return missing, rows, thoughts, graphs, links, attachments


def build_baseline(directory, expected_sha256, *, qualification):
    """Seal one closed transcript into /2, without converter-derived facts."""
    directory = Path(directory)
    raw = (directory / "recording.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected_sha256, "recording changed"
    ledger = read_json(raw)
    assert (
        ledger["schema"] == "brz2obsidian.api-http-recording/1"
        and ledger["complete"] is True
        and not ledger["failures"]
    ), "incomplete recording cannot seal"
    _, rows, thoughts, graphs, links, attachments = coverage(directory, ledger)
    qualification.verify()
    files = {}

    def bind(name):
        raw = safe_path(directory, name).read_bytes()
        files[name] = {"length": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        return name

    bind("recording.json")
    for occurrence in ledger["occurrences"]:
        bind(occurrence["body"])
        bind(occurrence["decoded_body"])
    root = "/api/"
    brain = ledger["brain_id"]
    suffix = "/" + brain

    def path(endpoint, index=0):
        return rows[root + endpoint][index]["decoded_body"]

    def outcome(endpoint):
        row = rows[root + endpoint][0]
        return {"status": row["status"], "path": row["decoded_body"]}

    excluded = {
        key
        for key, (row, _) in thoughts.items()
        if row["kind"] == 5 or row["forgottenDateTime"] is not None
    }
    active_links = {
        key
        for key, row in links.items()
        if not excluded.intersection((row["thoughtIdA"], row["thoughtIdB"]))
    }
    # Separate direction controls retain their own source/Brain and file pins.
    prefix = "qualification/"
    control_manifest = prefix + "manifest-" + qualification.fingerprint + ".json"
    assert control_manifest not in {
        prefix + name for name in qualification.data["files"]
    }, "qualification manifest collision"
    limit = ledger.get("limits", {}).get("max_total_bytes", 1000000000)
    required_bytes = (
        sum(path.stat().st_size for path in directory.iterdir() if path.is_file())
        + sum(row["length"] for row in qualification.data["files"].values())
        + qualification.manifest_path.stat().st_size
    )
    assert required_bytes < limit, (
        "bound qualification evidence exceeds aggregate capture limit"
    )
    for name in qualification.data["files"]:
        target = safe_path(directory, prefix + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(qualification.bytes(name))
        bind(prefix + name)
    with safe_path(directory, control_manifest).open("xb") as stream:
        stream.write(qualification.manifest_path.read_bytes())
    bind(control_manifest)
    load_baseline(safe_path(directory, control_manifest), qualification.fingerprint)
    controls = [
        {
            **control,
            "graph": prefix + control["graph"],
            "evidence": [prefix + name for name in control["evidence"]],
        }
        for control in qualification.data["one_way_controls"]
    ]
    manifest = {
        "schema": "brz2obsidian.api-acceptance/2",
        "files": files,
        "brain": path("brains" + suffix),
        "scope": {
            "thought_ids": sorted(graphs),
            "relationship_ids": sorted(active_links),
            "attachment_ids": sorted(attachments),
        },
        "graphs": {key: row["decoded_body"] for key, row in graphs.items()},
        "types": path("thoughts" + suffix + "/types"),
        "tags": outcome("thoughts" + suffix + "/tags"),
        "statistics": [
            path("brains" + suffix + "/statistics", 0),
            path("brains" + suffix + "/statistics", -1),
        ],
        "link_attachments": {
            key: path("links" + suffix + "/" + key + "/attachments")
            for key in active_links
        },
        "link_attachment_outcomes": {
            key: rows[root + "links" + suffix + "/" + key + "/attachments"][0]["status"]
            for key in active_links
        },
        "relationship_metadata": {
            key: outcome("links" + suffix + "/" + key) for key in active_links
        },
        "no_notes": {
            key: path("notes" + suffix + "/" + key)
            for key in graphs
            if not any(
                a["sourceId"] == key and a["isNotes"] for a in attachments.values()
            )
        },
        "payloads": {
            key: outcome("attachments" + suffix + "/" + key + "/file-content")
            for key, row in attachments.items()
            if row["type"] not in {2, 3, 8}
        },
        "attachment_inventories": {
            key: path("thoughts" + suffix + "/" + key + "/attachments")
            for key in graphs
        },
        "attachment_metadata": {
            key: outcome("attachments" + suffix + "/" + key + "/metadata")
            for key in attachments
        },
        "scope_inputs": {
            "excluded_thoughts": {
                key: outcome("thoughts" + suffix + "/" + key) for key in excluded
            },
            "excluded_relationships": {
                key: outcome("links" + suffix + "/" + key)
                for key in links
                if key not in active_links
            },
        },
        "qualification": [
            path("v1/docs.json"),
            control_manifest,
            *[prefix + name for name in qualification.data["qualification"]],
        ],
        "one_way_controls": controls,
        "archive_matches": [],
        "http_responses": "recording.json",
    }
    manifest_size = len(
        (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
    )
    assert (
        sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())
        + manifest_size
        <= limit
    ), "complete baseline exceeds aggregate capture limit"
    pin = write_json(directory / "manifest.json", manifest)
    return load_baseline(directory / "manifest.json", pin)


def prepare_controls(directory):
    """Materialize the retained independent API3 source/control packet unchanged.

    This is explicit reused qualification provenance, not a new observation of
    the current API build or an invented graph in the reported Brain.
    """
    from .api_scope_inputs import mixed_source_packet

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    packet = mixed_source_packet()
    files = {}
    for name, raw in packet["files"].items():
        target = safe_path(directory, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
        files[name] = {"length": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    data = {
        "schema": "brz2obsidian.api-acceptance/2",
        "files": files,
        **packet["baseline_inputs"],
    }
    pin = write_json(directory / "manifest.json", data)
    return load_baseline(directory / "manifest.json", pin)


def verify_recorded_baseline(baseline):
    """Re-derive coverage and index bindings when a recorded baseline is audited.

    A separately pinned manifest closes bytes, not request coverage. Its source
    indexes must still be justified by the retained HTTP observations.
    """
    data = baseline.data
    ledger = baseline.json(data["http_responses"])
    assert (
        ledger["schema"] == "brz2obsidian.api-http-recording/1"
        and ledger["complete"] is True
        and not ledger["failures"]
    ), "incomplete recording cannot qualify"
    _, rows, thoughts, graphs, links, attachments = coverage(
        baseline.manifest_path.parent, ledger
    )
    base = "/api/"
    namespace = "/" + ledger["brain_id"]

    def path(endpoint, index=0):
        return rows[base + endpoint][index]["decoded_body"]

    def outcome(endpoint):
        row = rows[base + endpoint][0]
        return {"status": row["status"], "path": row["decoded_body"]}

    excluded = {
        key
        for key, (row, _) in thoughts.items()
        if row["kind"] == 5 or row["forgottenDateTime"] is not None
    }
    active = {
        key
        for key, row in links.items()
        if not excluded.intersection((row["thoughtIdA"], row["thoughtIdB"]))
    }
    expected = {
        "brain": path("brains" + namespace),
        "scope": {
            "thought_ids": sorted(graphs),
            "relationship_ids": sorted(active),
            "attachment_ids": sorted(attachments),
        },
        "graphs": {key: row["decoded_body"] for key, row in graphs.items()},
        "types": path("thoughts" + namespace + "/types"),
        "tags": outcome("thoughts" + namespace + "/tags"),
        "statistics": [
            path("brains" + namespace + "/statistics", 0),
            path("brains" + namespace + "/statistics", -1),
        ],
        "link_attachments": {
            key: path("links" + namespace + "/" + key + "/attachments")
            for key in active
        },
        "link_attachment_outcomes": {
            key: rows[base + "links" + namespace + "/" + key + "/attachments"][0][
                "status"
            ]
            for key in active
        },
        "relationship_metadata": {
            key: outcome("links" + namespace + "/" + key) for key in active
        },
        "no_notes": {
            key: path("notes" + namespace + "/" + key)
            for key in graphs
            if not any(
                a["sourceId"] == key and a["isNotes"] for a in attachments.values()
            )
        },
        "payloads": {
            key: outcome("attachments" + namespace + "/" + key + "/file-content")
            for key, row in attachments.items()
            if row["type"] not in {2, 3, 8}
        },
        "attachment_inventories": {
            key: path("thoughts" + namespace + "/" + key + "/attachments")
            for key in graphs
        },
        "attachment_metadata": {
            key: outcome("attachments" + namespace + "/" + key + "/metadata")
            for key in attachments
        },
        "scope_inputs": {
            "excluded_thoughts": {
                key: outcome("thoughts" + namespace + "/" + key) for key in excluded
            },
            "excluded_relationships": {
                key: outcome("links" + namespace + "/" + key)
                for key in links
                if key not in active
            },
        },
    }
    assert all(data[key] == value for key, value in expected.items()), (
        "baseline indexes disagree with independent HTTP evidence"
    )
    assert path("v1/docs.json") in data["qualification"], (
        "current schema qualification binding"
    )
    for row in ledger["occurrences"]:
        for field, length, digest in (
            ("body", "length", "sha256"),
            ("decoded_body", "decoded_length", "decoded_sha256"),
        ):
            assert data["files"][row[field]] == {
                "length": row[length],
                "sha256": row[digest],
            }, "HTTP occurrence file binding"
