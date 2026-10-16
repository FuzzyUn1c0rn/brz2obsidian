"""Independent API-bound preservation oracle. No converter modules are imported."""

import hashlib
import re
from decimal import Decimal
from html.parser import HTMLParser
from io import BytesIO
from itertools import pairwise
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import UUID
from zipfile import BadZipFile, ZipFile

from .api_image_proofs import ico_proof, jpeg_headers
from .api_manifest import read_json, safe_path
from .api_note_text import (
    document_references,
    expected_document_text,
    expected_note_text,
)
from .checker import escaped, source_references, wiki
from .images import AuditUnavailable, decode_image
from .text import active_mask, inline_candidates


def identities(rows, key, label):
    indexed = {row[key]: row for row in rows}
    assert len(indexed) == len(rows), label + " identities"
    return indexed


def semantic(value):
    """JSON equality keeps booleans distinct from integers in source evidence."""
    if isinstance(value, dict):
        return ("object", tuple(sorted((k, semantic(v)) for k, v in value.items())))
    if isinstance(value, list):
        return ("array", tuple(map(semantic, value)))
    return (type(value).__name__, value)


def attachment_evidence(value, limit):
    """Apply only the documented position projection to independent raw facts."""
    if "position" not in value:
        return value
    position = value["position"]
    assert type(position) in (int, Decimal), "attachment position source number"
    number = Decimal(position)
    assert number.is_finite(), "finite attachment position"
    if not number:
        text = "0"
    else:
        sign, digits, exponent = number.as_tuple()
        digits = list(digits)
        while digits[-1] == 0:
            digits.pop()
            exponent += 1
        point = len(digits) + exponent
        length = sign + (
            point if exponent >= 0 else len(digits) + 1 if point > 0 else 2 - exponent
        )
        assert length <= limit, "attachment position cannot fit retained evidence"
        coefficient = "".join(map(str, digits))
        if exponent >= 0:
            text = coefficient + "0" * exponent
        elif point > 0:
            text = coefficient[:point] + "." + coefficient[point:]
        else:
            text = "0." + "0" * -point + coefficient
        if sign:
            text = "-" + text
    return value | {"position": {"decimal": text}}


def uuid(value):
    assert type(value) is str and str(UUID(value)) == value and UUID(value).int, (
        "canonical source UUID"
    )
    return value


def neighbor(graph, field, key):
    return any(row["id"] == key for row in graph[field] or [])


def qualify_source(
    baseline, thoughts, links, attachments, graphs, *, profile_version="1"
):
    data = baseline.data
    brain = baseline.json(data["brain"])
    collection = uuid(brain["id"])
    home = brain["homeThoughtId"]
    assert home in thoughts and thoughts[home]["kind"] == 1, "included ordinary Home"
    for key, row in thoughts.items():
        uuid(key)
        assert (
            row["brainId"] == collection
            and type(row["kind"]) is int
            and row["kind"] in {1, 2, 4}
        ), "supported public role"
        assert (
            type(row["acType"]) is int
            and row["acType"] == 0
            and row["forgottenDateTime"] is None
        ), "public non-forgotten source"
    for key, row in attachments.items():
        uuid(key)
        assert row["brainId"] == collection, "attachment collection"
    types = identities(baseline.json(data["types"]), "id", "type inventory")
    tag_result = data["tags"]
    statistics = [baseline.json(p) for p in data["statistics"]]
    assert len(statistics) == 2, "starting/ending statistics"
    for stats in statistics:
        assert stats["brainId"] == collection, "statistics collection"
        for field in ("thoughts", "thoughtTypes", "tags", "forgottenThoughts", "links"):
            assert type(stats[field]) is int and stats[field] >= 0, "statistics count"
    assert all(
        statistics[0][k] == statistics[1][k]
        for k in ("thoughts", "thoughtTypes", "tags", "forgottenThoughts", "links")
    ), "source population drift"
    if tag_result["status"] == 400:
        assert (
            baseline.bytes(tag_result["path"]).decode("utf-8").strip()
            == "Could not retrieve list of Tags for brain " + collection
        ), "exact zero-tag failure"
        assert all(s["tags"] == 0 for s in statistics), "zero-tag corroboration"
        tags = {}
    else:
        assert tag_result["status"] == 200, "required tag inventory"
        tags = identities(baseline.json(tag_result["path"]), "id", "tag inventory")
    for inventory, role in ((types, 2), (tags, 4)):
        assert set(inventory) == {
            key for key, t in thoughts.items() if t["kind"] == role
        }, "definition inventory coverage"
        assert all(row == thoughts[key] for key, row in inventory.items()), (
            "definition inventory disagreement"
        )
    for field, role in (("thoughts", 1), ("thoughtTypes", 2), ("tags", 4)):
        assert statistics[0][field] == sum(
            t["kind"] == role for t in thoughts.values()
        ), "independent population mismatch"
    assert set(data["link_attachments"]) == set(links), (
        "link content inventory coverage"
    )
    for path in data["link_attachments"].values():
        assert baseline.json(path) == [], "unqualified link-owned content"
    for key, row in links.items():
        uuid(key)
        assert row["brainId"] == collection, "relationship collection"
        a, b = row["thoughtIdA"], row["thoughtIdB"]
        kind = row["meaning"]
        signature = tuple(row[k] for k in ("kind", "relation", "meaning", "direction"))
        if profile_version == "3" and signature == (1, 1, 1, 3):
            qualify_reverse_joins(baseline, row, thoughts, links, graphs)
        if kind in {2, 5}:
            assert neighbor(graphs[a], "children", b), (
                "classification source graph join"
            )
            if kind == 2:
                assert (
                    thoughts[b]["typeId"] == a
                    and graphs[b]["type"]
                    and graphs[b]["type"]["id"] == a
                ), "classification member graph join"
            else:
                assert neighbor(graphs[b], "tags", a), "tag member graph join"
        elif row["relation"] == 1:
            assert neighbor(graphs[a], "children", b) and neighbor(
                graphs[b], "parents", a
            ), "hierarchy graph join"
        else:
            assert neighbor(graphs[a], "jumps", b) and neighbor(
                graphs[b], "jumps", a
            ), "jump graph join"
    for key, row in thoughts.items():
        providers = [
            r["thoughtIdA"]
            for r in links.values()
            if r["meaning"] == 2 and r["thoughtIdB"] == key
        ]
        assert providers == ([row["typeId"]] if row["typeId"] else []), (
            "complete type field/link agreement"
        )
    authored = {a["sourceId"] for a in attachments.values() if a["isNotes"]}
    assert set(data["no_notes"]) == set(thoughts) - authored, (
        "no-note observation coverage"
    )
    for owner, path in data["no_notes"].items():
        wrapper = baseline.json(path)
        required = {
            "brainId": collection,
            "sourceId": owner,
            "sourceType": 2,
            "markdown": "",
            "html": None,
            "text": None,
            "modificationDateTime": "0001-01-01T00:00:00",
        }
        assert all(
            k in wrapper and wrapper[k] == value for k, value in required.items()
        ), "unqualified no-note observation"
    directions = set()
    for control in data["one_way_controls"]:
        evidence = control["evidence"]
        assert evidence and all(p in data["files"] for p in evidence), (
            "unbound native control"
        )
        assert control["destination_hides_source"] is True, (
            "unqualified one-way visibility"
        )
        graph = baseline.json(control["graph"])
        match = [r for r in graph["links"] if r["id"] == control["relationship_id"]]
        assert len(match) == 1, "independent one-way source relationship"
        link = match[0]
        direction = control["direction"]
        assert (link["kind"], link["relation"], link["meaning"], link["direction"]) == (
            1,
            3,
            1,
            direction,
        ), "qualified one-way signature"
        assert direction in {5, 7}, "qualified one-way direction"
        endpoints = (link["thoughtIdA"], link["thoughtIdB"])
        if direction == 7:
            endpoints = endpoints[::-1]
        assert endpoints == (control["source_id"], control["destination_id"]), (
            "independent one-way endpoint direction"
        )
        directions.add(direction)
    assert directions == {5, 7}, "missing independent one-way visibility control"
    assert data["qualification"] and all(
        p in data["files"] for p in data["qualification"]
    ), "unbound independent qualification"


def qualify_reverse_joins(baseline, row, thoughts, links, graphs):
    """Independent complete source observations for the new finite hierarchy."""
    data = baseline.data
    key = row["id"]
    outcome = data.get("relationship_metadata", {}).get(key)
    assert isinstance(outcome, dict) and type(outcome.get("status")) is int, (
        "reverse hierarchy metadata outcome"
    )
    assert outcome["status"] == 200, "reverse hierarchy metadata outcome"
    metadata = read_json(baseline.bytes(outcome["path"]), parse_float=Decimal)
    assert semantic(metadata) == semantic(row), (
        "reverse hierarchy metadata disagreement"
    )
    status = data.get("link_attachment_outcomes", {}).get(key)
    assert type(status) is int and status == 200, "reverse hierarchy content outcome"
    for owner in (row["thoughtIdA"], row["thoughtIdB"]):
        graph = graphs[owner]
        incident = [
            r["id"]
            for r in graph["links"]
            if owner in (r["thoughtIdA"], r["thoughtIdB"])
        ]
        required = {
            r["id"]
            for r in links.values()
            if owner in (r["thoughtIdA"], r["thoughtIdB"])
        }
        assert len(incident) == len(set(incident)) and set(incident) == required, (
            "reverse hierarchy endpoint relationship inventory"
        )
        expected = {"parents": set(), "children": set(), "jumps": set(), "tags": set()}
        for link in links.values():
            a, b = link["thoughtIdA"], link["thoughtIdB"]
            if link["meaning"] == 1 and link["relation"] == 1:
                if a == owner:
                    expected["children"].add(b)
                if b == owner:
                    expected["parents"].add(a)
            elif link["meaning"] == 1 and link["relation"] == 3 and owner in {a, b}:
                expected["jumps"].add(b if owner == a else a)
            elif link["meaning"] == 5 and b == owner:
                expected["tags"].add(a)
        for field in (*expected, "siblings"):
            assert type(graph.get(field)) is list, "required reverse graph array"
        for field, wanted in expected.items():
            observed = graph[field]
            keys = [n["id"] for n in observed]
            assert len(keys) == len(set(keys)), "duplicate reverse graph neighbor"
            assert all(
                n["id"] in thoughts and semantic(n) == semantic(thoughts[n["id"]])
                for n in observed
            ), "reverse graph neighbor metadata disagreement"
            provider = thoughts[owner]["typeId"]
            if field == "parents" and provider and provider in keys:
                wanted.add(provider)
            assert set(keys) == wanted, "unexplained reverse graph adjacency"
        provider = thoughts[owner]["typeId"]
        assert semantic(graph["type"]) == semantic(
            thoughts[provider] if provider else None
        ), "reverse graph type declaration"


def source_facts(baseline, *, profile_version="1"):
    assert profile_version in {"1", "2", "3"}, "unsupported API profile version"
    baseline.verify()
    data = baseline.data
    for values in data["scope"].values():
        assert len(values) == len(set(values)), "duplicate independent scoped identity"
        for value in values:
            uuid(value)
    thoughts, links, attachments, graphs = {}, {}, {}, {}
    assert set(data["graphs"]) == set(data["scope"]["thought_ids"]), (
        "baseline thought coverage"
    )
    for key, path in data["graphs"].items():
        graph = read_json(baseline.bytes(path), parse_float=Decimal)
        graphs[key] = graph
        thought = graph["activeThought"]
        assert thought["id"] == key, "baseline thought identity"
        thoughts[key] = thought
        inventory = graph["attachments"]
        if inventory is None:
            assert key in data.get("attachment_inventories", {}), (
                "missing authoritative attachment inventory"
            )
            inventory = read_json(
                baseline.bytes(data["attachment_inventories"][key]), parse_float=Decimal
            )
        assert type(inventory) is list, "malformed authoritative attachment inventory"
        for attachment in inventory:
            assert attachment["sourceId"] == key and attachment["sourceType"] == 2, (
                "raw attachment owner"
            )
            assert attachment["id"] not in attachments, "raw attachment identities"
            attachments[attachment["id"]] = attachment
        assert type(graph["links"]) is list, "required graph relationship array"
        for row in graph["links"]:
            if row["id"] in links:
                assert semantic(links[row["id"]]) == semantic(row), (
                    "conflicting raw relationship"
                )
            links[row["id"]] = row
    assert set(links) == set(data["scope"]["relationship_ids"]), (
        "baseline relationship coverage"
    )
    expected = {}
    for key, row in links.items():
        a, b = row["thoughtIdA"], row["thoughtIdB"]
        assert a in thoughts and b in thoughts and a != b, "raw relationship endpoints"
        signature = tuple(row[k] for k in ("kind", "relation", "meaning", "direction"))
        assert all(type(v) is int for v in signature), "raw relationship integers"
        assert row["typeId"] is None, "unsupported custom relationship type"
        if signature in {(1, 1, 1, -1), (1, 1, 1, 1)}:
            kind = "hierarchy"
        elif profile_version == "3" and signature == (1, 1, 1, 3):
            assert (thoughts[a]["kind"], thoughts[b]["kind"]) == (1, 1), (
                "reverse hierarchy requires ordinary endpoints"
            )
            kind = "hierarchy"
        elif signature in {(1, 3, 1, -1), (1, 3, 1, 3), (1, 3, 1, 5), (1, 3, 1, 7)}:
            kind = "related"
        elif signature == (1, 1, 2, -1):
            assert (thoughts[a]["kind"], thoughts[b]["kind"]) == (2, 1), (
                "classification roles"
            )
            kind = "classification"
        elif signature == (1, 1, 5, -1):
            assert thoughts[a]["kind"] == 4, "tag role"
            kind = "tag"
        else:
            raise AssertionError("unqualified raw relationship signature")
        expected[key] = {"key": key, "kind": kind, "item_a": a, "item_b": b}
    assert set(attachments) == set(data["scope"]["attachment_ids"]), (
        "baseline attachment coverage"
    )
    qualify_source(
        baseline, thoughts, links, attachments, graphs, profile_version=profile_version
    )
    if profile_version == "3":
        qualify_image_joins(baseline, attachments, graphs)
    return thoughts, expected, attachments, links


def new_image_ids(baseline, attachments):
    """Scope obligations from original declarations/bytes, never output roles."""
    selected = set()
    for key, row in attachments.items():
        if row["type"] == 12 and row["location"].endswith(".jpg"):
            selected.add(key)
        elif row["type"] == 5:
            outcome = baseline.data["payloads"].get(key, {})
            if outcome.get("status") == 200 and baseline.bytes(
                outcome["path"]
            ).startswith(b"\x00\x00\x01\x00"):
                selected.add(key)
    return selected


def qualify_image_joins(baseline, attachments, graphs):
    for key in new_image_ids(baseline, attachments):
        row = attachments[key]
        owner = row["sourceId"]
        outcome = baseline.data.get("attachment_metadata", {}).get(key)
        assert (
            isinstance(outcome, dict)
            and type(outcome.get("status")) is int
            and outcome["status"] == 200
        ), "image authoritative metadata outcome"
        metadata = read_json(baseline.bytes(outcome["path"]), parse_float=Decimal)
        assert semantic(metadata) == semantic(row), "image metadata disagreement"
        inventory_path = baseline.data.get("attachment_inventories", {}).get(owner)
        assert inventory_path, "image authoritative list observation"
        rows = read_json(baseline.bytes(inventory_path), parse_float=Decimal)
        assert type(rows) is list, "image authoritative list shape"
        indexed = identities(rows, "id", "image list")
        expected = {k: a for k, a in attachments.items() if a["sourceId"] == owner}
        assert semantic(indexed) == semantic(expected), "image list disagreement"
        if graphs[owner]["attachments"] is not None:
            assert semantic(
                identities(graphs[owner]["attachments"], "id", "image graph")
            ) == semantic(expected), "image graph/list disagreement"
        icons = [a for a in expected.values() if a["type"] == 5]
        assert len(icons) <= 1, "unique source icon declaration"


def check_new_image_preservation(
    baseline, vault, record, thoughts, attachments, targets, assets
):
    selected = new_image_ids(baseline, attachments)
    if not selected:
        return
    for key in selected:
        assert (
            safe_path(vault, assets[key]["relative_path"]).name
            == attachments[key]["location"]
        ), "source image/icon actual filename"
    paths = [assets[key]["relative_path"].casefold() for key in selected]
    assert len(paths) == len(set(paths)), "distinct image/icon storage identities"
    # Raw declarations determine all binding roles. Assigned paths are checked
    # separately for source bytes before they are used to locate rendered text.
    bindings = {}
    for key, row in attachments.items():
        role, _, _ = expected_asset(baseline, row, "3")
        bindings[key] = {
            "asset_id": key,
            "owner": row["sourceId"],
            "role": role,
            "original_name": row["location"],
            "relative_path": assets[key]["relative_path"],
        }
    documents = identities(record.get("documents", []), "key", "image document")
    authored = {k: row for k, row in attachments.items() if row["isNotes"]}
    assert set(documents) == set(authored), "all image-bearing source documents"
    names = {key: row["relative_path"] for key, row in targets.items()}
    for key, row in authored.items():
        original = baseline.bytes(baseline.data["payloads"][key]["path"]).decode(
            "utf-8"
        )
        body = expected_document_text(original)
        digest = hashlib.sha256(body.encode()).hexdigest()
        document = documents[key]
        assert (
            document["owner"],
            document["original_asset_id"],
            document["text_digest"],
            document["owner_target"],
        ) == (row["sourceId"], key, digest, names[row["sourceId"]]), (
            "image document source binding"
        )
        expected = document_references(body, row["sourceId"], bindings)
        references = document["references"]
        assert len(references) == len(expected), "all source image references"
        for emitted, source in zip(references, expected, strict=True):
            for field in (
                "start",
                "end",
                "kind",
                "target",
                "destination_start",
                "destination_end",
                "presentation_normalization",
            ):
                assert emitted[field] == source[field], (
                    "image reference spans/target/presentation"
                )
            assert emitted["display_text"] == source["label"], (
                "image reference alt text"
            )
            assert (
                emitted["expected_original"] == body[source["start"] : source["end"]]
                and emitted["document_digest"] == digest
            ), "image reference source text"
            assert (
                emitted["source_target"]
                == body[source["destination_start"] : source["destination_end"]]
            ), "image source destination"
        owner = row["sourceId"]
        assert targets[owner]["created"] is True, "owned note materialization"
        expected_text = expected_note_text(
            original, owner, names[owner], names, bindings
        )
        generated = safe_path(vault, names[owner]).read_text(encoding="utf-8")
        expected_activity = active_mask(expected_text)
        actual_activity = active_mask(generated)
        positions = [
            match.start() for match in re.finditer(re.escape(expected_text), generated)
        ]
        assert any(
            all(
                actual_activity[start + index] == char
                for index, char in enumerate(expected_activity)
                if not char.isspace()
            )
            for start in positions
        ), "complete active generated image prose/order/alt/title/sizing"
    icons = {
        row["sourceId"]: key for key, row in attachments.items() if row["type"] == 5
    }
    image_owners = {
        attachments[key]["sourceId"]
        for key in selected
        if attachments[key]["type"] == 12
    }
    for owner in image_owners:
        assert (
            targets[owner]["created"] is True
            and safe_path(vault, names[owner]).is_file()
        ), "owned unreferenced image materialization"
    for owner, thought in thoughts.items():
        explicit = icons.get(owner)
        provider = thought["typeId"]
        effective = explicit or icons.get(provider)
        if not (explicit or effective):
            continue
        graph = baseline.json(baseline.data["graphs"][owner])
        owned = [a for a in bindings.values() if a["owner"] == owner]
        isolated_icon = (
            thought["kind"] == 1
            and owner != baseline.json(baseline.data["brain"])["homeThoughtId"]
            and not provider
            and owned
            and all(a["role"] == "icon" for a in owned)
            and not any(
                r["relation"] == 1 and r["meaning"] == 1 for r in graph["links"]
            )
        )
        if isolated_icon:
            assert (
                targets[owner]["created"] is False
                and not safe_path(vault, names[owner]).exists()
            ), "decorative-only owner remains uncreated"
        declaration = targets[owner].get("declared_appearance")
        assert (declaration or {}).get("icon_asset_id") == explicit, (
            "source declared icon ownership"
        )
        if targets[owner]["created"]:
            snapshot = targets[owner].get("icon_snapshot")
            assert snapshot == {
                "item_key": owner,
                "explicit_icon_asset_id": explicit,
                "appearance_category_key": provider,
                "effective_icon_asset_id": effective,
            }, "source effective explicit/inherited icon"


def external_projection(baseline, attachment, profile_version):
    """Qualify raw source joins and derive a URI without touching its target."""
    assert profile_version == "3", "external family profile"
    assert type(attachment["type"]) is int and attachment["type"] in {2, 8}, (
        "external type"
    )
    assert (
        attachment.get("isNotes") is False
        and "name" in attachment
        and attachment["name"] is None
    ), "external declaration"
    assert (
        type(attachment.get("sourceType")) is int and attachment["sourceType"] == 2
    ), "external owner type"
    key, owner = uuid(attachment["id"]), uuid(attachment["sourceId"])
    thoughts, _, attachments, _ = source_facts(
        baseline, profile_version=profile_version
    )
    assert (
        owner in thoughts
        and key in attachments
        and semantic(attachment) == semantic(attachments[key])
    ), "external scoped declaration"
    inventories = baseline.data.get("attachment_inventories", {})
    assert owner in inventories, "external authoritative owner inventory"
    rows = read_json(baseline.bytes(inventories[owner]), parse_float=Decimal)
    assert type(rows) is list, "external owner inventory shape"
    graph = read_json(
        baseline.bytes(baseline.data["graphs"][owner]), parse_float=Decimal
    )
    observed = graph["attachments"]
    assert len({row["id"] for row in rows}) == len(rows), (
        "external inventory duplicate identity"
    )
    if observed is not None:
        assert type(observed) is list and {
            row["id"]: semantic(row) for row in rows
        } == {row["id"]: semantic(row) for row in observed}, (
            "external graph/list inventory agreement"
        )
    matches = [row for row in rows if row["id"] == key]
    assert len(matches) == 1 and semantic(matches[0]) == semantic(attachment), (
        "external list agreement"
    )
    outcome = baseline.data.get("attachment_metadata", {}).get(key)
    assert outcome and type(outcome["status"]) is int and outcome["status"] == 200, (
        "external metadata outcome"
    )
    metadata = read_json(baseline.bytes(outcome["path"]), parse_float=Decimal)
    assert semantic(metadata) == semantic(attachment), "external metadata agreement"
    assert key not in baseline.data["payloads"], "external must have no payload outcome"
    location = attachment["location"]
    assert type(location) is str and re.match(r"^[A-Za-z]:[\\/]", location), (
        "external absolute drive path"
    )
    parts = re.split(r"[\\/]", location[3:])
    assert parts and all(parts), "external nonempty path segments"
    for part in parts:
        assert part not in {".", ".."} and not part.endswith((" ", ".")), (
            "external segment ending"
        )
        assert not any(ord(c) < 32 or c in '<>:"|?*' for c in part), (
            "external path characters"
        )
        assert not re.fullmatch(
            r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.IGNORECASE
        ), "external reserved segment"
        assert part not in {".", ".."} and not part.endswith((" ", ".")), (
            "external segment ending"
        )
        assert not any(ord(c) < 32 or c in '<>:"|?*' for c in part), (
            "external path characters"
        )
        assert not re.fullmatch(
            r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.IGNORECASE
        ), "external reserved segment"
    uri = "file:///" + quote(location[:2] + "/" + "/".join(parts), safe="/:")
    return ("file" if attachment["type"] == 2 else "directory"), parts[-1], uri


def expected_asset(baseline, attachment, profile_version="1", proofs=None):
    assert profile_version in {"1", "2", "3"}, "unsupported API profile version"
    if profile_version == "3":
        assert (
            type(attachment["sourceType"]) is int and attachment["sourceType"] == 2
        ), "raw attachment source type"
        uuid(attachment["id"])
        collection = uuid(attachment["brainId"])
        owner = uuid(attachment["sourceId"])
        assert collection == baseline.json(baseline.data["brain"])["id"], (
            "attachment collection"
        )
        assert owner in baseline.data["graphs"], "included attachment owner"
    kind, note = attachment["type"], attachment["isNotes"]
    assert type(kind) is int and type(note) is bool, "raw attachment role"
    if kind in {2, 8}:
        role, _, _ = external_projection(baseline, attachment, profile_version)
        return role, "external", None
    name = attachment["location"]
    display = attachment["name"]
    assert display is None or type(display) is str and display, (
        "raw attachment display name"
    )
    if kind == 3 and not note:
        uri = urlsplit(name)
        assert (
            uri.scheme.lower() in {"http", "https"}
            and uri.netloc
            and not any(ord(c) <= 32 or ord(c) == 127 for c in name)
        ), "raw external URI"
        return "url", "external", None
    assert name and name not in {".", ".."} and name.strip() == name, (
        "raw attachment basename"
    )
    assert not any(c in name for c in "/\\:%") and not any(
        ord(c) < 32 or ord(c) == 127 for c in name
    ), "raw attachment basename"
    if note:
        assert kind == 1 and name == "Notes.md" and display is None, "raw note role"
        role = "note_original"
    elif kind == 12:
        assert (
            name == attachment["id"] + ".webp"
            or profile_version in {"2", "3"}
            and name == attachment["id"] + ".png"
            or profile_version == "3"
            and name == uuid(attachment["id"]) + ".jpg"
        ) and display is None, "raw image role"
        role = "image"
    elif kind == 5:
        assert name == "Icon.png" and display is None, "raw icon role"
        role = "icon"
    else:
        suffixes = (
            (".pdf", ".png", ".zip") if profile_version in {"2", "3"} else (".pdf",)
        )
        assert (
            kind == 1
            and name.lower().endswith(suffixes)
            or kind == 15
            and name.lower().endswith(".txt")
        ), "raw file role"
        if kind == 1 and not name.lower().endswith(".pdf"):
            assert display is None, "profile2 resource explicit null name"
        role = "file"
    outcome = baseline.data["payloads"][attachment["id"]]
    if profile_version == "3":
        assert type(outcome["status"]) is int, "actual HTTP payload status"
    if outcome["status"] == 404:
        assert kind == 15 and not note, "unqualified missing payload"
        return role, "absent", None
    assert outcome["status"] == 200, "required payload unavailable"
    payload = baseline.bytes(outcome["path"])
    if note or kind == 15:
        payload.decode("utf-8", errors="strict")
    elif kind == 12:
        if name.endswith(".png"):
            qualify_v2_bytes(payload, "PNG", attachment["id"], proofs)
        elif name.endswith(".jpg"):
            jpeg_headers(payload)
            qualify_v2_bytes(payload, "JPEG", attachment["id"], proofs)
        else:
            assert payload[:4] == b"RIFF" and payload[8:12] == b"WEBP", (
                "raw image signature"
            )
    elif kind == 5:
        if profile_version == "3" and payload.startswith(b"\x00\x00\x01\x00"):
            proof = ico_proof(payload)
            if proofs is not None:
                proofs[attachment["id"]] = proof
        elif profile_version in {"2", "3"} and payload.startswith(b"\xff\xd8\xff"):
            qualify_v2_bytes(payload, "JPEG", attachment["id"], proofs)
        else:
            assert payload.startswith(b"\x89PNG\r\n\x1a\n"), "raw icon signature"
    else:
        if name.lower().endswith(".png"):
            qualify_v2_bytes(payload, "PNG", attachment["id"], proofs)
        elif name.lower().endswith(".zip"):
            qualify_v2_bytes(payload, "ZIP", attachment["id"], proofs)
        else:
            assert payload.startswith(b"%PDF-"), "raw PDF signature"
    return role, "present", payload


def qualify_v2_bytes(payload, format_name, asset_id, proofs):
    digest = hashlib.sha256(payload).hexdigest()
    if proofs is not None and asset_id in proofs:
        assert (
            proofs[asset_id]["source_sha256"] == digest
            and proofs[asset_id]["format"] == format_name
        ), "resource eligibility changed"
        return
    if format_name == "ZIP":
        assert payload.startswith(b"PK\x03\x04"), "profile2 ZIP signature"
        try:
            with ZipFile(BytesIO(payload)) as archive:
                entries = archive.infolist()
                assert 0 <= archive.start_dir < len(payload), (
                    "profile2 ZIP central directory"
                )
                proof = {
                    "format": "ZIP",
                    "source_sha256": digest,
                    "status": "central-directory-valid",
                    "members": len(entries),
                    "members_extracted": 0,
                    "member_crc_checked": False,
                }
        except (BadZipFile, UnicodeError, ValueError) as exc:
            raise AssertionError("profile2 ZIP central directory") from exc
        except MemoryError as exc:
            raise AuditUnavailable("ZIP directory memory unavailable") from exc
    else:
        if format_name == "JPEG":
            assert (
                payload.startswith(b"\xff\xd8\xff") and payload.rfind(b"\xff\xd9") >= 3
            ), "profile2 JPEG completeness"
        proof = decode_image(
            payload, "measured.png" if format_name == "PNG" else "measured.jpg"
        )
        assert proof["format"] == format_name and proof["source_sha256"] == digest, (
            "profile2 measured decoder classification"
        )
    if proofs is not None:
        proofs[asset_id] = proof


def has_measured_pdf(baseline, attachments, owner, profile_version, proofs):
    for attachment in attachments.values():
        if (
            attachment["sourceId"] == owner
            and attachment["type"] == 1
            and not attachment["isNotes"]
            and attachment["location"].lower().endswith(".pdf")
        ):
            role, availability, payload = expected_asset(
                baseline, attachment, profile_version, proofs
            )
            if (
                role == "file"
                and availability == "present"
                and payload.startswith(b"%PDF-")
            ):
                return True
    return False


def audit_baseline(baseline, *, profile_version="1"):
    """Qualify every scoped raw fact/outcome before any conversion takes place."""
    thoughts, relationships, attachments, _ = source_facts(
        baseline, profile_version=profile_version
    )
    assert profile_version in {"1", "2", "3"}, "unsupported API profile version"
    local = {
        key
        for key, a in attachments.items()
        if a["type"] not in {2, 3, 8}
        or expected_asset(baseline, a, profile_version)[1] != "external"
    }
    assert set(baseline.data["payloads"]) == local, "baseline payload coverage"
    present, absent, proofs, bindings = 0, 0, {}, {}
    for attachment in attachments.values():
        role, availability, _ = expected_asset(
            baseline, attachment, profile_version, proofs
        )
        bindings[attachment["id"]] = {
            "asset_id": attachment["id"],
            "owner": attachment["sourceId"],
            "role": role,
            "original_name": attachment["location"],
        }
        present += availability == "present"
        absent += availability == "absent"
        if availability == "absent":
            assert has_measured_pdf(
                baseline, attachments, attachment["sourceId"], profile_version, proofs
            ), "missing TXT lacks measured same-owner PDF"
    # This independent parser consumes only raw Markdown and owner/role/name
    # dictionaries. API DTOs and API outcomes remain the source oracle; no BRZ
    # flags, path maps, absent-note interpretation or archive scope is reused.
    for attachment in attachments.values():
        if attachment["isNotes"]:
            body = baseline.bytes(
                baseline.data["payloads"][attachment["id"]]["path"]
            ).decode("utf-8")
            if profile_version == "3":
                # Validate authored grammar before protecting generated code.
                body = expected_document_text(body)
            scanner = (
                document_references if profile_version == "3" else source_references
            )
            references = scanner(body, attachment["sourceId"], bindings)
            assert all(
                r["target"] in thoughts for r in references if r["kind"] == "item"
            ), "included API note reference target"
    matches = identities(
        baseline.data["archive_matches"], "attachment_id", "archive match"
    )
    for key, match in matches.items():
        assert key in attachments, "archive match attachment identity"
        _, availability, payload = expected_asset(
            baseline, attachments[key], profile_version, proofs
        )
        assert availability == "present", (
            "archive cannot invent current API availability"
        )
        assert match["archive"] in baseline.data["files"], "unbound original archive"
        with ZipFile(
            safe_path(baseline.manifest_path.parent, match["archive"])
        ) as archive:
            assert archive.namelist().count(match["member"]) == 1, (
                "archive match member identity"
            )
            assert archive.read(match["member"]) == payload, (
                "archive/live byte equivalence"
            )
    baseline.verify()
    summary = {
        "thoughts": len(thoughts),
        "relationships": len(relationships),
        "classifications": sum(
            r["kind"] == "classification" for r in relationships.values()
        ),
        "attachments": len(attachments),
        "payloads": present,
        "reviewed_gaps": absent,
        "archive_matches": len(matches),
        "live_only_payloads": present - len(matches),
    }
    if profile_version in {"2", "3"}:
        summary["resource_eligibility"] = proofs
    return summary


def check_reverse_navigation(
    baseline, vault, thoughts, expected, raw_links, attachments, targets, assets
):
    """Audit every generated navigation section after the trusted authored region."""
    owners = {
        owner
        for row in raw_links.values()
        if tuple(row[k] for k in ("kind", "relation", "meaning", "direction"))
        == (1, 1, 1, 3)
        for owner in (row["thoughtIdA"], row["thoughtIdB"])
    }
    if not owners:
        return
    # Source facts establish mandatory notes before deterministic edge coverage.
    # This audit remains scoped to new reverse endpoints; all hierarchy edges
    # participate because another edge can determine which empty parent is chosen.
    selected = {baseline.json(baseline.data["brain"])["homeThoughtId"]}
    selected.update(key for key, row in thoughts.items() if row["kind"] == 2)
    selected.update(
        row["item_b"] for row in expected.values() if row["kind"] == "classification"
    )
    for key, attachment in attachments.items():
        if attachment["isNotes"]:
            text = baseline.bytes(baseline.data["payloads"][key]["path"]).decode(
                "utf-8"
            )
            if text.strip():
                selected.add(attachment["sourceId"])
        else:
            asset = assets[
                key
            ]  # independently checked against the raw declaration/bytes
            if (
                asset["availability"] == "external"
                and asset["role"] in {"file", "url", "directory"}
            ) or (
                asset["availability"] == "present"
                and asset["role"] in {"file", "image"}
                and asset["actual_length"] > 0
            ):
                selected.add(attachment["sourceId"])
    edges = [
        (row["item_a"], row["item_b"])
        for row in expected.values()
        if row["kind"] == "hierarchy"
    ]
    pending = [(a, b) for a, b in edges if a not in selected and b not in selected]
    while pending:
        # Most uncovered incident edges first, then canonical parent identity.
        counts = {
            parent: sum(parent in {a, b} for a, b in pending)
            for parent in {a for a, b in pending}
        }
        selected.add(min(counts, key=lambda key: (-counts[key], key)))
        pending = [(a, b) for a, b in edges if a not in selected and b not in selected]
    pattern = re.compile(
        r"^## (Parents|Children|Related)\n\n((?:- \[\[[^\n]+\]\]\n)+)", re.MULTILINE
    )
    for owner in owners:
        target = targets[owner]
        assert type(target.get("created")) is bool and target["created"] == (
            owner in selected
        ), "reverse hierarchy note materialization"
        path = safe_path(vault, target["relative_path"])
        if owner not in selected:
            assert not path.exists(), "uncreated reverse hierarchy note exists"
            continue
        assert path.is_file(), "reverse hierarchy generated note unavailable"
        body = path.read_text(encoding="utf-8")
        title = "# " + escaped(thoughts[owner]["name"]) + "\n"
        title = title.replace("\r\n", "\n").replace("\r", "\n")
        start = body.find(title)
        assert start >= 0, "reverse hierarchy generated note title unavailable"
        cursor = start + len(title)
        authored = []
        if thoughts[owner].get("label"):
            authored.append(thoughts[owner]["label"])
        names = {key: value.get("relative_path") for key, value in targets.items()}
        for attachment in attachments.values():
            if attachment["sourceId"] == owner and attachment["isNotes"]:
                note = baseline.bytes(
                    baseline.data["payloads"][attachment["id"]]["path"]
                ).decode("utf-8")
                authored.append(
                    expected_note_text(
                        note, owner, target["relative_path"], names, assets
                    )
                )
        for source in authored:
            text = source.replace("\r\n", "\n").replace("\r", "\n")
            if text:
                position = body.find(text, cursor)
                assert position >= 0, "reverse hierarchy authored content unavailable"
                cursor = position + len(text)
        # Authored labels/prose/headings cannot stand in for generated links.
        body = body[cursor:]
        footer = "## Categories\n\n[[Categories.md|Browse categories]]"
        if owner == baseline.json(baseline.data["brain"])[
            "homeThoughtId"
        ] and body.rstrip().endswith(footer):
            body = body.rstrip()[: -len(footer)] + "\n"
        matches = list(pattern.finditer(body))
        assert matches and not body[matches[-1].end() :].strip(), (
            "reverse hierarchy generated navigation unavailable"
        )
        headings = list(
            re.finditer(
                r"^ {0,3}#{1,6}[ \t]+(?:Parents|Children|Related)\b[^\n]*",
                body,
                re.MULTILINE | re.IGNORECASE,
            )
        )
        assert len(headings) == len(matches) and all(
            heading.start() == match.start()
            for heading, match in zip(headings, matches)
        ), "unestablished generated relationship section"
        assert all(
            not body[left.end() : right.start()].strip()
            for left, right in pairwise(matches)
        ), "unexpected prose between generated relationship sections"
        sections = {}
        for match in matches:
            heading = match.group(1)
            assert heading not in sections, "duplicate generated relationship section"
            sections[heading] = match.group(2)
        for heading in ("Parents", "Children"):
            wanted = {
                r["item_a"] if heading == "Parents" else r["item_b"]
                for r in expected.values()
                if r["kind"] == "hierarchy"
                and r["item_b" if heading == "Parents" else "item_a"] == owner
            }
            required = "".join(
                "- " + wiki(targets[key]["relative_path"], thoughts[key]["name"]) + "\n"
                for key in sorted(wanted)
            )
            assert sections.get(heading, "") == required, (
                "reverse hierarchy generated Parents/Children navigation"
            )


def check_external_resources(
    baseline, vault, thoughts, attachments, targets, assets, profile_version
):
    """Bind generated Resources references to their independently qualified owner."""

    class FileHTML(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.file_target = False

        def handle_starttag(self, tag, attrs):
            if tag in {"a", "iframe", "img", "object", "embed"}:
                self.file_target |= any(
                    name in {"href", "src", "data"}
                    and value is not None
                    and value.lstrip().lower().startswith("file:")
                    for name, value in attrs
                )

    owners = {a["sourceId"] for a in attachments.values() if a["type"] in {2, 8}}
    for owner in owners:
        target = targets[owner]
        assert target.get("created") is True, "external resource owner must materialize"
        path = safe_path(vault, target["relative_path"])
        assert path.is_file(), "external resource note unavailable"
        body = path.read_text(encoding="utf-8")
        title = (
            ("# " + escaped(thoughts[owner]["name"]) + "\n")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )
        start = body.find(title)
        assert start >= 0, "external resource note title"
        cursor = start + len(title)
        authored = [thoughts[owner]["label"]] if thoughts[owner].get("label") else []
        for attachment in attachments.values():
            if attachment["sourceId"] == owner and attachment["isNotes"]:
                raw = baseline.bytes(
                    baseline.data["payloads"][attachment["id"]]["path"]
                ).decode("utf-8")
                authored.append(
                    expected_note_text(
                        raw,
                        owner,
                        target["relative_path"],
                        {key: row.get("relative_path") for key, row in targets.items()},
                        assets,
                    )
                )
        metadata_span = None
        for index, text in enumerate(authored):
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            if text:
                position = body.find(text, cursor)
                assert position >= 0, "external resource authored content unavailable"
                if index == 0 and thoughts[owner].get("label"):
                    metadata_span = (position, position + len(text))
                cursor = position + len(text)
        syntax = list(body)
        if metadata_span is not None:
            begin, end = metadata_span
            # Thought labels are metadata. Closed declarations retain their raw
            # output but are opaque to the stricter authored-note HTML policy.
            # Comments and trailing code/comment guards keep their ownership.
            for token in re.finditer(
                r"<!--.*?(?:-->|$)|<![A-Za-z][^>]*>", body[begin:end], re.DOTALL
            ):
                if token[0].startswith("<!--"):
                    continue
                for offset in range(begin + token.start(), begin + token.end()):
                    syntax[offset] = "\n" if body[offset] == "\n" else " "
        syntax = "".join(syntax)
        tail = body[cursor:]
        mask = active_mask(syntax, autolinks=False)
        activity = "".join(
            "\n" if raw == "\n" else active
            for raw, active in zip(body, mask, strict=True)
        )[cursor:]
        headings = list(
            re.finditer(
                r"^ {0,3}#{1,6}[ \t]+Resources\b[^\n]*",
                activity,
                re.MULTILINE | re.IGNORECASE,
            )
        )
        assert len(headings) == 1 and headings[0].group() == "## Resources", (
            "external generated Resources section"
        )
        section_start = headings[0].end()
        following = re.search(r"^## ", activity[section_start:], re.MULTILINE)
        section_end = section_start + following.start() if following else len(tail)
        file_rows = {}
        remainder = list(activity)

        def retain_row(position, *, body=body, cursor=cursor, file_rows=file_rows):
            begin = body.rfind("\n", 0, position) + 1
            end = body.find("\n", position)
            if end < 0:
                end = len(body)
            file_rows[begin - cursor] = body[begin:end]

        # Full-note activity carries authored guard state. Only the generated
        # region enters the reference grammar; trusted metadata stays opaque.
        for begin, end, _, _, destination, finish in inline_candidates(activity)[0]:
            if body[cursor + destination : cursor + finish].lower().startswith("file:"):
                retain_row(cursor + begin)
            for offset in range(begin, end):
                remainder[offset] = "\n" if tail[offset] == "\n" else " "
        remainder = "".join(remainder)
        extra_target = re.compile(
            r"\]\([ \t]*<?file:|<file:[^<>\s]*>"
            r"|\[\[file:[^\n\]]+\]\]"
            r"|^ {0,3}\[[^\]]+\]:[ \t]*<?file:",
            re.IGNORECASE | re.MULTILINE,
        )
        for match in extra_target.finditer(remainder):
            retain_row(cursor + match.start())
        html = FileHTML()
        html.feed(remainder)
        assert not html.file_target, "unexpected external HTML activation"

        required = []
        for key in sorted(attachments):
            attachment = attachments[key]
            if attachment["sourceId"] != owner or attachment["type"] not in {2, 8}:
                continue
            _, display, uri = external_projection(baseline, attachment, profile_version)
            label = re.sub(r"[\[\]|\r\n]", " ", display).strip() or "Resource"
            label = re.sub(r"([\\`*_{}<>])", r"\\\1", label)
            required.append("- [" + label + "](<" + uri + ">)")

        rows = sorted(file_rows.items())
        assert [
            row for offset, row in rows if section_start <= offset < section_end
        ] == required, "external generated Resources links"
        assert [row for _, row in rows] == required, (
            "unexpected external reference outside Resources"
        )


def check_api_vault(baseline, vault, *, profile_version="1"):
    """Audit actual assignments/bytes; the record never supplies expectations."""
    vault = Path(vault)
    audit = audit_baseline(baseline, profile_version=profile_version)
    proofs = audit.get("resource_eligibility", {})
    thoughts, expected, attachments, raw_links = source_facts(
        baseline, profile_version=profile_version
    )
    record_bytes = (vault / "migration-record.json").read_bytes()
    record = read_json(record_bytes)
    identity = record["source_identity"]
    assert (
        identity["module_id"],
        identity["module_version"],
        identity["format_version"],
    ) == ("thebrain-local-api", "1", "1"), "API module/format identity"
    assert (record["profile_id"], record["profile_version"]) == (
        "thebrain-local-api-reviewed",
        profile_version,
    ), "API-bound profile"
    assert (
        record["source_identity"]["source_id"]
        == baseline.json(baseline.data["brain"])["id"]
    ), "API-bound collection"

    def records(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from records(child)
        elif isinstance(value, list):
            for child in value:
                yield from records(child)

    originals = {semantic(row) for row in records(record["original_evidence"])}
    assert all(
        semantic(row) in originals
        for row in [
            *thoughts.values(),
            *raw_links.values(),
            *(attachment_evidence(a, len(record_bytes)) for a in attachments.values()),
        ]
    ), "raw API metadata/signatures preserved"
    actual = identities(record["relationships"], "key", "relationship")
    assert actual.keys() == expected.keys(), "relationship identities"
    for key, row in actual.items():
        assert all(row[k] == value for k, value in expected[key].items()), (
            "relationship endpoints/kind"
        )
    targets = identities(record["item_targets"], "item_key", "thought")
    assert targets.keys() == thoughts.keys(), "thought identities"
    for key, row in targets.items():
        assert (
            row["original_identity"] == key
            and row["original_title"] == thoughts[key]["name"]
        ), "thought identity/title"
    assignments = identities(
        record["classification_assignments"], "relationship_key", "classification"
    )
    required = {
        key: row for key, row in expected.items() if row["kind"] == "classification"
    }
    assert assignments.keys() == required.keys(), "classification identities"
    for key, row in assignments.items():
        assert (row["definition_key"], row["item_key"]) == (
            required[key]["item_a"],
            required[key]["item_b"],
        ), "classification endpoints"
    assets = identities(record["asset_targets"], "asset_id", "attachment")
    assert assets.keys() == attachments.keys(), "attachment identities"
    expected_gaps = {
        key
        for key, outcome in baseline.data["payloads"].items()
        if outcome["status"] == 404
    }
    warned = []
    for issue in record["issues"]:
        if issue.get("rule_id") == "local-api.missing-txt-pdf.v1":
            assert (
                issue["code"] == "approved_source_gap"
                and issue["severity"] == "warning"
            ), "reviewed gap warnings"
            warned.extend(issue["affected"])
    assert len(warned) == len(set(warned)) and set(warned) == expected_gaps, (
        "reviewed gap warnings"
    )
    local = {
        key
        for key, a in attachments.items()
        if a["type"] not in {2, 3, 8}
        or expected_asset(baseline, a, profile_version)[1] != "external"
    }
    assert set(baseline.data["payloads"]) == local, "baseline payload coverage"
    payload_count = 0
    for key, attachment in attachments.items():
        target = assets[key]
        role, availability, payload = expected_asset(
            baseline, attachment, profile_version, proofs
        )
        assert (target["owner"], target["role"], target["availability"]) == (
            attachment["sourceId"],
            role,
            availability,
        ), "attachment owner/role/availability"
        assert target["original_name"] == (
            attachment["name"] or attachment["location"]
            if role == "url"
            else attachment["location"]
        ), "attachment original name"
        display = (
            external_projection(baseline, attachment, profile_version)[1]
            if attachment["type"] in {2, 8}
            else attachment["name"]
        )
        assert target["display_name"] == display, "attachment display name"
        if availability == "present":
            assert target["relative_path"] is not None, "required payload file"
            path = safe_path(vault, target["relative_path"])
            assert path.is_file(), "required payload file"
            assert path.read_bytes() == payload, "required payload bytes"
            assert (target["actual_length"], target["actual_sha256"]) == (
                len(payload),
                hashlib.sha256(payload).hexdigest(),
            ), "measured payload integrity"
            payload_count += 1
        else:
            assert (
                target["relative_path"] is None
                and target["actual_length"] is None
                and target["actual_sha256"] is None
            ), "nonpresent payload must not fabricate bytes"
            if availability == "external":
                uri = (
                    external_projection(baseline, attachment, profile_version)[2]
                    if attachment["type"] in {2, 8}
                    else attachment["location"]
                )
                assert target["external_uri"] == uri, "authored external URI"
                if attachment["type"] in {2, 8}:
                    assert target["resource_link"] == uri, "external resource link"
            else:
                assert has_measured_pdf(
                    baseline,
                    attachments,
                    attachment["sourceId"],
                    profile_version,
                    proofs,
                ), "missing TXT lacks measured same-owner PDF"
    if profile_version == "3":
        check_new_image_preservation(
            baseline, vault, record, thoughts, attachments, targets, assets
        )

    check_external_resources(
        baseline, vault, thoughts, attachments, targets, assets, profile_version
    )
    check_reverse_navigation(
        baseline, vault, thoughts, expected, raw_links, attachments, targets, assets
    )
    baseline.verify()
    return {
        "thoughts": len(thoughts),
        "relationships": len(expected),
        "payloads": payload_count,
    }
