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
