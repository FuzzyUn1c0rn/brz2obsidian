"""Native linked membership, separate from graph navigation and source tags."""

import json
import re

from brz2obsidian.core.import_categories import (
    approved_views,
    shared_destinations,
    view_paths,
)


def classification_records(plan):
    targets = {t.item_key: t for t in plan.item_targets}
    shared = shared_destinations(plan)
    return [
        dict(
            **a.model_dump(),
            definition_target=shared.get(
                targets[a.definition_key].original_identity,
                targets[a.definition_key].relative_path,
            ),
            item_target=targets[a.item_key].relative_path,
        )
        for a in plan.analysis.snapshot.classification_assignments
    ]


def category_choice_records(plan):
    choices = {row.source_identity: row for row in plan.category_choices}
    definitions = {
        row.key for row in plan.analysis.snapshot.items if row.role == "definition"
    }
    views = {
        item.original_identity: [
            plan.import_support_paths[path] for path in view_paths(item)
        ]
        for item in approved_views(
            plan.analysis.snapshot, plan.item_targets, plan.category_choices
        )
    }
    return [
        {
            "source_identity": item.original_identity,
            "source_reference": item.relative_path,
            "destination": choices[item.original_identity].model_dump()
            if item.original_identity in choices
            else None,
            "view_paths": views.get(item.original_identity, []),
        }
        for item in plan.item_targets
        if item.item_key in definitions
    ]


def _link(path, label):
    return (
        "[[" + path + "|" + " ".join(re.sub(r"[\[\]|\r\n]", " ", label).split()) + "]]"
    )


def _view_link(plan, target):
    note, _ = view_paths(target)
    path = plan.import_support_paths.get(note)
    return _link(path, "Linked members — compatible view") if path else None


def reference_navigation(plan, target, destination):
    links = [_link(destination, f"Existing {target.original_title} category")]
    view = _view_link(plan, target)
    if view:
        links.append(view)
    return "".join("- " + link + "\n" for link in links) + "\n"


def _nonmember_paths(plan):
    paths = set(plan.known_nonmember_paths)
    paths.update(
        row.relative_path
        for row in plan.support_artifacts
        if row.purpose in ("template", "starter")
    )
    paths.update(
        row.relative_path for row in plan.asset_targets if row.relative_path is not None
    )
    return sorted(path for path in paths if path.casefold().endswith(".md"))


def scoped_category_outputs(plan):
    snapshot = plan.analysis.snapshot
    shared = shared_destinations(plan)
    used = {row.definition_key for row in snapshot.classification_assignments}
    lines = [f"# {snapshot.collection_title} categories", ""]
    for item in sorted(
        plan.item_targets, key=lambda row: (row.original_title.casefold(), row.item_key)
    ):
        if item.item_key not in used:
            continue
        title = item.original_title
        destination = shared.get(item.original_identity)
        if destination is None:
            lines.append("- " + _link(item.relative_path, title + " (separate)"))
            continue
        lines.append("- " + _link(destination, title + " (shared)"))
        view = _view_link(plan, item)
        if view:
            lines.append("  - " + view)
        lines.append(
            "  - "
            + _link(item.relative_path, f"Original {title} content and attachments")
        )
    outputs = {"Categories.md": "\n".join(lines) + "\n"}
    nonmembers = _nonmember_paths(plan)
    for item in approved_views(snapshot, plan.item_targets, plan.category_choices):
        destination = shared[item.original_identity]
        note, base = view_paths(item)
        outputs[note] = (
            "# Linked members — compatible view\n\n"
            + _link(destination, f"Existing {item.original_title} category")
            + "\n\n![["
            + plan.import_support_paths[base]
            + "#Members]]\n"
        )
        expression = f"list(categories).contains(link({json.dumps(destination, ensure_ascii=False)}))"
        outputs[base] = (
            "filters:\n  and:\n"
            + "".join(
                "    - " + json.dumps(value, ensure_ascii=False) + "\n"
                for value in (
                    'file.ext == "md"',
                    *(
                        f"file.path != {json.dumps(path, ensure_ascii=False)}"
                        for path in nonmembers
                    ),
                    expression,
                )
            )
            + "views:\n  - type: table\n    name: Members\n    order:\n"
            + "      - file.name\n      - note.categories\n"
            + "    sort:\n      - property: file.name\n        direction: ASC\n"
        )
    return outputs
