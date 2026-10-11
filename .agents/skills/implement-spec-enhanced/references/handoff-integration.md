# Integration publication

Before this stage, read the [common contract](handoffs.md),
[requirements/evidence](handoff-evidence.md), and
[transition validation](handoff-validation.md). For an occupied record or a
temporary prerequisite recovery, read [retry/carry-forward](handoff-retry.md).

### Integration

Additional fields:

- `status`: `integrated` or `failed`.
- `previous_tip`: full integration-branch commit before this merge.
- `integration_commit`: full resulting commit; record the inspected HEAD for
  a failed attempt too.
- `verification_sha256`: SHA-256 of the exact `verification.json` bytes used.

For `integrated`, both `previous_tip` and `candidate_commit` must be ancestors of
the result, verification must pass, and all integration checks must pass or have
documented evidence reuse. Capture the digest after the verifier finishes;
the validator rejects changed verdict files. A failed attempt never closes work.

An `integrated` record establishes local integration only. Remote delivery and
issue closure follow [PR delivery and issue completion](../../../../docs/agents/issue-tracker.md#pr-delivery-and-issue-completion);
keep that evidence in the ticket, outside immutable handoff records. The local
ancestry conditions above do not determine GitHub squash/rebase merge completion.

#### Publish the actual integration outcome

The merger captures the integration tip immediately before performing the merge,
then inspects the resulting checkout and prepares check evidence. Prefer a full
commit ID for `previous_tip_ref`: a branch can move during the merge. For example,
capture `$previousTip = git -C $integrationCheckout rev-parse HEAD` before merging
and put that captured value in the input. Ancestry validation cannot establish
capture timing. The writer records an already-performed integration; it performs
no merge or check execution.

Choose integration coverage from the actual combined result under
[check selection](check-scope.md). A clean fast-forward to the reviewed candidate
may reuse qualifying receipts when independently assigned requirements permit it.
Changes from the integration tip or merge resolution require affected combined
checks; reuse cannot satisfy a fresh-execution requirement.

```powershell
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/write_handoff.py integration $attempt --checkout $integrationCheckout --input $integrationInput --requirements $integrationRequirements
```

Use the coordinator's exact absolute attempt path. The input has exactly these
fields; substitute the captured commit ID and actual merger observations. This
manual-only example uses `checks: []` only when independent requirements assign
no covered automated checks. For assigned checks, use actual objects under
[requirements/evidence](handoff-evidence.md#shared-runner-check-example).

```json
{
  "actor": "merger-session",
  "status": "integrated",
  "previous_tip_ref": "0123456789abcdef0123456789abcdef01234567",
  "checks": [],
  "limits": ["Synthetic CLI checks do not demonstrate native or user acceptance"]
}
```

The helper derives schema/kind and copies ticket/candidate identity from this
attempt's `candidate.json`. It resolves the explicit `previous_tip_ref` to a full
commit and reads `integration_commit` from assessed HEAD, including for failures.
All Git operations use `--checkout` even when invoked from another checkout.
`verification_sha256` hashes the exact finished `verification.json` bytes in
this attempt, preserving whitespace and UTF-8 distinctions; it never hashes a
reserialization or a record selected from another attempt. Later verification
byte changes invalidate the standalone integration transition.

Ticket, commits, schema/kind and digest are helper-owned. Apply the common
[input/evidence/publication rules](handoffs.md#publication-contract); mismatched
record identities, invalid/non-commit references and applicable ancestry
violations fail before publication.

An `integrated` claim requires an approved candidate, passing verification,
passing or justifiably reused integration checks, and both the captured previous
tip and candidate commit as ancestors of the inspected result. For a failed
attempt supply `status: "failed"`, the captured reference and observed checks
and limits. Failure records still require a clean inspected checkout, valid
records/evidence and resolvable commit references; the validator does not impose
the successful integration's two ancestry conditions, approval or passing checks
on them. Resolve or abort an unfinished Git merge before publishing its clean
inspected state.

Valid integrated outcomes publish with exit `0` and allow the transition. Valid
failed outcomes publish with exit `2` and hold it. Invalid integrated claims,
invalid inputs/state, occupied destinations and publication failures return
`1` without a new record. Writing never closes tickets or establishes an actual
user verdict; the common publication contract governs retries and evidence quality.
