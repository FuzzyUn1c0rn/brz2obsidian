"""Literal accepted native support contracts, independent of renderer imports."""

import json
from pathlib import PurePosixPath

CATEGORY_VIEWS = "## Members\n\n![[Templates/Bases/Members.base#Members]]\n\n## Gallery\n\n![[Templates/Bases/Gallery.base#Gallery]]\n"
REOPEN_GUIDANCE = "Close and reopen the affected category dashboards and [[Categories.md|Categories overview]] after changing category icons, memberships or appearance providers. Open views may keep stale or inconsistent icons and statuses until reopened.\n\n"
CATEGORY_VIEWS_8 = REOPEN_GUIDANCE + CATEGORY_VIEWS
IMAGE_TYPES = '["avif", "bmp", "gif", "jpeg", "jpg", "png", "svg", "webp"]'


def image_formula(value):
    return f'if({value}.isType("link") && {value}.asFile() && {IMAGE_TYPES}.contains({value}.asFile().ext.lower()) && {value}.asFile().size > 0, {value}, null)'


def tag_listing(roles, titles, names, created, tokens, assignments, *, output_version):
    """Readable direct source-tag edges; no transitive/ancestor projection."""
    focused = [
        tag
        for tag in sorted(tokens)
        if not any(a == tag for a, _ in assignments)
        or any(
            a == tag and (b not in created or output_version == 8 and roles[b] == 4)
            for a, b in assignments
        )
    ]
    if not focused:
        return ""
    text = "# Tag memberships\n\n" + (
        "Explicit nested source-tag facts, assignments on uncreated targets and source tags without assignments. Tokens are independent: a parent tag is not inferred on a child tag's members. Use native tag search for created assigned notes.\n\n"
        if output_version == 8
        else "Assignments on uncreated targets and source tags without assignments. Use native tag search for created assigned notes.\n\n"
    )

    def linked(key):
        # Labels use the same independently reviewed Markdown escaping rule.
        from .checker import wiki

        return wiki(names[key], titles[key])

    for tag in focused:
        text += "## #" + tokens[tag] + "\n\nSource tag: " + linked(tag) + "\n\n"
        visible = sorted(
            {
                b
                for a, b in assignments
                if a == tag
                and (b not in created or output_version == 8 and roles[b] == 4)
            }
        )
        text += (
            "".join(
                "- Nested source tag: "
                + linked(child)
                + " (#"
                + tokens[child]
                + ("); uncreated target.\n" if child not in created else ").\n")
                if output_version == 8 and roles[child] == 4
                else "- " + linked(child) + "\n"
                for child in visible
            )
            + "\n"
            if visible
            else "No source assignments.\n\n"
        )
    return text.rstrip("\n") + "\n"


def check_base8(text, role):
    """Closed authoring protocol for the separately qualified native engine.

    Independently state each level's guards: own icon at zero, valid direct
    category, repeated-target stop, then icon at levels1..8. Level9 validates
    continuation only. This does not claim native runtime/reactivity evidence.
    """
    expected = {
        "p0": "file",
        "r0": image_formula("icon"),
        "s0": 'if(formula.r0, "found", "continue")',
    }
    for level in range(1, 10):
        prior = f"formula.p{level - 1}"
        selected = prior + ".properties.appearance_category"
        category = selected + ".asFile()"
        predicates = (
            selected + '.isType("link")',
            category,
            category + '.ext == "md"',
            category + '.inFolder("Categories")',
            "!" + category + '.folder.split("/").contains("Templates")',
            "!" + category + '.folder.split("/").contains("Attachments")',
            "list(" + category + '.properties.tags).contains("categories")',
            "list(" + prior + ".properties.categories).contains(" + selected + ")",
        )
        expected[f"blank{level}"] = f"if({prior}, {selected}.isEmpty(), true)"
        expected[f"valid{level}"] = (
            f"if({prior}, " + " && ".join(predicates) + ", false)"
        )
        seen = ", ".join(
            f"if(formula.p{index}, formula.p{index}.path, null)"
            for index in range(level)
        )
        expected[f"cycle{level}"] = (
            f"if(formula.valid{level}, [{seen}].contains({category}.path), false)"
        )
        guards = f'if(formula.blank{level}, "none", if(!formula.valid{level}, "invalid", if(formula.cycle{level}, "cycle", '
        if level == 9:
            expected["result"] = (
                'if(formula.s8 != "continue", formula.s8, ' + guards + '"limit"))))'
            )
        else:
            expected[f"p{level}"] = (
                f'if(formula.s{level - 1} == "continue" && formula.valid{level} && !formula.cycle{level}, {category}, null)'
            )
            image = f"formula.p{level}.properties.icon"
            predicate = image_formula(image).removeprefix("if(").rsplit(", ", 2)[0]
            expected[f"r{level}"] = (
                f"if(formula.p{level} && {predicate}, {image}, null)"
            )
            expected[f"s{level}"] = (
                f'if(formula.s{level - 1} != "continue", formula.s{level - 1}, '
                + guards
                + f'if(formula.r{level}, "found", "continue")))))'
            )
    expected["effective_icon"] = (
        "[" + ", ".join(f"formula.r{i}" for i in range(9)) + "].filter(value)[0]"
    )
    expected["picture"] = (
        "if(formula.effective_icon, image(formula.effective_icon.asFile()), null)"
    )
    expected["provider_status"] = (
        'if(formula.result == "limit", "Icon lookup exceeds 8 links.", if(formula.result == "cycle", "Icon provider cycle.", if(formula.result == "invalid", "Invalid appearance category.", if(formula.result == "none", "No inherited icon.", "Icon found."))))'
    )
    middle = "formulas:\n" + "".join(
        "  " + key + ": " + json.dumps(value) + "\n" for key, value in expected.items()
    )
    filters = 'filters:\n  and:\n    - file.ext == "md"\n'
    if role == "categories":
        filters += '    - file.inFolder("Categories")\n    - \'!file.folder.split("/").contains("Templates")\'\n    - \'!file.folder.split("/").contains("Attachments")\'\n    - list(tags).contains("categories")\n'
    else:
        filters += "    - '!file.inFolder(\"Templates\")'\n    - '!file.inFolder(\"Attachments\")'\n    - list(categories).contains(this)\n"
    label = "Category" if role == "categories" else "Note"
    properties = f"properties:\n  formula.picture:\n    displayName: Icon\n  file.name:\n    displayName: {label}\n  formula.provider_status:\n    displayName: Inheritance\n"
    if role == "gallery":
        views = "views:\n  - type: cards\n    name: Gallery\n    image: formula.effective_icon\n    imageFit: contain\n    imageAspectRatio: 0.4\n    cardSize: 230\n    order:\n      - file.name\n      - formula.provider_status\n"
    else:
        views = (
            "views:\n  - type: table\n    name: "
            + ("Categories" if role == "categories" else "Members")
            + "\n    columnSize:\n      formula.provider_status: 240\n    order:\n      - formula.picture\n      - file.name\n      - formula.provider_status\n"
        )
        if role != "categories":
            views += (
                "      - note.categories\n      - note.created\n      - note.updated\n"
            )
    views += "    sort:\n      - property: file.name\n        direction: ASC\n"
    assert text == filters + middle + properties + views, (
        "current native eight-link guards/formulas/status/view protocol"
    )


def check_base(path, role, *, output_version=7):
    text = path.read_bytes().decode()
    if output_version == 8:
        return check_base8(text, role)
    # This is a closed literal authoring contract, not a native-engine simulator.
    formulas = {}
    for line in text.splitlines():
        if line.startswith("  ") and not line.startswith("    ") and ": '" in line:
            key, value = line.strip().split(": ", 1)
            assert value.startswith("'") and value.endswith("'"), "Base formula quoting"
            assert key not in formulas, "duplicate Base formula"
            formulas[key] = value[1:-1]
    if role == "categories":
        expected_formulas = {
            "local_icon": image_formula("icon"),
            "picture": "if(formula.local_icon, image(formula.local_icon.asFile()), null)",
        }
        filters = 'filters:\n  and:\n    - file.ext == "md"\n    - file.inFolder("Categories")\n    - list(tags).contains("categories")\n'
        properties = "properties:\n  formula.picture:\n    displayName: Icon\n  file.name:\n    displayName: Category\n"
        views = "views:\n  - type: table\n    name: Categories\n    order:\n      - formula.picture\n      - file.name\n    sort:\n      - property: file.name\n        direction: ASC\n"
    else:
        expected_formulas = {
            "provider": 'if(appearance_category.isEmpty(), null, if(appearance_category.isType("link") && list(categories).contains(appearance_category) && appearance_category.asFile() && appearance_category.asFile().ext == "md" && appearance_category.asFile().inFolder("Categories") && list(appearance_category.asFile().properties.tags).contains("categories"), appearance_category.asFile(), null))',
            "explicit_icon": image_formula("icon"),
            "provider_icon": "if(formula.provider, formula.provider.properties.icon, null)",
            "inherited_icon": image_formula("formula.provider_icon"),
            "effective_icon": "if(formula.explicit_icon, formula.explicit_icon, formula.inherited_icon)",
            "picture": "if(formula.effective_icon, image(formula.effective_icon.asFile()), null)",
            "provider_status": 'if(appearance_category.isEmpty(), "No inheritance", if(formula.provider, "Category defaults", "Invalid provider"))',
        }
        filters = 'filters:\n  and:\n    - file.ext == "md"\n    - \'!file.inFolder("Templates")\'\n    - \'!file.inFolder("Attachments")\'\n    - list(categories).contains(this)\n'
        properties = "properties:\n  formula.picture:\n    displayName: Icon\n  file.name:\n    displayName: Note\n  formula.provider_status:\n    displayName: Inheritance\n"
        views = (
            "views:\n  - type: cards\n    name: Gallery\n    image: formula.effective_icon\n    imageFit: contain\n    imageAspectRatio: 0.4\n    cardSize: 230\n    order:\n      - file.name\n      - formula.provider_status\n"
            if role == "gallery"
            else "views:\n  - type: table\n    name: Members\n    order:\n      - formula.picture\n      - file.name\n      - formula.provider_status\n      - note.categories\n      - note.created\n      - note.updated\n"
        ) + "    sort:\n      - property: file.name\n        direction: ASC\n"
    assert formulas == expected_formulas, "native Base icon/provider formulas"
    expected = (
        filters
        + "formulas:\n"
        + "".join(f"  {key}: '{value}'\n" for key, value in expected_formulas.items())
        + properties
        + views
    )
    assert text == expected, "native Base filters/properties/view/order"


def template(category=None, role_tag=False):
    linked = "[[" + category + "]]" if category else None
    properties = {
        "categories": [linked] if linked else [],
        "appearance_category": linked,
        "icon": None,
        "created": "{{date:YYYY-MM-DD}}",
        "updated": "{{date:YYYY-MM-DD}}",
        "tags": ["categories"] if role_tag else [],
        "aliases": [],
    }
    text = "---\n"
    for name, value in properties.items():
        if isinstance(value, list) and value:
            text += (
                name
                + ":\n"
                + "".join(
                    "  - " + json.dumps(v, ensure_ascii=False) + "\n" for v in value
                )
            )
        else:
            text += (
                name
                + ":"
                + (
                    " " + json.dumps(value, ensure_ascii=False)
                    if value is not None
                    else ""
                )
                + "\n"
            )
    return text + "---\n\n# {{title}}\n"


def check_support_content(vault, names, definitions, *, output_version=7):
    for name, role in (
        ("Members", "members"),
        ("Gallery", "gallery"),
        ("Categories", "categories"),
        ("Starter", "members"),
    ):
        check_base(
            vault / ("Templates/Bases/" + name + ".base"),
            role,
            output_version=output_version,
        )
    expected = {
        "Templates/New note.md": template(),
        "Templates/Category starter.md": template(role_tag=True)
        + "\n"
        + (CATEGORY_VIEWS_8 if output_version == 8 else CATEGORY_VIEWS),
        "Templates/Member template starter.md": template()
        + "\n<!-- Duplicate this as a full template, then set categories and appearance_category to your existing category. Keep the date/title variables for insertion into a new note. See Vault guide. -->\n",
    }
    expected.update(
        {
            "Templates/" + PurePosixPath(names[k]).name: template(names[k])
            for k in definitions
        }
    )
    for name, text in expected.items():
        assert (vault / name).read_bytes() == text.encode(), (
            "canonical template membership/provider/date/identity contract"
        )
    guide = (vault / "Vault guide.md").read_bytes().decode()
    assert all(
        name not in guide for name in ("foreground_color", "background_color")
    ), "removed colour properties in maintenance guide"
    obligations = (
        "## Find and create an object",
        "look up existing names and aliases",
        "matching titles alone",
        "New objects omit both source IDs",
        "Templates: Insert template",
        "Maintain updated explicitly",
        'created: "{{date:YYYY-MM-DD}}"',
        "## Maintain existing notes",
        "edit categories directly",
        "Full native templates can replace shared",
        "CRLF line endings to LF",
        "Empty means no inheritance",
        "Invalid appearance category." if output_version == 8 else "Invalid provider",
        "body-icon snapshots",
        "source colours remain in migration-record.json without vault colour properties",
        "without timezone conversion",
        "## Canonical properties and relationships",
        "Custom future",
        "## Browse and extend categories",
        "table and Gallery after the title and any Parents/Children navigation",
        "hierarchy does not create membership",
        "Category notes have no generated\nintroductory icon image",
        "Retained source labels, authored text/images, resources and Related links follow\nthe Bases",
        "Ordinary/member notes keep their separately editable body snapshots",
        "standalone contextual Base",
        "filenames containing Template",
        "handwritten new note",
        "Duplicate [[Templates/Member template starter.md]]",
        "list(categories).contains(this)",
        "native rename",
        "## Check current vault conventions",
        "never repairs files",
        "independent migration source-preservation audit",
        "## Reference adaptations and migration limits",
        "PDF Search",
        "remote/offline video",
        "one-time fresh-vault operation",
    )
    assert all(o in guide for o in obligations), (
        "required maintenance guide obligations"
    )
    for key in definitions:
        mapping = (
            "- [[Templates/"
            + PurePosixPath(names[key]).name
            + "]] → [["
            + names[key]
            + "]]"
        )
        assert mapping in guide, "guide category template mapping"
