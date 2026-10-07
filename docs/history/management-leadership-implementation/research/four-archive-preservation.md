# Four-original preservation gate: complete m5 acceptance

Date: 2026-10-06

Execution and independently verified runtime:
`e2c5fc3f05d2daa0d0547d2bbaa2b12557a248b5`

Status: PASS for complete original-input preservation; native/user/release gates pending

The fresh `tmp/m5` matrix completed all twelve exact, repeat and ZIP/root-record
reordered outputs for the four mandatory original archives. The driver exited
**0**; every conversion returned warnings with CLI exit **2** and a published,
verified receipt. A separate read-only re-audit passed all twelve raw-source,
result and receipt checks, four reorder record-multiset/physical-payload checks
and eight vault comparisons. Its complete **7,029-file** matrix inventory was
unchanged before and after verification. This gate resolves
[ticket 07](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/68); earlier failed matrices
remain historical evidence below.

## Selected code, inputs and actual execution

The isolated ticket07 branch fast-forwarded to the execution head above before
running. Execution and independent verification selected the clean frozen root
checkout, root `.venv/Scripts/python.exe`, explicit `PYTHONPATH=<root>/src;<root>`,
UTF-8 and no bytecode writes. Runtime `0.3.0`, root source/driver/oracle imports,
exact Git HEAD and selected module byte hashes were verified. No installation,
editable retarget, source recovery or environment change was used.

The mandatory original D remained 320,594,486 bytes, SHA-256
`2b24c1d21b4090f3b0ed3ec0227f269b8c7a4e5b6832ada0e244a1dcfc941ced`.
The driver's earlier A/B/C fingerprint pins also remain unchanged. From the
root checkout, the prepared script executed this actual driver command:

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = (Join-Path (Get-Location) 'src') + ';' + (Get-Location)
.venv/Scripts/python.exe -m tests.local_acceptance.run `
  --source-a 'brz/D&D_ The Rise of Anzoras 2026-10-03.brz' `
  --source-b 'brz/Dungeons & Dragons 2026-10-03.brz' `
  --source-c 'brz/Software Engineering 2026-10-04.brz' `
  --source-d 'brz/Management & Leadership 2026-10-05.brz' `
  --output tmp/m5
```

Fingerprint checks surround every relevant driver operation and completion.
Separate before/after/final and post-supplement guards passed: **four originals
and all 562 retained-vault files unchanged**. Independent verification repeated
those checks. The old `tmp/m3` and `tmp/m4` outputs/evidence were preserved;
all experiments used fresh ignored destinations.

## Complete source-bound included obligations

Every entry below was derived from the exact raw source records, ownership,
scope and physical bytes, then checked by identities/joins across each variant.
Production receipts and matching totals were not expected preservation truth.

| Included obligations per variant | A | B | C | D |
| --- | ---: | ---: | ---: | ---: |
| Items / relationships | 69 / 117 | 56 / 55 | 372 / 693 | 570 / 730 |
| Attachment declarations / safe JSON records | 62 / 277 | 61 / 199 | 254 / 4,610 | 1,557 / 2,891 |
| Created notes / intentional uncreated targets | 47 / 21 | 41 / 15 | 305 / 66 | 472 / 97 |
| Definitions / assigned ordinary members | 0 / 0 | 0 / 0 | 7 / 195 | 47 / 330 |
| Present payloads / safe note originals | 56 / 39 | 48 / 32 | 232 / 122 | 1,017 / 359 |
| Supplied recognized bodies / authored local references | 39 / 51 | 32 / 12 | 122 / 84 | 359 / 437 |
| Warning records / included owners | 2 / 2 | 9 / 7 | 4 / 2 | 93 / 84 |
| Required support files / actual vault files | 17 / 120 | 16 / 105 | 23 / 560 | 63 / 1,552 |

D's 570 included items are 521 ordinary, 47 definitions, one tag and one system
item. Its 730 relationships comprise 376 hierarchy, 13 related, one tag, ten
system and 330 classification relationships; 54 hierarchy links join ordinary
parents to categories. Complete reciprocal navigation and classification remain
distinct. All 47 definitions and 330 assigned members materialize; the whole-source
332 assignment count is not the included expectation.

D preserves every one of its **359 supplied bodies** (328 marked and 31 canonical
NoteType-0) through only permitted source-reference adaptations, with all 359
safe originals exact. Its distinct physical payloads comprise 359 note originals,
499 note images, 106 generic files and 53 icons; 454 external URLs retain their
raw associations. Full names, dates, Home/tags, graph, membership, support and
body/reference bytes were audited, including supplied blank bodies.

All **63 absent ordinary-note owners** visibly embed their original owned images
with layout A: 62 WEBP cards and one PNG workflow chart. Every image's declaration,
physical bytes, complete pixel decode, ownership, assigned path, ordered embed and
diagnostic link was verified. They receive no fabricated Document, original-note
bytes or authored-reference credit. The two absent type notes remain unknown;
eight missing icon providers give neutral appearance to 45 included members.
The 13 positive-length TXT findings remain separate per declaration, including
five repeated absent-path pairs; seven actual icon-length discrepancies retain
their own evidence. The 73 new source gaps, 63 generated presentations and 93
total warnings remain distinct facts.

A/B/C match the recomputed included expectations in the historical table below.
Only the approved forgotten-scope differences from the unscoped v2 baseline apply
to A/B; C retains its 7 definitions/195 members, 122 supplied bodies, exceptional
note/image, four zero-TXT/PDF findings, four reviewed video resources, one owned
icon override and 194 inherited defaults. Included content survives independently
of excluded subjects' names or pixels. Excluded ownership, references, raw evidence
and history are absent from destination artifacts under the accepted privacy rule.

## Separate verification and handoff evidence

The independent `verifier-report-m5.json` binds PASS to the execution head, root
runtime/oracle imports, selected source module byte hashes, original fingerprints,
all twelve actual outputs and unchanged complete inventory. It separately derived
D's body/image/provider/member populations and verified full source obligations.
Repeat/reorder equivalence permits only established fingerprint/snapshot,
raw-evidence order/pointer and explicit run/clock/bookmark provenance differences.

Supplementary source-free checks passed **12 library plus 12 JSON CLI operations**,
CLI exit **0**, with complete relative inventories, lengths and SHA-256 hashes
unchanged after every call and across the whole matrix. They supplement the raw
source-bound proof. The private handoff independently derives expected note/asset
paths, all supplied-body and fallback-image joins, D's 47 category/330 member paths,
C's 7/195 controls, provider/explicit/neutral icon facts and scoped hierarchy.
It uses actual source/output joins, not prototype names or production counts.
The separate final `verifier-m5-handoff-report.json` confirms those handoff facts
against all four raw sources, including body hashes/safe originals, every generated
image's identity/owner/bytes/path, D47/330 and C7/195 dashboard/template/member paths
and all thirteen distinct TXT declarations. It again confirms complete matrix and
input preservation; it supplies no native application observation.

Detailed evidence stays ignored under root `tmp/m5/` and
`tmp/ml-implementation/07/`: `m5-matrix.log`, `m5-matrix-exit.txt`, head/import and
input guards, `verifier-report-m5.json`, `verifier-matrix-inventory-m5.json`,
`m5-supplementary-checks.json`, `m5-complete-inventory.json`,
`m5-raw-scope-facts.json` and `m5-native-handoff-private.json`.
Exact subject identities, titles, paths, assets and screenshots are not published.

## Remaining native, user and release limits

This proves included material supplied by these four exact originals. Absent
prose, captions and authored layout remain unknown; official state-3 meaning and
the producer's omission cause remain unproved. No native Obsidian review, actual
user verdict, final cumulative review, package refresh or release delivery is
supplied by this source-bound gate. Tickets 08 and 09 own those later obligations.

## Historical m4 failure: diagnostic alias mismatch

At clean root `a622058c82188a4b8a02b261f28271366a49961e`, fresh m4 passed the
nine A/B/C variants, then published D's exact vault but failed its independent
diagnostic-row audit. Replacing brackets in a title left extra alias whitespace
in the gap report; the target, identities, role and outcome matched, but the
established normalized link-label spelling did not. No D source-bound PASS,
repeat/reordered D output or complete matrix aggregate was claimed. The complete
failed-output inventory, private row facts and all original/562-file guards were
retained. The responsible renderer slice was repaired and independently verified
before the entirely fresh m5 matrix; no oracle expectation was weakened.

## Historical m3 gate: initial run refused

Date: 2026-10-06

Execution head: `30ed23205d5569b1884376ffd559b5d0068f8456`

Status: incomplete; original D refused before publication

At the m3 execution, the root source module `0.3.0` passed complete independent exact,
repeat and ZIP/root-record reordered audits for A, B and C. Original D was
refused by the source adapter with `invalid_source`: **Multiple declarations
assign one payload**. The mandatory twelve-output gate has not passed. There
was no D vault, verified publication receipt or successful D count record in m3.

## Execution and preserved inputs

All Python operations used the root project `.venv/Scripts/python.exe`, with
explicit `PYTHONPATH=<root>/src;<root>` and UTF-8 output. Before and after the
run, Git HEAD was the execution head above, the root checkout was clean, and
the selected package file was `<root>/src/brz2obsidian/__init__.py`, module
version `0.3.0`. No installation or environment retargeting was performed.

The actual driver help requires all four original inputs and a fresh output
directory. Executed from the root integration checkout:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src') + ';' + (Get-Location)
$env:PYTHONIOENCODING = 'utf-8'
.venv/Scripts/python.exe -m tests.local_acceptance.run `
  --source-a 'brz/D&D_ The Rise of Anzoras 2026-10-03.brz' `
  --source-b 'brz/Dungeons & Dragons 2026-10-03.brz' `
  --source-c 'brz/Software Engineering 2026-10-04.brz' `
  --source-d 'brz/Management & Leadership 2026-10-05.brz' `
  --output tmp/m3
```

Exit **1**. The driver retained nine published vaults and their conversion JSON
receipts, three independently checked reordered sources, and D's refusal JSON.
The accepted A/B/C fingerprints were retained. D was the mandatory original,
320,594,486 bytes, SHA-256
`2b24c1d21b4090f3b0ed3ec0227f269b8c7a4e5b6832ada0e244a1dcfc941ced`.
No recovered export was used. Driver fingerprint checks surrounded each completed
operation. The separate preservation guard passed before, after and at completion:
all four original archives and all **562 retained-vault files** were unchanged.

## Completed A/B/C evidence

Every exact/repeat/reordered output passed the independent raw-source oracle;
each conversion returned warnings with exit **2** and a verified receipt.
Each reordered archive retained the original ZIP member identities, complete
root-record multisets and every non-root physical payload byte. Repeated and
reordered outputs matched within only the established fingerprint/snapshot,
raw-evidence order/pointer and explicit clock/run/bookmark provenance differences.

| Raw-derived included obligations | A | B | C |
| --- | ---: | ---: | ---: |
| Items / relationships | 69 / 117 | 56 / 55 | 372 / 693 |
| Attachment declarations / safe JSON records | 62 / 277 | 61 / 199 | 254 / 4,610 |
| Created notes / intentional uncreated targets | 47 / 21 | 41 / 15 | 305 / 66 |
| Definitions / assigned ordinary members | 0 / 0 | 0 / 0 | 7 / 195 |
| Exact present payloads / safe note originals | 56 / 39 | 48 / 32 | 232 / 122 |
| Supplied recognized bodies / authored local references | 39 / 51 | 32 / 12 | 122 / 84 |
| Warning records / owners | 2 / 2 | 9 / 7 | 4 / 2 |
| Required support files / complete actual files | 17 / 120 | 16 / 105 | 23 / 560 |

These expectations were recomputed from exact raw records, ownership and physical
bytes. They were not copied from old unscoped v2 totals. Compared with the accepted
v2 baseline, default forgotten exclusion changes A's 76/129 items/relationships
to 69/117, 66 declarations to 62, 1,712 root records to 277 safe retained records,
49/26 created/uncreated targets to 47/21, 60/43 payloads/originals to 56/39,
68 references to 51 and 126 actual files to 120. B changes 58/57 items/relationships
to 56/55, 63 declarations to 61, 806 root records to 199 safe retained records,
42/16 targets to 41/15, 50/34 payloads/originals to 48/32 and 108 files to 105;
its twelve authored references remain. Unsafe/dependent evidence is removed under
the accepted privacy policy, including history tables when forgotten items exist.
C's included inventory and counts remain unchanged. A/B/C have no new ordinary
image fallback, missing-type note/icon gaps or ordinary-to-category hierarchy.

Full note bytes, allowed source-reference adaptations, exact safe originals,
resource bytes, scoped graph/navigation, dates, Home/tags, names and native
support obligations passed the raw oracle for all nine outputs. A's two icon
length warnings and B's nine TXT warnings remain distinct. C retains seven
category membership sizes 1/1/2/7/16/23/145, all 195 members, one owned override,
194 inherited defaults, 122 supplied bodies, the exceptional note/image, four
zero-TXT/intact-PDF findings and all four reviewed video resources/timing.

The public source-free library and JSON CLI checker additionally reported clean
for each of the nine outputs: **18 operations**, CLI exit **0**. Complete relative
file inventories, lengths and SHA-256 hashes before and after each call prove
that checking did not write. These convention checks supplement source-bound
proof; they do not establish the failed D acceptance or native rendering.

## Original D blocker and responsible seam

An independent scan of original D's declarations found **five** repeated local
member groups, containing **ten** declarations. Every group belongs to an included
owner; every pair is Type 15, NoteType 0, file state 2, and every referenced TXT
member is physically absent. None belongs to a forgotten owner. This is distinct
from competing declarations for present image/file bytes. The production scope
guard rejects the repeated absent-member spelling before reviewed TXT-gap
interpretation. Independently running the raw oracle scope produces its own
`raw unique payload declaration` assertion on the same original.

The responsible seams are the TheBrain adapter's local-declaration ownership
guard (`src/brz2obsidian/sources/thebrain/scope.py`) and its separate independent
raw-source counterpart (`tests/local_acceptance/scope.py`). A narrowly specified,
publicly verified repair must preserve refusal for genuinely ambiguous present
payload ownership and keep individual absent-TXT declaration facts distinct.
This evidence ticket made no production, oracle, test or expected-truth change.
The original was not altered or replaced to bypass refusal.

Detailed private evidence remains ignored under `tmp/m3/` and
`tmp/ml-implementation/07/`: matrix log/exit, failed D receipt, completed source
receipts, independent partial aggregate, complete checker inventories/results,
raw scope facts, exact duplicate declaration rows and input-preservation logs.
Public evidence contains no original subject/attachment identities or assets.

## Remaining gates at m3 execution (historical)

Ticket 07 remained claimed with every completion criterion unchecked. After a
responsible-seam repair is independently verified and integrated, rerun a fresh
complete twelve-output matrix. The 359 D bodies, 63 actual fallback images,
47 definitions/330 members, distinct type/icon/TXT facts and complete D privacy,
graph and file obligations remain unproved by this failed run. Native Obsidian
actual-output review, actual user acceptance, final review and release delivery
remain separate pending gates. Earlier prototypes and recovered-source evidence
do not close them.
