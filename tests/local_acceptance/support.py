"""Literal accepted native support contracts, independent of renderer imports."""

import json
from pathlib import PurePosixPath

CATEGORY_VIEWS = "## Members\n\n![[Templates/Bases/Members.base#Members]]\n\n## Gallery\n\n![[Templates/Bases/Gallery.base#Gallery]]\n"
IMAGE_TYPES = '["avif", "bmp", "gif", "jpeg", "jpg", "png", "svg", "webp"]'


def image_formula(value):
    return f'if({value}.isType("link") && {value}.asFile() && {IMAGE_TYPES}.contains({value}.asFile().ext.lower()) && {value}.asFile().size > 0, {value}, null)'


def check_base(path, role):
    text = path.read_bytes().decode()
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
        "foreground_color": None,
        "background_color": None,
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


def check_support_content(vault, names, definitions):
    for name, role in (
        ("Members", "members"),
        ("Gallery", "gallery"),
        ("Categories", "categories"),
        ("Starter", "members"),
    ):
        check_base(vault / ("Templates/Bases/" + name + ".base"), role)
    expected = {
        "Templates/New note.md": template(),
        "Templates/Category starter.md": template(role_tag=True)
        + "\n"
        + CATEGORY_VIEWS,
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
        "Invalid provider",
        "body-icon snapshots",
        "without timezone conversion",
        "## Canonical properties and relationships",
        "Custom future",
        "## Browse and extend categories",
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
