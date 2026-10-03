"""Source-neutral tag naming and presentation selection."""

import re
import unicodedata

from brz2obsidian.contracts import Issue, MigrationRefused, TagMembership, TagTarget

from .naming import collision_keys, extended_seed_width


def _token(title):
    normalized = unicodedata.normalize("NFC", title)
    value = re.sub(r"[\W_]+", "-", normalized)
    value = re.sub(r"-+", "-", value).strip("-") or "source-tag"
    return "tag-" + value if value.isnumeric() else value


def assign_tags(snapshot, item_targets):
    tags = sorted(
        (i for i in snapshot.items if i.live and i.role == "tag"), key=lambda i: i.key
    )
    widths = {i.key: 0 for i in tags}
    bases = {i.key: _token(i.title) for i in tags}
    seeds = {i.key: i.naming_seed for i in tags}
    while True:
        tokens = {}
        for tag in tags:
            suffix = "-" + tag.naming_seed[: widths[tag.key]] if widths[tag.key] else ""
            if len(suffix) >= 120:
                raise MigrationRefused(
                    (
                        Issue(
                            code="target_path_too_long",
                            phase="planning",
                            message="Tag identity suffix exceeds token limit",
                            guidance="Supply shorter distinct naming seeds.",
                        ),
                    )
                )
            base = bases[tag.key][: 120 - len(suffix)].rstrip("-")
            if base.isnumeric():
                base = "tag-" + base[: 116 - len(suffix)]
            tokens[tag.key] = base + suffix
        collisions = collision_keys(tokens, widths, seeds)
        if not collisions:
            break
        for key in sorted(collisions):
            new_width = extended_seed_width(widths[key], seeds[key])
            if new_width is None:
                raise MigrationRefused(
                    (
                        Issue(
                            code="invalid_source",
                            phase="planning",
                            message="Naming seeds cannot distinguish colliding tag tokens",
                            affected=tuple(sorted(collisions)),
                            guidance="Provide distinct stable naming seeds for these source tags.",
                        ),
                    )
                )
            widths[key] = new_width
    targets = {t.item_key: t for t in item_targets}
    memberships = tuple(
        TagMembership(
            relationship_key=r.key,
            tag_key=r.item_a,
            item_key=r.item_b,
            native=targets[r.item_b].created,
        )
        for r in sorted(snapshot.relationships, key=lambda r: r.key)
        if r.kind == "tag"
    )
    assigned = {m.tag_key for m in memberships}
    listing_path = (
        "Tag memberships.md"
        if any(not m.native for m in memberships)
        or any(t.key not in assigned for t in tags)
        else None
    )
    return (
        tuple(
            TagTarget(
                tag_key=t.key,
                original_identity=t.original_identity,
                original_name=t.title,
                token=tokens[t.key],
            )
            for t in tags
        ),
        memberships,
        listing_path,
    )
