# Structured implementation cycle

Read this when coordinating the structured path. Publication schemas and commands
remain in the [common contract](handoffs.md) and its stage references.

1. Claim each ready ticket through the issue tracker. Dispatch implementers in
   parallel where dependencies, ownership, and available agent slots permit.
   Give each an isolated worktree based on the integration branch. Preserve
   existing changes when correcting a worktree's starting point.

   Implementers read [candidate publication](handoff-candidate.md)
   before preparing their stage input.

2. The implementer applies `tdd` to features and behavior-changing fixes. Follow
   its [testing-boundary rules](../../tdd/SKILL.md#seams-where-tests-go) to preserve
   specified boundaries or select and record an established public interface
   when none is specified. Synchronize with the current integration tip and capture its full ID as `base_ref` at synchronization,
   before the final candidate checks. Follow the
   [stable-candidate checkpoint](../../../../docs/testing.md#stable-candidate-checkpoint):
   finish focused controls and known findings, confirm the check plan against
   the actual diff, commit stable source, then run
   required completion checks through the repository runner and retain receipts
   bound to that commit. Report the checked commit and clean checkout to the
   coordinator before publication. The coordinator then assigns the exact unused
   absolute attempt for that ticket/commit and returns it with the assessed
   checkout, candidate-input path, and candidate publication command. The initial
   dispatch may reserve the input path; it cannot know the final commit-derived
   attempt. Move prepared manual/native evidence from effort scratch to its final
   locations; keep runner receipts/logs in their original immutable run directories
   and reference them by absolute path. Author the input with every criterion, ownership, check, and material limit,
   and run the candidate writer and standalone candidate validator. Report the
   exact record path, commit, receipt paths/outcomes, and both publication/validation
   outcomes. Validate receipts against the coordinator's assigned requirements.
   Agents use assigned attempts; the coordinator owns allocation.

3. Dispatch an independent verifier when the candidate is ready. The verifier
   reads [independent verification](handoff-verification.md),
   inspects that commit in a separate checkout, checks the diff against the
   ticket/spec and approved presentation, and performs the checks needed to
   support a verdict. Execute checks assigned as fresh through its own runner
   invocation and receipt; apply the check-selection reference for other evidence. Validate
   candidate evidence and declared coverage against the independent requirements;
   keep manual/native observations distinct from covered automated checks. Dispatch
   includes the exact assigned attempt, clean assessed candidate checkout,
   verifier-input path, independent requirements path, and verification publication
   command.
   The verifier owns the judgments and invokes the verification writer for
   `PASS`, `REWORK`, or `BLOCKED`, then runs the standalone verification validator
   before reporting the path and outcomes. Distinct actor IDs alone establish no
   independent review. Preserve the candidate's code and actual user acceptance
   gates.

4. For `REWORK`, send the findings pointer to the implementer. Repair produces a
   new candidate commit and directory, followed by new verification. For
   `BLOCKED`, record the unavailable prerequisite in the ticket and continue
   independent ready work. Once it becomes available, follow the contract's
   [retry procedure](handoff-retry.md#retry-an-unchanged-candidate) to create
   another attempt for the same commit through `carry-forward` with fresh
   verification. The coordinator supplies exact source/destination attempts,
   candidate checkout, carry-input path, and command, and records the reason and
   both paths in the ticket. Preserve the earlier verdict. Advance to integration
   only after a valid `PASS`.

5. Serialize merges through the merger, which reads
   [integration publication](handoff-integration.md). It confirms the candidate and verdict
   refer to the same ticket and commit, captures the full integration tip as
   `previous_tip_ref` immediately before the actual merge, then
   integrates the verified commit. Abort an unfinished conflicting merge before
   returning repair to the implementer; substantive integration repairs need a
   new candidate and verification. Reassess checks for the actual combined result;
   an unchanged fast-forward may reuse qualifying evidence under the assigned
   requirements. Run required fresh checks through the runner, validate receipts
   and coverage, and invoke
   the integration writer using the assigned attempt, actual integration checkout,
   merger-input path, and independently assigned integration requirements. The writer
   binds the exact verifier bytes
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
