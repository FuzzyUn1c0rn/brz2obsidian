# Draft presentation review — 2026-10-08

The user requested independent sub-agents for each prototype. A was authored by `/root/prototype_guided`, B by `/root/prototype_workbench`, and C by `/root/prototype_compact`. Each received the same accepted behavior and a different structural brief, without reading/reusing the parent draft or sibling HTML. Root authored only the shared comparison host, performed the integrated review and captured the draft reference. The superseded root draft is excluded from this reference.

## Review boundary

Review used Microsoft Edge 154.0.4258.62 through Playwright on the local loopback server, with synthetic Garden data only. Twelve selected screenshots cover three layouts, distinct operation outcomes, two narrow layouts and inline validation. Layout references use 1280×1200, narrow samples 680×1000. These are browser observations of draft presentation; native Windows dialogs, Obsidian launch, converter publication safety, bundled runtime accessibility and clean-machine packaging were not tested. No private archive or retained vault was accessed.

## Observed cases

| Reference | Distinct behavior observed |
| --- | --- |
| `a-warning.png` | Focused inspection stage, progress rail, planned counts, visible source warning and route to destination. |
| `b-warning.png` | Persistent input panel beside findings; complete destination preview and explicit warning-conversion action. |
| `c-warning.png` | Stacked source, findings and destination; footer action and warning summary. |
| `a-running.png` | Indeterminate activity, elapsed time, disabled mode controls and deferred product Close feedback. |
| `b-published-error.png` | Verified published path, separate later error and all four completion actions. Simulated unavailable Obsidian feedback preserves the result and provides its path. |
| `b-unknown.png` | Explicit publication uncertainty and destination-review action before retry. |
| `a-changed.png` | Publication blocked; source reinspection is the next action. |
| `c-checker-issues.png` | Independent read-only checker findings, details and repeat-check action. |
| `b-leftover.png` | Exact reported staging path, manual guidance and user-initiated retry without deletion. |
| `a-narrow.png` | Wizard rail reflows horizontally; fields/actions remain reachable by scrolling. |
| `b-narrow.png` | Workbench stacks inputs above results; content remains reachable inside the preview. |
| `c-invalid-name.png` | Adjacent blank-name error, updated destination and disabled Convert. |

Synthetic text export was downloaded and inspected as `synthetic-diagnostic-report.txt`: operation, outcome, path, prototype/version context and aggregate diagnostic findings only; no note bodies or payloads. The active name field's arrow key leaves the variant unchanged; outer controls switch variants and synchronize URL/example state. Agents also performed bounded script and representative interaction checks, documented in their variant notes.

## Corrections during review

- The initial comparison host let its fixed prototype bar overlap longer child pages. Root reserved a separate area below the iframe; child pages scroll within the preview, and the corrected samples show no bar covering product controls. This defect justified refreshing the three layout references.
- A's browser-level beforeunload handler intercepted changing an illustrative running scenario. The author removed that handler; product Close still demonstrates deferral, while outer prototype controls remain usable.
- The actual generated report filename is `MIGRATION REPORT.md`; simulated open/copy paths were corrected before capture.
- B's unknown-destination guidance and stable published/requested paths were reviewed separately and corrected before the final reference capture. The final observation showed unknown contents explicitly, disabled destination edits/conversion until review, and locked published paths with a **Start another conversion** route. Refreshing these two screenshots was limited to the corrected states.

Final host checks also confirmed the prototype can switch away from A's synthetic running state without a browser-close prompt, its product Close remains deferred with all three mode buttons disabled, and both narrow samples have content width equal to their 680-pixel viewport with the comparison bar below the preview. No horizontal overflow was observed in those two cases.

## Pending user decision

No layout, color scheme, product name, icon or wording is accepted yet. The user can choose a layout, request changes or combine distinguishing parts. Accepted-presentation IDs and the user's verdict will be recorded in the presentation ticket only after that live feedback. The ticket remains open. This draft code will not be promoted directly into production.
