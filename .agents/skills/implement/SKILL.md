---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

Call the Skill tool with "tdd" where possible, at pre-agreed seams.

Run focused checks during development and the final checks required by the ticket
through [the repository runner](../../../docs/testing.md#automated-check-runner).
Record expected scope before final validation; report the receipt path and outcome.

Once done, call the Skill tool with "code-review" to review the work.

Commit your work to the current branch.
