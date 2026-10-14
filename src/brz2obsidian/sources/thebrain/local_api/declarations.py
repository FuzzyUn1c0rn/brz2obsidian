"""Qualified metadata declarations; search stubs grant no source meaning."""

import re
from datetime import datetime
from uuid import UUID

from .errors import refuse

THOUGHT_FIELDS = {
    "id",
    "brainId",
    "creationDateTime",
    "modificationDateTime",
    "name",
    "cleanedUpName",
    "typeId",
    "displayModificationDateTime",
    "forgottenDateTime",
    "linksModificationDateTime",
    "acType",
    "kind",
    "label",
    "aliases",
    "foregroundColor",
    "backgroundColor",
}
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
COUNTERS = ("thoughts", "thoughtTypes", "tags", "forgottenThoughts", "links")
NEIGHBORS = {
    "parents": "parents_ids",
    "children": "children_ids",
    "jumps": "jump_ids",
    "siblings": "sibling_ids",
    "tags": "tag_ids",
}
GRAPH_FIELDS = {"activeThought", "type", "links", "attachments", *NEIGHBORS}


def uuid(value):
    try:
        if isinstance(value, str) and str(UUID(value)) == value and UUID(value).int:
            return value
    except ValueError, AttributeError:
        pass
    refuse("An API identity is not a canonical nonzero UUID")


def source_date(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-5][0-9](?:\.[0-9]{1,7})?(?:Z|[+-](?:0[0-9]|1[0-4]):[0-5][0-9])?",
        value,
    ):
        refuse("A source timestamp is outside the qualified grammar")
    try:
        result = datetime.fromisoformat(value)
        offset = result.utcoffset()
        if (
            result.year == 1
            or offset is not None
            and abs(offset.total_seconds()) > 50400
        ):
            raise ValueError
    except ValueError:
        refuse("A source timestamp is outside the qualified calendar")
    return result.date()


def counters(value):
    if not isinstance(value, dict) or any(
        type(value.get(k)) is not int or not 0 <= value[k] <= 2147483647
        for k in COUNTERS
    ):
        refuse("Required source counters are invalid")
    return {key: value[key] for key in COUNTERS}


def collection(value, brain_id):
    if (
        not isinstance(value, dict)
        or value.get("id") != brain_id
        or not isinstance(value.get("name"), str)
    ):
        refuse("The requested Brain declaration does not agree")
    return {
        "id": uuid(value["id"]),
        "name": value["name"],
        "homeThoughtId": uuid(value.get("homeThoughtId")),
    }


def thought(value, brain_id, expected_id=None):
    if (
        not isinstance(value, dict)
        or not THOUGHT_REQUIRED <= value.keys()
        or value.keys() - THOUGHT_FIELDS
    ):
        refuse("An authoritative thought has an unsupported declaration")
    key = uuid(value["id"])
    if expected_id is not None and key != expected_id or value["brainId"] != brain_id:
        refuse("An authoritative thought has foreign or conflicting ownership")
    if type(value["acType"]) is not int or value["acType"] != 0:
        refuse("Encountered private or unqualified access cannot be imported")
    if type(value["kind"]) is not int or value["kind"] not in {1, 2, 4, 5}:
        refuse("An authoritative thought role is not qualified")
    if value["forgottenDateTime"] is not None:
        source_date(value["forgottenDateTime"])
    # Exclusions are validated before any authored content is considered.
    if value["kind"] == 5 or value["forgottenDateTime"] is not None:
        return value
    if not isinstance(value["name"], str):
        refuse("An included thought requires an authored title")
    for name in ("label", "cleanedUpName"):
        if (
            name in value
            and value[name] is not None
            and not isinstance(value[name], str)
        ):
            refuse("An authored metadata value has an unsupported type")
    if (
        "aliases" in value
        and value["aliases"] is not None
        and (
            not isinstance(value["aliases"], list)
            or any(not isinstance(v, str) for v in value["aliases"])
        )
    ):
        refuse("An authored alias declaration is malformed")
    for name in (
        "creationDateTime",
        "modificationDateTime",
        "displayModificationDateTime",
        "linksModificationDateTime",
    ):
        if name in value and value[name] is not None:
            source_date(value[name])
    if value["typeId"] is not None:
        uuid(value["typeId"])
    for name in ("foregroundColor", "backgroundColor"):
        if value[name] is not None and (
            not isinstance(value[name], str)
            or not re.fullmatch(r"#[0-9a-fA-F]{6}", value[name])
        ):
            refuse("An appearance declaration is not qualified")
    return value


def array(value):
    if not isinstance(value, list):
        refuse("A required inventory is not a successful complete array")
    return value
