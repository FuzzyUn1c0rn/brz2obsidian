"""Version1 CJSON1 encoding and deterministic frozen fact projections."""

import json
import re
from collections import defaultdict, deque

from .declarations import (
    COUNTERS,
    THOUGHT_FIELDS,
    collection,
    counters,
    source_date,
    thought,
    uuid,
)
from .errors import refuse


def canonical(value):
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if type(value) is int:
        return str(value).encode("ascii")
    if isinstance(value, str):
        result = '"'
        for ch in value:
            if 0xD800 <= ord(ch) <= 0xDFFF:
                refuse("Source text contains an invalid Unicode scalar")
            if ch == '"':
                result += '\\"'
            elif ch == "\\":
                result += "\\\\"
            elif ord(ch) < 32:
                result += f"\\u{ord(ch):04x}"
            else:
                result += ch
        return (result + '"').encode("utf-8")
    if isinstance(value, (list, tuple)):
        return b"[" + b",".join(canonical(v) for v in value) + b"]"
    if isinstance(value, dict):
        return (
            b"{"
            + b",".join(
                canonical(k) + b":" + canonical(value[k])
                for k in sorted(value, key=lambda k: k.encode("utf-8"))
            )
            + b"}"
        )
    refuse("Source value has an unsupported encoding")


IDENTIFIERS = {
    "format_id": "thebrain-local-api-capture",
    "format_version": "1",
    "module_id": "thebrain-local-api",
    "module_version": "1",
    "profile_id": "thebrain-local-api-reviewed",
    "profile_version": "1",
    "contract_version": 7,
}
SCHEMA_SHA256 = "7eba4646236dbecf2dd4c265d5cd52f782245a9b17f2ab92e90aa2e167a3b318"
DESKTOP_BUILD = "15.0.640.0"


def pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            refuse("Source JSON contains duplicate keys")
        result[key] = value
    return result


def parse_json(raw):
    def integer(value):
        if value == "-0":
            refuse("Canonical JSON contains negative zero")
        return int(value)

    def invalid(value):
        refuse("Canonical JSON contains a noninteger number")

    return json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_int=integer,
        parse_float=invalid,
        parse_constant=invalid,
    )


def source_projection(source):
    source = parse_json(canonical(source))
    validate_source(source)
    source["records"].sort(key=lambda r: r["key"].encode("utf-8"))
    source["payloads"].sort(key=lambda a: a["asset_id"].encode("utf-8"))
    for values in source["inventories"].values():
        values.sort(key=lambda v: v.encode("utf-8"))
    source["scope"]["decisions"].sort(key=lambda d: d["key"].encode("utf-8"))
    for decision in source["scope"]["decisions"]:
        decision["subjects"].sort()
        decision["evidence"].sort()
    for record in source["records"]:
        if record["domain"] == "graph":
            for values in record["value"].values():
                values.sort()
    return source


def fields(value, required, allowed=None):
    if (
        not isinstance(value, dict)
        or not set(required) <= value.keys()
        or value.keys() - set(allowed or required)
    ):
        refuse("A capture document contains unsupported or missing fields")


def unique(values, key=lambda value: value):
    if not isinstance(values, list) or len({key(value) for value in values}) != len(
        values
    ):
        refuse("A captured inventory contains duplicate or invalid identities")


def validate_source(source):
    fields(
        source, {"identifiers", "brain", "records", "inventories", "scope", "payloads"}
    )
    fields(source["brain"], {"id", "name", "homeThoughtId"})
    b = uuid(source["brain"]["id"])
    collection(source["brain"], b)
    fields(source["inventories"], {"ordinary_ids", "type_ids", "tag_ids"})
    all_ids = []
    for values in source["inventories"].values():
        unique(values)
        all_ids.extend(uuid(key) for key in values)
    unique(all_ids)
    fields(source["scope"], {"policy", "decisions"})
    if source["scope"]["policy"] != "public-live-ordinary-type-tag-v1":
        refuse("Capture scope policy is not qualified")
    unique(source["records"], lambda r: r["key"])
    unique(source["payloads"], lambda r: r["asset_id"])
    unique(source["scope"]["decisions"], lambda r: r["key"])
    allowed = {
        "brain": {"id", "name", "homeThoughtId"},
        "thought": THOUGHT_FIELDS,
        "link": {
            "id",
            "brainId",
            "creationDateTime",
            "modificationDateTime",
            "name",
            "cleanedUpName",
            "typeId",
            "kind",
            "color",
            "thickness",
            "thoughtIdA",
            "thoughtIdB",
            "relation",
            "direction",
            "meaning",
        },
        "attachment": {
            "id",
            "brainId",
            "sourceId",
            "sourceType",
            "creationDateTime",
            "modificationDateTime",
            "name",
            "position",
            "fileModificationDateTime",
            "type",
            "isNotes",
            "dataLength",
            "location",
        },
        "graph": {
            "parents_ids",
            "children_ids",
            "jump_ids",
            "sibling_ids",
            "tag_ids",
            "type_ids",
            "link_ids",
            "attachment_ids",
        },
        "no_note": {
            "brainId",
            "sourceId",
            "sourceType",
            "modificationDateTime",
            "markdown",
            "html",
            "text",
        },
        "note_text": {"text"},
        "statistics": set(COUNTERS),
        "exclusion": {"id", "brainId", "acType", "kind", "forgottenDateTime"},
    }
    for record in source["records"]:
        fields(record, {"key", "domain", "owner_id", "value"})
        domain, value, key, owner = (
            record[name] for name in ("domain", "value", "key", "owner_id")
        )
        if domain not in allowed:
            refuse("A capture domain is not qualified")
        fields(value, set(), allowed[domain])
        uuid(owner)
        if (
            domain in {"brain", "thought", "link", "statistics", "exclusion"}
            and owner != b
        ):
            refuse("A source record has foreign ownership")
        if domain in {"thought", "link", "attachment", "exclusion"}:
            if value.get("brainId") != b or key != domain + ":" + uuid(value.get("id")):
                refuse("A captured record has a conflicting source identity")
        elif domain == "statistics":
            fields(value, COUNTERS)
            counters(value)
            if key not in {"statistics:start", "statistics:end"}:
                refuse("A statistics identity is invalid")
        elif domain == "brain":
            if value != source["brain"] or key != "brain:" + b:
                refuse("Captured Brain records disagree")
        elif key != domain + ":" + owner:
            refuse("A captured owner record has a conflicting identity")
        if domain == "thought":
            thought(value, b)
        elif domain == "graph":
            fields(value, allowed[domain])
            for values in value.values():
                unique(values)
                for identity in values:
                    uuid(identity)
        elif domain == "attachment":
            fields(
                value,
                {
                    "id",
                    "brainId",
                    "sourceId",
                    "sourceType",
                    "type",
                    "isNotes",
                    "dataLength",
                    "location",
                    "name",
                    "position",
                },
                allowed[domain],
            )
            if (
                type(value["isNotes"]) is not bool
                or type(value["type"]) is not int
                or value["type"] not in {1, 3, 5, 12, 15}
                or value["dataLength"] is not None
                and (
                    type(value["dataLength"]) is not int
                    or not 0 <= value["dataLength"] <= 9223372036854775807
                )
            ):
                refuse("Captured attachment scalars do not match the reviewed schema")
            if (
                value.get("sourceId") != owner
                or type(value.get("sourceType")) is not int
                or value["sourceType"] != 2
            ):
                refuse("A captured attachment has foreign ownership")
            fields(value.get("position"), {"decimal"})
            decimal = value["position"]["decimal"]
            if not isinstance(decimal, str) or not re.fullmatch(
                r"(?:0|-?[1-9][0-9]*)(?:\.[0-9]*[1-9])?|-?0\.[0-9]*[1-9]", decimal
            ):
                refuse("A captured attachment position is not canonical decimal")
        elif domain == "no_note":
            if value != {
                "brainId": b,
                "sourceId": owner,
                "sourceType": 2,
                "modificationDateTime": "0001-01-01T00:00:00",
                "markdown": "",
                "html": None,
                "text": None,
            }:
                refuse("A captured empty note declaration is not qualified")
        elif domain == "note_text":
            fields(value, {"text"})
            if not isinstance(value["text"], str):
                refuse("Captured note text is invalid")
        elif domain == "exclusion":
            fields(value, allowed[domain])
            if (
                type(value["acType"]) is not int
                or value["acType"] != 0
                or type(value["kind"]) is not int
                or value["kind"] not in {1, 2, 4, 5}
            ):
                refuse("A captured exclusion lacks qualified public role evidence")
            if value["forgottenDateTime"] is not None:
                source_date(value["forgottenDateTime"])
            elif value["kind"] != 5:
                refuse("A captured forgotten exclusion lacks its source timestamp")
    records = {r["key"]: r for r in source["records"]}
    included = set(all_ids)
    if {
        r["value"]["id"] for r in source["records"] if r["domain"] == "thought"
    } != included:
        refuse("Source thought records do not equal the included inventory")
    for record in source["records"]:
        if (
            record["domain"] in {"graph", "attachment", "no_note", "note_text"}
            and record["owner_id"] not in included
        ):
            refuse("A source content record has no included owner")
    if not {"brain:" + b, "statistics:start", "statistics:end"} <= records.keys():
        refuse("Required source records are missing")
    if records["statistics:start"]["value"] != records["statistics:end"]["value"]:
        refuse("Captured source counters drifted")
    for name, role in (("ordinary_ids", 1), ("type_ids", 2), ("tag_ids", 4)):
        for identity in source["inventories"][name]:
            item = records.get("thought:" + identity)
            if (
                item is None
                or item["value"].get("kind") != role
                or item["value"].get("forgottenDateTime") is not None
            ):
                refuse("Captured inventories disagree with authoritative roles")
    for fact in source["payloads"]:
        fields(
            fact,
            {
                "asset_id",
                "owner_id",
                "availability",
                "actual_length",
                "actual_sha256",
                "external_uri",
            },
        )
        uuid(fact["asset_id"])
        uuid(fact["owner_id"])
        if "attachment:" + fact["asset_id"] not in records:
            refuse("A captured payload has no source declaration")
    decisions = source["scope"]["decisions"]
    references = (
        set(records)
        | {"inventory:" + key for key in source["inventories"]}
        | {"payload:" + r["asset_id"] for r in source["payloads"]}
        | {d["key"] for d in decisions}
    )
    for decision in decisions:
        fields(decision, {"key", "rule_id", "outcome", "subjects", "evidence"})
        if (
            not decision["key"].startswith("scope:")
            or not isinstance(decision["rule_id"], str)
            or decision["rule_id"]
            not in {
                "local-api.roles-access.v1",
                "local-api.forgotten.v1",
                "local-api.system.v1",
                "local-api.tag400.v1",
            }
            or decision["outcome"]
            not in {
                "included",
                "excluded_forgotten",
                "excluded_system",
                "excluded_association",
                "tag400_zero",
                "missing_txt404",
            }
        ):
            refuse("A captured scope decision is not qualified")
        qualified_rules = {
            "included": {"local-api.roles-access.v1"},
            "excluded_forgotten": {"local-api.forgotten.v1"},
            "excluded_system": {"local-api.system.v1"},
            "excluded_association": {"local-api.forgotten.v1", "local-api.system.v1"},
            "tag400_zero": {"local-api.tag400.v1"},
        }
        if decision["rule_id"] not in qualified_rules.get(decision["outcome"], set()):
            refuse("A captured scope outcome does not match its reviewed rule")
        for name in ("subjects", "evidence"):
            unique(decision[name])
        if (
            not set(decision["evidence"]) <= references
            or decision["key"] in decision["evidence"]
        ):
            refuse("A captured scope decision has unresolved evidence")
    validate_scope_references(records, source["payloads"], decisions)


def validate_scope_references(records, payloads, decisions):
    """Check the finite evidence graph without recursion or unbounded walks."""
    by_key = {decision["key"]: decision for decision in decisions}
    dependencies = {
        key: {ref for ref in decision["evidence"] if ref in by_key}
        for key, decision in by_key.items()
    }
    dependents = defaultdict(list)
    remaining = {key: len(refs) for key, refs in dependencies.items()}
    for key, refs in dependencies.items():
        for reference in refs:
            dependents[reference].append(key)
    ready = deque(key for key, count in remaining.items() if count == 0)
    visited = 0
    while ready:
        key = ready.popleft()
        visited += 1
        for dependent in dependents[key]:
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                ready.append(dependent)
    if visited != len(decisions):
        refuse("Captured scope evidence contains a reference cycle")

    def reaches(decision, target):
        seen, pending = set(), [decision["key"]]
        while pending:
            key = pending.pop()
            if key in seen:
                continue
            seen.add(key)
            for reference in by_key[key]["evidence"]:
                if reference == target:
                    return True
                if reference in by_key and reference not in seen:
                    pending.append(reference)
        return False

    known = set(records) | {"payload:" + fact["asset_id"] for fact in payloads}
    for decision in decisions:
        excluded = set()
        for subject in decision["subjects"]:
            if subject in known:
                continue
            if not isinstance(subject, str) or not subject.startswith("thought:"):
                continue
            identity = uuid(subject.removeprefix("thought:"))
            exclusion_key = "exclusion:" + identity
            exclusion = records.get(exclusion_key)
            if (
                exclusion is None
                or decision["outcome"]
                not in {"excluded_forgotten", "excluded_system", "excluded_association"}
                or not reaches(decision, exclusion_key)
            ):
                continue
            value = exclusion["value"]
            if decision["outcome"] == "excluded_system" and value["kind"] != 5:
                continue
            if decision["outcome"] == "excluded_forgotten" and (
                value["kind"] == 5 or value["forgottenDateTime"] is None
            ):
                continue
            excluded.add(subject)
        included_endpoint = any(
            subject.startswith("thought:")
            and subject in records
            and records[subject]["domain"] == "thought"
            for subject in decision["subjects"]
            if isinstance(subject, str)
        )
        for subject in decision["subjects"]:
            if subject in known or subject in excluded:
                continue
            if (
                isinstance(subject, str)
                and subject.startswith("link:")
                and decision["outcome"] == "excluded_association"
                and excluded
                and included_endpoint
            ):
                uuid(subject.removeprefix("link:"))
                continue
            refuse("A captured scope subject has no qualified source reference")


def validate_binding(source, snapshot, audit):
    identity = snapshot.identity
    b = source["brain"]["id"]
    if (
        identity.source_id,
        identity.module_id,
        identity.module_version,
        identity.format_version,
    ) != (b, "thebrain-local-api", "1", "1") or any(
        request.brain_id != b for request in audit.requests
    ):
        refuse("Capture metadata has a foreign or incompatible identity")
    for name, key in (
        ("items", "key"),
        ("relationships", "key"),
        ("documents", "key"),
        ("assets", "asset_id"),
        ("original_evidence", "key"),
    ):
        values = getattr(snapshot, name)
        if len({getattr(v, key) for v in values}) != len(values):
            refuse("A normalized captured inventory has duplicate identities")
    source_values = {r["key"]: r["value"] for r in source["records"]} | {
        d["key"]: d for d in source["scope"]["decisions"]
    }
    originals = {e.key: e for e in snapshot.original_evidence}
    if originals.keys() != source_values.keys():
        refuse("Snapshot originals are not bound to safe scoped source records")
    for key, evidence in originals.items():
        if (
            evidence.kind != "records"
            or parse_json(evidence.original_json) != source_values[key]
        ):
            refuse("Snapshot originals disagree with scoped source facts")
    if snapshot.findings or snapshot.source_gaps or snapshot.generated_presentations:
        refuse("Finding and gap content is not implemented in this stage")
    entries = snapshot.accounting.entries
    allowed_references = (
        set(source_values)
        | {entry.key for entry in snapshot.items}
        | {entry.key for entry in snapshot.documents}
        | {entry.key for entry in snapshot.relationships}
        | {entry.asset_id for entry in snapshot.assets}
    )
    if (
        len({entry.identity for entry in entries}) != len(entries)
        or {entry.identity for entry in entries} != source_values.keys()
    ):
        refuse("Capture accounting does not cover scoped evidence exactly")
    for entry in entries:
        if (
            entry.disposition == "unresolved"
            or not entry.references
            or not set(entry.references) <= allowed_references
        ):
            refuse("Captured accounting has unresolved or foreign references")
    included = {key for values in source["inventories"].values() for key in values}
    if (
        {item.key for item in snapshot.items} != included
        or snapshot.entry_key != source["brain"]["homeThoughtId"]
        or snapshot.collection_title != source["brain"]["name"]
    ):
        refuse("Snapshot collection or included inventory disagrees with capture")
    for item in snapshot.items:
        declaration = source_values["thought:" + item.key]
        if (
            item.title != declaration["name"]
            or item.label != declaration.get("label")
            or item.role
            != {1: "ordinary", 2: "definition", 4: "tag"}[declaration["kind"]]
            or not item.live
            or item.original_identity != item.key
            or item.naming_seed != item.key.replace("-", "")
        ):
            refuse(
                "Normalized item metadata is not bound to authoritative source declarations"
            )


def snapshot_projection(snapshot):
    value = snapshot.model_dump(mode="json")
    for name, key in [
        ("items", "key"),
        ("relationships", "key"),
        ("documents", "key"),
        ("assets", "asset_id"),
        ("original_evidence", "key"),
    ]:
        value[name].sort(key=lambda r: r[key].encode("utf-8"))
    for name, keys in [
        (
            "classification_assignments",
            ("relationship_key", "definition_key", "item_key"),
        ),
        ("source_gaps", ("owner", "asset_id", "role", "rule_id")),
        ("generated_presentations", ("owner", "source_gap_asset_id", "kind")),
    ]:
        value[name].sort(key=lambda r: tuple(r[k].encode("utf-8") for k in keys))
    value["accounting"]["entries"].sort(key=lambda r: r["identity"].encode("utf-8"))

    def refs(node):
        if isinstance(node, dict):
            for key, child in node.items():
                if (
                    key
                    in {
                        "evidence",
                        "affected",
                        "references",
                        "document_ids",
                        "resource_ids",
                    }
                    and isinstance(child, list)
                    and all(isinstance(v, str) for v in child)
                ):
                    if len(set(child)) != len(child):
                        refuse("Captured evidence references are duplicated")
                    child.sort(key=lambda v: v.encode("utf-8"))
                refs(child)
        elif isinstance(node, list):
            for child in node:
                refs(child)

    refs(value)
    for evidence in value["original_evidence"]:
        original = parse_json(evidence["original_json"])
        if evidence["key"].startswith("graph:"):
            for entries in original.values():
                entries.sort()
        if evidence["key"].startswith("scope:"):
            original["subjects"].sort()
            original["evidence"].sort()
        evidence["original_json"] = canonical(original).decode("utf-8")
    for finding in value["findings"]:
        finding["observed_json"] = canonical(
            parse_json(finding["observed_json"])
        ).decode("utf-8")
    value["findings"].sort(key=canonical)
    return value
