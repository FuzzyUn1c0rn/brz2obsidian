# Standard Obsidian representation evidence

Investigated: 2026-10-03. Supports [Establish what standard Obsidian can represent](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/52). Scope: a one-time migration into a new vault, without community plugins. This report uses public first-party documentation and synthetic examples only; it does not inspect or upload either real BRZ archive.

**Finding:** Standard Obsidian can preserve readable relationship meaning alongside notes and files. Its native Graph view represents internal links, while Canvas provides a separate native view with labeled connections. The final representation remains a design decision.

## Documented behavior and design consequences

| Area | Documented behavior | Consequence or limit |
| --- | --- | --- |
| Vault | Notes are Markdown plain text in a local folder and its subfolders. External file changes are refreshed; `.obsidian` contains vault preferences. An existing folder can be opened as a vault. [Data storage](https://obsidian.md/help/data-storage), [Create a vault](https://obsidian.md/help/vault). | **Inference:** a generated folder needs no proprietary note database or account. Shipping settings is optional for the content format. |
| Note content | Obsidian supports CommonMark, GitHub Flavored Markdown, and its own extensions. HTML is sanitized; Markdown within HTML elements is not rendered, and HTML blocks have formatting constraints. [Markdown flavors](https://obsidian.md/help/obsidian-flavored-markdown), [HTML content](https://obsidian.md/help/html). | **Inference:** preserving source text and preserving its appearance are separate acceptance criteria. Rich HTML, mixed HTML/Markdown, and source-specific links need conversion rules and a render trial. |
| Link targets | Wikilinks and Markdown links are supported. Paths use `/`, including on Windows; Markdown destinations require URL encoding. Non-Markdown files need their extension. Display text can differ from the destination. [Internal links](https://obsidian.md/help/links). | **Inference:** explicit paths avoid ambiguous titles, but their base must match the link form; see the clarification below. Escape visible text independently of paths. Avoid machine-specific absolute paths for archived files. |
| Alternate names | `aliases` is a YAML list. Selecting an alias creates a link to the actual note with alternate display text. [Aliases](https://obsidian.md/help/aliases). | **Inference:** aliases improve discovery but do not constitute an identity system or resolve duplicate source titles. |
| Structured fields | Properties use top-of-file YAML. Names must be unique within a note. Types include text, list, number, checkbox, date, and date/time; a property name has one type throughout the vault. Text/list values may contain quoted wikilinks. Nested properties and Markdown formatting are unsupported in the normal property editor. [Properties](https://obsidian.md/help/properties). | **Inference:** source IDs fit quoted text; flat relation lists fit the native editor. Full edge objects require another representation. Generated fields must avoid conflicts with existing source frontmatter. |
| Navigation | Backlinks show references to the active note, with optional paragraph context; unlinked mentions search its name. [Backlinks](https://obsidian.md/help/plugins/backlinks). | **Inference:** backlinks expose incoming links, not an explicitly typed inverse relationship. Readable relation headings can provide context. |
| Graph | Graph lines represent internal links. Arrows show link direction; groups color notes; filters include attachments and orphans. [Graph view](https://obsidian.md/help/plugins/graph). | **Inference:** the documented Graph controls do not provide typed or labeled edges. Adding inverse links to both notes makes written links reciprocal, even when the source relationship is directional. Repeated links and multiple source relationships between the same pair need a trial. |
| Files | Attachments are ordinary filesystem files. Native formats include Markdown, Canvas, Bases, images, audio, video, and PDF; media support depends on device codecs. The **Show all file types** setting exposes other extensions for linking and discovery. [Attachments](https://obsidian.md/help/attachments), [Accepted formats](https://obsidian.md/help/file-formats), [Settings](https://obsidian.md/help/settings#Files%20and%20links). | **Inference:** copy all archived files byte-for-byte; distinguish preservation from native preview. Unsupported formats still need an accessible path or index and a trial of opening behavior. |
| Embeds | `![[...]]` embeds supported files, notes, headings, or blocks. PDF embeds can select a page. Canvas embeds show shapes without card text. [Embed files](https://obsidian.md/help/embeds). | **Inference:** embed supported media when useful, but retain links for unsupported files. A rendered Canvas embed cannot be the only readable record of relationships. |

### Path bases: documented examples versus unverified resolution

The [Internal links documentation](https://obsidian.md/help/links) describes vault-root folder paths and gives both `[[Projects/Three laws of motion]]` and `[Three laws of motion](Projects/Three laws of motion.md)`. Separately, [New link format settings](https://obsidian.md/help/settings#New%20link%20format) offer **Relative path to file** (from the current file), **Absolute path in vault** (from the vault root), and **Shortest path when possible** (the shortest unique path). These are generation settings; they do not fully specify parsing or fallback precedence.

**Trial required:** from `Notes/start.md`, target `Notes/foo.md` using `[[Notes/foo]]`, `[foo](Notes/foo.md)`, `[foo](foo.md)`, and `[foo](../Notes/foo.md)`. The last two are candidate current-file-relative forms (**inference**), not verified behavior. Add `Notes/Notes/foo.md` to expose incorrect base selection or fallback. Also test parent-folder attachment links. Do not treat all folder-qualified Markdown targets as universally root-relative, or add a leading `/` without testing its meaning. Vault-absolute paths are distinct from filesystem-absolute paths.

## Viable relationship representations

These options can be combined; no selection is made here.

| Option | Benefit | Tradeoff / unresolved question |
| --- | --- | --- |
| Named sections in each note, with labeled linked lists | Meaning is readable in ordinary Markdown, including relation direction, labels, and edge-specific comments. | Decide which endpoint owns the canonical relationship and whether to show inverse lists. Generated navigation links affect Graph arrows. |
| Flat relation properties, e.g. `brain_parents: ["[[Notes/example-id]]"]` | Native property editing; property-based search is available. [Search](https://obsidian.md/help/plugins/search#Search%20properties). | A target list cannot alone retain a unique relationship ID, order, direction flags, and other per-edge fields. Duplicating body lists introduces two editable representations. |
| One note per relationship | A relationship can have its own ID, fields, content, and links to endpoints. | Additional files become extra Graph nodes and change navigation from a direct connection to a two-step route. |
| A machine-readable relationship manifest plus readable note lists | Complete source edge records can coexist with convenient navigation. | A manifest is a converter-defined preservation artifact; standard Obsidian will not interpret it as a typed graph. Decide which fields must also be visible to readers. |
| Optional Canvas with labeled edges | Native Canvas connects note/file cards with directed, colored, labeled lines. JSON Canvas stores edge IDs, endpoints, arrow ends, colors, and labels. [Canvas](https://obsidian.md/help/plugins/canvas), [JSON Canvas specification](https://jsoncanvas.org/spec/1.0/). | Canvas requires explicit card position and size. **Inference:** large layouts need a separate usability/scaling design; this does not add edge typing to Graph view. Text-only cards do not appear in backlinks. |

Native Bases can optionally show, sort, and filter note properties as database-like views; data remains in Markdown. This is a possible navigation aid, not a required migration format or evidence of typed Graph behavior. [Introduction to Bases](https://obsidian.md/help/bases).

## Identity, names, and portability

**Documented constraints:** Windows reserves `< > : " / \\ | ? *`, NUL, and control characters 1–31. Device names such as `CON`, `NUL`, `COM1`–`COM9` and `LPT1`–`LPT9` remain reserved with extensions; the documented superscript-digit variants are also reserved. Avoid trailing spaces/periods and case-only distinctions. [Microsoft filename rules](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file#naming-conventions). Obsidian additionally warns that link strings containing `# | ^ : %% [[ ]]` may fail. [Internal links](https://obsidian.md/help/links).

Windows commonly has a 260-character API path limit. Longer paths depend on application and system opt-in; component limits depend on the filesystem, commonly 255. Filesystem-valid paths may still fail in shell UI. [Microsoft path limits](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation). **Inference:** specify short bounded filenames, shallow folders, and a full destination-path check; do not rely on WSL or a registry change to make the resulting vault usable.

| Filename approach | Practical consequence (**inference**) |
| --- | --- |
| Sanitized source title, adding a disambiguator only for collisions | Familiar file explorer names; requires deterministic collision handling after sanitizing, truncating, and case comparison. |
| Sanitized title plus source-ID suffix on every note | Readable and consistently disambiguated; longer names. A truncated ID needs collision detection. |
| Full source ID, original title in a heading/property/alias | Stable, short, easy mapping; filenames and Graph labels can become less readable. Test discovery and navigation. |

Keep the exact original title and source ID independently of the filename. A custom `brain_id` field is preservation metadata: documented internal links target files/paths, not arbitrary property IDs (**inference**). Obsidian's inline title displays the filename, so an alias or `title` field should not be assumed to change it. [Settings](https://obsidian.md/help/settings#Show%20inline%20title). Unicode normalization and collision comparison need an explicit converter policy; Microsoft notes that Windows APIs treat names as opaque character sequences rather than normalizing them. [Microsoft path limits](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation).

## Local vault trial and next design decisions

Use synthetic cases; record installed Obsidian version and core settings. Documentation is current, but no local rendering or application behavior was verified by this research.

1. Open the generated folder; run the path-base cases above, including duplicate titles, case variants, punctuation, Unicode, and encoded Markdown destinations. Check aliases, filename-based titles, and rename updates.
2. Verify quoted text/list property links in the editor, backlinks, and Graph. Compare one-way links, inverse lists, repeated links, and several relationship types between one pair. Check whether native displays expose sufficient meaning.
3. Render representative Markdown/HTML, tables, lists, local images, and PDF embeds. Check preservation and access to an unsupported extension with default settings and **Show all file types** enabled.
4. If Canvas is pursued, verify labeled directions, file paths, backlinks, and readability at the relevant scale. Test that a copied vault still works from a different root path.

The next design ticket must settle filename/identity policy, canonical relationship storage, direction versus inverse-navigation behavior, file organization, source-frontmatter handling, and whether optional native views are worth their added output. Exact note-conversion fidelity and attachment requirements must come from the BRZ evidence; this report does not infer them from Obsidian capabilities.
