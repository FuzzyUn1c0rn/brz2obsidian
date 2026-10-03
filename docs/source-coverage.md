# Reviewed format-5 source coverage

The `thebrain-format5-reviewed` version-1 profile supports the accepted BRZ
format-5 interpretation. It uses structural predicates rather than archive
fingerprint exceptions. Inspect and convert both repeat source validation;
neither command accepts a missing-file allowlist.

The adapter validates ZIP identities, CRCs, live identities, ownership and
references before returning a durable snapshot. Duplicate live identities,
live/deleted overlap, ambiguous physical assignments, malformed JSON,
duplicate JSON keys and nonstandard nonfinite values refuse conversion.
Original JSON is retained independently of normalized facts, including every
field, omitted/null distinctions, original numeric spelling and naive dates.
JSON Lines split only at CR/LF; Unicode separators inside strings remain data.
Historical references can be nonlive and remain retained evidence. Forgotten
live thoughts keep ordinary eligibility.

Ordinary/tag/system thought roles are Kind 1/4/5 with ACType 0. Populated
custom type IDs, nonempty TagIds and unverified semantic role flags refuse.
Additional uninterpreted metadata remains evidence. Nonempty calendar, access
and custom-field collections refuse; retaining their bytes does not establish
semantic support. Home comes exclusively from the collection's UUIDv5 `20`
setting and must identify a live ordinary thought.

All supported relationships have Kind 1:

| Meaning | Relation / Meaning / Direction | Endpoints |
| --- | --- | --- |
| Hierarchy | 1 / 1 / -1, 1, or 7 | Ordinary parent to ordinary child |
| Hierarchy | 1 / 1 / -1 | Ordinary parent to tag child |
| Related | 3 / 1 / -1, 3, 5, or 7 | Ordinary to ordinary |
| Classification | 1 / 5 / -1 | Tag to ordinary |
| Retained system connection | 1 / 6 / -1 | System to ordinary or tag |

Other signatures refuse. Original arrow/visibility details remain evidence;
simple vault navigation is a recorded adaptation, not a warning.

Thought-owned attachments use SourceType 2. Supported Type/NoteType roles are
Markdown 1/4, ordinary file or empty Notes.md placeholder 1/0, URL 3/0,
icon 5/0 with IsIcon true, absolute Windows directory 8/0, and image 12/0.
Present local assets require state 1, uniquely assigned CRC-valid bytes and
matching declared length, with the precise icon exception below. A BOM-only
Notes.md placeholder is decoded empty and preserves its original bytes.
External references have no local file state and are never fetched/opened.
Unknown ownership/role combinations, special attachment flags, unaccounted
payloads, ambiguous notes and unsupported absence patterns refuse.

Supported active source-local Markdown is inline compact-GUID thought links
and owner-relative `.data/md-images/` images. The adapter emits exact Unicode
code-point spans; all other authored characters and CR/LF spelling survive.
Code examples and literal HTML comments remain text. Rich/legacy HTML notes,
attributed HTML, HTML local references, cross-Brain links and unsupported
active local reference forms refuse. The exact accepted A export contains two
attribute-free `<br>` line breaks in Markdown; those bare line breaks are
preserved verbatim, including `<br/>` serialization, without transforming
HTML content or admitting additional tags/attributes.

## Approved anomaly findings

The source adapter owns numeric predicates and versioned recognition rules.
Generic core matches findings to a compatible reviewed kind/rule/disposition
and validates their evidence and subjects. Unknown rules/kinds, missing
evidence and profile incompatibility refuse. There is no generic numeric BRZ
interpretation or unrestricted warning allowlist.
Reviewed dispositions can emit warnings only with the two approved warning
codes; a caller cannot downgrade required refusal codes to warnings.

| Rule | Required evidence | Result |
| --- | --- | --- |
| `thebrain-format5/absent-txt/v1` | Thought owner, SourceType 2, Type 15, NoteType 0, `.txt` location, positive declared length, state 2, absent owner/location bytes, intact archived PDF under the same owner | `approved_source_gap` warning (source finding kind `known_absent_payload`); retain metadata, no file/link or inferred purpose, optionality or particular PDF pairing |
| `thebrain-format5/icon-length/v1` | Verified icon role, state 1, present CRC-valid bytes, declared/actual length difference | `approved_metadata_discrepancy` warning; preserve actual bytes and both lengths |

Warnings do not make an item eligible for a note. An absent-filename notice
appears only in an existing owner note's Resources section; icon discrepancies
appear in the report/record. Inspect returns planned counts; a published
conversion returns actual verified counts and a receipt. Both warning outcomes
exit 2. Structured issues agree across library/JSON output and the migration
record; the report carries the same warning code, rule and observed evidence.
The migration record keeps the specified top-level field set. Each affected
asset target contains its versioned `source_findings`; item targets contain
their `documents` and exact reference spans. Documents belonging to retained
system items appear under their original asset target's `retained_documents`,
with no invented navigation target.

Normal tests use synthetic archives at the accepted workflow and public module
interfaces. Ticket 06's read-only smoke on the exact private A/B archives
matched 49/42 planned notes, 60/50 payloads and 2/9 warnings. Independent full
preservation and native Obsidian acceptance remain separate gates.
