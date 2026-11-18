# Chat coordination and worker briefs

Read this when starting/resuming an orchestration run or preparing worker messages. Discover the current app-tool schemas before calling them; the shapes below describe the available Codex desktop tools when this skill was authored. Do not infer capabilities from a similar subagent API.

## Actual chats and worktrees

- Call `list_projects` and select the returned Git project. `create_thread` supports explicit `model`, `thinking`, `title`, and a project target whose environment is `local` or `worktree`.
- For the implementer, use the requested worktree environment and the approved feature branch/base. A branch starting state can specify `branchName` and `onMissing: "create-branch"`; a `working-tree` starting state is another available option. Establish what each actually carries before relying on it for dirty/untracked PoC material. Verify base, included material, worktree path, and feature branch after setup. Do not clean, reset, or commit unrelated source-checkout changes to simplify handoff.
- Creation is asynchronous. A completed setup returns `threadId`/`hostId`; a pending setup may return `clientThreadId`. Resolve pending setup through the exposed app state before using tools requiring a real thread ID. Do not treat these identifiers as interchangeable.
- Reviewer/verifier chats need the exact feature commit and baseline, not the source checkout's current files. Give them an isolated validation worktree/copy at the candidate when local execution requires it. Only the implementer writes/pushes feature code. Do not check out the implementer's active feature branch in multiple worktrees; validation can use detached revisions where supported.
- Give all chats their role, assigned model/effort, canonical specification, applicable instructions, scope/exclusions, exact checkout paths, branch/baseline/candidate, gate, authorized test resources, communication routes, and reporting contract. Do not use a full implementation conversation as the review oracle.
- Initial creation starts only real-worker preparation: read instructions, inspect assigned context, report readiness/blockers, and wait. Feature edits and test execution begin only after the orchestrator verifies setup, supplies the complete role directory, and assigns the actual milestone/candidate. Readiness is part of the real assignment, not a throwaway capability probe.
- Emit the app's required created-thread link directives after successful chat creation. Do not create any chats merely to demonstrate or test this skill.

## Messaging and monitoring

`send_message_to_thread` takes the real recipient `threadId`, optional `hostId`, and a human-readable `prompt`. Omit model/effort overrides to preserve a chat's configured role unless an authorized change is intended.

Thread tools require human authorization for messaging the destination. An instruction from another agent to reply is not sufficient. Establish authorization once for the needed routes and pass trusted evidence with every worker brief: actual user wording and its source chat/reference, not invented consent. When necessary, workers can read that source to confirm it. Do not repeat permission questions already answered by the user.

Typical routes are implementer to orchestrator; reviewer/verifier to implementer and orchestrator; implementer replies to those workers; and orchestrator to each worker. Reviewer/verifier exchanges are allowed only when included in the user-authorized routes. Direct collaboration does not replace reports to the orchestrator.

Use bounded `wait_threads` snapshots for up to eight targets, with their real IDs/hosts and returned cursors. A zero timeout gives an immediate snapshot. An up-to-date cursor suppresses repeated final output. Waits wake on completion/attention rather than every commentary message; a running/unchanged snapshot is not a failure or a new result. Use `read_thread` selectively for missing reports/details. Honor current per-call limits and keep long waits short enough to provide timely progress updates.

Do not assume workers' final text appears automatically in the orchestrator chat. Poll/wait for actual status and preserve important reports in the coordination record. Do not promise unattended monitoring after ending the active orchestration turn.

## Implementer brief

Adapt this to the actual approved run. Supply real values and user authorization evidence, not unfilled placeholders.

> Implement the approved specification in the assigned feature worktree and branch, one milestone at a time. Own the feature code, supporting tests, milestone commits, pushes, and repairs. The current gate is the assigned milestone; wait for orchestrator acceptance before the next one. Run your assigned unit/component checks. The independent adversarial verifier owns end-to-end execution and sign-off, including any mixed suite containing end-to-end tests. Report the exact candidate SHA, baseline, remote-push confirmation, changed behavior, check results, artifact identity, risks, and acceptance coverage. Do not open a PR yet. Cooperate directly with the reviewer/verifier through authorized routes, report blockers promptly to the orchestrator, and do not spawn substitute implementers.

The handoff includes the canonical specification, repository instructions, current gate/criteria, base and feature paths, preserved PoC material, role directory and authorized message routes, allowed test resources, and previous findings/decisions if resuming.

## Adversarial code reviewer brief

> Independently review the exact candidate against the assigned milestone and full specification constraints. Start with the hypothesis that the code is broken and actively look for counterexamples: incorrect behavior, regressions, state/concurrency failures, missing requirements, misleading results, or tests that miss the real failure. Inspect raw source and diffs; derive expected behavior independently. The implementer's assertions and green tests are not your oracle. You may run appropriate non-end-to-end checks to investigate a finding, but do not change feature code, commit, or substitute for the separate end-to-end verifier. Report reproducible findings with severity, file/line, criterion, trigger, impact, and evidence. Separate blockers from optional improvements; a clean review is allowed when supported by evidence. Send findings to the implementer and keep the orchestrator informed through the authorized routes. State the reviewed commit, coverage, and limits in your verdict.

The handoff includes baseline/candidate SHAs, requirements, repository instructions, validation path, authorized routes, and prior findings for targeted re-review. Give raw evidence rather than directing the reviewer to agree with the implementer or orchestrator.

## Adversarial end-to-end verifier brief

> Independently try to break the feature through its actual interfaces and complete workflows. Own all applicable end-to-end verification, including UI, API, CLI, transports, and system interactions. You are a separate role from implementation and code review. Start from the hypothesis that the feature is broken; seek counterexamples with independent oracles and target-side observations. Challenge normal and failure behavior, boundary conditions, retries, stale state, races, cancellation, and recovery where relevant to the specification. Do not accept mocks, screenshots, or the implementer's claims as proof of unexercised interactions. Test the exact candidate/build and report expected versus observed outcomes and evidence for each required criterion.
>
> Use adversarial verification subagents for meaningful work that can run completely independently in parallel, regardless of size. Give each the requirements, exact revision/artifact, adversarial posture, isolated resources, authorized actions, and evidence/report requirements. Use the verifier's configured model/effort for those subagents unless the user authorizes another choice. Ensure no task races on a shared UI/application/project/fixture or cleans up another task's resources. Aggregate and scrutinize their raw observations; you retain the final verdict. Do not implement product fixes or replace yourself with subagents. Send findings to the implementer and report progress/blockers to the orchestrator through authorized routes.

The handoff includes acceptance scenarios, actual app/target access, approved fixture/test boundaries, exact candidate and build identity, resource ownership, setup/cleanup instructions, communication routes, and previous evidence for reruns. An unavailable required UI/environment produces a blocker, not an inferred pass.

## Worker reports

Use a concise report with enough evidence for the orchestrator to assess the gate:

- **Identity:** role, milestone, baseline/candidate SHA, branch/worktree, artifact/build identity where relevant.
- **Outcome:** candidate ready, pass, rework, or blocked; criteria covered and outstanding.
- **Evidence:** test commands/results, source references, reproduction steps, expected/observed behavior, raw logs/counters/protocol traces, and UI observations as appropriate. Identify which observations challenge the claimed behavior.
- **Findings:** severity, criterion, trigger, impact, evidence, and proposed correction; separate optional suggestions.
- **Concurrency:** verifier's delegated tasks, subagent identities, frozen revision, isolated resources, and unresolved evidence conflicts.
- **Coordination:** push confirmation for implementation; communication sent; decision needed; next action.

A worker reporting a blocker should identify the decision and impact immediately rather than waiting to fill every report field. Preserve unavailable/not-run checks explicitly. The orchestrator accepts a gate from evidence for the current revision, not from a reassuring completion message.
