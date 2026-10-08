# B — Persistent workbench

Throwaway, synthetic-only presentation for issue #90. Open `b.html` directly or through the parent wrapper. No dependencies, filesystem reads, converter calls, external resources, storage, or production stack selection. Parent wrapper owns variant/scenario controls.

## Design question

Does keeping source and destination in a narrow, persistent left panel make it easier to review the findings and understand the current operation than a step-by-step presentation?

The right inspector gives the outcome first, then the relevant destination, warnings or guidance, optional actions, and expandable diagnostics. Independent operation tabs stay visible above both panels. Inspection retains findings when moving into conversion. On smaller windows the inputs stack above the inspector.

## Scenarios

`?scenario=` supports `start`, `review-clean`, `review-warnings`, `destination`, `running`, `success`, `success-warnings`, `refused`, `failed`, `leftover`, `changed`, `published-error`, `unknown`, `checker-clean`, `checker-issues`, `checker-failed`.

`?mode=convert|inspect|check` sets operation navigation. Checker scenarios default to Check; other scenarios default to Convert. Default scenario is Start. Some intentionally mismatched mode/scenario combinations expose the seeded outcome beside another mode's inputs for comparison; normal navigation resets checker/converter results appropriately.

## Interactions

- Synthetic archive picker provides clean, warning, refused, failed and alternate-source examples. Selecting a source clears inspection. Conversion requires usable inspection; warning findings require **Convert with warnings**.
- Source, parent and vault name stay visible during conversion. Name/parent validation is inline, with a full destination preview. The parent picker includes absent, empty and populated destination examples. Populated destinations block conversion.
- Inspect, Convert and Check show responsive indeterminate activity and elapsed seconds for four seconds. Inputs and operation tabs are disabled while busy. No Cancel action or invented progress phases. Close window demonstrates deferred closure.
- Changed source blocks publication and offers reinspection. Unknown publication requires an explicit destination review before retry. A populated review requires another destination; existence never establishes successful publication.
- Published outcomes retain optional folder, migration report, Obsidian and checker actions. Opens are simulated; Obsidian demonstrates unavailable-app feedback without losing the successful result. Checking runs read-only synthetic clean/issues/failed examples.
- Leftovers show the exact synthetic path `C:\Vaults\.Garden.staging-demo-001`, manual cleanup guidance, and user-initiated validation/retry. There is no deletion action or automatic retry.
- Expandable diagnostics provide Copy and local plain-text Save. Clipboard fallback shows selectable text. Reports contain paths, aggregate findings and metadata, never note bodies or archive payloads. Save requests a browser download and does not verify completion.
- Last output parent is illustrative and held only in memory. Reload resets all state; no archive history.

## Verification boundary

Selected interaction samples before review: clean start → inspect → destination → convert → check; warnings → explicit conversion action; invalid name and populated destination; changed source; unknown publication; published plus follow-up error; leftover; checker issues. These cover the distinct hierarchy, gating, publication and read-only outcomes. No private vaults or native applications are opened.

This is a presentation demo, not integration, packaging, publication-safety or acceptance proof. Timed outcomes and destination conditions are synthetic. No user presentation verdict has been recorded.

## Completed smoke review

JavaScript passed `node --check`. In the independent `ui-workbench-b` browser session, verified blank-name blocking, warning-only conversion wording, busy input/tab locking, deferred close feedback, successful warning publication, changed-source blocking, unknown publication blocking (including an unresolved review), populated destination blocking, selecting a different destination, and source replacement clearing inspection. Sampled checker-issues and warning-review screenshots at 1280 × 720; content remains readable, with lower controls reached by page scrolling at that height. Browser console had no application errors after the favicon was made self-contained. Initial browser navigation had only a harmless missing-favicon response, now removed.

The smoke review observed representative states rather than every mode/scenario combination. It did not verify browser download completion or real clipboard/application availability. Screenshot and browser-session evidence is disposable under `tmp/ui-wayfinding/prototype/.playwright-cli/`.

Integrated-review corrections: unknown publication now seeds an unknown destination condition and explicitly says its contents have not been established. Destination fields/picker stay locked while a published or unknown result is shown; unknown also blocks replacing/reinspecting the source until destination review resolves the uncertainty. A published result offers **Start another conversion**, reopening destination fields while blocking reuse of the populated target. Bounded browser review confirmed unknown copy and locks, empty-destination review unlocking, published-path/action stability, and new-attempt gating until another target is entered. JavaScript syntax passed again.
