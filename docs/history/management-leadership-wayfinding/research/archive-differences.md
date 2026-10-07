# Complete four-archive comparison against v2

Assessed 2026-10-05 against `thebrain-format5-reviewed`, version `2`.
**The complete comparison finds the same two blocker classes as the initial
assessment: 74 state-3 absent note/icon payloads and 54 ordinary-to-type hierarchy
links. It finds no additional observed feature requiring new semantics.** This
does not certify the missing notes' unseen content or a successful complete
migration. [Aggregate evidence](aggregate-archive-differences.json),
[initial assessment](archive-coverage.md),
[reviewed v2 coverage](../../../source-coverage.md).

## Exact inputs and evidence reuse

| Input | Original filename | SHA-256 |
| --- | --- | --- |
| A | `D&D_ The Rise of Anzoras 2026-10-03.brz` | `84405276897f27f188a9f33453aac94cfdac6a4dfaaeecf8f0bd5a46454b7be4` |
| B | `Dungeons & Dragons 2026-10-03.brz` | `20b6085239b82ba7c4a6951d07a53243c3d7ddd00fcd3d6b91115cd7170c26b0` |
| C | `Software Engineering 2026-10-04.brz` | `7c533a30439e281b1d51d6617c9f1f3cad9c2c1d67e5a1e056f280bf37709764` |
| D | `Management & Leadership 2026-10-05.brz` | `2b24c1d21b4090f3b0ed3ec0227f269b8c7a4e5b6832ada0e244a1dcfc941ced` |

All four exact fingerprints match the earlier inventories and remain unchanged
after this scan. Whole-archive CRC evidence is reused only for those exact
identities: [A/B/C inventory](../../brz-to-obsidian-v2/research/aggregate-feature-inventory.json)
and [D assessment](archive-coverage.md).
All root records, present thought-note bytes, complete-record identity/reference
joins and per-record v2 compatibility probes were rescanned. No diagnostic
conversion was repeated. A/B/C complete independent preservation acceptance
remains the [delivered baseline](../../brz-to-obsidian-v2-implementation/research/three-archive-preservation.md).
D's earlier incomplete-subset pass is reused only for preservation of its
present bytes and reviewed remaining features.

| Collection/measure | A | B | C | D |
| --- | ---: | ---: | ---: | ---: |
| Compressed bytes | 45,016,149 | 153,693,431 | 62,008,262 | 320,594,486 |
| ZIP members / physical payloads | 73 / 60 | 63 / 50 | 245 / 232 | 1,037 / 1,024 |
| `meta.json` | 1 | 1 | 1 | 1 |
| `thoughts.json` | 76 | 58 | 372 | 586 |
| `links.json` | 129 | 57 | 693 | 753 |
| `attachments.json` | 66 | 63 | 254 | 1,568 |
| `settings.json` | 27 | 25 | 32 | 32 |
| `modificationlogs.json` | 1,163 | 464 | 2,675 | 6,607 |
| `brainusers.json` | 1 | 1 | 1 | 1 |
| `syncpoints.json` | 186 | 77 | 143 | 664 |
| `tombstones.json` | 63 | 60 | 439 | 667 |
| Each of `calendarevents`, `access`, `fielddefinitions`, `fieldinstances` | 0 | 0 | 0 | 0 |
| Type assignments | 0 | 0 | 195 | 332 |
| Present canonical Markdown candidates | 43 | 34 | 122 | 359 |
| Absent declarations | 0 | 9 | 4 | 87 |
| Approved warning predicates | 2 | 9 | 4 | 20 |

All thirteen known root files occur, with UTF-8 BOM and LF framing; no additional
root file occurs. Strict decoding succeeds. There are no duplicate record IDs,
foreign Brain ownership, live/deleted overlap, dangling live endpoints, missing
attachment owners, unmatched file-state IDs, ambiguous physical assignments or
unaccounted payloads. Home is a live ordinary thought in all four. Every D
TypeId matches exactly one type-to-member instance link, including multiplicity;
none is inferred from a hierarchy edge. History's nonlive references remain
evidence, not resurrected objects. Sources: aggregate `collections`, `joins`,
`identity`, `graph`; [reader/decoder](../../../../src/brz2obsidian/sources/thebrain/reader.py),
[classification join](../../../../src/brz2obsidian/sources/thebrain/classifications.py).

## Classification of every observed feature and structural delta

The aggregate `differences.collections` enumerates every field-key, exact
record-key-schema, shape, scalar, omission and null delta against the A/B/C
union. D introduces **no root field**, no novel null shape and no novel array
membership shape. Seventeen new optional-field combinations are enumerated
(12 thought, two attachment, two history, one tombstone schemas); their fields
are individually known. Shape matching alone does not establish semantics.

| Feature/delta in D | Classification against delivered v2 |
| --- | --- |
| 537 ordinary, 47 type, one tag, one system thought; ACType 0 | Supported roles. Types and tags coexist here; membership, tag assignment and system links retain distinct meanings. |
| 343 ordinary hierarchy, 13 ordinary jumps, 332 instance links, one tag assignment, ten system links | Supported exact signatures. The only novel relationship signature is the separate 54-link ordinary-to-type hierarchy below. |
| Three ordinary items in a hierarchy cycle; 38 items with multiple parents, maximum eight; six title collisions | Novel real-export cycle observation, supported graph/naming variation. Include it in full-archive regression; it needs no new destination policy. Cycles/multiple parents are accepted in the existing planner. |
| 54 `(1,1,1,-1,1,2)` links | Unsupported endpoint meaning in the adapter; source/native direction and destination hierarchy presentation remain prerequisites. Tuple order is Kind, Relation, Meaning, Direction, A role, B role. |
| 74 unknown-state entries, all absent: 66 Type-1/NoteType-4 notes and eight Type-5 icons | Blocker, not an approved TXT warning. The same 74 records fail both global state and required-payload gates; these are not 148 separate gaps. Native recovery/availability evidence and policy remain open. |
| New ownership signatures: two type-owned marked notes, one type-owned NoteType-0 file, one tag-owned icon | Type-owned marked notes are a supported content role whose bytes are absent here. The NoteType-0 candidate is an empty BOM-only canonical placeholder, already supported on this owner role. The present tag-owned icon uses the existing single-owned-icon rule. No ownership policy expansion is indicated. |
| 328 present marked notes and 31 present canonical NoteType-0 candidates | Supported. Two NoteType-0 candidates are substantive, ordinary-owned and sole candidates; 29 are decoded empty, including one type-owned placeholder. No competing note declarations occur. |
| 359 present Markdown candidates, 329 substantive; 436 bound image references and one bound thought reference | All parse and bind within reviewed active syntax. BOM bytes are preserved; no CRLF, bare CR or NUL occurs here. Lists, emphasis, blockquotes, headings, images and bare `br` are known syntax. Pipe-text probes find matches, but yield no new parser token or local-reference form; regex matches do not establish a new table feature. |
| 500 Markdown images, 112 generic files, 53 present icons | Supported byte-preserved roles. Generic files are 97 PNG, eight PDF and seven ZIP; ZIP is the only novel payload extension and requires no expansion/unpacking. Image presence does not recover absent authored note bytes. |
| 457 HTTP(S) references; one populated reviewed YouTube preview | Supported. Plain HTTP is a novel observed URI shape here, already allowed by v2. The video passes the current exact provider/URL/metadata predicate; other references receive no inferred video role. Remote bytes are not fetched. |
| 13 positive-length state-2 absent TXT records, each with intact same-owner PDF | Approved `absent-txt/v1` warning. No new zero-length rule is needed. This rule says nothing about the absent note/icon roles. |
| Seven present icon declared/actual length mismatches | Approved `icon-length/v1` warning; no other present-payload length discrepancy occurs. Existing CRC/byte preservation evidence applies to actual bytes. |
| All 47 type labels, 46 type foreground colours; 18 new signed colour values; no background field in D | Supported metadata/appearance ranges. Members have no direct label/colour/icon override here. `ThoughtIconInfo` has no novel token shape and remains opaque. Eight absent type icons affect appearance availability and belong to the state-3 decision. |
| New omission combinations for `DisplayModificationDateTime`, `SyncSentId`; no `SyncSentId` on Brain-user/syncpoint records; no link `Name` | Retained metadata variation. Created/updated date validators pass; display/history/sync fields are not date fallbacks or graph meanings. Omission is preserved separately from null. |
| New attachment Position scalars -5/-7/-8/-9/-10; 698 novel DataLength scalars | Volume/order metadata, not new roles. Exact numbers survive in original evidence. Length/payload gates are evaluated separately as above. |
| New modification codes 206/502/503; new HTTP shape in history NewValue; 1,891 nonlive history-source references | Opaque history evidence. No inference about deletion, recovery or content semantics is justified by these codes. |
| New UUIDv5 numeric settings names 42/44 with string-boolean values; 58/101 absent relative to C | Opaque settings evidence. Only the existing name-20 Home meaning is interpreted. A setting's apparent boolean shape is not a new product rule. |
| Empty events/access/custom fields; no Meaning-3 links, populated custom link type, TagIds entries or type-on-type TypeId | Negative evidence for these exact inputs. Their absence keeps the current unsupported boundary closed; it does not prove absence from the producer's capabilities. |

Sources: aggregate `archives.D` and `differences`;
[attachment rules](../../../../src/brz2obsidian/sources/thebrain/attachments.py),
[note tracer/binder](../../../../src/brz2obsidian/sources/thebrain/notes.py),
[metadata](../../../../src/brz2obsidian/sources/thebrain/metadata.py),
[videos](../../../../src/brz2obsidian/sources/thebrain/videos.py),
[semantic guards](../../../../src/brz2obsidian/sources/thebrain/semantics.py),
[core graph analysis](../../../../src/brz2obsidian/core/analysis.py),
[accepted v2 specification](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/11).
Per-record guards produce no failures on A/B/C. D produces exactly 54
relationship failures and the same 74 records at both attachment-state gates;
all calendar/appearance/classification/semantic/video/note-bind probes pass.
This avoids the public CLI's first-error-only limitation without relaxing its
gates or treating compatibility probes as an independent preservation oracle.

## What the hierarchy means, and what native observation must settle

The freshly read first-party export-field explanation identifies Relation 1 as
Child, Meaning 1 as Normal, Meaning 2 as type-A-to-ordinary-B InstanceOf and
Meaning 3 as supertype-A-to-type-B TypeOf. It separately defines visual arrow
and one-way flags. That supports distinguishing D's normal hierarchy from
instance assignment or subtype inheritance; it supplies no new interpretation
of the `Direction=-1` sentinel. It is staff export documentation, not a complete
current-build format-5 specification. [Harlan's export-field explanation](https://forums.thebrain.com/post/in-links-json-what-are-these-fields-10616870).

D's 54 links connect seven untyped ordinary A endpoints to 46 type B endpoints;
some types have multiple ordinary parents. The 332 independent instance links
agree exactly with TypeId. No Meaning-3 link occurs. The current adapter rejects
only the normal hierarchy's `(ordinary,type)` role combination. These measured
facts do not establish how the current UI displays a type's normal parent, or
whether a Plex visibility preference hides it. [Aggregate `graph`](aggregate-archive-differences.json),
[relationship decoder](../../../../src/brz2obsidian/sources/thebrain/relationships.py).

Native follow-up should record the Brain/build and, without changing the source,
verify an ordinary A / type B pair appears as A parent and B child; verify a
type with multiple ordinary parents retains each parent; separately observe a
type/member pair and its classification. Use a disposable control only if the
current display is ambiguous. A changed type-parent visibility setting must not
be mistaken for deleted hierarchy or membership. Category presentation is a
later prototype/user decision, not an answer supplied by numeric correlation.

## Remaining bounds and map consequences

The existing native-observation, missing-content policy and category-hierarchy
prototype/decision children cover the unresolved questions. No additional
behavior decision is justified by this comparison. Carry the real cycle,
type-owned empty placeholder, tag icon, ZIP preservation and coexistence of
type/tag roles into subsequent specification/regression evidence. The
[source-neutral ADR](../../../adr/0001-source-neutral-core.md) remains
compatible: BRZ meaning stays in its source adapter; no domain/ADR change is
established by this research.

The 66 absent notes' syntax/content cannot be assessed from unavailable bytes.
Archive metadata does not record the producer build. Whole-archive successful
conversion/preservation remains unverified; subset selection/output counts are
not acceptance of D. Re-export or recovery creates a new fingerprint and may
expose additional content or metadata; rerun the complete inventory on that
exact new input before accepting its scope. The report selects neither a
missing-content policy nor a category design.

## Reproduce and verify

From this checkout, with all four originals still under `brz/`:

```powershell
& .\.venv\Scripts\python.exe `
  .scratch\management-leadership-wayfinding\research\inspect_archive_differences.py `
  --output tmp\ml-wayfinding\archive-comparison\aggregate-rerun.json
& .\.venv\Scripts\python.exe -m ruff check `
  .scratch\management-leadership-wayfinding\research\inspect_archive_differences.py
& .\.venv\Scripts\python.exe -m ruff format --check `
  .scratch\management-leadership-wayfinding\research\inspect_archive_differences.py
```

The [inspector](inspect_archive_differences.py) imports the earlier maintained
privacy-safe field/Markdown helpers and records helper/current-inspector and all
adapter hashes. It refuses absent prior CRC fingerprint evidence, rescans all
records and present note candidates, and writes only the requested aggregate.
Deterministic rerun bytes, Ruff lint/format and private-string/record-ID exclusion
checks passed. Private validation results remain under
`tmp/ml-wayfinding/archive-comparison/`. No production code, source archive,
retained vault, branch checkout or normal Git index was modified.
