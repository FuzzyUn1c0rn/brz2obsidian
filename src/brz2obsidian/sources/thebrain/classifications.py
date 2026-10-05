"""Join the reviewed assignment field to exactly one exported instance link."""

from brz2obsidian.contracts import ClassificationAssignment


def decode_classifications(thoughts, relationships, refuse, uuid):
    instances = {}
    for relationship in relationships:
        if relationship.kind == "classification":
            instances.setdefault(relationship.item_b, []).append(relationship)
    assignments = []
    for index, (key, thought) in enumerate(thoughts.items()):
        declared = thought.get("TypeId")
        links = instances.get(key, [])
        if declared:
            definition = uuid(declared)
            if (
                thought["Kind"] != 1
                or definition not in thoughts
                or thoughts[definition]["Kind"] != 2
            ):
                refuse(
                    "invalid_reference",
                    "TypeId must join an ordinary member to a live type definition",
                    (key, definition),
                )
            if len(links) != 1 or links[0].item_a != definition:
                refuse(
                    "invalid_reference",
                    "TypeId must agree with exactly one exported instance relationship",
                    (key, definition),
                )
            assignments.append(
                ClassificationAssignment(
                    relationship_key=links[0].key,
                    definition_key=definition,
                    item_key=key,
                    evidence=(f"thoughts.json:{index}",) + links[0].evidence,
                )
            )
        elif links:
            refuse(
                "invalid_reference",
                "Instance relationship lacks its corresponding TypeId",
                (key,),
            )
    return tuple(sorted(assignments, key=lambda assignment: assignment.item_key))
