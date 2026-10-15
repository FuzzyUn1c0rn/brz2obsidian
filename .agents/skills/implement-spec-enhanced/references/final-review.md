# Final review

Read this when assessing changes against accepted requirements. Completed
implementation or repairs require an independent reviewer for the enhanced
workflow's final verdict; one reviewer may assess both requirements and standards.
For an explicit read-only review, inspect the relevant source and evidence and
return findings within that scope.

## Identify the assessed changes

The outer orchestrator creates the draft PR after implementation is assembled,
then assigns its independent final review. Record the PR URL, repository, actual
base branch and full base/head commit IDs, resolved comparison base, absolute
clean assessed checkout, accepted scope, changed files and review commands.
Inspect the actual PR diff from its resolved comparison base to the recorded
head. Include all changes the PR delivers, including existing work on a reused
root; the effort's starting commit alone may omit part of that PR.

For an explicitly requested local assessment without a PR, preserve its scope:
an integrated-change comparison uses the recorded starting commit; a branch
comparison uses its resolved merge-base. A bounded read-only review does not
create a PR or turn into implementation preparation.

When reviewing work in progress, include staged and unstaged tracked changes
with `git diff HEAD`, and discover untracked files with
`git ls-files --others --exclude-standard`; read the new files as part of the
review. A committed diff alone cannot establish a verdict on uncommitted work.
For a change-only review, an empty diff needs an honest no-changes result.

Freeze the assessed source during review and check execution. A relevant source
change requires reassessment and invalidates a verdict on the previous source.
Structured publication still requires the contract's clean committed candidate.
For PR review, confirm the head and relevant base/comparison remain current before
reporting PASS. A new head, relevant base change or accepted scope change requires
independent reassessment; no old verdict silently covers a new revision.

## Assess requirements and standards

- Compare the entire PR with the complete accepted spec and all subtasks,
  including cross-ticket interactions and missing requirements. Per-ticket
  verdicts support this assessment but cannot replace it. For scoped local
  review, use its accepted spec/ticket: missing or partial requirements,
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

When repairs are unauthorized, end with findings and remaining evidence gaps.
When implementation or repairs are authorized, repair blocking findings, select
checks for the actual repair, and obtain renewed independent review before
completion. The orchestrator coordinates repairs through the applicable ticket
review and root integration path, updating the same draft PR. Reassess affected
requirements, findings, interactions and checks, preserving mandatory freshness
and qualifying reuse. Keep earlier verdicts. Final PASS does not automatically
mark the PR ready or merge it; the default handoff remains draft under
[the shared lifecycle](../../../../docs/agents/issue-tracker.md#pr-delivery-and-issue-completion).
