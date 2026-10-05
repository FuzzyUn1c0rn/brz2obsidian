# Choose how thought types and inherited appearance translate into the vault

Status: resolved
Type: grilling
Labels: wayfinder:grilling
Parent: [Find the route to version 2 for the Software Engineering Brain](../map.md)
Blocked by: 02, 08, 10
Assignee: /root

## Question

How should the evidenced thought-type definitions, assignments and inherited properties appear and behave in everyday Obsidian use?

Discuss representative, privacy-safe examples with the user after all evidence prerequisites are resolved. Separate type identity, membership, definition-authored content, hierarchy and effective appearance. Choose the representation of definition items and assigned thoughts, discovery of members, any inherited versus explicit values worth exposing, and the behavior of empty or otherwise uncreated endpoints.

Make the preservation tradeoffs concrete: facts in the migration record, readable information in notes/properties, and visible appearance are different results. Decide which are required for a successful migration, which appearance changes are acceptable in standard Obsidian, and whether optional CSS or plugin-dependent enhancements are worth a separate scope. Carry forward the existing native-feature baseline unless the human chooses to reopen it.

Record only decisions reached through live exchange. Update resolved domain terms in the root glossary; propose an ADR only for a consequential architectural tradeoff. Surface newly specific decisions as separate children of the map.

## Decision boundaries

The accepted representation is recorded in the Answer below. Detailed category paths/aliases, property syntax, template fields/defaults and maintenance invariants belong to [Choose templates and maintenance conventions for the generated vault](11-vault-templates-and-maintenance.md) and the required specification. Native rendering, query/rename behavior, appearance updates and portability belong to [the disposable vault trial](05-version-two-vault-trial.md). This decision defines the target representation; the named follow-ups supply schema choices and behavior verification before implementation.

## Comments

- 2026-10-04: Created during charting. Wait for Obsidian evidence and the native source checks before choosing the mapping; the latter depend on the complete source comparison.
- 2026-10-04: The [working native evidence](../research/native-source-behavior.md) confirms icon/colour precedence but does not support generic label fallback: labelled types assigned to existing control members left their labels blank. Use that qualified evidence when discussing desired vault behavior after the source task is complete.
- 2026-10-04: The [native source investigation](08-native-source-behavior.md) is resolved. Its completed report includes approved icon reset and the attachment-related icon-token change. Both prerequisites are now resolved; this is the next unclaimed decision on the frontier. The representation still requires live discussion with the user.
- 2026-10-04: Claimed at the user's request to begin grilling. Use the grilling and domain-modeling skills; record only decisions the user makes and pause after each question round. Keep the ticket open until the design tree is settled and the user confirms shared understanding.
- 2026-10-04: Opening question round covers three independent choices: the representation of type identity/membership, the essential surfaces for visible appearance, and the acceptable dependency boundary. Recommendations are proposals, not accepted decisions. Subsequent rounds cover materialization, membership discovery and maintenance, direct versus effective values, overrides/labels, and behavior after editing, as the answers establish their prerequisites. Current official Properties, Graph and CSS-snippet documentation was rechecked; concrete rendering remains subject to the disposable vault trial.
- 2026-10-04: The user mostly agrees with the initial recommendations and proposes linked `categories`, category notes, corresponding templates, canonical linked properties, dynamic Bases and embedded category dashboards, drawing on Steph Ango's actual vault. They explicitly require reference inspection before design/implementation. Added [Evaluate the kepano reference vault against the migration requirements](10-kepano-reference-patterns.md) as a prerequisite. The broad architectural direction is recorded; exact source-to-category naming, schema, materialization, appearance surfaces, dependency boundary and maintenance scope remain for live confirmation. No design has been finalized from the supplied summary alone.
- 2026-10-04: A source impact check found 152 of the 195 typed ordinary thoughts have neither a nonblank active thought note nor a present ordinary file/URL beyond icons and TXT records. Classification properties and Base discovery require actual note files. This is not a claim of 152 additional files: the v1 hierarchy policy may already materialize some. The metadata-only member policy therefore needs an explicit human decision. Detailed templates/property vocabulary and ongoing maintenance scope now have a focused child, [Choose templates and maintenance conventions for the generated vault](11-vault-templates-and-maintenance.md), which also blocks the native trial.
- 2026-10-04: The [pinned reference investigation](10-kepano-reference-patterns.md) is resolved and its [findings](../research/kepano-reference-patterns.md) integrated. The actual Books chain supports the category/dashboard model. The separate map `type` taxonomy, plugin dependence, lack of schema enforcement and filename-based template exclusions require explicit adaptations. Next round addresses source category fidelity, metadata-bearing member materialization and the required appearance surfaces; detailed template fields/tooling remain in the focused follow-up. Await the user's answers before proceeding with design.
- Next question round: **Q4** asks whether initial categories/memberships should map faithfully to the seven source types before later manual expansion or use a reviewed remapping; **Q5** asks whether every typed member should receive a metadata-bearing note so Bases include the no-authored-content cases; **Q6** asks whether dashboards plus note icons satisfy appearance goals or file-list/Graph presentation is essential. Proposed defaults are faithful initial mapping, complete typed-member materialization while retaining v1 handling for untyped thoughts, and dashboards/note icons with other appearance enhancements subject to the native trial. These are recommendations, not accepted choices; pause for the user's answers.
- 2026-10-04: The user answered **Agreed** to Q4–Q6. Recorded the confirmed choices above and recomputed the question frontier. Next round asks about live versus snapshot appearance across accepted surfaces, a stable appearance source for future multi-category notes, and a category overview entry point. Wait for the user's answers; detailed template/property/tooling design remains in its focused child.
- 2026-10-04: The user answered **Agreed** to Q7–Q9: live category-driven appearance in Base dashboards with editable migration snapshots for note icons; an explicit appearance category initially mapped from the source type; and a dynamic Categories overview reachable from Home. Together with the prior confirmed round and requested architecture, this settles the representation tree and confirms shared understanding. Resolved this ticket; no second human decision or implementation ticket was started in this session.
- 2026-10-04: Closure checks passed for the Answer/status, local artifact links, blocker references and dependency acyclicity, and public source-identity/URL privacy. The source archive retains its original hash. The unclaimed frontier is other-archive coverage followed by template/maintenance conventions; no production test run was needed for this decision/documentation update.

## Answer

Resolved through live grilling on 2026-10-04. The user requested the kepano-inspired architecture, then explicitly agreed to the recommendations in Q4–Q6 and Q7–Q9. The [pinned reference investigation](../research/kepano-reference-patterns.md), [native source controls](../research/native-source-behavior.md) and [Obsidian options](../research/obsidian-type-options.md) establish the evidence boundaries for this accepted design.

### Classification and materialization

Map each of the supplied seven thought types directly to a first-class linked category note/dashboard. Each assigned ordinary thought receives a linked entry in its `categories` list matching its actual source type. Initially there is one membership per typed member; later user editing may add categories. Preserve source identity, original titles, assignment evidence, labels and appearance facts. The migration does not infer new classifications, merge categories or rename them to imitate the reference's pluralization convention. Exact safe paths and aliases follow the agreed identity/naming conventions and the focused follow-up.

Create notes for all seven definitions and all 195 typed ordinary members, including those without authored note/resource content. Their membership and relationships make those notes useful objects. Keep the v1 materialization policy for untyped empty thoughts, along with Home, original-content and payload preservation guarantees. The 152 typed members without substantive note/resource content are not a prediction of 152 additional files; some already qualify as hierarchy notes. Final file counts must come from the agreed planner and verification.

Category membership remains distinct from source tags, ordinary parent/child relationships and Jump relationships. Retain those meanings and their existing representations. Category links can serve as native Graph connections; special category-edge rendering and file-list icons are not required. Type labels belong to their source definitions and must not be invented as inherited member labels.

### Discovery and navigation

Each category note embeds a Base that dynamically discovers actual member notes through category membership. A prose, hierarchy or appearance-source link to the category is not itself membership. Exclude templates/generated support files using deliberate support conventions, rather than blindly copying the reference's filename-substring filter. Query completeness, quoted/qualified links, renames and false-positive controls require the native trial.

Generate a Categories overview reachable from Home. Its Base dynamically lists the category dashboards, giving the user a common entry point without a manually maintained list. This is generated vault navigation, not an invented source relationship. Preserve the source-neutral migration record and distinguish support artifacts from source-item notes in accounting.

### Appearance and editing

Require effective icons in category dashboards and icons inside individual notes. During live prototype review the user explicitly removed the decorative **Appearance** display from the design because it adds no navigation value; coloured duplicate note-name rendering is no longer required. Keep source colour facts as preserved metadata, rather than deleting them with the presentation. Retain explicit icon overrides: the member's explicit icon wins over the category default. Preserve declared versus inherited facts and original bytes; neither opaque icon tokens nor the reference's first-type map formula replaces the evidenced source rules.

Base dashboards should calculate icons from current category defaults and member overrides, so editing a shared category icon updates those views. Individual note icons start as editable migration snapshots: they reference the image selected at conversion and are not automatically rewritten when a category's icon property changes. Reuse the preserved local media rather than copying an inherited icon payload per member; normal edits to the shared image file itself can still affect its references.

Give each member an explicit **appearance category**, initially its category mapped from the source thought type. This is the chosen provider of default style, independent of category-list order. Later additions or reordering of membership alone must not silently switch the appearance provider. Member overrides retain precedence. Exact property names, validation/fallback conventions for future manual edits, and any executable maintenance helpers are owned by the template/maintenance follow-up.

Continue the built-in Obsidian baseline with optional vault-local CSS. Graph colour is an optional native-trial candidate; no required community plugin, Maps dependency, automatic note-icon propagation or global inherited UI styling was accepted. The native trial must verify that the agreed dashboard/icon presentation is achievable and usable, and reopen this decision if a material limitation requires a new choice.

### Remaining route

The representation decision is complete. [Choose version 2 coverage for the other archive differences](04-version-two-coverage.md) owns the non-type support/gap decisions. [Choose templates and maintenance conventions for the generated vault](11-vault-templates-and-maintenance.md) owns detailed schemas, template defaults, naming/support conventions and ongoing tooling scope. Their outcomes feed the disposable native trial, then the required **to-spec** specification and **to-tickets** implementation frontier. Resolving this decision does not complete the v2 map or establish production conversion success.
