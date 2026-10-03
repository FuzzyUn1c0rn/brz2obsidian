# Convert a TheBrain BRZ archive into a new Obsidian vault

Status: claimed

Assignee: /root

Integration branch: `codex/brz-to-obsidian-v1`

Accepted: 2026-10-03. The user confirmed the consolidated specification, including its seams, schemas, tooling choices, and verification gates. This file publishes that accepted scope in the to-spec format. Production implementation has not begun.

## Problem Statement

The user has accumulated linked knowledge in TheBrain and wants to migrate to Obsidian for openness, transparency, and configurability. Available export paths do not provide a usable Obsidian vault that preserves the content, associated files, and hierarchical context the user needs.

The source material includes real TheBrain 15 BRZ exports. Those archives contain thought identities, relationships, note text, files, tags, metadata, and a designated Home thought. A migration that simply extracts files would lose important context. Creating a note for every empty thought would also fill the vault with unwanted empty files.

The user needs a trustworthy one-time migration into a new standard Obsidian vault: authored material must survive, empty thoughts should remain useful uncreated targets, Home must be clearly identifiable, and known source gaps must be reported honestly.

## Solution

Deliver an installable Python library with a thin CLI that inspects a BRZ archive and converts it into a fresh Obsidian vault. Preserve thought-note content, every present archived payload, hierarchical context, useful connections, tag memberships, original identities, and original evidence. Expose simple Markdown relationships and resources while relying on native Obsidian Backlinks, Graph, tags, search, and navigation.

Create content-bearing notes, materialize the designated Home at the vault root, and add only the parent notes needed to cover otherwise unrepresented hierarchy connections. Leave other empty thoughts as distinct readable uncreated targets that the user can materialize later through Obsidian. Keep ordinary source metadata and simplified relationship details in a separate migration record.

Inspect provides an optional read-only preflight; convert repeats validation automatically and publishes only verified complete output. Preserve all present bytes, allow only the narrowly agreed source-gap warnings, and stop with actionable diagnostics for unsupported meanings, corrupt data, or missing required content.

Initial coverage is the verified feature classes in the two supplied TheBrain 15 exchange-format-5 archives and controlled synthetic fixtures. The source-neutral architecture permits a future compatible source module to reuse the same migration core, renderer, and publisher. The initial runtime target is native Windows with Python 3.14, verified during implementation on the installed Python 3.14.8. Native presentation acceptance uses the observed Obsidian 1.13.7.

## User Stories

1. As a TheBrain user, I want to migrate a BRZ archive into a new Obsidian vault, so that I can continue using my knowledge in open, configurable files.
2. As a TheBrain user, I want to convert my archive locally, so that my private thoughts and attachments remain on my computer.
3. As a Windows user, I want to install and run a Python CLI on the available native interpreter, so that I can migrate without requiring WSL or application automation.
4. As a TheBrain user, I want to inspect an archive before converting it, so that I can see expected notes, preserved resources, warnings, and unsupported features.
5. As a TheBrain user, I want to have conversion validate the archive automatically, so that I do not need to perform a separate inspection first.
6. As a TheBrain user, I want to see concise terminal summaries and actionable diagnostics, so that I can understand the outcome and resolve source problems.
7. As an automation caller, I want to receive one versioned JSON result, so that I can process outcomes without parsing mixed terminal text.
8. As an automation caller, I want to receive distinct clean, warning, and unsuccessful exit codes, so that I can handle successful migrations with known source gaps correctly.
9. As a vault owner, I want to allow conversion only into an absent or empty destination, so that my existing notes are protected from merging or replacement.
10. As a vault owner, I want to have a complete vault validated before publication, so that a failed preparation does not leave a finished-looking migration.
11. As a vault owner, I want to have failed staging cleaned up with any leftover path reported, so that I can recover without losing unrelated files.
12. As a TheBrain user, I want to preserve the text of every supported thought note, so that my authored content survives migration.
13. As a TheBrain user, I want to retain the original bytes of thought notes as separate backups, so that I can inspect the source independently of adapted vault notes.
14. As a TheBrain user, I want to retain every exported JSON record and field, so that metadata and history remain available for traceability.
15. As a TheBrain user, I want to retain source dates without adding a timezone interpretation, so that the migration does not invent information.
16. As a TheBrain user, I want to preserve every present archived payload byte-for-byte, so that my files remain intact.
17. As an Obsidian user, I want to keep existing inline images inline, so that the migrated notes remain readable.
18. As an Obsidian user, I want to find additional files in ordinary Resources links, so that I can open preserved material without special migration features.
19. As an Obsidian user, I want to retain external URLs and directory references as links, so that I can access their original destinations later.
20. As a TheBrain user, I want to retain decorative icon bytes without filling Resources with them, so that source material survives while everyday notes stay simple.
21. As an Obsidian user, I want to leave ordinary empty thoughts as uncreated targets, so that the vault does not fill up with empty files.
22. As an Obsidian user, I want to have distinct readable targets for every source thought, so that an empty thought can still be linked without confusing it with another thought.
23. As an Obsidian user, I want to materialize an uncreated target by clicking its native link, so that I can add content when I need it.
24. As a TheBrain user, I want to create a parent note when neither hierarchy endpoint has a note, so that every accepted hierarchy connection has readable context.
25. As a TheBrain user, I want to preserve multiple parents and cycles as graph relationships, so that the migration does not force my knowledge into a single-parent folder tree.
26. As an Obsidian user, I want to see short Parents, Children, and Related sections with empty sections omitted, so that I can navigate the retained relationships easily.
27. As a TheBrain user, I want to retain jump connections as Related links, so that useful connections survive without unnecessary arrow mechanisms.
28. As an Obsidian user, I want to avoid duplicate displayed links while retaining original relationship evidence, so that the notes remain concise without losing traceability.
29. As an Obsidian user, I want to use native Backlinks, Graph, tags, search, and navigation, so that the vault fits ordinary Obsidian behavior.
30. As a TheBrain user, I want to convert source tag memberships into native vault tags, so that I can filter and discover migrated notes.
31. As a TheBrain user, I want to preserve authored tag content in a normal note, so that a source tag's text is not discarded.
32. As a TheBrain user, I want to retain otherwise unrepresented tag memberships in a focused listing, so that assignments on uncreated thoughts remain available.
33. As an Obsidian user, I want to avoid creating notes solely for labels, colors, dates, or icons, so that supporting metadata does not create unnecessary files.
34. As a TheBrain user, I want to show a thought's short label below its original heading, so that useful authored context remains visible.
35. As a TheBrain user, I want to retain other source metadata in a separate migration record, so that everyday notes remain simple.
36. As an Obsidian user, I want to locate the Home note at the vault root, so that I can identify the source's entry point among many notes.
37. As a TheBrain user, I want to have the designated Home materialized even when empty, so that the migration always preserves a concrete starting point.
38. As an Obsidian user, I want to open Home through startup behavior and a native bookmark, so that the original entry point is easy to reach.
39. As a TheBrain user, I want to receive clear instructions when Home is missing or invalid, so that I can set it in TheBrain and re-export.
40. As an Obsidian user, I want to use Home as the entry note and the migration report for migration guidance, so that the vault has no competing permanent start guide.
41. As a TheBrain user, I want to retain isolated empty thoughts in a conditional listing, so that their identities do not disappear merely because they lack content.
42. As a TheBrain user, I want to retain Related pairs with no endpoint files in a conditional listing, so that those connections survive without forcing empty notes.
43. As an Obsidian user, I want to receive safe readable filenames, so that notes work on Windows and through native internal links.
44. As a TheBrain user, I want to receive stable identity suffixes only when names collide, so that similarly titled thoughts remain distinguishable.
45. As a TheBrain user, I want to retain exact original titles and labels alongside filename adaptations, so that readability changes remain traceable.
46. As an automation caller, I want to receive the same logical vault from equivalent source/configuration, so that record or ZIP ordering does not change migration choices.
47. As an Obsidian user, I want to have resources grouped by their owning source item, so that preserved files stay organized and uniquely addressable.
48. As a TheBrain user, I want to adapt supported source-local note and image references, so that links reach the assigned vault targets.
49. As a TheBrain user, I want to preserve code examples, literal link-like text, and nonadapted Markdown, so that conversion does not rewrite unrelated authored content.
50. As a TheBrain user, I want to continue with explicit warnings for the verified absent TXT pattern, so that known gaps do not block the agreed simpler Brains.
51. As an Obsidian user, I want to see a brief absent-file notice on an existing owner note, so that I know about the gap without receiving a fake file or link.
52. As a TheBrain user, I want to preserve actual icon bytes and report their metadata length discrepancy, so that the migration remains useful and honest.
53. As a TheBrain user, I want to stop when required notes, ordinary files, or inline images are missing, so that essential losses are not silently accepted.
54. As a TheBrain user, I want to stop with an explanation for unverified meanings or source features, so that a migration does not silently flatten information it cannot represent.
55. As a TheBrain user, I want to reject corrupt, malformed, or ambiguous source data, so that the vault is based on trustworthy identities and content.
56. As a TheBrain user, I want to understand the verified source-format boundary, so that I know when another Brain requires investigation.
57. As a TheBrain user, I want to treat forgotten live thoughts separately from deleted history, so that live knowledge is eligible without resurrecting deleted objects.
58. As a TheBrain user, I want to independently compare the complete output with both real archives, so that acceptance establishes preservation beyond summary counts.
59. As an Obsidian user, I want to review actual converter output in fresh test vaults, so that native navigation and resource rendering are verified without touching my normal vault.
60. As a library caller, I want to invoke the conversion workflow without the CLI, so that I can reuse the functionality in another application.
61. As an application developer, I want to replace the command-line interface with another entry interface, so that presentation remains separate from conversion behavior.
62. As an application developer, I want to swap the source module for another compatible format, so that the existing core, renderer, and publisher remain reusable.
63. As a maintainer, I want to keep dependencies pointing inward toward source-neutral contracts and pure core logic, so that outer input/output changes do not couple the core to an archive reader.
64. As a library caller, I want to use strict immutable Pydantic contracts, so that invalid or mutable facts do not silently alter a migration.
65. As a maintainer, I want to test through public module interfaces, so that tests verify reusable behavior rather than private helper implementations.
66. As a library caller, I want to stream binary assets through a scoped source session, so that conversion does not require loading all files into memory.
67. As a library caller, I want to detect changed sources and mismatched source bindings before publication, so that output does not combine a stale plan with different payloads.
68. As a maintainer, I want to prove source substitution using a second test-only source with non-UUID identities, so that hidden TheBrain assumptions cannot pass as generic architecture.
69. As a TheBrain user, I want to receive installation, usage, warning, and testing documentation, so that I can run and assess the converter confidently.
70. As a maintainer, I want to keep private archive fixtures out of normal tests and public reports, so that ordinary development remains shareable.
71. As an automation caller, I want to receive versioned mappings, structured issues, and unavailable counts represented honestly, so that downstream tools can rely on a stable result contract.
72. As a library caller, I want to receive durable results that state whether publication actually occurred, so that session closure or later failures do not misrepresent completed output.
73. As a contributor, I want to install all required Python packages inside a project virtual environment and add them only as needed, so that project dependencies remain isolated and reproducible.

## Implementation Decisions

1. **Operation and publication contract**

    The public inspection command is brz2obsidian inspect SOURCE.brz with optional --json; conversion is brz2obsidian convert SOURCE.brz DESTINATION with optional --json.

    Inspect is optional read-only preflight. Convert repeats source validation/analysis/planning automatically; an earlier inspection never authorizes trusting changed input. Process one source into one destination per operation. No merge, overwrite, Home override, user allowlist, or debug-retention option is included.

    Allow an absent or empty destination. Refuse a nonempty destination without altering its contents. Generate in owned staging on the destination filesystem, validate fully, then publish. Failed generation/validation must not expose a supposedly completed vault. Clean only converter-owned staging; report any leftover path if cleanup fails.

    | Outcome | Exit code | Meaning |
    | --- | ---: | --- |
    | clean | 0 | Inspection succeeded, or the vault was published, without warnings |
    | warnings | 2 | Inspection succeeded, or the vault was published, with explicit warnings |
    | refused | 1 | Input/destination/feature contract prevents proceeding |
    | failed | 1 | An operational failure prevents completion |

    Text mode prints a concise summary and actionable issues. JSON mode writes one versioned JSON result to stdout, without mixed progress text. Reusable modules neither print nor parse arguments nor call sys.exit. The CLI alone chooses presentation and exit codes. A failure result contains available diagnostics/counts, with unavailable counts represented as null rather than zero; it contains no invented publication receipt.

    Inspect reports planned outcomes and explicitly leaves destination-dependent path/publication checks pending. Convert reports actual verified output. No external URL/directory content is fetched or opened.

2. **Verified TheBrain source interpretation**

    The source module owns format interpretation. Open ZIPs read-only; validate member identity, duplicate/ambiguous entries, CRCs, and declared format. Reject malformed/ambiguous records or unsafe member resolution. Compute SHA-256 of the actual source and present payloads. Declared DataLength does not replace actual byte inventory.

    The known root files are meta.json, thoughts.json, links.json, attachments.json, settings.json, modificationlogs.json, brainusers.json, syncpoints.json, tombstones.json, calendarevents.json, access.json, fielddefinitions.json, and fieldinstances.json. Decode UTF-8 with an optional BOM; meta is one object, other collections are objects per nonempty line. Empty collections are valid. Retain every original record/field, including omission versus null and naive timestamp strings. Reject duplicate object keys/nonstandard nonfinite JSON rather than silently losing values. Preserve source order in original evidence even though planning is order-independent.

    Validate live identities, ownership and references. Historical references may be nonlive; tombstones do not resurrect items. Duplicate live identities and live/deleted overlap are unreliable source data. Live forgotten thoughts use ordinary eligibility rules. Additional uninterpreted metadata is retained; an unknown content/relationship feature must produce an unsupported finding.

    Thought roles observed: ordinary Kind 1, tag Kind 4, retained system Kind 5, with ACType 0 and no populated thought/link type IDs or TagIds membership arrays. Source tags are established by verified Meaning 5 relationships. Nonempty events/access/custom-field collections, custom types, HTML notes, cross-Brain references, other ownership kinds, and unverified semantic role flags stop initial conversion. Merely preserving their raw fields does not establish semantic support.

    The initial reviewed relationship signatures use Kind 1:

    | Source meaning | Relation / Meaning / Direction | Canonical interpretation |
    | --- | --- | --- |
    | Ordinary hierarchy | 1 / 1 / -1, 1, or 7 | A parent, B child; ordinary endpoints |
    | Ordinary parent to tag child | 1 / 1 / -1 | A parent, B tag child |
    | Ordinary jump | 3 / 1 / -1, 3, 5, or 7 | Related; ordinary endpoints |
    | Tag assignment | 1 / 5 / -1 | A source tag classifies ordinary B |
    | System connection | 1 / 6 / -1 | A system item to ordinary/tag B; retained only |

    Do not infer hierarchy from Direction. Preserve every original relationship field, including names/arrow/one-way flags. Source values/combinations outside verified coverage are unsupported; Relation 2/4 and Direction 0 are not silently admitted from documentation alone. See [controlled relationship evidence](../brz-to-obsidian/research/extended-relationship-fixture.md).

    Thought-owned attachments use SourceType 2:

    | Type / note role | Resolution and output |
    | --- | --- |
    | 1, NoteType 4 | Thought Markdown at owner/Location; decode content and preserve original bytes |
    | 1, NoteType 0, empty Notes.md | Empty note placeholder; original bytes preserved |
    | 1, NoteType 0, ordinary file | owner/Location; Resources link and byte-preserving copy |
    | 3, NoteType 0 | External URL reference; Resources link |
    | 5, NoteType 0, icon | owner/.data/Location; preserve bytes without Resources clutter |
    | 8, NoteType 0 | External directory reference; Resources link |
    | 12, NoteType 0, Markdown image | owner/.data/md-images/Location; preserve and adapt inline references |
    | 15, NoteType 0, known absent TXT | Exact warning predicate below; preserve original metadata |

    Present local payload states are 1. Match every physical resource to its metadata; unaccounted payloads or other absence/state/role patterns require investigation. Generic files are preserved regardless of native preview support. Classify actual thought notes by verified role, not extension alone. A nonempty ambiguous Notes.md placeholder is unsupported.

    The source module recognizes two exact anomaly rules and supplies evidence; the approved profile permits core warning disposition:

    - Absent unclassified TXT: thought-owned Type 15, NoteType 0, .txt location, positive declared length, state 2, absent owner/location bytes, with an intact archived PDF under that same owner. Do not assert derived purpose, optionality, or a particular TXT/PDF pairing.
    - Icon length discrepancy: verified icon role with present CRC-valid bytes, but declared length differs from actual length. Copy actual bytes and retain both lengths.

    Unmatched missing ordinary files, thought Markdown, or inline images fail. Unknown finding rules and unsupported meanings fail. There is no general permission to ignore missing bytes.

    Home recognition belongs in the TheBrain module: find settings.Id = UUIDv5(UUID(meta.BrainId), name="20"), interpret its Value as the designated thought identity, and retain the evidence. Core requires a valid live entry under the initial profile. Missing/invalid Home refuses conversion with instructions to set Home in TheBrain and re-export. Do not guess from activation, title, or topology. See [Home evidence](../brz-to-obsidian/research/home-thought.md).

3. **Vault representation and deterministic planning**

    The vault root contains the Home note, MIGRATION REPORT.md, migration-record.json, and conditional Tag memberships.md / Uncreated targets.md. Other thought notes go under Notes; files go under Attachments grouped by a short owner token; tested native settings accompany the vault.

    The prototype START HERE guide is not a production page. Migration instructions and links to conditional listings belong in MIGRATION REPORT. Home is the entry note.

    Create a note for a live ordinary/tag item with nonblank thought-note text, a substantive archived non-note file/image, or a supported external resource reference. Empty placeholders, decorative icons, labels/colors/dates alone do not qualify. Always create the designated Home at root, even empty; preserve its original heading/label/body/relationships.

    After content and Home selection, cover accepted hierarchy edges as follows:

    1. An edge is covered when at least one endpoint has a note.
    2. Candidate selections are parents of currently uncovered edges.
    3. Select the candidate covering the most currently uncovered incident hierarchy edges, including edges where that candidate is the child.
    4. Recompute after each selection; ties use canonical source-key ordering. For BRZ this preserves the agreed source-ID ordering.
    5. Stop when every hierarchy edge is covered. Do not claim global optimality.

    All selected notes receive all applicable relationships after selection. Empty A→B→C selects B alone. Multiple parents/cycles are graph cases, not nested folders or recursive creation.

    Reserve remaining nonsystem items as distinct uncreated targets. Every created endpoint lists its Parents, Children, and Related targets; omit empty sections. Deduplicate repeated displayed targets while retaining all underlying source relationships/mappings. Arrows/one-way visibility are intentionally simplified. The source system item/relationships remain in the migration record without invented navigation meaning.

    Use native tags on created assigned items, preserving source memberships. Flat tokens normalize whitespace/slashes/punctuation to hyphens, prefix numeric-only tokens with tag-, use source-tag for an empty token, and resolve case-insensitive collisions with stable identity suffixes. A source tag's authored content becomes a normal note; do not invent self-membership. Generate Tag memberships when needed for assignments on uncreated targets or otherwise unrepresented/unused tags; keep that listing focused on those gaps rather than reproducing native tag search.

    Generate Uncreated targets only for isolated empty ordinary items without another readable reference, or Related pairs whose endpoint files are both absent. Preserve those pairs as readable links; do not force extra files solely for them. Source labels appear below the original heading on created notes; other metadata remains in the record.

    Existing inline images stay inline. Additional files/external references appear as ordinary Resources links. An absent-TXT warning gets a brief source-filename notice in an existing owner's Resources section and details in the report; it does not create a note or a fake file/link. Icon discrepancies appear in report/record only.

    Native Backlinks, Graph, Tags/search, and navigation supply discovery. Later click-to-create makes an ordinary Obsidian note; the converter does not automatically populate its reciprocal sections.

4. **Naming and source-content adaptation**

    Reserve created and uncreated targets together. Require unique thought basenames across Notes/root and reserve supporting names. Home keeps its Home — marker. Source identities are opaque keys; source modules supply stable lowercase hex naming seeds. BRZ uses dashless source UUIDs, preserving existing identity-based suffixes and per-owner attachment folder naming.

    Normalize readable names to Unicode NFC; collapse whitespace; replace colon with ` - `, square brackets with parentheses, Windows-unsafe characters and unsafe link punctuation (`< > " / \\ | ? * # ^ %`) plus control characters with spaces; trim trailing dots/spaces. Prefix Windows device names, including reserved stems with extensions, with Note -; use Untitled when empty. Compare normalized names case-insensitively.

    Every member of a colliding thought group gets ` — <seed-prefix>`, initially eight hex characters, extending four at a time when needed. Supporting names remain fixed; conflicting source targets receive suffixes. Resolve natural suffix-like names and truncation collisions deterministically, reserving all identities before writing. Resource-name collisions use attachment naming seeds; owner folders use unique short owner seeds. No suffix allocation may depend on ZIP/record order.

    Final stems are bounded to 120 UTF-16 units without splitting characters or losing Home/identity markers. Truncate the readable portion before suffixes. Validate final absolute paths against the conservative 240-unit policy, explaining when a shorter destination is needed. Source originals and every adaptation remain traceable. Preserve resource extensions and the non-note `.md.original` ending for thought-note backups. Identity-preserving link forms, including names containing dots, must resolve to exactly the assigned file in acceptance tests.

    Created notes have an escaped original-title H1, optional source label, original thought Markdown with only approved reference edits, Resources, then relationship sections. Generated tag frontmatter precedes content when needed. Escaping is serialization, not a new source title. Prefer original display text; use a readable adapted display label when it would break link syntax, retaining the original.

    The source module parses actual supported local references and emits spans. For BRZ, recognize the observed inline `[label](brain://<compact-id>/<informational suffix>)` and `![alt](.data/md-images/<location>)` forms. Compact GUID decoding uses .NET bytes_le URL-safe base64. Referenced identities must be live; a valid empty target is intentional. Unsupported cross-Brain/local syntax is an actionable refusal. External references remain unchanged; no fetch occurs. Code examples, fenced/inline code, and literal link-like text are not treated as live references.

    Define spans as zero-based half-open Unicode code-point offsets in the exact decoded text. Preserve CRLF/CR/LF spelling and all text outside approved spans. Each span includes its expected original substring, kind, canonical target, display text, and document digest; verify bounds/nonoverlap/binding. The renderer applies spans rather than regenerating the entire Markdown document.

    Initial parser choice: markdown-it-py base parser, with explicit source-span instrumentation/provenance mapping. Token.map only gives line indexes; inline parser positions refer to transformed inline input. Therefore, build normalization/block-to-inline offset mapping and verify it early. Do not mistake parser tokens for automatic exact source positions. Reference-style/HTML local references not in current support must be reported, not missed silently or converted by regex guesswork. Source-specific rich/legacy transformations remain outside first support.

5. **Reusable deep modules and inward dependency direction**

    All module interfaces are reusable and are the test seams. Contracts define data plus invariants, failure behavior, ordering and resource lifetime. Core contains pure analysis/planning; outer modules own source interpretation, rendering, I/O and composition. Pydantic is an explicitly accepted pure-library dependency of inward models.

    Packages expose cohesive interfaces with few operations; internal files are implementation detail. The contracts implementation can split internally if needed while remaining inward-owned. No dynamic exporter registry/framework is needed. Root/package initializers must not eagerly load TheBrain/CLI when importing generic modules.

    | Interface | Contract |
    | --- | --- |
    | SourceModule.open(source_ref) → context-managed SourceSession | Read/interpret source, expose durable snapshot and payload access; preserve originals; emit unmapped findings rather than invented semantics |
    | core.analyze(snapshot, policy) → Analysis | Check canonical consistency, entry/references/accounting and finding disposition; refuse invalid data before planning |
    | core.plan(analysis) → MigrationPlan | Determine selections/targets/resources/representations/adaptations; no I/O |
    | obsidian.render(plan, run_metadata) → RenderedVault | Generate exact note/report/record/config bytes and copy manifest; no filesystem or source parsing |
    | publication.publish(artifacts, payloads, destination) → Receipt | Destination/path checks, streamed copies, staged verification, publication and owned cleanup; no naming or migration policy |
    | Workflow.inspect(source_ref) → RunResult | Shared read/analyze/plan path; durable planned summary; no destination mutation |
    | Workflow.convert(source_ref, destination) → RunResult | Fresh preparation, rendering/publication, session closure, durable actual receipt |
    | cli.main(argv) → int | Argument parsing, default wiring, presentation, exit-code translation |

    An outer SourceModuleBinding combines the source opener and reviewed profile. It is ordinary composition, not a Pydantic model holding resource objects. Wiring chooses BrzSourceModule by default; the generic workflow receives the binding rather than importing TheBrain. Reader/renderer/publisher depend only on inward contracts, not each other's concrete implementations. The generic Workflow receives source, rendering, and publication interfaces; the outer wiring module is the composition point allowed to select concrete implementations. The CLI or another entry interface selects/configures a workflow. An advanced caller can invoke individual modules.

    Define the source/session, rendering, and publication interfaces as small typing.Protocol contracts with inward models for their arguments/results. A SourceSession exposes snapshot, context-managed open_payload(asset_id), and verify_consistency(); its payload access supplies the same SourceIdentity as its snapshot. Source references remain outer input values and do not reach core. SourceIdentity is durable provenance/fingerprint data, distinct from the outer SourceModuleBinding.

    Public operations below Workflow return their declared model on success and raise MigrationRefused or MigrationFailed with structured immutable issues on a known refusal or operational failure. Workflow translates these into RunResult; warnings accompany successful Analysis/Plan/results. Source decoding translates Pydantic validation failures into source issues at its boundary. Unsupported features are refusals, not generic crashes. Unexpected programming errors are not disguised as successful results. Report a receipt only when publication was verified; if an error occurs after commit, retain the actual receipt and explicitly report that publication occurred rather than falsely claiming no output exists. Session teardown/publication error precedence must retain all material diagnostics and truthful completion state.

    Use Pydantic v2 strict, closed, frozen normalized models, with immutable nested collections. A frozen model containing a mutable list/dict is not immutable. Decode source explicitly into Python facts, then validate strict models; do not silently coerce source values. Original JSON/text evidence is independently retained in immutable form, not reconstructed from normalized model dumps. Source dates remain raw strings. Payload streams/sessions are ordinary outer resources, not Pydantic models containing file objects.

6. **Inward models, JSON schemas, and failure contracts**

    These are accepted operation-focused field requirements, not a requirement for a class per helper. Use version 1 for shared contracts, migration record, and CLI result. Python contract names may use snake_case; JSON field naming is consistently snake_case.

    | Contract | Required information |
    | --- | --- |
    | SourceIdentity | Source identity, module/format versions, source SHA-256, normalized snapshot digest |
    | SourceSnapshot | Contract version, SourceIdentity, collection title, optional entry key, immutable items/relationships/documents/assets/original evidence/findings/accounting |
    | Item | Opaque key, original identity, stable hex naming seed, title/label, canonical role/live status, document/resource references and evidence pointers |
    | Relationship | Key, canonical kind, explicit endpoints/parent-child orientation, evidence pointers; document links remain separate |
    | Document | Owner/key, supported Markdown text, text digest, original-byte asset ID, validated reference spans/evidence |
    | Asset | Opaque ID, owner, original name, role/availability, actual length/hash when present, source evidence |
    | OriginalEvidence | All original records/fields or source text/binary descriptors, ordered provenance, raw source values distinct from normalized facts |
    | SourceFinding | Kind, opaque versioned recognition-rule ID, affected identities/assets, observed facts and evidence; no authority to ignore losses |
    | SourceAccounting | Every exported item's/evidence identity and its normalized, retained-only, or unresolved disposition with corresponding references |
    | SourcePolicy | Profile/version, compatible module/format/contract, entry requirement, explicit permitted finding rules/kinds/dispositions |
    | Analysis | Bound checked facts, resolved entry/references, classified issues, complete declared accounting and logical counts |
    | MigrationPlan | Binding/profile/version, created/uncreated targets/reasons, resource assignments, hierarchy/tag/fallback presentation, approved edits, copy obligations, adaptations, issues/counts |
    | RenderedVault | Binding/renderer version, generated bytes/digests, copy entries with expected asset lengths/hashes, complete relative-path manifest, publication constraints |
    | Issue | Stable code, severity, phase, readable message, affected identities/evidence, rule, actionable guidance and optional leftover path |
    | Receipt | Published destination, binding, verified manifest/counts and completion facts; durable values only |
    | RunMetadata | Explicit converter/renderer versions, run identifier/time, tested Obsidian version and supplied bookmark creation time; no hidden clock reads in pure modules |
    | RunResult | Versioned operation/outcome envelope, available source/profile identity and counts, issues, planned inspection summary/pending checks, optional verified Receipt |

    Represent missing entry honestly as null in SourceSnapshot; the initial BRZ and compatible test profiles require it. A format without a source entry needs a later explicit entry policy, not automatic guessing.

    Approved profiles are reviewed fixed configuration supplied through composition. BRZ recognizes the exact missing-TXT/icon predicates in its source module; core interprets evidence-backed findings under the profile. Unknown rules/profile mismatches refuse. No raw TheBrain numeric predicates/rule constants belong in generic core. Adapter comparisons prove that declared source accounting includes everything; the generic core cannot independently audit a foreign parser's omissions.

    CLI-result v1 top-level fields: schema=`brz2obsidian.result`, schema_version=1, converter_version, operation (`inspect` or `convert`), outcome (`clean`, `warnings`, `refused`, or `failed`), source_identity, profile_id, profile_version, counts, issues, inspection, receipt. Nullable fields stay explicit null when unavailable; issues is always an array. Counts distinguish planned and actual values, using null for an unmeasured value. Inspection is null for conversion; a receipt is null before verified publication. JSON round-trips through the result model; error results use the same envelope.

    Migration-record v1 top-level fields: schema=`brz2obsidian.migration`, schema_version=1, converter_version, renderer_version, source_identity, profile_id, profile_version, run_metadata, original_evidence, item_targets, asset_targets, relationships, tag_memberships, adaptations, source_accounting, issues, counts, obsidian_configuration. Item targets include original identity/title, assigned relative target, whether created, and creation reasons; asset targets include availability, assigned copy/link, original name and expected length/hash. Relationship/tag entries connect original evidence to canonical endpoints and destination representations. Every original BRZ record remains an original JSON value with all fields; serialization must use retained original evidence, not typed normalization. Preserve omitted/null distinctions and number values. Original note bytes use copy artifacts, not active note duplicates.

    Initial stable issue codes are unsupported_format, unsupported_feature, invalid_source, invalid_reference, invalid_entry, missing_required_payload, approved_source_gap, approved_metadata_discrepancy, source_changed, destination_not_empty, unsafe_target_path, target_path_too_long, payload_integrity_failure, write_failure, publication_failure, cleanup_failure, and internal_failure. Each Issue records severity (`warning` or `error`), phase, message, affected identities/evidence, optional recognition rule, actionable guidance and optional leftover path. Approved source gaps/discrepancies are warnings only under the reviewed policy; the other codes cannot be downgraded by the caller. Precise source findings distinguish cases within these codes. Test codes through interfaces. Approved intentional simplifications and ordinary name adaptations are recorded as adaptations, not extra warnings.

7. **Source lifetime and transactional publication**

    Keep the source session open while preparing and streaming copies. Core/renderer receive durable facts, not streams or ZIP paths. The session offers scoped open_payload(asset_id) and source/binding consistency verification. Using a session after closure fails explicitly. Plans/artifacts bind to both source fingerprint and normalized snapshot digest; publishing with another session fails even if asset IDs match.

    Verify source consistency and copied lengths/hashes before commit. Source mutation, truncation or I/O failure prevents publication and triggers owned cleanup. Large binary assets are streamed, not all loaded into memory or obligatorily duplicated into an extra source snapshot. The workflow owns session lifetime and returns durable results only.

    The publisher validates path uniqueness/containment and destination feasibility, creates its own staging, writes generated artifacts/copies, checks every expected file and byte digest, and publishes only after the complete manifest passes. Recheck destination state at commit; never replace caller-owned content. No unexpected file or missing required artifact can be silently published. Cleanup resolves and checks owned paths before recursive operations, particularly on Windows. Return leftover diagnostics if cleanup fails. Independent source/output acceptance remains separate from this production manifest check.

8. **Native Obsidian preferences and link serialization**

    Generate only the tested preferences: showInlineTitle false, defaultViewMode preview, newFileLocation folder, newFileFolderPath Notes, useMarkdownLinks false, newLinkFormat absolute, openBehavior `file:<assigned root Home filename>`. Generate a native file bookmark titled Home using that same path. Run metadata supplies bookmark creation time explicitly. Other preferences belong to the user; no community plugin/configuration is installed.

    Generate qualified Wikilinks for notes/uncreated targets and safe display labels; inline image paths are encoded relative Markdown paths from each actual note location. Root Home and Notes locations therefore use different relative image paths. File Resources links point to the one assigned attachment; external destinations remain references. Tested startup/bookmark serialization is version-specific evidence, not a cross-version Obsidian configuration guarantee. See [vault trial](../brz-to-obsidian/research/vault-trial.md).

9. **Runtime and development tooling**

    Provision a minimal project Python virtual environment before implementation. Install all runtime, build, and development packages only inside that environment, adding them gradually when a slice needs them. Bootstrap with the available native Python; an initially empty requirements manifest is valid. Future package metadata declares dependency requirements, while the requirements manifest records the resolved compatibility-checked development environment. Keep the environment and generated tooling artifacts outside Git.

    Use a normal pyproject package with src layout, setuptools.build_meta, a brz2obsidian console entry point, and `python -m brz2obsidian`. Use standard-library ZIP/JSON/UUID/hash/path/streaming facilities; no application automation is required at runtime.

    Accepted initial dependency families and verified releases on 2026-10-03:

    | Purpose | Dependency / initial resolved candidate |
    | --- | --- |
    | Inward models | Pydantic 2.x / 2.13.5 |
    | Source Markdown parsing | markdown-it-py 4.2.x / 4.2.0, base parser only |
    | Behavioral tests | pytest 9.x / 9.1.1 |
    | Formatting/lint | Ruff 0.16.x / 0.16.10 |
    | Packaging | setuptools 84.x / 84.0.0 |

    Declare Python >=3.14 for the first package target; record that tested support is Windows/Python 3.14 rather than asserting all later runtimes. Pin the resolved development/build/runtime environment after the native dependency gate and record versions in diagnostics. Do not add a second package manager requirement. Development commands after implementation use the project interpreter: `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`, `.\.venv\Scripts\python.exe -m pytest`, `.\.venv\Scripts\python.exe -m ruff check .`, and `.\.venv\Scripts\python.exe -m ruff format --check .`.

    Pydantic, pytest, Ruff and setuptools have documented/metadata Python 3.14 evidence; markdown-it-py's version metadata/CI does not establish explicit 3.14 support. Test the chosen versions on the actual native interpreter before building the converter. Exact source-span tracing is also an early gate. If a dependency fails, repair or replace its private implementation while preserving the agreed interface/behavior; report a material design change before widening scope.

    Primary tooling evidence: [Pydantic package](https://pypi.org/project/pydantic/), [strict validation](https://docs.pydantic.dev/latest/concepts/strict_mode/), [model configuration/immutability](https://docs.pydantic.dev/latest/concepts/models/), [markdown-it-py package](https://pypi.org/project/markdown-it-py/), [token map](https://github.com/executablebooks/markdown-it-py/blob/v4.2.0/markdown_it/token.py), [normalization](https://github.com/executablebooks/markdown-it-py/blob/v4.2.0/markdown_it/rules_core/normalize.py), [pytest](https://pypi.org/project/pytest/), [Ruff](https://pypi.org/project/ruff/), [setuptools configuration](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html).

## Testing Decisions

1. **Test external behavior at the highest practical seam.** The reusable Workflow inspect/convert interface is the main seam for complete operation behavior. Focused tests also exercise the public source, analysis/planning, rendering, publication, and CLI interfaces because the user requires every module to be independently reusable. These seams and responsibilities were explicitly accepted during architecture grilling and reconfirmed with the final specification; no new seam interview is needed. Tests assert observable outcomes, emitted artifacts, preserved content, and failure behavior, rather than private helper calls or implementation structure.
2. **Use the existing research and accepted prototype as prior evidence.** The repository currently contains domain/agent documentation, local decision tickets, archive inspection scripts, research reports, and disposable prototype evidence. There is no production converter or established automated test suite to extend. The source inventories, controlled relationship/Home exports, independent parent-selection checks, and accepted native vault trial supply expected behavior, not production acceptance.
3. **Separate shareable automated tests from private full-source acceptance.** Ordinary tests use synthetic archives and temporary directories and require neither private inputs nor GUI access. Select the exact real acceptance inputs explicitly for independent preservation checks. Private titles, identities, content, and generated vaults remain local; public reports contain aggregate or synthetic evidence.

### Full-source preservation and expected baselines

The real acceptance fingerprints are fixed in [the preservation report](../brz-to-obsidian/research/brz-preservation.md). A fresh read-only Python 3.14 check on 2026-10-03 reconfirmed both fingerprints and the agreed greedy selections. The following are expected full-conversion results, not claims that production conversion has already passed:

| Measure | A | B |
| --- | ---: | ---: |
| Live ordinary / tag / system items | 63 / 12 / 1 | 58 / 0 / 0 |
| Total live items | 76 | 58 |
| Content-bearing ordinary items | 43 | 40 |
| Additional hierarchy-only notes | 5 | 2 |
| Additional notes solely for Home | 0 | 0 |
| Ordinary / tag thought notes | 48 / 1 | 42 / 0 |
| Total thought notes, including root Home | 49 | 42 |
| Uncreated ordinary / tag targets | 15 / 11 | 16 / 0 |
| Present payloads preserved once | 60 | 50 |
| Original-note backups within those payloads | 43 | 34 |
| Hierarchy edges, including ordinary-to-tag | 67 | 56 |
| Related / tag-assignment / system edges | 4 / 47 / 11 | 1 / 0 / 0 |
| Total source relationships | 129 | 57 |
| Missing-TXT / icon warning items | 0 / 2 | 9 / 0 |
| Expected conversion exit | 2 | 2 |

Each has one root Home already content-eligible. B's nine absent TXT records span seven owners; no PDF is missing. Reports/conditional listings are excluded from thought-note counts. Raw metadata/history/system retention and intentional simplifications do not generate additional warning items.

Independent real-source checks must compare every present payload and original-note backup byte-for-byte, all exported JSON records/fields semantically, every source identity and assigned target, every accepted relationship/tag representation, and every actual local reference. Check original Markdown outside approved edits, complete item/resource accounting, and exact warning predicates/counts. Counts alone and the publisher's self-check do not establish preservation. Local comparisons produce aggregate public reports; private titles/IDs/content remain under ignored brz.

| Seam / acceptance case | Required observation |
| --- | --- |
| Reader | Both verified record layouts; BOM/empty records; malformed/duplicate keys/IDs; corruption; unsupported format/feature; all original fields/payloads accounted |
| Source-note parsing | Actual local refs adapted; code examples/literals untouched; repeated links, escaped delimiters, CRLF, lists/quotes and nesting retain exact nonadapted text; unsupported local forms refuse |
| Core analysis | Live versus forgotten/deleted, Home validity, ordinary-to-tag hierarchy, exact known gaps/profile compatibility, invalid identities/references and unknown findings refuse |
| Core planning | Empty Home, empty A→B→C, cycles/multiple parents, isolated/Related/tag absent cases, order invariance, duplicates/sanitization/reserved/long names, truncated/short-ID collisions |
| Renderer | Original heading/label/text; resources/images; simple omitted-empty sections; root Home links; flat native tags; original evidence and tested config; no invented edges/membership |
| Publisher | Real temp folders/streams, nonempty destination unchanged, complete manifest, source binding/mutation, partial stream/write failure, late destination appearance, cleanup failure, no early publication |
| Workflow | Shared inspect/convert preparation, durable results, session ownership/closure, no trusted stale preflight, source exceptions and actual receipt |
| CLI | Installed command/module entry, argument errors, text/JSON isolation, exact 0/2/1 mapping, structured failure shape |
| Architecture | Core/contracts have no outer imports; generic workflow has no BRZ/CLI import; modules work independently through public interfaces |
| Alternate test source | Non-UUID keys reach core; no BrainId/settings/enums required; same logical fixture produces corresponding vault paths/content/relationships/tags/assets with source-specific evidence faithfully different |

Use checked-in programmatic synthetic archives, not unsanitized copies of user exports. Reader/publisher/workflow tests exercise real local I/O; pure core/renderer tests use input values and expected outcomes. Fault injection crosses genuine interfaces and must not replace all real-file evidence. Ordinary automated tests require no private archive or GUI. Private full-export acceptance is explicitly selected by exact inputs and must run before first-version acceptance.

After automatic checks, open each actual generated real vault in fresh test copies for standard Obsidian review. Check root Home/startup/bookmark, hierarchy/uncreated click-to-create/backlinks, native tag discovery, and selected PNG/WebP/PDF/resource links. Do not use the user's normal vault. Preserve pre-click outputs for comparison; UI creation changes files intentionally. Full byte/content checks plus representative rendering establish the agreed first-version evidence; no claim about every note/PDF page or untested app versions is made. The earlier accepted prototype is baseline evidence, not a replacement for testing converter output.

Reproducibility compares assigned relative names, creation selections, note content, resource bytes, relationship/tag presentation and logical mappings for the same source/configuration. Equivalent ZIP/record reordering must preserve these decisions. Original evidence order, changed source fingerprint, explicit run timestamps/absolute destination details and source-specific provenance are documented exceptions; do not demand identical whole-record bytes across different sources/runs.

## Out of Scope

- Synchronization, incremental conversion into an edited vault, merging, force overwrite, or replacing existing user content.
- Universal compatibility across TheBrain versions or every exchange-format-5 export.
- Investigation or support of substantially larger Brains, unverified source features, other absent-payload patterns, or the unknown purpose/pairing of the TXT records before the agreed initial version is accepted.
- A second real note-taking source format in the first version; only a test-only alternate source is required to prove substitution.
- Source formats or rich-content meanings that cannot fit the reviewed shared contract without further modeling and acceptance.
- Guessing a missing entry from titles, activation, or graph topology; a CLI Home override; arbitrary user warning allowlists.
- Recreating TheBrain navigation, arrow/one-way visibility, or single-parent folder nesting.
- Community-plugin dependencies or replacements for native Backlinks, Graph, tags, search, or navigation.
- Fetching external resources, maintaining links after migration, or automatically populating reciprocal sections on later user-created notes.
- A dynamic plugin/exporter registry, another required package manager, or a WSL runtime requirement.
- Debug staging-retention options, full duplicate BRZ snapshots, reviewing every PDF page/note in the GUI, or unsupported cross-platform/app-version guarantees.

## Further Notes

### Accepted decisions and supporting artifacts

This specification consolidates [Choose note identity, relationships, and vault layout](../brz-to-obsidian/issues/03-vault-model.md), [Validate the proposed vault in Obsidian](../brz-to-obsidian/issues/04-vault-trial.md), [Choose the conversion and failure contract](../brz-to-obsidian/issues/05-conversion-contract.md), and [Agree acceptance checks and the implementation specification](../brz-to-obsidian/issues/06-implementation-specification.md). Follow the accepted [source-neutral core architecture decision](../../docs/adr/0001-source-neutral-core.md) and [domain vocabulary](../../GLOSSARY.md).

The [initial folder-layout proposal](architecture-layout.md) retains the concrete source/test layout requested by the user. Its file placement is an initial implementation guide; the module interfaces, dependency direction, and preservation rules above are the stable decisions. Keeping that layout separate avoids tying this specification's implementation decisions to provisional code paths.

The [BRZ preservation report](../brz-to-obsidian/research/brz-preservation.md) identifies the exact A/B acceptance inputs by size and SHA-256. [Controlled relationship evidence](../brz-to-obsidian/research/extended-relationship-fixture.md), [Home evidence](../brz-to-obsidian/research/home-thought.md), [uncreated-target evidence](../brz-to-obsidian/research/uncreated-targets.md), [parent-materialization evidence](../brz-to-obsidian/research/parent-materialization.md), and [native vault trial](../brz-to-obsidian/research/vault-trial.md) supply the measured basis for the accepted behavior.

Dependency metadata and primary documentation were checked on 2026-10-03. The selected candidate releases have not been installed or exercised as a production package in the native project environment. Native compatibility and exact Markdown span tracing are deliberate early implementation gates. The two real exports are acceptance cases, not a fingerprint allowlist.

### Implementation sequence and completion

1. Establish package/interfaces/models and native dependency checks; enforce inward imports. Prove exact reference-span tracing before relying on it.
2. Build one small synthetic end-to-end inspect/convert operation with transactional output and structured results.
3. Complete verified source mappings, deterministic planning/rendering, source retention and warning/refusal/failure handling through seam tests.
4. Prove alternative test-source substitution and logical reproducibility; run independent full-source acceptance on exact A/B inputs.
5. Review freshly generated real vaults in standard Obsidian, then complete installation/library/CLI/testing documentation and recorded versions.

Each stage has observable gates. First-version acceptance requires all applicable automated, private-source and native-review checks; no production result is declared merely because a prototype or partial slice works. Usage documentation explains fresh-vault use, expected warnings, uncreated-target behavior, source scope and optional JSON results. Architecture documentation records interfaces/dependency direction; Testing documentation records public/private acceptance commands and native-review procedure.

The completed Wayfinder map and decision tickets remain in the separate planning area. This accepted specification now defines the first-version implementation in its own tracker area. The [implementation tickets](README.md) record the approved vertical slices and their dependencies. Completion of wayfinding does not mean the converter or its acceptance checks have been completed.
