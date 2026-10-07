# Check an editable vault

The read-only checker examines current vault files without a source archive,
migration record or Obsidian session. Run it after membership edits, category
renames or template changes. It returns diagnostics and never creates, repairs,
renames or rewrites files.

```powershell
.\.venv\Scripts\brz2obsidian.exe check-vault 'C:\vaults\editable-vault'
.\.venv\Scripts\python.exe -m brz2obsidian check-vault 'C:\vaults\editable-vault' --json
```

```python
from brz2obsidian.vault_check import check_vault

result = check_vault("editable-vault")  # str or pathlib.Path
for issue in result.issues:
    print(issue.code, issue.artifact, issue.property, issue.reference)
print(result.model_dump_json(by_alias=True))
```

| Outcome | Exit | Meaning |
| --- | ---: | --- |
| `clean` | 0 | Checked structural conventions have no reported problems |
| `issues` | 2 | Convention or unsafe-reference problems were found |
| `failed` | 1 | Vault access, enumeration, decoding or a file read failed |

An unsafe supplied vault root also returns `failed`. Argument errors exit 1
and help exits 0. JSON mode prints one result envelope; text mode presents the
same outcome and diagnostics. A per-file failure does not stop other readable
files from being checked.
An unreadable or unparseable category has its own diagnostic; unavailable role
information does not fabricate invalid-membership/provider conclusions.

## Structural scope

All contained regular `.md` files are examined for boundary frontmatter and
active required embeds/images; all contained regular `.base` files are parsed
as YAML mappings. File extensions are compared without case sensitivity. YAML
is data only: executable tags, malformed mappings and duplicate keys, including
nested mappings and merge collisions, are diagnosed. Unknown custom properties
are allowed. Notes need not contain the entire imported canonical core.

When present, `categories` is a list of wikilinks; `appearance_category` and
`icon` are optional single wikilinks. `tags` and `aliases` are string lists.
`created` and `updated` are optional valid calendar dates (YAML date scalars or
ISO strings). Null and blank strings are valid optional scalar values. Under
the root `Templates` folder,
quoted literal `{{date}}` and `{{date:YYYY-MM-DD}}` strings are also valid dates.
Variables are never substituted. Use the quoted ISO form produced by the
converter so native link updates preserve it; malformed unquoted mappings are
still reported. A filename containing Template does not confer template scope.

Imported `source_collection_id` and `source_item_id` must both be present as
nonempty opaque strings or both be absent. Duplicate pairs are diagnosed using
current properties, independently of note titles, filenames and migration
records. New objects and templates need no invented imported identities.

A category target is a Markdown note under root `Categories` with the native
`categories` tag. Templates/Attachments folders do not confer category roles.
Every populated appearance provider must resolve to a qualifying category in
the note's memberships. A blank provider opts out; invalid providers remain
problems even when a valid explicit icon exists. The checker never reselects a
provider or changes separately editable body-icon snapshots.

Qualified wikilinks resolve by vault path; shortened references require exactly
one matching file across the inventory before category-role filtering. Matching
uses NFC and case-folded names without discarding colliding candidates. Category
links may omit `.md`, including dotted basenames such as `Topic.v2`. Aliases,
headings and Base view fragments are presentation details, and equivalent link
spellings compare by resolved file identity. Image/Base links identify their
file extension. Ambiguous candidates retain sorted relative paths.

Active `![[...base#View]]` embeds require regular `.base` targets. Native image
embeds, the `icon` property and local Markdown images require nonempty files
with extensions `avif`, `bmp`, `gif`, `jpeg`, `jpg`, `png`, `svg` or `webp`.
Markdown image paths are relative to the referring note, may be URL-encoded and
may use `../` while remaining within the vault. Fenced/indented code, inline code
and HTML comments do not establish required targets. Ordinary note links and
note embeds may intentionally name uncreated targets. HTTP/HTTPS and embedded
data images are outside local existence checks; raw HTML is not evaluated.

Traversal outside the vault, absolute/drive/UNC/device/file-URL references,
unsafe Windows path components and control characters are diagnosed. Reads
check lexical and physical containment and reject symbolic links and Windows
reparse points, including junctions, before enumeration or opening. Unsafe
child entries are reported without following them. Files can change between
checks; this operation does not take an atomic filesystem snapshot.

The scope is structural conventions. A clean result does not prove source
preservation, image decoding/native rendering, Base query/formula semantics,
all-purpose link completeness, exact Obsidian configuration or continued date
maintenance. Use the separate migration preservation audit for conservation
of source records, authored content and payload bytes.

## Versioned result

`VaultCheckResult`, `VaultCheckIssue` and `VaultCheckCounts` are closed, strict,
frozen Pydantic contracts, exported alongside `check_vault`. JSON round-trips
through `VaultCheckResult.model_validate_json(...)`. This independent schema
does not change the version-3 migration result or its inspect/convert outcomes.

| Field | Meaning |
| --- | --- |
| `schema` / `schema_version` | `brz2obsidian.vault-check` / `1` |
| `operation` | `check-vault` |
| `outcome` | `clean`, `issues` or `failed` |
| `vault` | Absolute supplied directory `location` and directory `name`; no fabricated source identity |
| `counts` | Measurements below, with unavailable totals represented as `null` |
| `checked_scope` | Fixed true flags: `data_only_yaml`, `known_properties`, `category_provider_references`, `base_image_targets`, `imported_identities`, `contained_reads` |
| `issues` | Ordered diagnostics, represented internally by immutable tuples |

`inventory_files`, `markdown_files` and `base_files` measure the complete safe
regular-file inventory. They are null when enumeration is incomplete or an
unsafe entry prevents a complete inventory. `read_markdown_files` and
`read_base_files` measure successfully decoded files, including files whose
YAML has convention problems; zero means no files were decoded.
`category_notes` counts qualifying category roles and `imported_notes` counts
notes with valid paired identities, including duplicates. These totals are null
when a note cannot be read/parsed or the inventory is incomplete. A Base-only
read failure leaves fully measured note totals available.

Each diagnostic has `code`, optional vault-relative `artifact`, optional
`property` and `reference`, a `message`, `guidance` and immutable `candidates`.
Diagnostics sort by artifact, code, property, reference and candidate paths.
Unchanged input produces equal results, without timestamps or random IDs.

| Code | Meaning |
| --- | --- |
| `invalid_frontmatter` | Malformed, non-mapping, duplicate-key or executable-tag frontmatter |
| `invalid_property` | Known property has an invalid type, cardinality, value or identity pair |
| `invalid_category` | Membership target is missing or lacks the category role |
| `invalid_provider` | Provider is missing, has the wrong role or is outside valid memberships |
| `missing_base` / `missing_image` | Required file is absent or has an unsuitable kind; images must be nonempty |
| `invalid_base` | Base YAML is malformed, non-mapping, duplicate-key or contains unsupported tags |
| `ambiguous_reference` | Required reference has multiple matching files; candidates are included |
| `duplicate_source_identity` | An imported identity pair appears on multiple notes; candidates identify the copies |
| `unsafe_reference` | Required reference or inventory entry cannot be read safely within the vault |
| `read_failure` | Directory/file access or text decoding failed |
