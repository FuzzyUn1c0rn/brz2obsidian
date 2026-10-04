"""Validate source-neutral classification facts without interpreting source fields."""


def validate_classifications(snapshot, refuse):
    items = {item.key: item for item in snapshot.items}
    relationships = {
        r.key: r for r in snapshot.relationships if r.kind == "classification"
    }
    assignments = snapshot.classification_assignments
    known_evidence = {e.identity for e in snapshot.accounting.entries} | {
        e.key for e in snapshot.original_evidence
    }
    if len({a.relationship_key for a in assignments}) != len(assignments) or len(
        {a.item_key for a in assignments}
    ) != len(assignments):
        refuse(
            "invalid_reference",
            "Classification assignments must have unique members and relationships",
        )
    if {a.relationship_key for a in assignments} != set(relationships):
        refuse(
            "invalid_reference",
            "Classification facts and relationships must correspond in both directions",
        )
    for assignment in assignments:
        definition = items.get(assignment.definition_key)
        member = items.get(assignment.item_key)
        relationship = relationships[assignment.relationship_key]
        if (
            definition is None
            or member is None
            or not definition.live
            or not member.live
            or definition.role != "definition"
            or member.role != "ordinary"
            or (relationship.item_a, relationship.item_b)
            != (definition.key, member.key)
            or not assignment.evidence
            or not set(assignment.evidence) <= known_evidence
        ):
            refuse(
                "invalid_reference",
                "Classification requires a live definition and matching ordinary member",
            )
