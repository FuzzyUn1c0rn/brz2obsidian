# Synthetic workflow rehearsal

Read this only when checking documentation/CLI agreement across the workflow.
Start with the [common contract](handoffs.md), [dispatch](handoff-dispatch.md),
[requirements/evidence](handoff-evidence.md), and [transition validation](handoff-validation.md);
read [retry/carry-forward](handoff-retry.md) for the recovery operations below.

### Synthetic workflow rehearsal

For a documentation/CLI agreement check, create disposable real Git repositories
under `tmp/<effort>/`: a candidate checkout, a verifier checkout at the candidate
commit, and an integration checkout. Track synthetic `ticket.md`, `spec.md`, and
`output.txt`; use local test identity with hooks/signing disabled. Run the writer
and standalone validator from outside the candidate/verifier checkout with
absolute script, attempt, checkout, and input paths. Keep inputs outside attempts.
Use the linked [candidate](handoff-candidate.md), [verification](handoff-verification.md),
and [integration](handoff-integration.md) stage inputs with actual synthetic observations; the driver owns
check execution and merges, while the writer only publishes those observations.

| Operation | Writer exit | Standalone stage/exit |
| --- | --- | --- |
| Capture base; finish focused development checks; commit stable source; run completion checks; publish candidate | 0 | candidate / 0 |
| Publish unavailable-prerequisite BLOCKED verification | 2 | verification / 2 |
| Recover prerequisite; carry candidate to assigned next attempt with false | 0 | candidate / 0; verification / 1 until fresh verdict |
| Publish fresh independent-role PASS observations | 0 | verification / 0 |
| Capture pre-merge tip; merge once; publish temporary failed integration | 2 | integration / 2 |
| Carry candidate/PASS to another assigned attempt with explicit true/rationale | 0 | verification / 0 |
| Recover check; inspect already-incorporated result; publish fresh integration | 0 | integration / 0 |
| Repeat publication or carry into an occupied destination | 1 | earlier valid records remain unchanged |

Save exact argv, working directories, stdout/stderr, exits, observations and input
bytes. Compare all earlier record/evidence bytes before and after carries/refusals;
compare carried candidate/PASS bytes, nested relative layout, unchanged absolute
references, and auxiliary receipts. Assert the final digest equals the exact new
attempt's verification bytes and the already-incorporated retry changes neither
HEAD nor commit count. Record the full historical base/pre-merge IDs and prove
both CLIs preserve assessed HEAD and clean state.

This rehearsal checks CLI/file/Git behavior. Focused CLI tests additionally cover
invalid inputs, concurrency, interruption and partial-attempt recovery. Record
material limits explicitly: synthetic roles do not demonstrate live multi-agent
execution, independent evidence judgment, native/user acceptance, remote PRs,
or managed-worktree lifecycle behavior.
For delivery timing/ownership decisions, pair protocol checks with observed
agent responses/traces and independent rubrics under
[skill behavior evaluations](../../../../docs/agents/skill-evaluations.md#delivery-lifecycle-coverage).
Scripted actions and authored verdicts remain simulated inputs, not evidence of
independent agent judgment.
