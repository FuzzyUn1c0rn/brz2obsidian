# How kepano's templates and category Bases actually connect

Checked: 2026-10-04 for the active [template/maintenance decision](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/49). The inspected commit is [`473697347a0eaac790a6596229c741b3915f3b77`](https://github.com/kepano/kepano-obsidian/tree/473697347a0eaac790a6596229c741b3915f3b77), authored 2026-01-08. A fresh `git ls-remote` check found remote `HEAD` and `main` at that same commit; no intervening reference changes were found and no checkout mutation was needed. This report uses public reference files and current first-party Obsidian documentation, without private source content or GUI testing.

**Finding:** the reference connects these components through ordinary linked properties, filenames, body embeds and Base queries. It does **not** define category `template`, `base` or `vault_role` properties. A person selects a template; that template writes membership; a Base independently discovers notes with matching membership. The category note displays that Base. These are separate actions, rather than an automatic category-to-template binding.

## The actual Books chain

The following are faithful **shortened excerpts** from the pinned files; omitted bibliographic fields and additional views are not reproduced.

[Templates/Book Template.md](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/Templates/Book%20Template.md) initializes membership and a date variable:

```yaml
categories:
  - "[[Books]]"
created: {{date}}
```

The existing [References/Out of Control.md](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/References/Out%20of%20Control.md) contains the same membership plus populated fields:

```yaml
categories:
  - "[[Books]]"
author:
  - "[[Kevin Kelly]]"
```

Both blocks belong inside YAML frontmatter delimited by `---`. The repository does not record whether this object was originally created by executing the template; it supplies an actual object that matches the mechanism.

The category/dashboard [Categories/Books.md](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/Categories/Books.md) is:

```markdown
---
tags:
  - categories
---

![[Books.base]]
```

Its embed targets [Templates/Bases/Books.base](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/Templates/Bases/Books.base), whose global filters are:

```yaml
filters:
  and:
    - categories.contains(link("Books"))
    - '!file.name.contains("Template")'
```

Thus membership comes from the object's `categories` value, not its folder, template filename, prose links or a registry row. The category tag identifies the dashboard by convention; it is not the member-selection predicate. The Base provides Books, Top rated, Author and Genre views. The Author view additionally tests `list(author).contains(this)`.

The real [Kevin Kelly note](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/References/Kevin%20Kelly.md) embeds `Books.base#Author`. When embedded there, `this` represents Kevin Kelly, so the reusable view selects books whose author links to that note. When embedded in the Books category, the default Books view provides the category listing. Named-view selection and embedding context are documented native behavior. [Create a base](https://obsidian.md/help/bases/create-base), [Bases syntax](https://obsidian.md/help/bases/syntax).

## Other categories confirm both the convention and its variations

An exhaustive scan of all **21 Categories Markdown files** found the `categories` tag in every file. Twenty have only `tags` in frontmatter; Podcasts additionally has `related`. Counts for the proposed `template`, `base` and `vault_role` keys are each **zero**. [Pinned Categories tree](https://github.com/kepano/kepano-obsidian/tree/473697347a0eaac790a6596229c741b3915f3b77/Categories).

| Category example | Actual dashboard and query mechanism |
| --- | --- |
| [People](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/Categories/People.md) | Embeds People.base, which selects linked People memberships. People Template initializes that membership; Author Template also assigns People and adds a separate Authors `type` link. There is no exclusive one-template-per-category binding. |
| [Clippings](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/Categories/Clippings.md) | Embeds Clippings.base; the Base filters linked Clippings memberships and supplies a contextual Author view. [Base source](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/Templates/Bases/Clippings.base). |
| [Movies](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/Categories/Movies.md) | Embeds two named views, Favorites and Last seen, beneath headings. It does not declare one `base` property. |
| [Places](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/Categories/Places.md) | Embeds two different files, Map.base and Places.base. This demonstrates multiple presentation files; it does not authorize adding the reference's Maps dependency to our baseline. |
| [Journal](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/Categories/Journal.md) | Embeds Journal.base, whose member predicate is a journal **tag**, rather than linked category membership. Journal Template initializes that tag. [Base source](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/Templates/Bases/Journal.base). |

The [People Template](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/Templates/People%20Template.md) and [Author Template](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/Templates/Author%20Template.md) also illustrate that templates may contribute different content to the same category. This is composition by convention, not class enforcement.

## Human steps and what Obsidian actually automates

1. Create/open a note and give it an appropriate filename. The reference uses meaningful filenames; its template names use forms such as `Book Template`, category names such as `Books`, and Base filenames such as `Books.base`.
2. Invoke **Templates: Insert template** and choose Book Template. Native Templates inserts its text and substitutes variables at insertion. The reference enables Templates in [.obsidian/core-plugins.json](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/.obsidian/core-plugins.json), with `Templates` configured as the folder in [.obsidian/templates.json](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/.obsidian/templates.json). [Native Templates](https://obsidian.md/help/plugins/templates).
3. Fill/edit properties and content. Quoted wikilinks in text/list properties are native links; inserted template properties are added/merged with existing properties. Enabling Templates does not establish continuing category-schema enforcement or automatic future edit dates. Exact composition/merge cases remain a native trial. [Properties](https://obsidian.md/help/properties).
4. Follow the Books category link or open the category note. Its body embed renders the existing Base query, which selects matching existing notes. Changing membership changes the query input; it does not select or reapply a template. [Bases syntax](https://obsidian.md/help/bases/syntax).

The reference's short `Books.base` embed points to a file actually located in `Templates/Bases`; it is an internal file link, **not** a value resolved through category frontmatter. The `.base` extension identifies the non-Markdown file, and native syntax also supports a qualified vault path and a named view. Duplicate-name resolution and rename behavior need the migration's explicit path convention and trial. [Internal links](https://obsidian.md/help/links), [Create a base](https://obsidian.md/help/bases/create-base).

There are narrower plugin-specific associations: [.obsidian/daily-notes.json](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/.obsidian/daily-notes.json) selects Daily Note Template, and [.obsidian/zk-prefixer.json](https://github.com/kepano/kepano-obsidian/blob/473697347a0eaac790a6596229c741b3915f3b77/.obsidian/zk-prefixer.json) selects Journal Template. These configure particular note-creation workflows. They are not category-to-template bindings. Neither the inspected reference nor the current Templates/Properties/Bases documentation supplies a generic binding based on `categories`, `template`, `base` or `vault_role` note properties.

## Consequences for the current proposal

The active ticket's Q6 proposed `vault_role: category` plus linked `template` and `base` fields. **Those are additional design proposals, not accepted choices and not kepano's existing mechanism.** They could provide custom metadata for people/checkers, but merely adding them would not cause native Templates to select a template or cause Bases to embed themselves. A single `base` field would also not describe the reference's multiple embeds/views without additional conventions.

**Recommendation for the human's decision:** follow the unchanged native mechanisms—manual template selection, templates that initialize linked membership, category notes containing actual Base embeds, and dynamic member queries. A `categories` tag is the reference's existing category-dashboard marker and deserves consideration before introducing another role field. Template-discovery convenience can be documented through the naming convention or ordinary links; a registry is optional and requires a reason beyond making native functionality work. This recommendation does not select a marker or schema on the user's behalf.

Already accepted adaptations in [the representation decision](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/41) and [the active convention ticket](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/49) include faithful imported category identity, actual notes for typed definitions/members, a dynamic Home-linked category overview, an explicit appearance provider, and retaining Home/Notes/Attachments while adding Categories/Templates/Templates/Bases. Existing v1 deterministic naming, collision reservation and source/payload preservation remain constraints. New support-name reservations, precise qualified-link/alias conventions and robust support-file exclusions still need specification; the reference's filename-substring exclusion should not silently hide legitimate imported notes. Exact registry fields remain undecided.

No schema, plugin configuration, checker or production code was implemented. This report establishes the mechanism; native rendering, insertion, merging, query completeness and collision/rename behavior remain for the already planned disposable trial.
