"""Validate source-neutral classification facts without interpreting source fields."""

from itertools import pairwise

from .cycles import directed_cycle


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
            or member.role not in {"ordinary", "definition"}
            or (relationship.item_a, relationship.item_b)
            != (definition.key, member.key)
            or not assignment.evidence
            or not set(assignment.evidence) <= known_evidence
        ):
            refuse(
                "invalid_reference",
                "Classification requires a live definition and matching ordinary or definition member",
            )
    cycle = directed_cycle((a.item_key, a.definition_key) for a in assignments)
    if cycle:
        cycle_pairs = set(pairwise(cycle))
        cycle_assignments = tuple(
            a for a in assignments if (a.item_key, a.definition_key) in cycle_pairs
        )
        refuse(
            "source_type_cycle",
            "Source type assignments contain a cycle or self-assignment",
            affected=tuple(
                dict.fromkeys(
                    (*cycle, *(a.relationship_key for a in cycle_assignments))
                )
            ),
            evidence=tuple(
                dict.fromkeys(e for a in cycle_assignments for e in a.evidence)
            ),
        )
