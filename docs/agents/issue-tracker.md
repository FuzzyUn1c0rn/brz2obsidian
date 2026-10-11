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
- Close: `gh issue close <number> --reason completed` after the applicable
  [completion conditions](#pr-delivery-and-issue-completion) and recorded results.

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
For structured implementation handoffs, preserve the accepted body/comments
using [GitHub scope snapshots](../../.agents/skills/implement-spec-enhanced/references/issue-sources.md).
Records use the issue URL as identity; local snapshots retain the exact assessed
scope while GitHub remains authoritative for current state.

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
   verification commands, results and material limits in comments. Follow
   [PR delivery and issue completion](#pr-delivery-and-issue-completion) for
   publication, readiness and closure.

## PR delivery and issue completion

For authorized repository implementation, publish the integration branch and open
a draft delivery PR targeting `main` after the first publishable integration
commit, on structured, lightweight and ordinary implementation paths. Reuse a
suitable existing open delivery PR instead of duplicating it; preserve an already
ready status while its readiness evidence remains applicable. Confirm its
repository, base, branch and head correspond to this implementation effort.
Respect explicit user publication constraints and read-only
or planning requests. When publication is unavailable or prohibited, record the
local result and remaining delivery gate and keep the implementation issue open.

The PR head must be a branch distinct from `main`. If the work is already
committed locally on `main`, publish it from a separate integration branch.
Do not push `main` as a substitute for PR delivery.

Use the [PR skill](../../.agents/skills/pr/SKILL.md) for the body. Link the accepted
specification and tickets; record the delivery PR URL in each associated issue.
For a new PR, use an already published head and an explicit base:

```powershell
gh pr create --repo FuzzyUn1c0rn/brz2obsidian --draft --base main --head <integration-branch> --title "..." --body-file tmp/<effort>/pr-body.md
```

Local candidate/verification PASS and integration establish stage results.
GitHub merge is a delivery gate for issue completion, not a prerequisite for
those local judgments or draft publication. All other assigned acceptance gates
retain their stage requirements. Mark a delivery PR ready only after required
checks, independent review, final aggregate review and applicable user/native
gates pass for its current head and scope. PR creation or readiness supplies no
authorization to merge; a remote merge requires user authorization.

Before closing an implementation issue, obtain fresh GitHub state for the exact
associated delivery PR, for example:

```powershell
gh pr view <delivery-pr-number> --repo FuzzyUn1c0rn/brz2obsidian --json number,url,state,isDraft,baseRefName,headRefName,headRefOid,mergedAt,mergeCommit,closingIssuesReferences
```

Closure requires `state: MERGED`, `baseRefName: main`, a non-null `mergedAt` and
`mergeCommit.oid`, and every applicable acceptance/review gate satisfied. Verify
that the merged PR actually delivers this issue's accepted scope and reviewed
result: an unrelated merged PR or a stale head missing later accepted changes
does not qualify. Inspect its diff/commits and the delivered result as needed;
GitHub's merge evidence supports squash and rebase, so do not require the local
candidate commit to be an ancestor of `main`.

Record the PR URL, assessed/delivered head, target base, merge time and merge
commit together with criterion/review outcomes and material limits in the issue
before closing it. Local integration, handoff PASS, readiness, draft/open state,
closed-unmerged state, merge into another base, or unavailable merge evidence
keeps the issue open. Retain the claim and dependency/blocker semantics while
awaiting delivery; local completion does not unblock a dependency requiring a
closed issue. Use plain issue links in a PR body until closure gates are met;
auto-closing keywords must not bypass unresolved acceptance gates.

Answer-only, research or planning tickets that change no repository content need
no delivery PR. Record their answer/evidence and close only when their own
accepted criteria are satisfied.

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
- Resolve: record the answer and evidence; close under the applicable
  [completion conditions](#pr-delivery-and-issue-completion), then append a summary
  and issue link to the map's Decisions-so-far.

## Pull requests as a triage surface

**PRs as a request surface: no.**

Issues remain the intake, accepted scope, triage and dependency surface. Delivery
PRs carry implementation review and merge evidence under the lifecycle above;
their existence or readiness does not replace an issue's triage status or claim.

## Migrated history and temporary artifacts

On 2026-10-07, existing local specifications, Wayfinder maps, implementation
indexes and tickets moved to GitHub. Completed work is closed and labelled
`historical`; original status lines, comments and local ticket numbers in those
bodies are historical evidence. Use the issue's current state and native
relationships for tracking. The [migration index](https://github.com/FuzzyUn1c0rn/brz2obsidian/blob/05b36923cd330261973bd35e19e6fa20ada88290/docs/history/README.md) maps
former paths to GitHub issues. Supporting research and verification reports are
retained in the linked Git snapshot. Historical evidence links use that fixed
revision; current decisions and completion state live in GitHub Issues.

Use `.scratch/<effort>/` only for disposable local artifacts, such as draft
issue bodies and exploratory notes. It is Git-ignored. Publish accepted specs,
maps, tickets, decisions and durable conclusions to GitHub before removing any
temporary working copy. See [workspace housekeeping](../workspace.md).
