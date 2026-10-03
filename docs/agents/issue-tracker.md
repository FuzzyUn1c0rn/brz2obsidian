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
