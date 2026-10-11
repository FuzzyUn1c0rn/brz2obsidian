---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

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

Commit your work to the current branch.
