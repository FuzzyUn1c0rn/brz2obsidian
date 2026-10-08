# Prototype C — compact task sheet

Question: can one compact sheet keep source, findings and destination understandable without a wizard or a workbench?

The design uses a centered, modest desktop dialog with three operation tabs, vertically stacked sections and an anchored action footer. Findings stay above destination so the reviewed source remains visible at the point of conversion. Published outcomes replace the destination form with a result and optional actions. A narrow viewport stacks the two destination fields.

## Run and scenarios

Open `c.html` directly, or through the parent's prototype wrapper. There are no dependencies. The parent supplies the scenario and variant controls; this child has none.

`?mode=convert|inspect|check` selects the operation. `?scenario=` supports `start`, `review-clean`, `review-warnings`, `destination`, `running`, `success`, `success-warnings`, `refused`, `failed`, `leftover`, `changed`, `published-error`, `unknown`, `checker-clean`, `checker-issues`, `checker-failed`. Default is `start`; checker scenarios select Check unless mode is explicitly supplied.

The synthetic source picker includes clean, warning, refused and failed inspection examples. The parent picker includes new, existing-empty and populated destinations. The vault picker includes clean, issue and failed checks. The normal clean/warning workflow is fully interactive. Scenario links provide the exceptional conversion outcomes. Busy operations use a spinner and elapsed time, prevent overlapping work, and defer the simulated Close until completion. Optional opens explicitly simulate feedback; Obsidian demonstrates an unavailable-app failure while preserving the successful result. Copy uses the clipboard when available; Save explicitly requests a local readable diagnostic text download. Both omit note bodies/payloads.

The changed-source scenario invalidates review and requires inspection before publication. Unknown publication requires simulated manual destination review before another conversion. Populated destinations block conversion. Leftovers give the exact synthetic staging path and manual guidance; there is no deletion action. Published follow-up errors retain all completion actions. Last-parent memory is illustrative and session-only.

## Verification boundary

Strategic review cases selected before browser use: start (hierarchy and empty-source gating), review-warnings (summary, destination and explicit warning action), unknown (publication uncertainty), published-error (completion actions despite late failure), checker-issues (read-only outcomes), and narrow destination layout (field stacking). No source app, private files, production converter, native picker, filesystem destination check or packaging integration is involved. All path/count/result evidence is invented. This prototype cannot prove source-identity binding or publication safety. Browser-specific clipboard/download controls may limit Copy/Save, and Save cannot confirm a completed download.

No user presentation acceptance is implied. No commits, pushes or issue writes were performed.

Executed: Node syntax check passed. An in-memory DOM-stub smoke check passed all 16 scenario renders, warning continuation, blank/reserved name validation, changed/unknown gating, and published-error completion actions. This checks script/render branches only; root performs integrated browser screenshots after handoff.
