# Testing and acceptance

## Automated check runner

Every repository agent uses `tools/check.py` for pytest, Ruff lint, Ruff format
checking and dependency consistency (`pip check`). This includes implementers,
reviewers, verifiers, coordinators, exploratory and delegated agents. The rule
starts when the runner and adoption changes integrate together; before then,
existing commands remain usable. Guidance, review, handoff validation and CI
consumption enforce this contract; it does not intercept arbitrary shell commands
or modify external/global agent configuration.

Use an absolute assessed checkout and project `.venv` interpreter. A worktree may
reuse another checkout's interpreter read-only; package installation remains a
separate serialized bootstrap step. Invoke a runner with identical content to
the assessed checkout's `tools/check.py`. The runner checks tools/environment and
binds imports to the selected checkout's source without redirecting an editable
installation or changing the caller's environment. See `README.md` for environment
bootstrap and [workspace housekeeping](workspace.md) for disposable artifacts.

```powershell
$checkout = (Get-Location).Path
$python = Join-Path $checkout '.venv\Scripts\python.exe'
$runner = Join-Path $checkout 'tools\check.py'
# Full existing check set; GUI environment includes the full Windows launcher coverage.
& $python $runner run --checkout $checkout --python $python --environment gui
# One focused public regression file.
& $python $runner run --checkout $checkout --python $python --environment gui --check pytest --test tests/application/test_ui_preferences.py
# Only lint and format checks.
& $python $runner run --checkout $checkout --python $python --environment base --check lint --check format
& $python $runner run --help
& $python $runner validate --help
```

`run` defaults to all four stable check IDs: `pytest`, `lint`, `format`,
`dependency`. Repeat `--check` to select checks and `--test` for repository-relative
test files/directories or pytest node IDs. `-k` and `-m` apply keyword and marker
expressions. With no test selector or expression, pytest selects the full suite;
a selection/expression is focused coverage. The configured full suite discovers
`tests/`; handoff regressions under `.agents/skills/implement-spec-enhanced/tests/`
need their own focused selection. A full receipt covers a focused selector only
when its captured executed node IDs establish that selector actually ran.
Keyword/marker expression requirements need the same executed expression;
a full receipt does not infer whether an expression would select any tests.
Invalid and zero-test selections
cannot qualify as successful execution. The runner offers maintained check
selections, not arbitrary command passthrough, repair or retries.

Use `--environment base` with a Qt-absent environment to establish base coverage,
`gui` with the pinned GUI dependencies installed to establish GUI coverage, or
`auto` for development convenience. Completion requirements name `base` or `gui`
explicitly; auto records its resolved mode. `--require-gui` requires actual GUI
test execution. Merely collecting or skipping GUI tests does not establish that
coverage. Full GUI coverage includes the existing Windows launcher controls.

Each invocation exclusively allocates `tmp/checks/<8-hex>/` in the assessed
checkout, containing `receipt.json`, per-check logs and isolated pytest temporary
and pytest/Ruff cache locations. Logs/receipts stay outside pytest-owned paths.
Use the printed `RECEIPT:` absolute path; preserve failed and interrupted runs as
separate evidence. The runner streams stdout/stderr and retains original bytes
and readable UTF-8 logs. Normal tool failures retain their original diagnostics
and permit later requested independent checks to run once; setup errors,
interruption and changed source leave unrun checks explicit.

| Run exit | Meaning |
| --- | --- |
| `0` | Every requested check completed successfully |
| `1` | One or more tools completed with a normal failure |
| `2` | Setup/execution error or source changed during execution |
| `3` | Incomplete/interrupted execution |

### Requirements and completion evidence

The coordinator/reviewer decides appropriate checks from the ticket and workflow
stage before accepting completion. Record environment, check IDs, full/focused
pytest scope, selectors/expressions and required GUI execution independently of
the submitted results. A full suite is not required for every task; a required
check cannot disappear because a submission omits it or presents a manual entry.
Delegation supplies absolute checkout, interpreter and runner pointers, selected
scope, requirements and receipt destination/contract. Completion reports name
receipt paths and outcomes. Independent fresh verification runs its own runner
invocation and receipt in its assessed checkout.

### Stable-candidate checkpoint

Before completion checks, plan focused development/audit controls and required
completion coverage from the ticket. The coordinator/reviewer records the
environment, selectors/expressions, full/focused scope and freshness independently
of the implementer's results. Complete relevant focused controls through the
accepted public testing seams and resolve known findings before launching
expensive full completion suites. In the handoff dispatch handshake, these are
the development checks finished before committing; expensive completion suites
follow the commit, before reporting the checked candidate. Focused receipts may
precede the commit under the content-binding rules below.

The checkpoint is complete when those focused controls pass, known findings are
resolved, integration synchronization is finished, and the candidate source is
committed in a clean checkout. Record the full candidate commit ID. Run required
completion checks against that stable source through the runner, retaining and
validating receipts bound to that commit. Keep source unchanged during execution
and until publication; the runner's snapshots detect changes during a run.
Focused success cannot replace coordinator-assigned full base/GUI or other
required coverage. Tickets requiring only focused coverage retain that scope;
independent verification still uses its own assessed checkout and fresh execution.

A repair during or after completion checks returns to this checkpoint: resolve
the finding, complete affected focused controls, commit a new stable candidate,
then obtain qualifying completion evidence and independent verification for it.
Preserve earlier receipts with their original source and outcomes. A changed
source snapshot cannot qualify a run as passing; a completed receipt for an
earlier source remains evidence for that source. Evaluate existing evidence
against the new candidate and requirements using the binding and reuse rules
below and the handoff contract. Retain applicable unchanged evidence with explicit
provenance and rationale where reuse is allowed; rerun affected checks and every
check requiring fresh execution. This checkpoint reduces avoidable replacement
full runs; later discoveries still require repair and a new candidate.

### Requirements format and receipt validation

The public runner validator accepts a separately supplied schema-1 requirements
JSON file. For example, focused base pytest plus lint:

```json
{
  "schema_version": 1,
  "environment": "base",
  "checks": [
    {
      "id": "pytest",
      "scope": "focused",
      "selectors": ["tests/application/test_ui_preferences.py"],
      "keyword": null,
      "marker": null,
      "require_gui": false
    },
    {"id": "lint"}
  ]
}
```

```powershell
& $python $runner validate --receipt 'C:\checkout\tmp\checks\1234abcd\receipt.json' --checkout $checkout --requirements 'C:\checkout\tmp\effort\required-checks.json'
```

Validation exits `0` only for passing evidence meeting the supplied requirements;
`2` means rejection. It checks schema, selection, environment, completed results,
source binding and referenced evidence digests. Missing, truncated, altered, stale,
wrong-checkout and insufficient-scope evidence fail. Validate before accepting
check claims in reviews, issue completion or qualifying handoff transitions. A
text log or manually written passed value is insufficient. Honest failures remain
failed evidence; a later successful run cannot erase the earlier result.
`validate --allow-failed` permits read-only integrity inspection of an honestly
executed failed receipt for a held/failed verdict. Its acceptance is not passing
completion evidence; ordinary completion validation omits this option.

Receipts preserve unique run identity, checkout, original Git revision/dirty state,
source identity, runner identity, interpreter/tool versions, resolved environment,
argument arrays/CWD, selectors, timestamps, check/aggregate results, executed and
skipped test counts, and evidence digests. The before/after snapshot covers tracked
and nonignored new repository files, including source, tests, tools/configuration
and current guidance. Ignored private data, environments and generated output are
excluded. Git-normalized content identifies the candidate while separate disk
SHA facts describe the bytes executed; a source change during execution prevents
passing evidence.

A pre-commit receipt can bind to a later clean commit only when the relevant
Git-normalized tested contents remain identical. Validation preserves original
revision and dirty-state facts.

Git reads checkout-relative paths so scoped `.gitattributes` rules apply,
including the authored CRLF fixture's `-text` exception. Reference binding cleans
historical blobs under the reference tree's effective attributes/filters rather
than assuming every stored blob was already normalized. This uses Git's
[`--attr-source`](https://git-scm.com/docs/git/2.43.0#Documentation/git.txt---attr-sourcelttree-ishgt)
support (Git 2.43 or later); receipts record the Git version.

For equivalent contents in another checkout,
provide `--reuse-reason` with explicit original context and applicability; this is
reused evidence, not an independent fresh run. `validate --ref FULL_COMMIT` binds
the receipt to that Git tree instead of the checkout's current files; stage
requirements select the candidate/result commit independently. Disk changes
during execution invalidate a receipt even if Git normalizes their line endings.
The runner removes inherited `PYTEST_ADDOPTS` and `PYTEST_PLUGINS` from children
so caller options cannot silently narrow the declared selection.
Reviewers judge whether declared
coverage fits the ticket. Receipts establish execution and integrity facts, not
security attestation against deliberate forgery.

The [enhanced handoff contract](../.agents/skills/implement-spec-enhanced/references/handoffs.md)
is authoritative for structured per-stage requirements, publication commands,
current versus historical schema, reuse and transition validation. Its separately
authored requirements bind the stage/ticket/candidate and assessed result; they
must accompany candidate, verification and integration publication and standalone
validation. Historical records remain byte-preserved and readable as historical
evidence. New transitions use the current contract. An explicit historical reuse
retains its source and rationale and cannot satisfy a fresh execution requirement.
Manual/native observations retain their separate acceptance boundaries.

### Bootstrap and runner-failure investigation

Direct covered-tool execution is permitted only when bootstrapping the runner or
investigating a concrete runner failure that prevents it from supplying necessary
evidence. Record why the runner cannot be used, the exact command, interpreter,
checkout and result. Label this bootstrap/diagnostic evidence; it cannot qualify as
normal completion verification. After repair, run qualifying final checks through
the runner and validate receipts. Package installation, build tooling, native
observations and separately specified private acceptance drivers retain their own
documented routes. Runner receipt/log directories are immutable evidence; retain
needed conclusions and pointers before retiring the ignored effort artifacts.

## Optional GUI checks

The UI adapter lives in `src/brz2obsidian_ui`; the application operations,
host-lifetime session and hidden worker are Qt-independent. Qt-dependent checks
under `tests/gui` carry the `gui` marker and skip during discovery when PySide6 is
absent. Install the pinned `requirements-gui.txt` only for GUI development.

The runner sets the offscreen platform for GUI checks. With the absolute paths
from the runner examples above:

```powershell
& $python $runner run --checkout $checkout --python $python --environment gui --check pytest -m gui --require-gui
& $python $runner run --checkout $checkout --python $python --environment base --check pytest -m 'not gui'
```

The marker selections above are focused; use a full GUI run when full GUI and
Windows launcher coverage are required.

The injected public UI seam accepts session commands and presents immutable
snapshots. Deterministic barriers hold inspection, conversion, vault checking, destination
validation and diagnostic preparation while queued GUI input is processed,
before releasing work. Real hidden-worker
checks cover correlation, UTF-8 framing, separate concurrent pipe draining,
bounded output, launch/crash failures and safe diagnostic omission. Static and
import-blocked checks keep backend/CLI use independent of Qt. Launcher checks
exercise Unicode/spaced source roots, an unrelated CWD and readable setup errors.
Destination checks also cover reserved/nested names, populated and reparse targets,
unchanged inventories, no write probes, stale/coalesced revisions, independent
retained inspection results, adjacent errors/path order and narrow field stacking.
Publisher and CLI controls preserve final safety and creation of missing parents.
These controls do not establish final native appearance, platform-dialog behavior
or actual user acceptance. Use the generated local launcher for strategically
sampled Windows observations and retain requirement IDs/evidence in the ticket.

`tests/gui/test_transport_parsing_window.py` holds the public response decoder
after an actual hidden Inspect worker has exited and its pipes have drained.
Queued heartbeat/disclosure input, repaint, stable busy inputs, primary gating
and deferred Close must complete before the decoder is released. The original
decoder then validates the real response and correlation; the window receives
the actual clean inspection result and the source bytes/inventory stay unchanged.
The bounded wait is a test guard, not an operation timeout or worker-kill policy.
The [Windows UI acceptance record](history/windows-ui-acceptance.md) summarizes
the integrated automated/native checks and their retained evidence limits.

Checker controls exercise actual clean/issues/failed hidden workers, strict
checker-only aggregate counts, safe diagnostics, deliberate retries and unchanged
file/directory inventories and bytes. Native synthetic clean/issues selection and
picker cancellation supplement public GUI responsiveness/deferred-Close checks.

Diagnostic controls exercise public generation/action admission, same-revision and
identical-result replacement, worker-exit lifetime, bounded selectable pages,
complete/omitted Unicode copy/save round trips and nonfatal failures. Injected UI
barriers hold preparation/export while queued input/repaint and Close are processed;
stale save callbacks, queued exports and paged callbacks cannot use an old report.
Failed diagnostic saves retain the explicitly selected target as exact selectable
path text, including unexpected adapter exceptions, without replacing the main
result or report. Public adapter/runner and GUI controls cover Unicode/spaced
targets, preserved existing bytes, exception privacy, new action/cancel/success
clearing, and rejection of delayed paths after identical-result replacement.
An offscreen, nonnative Qt dialog control verifies Save starts in the absolute
home directory despite an unrelated working directory, retains its report
filename and returns focus on keyboard cancellation. Its Qt settings use only
test-owned INI files; the control does not invoke a native dialog.
Native synthetic clipboard paste and asynchronous Save cancellation/local UTF-8
readback supplement these controls; final independent presentation/user checks remain
separate.

Reviewed conversion controls exercise actual public Workflow/Publisher and hidden
worker boundaries. They compare all source identity and converter/profile facts
at the rendered publisher boundary, preserve custom adapters/metadata, and verify
zero publisher calls and unchanged inventories for stale reviews. Real controls
cover destination races, source mutation, path/manifest limits, permission and
disk-full-equivalent failures, exact cleanup guidance and late verified receipts.
Session and injected UI controls distinguish known not-started from uncertain
termination, require fresh validation after failure, and retain actual receipt
paths without directory inference. A synthetic native clean conversion supplements
these controls. Standalone carry and explicit warning-action controls preserve the
source/opaque review, reject refused/failed carry, and ensure tab changes do not
authorize warnings. The host snapshot supplies a strict conversion primary-action
fact independently of destination readiness; actual widget controls observe every
review-field access to keep the returned review opaque, including after checker
results replace inspection presentation. Real warning workers publish with verified receipt/exit2;
missing/stale authorization and incompatible identity/profile/converter facts
produce no publisher delegation. Same-path fresh review requires a new explicit
authorization; malformed warning receipt facts never imply a created vault.
Completion controls exercise current verified-receipt admission, stale/closed/busy
intents and atomic selection of the published folder for explicit checking. The
independent selector remains disabled without its own visible selection. Outer
adapter controls verify Unicode/spaced paths, path-free Obsidian vault-manager
requests, missing targets and safe native failures without file changes. Obsidian
feedback uses the admitted report's folder even when an adapter returns an
untrusted path or raises; report admission remains unchanged. Public Qt clicks
observe first-open guidance and exact copyable folder feedback for successful
dispatch and handler failure. Independent actual Windows verification separately
confirms that the installed URI handler opens the vault manager.
A deliberately blocked filesystem check re-admits immediately before dispatch;
the runner never holds the session lock across platform work. Injected UI controls
retain clean/warning/late-error results on open failures, process Qt events during
blocked dispatch and run the actual checker worker against the published target.
Normal conversion completion and deferred Close start no open/check action.
Final independent/native user acceptance remains separate. Single-instance and
preferences have separate controls below.

Independent accepted-presentation controls in
`tests/gui/test_accepted_presentation.py` derive task order, outcome wording,
publication replacement and action placement from canonical specification #92
and its exact C reference. Actual Qt keyboard events exercise forward/reverse
control order, selectable diagnostic text, narrow reflow and scrolling. Deliberate
wrong-title, hidden-action and swapped-tab controls prove the presentation
assertions reject incorrect output. Read-only path displays wrap arbitrary
unbroken Windows segments without inserting break characters into the selected
text; actual document line bounds, full height and exact selection are checked
at a narrow width. Existing completion and diagnostic controls
also hold asynchronous actions open: focus returns to the invoked action when
the user has left it unchanged, while later keyboard navigation takes precedence.
Narrow recovery controls keep contextual footer guidance and every current action
readable, and wrap previous destinations within the scrollable sheet. Keyboard
selection controls cover partial Unicode path/report selections as well as Select
All; copied path and recovery text retain the original characters and paragraphs.
Findings controls cover long unbroken checker filenames and owned cleanup paths:
the prominent read-only panel wraps within the task sheet without nested scrolling,
and exact leftover paths remain selectable in adjacent recovery guidance. Checker
file findings identify the affected file without suggesting a staging leftover.
These checks complement strategically sampled Windows scaling, contrast and
dialog observations; they do not establish comprehensive assistive-technology
certification or the final independent/user verdict.

### Local startup and preference controls

`tests/application/test_ui_preferences.py` exercises canonical persistence effects
and the atomic public `ApplicationSession.dispatch_if_current` revision guard.
Deterministic blocked reads/saves verify newer input still reaches the serialized
runner, stale startup delivery cannot overwrite it, stale failure feedback is
discarded, and saves retain their admission order. The closed session command
vocabulary is unchanged.

The Qt-independent preference, activation and startup adapter controls under
`tests/gui` run in the headless selection. They use actual UTF-8 preference bytes,
loopback connections and separate processes in unique pytest-owned directories.
Only the disposable adapter crash fixture is deliberately terminated. Controls
verify parent-only content, safe corrupt/unavailable handling, retained prior
preferences after replacement failure, activation-only authenticated messages,
CLI independence, foreground-denial attention and crash-stale recovery. A live
lock owner is never replaced because its endpoint is temporarily unavailable.
Relative, drive-relative, root-relative and invalid configured preference roots
are rejected before filesystem access; public controls prove no CWD writes from
either `LOCALAPPDATA` or an explicit preference adapter directory.

`tests/gui/test_local_startup.py` uses offscreen Qt with synthetic user-profile
roots. A blocked preference read leaves a queued Qt heartbeat and newer input
responsive before release. A separate control proves unavailable preferences
permit a usable empty launch while ownership still prevents a second window.
These controls inject the native foreground boundary and do not establish actual
Windows activation or presentation.

Preferences live only in `%LOCALAPPDATA%\brz2obsidian\preferences.json`.
Transient activation registration and its OS-held byte lock are separate, under
`%USERPROFILE%\AppData\Local\Temp\brz2obsidian`; this relies on the signed-in
user's private profile permissions and uses no shared/system-temp or checkout
fallback. Registration contains only a port and random authentication token;
normal close removes it, and crash recovery replaces it only after acquiring the
released lock. An unavailable coordination location safely refuses startup.
No operation history is stored there and no converter/CLI lock is involved.

Actual local-build acceptance must separately sample two launches, existing
window restoration or attention, unchanged active inputs, parent-only fresh
launch behavior, one corrupt-preference case and an idle test-owned crash/stale
relaunch. Preserve any pre-existing preference bytes before those controls and
retain local environment, assessed source hashes and observations in the ticket's
ignored effort evidence. Do not terminate an active conversion or a user-owned
process for this sample. Final presentation and the user's verdict remain their
separate gates.

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
formed the earlier 121-test group.
False receipts are rehashed and recounted consistently before the oracle rejects
incorrect assignments, materialization, icons/dates, note/reference evidence,
TXT/PDF/video facts, Bases/templates/configuration and required support. The
expected-fact modules import only the standard library and local oracle modules;
production manifests/counts do not provide expected preservation facts.
The v3 extension independently derives included scope and ownership, retained
safe evidence with exact JSON numbers, safe-original eligibility, whole excluded
reference-phrase removal, every supplied-body edit, absent declarations and their
owned image basis, neutral category providers and explicit overrides. It checks
complete note bytes, canonical generated-image order and separate reference credit,
full category hierarchy/membership/support, raw diagnostic facts and resolving
owner/provider/member/image links, scoped digest and exact payload bytes.
Original record ordinals remain private audit facts. Public `thoughts.json:N`,
`attachments.json:N` and similar pointers address the retained safe evidence
tables; they are not physical original JSON-line ordinals. An excluded-first
control verifies this difference without adding an excluded ledger to a vault.
Nested/escaped/serialized ownership, safe evidence/precision, missing/duplicate/
misowned/reordered embeds, fabricated originals/Documents/reference credit,
provider/override effects, graph/navigation and diagnostic corruptions are rejected
after actual file receipts are consistently rehashed and recounted. Residual proven
excluded identities in inactive literals refuse the audit, including canonical
UUID case, percent and Unicode spellings. Compact identities remain case sensitive.
Omission of the exact original backup alone does not make that destination safe.
Authored reference labels are interpreted separately from body spans; emphasis,
code, entities and escaped literal punctuation retain their displayed text while
untouched CRLF/CR/LF body spans remain exact.
The earlier oracle/driver baseline passed 243 public checks: the 115 earlier oracle
controls, 116 v3 controls and twelve driver controls. Escaped opening/closing and
balanced bracket labels retain richer record display text separately from sanitized
wiki aliases; nested active phrases and incomplete local destinations remain closed.
Three corruptions still pass
the source-free convention checker after consistent rehashing; the raw-source
oracle rejects their changed body, generated order or diagnostic facts.

Repeated local member declarations receive a narrowly bounded raw-source audit
exception only when every row has a distinct trusted identity, SourceType 2,
Type 15, NoteType 0, a positive integer declared length, state 2, a safe TXT path,
string Name metadata, false Is* flags, null/empty custom type metadata and
physical ZIP absence. The raw scope retains
each included declaration and independently omits an eligible excluded-owner
group. Existing per-declaration auditing still requires intact same-owner PDFs;
zero-length TXT/PDF handling retains its separate reviewed rule. Public controls
cover both row orders, unsupported group members and complete forgotten omission.
A five-pair plus three-single fixture requires thirteen distinct warnings,
evidence pointers and observations with no invented payload or reference credit.
Semantic corruption controls repair actual receipt hashes and counts before
checking collapsed declarations/warnings, paired lengths/evidence and fabricated
bytes/reference credit against the raw source.
Malformed names, unknown active/nonboolean Is* flags and populated/nonstring
custom attachment types refuse before excluded-group omission. A complete forged
vault/receipt control rebinds the source fingerprint and repairs every actual file
hash while confirming that an excluded invalid role still refuses; the adjacent
false-flag control passes with the same source/receipt rebinding.

The independent image interpreter uses standard-library Python imports and existing
Windows WIC codecs through `ctypes`, never production image helpers or Pillow.
It forces full BGRA pixels for every accepted frame and reports decoder CLSID,
name/version and completed-frame counts. PNG additionally requires independent
chunk/CRC/order, complete zlib, exact scanline/filter and reconstructed palette
checks, including Adam7 passes. WebP headers/container structure alone cannot pass.
Invalid data raises an assertion; missing codecs/native libraries, platform or
resource limits raise `AuditUnavailable` and do not certify image eligibility.
Strict APNG frame-stream validation is currently unavailable. The host's existing
Microsoft WebP image extension is a native dependency, with no installation step
performed by this tooling. Public controls include valid PNG/WebP, Adam7 and all
PNG filters, reconstructed indexed palettes and a two-frame GIF, plus header-valid
compressed failures, repaired PNG CRCs/ZIP CRCs/lengths/hashes, scanline/filter/
palette failures and injected native-library unavailability. Full-source and native
Obsidian gates remain separate from this source-required oracle and source-free
`check_vault`.
Refinement controls reject obsolete colour fields in generated notes, templates,
starters, Bases, property typing and guide while still rejecting falsified source
colour evidence. The checker permits manually added colour-named properties as
ordinary custom extensions.
See [current complete preservation](history/brz-to-obsidian-v2-implementation/research/colour-property-refinement.md),
the [historical pre-refinement v2 report](history/brz-to-obsidian-v2-implementation/research/three-archive-preservation.md)
and the [earlier v1 report](history/brz-to-obsidian-v1/research/real-export-acceptance.md).

## Combined external/literal/image preservation audit

The public combined ZIP and Workflow/CLI controls cover an external-file-only
owner, distinct external and copied PDF resources with the same label, active
literal edits interleaved with live references, two same-filename images owned by
two different thoughts, protected Markdown, Home, tags/categories, forgotten
associations and established TXT/PDF/type gaps. Inspection creates no receipt or
output; conversion reopens the source. The alternative Folio control composes
opaque text edits, presentation declarations and external-file facts without BRZ
syntax in generic modules. All shared contracts remain version 6. The only runtime
repair in this extension sorts sizing-report documents by identity, preserving
within-document authored reference order; it changes no admitted meaning or fields.

The oracle uses raw records and archived note/payload bytes as authority. Its
standard-library activity scanner masks fenced/indented/inline code, comments,
escapes, autolinks and balanced reference destinations/titles while retaining
active labels. Unsupported active HTML and source-local autolinks fail closed.
Protection is lexical rather than successive global regex masking: leaf blocks
are resolved first, then a matched inline code span or comment owns its contents
in source order. Comment blocks protect their closing line or continue to the
end of their container; unterminated inline openers do not acquire that rule.
Backtick matching stays within an inline region and cannot cross blank lines,
fences, container exits, headings or thematic breaks. Only CR/LF delimit source
lines; raw Unicode coordinates and authored bytes remain unchanged. These
boundaries follow the [CommonMark block grammar](https://spec.commonmark.org/0.31.2/#html-blocks)
and [inline precedence](https://spec.commonmark.org/0.31.2/#code-spans), with actual
ZIP/CLI byte, span and rehashed-corruption controls in `test_activity_boundaries.py`.
State-map keys and identity ownership are checked globally. Scalar state values
are checked only after independently deriving direct and transitive forgotten
omission; malformed excluded values cannot block an audit or appear in its output.
Malformed included values and unknown state keys still refuse.
HTML element boundaries use the [WHATWG element index](https://html.spec.whatwg.org/multipage/indices.html#elements-3)
and [obsolete features](https://html.spec.whatwg.org/multipage/obsolete.html#non-conforming-features),
reviewed 2026-10-09, independently of production metadata. Protected matching-looking end tokens never pair with active
openers. Scoped text follows whole excluded-phrase removal; literal edits retain
Unicode codepoint spans and scoped digest before escaping, adapted spans/digest
before reference rewriting, and exact before/after text. Every safe original copy
remains byte exact; unsafe copies remain absent. Sizing declarations have exact
adapted-document spans, digest and affected owner/document/image/reference evidence.
Distinct external identities, original locations and file URIs remain separate
from copied bytes, actual references, generated fallback and source-gap warnings.

Rehashed/recounted corruptions cover dropped/merged external IDs, URI/location,
under/overescaping, spans/bases/digests, wrong image owner/bytes, omitted sizing
warnings, excluded output and invented counts. Actual publication controls cover
new note/image/report/record staging writes, deletion/truncation/same-length
corruption, source drift, image stream faults, commit races, junctions/cleanup and
late teardown/post-commit failures with truthful complete receipts.

The current driver requires five originals and audits fifteen exact/repeat/
ZIP-and-root-reordered outputs. It inventories every raw stream before inclusion,
requires exact E totals of 756 thoughts, 963 links and 1,364 attachments, and pins E
to 219,504,950 bytes with SHA-256
`bc55f68c9ab3febaa770bfc7a9a90621bcd82107d876664371e1ff8558b4cf68`.
E's independently derived included gates require 17 external files, five literal
owners and two sizing references in two distinct owners. Complete owner resources
are audited by raw IDs/member joins; three same-label PDF entries are a subset,
not a total-resource assumption. Each conversion obtains a fresh CLI inspection,
checks identity/count/diagnostic parity and retains complete raw audits, input
fingerprint guards and the A–D established scoped obligations. Synthetic pins
exercise the same driver without private inputs. Public success does not establish
actual E support: further unsupported relationship signatures remain a separate
bounded ticket (#145), followed by actual matrix, native and user acceptance gates.

## Private full-export acceptance

The complete v3 four-original gate passed on 2026-10-06 at verified clean root
`e2c5fc3f05d2daa0d0547d2bbaa2b12557a248b5`, in fresh `tmp/m5`. All twelve
A/B/C/D exact/repeat/reordered outputs passed the driver and a separate complete
raw-source/result/receipt re-audit. Four reordered-source proofs and eight vault
comparisons passed; all 7,029 matrix files stayed unchanged. Original D's 359
supplied bodies, 63 original fallback images, 47 definitions/330 included members,
distinct type/icon/TXT facts and full ownership/byte/graph/privacy obligations were
checked by source identities and joins. All four originals and 562 retained-vault
files stayed unchanged. Twelve library plus twelve CLI source-free checks were
clean and read-only; they supplement source-bound preservation.

The failed m3 source/oracle duplicate-declaration gate and m4 diagnostic-alias
gate remain retained history. Responsible public-seam repairs were independently
verified before m5; no recovered original or weakened oracle substituted for a
fresh matrix. See the [complete four-original result and failed history](history/management-leadership-implementation/research/four-archive-preservation.md).
The ignored raw-source handoff joins actual note/image paths, all supplied bodies,
D's 47 category/330 member paths and C's 7/195 control memberships for later native
review. [Actual-output native review](history/management-leadership-implementation/research/native-v3-acceptance.md)
subsequently passed in observed Obsidian 1.14.4. Actual user acceptance and
independent final review remain pending; this automated gate supplies neither verdict.

Choose the exact fingerprinted A/B/C/D/E originals and a fresh short ignored output
directory. D is the original Management & Leadership export (320,594,486 bytes,
SHA-256 `2b24c1d21b4090f3b0ed3ec0227f269b8c7a4e5b6832ada0e244a1dcfc941ced`);
a comparison/recovery backup cannot substitute. A/B/C fingerprint pins are retained.
The current driver refuses an existing output directory, performs fifteen complete
conversions (exact, repeat and ZIP/root-record reordered for each source), saves
private results/operation evidence, and prints aggregate counts. It checks source
fingerprints before/after every operation and at completion, proves reordered
root-record multisets and physical bytes independently, and verifies the selected
worktree import/current `0.3.0` version. Expected preservation comes from raw scoped
records for each original; the old unscoped v2 A/B/C totals are historical evidence.
D's accepted aggregate inventory gates supplement the complete raw-source audit.
Generated image/member/diagnostic ordering remains contractual during comparison;
only documented provenance/run/fingerprint differences are normalized.
Set PYTHONPATH even in the integration checkout.

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = (Join-Path (Get-Location) 'src') + ';' + (Get-Location)
$sourceA = 'C:\path\to\exact-A.brz'
$sourceB = 'C:\path\to\exact-B.brz'
$sourceC = 'C:\path\to\exact-C.brz'
$sourceD = 'C:\path\to\Management & Leadership 2026-10-05.brz'
$sourceE = 'C:\path\to\exact-E.brz'
$output = Join-Path (Get-Location) 'tmp/audit-01'
.\.venv\Scripts\python.exe -m tests.local_acceptance.run --source-a $sourceA --source-b $sourceB --source-c $sourceC --source-d $sourceD --source-e $sourceE --output $output
```

The synthetic tooling example alone supplies no private-input acceptance; the
completed four-original gate is recorded above. The public
synthetic example below exercises the same five-input callable with explicit
independently computed synthetic pins, producing fifteen complete outputs in a
fresh ignored directory. The CLI always uses the accepted original pins.

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = (Join-Path (Get-Location) 'src') + ';' + (Get-Location)
.\.venv\Scripts\python.exe -m tests.local_acceptance.run --help
@'
from pathlib import Path
from tests.local_acceptance.run import fingerprint, run_acceptance
from tests.local_acceptance.test_checker_v3 import mixed_v3_archive
from tests.support.combined_collection import combined_archive

root = Path('tmp/audit-synth-02')
root.mkdir(parents=True, exist_ok=False)
sources = {key: (combined_archive if key == 'E' else mixed_v3_archive)(root / (key + '.brz')) for key in 'ABCDE'}
pins = {key: fingerprint(path) for key, path in sources.items()}
run_acceptance(sources, root / 'out', pins)
'@ | .\.venv\Scripts\python.exe -
```

The earlier four-input example and help were executed on 2026-10-06 against selected `0.3.0` code.
All twelve complete synthetic outputs passed, each with 29 files, five created
notes, six exact payload copies, three source gaps, two generated embeds and two
fully decoded PNG/WebP frames. The original synthetic fingerprints remained
unchanged. The mixed source also retains an included image whose bytes equal an
excluded owner's image; scope follows independently derived ownership.

The earlier v2 nine accepted conversions passed independent comparisons with exit 2.
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

## Visual sampling policy

For native source diagnosis or recovery experiments, use
[bounded native investigation](agents/native-investigation.md).

Use strategic sampling for visual and native reviews in this repository, as
requested by the user on 2026-10-06. Select a small set of actual-output cases
covering each distinct rendering or application behavior. Include unusual source
syntax, media formats, missing-content and icon/provider states, hierarchy shapes,
large contextual views, and the editing/template operations affected by the change.
Combine behaviors in one sample where practical and reuse completed observations.

For application UI, apply the requirements in the
[presentation procedure](agents/accepted-presentation.md#3-verify-actual-presentation-independently)
with this sampling method:

1. Inventory each control type, distinct style/rendering context and relevant
   state in the UI under review. Include controls initially hidden by overflow,
   scrolling, expansion or application state. Group equivalent instances; select
   representative controls for every distinct group, combining cases where
   practical. Sample enabled/disabled, focus, hover and expanded states where
   relevant; record any relevant states that remain unobserved. A distinct styling path
   or rendering context needs its own sample, not an exhaustive instance/state
   matrix.
2. Record each group's applicable reference and planned appearance/interaction
   observations before using the app. In the actual application, compare the
   representative controls with that reference and exercise their interactions.
   Reveal initially hidden controls in the relevant context. For scrollbars,
   explicitly observe track and thumb visibility against their surroundings and
   verify that dragging the actual thumb moves the content; also exercise wheel
   and keyboard access where applicable. A scroll-reachability test or offscreen
   drawing alone does not establish these appearance and pointer observations.
3. Record the observed states, evidence and satisfied/failed/unverified status
   for each group and affected requirement in the review record. Reuse applicable
   evidence for equivalent instances, identifying what it covers; missing or
   inapplicable evidence leaves required coverage unverified. Expand samples
   around defects, uncertainty or meaningful differences, then repair and recheck
   affected failures before completing the review.

Before using the UI, record the chosen cases, their independently derived paths,
the behaviors each covers, and any special cases needing their own observation.
Before opening an imported note, verify that its subject is included, its assigned
target is expected to be created, and that exact file exists in the review copy.
Check intentionally uncreated targets through their links or listings; opening a
missing target can create a new blank note and does not verify converter output.
Compare sampled native Base results with the expected member set for that view;
native CSV export can provide complete results for a large sampled view. Equivalent
items using the same behavior need no repeated visual check. Expand the relevant
samples when a defect, uncertainty or meaningful implementation difference appears.

Complete when every required control group, selected behavior and special case
has applicable actual observation evidence and any defects have been repaired
and rechecked. Report the sample selection, covered behaviors and limits; extrapolated confidence in equivalent
cases is distinct from observing each item. Complete required automated source,
body/image, inventory and preservation audits keep their full scope. Actual user
acceptance remains a separate gate when required by the accepted specification.

For the first local Windows UI, the owner's
[current scaling decision](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/92#issuecomment-6077040155)
requires **100% only**, with the normal **100%** display setting left unchanged.
Keep narrow-window, long-path/findings, stacking, scrolling, keyboard and usable
footer checks. Do not change system scaling or sample other scales. Earlier
100%/125% reuse, 150% uncertainty and BLOCKED records retain their historical
scope; owner corrections do not turn old uncertainty into passing observations.
Independent applicable 100% observations are required before review PASS, and
the user's actual running-app verdict remains separate.

The UI-P11 scrollbar correction uses Qt's platform style instead of a custom
scrollbar theme. Background paint is scoped to plain containers rather than all
QWidget subclasses; inherited typography and targeted sheet/control colors remain
in place. Because C is explicitly light, MainWindow requests Qt's application-local
Light color scheme before constructing controls. This retains the platform style
and does not change Windows theme preferences. A Windows11 dark-scheme thumb can
otherwise paint white against the light sheet; a widget palette alone does not
select that native thumb color. See [QStyleHints](https://doc.qt.io/qt-6/qstylehints.html#colorScheme-prop).
Existing public GUI controls exercise scroll reachability, exact wrapped
paths, narrow/short reflow, keyboard/focus and the anchored footer. Offscreen
style comparisons diagnose platform delegation, not actual Windows appearance.
Offscreen QPA may ignore color-scheme requests; an unchanged Unknown scheme cannot
prove actual Windows contrast. Public QStyle drawing can isolate the scheme cause,
but cannot establish pointer usability in the maintained product.
Independently sample the actual task-sheet and diagnostic scrollbars at 100%,
including wheel, thumb drag and keyboard access; previous scrollbar observations
cannot establish this changed appearance. No CSS-mirroring or screenshot-pixel
oracle is needed as a permanent test.

## Native review procedure

Apply the sampling policy above to new reviews. The v1/v2 procedures and completed
reports below retain their historical scope; choose representative cases from
their behavior lists for current work.

The [v2 dashboard slice](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/27)
has an earlier bounded native gate on a fresh review copy of an actual synthetic
converter output. Use valid distinct image payloads and check contextual
membership, role/support exclusions, table/card images, provider/override edits
and a native link-preserving category rename. Keep the exact published baseline
unchanged. Public ZIP/workflow tests check generated obligations and byte
preservation; the native check verifies Obsidian evaluates those queries and
images. This early check remains separate from final complete-output acceptance.

The [v2 templates slice](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/28)
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
declared finished. The [v1 native report](history/brz-to-obsidian-v1/research/native-acceptance.md)
and earlier bounded synthetic/prototype trials remain historical evidence.

## Recorded versions

For the Management & Leadership extension, the
[actual-output native report](history/management-leadership-implementation/research/native-v3-acceptance.md)
records strategic rendering/maintenance samples, the retained complete D native
ledger, native C CSV correspondence limits and independent read-only checker
controls. The observed app was 1.14.4, while the earlier stored target below
remains 1.13.7. Native review does not supply the final user's actual-vault verdict.

The [final actual-output native review](history/brz-to-obsidian-v2-implementation/research/native-v2-acceptance.md)
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
