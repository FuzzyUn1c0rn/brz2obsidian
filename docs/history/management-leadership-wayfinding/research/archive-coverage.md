# Management & Leadership: archive coverage against version 2

Assessed: 2026-10-05. Converter: `0.2.0`, reviewed profile version `2`.
Code baseline: `9ddba911eb53e589b53d8059141462ee3a274aea`, plus the existing
workspace changes present at assessment start. No production code was changed.

**The original archive cannot currently be converted by v2.** Exact-input
`inspect` and `convert` both exit 1 / `refused`, at `Invalid attachment file
state`. No exact-input vault is published. Exhaustive raw inventory and
per-record checks identify two blocker classes: 74 state-3 absent payloads and
54 hierarchy links from ordinary thoughts to thought types. The archive's
larger collection of present resources otherwise fits v2, as a deliberately
incomplete diagnostic subset demonstrates. This is not acceptance of a complete
migration.

The user reported **no warnings noticed during export**. That is useful source
context but does not explain absent bytes or establish state-3 semantics.

## Source identity and integrity

Input: `brz/Management & Leadership 2026-10-05.brz`.

| Measurement | Exact archive |
| --- | ---: |
| Compressed file bytes | 320,594,486 (about 320.6 MB / 305.7 MiB) |
| Exchange format | 5 |
| ZIP entries | 1,037 |
| Live thoughts | 586: 537 ordinary, 47 types, one tag, one system |
| Relationships | 753 |
| Attachment records | 1,568 |
| Present payloads | 1,024, totaling 357,042,724 bytes |
| External URL resources | 457 |
| Absent payload declarations | 87: 74 state 3; 13 state 2 TXT |
| Type assignments | 332, with complete TypeId/instance-link correspondence |

SHA-256:
`2b24c1d21b4090f3b0ed3ec0227f269b8c7a4e5b6832ada0e244a1dcfc941ced`.

All ZIP CRC checks pass; names are unique; every physical payload maps to an
attachment. No live identity duplicates or live/deleted identity overlap were
found. Home is a valid live ordinary thought. All thought ACType values are zero.
Events, access and custom-field definition/instance collections are empty.
The source fingerprint was rechecked after the diagnostic verification and is
unchanged. Sources: original archive; private `inventory-private.json`,
`audit-private.json` and `verification.json` under `tmp/ml-assess/`.

Format 5 establishes the container boundary, not universal feature support.
V2's reviewed meaning gates are documented in
[source coverage](../../../source-coverage.md) and implemented in the
[source reader](../../../../src/brz2obsidian/sources/thebrain/reader.py).

## Supported content and existing warning classes

| Observed feature | Assessment |
| --- | --- |
| 47 types; 332 typed ordinary members | Existing category/dashboard/template and membership behavior applies. All 47 types have members. The separate hierarchy-to-type links remain a blocker. |
| 359 present note payloads | 328 marked Markdown notes and 31 canonical NoteType-0 Notes.md candidates. Of the latter, two have substantive content and 29 are empty. Both substantive exceptions fit the v2 sole-candidate rule; no competing candidates exist. |
| 329 substantive present thought notes | All 359 present candidates parse within reviewed Markdown coverage; 436 local image references and one thought reference bind successfully. Original bytes can receive exact backups. No new active HTML/local-reference syntax was detected. |
| 500 Markdown images | 499 WEBP and one PNG. Existing image copying/reference adaptation applies; unreferenced images remain resources. |
| 112 ordinary file resources | 97 PNG, eight PDF and seven ZIP payloads. File extension/preview support is independent of byte preservation. No new attachment role is needed for these files. |
| 53 present owned icons | Existing copying/appearance rules apply. Seven have declared/actual length discrepancies, fitting the existing icon warning rule. The other eight declared icons are absent state-3 blockers. |
| 457 HTTP(S) references | 456 HTTPS and one HTTP; existing exact external-reference behavior applies. No fetching or offline completeness is promised. |
| One populated VideoHtml resource | Exactly the reviewed YouTube URL/metadata form; current video presentation passes. Other video-looking URLs with no metadata remain ordinary references. |
| 13 absent TXT declarations | All are positive length, Type 15 / NoteType 0 / state 2, with an intact same-owner PDF. All fit `thebrain-format5/absent-txt/v1`; no zero-length TXT rule is needed here. |
| Metadata/history | Existing date, colour and semantic-field validators pass the observed records. Additional settings, modification history, syncpoints and tombstones remain retained evidence. |

Attachment role totals are 394 Type-1/NoteType-4 notes, 143 Type-1/NoteType-0
attachments, 500 Type-12 images, 61 Type-5 icons, 457 Type-3 URLs and 13 Type-15
TXT declarations, all SourceType 2. The 66 absent marked notes explain the
difference between 394 declarations and 328 present marked payloads.

The 699 relationships already supported are 343 ordinary hierarchy, 13 ordinary
jumps, 332 classifications, one tag assignment and ten system connections.
Sources: exact raw archive and private audits; adapter predicates in
[attachments.py](../../../../src/brz2obsidian/sources/thebrain/attachments.py),
[notes.py](../../../../src/brz2obsidian/sources/thebrain/notes.py),
[classifications.py](../../../../src/brz2obsidian/sources/thebrain/classifications.py),
[metadata.py](../../../../src/brz2obsidian/sources/thebrain/metadata.py) and
[videos.py](../../../../src/brz2obsidian/sources/thebrain/videos.py).

## State-3 payloads

The adapter validates the entire file-state map before attachment interpretation
and accepts only exact integers 1 and 2 (`attachments.py:35–40`). This archive
has 74 entries with integer value 3, all without their expected local member:

| Role | Count | Observed impact |
| --- | ---: | --- |
| Marked Markdown note on ordinary thought | 64 | 63 owners are typed members. Their authored bytes cannot be read from this archive. |
| Marked Markdown note on type definition | 2 | Category-authored note bytes are absent. |
| Type-definition icon | 8 | Category appearance is absent; those categories collectively classify 45 ordinary members. |

These declarations affect 72 distinct owners. Missing notes declare 4,299 bytes
in total; missing icons declare 17,141 bytes. Notes declare lengths 5, 7, 64,
67 or 69; 62 declare 67. All are nonzero, including the two type-owned notes.
64 missing-note owners have one present Markdown image each; two have none.
An intact 67-byte note elsewhere is image-only, but this correlation does not
prove the content of missing notes, their exact reference syntax or omission
intent. A present icon elsewhere with a matching length likewise provides no
authenticated replacement.

**Unknown state does not prove corruption, emptiness or recoverability.** ZIP
integrity and absence are measured; the producer's meaning for state 3 is not
established. A bounded current official-domain/vendor search did not locate a
BRZ state-3 definition. The fetched
[vendor attachment example model](https://github.com/TheBrainTech/thebrain-api-quickstart-blazor/blob/master/TheBrainApiQuickstart/Data/Attachment.cs)
contains no BRZ file-state field or enum and cannot supply this meaning. The
official API schema fetch failed, so it supplies no fresh evidence. Earlier
[attachment-state research](../../brz-to-obsidian-v2/research/attachment-text-evidence.md)
also separates missing bytes from unproven state semantics.

Simply admitting integer 3 is insufficient: present local roles still require
state 1 and actual bytes (`attachments.py:191–195`); icons and active documents
also need honest availability/accounting. Do not downgrade missing thought-note
content using the unrelated absent-TXT rules or synthesize exact originals.

Planning prerequisite: inspect representative source notes and all eight icons,
record the source build/export options, and compare a controlled export or
disposable restore. Determine whether a complete re-export/recovery can provide
the bytes before specifying any loss-aware conversion rule. If they remain
unavailable, refusal versus explicit reviewed missing-content handling is a
product decision. See [original state-3 finding](intake-history.md#state-three-payload-finding).

## Hierarchy to thought types

54 records have signature `(1, 1, 1, -1)` but roles ordinary → definition. They
connect seven ordinary parents to 46 distinct types. V2's
[relationship decoder](../../../../src/brz2obsidian/sources/thebrain/relationships.py)
accepts ordinary → ordinary and ordinary → tag hierarchy, but excludes this
endpoint combination (`relationships.py:35–44`). Per-record decoding accepts
the other 699 records and rejects exactly these 54.

These are distinct from instance/classification links `(1, 1, 2, -1)` and do
not establish subtype inheritance. A likely faithful extension is ordinary
Children → category dashboard, and category Parents → ordinary note, preserving
all parents while leaving categories/membership/appearance independent.
This direction needs source/native confirmation before acceptance.

The [source-neutral analysis](../../../../src/brz2obsidian/core/analysis.py) permits
live nonsystem hierarchy endpoints, and the
[relationship renderer](../../../../src/brz2obsidian/obsidian/relationships.py)
already renders target paths without assuming an ordinary-note folder. This
suggests a focused adapter/profile/acceptance extension can reuse the current
core; it is a code-backed inference, not implemented or tested support for
these 54 links. No ADR change appears necessary. See
[original hierarchy finding](intake-history.md#hierarchy-to-type-finding).

## Diagnostic subset trial and its limits

To expose later failures without modifying the original or production code,
`tmp/ml-assess/subset_trial.py` wrote a private diagnostic archive that:

1. Removes all 74 state-3 attachment records and corresponding file-state entries.
2. Removes all 54 unsupported ordinary-to-type hierarchy records.
3. Retains all 586 thoughts, all other records and every physical payload byte.

**The subset is intentionally incomplete and is not a migration deliverable.**
The exact source remains refused. Its subset vault is only under
`tmp/ml-assess/subset-vault/`; missing notes/icons and omitted hierarchy are
not preserved by this trial.

| Check | Diagnostic subset result |
| --- | --- |
| Public inspect | Exit 2 / warnings; 480 planned notes, 1,024 assets, 437 references |
| Public convert | Exit 2 / warnings; verified receipt; 480 notes (433 ordinary, 47 categories), 1,024 assets, 1,567 files |
| Expected warnings | Exactly 20: 13 approved absent-TXT gaps and seven icon-length discrepancies |
| Read-only check-vault | Exit 0 / clean; 533 Markdown files and four Bases checked |
| Independent preservation oracle | Passes content/byte/reference/graph/classification/source-evidence checks against the subset source, plus public result/receipt checks |
| Exact-source payload cross-check | All 1,024 exact-source present payloads hash-identical in the subset and conserved by the independent vault audit |
| Original source fingerprint | Unchanged |

The subset creates all 332 typed members and 47 dashboards/templates; 105 other
nonsystem items intentionally remain uncreated under existing v2 selection.
All 359 present notes receive exact-original backups. The independent checker
reports 287 inherited member icons; the 45 memberships whose category icon is
absent are the remaining typed members. These counts describe the incomplete
subset, not a prediction of final full-archive output after missing bytes and
hierarchy are resolved.

Observed CLI durations were about 8.4 seconds for inspect, 42.0 seconds for
convert and 8.3 seconds for check-vault on this workstation. One run supplies
practical volume evidence, not a repeatability/scale benchmark.

The [independent checker](../../../../tests/local_acceptance/checker.py) and its
[source facts](../../../../tests/local_acceptance/facts.py) import no converter
implementation; they currently encode reviewed state-1/state-2 and graph-role
predicates. Their subset pass cannot certify new state or hierarchy semantics.
New coverage requires new independent expectations, not a blanket relaxation.
No full original-input repeat/reordered preservation matrix or native Obsidian
visual acceptance was possible/completed in this assessment.

## Inputs for the next implementation plan

1. Resolve source completeness and state-3 behavior first. Recover/re-export if
   possible, otherwise agree an explicit missing-note/icon policy and its limits.
2. Confirm and specify ordinary-to-type hierarchy navigation independently of
   membership and inheritance.
3. Extend the narrow adapter/profile, honest accounting/reporting and any
   eligibility/appearance handling those accepted decisions require. Existing
   templates, WEBP/PNG/PDF/ZIP resources, ordinary URLs and this video's syntax
   do not currently justify new feature work.
4. Add meaningful public positive/negative workflow controls and independent
   raw-source acceptance predicates; verify the exact new archive, repeat and
   reordered variants, and the previous three acceptance archives.
5. Review actual full output in native Obsidian: parent/category navigation,
   image-heavy notes, missing/recovered icon providers, PDF/ZIP resources,
   exceptional notes, duplicate naming and representative large resource lists.

Existing limitations continue: simplified graph navigation retains arrow/one-way
details as evidence; external references depend on availability; generic ZIPs
are preserved resources rather than expanded imports; PDF body search is not
implemented; generated body-icon snapshots remain separately editable. See
[v2 source coverage](../../../source-coverage.md). No archive evidence
requires broadening these boundaries now.

Private record-level evidence and scripts are retained in `tmp/ml-assess/`,
including original/subset CLI envelopes, the independent verification receipt
and a human-readable source-review list. This report retains aggregate decisions
when that temporary directory is later retired. The original finding records are retained in [intake history](intake-history.md);
follow-up now uses the [Wayfinder map](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/9) and its child tickets. An
implementation specification has not yet been accepted.
