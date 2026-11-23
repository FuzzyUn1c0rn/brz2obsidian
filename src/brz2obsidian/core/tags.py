"""Source-neutral tag naming and presentation selection."""

import re
import unicodedata
from hashlib import sha256

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
        if any(not m.native or m.item_key in tokens for m in memberships)
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


def scoped_tags(snapshot, targets, existing, reuse, remembered=()):
    choices = dict(reuse)
    retained = {source: token for source, token, _ in remembered} | choices
    available = set(existing)
    identities = {target.original_identity for target in targets}
    if (
        len(choices) != len(reuse)
        or choices.keys() - identities
        or any(token not in available for token in choices.values())
        or any(not _valid_vault_tag(token) for token in retained.values())
    ):
        raise MigrationRefused(
            (
                Issue(
                    code="import_tag_reuse_unavailable",
                    phase="planning",
                    message="An existing vault tag choice no longer matches the source or vault.",
                    guidance="Review the tag mapping with the current vault.",
                ),
            )
        )
    prefix = _import_tag_prefix(snapshot, available, remembered)
    occupied = {_tag_key(token) for token in available | set(retained.values())}
    result = []
    for target in targets:
        token = retained.get(target.original_identity)
        if token is None:
            base = f"{prefix}/{target.token}"
            token = base
            seed = sha256(target.original_identity.encode()).hexdigest()[:8]
            collision = 0
            while _tag_key(token) in occupied:
                collision += 1
                suffix = f"-{seed}" if collision == 1 else f"-{seed}-{collision}"
                token = f"{prefix}/{target.token[: 120 - len(suffix)]}{suffix}"
            occupied.add(_tag_key(token))
        result.append(target.model_copy(update={"token": token}))
    return tuple(result)


def _tag_key(token):
    return unicodedata.normalize("NFC", token).casefold()


def _import_tag_prefix(snapshot, existing, remembered):
    prior = next(
        (
            token.partition("/")[0]
            for _, token, mode in remembered
            if mode == "new" and "/" in token
        ),
        None,
    )
    if prior is not None:
        return prior
    occupied = {_tag_key(token.partition("/")[0]) for token in existing} | {
        "categories"
    }
    base = _token(snapshot.collection_title)[:100].rstrip("-")
    prefix = base
    identity = snapshot.identity
    seed = sha256((identity.module_id + "\0" + identity.source_id).encode()).hexdigest()
    collision = 0
    while _tag_key(prefix) in occupied:
        collision += 1
        suffix = f"-{seed[:8]}" if collision == 1 else f"-{seed[:8]}-{collision}"
        prefix = base + suffix
    return prefix


def _valid_vault_tag(value):
    return (
        re.fullmatch(r"[\w/-]+", value) is not None
        and all(value.split("/"))
        and not value.replace("/", "").isnumeric()
    )
