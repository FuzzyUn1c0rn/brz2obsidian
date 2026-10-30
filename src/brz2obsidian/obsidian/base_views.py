"""Exact named-view anchors from bounded Base YAML, without reading vault files."""

import yaml

from brz2obsidian.contracts import LinkAnchor, LinkFragment, StructureSpan


def _fields(node):
    if not isinstance(node, yaml.MappingNode) or node.tag != "tag:yaml.org,2002:map":
        raise ValueError("base_mapping_unsupported")
    fields = {}
    for key, value in node.value:
        if key.tag != "tag:yaml.org,2002:str" or key.value in fields:
            raise ValueError("base_mapping_ambiguous")
        fields[key.value] = value
    return fields


def view_anchors(text):
    """Interpret actual view names; unsupported syntax never grants an anchor."""
    root = yaml.compose(text, Loader=yaml.SafeLoader)
    views = _fields(root).get("views")
    if not isinstance(views, yaml.SequenceNode):
        raise ValueError("base_views_unsupported")
    anchors = []
    for view in views.value:
        name = _fields(view).get("name")
        if (
            not isinstance(name, yaml.ScalarNode)
            or name.tag != "tag:yaml.org,2002:str"
            or not name.value
        ):
            raise ValueError("base_name_unsupported")
        start, end = name.start_mark.index, name.end_mark.index
        if name.style in ("'", '"'):
            start, end = start + 1, end - 1
        if text[start:end] != name.value or any(ord(c) < 32 for c in name.value):
            raise ValueError("base_name_unbound")
        # "heading" records the non-block # destination syntax. For .base
        # media its exact destination is a named view rather than a Markdown heading.
        anchors.append(
            LinkAnchor(
                fragment=LinkFragment(kind="heading", value=name.value),
                spans=(
                    StructureSpan(
                        start=len(text[:start].encode()),
                        end=len(text[:end].encode()),
                    ),
                ),
                raw_parts=(name.value.encode(),),
            )
        )
    return tuple(anchors)
