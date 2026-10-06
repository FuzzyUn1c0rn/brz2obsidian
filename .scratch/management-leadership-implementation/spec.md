# Archive-only conversion with visible images and included-scope preservation

Status: ready-for-agent
Drafted: 2026-10-06
Accepted: 2026-10-06
Decision source: [Management & Leadership Wayfinder map](../management-leadership-wayfinding/map.md)

The user confirmed the testing boundaries on 2026-10-06 with “I agree” and
requested to-tickets on this specification. Product behavior below synthesizes
the settled policy and the user's choice of layout A.
This document defines implementation requirements, not completed conversion.

The user's final actual-vault review on 2026-10-06 clarified the approved visual
treatment: generated source-gap notices use Obsidian warning callouts, with an
orange warning title/icon and tinted background, rather than ordinary blockquotes.
The absent ordinary-note title is **Source note unavailable**. Use corresponding
descriptive titles for unavailable category notes and category/inherited icons.
Keep truthful existing limitation text and resolving report/provider links.
Place notices above affected note content; category Parents/Children remain
immediately below the title, followed by notices before Members/Gallery. Separate
adjacent notices into individual callouts. This changes generated presentation,
not supplied Markdown, image order, source evidence or migration accounting.

## Problem Statement

The user has a larger desktop Backup to BRZ export containing important technique
cards, a workflow chart, Markdown, thought types and attached resources. Version
2 refuses the original archive because it contains absent note/icon declarations
with an unreviewed file state and ordinary hierarchy links to thought types.

The important images already exist in that original archive. Repeatedly opening
thoughts and retrieving small note files in TheBrain is not a feasible migration
workflow. The user needs those images visible in the corresponding Obsidian
notes, preservation of included Markdown actually supplied by the archive, and
enough diagnostic information to investigate source problems when desired.
Forgotten thoughts must disappear completely from destination output by default.

Success must distinguish supplied content from unavailable source text. A vault
with visible available images can be useful without pretending that unknown
prose, captions or layout have been recovered. Earlier converter coverage and
the user's native category/maintenance conventions must continue to work.

## Solution

Convert the unaltered BRZ directly into a new Obsidian vault. Preserve every
included physically present note through the established exact-source adaptation
path. When the reviewed ordinary-note declaration lacks bytes but valid owned
note images exist, display those original images automatically, with a brief
source-gap notice above them and a link to the Migration report. The notice is
layout A; it has no additional Available note images heading.

Create usable category dashboards despite the separately reviewed absent type
notes/icons. Keep missing type-note content unknown, use neutral appearance
where icon pixels are unavailable, and preserve hierarchy and membership as
distinct relationships. Category Parents/Children appear below the title before
Members/Gallery, with reciprocal links from ordinary notes.

Inspection and completed migration identify each affected included thought,
the missing attachment and what the converter displayed. Source investigation
is optional. Exclude forgotten items and all associated destination artifacts,
references and unsafe evidence. Retain strict refusal for unsupported or
contradictory source shapes. Prove the finished behavior through public workflow
tests, independent full-input audits, cumulative regression and actual native
output review before declaring the migration delivered.

## User Stories

1. As a knowledge owner, I want to convert my original BRZ, so that I do not need to prepare a replacement export first.
2. As a knowledge owner, I want conversion to run without live TheBrain access, so that every migration is reproducible from its input archive.
3. As a knowledge owner, I want available card images displayed inside their owning notes, so that important content is immediately readable.
4. As a knowledge owner, I want the available workflow chart displayed, so that image content is not treated as decoration.
5. As a knowledge owner, I want ownership established from source records, so that similarly named thoughts cannot receive each other's images.
6. As a knowledge owner, I want all supported owned images displayed beside an absent note, so that a future multiple-image case does not lose content.
7. As a knowledge owner, I want generated image ordering to be stable, so that repeated exports do not arbitrarily rearrange that presentation.
8. As a knowledge owner, I want generated ordering identified honestly, so that I do not mistake it for recovered authored layout.
9. As a knowledge owner, I want a brief notice above fallback images, so that I see the source limitation before reading them.
10. As a knowledge owner, I want detailed diagnostics outside the card presentation, so that the note remains useful to read.
11. As a knowledge owner, I want unknown absent prose and captions described accurately, so that a successful conversion does not promise unavailable content.
12. As a knowledge owner, I want present Markdown preserved, so that image fallback cannot replace text that the archive supplied.
13. As a knowledge owner, I want physically present blank notes respected, so that blank content is not misclassified as an export gap.
14. As a knowledge owner, I want tables, image order and newline spelling retained, so that migration does not reconstruct my note bodies unnecessarily.
15. As a knowledge owner, I want permitted internal-reference adaptations to remain exact, so that unrelated text is not rewritten.
16. As a knowledge owner, I want safe original note bytes retained, so that I can compare supplied source content with the adapted note.
17. As a knowledge owner, I want no fabricated original-note backup for an absent body, so that generated presentation never looks like source evidence.
18. As a knowledge owner, I want original image bytes and hashes preserved, so that display does not require image re-creation or recompression.
19. As a knowledge owner, I want source gaps permitted only under reviewed rules, so that an unexpected missing resource cannot silently disappear.
20. As a knowledge owner, I want invalid, ambiguous or contradictory source cases refused, so that a reassuring-looking vault does not conceal unsupported content.
21. As a knowledge owner, I want missing type notes disclosed, so that unavailable category text is not called empty.
22. As a knowledge owner, I want category dashboards created despite reviewed source gaps, so that classification remains useful.
23. As a knowledge owner, I want missing type icons to produce neutral appearance, so that broken images or invented icons do not distract me.
24. As a knowledge owner, I want full cards kept distinct from icons, so that important note content is not reduced to a substitute thumbnail.
25. As a knowledge owner, I want affected members linked to their missing icon provider, so that I can investigate the actual source of an appearance gap.
26. As a knowledge owner, I want available explicit and inherited icons preserved, so that unaffected appearance continues to work.
27. As a knowledge owner, I want every direct ordinary parent shown on a category, so that multiple-parent hierarchy survives conversion.
28. As a knowledge owner, I want category children linked from ordinary parents, so that navigation works in both directions.
29. As a knowledge owner, I want category hierarchy above Members/Gallery, so that I can understand the category's position before browsing members.
30. As a knowledge owner, I want membership separate from hierarchy, so that a parent relationship does not imply classification.
31. As a knowledge owner, I want existing native Bases and templates retained, so that category discovery and manual maintenance remain familiar.
32. As a knowledge owner, I want forgotten thoughts excluded by default for every archive, so that migration reflects how I treat them.
33. As a knowledge owner, I want their owned files, icons and source copies omitted, so that excluded content cannot reappear through attachments.
34. As a knowledge owner, I want authored references to excluded thoughts removed completely, so that no linked phrase, target or stub remains.
35. As a knowledge owner, I want unsafe original copies omitted when they contain such references, so that exact backups cannot bypass exclusion.
36. As a knowledge owner, I want associated raw records and history omitted, so that hidden migration evidence does not restore excluded content.
37. As a knowledge owner, I want no individual exclusion list or forgotten counts in destination output, so that excluded thoughts leave no identifying audit artifacts.
38. As a knowledge owner, I want unrelated included content with similar names or pixels preserved, so that exclusion does not become keyword or visual matching.
39. As a knowledge owner, I want my source archive unchanged, so that destination exclusion does not delete anything from TheBrain.
40. As a knowledge owner, I want inspection to identify source gaps before conversion, so that I can understand the expected result.
41. As a knowledge owner, I want the report to identify each affected included thought and attachment, so that optional investigation is practical.
42. As a knowledge owner, I want the archive fingerprint and Brain identity recorded, so that diagnostics refer to the right source snapshot.
43. As a knowledge owner, I want a vault-note link in each diagnostic, so that I can navigate from evidence to the visible result.
44. As a knowledge owner, I want raw state, declared length and physical absence distinguished, so that source observations are not confused with conclusions.
45. As a knowledge owner, I want optional investigation guidance without an invented source deep link, so that I can locate the thought reliably.
46. As a knowledge owner, I want source omissions reported without a confirmed vendor-bug claim, so that the report reflects established facts.
47. As a script author, I want inspect and convert results to agree on planned obligations, so that automation can interpret warnings consistently.
48. As a script author, I want generated image presentation counted separately from authored references, so that conservation figures remain meaningful.
49. As a script author, I want explicit compatible schema and profile versions, so that interface changes cannot pass as the old closed contract.
50. As a script author, I want the existing CLI arguments and outcome codes retained, so that existing invocation patterns remain usable.
51. As a knowledge owner, I want fresh-destination publication verified transactionally, so that a failure cannot leave a partial accepted vault.
52. As a knowledge owner, I want durable receipts after actual publication, so that a later failure does not conceal an existing verified output.
53. As a knowledge owner, I want unavailable measurements left unknown after failure, so that failure reports do not invent successful counts.
54. As a knowledge owner, I want PDFs, generic files and ZIP resources preserved, so that resource volume does not narrow compatibility.
55. As a knowledge owner, I want original external URLs and reviewed video timing retained, so that established resource behavior continues to work.
56. As a knowledge owner, I want source tags, Home, dates and collision-safe naming retained, so that the new features do not disrupt normal navigation.
57. As a knowledge owner, I want cycles and multiple parents handled deterministically, so that migration does not require a single-parent tree.
58. As a maintainer, I want the existing read-only vault checker retained, so that mutable convention problems can be found without rewriting notes.
59. As a maintainer, I want convention checks separate from preservation proof, so that a clean checker result cannot certify a complete migration.
60. As a developer, I want public synthetic fixtures for new cases and interactions, so that ordinary testing needs neither private archives nor GUI access.
61. As a developer, I want tests at existing public boundaries, so that internal refactoring does not invalidate behavior-oriented tests.
62. As a developer, I want a source-neutral core and alternate-source proof retained, so that BRZ numeric semantics do not enter generic planning.
63. As a knowledge owner, I want all four archives independently audited, so that this extension retains the earlier migration coverage.
64. As a knowledge owner, I want original, repeated and reordered conversions compared, so that deterministic output is proved rather than inferred.
65. As a knowledge owner, I want complete supplied-body and affected-image checks, so that a representative prototype is not mistaken for final preservation.
66. As a knowledge owner, I want an actual native Obsidian review of converter output, so that image and Base visibility is verified in the application.
67. As a knowledge owner, I want to evaluate the actual converted vault before delivery is declared, so that my final acceptance is not supplied by an agent.
68. As a knowledge owner, I want a repaired or recovered export treated as a distinct source, so that its acceptance cannot substitute for the original archive.
69. As a knowledge owner, I want private records, vaults and screenshots kept local, so that evidence gathering does not publish my knowledge collection.
70. As a developer, I want updated documentation and a specification-driven implementation frontier, so that the route to delivery remains reviewable.

## Implementation Decisions

1. **Cumulative scope.** Extend the reviewed exchange-format-5 feature profile,
   rather than introducing a fingerprint or Pip Decks allowlist. The original
   archive is an acceptance input, not the definition of support. Retain all
   delivered v2 behavior except the explicit new exclusion, reviewed absences
   and category hierarchy/placement decisions. Official state-3 meaning and the
   export-omission cause remain unknown.
2. **Architecture.** Preserve the accepted source-neutral core and inward
   Pydantic contracts. The source adapter owns BRZ roles, scope extraction,
   ownership, exact reference tracing and reviewed source findings. Generic
   analysis/planning owns consistency, materialization, names and destination
   obligations. The renderer owns notes, generated display, diagnostics and
   native support. The publisher owns verified filesystem publication. The
   workflow orchestrates injected interfaces; the CLI remains thin.
3. **Versions and interfaces.** Use package release 0.3.0; advance strict
   snapshot/policy contracts, source module/profile, renderer and serialized
   migration result/record schemas to version 3. Keep schema identities and
   established operations, outcome meanings and fields where compatible.
   Inspection and plans gain explicit source-gap and generated-presentation
   obligations; they must not overload authored Documents or ReferenceSpans.
   BRZ remains format 5. Keep the independent source-free checker schema at 1
   unless its public shape actually changes. Reject incompatible/unknown
   combinations explicitly and update the alternate-source adapter to prove
   the current contract with empty optional gap/presentation facts.
4. **Inclusion before destination planning.** Default TheBrain scope excludes
   thoughts with a valid populated ForgottenDateTime. This is independent of
   attachment file state and applies to every archive. Establish trusted source
   identities/ownership before scoping. Pass only included items, incident-safe
   relationships, assignments, assets and safe evidence into destination-facing
   facts. Do not add an include-forgotten CLI mode in this effort. Global
   container, path, identity and source-consistency safety checks still apply;
   invalid scope markers or untrustworthy ownership refuse safely.
5. **Complete exclusion.** Excluded subjects contribute no target, reserved path,
   note, owned asset, original copy, appearance snapshot, classification/tag
   membership, navigation link, stub, warning subject, individual audit identity,
   exclusion count/list, raw record or associated history. Filtering follows
   identity, ownership and proven reference association. Independently included
   items with the same name or pixels survive. Generated counts describe the
   included scope; they do not expose a raw-versus-excluded tally. Source input
   fingerprint and source collection identity remain legitimate provenance.
6. **References and safe evidence.** Remove the whole authored linked phrase or
   embed that resolves to an excluded subject, including its target and label;
   do not retain a plain-text reminder or deletion marker. Preserve all other
   source text and newline spelling. Do not use title matching to erase prose.
   Raw spans, reference labels, serialized evidence and exact-original copies
   must not reintroduce the removed material. Omit an unsafe exact source copy
   rather than modifying it and calling it exact. Retain provably included
   evidence with original values/omission/null distinctions; omit records,
   fields or whole history/evidence collections that cannot be safely scoped.
   Scope policy is documented generally, without per-thought removal artifacts.
7. **Scope interactions.** Remove both sides of relationships/assignments to an
   excluded endpoint and remove associated provider effects. An included member
   whose source classification provider is excluded is considered without that
   membership/provider and proceeds under ordinary included-item selection;
   never create a missing-category placeholder or inherit excluded pixels.
   Genuine dangling references to unknown nonexcluded identities still refuse.
   If the designated entry is outside included scope, retain the existing
   required-entry refusal; do not pick another Home automatically. Such errors
   and raw parse failures must not echo excluded identity, title or content.
8. **Present note precedence.** A physically present recognized note follows
   the normal Document path, including zero-length/blank content, BOMs, prose,
   image-only content and multiple-image/table syntax. Retain the established
   marked/canonical NoteType-0 recognition and competing-note refusal. Adapt
   only approved reference destinations plus the separately mandated scope
   removals. Do not rebuild Markdown, normalize line endings, reorder authored
   images, fix a source pipe row or insert fallback because content looks empty.
   Preserve a byte-exact original copy whenever doing so is safe under scope.
9. **Reviewed ordinary-note absence.** Admit a unique recognized absent
   Type-1/NoteType-4 canonical Notes.md declaration, SourceType 2, ordinary
   included owner, raw state 3 and no physical member, only with the valid owned
   note-image basis. Preserve normal scalar, flag, owner, path and declaration
   checks. Declared length is nonnegative evidence, not an empty-content test.
   Findings retain their precise versioned rule and evidence; generic policy
   permits only that reviewed disposition. A present-state/missing-member or
   state-3/present-member contradiction does not match the rule.
10. **Valid image basis.** Identify note images by the reviewed Type-12/NoteType-0,
    SourceType-2, IsIcon=false role and same source ownership. Required images
    must have actual state-1 archived bytes, unique safe paths, valid ZIP CRC,
    matching declared length, actual hash and usable supported image content.
    Generated-display eligibility must reject invalid/undecodable image content
    or zero dimensions; file extension alone does not prove a displayable card.
    Do not infer ownership, missing prose or importance from names, OCR, pixels,
    Position or byte-length similarity. This validation adds no blanket new
    image-processing behavior to unrelated present-body cases.
11. **Truthful absence facts.** Retain a missing note asset as absent with its
    declaration, raw-state evidence and no actual byte/hash claims. Do not
    manufacture a Document, original payload, original-note backup or authored
    reference span/count. Model source gaps and generated image presentations
    explicitly in source-neutral contracts and require consistent included
    owner, reviewed finding, absent asset and present image associations.
12. **Generated visible presentation.** Every supported available owned note
    image in the accepted absent-body case receives a real copied asset and a
    visible local image embed in its owner's created note. Order generated
    embeds by stable canonical asset identity, independently of export order;
    separate multiple images without reconstructing a guessed table/caption.
    Place the brief source-gap notice first, then the images, without variant
    C's extra heading. Notice wording states that source note text is absent
    and unknown prose/layout was not recovered, and links to detailed evidence.
    Copying to Attachments or listing a Resources link alone does not satisfy
    presentation. Suppress redundant resource listings only under existing rules.
13. **Reviewed type-note/icon absences.** Permit the evidenced type-owned
    Type-1/NoteType-4 Notes.md and Type-5/NoteType-0 icon declarations with
    SourceType 2, raw state 3 and no member, after normal role/path/ownership
    checks. Icon flags must agree with the icon role. Their findings are
    separate from ordinary image fallback; type-note omission needs no image
    substitute. Do not generalize this to tag/system notes, ordinary icons or
    arbitrary state values. Do not infer empty content from the two recovered
    whitespace controls or small declared lengths.
14. **Neutral appearance.** Retain declared missing type-icon evidence but give
    its category and inheriting members no broken image target or fabricated
    effective icon. Keep membership and appearance_category links so a later
    user edit to the dashboard's icon works through existing native Bases.
    Valid explicit member icons retain precedence. Do not promote a note card
    into an icon. Preserve other available appearance evidence under v2 rules,
    including the existing distinction between live dashboard defaults and
    static ordinary-note snapshots. Do not reintroduce generated colour fields.
15. **Hierarchy and materialization.** Add the evidenced Kind 1 / Relation 1 /
    Meaning 1 / Direction -1 normal hierarchy signature, with ordinary A as
    parent and type B as child, keeping all direct parents and reciprocal
    children. This does not generalize other ordinary-only arrow variants to
    type endpoints. Require the normal owner/identity/signature
    checks; do not admit custom links, arbitrary endpoint combinations or
    subtype inheritance. Classification still requires exact included TypeId
    and instance-link correspondence. Create all included type definitions and
    assigned members, plus the accepted absent-image owners and existing
    content/Home obligations. Retain canonical greedy selection for other empty
    ordinary items, cycle handling and intentional included uncreated targets.
16. **Category presentation.** Put relevant Parents/Children directly after a
    category's title and before Members/Gallery, using the actual full scoped
    graph rather than prototype subset wording. Preserve native v2 Base roles,
    contextual membership, Icon-before-Note columns, no Appearance display,
    category image suppression, available source content/resources and manual
    templates/provider/date conventions. Hierarchy does not populate Members.
    Unrelated Related navigation retains established semantics.
17. **Actionable diagnostics.** Inspection and completed conversion expose
    consistent structured gap entries and readable included-thought information.
    The Migration report supplies an optional repair checklist. Each entry has
    archive fingerprint/collection identity, thought title and original ID,
    vault-note target, attachment ID/role/expected owned path, raw state,
    declared length, physical absence and actual outcome. Image fallback also
    identifies the real ordered image assets used. Missing-icon entries identify
    the provider and affected included members separately, without multiplying
    or inventing missing-file declarations. Existing TXT gaps and actual icon
    length discrepancies retain their distinct evidence and notices.
    Require resolving vault-note links for the new ordinary/type-note/icon
    outcomes and other materialized subjects. Prior TXT gaps do not create a
    note solely for diagnostics: retain their existing no-note behavior and
    distinguish an assigned uncreated target from an existing owner note.
18. **Optional source investigation.** Use a verified source locator only when
    available; otherwise titles and source IDs are sufficient. Importer support
    for a brain URI does not establish a native launch link. Do not generate a
    guessed URI or expose an internal local document-server address. Guidance
    may explain how the user can inspect/retrieve/re-export and compare gaps.
    Conversion itself never mutates, repairs, retrieves from or logs into the
    source application. Describe observed absences, not a proven producer bug.
19. **Refusal boundary.** Unknown states, contradictory state/payload evidence,
    ambiguous notes, wrong-owner or ambiguous images, unavailable required image
    bytes, invalid image basis, unsupported note/icon absence roles and absent
    ordinary notes without a valid image basis refuse. Existing approved
    positive-length TXT, exactly associated zero-length TXT/PDF and present-icon
    metadata-length rules remain narrow independent predicates. Refusal never
    becomes a generated empty note or a success-like fallback.
20. **Accounting and source binding.** Bind scoped facts, findings, image
    obligations, analysis, plan, renderer and receipt to the complete input
    fingerprint, scoped snapshot digest and reviewed versioned policy. Count
    supplied Documents/authored references separately from generated embeds and
    source-gap/provider effects. Plan and record each generated presentation and
    its asset paths explicitly. Missing bytes get no preservation credit;
    original included bytes retain actual hashes/lengths. Imported notes,
    support artifacts and intentional uncreated targets retain separate existing
    accounting. No serialized exclusion ledger can bypass scope.
21. **Public behavior and publication.** Retain public inspect/convert signatures,
    dependency injection/default wiring, text/JSON modes and console/module CLI
    arguments. Outcomes remain clean/warnings/refused/failed with exits 0/2/1/1.
    Inspection is read-only and has no published-output counts or publication
    receipt; retain measured available scoped-source counts and planned obligations.
    Conversion prepares afresh and publishes only to a safe fresh destination
    after complete verification. Extend real staging, stream, manifest, path,
    source-change, race and teardown protection to every new artifact. Preserve
    durable receipts after actual publication and honest available/null counts.
22. **Source-free checker.** Keep the public read-only check_vault operation and
    thin command, with independent clean/issues/failed semantics and exits
    0/2/1. Its actual-image/reference checks must recognize generated local
    embeds without becoming a source-gap oracle or trusting current mutable
    state to a historical migration record. Required local image targets remain
    real files; missing type icons use empty valid properties. Preserve actual
    caller inventory/bytes and source/workflow independence.
23. **Determinism.** Repeated and ZIP/root-record reordered inputs preserve
    included selections, assigned paths, supplied-body adaptations, generated
    image ordering, gaps/member diagnostics and logical output. Allow only the
    already documented input fingerprint/snapshot provenance, raw evidence order
    and explicit clock/run/bookmark differences. Never let omitted subjects affect
    destination naming collisions, greedy ties or membership order.
24. **Source identity for acceptance.** The unaltered original Management &
    Leadership archive is mandatory. Retrieved note bytes and the fresh backup
    are comparison controls only. Any later repaired/recovered/re-exported
    archive has its own fingerprint and requires a new full inventory/audit;
    it cannot inherit or replace original-input acceptance. Keep original inputs
    and retained vaults outside disposable output areas.
25. **Delivery and documentation.** Update public result/schema/profile guidance,
    source coverage, preservation claims, exclusion/default behavior, diagnostic
    guidance, native category layout, checker limits and acceptance tooling.
    Use the project virtual environment and add only needed runtime/development
    dependencies. Preserve packaging hygiene and synthetic public fixtures;
    keep real records, assets, oracle outputs and screenshots local and ignored.
    The planning map ends with a specification and approved implementation
    breakdown. Complete conversion and actual-vault acceptance belong to delivery.

## Testing Decisions

1. **Primary existing seam.** Exercise default_workflow().inspect and .convert
   with actual synthetic ZIPs and temporary filesystems. Retain dependency
   injection for source substitution, deterministic run metadata and actual
   boundary failures. No new public runtime test endpoint is needed.
2. **Thin public wrappers.** Check installed console and module inspect/convert
   text/JSON commands against the same workflow facts, schema 3, warnings and
   failure phases. Exercise the existing source-free check_vault operation and
   check-vault command separately; they supplement preservation, never replace it.
3. **Good tests and prior art.** Assert externally observable files, source bytes,
   spans, strict result contracts, warnings, selected graph, identities and actual
   manifests. Extend integrated v2 workflow, exact-span/reference, source-coverage,
   classification/dashboard, alternate-source, convention-checker and publication
   suites. Use focused existing public source/core/renderer/publisher boundaries
   only when they are the highest practical contract/failure seam. Do not expose
   private helpers, mirror algorithms or build mock-only conservation tests.
4. **Complete absence predicates.** Independently author ordinary absence plus
   one/multiple valid same-owner images, type-note absence and type-icon absence
   fixtures. Test every predicate's near miss independently and in interactions:
   raw state, physical presence, role/NoteType/SourceType/flags, canonical path,
   length, identity, ownership, candidate uniqueness and image integrity. Include
   unknown state, state-3 present bytes, state-1 absent bytes, no-image basis,
   wrong-owner image, unavailable image, false extension/invalid pixels and
   ambiguous candidates. Refused conversions preserve caller files.
5. **Body preservation.** Test present blank/zero/BOM/prose/caption/table and
   multi-image bodies, Unicode, code literals, nested reference syntax and mixed
   CR/LF/CRLF. Compare independently authored expected bodies and exact originals;
   only permitted reference edits/scope removals may differ. Verify no fallback
   is activated by emptiness, length or a body that merely contains images.
6. **Truthful generated display.** Compare visible embed tokens/targets and actual
   original image bytes. Notice A must precede images; multiple images use stable
   generated order. Reject omitted/duplicate/misowned embeds, images only in
   Resources, a made-up original payload/Document/hash, false authored-reference
   credit or a fabricated recovered-layout claim, even with self-consistent counts.
7. **Forgotten scope and privacy.** Use handwritten synthetic original records
   with owned notes/images/icons/URLs, hierarchy, assignments, incoming authored
   references, dependent metadata/tombstones, embedded state-map keys and unsafe
   history. Prove no subject, target/label/stub, owned payload or identifying raw
   evidence appears in inspection JSON/text, notes, manifests, records, reports,
   guide-linked copies or failure messages. Include source-copy conflicts,
   same-title/same-pixel included controls, excluded provider and excluded Home,
   malformed scope markers and genuine unknown/dangling targets. Expected scope
   comes from raw fixture facts, never converter exclusion claims.
8. **Hierarchy and native obligations.** Test ordinary-to-category links, multiple
   direct parents, cycles and reciprocal navigation, with classification joined
   independently. Category Parents/Children precede Members/Gallery; actual
   members come from assignments. Preserve role/support exclusions, linked
   properties, safe YAML, templates, dates, explicit override/default/opt-out
   behavior, category body-image suppression and no generated colour fields.
9. **Appearance/diagnostic interactions.** Test missing type note and icon together
   and separately; real provider/member association, neutral output, valid
   explicit override and remaining card visibility. Check inspection/report/
   structured record agreement with actual declaration/state/length/path and
   used image facts. Distinguish unavailable pixels from CRC-valid present
   icon-length discrepancies and prior absent-TXT findings. All gap subjects
   and affected members must be included. New note/icon outcomes and other
   materialized owners must have resolving vault links; do not materialize
   prior TXT-gap owners solely to satisfy a diagnostic link.
10. **Architecture/version regression.** Preserve strict closed contracts,
    incompatible-version rejection, opaque non-UUID alternate-source behavior
    and inward import barriers. A source module supplies meanings; generic core
    does not parse raw numeric BRZ roles or ForgottenDateTime. New presentation
    facts must fail core consistency checks when their owner/asset/finding joins
    are inconsistent. The source-free checker remains independent of conversion.
11. **Real publication safety.** Extend actual partial stream/write/copy failures,
    staging deletion/truncation/same-length corruption, source changes, Windows
    junctions, rename/rmdir races and teardown/post-commit failures. Check owned
    cleanup and complete caller before/after inventories/hashes; never delete
    caller files or claim no publication when a verified destination exists.
12. **Independent acceptance oracle.** Extend the existing standard-library-only
    raw-source oracle and private driver. Derive included subjects, graph,
    membership, supplied bodies, image associations, absences, retained safe
    evidence and expected payloads from the exact original records independently.
    Do not use production manifests, filtered snapshots, generated counts or
    claimed dispositions as expected preservation truth. Retain the import
    boundary regression and existing corruption proofs.
13. **Adversarial oracle controls.** Falsify excluded leaks, safe-evidence omissions,
    body edits, gap predicates, missing/misowned/generated-order images, fake
    originals/reference counts, neutral/provider effects, graph/memberships and
    diagnostics. Recompute the corrupted record's counts and file receipts
    consistently before the oracle rejects it. Include changes/omissions/duplicates
    in source reordering and final fingerprint checks. A structurally valid
    receipt or clean production checker must not mask the corruption.
14. **Four-archive complete matrix.** Extend the driver's three-input interface
    to accept the exact original fourth input while retaining prior pins. Run
    original, repeated and ZIP/root-record reordered conversion for each archive:
    12 complete outputs. Prove reordered root-record multisets and physical
    payload equality independently, verify the selected code import/version and
    recheck all source fingerprints before/after operations and at completion.
    Use fresh short ignored destinations. No diagnostic subset or recovery
    backup can satisfy this matrix. Add and document the fourth-source driver
    argument, preserving prior input arguments; its help and executed example
    must identify all four required originals and the fresh output location.
15. **Original included-scope gates.** For the specified original fingerprint,
    independently require the table below and audit actual identities/joins/
    payloads rather than accepting matching totals. All 359 supplied thought-note
    bodies must be accounted through their permitted adaptations and exact safe
    copies. All 63 affected original images must be visibly embedded in their
    corresponding notes with actual bytes preserved. All 47 definitions and 330
    included assigned members must materialize under the existing category rule.
    Do not substitute the whole-source 332 assignment figure for scoped output.

    | Included measurement | Expected |
    | --- | ---: |
    | Items: ordinary / definition / tag / system | 570: 521 / 47 / 1 / 1 |
    | Relationships | 730 |
    | Normal hierarchy / related / tag / system | 376 / 13 / 1 / 10 |
    | Classification assignments | 330 |
    | Ordinary-to-type hierarchy links | 54 |
    | Attachment declarations / present local payloads / external URLs | 1,557 / 1,017 / 454 |
    | Present recognized note bodies | 359: 328 marked + 31 canonical NoteType-0 |
    | Present note images / generic files / icons | 499 / 106 / 53 |
    | Ordinary absent-note owners and visible image presentations | 63 / 63 |
    | Absent type notes / icon providers / affected included members | 2 / 8 / 45 |
    | Prior positive-length absent-TXT findings / present-icon discrepancies | 13 / 7 |

    Created-note/support/actual-file counts follow independently derived complete
    obligations, not a prototype tally or addition of overlapping populations.
    The 63 affected images comprise 62 substantive cards and one workflow chart;
    their original formats are 62 WEBP and one PNG. Each owner has one image in
    this exact source; synthetic multiple-image gates establish broader behavior.
16. **Earlier-archive regression.** Reaudit A/B/C with independently recomputed
    scoped expectations. Retain all included v1/v2 content, original bytes,
    source tags, dates, classifications, property/Base/template/checker behavior,
    exceptional notes, narrow TXT/PDF/icon warnings, reviewed video URLs/timing,
    external resources and failure guarantees. Record only changes authorized
    by default scope or category hierarchy placement; do not blindly retain old
    totals when included scope differs.
17. **Read-only checks and package validation.** Prove inspection/check-vault
    preserve complete caller inventory/bytes on success and failure. Run the
    complete final public regression suite with the project interpreter:
    `.venv\Scripts\python.exe -m pytest -q`,
    `.venv\Scripts\python.exe -m ruff check --no-cache .`,
    `.venv\Scripts\python.exe -m ruff format --check .` and
    `.venv\Scripts\python.exe -m pip check`.
    During repairs, run affected checks before the final complete gate.
    Also run package/documented-example smoke for the delivered version. The built package must
    contain only runtime distribution material; schemas and documented library/
    console/module examples must agree with actual output.
18. **Native actual-output gate.** After complete independent audit, open fresh
    review copies of real converter outputs in standard Obsidian and record the
    observed version and pristine inventories. Independently join raw subjects
    to assigned paths. Review representative original PNG/WEBP cards and workflow
    chart, notice A and repair links, supplied prose/blank/multiple-image bodies,
    multiple-parent category navigation, representative category discovery and
    membership behaviors, neutral icon providers versus intact card bodies and
    existing native maintenance conventions. Use strategic samples covering each
    distinct behavior and special case, following the repository's
    [visual sampling policy](../../docs/testing.md#visual-sampling-policy).
    Independently compare the sampled native Base views with their expected
    member sets. Record selection rationale, actual observations and sampling
    limits; equivalent cases can rely on representative native confidence.
    The complete independent audit still checks every required body/embed and
    every category/member obligation; native samples verify application rendering
    and Base evaluation.
    Recheck relevant earlier-archive actual outputs and source-free read-only edits.
    Do not treat prototype paths/screenshots as final output evidence.
19. **Actual user acceptance.** Obtain the user's verdict on a clean actual
    Management & Leadership converter-output review vault before declaring
    delivery. Keep the audited baseline separate from mutable UI copies. Repair
    any defect through the responsible public seam, rerun affected automated/
    independent checks and repeat affected native observations. Agent inspection
    or specification publication never supplies this verdict.
20. **Testing-boundary confirmation.** The user confirmed the existing
    workflow with thin CLI checks, the separate read-only checker, the independent
    raw-source four-archive driver and actual native/user review on 2026-10-06.
    The actual response was “I agree,” followed by the request to use to-tickets
    on the newly generated specification.

## Out of Scope

- Reconstructing unavailable arbitrary Markdown, prose, captions or authored
  ordering; claiming complete content of the live Brain from an incomplete BRZ.
- Mandatory source UI retrieval, automated source repair, re-export, cloud access
  or remote file downloading during conversion.
- Blanket state-3/format-5 feature support, unsupported tag/system absence roles,
  arbitrary missing-resource allowances, subtype inheritance or custom link types.
- Reformatting or fixing physically present Markdown, OCR, card recognition,
  converting full cards into icons, image re-creation or pixel transformation.
- Destination synchronization, overwrite/merge of an existing vault, source
  deletion or changes to the retained user vaults.
- New PDF text indexing, ZIP expansion, unrelated video support, community
  plugins, template-driven edits to existing imported bodies or automatic dates.
- Per-item forgotten retention, a forgotten-content inclusion mode, full raw
  evidence preservation where it conflicts with the accepted exclusion.
- Production implementation, release delivery or implementation-ticket publication
  as part of this specification session. Those follow the approved frontier.

## Further Notes

On 2026-10-06, during implementation, the user explicitly changed native visual
verification to strategic sampling and made this the default for future visual
checks in this repository. This supersedes per-category native enumeration in
the earlier implementation breakdown. Distinct behaviors and special cases still
receive explicit observations; complete automated preservation and the actual
user-verdict gate remain required. Already completed native observations remain
valid evidence and need no repetition.

The mandatory original input is `brz/Management & Leadership 2026-10-05.brz`,
320,594,486 bytes, SHA-256
`2b24c1d21b4090f3b0ed3ec0227f269b8c7a4e5b6832ada0e244a1dcfc941ced`.
The earlier whole-source inventory is context; generated evidence/counts follow
included scope. A source re-export, including the recovered comparison backup,
is a different fingerprinted input with independent acceptance obligations.

The current baseline is package 0.2.0, source/result contracts and renderer 2,
BRZ format 5 and checker schema 1. The assessment records baseline commit
`9ddba911eb53e589b53d8059141462ee3a274aea` with the then-existing workspace
changes. The accepted source-neutral ADR remains applicable. Native source
evidence used TheBrain 15.0.624.0 and prototype review used Obsidian 1.13.7;
implementation records its actually observed runtime/app versions.

The user selected **layout A** on 2026-10-06. The prototype proves representative
discussion fidelity only. Its preserved two-image source pipe row renders as
stacked images and literal pipes in Obsidian; that observation does not authorize
changing supplied Markdown or promise visual parity with TheBrain. Portable
throwaway code is on `codex/ml-vault-prototype-2026-10-05` at
`c4eefbba07c89361887a4b194a7001555e1b8995`; it is not production implementation.

Evidence and cumulative decisions:

- [Accepted conversion policy](../management-leadership-wayfinding/issues/04-conversion-policy.md#answer).
- [Representative prototype and actual layout choice](../management-leadership-wayfinding/research/vault-prototype.md).
- [Independent included-source inventory](../management-leadership-wayfinding/research/included-source-scope.md).
- [Complete archive comparison](../management-leadership-wayfinding/research/archive-differences.md).
- [Exact-input v2 assessment](../management-leadership-wayfinding/research/archive-coverage.md).
- [Archive-only image facts and limits](../management-leadership-wayfinding/research/automatic-image-fallback.md).
- [Recovered reference evidence](../management-leadership-wayfinding/research/native-source-recovery.md).
- [Cumulative delivered v2 specification](../brz-to-obsidian-v2-implementation/spec.md).
- [Source-neutral architecture decision](../../docs/adr/0001-source-neutral-core.md).
- [Domain vocabulary](../../GLOSSARY.md) and [current testing prior art](../../docs/testing.md).

Historical source-coverage/refusal and unconditional raw-evidence claims describe
delivered v2 and are explicitly changed by this specification. No new unresolved
product choice is inferred from stale research wording. Testing confirmation is
recorded; the specification is ready for implementation planning. The to-tickets
session drafts and reviews implementation slices before ticket publication.
