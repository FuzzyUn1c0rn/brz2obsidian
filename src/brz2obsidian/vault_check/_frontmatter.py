"""Private data-only YAML parsing and documented native property validation."""

import re
from datetime import date, datetime

import yaml

from .contracts import VaultCheckIssue


class _UniqueSafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        if isinstance(node, yaml.MappingNode):
            self.flatten_mapping(node)
            seen = set()
            for key_node, _ in node.value:
                key = self.construct_object(key_node, deep=deep)
                try:
                    if key in seen:
                        raise yaml.constructor.ConstructorError(
                            None, None, "duplicate mapping key", key_node.start_mark
                        )
                    seen.add(key)
                except TypeError as error:
                    raise yaml.constructor.ConstructorError(
                        None, None, "non-scalar mapping key", key_node.start_mark
                    ) from error
        return super().construct_mapping(node, deep=deep)


def mapping(text):
    value = yaml.load(text, Loader=_UniqueSafeLoader)
    if value is None and not text.strip():
        return {}
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not key.strip() for key in value
    ):
        raise ValueError("Expected a mapping with nonempty string property names")
    return value


def frontmatter(text):
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip("\r\n") != "---":
        return {}, text
    for index, line in enumerate(lines[1:], 1):
        if line.strip("\r\n") in {"---", "..."}:
            return mapping("".join(lines[1:index])), "".join(lines[index + 1 :])
    raise ValueError("Frontmatter has no closing delimiter")


def blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def wikilink(value):
    return isinstance(value, str) and bool(re.fullmatch(r"\[\[[^\[\]\r\n]+\]\]", value))


def category(properties, artifact):
    parts = artifact.split("/")
    return (
        parts[0] == "Categories"
        and not any(part in {"Templates", "Attachments"} for part in parts[:-1])
        and isinstance(properties.get("tags"), list)
        and "categories" in properties["tags"]
    )


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
        "foreground_color": lambda v: (
            blank(v)
            or (isinstance(v, str) and bool(re.fullmatch(r"#[0-9a-fA-F]{6}", v)))
        ),
        "background_color": lambda v: (
            blank(v)
            or (isinstance(v, str) and bool(re.fullmatch(r"#[0-9a-fA-F]{6}", v)))
        ),
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
