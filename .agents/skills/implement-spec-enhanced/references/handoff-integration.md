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

#### Publish the actual integration outcome

The merger captures the integration tip immediately before performing the merge,
then inspects the resulting checkout and prepares check evidence. Prefer a full
commit ID for `previous_tip_ref`: a branch can move during the merge. For example,
capture `$previousTip = git -C $integrationCheckout rev-parse HEAD` before merging
and put that captured value in the input. Ancestry validation cannot establish
capture timing. The writer records an already-performed integration; it performs
no merge or check execution.

```powershell
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/write_handoff.py integration $attempt --checkout $integrationCheckout --input $integrationInput --requirements $integrationRequirements
```

Use the coordinator's exact absolute attempt path. The input has exactly these
fields; substitute the captured commit ID and actual merger observations:

```json
{
  "actor": "merger-session",
  "status": "integrated",
  "previous_tip_ref": "0123456789abcdef0123456789abcdef01234567",
  "checks": [
    {
      "kind": "runner",
      "check_id": "pytest",
      "receipt": "C:/absolute/integration/tmp/checks/run-id/receipt.json",
      "name": "Integration acceptance tests",
      "status": "passed",
      "method": "From the assessed checkout: .venv\\Scripts\\python.exe tools/check.py run --check pytest --test tests/test_public_contract.py",
      "exit_code": 0,
      "evidence": ["logs/integration-tests.txt"]
    }
  ],
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

Keep actor, status, checks and limits explicit, including permitted empty
arrays. Check outcomes, reuse source commits and applicability rationale remain
agent judgments under [Checks and evidence reuse](handoff-evidence.md#checks-and-evidence-reuse).
Unknown/duplicate input fields and helper-owned overrides (including ticket,
commits, schema/kind and digest) are errors. Evidence paths remain absolute or
relative to the final attempt. Missing evidence, mismatched record identities,
invalid/non-commit references, dirty checkout state and applicable ancestry
violations fail before publication. Inputs and prior records remain unchanged.

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
`1` without a new record. Output names the published path separately from
permission to advance. Publication uses the same stable UTF-8 serialization
and atomic no-overwrite mechanism as candidate/verification; even identical
existing bytes cause refusal. Follow the coordinator's retry procedure instead
of editing records. Writing never closes tickets, infers user acceptance or
establishes evidence quality.
