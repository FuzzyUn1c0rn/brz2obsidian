"""Human and agent instructions for maintaining the editable vault."""

from brz2obsidian.core.support import category_template_path

GUIDE = """# Vault guide

## Imported Markdown inserts

Generated tables of contents are static links to the authored headings. Their
block IDs distinguish repeated headings and Unicode or punctuation labels.
After heading edits, update the list and retain its destination block IDs, or
edit the links manually; there is no automatic ToC maintenance.

Reviewed source tables become ordinary editable Markdown tables. Native layout
is responsive; source column widths and justification remain in the migration
record and are not reproduced. Table link aliases use native pipe escaping;
code spans containing pipes use narrowly generated, escaped code elements so
the displayed code and cells remain intact. Review disclosed malformed tables before
editing their cell structure.

All 13 standard source callout types use their corresponding native Obsidian
colours and icons. Consecutive callouts become separate panels; titles, folding
and nested bodies remain editable. Authored emoji icons appear in the title,
alongside Obsidian's native icon. This is a visible fallback, not an icon
replacement. Unsupported icon declarations remain visible with warnings.
No community plugin, generated CSS or custom standard icon assets are required.
Compatible mathematics is retained. The Migration report links affected notes;
the migration record retains exact declarations and adaptation edits, and safe
original note bytes remain under Attachments.

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
the optional icon override stays blank. Templates initialize structure rather
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

Close and reopen the affected category dashboards and [[Categories.md|Categories overview]] after changing category icons, memberships or appearance providers. Open views may keep stale or inconsistent icons and statuses until reopened.

Choose appearance_category explicitly from memberships, independently of
membership order. Empty means no inheritance. A populated invalid/nonmember
provider shows "Invalid appearance category."; it never selects a substitute. A valid local
icon override wins even with an empty or invalid provider. After reopening, dashboards
follow the selected provider chain, taking the nearest valid owned image.
Members, Gallery and Categories overview check the note's own icon at link zero
and at most eight provider links. If no icon is found and a valid unrepeated
chain continues, they show no inherited image and the exact status
**Icon lookup exceeds 8 links.** Assign a nearer valid icon or change a selected
provider to resolve this warning. Blank stops normally; invalid/repeated
providers have distinct statuses. A valid icon found within the limit succeeds
even if the remaining chain is longer. Lookup never selects another membership
or writes a borrowed icon into an owned icon property. Category changes do not rewrite
ordinary/member body-icon snapshots; those full-chain migration-time image
references are separately editable and can show an image while the live view
reports the eight-link limit. Declared
source colours remain in migration-record.json without vault colour properties
or the decorative Appearance display.

When a source category icon is absent, its icon property is empty and inheriting
members keep their categories and appearance_category links. Lookup uses a
farther valid selected icon if available, otherwise appearance is neutral. A valid explicit member icon still wins. Add a valid local image to
the category's icon property to supply future dashboard defaults. The Migration
report identifies the missing provider and affected included members separately.
Missing source category text remains unknown; its notice does not reconstruct a
body from images or declared length. Source repair and re-export are optional.

Imported created/updated are source creation/overall-modification calendar dates,
without timezone conversion. Full timestamps remain in migration-record.json.
An ordinary manual membership edit does not automatically change updated.

## Canonical properties and relationships

| Property | Meaning |
| --- | --- |
| categories | List of links to category notes; empty is valid. |
| appearance_category | Optional single category link also in categories. |
| icon | Optional single link to a local image; category default or member override. |
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
table and Gallery after the title and any Parents/Children navigation.
Every direct included parent is linked; hierarchy does not create membership.
A category can itself be a direct member and has one unique category note.
Dashboards list direct members only; B's member template initializes B, never
B's own parent A.
Category notes have no generated
introductory icon image; their icon property still supplies dashboard images.
Retained source labels, authored text/images, resources and Related links follow
the Bases. Ordinary/member notes keep their separately editable body snapshots.
A standalone contextual Base has no selected embedding
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

Source-tag tokens remain independent. Tag memberships.md lists explicit
nested source-tag facts even when a child tag has a created note. A nested fact
may also point to an uncreated tag target. The parent tag is not inferred on the
child tag's members; discover created assignments through native tag search.

## Check current vault conventions

From the installed converter environment, run these read-only commands with
this vault's folder path:

```text
brz2obsidian check-vault "C:/vaults/this-vault"
brz2obsidian check-vault "C:/vaults/this-vault" --json
```

Python callers use brz2obsidian.vault_check.check_vault(vault). The checker reads
actual current notes, properties, Bases and required local-image references;
it needs no source archive or migration-record.json and never repairs files.
Custom properties, template date variables and intentional uncreated ordinary
targets are allowed. Required category/provider/media links must resolve
unambiguously; blank appearance providers opt out. provider_cycle reports the
full repeated provider chain, including cycles beyond the native search.
invalid_provider also identifies affected chains reaching invalid declarations,
even when a nearer owned icon displays. icon_lookup_depth reports the affected
chain with "Icon lookup exceeds 8 links."; it is a nonblocking warning. Results are clean/issues/failed
with command exits 0/2/1 and a separate version-1 brz2obsidian.vault-check JSON
envelope. Read failures retain other readable-note diagnostics and unavailable
measurements are null. This checks structural conventions, not Base formula
execution, native rendering or continuing date maintenance. A clean editable
vault does not replace the independent migration source-preservation audit.

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


def _import_guide(plan):
    location = plan.import_location
    home = next(
        t.relative_path
        for t in plan.item_targets
        if t.item_key == plan.analysis.entry_key
    )
    return (
        "# Imported collection guide\n\n"
        f"Open [[{home}|Home]] to browse this import under `{location}/`. "
        "[[Categories.md|Categories]] lists its imported categories. "
        "[[MIGRATION REPORT.md|Migration report]] explains preserved source material and warnings.\n\n"
        "The import uses the vault’s existing Obsidian settings. It includes "
        "native Bases and templates under the import folder. Use the Bases "
        "embedded in category notes to browse members. "
        "Open [[Templates/New note.md|the general template]] or a category template "
        "to see its properties.\n\n"
        "Keep source_collection_id and source_item_id together on imported notes "
        "when moving or renaming them. Maintain user-authored links when moving files. "
        "The scoped migration record describes the generated source version.\n"
    )


def vault_guide(plan):
    if plan.import_location is not None:
        return _import_guide(plan)
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
