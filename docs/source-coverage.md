# Reviewed source coverage

Historical version 2 support covers reviewed feature classes in all three accepted
TheBrain 15 BRZ exchange-format-5 exports and controlled synthetic fixtures.
All three archives use the same application version; the newer acceptance case
exercises additional features rather than a new source-format version.
Those archives are acceptance cases, not a fingerprint allowlist. Another
format-5 Brain may convert if it fits these meanings; its version alone does
not establish support. Invalid, ambiguous, corrupt or unsupported input refuses.

The version-3 profile combines default included scope, reviewed ordinary/type
source gaps and category hierarchy with the prior resource rules. Public mixed
actual-ZIP controls exercise those interactions and real publication failures;
they are bounded synthetic coverage. Complete four-original preservation and
native actual-output review passed; independent final review and actual-user
acceptance remain pending gates in the [current frontier](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/8).

## External file references (version 4)

Version 4 introduced external file support. The current version-6 module/profile and snapshot/policy contracts retain it, with
matching renderer and migration result/record versions. Thought-owned
`SourceType=2`, `Type=2`, `NoteType=0` records with coherent identities, integer
nonnegative lengths and ordinary boolean flags represent external files.
Reviewed locations are safe absolute drive-qualified Windows file paths; UNC,
relative, drive-relative, device paths, traversal, alternate streams and unsafe
Windows filename shapes remain refusals. Extensions do not change this role.

Each identity receives an encoded file URI and a distinct ordinary Resources
entry, preserving original location and metadata in scoped evidence. An external
file alone makes an included owner content-bearing. Historical lengths do not
assert accessibility: inspect/convert never check, open, execute, fetch, copy or
relocate external targets. External files contribute no copied payloads, missing
payload gaps or authored-reference counts. Conflicting local file states and
unassigned same-owner archive payload claims refuse; a separately declared
same-named internal file keeps its own identity and intact bytes.

Public actual-ZIP Workflow and thin CLI controls establish this bounded support.
The complete Red vs Blue archive, raw-source audit, native comparison and final
user presentation verdict remain separate gates under issue #78. Attachment
refusals identify included owners/attachments and evidence with role-specific
advice; Home guidance is reserved for invalid-entry failures. Forgotten owners
and excluded associations remain omitted before role interpretation.

## Literal prose (version 5)

The source adapter minimally escapes parser-active, attribute-free, unpaired
opening words such as `<Enter>` and `<username>`. Names match ASCII letters
followed by letters, digits or hyphens. This is a syntactic allowance for unknown
names, rather than a token whitelist. Existing code, escaped text, autolinks,
comments and accepted line breaks keep their behavior. Active end tags, paired
markup, attributes, declarations, processing instructions and recognized HTML
elements remain unsupported.

Recognized names include the current [WHATWG element index](https://html.spec.whatwg.org/multipage/indices.html#elements-3)
and [obsolete elements](https://html.spec.whatwg.org/multipage/obsolete.html#non-conforming-features),
reviewed 2026-10-09, plus the legacy `image` parser alias and foreign-content
roots `svg`/`math`. Thus newer `search`/`selectedcontent`, raw text containers
and legacy elements cannot become literal prose accidentally. Only parser-active
positions participate: a matching-looking end token inside code is protected.

`Document.text_adaptations` exposes source-neutral exact edits. Original offsets
use `scoped_source_text/unicode_codepoints`: UTF-8-sig decoded text after excluded
reference phrases have been removed, before escaping. Each edit carries that
representation's SHA-256, original span and before/after strings. Adapted offsets
use `document.text/unicode_codepoints`; references and document digest use this
adapted text. Generic validation reconstructs the scoped source and verifies
every edit before rendering. Reference rewriting composes against adapted text
without escaping it again. Safe original copies still preserve archived bytes,
including BOM and line endings; unsafe originals remain omitted.

Version 5 adds closed document/inspection edit fields, adaptation owner/document
and evidence fields, and `Counts.text_adaptations`. Snapshot/policy, result,
migration record, renderer and TheBrain module/profile versions change together.
The independent Folio adapter adopts contract 5 with explicit arbitrary edits;
its format and module/profile version remain unchanged. Literal edits create no
authored-reference, payload-copy or source-gap credit. Synthetic coverage does
not establish the later private-archive/native acceptance gates under #78.

## Sized inline images (version 6)

Parser-active local image destinations can carry exactly `#$width=Np$`, with a
canonical decimal integer N from 1 through 100. Only that complete raw fragment
is recognized, including the evidenced 75/90 widths. Entities, escapes or encoded
near misses cannot acquire support through parser normalization. Empty or
nonempty queries, unknown/empty/repeated/mixed fragments, leading zeros, signs,
fractional values and out-of-range widths refuse. Binding still requires exactly
one present same-owner image with intact payload inventory.

Paths decode percent encoding once, strictly as UTF-8. Malformed percent/UTF-8,
encoded separators, traversal/backslashes and residual encoded octets refuse as
ambiguous. Once-encoded spaces, Unicode and URI-significant `#` remain supported;
`%25` can represent a literal percent when the decoded name does not itself look
like an encoded octet. Safe vault assignment follows the existing filename policy
and collision handling, independently of the exact original source name. No
external targets are probed.

The adapter supplies a source-neutral `ImagePresentationNormalization` on the
reference: exact declaration, scoped adapted-document codepoint bounds, digest,
explicit basis and ordinary `responsive` presentation. Literal text adaptations
and excluded-reference removals retain their separately named coordinate bases.
Generic validation binds every fact to exact document text and its present owned
image; planning adds one honest presentation adaptation and an actionable
`image_presentation_normalized` warning per declaration. The renderer replaces
only the assigned image destination and recognized fragment, preserving authored
alt/title/order and exact source image bytes. It adds no HTML, CSS, plugin, pixel
width, resizing or recompression. Eligible original note bytes remain exact.

The warning/report links included affected notes, retains exact declarations and
explains ordinary responsive inline Markdown presentation without exact percentage
fidelity. It is distinct from source gaps and generated fallback images.
`Counts.image_presentation_normalizations` counts declared presentation facts;
authored reference and copied payload counts still describe real obligations.
Snapshot/policy, result/record, renderer and TheBrain module/profile versions all
move to 6 because reference fields and admitted meaning change. Folio adopts
contract 6 while retaining module/profile 3 and independently declared facts.
Original private archive preservation, full raw-source oracle and native
placement/readability remain later #78 acceptance gates.

## Records, Home and relationships

Known root files are `meta.json`, `thoughts.json`, `links.json`,
`attachments.json`, `settings.json`, `modificationlogs.json`, `brainusers.json`,
`syncpoints.json`, `tombstones.json`, `calendarevents.json`, `access.json`,
`fielddefinitions.json` and `fieldinstances.json`. UTF-8 accepts an optional
BOM. Meta is one object; other collections have one object per nonempty
CR/LF-delimited line, with empty collections valid. Duplicate JSON keys,
nonfinite values, ambiguous ZIP names, unsafe members, corrupt CRCs and invalid
live identities/ownership/references refuse. Version 3 excludes live thoughts
with valid populated ForgottenDateTime markers before destination planning,
independently of attachment states. Excluded subjects, owned assets, memberships,
relationships and identifying records do not reach the vault or public output.
Ownership closure includes nested objects/arrays and valid serialized JSON,
including canonical UUID case variants, Unicode-escaped identifiers and
duplicate ownership declarations.
Associated records and their transitive identities are omitted as a whole;
provably safe serialized strings retain their exact original spelling and
numeric precision. Reference refusal messages omit raw source targets.
Incoming authored phrases/embeds are removed exactly; unrelated included content
with matching titles or pixels survives. After those removals, an included body
with a proven omitted identity or associated record identity outside the approved
reference spans refuses with a static private error. This includes inline/fenced
code, HTML comments and bare source URIs; arbitrary literal rewriting cannot
preserve their unrelated bytes safely. The shared note/evidence safety check
recognizes known canonical UUIDs with valid case variants, case-exact compact
identities and omitted associated record IDs. It also inspects one percent-encoding
layer followed by one serialized `\uXXXX` layer without rewriting source text.
Repeated arbitrary decoding and title/pixel matching are not inferred; this is
bounded identity-association coverage, not a claim to detect every possible
representation of private content. Safe exact originals and provably
included raw fields preserve omission/null distinctions, exact numeric values
and date strings. Unsafe original copies are omitted explicitly; unscopable
modificationlogs, syncpoints and tombstones collections are omitted whenever
scope excludes subjects. Malformed markers and untrustworthy identities,
ownership or paths refuse without disclosing private subject details.
A forgotten Home retains required-entry refusal.

Live/deleted identity overlap and ambiguous physical assignments also refuse.
Unicode separators inside JSON strings remain data; record splitting uses only
CR/LF. Additional uninterpreted metadata remains evidence.

Thought roles are ordinary Kind 1, definition Kind 2, tag Kind 4 and retained
system Kind 5, with ACType 0. A populated ordinary `TypeId` must identify a live
definition and agree with exactly one type-to-member instance link; the converse
is also required. Missing, conflicting, duplicate, wrong-role and dangling
assignments refuse. Populated `ThoughtTypeId`, custom link IDs, type inheritance
and TagIds membership arrays remain unsupported. Home is the valid live ordinary thought referenced by the setting whose
ID is UUIDv5 of BrainId with name `20`. Missing/invalid Home refuses with
instructions to set Home in TheBrain and re-export.

All reviewed links use Kind 1:

| Meaning | Relation / Meaning / Direction | Endpoints / representation |
| --- | --- | --- |
| Hierarchy | 1 / 1 / -1, 1 or 7 | Ordinary A parent, ordinary B child |
| Hierarchy to source tag | 1 / 1 / -1 | Ordinary A parent, tag B child |
| Hierarchy to category | 1 / 1 / -1 | Ordinary A parent, definition B child; reciprocal Parents/Children |
| Jump | 3 / 1 / -1, 3, 5 or 7 | Ordinary endpoints; Related |
| Tag assignment | 1 / 5 / -1 | Tag A classifies ordinary B; native tags or hidden-membership listing |
| Instance assignment | 1 / 2 / -1 | Definition A classifies ordinary B; linked category membership |
| System connection | 1 / 6 / -1 | System A to ordinary/definition/tag B; retained only |

Original arrow/one-way details remain evidence, while navigation uses simple
Parents/Children/Related links. Other combinations, including Relation 2/4 or
Direction 0 and subtype Meaning 3, are unsupported. After content, Home,
definition and typed-member selection, the greedy
hierarchy cover selects parents covering the most uncovered incident edges,
with canonical key ties. It preserves cycles/multiple parents and does not
claim a global minimum.
The category signature does not admit Direction 1/7, reversed definition-to-ordinary
edges, definition-to-definition hierarchy or subtype inheritance. Category
Parents/Children follow the title before Members/Gallery. Every direct included
parent is linked, including intentional uncreated ordinary targets; hierarchy
does not create membership or force an empty parent note when its category
already covers the edge. TypeId and the exact instance link still establish
classification independently.

## Imported metadata and icon snapshots

Created ordinary thoughts, definitions and authored/resource-bearing source tags
share the canonical linked property core and paired original identities. Their
`created` and `updated` properties use valid encoded calendar dates from
`CreationDateTime` and overall `ModificationDateTime`; source timestamps retain
full precision independently, without timezone conversion. Missing/null/empty
dates remain empty, while invalid populated timestamps refuse. Display/file/note
modification timestamps remain uninterpreted evidence rather than update-date
fallbacks.

One owned Type-5 icon supplies an explicit local-image property. A typed member
without one keeps its override blank and receives its category's effective icon
as an initial editable body snapshot. Each icon is copied once, including icons
whose untyped owner remains uncreated; decorative icons never become Resources.
Multiple owned icon declarations refuse because a single displayed override
would otherwise require an unevidenced selection. Each item's own label survives;
type labels are not synthesized on members and `ThoughtIconInfo` remains opaque.

Declared integer `ForegroundColor`/`BackgroundColor` values in the reviewed
signed opaque ARGB range (`-16777216` through `-1`) normalize to `#RRGGBB`.
Other encodings refuse instead of inventing alpha/channel meaning. Declared
values remain distinct from inheritance and raw numeric evidence survives.
These colours remain migration/source evidence rather than vault properties.
Generated notes, templates, property-type configuration and Bases expose neither
foreground/background colour fields nor a decorative Appearance display.

## Notes and resources

Thought-owned attachments use SourceType 2:

| Type / NoteType | Supported interpretation |
| --- | --- |
| 1 / 4 | Thought Markdown at owner/Location; active content plus a safe exact `.md.original` backup; unsafe originals are omitted |
| 1 / 0 | Ordinary file, except a sole nonempty canonical `Notes.md` on an ordinary thought: active Markdown plus a safe exact original backup; unsafe originals are omitted. Empty decoded placeholders remain backups without content eligibility. |
| 3 / 0 | Exact external HTTP/HTTPS URL reference; populated reviewed YouTube metadata adds independently derived native video presentation |
| 5 / 0 | Decorative icon at owner/.data/Location; copied without Resources clutter |
| 8 / 0 | Absolute Windows directory reference rendered as file URI |
| 12 / 0 | Markdown image at owner/.data/md-images/Location; inline when referenced, otherwise Resources |
| 15 / 0 | Only the approved absent-TXT rules below |

Present local payload states are 1; every physical resource must be accounted
for with uniquely assigned CRC-valid bytes and matching declared length, apart
from the exact icon exception below. External references have no local file
state. BOM-only Notes.md is decoded empty while its original bytes survive.
Generic files are preserved regardless of preview support. A differently marked
active note requires exactly `Notes.md`, an ordinary owner and no competing
thought-note candidate, including an empty marked note. Nonempty NoteType-0
canonical notes on type/tag/system owners, competing candidates and other
ownership/roles/states or unverified semantic flags refuse. Whitespace-only
content does not by itself materialize an otherwise empty owner; its original
backup survives. Arbitrary Markdown files are resources rather than active
thought notes. The numeric marker is not interpreted as UI selection state.
External resources are never fetched.

Populated `VideoHtml` is accepted only for the reviewed zero-length external URL
role: an HTTPS `www.youtube.com/watch` URL with one 11-character `v` identity and
optional integer-seconds `t` value ending in `s`, plus the reviewed single iframe
metadata form with a matching YouTube identity and baseline `start=0`. Other
providers, metadata markup/attributes, extra query semantics, conflicting
identities or nonbaseline metadata starts refuse. Empty/null/omitted metadata
does not infer a video from an ordinary URL.

The original URL spelling/query and complete raw metadata survive independently.
Obsidian receives a fresh fixed iframe generated only from validated provider,
identity and timing facts beside the exact original clickable link. A URL such as
`t=18s` becomes the separate derived embed's `start=18`, even though the retained
archive metadata says `start=0`; the native embed and timing adaptations are
accounted separately in inspection and the migration record. Archived HTML is
never copied into active note content or executed by inspection/conversion.
No local video payload is invented or downloaded. One report paragraph explains
remote service/network/offline dependence outside individual source-gap warnings;
an unavailable remote preview does not mean archived bytes are missing.

Supported active local syntax is inline `[label](brain://<compact-id>/<suffix>)`
and `![alt](.data/md-images/<location)`; compact GUIDs use .NET bytes_le
URL-safe base64. Exact spans adapt only those references, retaining other text
and CRLF/CR/LF spelling. Code examples/literal link-like text remain unchanged.
Source-local reference-style, autolink, HTML-link and cross-Brain forms outside
reviewed syntax refuse. Observed bare, attribute-free `<br>` Markdown line
breaks, including `<br/>` spelling, are preserved; literal HTML comments remain
text. Rich HTML notes and unverified rich/legacy transformations
are unsupported. Nonempty events/access/custom-field collections and custom
type hierarchies/custom link types also refuse.

## Approved warnings

The fixed profile `thebrain-format5-reviewed`, version `3`, currently permits exactly:

Findings must have the reviewed kind, compatible rule/profile, subject and
evidence. Missing evidence and unknown kinds refuse; generic core contains no
numeric BRZ recognition predicates.

| Issue code / rule ID | Required conditions and result |
| --- | --- |
| `approved_source_gap` / `thebrain-format5/absent-ordinary-note-images/v1` | Unique included ordinary-owner Type 1/NoteType 4 canonical Notes.md, SourceType 2, raw state 3, absent physical owner/Notes.md bytes, nonnegative declared length, with a complete usable same-owner Type 12/NoteType 0 state-1 image basis. Keep the absent declaration without actual length/hash, Document, original backup or authored-reference credit. Display all images beneath a source-gap notice, with canonical asset-identity ordering and original copied bytes. |
| `approved_source_gap` / `thebrain-format5/absent-type-note/v1` | Unique included definition-owner Type 1/NoteType 4 canonical Notes.md, SourceType 2, raw state 3, absent owner/Notes.md bytes and nonnegative declared length. Category text remains unknown, with a category notice/report entry and no image reconstruction, Document, actual hash/length or original backup. |
| `approved_source_gap` / `thebrain-format5/absent-type-icon/v1` | Unique included definition-owner Type 5/NoteType 0, SourceType 2, IsIcon=true, safe owned owner/.data/Location path, raw state 3, absent bytes and nonnegative declared length. Retain the declaration, use neutral icon properties and preserve membership/provider links. Report the provider and genuinely affected included members separately; a valid explicit member icon wins. |
| `approved_source_gap` / `thebrain-format5/absent-txt/v1` | Thought-owned Type 15, NoteType 0, `.txt` Location, positive declared length, state 2, absent owner/Location bytes, with intact archived PDF under the same owner. Retain metadata/evidence; brief filename notice only on an existing owner note. No fake file/link or note solely for this gap. |
| `approved_source_gap` / `thebrain-format5/zero-length-absent-txt/v1` | Thought-owned Type 15, NoteType 0, safe `.txt` Location, declared length exactly zero, state 2, absent owner/Location bytes. The filename stem must equal one same-owner PDF attachment identity with ordinary Type 1/NoteType 0, state 1, present CRC-valid bytes and matching declared/actual length. Retain each declaration, exact PDF association and integrity evidence individually; apply the same existing-owner notice and no-fabrication rules. |
| `approved_metadata_discrepancy` / `thebrain-format5/icon-length/v1` | Verified icon role, present CRC-valid payload, declared length different from actual length. Copy actual bytes and retain both lengths; report discrepancy. |

The positive-length TXT rule makes no claim of particular PDF pairing; the
separate zero-length rule requires the identity association. Neither rule claims
derived purpose, optionality, extraction failure or search after a fresh restore.
Wrong state, ownership, role, stem, ambiguous identity or absent/corrupt PDF
refuses rather than widening the zero-length rule. A has two icon warnings; B has
nine positive-length absent-TXT warnings under seven owners; C has four
zero-length absent-TXT warnings under two owners, each associated with its intact
PDF. Those historical nine v2 exact/repeat/reordered conversions exit 2.
The current v3 four-original matrix also exits 2 for all twelve conversions;
original D preserves 359 supplied bodies and 63 fallback images, with 47
definitions/330 members, 1,017 present payloads, 1,552 actual files and 93 warnings.
See the [complete scoped matrix](history/management-leadership-implementation/research/four-archive-preservation.md). Unmatched missing notes/files/images
refuse as missing required payload. Unknown findings/profile incompatibility and
unsupported meanings cannot be downgraded by caller allowlists.

PDF bytes are preserved for normal native opening. The migration report explains
once, separately from individual source gaps, that Obsidian vault Search does not
search PDF body text. This converter does not extract/index PDFs or promise
equivalent TheBrain PDF body search.

Name sanitation, simple graph presentation and intentional uncreated targets
are adaptations rather than extra warnings. See [complete current four-original
preservation results](history/management-leadership-implementation/research/four-archive-preservation.md)
and the [source-feature-to-vault comparison](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/5#issuecomment-6040210387).

## Reviewed absent-note image display (version 3)

The generated fallback validates each owned note image fully. PNG, JPEG, WebP,
GIF, BMP and AVIF content must match the supported filename kind, have positive
dimensions, pass file verification and decode every frame. Unsupported kinds,
corrupt or truncated content, missing required images and state/member
contradictions refuse. This additional decoding is confined to an accepted
absent-note candidate; present-body resource preservation is unchanged.

The runtime uses Pillow 12.3.0, pinned in requirements.txt and constrained to
12.3.x or a compatible 12.x release in pyproject.toml. Pillow documents that
[Image.open is lazy and load reads pixel data](https://pillow.readthedocs.io/en/stable/reference/Image.html),
while [supported file formats have format-specific behavior](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html).
The decoder verifies the stream, reopens it, and loads every frame. It does not
recompress, repair or replace the archived payload.

Inspection and migration record version 3 expose joined source_gaps and
generated_presentations with the included owner, absent asset, reviewed finding,
ordered image identities and assigned image paths. source_gaps and
generated_presentations count source facts; planned_generated_embeds and
actual_generated_embeds count generated display separately from source/authored
references. Inspection leaves actual counts and receipt unknown. An absent note
gets no measured-byte or authored-reference preservation credit.

Each fallback notice links to the Migration report. Its optional repair checklist
records the fingerprint/scoped digest and collection, thought title/ID and
resolving owner-note link, attachment role/owned path/state/declared length and
physical absence, outcome and ordered real image identities/paths. Existing TXT
findings keep their distinct rules and no-note behavior; their checklist labels
an assigned uncreated target explicitly rather than making a resolving-link
claim. Titles and IDs provide source lookup; no native launch locator is inferred.
A clean source-free checker confirms current references, not missing prose
recovery or complete source preservation/native acceptance.

## Reviewed category source gaps (version 3)

Missing category text remains unknown even when its declared length is zero or
small. A category-owned note image does not reconstruct the missing type body
or become an icon. Present recognized category text, including empty, whitespace
and BOM-only bytes, follows the existing preservation path regardless of missing
icons. Only the exact reviewed type-owned declarations above admit state 3;
ordinary-icon, tag/system note/icon absence and contradictory state/payload
evidence remain refused.

A missing type icon produces a category notice and notices on included members
that would inherit it. An explicit valid member icon prevents that member from
being reported as losing its effective icon. Structured inspection/record entries
identify the missing asset once, its provider_key and affected_member_keys;
item_targets supplies their source titles, identities and destination paths.
The report links to the actual created category/member notes and retains the
raw state, declared length, owned path and source fingerprint. Existing TXT
diagnostics continue to label uncreated targets honestly without creating notes.

Membership and appearance_category remain linked when an included provider's
icon is absent. Adding a valid local icon to that category later updates native
Base defaults; static note-body snapshots remain independently editable.
Excluded providers and members contribute no diagnostics or inherited pixels.
Available unrelated icons and the narrow present-icon length discrepancy rule
retain actual measured bytes and hashes. Decorative absent icons do not create
Resources clutter or broken local links. The read-only checker accepts neutral
properties and still reports missing actual image targets.
