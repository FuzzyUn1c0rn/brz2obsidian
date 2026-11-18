"""Serialize qualified links and focused graph presentations."""

import re
from collections import defaultdict


def note_link(target, title):
    label = re.sub(r"[\[\]|\r\n]", " ", title)
    return "[[" + target.relative_path + "|" + " ".join(label.split()) + "]]"


def navigation_index(relationships):
    neighbors = defaultdict(lambda: defaultdict(set))
    for relation in relationships:
        a, b = relation.item_a, relation.item_b
        if relation.kind == "hierarchy":
            neighbors[a]["Children"].add(b)
            neighbors[b]["Parents"].add(a)
        elif relation.kind == "related":
            neighbors[a]["Related"].add(b)
            neighbors[b]["Related"].add(a)
    return neighbors


def relationship_sections(
    sections, targets, items, *, headings=("Parents", "Children", "Related")
):
    text = ""
    for heading in headings:
        neighbors = sections.get(heading)
        if neighbors:
            text += (
                "## "
                + heading
                + "\n\n"
                + "".join(
                    "- " + note_link(targets[n], items[n].title) + "\n"
                    for n in sorted(neighbors)
                )
                + "\n"
            )
    return text.rstrip("\n") + "\n" if text else ""


def uncreated_listing(plan):
    targets = {t.item_key: t for t in plan.item_targets}
    snapshot = plan.analysis.snapshot
    items = {i.key: i for i in snapshot.items}
    isolated = plan.isolated_item_keys
    pairs = plan.uncreated_related_pairs
    if not isolated and not pairs:
        return ""
    text = "# Uncreated targets\n\n"
    if isolated:
        text += (
            "## Isolated thoughts\n\n"
            + "".join(
                "- " + note_link(targets[k], items[k].title) + "\n" for k in isolated
            )
            + "\n"
        )
    if pairs:
        text += "## Related pairs\n\n" + "".join(
            "- "
            + note_link(targets[a], items[a].title)
            + " — "
            + note_link(targets[b], items[b].title)
            + "\n"
            for a, b in sorted(pairs)
        )
    return text.rstrip("\n") + "\n"
