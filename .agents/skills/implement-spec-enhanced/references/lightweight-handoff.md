# Lightweight report and documentation handoffs

Use this path for a report-only update or a small, bounded correction to
non-executable documentation. It retains an author, a different independent
reviewer, and serialized application by the coordinator. One short Markdown
review record replaces three structured JSON records and their publication
handshakes; a dedicated merger agent and separate review worktree are optional.
Structured writer/validator schemas remain unchanged and do not validate this path.

## Eligibility

The coordinator selects this path before dispatch and records why the proposed
change qualifies. The reviewer confirms eligibility against the actual diff.

Eligible examples include recording an already-given user verdict, correcting a
current-version table, fixing prose/links, or adding a missing description of
already implemented support. Verify those facts against their original sources.

Use the structured path for runtime/generated-output changes, tests, executable
examples or commands, tools, dependencies/configuration, CI, agent instructions
or workflow rules, and changes to acceptance criteria or evidence contracts.
A report that changes a verdict or reveals an unresolved behavioral finding needs
that finding handled at its actual scope. If the ticket explicitly requires
structured transitions or fresh checks, preserve those obligations; eligibility
alone does not waive them. Size is judged by a clearly reviewable bounded diff,
not a line-count threshold.

## Prepare, review and apply

1. Claim the eligible ticket. Record its spec/criteria, assigned files, selected
   path and [check plan](check-scope.md). The author prepares the bounded change
   in a suitable existing checkout; an isolated worktree is useful when other
   work would interfere. Commit a clean candidate and record the full base and
   candidate IDs. Run required checks through the repository runner, preserving
   receipt paths and validating them against separately selected requirements.

2. Create `tmp/<effort>/reviews/<ticket>/<full-candidate-id>.md` with the candidate
   identity, checkout, diff command, criteria, plan, original evidence pointers
   and limits. Dispatch that pointer and authoritative sources to a different
   reviewer. The reviewer may read the same frozen clean checkout; confirm HEAD
   and clean state before and after review, and keep review artifacts ignored.
   Serialize review/check execution with author mutations. A separate actor ID
   without a separate person's/agent's actual review is insufficient.

3. The reviewer appends its actor identity, eligibility/coverage judgment,
   criterion outcomes, observations and verdict (`PASS`, `REWORK` or `BLOCKED`).
   Inspect the actual diff and source facts; validate submitted runner evidence
   against the independently selected requirements. Execute fresh checks only
   where the plan or review needs them. Existing user/native/archive verdicts
   remain actual evidence with their original scope; unrelated runtime reruns
   are unnecessary. `PASS` requires all candidate criteria satisfied, required
   checks passing, and no unresolved finding or candidate acceptance gate.
   Remote delivery remains a separate issue-completion gate.

4. For `REWORK`, prepare a new candidate and record, retaining the earlier finding
   and verdict. For `BLOCKED`, retain the missing prerequisite and leave the ticket
   open. A source change after review invalidates the approval of that new source.
   If scope expands beyond eligibility or integration requires conflict repair,
   switch to the structured path with a new plan; keep the lightweight history.

5. After `PASS`, the coordinator captures the current integration tip, then
   fast-forwards to the reviewed candidate, or confirms it is already the exact
   clean integration HEAD. A moved tip requires reassessment of the combined diff
   and evidence before application; obtain renewed independent review if the
   assessed candidate/context changes. Record previous/result IDs, exact reviewed
   record and applicable receipt/reuse facts. Run any required integration checks;
   a fast-forward alone is not proof that evidence applies.

6. Append the local application result and preserve the review record.
   Publish a concise durable issue comment covering the selected path/rationale,
   author/reviewer identities, reviewed/result commits, each acceptance outcome,
   verdict, checks/receipt outcomes, historical reuse and material limits. Follow
   [PR delivery and issue completion](../../../../docs/agents/issue-tracker.md#pr-delivery-and-issue-completion)
   after the first publishable integration commit for default draft publication
   and closure after merge into `main`; append the delivery outcome when known.
   Private evidence stays local. The parent feature's final review still applies.

The record is a review aid, not a machine-validated structured transition. Failed
reviews and superseded candidates remain evidence; never report them as passing
handoff-validator results or infer approval from the record's existence.
