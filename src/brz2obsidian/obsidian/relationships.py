"""Serialize qualified links and focused graph presentations."""

import re


def note_link(target, title):
    label = re.sub(r"[\[\]|\r\n]", " ", title)
    return "[[" + target.relative_path + "|" + " ".join(label.split()) + "]]"


def relationship_sections(plan, key):
    targets = {t.item_key: t for t in plan.item_targets}
    items = {i.key: i for i in plan.analysis.snapshot.items}
    sections = {"Parents": set(), "Children": set(), "Related": set()}
    for relation in plan.analysis.snapshot.relationships:
        a, b = relation.item_a, relation.item_b
        if relation.kind == "hierarchy":
            if key == a:
                sections["Children"].add(b)
            if key == b:
                sections["Parents"].add(a)
        elif relation.kind == "related":
            if key == a:
                sections["Related"].add(b)
            if key == b:
                sections["Related"].add(a)
    text = ""
    for heading, neighbors in sections.items():
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
