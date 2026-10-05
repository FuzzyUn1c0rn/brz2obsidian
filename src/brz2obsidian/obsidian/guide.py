"""Human and agent instructions for maintaining the editable vault."""

from brz2obsidian.core.support import category_template_path

GUIDE = """# Vault guide

## Find and create an object

Before creating a note, look up existing names and aliases using Search or the
Quick switcher. Reuse an existing entity when appropriate; matching titles alone
do not prove identity. Imported source_collection_id and source_item_id form a
stable pair and must survive native renames. New objects omit both source IDs.

Create a suitably named note, switch to Editing view, run **Templates: Insert template**,
and choose the full template for its category, or [[Templates/New note.md]]
for an unclassified object. The configured Templates folder is Templates; nested
.base files are views, not Markdown templates. Native Templates resolves title
and date variables on insertion. Both dates begin on the insertion day, not the
conversion day. Maintain updated explicitly after later meaningful edits.

Keep template date variables quoted as literal strings, for example
created: "{{date:YYYY-MM-DD}}". Native Templates still inserts the date; quoting
also protects the variable when Obsidian rewrites YAML during link updates.

A full category template initializes linked categories and appearance_category;
optional icon/colour overrides stay blank. Templates initialize structure rather
than enforcing a continuing schema. Selecting a category in a property does not
select or apply a template, and Base queries discover membership independently.

## Maintain existing notes

On existing notes, edit categories directly using the Properties editor or
frontmatter. Adding or reordering memberships preserves established dates,
content, provider and imported identity. Full native templates can replace shared
scalar properties, including dates and the provider; use them for new notes.
There are no additive category-only templates or promises of overwrite protection.

In the reviewed Obsidian build, saving a Properties edit normalized existing
CRLF line endings to LF without changing authored text. Keep the pristine
converter output and original note backups when exact pre-edit bytes matter.
Manual editor saves are separate from the converter's byte-preservation checks.

Choose appearance_category explicitly from memberships, independently of
membership order. Empty means no inheritance. A populated invalid/nonmember
provider shows Invalid provider; it never selects a substitute. A valid local
icon override wins even with an empty or invalid provider. Otherwise dashboards
use the valid provider's current local image. Category changes do not rewrite
body-icon snapshots; those image references are separately editable. Declared
colours remain metadata, without the decorative Appearance display.

Imported created/updated are source creation/overall-modification calendar dates,
without timezone conversion. Full timestamps remain in migration-record.json.
An ordinary manual membership edit does not automatically change updated.

## Canonical properties and relationships

| Property | Meaning |
| --- | --- |
| categories | List of links to category notes; empty is valid. |
| appearance_category | Optional single category link also in categories. |
| icon | Optional single link to a local image; category default or member override. |
| foreground_color, background_color | Optional declared colour metadata. |
| created, updated | Optional ISO calendar dates; new templates initialize insertion day. |
| tags, aliases | Native lists; source tags are distinct from categories. |
| source_collection_id, source_item_id | Paired opaque imported identity; absent for new objects. |

Reference another meaningful entity through an Obsidian link instead of duplicating
its information. Before adding a property, reuse the existing canonical vocabulary
or document a deliberate extension with its meaning and cardinality. Custom future
vocabulary is allowed; do not infer domain fields from prose or casually introduce
synonyms. Semantic relationships belong in properties/links, not folder nesting.
Keep notes human-readable and preserve their authored content.

## Browse and extend categories

Open [[Categories.md]] from Home, then open the category dashboard for its Members
table and Gallery. A standalone contextual Base has no selected embedding
category. Discovery follows linked membership, with Templates and Attachments
excluded; filenames containing Template remain valid members. Category role uses
the Categories folder and native categories tag. Members can live in Notes or
other ordinary areas; folders are not their type system.

For a future category such as Experiments:

1. Create Categories/Experiments.md, switch to Editing view, and insert
   [[Templates/Category starter.md]]. It initializes the categories role tag,
   insertion dates and contextual Members/Gallery embeds. Add an optional local
   icon by linking an image under Attachments.
2. A handwritten new note can already join it without inserting a member template.
   Use the following properties; leave the provider empty to opt out instead:

```yaml
categories:
  - "[[Categories/Experiments]]"
appearance_category: "[[Categories/Experiments]]"
```

3. Duplicate [[Templates/Member template starter.md]] as Templates/Experiments.md.
   Edit its categories/provider to the existing category links shown above. Keep
   the insertion variables literal in the template. Select that full template
   manually when creating another new object. The unadapted starter leaves
   categories/provider empty, so it has no dangling example references.
4. Reuse Members/Gallery, or copy [[Templates/Bases/Starter.base]] under
   Templates/Bases with a distinct name and customize its view. Embed it in the
   category dashboard, retaining list(categories).contains(this) for contextual
   membership. The Base starter already uses Icon before Note and excludes the
   operational support areas. No template/base/vault_role registry is needed.

Use Obsidian's native rename with automatic link updates enabled. Qualified
category/member-template links may become shorter unambiguous links. Contextual
member queries follow the renamed dashboard; source IDs remain unchanged. Prefer
qualified links when similarly named targets are ambiguous.

## Reference adaptations and migration limits

This follows kepano's real vault: manual full-template selection, linked category
properties, independent native Bases and embeds in category-note bodies. It adapts
that pattern using faithful imported names, complete typed membership, explicit
icon providers, qualified collision-safe links, operational folder exclusions and
contextual queries that survive native category renames. It adds the canonical
core, quoted date variables that survive native link updates and explicit
update-date maintenance; it does not clone reference domain
properties, unrelated plugin toggles, styling or community plugins.

The original Home/bookmark, source content/resources, source tags and graph links
remain available. [[MIGRATION REPORT.md]] explains preserved material, source
warnings and resource limits, including PDF Search and remote/offline video
availability. migration-record.json is migration evidence, not current editable
state. Conversion is a one-time fresh-vault operation, not synchronization.
"""


def vault_guide(plan):
    definitions = {
        i.key for i in plan.analysis.snapshot.items if i.role == "definition"
    }
    templates = [
        "- [[" + category_template_path(t) + "]] → [[" + t.relative_path + "]]"
        for t in plan.item_targets
        if t.item_key in definitions
    ]
    return (
        GUIDE
        + "\n## Imported category templates\n\n"
        + (
            "\n".join(templates) + "\n"
            if templates
            else "This source has no imported categories; use the generic template and future-category recipe.\n"
        )
    )
