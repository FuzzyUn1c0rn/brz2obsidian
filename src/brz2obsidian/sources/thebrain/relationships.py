"""Interpret only the independently verified TheBrain graph signatures."""

from brz2obsidian.contracts import Relationship

from .semantics import validate_semantic_fields


def decode_relationships(records, thoughts, brain_id, refuse, uuid):
    result, keys = [], set()
    for index, record in enumerate(records):
        validate_semantic_fields(record, refuse)
        fields = ("Kind", "Relation", "Meaning", "Direction")
        if any(type(record.get(field)) is not int for field in fields):
            refuse(
                "unsupported_feature",
                "Relationship signature is outside reviewed coverage",
            )
        key = uuid(record["Id"])
        a, b = uuid(record["ThoughtIdA"]), uuid(record["ThoughtIdB"])
        if key in keys or record.get("BrainId") != brain_id:
            refuse(
                "invalid_source", "Duplicate relationship or foreign ownership", (key,)
            )
        keys.add(key)
        if a not in thoughts or b not in thoughts:
            refuse(
                "invalid_reference", "Relationship has a nonlive endpoint", (key, a, b)
            )
        if record.get("TypeId") or record.get("LinkTypeId"):
            refuse(
                "unsupported_feature",
                "Custom relationship types are unverified",
                (key,),
            )
        signature = tuple(record[field] for field in fields)
        roles = thoughts[a]["Kind"], thoughts[b]["Kind"]
        kind = None
        if (
            signature in {(1, 1, 1, -1), (1, 1, 1, 1), (1, 1, 1, 7)}
            and roles == (1, 1)
            or signature == (1, 1, 1, -1)
            and roles == (1, 4)
        ):
            kind = "hierarchy"
        elif signature in {
            (1, 3, 1, -1),
            (1, 3, 1, 3),
            (1, 3, 1, 5),
            (1, 3, 1, 7),
        } and roles == (1, 1):
            kind = "related"
        elif signature == (1, 1, 6, -1) and roles[0] == 5 and roles[1] in {1, 4}:
            kind = "system"
        elif signature == (1, 1, 5, -1) and roles == (4, 1):
            kind = "tag"
        if kind is None:
            refuse(
                "unsupported_feature",
                "Relationship meaning/endpoints are outside reviewed coverage",
                (key,),
            )
        result.append(
            Relationship(
                key=key,
                kind=kind,
                item_a=a,
                item_b=b,
                evidence=(f"links.json:{index}",),
            )
        )
    return tuple(result)
