"""Full native templates for new objects, with no imported source identity."""

import json

from brz2obsidian.core.support import category_template_path

from .bases import CATEGORY_VIEWS, MEMBERS
from .guide import vault_guide

TEMPLATE_CONFIGURATION = {"folder": "Templates", "dateFormat": "YYYY-MM-DD"}
PROPERTY_TYPES = {
    "categories": "multitext",
    "appearance_category": "text",
    "icon": "text",
    "foreground_color": "text",
    "background_color": "text",
    "created": "date",
    "updated": "date",
    "tags": "tags",
    "aliases": "aliases",
    "source_collection_id": "text",
    "source_item_id": "text",
}


def new_object_template(category=None, tags=()):
    properties = {
        "categories": [category] if category else [],
        "appearance_category": category,
        "icon": None,
        "foreground_color": None,
        "background_color": None,
        "created": "{{date:YYYY-MM-DD}}",
        "updated": "{{date:YYYY-MM-DD}}",
        "tags": list(tags),
        "aliases": [],
    }
    lines = ["---"]
    for name, value in properties.items():
        if name in {"created", "updated"}:
            lines.append(name + ": " + value)
        elif isinstance(value, list) and value:
            lines.append(name + ":")
            lines.extend("  - " + json.dumps(v, ensure_ascii=False) for v in value)
        elif value is None:
            lines.append(name + ":")
        else:
            lines.append(name + ": " + json.dumps(value, ensure_ascii=False))
    return "\n".join(lines) + "\n---\n\n# {{title}}\n"


def category_template_files(plan):
    definitions = {
        i.key for i in plan.analysis.snapshot.items if i.role == "definition"
    }
    return tuple(
        (
            category_template_path(t),
            new_object_template("[[" + t.relative_path + "]]"),
        )
        for t in plan.item_targets
        if t.item_key in definitions
    )


def support_files(plan):
    return (
        ("Templates/New note.md", new_object_template()),
        (
            "Templates/Category starter.md",
            new_object_template(tags=("categories",)) + "\n" + CATEGORY_VIEWS,
        ),
        (
            "Templates/Member template starter.md",
            new_object_template()
            + "\n<!-- Duplicate this as a full template, then set categories and appearance_category to your existing category. Keep the date/title variables for insertion into a new note. See Vault guide. -->\n",
        ),
        ("Templates/Bases/Starter.base", MEMBERS),
        ("Vault guide.md", vault_guide(plan)),
    ) + category_template_files(plan)
