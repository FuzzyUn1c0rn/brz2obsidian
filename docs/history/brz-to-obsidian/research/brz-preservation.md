# BRZ preservation evidence

Investigated 2026-10-03 for [Determine what the BRZ export can preserve](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/51). This is evidence for later conversion decisions, not a converter specification. **Observed** means measured in the two supplied archives; **documented** means first-party descriptions; **inference** is identified explicitly. Private content, identifiers, and external destinations are excluded.

## Reproducible inputs and method

| Input | Logical repository path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| A: smaller, richer graph | `brz/D&D_ The Rise of Anzoras 2026-10-03.brz` | 45,016,149 | `84405276897f27f188a9f33453aac94cfdac6a4dfaaeecf8f0bd5a46454b7be4` |
| B: larger, more files | `brz/Dungeons & Dragons 2026-10-03.brz` | 153,693,431 | `20b6085239b82ba7c4a6951d07a53243c3d7ddd00fcd3d6b91115cd7170c26b0` |

The [inspection script](inspect_brz.py) uses Python's standard library, opens ZIPs read-only, parses every root record, checks all live graph references and attachment metadata, reads note files in memory, and validates ZIP CRCs. It neither extracts nor uploads resources. Run from the repository root, supplying these two archive paths in A/B order:

Both inspections and an independent repeat used the installed Windows Python 3.14.8. The script's Python 3.11+ declaration is its minimum runtime requirement, not the version used for this investigation.

```powershell
.\.venv\Scripts\python.exe .scratch/brz-to-obsidian/research/inspect_brz.py 'brz/D&D_ The Rise of Anzoras 2026-10-03.brz' 'brz/Dungeons & Dragons 2026-10-03.brz'
```

Full aggregate results and schema keys are in [archive-inventory.json](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/7#issuecomment-6040213212). Note syntax scans are regex probes, not a complete Markdown parser. The script is an investigation aid for this format, not a hardened validator for arbitrary inputs.

## Container and record format

**Observed:** Both declare `ExchangeFormatVersion: 5`. A has 73 ZIP members, including 60 resources; B has 63, including 50 resources. Every member uses DEFLATE. CRC checks pass; there are no duplicate paths, traversal/absolute paths, symlinks, or encrypted members. Uncompressed totals are 45,922,444 and 164,001,091 bytes.

Both have the same 13 root files. All begin with a UTF-8 BOM. `meta.json` contains one object with `BrainId`, `ExchangeFormatVersion`, and `AttachmentFileStates`. Other files contain one JSON object per nonempty line, with zero-record files consisting only of the BOM. They are not JSON arrays. **Documented:** TheBrain intentionally uses per-line objects for progressive processing. ([Export to JSON](https://bra.in/2vGPYa))

| Root collection | A records | B records |
| --- | ---: | ---: |
| thoughts | 76 | 58 |
| links | 129 | 57 |
| attachments | 66 | 63 |
| settings | 27 | 25 |
| modificationlogs | 1,163 | 464 |
| brainusers | 1 | 1 |
| syncpoints | 186 | 77 |
| tombstones | 63 | 60 |
| calendarevents, access, fielddefinitions, fieldinstances | 0 each | 0 each |

Every collection has unique `Id` values within that collection and a matching `BrainId`. IDs checked by the script are canonical UUID strings; settings IDs are also UUIDs. Recorded datetime strings have no timezone suffix. Preserve their original values; assigning UTC would add an unsupported interpretation. The archive does not declare the producing application version, so format version 5 does not verify a particular TheBrain release or note dialect.

Subsequent user clarification on 2026-10-03 identifies the application as TheBrain 15. This supplies application-version context independently of the observed exchange format; the exact build and note-dialect setting remain unrecorded.

## Thoughts and graph integrity

**Observed:** A contains 63 thoughts of `Kind=1`, 12 of `Kind=4`, and one of `Kind=5`; B contains 58 of `Kind=1`. `ACType=0` throughout. No thought or relationship has `TypeId`; neither archive contains thought types or relationship types. Both retain creation/modification dates, names, icon information, and optional activation/forgotten/sync dates. A additionally has two labels and two foreground colors. A has seven forgotten thoughts and B two; these remain live objects with relationships/content, not tombstones. No alias fields occur.

**Documented:** The export reference identifies thought kinds 1/2/4 as normal/type/tag and access 0/1 as public/private. The current API additionally documents kinds 3/5 as event/system. This corroborates the single `Kind=5` thought as a system object, while the archive-specific role of that object remains unspecified. ([Export to JSON](https://bra.in/2vGPYa), [API createThought documentation](https://api.bra.in/index.html), [OpenAPI source](https://api.bra.in/v1/docs.json))

**Observed:** All 372 endpoint references across both archives resolve to live thoughts. There are no self-links or duplicate ordered endpoint pairs. A has one isolated thought and components of 75 and 1 when all relationship meanings are included; B is a single component of 58. Under ordinary child relationships, A has seven thoughts with multiple incoming parents, up to three each; B has none. Neither ordinary child subgraph contains a cycle. A also has one ordinary relationship between a normal thought and a tag. These archives cannot be represented faithfully by an assumed single-parent tree.

All `TagIds` arrays are empty, including on tagged thoughts. A nevertheless has 47 `Meaning=5` relationships whose A endpoints are tags and B endpoints normal thoughts. **Observed conclusion:** `TagIds` alone would lose every tag assignment in this acceptance case; relationships supply the assignments.

B has one repeated exact title. Windows-invalid filename characters occur in three A titles and twelve B titles. Identity must therefore survive independently of a title-derived path; this finding does not select a naming scheme.

## Relationship meaning and direction

**Documented:** Export enums distinguish `Relation` (child=1, parent=2, jump=3, sibling=4), `Kind` (normal=1, type=2), and `Meaning` (normal=1, instance-of=2, type-of=3, event=4, tag=5, system=6, subtag=7). Tag assignment runs from tag A to item B; type assignment runs from type A to instance B. Direction uses bits 1/2/4 for directed/backward/one-way, respectively. These fields express separate dimensions. ([Export to JSON](https://bra.in/2vGPYa), [staff enum explanation](https://forums.thebrain.com/post/in-links-json-what-are-these-fields-10616870))

| Observed signature `(Kind, Relation, Meaning, Direction)` | A | B |
| --- | ---: | ---: |
| `(1,1,1,-1)` | 66 | 56 |
| `(1,1,1,7)` | 1 | 0 |
| `(1,3,1,-1)` | 2 | 1 |
| `(1,3,1,5)` | 2 | 0 |
| `(1,1,5,-1)` | 47 | 0 |
| `(1,1,6,-1)` | 11 | 0 |

A has three named relationships, all explicitly directed. Flag decoding documents `5` as one-way A→B and `7` as one-way B→A. Hierarchical placement and arrow direction cannot safely be collapsed: the reversed arrow still has `Relation=1`. All other links carry `Direction=-1`; this sentinel is **not defined by the first-party sources inspected**, and must not be decoded as an ordinary bitmask. A third-party reply calls it bidirectional, which is insufficient evidence to adopt that label.

**Initially an inference, subsequently verified:** `Relation=1` stores parent A / child B in the observed ordinary hierarchy records. The consulted official export reference did not explicitly pin the stored A/B orientation, so the script's incoming-parent counts initially relied on an inference. The later [controlled export and UI comparison](relationship-fixture-records.md) confirms this orientation and shows `Direction=-1` for default no-arrow hierarchy/jump presentation, plus `Direction=1` for an explicit A→B arrow without the one-way bit. Custom link-type inheritance remains unexercised; keep the sentinel separate from bitmask decoding.

**Additional controlled observation:** The [extended fixture](extended-relationship-fixture.md) confirms jump directions 3 (B→A arrow), 5 (A→B with One Way), and 7 (B→A with One Way). The explicit One Way control affects normal Plex neighbor visibility; immediate previous-thought context can temporarily retain a hidden neighbor. These observations corroborate the direction flags without selecting a vault representation.

All eleven system relationships in A start at the system thought; six end at normal thoughts and five at tags. This establishes their topology, not their user-facing purpose or whether they belong in vault navigation. Positional values also exist (`PositionAToB` nonzero on eleven links); no general interpretation of these settings was established.

## Attachments and payload resolution

**Observed:** Every attachment has `SourceType=2` and a `SourceId` resolving to a live thought. Neither input exercises link-owned or Brain-owned attachments. All physical resources have live thought owners and can be matched to attachment metadata.

Verified member resolution uses `SourceId`, attachment type, and `Location`:

| Type | Documented meaning | Verified member path | A | B |
| --- | --- | --- | ---: | ---: |
| 1 | internal file | `<SourceId>/<Location>` | 45 | 43 |
| 3 | external URL | reference only | 6 | 3 |
| 5 | icon | `<SourceId>/.data/<Location>` | 13 | 4 |
| 8 | external directory | reference only | 0 | 1 |
| 12 | Markdown image | `<SourceId>/.data/md-images/<Location>` | 2 | 3 |
| 15 | unresolved name | no matching payload found | 0 | 9 |

Type labels through 12 are documented by TheBrain staff. Current API `AttachmentType` admits value 15 but does not name it. ([staff attachment enum explanation](https://forums.thebrain.com/post/in-links-json-what-are-these-fields-10616870), [OpenAPI source](https://api.bra.in/v1/docs.json))

A's 60 local resources are 43 Markdown and 17 PNG files. B's 50 are 34 Markdown, nine PDFs, four PNGs, and three WebP images. Every type 1/5/12 record resolves; every archived member belongs to such a record. Actual bytes equal `DataLength` except for two A icons, whose metadata lengths are nonzero and differ from the ZIP payload sizes. Thus metadata lengths cannot replace actual payload sizes or independently prove corruption when CRCs pass.

**Missing payloads:** B's nine type 15 records have `.txt` locations, positive `DataLength`, and `AttachmentFileStates=2`. Each shares a thought owner with an archived PDF. All other local records have state 1 and a payload. **Inference:** type 15 may be derived searchable text from PDF processing, and state 2 may describe its absent/export-excluded data. Neither interpretation is established; record nine absent payloads, without claiming nine missing PDFs. The PDFs themselves are complete.

**External references:** Nine URLs and B's one absolute Windows directory reference are explicitly external types. Their destination content is not part of this archive. This is distinct from a local attachment whose metadata advertises a payload that cannot be found. No external destinations were opened or fetched, and the linked directory was not inspected.

## Notes and embedded references

**Observed:** A has 40 attachments classified `Type=1, NoteType=4`, plus three `Notes.md` files with `NoteType=0`; those three are empty. All 43 physical note files are BOM-prefixed UTF-8; 40 are nonempty. B has 33 classified Markdown notes plus one empty `NoteType=0` `Notes.md`; 31 of its 34 physical notes are nonempty. A filename alone would include additional empty placeholders; `NoteType` supplies classification.

**Documented:** TheBrain 11+ notes are internal files with Markdown note type 4; older unedited notes can remain HTML attachments. ([staff note clarification](https://forums.thebrain.com/post/brainzips-technical-information-10059702)) Since 15.0.610, new Brains use standard Markdown; existing Brains can retain the deprecated dialect until changed in content settings. Updating TheBrain and re-exporting does not demonstrate dialect conversion. ([current Markdown reference](https://www.thebrain.com/docs/markdown-info))

The supplied notes exercise headings, ordinary text/list/emphasis syntax, links, and images. Regex probes find no fenced code, pipe tables, checklist syntax, footnote definitions, YAML frontmatter, wiki links, or `tb:` comments. One A note contains an HTML-like tag. This limited feature set is compatible with common Markdown syntax, but is not proof of a global standard-dialect flag or of fidelity for legacy styled notes.

There are 66 A and nine B embedded local thought links, all shaped `brain://<short-thought-id>/<readable-text>`. Each resolves to a live thought. **Documented:** Both server and Brain ID may be omitted inside the same Brain, and the readable suffix is informational. Short GUIDs use URL-safe base64 of .NET GUID bytes; Python must use `uuid.UUID(...).bytes_le`, not `bytes`. ([brain:// Links](https://bra.in/7p6nXP))

All two A and three B relative image references resolve to the archived `.data/md-images` resources. A also has five HTTPS links in note bodies. No unresolved embedded local target was found. Scans cover the observed inline link/image forms; reference-style Markdown, HTML attributes, and links inside other attachment formats are not claimed as verified.

## History, limits, and follow-up evidence

**Documented:** Tombstones mark deletions for synchronization and may be ignored for other uses. ([Export to JSON](https://bra.in/2vGPYa)) **Observed:** No tombstone ID overlaps a live thought/link/attachment ID. Tombstone type counts are A `{2:15,3:24,4:24}`, B `{2:25,3:29,4:6}`. History records frequently reference nonlive objects (588 A, 174 B), so treating historical references as live graph-integrity failures would be misleading. Forgotten thoughts remain live. Settings, account records and sync history exist; the report does not decode settings or expose account data.

Evidence supports **these two format-5 exports with their observed features**, not all format-5 archives or all TheBrain versions. Unexercised features include types and subtype hierarchies, typed links, events, nonempty custom fields/access lists, HTML notes, internal directories, linked external files, link-owned content, and cross-Brain embedded links. Empty collection files prove layout, not semantic support.

The [accepted first-version specification](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/10) sets the implementation boundary. The unresolved investigations below are future coverage work, not prerequisites for the initial version; unknown TXT purpose and additional styling fidelity are explicitly deferred.

Historical and future controlled-fixture evidence requests:

1. **Completed for the initial scope:** [Verify hierarchy and default direction with a controlled export](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/57) confirms parent A / child B and the observed default sentinel using a separate TheBrain 15 export. [Verify reverse arrows and one-way relationship behavior](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/58) additionally confirms jump directions 3/5/7 and one-way Plex visibility. Creation via adding a parent and custom link-type inheritance remain unexercised and are additional evidence cases only if required by the chosen coverage.
2. Attach one simple PDF with a unique text token; export before/after indexing, inspect type 15 payload presence and state values, and obtain the vendor's type/state names if available. This distinguishes primary content from derived search text and missing versus deliberately excluded data.
3. If styling beyond the observed note subset enters initial scope, export one existing Brain note before/after switching content settings, with underline, color, table, callout and line breaks. Compare Markdown and rendered output. No claim of general legacy-style fidelity is justified by these inputs.

The API docs were read publicly without credentials. Their OpenAPI 1.0.5 source SHA-256 was `1c002b52b42d30b8c00dbbd7696a60d8144e75fc43ca5a62949452324c541342`. Knowledgebase pages were read through their public JS client; both were marked “v14 Legacy”, modified 2026-05-29. Those limitations explain why API corroboration and explicit unknowns remain necessary.
