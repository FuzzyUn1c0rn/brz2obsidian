# What the Software Engineering archive adds

Research date: 2026-10-04. Scope: complete structural comparison of the three supplied archives, current version 1 source coverage, and first-party documentation. This establishes source evidence; it does not select an Obsidian representation or authorize a relaxed refusal policy.

The new archive adds thought types and instance assignments, type-owned icons and inherited appearance, video-preview metadata, **four zero-length absent-TXT declarations**, and **one nonempty `Notes.md` marked `NoteType=0`**. The last two are outside the existing approved gap/content rules. The format number remains 5. [Complete aggregate evidence](aggregate-feature-inventory.json), [reproducible inspector](inspect_v2_archives.py), [reviewed v1 coverage](../../../docs/source-coverage.md).

## Inputs and complete comparison

A = `D&D_ The Rise of Anzoras 2026-10-03.brz`; B = `Dungeons & Dragons 2026-10-03.brz`; C = `Software Engineering 2026-10-04.brz`. No archive was extracted, changed, uploaded or converted by this research.

| Measure | A | B | C |
| --- | ---: | ---: | ---: |
| Compressed bytes | 45,016,149 | 153,693,431 | 62,008,262 |
| ZIP members / payload files | 73 / 60 | 63 / 50 | 245 / 232 |
| Uncompressed bytes | 45,922,444 | 164,001,091 | 70,776,901 |
| Thoughts / links / attachments | 76 / 129 / 66 | 58 / 57 / 63 | 372 / 693 / 254 |
| Settings / modification logs | 27 / 1,163 | 25 / 464 | 32 / 2,675 |
| Brain users / syncpoints / tombstones | 1 / 186 / 63 | 1 / 77 / 60 | 1 / 143 / 439 |
| Active Markdown thought-note records | 40 | 33 | 121 |
| Ordinary / type / tag / system thoughts | 63 / 0 / 12 / 1 | 58 / 0 / 0 / 0 | 364 / 7 / 0 / 1 |

Each archive has `meta.json` (one object), `thoughts.json`, `links.json`, `attachments.json`, `settings.json`, `modificationlogs.json`, `brainusers.json`, `syncpoints.json`, `tombstones.json`, `calendarevents.json`, `access.json`, `fielddefinitions.json` and `fieldinstances.json`. The last four remain empty in all three. Strict UTF-8/BOM and CR/LF JSON decoding succeeded; every member passed CRC verification. There are no unsafe, encrypted, symlink, duplicate or case-ambiguous members, duplicate live identities, foreign Brain ownership, live/tombstone overlap, dangling live link endpoints, unresolved attachment owners, unmatched state identities or unaccounted physical payloads. Home references a live ordinary untyped thought in each archive. Historical references to nonlive identities remain history, not live-reference errors. [Inventory: `zip`, `identity`, `settings`, `top_level_identifier_reference_joins`](aggregate-feature-inventory.json).

SHA-256 fingerprints:

| Input | SHA-256 |
| --- | --- |
| A | `84405276897f27f188a9f33453aac94cfdac6a4dfaaeecf8f0bd5a46454b7be4` |
| B | `20b6085239b82ba7c4a6951d07a53243c3d7ddd00fcd3d6b91115cd7170c26b0` |
| C | `7c533a30439e281b1d51d6617c9f1f3cad9c2c1d67e5a1e056f280bf37709764` |

The A/B fingerprints, byte/member counts, collection counts, field-key unions and payload extensions reproduce the [original aggregate inventory](../../brz-to-obsidian/research/archive-inventory.json). The new inventory adds exact record-key schemas; field presence, omission/null, distinct-value counts and shapes; scalar numeric/boolean distributions; complete live/payload joins; parser-based note probes; and compatibility probes. It does not publish private strings, URLs or record IDs. Old regex note counts and new parser counts have different scopes and are not interchangeable.

## Roles, assignments and appearance

These are **all** C relationship combinations; tuples are `(Kind, Relation, Meaning, Direction, endpoint-A Kind, endpoint-B Kind)`:

| Tuple | Count | Evidence/classification |
| --- | ---: | --- |
| `(1,1,1,-1,1,1)` | 488 | Reviewed ordinary hierarchy |
| `(1,3,1,-1,1,1)` | 3 | Reviewed ordinary jump |
| `(1,1,2,-1,2,1)` | 195 | New type-instance assignment |
| `(1,1,6,-1,5,2)` | 7 | Existing system meaning with new type endpoints |

TheBrain staff identifies thought `Kind=2` as Type and link `Meaning=2` as `InstanceOf`, from type A to ordinary thought B. The same explanation identifies `Meaning=3` as `TypeOf`, from supertype A to subtype B. This provides a first-party numeric interpretation, rather than deriving meaning from correlations. It is older staff documentation, not a complete versioned format-5 specification. [Harlan's export-field explanation](https://forums.thebrain.com/post/in-links-json-what-are-these-fields-10616870).

All 195 populated thought `TypeId` values reference one of the seven live type thoughts and match the instance links exactly in both directions of the comparison. Membership sizes are 145, 23, 16, 7, 2, 1 and 1. C has no populated type identifiers on type thoughts, no `Meaning=3`, no link-type records/identifiers, no tag thoughts, no tag-assignment links and no `TagIds` entries. Absence here does not establish that TheBrain lacks those features. Ordinary hierarchy has 94 multiple-parent thoughts, maximum eight parents and no observed cycles/self-links. Ten title collisions are routine naming variation already covered by v1. [Inventory: `graph`](aggregate-feature-inventory.json).

Each type has a nonempty `Label` and one Type-5 PNG icon; six types declare `ForegroundColor`, one also declares `BackgroundColor`. Assigned ordinary thoughts have no direct colour or label fields; **one assigned ordinary thought owns its own icon attachment**. Physical ownership proves there is a separate icon resource, not which image takes precedence on screen. `ThoughtIconInfo` remains an opaque seven-token colon-delimited string; no meanings are assigned to its numeric/boolean tokens. Signed colour values are retained without assuming a channel/alpha encoding. [Inventory: `appearance`, attachment owner signatures](aggregate-feature-inventory.json).

The guide documents icon/label/colour inheritance, one parent type, and optional Plex visibility of a type parent. It also explains why membership should not be mistaken for ordinary sibling navigation. [TheBrain 14 guide, printed p.136](https://assets.thebrain.com/documents/TheBrain14/TheBrain14-User-Guide-v01.pdf). The earlier guide states that direct instance attributes override inherited attributes and that supertype attributes pass down through subtypes and instances. [TheBrain 12 guide, printed p.143](https://assets.thebrain.com/documents/TheBrain12/TheBrain12-User-Guide_V9.pdf).

Labels need specific verification: a staff response for v12/v13 describes fallback to the type name when an instance has no label and says a direct label overrides the inherited display. A separate staff explanation describes restoring inheritance by clearing the label and selecting the default colour. These establish general behavior in those versions, not the exact current export encoding or v15 editor/display distinction. [Chase's label explanation](https://forums.thebrain.com/post/show-thought-label-feature-12423484), [staff inheritance-reset explanation](https://forums.thebrain.com/post/feature-request-thoughtgtreclaim-inheritancecommand-6163-10376439).

The parent agent's read-only native observation on 2026-10-04 corroborated one type/member pair in the same Brain: the type UI identified a Type Thought, and its member showed the same icon/red presentation despite no direct archived colour, label or icon attachment. The member label editor showed an empty-label placeholder. Private evidence is under ignored `brz/v2-research-native/` in the original checkout. This is a reported corroboration, not a controlled override experiment, recorded build check or proof that the entire live Brain equals the archive.

Type thoughts can themselves own notes and attachments according to the guide; that does not imply inherited note/file contents. C exercises only their icon attachments, with no type-authored thought notes or ordinary files. [TheBrain 13 guide, printed p.118](https://assets.thebrain.com/documents/TheBrain13/TheBrain13-User-Guide_v04.pdf). Preserve the distinction between a thought's type, attachment `Type`, tags and programming-language types.

## Payloads, notes and newly unreviewed states

C's 254 attachment records comprise 121 Type-1/NoteType-4 thought notes, five Type-1/NoteType-0 files (four PDFs plus the ambiguous `Notes.md`), 82 Type-12 images, 24 Type-5 icons, 18 Type-3 HTTPS references and four Type-15 TXT records. All owners use `SourceType=2`. Special role flags remain false; `IsIcon` agrees with Type 5. The 232 present payloads are 122 `.md`, 81 `.webp`, 25 `.png` and four `.pdf`; their declared lengths match actual CRC-valid bytes. There are no new attachment enum combinations apart from the type owner role. [Inventory: `attachments`](aggregate-feature-inventory.json).

| Difference | Established fact | Coverage consequence |
| --- | --- | --- |
| Absent TXT declarations | Four Type-15/NoteType-0/state-2 `.txt` records have **`DataLength=0`**; each has a present PDF under the same owner | Existing warning requires positive length. These are unreviewed states; no derived/optional purpose or PDF pairing is established |
| Nonempty ambiguous note | One ordinary owner has exact `Notes.md`, Type 1/NoteType 0, 352 actual/declared bytes, nonempty UTF-8 without BOM; no second note record on that owner | Existing coverage accepts only empty placeholders. Source role and eligibility need evidence |
| Video metadata | Four Type-3/NoteType-0 URL records contain nonempty `VideoHtml`; each contains an HTTPS `iframe` with `src`, `width`, `height`, `frameborder` | URL bytes/metadata exist; playable-preview behavior is not yet an accepted mapping |

The official tutorials describe embedded videos in notes, but they do not document the `VideoHtml` attachment field or its relationship to the attachment's URL. No first-party definition of that field was located. Do not treat the general video tutorial as proof of these records' semantics. [TheBrain tutorials](https://thebrain.com/support/tutorials).

All 121 active thought-note payloads use UTF-8 BOM Markdown; 120 are nonblank. One contains CRLF; 65 contain bare LF; there is no bare CR or NUL. The current note tracer accepts all active notes, resolving **81 image references and two ordinary thought references**. The ambiguous NoteType-0 payload independently parses one additional local image reference, whose payload exists. Thus 82 physical images are referenced across both groups. Do not silently promote that ambiguous payload to an active thought note. [Inventory: `notes`](aggregate-feature-inventory.json).

C newly exercises fenced code (11 fences across two active notes), inline code (six notes) and a blockquote (one note). These are ordinary Markdown additions; the current tracer handles them. No source-local reference-style/autolink/HTML-link, cross-Brain form, parsed HTML note content, YAML frontmatter, wiki links, custom marker, footnote or table probe was observed. The probes describe these archives and do not certify every Markdown or future editor feature.

Other complete field/value differences are structural metadata: new `DisplayModificationDateTime` on every thought; absent `ForgottenDateTime` and several `SyncSentId` fields; five additional settings matching UUIDv5 numeric names 41, 46, 58, 62 and 101; string-boolean settings/history values; new modification-log codes 203, 204, 304 and 807; attachment position -6.0; and different colour/length scalars. Apart from independently reviewed Home name `20`, the setting names, history-code meanings, display timestamp and icon-token meanings remain uninterpreted. They must remain original evidence; their shapes are not new conversion rules. The JSON's `differences.collections` enumerates every field/shape/scalar delta against the A/B union.

## Compatibility and confidence

The current full source reader accepts A and B and refuses C at populated custom thought types. Independently examining the guards reveals seven unreviewed type-role records, 195 custom-type assignments, 202 unreviewed relationship signatures and **five attachment blockers** (four zero-length absent TXT records and one nonempty NoteType-0 `Notes.md`). The complete attachment normalizer also refuses. A diagnostic in-memory subset excluding exactly those five attachment records passes attachment/note checks; it leaves one physical member unaccounted and is **not a valid complete input or conversion**. It shows that the remaining attachment roles fit existing mechanics, while `VideoHtml` would currently survive only as original metadata. No refusal predicate was weakened. [Reader](../../../src/brz2obsidian/sources/thebrain/reader.py), [semantic guards](../../../src/brz2obsidian/sources/thebrain/semantics.py), [relationship decoder](../../../src/brz2obsidian/sources/thebrain/relationships.py), [attachment guards](../../../src/brz2obsidian/sources/thebrain/attachments.py), [profile](../../../src/brz2obsidian/sources/thebrain/profile.py).

| Claim/boundary | Confidence and basis | Remaining evidence |
| --- | --- | --- |
| Inventory, integrity, identities and payload accounting | High: complete local scans; fingerprints unchanged afterward; original A/B comparison agrees | Does not establish effective UI meaning |
| Type and InstanceOf numeric roles | High: staff enum explanation, exact assignment correspondence, native type observation | Tiny current-build export before broadening profile |
| Icon/colour inheritance; direct override model | Documented; one inherited member corroborated natively | Current-build precedence, default/reset/absent encoding and colour encoding |
| Labels and type-name fallback | Documented for earlier versions | v15 visible label vs editor value, whitespace/empty/default and override cases |
| Type hierarchy/content/link types | Documented feature classes; not exercised here | Only investigate further if accepted scope includes them |
| Zero-length absent TXT and nonempty NoteType-0 note | High structural evidence; source purpose unknown | Native owner review and minimal export comparison |
| VideoHtml | High structural evidence; semantic interpretation provisional | Native preview/URL relation and a controlled URL attachment export |
| Extra settings/history/display/icon tokens | High field/value-shape evidence; meaning unknown | Preserve opaquely unless destination behavior requires interpretation |

## Small controlled evidence requests

The next evidence step is [Verify the new source behaviors in native TheBrain](../issues/08-native-source-behavior.md). Use a disposable Brain and record exact TheBrain build/platform plus screenshots and BRZ fingerprints. These are proposed follow-up tests; none were performed here.

1. **One type, two instances:** assign distinctive foreground/background/icon/label; give one instance direct icon/colour/label overrides. Export before/after editing the type, then after clearing instance overrides. Compare direct fields, icon payload ownership, `TypeId`, instance links and actual displayed values. Include a blank type label to isolate type-name fallback. Toggle type-parent visibility once to identify its storage, without conflating visibility with membership.
2. **Two supplied exceptional owner cases:** read-only native review of the ambiguous NoteType-0 note and the four zero-length TXT records, followed only if necessary by disposable export examples for empty/nonempty note placeholders and PDFs with absent/empty TXT records. Determine active-content status and source purpose without inventing absent file bytes.
3. **One video URL attachment:** create a plain web reference and a video reference in a disposable Brain; inspect preview, export `VideoHtml`/`Location` correspondence and offline behavior. Avoid conflating note-embedded videos with attachment previews.
4. **Only if later scope demands it:** one supertype/subtype/instance, a type with its own note/file, and one custom link type. Establish exported signatures and precedence separately; none can be accepted merely because the OOP analogy suggests them.

Later decisions need separate boundaries for type definitions/membership/navigation, inherited and overridden appearance/labels, exceptional note eligibility, absent TXT reporting, and video preservation/display. Metadata preservation and ordinary Markdown/scale regression checks carry forward the v1 baseline. An agreed destination design and implementation specification belong to later Wayfinder milestones.

## Reproduce and verify

Run from the repository containing this script; inputs remain in the original checkout. The checked-out reader code is imported explicitly from that repository. The aggregate includes reader-file hashes and profile identity/version so a later source change is detectable.

```powershell
$projectPython = 'C:/Users/stefa/projects/brz2obsidian/.venv/Scripts/python.exe'
& $projectPython .scratch/brz-to-obsidian-v2/research/inspect_v2_archives.py `
  --original-inventory .scratch/brz-to-obsidian/research/archive-inventory.json `
  --output .scratch/brz-to-obsidian-v2/research/aggregate-feature-inventory.json `
  'C:/Users/stefa/projects/brz2obsidian/brz/D&D_ The Rise of Anzoras 2026-10-03.brz' `
  'C:/Users/stefa/projects/brz2obsidian/brz/Dungeons & Dragons 2026-10-03.brz' `
  'C:/Users/stefa/projects/brz2obsidian/brz/Software Engineering 2026-10-04.brz'
& $projectPython -m brz2obsidian inspect `
  'C:/Users/stefa/projects/brz2obsidian/brz/Software Engineering 2026-10-04.brz'
```

The first command writes only the requested aggregate file. The second is read-only and currently exits with refusal. Report links were checked against the research checkout and parent checkout (the map/ticket is still parent-owned); the inventory was rerun deterministically and checked for accidental private identifiers/strings.
