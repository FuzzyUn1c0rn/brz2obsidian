"""Native linked membership, separate from graph navigation and source tags."""

import json

from .tags import tag_frontmatter


def category_frontmatter(plan, item_key):
    frontmatter = tag_frontmatter(plan, item_key)
    assignments = [
        a
        for a in plan.analysis.snapshot.classification_assignments
        if a.item_key == item_key
    ]
    if not assignments:
        return frontmatter
    targets = {t.item_key: t for t in plan.item_targets}
    links = ["[[" + targets[a.definition_key].relative_path + "]]" for a in assignments]
    properties = "categories:\n" + "".join(
        "  - " + json.dumps(link, ensure_ascii=False) + "\n" for link in links
    )
    properties += (
        "appearance_category: " + json.dumps(links[0], ensure_ascii=False) + "\n"
    )
    return (
        frontmatter[:-5] + properties + "---\n\n"
        if frontmatter
        else "---\n" + properties + "---\n\n"
    )


def classification_records(plan):
    targets = {t.item_key: t for t in plan.item_targets}
    return [
        dict(
            **a.model_dump(),
            definition_target=targets[a.definition_key].relative_path,
            item_target=targets[a.item_key].relative_path,
        )
        for a in plan.analysis.snapshot.classification_assignments
    ]
