"""Independent API-bound preservation oracle. No converter modules are imported."""

import hashlib
import re
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID
from zipfile import BadZipFile, ZipFile

from .api_manifest import read_json, safe_path
from .checker import source_references, wiki
from .images import AuditUnavailable, decode_image


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
            for r in graph["links"] or []
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
        for field, wanted in expected.items():
            observed = graph[field] or []
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
        for row in graph["links"] or []:
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
    return thoughts, expected, attachments, links


def expected_asset(baseline, attachment, profile_version="1", proofs=None):
    assert profile_version in {"1", "2", "3"}, "unsupported API profile version"
    kind, note = attachment["type"], attachment["isNotes"]
    assert type(kind) is int and type(note) is bool, "raw attachment role"
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
        else:
            assert payload[:4] == b"RIFF" and payload[8:12] == b"WEBP", (
                "raw image signature"
            )
    elif kind == 5:
        if profile_version in {"2", "3"} and payload.startswith(b"\xff\xd8\xff"):
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
    local = {key for key, a in attachments.items() if a["type"] != 3}
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
            references = source_references(body, attachment["sourceId"], bindings)
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


def check_reverse_navigation(vault, thoughts, expected, raw_links, targets):
    """Audit actual trailing navigation independently of migration-record claims."""
    owners = {
        owner
        for row in raw_links.values()
        if tuple(row[k] for k in ("kind", "relation", "meaning", "direction"))
        == (1, 1, 1, 3)
        for owner in (row["thoughtIdA"], row["thoughtIdB"])
    }
    pattern = re.compile(
        r"^## (Parents|Children|Related)\n\n((?:- \[\[[^\n]+\]\]\n)+)", re.MULTILINE
    )
    for owner in owners:
        target = targets[owner]
        assert target.get("created") is True, "reverse hierarchy note materialization"
        path = safe_path(vault, target["relative_path"])
        assert path.is_file(), "reverse hierarchy generated note unavailable"
        body = path.read_text(encoding="utf-8")
        matches = list(pattern.finditer(body))
        assert matches and not body[matches[-1].end() :].strip(), (
            "reverse hierarchy generated navigation unavailable"
        )
        tail = [matches[-1]]
        for match in reversed(matches[:-1]):
            if body[match.end() : tail[0].start()].strip():
                break
            tail.insert(0, match)
        sections = {}
        for match in tail:
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
    check_reverse_navigation(vault, thoughts, expected, raw_links, targets)
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
    local = {key for key, a in attachments.items() if a["type"] != 3}
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
        assert target["display_name"] == attachment["name"], "attachment display name"
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
                assert target["external_uri"] == attachment["location"], (
                    "authored external URI"
                )
            else:
                assert has_measured_pdf(
                    baseline,
                    attachments,
                    attachment["sourceId"],
                    profile_version,
                    proofs,
                ), "missing TXT lacks measured same-owner PDF"
    baseline.verify()
    return {
        "thoughts": len(thoughts),
        "relationships": len(expected),
        "payloads": payload_count,
    }
