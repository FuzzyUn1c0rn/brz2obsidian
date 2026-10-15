---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

For an explicit read-only review or plan, return that assessment without branch
setup, claims, implementation or publication. For authorized implementation,
retain the assigned/recorded root or follow
[initial feature-root setup](../../../docs/agents/issue-tracker.md#establish-the-feature-root)
before claims or changes: branch from `main`, otherwise retain the current branch.
Record and preserve that root and existing work throughout the effort.

Apply `tdd` to features and behavior-changing fixes. Use testing boundaries
specified in the conversation, accepted specification, or ticket, recording
their decision source. If none is specified, select an established public
interface that can demonstrate the requested behavior, and record the choice
and rationale. Ask when a material interface or acceptance decision remains
unresolved, or the choice would contradict an explicit testing decision.
Continue independent work while it is unresolved; preserve settled decisions.

Run focused checks during development and the final checks required by the ticket
through [the repository runner](../../../docs/testing.md#automated-check-runner).
Record expected scope before final validation; report the receipt path and outcome.

Review the actual changes against the accepted requirements and repository
standards, following the [final review procedure](../implement-spec-enhanced/references/final-review.md).

Commit and integrate work into that recorded root, preserving existing work.
An assigned ticket worker reports to the outer orchestrator and creates no
delivery PR. Its handoff includes known checked-candidate and integration commit
IDs, review/receipt pointers and outcomes, and explicit missing evidence or limits.
Do not infer commit identities or qualifying evidence from a reported stage PASS.
Under [the shared lifecycle](../../../docs/agents/issue-tracker.md#pr-delivery-and-issue-completion),
internal subtasks complete on the root. The orchestrator creates one draft PR
only after the full effort's implementation is assembled, then assigns independent
review of that full PR and repairs it in place. A standalone request is one effort.
Leave the PR draft by default; later readiness and merge require applicable user
authorization. Respect explicit publication constraints.
