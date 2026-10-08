# Strategic prototype review plan

Evidence source: the accepted workflow and run-behavior resolutions in GitHub. All subjects/paths/counts are synthetic, independently chosen for the prototype; no generated/private vault is opened. Review covers the browser presentation, not a native Windows release or actual converter behavior.

Route base: http://127.0.0.1:8765/prototype.html

1. `?variant=A&scenario=review-warnings`: wizard hierarchy, warning review, source context and next action. Exercise choosing archive, review, destination, conversion and completion.
2. `?variant=B&scenario=review-warnings`: persistent input/result hierarchy and complete destination preview.
3. `?variant=C&scenario=review-warnings`: compact stacked hierarchy, warning/action placement and keyboard layout switch guard.
4. `?variant=A&scenario=running`: indeterminate activity/elapsed time, disabled operation actions and deferred-close example.
5. `?variant=B&scenario=published-error`: verified destination and follow-up error separately, retained completion actions. Also inspect success-with-warnings and unknown-publication examples.
6. `?variant=A&scenario=changed`: changed-source reinspection message and conversion gating. Also inspect refused/failed and exact leftover-path examples.
7. `?variant=C&scenario=checker-issues`: independent checker, read-only meaning, expandable findings, synthetic copy/export and unavailable-Obsidian feedback.
8. Narrow viewport of A and B: scroll/reflow and floating bar overlap. Inspect blank vault name and populated-destination validation as special cases.

Initial bound: at most 12 screenshots plus focused browser interactions/DOM observations for the above cases. Stop when each distinct layout/state and special case is observed without blocking defects; expand only for a defect or material uncertainty. Screenshots go in `tmp/ui-wayfinding/prototype/review/`. No tests are added to the project for this throwaway prototype. User selection/approval is a separate pending step.
