# Choose note identity, relationships, and vault layout

Status: resolved
Type: grilling
Labels: wayfinder:grilling
Parent: [Find the route from a BRZ archive to an Obsidian vault](../map.md)
Blocked by: 01, 02, 07, 08, 09, 10
Assignee: /root

## Question

Which vault representation should the converter use so that the user can find thoughts, read their content, and navigate hierarchical context and connections with simple native Obsidian links?

Use the source and Obsidian evidence to agree what becomes a note; how source identity and display names survive; how filenames handle collisions and awkward characters; how tags, types, metadata, and attachments appear; and how each supported relationship is represented.

The smaller export supplies tag assignments through links despite empty `TagIds`, a system thought and system relationships, and explicit arrow flags distinct from hierarchy placement. The larger supplies duplicate names and additional attachment cases. Use the controlled relationship evidence to establish parent/child orientation and default direction before labeling them. Distinguish documented enum meaning from the still-unverified user-facing purpose of system relationships.

Discuss concrete scenarios such as multiple parents, cycles, duplicate names, a thought with no note content, and a connection whose direction or meaning differs from an ordinary link. Choose whether folders express categories, source relationships, or only storage. Do not equate a graph with a folder tree by assumption.

The user's first-round answers are constraints for subsequent choices: represent empty thoughts as uncreated targets, use folders for storage, preserve hierarchy, and simplify explicit arrow/one-way presentation. Resolve content eligibility and how relationships between two uncreated targets remain accessible. Do not treat a deliberate uncreated target as an invalid source reference.

Use grilling and domain-modeling with the human. Record selected trade-offs in the answer and vocabulary in the root glossary; use an ADR only when its criteria apply.

## Comments

- 2026-10-03: Resumed after the controlled relationship investigations. All prerequisites are resolved. Claimed to agree the vault representation with the user, using grilling and domain-modeling. The first round covers ordinary-thought coverage, folder purpose, and the trade-off between reciprocal navigation and source one-way visibility; downstream naming and preservation details await those answers.
- 2026-10-03: User answered Q7: avoid creating notes for empty thoughts; use Obsidian links to uncreated notes so they can be materialized later. Q8: agreed to shallow storage folders and hierarchy expressed through links. Q9: prioritize simple native links and preserved hierarchical context; loss of explicit arrow/one-way details is acceptable. Consider a lightweight direction scheme only if useful; do not add complexity solely to emulate TheBrain. These are accepted constraints; the remaining representation choices are still open.
- 2026-10-03: Started focused evidence gathering on uncreated targets, their later creation, and source relationships where neither endpoint has substantive content. This checks feasibility without reversing the user's preference for avoiding empty note files.
- 2026-10-03: User answered Q10: use ordinary Markdown Parents, Children, and Related linked sections, omitting empty sections and arrow/one-way decoration. Q11: use readable thought names for files and uncreated targets, sanitizing unsafe characters and adding suffixes only for collisions. Reserve distinct targets across all thoughts, including thoughts without files; exact filename/path and collision rules will be specified after the vault model is agreed.
- 2026-10-03: [Verify uncreated targets and empty-thought hierarchy coverage](09-uncreated-target-evidence.md) is resolved. Independently reran the aggregate inspection with Python 3.14.8: 20/18 ordinary thoughts lack substantive content, and 7/4 hierarchy relationships connect two such thoughts. A also contains an isolated empty tag and a different tag with authored note content. File/URL-bearing thoughts require a content note even if their thought-note text is empty; icons and labels were counted separately. The next round asks the user to choose a readable home for empty-to-empty hierarchy, native-versus-linked tag presentation, and a separate provenance record. No choice in that round is assumed.
- 2026-10-03: Before the next round was sent, the user proposed creating a parent note for an otherwise unrepresented hierarchy connection, then clarified that this applies when **neither endpoint** has a note file. Every existing endpoint note will show its applicable Parents/Children sections, so creating one endpoint can cover several relationships. [Quantify creating parents for uncovered hierarchy relationships](10-parent-materialization-evidence.md) checks the effect and selection-order issue before agreeing the exception to uncreated empty thoughts. The index alternative and exact selection policy remain unsettled.
- 2026-10-03: While parent-materialization counts are investigated, sent the independent remaining choices: Q13 native Obsidian tags with preserved tag-note content and a readable listing for memberships on uncreated targets, versus linked tag thoughts; Q14 a separate JSON source/target/relationship record, versus per-note source metadata or minimal navigation data. Both are pending human answers. The proposed JSON record would not require special Obsidian navigation or a plugin.
- 2026-10-03: User answered Q13: native Obsidian tags, retain authored tag-note content in a normal note, and preserve memberships for uncreated thoughts in a small readable listing. Q14: retain a separate JSON migration record for original identities/names, assigned targets, and source relationship fields. Keep ordinary note presentation simple; archival source fields do not require Obsidian direction controls.
- 2026-10-03: Research found that the proposed hierarchy exception needs 5/2 additional ordinary note files in A/B, leaving 15/16 ordinary targets uncreated. The real inputs have no selection-order variation, but a synthetic empty A→B→C chain does: creating B can cover both edges. Sent Q15 to adopt the parent-note rule with reuse, versus a shared index; Q16 to retain source inline images and list other files/URLs in a Resources section, versus embedding additional supported resources; Q17 to show short source labels below a created note's title without making labels alone trigger creation, while keeping source dates/colors/other metadata in JSON, versus archival-only labels or added date properties. These three decisions await human answers.
- 2026-10-03: User answered Q15: adopt the parent-note exception with reuse. Q16: retain existing inline images and link other files and external references from Resources. Q17: show short source labels below the title of created notes without making labels alone trigger creation; keep dates, colors, and other source metadata in the JSON record. Do not create a hierarchy index for the already-covered ordinary hierarchy. Remaining model edge case: readable representation for an isolated empty ordinary thought or a Related connection between two uncreated targets (neither is observed in the supplied ordinary-thought data).
- 2026-10-03: Sent Q18 to retain isolated empty thoughts and Related pairs between two uncreated targets in a small readable fallback listing alongside the tag listing, versus creating notes for these exceptions. Sent Q19 to keep the observed system thought and 11 system relationships in the JSON migration record while omitting them from ordinary navigation, versus explicitly unclassified navigation. The system item's user-facing purpose remains unverified; do not invent hierarchy or semantic labels for its relationships. Both choices await answers.
- 2026-10-03: User agreed to both Q18 and Q19. Use the small readable fallback listing for isolated empty thoughts and Related connections between two uncreated targets. Keep the observed system thought and its 11 relationships in the JSON migration record, outside ordinary navigation. All individual representation questions are answered. Consolidated the choices below for the final shared-understanding check required by grilling; pause work after presenting that check until the user replies.
- 2026-10-03: User confirmed the consolidated model in Q20. Shared understanding is established; this decision is resolved. The next step is the disposable Obsidian vault trial, followed by the conversion/failure contract and implementation-ready specification.

## Answer

### Scope and storage

The baseline is standard Obsidian, without required community plugins, for a one-time migration into a new vault. Initial source coverage is the two inspected TheBrain 15 format-5 exports and archives with the same verified features. Universal format/version support is outside this effort.

Use shallow `Notes/` and `Attachments/` storage folders. Source hierarchy is represented by links, rather than folder nesting. Supporting tag/fallback listings and the JSON migration record are separate from ordinary thought notes; their exact filenames and schema belong to the later conversion contract.

### Which thoughts become files

Create an ordinary note when its source thought has nonblank thought-note text, an archived substantive file/image, or an external file/URL/directory reference. Empty note placeholders, decorative icons, labels, colors, and identity/date metadata do not alone require a note.

Empty ordinary thoughts otherwise remain distinct uncreated targets. For any hierarchy relationship with neither endpoint represented by a note file, create its parent note. Reuse the resulting note set so one created endpoint can cover several relationships, and write all applicable relationship sections after selecting the files. The selection must be deterministic; its exact algorithm will be specified in the conversion contract, without promising a globally minimum note count.

The supplied cases require five additional ordinary parent notes in the smaller export and two in the larger, resulting in 48/42 ordinary notes and 15/16 uncreated ordinary targets. The smaller export's one content-bearing source tag receives an additional normal note. These counts exclude supporting listings. See [Creating parent notes for uncovered hierarchy relationships](../research/parent-materialization.md).

If an isolated empty ordinary thought has no other readable reference, retain a link to it in the small fallback listing. A Related connection between two targets that remain uncreated is recorded as a readable linked pair there. Do not create extra note files solely for these cases. This fallback is conditional; neither ordinary-thought case occurs in the two real inputs.

### Identity and names

Use readable thought names for note filenames and uncreated targets. Adjust unsafe characters and append a distinguishing suffix only for collisions. Reserve identities across both created and uncreated targets, so later creation cannot merge duplicate thoughts. Retain the exact original title when a note is created and original identity/name in the JSON migration record.

Exact normalization, suffixes, path limits, escaping, and link syntax are later contract/trial details. The identity rule is already agreed; implementation choices must satisfy it.

### Everyday note presentation

Show the original title and, when present, the short source label below it. Preserve thought-note content, adapting internal thought links and archived image references to their vault destinations. Keep existing inline images inline. List additional associated files and external references as ordinary links in Resources, with archived files under Attachments.

Use short Parents, Children, and Related linked sections at the end of created notes; omit empty sections. Every created endpoint lists all applicable relationships, including links to uncreated targets. Multiple parents are supported. A hierarchy cycle does not require nested folders or recursive creation; the endpoint-coverage rule and linked sections still apply.

Ordinary parent/child relationships determine Parents/Children membership independently of arrow direction. Ordinary jumps appear as Related connections. Both endpoints show the relationship when both have note files, regardless of TheBrain's one-way visibility. Explicit arrows and one-way decorations are intentionally simplified; their original fields remain in the JSON migration record. Native Graph represents the links written in files and does not supply typed hierarchy edges.

### Tags and source metadata

Represent source tag assignments using native Obsidian tags on created notes. Preserve authored source tag-note content in a normal note. Retain tag names and memberships involving uncreated targets in the small readable tag listing, including the observed isolated empty source tag. The tag listing preserves those assignments; an absent target has no own stored properties.

Keep original IDs/names, assigned targets, relationship fields, source dates, colors, and other source metadata in the separate JSON migration record. Do not require users to navigate through that record for ordinary note use. Preserve source labels there as well as displaying them when their thought has a note.

Retain the observed system thought and its 11 system relationships in that record, while omitting them from ordinary vault navigation. Their user-facing purpose is unverified, so no ordinary meaning is invented for them.

### Practical limits and next validation

Following an uncreated target later creates a note through Obsidian's normal behavior; the converter does not remain active to populate that new file. Existing incoming links and their relationship context remain in the generated notes/listings. Verify creation location, backlinks, and usability in the vault trial.

The next ticket, [Validate the proposed vault in Obsidian](04-vault-trial.md), tests this representation with a disposable local vault and the user's reaction. Exact naming/link rules, deterministic parent selection, supported-feature validation, attachment anomalies, source history/deletions, and failure/reporting policies belong to [Choose the conversion and failure contract](05-conversion-contract.md). The agreed representation must not silently discard unknown or unsupported content; that ticket decides how it is reported.
