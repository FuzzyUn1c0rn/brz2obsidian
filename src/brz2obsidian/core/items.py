"""Deterministic item eligibility, hierarchy coverage and target reservation."""

import unicodedata

from brz2obsidian.contracts import Issue, ItemTarget, MigrationRefused

from .naming import collision_keys, extended_seed_width, readable_filename
from .support import SUPPORTING_NAMES


def _readable(title):
    # Note titles discard all Unicode control characters; resource names retain
    # the original non-ASCII controls under their established naming policy.
    return readable_filename(
        "".join(" " if unicodedata.category(char) == "Cc" else char for char in title)
    )


def _bounded(readable, prefix, suffix):
    limit = 120 - len((prefix + suffix).encode("utf-16-le")) // 2
    if limit < 1:
        raise MigrationRefused(
            (
                Issue(
                    code="target_path_too_long",
                    phase="planning",
                    message="Identity marker exceeds the note stem limit",
                    guidance="Supply shorter distinct naming seeds.",
                ),
            )
        )
    while len(readable.encode("utf-16-le")) // 2 > limit:
        readable = readable[:-1]
    return prefix + readable.rstrip(" .") + suffix


def assign_item_targets(analysis, resource_owners=()):
    snapshot = analysis.snapshot
    items = sorted(
        (i for i in snapshot.items if i.live and i.role != "system"),
        key=lambda i: i.key,
    )
    documents = {d.key: d for d in snapshot.documents}
    reasons = {}
    classified = {a.item_key for a in snapshot.classification_assignments}
    for item in items:
        selected = []
        if (
            any(documents[key].text.strip() for key in item.document_ids)
            or item.key in resource_owners
        ):
            selected.append("content")
        if item.key == analysis.entry_key:
            selected.append("home")
        if item.role == "definition":
            selected.append("definition")
        if item.key in classified:
            selected.append("classification")
        if selected:
            reasons[item.key] = tuple(selected)
    edges = [
        (r.item_a, r.item_b) for r in snapshot.relationships if r.kind == "hierarchy"
    ]
    while uncovered := [
        (a, b) for a, b in edges if a not in reasons and b not in reasons
    ]:
        parents = {a for a, b in uncovered}
        chosen = min(
            parents, key=lambda key: (-sum(key in {a, b} for a, b in uncovered), key)
        )
        reasons[chosen] = ("hierarchy",)
    readable = {item.key: _readable(item.title) for item in items}
    widths = {item.key: 0 for item in items}
    seeds = {item.key: item.naming_seed for item in items}
    while True:
        stems = {
            item.key: _bounded(
                readable[item.key],
                "Home — " if item.key == analysis.entry_key else "",
                " — " + item.naming_seed[: widths[item.key]]
                if widths[item.key]
                else "",
            )
            for item in items
        }
        collisions = collision_keys(stems, widths, seeds, SUPPORTING_NAMES)
        if not collisions:
            break
        for item in items:
            if item.key in collisions:
                new_width = extended_seed_width(widths[item.key], item.naming_seed)
                if new_width is None:
                    raise MigrationRefused(
                        (
                            Issue(
                                code="invalid_source",
                                phase="planning",
                                message="Naming seeds cannot distinguish colliding item targets",
                                affected=tuple(sorted(collisions)),
                                guidance="Provide distinct stable naming seeds for these source items.",
                            ),
                        )
                    )
                widths[item.key] = new_width
    return tuple(
        ItemTarget(
            item_key=i.key,
            original_identity=i.original_identity,
            original_title=i.title,
            relative_path=(
                ""
                if i.key == analysis.entry_key
                else "Categories/"
                if i.role == "definition"
                else "Notes/"
            )
            + stems[i.key]
            + ".md",
            created=i.key in reasons,
            creation_reasons=reasons.get(i.key, ()),
        )
        for i in items
    )


def select_fallbacks(snapshot, item_targets):
    targets = {t.item_key: t for t in item_targets}
    items = {i.key: i for i in snapshot.items}
    represented, pairs = set(), set()
    for relation in snapshot.relationships:
        a, b = relation.item_a, relation.item_b
        if relation.kind in {"hierarchy", "related", "tag"}:
            represented.update((a, b))
        if (
            relation.kind == "related"
            and not targets[a].created
            and not targets[b].created
        ):
            pairs.add(tuple(sorted((a, b))))
    for document in snapshot.documents:
        if document.owner in targets and targets[document.owner].created:
            represented.update(
                ref.target for ref in document.references if ref.kind == "item"
            )
    isolated = tuple(
        sorted(
            key
            for key, target in targets.items()
            if not target.created
            and items[key].role == "ordinary"
            and key not in represented
        )
    )
    return isolated, tuple(sorted(pairs))
