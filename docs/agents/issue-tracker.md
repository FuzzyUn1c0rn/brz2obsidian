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
- Close: the orchestrator records evidence and closes internal subtasks after
  accepted integration into the feature root. Parent specification delivery uses
  [PR delivery and issue completion](#pr-delivery-and-issue-completion), including
  automatic closure on merge when eligible.

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
For same-spec dependencies, confirm the closed blocker's accepted result is in
the consuming candidate's feature-root base. A closed subtask records completion
on its recorded root, not availability on `main`; external or delivery-dependent
consumers must inspect the required delivery evidence as well.
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

This lifecycle applies to structured, lightweight and ordinary implementation.
Read-only reviews and planning perform no branch setup, claims, dispatch or
publication. Respect explicit user publication constraints.

### Establish the feature root

For a new effort, the outer orchestrator inspects the current branch before
implementation, claims or dispatch. On `main`, create and switch to a local
`codex/<effort>` branch; otherwise continue on the current branch. Assigned workers
and continuations use the already recorded/dispatched root; a worker's checkout
branch never replaces it. Read-only discovery may precede setup. Record the specification,
feature-root branch, integration checkout and full starting commit in the existing
effort record. Retain that root across subtasks, continuations and repairs,
preserving existing edits and commits. An unresolved branch/root identity must be
resolved before dependent work; never reset or replace it implicitly.

Every new implementation branch, including one created with a worktree, starts
from the feature root's current tip. Pass the root or its resolved full commit
explicitly to worktree creation; tool defaults may start from `main`. Supply root
identity and captured base in dispatches. Reviewer checkouts may assess exact
commits without creating a branch. Serialize ticket and intermediate side-branch
integration into the feature root. Upstream synchronization preserves that root
and requires reassessment of affected evidence; it does not deliver to `main`.

### Complete internal subtasks

The outer orchestrator owns issue bookkeeping and overall delivery. Implementers,
independent ticket reviewers and mergers report assigned results; finishing a
ticket does not authorize them to create, mark ready or merge delivery PRs.

An internal subtask may close after its ticket-stage acceptance gates, independent
review and actual integration into the recorded feature root all pass. First
record the specification/root identity, candidate and integration commits,
criterion outcomes, qualifying checks, review verdict and material limits in the
ticket. A handoff PASS alone never closes it. Completed same-root subtasks can
unblock dependent implementation without a PR or merge to `main`.

Keep actual user/native prerequisites, external dependencies and explicit
delivery-dependent criteria. If a ticket requires post-delivery acceptance yet
must close before draft publication, report the scope/lifecycle conflict for
resolution; do not waive the gate or create an intermediate PR. Answer-only,
research and planning tickets need no delivery PR and close when their own
accepted criteria and evidence are satisfied.

### Publish one draft after implementation is assembled

The outer orchestrator reconciles the complete accepted scope and subtask graph,
including nested and newly discovered accepted work. Every implementation subtask
must be complete and integrated, and required pre-publication checks and gates
must pass. Held or unreviewed work remains unfinished. With no subtasks, assess
the accepted implementation scope directly. Record coverage and stage results;
independent final PR review is still pending, and later-stage gates retain their
assigned stage.

Only then does the outer orchestrator publish the feature root and create one
draft delivery PR from it to `main`, linked to the full specification and
subtasks. Use the [PR skill](../../.agents/skills/pr/SKILL.md) and record the URL
in the parent and relevant tickets. State that independent final review is pending.
For a new PR, use an already published head and explicit base:

```powershell
gh pr create --repo FuzzyUn1c0rn/brz2obsidian --draft --base main --head <feature-root> --title "..." --body-file tmp/<effort>/pr-body.md
```

For continuations or uncertain creation outcomes, inspect the exact specification,
root and existing delivery state before creating anything. Reuse the matching
draft and update it for repairs. An already ready, merged, closed or mismatched
legacy PR needs explicit reconciliation; it does not justify duplicate delivery
or rewriting history. If publication is unavailable or prohibited, retain the
root and local evidence and report the remaining gate with the parent open.

### Independently review and repair the draft

After creation, the orchestrator assigns an independent reviewer to the entire
draft PR under [final review](../../.agents/skills/implement-spec-enhanced/references/final-review.md).
Assess its full change set against the full accepted spec and subtasks, including
cross-ticket interactions and omissions. Ticket PASS records support this review;
the orchestrator's assessment does not replace it. Bind the verdict to the actual
PR base, head and comparison commits.

Coordinate repairs through the applicable candidate review and root integration
path, then update the same PR. New heads, relevant base changes and accepted scope
changes require independent reassessment of affected requirements, findings and
checks, retaining mandatory freshness and evidence-reuse rules. Resolve repair
tickets only after their gates pass. Preserve earlier findings and verdicts.

The default handoff remains draft, with the current independent verdict and
remaining gates reported. Agent checks or final PASS do not automatically mark
it ready or merge it. Later readiness and remote merge follow applicable user
authorization; reuse existing authorization within its scope without asking again.

### Deliver and close the parent specification

Keep the parent open through draft publication and final review. Parent completion
requires actual delivery to `main` and every assigned acceptance gate. Use ordinary
issue references while closure conditions remain unresolved. For a later authorized
readiness transition, record current acceptance/review outcomes and limits. If
merge into `main` is an issue's only remaining condition, add `Closes #<number>`
with one reference per eligible issue. Already completed internal subtasks need no
deferred auto-closure. Keep ordinary references for partial scope and post-merge
acceptance; closing keywords must not bypass gates.

Verify that the PR targets `main`, that `main` is the repository's default branch,
and that `closingIssuesReferences` matches the intended issues before readiness.
Reassess closing references when scope or applicable readiness evidence changes;
remove any that are no longer justified. For readiness checks and after merge,
obtain fresh GitHub state for the exact associated delivery PR, for example:

```powershell
gh pr view <delivery-pr-number> --repo FuzzyUn1c0rn/brz2obsidian --json number,url,state,isDraft,baseRefName,headRefName,headRefOid,mergedAt,mergeCommit,closingIssuesReferences
```

Automatic closure requires the repository setting **Settings → General → Issues →
Auto-close issues with merged linked pull requests** to be enabled. Confirm this
as a repository setup prerequisite; do not change it on every delivery. GitHub
interprets closing keywords in the PR description when the PR targets the default
branch. See [GitHub's linking rules](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue)
and [automatic closure setting](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/managing-auto-closing-issues).

After merge, verify merge evidence and each intended issue's closure with
`gh issue view <number> --json number,url,state,closedAt`.
Completed delivery requires `state: MERGED`, `baseRefName: main`, a non-null
`mergedAt` and `mergeCommit.oid`, and every applicable acceptance/review gate
satisfied. Verify
that the merged PR actually delivers this issue's accepted scope and reviewed
result: an unrelated merged PR or a stale head missing later accepted changes
does not qualify. Inspect its diff/commits and the delivered result as needed;
GitHub's merge evidence supports squash and rebase, so do not require the local
candidate commit to be an ancestor of `main`.

Record the PR URL, assessed/delivered head, target base, merge time and merge
commit together with final criterion/review outcomes and material limits in the
issue after automatic closure. If automatic closure did not occur, or an issue
has acceptance gates assigned after merge, record that evidence before manual
closure and close only when all applicable completion conditions pass.
Local integration, handoff PASS, PR readiness or draft/open state, a closed-unmerged
PR, another target base or missing merge evidence does not establish parent
delivery. Internal subtask completion follows the separate root-integration rule
above; never infer delivered-to-main availability from a closed subtask alone.

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
- Claim: assign the issue as the session's first issue-tracker write before
  implementation; feature-root setup precedes claiming.
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
