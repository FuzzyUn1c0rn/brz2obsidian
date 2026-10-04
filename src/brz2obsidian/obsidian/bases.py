"""Native contextual category queries and their dashboard entry points."""

HOME_CATEGORIES = "## Categories\n\n[[Categories.md|Browse categories]]\n"
CATEGORY_VIEWS = (
    "## Members\n\n![[Templates/Bases/Members.base#Members]]\n\n"
    "## Gallery\n\n![[Templates/Bases/Gallery.base#Gallery]]\n"
)

MEMBER_FILTERS = """filters:
  and:
    - file.ext == "md"
    - '!file.inFolder("Templates")'
    - '!file.inFolder("Attachments")'
    - list(categories).contains(this)
"""

MEMBER_FORMULAS = """formulas:
  provider: 'if(appearance_category.isEmpty(), null, if(appearance_category.isType("link") && list(categories).contains(appearance_category) && appearance_category.asFile() && appearance_category.asFile().ext == "md" && appearance_category.asFile().inFolder("Categories") && list(appearance_category.asFile().properties.tags).contains("categories"), appearance_category.asFile(), null))'
  explicit_icon: 'if(icon.isType("link") && icon.asFile() && ["avif", "bmp", "gif", "jpeg", "jpg", "png", "svg", "webp"].contains(icon.asFile().ext.lower()) && icon.asFile().size > 0, icon, null)'
  provider_icon: 'if(formula.provider, formula.provider.properties.icon, null)'
  inherited_icon: 'if(formula.provider_icon.isType("link") && formula.provider_icon.asFile() && ["avif", "bmp", "gif", "jpeg", "jpg", "png", "svg", "webp"].contains(formula.provider_icon.asFile().ext.lower()) && formula.provider_icon.asFile().size > 0, formula.provider_icon, null)'
  effective_icon: 'if(formula.explicit_icon, formula.explicit_icon, formula.inherited_icon)'
  picture: 'if(formula.effective_icon, image(formula.effective_icon.asFile()), null)'
  provider_status: 'if(appearance_category.isEmpty(), "No inheritance", if(formula.provider, "Category defaults", "Invalid provider"))'
properties:
  formula.picture:
    displayName: Icon
  file.name:
    displayName: Note
  formula.provider_status:
    displayName: Inheritance
"""

MEMBERS = (
    MEMBER_FILTERS
    + MEMBER_FORMULAS
    + """views:
  - type: table
    name: Members
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
CATEGORIES = """filters:
  and:
    - file.ext == "md"
    - file.inFolder("Categories")
    - list(tags).contains("categories")
formulas:
  local_icon: 'if(icon.isType("link") && icon.asFile() && ["avif", "bmp", "gif", "jpeg", "jpg", "png", "svg", "webp"].contains(icon.asFile().ext.lower()) && icon.asFile().size > 0, icon, null)'
  picture: 'if(formula.local_icon, image(formula.local_icon.asFile()), null)'
properties:
  formula.picture:
    displayName: Icon
  file.name:
    displayName: Category
views:
  - type: table
    name: Categories
    order:
      - formula.picture
      - file.name
    sort:
      - property: file.name
        direction: ASC
"""


def support_files():
    return (
        ("Categories.md", "# Categories\n\n![[Templates/Bases/Categories.base]]\n"),
        ("Templates/Bases/Members.base", MEMBERS),
        ("Templates/Bases/Gallery.base", GALLERY),
        ("Templates/Bases/Categories.base", CATEGORIES),
    )
