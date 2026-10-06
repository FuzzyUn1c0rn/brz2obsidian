# Four-original preservation gate: initial run refused

Date: 2026-10-06

Execution head: `30ed23205d5569b1884376ffd559b5d0068f8456`

Status: incomplete; original D refused before publication

The current root source module `0.3.0` passed complete independent exact,
repeat and ZIP/root-record reordered audits for A, B and C. Original D was
refused by the source adapter with `invalid_source`: **Multiple declarations
assign one payload**. The mandatory twelve-output gate has not passed. There
is no D vault, verified publication receipt or successful D count record.

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

## Remaining gates

Ticket 07 remains claimed with every completion criterion unchecked. After a
responsible-seam repair is independently verified and integrated, rerun a fresh
complete twelve-output matrix. The 359 D bodies, 63 actual fallback images,
47 definitions/330 members, distinct type/icon/TXT facts and complete D privacy,
graph and file obligations remain unproved by this failed run. Native Obsidian
actual-output review, actual user acceptance, final review and release delivery
remain separate pending gates. Earlier prototypes and recovered-source evidence
do not close them.
