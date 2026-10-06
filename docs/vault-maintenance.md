# Maintain the converted vault

Every generated vault includes `Vault guide.md` and links to its actual category
templates. Use that local guide when names have been sanitized or disambiguated.
Notes remain ordinary Markdown; bundled Templates and Bases provide authoring
and discovery in standard Obsidian, with no required community plugin.

## Create an object

Search existing names and aliases before creating a note. Matching titles alone
do not establish identity. Imported `source_collection_id` and `source_item_id`
form a stable pair; preserve both through renames. New objects omit both.

Create a suitably named note, switch to Editing view, run **Templates: Insert
template**, and select `New note` or the full template named for the category's
assigned stem. For example, the source type Book yields `Categories/Book.md`
and `Templates/Book.md` when no naming collision requires a suffix. The template
initializes linked membership/provider and leaves the optional icon blank.
Both dates begin on the insertion day. Maintain `updated` explicitly thereafter.

Keep template variables quoted, for example `created: "{{date:YYYY-MM-DD}}"`.
Native Templates substitutes them on insertion; quoting preserves the literal
variable when native link updates rewrite YAML. Templates initialize structure.
Choosing a category does not apply a template, and Bases discover members
independently of how their properties were created.

## Edit an existing object

Edit `categories` directly in Properties or frontmatter. Full templates may
overwrite shared scalar values, including dates and providers, so use them for
new notes. Preserve existing content, source IDs, dates and appearance provider
when merely adding membership. Update the provider explicitly if removing its
category. Reordering memberships never chooses a different provider.

| Property | Meaning and cardinality |
| --- | --- |
| `categories` | List of links to category notes; empty is valid. |
| `appearance_category` | Optional single category link also in `categories`. |
| `icon` | Optional single local-image link: category default or member override. |
| `created`, `updated` | Optional ISO calendar dates. Imported values use source creation/overall modification, without timezone conversion. |
| `tags`, `aliases` | Native string lists; source tags remain distinct from categories. |
| `source_collection_id`, `source_item_id` | Paired opaque imported identities; absent on new objects. |

Use links for meaningful entities, such as `organization: "[[Acme]]"`, when that
property has a deliberately documented meaning. Reuse established vocabulary
before adding synonyms. The converter does not infer domain fields from prose.
Folders serve operational organization; members are classified by properties.

A valid local `icon` wins. Otherwise dashboards use the current icon of a valid
appearance category. A blank provider opts out; a dangling/nonmember provider
shows Invalid provider and is reported by the checker, without reselection.
A valid override remains visible in either case. The icon field links to a real
preserved image; it is not an emoji field. Source colours stay in migration
evidence; notes/templates/Bases expose no foreground/background colour fields
and member views have no decorative Appearance column.

Ordinary/member body-icon references are migration-time snapshots. Changing category/provider
properties does not rewrite them; edit those references separately. Replacing a
shared image's bytes can naturally affect all references to that file. Original
timestamps and colour values remain in `migration-record.json` independently.
Obsidian Properties saves can normalize CRLF to LF in the reviewed build; keep
pristine converter output and `.md.original` backups for exact pre-edit evidence.

## Browse and rename categories

Home links to `Categories.md`. A category dashboard places contextual Members
and Gallery views from `Templates/Bases/` after its title and any Parents/Children
navigation, with no
generated introductory icon image. Its icon property remains available to
overview/member tables and cards. Retained source labels, authored text/images,
resources and Related links follow the Bases. Every direct included hierarchy
parent appears above Members/Gallery; hierarchy does not create membership.
Tables begin Icon, Note, Inheritance,
categories, created, updated; cards use the effective image. Open these views
through the dashboard, since a standalone contextual Base has no embedding
category. Prose links, hierarchy, source tags and provider links do not create
membership. Templates/Attachments are excluded by folder; a member whose name
contains Template remains eligible.

Use Obsidian's native rename with automatic internal-link updates enabled.
Contextual membership uses `list(categories).contains(this)`, so the renamed
dashboard remains the query context. Imported identity stays stable. Native
updates may shorten qualified links; shortened links are valid when unique.
Prefer qualified paths when names collide. Migration records describe the
original conversion and do not track later edits or renames.

## Add a future category

1. Create `Categories/Experiments.md` and insert `Category starter` in Editing
   view. Keep its native `categories` tag, dates and contextual dashboard embeds.
   Add an optional local-image `icon`, for example under Attachments.
2. Classify a handwritten new object with linked metadata:

   ```yaml
   categories:
     - "[[Categories/Experiments]]"
   appearance_category: "[[Categories/Experiments]]"
   ```

   Leave the provider empty if the object should have no inherited icon.
3. Duplicate `Templates/Member template starter.md` as `Templates/Experiments.md`.
   Set membership/provider to those same existing category links. Preserve quoted
   insertion variables and omit source IDs. Select this full template manually
   for subsequent new objects; the unadapted starter intentionally has no example
   category link.
4. Reuse Members/Gallery, or copy `Templates/Bases/Starter.base` with a distinct
   name and embed it in the dashboard. Preserve contextual membership and support
   exclusions when customizing its views. Nested `.base` files are views, not
   Markdown templates. There is no template/base/vault_role registry to maintain.

Run [the read-only checker](vault-checker.md) after membership, template or rename
changes. It reads current files without the archive and preserves bytes/inventory.
Custom properties and intentional ordinary uncreated links are allowed. It finds
structural problems without repair; a clean result does not verify Base execution,
native rendering, continuing dates or source preservation.

## Reference and deliberate adaptations

The implementation follows the actual
[kepano example vault at the inspected commit](https://github.com/kepano/kepano-obsidian/tree/473697347a0eaac790a6596229c741b3915f3b77).
Its Book template initializes linked Books membership; the Out of Control note
uses that membership; the Books category embeds Books.base, which independently
queries members and provides multiple views. Kevin Kelly embeds the Author view
with contextual `this`. See the [full reference trace](../.scratch/brz-to-obsidian-v2/research/kepano-template-base-mechanism.md).

The migration adapts that pattern with faithful source type names, complete typed
member notes, explicit icon providers, qualified collision-safe links, folder
exclusions and rename-safe contextual member queries. It adds a canonical core,
quoted insertion variables and explicit date maintenance. It does not copy the
reference's filename-substring exclusion, bibliographic schemas, styling, Maps or
unrelated plugin settings. Additional semantic fields remain deliberate human
extensions rather than inferred data.

PDFs remain byte-preserved and open natively; vault Search does not search their
body text. Reviewed videos preserve exact URLs beside derived embeds and retain
service/network/offline limits. Read `MIGRATION REPORT.md` for per-record source
gaps and [source coverage](source-coverage.md) for strict refusal boundaries.
## Native review observations

Insert a full template into the active note in Editing view. The actual-output
review confirmed insertion-day dates and title expansion for generic, category
and adapted future-member templates without imported identity fields. Native
rename with link updates preserves contextual category discovery and quoted
template variables; the existing Markdown heading is still ordinary text and
can be edited separately. Native Properties may rewrite frontmatter quoting,
so preserve identity/date values and independently compare body content when
checking an intentional edit. See the
[native review evidence](../.scratch/management-leadership-implementation/research/native-v3-acceptance.md).
