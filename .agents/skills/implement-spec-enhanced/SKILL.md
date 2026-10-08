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

Read [the handoff contract](references/handoffs.md) before dispatch; it is the
authoritative publication, input, evidence, and transition reference. Use its
`write_handoff.py` CLI for every candidate, verification, integration, and
carry-forward publication, followed by the explicit standalone validator.
Choose one absolute shared root under `tmp/<effort>/handoffs/` in the integration
checkout.
All agents receive that root, the spec and ticket pointers, integration branch,
assigned files, and relevant testing instructions. Give absolute interpreter,
script, assessed-checkout, and stage-input pointers so commands also work from
another checkout. The ticket remains the source of truth for scope, ownership,
blockers, and durable completion state.

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
   integration tip and capture its full ID as `base_ref` at synchronization,
   before the final candidate checks. Commit the completed changes and report
   the commit and clean checkout to the
   coordinator before publication. The coordinator then assigns the exact unused
   absolute attempt for that ticket/commit and returns it with the assessed
   checkout, candidate-input path, and candidate publication command. The initial
   dispatch may reserve the input path; it cannot know the final commit-derived
   attempt. Move prepared evidence from effort scratch to its final locations,
   author the input with every criterion, ownership, check, and material limit,
   and run the candidate writer and standalone candidate validator. Report the
   exact record path, commit, and both outcomes. Agents use assigned attempts;
   the coordinator owns allocation.

3. Dispatch an independent verifier when the candidate is ready. The verifier
   inspects that commit in a separate checkout, checks the diff against the
   ticket/spec and approved presentation, and performs the checks needed to
   support a verdict. Dispatch includes the exact assigned attempt, clean assessed
   candidate checkout, verifier-input path, and verification publication command.
   The verifier owns the judgments and invokes the verification writer for
   `PASS`, `REWORK`, or `BLOCKED`, then runs the standalone verification validator
   before reporting the path and outcomes. Distinct actor IDs alone establish no
   independent review. Preserve the candidate's code and actual user acceptance
   gates.

4. For `REWORK`, send the findings pointer to the implementer. Repair produces a
   new candidate commit and directory, followed by new verification. For
   `BLOCKED`, record the unavailable prerequisite in the ticket and continue
   independent ready work. Once it becomes available, follow the contract's
   [retry procedure](references/handoffs.md#retry-an-unchanged-candidate) to create
   another attempt for the same commit through `carry-forward` with fresh
   verification. The coordinator supplies exact source/destination attempts,
   candidate checkout, carry-input path, and command, and records the reason and
   both paths in the ticket. Preserve the earlier verdict. Advance to integration
   only after a valid `PASS`.

5. Serialize merges through the merger. It confirms the candidate and verdict
   refer to the same ticket and commit, captures the full integration tip as
   `previous_tip_ref` immediately before the actual merge, then
   integrates the verified commit. Abort an unfinished conflicting merge before
   returning repair to the implementer; substantive integration repairs need a
   new candidate and verification. Run checks appropriate to the combined result
   and invoke the integration writer using the assigned attempt, actual integration
   checkout, and merger-input path. The writer binds the exact verifier bytes
   and inspected result. Run the standalone integration validator against the
   clean result, including failed outcomes. Resolve the ticket only after it
   validates successfully and all required acceptance gates are satisfied.
   If integration is held by a temporary check or prerequisite, use a new
   attempt for the unchanged candidate when it becomes available. Reuse the
   passing verification only with explicit still-applicable PASS rationale in the
   carry input. Carry against the unchanged candidate checkout; inspect the current
   integration checkout for fresh integration, including already-incorporated
   candidates. Preserve any reported partial attempt and obtain a new unused
   assignment before retrying; follow the contract's recovery instructions.

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
