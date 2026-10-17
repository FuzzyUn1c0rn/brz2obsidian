"""Reviewed graph joins; adjacency is evidence, never a substitute for links."""

import re

from brz2obsidian.contracts import ClassificationAssignment, Relationship

from .declarations import source_date, uuid
from .errors import refuse, unsupported_shape

LINK_FIELDS = {
    "id",
    "brainId",
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
}


def link_identity(value, brain_id, expected_id=None):
    if not isinstance(value, dict) or value.get("brainId") != brain_id:
        refuse("A relationship has foreign or invalid ownership")
    key = uuid(value.get("id"))
    if expected_id is not None and key != expected_id:
        refuse("An authoritative relationship identity disagrees")
    uuid(value.get("thoughtIdA"))
    uuid(value.get("thoughtIdB"))
    return key


def normalize_relationships(
    links, graphs, thoughts, excluded=(), *, profile_version="1"
):
    result, assignments = [], []
    excluded, providers_by_item = set(excluded), {}
    expected_graphs = {
        key: {
            name: set()
            for name in (
                "parents_ids",
                "children_ids",
                "jump_ids",
                "tag_ids",
                "type_ids",
                "link_ids",
            )
        }
        for key in thoughts
    }
    for key, value in sorted(links.items()):
        if (
            not LINK_FIELDS - {"cleanedUpName"} <= value.keys()
            or value.keys() - LINK_FIELDS
        ):
            refuse("An included relationship declaration is incomplete or unsupported")
        for name in ("kind", "relation", "direction", "meaning"):
            if type(value[name]) is not int:
                refuse("A relationship scalar is not qualified")
        a, b = value["thoughtIdA"], value["thoughtIdB"]
        if a == b:
            refuse("An included relationship meaning is not qualified")
        if profile_version == "3" and value["typeId"] is not None:
            uuid(value["typeId"])
        if value["kind"] != 1 or value["typeId"] is not None:
            unsupported_shape(
                profile_version,
                "relationship",
                "An included relationship meaning is not qualified",
            )
        pair = value["relation"], value["direction"]
        if value["meaning"] == 2 and pair == (1, -1):
            if thoughts[a]["kind"] != 2 or thoughts[b]["kind"] != 1:
                refuse(
                    "A type assignment requires an inventoried definition and ordinary member"
                )
            kind, left, right = "classification", "children_ids", "type_ids"
            assignments.append(
                ClassificationAssignment(
                    relationship_key=key,
                    definition_key=a,
                    item_key=b,
                    evidence=("link:" + key, "thought:" + a, "thought:" + b),
                )
            )
            providers_by_item.setdefault(b, []).append(a)
            if a in graphs[b][0]["parents_ids"]:
                expected_graphs[b]["parents_ids"].add(a)
        elif value["meaning"] == 5 and pair == (1, -1):
            if thoughts[a]["kind"] != 4:
                refuse("A tag association requires an inventoried source tag")
            kind, left, right = "tag", "children_ids", "tag_ids"
        elif value["meaning"] == 1 and (
            pair in {(1, -1), (1, 1)}
            or (
                profile_version == "3"
                and pair == (1, 3)
                and thoughts[a]["kind"] == 1
                and thoughts[b]["kind"] == 1
            )
        ):
            kind, left, right = "hierarchy", "children_ids", "parents_ids"
        elif value["meaning"] == 1 and pair in {(3, -1), (3, 3), (3, 5), (3, 7)}:
            kind, left, right = "related", "jump_ids", "jump_ids"
        else:
            unsupported_shape(
                profile_version,
                "relationship",
                "An included relationship tuple is not qualified",
            )
        if b not in graphs[a][0][left] or a not in graphs[b][0][right]:
            refuse("Relationship endpoints do not agree with graph adjacency")
        if any(key not in graphs[node][0]["link_ids"] for node in (a, b)):
            refuse("A relationship is missing from its endpoint graph")
        expected_graphs[a][left].add(b)
        expected_graphs[b][right].add(a)
        expected_graphs[a]["link_ids"].add(key)
        expected_graphs[b]["link_ids"].add(key)
        for name in ("name", "cleanedUpName"):
            if (
                name in value
                and value[name] is not None
                and not isinstance(value[name], str)
            ):
                refuse("An authored relationship value is malformed")
        if value["color"] is not None and (
            not isinstance(value["color"], str)
            or not re.fullmatch(r"#[0-9a-fA-F]{6}", value["color"])
        ):
            refuse("A relationship colour is not qualified")
        if value["thickness"] is not None and (
            type(value["thickness"]) is not int
            or not -2147483648 <= value["thickness"] <= 2147483647
        ):
            refuse("A relationship thickness is malformed")
        source_date(value["creationDateTime"])
        source_date(value["modificationDateTime"])
        result.append(
            Relationship(
                key=key, kind=kind, item_a=a, item_b=b, evidence=("link:" + key,)
            )
        )
    for key, value in thoughts.items():
        for name, expected_ids in expected_graphs[key].items():
            observed_ids = set(graphs[key][0][name])
            observed_ids = (
                observed_ids & links.keys()
                if name == "link_ids"
                else observed_ids - excluded
            )
            if observed_ids != expected_ids:
                refuse(
                    "Graph adjacency is not completely explained by qualified relationships"
                )
        providers = providers_by_item.get(key, [])
        expected = (
            [value["typeId"]]
            if value["typeId"] is not None and value["typeId"] not in excluded
            else []
        )
        if (
            providers != expected
            or [node for node in graphs[key][0]["type_ids"] if node not in excluded]
            != expected
        ):
            refuse("Type field, graph type and assignment links disagree")
    return tuple(result), tuple(assignments)
