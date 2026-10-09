# Issue tracker: GitHub

Issues, accepted specifications and Wayfinder maps live in GitHub Issues for
`FuzzyUn1c0rn/brz2obsidian`.
Use the `gh` CLI from this checkout, or pass
`--repo FuzzyUn1c0rn/brz2obsidian` explicitly.

## Conventions

- Create: `gh issue create --title "..." --body-file <path> --label <label>`.
  Store temporary UTF-8 body files under `tmp/<effort>/`.
- Read: `gh issue view <number> --comments`; fetch labels, assignees and state
  with `gh issue view <number> --json number,title,body,labels,assignees,state`.
- List: `gh issue list --state open --json number,title,body,labels,assignees`.
  Apply `--label` and `--state` filters as appropriate.
- Comment: `gh issue comment <number> --body-file <path>`.
- Apply or remove labels: `gh issue edit <number> --add-label "..."` or
  `--remove-label "..."`. Use the mapping in `triage-labels.md`.
- Claim: `gh issue edit <number> --add-assignee @me`. Record the working
  session or agent identifier in a comment when sharing a GitHub account.
- Close: `gh issue close <number> --reason completed` after recording results.

GitHub issue numbers are repository-wide, shared with pull requests. Use full
URLs for cross-repository references and distinguish legacy local ticket numbers
by their feature path.

## Publish to the issue tracker

Create a GitHub issue. Include the accepted scope, acceptance checklist,
dependencies, and verification boundary. When publishing an existing local spec,
include its complete requirements so the issue is usable without an unpublished
file. Link authoritative references and identify the source path.

## Fetch the relevant ticket

Run `gh issue view <number> --comments` and inspect its labels, assignees,
dependencies and state before acting.

### Discover the implementation frontier

Before claim or dispatch, read the accepted parent/index and discover native
children and blockers with paginated requests. These read-only commands retain
current states and assignments on each page; replace `<number>` with the parent or ticket:

```powershell
gh api repos/FuzzyUn1c0rn/brz2obsidian/issues/<number> --jq '{number,state,assignees: [.assignees[].login],labels: [.labels[].name],sub_issues_summary,issue_dependencies_summary}'
gh api --paginate repos/FuzzyUn1c0rn/brz2obsidian/issues/<number>/sub_issues --jq 'map({number,title,state,assignees: [.assignees[].login],labels: [.labels[].name]})'
gh api --paginate repos/FuzzyUn1c0rn/brz2obsidian/issues/<number>/dependencies/blocked_by --jq 'map({number,title,state,assignees: [.assignees[].login]})'
```

Run blocker discovery for the selected ticket and every open child. Repeat child
discovery for a proposed ticket with children until the selected work is a leaf. Keep the parent's map
order when choosing eligible work. Check the parent and child bodies/comments for
task-list, `Part of #<parent>` and `Blocked by:` fallback relationships; resolve
each referenced issue's current state with `gh issue view <number> --json
number,state,labels,assignees`. Reconcile fallbacks with native relationships.

A leaf result requires successful child discovery, agreement with
`sub_issues_summary.total` when present, and inspection of fallback relationships.
An empty response alone or a failed/truncated request leaves discovery unresolved.
If native endpoints are unavailable, record that limit and use the documented
fallbacks only when they establish the complete relationships; otherwise resolve
the missing graph before dispatch.

Preparation is complete when a record under `tmp/<effort>/` identifies the
parent/ticket, discovered children, current states/assignments, blockers, and the
eligible selected leaf, established leaf result, or empty frontier with reasons.
Eligibility requires open
`ready-for-agent` work, all blockers closed, and no other claim. A parent with no
eligible children has an empty frontier; wait for a blocker or claim to resolve.
Record explicit user authorization for combined work with its scope and affected
child tickets instead of requiring leaf selection for that scope. Preserve that
authorization and record child completion individually against acceptance criteria.
Publish durable scope/authorization decisions in the issue after claiming.

## Implementation operations

1. Read the accepted specification and feature index or parent issue. Complete
   [frontier discovery](#discover-the-implementation-frontier) before choosing
   work. The `ready-for-agent` label means specified; dependencies and claims
   still govern when work starts.
2. Assign the issue before implementation and record the working session or
   agent identifier. An assigned issue is claimed.
3. Implement its scope and verify the acceptance criteria through the documented
   test seams. Comment on scope conflicts or unresolved criteria.
4. Check each acceptance box only after its criterion is satisfied. Record
   verification commands, results and material limits in comments. Close as
   completed only when every criterion is satisfied.

## Dependencies and wayfinding

- Map: one issue labelled `wayfinder:map`, with Notes, Decisions-so-far and Fog.
- Child: link each ticket as a native GitHub sub-issue of the map or feature
  issue. Use `gh issue create --parent <parent>` or
  `gh issue edit <parent> --add-sub-issue <child>`.
  If unavailable, use a task list in the parent and `Part of #<parent>` in
  the child. Wayfinding types use `wayfinder:<type>` labels (`research`,
  `prototype`, `grilling`, `task`); create those labels when needed.
- Blocking: use native GitHub dependencies. Add a blocker with
  `gh api --method POST repos/FuzzyUn1c0rn/brz2obsidian/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-database-id>`.
  Obtain the database ID with
  `gh api repos/FuzzyUn1c0rn/brz2obsidian/issues/<blocker> --jq .id`.
  This is the numeric database ID, distinct from the issue number and node ID.
  If native dependencies are unavailable, record `Blocked by: #<n>, #<n>` in
  the body. All blockers must be closed before work starts.
- Frontier: among the parent's open children, select the first in map order
  with no open blockers and no assignee. Native
  `issue_dependencies_summary.blocked_by` counts open blockers; otherwise
  inspect each issue referenced by the fallback line.
- Claim: assign the issue as the session's first write before starting work.
- Resolve: comment with the answer and evidence, close the ticket, and append
  a summary and issue link to the map's Decisions-so-far.

## Pull requests as a triage surface

**PRs as a request surface: no.**

## Migrated history and temporary artifacts

On 2026-10-07, existing local specifications, Wayfinder maps, implementation
indexes and tickets moved to GitHub. Completed work is closed and labelled
`historical`; original status lines, comments and local ticket numbers in those
bodies are historical evidence. Use the issue's current state and native
relationships for tracking. The [migration index](../history/README.md) maps
former paths to GitHub issues. Supporting research and verification reports
remain under `docs/history/`.

Use `.scratch/<effort>/` only for disposable local artifacts, such as draft
issue bodies and exploratory notes. It is Git-ignored. Publish accepted specs,
maps, tickets, decisions and durable conclusions to GitHub before removing any
temporary working copy. See [workspace housekeeping](../workspace.md).
