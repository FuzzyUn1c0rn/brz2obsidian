# Reviewed source coverage

First-version support covers reviewed feature classes in the two accepted
TheBrain 15 BRZ exchange-format-5 exports and controlled synthetic fixtures.
Those archives are acceptance cases, not a fingerprint allowlist. Another
format-5 Brain may convert if it fits these meanings; its version alone does
not establish support. Invalid, ambiguous, corrupt or unsupported input refuses.

## Records, Home and relationships

Known root files are `meta.json`, `thoughts.json`, `links.json`,
`attachments.json`, `settings.json`, `modificationlogs.json`, `brainusers.json`,
`syncpoints.json`, `tombstones.json`, `calendarevents.json`, `access.json`,
`fielddefinitions.json` and `fieldinstances.json`. UTF-8 accepts an optional
BOM. Meta is one object; other collections have one object per nonempty
CR/LF-delimited line, with empty collections valid. Duplicate JSON keys,
nonfinite values, ambiguous ZIP names, unsafe members, corrupt CRCs and invalid
live identities/ownership/references refuse. Every original field/history record,
omitted/null distinction, exact numeric value and raw date string remains
in the migration record. Forgotten live thoughts stay eligible; history and
tombstones do not resurrect deleted items.

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
These colours are preserved metadata; no decorative Appearance display is added.

## Notes and resources

Thought-owned attachments use SourceType 2:

| Type / NoteType | Supported interpretation |
| --- | --- |
| 1 / 4 | Thought Markdown at owner/Location; active content plus exact `.md.original` backup |
| 1 / 0 | Ordinary file, except a sole nonempty canonical `Notes.md` on an ordinary thought: active Markdown plus exact original backup. Empty decoded placeholders remain backups without content eligibility. |
| 3 / 0 | External HTTP/HTTPS URL reference |
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

Supported active local syntax is inline `[label](brain://<compact-id>/<suffix>)`
and `![alt](.data/md-images/<location>)`; compact GUIDs use .NET bytes_le
URL-safe base64. Exact spans adapt only those references, retaining other text
and CRLF/CR/LF spelling. Code examples/literal link-like text remain unchanged.
Source-local reference-style, autolink, HTML-link and cross-Brain forms outside
reviewed syntax refuse. Observed bare, attribute-free `<br>` Markdown line
breaks, including `<br/>` spelling, are preserved; literal HTML comments remain
text. Rich HTML notes and unverified rich/legacy transformations
are unsupported. Nonempty events/access/custom-field collections and custom
type hierarchies/custom link types also refuse.

## Approved warnings

The fixed profile `thebrain-format5-reviewed`, version `2`, currently permits exactly:

Findings must have the reviewed kind, compatible rule/profile, subject and
evidence. Missing evidence and unknown kinds refuse; generic core contains no
numeric BRZ recognition predicates.

| Issue code / rule ID | Required conditions and result |
| --- | --- |
| `approved_source_gap` / `thebrain-format5/absent-txt/v1` | Thought-owned Type 15, NoteType 0, `.txt` Location, positive declared length, state 2, absent owner/Location bytes, with intact archived PDF under the same owner. Retain metadata/evidence; brief filename notice only on an existing owner note. No fake file/link or note solely for this gap. |
| `approved_source_gap` / `thebrain-format5/zero-length-absent-txt/v1` | Thought-owned Type 15, NoteType 0, safe `.txt` Location, declared length exactly zero, state 2, absent owner/Location bytes. The filename stem must equal one same-owner PDF attachment identity with ordinary Type 1/NoteType 0, state 1, present CRC-valid bytes and matching declared/actual length. Retain each declaration, exact PDF association and integrity evidence individually; apply the same existing-owner notice and no-fabrication rules. |
| `approved_metadata_discrepancy` / `thebrain-format5/icon-length/v1` | Verified icon role, present CRC-valid payload, declared length different from actual length. Copy actual bytes and retain both lengths; report discrepancy. |

The positive-length TXT rule makes no claim of particular PDF pairing; the
separate zero-length rule requires the identity association. Neither rule claims
derived purpose, optionality, extraction failure or search after a fresh restore.
Wrong state, ownership, role, stem, ambiguous identity or absent/corrupt PDF
refuses rather than widening the zero-length rule. A has two icon warnings; B has nine absent-TXT warnings under seven
owners. Both successful conversions exit 2. Unmatched missing notes/files/images
refuse as missing required payload. Unknown findings/profile incompatibility and
unsupported meanings cannot be downgraded by caller allowlists.

PDF bytes are preserved for normal native opening. The migration report explains
once, separately from individual source gaps, that Obsidian vault Search does not
search PDF body text. This converter does not extract/index PDFs or promise
equivalent TheBrain PDF body search.

Name sanitation, simple graph presentation and intentional uncreated targets
are adaptations rather than extra warnings. See [complete independent
preservation results](../.scratch/brz-to-obsidian-v1/research/real-export-acceptance.md).
