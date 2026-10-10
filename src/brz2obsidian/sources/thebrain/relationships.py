"""Interpret only the independently verified TheBrain graph signatures."""

import json

from brz2obsidian.contracts import Relationship

from .semantics import validate_semantic_fields


def relationship_problem(record, index, refuse, uuid, code, message, *, private=False):
    """Name only trusted included identities; arbitrary metadata stays in source."""
    if private:
        refuse(code, message)
    subjects = []
    for field in ("Id", "ThoughtIdA", "ThoughtIdB"):
        try:
            subjects.append(uuid(record.get(field)))
        except ValueError, TypeError, AttributeError:
            pass
    signature = ", ".join(
        f"{field}={json.dumps(record.get(field))}"
        if type(record.get(field)) in {int, bool, str, type(None)}
        else f"{field}: invalid {type(record.get(field)).__name__}"
        for field in ("Kind", "Relation", "Meaning", "Direction")
    )
    refuse(
        code,
        message,
        tuple(dict.fromkeys(subjects)),
        evidence=(f"links.json:{index}", signature),
        guidance="Review the included relationship signature, endpoint roles and ownership in the source records before re-exporting.",
    )


def decode_relationships(
    records, thoughts, brain_id, refuse, uuid, *, private_record=None
):
    result, keys = [], set()
    for index, record in enumerate(records):

        def problem(code, message, affected=(), *, record=record, index=index):
            relationship_problem(
                record,
                index,
                refuse,
                uuid,
                code,
                message,
                private=private_record(record) if private_record is not None else False,
            )

        validate_semantic_fields(record, problem)
        fields = ("Kind", "Relation", "Meaning", "Direction")
        if any(type(record.get(field)) is not int for field in fields):
            problem(
                "unsupported_feature",
                "Relationship signature is outside reviewed coverage",
            )
        key = uuid(record["Id"])
        a, b = uuid(record["ThoughtIdA"]), uuid(record["ThoughtIdB"])
        if key in keys or record.get("BrainId") != brain_id:
            problem(
                "invalid_source", "Duplicate relationship or foreign ownership", (key,)
            )
        keys.add(key)
        if a not in thoughts or b not in thoughts:
            problem(
                "invalid_reference", "Relationship has a nonlive endpoint", (key, a, b)
            )
        if record.get("TypeId") or record.get("LinkTypeId"):
            problem(
                "unsupported_feature",
                "Custom relationship types are unverified",
                (key,),
            )
        signature = tuple(record[field] for field in fields)
        roles = thoughts[a]["Kind"], thoughts[b]["Kind"]
        kind = None
        if (
            signature in {(1, 1, 1, -1), (1, 1, 1, 1), (1, 1, 1, 3), (1, 1, 1, 7)}
            and roles == (1, 1)
            or signature == (1, 1, 1, -1)
            and roles in {(1, 2), (1, 4)}
        ):
            kind = "hierarchy"
        elif (
            signature in {(1, 3, 1, -1), (1, 3, 1, 3), (1, 3, 1, 5), (1, 3, 1, 7)}
            and roles == (1, 1)
            or signature == (1, 3, 1, -1)
            and roles == (1, 2)
        ):
            kind = "related"
        elif signature == (1, 1, 6, -1) and roles[0] == 5 and roles[1] in {1, 2, 4}:
            kind = "system"
        elif signature == (1, 1, 2, -1) and roles == (2, 1):
            kind = "classification"
        elif signature == (1, 1, 5, -1) and roles == (4, 1):
            kind = "tag"
        if kind is None:
            problem(
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
