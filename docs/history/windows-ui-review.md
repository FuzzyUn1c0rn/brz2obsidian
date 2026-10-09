# Windows UI independent review candidate

The required diagnostic Save repair is independently verified. The review remains
**held** because actual application readability at 150% is **UNVERIFIED** under
UI-U02. This report supports a review candidate, not a final review PASS, ticket
closure, integration decision or the user's actual-running-app verdict in #106.

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

Actual 150% small Qt text remained fragmented in settled captures, including one
distinct maintained-launcher Inspect and same-state screenshot-only control at
first-display original detail. Native chooser text was substantially clear.
Neither product painting failure nor a capture/Qt/driver/font cause is established.
Root requested one concrete human readability observation on the actual app and
paused inputs for a bounded interval; no answer arrived. Silence is not evidence.
The reviewer restored observed 100% and normally closed the owned app/Settings.
Nineteen maintained-control input/launch attempts over about 5m42 remained within
20/eight-minute limits. The user removed 200%; it is neither tested nor pending.

| ID | Independent disposition and limit |
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
| UI-P10 | SATISFIED with U02 readability limit: light palette, typography, dividers, modest borders and green direction; no exact pixel promise. |
| UI-U01 | SATISFIED basic strategic scope: labels, textual meaning, visible focus, report/path selection; no exhaustive assistive-technology certification. |
| UI-U02 | UNVERIFIED required prerequisite: actual 100%/narrow readability/stacking/scroll/footer pass; actual 150% small-text readability uncertain and human observation pending. |

## All five ticket criteria

| Criterion | Current assessment |
| --- | --- |
| 105-AC1 | SATISFIED: reviewer separation, actual runtime/reference/report identities and bounded strategic procedure recorded. |
| 105-AC2 | SATISFIED: independent full-delta Standards/Spec review and repair refresh; required P2 fixed; zero documented breaches and two nonblocking P3 maintenance judgments. |
| 105-AC3 | UNVERIFIED: representative own observations cover P01–P10/U01, but required actual 150% U02 readability remains unavailable pending human observation. |
| 105-AC4 | HELD: findings, repairs, automated evidence, all per-ID judgments and affected104 refresh are recorded; required U02 cannot yet be independently resolved. |
| 105-AC5 | HELD: no final review PASS or closure until required checks are satisfied; #106/UI-V10 and packaging remain separate. |

## Evidence bindings and limits

Separate original/repair Standards and Spec records, original native review and
`native-review-d237-save.md`/`native-review-d237-final.md` are retained under ignored
`tmp/windows-ui-93/review105`; candidate evidence includes their exact hashes and
the raw check/native preservation receipts. Pixels remain in Sky tool history;
stored JSON contains accessibility/geometry metadata, not saved screenshots.
The report-only candidate's runtime/source/wheel bindings accompany its handoff.

Only runner path context, platform failed-save outcome and window path
presentation changed from 08d; seven other frozen runtime modules are unchanged.
Prior observations apply only to unaffected behavior, with fresh own d237 Save
and maintained 150% controls for changed/current boundaries. No claim that all
historical raw hashes match is made. Source/prepared inventories, caller bytes,
owned leftovers, original preference absence, seven baseline windows and current
runtime/launcher identity were independently checked. Observer/helper corrections
and initial blank/occluded/input/resize uncertainty remain labelled and retained.

Historical #98/#103 safe WinError5 publication failures remain failed/cause unknown;
successful checks/samples do not diagnose or fix them. No AV/ACL/handle attribution,
production workaround or new private-source preservation audit is asserted.
Current normal/restoration 100% is observed; no unrelated apps/preferences/security
settings were changed. Required 150% human observation remains pending, and the
user's actual-running-app #106 verdict is wholly unclaimed.
