# Issue tracker: Local Markdown

Issues and specs live as Markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`.
- Specs live at `.scratch/<feature-slug>/spec.md`.
- Implementation tickets live at
  `.scratch/<feature-slug>/issues/<NN>-<slug>.md`,
  numbered from `01`, with one file per ticket.
- Record triage state as a `Status:` line near the top.
  Use the strings in `triage-labels.md`.
- Append comments and conversation history under `## Comments`.

## Publish to the issue tracker

Create the spec or individual ticket at its conventional path,
creating directories as needed.

## Fetch the relevant ticket

Read the referenced file. Resolve an issue number within its
feature directory; ask for the feature when ambiguous.

## Implementation operations

1. Read the feature's index and accepted specification. Choose a
   `ready-for-agent` ticket whose linked blockers are all `resolved`.
   Ready-for-agent means specified; blockers still govern when work starts.
2. Before implementation, set `Status: claimed` and record `Assignee:`
   with the working session or agent identifier. Save the claim.
3. Implement the ticket's scope and verify its acceptance criteria through
   the documented test seams. Record a scope conflict or unresolved
   criterion in Comments rather than treating it as complete.
4. Check each acceptance box only after its criterion is satisfied.
   Append the verification commands/results and any material limits under
   Comments. Set `Status: resolved` only when all criteria are satisfied.

Dependencies and issue numbers are local to the implementation feature.
Completed Wayfinder tickets remain decision evidence; implementation has
its own index and tickets rather than new children on the completed map.

## Wayfinding operations

- Map: `.scratch/<effort>/map.md`, containing Notes,
  Decisions-so-far, and Fog.
- Child ticket: `.scratch/<effort>/issues/NN-<slug>.md`.
  Record its type in `Type:` (`research`, `prototype`,
  `grilling`, or `task`).
- Blocking: record `Blocked by: NN, NN` near the top.
  A ticket is unblocked when all listed tickets are resolved.
- Frontier: select the first open, unblocked, unclaimed ticket
  by number.
- Claim: set `Status: claimed` and save before starting work.
- Resolve: append the answer under `## Answer`, set
  `Status: resolved`, and add a summary and link to the map's
  Decisions-so-far.
