"""Native contextual category queries and bounded editable icon lookup."""

import json

HOME_CATEGORIES = "## Categories\n\n[[Categories.md|Browse categories]]\n"
REOPEN_GUIDANCE = (
    "Close and reopen the affected category dashboards and [[Categories.md|Categories overview]] "
    "after changing category icons, memberships or appearance providers. "
    "Open views may keep stale or inconsistent icons and statuses until reopened.\n\n"
)
CATEGORY_VIEWS = (
    REOPEN_GUIDANCE + "## Members\n\n![[Templates/Bases/Members.base#Members]]\n\n"
    "## Gallery\n\n![[Templates/Bases/Gallery.base#Gallery]]\n"
)
MEMBER_FILTERS = """filters:
  and:
    - file.ext == "md"
    - '!file.inFolder("Templates")'
    - '!file.inFolder("Attachments")'
    - list(categories).contains(this)
"""


def _owned_icon(value):
    return (
        f'{value}.isType("link") && {value}.asFile() && '
        f'["avif", "bmp", "gif", "jpeg", "jpg", "png", "svg", "webp"].contains({value}.asFile().ext.lower()) && '
        f"{value}.asFile().size > 0"
    )


def _provider_valid(node):
    provider = node + ".properties.appearance_category"
    target = provider + ".asFile()"
    return (
        f'{provider}.isType("link") && {target} && {target}.ext == "md" && '
        f'{target}.inFolder("Categories") && '
        f'!{target}.folder.split("/").contains("Templates") && '
        f'!{target}.folder.split("/").contains("Attachments") && '
        f'list({target}.properties.tags).contains("categories") && '
        f"list({node}.properties.categories).contains({provider})"
    )


def _lookup_formulas():
    # Step9 validates continuation only; it never reads the next icon.
    formulas = {
        "p0": "file",
        "r0": f"if({_owned_icon('icon')}, icon, null)",
        "s0": 'if(formula.r0, "found", "continue")',
    }
    for step in range(1, 10):
        previous = f"formula.p{step - 1}"
        provider = previous + ".properties.appearance_category"
        formulas[f"blank{step}"] = f"if({previous}, {provider}.isEmpty(), true)"
        formulas[f"valid{step}"] = f"if({previous}, {_provider_valid(previous)}, false)"
        visited = ", ".join(
            f"if(formula.p{i}, formula.p{i}.path, null)" for i in range(step)
        )
        formulas[f"cycle{step}"] = (
            f"if(formula.valid{step}, [{visited}].contains({provider}.asFile().path), false)"
        )
        stop = f'if(formula.blank{step}, "none", if(!formula.valid{step}, "invalid", if(formula.cycle{step}, "cycle", '
        if step == 9:
            formulas["result"] = (
                f'if(formula.s8 != "continue", formula.s8, {stop}"limit"))))'
            )
            break
        formulas[f"p{step}"] = (
            f'if(formula.s{step - 1} == "continue" && formula.valid{step} && !formula.cycle{step}, {provider}.asFile(), null)'
        )
        icon = f"formula.p{step}.properties.icon"
        formulas[f"r{step}"] = (
            f"if(formula.p{step} && {_owned_icon(icon)}, {icon}, null)"
        )
        formulas[f"s{step}"] = (
            f'if(formula.s{step - 1} != "continue", formula.s{step - 1}, {stop}if(formula.r{step}, "found", "continue")))))'
        )
    formulas["effective_icon"] = (
        "[" + ", ".join(f"formula.r{i}" for i in range(9)) + "].filter(value)[0]"
    )
    formulas["picture"] = (
        "if(formula.effective_icon, image(formula.effective_icon.asFile()), null)"
    )
    formulas["provider_status"] = (
        'if(formula.result == "limit", "Icon lookup exceeds 8 links.", if(formula.result == "cycle", "Icon provider cycle.", if(formula.result == "invalid", "Invalid appearance category.", if(formula.result == "none", "No inherited icon.", "Icon found."))))'
    )
    return formulas


MEMBER_FORMULAS = (
    "formulas:\n"
    + "".join(
        "  " + name + ": " + json.dumps(expression) + "\n"
        for name, expression in _lookup_formulas().items()
    )
    + """properties:
  formula.picture:
    displayName: Icon
  file.name:
    displayName: Note
  formula.provider_status:
    displayName: Inheritance
"""
)

MEMBERS = (
    MEMBER_FILTERS
    + MEMBER_FORMULAS
    + """views:
  - type: table
    name: Members
    columnSize:
      formula.provider_status: 240
    order:
      - formula.picture
      - file.name
      - formula.provider_status
      - note.categories
      - note.created
      - note.updated
    sort:
      - property: file.name
        direction: ASC
"""
)
GALLERY = (
    MEMBER_FILTERS
    + MEMBER_FORMULAS
    + """views:
  - type: cards
    name: Gallery
    image: formula.effective_icon
    imageFit: contain
    imageAspectRatio: 0.4
    cardSize: 230
    order:
      - file.name
      - formula.provider_status
    sort:
      - property: file.name
        direction: ASC
"""
)
CATEGORIES = (
    """filters:
  and:
    - file.ext == "md"
    - file.inFolder("Categories")
    - '!file.folder.split("/").contains("Templates")'
    - '!file.folder.split("/").contains("Attachments")'
    - list(tags).contains("categories")
"""
    + MEMBER_FORMULAS.replace("displayName: Note", "displayName: Category")
    + """views:
  - type: table
    name: Categories
    columnSize:
      formula.provider_status: 240
    order:
      - formula.picture
      - file.name
      - formula.provider_status
    sort:
      - property: file.name
        direction: ASC
"""
)


def support_files():
    return (
        (
            "Categories.md",
            "# Categories\n\n"
            + REOPEN_GUIDANCE
            + "![[Templates/Bases/Categories.base]]\n",
        ),
        ("Templates/Bases/Members.base", MEMBERS),
        ("Templates/Bases/Gallery.base", GALLERY),
        ("Templates/Bases/Categories.base", CATEGORIES),
    )
