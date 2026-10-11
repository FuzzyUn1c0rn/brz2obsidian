---
name: implement-spec-enhanced
description: Implement an accepted specification or ticket graph with scoped checks and independent review.
---

# Implement Spec Enhanced

Implement the accepted scope on one integration branch, preserving its acceptance
criteria and existing work. This is the repository's implementation workflow for
specifications and ticket graphs.

## Prepare and choose the path

Read the accepted spec and ticket/index. Complete
[frontier discovery](../../../docs/agents/issue-tracker.md#discover-the-implementation-frontier)
before claim or dispatch. Record eligible leaves, an established leaf result, or
explicitly authorized combined scope. Reuse a suitable integration branch or
create one; record the full starting commit for final review.

Define completion from the accepted requirements, required checks, independent
review and any actual-user/native gate. Reuse already approved scope, testing
boundaries and presentation decisions. Resolve only missing decisions that
materially affect the work; continue independent authorized work meanwhile.
A read-only review or planning request produces findings without implementation.

Choose coverage using [check selection](references/check-scope.md), recording
the rationale independently of submitted results and confirming it against the
actual diff before completion checks.

- For eligible report-only or small non-executable documentation corrections,
  use [lightweight handoffs](references/lightweight-handoff.md).
- For substantive changes, including agent instructions or workflow rules, use
  the [structured handoff contract](references/handoffs.md). Coordinators read
  the [implementation cycle](references/implementation-cycle.md) and
  [dispatch details](references/handoff-dispatch.md). Publishers and transition
  reviewers read the common contract, requirements/evidence and validation, then
  only their applicable stage reference.

Both paths retain issue claiming, independent review and mandatory acceptance
gates. The ticket remains authoritative for scope, ownership and durable status.

## Dispatch and preserve evidence

Use available general-purpose agents with stable implementer, verifier and merger
responsibilities. Parallelize independent ready tickets when dependencies,
ownership and available slots permit; serialize integration. Give implementers
isolated worktrees based on the integration branch. Preserve others' edits and
existing work when correcting a starting point. Delegate exploration only for a
concrete unresolved question.

Supply the spec/ticket pointers, branch, assigned files, selected path and check
rationale. For checks, supply absolute assessed-checkout, project-interpreter and
runner paths, required scope/freshness and the
[runner receipt contract](../../../docs/testing.md#automated-check-runner).
Workers share a workspace: state ownership and the requirement to preserve
others' edits in each assignment.

For structured stages, choose an absolute shared root under
`tmp/<effort>/handoffs/` in the integration checkout. The coordinator assigns
attempts and independent requirements; dispatch exact attempt, stage-input,
requirements and command pointers. Use `write_handoff.py` and the standalone
validator at every publication/transition. Submitted results cannot narrow
assigned requirements. Follow the linked stage contracts for commit capture,
clean assessed checkouts, immutable evidence, repairs and unchanged-candidate
retries. Advance to integration only after valid independent `PASS`.

Finish focused controls and known findings before expensive completion checks,
following the [stable-candidate checkpoint](../../../docs/testing.md#stable-candidate-checkpoint).
Select the smallest coverage that meets the obligations. Once it passes, broaden
or repeat checks only for new changes, failures, unresolved concerns or explicit
fresh-execution requirements. Keep reused evidence's provenance and applicability;
it cannot satisfy a required fresh run. Native and accepted presentation evidence
retain their separate requirements.

## Coordinate and finish

Dispatch messages carry pointers and ownership; completion messages carry the
manifest or lightweight review record, receipt paths and outcomes. Read records
on completion, rework or a meaningful state change. Use completion events or
bounded waits; update the user on meaningful progress, blockers and decisions.
Save temporary notes under `tmp/<effort>/` and durable conclusions in the ticket.

After integration, perform [final review](references/final-review.md) against the
recorded starting commit and accepted scope. Reassess the path and checks for
each repair, retaining independent review and any required user verdict.
Mark a requested PR ready only when required checks and reviews pass; otherwise
report the integration branch and remaining gates. Retain durable results before
archiving managed worktrees and retiring disposable evidence under
[workspace housekeeping](../../../docs/workspace.md).
