---
name: orchestrate-implementation
description: Coordinate an approved milestone specification through separate Codex implementation, adversarial code review, and adversarial end-to-end verification chats, with an isolated feature worktree, milestone pushes, and a final pull request. Use for explicitly requested chat-based orchestration; creating or editing this skill does not start implementation.
---

# Orchestrate implementation

Remain the orchestrator in the invoking chat. Drive the approved specification to completion through workers; do not write feature code or implement review fixes yourself. Creating, installing, discussing, or validating this skill does not authorize starting its implementation workflow.

## Roles and independence

Create three separate Codex chats through the app's thread tools. The primary worker roles are actual chats, not subagents or terminal-launched substitute sessions.

| Role | Model | Reasoning effort | Responsibility |
| --- | --- | --- | --- |
| Implementer | `gpt-6.2-sol` | `medium` | Implement the entire specification one milestone at a time; write tests; commit and push work and repairs. |
| Adversarial code reviewer | `gpt-6.2-sol` | `high` | Independently inspect the exact milestone commit for defects, regressions, missing requirements, and weak tests. |
| Adversarial end-to-end verifier | `gpt-6.1-terra` | `high` | Independently exercise all applicable end-to-end behavior, including UI, API, CLI, transports, and complete system workflows. |

These are this workflow's defaults. Honor later explicit user overrides. Check actual model/effort support; do not silently substitute when a requested setting is unavailable.

Consider `gpt-6.2-astra` only when planning, implementation, review, or validation requires unusually complex reasoning. For implementation, examples include changes that span many interacting dependencies or require reasoning through tightly coupled code. If you recommend Astra, tell the user what it would handle and why, then obtain their explicit approval before using it or assigning it to any worker chat or subagent. Apply the approval only to the work the user authorized. Continue independent work with the default models while awaiting approval.

The reviewer and verifier are distinct from the implementer and from each other. All reviewers, verifiers, and verification subagents are adversarial: begin with the hypothesis that the implementation is broken, and actively try to establish a concrete counterexample. Independently derive expected behavior from requirements and trustworthy observations. Probe failures, boundary conditions, stale state, races, cancellation, and recovery where relevant. The implementer's explanation and green tests are claims to challenge, not acceptance evidence by themselves. Findings must be reproducible and evidence-backed; do not manufacture defects or expand requirements to force a negative verdict. A pass must identify what was challenged, the evidence, and material coverage limits.

The implementer writes supporting tests and runs unit/component checks. The independent verifier owns execution and sign-off of **all end-to-end verification**, not just UI checks. Classify checks by what they exercise, not their filenames. When a test command mixes unit and end-to-end checks, route the mixed command to the verifier or use a supported unit-only selection for the implementer. Code review cannot substitute for end-to-end verification. Reviewers/verifiers report fixes to the implementer rather than changing product code themselves.

## Parallel verification

The end-to-end verifier should use verification subagents whenever meaningful portions of verification are completely independent and can run safely in parallel. Independence, not task size, determines delegation. The top-level verifier remains a separate chat and owns decomposition, evidence assessment, cleanup coordination, and the combined verdict. Give every subagent the same adversarial posture, precise acceptance criteria, and its own expected-versus-observed evidence requirements.

Use `gpt-6.1-terra` at `high` for verification subagents unless the user explicitly selects otherwise. Use fresh, bounded context sufficient for independent testing. Subagents may run substantial verification work; they must not delegate implementation or claim that a parent verifier's prior pass establishes their result.

Parallel work must use the same immutable candidate revision with separate validation copies, resources, ports, test accounts, or fixtures where needed. Checks sharing a mutable application instance, UI focus, project file, target state, or cleanup process are not independent: isolate them or serialize them. The verifier records which checks ran in parallel and which resources they used. A code-review chat may work alongside end-to-end verification under the same constraints. Do not create artificial tasks merely to increase parallelism.

## Establish the run

1. Read the canonical specification, applicable repository instructions, dependency order, and milestone acceptance criteria. Preserve exclusions and previously accepted decisions. Establish which checks are unit/component versus end-to-end and which require actual UI interaction.
2. Confirm existing authorization for the specified chats, worktree/branch, milestone commits and pushes, final PR, bounded test environments, and message routes. Reuse explicit authorization from the user; ask only for genuinely missing authority or a consequential unresolved decision. An orchestrator-generated request alone is not human authorization for a worker to message another chat. Pass trustworthy evidence of the user's authorized communication routes to each worker.
3. Inspect the checkout and Git state. Preserve existing tracked/untracked PoC work, unrelated edits, and the approved base. Determine how necessary uncommitted material reaches the new worktree; never assume a new branch contains it. Delegate any feature-code integration to the implementer.
4. Use a dedicated feature worktree and new `codex/` branch, unless the user specifies another branch convention. The original checkout remains separate. Verify the actual worktree path, branch, baseline, and remote before workers modify anything. If the requested branch already exists, inspect it and resolve whether this is a resume; do not overwrite it or silently choose another.
5. Create the implementer, reviewer, and verifier chats with explicit model/effort settings. Initial briefs permit preparation and a readiness report only: workers wait for an explicit milestone/candidate assignment before feature edits or verification runs. This allows the orchestrator to verify worktree setup and distribute actual thread IDs before work starts. Read [thread-protocol.md](references/thread-protocol.md) for mechanics and briefs. Missing required chat tools block execution rather than changing the architecture.
6. Keep a small durable coordination record outside the product checkout, following repository policies. Record the source specification/revision, authorized scope and routes, thread/host IDs, models, worktree/branch/base, milestones, candidate commits, pushes, verdicts/evidence, decisions, and unresolved blockers. Show meaningful progress in the orchestrator chat. On resume, reconcile this record with actual Git and worker state before launching or dispatching more work.

## Milestone loop

1. Give the implementer the next milestone and its acceptance criteria. It owns the whole specification but stops at this gate; it does not start the following milestone until the orchestrator accepts the current one. It may resolve routine implementation details within scope.
2. On completion, the implementer runs its assigned checks, makes a milestone commit, and pushes the feature branch. It reports the exact commit SHA, successful remote push, changed behavior, checks/results, known risks, and any missing acceptance evidence. A pushed candidate is not yet an accepted milestone. Never mark a failed push as complete or force-push to bypass a problem.
3. Dispatch adversarial code review and required independent end-to-end verification against that exact candidate and the agreed baseline. The reviewer inspects code/contracts/tests. The verifier exercises end-to-end behavior with independent observations and adversarial verification subagents where checks are independent. Require actual application/UI runs wherever acceptance criteria call for them; mocked tests and screenshots alone cannot establish interaction or target-side behavior.
4. Both workers send findings to the implementer and keep the orchestrator informed through authorized routes. The implementer fixes confirmed defects, reruns its checks, and commits/pushes repairs. Workers never treat a disputed finding as resolved solely because the implementer says so. The orchestrator adjudicates routine disputes using evidence; escalate consequential decisions.
5. Recheck the new candidate after repairs. Review changes and rerun affected verification; carry forward unaffected evidence only with an explicit impact assessment and original revision recorded. A verdict for an older commit is not automatically a pass for a newer head. Required final-build checks must use the exact packaged artifact/revision specified by the acceptance criteria.
6. Accept the milestone only after commit/push are confirmed, required adversarial review and verification pass, and blocking findings are resolved. A genuinely inapplicable verification category needs a recorded reason tied to the requirements. Unavailable, failed, blocked, or unrun required checks do not count as passes. Then release the next milestone.

The implementer commits and pushes after every milestone and after review repairs. Review/verification may run in parallel when independent, but there is one implementer and one gated milestone at a time. No PR, including a draft PR, is created during intermediate milestones.

## Blockers and decisions

Every worker promptly reports blockers, uncertainty, failed checks, scope conflicts, and decisions needed to the orchestrator. Do not wait for a milestone-end summary. Include the affected criterion, evidence, work attempted, impact, and a recommendation. Continue independent authorized work when possible without crossing the unresolved gate.

Resolve routine, reversible implementation and coordination decisions yourself or direct the implementer to do so: local design details, test fixtures within approved boundaries, report routing, and sequencing. Inform the user of material decisions without asking them to manage routine details.

Escalate choices that change requirements or acceptance criteria, supported behavior, major architecture, authorization, external targets, destructive actions, or significant cost/risk. State the concrete decision, evidence, options/tradeoffs, and recommendation. Do not waive a failed requirement to declare progress. When repeated repairs produce the same failure without new evidence, stop repeating the same attempt, reassess, and escalate if resolution needs a consequential decision. Preserve completed work and commits while blocked.

If direct worker-to-worker messaging is unavailable but messaging to/from the orchestrator is available and authorized, relay the reports. If the permission for a route is missing, obtain it rather than sending anyway. Keep the orchestrator informed even when workers collaborate directly. Native chat and tool limitations must be reported honestly.

## Finish

After all milestones pass, have the adversarial reviewer and verifier reconcile their coverage against the complete specification and final head/build, including repairs and required regressions. Record any justified evidence carried forward. Confirm resolved findings, the final push, and relevant CI results. Create one PR with the concrete resulting behavior, source specification, scope exclusions, verification evidence, and remaining limitations. Do not merge it without separate authorization.

Report the PR, branch, milestone commits, reviewer/verifier conclusions, test/build identity, unresolved limitations, and any decision still requiring the user. Preserve a resumable record and leave worker chats available for follow-up; do not launch an unrelated implementation run.
