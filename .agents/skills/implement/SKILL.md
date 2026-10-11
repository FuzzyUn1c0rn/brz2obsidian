---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

Use `tdd` for behavioral changes at already approved public testing boundaries.

Run focused checks during development and the final checks required by the ticket
through [the repository runner](../../../docs/testing.md#automated-check-runner).
Record expected scope before final validation; report the receipt path and outcome.

Review the actual changes against the accepted requirements and repository
standards, following the [final review procedure](../implement-spec-enhanced/references/final-review.md).

Commit your work to the current branch.
