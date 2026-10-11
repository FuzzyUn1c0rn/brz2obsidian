# Final review

Read this when assessing completed implementation or a repair. Use an independent
reviewer for the enhanced workflow's final verdict; one reviewer may assess both
requirements and standards. Review the actual changes and applicable evidence.

## Identify the assessed changes

Record the absolute checkout, full baseline and assessed commit IDs, accepted
scope, changed files and review commands. For an integrated implementation, use
the recorded starting commit and `git diff <starting-commit> HEAD`.
For a branch comparison, record its resolved merge-base and compare from that
commit. Preserve an explicitly requested commit or comparison scope.

When reviewing work in progress, include staged and unstaged tracked changes
with `git diff HEAD`, and discover untracked files with
`git ls-files --others --exclude-standard`; read the new files as part of the
review. A committed diff alone cannot establish a verdict on uncommitted work.
An empty diff needs an honest no-changes result, not an invented review.

Freeze the assessed source during review and check execution. A relevant source
change requires reassessment and invalidates a verdict on the previous source.
Structured publication still requires the contract's clean committed candidate.

## Assess requirements and standards

- Compare with the accepted spec/ticket: missing or partial requirements,
  incorrect behavior, regressions, and changes outside the authorized scope.
- Compare with applicable repository instructions and architecture decisions.
  Prioritize concrete defects and acceptance gaps; distinguish documented rule
  violations from optional design suggestions.
- Assess test quality and evidence applicability using
  [check selection](check-scope.md) and the
  [runner contract](../../../../docs/testing.md#automated-check-runner).
  Validate receipts against independently selected requirements. Run fresh
  checks where required or needed to resolve a concrete concern; do not repeat
  unrelated suites merely to create a separate review result.
- For affected presentation, apply the
  [accepted presentation procedure](../../../../docs/agents/accepted-presentation.md).
  Automated checks and another agent's report do not establish an actual-user
  verdict or missing native observations.

Use available authoritative scope rather than asking the user to repeat it.
If a necessary requirement or decision is unavailable, name the gap and continue
the assessment that can be completed independently.

## Report and resolve

Record the assessed identity, coverage, requirement outcomes, findings with
specific evidence pointers, applicable receipts and material limits. Distinguish
blocking defects from advisories and preserve separate conclusions for
requirements and standards. Use `PASS`, `REWORK` or `BLOCKED` where the handoff
path requires a verdict. Missing required evidence remains unverified.

Repair blocking findings, select checks for the actual repair, and obtain renewed
independent review before completion. The selected handoff path owns publication
and integration; this procedure supplies the review judgments.
