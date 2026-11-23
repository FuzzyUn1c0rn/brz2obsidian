"""Read the vault's native category and tag candidates without taking ownership."""

import re
import unicodedata
from collections import defaultdict
from hashlib import sha256
from pathlib import PurePosixPath

import yaml
from markdown_it import MarkdownIt

from brz2obsidian.contracts import (
    ImportCategoryCandidate,
    ImportCategoryChoice,
    ImportClassificationReview,
    Issue,
    MigrationRefused,
)
from brz2obsidian.obsidian_dialect import category, frontmatter, mapping


def _key(value):
    return unicodedata.normalize("NFC", value).casefold()


def _tags(properties, body, parser):
    values = properties.get("tags", ())
    if isinstance(values, str):
        values = re.split(r"[,\s]+", values)
    if not isinstance(values, (list, tuple)):
        values = ()
    body = re.sub(
        r"<!--.*?(?:-->|\Z)|%%.*?(?:%%|\Z)|!?\[\[.*?\]\]", " ", body, flags=re.DOTALL
    )
    inline = {
        match
        for token in parser.parse(body)
        for child in token.children or ()
        if child.type == "text"
        for match in re.findall(r"(?<![\w/])#([\w/-]+)", child.content)
    }
    return {
        value
        for value in (*values, *inline)
        if isinstance(value, str)
        and re.fullmatch(r"[\w/-]+", value)
        and all(value.split("/"))
        and not value.replace("/", "").isnumeric()
    }


def _linked_members(body, existing):
    for path in re.findall(r"!\[\[([^\[\]#|]+\.base)(?:#[^\[\]]+)?\]\]", body):
        raw = existing.get(path)
        if not isinstance(raw, bytes):
            continue
        try:
            data = mapping(raw.decode("utf-8"))
        except UnicodeError, ValueError, yaml.YAMLError:
            continue
        filters = data.get("filters")
        items = filters.get("and") if isinstance(filters, dict) else None
        if isinstance(items, list) and "list(categories).contains(this)" in items:
            return True
    return False


def vault_classifications(existing, *, excluded=(), collections=()):
    parser = MarkdownIt("commonmark")
    categories, tags = [], set()
    modules = defaultdict(set)
    for module, collection in collections:
        modules[collection].add(module)
    for path, raw in sorted(existing.items()):
        if not path.casefold().endswith(".md") or not isinstance(raw, bytes):
            continue
        try:
            properties, body = frontmatter(raw.decode("utf-8"))
        except UnicodeError, ValueError, yaml.YAMLError:
            continue
        observed_tags = _tags(properties, body, parser)
        tags.update(observed_tags)
        if path in excluded or not category(properties, path, scoped=True):
            continue
        collection = properties.get("source_collection_id")
        item = properties.get("source_item_id")
        identity = (
            (next(iter(modules[collection])), collection, item)
            if isinstance(collection, str)
            and len(modules.get(collection, ())) == 1
            and isinstance(item, str)
            and item
            else None
        )
        categories.append(
            ImportCategoryCandidate(
                destination_path=path,
                destination_sha256=sha256(raw).hexdigest(),
                destination_identity=identity,
                link_members_view="linked_members"
                if _linked_members(body, existing)
                else "compatible_view_available",
            )
        )
    return tuple(categories), tuple(
        sorted(tags, key=lambda token: (_key(token), token))
    )


def classification_review(snapshot, categories, tags):
    types = tuple(
        (row.original_identity, row.title)
        for row in snapshot.items
        if row.live and row.role == "definition"
    )
    source_tags = tuple(
        (row.original_identity, row.title)
        for row in snapshot.items
        if row.live and row.role == "tag"
    )
    return ImportClassificationReview(
        source_categories=types,
        source_tags=source_tags,
        vault_categories=categories,
        vault_tags=tags,
        category_suggestions=tuple(
            (source, row.destination_path)
            for source, title in types
            for row in categories
            if _key(title) == _key(PurePosixPath(row.destination_path).stem)
        ),
    )


def require_classification_choices(review, choices, *, preview=False):
    choices = tuple(ImportCategoryChoice.model_validate(row) for row in choices)
    required = {key for key, _ in review.source_categories}
    if preview or {row.source_identity for row in choices} != required:
        refuse_classification("import_classification_review_required")
    qualify_category_targets(choices, review.vault_categories)
    return choices


def qualify_category_targets(choices, candidates):
    by_path = {row.destination_path: row for row in candidates}
    for choice in choices:
        path = choice.destination_path
        if path is None:
            continue
        target = by_path.get(path)
        if (
            target is None
            or target.destination_sha256 != choice.destination_sha256
            or target.destination_identity != choice.destination_identity
            or choice.destination_identity is not None
            and sum(
                row.destination_identity == choice.destination_identity
                for row in candidates
            )
            != 1
        ):
            refuse_classification("import_category_target_changed")


def refuse_classification(code):
    raise MigrationRefused(
        (
            Issue(
                code=code,
                phase="planning",
                message="Review the category and tag choices against the current vault.",
                guidance="Choose a separate definition or a supported existing target.",
            ),
        )
    )


def reobserve_category_choices(choices, candidates):
    result = []
    for choice in choices:
        if choice.destination_identity is None:
            qualify_category_targets((choice,), candidates)
            result.append(choice)
            continue
        matches = tuple(
            row
            for row in candidates
            if row.destination_identity == choice.destination_identity
        )
        if len(matches) != 1:
            refuse_classification("import_category_target_ambiguous")
        (target,) = matches
        result.append(
            choice.model_copy(
                update={
                    "destination_path": target.destination_path,
                    "destination_sha256": target.destination_sha256,
                }
            )
        )
    return tuple(result)
