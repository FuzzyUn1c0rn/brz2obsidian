# Testing and acceptance

Use the project virtual environment (tested native Windows / CPython 3.14.8):

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check --no-cache .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
```

In a separate worktree, use the integration checkout's full `.venv` interpreter
path and set `$env:PYTHONPATH = Join-Path (Get-Location) 'src'` for that worktree.
Do not redirect a shared editable installation while other worktrees are active.

## Public tests

Ordinary tests require neither private inputs nor GUI access. Shareable synthetic
archives and actual temporary ZIPs/filesystems exercise Workflow inspect/convert
as the primary seam, with focused source/core/renderer/publication/CLI interfaces.
The checked-in minimal archive contains only synthetic records. Tests cover
source/accounting/refusal boundaries, Home and greedy hierarchy selection,
Windows names/collisions/truncation, resources/tags, exact reference spans and
unchanged Markdown, planned/actual results, installed/module CLI behavior,
transactional publication and durable receipts. Failure injection crosses OS
or source-stream boundaries while retaining real staging/filesystem evidence.

The test-only Folio source proves non-UUID substitution, distinct source evidence,
compatible output and inward import direction. Exact span tests cover repeated
references, escapes, nested lists/quotes, Unicode, code literals and CR/LF/CRLF.
The parser instruments base markdown-it-py rules and maps transformed inline
positions back to exact decoded source offsets; tokens' line maps alone are
not treated as character spans.

The suite includes 22 synthetic corruption proofs for the independent acceptance
checker. The checker imports only the standard library and reads archives/output
directly; production manifest/counts do not provide expected preservation facts.
See [the full acceptance report](../.scratch/brz-to-obsidian-v1/research/real-export-acceptance.md)
for audited bytes, original JSON, graph/tags, authored text, references, warning
conjuncts, identities/accounting, native configuration and reproducibility scope.

## Private full-export acceptance

Choose the exact fingerprinted A/B archives from the accepted preservation
baseline and a fresh short ignored output directory. The driver refuses an
existing output directory, performs six complete conversions (exact, repeat and
ZIP/root-record reordered A/B), saves private results, and prints aggregate counts.

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$sourceA = 'C:\path\to\exact-A.brz'
$sourceB = 'C:\path\to\exact-B.brz'
$output = 'C:\short\ignored\new-acceptance-run'
.\.venv\Scripts\python.exe -m tests.local_acceptance.run --source-a $sourceA --source-b $sourceB --output $output
```

All six accepted conversions passed independent comparisons with exit 2.
A produced 49 thought notes/60 present payloads/two exact icon warnings; B
produced 42 thought notes/50 present payloads/nine exact absent-TXT warnings.
Supporting files are excluded from thought-note counts. Logical repeated and
reordered vault behavior is stable, with documented source-order/fingerprint
and explicit run-metadata differences. Private archives, results, generated
vaults and UI evidence remain ignored under `brz/`; public reports are aggregate.

## Native review procedure

The [v2 dashboard slice](../.scratch/brz-to-obsidian-v2-implementation/issues/03-native-category-dashboards.md)
has an earlier bounded native gate on a fresh review copy of an actual synthetic
converter output. Use valid distinct image payloads and check contextual
membership, role/support exclusions, table/card images, provider/override edits
and a native link-preserving category rename. Keep the exact published baseline
unchanged. Public ZIP/workflow tests check generated obligations and byte
preservation; the native check verifies Obsidian evaluates those queries and
images. This early check remains separate from final complete-output acceptance.

The [v2 templates slice](../.scratch/brz-to-obsidian-v2-implementation/issues/04-native-templates-maintenance.md)
adds workflow checks of actual full templates, insertion variables, configured
native property types, future-category starters/guide, complete support records
and manifests, and reserved-title/NFC/duplicate/long-stem reproducibility.
Its separate bounded native gate uses a pristine synthetic converter output and
an editable review copy: select a full template in Editing view, verify current
insertion-day dates and inherited dashboard discovery, edit an existing note's
memberships without changing its dates/body/provider/source IDs, create a future
category from its starter and discover a handwritten member, then adapt/select
its full member template. Test a native category rename with automatic link
updates. Nested .base files are not Markdown templates. Do not apply a full
template to the established imported note as a membership-edit mechanism.
An actual category rename exposed unquoted template dates becoming YAML mappings.
The public workflow regression now verifies every generated Markdown template's
quoted date variables survive safe YAML parsing/rewriting and later insertion.
PyYAML is declared as a development dependency for this data-level regression;
the converter itself continues to serialize through its existing JSON quoting.

After full independent acceptance, make fresh copies of both accepted generated
vaults and preserve pre-click originals. Open only those copies in standard
Obsidian and record its observed version. Use original-source candidates joined
to final migration-record paths/tokens; do not guess filenames.

1. Confirm startup opens assigned root Home in Reading view and native Home
   bookmark opens the same file. Review original heading/body.
2. Navigate representative Parents, Children and Related links; inspect native
   Backlinks and Graph around existing and uncreated neighbors.
3. Confirm a reserved target is absent, click its native link, then verify the
   created file's exact assigned `Notes/` path and native backlink behavior.
4. For A, discover assigned created members through native tag search. B has
   no source tags; do not invent assignments. Review focused hidden memberships.
5. Render selected actual inline PNG (A), WebP (B), PDFs (B) and generic file
   Resources links (PNG in A/PDF in B). Actual roots have no inline images;
   root-relative image behavior is covered by synthetic renderer tests.
6. Verify preserved external URL/directory destinations without opening/fetching
   them. B Home has an external URL; remaining classes occur on ordinary notes.
7. If output defects appear, repair through the responsible public seam, rerun
   affected automatic/independent checks and repeat affected native observations.

No community plugins or replacement discovery features are required. This is
representative presentation review, not every note/PDF page. The user's normal
vault is never used. Native evidence and checked limitations are recorded in
[the native report](../.scratch/brz-to-obsidian-v1/research/native-acceptance.md);
prior prototype/Wayfinder results are not implementation acceptance.

## Recorded versions

| Component | Verified version |
| --- | --- |
| CPython on native Windows | 3.14.8 |
| Pydantic / pydantic-core | 2.13.5 / 2.46.5 |
| markdown-it-py / mdurl | 4.2.0 / 0.1.2 |
| pytest | 9.1.1 |
| PyYAML (template rewrite regression) | 6.0.3 |
| Ruff | 0.16.10 |
| setuptools / pip | 84.0.0 / 26.2.1 |
| Obsidian native presentation target | 1.13.7 |

`requirements.txt` records the full pinned environment, including transitive
packages. These observed versions establish the tested Windows/Python/app
boundary, not universal platform, later-runtime or Obsidian-version compatibility.
