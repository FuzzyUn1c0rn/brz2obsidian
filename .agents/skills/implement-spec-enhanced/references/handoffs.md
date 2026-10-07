# Structured handoffs

## Location and ownership

Use a directory for each attempt at a ticket candidate under the shared
integration checkout:
`tmp/<effort>/handoffs/<ticket>/<candidate-commit>/attempt-001/`.
The coordinator assigns the next unused attempt number for that ticket/commit.
The absolute directory path identifies the attempt; the JSON format stays at
schema version 1. Pass that exact path to every agent, including agents in other
worktrees. Temporary records and logs stay here; accepted decisions and
completion results stay in existing tickets.

| Record | Writer | Consumer |
| --- | --- | --- |
| `candidate.json` | Implementer | Verifier |
| `verification.json` | Independent verifier | Merger |
| `integration.json` | Merger | Coordinator |

Publish each record once, after its evidence is ready, then leave it immutable.
Keep work-in-progress notes elsewhere in the effort directory. A changed
candidate starts at `attempt-001` beneath its new commit. An unchanged candidate
can have further attempts as described below; keep previous records for
diagnosis. The coordinator claims/closes tickets so concurrent workers do not
edit the same bookkeeping files.

## Retry an unchanged candidate

A prerequisite becoming available or a temporary integration-check failure
resolving can justify another attempt without a code change. Record the reason
and previous/new attempt paths in the ticket. Allocate `attempt-002` (or the next
unused number) beneath the same candidate commit, leaving the earlier attempt
intact. Carry forward `candidate.json` byte for byte. Ensure its evidence still
resolves in the new directory: retain absolute evidence paths, or copy referenced
relative files with their original layout. Reassess evidence applicability
before reusing it; a new attempt does not require an empty Git commit.

- **Verification was BLOCKED:** dispatch the independent verifier at the same
  candidate commit. It checks the newly available prerequisite and any affected
  criteria, then publishes a fresh `verification.json` in the new attempt.
  Reuse unaffected evidence with the normal rationale. Preserve the earlier
  BLOCKED record in its original directory.
- **Integration failed temporarily:** carry forward the passing verification
  byte for byte, including its referenced evidence, only if it remains valid.
  Otherwise, obtain fresh verification in the new attempt. The merger inspects
  the current integration state and records the actual `previous_tip` and result
  for this attempt. If the candidate is already incorporated, rerun the affected
  checks against the current result; another merge is unnecessary. Publish a new
  `integration.json` with the digest of this attempt's verification record.

Validate each transition against the checkout actually assessed. Resume from
the explicitly selected attempt path, rather than treating an earlier failed
record as approval. A substantive repair still requires a new candidate commit
and verification. A required user verdict still comes from the user.

## Record format

All records are UTF-8 JSON objects with `schema_version: 1`, `kind`
(`candidate`, `verification`, or `integration`), `actor` (agent/session ID),
`ticket` (repository-relative path), `candidate_commit` (full Git object ID),
`checks`, and `limits` (array of material-limit strings; empty when none).
Use identical ticket and candidate identities throughout an attempt.

### Candidate

Additional fields:

- `spec`: repository-relative accepted specification path.
- `base_commit`: integration tip incorporated before final candidate checks.
- `worktree`: absolute path to the implementer's checkout.
- `owned_files`: repository-relative files or directories assigned to the worker.
- `criteria`: nonempty array of distinct acceptance criterion IDs or anchors.
  Reuse accepted presentation IDs where present; reference ticket criteria
  without copying the spec's prose.

The commit includes the completed change. Required failing checks must be fixed
before dispatch; unavailable checks remain explicit for the verifier to resolve.

### Verification

Additional fields:

- `verdict`: `PASS`, `REWORK`, or `BLOCKED`.
- `criteria`: one object for every candidate criterion, with `id`, `status`
  (`satisfied`, `failed`, or `unverified`), and `evidence` (nonempty file paths).
- `findings`: array of blocking findings, with criterion/file pointers.

The verifier is a different actor from the implementer. `PASS` requires every
criterion satisfied, every listed check passed or justifiably reused, and no
blocking findings. `REWORK` means repair is needed; `BLOCKED` means a required
prerequisite or check is unavailable. User/native acceptance required by this
ticket remains unverified until its actual verdict exists. Check coverage against the ticket,
not merely the candidate's list: omitted requirements invalidate approval.

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

## Checks and evidence reuse

Each check has `name`, `status` (`passed`, `failed`, `unavailable`, or `reused`),
`method` (exact command and working directory, or manual procedure), `exit_code`
(integer for executed commands; `null` for manual, unavailable, or reused checks), and `evidence`
(nonempty array of file paths). Paths are absolute or relative to the handoff
directory. Store output or a concise observation receipt; preserve failures.
For unavailable checks the evidence records the attempted procedure and reason.
An empty checks array is allowed when criterion evidence alone is sufficient;
the verifier still assesses all required checks from the ticket and repo docs.

For example, a command check can be recorded as:

```json
{
  "name": "Public acceptance tests",
  "status": "passed",
  "method": "From the candidate checkout: .venv\\Scripts\\python.exe -m pytest tests/test_public_contract.py",
  "exit_code": 0,
  "evidence": ["logs/public-tests.txt"]
}
```

`failed`, `unavailable`, and `reused` also require `reason`. A reused check also
requires `source_commit` (full Git ID). Record the prior evidence and explain why
the changes since that commit cannot affect the checked behavior. Candidate
checks alone do not constitute independent verification. Reuse expensive native
evidence when source inputs, generated output, renderer conditions, and relevant
requirements remain applicable. Rerun affected checks for runtime/output changes
or contradictory evidence. A ticket-closure-only commit can reuse runtime
evidence when its diff demonstrates the limited scope; user acceptance is an
actual verdict, never an inferred check.

## Validate at transitions

Run the helper with the project `.venv` interpreter from the integration checkout.
Pass the checkout actually being assessed, which may be another worktree:

```powershell
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/validate_handoff.py $attempt --stage candidate --checkout $implementationCheckout
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/validate_handoff.py $attempt --stage verification --checkout $verificationCheckout
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/validate_handoff.py $attempt --stage integration --checkout $integrationCheckout
```

`$attempt` is the absolute attempt directory. Candidate and verification stages
require a clean checkout at the candidate commit; integration requires a clean
checkout at the result. The helper reads records and Git state; it performs no
merge, test execution, or ticket edits. Exit `0` allows the transition, `1` means
invalid records or Git state, and `2` means valid records with a failing,
unavailable, or rework verdict that cannot advance. Candidate-stage unavailable
checks may proceed to a verifier, who must resolve them before `PASS`.

Validation covers format, evidence-file existence, actor separation, commit
identity/ancestry, criterion coverage within the records, and the verdict digest.
It cannot judge evidence quality, discover omitted spec requirements, or prove
that commands were run. The independent review supplies those judgments.

Use ordinary completion messages such as `candidate ready: <path> (<commit>)`,
`verification: <path> REWORK`, or `integration: <path> integrated`. Records carry
the details; the coordinator reads them when the state changes.

When changing the helper, run its self-contained CLI tests from the workspace
root; they create isolated Git repositories under `tmp/implement-spec-enhanced-tests/`:

```powershell
.venv\Scripts\python.exe -m unittest discover -s .agents/skills/implement-spec-enhanced/tests -v
```
