# Windows UI independent review candidate

This record preserves the independent #105 review and subsequent owner
corrections. The latest required verification is **100% only**, without a system
scale change. The first #107/UI-P11 candidate received REWORK because its native
thumb was imperceptible against the light sheet. The subsequent app-local Light
repair awaits independent actual100% appearance/interaction evidence. Earlier
100%/125% reuse and unavailable 125%/uncertain 150% samples retain their historical
facts; they do not prove the changed scrollbar appearance. The user's repaired
actual-running-app #106/UI-V10 verdict remains separate.

## Current scrollbar repair checkpoint

The owner's [latest decision](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/92#issuecomment-6077040155)
supersedes the former 100%/125% verification requirement. Preserve narrow/short
scrolling, paths/findings, stacking, focus/keyboard and unobstructed footer at 100%.
No other scale is tested or diagnosed by this repair.

The first candidate `d1f15e13ca16dc103329b17055fbaf1bb2890566` received independent
REWORK: at actual 443×583, task-sheet and diagnostic thumbs were imperceptible.
Wheel, diagnostic keyboard/selection and the anchored footer worked, but the
attempted gutter drag did not establish a thumb hit or movement. No drag-handler,
OS or capture cause was inferred. Its 138-test receipt and wheel remain historical;
they did not establish UI-P11 appearance.

The retained two-line stylesheet repair removes the background override from QWidget's
inherited typography rule and applies it to plain `.QWidget` containers instead.
Qt type selectors also match subclasses, so the old rule customized QScrollBar
painting. In one bounded offscreen Windows11-style comparison the scoped version
keeps container/panel colors while the standalone scrollbar matches the unstyled
platform control. [Qt's stylesheet rules](https://doc.qt.io/qt-6/stylesheet-syntax.html)
and [style delegation](https://doc.qt.io/qt-6/stylesheet.html) explain this boundary.
The additional repair requests Qt's application-local Light scheme at public
MainWindow construction, before light controls are built. Qt6.12 Windows11 paints
the thumb from its scheme table, independent of the widget palette. One nonvisible
public QStyle/QImage comparison started in Dark: idle/hover thumb drawing on white
had no nonwhite pixels. A Light request changed the effective scheme and drew gray
thumbs (50 idle / 288 hover pixels) with the same default QWindows11Style. These
are causal drawing observations, not pixel acceptance criteria. The first probe
stopped before drawing on a disposable enum typo; its failure is retained alongside
the corrected comparison. [Qt's exact Windows11 source](https://raw.githubusercontent.com/qt/qtbase/v6.12.0/src/plugins/styles/modernwindows/qwindows11style.cpp)
and [QStyleHints](https://doc.qt.io/qt-6/qstylehints.html#colorScheme-prop) support
this app-only request. No Windows preferences or application style is forced,
scrollbar theme duplicated, operation policy changed or permanent CSS/Qt-call test added.

A disposable public-construction ordering probe was RED on d1f and GREEN after
the request, preserving the default style. Offscreen QPA remained Unknown, so that
probe establishes request ordering only, not contrast or actual native usability.

Fresh affected evidence: **138 tests under tests/gui passed once in 53.21s**;
Ruff lint/format (243 files), dependencies, maintained launcher and wheel passed.
All72 new-wheel Python modules match source; only window.py differs from the d1f
wheel. Its SHA256 is `14b5221b9f10ae44c5d050c45d4fe1d91a3238ee102bf322db7eb069576928a6`.
Exact module/runtime bindings accompany the repaired #107 candidate. The previous
1945/115-GUI cohort is historical; it was not rerun against this style change.
Prior Standards/Spec findings remain applicable to unchanged code; the new
presentation delta receives its own independent #107 review.

| Current requirement | Preparation disposition |
| --- | --- |
| UI-P11 | First d1f native candidate FAILED/REWORK. New app-local Light repair has causal public drawing support; independent task-sheet/diagnostic visibility and thumb interaction at 100% remain UNVERIFIED. |
| UI-P01/UI-P07/UI-P08/UI-U01/UI-U02 | Affected wrapping/scroll/focus/footer public controls pass; independent actual 100% wheel/thumb/keyboard and short/narrow recheck pending. |
| #107 handoff/integration | Candidate preparation only; independent verification and serialized integration remain separate. |
| UI-V10/#106 | No final user acceptance supplied by the technical repair. |

The sections below retain #105's exact actors, candidates, reference, source axes
and the then-current 100%/125% applicability judgment. Prior 125% and 150% observations
are historical; no new other-scale PASS, regression or cause is claimed.

## Scope and independent roles

Canonical amended [#92](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/92),
parent [#93](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/93) and
[#105](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/105) govern this review.
The exact accepted C reference is
`0e0120a15e6ba0c70e6765947972c36aaa672f87`. The native reviewer independently
verified all five retained reference artifacts against Git and directly viewed
the three C images. Prototype examples do not establish production behavior.

The original review compared `6586666e0013b186156f0d111285627d04c4fddd` with
`08d251005dcaec4426865279c01ea18be76508ec`, the complete 24-commit implementation
delta. Independent Standards and Spec reviewers then read every hunk of the
eight-file repair at `d2378ebc72ff50e9fa91220ea4a55ae3ad7aeb69`, the 25th commit,
and reassessed the preceding entire-delta findings. Incorporated base 08d was
captured before the repair's final checks. This subsequent report-only change
preserves that reviewed runtime; its exact final commit and byte bindings belong
to the candidate handoff.

The owner's [2026-10-09 correction](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/92#issuecomment-6076372221)
now requires representative **100% and 125% only**, with normal/restoration 100%.
This supersedes the earlier 150% prerequisite and previously removed 200% case;
it does not turn any old uncertainty or BLOCKED record into a passing observation.
The original `57df9cfe0501f43cbb85ff4232a1f1f3aad9a36e` attempt remains immutable.
Only this review, the acceptance follow-up and testing guidance change now;
production, tests, dependency/build manifests and reviewed artifacts do not.

The final presentation reviewer `/root/ui_verifier` neither implemented the
changed presentation nor authored the assessed implementation report
[windows-ui-acceptance.md](windows-ui-acceptance.md) or root's native104 ledger.
That reviewer owns exclusive Sky desktop input and its own bounded observations;
root owns serialized integration. The report implementer aggregates separate
independent records, without supplying their verdicts or driving native UI.

## Standards axis

The original review and repair refresh identify **zero documented-standard
breaches**, with no new actionable smell in the repair. Two original P3
maintenance judgments remain nonblocking: duplicated conversion outcome and
verified-publication mappings in producer/validator, and duplicated focus
restoration after completion/diagnostic actions. They do not demonstrate runtime
defects. Unrelated refactoring is deferred; the distinct semantic feedback
channels and independent test expectations are retained.

This axis assesses repository conventions and module boundaries. It supplies no
native readability or user-acceptance verdict. Original `standards.md` and
`standards-repair.md` remain separate preserved records.

## Specification axis and required repair

The original Spec review found one required P2: UI-W11 diagnostic Save failure
lost the selected export target. No additional confirmed defect or unasked scope
creep was identified. The original finding and public reproduction are retained.

The minimal repair carries optional immutable path context through the existing
outer adapter/host runner and presents the exact target using the existing
selectable, wrapping path control. Explicit UI selection is authoritative,
including generic adapter exceptions. Direct public failed-save outcomes also
retain the destination. Success, cancellation, new Copy/Save and changed or
identical-result generations clear old targets; stale requests/completions cannot
restore them. Operation results, reports and other actions survive. There is no
exception/source-content leak, new wire/session vocabulary, policy in Qt,
automatic retry or worker timeout/kill.

The independent Spec refresh confirms this P2 fixed in code/public behavior. Its
fresh public probe exits 0: actual missing-parent failure, generic exception,
explicit-target precedence, rejected stale admission, success without a failure
path and unchanged session/report/no destination creation. The probe's first
observer-only output encoding error is retained; explicit UTF-8 output succeeded
without replaying conversion or a filesystem failure.

Meaningful UI/adapter REDs and 43 focused passing controls precede **one full
1945-pass cohort**, including **115 GUI controls**, in 476.64 seconds. Ruff lint
and format (243 files), dependency checks, Qt-blocked imports/base discovery
(1830 tests), maintained launcher and wheel build passed. All 72 wheel Python
modules match the repaired source. These receipts preserve the historical
1931-test/102-GUI acceptance cohort at 08d rather than relabelling it. The reviews
cover functional scope and affected UI-S/A/W/R/D/I/T/B/U/P/V requirements,
including thread ownership, backend policy, replaceable UI/import direction,
hidden-worker protocol/freshness, destination/receipt/uncertainty safety and
diagnostic lifetime. Automated evidence cannot resolve native readability.

## Independent native axis

Own actual 08d samples cover maintained clean Inspect and long Unicode native
selection/report keyboard selection; warning/reserved-name destination at normal
and 454px narrow; checker issues; controlled write/owned-cleanup failure; real
malformed-worker unknown publication; actual late verified receipt and repeated
injected unavailable-open fallback; not-started; actual populated-destination
race refusal; and held off-thread actual worker, elapsed/repaint/movement and
deferred Close. Real versus injected boundaries and sample budgets remain in the
reviewer's records, rather than being inferred from implementation-authored reports.

Own affected d237 Save sample uses real production Save with a selected synthetic
long Unicode target whose owned parent is absent, plus public dialog/clipboard
callback injection. At 100% and 454px narrow, safe guidance and the exact target
remain readable and native Ctrl+A selects the full target. Result/findings/actions
remain current. New Copy clears the target, the next explicit Save cancels with
no target, and normal Close restores the baseline. Ten inputs/about two minutes
stay within the planned 18-input/eight-minute bound. This proves affected UI-W11
and P07; it does not claim native Save-dialog/global clipboard success or ACL
replacement denial from injected callbacks.

Historically, actual 150% small Qt text remained fragmented in settled captures,
including one distinct maintained-launcher Inspect and same-state screenshot-only control at
first-display original detail. Native chooser text was substantially clear.
Neither product painting failure nor a capture/Qt/driver/font cause is established.
Root requested one concrete human readability observation on the actual app and
paused inputs for a bounded interval; no answer arrived. Silence is not evidence.
The reviewer restored observed 100% and normally closed the owned app/Settings.
Nineteen maintained-control input/launch attempts over about 5m42 remained within
20/eight-minute limits. These observations and the original BLOCKED handoff are
preserved; the owner has since superseded that requirement, without a painting
cause or a claim that removed scales passed.

### Historical #105 100%/125% applicability

The separate independent `native-review-125-applicability.md` assesses runtime
`57df9cfe0501f43cbb85ff4232a1f1f3aad9a36e`, byte-identical to d237. Reviewer
`/root/ui_verifier` read the full root-authored native103 ledger and applicable
actual 125% state records, runtime/source bindings and raw geometry/selected text.
Those earlier observations remain attributed to root; they do not become a new
actual 125% run by the reviewer. The reviewer supplies its own current 100%/narrow/C
comparison and affected d237 Save observation, then independently judges reuse.

Actual 125% sources are `1b16155c11fbf7cfb14c026922befe47fecd2d8d` for normal
782×851/narrow 453×851 findings/recovery/cleanup paths, verified late-error/form
replacement/four actions, corrected not-started, actual refusal/checker and held
real runner/elapsed/repaint/deferred Close; and
`12cf70e4af2d12af8348130faffd8a3aca31acdd` for repeated explicit Open-folder
failure with exact wrapped/selected receipt path after the PathText.clear repair.
The earlier inconclusive not-started fixture and clipped findings are not reused
as successful final samples. Prior actual 125% context/unknown/partial diagnostic
selection retain their original versions and limits. Runtime versions and
preservation inventories remain attached to those original receipts.

Independent binding output exits 0: ten frozen modules from each 125% receipt match
their original Git blobs, 62 retained 1b files and 21 retained 12cf files remain
unchanged, and 28 raw receipts are indexed. The earlier metadata list-shape helper
error is retained; correcting that evidence-only annotation did not rerun native
or conversion work. Current STYLE, label, PathText, DestinationFields and Footer
are equivalent to sampled 12cf implementations. Fonts, wrapping/height/selection,
resize/narrow reflow, surfaces and anchored layout are unchanged. The only three
runtime deltas add diagnostic Save context and a new instance of the same PathText
in the existing scrollable body. Fresh current 100%/narrow Save covers that new
location/lifetime; earlier actual 125% paths/findings/footer cover its unchanged
scale-sensitive renderer. This is an explicit applicability inference, not a
state×scale pixel matrix, and byte matching alone is not visual evidence.

The attempted fresh 125% sample instead exposed only a loading Settings splash.
No scale control, 125% selection or converter launch occurred. Four input/launch
attempts over 165.9 seconds ended with normal Settings Close and the exact seven-
window baseline; source/runtime/launcher/preferences were preserved. No scale
changed, so no 125%→100% restoration is claimed and the unavailable controls supply
no new visible 100% readback. User-normal 100% and the last observed 100% restoration
retain their scope. The unavailable attempt remains a distinct preserved record;
it contains no contradictory 125% converter observation and is not marked passed.

| ID | Recorded #105 disposition and limit before the scrollbar correction |
| --- | --- |
| UI-P01 | SATISFIED: task sheet, body scroll, narrow layout and retained shell/footer; affected d237 path freshly observed. |
| UI-P02 | SATISFIED: headings, explanations, ordered tabs and context; small text retains U02 limit. |
| UI-P03 | SATISFIED: source/findings/destination order and verified result substitution without inventing unknown/refused publication. |
| UI-P04 | SATISFIED: native picker/identity and exact wrapped/selectable paths; prior cancellation/focus controls scoped. |
| UI-P05 | SATISFIED: stacking, preview, scroll, reserved-name guidance and action gating at normal/narrow sizes. |
| UI-P06 | SATISFIED: distinct honest clean/warning/refusal/failure/checker/unknown/late/busy states and counts. |
| UI-P07 | SATISFIED affected scope: own d237 failed-Save guidance/exact selected target, new Copy/cancel clearing and retained result; unaffected export controls scoped. |
| UI-P08 | SATISFIED: contextual footer, actual busy elapsed/repaint and deferred Close without Cancel. |
| UI-P09 | SATISFIED: verified exact path/four explicit actions and preserved receipt/bytes on repeated unavailable-open; no successful editor/Obsidian inference. |
| UI-P10 | SATISFIED: own current C/light-palette comparison and applicable actual 125% output through identical style/fonts; no exact pixel promise. |
| UI-U01 | SATISFIED basic strategic scope: labels, textual meaning, visible focus, report/path selection; no exhaustive assistive-technology certification. |
| UI-U02 | SATISFIED in amended strategic scope: own current 100%/narrow observations plus independently assessed actual 125% normal/narrow/path/findings/stacking/scroll/footer reuse; no fresh 125% control readback or all-state matrix claimed. |

## Recorded #105 ticket criteria

| Criterion | Current assessment |
| --- | --- |
| 105-AC1 | SATISFIED: reviewer separation, actual runtime/reference/report identities and bounded strategic procedure recorded. |
| 105-AC2 | SATISFIED: independent full-delta Standards/Spec review and repair refresh; required P2 fixed; zero documented breaches and two nonblocking P3 maintenance judgments. |
| 105-AC3 | SUPPORTED: independent own current 100%/narrow/C comparison and explicit actual 125% reuse cover P01–P10/U01/amended U02; fresh unavailable attempt retains its original result. |
| 105-AC4 | SUPPORTED: all findings, repair/recheck, current per-ID judgments, automated evidence, source bindings and affected104 refresh are recorded; old BLOCKED/uncertainty records preserved. |
| 105-AC5 | READY FOR FORMAL DECISION: required current checks have supported evidence, subject to fresh structured verification. No closure/integration is claimed here; #106/UI-V10 and packaging remain separate. |

## Evidence bindings and limits

Separate original/repair Standards and Spec records, original native review and
`native-review-d237-save.md`/`native-review-d237-final.md` and current
`native-review-125.md`/`native-review-125-applicability.md` are retained under ignored
`tmp/windows-ui-93/review105`; candidate evidence includes their exact hashes and
the raw check/native preservation receipts. Pixels remain in Sky tool history;
stored JSON contains accessibility/geometry metadata, not saved screenshots.
The report-only candidate's runtime/source/wheel bindings accompany its handoff.

Only runner path context, platform failed-save outcome and window path
presentation changed from 08d; seven other frozen runtime modules are unchanged.
Prior observations apply only to unaffected behavior, with fresh own d237 Save
and historically maintained 150% controls for changed boundaries. Current 100%/125%
applicability and 28 original receipt bindings are separate. No claim that all
historical raw hashes match is made. Source/prepared inventories, caller bytes,
owned leftovers, original preference absence, seven baseline windows and current
runtime/launcher identity were independently checked. Observer/helper corrections
and initial blank/occluded/input/resize uncertainty remain labelled and retained.

Historical #98/#103 safe WinError5 publication failures remain failed/cause unknown;
successful checks/samples do not diagnose or fix them. No AV/ACL/handle attribution,
production workaround or new private-source preservation audit is asserted.
Current normal/restoration 100% is observed; no unrelated apps/preferences/security
settings were changed. No further 150% observation is required under the
owner's correction; removed scales are not passed or diagnosed. The user's
actual-running-app #106 verdict remains wholly unclaimed.
