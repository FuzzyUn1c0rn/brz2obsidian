# A — guided steps

Question: does showing one decision at a time make the accepted conversion workflow easier to follow?

The quiet Windows-style frame has three operation tabs. Conversion uses a left progress rail and a single active stage: archive selection, inspection review, destination, and creation/outcome. Inspect and Check are independent read-only modes. The rail describes progress rather than acting as a shortcut around inspection. All scenarios and counts use synthetic Garden data.

## Supported scenarios

`?scenario=start|review-clean|review-warnings|destination|running|success|success-warnings|refused|failed|leftover|changed|published-error|unknown|checker-clean|checker-issues|checker-failed`.

`?mode=convert|inspect|check` chooses the operation; checker scenario keys select Check mode. Default is conversion start. Parent wrapper owns scenario/variant controls; this file has no duplicate prototype toolbar.

Pickers are clearly labeled prototype dialogs. They offer synthetic clean/warning/refused/failed archive examples, alternative parent folders including a populated-folder control, and clean/issues/failed checker examples. Conversion requires inspection; warnings use **Convert with warnings**. Destination names validate on entry. Full paths remain visible. A changed source blocks publication and requires reinspection/review. Unknown status has a Check destination route before choosing a fresh destination. Published plus late error retains completion actions. Leftover staging path is exact and no deletion is offered.

Running operations show an indeterminate indicator and elapsed seconds, lock operation/input changes, and finish after a short demonstration delay. The Close button demonstrates deferred closure. Real window lifecycle integration remains unimplemented. Optional folder/report/Obsidian actions provide simulated feedback and copyable paths. Copy uses the browser clipboard; Save requests a local synthetic text download. No note bodies or archive contents are in diagnostics. Last parent is remembered in memory for this page session only; reloading resets it.

The synthetic page does not intercept browser unload. Outer comparison controls can switch layouts or scenarios during a demonstration operation; deferred closure is illustrated only through the product Close button.

## Strategic review selection

Review start (mode distinction + source selection), warning review and destination (warning gating + field validation), running (responsive elapsed + deferred closure), published-error (verified publication + optional actions), changed/unknown/leftover (three different recovery restrictions), checker-issues (read-only findings). These sample distinct presentation behaviors; other equivalent scenario screens share the same outcome structure. This prototype demonstrates presentation, not converter correctness, native pickers, desktop packaging or production integration.

No files outside this variant and its notes are owned by this agent. No converter invoked; no private data, dependencies or persisted preferences used.

## Lightweight verification performed

Node parsed the standalone script. A one-off in-memory DOM review rendered all 16 scenario keys and checked warning conversion, invalid-name gating, changed-source reinspection and unknown-status checking. A distinct Playwright browser session (`ui-guided-a`) exercised warning review → destination, rejected `CON` with an adjacent error and disabled conversion, updated the full path, then converted with warnings. During the running state all operation tabs were disabled and Close displayed deferred-close feedback. No horizontal overflow was observed at the sampled browser width. This is a bounded interaction sample, not a test suite or full visual acceptance. The comparison owner performs integrated visual review.
