# Windows UI acceptance record

The integrated Windows UI completes the synthetic offline Inspect → Convert →
Check workflow. The final automated acceptance selection passed **1931 tests**,
including **102 optional GUI controls**, on 2026-10-09. This implementation record
supports [acceptance ticket #104](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/104)
under [canonical contract #92](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/92).
Independent actual-app review (#105) and the user's running-app verdict (#106)
remain separate gates.

## Candidate and environment

The incorporated base is `12cf70e4af2d12af8348130faffd8a3aca31acdd`, captured before
final checks. This slice adds only a public GUI acceptance control and testing
documentation; production code, dependencies and wire/session contracts are
unchanged from that runtime. The committed candidate and complete command/evidence
manifest are bound by the coordinator-assigned #104 handoff.

Checks used the primary project virtual environment and explicit assessed-worktree
`PYTHONPATH`, without changing the shared editable installation. Observed versions
were Windows 11 build 26100, CPython 3.14.8, application 0.3.0, PySide6/Qt 6.12.0,
Pydantic 2.13.5, pytest 9.1.1, Ruff 0.16.10, pip 26.2.1 and setuptools 84.0.0.

## Automated acceptance

The one fresh full suite passed **1931 tests in 428.99 seconds**, with offscreen Qt
installed and an ignored observer ready to retain safe returned conversion/workflow
diagnostics on failure. No failure or repeated full-suite run occurred. The
explicit GUI collection selected 102 of those tests. With Qt imports deliberately
blocked, CLI help and public operation/protocol/host imports succeeded and base
discovery collected 1829 tests. The full suite includes schema/correlation checks,
static imports through type-only branches and package initializers, inward
dependency checks, and actual public/CLI imports with GUI dependencies blocked.

Ruff lint, Ruff formatting (243 files) and `pip check` passed. The local wheel and
maintained launcher built successfully; all 72 wheel Python modules matched the
assessed source bytes. These checks establish a local build, not packaging or
distribution acceptance.

The added response-parsing control uses the actual hidden Inspect worker and
public response decoder. It holds the decoder after the child has exited and
both pipes have drained. Before release, queued heartbeat/disclosure input and
repaint complete, selected input stays stable, primary controls remain gated,
no terminal result is applied, and Close is deferred while the window remains
visible. The decoder runs outside the Qt thread. Its original validation then
correlates the real response, supplies clean inspection and completes deferred
Close without changing source bytes or inventory. Its first run passed against
unchanged production; no product defect or artificial red result is claimed.

Existing controls cover blocked Inspect/Convert/Check, slow destination validation
and preference loading, diagnostic preparation/export, elapsed guidance and
deferred Close. Real worker/failure controls cover schema/ID/operation mismatch,
encoding/Unicode/spaces/unrelated CWD, malformed/missing/extra/oversized output,
concurrent pipes, launch failure versus child termination, warning/check exit 2,
late verified receipts, unknown publication, stale source/destination changes,
write/cleanup failures and unchanged caller/source/published inventories. Test
guards introduce no production cancellation, worker-kill or automatic retry rule.

## Actual maintained workflow

Root observed the maintained local launcher from an unrelated working directory,
using the exact unchanged runtime base above. The human's current normal Windows
scale was 100%; this sample changed no display setting. One fresh synthetic
archive and destination supplied the entire workflow:

- The native source chooser selected a long Unicode/spaced path. Standalone
  Inspect reported clean review with planned counts, unchanged source and no
  output.
- Explicit **Convert this archive** retained the review. The native parent picker,
  vault-name editing, full destination preview and fresh validation preceded an
  explicit Convert. Publication supplied a verified receipt, 18 files and one
  actual imported note. Four optional actions appeared; none ran automatically.
- Explicit **Check vault** selected the verified target and ran the actual
  read-only checker: 18 files, seven Markdown files, four Bases, seven/four
  successfully read and one imported note. Complete file/directory inventories
  and all 18 file hashes matched before/after checking; source SHA-256 remained
  `99975825df23d100f425f0ebc81ea3bd51f6d09251ed3ec2af05201c4fa6c8e2`.
- Normal Close ended the app. Generated preferences contained only the output
  parent; original preference absence was restored. All ten runtime hashes and
  the current seven baseline window IDs matched before/after, with no test app
  or Settings left open.

The bounded case used 19 native input attempts in under seven minutes, within its
30-input/12-minute plan. Two stale UIA dialog assignments were refused without
selection, followed by fresh observation and literal input; no conversion retry
occurred. Stale accessibility focus metadata was not treated as focus proof.
A preference-restoration containment guard initially refused before deletion;
the corrected resolved LOCALAPPDATA guard removed only the owned generated file
after verifying unchanged bytes. That tooling correction is not a converter
failure or a diagnosis of earlier filesystem failures.

## Presentation and prior evidence applicability

The fresh workflow observed the compact task sheet, correct operation context,
source/findings/destination order, publication replacing editors, exact readable
paths, destination validation, honest counts, collapsed diagnostics, contextual
footer, explicit receipt actions and restrained light styling. This supplies
current observations for UI-P01–P10, basic UI-U01 behavior and the amended UI-U02
100%/long-path context.

Earlier verified slices 94–103 retain actual startup/instance/stale recovery,
native dialog/copy/save/platform-action, warning/fault/busy/deferred-Close and
normal/narrow/100%/150% observations. Reuse remains limited to those recorded
behaviors and source diffs. The final 103 runtime repair only routes path clearing
through the existing text setter; its affected repeated-open path behavior had
fresh actual observation. Earlier findings/footer/keyboard repairs had their own
native and public controls. This slice changes no runtime, so it does not add a
new applicability delta to those verified records. No claim is made that every
historical hash matches, or that this workflow freshly sampled 150% or narrow
windows. Independent #105 must perform its own actual-app comparison.

The user explicitly removed required 200% testing from #92. It was not tested or
passed; earlier pending-200 records remain historical. Future native restoration
uses the current 100% baseline, not the historical 125% setting.

## Limits and retained evidence

Complete synthetic sources, fresh outputs, command logs, inventories, versions,
native snapshots and per-criterion/requirement judgments are retained under ignored
`tmp/windows-ui-93` and the assigned immutable handoff. The public record contains
aggregate safe facts. Existing retained vaults and user archives were not altered.
This slice does not claim a new complete private-source preservation audit,
comprehensive accessibility certification or the user's final acceptance.

Historical intermittent safe publication failures, including AccessDenied during
staging rename, remain unresolved and preserved. This passing suite does not fix
or establish their cause; no external AV/ACL/handle explanation or production
workaround is asserted. Prior document-association chooser and Obsidian request
observations also retain their installed-handler limits: they do not prove a
document opened or that a new vault was registered.

## Follow-up from independent #105 review

The 1931-test/102-GUI and native workflow results above remain historical
acceptance evidence for `08d251005dcaec4426865279c01ea18be76508ec`. Independent
specification review subsequently identified UI-W11's missing selected target
after a failed diagnostic Save. The original finding and public reproduction
remain unchanged; this finding requires repair and independent recheck.

The repair carries the selected target through immutable host feedback and shows
it using the existing exact selectable/wrapping path control. Public adapter
failures retain their destination; explicitly selected UI context also covers
unexpected outer exceptions. Current generation admission, worker/report lifetime,
thread ownership and operation policy remain unchanged. New Copy/Save requests,
cancel, success and result replacement clear old targets. Tests cover real
replacement failure, missing parents, conversion/check result preservation,
Unicode/spaces, exception privacy and delayed failures after identical-result
replacement. Meaningful failing controls and focused passing receipts are retained
separately from the original acceptance cohort.

Repair acceptance used one fresh full cohort: **1945 tests passed in 476.64
seconds**, including **115 GUI controls**. All 43 focused diagnostic controls,
Ruff lint/format, dependency checks, Qt-blocked imports/base discovery (1830
tests), maintained launcher and local wheel build passed. All 72 wheel modules
match the repaired source. This new green cohort does not diagnose or fix the
historical incidental filesystem failures.

Only diagnostic Save failure context and its presentation change. Prior workflow,
publication, checking, startup/instance, dialog and unrelated presentation evidence
remains scoped to its recorded behavior; the new runtime must receive an affected
native failed-Save/path and independent review refresh. The final #105 report
must identify the actual reviewed candidate. No repaired candidate's native
observation, independent pass or user's verdict is inferred from the earlier run.

### Independent affected native recheck at d237

The independent presentation reviewer subsequently observed the repaired runtime
`d2378ebc72ff50e9fa91220ea4a55ae3ad7aeb69` at 100% and 454px narrow. A real Save
to an absent synthetic parent retained readable feedback, the exact long Unicode
target and the current result/actions. Native Ctrl+A selected the full target;
new Copy cleared it and the next explicit Save cancellation left it absent.
Public dialog/clipboard callbacks were injected; native Save-dialog or global
clipboard success is not inferred. Source/prepared bytes, missing target,
preferences absence and seven baseline windows were independently preserved.

The affected UI-W11/P07 repair is satisfied in this scope. A distinct maintained-
launcher sample at actual 150%, including a settled screenshot-only control,
still left small-text readability UNVERIFIED under UI-U02. No human readability
answer arrived during the bounded pause; no product/capture cause is established.
Observed 100% was restored and the owned app/Settings normally closed. The user's
removed 200% case is not tested or pending. This open prerequisite holds the final
independent review; automated passes do not resolve it. The separate
[review candidate report](windows-ui-review.md) records all P/U statuses and
required held criteria without claiming review PASS, closure or #106 acceptance.

### Owner correction and independent 100%/125% reuse

The owner's [current scope decision](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/92#issuecomment-6076372221)
requires 100% and 125% only, with normal/restoration 100%. Earlier 150% uncertainty
and the original BLOCKED attempt remain historical; that prerequisite was
superseded, rather than its observations becoming successful. Existing 1931/102-GUI
and 1945/115-GUI cohorts and their exact reviewed runtimes above are unchanged.

The independent native reviewer now supports amended UI-U02 and all P01–P10/U01
through explicit assessed reuse. Root's actual 125% observations at
`1b16155c11fbf7cfb14c026922befe47fecd2d8d` and
`12cf70e4af2d12af8348130faffd8a3aca31acdd` cover normal/narrow paths/findings,
stacking/scroll/footer, outcomes, repeated path feedback and real busy/deferred
Close. Those original actors and versions remain attributed; they are not a
fresh reviewer-run 125% sample. Current styles, fonts, PathText, DestinationFields
and Footer match those sampled versions; the new diagnostic target uses the same
renderer within the existing scrollable body. The reviewer's own affected
current 100%/narrow Save observation covers the new placement/lifetime. Raw binding
receipts and manual applicability judgment distinguish unchanged mechanisms from
the three modified feedback modules; byte matching alone does not prove pixels.

The one fresh 125% attempt remained UNVERIFIED because Settings exposed only a
loading splash. No scale change or converter launch occurred; normal Settings
Close retained all seven baseline windows and unchanged source/runtime/preferences.
Its unavailable result is preserved separately and not renamed as a passing run.
Current review support comes from applicable actual 125% reuse plus independent
current 100%/narrow observations. The [review report](windows-ui-review.md) records
all current statuses and limits, subject to fresh formal verification; no review
closure, integration or user's #106 verdict is supplied by this append.

## Scrollbar correction and latest 100%-only scope

The owner's [latest scope decision](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/92#issuecomment-6077040155)
requires verification at **100% only**, without changing system scaling. Earlier
100%/125% applicability and other-scale observations above retain their original
scope and dates. They are not new scrollbar appearance evidence. The owner
reported the boxed/stippled scrollbar in the actual review app; #107/UI-P11
requires platform scrollbar appearance while preserving C's sheet and behavior.

The first candidate `d1f15e13ca16dc103329b17055fbaf1bb2890566` corrected the broad
QWidget background rule, which also matches QScrollBar
subclasses. A bounded offscreen comparison using the available Windows11 style
shows that overriding background changes platform scrollbar drawing. The minimal
repair keeps inherited font/color declarations but moves white background to the
plain-container `.QWidget` selector. Targeted header, sheet, footer, findings and
diagnostic colors are unchanged; no whole-application style is forced and no
WinUI scrollbar is imitated. In that controlled comparison, the corrected
standalone scrollbar matches the unstyled Windows11 control. This establishes
the style interaction, not actual native appearance or overlay/animation parity.

One affected run of **138 tests under tests/gui passed in 41.06 seconds**, using
offscreen Qt with factor 1 and the safe public-result failure observer. Existing
controls verify scrolling, wrapping/reflow, exact path selection, focus and footer
reachability; no CSS/pixel-oracle test was added. Ruff lint, format (243 files),
dependency checks, maintained launcher and a fresh wheel build passed. The old
1945-test/115-GUI cohort remains historical, not a new execution against this
style change. The old wheel binding is superseded for the changed window module;
all 72 fresh-wheel Python modules match current source. Only window.py differs
from the previous wheel; the new wheel SHA256 is
`46025bb80ed686072373fdd34c9b12cc4d16c15be759773bbf15d93b5c68b0ff`.

At implementation preparation, independent actual 100% task-sheet/diagnostic
appearance, wheel/thumb/keyboard and short/narrow interaction remain **UNVERIFIED**
for UI-P11 and affected UI-P01/P07/P08/U01/U02. Offscreen output and older native
samples do not satisfy that changed appearance gate. The assigned independent
reviewer will supply current evidence in the #107 handoff. Serialized integration
and the owner's repaired actual-app #106/UI-V10 verdict remain separate.

### Independent REWORK and app-local Light repair

The independent d1f review subsequently found imperceptible task-sheet and
diagnostic thumbs at actual 443×583 against C's light sheet. Outer wheel,
diagnostic keyboard/selection and anchored footer worked. The attempted gutter
drag did not establish a discernible thumb hit or movement. The immutable first
candidate/REWORK and its build/test receipts are retained; no precise input-handler
or OS cause was inferred from that observation.

The minimal additional repair requests the application's Light color scheme at
public MainWindow construction before building its light controls, retaining the
default Windows platform style. [QStyleHints](https://doc.qt.io/qt-6/qstylehints.html#colorScheme-prop)
documents that this applies only to the application, not system preferences.
Exact Qt6.12 Windows11 source uses a white dark-scheme thumb and a black light-scheme
thumb, independent of the widget palette. One bounded nonvisible public drawing
comparison observed effective Dark with white-on-white output; Light produced
gray idle/hover thumbs while style identity stayed QWindows11Style. A first
disposable enum typo stopped before drawing and is retained with the corrected
comparison. No user window, input, settings, scale or source operation was involved.

A temporary public-construction request/ordering diagnostic was RED before the
repair and GREEN afterward. Offscreen QPA does not honor this scheme request and
retained Unknown, so this is not a permanent Qt-call test or native contrast proof.
The new affected GUI cohort passed **138 tests in 53.21s**, once with offscreen
factor1 and the safe public-result failure observer. Ruff lint/format (243 files),
dependency checks, maintained launcher and wheel build passed. All72 wheel modules
match source; only window.py differs from the first #107 wheel. The new wheel
SHA256 is `14b5221b9f10ae44c5d050c45d4fe1d91a3238ee102bf322db7eb069576928a6`.
Exact fresh build/module receipts bind the repaired candidate;
the full1945 cohort remains historical and scoped to unchanged backend semantics.
Independent actual maintained-launcher Windows100 wheel/thumb/keyboard and
short/narrow appearance are still **UNVERIFIED** before the new candidate review.
This causal repair does not supply UI-P11 PASS or the separate #106 user verdict.
