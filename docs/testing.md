# Testing and acceptance

Use the project virtual environment (tested native Windows / CPython 3.14.8):

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check --no-cache .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
```

Run from the checkout root. Pytest uses reserved `tmp/pytest` for temporary test
files and clears that directory before each run; its cache lives in
`tmp/pytest-cache`. Ruff uses `tmp/ruff-cache`. For concurrent pytest runs in one
checkout, select distinct paths with `--basetemp=tmp/pytest-<run>`.
See [workspace housekeeping](workspace.md) for other temporary artifacts.

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

Category hierarchy tests use an actual complete synthetic ZIP with multiple
ordinary parents, duplicate edges, a cycle, assigned/unassigned parents, an
excluded endpoint and intentional uncreated targets. They verify reciprocal
navigation, hierarchy before Members/Gallery, independent membership, exact
source bytes, CLI agreement and repeat/reordered output. Signature near misses
remain refusals. A source-neutral Folio control checks category Children above
Bases and Related navigation after content without widening BRZ coverage.
The existing independent raw-source oracle admits the exact new hierarchy
signature and layout; an included-only control exercises its current whole-raw
evidence boundary. Full scoped/private four-archive audits and native/user
acceptance remain separate implementation gates.

The combined v2 actual-ZIP fixture independently checks seven imported notes,
eight byte-preserved payloads and 19 support artifacts, including exceptional
Markdown/image references, graph/tags, category membership/icon snapshots/dates,
the TXT/PDF gap and timed video. Current library/CLI schema 3, warning exit 2 and the
source-free checker schema 1/clean exit 0 agree. Exact/repeat/reordered synthetic
outputs retain logical records and output bytes; caller inventory/bytes remain
unchanged by inspection/checking/refused reconversion.

The combined v3 actual-ZIP fixture extends that same resource collection with
forgotten owned content/incident hierarchy, collision naming, a physically blank
supplied note, an absent ordinary note with two usable original PNGs, simultaneous
type note/icon gaps, an explicit member override, two included ordinary parents
of the category and an opaque ZIP resource. Independent literals require 11
included items, 11 relationships, seven imported notes, 11 exact payload copies,
18 support files, three source gaps and two generated embeds in 36 published
files. Missing source bodies/icons add neither fake original copies nor authored
reference credit. Expected bytes, graph/membership/provider joins, generated
image order, scoped diagnostics, privacy, metadata and receipt inventory are
checked at public workflow/CLI/checker boundaries. Console/module text and JSON
routes agree. Inspection and checker calls preserve caller inventories/bytes;
checking a deleted generated image detects the current defect despite the
historical verified migration record.

The v3 publication controls reach generated fallback/category notes, each
original fallback image, report and record with real partial writes, missing,
truncated or same-length corrupted staging bytes, and source mutation during
verification. Actual owner-directory Windows junctions and rename/rmdir races
preserve caller files. Source-stream open/partial-read/short-copy controls close
the streams and clean owned staging. Post-commit and teardown failures retain
the complete verified 36-file receipt and available actual counts. Conversion
reprepares a source changed after inspection. Exact/repeat/root-record and ZIP
reordering preserve all content, generated/affected-member ordering and logical
facts, apart from explicit fingerprint/digest, raw evidence pointers/order,
relationship-derived evidence order and clock/run/bookmark provenance. These
bounded synthetic checks leave full-original, native and actual-user gates open.

Focused v2 controls reach each selected template/Base/configuration/guide before
injecting partial writes, deletion/truncation/same-length corruption or source
changes. Actual Windows support-directory junctions and native rename/rmdir races
retain caller files and safe cleanup/leftover evidence. Category/default and
member/override streams are selected separately; post-commit/teardown failures
retain complete verified manifests and available actual counts. The additive
Folio fixture independently authors compatible classification, dates, icons and
video facts, with constructor/core version controls and active outer-import
barriers. These public checks do not replace the complete private archive audit.

`tests/vault_check` exercises the public source-free `check_vault` operation on
handwritten actual mutable vaults and its thin command. Controls cover known
properties, safe YAML/duplicates, roles/providers, qualified/shortened/ambiguous
references, active Base/images versus code/comments, imported identity pairs,
customs/uncreated targets/template dates, external paths, linked files and real
Windows junctions. OS/file-boundary failures retain readable-note diagnostics
and honest available/null counts. Complete before/after directory inventory and
byte hashes prove normal/problem/failure checks preserve caller files. Console
and module entry points agree with the API, and the checker still works when
source/workflow/renderer/publisher imports are blocked. This suite remains
separate from the independent migration preservation checker below.

The independent acceptance suite retains all 22 earlier corruption proofs,
69 v2 corruption/interaction checks, five driver corruption controls, two
positive v2 audit tracers and a standard-library import check. Eighteen additional
presentation-refinement controls plus four category-layout/evidence controls
bring the current group to 121 tests.
False receipts are rehashed and recounted consistently before the oracle rejects
incorrect assignments, materialization, icons/dates, note/reference evidence,
TXT/PDF/video facts, Bases/templates/configuration and required support. The
expected-fact modules import only the standard library and local oracle modules;
production manifests/counts do not provide expected preservation facts.
Refinement controls reject obsolete colour fields in generated notes, templates,
starters, Bases, property typing and guide while still rejecting falsified source
colour evidence. The checker permits manually added colour-named properties as
ordinary custom extensions.
See [current complete preservation](../.scratch/brz-to-obsidian-v2-implementation/research/colour-property-refinement.md),
the [historical pre-refinement v2 report](../.scratch/brz-to-obsidian-v2-implementation/research/three-archive-preservation.md)
and the [earlier v1 report](../.scratch/brz-to-obsidian-v1/research/real-export-acceptance.md).

## Private full-export acceptance

Choose the exact fingerprinted A/B/C archives and a fresh short ignored output
directory. The driver refuses an existing output directory, performs nine complete
conversions (exact, repeat and ZIP/root-record reordered for each source), saves
private results/operation evidence, and prints aggregate counts. It checks source
fingerprints before/after every operation and at completion, proves reordered
root-record multisets and physical bytes independently, and verifies the selected
worktree import. Set PYTHONPATH even in the integration checkout.

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$sourceA = 'C:\path\to\exact-A.brz'
$sourceB = 'C:\path\to\exact-B.brz'
$sourceC = 'C:\path\to\exact-C.brz'
$output = Join-Path (Get-Location) 'tmp/audit-01'
.\.venv\Scripts\python.exe -m tests.local_acceptance.run --source-a $sourceA --source-b $sourceB --source-c $sourceC --output $output
```

All nine accepted conversions passed independent comparisons with exit 2.
Those v2 fresh outputs placed category Members/Gallery immediately after their
heading, omitted generated introductory category images and retained category icon
properties/assets plus ordinary/member body snapshots. Four independent controls
reject reintroduced category images, Bases moved below labels, fabricated category
snapshot adaptations and false dashboard descriptions, even after consistent
receipt rehash/recount. A rich public workflow control audits retained category
authored images, mixed line endings, labels and resources against raw source facts.
Exact comparison with the preceding pristine presentation accounts for the seven
changed category notes, presentation-only adaptation/guide/report changes and
explicit run metadata; all ordinary notes, payloads, Bases, templates and other
configuration remain byte-identical. All 27 earlier audited outputs remain intact.
These outputs also omit colour properties and retain all source colour
facts in migration evidence; the earlier audit outputs remain intact as historical
evidence. Each original archive remains unchanged.
A produced 49 thought notes/60 present payloads/two exact icon warnings; B
produced 42 thought notes/50 present payloads/nine exact absent-TXT warnings. C
produced 305 imported notes, including seven definitions and all 195 typed members,
232 present payloads and four exact zero-TXT/intact-PDF warnings. Its 122 original
notes/backups, 84 references and four reviewed videos passed complete audit.
Supporting files are excluded from thought-note counts. Logical repeated and
reordered vault behavior is stable, with documented source-order/fingerprint
and explicit run-metadata differences. Private acceptance results, generated
vaults and UI evidence belong under ignored `tmp/<effort>/`; original exports
remain in `brz/`. Historical artifact paths are mapped in
[workspace housekeeping](workspace.md); public reports are aggregate.

## Local package and documented examples

On 2026-10-06, ticket 05 built the local `0.3.0` wheel with the project
environment and `pip wheel --no-deps --no-build-isolation`. All 57 runtime
package modules matched worktree source bytes; other entries were distribution
metadata only. Metadata/entry point declare the current version, Python >=3.14
and runtime Pydantic, markdown-it-py, PyYAML and Pillow. The unchanged actual
README default-workflow and architecture explicit-workflow/direct-module Python
examples ran against the complete mixed v3 archive, with caller paths substituted.
Each produced the expected 36-file verified vault and passed the documented
checker example. A separate subprocess imported from the wheel directly without
installation and passed module inspect/convert/check-vault JSON operations with
exits 2/2/0, schema 3/checker 1 and two actual generated embeds. Source bytes
remained unchanged. Ticket 05 records the commands and bounded evidence.

On 2026-10-05, the local `0.2.0` wheel built through the project environment with
`pip wheel --no-deps --no-build-isolation`. Its metadata declares Python >=3.14,
Pydantic, markdown-it-py and runtime PyYAML; the console entry point is
`brz2obsidian.cli:main`. Inspection found exactly the 53 source package modules
and distribution metadata, with no private extracts, vaults or test fixtures.
A subprocess imported directly from that wheel without installation and passed
module inspect/convert/check-vault JSON calls.

The actual Python examples in README, architecture and checker guidance were
executed on an independently authored synthetic ZIP with a type, an empty typed
member, source dates, an authored CRLF Home body and a local category image.
Default Workflow, explicit Workflow, direct analyze/plan/render/publish, and
console/module text/JSON routes and direct-wheel conversion produced eight
complete vaults, each with the independently expected 22 files: three imported
notes, two exact payloads and
17 support artifacts. API receipts matched every actual length/hash; CLI outputs
matched the same independent inventory, properties and payload-byte expectations.
Migration schemas 2 and checker schema 1 round-tripped separately; inspection
had no receipt/actual counts. Repeated checking preserved complete inventories
and bytes. The refined smoke confirmed colour fields are absent from generated
notes/templates/Bases/types while exact original colour evidence remains; a
separate edited copy accepted arbitrary colour-named custom properties without
writes. Nonempty destination refusals preserved caller files. Help and
invalid arguments returned the documented exits. These local smoke results
supplement the public suite and private preservation audit; they make no native
rendering or user-acceptance claim.

The v2 category-presentation wheel and all eight examples also confirmed
Bases immediately follow category headings, introductory category embeds are
absent, category icon properties/assets remain and member snapshots are unchanged.
All 53 wheel module bytes match their current worktree sources. The Category
starter already follows this presentation and remains unchanged.

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
PyYAML is a runtime dependency for the convention checker and is also used by
this data-level regression; the converter continues to serialize through its
existing JSON quoting.

After full independent acceptance, make fresh copies of all three accepted
generated vaults and preserve complete pre-click file inventories/hashes. Open
only those copies in standard Obsidian using Computer and record its observed
version. Join raw-source candidates to independently audited paths/tokens; do
not guess filenames or reuse prototype paths.

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
7. For C, verify all seven category dashboards and their raw-derived membership
   sizes: Book 7, Code Smell 23, Design Pattern 145, Development Practice 1,
   Language 1, Refactoring Technique 16 and Tool 2. Check Members/Gallery,
   Icon-before-Note, no Appearance column, typed empty notes and preserved
   definition-owned content/resources. A/B have no imported thought types.
   Members/Gallery must follow the heading and any Parents/Children navigation,
   with no generated introductory category image; retained source content
   follows the Bases.
8. Exercise live inherited icons, the actual owned override, blank opt-out and
   invalid/nonmember provider controls on disposable copies. Membership order
   must not choose a provider. Keep source identities/dates unchanged and verify
   body snapshots remain independently editable. Source colours stay in migration
   evidence, with no foreground/background colour properties or Base columns.
9. Confirm bundled Templates/Bases settings. Insert a full category template into
   a new note in Editing view; verify insertion-day dates, no imported IDs,
   blank overrides and member discovery. Edit an existing note's membership
   directly. Native rename with link updates must preserve contextual discovery,
   stable IDs and quoted template variables; insert the template after rename.
10. Extend a future category from the generated category/member/Base starters.
    Independently discover handwritten and template-created members. Check
    unambiguous shortened links and report ambiguous required references.
11. Review C's exceptional active Markdown/local image, blockquote/code examples,
    intact PDFs and individual absent-TXT notices. Inspect all four reviewed
    video resources, original URLs and the evidenced 18-second embed where
    service availability permits. Leave playback paused. PDF vault Search and
    remote/offline playback retain their documented limits.
12. Run the public checker on representative valid/invalid current edits. Compare
    complete before/after inventory and bytes for each call; it reports without
    repair. Keep a separate clean actual C copy for the user's verdict.
13. If output defects appear, repair through the responsible public seam, rerun
   affected automatic/independent checks and repeat affected native observations.

No community plugins or replacement discovery features are required. This is
representative presentation review, not every note/PDF page. The user's normal
vault is never used. Ticket 11 records actual-output native evidence, final
two-axis review from completed v1 `f4627d9`, applicable final checks and the
required user's actual converted-vault verdict. Until those pass, v2 is not
declared finished. The [v1 native report](../.scratch/brz-to-obsidian-v1/research/native-acceptance.md)
and earlier bounded synthetic/prototype trials remain historical evidence.

## Recorded versions

The [final actual-output native review](../.scratch/brz-to-obsidian-v2-implementation/research/native-v2-acceptance.md)
records the completed three-vault matrix, read-only edit controls and clean user
copy. The final category-presentation refinement adds five public regression
controls; independent root verification passes 781 tests and Ruff lint/format
on 114 files. Spec/Standards follow-up leaves no findings. The user performed
the revised actual-vault visual review personally and approved it on 2026-10-05;
ticket 11 and the delivery map are resolved. The earlier 776-test/native
checkpoint remains historical. Refinement 14 and ticket 11 record affected
preservation, independent review and the user's final acceptance.

| Component | Verified version |
| --- | --- |
| CPython on native Windows | 3.14.8 |
| Pydantic / pydantic-core | 2.13.5 / 2.46.5 |
| markdown-it-py / mdurl | 4.2.0 / 0.1.2 |
| pytest | 9.1.1 |
| PyYAML (checker/template rewrite regression) | 6.0.3 |
| Ruff | 0.16.10 |
| setuptools / pip | 84.0.0 / 26.2.1 |
| Obsidian native presentation target | 1.13.7 |

`requirements.txt` records the full pinned environment, including transitive
packages. These observed versions establish the tested Windows/Python/app
boundary, not universal platform, later-runtime or Obsidian-version compatibility.
