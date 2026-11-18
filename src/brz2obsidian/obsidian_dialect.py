"""Data-only native property and file-role predicates shared by readers."""

import html
import json
import re
from hashlib import sha256
from pathlib import PurePosixPath

import yaml

from brz2obsidian.contracts import (
    REVIEWABLE_OUTPUT_FORMATS,
    FileRoleFacts,
    MembershipDeclarationFacts,
    ReferenceDeclarationFacts,
    SourceIdentity,
)

IMAGE_EXTENSIONS = frozenset(
    (".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp")
)

_PLAYER_MARKUP = (
    '<iframe src="{uri}" width="560" height="315" title="YouTube video player" '
    'frameborder="0" allowfullscreen></iframe>'
)
_CANONICAL_PLAYER = re.compile(
    re.escape(_PLAYER_MARKUP).replace(
        re.escape("{uri}"),
        r"https://www\.youtube\.com/embed/[A-Za-z0-9_-]{11}\?start=(?:0|[1-9][0-9]*)",
    )
)


def video_player_markup(uri):
    return _PLAYER_MARKUP.format(uri=html.escape(uri, quote=True))


def canonical_player_ranges(text):
    """Recognize only this closed external markup shape, never its provenance."""
    return [(match.start(), match.end()) for match in _CANONICAL_PLAYER.finditer(text)]


def migration_record_data(text, source_path, *, record_format=8):
    """Recognize a supported data envelope, without validating its authority."""
    if source_path != "migration-record.json":
        return False

    def unique_members(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate record-data member")
            result[key] = value
        return result

    def non_json_constant(_):
        raise ValueError("Non-JSON record-data constant")

    try:
        value = json.loads(
            text, object_pairs_hook=unique_members, parse_constant=non_json_constant
        )
        if (
            not isinstance(value, dict)
            or value.get("schema") != "brz2obsidian.migration"
            or type(value.get("schema_version")) is not int
            or type(record_format) is not int
            or record_format not in (6, *REVIEWABLE_OUTPUT_FORMATS)
            or value["schema_version"] != record_format
            or any(
                not isinstance(value.get(key), str) or not value[key]
                for key in ("profile_id", "profile_version")
            )
            or any(
                not isinstance(value.get(key), list)
                or not all(isinstance(row, dict) for row in value[key])
                for key in ("item_targets", "asset_targets")
            )
        ):
            return False
        SourceIdentity.model_validate(value["source_identity"])
    except ValueError, KeyError, TypeError:
        return False
    return True


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


def category(properties, artifact):
    parts = artifact.split("/")
    return (
        parts[0] == "Categories"
        and not any(part in {"Templates", "Attachments"} for part in parts[:-1])
        and isinstance(properties.get("tags"), list)
        and "categories" in properties["tags"]
    )


def blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def wikilink(value):
    return isinstance(value, str) and bool(re.fullmatch(r"\[\[[^\[\]\r\n]+\]\]", value))


def image_path(artifact):
    return PurePosixPath(artifact).suffix.lower() in IMAGE_EXTENSIONS


def nonempty_image(artifact, size):
    return image_path(artifact) and size > 0


def native_properties(content):
    if content is None:
        return None
    try:
        properties, _ = frontmatter(content.data.decode("utf-8"))
        return properties
    except UnicodeError, ValueError, yaml.YAMLError:
        return None


def file_roles(content, *, path, existence, reference_query):
    note = path.lower().endswith(".md")
    properties = native_properties(content) if existence == "present" and note else {}

    def declaration(name):
        value = None if properties is None else properties.get(name)
        status, query = "invalid", None
        if properties is not None:
            if name not in properties:
                status = "absent"
            elif blank(value):
                status = "blank"
            elif wikilink(value):
                query = reference_query(value)
                if query is not None:
                    status = "valid"
        return ReferenceDeclarationFacts(status=status, query=query)

    queries, status = (), "invalid"
    if properties is not None:
        if "categories" not in properties:
            status = "absent"
        elif isinstance(properties["categories"], list):
            values = properties["categories"]
            queries = tuple(
                reference_query(value) for value in values if wikilink(value)
            )
            status = (
                "valid"
                if len(queries) == len(values)
                and all(query is not None for query in queries)
                else "invalid"
            )
            queries = tuple(query for query in queries if query is not None)
    return FileRoleFacts(
        path=path,
        content_sha256=None if content is None else sha256(content.data).hexdigest(),
        category=note and existence == "present" and category(properties or {}, path),
        image_path=image_path(path),
        category_memberships=MembershipDeclarationFacts(status=status, queries=queries),
        provider=declaration("appearance_category"),
        owned_icon=declaration("icon"),
    )
