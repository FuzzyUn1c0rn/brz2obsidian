# Native disposable vault trial

Built and checked on 2026-10-04 using the Computer skill in **Obsidian 1.13.7**.
This establishes observed behavior for [the prototype ticket](../issues/05-version-two-vault-trial.md).
The user accepted the prototype presentation and subsequently settled its maintenance choices in the focused follow-up. The specification is now unblocked. This trial does not establish a finished converter or final archive acceptance.

## Review artifact

- Private vault: [Home](../../../brz/v2-prototype/Software%20Engineering%20v2%20Prototype/Home.md).
- Guided scenarios: [Review walkthrough](../../../brz/v2-prototype/Software%20Engineering%20v2%20Prototype/Review%20walkthrough.md).
- Private evidence: `brz/v2-prototype/evidence/`, including numbered native screenshots/accessibility observations and `integrity-receipt.json`.
- Disposable construction script: `brz/v2-prototype/build_prototype.py`; read-only convention sketch: `brz/v2-prototype/check_prototype.py`. Sanitized source scripts are captured on the local throwaway branch recorded in the ticket. Generated source content and screenshots remain ignored.

The vault contains all **seven type definitions and 195 typed members**, including members without authored content, the original Brain Home, and selected additional resource owners: **208 source items**. It adds clearly marked synthetic editing controls and two extension categories. The operational Home links the category overview, instructions, resource cases and original Brain Home. Notes use linked properties, normal Markdown relationships and embedded native Bases. Templates and Bases are enabled core plugins; no community plugin or custom CSS is required.

## Observed native behavior

| Area | What the trial demonstrated |
| --- | --- |
| Category discovery | Actual members render in table and card views. Templates, a prose-only category link, an ordinary source-style `categories` tag and a same-basename ordinary note are excluded by operational guards. A legitimate note containing “Template” in its name remains included. |
| Appearance | Local icons and computed foreground/background colours render in Bases. Editing a category's properties changes inherited dashboard values live. Member overrides win per field. Existing body-icon snapshots remain unchanged. Original category defaults were restored after the experiment. |
| Provider controls | Blank provider gives no inheritance. Missing, deleted/dangling and nonmember providers show an invalid-provider state without borrowing that category's appearance. Reordering and adding memberships does not change an explicit provider. |
| Templates | The configured picker discovers Markdown templates and excludes nested `.base` files. Native insertion in Editing view initializes linked memberships and `YYYY-MM-DD` dates to the current day. Reading-view insertion did not modify the target in this trial. No imported identity fields are fabricated in new notes. |
| Existing-note composition | A full category template replaced existing scalar dates with today's dates. A candidate template containing only `categories` merged an additional membership while preserving dates, explicit provider, synthetic imported identity and authored content. The second Base discovered the note immediately. |
| Extension | Native insertion of the category starter initialized a new dashboard, tag, dates, heading and contextual Base embed. That dashboard discovered a manually classified note without any member-template insertion. |
| Renaming | Native note rename updated a normal incoming link while retaining dates, identity and content. Category rename updated membership/provider/template wikilinks. A contextual embedded query retained its member; a literal `link("old category path")` Base filter remained unchanged and returned zero members. Native rewrites shortened some originally qualified links. Alias lookup found the existing synthetic object. |
| Markdown/resource cases | The confirmed unusual thought note renders its authored text and adapted local image. An intact source PDF opened in the native viewer, showing 337 pages. Aggregated source-gap notices report absent TXT bytes without fabricating extracted text. |
| PDF search | Vault Search returned zero results for a unique PDF-only sentinel. The PDF viewer's own search found one match. Adding a synthetic Markdown positive control made vault Search return only that Markdown note. |
| Video | Native source YouTube embeds previewed and played. The timed URL was rendered through an embed with `start=18`; the first playback observation was at 21 seconds. Original resource URLs retain their query strings. Playback was paused after checking. Remote/offline availability remains a destination limit. |
| Baseline interaction | Synthetic native tag search opens the hierarchy control. Parents/Children/Related links, Backlinks and local Graph work beside linked categories. Graph includes the category link and an intentionally uncreated ordinary target. This archive has no source tag assignments; synthetic tags do not replace earlier archive regression checks. |

The trial demonstrated documented Link/file property access, image and HTML rendering; the user's subsequent review withdrew the decorative HTML Appearance display. The accepted presentation keeps native image rendering. Contextual `this` refers to the embedding note. Card images use native Base settings. These presentation formulas do not enforce schemas or automatically select templates. [Bases functions](https://obsidian.md/help/bases/functions), [Bases syntax](https://obsidian.md/help/bases/syntax), [Cards view](https://obsidian.md/help/bases/views/cards).

## Review decisions exposed by the trial

The user said the prototype looks good overall and that they are quite happy with this version. Their requested presentation change is applied: **Icon first, Note second, remaining columns in their existing order**. The Categories overview uses Icon first, Category second. All nine relevant table views were checked; eight Base files changed because one was already ordered this way. Structural comparison retained other Base settings, and private native evidence 36/37 verifies both a category table and the overview. The disposable builder now generates this order too.

The Book icon is a copied PNG image, referenced through a text property containing a wikilink. The Book member template leaves the optional `icon` override empty; its explicit appearance provider supplies the category's default image in the Base. These observations explain the existing mechanism rather than changing its accepted semantics.

During further live review, the user said the **Appearance** column adds no useful navigation value and explicitly removed it from the design, while keeping icons and saying the rest looks good. Removed its coloured duplicate note-name rendering from all eight member Bases, covering 16 table/gallery views. Icon and Note keep their first/second order; other view settings and source colour metadata are retained. The builder is updated too. Private native evidence 38 verifies the final category layout with unchanged membership, and the structural receipt checks the remaining settings. The native colour experiment above remains historical evidence of the trial, rather than a requirement of the accepted presentation.

1. **Safe template composition, accepted:** use full templates for new notes and direct membership edits on existing notes. Do not deliver additional additive templates in v2. The category-only insertion candidate remains trial evidence.
2. **Category rename and Base queries, accepted:** generate contextual member queries that follow the embedding category note. Enter member views through category dashboards; a standalone Base without an embedding category has no category to display. Preserve that deliberate reference adaptation and entry-point tradeoff in the specification.
3. **Qualified links after human editing, accepted:** generation retains deterministic collision-safe links. The read-only checker accepts shortened links that resolve unambiguously, reports ambiguous category/provider/local-image references without repair and continues to allow intentionally uncreated ordinary targets.

The user accepted all three recommendations through a subsequent live grilling round, recorded in [Choose maintenance adaptations exposed by the native vault trial](../issues/12-native-maintenance-adaptations.md). These choices define v2 implementation requirements; the disposable vault retains its comparison controls and does not implement a production checker. No production schema, converter or filename contract was changed by the trial.

## Preservation and limits

The construction script ran successfully into a fresh repeatability directory. Its retained-copy integrity receipt confirms the archive fingerprint is unchanged, **99 copied payloads** and **43 exact original note backups** match their hashes, all **208 imported identities** match selected records, and **416 date fields** match their original encoded calendar prefixes. Full timestamp strings remain in the private migration record. This does not establish native source-display or timezone equivalence.

The read-only convention sketch hashes vault content before and after checking; it changed no content. It reported only the intended controls: three invalid providers and one invalid category membership. Custom properties and an intentionally uncreated ordinary target were allowed. It is a decision aid, not the complete v2 checker: production diagnostics, broader invalid schemas, duplicate/collision handling, alias ambiguity and exact checking boundaries remain implementation requirements.

Ordinary relationships from selected items now have Parents, Children and Related sections, including uncreated endpoints. This subset does not implement the complete empty-thought selection algorithm or all untyped source items. Prototype naming and Markdown adaptation are deliberately narrow and do not establish production span-preservation guarantees. Source labels are distinct from inherited appearance. Full raw coverage, strict source acceptance, all-archive cumulative regression, publication protection and final converter-output acceptance remain later gates.

The vault keeps native edits and deliberately invalid controls for review. The archive and the user's other Brains/vaults were not edited. No file was uploaded or remotely published.
