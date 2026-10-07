---
name: implement-spec-enhanced
description: "Implement a specification and ticket graph with structured implementation, verification, and integration handoffs."
---

# Implement Spec Enhanced

Workspace-local adaptation of `implement-spec`. Implement the accepted spec on
one integration branch, resolving its ticket graph through independently
verified candidates. Use this copy when structured handoffs are wanted; the
original skill remains available.

## Prepare

Read the accepted spec, implementation index, and issue-tracker instructions.
Select only tickets whose blockers are resolved. Reuse a suitable integration
branch or create one, recording its starting commit for the final review.

Read [the handoff contract](references/handoffs.md) before dispatch. Choose one
absolute shared root under `tmp/<effort>/handoffs/` in the integration checkout.
All agents receive that root, the spec and ticket pointers, integration branch,
assigned files, and relevant testing instructions. The ticket remains the source
of truth for scope, ownership, blockers, and durable completion state.

Use stable implementer, verifier, and merger responsibilities. Use available
general-purpose agents if a configured role expects a different workflow; this
skill needs no hidden guard metadata or workflow-specific companion skill. Workers share the
workspace: assign disjoint files where possible and preserve others' edits.

Delegate exploration only for a concrete unresolved question. Save temporary
notes under the effort's `tmp/` directory; retain decisions in the ticket or spec.
Native investigation and approved presentation follow the repository guidance.

## Implement, verify, integrate

1. Claim each ready ticket through the issue tracker. Dispatch implementers in
   parallel where dependencies, ownership, and available agent slots permit.
   Give each an isolated worktree based on the integration branch. Preserve
   existing changes when correcting a worktree's starting point.

2. The implementer builds the ticket through its accepted public testing seams,
   consulting `tdd` for behavioral changes. Synchronize with the current
   integration tip before the final candidate checks. Commit the completed
   changes, leave the worktree clean, and publish `candidate.json` in the first
   attempt directory for that commit. Record every acceptance criterion,
   changed-file ownership, checks, evidence, and material limits. Validate the
   candidate and notify the coordinator with its path and commit.

3. Dispatch an independent verifier when the candidate is ready. The verifier
   inspects that commit in a separate checkout, checks the diff against the
   ticket/spec and approved presentation, and performs the checks needed to
   support a verdict. It owns `verification.json`, with `PASS`, `REWORK`, or
   `BLOCKED` and criterion-level evidence. It preserves the candidate's code.
   Validate the record before reporting its path and verdict.

4. For `REWORK`, send the findings pointer to the implementer. Repair produces a
   new candidate commit and directory, followed by new verification. For
   `BLOCKED`, record the unavailable prerequisite in the ticket and continue
   independent ready work. Once it becomes available, follow the contract's
   [retry procedure](references/handoffs.md#retry-an-unchanged-candidate) to create
   another attempt for the same commit and dispatch fresh verification. Preserve
   the earlier verdict. Advance to integration only after a valid `PASS`.

5. Serialize merges through the merger. It confirms the candidate and verdict
   refer to the same ticket and commit, captures the integration tip, then
   integrates the verified commit. Abort an unfinished conflicting merge before
   returning repair to the implementer; substantive integration repairs need a
   new candidate and verification. Run checks appropriate to the combined result
   and publish `integration.json`, bound to the verifier record
   and resulting commit. Resolve the ticket only after this record validates
   successfully and all required acceptance gates are satisfied.
   If integration is held by a temporary check or prerequisite, use a new
   attempt for the unchanged candidate when it becomes available. Reuse the
   passing verification only while its evidence remains applicable.

6. Save the durable conclusion, commits, verification results, evidence-reuse
   rationale, and material limits in the ticket. Update the frontier and dispatch
   newly unblocked work. If the tracker requires PRs or the user requested one,
   open a draft after the first integration commit and link the spec/tickets.

## Coordination and finish

Dispatch messages carry pointers and ownership, completion messages carry a
manifest path and outcome. Read records on completion, rework, or a meaningful
state change. Use completion events or bounded waits instead of repeatedly
requesting unchanged status. Send human updates for progress, blockers, and
decisions that matter. The contract defines evidence reuse; a new commit alone
does not require repeating every native check.

After all tickets integrate, use `code-review` against the recorded starting
commit and accepted spec. Route fixes through the same candidate/verifier/merger
sequence. Preserve any required user acceptance gate. Mark a requested PR ready
only when required checks and reviews pass, or otherwise report the completed
integration branch. Retain durable results before archiving managed worktrees
through their lifecycle and retiring disposable handoff files.
