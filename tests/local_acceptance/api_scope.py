"""Pure API-local scope derivation from pinned wire facts; no product imports."""

import base64
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID

from .api_manifest import read_json
from .text import inline_candidates

THOUGHT_REQUIRED = {
    "id",
    "brainId",
    "creationDateTime",
    "modificationDateTime",
    "name",
    "typeId",
    "forgottenDateTime",
    "acType",
    "kind",
    "foregroundColor",
    "backgroundColor",
}
THOUGHT_FIELDS = THOUGHT_REQUIRED | {
    "cleanedUpName",
    "displayModificationDateTime",
    "linksModificationDateTime",
    "label",
    "aliases",
}
NEIGHBORS = ("parents", "children", "jumps", "siblings", "tags")


def canonical(value):
    assert type(value) is str, "canonical scope identity"
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise AssertionError("canonical scope identity") from error
    assert str(parsed) == value and parsed.int, "canonical scope identity"
    return value


def strict(value):
    if isinstance(value, dict):
        return ("object", tuple(sorted((key, strict(v)) for key, v in value.items())))
    if isinstance(value, list):
        return ("array", tuple(map(strict, value)))
    return (type(value).__name__, value)


@dataclass(frozen=True)
class SafeNote:
    owner: str
    scoped_text: str
    removed_thought_ids: frozenset


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(map(freeze, value))
    return value


def thaw(value):
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return list(map(thaw, value))
    return value


@dataclass(frozen=True)
class ScopeView:
    _graphs: dict
    _excluded_thoughts: dict
    _excluded_relationships: dict
    _safe_notes: dict
    _declarations: dict
    observed_ids: frozenset
    omitted_ids: frozenset
    retained_ids: frozenset

    def __post_init__(self):
        for field in (
            "_graphs",
            "_excluded_thoughts",
            "_excluded_relationships",
            "_safe_notes",
            "_declarations",
        ):
            object.__setattr__(self, field, freeze(getattr(self, field)))

    @property
    def graphs(self):
        return thaw(self._graphs)

    @property
    def excluded_thoughts(self):
        return thaw(self._excluded_thoughts)

    @property
    def excluded_relationships(self):
        return thaw(self._excluded_relationships)

    @property
    def safe_notes(self):
        return self._safe_notes

    @property
    def declarations(self):
        return thaw(self._declarations)


def scope_note(raw, excluded):
    """Remove whole active outer phrases before inspecting enclosed images."""
    removals, removed = [], set()
    for begin, end, _image, _label, start, finish in inline_candidates(raw)[0]:
        target = raw[start:finish]
        if not target.startswith("brain://"):
            continue
        spelling = target[8:].split("/", 1)[0]
        try:
            key = str(
                UUID(
                    bytes_le=base64.urlsafe_b64decode(
                        spelling + "=" * (-len(spelling) % 4)
                    )
                )
            )
        except (ValueError, TypeError) as exc:
            raise AssertionError("qualified scoped thought destination") from exc
        if key in excluded:
            removals.append((begin, end))
            removed.add(key)
    for begin, end in reversed(removals):
        raw = raw[:begin] + raw[end:]
    tokens = {
        token
        for key in excluded
        for token in (
            key,
            key.replace("-", ""),
            base64.urlsafe_b64encode(UUID(key).bytes_le).decode().rstrip("="),
        )
    }
    decoded = re.sub(r"%([0-9a-fA-F]{2})", lambda m: chr(int(m[1], 16)), raw)
    decoded = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)), decoded)
    assert not any(
        token in candidate for candidate in (raw, decoded) for token in tokens
    ), "unremoved excluded note association"
    assert not any(
        m[0].lower() in tokens
        for m in re.finditer(
            r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", decoded
        )
    ), "unremoved excluded note association"
    return raw, frozenset(removed)


def qualify_scope(baseline, *, profile_version):
    """Derive scope only; no safe text/availability assertion is an input."""
    assert profile_version in {"1", "2", "3"}, "unsupported API profile version"
    baseline.verify()
    data = baseline.data
    graphs = {
        key: read_json(baseline.bytes(path), parse_float=Decimal)
        for key, path in data["graphs"].items()
    }
    declarations, declared_owners = {}, {}
    for owner, graph in graphs.items():
        inventory = graph["attachments"]
        if inventory is None:
            assert owner in data.get("attachment_inventories", {}), (
                "missing authoritative attachment inventory"
            )
            inventory = read_json(
                baseline.bytes(data["attachment_inventories"][owner]),
                parse_float=Decimal,
            )
        assert type(inventory) is list, "scope attachment inventory"
        for row in inventory:
            key = canonical(row["id"])
            assert key not in declarations, "scope attachment identities"
            declarations[key] = row
            declared_owners[key] = owner
    observed = frozenset(declarations)
    if data["schema"] == "brz2obsidian.api-acceptance/1":
        return ScopeView(
            graphs, {}, {}, {}, declarations, observed, frozenset(), observed
        )
    inputs = data["scope_inputs"]
    assert type(inputs) is dict and set(inputs) == {
        "excluded_thoughts",
        "excluded_relationships",
    }, "closed scope inputs"
    collection = canonical(baseline.json(data["brain"])["id"])
    authority = {}

    def thought(row, expected=None):
        assert type(row) is dict and THOUGHT_REQUIRED <= row.keys() <= THOUGHT_FIELDS, (
            "full eleven-field authoritative thought"
        )
        key = canonical(row["id"])
        assert row["brainId"] == collection and (expected is None or key == expected), (
            "scope thought ownership"
        )
        assert type(row["acType"]) is int and row["acType"] == 0, "scope public access"
        assert type(row["kind"]) is int and row["kind"] in {1, 2, 4, 5}, (
            "scope source role"
        )
        marker = row["forgottenDateTime"]
        if marker is not None:
            assert type(marker) is str and re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-5][0-9](?:\.[0-9]{1,7})?(?:Z|[+-](?:0[0-9]|1[0-4]):[0-5][0-9])?",
                marker,
            ), "scope forgotten timestamp"
            try:
                date = datetime.fromisoformat(marker)
            except ValueError as error:
                raise AssertionError("scope forgotten calendar") from error
            assert date.year != 1 and (
                date.utcoffset() is None
                or abs(date.utcoffset().total_seconds()) <= 50400
            ), "scope forgotten calendar"
        if row["kind"] != 5 and marker is None:
            assert type(row["name"]) is str, "included source title"
            for field in ("label", "cleanedUpName"):
                assert row.get(field) is None or type(row[field]) is str, (
                    "included source authored metadata"
                )
            aliases = row.get("aliases")
            assert (
                aliases is None
                or type(aliases) is list
                and all(type(value) is str for value in aliases)
            ), "included source aliases"
            if row["typeId"] is not None:
                canonical(row["typeId"])
            for field in ("foregroundColor", "backgroundColor"):
                color = row[field]
                assert (
                    color is None
                    or type(color) is str
                    and re.fullmatch(r"#[0-9a-fA-F]{6}", color)
                ), "included source appearance"
            for field in (
                "creationDateTime",
                "modificationDateTime",
                "displayModificationDateTime",
                "linksModificationDateTime",
            ):
                value = row.get(field)
                if value is None:
                    continue
                assert type(value) is str and re.fullmatch(
                    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-5][0-9](?:\.[0-9]{1,7})?(?:Z|[+-](?:0[0-9]|1[0-4]):[0-5][0-9])?",
                    value,
                ), "included source timestamp"
                try:
                    date = datetime.fromisoformat(value)
                except ValueError as error:
                    raise AssertionError("included source calendar") from error
                assert date.year != 1 and (
                    date.utcoffset() is None
                    or abs(date.utcoffset().total_seconds()) <= 50400
                ), "included source calendar"
        if key in authority:
            assert strict(authority[key]) == strict(row), (
                "contradictory raw scope thought"
            )
        authority[key] = row
        return key

    def outcome(value):
        assert type(value) is dict and set(value) == {"status", "path"}, (
            "scope authority outcome fields"
        )
        assert type(value["status"]) is int and value["status"] == 200, (
            "scope authority HTTP outcome"
        )
        return read_json(baseline.bytes(value["path"]), parse_float=Decimal)

    assert (
        type(inputs["excluded_thoughts"]) is dict
        and type(inputs["excluded_relationships"]) is dict
    ), "scope authority maps"
    attachment_required = {
        "id",
        "brainId",
        "sourceId",
        "sourceType",
        "name",
        "position",
        "type",
        "isNotes",
        "dataLength",
        "location",
    }
    attachment_optional = {
        "creationDateTime",
        "modificationDateTime",
        "fileModificationDateTime",
    }
    for owner, graph in graphs.items():
        inventory = read_json(
            baseline.bytes(data["attachment_inventories"][owner]), parse_float=Decimal
        )
        assert type(inventory) is list, "authoritative scoped owner attachment array"
        expected = {
            key: row
            for key, row in declarations.items()
            if declared_owners[key] == owner
        }
        assert len(inventory) == len(expected) and len(
            {row["id"] for row in inventory}
        ) == len(inventory), "scoped owner unique attachment identities"
        assert strict({row["id"]: row for row in inventory}) == strict(expected), (
            "scoped attachment graph/list agreement"
        )
        assert graph["attachments"] is not None or not inventory, (
            "populated scoped graph inventory required"
        )
    for key, row in declarations.items():
        assert (
            type(row) is dict
            and attachment_required
            <= row.keys()
            <= attachment_required | attachment_optional
        ), "closed scoped attachment declaration"
        assert (
            canonical(row["sourceId"]) == declared_owners[key]
            and row["brainId"] == collection
        ), "scoped attachment ownership"
        assert type(row["sourceType"]) is int and row["sourceType"] == 2, (
            "scoped attachment source type"
        )
        assert type(row["type"]) is int and type(row["isNotes"]) is bool, (
            "scoped attachment role scalars"
        )
        assert type(row["location"]) is str and row["location"], (
            "scoped attachment location"
        )
        assert (
            row["dataLength"] is None
            or type(row["dataLength"]) is int
            and 0 <= row["dataLength"] <= 9223372036854775807
        ), "scoped declared length"
        assert (
            type(row["position"]) in (int, Decimal)
            and Decimal(row["position"]).is_finite()
        ), "scoped attachment position"
        assert strict(outcome(data["attachment_metadata"][key])) == strict(row), (
            "scoped standalone attachment agreement"
        )

    excluded = {}
    for key, value in inputs["excluded_thoughts"].items():
        row = outcome(value)
        thought(row, canonical(key))
        assert row["kind"] == 5 or row["forgottenDateTime"] is not None, (
            "unqualified excluded thought"
        )
        excluded[key] = {
            field: row[field]
            for field in ("id", "brainId", "kind", "acType", "forgottenDateTime")
        }
    for key, graph in graphs.items():
        thought(graph["activeThought"], canonical(key))
        assert key not in excluded, "excluded graph authored content"
        assert (
            graph["activeThought"]["kind"] != 5
            and graph["activeThought"]["forgottenDateTime"] is None
        ), "unlisted source exclusion"
        for field in NEIGHBORS:
            assert type(graph[field]) is list, "required scope neighbor array"
            for row in graph[field]:
                thought(row)
        if graph["type"] is not None:
            thought(graph["type"])
    assert set(authority) == set(graphs) | set(excluded), (
        "scope authority identity coverage"
    )
    assert all(
        row["kind"] != 5 and row["forgottenDateTime"] is None
        for key, row in authority.items()
        if key not in excluded
    ), "unlisted source exclusion"
    excluded_links = {}
    for key, value in inputs["excluded_relationships"].items():
        row = outcome(value)
        assert (
            canonical(row["id"]) == canonical(key) and row["brainId"] == collection
        ), "excluded relationship ownership"
        a, b = canonical(row["thoughtIdA"]), canonical(row["thoughtIdB"])
        assert {a, b} <= authority.keys() and {a, b} & excluded.keys(), (
            "excluded relationship endpoints"
        )
        excluded_links[key] = {
            field: row[field] for field in ("id", "brainId", "thoughtIdA", "thoughtIdB")
        }
    for graph in graphs.values():
        assert type(graph["links"]) is list, "scope relationship array"
        retained = []
        for row in graph["links"]:
            key = canonical(row["id"])
            endpoints = {row["thoughtIdA"], row["thoughtIdB"]}
            assert endpoints <= authority.keys(), (
                "unresolved scope relationship endpoint"
            )
            if endpoints & excluded.keys():
                assert key in excluded_links and strict(row) == strict(
                    outcome(inputs["excluded_relationships"][key])
                ), "contradictory excluded relationship"
            else:
                assert key not in excluded_links, "falsely excluded relationship"
                retained.append(row)
        graph["links"] = retained
        for field in NEIGHBORS:
            graph[field] = [row for row in graph[field] if row["id"] not in excluded]
        if graph["type"] is not None and graph["type"]["id"] in excluded:
            graph["type"] = None
        if graph["activeThought"]["typeId"] in excluded:
            graph["activeThought"] = dict(graph["activeThought"], typeId=None)
    statistics = [baseline.json(path) for path in data["statistics"]]
    counters = ("thoughts", "thoughtTypes", "tags", "forgottenThoughts", "links")
    assert len(statistics) == 2, "scope consistency observations"
    for stats in statistics:
        assert stats["brainId"] == collection and all(
            type(stats[field]) is int and 0 <= stats[field] <= 2147483647
            for field in counters
        ), "scope consistency counters"
    assert all(statistics[0][field] == statistics[1][field] for field in counters), (
        "scope consistency population drift"
    )
    forgotten = sum(
        row["kind"] == 1 and row["forgottenDateTime"] is not None
        for row in excluded.values()
    )
    assert forgotten <= statistics[0]["forgottenThoughts"], (
        "observed forgotten population lower bound"
    )
    safe_notes = {}
    for key, row in declarations.items():
        if row["isNotes"]:
            assert (
                row["sourceId"] in graphs
                and row["type"] == 1
                and row["location"] == "Notes.md"
                and row["name"] is None
            ), "qualified original note declaration"
            value = data["payloads"][key]
            assert type(value["status"]) is int and value["status"] == 200, (
                "required raw note HTTP outcome"
            )
            raw = baseline.bytes(value["path"]).decode("utf8", errors="strict")
            text, removed = scope_note(raw, excluded)
            safe_notes[key] = SafeNote(row["sourceId"], text, removed)
    omitted = frozenset(
        key for key, note in safe_notes.items() if note.removed_thought_ids
    )
    return ScopeView(
        graphs,
        excluded,
        excluded_links,
        safe_notes,
        declarations,
        observed,
        omitted,
        observed - omitted,
    )
