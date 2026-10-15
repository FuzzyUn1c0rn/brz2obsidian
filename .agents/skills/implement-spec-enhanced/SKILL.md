---
name: implement-spec-enhanced
description: Implement an accepted specification or ticket graph with scoped checks and independent review.
---

# Implement Spec Enhanced

Implement the complete accepted specification on one feature root. Independently
review tickets before integration; the outer orchestrator creates one draft PR
after implementation is assembled, then assigns independent review of that PR.

## Route the request

For an explicit read-only review or planning request, inspect the relevant scope,
source and evidence and return findings or a plan in the conversation. Reuse
already approved requirements and decisions. Apply the relevant assessment guidance
in [final review](references/final-review.md) for a review. End this route with the
requested findings or plan; implementation preparation, claims, branch changes,
dispatch and repairs require implementation authorization. Relevant read-only
inspection is allowed within the requested scope.

For authorized implementation, continue below.

## Prepare and choose the implementation path

Read the accepted spec and ticket/index. Complete
[frontier discovery](../../../docs/agents/issue-tracker.md#discover-the-implementation-frontier)
before claim or dispatch. Record eligible leaves, an established leaf result, or
explicitly authorized combined scope. Before implementation, claims or dispatch,
retain the assigned/recorded root or follow
[initial feature-root setup](../../../docs/agents/issue-tracker.md#establish-the-feature-root):
on `main`, create a local feature branch; otherwise retain the current branch.
Record and preserve its root identity and full starting commit across the effort.

Define completion from the accepted requirements, required checks, independent
review and any actual-user/native gate. Reuse already approved scope and
presentation decisions. Follow the [TDD testing-boundary rules](../tdd/SKILL.md#seams-where-tests-go)
to preserve specified boundaries or select and record an established public
interface when none is specified. Resolve only missing decisions that materially
affect the work; continue independent authorized work meanwhile.

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
ownership and available slots permit; serialize integration. On the structured
path, give implementers isolated worktrees with the feature root's current tip
passed explicitly as their base;
lightweight work follows its frozen-checkout and serialization safeguards.
Preserve others' edits and existing work when correcting a starting point.
Delegate exploration only for a
concrete unresolved question.

Supply the spec/ticket pointers, branch, assigned files, selected path and check
rationale. For checks, supply absolute assessed-checkout, project-interpreter and
runner paths, required scope/freshness and the
[runner receipt contract](../../../docs/testing.md#automated-check-runner).
Workers share a workspace: state ownership and the requirement to preserve
others' edits in each assignment.
When scope lives in GitHub Issues, use [preserved issue sources](references/issue-sources.md)
so structured reviews assess the same accepted content across worktrees.

For structured stages, choose an absolute shared root under
`tmp/<effort>/handoffs/` in the integration checkout. The coordinator assigns
attempts and independent requirements; dispatch exact attempt, stage-input,
requirements and command pointers. Use `write_handoff.py` and the standalone
validator at every publication/transition. Submitted results cannot narrow
assigned requirements. Follow the linked stage contracts for commit capture,
clean assessed checkouts, immutable evidence, repairs and unchanged-candidate
retries. Advance to integration only after valid independent `PASS`.

Follow the [stable-candidate checkpoint](../../../docs/testing.md#stable-candidate-checkpoint):
finish focused development checks and known findings, commit stable source, then
run required completion checks. Apply [check selection](references/check-scope.md)
for coverage and evidence reuse, preserving required fresh, native and accepted
presentation gates.

## Coordinate and finish

Dispatch messages carry pointers and ownership; completion messages carry the
manifest or lightweight review record, receipt paths and outcomes. Read records
on completion, rework or a meaningful state change. Use completion events or
bounded waits; update the user on meaningful progress, blockers and decisions.
Save temporary notes under `tmp/<effort>/` and durable conclusions in the ticket.

Complete verified internal subtasks on the feature root under
[the shared lifecycle](../../../docs/agents/issue-tracker.md#pr-delivery-and-issue-completion),
so same-root dependencies can advance. Ticket workers report results to the
orchestrator; they do not publish delivery PRs.

The outer orchestrator reconciles the full scope and subtask graph. Once all
implementation is complete and integrated and pre-publication gates pass, it
creates the single draft PR from the feature root to `main`, linked to the spec.
Then assign an independent reviewer to the entire PR using
[final review](references/final-review.md). Repair findings on the same root/PR
with renewed independent review. The default handoff remains draft, even after
PASS; later readiness and merge follow applicable user authorization.

Report the feature root, PR revision, verdict and remaining gates. Retain durable
results before
archiving managed worktrees and retiring disposable evidence under
[workspace housekeeping](../../../docs/workspace.md).
