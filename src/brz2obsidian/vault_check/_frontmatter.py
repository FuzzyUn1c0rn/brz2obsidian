"""Private data-only YAML parsing and documented native property validation."""

import re
from datetime import date, datetime

from brz2obsidian.obsidian_dialect import (
    blank,
    category,
    frontmatter,
    mapping,
    wikilink,
)

from .contracts import VaultCheckIssue

__all__ = [
    "blank",
    "category",
    "frontmatter",
    "mapping",
    "valid_date",
    "wikilink",
]


def valid_date(value, template):
    if blank(value) or (type(value) is date):
        return True
    if isinstance(value, datetime) or not isinstance(value, str):
        return False
    if template and value in {"{{date}}", "{{date:YYYY-MM-DD}}"}:
        return True
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def validate(properties, artifact):
    issues = []
    template = artifact.split("/")[0] == "Templates"
    expected = {
        "categories": lambda v: isinstance(v, list) and all(wikilink(x) for x in v),
        "appearance_category": lambda v: blank(v) or wikilink(v),
        "icon": lambda v: blank(v) or wikilink(v),
        "tags": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
        "aliases": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
        "created": lambda v: valid_date(v, template),
        "updated": lambda v: valid_date(v, template),
        "source_collection_id": lambda v: isinstance(v, str) and bool(v.strip()),
        "source_item_id": lambda v: isinstance(v, str) and bool(v.strip()),
    }
    for name, predicate in expected.items():
        if name in properties and not predicate(properties[name]):
            issues.append(
                VaultCheckIssue(
                    code="invalid_property",
                    artifact=artifact,
                    property=name,
                    message=f"{name} has an invalid type, cardinality or value.",
                    guidance="Use the documented native property shape; custom properties may remain.",
                )
            )
    identities = ("source_collection_id", "source_item_id")
    if sum(name in properties for name in identities) == 1:
        missing = next(name for name in identities if name not in properties)
        issues.append(
            VaultCheckIssue(
                code="invalid_property",
                artifact=artifact,
                property=missing,
                message="Imported source identities must be present together.",
                guidance="Keep both opaque imported identities, or omit both on a new object.",
            )
        )
    return issues
